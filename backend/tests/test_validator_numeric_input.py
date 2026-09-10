import json

import pytest

from app.core.paths import repository_root
from app.planning.final_scope_reference import FinalScopeReferencePlanner
from app.planning.final_scope_validator import FinalPlanningValidator
from app.planning.mixed_shopping import build_mixed_shopping, validate_mixed_shopping
from app.schemas.planning_v2 import FinalPlanningProblem, PlanningAssignment, PlanningNutritionBand


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan")])
@pytest.mark.parametrize("field", ["protein_g", "purchase_budget_sgd", "remaining_quantity"])
def test_nonfinite_input_is_never_validated(value, field):
    path = repository_root() / "data/fixtures/planning-v2/mixed-package-developer.json"
    problem = FinalPlanningProblem.model_validate_json(path.read_text(encoding="utf-8"))
    problem.purchase_budget_sgd = 100
    solution = FinalScopeReferencePlanner().solve(problem)
    if field == "protein_g":
        problem.recipes[0].nutrients_per_serving.protein_g = value
    elif field == "purchase_budget_sgd":
        problem.purchase_budget_sgd = value
    else:
        solution.shopping[0].remaining_quantity = value
    report = FinalPlanningValidator().validate(problem, solution.assignments, solution.shopping)
    assert report.status == "failed"
    assert any(c.code == "input_numeric" and c.scope_id.endswith(field) for c in report.checks)
    assert next(c for c in report.checks if c.code == "purchase_budget").status == "indeterminate"
    json.dumps(report.model_dump(mode="json"), allow_nan=False)


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan")])
def test_mixed_validation_rejects_nonfinite_nutrition_even_without_targets(value):
    path = repository_root() / "data/fixtures/planning-v2/mixed-package-developer.json"
    problem = FinalPlanningProblem.model_validate_json(path.read_text(encoding="utf-8"))
    assignments = [PlanningAssignment(slot_id=s.slot_id, recipe_id="a") for s in problem.slots]
    shopping = build_mixed_shopping(problem, assignments)
    problem.recipes[0].nutrients_per_serving.protein_g = value
    issues = validate_mixed_shopping(problem, assignments, shopping)
    assert "input_numeric:recipes[0].nutrients_per_serving.protein_g" in issues
    rejected = build_mixed_shopping(problem, assignments)
    assert rejected.status == "candidate_rejected"
    assert rejected.lines == ()


@pytest.mark.parametrize("scope", ["per_day", "horizon_average"])
def test_finite_nutrition_inputs_can_overflow_without_producing_invalid_json(scope):
    path = repository_root() / "data/fixtures/planning-v2/mixed-package-developer.json"
    problem = FinalPlanningProblem.model_validate_json(path.read_text(encoding="utf-8"))
    problem.purchase_budget_sgd = 100
    solution = FinalScopeReferencePlanner().solve(problem)
    problem.recipes[0].nutrients_per_serving.protein_g = 1e308
    problem.nutrition_bands = [PlanningNutritionBand(metric="protein_g", scope=scope, lower=1)]
    report = FinalPlanningValidator().validate(problem, solution.assignments, solution.shopping)
    check = next(c for c in report.checks if c.code.startswith("nutrition_"))
    assert check.status == "indeterminate"
    assert check.actual is None and check.margin is None
    assert report.status == "indeterminate"
    json.dumps(report.model_dump(mode="json"), allow_nan=False)


def test_finite_price_times_package_count_overflow_keeps_budget_indeterminate():
    path = repository_root() / "data/fixtures/planning-v2/mixed-package-developer.json"
    problem = FinalPlanningProblem.model_validate_json(path.read_text(encoding="utf-8"))
    problem.purchase_budget_sgd = 100
    solution = FinalScopeReferencePlanner().solve(problem)
    selected = solution.shopping[0].selected_product_id
    for product in problem.products:
        if product.product_id == selected:
            product.price_sgd = 1e308
    assert solution.shopping[0].packages >= 2
    report = FinalPlanningValidator().validate(problem, solution.assignments, solution.shopping)
    assert report.status == "failed"
    assert any(c.code == "purchase_numeric" for c in report.checks)
    assert next(c for c in report.checks if c.code == "purchase_budget").status == "indeterminate"
    json.dumps(report.model_dump(mode="json"), allow_nan=False)
