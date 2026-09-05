from pathlib import Path

from app.planning.final_scope_reference import FinalScopeReferencePlanner
from app.planning.final_scope_scoring import energy_proportional_sodium_benchmark, flexible_upper_loss
from app.schemas.planning_v2 import FinalPlanningProblem

FIXTURE_PATH = Path(__file__).resolve().parents[2] / "data" / "fixtures" / "planning-v2" / "final-scope-multislot.json"


def load_problem() -> FinalPlanningProblem:
    return FinalPlanningProblem.model_validate_json(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_final_scope_fixture_supports_explicit_multi_meal_slots() -> None:
    problem = load_problem()
    solution = FinalScopeReferencePlanner().solve(problem)

    assert {slot.meal_type for slot in problem.slots} == {"breakfast", "lunch", "dinner", "snack"}
    assert {assignment.slot_id for assignment in solution.assignments} == {
        slot.slot_id for slot in problem.slots if slot.required
    }
    assert solution.status == "feasible"
    assert solution.validation.status == "passed"
    assert (
        next(
            assignment.recipe_id for assignment in solution.assignments if assignment.slot_id == "2026-09-07-breakfast"
        )
        == "overnight-oats"
    )


def test_reference_planner_is_deterministic_and_unknown_pantry_is_not_deducted() -> None:
    problem = load_problem()
    planner = FinalScopeReferencePlanner()

    first = planner.solve(problem)
    second = planner.solve(problem)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    salt = next(line for line in first.shopping if line.ingredient_id == "salt")
    assert salt.pantry_deduction == 0
    assert salt.packages == 1


def test_hard_budget_failure_rejects_candidate_without_claiming_infeasibility() -> None:
    problem = load_problem().model_copy(update={"purchase_budget_sgd": 1.0})

    solution = FinalScopeReferencePlanner().solve(problem)

    assert solution.status == "candidate_rejected"
    budget_check = next(check for check in solution.validation.checks if check.code == "purchase_budget")
    assert budget_check.status == "failed"
    assert budget_check.hard is True


def test_soft_nutrition_failure_is_reported_but_does_not_become_hard_failure() -> None:
    problem = load_problem()
    soft_band = problem.nutrition_bands[1].model_copy(update={"lower": 500.0})
    problem = problem.model_copy(update={"nutrition_bands": [problem.nutrition_bands[0], soft_band]})

    solution = FinalScopeReferencePlanner().solve(problem)

    soft_check = next(
        check for check in solution.validation.checks if check.code == "nutrition_protein_g_horizon_average"
    )
    assert soft_check.status == "failed"
    assert soft_check.hard is False
    assert solution.validation.hard_failure_count == 0
    assert solution.validation.status == "passed"


def test_sodium_reference_is_energy_proportional_and_gradually_relaxed() -> None:
    assert energy_proportional_sodium_benchmark(650) == 650
    assert flexible_upper_loss(650, 650) == 0
    assert flexible_upper_loss(975, 650) == 0.5
    assert flexible_upper_loss(1300, 650) == 1
