"""Propose, check and merge the release v2 ingredient-to-FairPrice-product mapping.

Works on the observations written by `capture_fairprice_snapshot.py`:

    python scripts/fairprice_mapping.py packet --shards 8     # data/review/fairprice/packet-<i>.jsonl
    python scripts/fairprice_mapping.py validate FILE...       # check proposals, print problems
    python scripts/fairprice_mapping.py merge FILE...          # write data/enrichment/fairprice/v2/mapping.jsonl
    python scripts/fairprice_mapping.py export                 # write data/products/fairprice-v2-snapshot.json
    python scripts/fairprice_mapping.py sample --size 40       # the owner's review sample, fixed seed
    python scripts/fairprice_mapping.py record VERDICTS.jsonl  # record the owner's verdicts

A packet line gives one ingredient with what a reviewer needs to choose: its
name and nutrition form, the gram weights of its common units, a few recipe
lines that use it, and every product its searches returned. A proposal line
answers it (fields below). Nothing is accepted without passing `validate`, and
every accepted line keeps `review_status = "proposed"` until the owner's sampled
review records otherwise (`docs/design/fairprice-product-grounding.md`).

Proposal fields:

- `ingredient_id`, `status`: `mapped`, `not_purchased` (water, ice), or
  `unavailable` (no product in the observations is a fair purchase for it).
- `selected`: for `mapped`, one or more products that are a fair purchase, each
  with `product_id`, `package_grams` (the package expressed in grams of this
  ingredient) and `package_grams_basis` (how: printed weight, volume x density,
  count x grams per piece).
- `rejected`: near-name products that must not be bought for it, each with
  `product_id` and `reason` (wrong food, wrong form, flavoured variant, ...).
- `search_again`: for `unavailable`, other search texts worth trying.
- `confidence` (0-1), `notes`, `enriched_by`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "data" / "release" / "v2.1"  # the mapping covers v2 and v2.1 ingredients
SNAPSHOT = ROOT / "data" / "enrichment" / "fairprice" / "v2"
OBSERVATIONS = SNAPSHOT / "observations.jsonl"
MAPPING = SNAPSHOT / "mapping.jsonl"
PACKETS = ROOT / "data" / "review" / "fairprice"
RUNTIME = ROOT.parent / "data" / "products" / "fairprice-v2-snapshot.json"
SAMPLE = PACKETS / "review-sample.json"  # redrawable from the seed, so not committed
REVIEW = ROOT / "docs" / "fairprice-v2-sampled-review.json"  # the owner's judgement, committed
DEFAULT_SEED = 20260921
VERDICTS = {"accepted", "corrected"}
# Below this a mapping is a substitute or a rough yield estimate; the runtime leaves it unpriced.
MIN_CONFIDENCE = 0.6
NOT_PURCHASED = {"ING_WATER", "ING_ICE"}
STATUSES = {"mapped", "not_purchased", "unavailable"}
SAMPLE_LINES = 4


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def observed_products() -> dict[str, dict[str, dict]]:
    """Per ingredient, every product any of its searches returned, keyed by product id."""
    products: dict[str, dict[str, dict]] = defaultdict(dict)
    for row in _jsonl(OBSERVATIONS):
        if row["status"] != "ok":
            continue
        for rank, product in enumerate(row["products"], start=1):
            products[row["ingredient_id"]].setdefault(
                product["product_id"], dict(product, query=row["query"], rank=rank, fetched_at=row["fetched_at"])
            )
    return products


def build_packets(shards: int, unavailable: bool = False) -> None:
    ingredients = {row["ingredient_id"]: row for row in _jsonl(RELEASE / "ingredients.jsonl")}
    lines: dict[str, list[str]] = defaultdict(list)
    for recipe in _jsonl(RELEASE / "recipes.jsonl"):
        for item in recipe["ingredients"]:
            bucket = lines[item["canonical_ingredient_id"]]
            if len(bucket) < SAMPLE_LINES and item["original_text"] not in bucket:
                bucket.append(item["original_text"])
    products = observed_products()
    mapping = _jsonl(MAPPING) if MAPPING.exists() else []
    # A second look after follow-up searches: only what is still unavailable is repacked.
    done = {row["ingredient_id"] for row in mapping if not (unavailable and row["status"] == "unavailable")}
    searched = {row["ingredient_id"] for row in _jsonl(OBSERVATIONS) if row["status"] == "ok"} | NOT_PURCHASED
    todo = [ingredient_id for ingredient_id in ingredients if ingredient_id not in done and ingredient_id in searched]
    PACKETS.mkdir(parents=True, exist_ok=True)
    for shard in range(shards):
        with (PACKETS / f"packet-{shard + 1}.jsonl").open("w", encoding="utf-8") as handle:
            for ingredient_id in todo[shard::shards]:
                record = ingredients[ingredient_id]
                form = (record.get("forms") or {}).get(ingredient_id) or {}
                candidates = [
                    {
                        key: product[key]
                        for key in (
                            "product_id",
                            "name",
                            "brand",
                            "category_path",
                            "display_unit",
                            "unit_of_weight",
                            "sap_name",
                            "sold_by_weight",
                            "final_price",
                            "in_stock",
                            "query",
                        )
                    }
                    for product in products.get(ingredient_id, {}).values()
                ]
                packet = {
                    "ingredient_id": ingredient_id,
                    "canonical_name": record["canonical_name"],
                    "nutrition_form": form.get("nutrition_form"),
                    "unit_grams": form.get("unit_grams", []),
                    "recipe_lines": lines[ingredient_id],
                    "not_purchased": ingredient_id in NOT_PURCHASED,
                    "candidates": candidates,
                }
                handle.write(json.dumps(packet, ensure_ascii=False) + "\n")
    print(f"{len(todo)} ingredients in {shards} packets under {PACKETS}")


def problems(proposal: dict, products: dict[str, dict[str, dict]], known: set[str]) -> list[str]:
    issues = []
    ingredient_id = proposal.get("ingredient_id")
    if ingredient_id not in known:
        return [f"unknown ingredient {ingredient_id}"]
    status = proposal.get("status")
    if status not in STATUSES:
        issues.append(f"status {status!r}")
    if (status == "not_purchased") != (ingredient_id in NOT_PURCHASED):
        issues.append("not_purchased is reserved for water and ice")
    seen = products.get(ingredient_id, {})
    selected = proposal.get("selected") or []
    if status == "mapped" and not selected:
        issues.append("mapped without a selected product")
    if status != "mapped" and selected:
        issues.append(f"{status} with selected products")
    for item in selected:
        if item.get("product_id") not in seen:
            issues.append(f"selected {item.get('product_id')} was not returned for this ingredient")
        grams = item.get("package_grams")
        if not isinstance(grams, (int, float)) or grams <= 0:
            issues.append(f"selected {item.get('product_id')} has package_grams {grams!r}")
        if not str(item.get("package_grams_basis") or "").strip():
            issues.append(f"selected {item.get('product_id')} has no package_grams_basis")
    chosen = {item.get("product_id") for item in selected}
    for item in proposal.get("rejected") or []:
        if item.get("product_id") not in seen:
            issues.append(f"rejected {item.get('product_id')} was not returned for this ingredient")
        if item.get("product_id") in chosen:
            issues.append(f"{item.get('product_id')} is both selected and rejected")
        if not str(item.get("reason") or "").strip():
            issues.append(f"rejected {item.get('product_id')} has no reason")
    confidence = proposal.get("confidence")
    if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        issues.append(f"confidence {confidence!r}")
    if not str(proposal.get("enriched_by") or "").strip():
        issues.append("enriched_by missing")
    return issues


def load_proposals(files: list[str]) -> tuple[list[dict], list[str]]:
    products = observed_products()
    known = {row["ingredient_id"] for row in _jsonl(RELEASE / "ingredients.jsonl")}
    proposals, report, seen = [], [], set()
    for file in files:
        for number, proposal in enumerate(_jsonl(Path(file)), start=1):
            issues = problems(proposal, products, known)
            if proposal.get("ingredient_id") in seen:
                issues.append("duplicate ingredient")
            seen.add(proposal.get("ingredient_id"))
            if issues:
                report.append(f"{file}:{number} {proposal.get('ingredient_id')}: " + "; ".join(issues))
            else:
                proposals.append(proposal)
    return proposals, report


def export() -> None:
    """The runtime view: mapped and not-purchased ingredients, keyed by the catalog's normalized name."""
    products = observed_products()
    mapping = _jsonl(MAPPING)
    fetched = sorted(row["fetched_at"] for row in _jsonl(OBSERVATIONS) if row["status"] == "ok")
    ingredients = {}
    for row in mapping:
        if row["status"] == "unavailable" or row["review_status"] == "owner_corrected":
            continue
        if row["status"] == "mapped" and row["confidence"] < MIN_CONFIDENCE:
            continue
        entry = {"status": row["status"], "review_status": row["review_status"]}
        if row["status"] == "mapped":
            chosen = []
            for item in row["selected"]:
                seen = products[row["ingredient_id"]][item["product_id"]]
                chosen.append(
                    {
                        "external_id": item["product_id"],
                        "name": seen["name"],
                        "brand": seen["brand"],
                        "category": (seen["category_path"] or [None])[-1],
                        "package_grams": item["package_grams"],
                        "package_grams_basis": item["package_grams_basis"],
                        "price_sgd": seen["final_price"],
                        "product_url": seen["url"],
                        "in_stock": bool(seen["in_stock"]),
                        "query": seen["query"],
                        "fetched_at": seen["fetched_at"],
                    }
                )
            entry["products"] = chosen
        ingredients[row["ingredient_id"][4:].lower()] = entry
    snapshot = {
        "snapshot_version": "fairprice-v2",
        "source": "FairPrice search results captured by data-engineering/scripts/capture_fairprice_snapshot.py",
        "fetched_from": fetched[0],
        "fetched_to": fetched[-1],
        "min_confidence": MIN_CONFIDENCE,
        "ingredients": dict(sorted(ingredients.items())),
    }
    RUNTIME.parent.mkdir(parents=True, exist_ok=True)
    RUNTIME.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    counts = {status: sum(1 for row in mapping if row["status"] == status) for status in STATUSES}
    print(f"{len(ingredients)} ingredients exported to {RUNTIME}; mapping counts {counts}")


