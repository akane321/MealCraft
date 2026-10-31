"""Capture raw Cold Storage search observations for the ingredients FairPrice lacks.

The second retailer of `docs/design/cold-storage.md`: FairPrice stays the main store, Cold Storage is searched only
for the release v2.2 ingredients that are not in `data/products/fairprice-v2-snapshot.json` (and are not water or
ice). One search per query, stored as immutable observations with the query, the time and the raw product fields,
before any matching. Matching and review happen later (`cold_storage_mapping.py`).

    python scripts/capture_cold_storage_snapshot.py             # every target not yet captured
    python scripts/capture_cold_storage_snapshot.py --query ING_CHERVIL="fresh chervil"
    python scripts/capture_cold_storage_snapshot.py --follow-up --limit 400   # second pass, see below

An ingredient's queries are the `search_again` texts of its FairPrice mapping, then its canonical name, at most 3.
The ingredient is done as soon as one query returns a product whose name holds every word of the query. Reruns skip
what is captured, so an interrupted run resumes. Requests are public GETs spaced by `--delay` seconds (at least a
second), capped by `--limit`, and the run stops at the first non-200 or unrecognised page (a captcha is one).

The follow-up pass (`--follow-up`) is for the gap ingredients that still have no `mapped` row in
`data/enrichment/cold_storage/v1/mapping.jsonl`. Per ingredient it tries up to 3 queries not yet captured: the
canonical name, a simpler shopper's form (qualifiers such as fresh/ground/dried/chopped/canned dropped, singular, the
first side of "x or y", a few Singapore names), then the mapping's untried `search_again` texts. Earlier hits do not
stop it (the reviewer rejected them); a plausible hit in this run does. The queries go breadth first (every
ingredient's first new query before any second), so the request cap cuts the least useful ones.

The product list is in the Next.js flight payload (the `self.__next_f.push([1,"..."])` strings, concatenated), after
`"initialProducts":`. Only the first 30 results come with a plain GET.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "data" / "release" / "v2.2"
FAIRPRICE_SNAPSHOT = ROOT.parent / "data" / "products" / "fairprice-v2-snapshot.json"
FAIRPRICE_MAPPING = ROOT / "data" / "enrichment" / "fairprice" / "v2" / "mapping.jsonl"
OUTPUT = ROOT / "data" / "enrichment" / "cold_storage" / "v1" / "observations.jsonl"
BASE_URL = "https://coldstorage.com.sg"
USER_AGENT = "MealCraft/0.1 academic prototype"
PARSER_VERSION = "cold-storage-capture-v1"
PUSH = re.compile(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)')
PRODUCTS_KEY = '"initialProducts":'
TOTAL = re.compile(r'"totalProducts":(\d+)')
NO_MATCH = "Sorry, we couldn't find any results for"
REQUIRED = ("productId", "name", "slug", "price", "inventoryStatus")
# Drinking water and ice come from the tap and the freezer; they are never purchased.
NOT_PURCHASED = {"ING_WATER", "ING_ICE"}
COLD_MAPPING = OUTPUT.parent / "mapping.jsonl"
MAX_QUERIES = 3
# Words a shopper leaves out; only dropped when the rest still names the same ingredient.
# ponytail: a word list, so "dried shrimp" would lose "dried" too; the plausibility check and the review catch that.
QUALIFIERS = {
    "fresh",
    "ground",
    "dried",
    "dry",
    "chopped",
    "canned",
    "minced",
    "sliced",
    "diced",
    "shredded",
    "crushed",
    "frozen",
    "raw",
    "whole",
    "condensed",
}
# Singapore shoppers' names, keyed by canonical name.
SG_NAMES = {
    "calamansi": ["limau kasturi"],
    "catfish": ["patin"],
    "chard": ["swiss chard"],
    "lye water": ["kansui"],
    "gochugaru": ["korean chilli flakes"],
    "cilantro": ["coriander leaves"],
    "half and half": ["cream"],
    "scotch bonnet pepper": ["habanero"],
}
MIN_DELAY = 1.0


class ProductSchemaDriftError(ValueError):
    """The page is neither a product list nor the site's no-match page."""


def flight(page: str) -> str:
    return "".join(json.loads(chunk) for chunk in PUSH.findall(page))


