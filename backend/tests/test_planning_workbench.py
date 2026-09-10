import json
import sys
from pathlib import Path

from app.planning.workbench import main

FIXTURE = Path(__file__).resolve().parents[2] / "data/fixtures/planning-v2/final-scope-multislot.json"


def test_workbench_plan_runs_without_production_services(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["workbench", "plan", str(FIXTURE)])
    main()
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "feasible"
    assert result["validation"]["status"] == "passed"


def test_workbench_mixed_package_output_is_independently_validated(tmp_path, monkeypatch, capsys):
    path = tmp_path / "packages.json"
    path.write_text(
        json.dumps(
            {
                "ingredient_id": "rice",
                "required": 1000,
                "unit": "g",
                "products": [
                    {
                        "ingredient_id": "rice",
                        "product_id": "large",
                        "package_quantity": 600,
                        "package_unit": "g",
                        "price_sgd": 4,
                    },
                    {
                        "ingredient_id": "rice",
                        "product_id": "small",
                        "package_quantity": 400,
                        "package_unit": "g",
                        "price_sgd": 3,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", ["workbench", "packages", str(path)])
    main()
    result = json.loads(capsys.readouterr().out)
    assert result["purchase_cost_sgd"] == 7
    assert result["validation"] == []


def test_workbench_oracle_does_not_mislabel_a_limit(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["workbench", "oracle", str(FIXTURE), "--limit", "1"])
    main()
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "limit_exceeded"
    assert result["checked_combinations"] == 0
