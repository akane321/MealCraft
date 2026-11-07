import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from app.core.paths import repository_root


def comparison_script():
    path = repository_root() / "scripts/compare_snapshot_packaging.py"
    spec = importlib.util.spec_from_file_location("compare_snapshot_packaging", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def readiness_script():
    path = repository_root() / "scripts/audit_real_price_minimum.py"
    spec = importlib.util.spec_from_file_location("audit_real_price_minimum", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_snapshot_comparison_is_matched_deterministic_and_claim_limited():
    snapshot = {
        "snapshot_version": "observed-v1",
        "ingredients": {
            "rice": {
                "status": "mapped",
                "products": [
                    {"external_id": "large", "package_grams": 10, "price_sgd": 9, "in_stock": True},
                    {"external_id": "small", "package_grams": 6, "price_sgd": 5, "in_stock": True},
                ],
            },
            "water": {"status": "not_purchased", "products": []},
        },
    }
    script = comparison_script()
    first = script.build_artifact(snapshot)
    second = script.build_artifact(snapshot)
    assert first == second
    assert first["comparison"] == "same ingredient, demand, availability, package sizes and observed prices"
    assert first["row_count"] == first["same_cost_row_count"] + first["mixed_saving_row_count"]
    assert first["mixed_saving_row_count"] > 0
    assert first["skipped_count"] == 0
    assert "not a plan optimum" in first["claim_scope"]
    assert len(first["rows_sha256"]) == 64


def test_readiness_measures_the_product_mixed_package_contract():
    capability = readiness_script().product_mixed_package_capability()
    assert capability["multi_product_allocation_fields"] == ["allocations"]
    assert capability["supports_multiple_products_per_ingredient_line"]
    assert {"selected_product_id", "packages"} <= set(capability["shopping_selection_fields"])


def test_committed_evidence_is_exactly_regenerated_by_the_scripts(tmp_path):
    root = repository_root()
    cases = (
        ("scripts/audit_real_price_minimum.py", "docs/evaluation/algorithm-dev/real-price-minimum-readiness.json"),
        (
            "scripts/compare_snapshot_packaging.py",
            "docs/evaluation/algorithm-dev/snapshot-package-policy-comparison.json",
        ),
    )
    for script, committed in cases:
        generated = tmp_path / Path(committed).name
        subprocess.run([sys.executable, str(root / script), "--output", str(generated)], check=True, cwd=root)
        assert json.loads(generated.read_text(encoding="utf-8")) == json.loads(
            (root / committed).read_text(encoding="utf-8")
        )
        subprocess.run(
            [sys.executable, str(root / script), "--output", str(root / committed), "--check"],
            check=True,
            cwd=root,
        )