def parse_search(page: str) -> tuple[int, list[dict]]:
    """(total result count, the raw products) of a search page; no-match is (0, [])."""
    payload = flight(page)
    start = payload.find(PRODUCTS_KEY)
    if start < 0:
        if NO_MATCH in html.unescape(page):
            return 0, []
        raise ProductSchemaDriftError("page has neither initialProducts nor the no-results message")
    products, end = json.JSONDecoder().raw_decode(payload[start + len(PRODUCTS_KEY) :])
    if not isinstance(products, list) or any(
        not isinstance(item, dict) or any(key not in item for key in REQUIRED) for item in products
    ):
        raise ProductSchemaDriftError(f"initialProducts is not a list of products with {REQUIRED}")
    total = TOTAL.search(payload, start + len(PRODUCTS_KEY) + end)
    return int(total.group(1)) if total else len(products), products


def trim_product(record: dict) -> dict:
    """The raw fields the mapping needs, unparsed: the weighted pack price is worked out at export."""
    return {
        "product_id": str(record["productId"]),
        "name": record["name"],
        "slug": record["slug"],
        "price": record["price"],
        "promo_price": record.get("promoPrice"),
        "average_weight": record.get("averageWeight"),
        "in_stock": record["inventoryStatus"] == "In Stock",
        "url": f"{BASE_URL}/product/{record['slug']}",
    }


