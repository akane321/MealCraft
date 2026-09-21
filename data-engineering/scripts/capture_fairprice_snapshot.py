"""Capture raw FairPrice search observations for the release v2 ingredients.

This is the first step of the ingredient-product mapping
(`docs/design/fairprice-product-grounding.md`): one search per ingredient,
stored as immutable observations with the query, the time and the raw product
fields, before any matching. Matching and review happen later, on this file.

    python scripts/capture_fairprice_snapshot.py              # every ingredient not yet captured
    python scripts/capture_fairprice_snapshot.py --query ING_SCALLION="spring onion"
    python scripts/capture_fairprice_snapshot.py --follow-ups 2   # search_again texts of unavailable mappings

Reruns skip (ingredient, query) pairs already captured, so an interrupted run
resumes. Requests are spaced by `--delay` seconds and the run stops after three
consecutive failures rather than hammering a site that is refusing it.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "data" / "release" / "v2.1"  # the mapping covers v2 and v2.1 ingredients
OUTPUT = ROOT / "data" / "enrichment" / "fairprice" / "v2" / "observations.jsonl"
BASE_URL = "https://www.fairprice.com.sg"
USER_AGENT = "MealCraft/0.1 academic prototype"
NEXT_DATA = re.compile(r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)
PARSER_VERSION = "fairprice-capture-v1"
# Drinking water and ice come from the tap and the freezer; they are recorded as
# deliberately not purchased in the mapping instead of being searched.
NOT_PURCHASED = {"ING_WATER", "ING_ICE"}


def category_path(category: dict | None) -> list[str]:
    names = []
    while isinstance(category, dict):
        names.append(category.get("name"))
        category = category.get("parentCategory")
    return [name for name in reversed(names) if name]


def trim_product(record: dict) -> dict:
    """The raw fields the mapping needs, unparsed, so package parsing can be re-run later."""
    metadata = record.get("metaData") or {}
    store = (record.get("storeSpecificData") or [{}])[0] or {}
    return {
        "product_id": str(record.get("clientItemId") or record.get("id")),
        "name": record.get("name"),
        "brand": (record.get("brand") or {}).get("name"),
        "category_path": category_path(record.get("primaryCategory")),
        "display_unit": metadata.get("DisplayUnit"),
        "unit_of_weight": metadata.get("Unit Of Weight"),
        "unit_of_measurement": metadata.get("Unit Of Measurement"),
        "sap_name": metadata.get("SAP Product Name"),
        "sold_by_weight": record.get("soldByWeight"),
        "final_price": record.get("final_price"),
        "regular_price": store.get("mrp"),
        "discount": store.get("discount"),
        "in_stock": record.get("has_stock"),
        "url": f"{BASE_URL}/product/{record.get('slug')}",
    }


def search(query: str, timeout: float) -> tuple[int | None, list[dict]]:
    url = f"{BASE_URL}/product-listing?" + urllib.parse.urlencode({"pageType": "search", "url": query})
    request = urllib.request.Request(url, headers={"Accept": "text/html", "User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        html = response.read().decode("utf-8")
    match = NEXT_DATA.search(html)
    if match is None:
        raise ValueError("page has no __NEXT_DATA__")
    data = json.loads(match.group(1))["props"]["pageProps"]["data"]["data"]
    return data.get("count"), [trim_product(item) for item in data.get("product") or []]


def ingredients_by_use() -> list[tuple[str, str]]:
    names = {}
    for line in (RELEASE / "ingredients.jsonl").read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        names[record["ingredient_id"]] = record["canonical_name"]
    uses = Counter()
    for line in (RELEASE / "recipes.jsonl").read_text(encoding="utf-8").splitlines():
        uses.update({item["canonical_ingredient_id"] for item in json.loads(line)["ingredients"]})
    return sorted(names.items(), key=lambda item: (-uses[item[0]], item[0]))


def captured() -> set[tuple[str, str]]:
    if not OUTPUT.exists():
        return set()
    rows = (json.loads(line) for line in OUTPUT.read_text(encoding="utf-8").splitlines() if line.strip())
    return {(row["ingredient_id"], row["query"]) for row in rows if row["status"] == "ok"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--delay", type=float, default=3.0)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--limit", type=int, default=None, help="stop after this many requests")
    parser.add_argument("--query", action="append", default=[], help="ING_ID=search text, for a follow-up search")
    parser.add_argument("--follow-ups", type=int, default=0, help="search N search_again texts per unavailable")
    args = parser.parse_args()

    if args.follow_ups:
        mapping = OUTPUT.parent / "mapping.jsonl"
        rows = [json.loads(line) for line in mapping.read_text(encoding="utf-8").splitlines() if line.strip()]
        plan = [
            (row["ingredient_id"], query)
            for row in rows
            if row["status"] == "unavailable"
            for query in (row.get("search_again") or [])[: args.follow_ups]
        ]
    elif args.query:
        plan = [tuple(item.split("=", 1)) for item in args.query]
    else:
        plan = [
            (ingredient_id, name) for ingredient_id, name in ingredients_by_use() if ingredient_id not in NOT_PURCHASED
        ]
    done = captured()
    todo = [(ingredient_id, query) for ingredient_id, query in plan if (ingredient_id, query) not in done]
    print(f"{len(todo)} searches to run ({len(plan) - len(todo)} already captured)")
    if args.limit is not None:
        todo = todo[: args.limit]

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    failures = 0
    with OUTPUT.open("a", encoding="utf-8") as handle:
        for index, (ingredient_id, query) in enumerate(todo, start=1):
            row = {"ingredient_id": ingredient_id, "query": query, "parser_version": PARSER_VERSION}
            try:
                count, products = search(query, args.timeout)
                row.update(status="ok", result_count=count, products=products)
                failures = 0
            except Exception as error:  # noqa: BLE001 - every failure is recorded, then counted
                row.update(status="error", error=f"{type(error).__name__}: {error}")
                failures += 1
            row["fetched_at"] = datetime.now(UTC).isoformat(timespec="seconds")
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()
            if index % 25 == 0 or row["status"] == "error":
                print(f"[{index}/{len(todo)}] {ingredient_id} {row['status']} {row.get('error', '')}", flush=True)
            if failures >= 3:
                sys.exit("Three consecutive failures; stopping. Rerun later to resume.")
            time.sleep(args.delay)
    print("done")


if __name__ == "__main__":
    main()
