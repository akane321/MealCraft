"""Rank the ingredients no store prices yet and prepare the FairPrice follow-up review (A2).

The v3 mapping stays frozen: `data/products/fairprice-v2-snapshot.json` is not read for writing here and nothing in
this script writes under `data/products/`. The output is a worklist and review packets under a directory you choose
(default `data/review/fairprice-gaps/`, not committed). Where the candidates a person confirms are stored is still
to be decided with the owner; nothing here depends on it.

    python scripts/fairprice_gaps.py rank [--top 120]        # worklist.csv: unpriced ingredients, most used first
    python scripts/fairprice_gaps.py packet --top 120        # packet-<i>.jsonl for the AI proposer / the reviewer
    python scripts/fairprice_gaps.py summary                 # the numbers the coverage report starts from

An ingredient is *priced* when some layer (FairPrice, Cold Storage, RedMart, the hand-recorded sheet) maps it to a
product that is in stock, the same rule the backend's `price_coverage.priced` applies. Water and ice are not
purchased and never appear. Ingredients are ranked by the number of distinct release recipes that use them, counted
from `recipes.jsonl` (the `recipe_occurrences` field of `ingredients.jsonl` does not agree with it and is not used),
so the first rows are the ones whose pricing unlocks the most recipes.

A packet line carries everything a reviewer needs to judge a FairPrice candidate without opening the site: the
ingredient, a few recipe lines, what the FairPrice mapping said about it before, and every product any capture
returned for it (the v2 observations plus any follow-up capture passed with `--observations`).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT.parent
RELEASE = ROOT / "data" / "release" / "v3"
PRODUCTS = REPOSITORY / "data" / "products"
FAIRPRICE_MAPPING = ROOT / "data" / "enrichment" / "fairprice" / "v2" / "mapping.jsonl"
FAIRPRICE_OBSERVATIONS = ROOT / "data" / "enrichment" / "fairprice" / "v2" / "observations.jsonl"
OUTPUT = ROOT / "data" / "review" / "fairprice-gaps"
# The fill order of the backend (`app.planning.retailers`); the hand-recorded layer's export may not exist yet.
LAYERS = (
    ("fairprice", "fairprice-v2-snapshot.json"),
    ("cold_storage", "cold-storage-v1-snapshot.json"),
    ("redmart", "redmart-v1-snapshot.json"),
    ("manual", "manual-v1-snapshot.json"),
)
NOT_PURCHASED = {"ING_WATER", "ING_ICE"}
RECIPE_LINES = 4


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def runtime_name(ingredient_id: str) -> str:
    """The key the snapshots use: the catalog's normalized name, which is the id without `ING_`, lower-cased."""
    return ingredient_id.removeprefix("ING_").lower()


def priced_names(mapping: dict[str, dict]) -> set[str]:
    """Ingredients a snapshot can fill: mapped, with at least one product in stock."""
    return {
        name
        for name, entry in mapping.items()
        if entry.get("status", "mapped") == "mapped" and any(p.get("in_stock", True) for p in entry.get("products", ()))
    }


def load_layers(products: Path = PRODUCTS) -> dict[str, set[str]]:
    """The set of ingredient names each layer prices; a layer whose file is absent prices nothing."""
    layers: dict[str, set[str]] = {}
    for layer, filename in LAYERS:
        path = products / filename
        layers[layer] = (
            priced_names(json.loads(path.read_text(encoding="utf-8"))["ingredients"]) if path.exists() else set()
        )
    return layers


def release_ingredients(release: Path = RELEASE) -> list[dict]:
    return read_jsonl(release / "ingredients.jsonl")


def recipe_usage(release: Path = RELEASE) -> dict[str, int]:
    """Distinct recipes that use each ingredient, counted from the recipes themselves."""
    counts: dict[str, int] = defaultdict(int)
    for recipe in read_jsonl(release / "recipes.jsonl"):
        for ingredient_id in {item["canonical_ingredient_id"] for item in recipe["ingredients"]}:
            counts[ingredient_id] += 1
    return counts


def unpriced(ingredients: list[dict], layers: dict[str, set[str]], usage: dict[str, int]) -> list[dict]:
    """The bought ingredients no layer prices, most used first (ties by id, so the order is stable)."""
    covered = set().union(*layers.values()) if layers else set()
    rows = [
        {
            "ingredient_id": row["ingredient_id"],
            "canonical_name": row["canonical_name"],
            "recipes": usage.get(row["ingredient_id"], 0),
        }
        for row in ingredients
        if row["ingredient_id"] not in NOT_PURCHASED and runtime_name(row["ingredient_id"]) not in covered
    ]
    return sorted(rows, key=lambda row: (-row["recipes"], row["ingredient_id"]))


def coverage(ingredients: list[dict], layers: dict[str, set[str]]) -> dict:
    """Ingredient-level coverage, each layer counted only for what the earlier ones do not price."""
    bought = [row for row in ingredients if row["ingredient_id"] not in NOT_PURCHASED]
    remaining = {runtime_name(row["ingredient_id"]) for row in bought}
    by_layer, running = {}, 0
    for layer, _ in LAYERS:
        hit = remaining & layers.get(layer, set())
        by_layer[layer] = len(hit)
        remaining -= hit
        running += len(hit)
    total = len(bought)
    return {
        "bought_ingredients": total,
        "priced": running,
        "share": round(running / total, 4) if total else 0.0,
        "by_layer": by_layer,
        "unpriced": total - running,
    }


def cumulative_share(rows: list[dict], total_recipe_uses: int) -> list[float]:
    """For each ranked row, the share of all unpriced recipe-uses covered by this row and the ones above it."""
    running, shares = 0, []
    for row in rows:
        running += row["recipes"]
        shares.append(round(running / total_recipe_uses, 4) if total_recipe_uses else 0.0)
    return shares


