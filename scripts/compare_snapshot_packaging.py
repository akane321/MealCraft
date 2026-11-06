"""Matched fixed-product versus mixed-package comparison on the FairPrice snapshot."""

import argparse
import hashlib
import json
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.planning.acceptance_evidence import compare_package_policies  # noqa: E402

SNAPSHOT = ROOT / "data/products/fairprice-v2-snapshot.json"


def demand_grid(products):
    """Synthetic developer demands derived only from observed package sizes."""
    sizes = sorted(
        {
            Decimal(str(product["package_grams"]))
            for product in products
            if product.get("in_stock") and isinstance(product.get("package_grams"), (int, float))
        }
    )
    if not sizes:
        return []
    demands = {sizes[0] / 2, *sizes, sizes[-1] + sizes[0] / 2}
    demands.update((left + right) / 2 for left, right in zip(sizes, sizes[1:], strict=False))
    return sorted(demand for demand in demands if demand > 0)


def build_artifact(snapshot):
    rows = []
    skipped = 0
    for ingredient_id, entry in sorted(snapshot["ingredients"].items()):
        if entry.get("status") != "mapped":
            continue
        products = entry.get("products", [])
        for demand in demand_grid(products):
            compared = compare_package_policies(ingredient_id, products, float(demand))
            if compared is None:
                skipped += 1
            else:
                rows.append(compared.model_dump(mode="json"))
    savings = [Decimal(row["savings_sgd"]) for row in rows]
    improved = [row for row in rows if Decimal(row["savings_sgd"]) > 0]
    canonical_rows = json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    largest = sorted(
        improved,
        key=lambda row: (-Decimal(row["savings_sgd"]), row["ingredient_id"], Decimal(row["demand_grams"])),
    )[:25]
    return {
        "schema_version": "snapshot-package-policy-comparison-v1",
        "generator": "scripts/compare_snapshot_packaging.py",
        "snapshot_version": snapshot.get("snapshot_version"),
        "comparison": "same ingredient, demand, availability, package sizes and observed prices",
        "fixed_policy": "minimum checkout using repetitions of one product type",
        "mixed_policy": "exact bounded combination of all valid in-stock product types",
        "demand_source": "synthetic developer grid derived from observed package sizes; not household demand",
        "claim_scope": "matched package-policy diagnostic; not a plan optimum or real-catalog five-percent result",
        "row_count": len(rows),
        "skipped_count": skipped,
        "mixed_saving_row_count": len(improved),
        "same_cost_row_count": len(rows) - len(improved),
        "total_savings_sgd": str(sum(savings, Decimal(0))),
        "max_savings_sgd": str(max(savings, default=Decimal(0))),
        "rows_sha256": hashlib.sha256(canonical_rows).hexdigest(),
        "largest_savings_rows": largest,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    raw = SNAPSHOT.read_bytes()
    artifact = build_artifact(json.loads(raw))
    artifact.update(snapshot_sha256=hashlib.sha256(raw).hexdigest())
    rendered = json.dumps(artifact, indent=2) + "\n"
    if args.check:
        if not args.output.exists() or args.output.read_text(encoding="utf-8") != rendered:
            raise SystemExit(f"generated evidence is stale: {args.output}")
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
