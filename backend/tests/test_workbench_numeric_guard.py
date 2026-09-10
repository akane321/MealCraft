import json
import sys
from pathlib import Path

import pytest

from app.planning import workbench

FIXTURE = Path(__file__).resolve().parents[2] / "data/fixtures/planning-v2/mixed-package-developer.json"


def run(monkeypatch, path, operation, *extra):
    monkeypatch.setattr(sys, "argv", ["workbench", operation, str(path), *extra])
    workbench.main()


@pytest.mark.parametrize("operation", ["plan", "mixed-plan", "oracle", "mixed-oracle", "packages", "relax", "repair"])
@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan")])
def test_every_cli_operation_rejects_nonfinite_input_before_schema_or_calculation(
    tmp_path, monkeypatch, capsys, operation, value
):
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps({"nested": [{"quantity": value}]}), encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        run(monkeypatch, path, operation)
    assert exc.value.code == 2
    output = json.loads(capsys.readouterr().out, parse_constant=lambda value: pytest.fail(value))
    assert output["status"] == "invalid_input"
    assert output["issues"][0]["path"] == "nested[0].quantity"


def test_schema_coerced_infinity_is_blocked_before_beam_runs(tmp_path, monkeypatch, capsys):
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    data["recipes"][0]["nutrients_per_serving"]["protein_g"] = "Infinity"
    path = tmp_path / "problem.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    def forbidden(*args, **kwargs):
        pytest.fail("The planner must not receive nonfinite input")

    monkeypatch.setattr(workbench, "BeamPlanner", forbidden)
    with pytest.raises(SystemExit):
        run(monkeypatch, path, "plan")
    assert json.loads(capsys.readouterr().out)["issues"][0]["path"].endswith("protein_g")


@pytest.mark.parametrize("operation", ["relax", "repair"])
def test_options_are_checked_before_search(tmp_path, monkeypatch, capsys, operation):
    options = tmp_path / "options.json"
    options.write_text('{"value": Infinity}', encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        run(monkeypatch, FIXTURE, operation, "--options", str(options))
    assert exc.value.code == 2
    assert json.loads(capsys.readouterr().out)["issues"][0]["path"] == "options.value"


def test_unknown_pantry_is_not_rejected_by_numeric_guard(tmp_path, monkeypatch, capsys):
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    data["pantry"][0]["quantity"] = None
    data["purchase_budget_sgd"] = 100
    path = tmp_path / "unknown.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    run(monkeypatch, path, "mixed-plan")
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "feasible"
    assert result["shopping"]["lines"][0]["pantry_deduction"] == 0