def search(query: str, timeout: float) -> tuple[int, list[dict]]:
    url = f"{BASE_URL}/search?q={urllib.parse.quote(query)}"
    request = urllib.request.Request(url, headers={"Accept": "text/html", "User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        if response.status != 200:
            raise urllib.error.HTTPError(url, response.status, "not 200", response.headers, None)
        page = response.read().decode("utf-8")
    count, products = parse_search(page)
    return count, [trim_product(item) for item in products]


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _words(text: str) -> list[str]:
    return [
        word[:-1] if len(word) > 3 and word.endswith("s") else word for word in re.findall(r"[a-z0-9]+", text.lower())
    ]


def plausible(query: str, products: list[dict]) -> bool:
    """Some product name holds every word of the query (plural 's' ignored): worth mapping, so stop searching."""
    words = _words(query)
    return bool(words) and any(all(word in " ".join(_words(p["name"])) for word in words) for p in products)


def gap_rows() -> list[dict]:
    """Every v2.2 ingredient FairPrice's snapshot lacks, commonest first."""
    priced = {f"ING_{key.upper()}" for key in json.loads(FAIRPRICE_SNAPSHOT.read_text(encoding="utf-8"))["ingredients"]}
    rows = [
        row
        for row in _jsonl(RELEASE / "ingredients.jsonl")
        if row["ingredient_id"] not in priced and row["ingredient_id"] not in NOT_PURCHASED
    ]
    rows.sort(key=lambda row: (-row.get("recipe_occurrences", 0), row["ingredient_id"]))
    return rows


def targets() -> list[tuple[str, list[str]]]:
    """(ingredient id, queries) for every gap ingredient: its FairPrice search_again texts, then the canonical name."""
    again = {row["ingredient_id"]: row.get("search_again") or [] for row in _jsonl(FAIRPRICE_MAPPING)}
    plan = []
    for row in gap_rows():
        queries = list(dict.fromkeys([*again.get(row["ingredient_id"], []), row["canonical_name"]]))
        plan.append((row["ingredient_id"], queries[:MAX_QUERIES]))
    return plan


def singular(text: str) -> str:
    head, _, last = text.rpartition(" ")
    if last.endswith(("ies", "oes")) and len(last) > 4:
        last = last[:-3] + ("y" if last.endswith("ies") else "o")
    elif last.endswith("s") and not last.endswith(("ss", "us", "is")) and len(last) > 3:
        last = last[:-1]
    return f"{head} {last}".strip()


def shopper_forms(canonical: str) -> list[str]:
    """Simpler ways a shopper would name the ingredient, most likely first; never the canonical name itself."""
    forms = []
    for part in canonical.lower().split(" or "):
        words = part.split()
        kept = " ".join([word for word in words if word not in QUALIFIERS] or words)
        forms += [kept, singular(kept)]
    forms += SG_NAMES.get(canonical.lower(), [])
    return [form for form in dict.fromkeys(forms) if form != canonical.lower()]


def follow_up_queries(canonical: str, again: list[str], tried: set[str]) -> list[str]:
    """Up to MAX_QUERIES queries not yet tried: the canonical name, a simpler form, then the mapping's search_again."""
    fresh = {}
    for query in [canonical, *shopper_forms(canonical), *again]:
        if query.lower() not in tried:
            fresh.setdefault(query.lower(), query)
    return list(fresh.values())[:MAX_QUERIES]


def follow_ups() -> list[tuple[str, list[str]]]:
    """(ingredient id, new queries) for every gap ingredient with no mapped Cold Storage row, commonest first."""
    rows = _jsonl(COLD_MAPPING) if COLD_MAPPING.exists() else []
    mapped = {row["ingredient_id"] for row in rows if row["status"] == "mapped"}
    again = {row["ingredient_id"]: row.get("search_again") or [] for row in rows}
    tried = defaultdict(set)
    for ingredient_id, query in captured()[0]:
        tried[ingredient_id].add(query.lower())
    plan = []
    for row in gap_rows():
        ingredient_id = row["ingredient_id"]
        queries = follow_up_queries(row["canonical_name"], again.get(ingredient_id, []), tried[ingredient_id])
        if ingredient_id not in mapped and queries:
            plan.append((ingredient_id, queries))
    return plan


def breadth_first(plan: list[tuple[str, list[str]]]) -> list[tuple[str, str]]:
    """Every ingredient's first query, then every second one, then every third: a request cap cuts the tail."""
    return [(i, queries[rank]) for rank in range(MAX_QUERIES) for i, queries in plan if len(queries) > rank]


def captured() -> tuple[set[tuple[str, str]], set[str]]:
    """The (ingredient, query) pairs done, and the ingredients with a plausible hit already."""
    if not OUTPUT.exists():
        return set(), set()
    rows = [row for row in _jsonl(OUTPUT) if row["status"] == "ok"]
    return (
        {(row["ingredient_id"], row["query"]) for row in rows},
        {row["ingredient_id"] for row in rows if plausible(row["query"], row["products"])},
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--delay", type=float, default=MIN_DELAY, help=f"seconds between requests, at least {MIN_DELAY}"
    )
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--limit", type=int, default=600, help="stop after this many requests")
    parser.add_argument("--query", action="append", default=[], help="ING_ID=search text, for a single search")
    parser.add_argument("--follow-up", action="store_true", help="new queries for gap ingredients with no mapped row")
    args = parser.parse_args()
    delay = max(args.delay, MIN_DELAY)

    done, hit = captured()
    if args.follow_up:
        plan, hit = follow_ups(), set()  # earlier hits were reviewed and rejected: only a new hit stops an ingredient
        todo = breadth_first(plan)
    else:
        plan = [(item.split("=", 1)[0], [item.split("=", 1)[1]]) for item in args.query] if args.query else targets()
        todo = [
            (ingredient_id, query)
            for ingredient_id, queries in plan
            if ingredient_id not in hit
            for query in queries
            if (ingredient_id, query) not in done
        ]
    print(f"{len(plan)} ingredients, {len(todo)} searches at most ({len(done)} already captured)")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    requests, failures, finished = 0, 0, set(hit)
    with OUTPUT.open("a", encoding="utf-8", newline="\n") as handle:
        for ingredient_id, query in todo:
            if ingredient_id in finished:
                continue
            if requests >= args.limit:
                print(f"request cap {args.limit} reached; rerun to resume")
                break
            row = {"ingredient_id": ingredient_id, "query": query, "parser_version": PARSER_VERSION}
            stop = None
            try:
                count, products = search(query, args.timeout)
                row.update(status="ok", result_count=count, products=products)
                failures = 0
                if plausible(query, products):
                    finished.add(ingredient_id)
            except (urllib.error.HTTPError, ProductSchemaDriftError) as error:
                row.update(status="error", error=f"{type(error).__name__}: {error}")
                stop = f"Stopping at the first non-200 or unrecognised page: {row['error']}"
            except Exception as error:  # noqa: BLE001 - every failure is recorded, then counted
                row.update(status="error", error=f"{type(error).__name__}: {error}")
                failures += 1
                if failures >= 3:
                    stop = f"Three consecutive failures; stopping: {row['error']}"
            requests += 1
            row["fetched_at"] = datetime.now(UTC).isoformat(timespec="seconds")
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()
            if requests % 25 == 0 or row["status"] == "error":
                print(f"[{requests}] {ingredient_id} {query!r} {row['status']} {row.get('error', '')}", flush=True)
            if stop:
                sys.exit(stop)
            time.sleep(delay)
    print(f"done: {requests} requests")


if __name__ == "__main__":
    main()
