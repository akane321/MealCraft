"""Capture raw RedMart search observations for the ingredients neither FairPrice nor Cold Storage prices.

The third retailer of `docs/design/redmart.md`: RedMart (Lazada Singapore's grocery store) is searched only for the
release v2.2 ingredients that are in neither `data/products/fairprice-v2-snapshot.json` nor
`data/products/cold-storage-v1-snapshot.json` (and are not water or ice). One search per query, stored as immutable
observations with the query, the time and the raw product fields, before any matching. Matching and review happen
later (`redmart_mapping.py`).

    python scripts/capture_redmart_snapshot.py             # every target not yet captured
    python scripts/capture_redmart_snapshot.py --query ING_CHERVIL="fresh chervil"

An ingredient's queries are its canonical name, a simpler shopper's form (as in the Cold Storage follow-up), then the
`search_again` texts of its FairPrice and Cold Storage mappings, at most 3. Page 2 is read only when page 1 has no
RedMart item. The ingredient is done as soon as one query returns a RedMart product whose name holds every word of
the query. Reruns skip what is captured, so an interrupted run resumes. Requests are public GETs of the one search
endpoint, spaced by `--delay` seconds (at least a second), capped by `--limit`, and the run stops at the first
non-200, redirect (a login is one) or unrecognised page (a captcha or punish page is one). Nothing is bypassed.
A 404 is not a stop: Lazada has no such tag, so it is recorded as a `no_tag` row (no products) and the run goes on.

The search covers all of Lazada: only items sold by RedMart are kept (`sellerName`, `sellerId` or the `Redmart` icon).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from capture_cold_storage_snapshot import MIN_DELAY, NOT_PURCHASED, _jsonl, plausible, shopper_forms

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "data" / "release" / "v2.2"
PRODUCTS = ROOT.parent / "data" / "products"
FAIRPRICE_SNAPSHOT = PRODUCTS / "fairprice-v2-snapshot.json"
COLD_SNAPSHOT = PRODUCTS / "cold-storage-v1-snapshot.json"
FAIRPRICE_MAPPING = ROOT / "data" / "enrichment" / "fairprice" / "v2" / "mapping.jsonl"
COLD_MAPPING = ROOT / "data" / "enrichment" / "cold_storage" / "v1" / "mapping.jsonl"
OUTPUT = ROOT / "data" / "enrichment" / "redmart" / "v1" / "observations.jsonl"
BASE_URL = "https://www.lazada.sg"
USER_AGENT = "MealCraft/0.1 academic prototype"
PARSER_VERSION = "redmart-capture-v1"
SELLER_ID = "1000008313"
PAGE_SIZE = 40
MAX_QUERIES = 3
REQUIRED = ("itemId", "name", "price", "inStock", "itemUrl")
DONE_STATUSES = ("ok", "no_tag")  # no_tag: Lazada answered 404, it has no such tag
CHALLENGE = re.compile(r"punish|captcha|x5sec", re.IGNORECASE)


class ProductSchemaDriftError(ValueError):
    """The response is neither a RedMart-bearing product list nor an empty one."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # a redirect (a login, a challenge) is a stop, never followed
        return None


def parse_search(body: str) -> tuple[int, list[dict]]:
    """(total result count over all of Lazada, the raw items) of a search response; an empty result is (0, [])."""
    try:
        data = json.loads(body)
    except ValueError:
        data = None
    if not isinstance(data, dict):
        marker = CHALLENGE.search(body)
        raise ProductSchemaDriftError(f"not JSON{f' (challenge marker {marker.group(0)!r})' if marker else ''}")
    mods = data.get("mods")
    items = mods.get("listItems") if isinstance(mods, dict) else None
    info = data.get("mainInfo") if isinstance(data.get("mainInfo"), dict) else {}
    total = int(info.get("totalResults") or 0)
    # Only a listItems list is a result, an empty one included; `mods` without it is drift, as the live adapter has it.
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise ProductSchemaDriftError("response has no mods.listItems list")
    return total or len(items), items