def fairprice_history(path: Path = FAIRPRICE_MAPPING) -> dict[str, dict]:
    """What the v2 FairPrice review already said about an ingredient (status, rejected products, search ideas)."""
    if not path.exists():
        return {}
    return {row["ingredient_id"]: row for row in read_jsonl(path)}


def observed_products(*paths: Path) -> dict[str, dict[str, dict]]:
    """Every product any capture returned per ingredient, keyed by product id.

    Within one file the first sighting wins (its search rank is kept); a product seen again in a later file is replaced
    by that file's record, so a newer capture's price and stock override an older one's.
    """
    products: dict[str, dict[str, dict]] = defaultdict(dict)
    for path in paths:
        if not path.exists():
            continue
        seen: dict[str, dict[str, dict]] = defaultdict(dict)
        for row in read_jsonl(path):
            if row.get("status") != "ok":
                continue
            for rank, product in enumerate(row["products"], start=1):
                seen[row["ingredient_id"]].setdefault(
                    product["product_id"],
                    dict(product, query=row["query"], rank=rank, fetched_at=row["fetched_at"]),
                )
        for ingredient_id, found in seen.items():
            products[ingredient_id].update(found)
    return products


def recipe_lines(release: Path, wanted: set[str]) -> dict[str, list[str]]:
    lines: dict[str, list[str]] = defaultdict(list)
    for recipe in read_jsonl(release / "recipes.jsonl"):
        for item in recipe["ingredients"]:
            bucket = lines[item["canonical_ingredient_id"]]
            if item["canonical_ingredient_id"] in wanted and len(bucket) < RECIPE_LINES:
                if item["original_text"] not in bucket:
                    bucket.append(item["original_text"])
    return lines


CANDIDATE_KEYS = (
    "product_id",
    "name",
    "brand",
    "category_path",
    "display_unit",
    "unit_of_weight",
    "sold_by_weight",
    "final_price",
    "in_stock",
    "url",
    "query",
)


def build_packets(
    rows: list[dict],
    ingredients: dict[str, dict],
    history: dict[str, dict],
    products: dict[str, dict[str, dict]],
    lines: dict[str, list[str]],
) -> list[dict]:
    packets = []
    for row in rows:
        ingredient_id = row["ingredient_id"]
        record = ingredients[ingredient_id]
        form = (record.get("forms") or {}).get(ingredient_id) or {}
        past = history.get(ingredient_id, {})
        previously_rejected = {item["product_id"]: item["reason"] for item in past.get("rejected") or []}
        candidates = [
            dict(
                {key: product.get(key) for key in CANDIDATE_KEYS},
                previously_rejected=previously_rejected.get(product_id),
            )
            for product_id, product in products.get(ingredient_id, {}).items()
        ]
        packets.append(
            {
                "ingredient_id": ingredient_id,
                "canonical_name": record["canonical_name"],
                "recipes": row["recipes"],
                "nutrition_form": form.get("nutrition_form"),
                "unit_grams": form.get("unit_grams", []),
                "recipe_lines": lines.get(ingredient_id, []),
                "previous_status": past.get("status"),
                "previous_notes": past.get("notes"),
                "search_again": past.get("search_again", []),
                "candidates": candidates,
            }
        )
    return packets


def write_worklist(rows: list[dict], total_uses: int, out: Path) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    path = out / "worklist.csv"
    shares = cumulative_share(rows, total_uses)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["rank", "ingredient_id", "canonical_name", "recipes", "cumulative_share_of_unpriced_uses"])
        for rank, (row, share) in enumerate(zip(rows, shares, strict=True), start=1):
            writer.writerow([rank, row["ingredient_id"], row["canonical_name"], row["recipes"], share])
    return path


def write_packets(packets: list[dict], shards: int, out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    for stale in out.glob("packet-*.jsonl"):  # a rerun with fewer shards must not leave old ones behind
        stale.unlink()
    paths = []
    for shard in range(shards):
        path = out / f"packet-{shard + 1}.jsonl"
        with path.open("w", encoding="utf-8") as handle:
            for packet in packets[shard::shards]:
                handle.write(json.dumps(packet, ensure_ascii=False) + "\n")
        paths.append(path)
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("rank", "packet", "summary"):
        sub = commands.add_parser(name)
        sub.add_argument("--release", type=Path, default=RELEASE)
        sub.add_argument("--products", type=Path, default=PRODUCTS)
        sub.add_argument("--out", type=Path, default=OUTPUT)
        if name != "summary":
            sub.add_argument("--top", type=int, default=120)
        if name == "packet":
            sub.add_argument("--shards", type=int, default=4)
            sub.add_argument("--observations", type=Path, nargs="*", default=[], help="follow-up captures to include")
    args = parser.parse_args(argv)

    ingredients = release_ingredients(args.release)
    layers = load_layers(args.products)
    if args.command == "summary":
        print(json.dumps(coverage(ingredients, layers), indent=1))
        return 0
    rows = unpriced(ingredients, layers, recipe_usage(args.release))
    total_uses = sum(row["recipes"] for row in rows)
    top = rows[: args.top]
    if args.command == "rank":
        path = write_worklist(top, total_uses, args.out)
        print(f"{len(rows)} unpriced ingredients; top {len(top)} written to {path}")
        return 0
    by_id = {row["ingredient_id"]: row for row in ingredients}
    products = observed_products(FAIRPRICE_OBSERVATIONS, *args.observations)
    packets = build_packets(
        top,
        by_id,
        fairprice_history(),
        products,
        recipe_lines(args.release, {row["ingredient_id"] for row in top}),
    )
    paths = write_packets(packets, args.shards, args.out)
    print(f"{len(packets)} ingredients in {len(paths)} packets under {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
