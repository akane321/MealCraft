"""Generate honest readiness evidence for Issue #310's real-minimum price claim."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.planning.acceptance_evidence import assess_real_minimum_readiness  # noqa: E402
from app.schemas.planning_v2 import PlanningShoppingSelection  # noqa: E402

SNAPSHOT = ROOT / "data/products/fairprice-v2-snapshot.json"


def product_mixed_package_capability():
    """Measure whether the product output can carry several products per line."""
    fields = tuple(sorted(PlanningShoppingSelection.model_fields))
    allocation_fields = tuple(field for field in fields if "allocation" in field or "products" in field)
    return {
        "shopping_selection_fields": list(fields),
        "multi_product_allocation_fields": list(allocation_fields),
        "supports_multiple_products_per_ingredient_line": bool(allocation_fields),
    }


def build_artifact(snapshot, raw):
    capability = product_mixed_package_capability()
    readiness = assess_real_minimum_readiness(
        snapshot["ingredients"],
        observed_snapshot=True,
        # Product candidate construction is bounded and role-ranked.
        full_supported_catalog=False,
        # ProductPlanningEngine projects the one product already selected for each grocery line.
        mixed_packages_in_product=capability["supports_multiple_products_per_ingredient_line"],
        # Existing exact references solve generated assignments and package subproblems separately.
        exact_joint_plan_and_purchase_solver=False,
    )
    return {
        "schema_version": "real-price-minimum-readiness-v1",
        "generator": "scripts/audit_real_price_minimum.py",
        "snapshot_version": snapshot.get("snapshot_version"),
        "snapshot_sha256": hashlib.sha256(raw).hexdigest(),
        "readiness": readiness.model_dump(mode="json"),
        "supported_claim": "observed-snapshot domain audit; no real-minimum or five-percent conclusion",
        "product_projection": "one selected product per ingredient line",
        "offline_mixed_solver": "exact package subproblem for a supplied bounded packet; not product wiring",
        "product_output_contract": capability,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    raw = SNAPSHOT.read_bytes()
    artifact = build_artifact(json.loads(raw), raw)
    rendered = json.dumps(artifact, indent=2) + "\n"
    if args.check:
        if not args.output.exists() or args.output.read_text(encoding="utf-8") != rendered:
            raise SystemExit(f"generated evidence is stale: {args.output}")
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