def is_redmart(item: dict) -> bool:
    icons = item.get("icons") or []
    return (
        item.get("sellerName") == "RedMart"
        or str(item.get("sellerId")) == SELLER_ID
        or any(isinstance(icon, dict) and icon.get("bizType") == "Redmart" for icon in icons)
    )


def trim_product(item: dict) -> dict:
    """The raw fields the mapping needs, unparsed: the pack size is only in the name and is read at review."""
    missing = [key for key in REQUIRED if key not in item]
    if missing:
        raise ProductSchemaDriftError(f"RedMart item without {missing}")
    try:
        price = float(item["price"])
        original = float(item["originalPrice"]) if item.get("originalPrice") else None
    except (TypeError, ValueError) as error:
        raise ProductSchemaDriftError(f"RedMart item with a price of {item['price']!r}") from error
    if not isinstance(item["inStock"], bool):
        raise ProductSchemaDriftError(f"RedMart item with a stock flag of {item['inStock']!r}")
    url = str(item["itemUrl"])
    return {
        "product_id": str(item["itemId"]),
        "sku_id": str(item["skuId"]) if item.get("skuId") else None,
        "name": item["name"],
        "brand": item.get("brandName") or None,
        "price": price,
        "original_price": original,
        "in_stock": item["inStock"],
        "url": f"https:{url}" if url.startswith("//") else url,
        "image": item.get("image"),
    }


def search_url(query: str, page: int) -> str:
    slug = urllib.parse.quote(query.lower().replace(" ", "-"), safe="-")
    return f"{BASE_URL}/tag/{slug}/?ajax=true&q={urllib.parse.quote(query)}&page={page}"


def search(query: str, page: int, timeout: float, opener=None) -> tuple[int, list[dict]]:
    url = search_url(query, page)
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    opener = opener or urllib.request.build_opener(_NoRedirect)
    with opener.open(request, timeout=timeout) as response:
        if response.status != 200:
            raise urllib.error.HTTPError(url, response.status, "not 200", response.headers, None)
        body = response.read().decode("utf-8")
    total, items = parse_search(body)
    return total, [trim_product(item) for item in items if is_redmart(item)]


def _priced_by(path: Path) -> set[str]:
    return {f"ING_{key.upper()}" for key in json.loads(path.read_text(encoding="utf-8"))["ingredients"]}


def gap_rows() -> list[dict]:
    """Every v2.2 ingredient neither FairPrice's nor Cold Storage's snapshot prices, commonest first."""
    priced = _priced_by(FAIRPRICE_SNAPSHOT) | _priced_by(COLD_SNAPSHOT) | NOT_PURCHASED
    rows = [row for row in _jsonl(RELEASE / "ingredients.jsonl") if row["ingredient_id"] not in priced]
    rows.sort(key=lambda row: (-row.get("recipe_occurrences", 0), row["ingredient_id"]))
    return rows


def queries_for(canonical: str, again: list[str]) -> list[str]:
    """The canonical name, one simpler shopper's form, then the other stores' search_again texts: at most 3."""
    forms = shopper_forms(canonical)
    fresh = {}
    for query in [canonical, *forms[:1], *again]:
        fresh.setdefault(query.lower(), query)
    return list(fresh.values())[:MAX_QUERIES]


def targets() -> list[tuple[str, list[str]]]:
    """(ingredient id, queries) for every gap ingredient."""
    again: dict[str, list[str]] = {}
    for path in (FAIRPRICE_MAPPING, COLD_MAPPING):
        if path.exists():
            for row in _jsonl(path):
                again.setdefault(row["ingredient_id"], []).extend(row.get("search_again") or [])
    return [
        (row["ingredient_id"], queries_for(row["canonical_name"], again.get(row["ingredient_id"], [])))
        for row in gap_rows()
    ]


