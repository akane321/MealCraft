"""Propose, check and merge the ingredient-to-Cold-Storage-product mapping.

Works on the observations written by `capture_cold_storage_snapshot.py`, the same flow as `fairprice_mapping.py`
(`docs/design/cold-storage.md`):

    python scripts/cold_storage_mapping.py packet --shards 3   # data/review/cold_storage/batch<i>.jsonl
    python scripts/cold_storage_mapping.py validate FILE...    # check proposals, print problems
    python scripts/cold_storage_mapping.py merge FILE...       # write data/enrichment/cold_storage/v1/mapping.jsonl
    python scripts/cold_storage_mapping.py export              # write data/products/cold-storage-v1-snapshot.json
    python scripts/cold_storage_mapping.py sample --size 40    # the owner's review sample, fixed seed
    python scripts/cold_storage_mapping.py record VERDICTS.jsonl  # record the owner's verdicts

A packet line gives one ingredient with what a reviewer needs to choose: its name and nutrition form, the gram
weights of its common units, a few recipe lines that use it, and every product its searches returned. A proposal
line answers it (fields below). Nothing is accepted without passing `validate`, and every accepted line keeps
`review_status = "proposed"` until the owner's sampled review records otherwise.

Proposal fields:

- `ingredient_id`, `status`: `mapped`, or `unavailable` (no product in the observations is a fair purchase for it).
- `selected`: for `mapped`, one or more products that are a fair purchase, each with `product_id`, `package_grams`
  (the package expressed in grams of this ingredient) and `package_grams_basis` (how: printed weight, volume x
  density, count x grams per piece; for a weighted item its average weight).
- `rejected`: near-name products that must not be bought for it, each with `product_id` and `reason`.
- `search_again`: for `unavailable`, other search texts worth trying.
- `confidence` (0-1), `notes`, `enriched_by`.

A weighted item (`average_weight` set) is priced per kg on the site: its pack price is `round(paid x average_weight,
2)`, where paid is the promo price if there is one. Packets and the export both show the pack price.
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
RELEASE = ROOT / "data" / "release" / "v2.2"
SNAPSHOT = ROOT / "data" / "enrichment" / "cold_storage" / "v1"
OBSERVATIONS = SNAPSHOT / "observations.jsonl"
MAPPING = SNAPSHOT / "mapping.jsonl"
PACKETS = ROOT / "data" / "review" / "cold_storage"
RUNTIME = ROOT.parent / "data" / "products" / "cold-storage-v1-snapshot.json"
SAMPLE = PACKETS / "review-sample.json"  # redrawable from the seed, so not committed
REVIEW = ROOT / "docs" / "cold-storage-v1-sampled-review.json"  # the owner's judgement, committed
DEFAULT_SEED = 20261031
# "uncertain": the person could not confirm it from the product page. Such a row stays in use (as proposed, ADR-0109)
# unless its notes narrow it; only "corrected" leaves the snapshot.
VERDICTS = {"accepted", "corrected", "uncertain"}
# Below this a mapping is a substitute or a rough yield estimate; the runtime leaves it unpriced.
MIN_CONFIDENCE = 0.6
STATUSES = {"mapped", "unavailable"}
SAMPLE_LINES = 4


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8", newline="\n")


def pack_price(product: dict) -> float:
    """What one pack costs: the promo price if any, times the average weight (kg) for a weighted item."""
    paid = product.get("promo_price") or product["price"]
    weight = product.get("average_weight")
    return round(paid * float(weight), 2) if weight else paid


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


def build_packets(shards: int, out: Path, unavailable: bool = False) -> None:
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
    searched = {row["ingredient_id"] for row in _jsonl(OBSERVATIONS) if row["status"] == "ok"}
    todo = [ingredient_id for ingredient_id in ingredients if ingredient_id not in done and ingredient_id in searched]
    out.mkdir(parents=True, exist_ok=True)
    for shard in range(shards):
        with (out / f"batch{shard + 1}.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
            for ingredient_id in todo[shard::shards]:
                record = ingredients[ingredient_id]
                form = (record.get("forms") or {}).get(ingredient_id) or {}
                candidates = [
                    {
                        "product_id": product["product_id"],
                        "name": product["name"],
                        "pack_price_sgd": pack_price(product),
                        "average_weight_kg": product["average_weight"],
                        "in_stock": product["in_stock"],
                        "query": product["query"],
                    }
                    for product in products.get(ingredient_id, {}).values()
                ]
                packet = {
                    "ingredient_id": ingredient_id,
                    "canonical_name": record["canonical_name"],
                    "nutrition_form": form.get("nutrition_form"),
                    "unit_grams": form.get("unit_grams", []),
                    "recipe_lines": lines[ingredient_id],
                    "candidates": candidates,
                }
                handle.write(json.dumps(packet, ensure_ascii=False) + "\n")
    print(f"{len(todo)} ingredients in {shards} packets under {out}")


def problems(proposal: dict, products: dict[str, dict[str, dict]], known: set[str]) -> list[str]:
    issues = []
    ingredient_id = proposal.get("ingredient_id")
    if ingredient_id not in known:
        return [f"unknown ingredient {ingredient_id}"]
    status = proposal.get("status")
    if status not in STATUSES:
        issues.append(f"status {status!r}")
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
    """The runtime view: mapped ingredients, keyed by the catalog's normalized name (lower case, no `ING_`)."""
    products = observed_products()
    mapping = _jsonl(MAPPING)
    fetched = sorted(row["fetched_at"] for row in _jsonl(OBSERVATIONS) if row["status"] == "ok")
    ingredients = {}
    for row in mapping:
        if row["status"] == "unavailable" or row["review_status"] == "owner_corrected":
            continue
        if row["status"] == "mapped" and row["confidence"] < MIN_CONFIDENCE:
            continue
        chosen = []
        for item in row["selected"]:
            seen = products[row["ingredient_id"]][item["product_id"]]
            chosen.append(
                {
                    "external_id": f"cs-{item['product_id']}",
                    "name": seen["name"],
                    "brand": None,
                    "category": None,
                    "package_grams": item["package_grams"],
                    "package_grams_basis": item["package_grams_basis"],
                    "price_sgd": pack_price(seen),
                    "product_url": seen["url"],
                    "in_stock": bool(seen["in_stock"]),
                    "query": seen["query"],
                    "fetched_at": seen["fetched_at"],
                }
            )
        ingredients[row["ingredient_id"][4:].lower()] = {
            "status": row["status"],
            "review_status": row["review_status"],
            "products": chosen,
        }
    snapshot = {
        "snapshot_version": "cold-storage-v1",
        "source": "cold_storage",
        "fetched_from": fetched[0],
        "fetched_to": fetched[-1],
        "min_confidence": MIN_CONFIDENCE,
        "ingredients": dict(sorted(ingredients.items())),
    }
    RUNTIME.parent.mkdir(parents=True, exist_ok=True)
    RUNTIME.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    counts = {status: sum(1 for row in mapping if row["status"] == status) for status in STATUSES}
    print(f"{len(ingredients)} ingredients exported to {RUNTIME}; mapping counts {counts}")