def draw_sample(size: int, seed: int) -> None:
    """A stable pseudo-random sample of the proposed mapping, with what the owner needs to judge it."""
    products = observed_products()
    rows = [row for row in _jsonl(MAPPING) if row["status"] != "not_purchased"]
    chosen = sorted(rows, key=lambda row: hashlib.sha256(f"{seed}:{row['ingredient_id']}".encode()).hexdigest())
    items = []
    for row in chosen[:size]:
        seen = products.get(row["ingredient_id"], {})
        items.append(
            dict(
                row,
                selected=[dict(item, product=seen.get(item["product_id"])) for item in row.get("selected") or []],
                rejected=[dict(item, product=seen.get(item["product_id"])) for item in row.get("rejected") or []],
            )
        )
    sheet = {"seed": seed, "drawn_at": datetime.now(UTC).isoformat(timespec="seconds"), "items": items}
    SAMPLE.parent.mkdir(parents=True, exist_ok=True)
    SAMPLE.write_text(json.dumps(sheet, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(items)} of {len(rows)} mapped/unavailable ingredients sampled into {SAMPLE}")


def record(path: Path) -> None:
    """Record verdicts ({"ingredient_id", "verdict": accepted|corrected, "note"}) on the drawn sample."""
    sheet = json.loads(SAMPLE.read_text(encoding="utf-8"))
    sampled = {item["ingredient_id"] for item in sheet["items"]}
    verdicts = _jsonl(path)
    bad = [v for v in verdicts if v.get("ingredient_id") not in sampled or v.get("verdict") not in VERDICTS]
    if bad:
        sys.exit(f"verdicts outside the sample or with an unknown verdict: {bad[:3]}")
    by_id = {v["ingredient_id"]: v for v in verdicts}
    counts = {verdict: sum(v["verdict"] == verdict for v in by_id.values()) for verdict in sorted(VERDICTS)}
    REVIEW.write_text(
        json.dumps(
            {
                "seed": sheet["seed"],
                "drawn_at": sheet["drawn_at"],
                "reviewed_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "reviewer": "owner",
                "sampled": len(sampled),
                "verdicts_recorded": len(by_id),
                "results": counts,
                "verdicts": [by_id[key] for key in sorted(by_id)],
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    rows = _jsonl(MAPPING)
    for row in rows:
        verdict = by_id.get(row["ingredient_id"])
        if verdict is not None:
            row["review_status"] = f"owner_{verdict['verdict']}"
    MAPPING.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    print(f"{len(by_id)} verdicts recorded: {counts}; written to {REVIEW}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    packer = commands.add_parser("packet")
    packer.add_argument("--shards", type=int, default=8)
    packer.add_argument("--unavailable", action="store_true", help="repack ingredients still unavailable")
    commands.add_parser("export")
    sampler = commands.add_parser("sample")
    sampler.add_argument("--size", type=int, default=40)
    sampler.add_argument("--seed", type=int, default=DEFAULT_SEED)
    commands.add_parser("record").add_argument("verdicts")
    for name in ("validate", "merge"):
        commands.add_parser(name).add_argument("files", nargs="+")
    args = parser.parse_args()

    if args.command == "packet":
        build_packets(args.shards, args.unavailable)
        return
    if args.command == "export":
        export()
        return
    if args.command == "sample":
        draw_sample(args.size, args.seed)
        return
    if args.command == "record":
        record(Path(args.verdicts))
        return
    proposals, report = load_proposals(args.files)
    print("\n".join(report) or "all proposals valid")
    if args.command == "validate" or report:
        sys.exit(1 if report else 0)
    existing = {row["ingredient_id"]: row for row in _jsonl(MAPPING)} if MAPPING.exists() else {}
    for proposal in proposals:
        existing[proposal["ingredient_id"]] = dict(proposal, review_status="proposed")
    rows = [existing[key] for key in sorted(existing)]
    MAPPING.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    print(f"{len(proposals)} merged; {len(rows)} ingredients in {MAPPING}")


if __name__ == "__main__":
    main()