def captured() -> tuple[dict[tuple[str, str, int], dict], set[str]]:
    """The ok and no_tag rows by (ingredient, query, page), and the ingredients with a plausible RedMart hit."""
    if not OUTPUT.exists():
        return {}, set()
    rows = [row for row in _jsonl(OUTPUT) if row["status"] in DONE_STATUSES]
    return (
        {(row["ingredient_id"], row["query"], row.get("page", 1)): row for row in rows},
        {row["ingredient_id"] for row in rows if plausible(row["query"], row["products"])},
    )


def needs_page_two(row: dict) -> bool:
    """Page 1 had no RedMart item although Lazada has more results than one page holds."""
    return not row["products"] and row["result_count"] > PAGE_SIZE


def run(plan, done, finished, handle, *, opener=None, limit=500, delay=MIN_DELAY, timeout=20.0, sleep=time.sleep):
    """Search the plan, appending one row per request to `handle`. Returns (requests, why it stopped or None).

    A 404 means Lazada has no such tag: a no_tag row, and on. Any other failure (403, 429, 5xx, a redirect, a
    challenge page) is recorded as an error row and stops the run.
    """
    requests = 0
    for ingredient_id, queries in plan:
        for query in queries:
            if ingredient_id in finished:
                break
            page = 1
            while page <= 2 and ingredient_id not in finished:
                row = done.get((ingredient_id, query, page))
                if row is None:
                    if requests >= limit:
                        return requests, f"request cap {limit} reached; rerun to resume"
                    row = {
                        "ingredient_id": ingredient_id,
                        "query": query,
                        "page": page,
                        "parser_version": PARSER_VERSION,
                    }
                    stop = None
                    try:
                        count, products = search(query, page, timeout, opener)
                        row.update(status="ok", result_count=count, products=products)
                    except urllib.error.HTTPError as error:
                        if error.code == 404:
                            row.update(status="no_tag", result_count=0, products=[])
                        else:
                            row.update(status="error", error=f"{type(error).__name__}: {error}")
                            stop = row["error"]
                    except Exception as error:  # noqa: BLE001 - the first failure of any kind is recorded, then stops
                        row.update(status="error", error=f"{type(error).__name__}: {error}")
                        stop = row["error"]
                    requests += 1
                    row["fetched_at"] = datetime.now(UTC).isoformat(timespec="seconds")
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                    handle.flush()
                    if requests % 25 == 0 or stop:
                        print(f"[{requests}] {ingredient_id} {query!r} p{page} {row['status']}", flush=True)
                    if stop:
                        return requests, f"Stopping at the first non-200 or unrecognised response: {stop}"
                    sleep(delay)
                done[(ingredient_id, query, page)] = row
                if plausible(query, row["products"]):
                    finished.add(ingredient_id)
                page = page + 1 if page == 1 and needs_page_two(row) else 3
    return requests, None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--delay", type=float, default=MIN_DELAY, help=f"seconds between requests, at least {MIN_DELAY}"
    )
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--limit", type=int, default=500, help="stop after this many requests")
    parser.add_argument("--query", action="append", default=[], help="ING_ID=search text, for a single search")
    args = parser.parse_args()

    done, finished = captured()
    plan = [(item.split("=", 1)[0], [item.split("=", 1)[1]]) for item in args.query] if args.query else targets()
    print(f"{len(plan)} ingredients, {sum(len(q) for _, q in plan)} queries at most ({len(done)} already captured)")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("a", encoding="utf-8", newline="\n") as handle:
        requests, stopped = run(
            plan, done, finished, handle, limit=args.limit, delay=max(args.delay, MIN_DELAY), timeout=args.timeout
        )
    if stopped and not stopped.startswith("request cap"):
        sys.exit(f"{stopped} (after {requests} requests)")
    print(f"{stopped or 'done'}: {requests} requests")


if __name__ == "__main__":
    main()
