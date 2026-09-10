from pathlib import Path

import pytest

from app.planning.beam_planner import BeamLimits
from app.planning.mixed_beam import solve_mixed_beam
from app.planning.mixed_developer_comparison import compare_mixed, developer_cases
from app.planning.whole_plan_scoring import WholePlanPolicy
from app.schemas.planning_v2 import FinalPlanningProblem


def base():
    path = Path(__file__).resolve().parents[2] / "data/fixtures/planning-v2/mixed-package-developer.json"
    return FinalPlanningProblem.model_validate_json(path.read_text(encoding="utf-8"))


def test_comparison_checks_validity_and_does_not_score_unknown_or_failed_outputs():
    report = compare_mixed(base())
    assert len(report["rows"]) == 24
    for row in report["rows"]:
        assert row["deterministic"]
        if row["status"] == "feasible":
            assert row["validation_issues"] == ()
            assert row["gap"] >= -1e-12
        else:
            assert row["gap"] is None
            assert row["loss"] is None
        if row["scenario"] == "missing-products":
            assert row["oracle_status"] == "incomplete_evidence"
            assert row["status"] == "needs_data"
        if row["scenario"] == "budget-impossible":
            assert row["oracle_status"] == "no_valid_assignment"
            assert row["status"] == "candidate_rejected"


def test_case_generation_is_stable_and_does_not_modify_base():
    original = base()
    before = original.model_dump_json()
    cases = list(developer_cases(original))
    assert cases == list(developer_cases(original))
    assert original.model_dump_json() == before
    assert len({c.problem_id for c in cases}) == 8
    assert all(len({s.planned_date for s in c.slots}) == 2 for c in cases)


def test_reordering_catalog_slots_and_products_preserves_decisions():
    for problem in developer_cases(base()):
        reordered = problem.model_copy(
            update={
                "slots": list(reversed(problem.slots)),
                "recipes": list(reversed(problem.recipes)),
                "products": list(reversed(problem.products)),
            }
        )
        args = dict(limits=BeamLimits(4), scoring_policy=WholePlanPolicy())
        assert solve_mixed_beam(problem, **args) == solve_mixed_beam(reordered, **args)


def test_cp_sat_and_enumerated_package_oracles_agree_on_developer_packets():
    pytest.importorskip("ortools")
    reference = compare_mixed(base(), repeats=1, widths=(4,))
    cp_sat = compare_mixed(base(), repeats=1, widths=(4,), use_cp_sat=True)
    for expected, actual in zip(reference["rows"], cp_sat["rows"], strict=True):
        for field in ("input_sha256", "oracle_status", "oracle_loss", "gap"):
            assert expected[field] == actual[field]