def draw_sample(size: int, seed: int) -> None:
    """A stable pseudo-random sample of the proposed mapping, with what the owner needs to judge it."""
    products = observed_products()
    rows = _jsonl(MAPPING)
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
    SAMPLE.write_text(json.dumps(sheet, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"{len(items)} of {len(rows)} mapped/unavailable ingredients sampled into {SAMPLE}")


def record(path: Path) -> None:
    """Record verdicts ({"ingredient_id", "verdict": accepted|corrected|uncertain, "note"}) on the drawn sample."""
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
        newline="\n",
    )
    rows = _jsonl(MAPPING)
    for row in rows:
        verdict = by_id.get(row["ingredient_id"])
        if verdict is not None:
            row["review_status"] = f"owner_{verdict['verdict']}"
    _write_jsonl(MAPPING, rows)
    print(f"{len(by_id)} verdicts recorded: {counts}; written to {REVIEW}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    packer = commands.add_parser("packet")
    packer.add_argument("--shards", type=int, default=3)
    packer.add_argument("--out", type=Path, default=PACKETS, help="directory for batch<i>.jsonl")
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
        build_packets(args.shards, args.out, args.unavailable)
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
    _write_jsonl(MAPPING, rows)
    print(f"{len(proposals)} merged; {len(rows)} ingredients in {MAPPING}")


if __name__ == "__main__":
    main()
