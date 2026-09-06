from pathlib import Path

import pytest

from app.planning.final_scope_reference import FinalScopeReferencePlanner
from app.planning.final_scope_validator import FinalPlanningValidator
from app.schemas.planning_v2 import FinalPlanningProblem

FIXTURE = Path(__file__).resolve().parents[2] / "data/fixtures/planning-v2/final-scope-multislot.json"


def sample():
    problem = FinalPlanningProblem.model_validate_json(FIXTURE.read_text(encoding="utf-8"))
    return problem, FinalScopeReferencePlanner().solve(problem)


def test_forged_zero_prices_cannot_hide_budget_failure():
    problem, solution = sample()
    forged = [line.model_copy(update={"purchase_cost_sgd": 0}) for line in solution.shopping]
    report = FinalPlanningValidator().validate(
        problem.model_copy(update={"purchase_budget_sgd": 0.01}), solution.assignments, forged
    )
    assert report.status == "failed"
    assert report.purchase_total_sgd == 77.05
    assert any(check.code == "purchase_cost" and check.status == "failed" for check in report.checks)
    assert next(check for check in report.checks if check.code == "purchase_budget").status == "failed"


@pytest.mark.parametrize(
    "mutation,code",
    [
        ("unknown", "product_identity"),
        ("unavailable", "product_available"),
        ("ingredient", "product_ingredient"),
        ("unit", "product_unit"),
        ("packages", "package_coverage"),
    ],
)
def test_invalid_product_selections_are_rejected(mutation, code):
    problem, solution = sample()
    lines = list(solution.shopping)
    index = next(i for i, line in enumerate(lines) if line.selected_product_id and line.remaining_quantity > 0)
    line = lines[index]
    product_index = next(
        i for i, product in enumerate(problem.products) if product.product_id == line.selected_product_id
    )
    if mutation == "unknown":
        lines[index] = line.model_copy(update={"selected_product_id": "missing"})
    elif mutation == "packages":
        lines[index] = line.model_copy(update={"packages": 0, "purchase_cost_sgd": 0})
    else:
        update = (
            {"available": False}
            if mutation == "unavailable"
            else {"ingredient_id": "wrong"}
            if mutation == "ingredient"
            else {"package_unit": "wrong"}
        )
        products = list(problem.products)
        products[product_index] = products[product_index].model_copy(update=update)
        problem = problem.model_copy(update={"products": products})
    report = FinalPlanningValidator().validate(problem, solution.assignments, lines)
    assert report.status == "failed"
    assert any(check.code == code and check.status == "failed" for check in report.checks)


def test_missing_mapping_does_not_report_budget_pass():
    problem, solution = sample()
    lines = [
        line.model_copy(update={"selected_product_id": None, "packages": 0, "purchase_cost_sgd": 0})
        for line in solution.shopping
    ]
    report = FinalPlanningValidator().validate(problem, solution.assignments, lines)
    assert report.status == "indeterminate"
    assert next(check for check in report.checks if check.code == "purchase_budget").status == "indeterminate"


def test_ambiguous_product_id_is_not_resolved_by_list_order():
    problem, solution = sample()
    product = next(
        product
        for product in problem.products
        if any(line.selected_product_id == product.product_id for line in solution.shopping)
    )
    problem = problem.model_copy(update={"products": [*problem.products, product]})
    report = FinalPlanningValidator().validate(problem, solution.assignments, solution.shopping)
    assert any(check.code == "product_identity" for check in report.checks)
    assert report.status == "failed"


def hand_calculated_case():
    from app.schemas.planning_v2 import PlanningAssignment, PlanningShoppingSelection

    problem, _ = sample()
    recipe = problem.recipes[0].model_dump()
    recipe.update(recipe_id="rice", servings=2, ingredients=[{"ingredient_id": "rice", "quantity": 100, "unit": "g"}])
    slots = []
    for index in range(2):
        slot = problem.slots[0].model_dump()
        slot.update(slot_id=f"meal-{index}", servings=3, locked_recipe_id="rice", max_time_minutes=None)
        slots.append(slot)
    data = problem.model_dump()
    data.update(
        slots=slots,
        recipes=[recipe],
        nutrition_bands=[],
        purchase_budget_sgd=6,
        pantry=[{"ingredient_id": "rice", "quantity": 50, "unit": "g"}],
        products=[
            {
                "ingredient_id": "rice",
                "product_id": "bag",
                "package_quantity": 100,
                "package_unit": "g",
                "price_sgd": 2,
                "available": True,
            }
        ],
    )
    problem = FinalPlanningProblem.model_validate(data)
    assignments = [PlanningAssignment(slot_id=f"meal-{index}", recipe_id="rice") for index in range(2)]
    line = PlanningShoppingSelection(
        ingredient_id="rice",
        required_quantity=300,
        unit="g",
        pantry_deduction=50,
        remaining_quantity=250,
        selected_product_id="bag",
        packages=3,
        purchase_cost_sgd=6,
        surplus_quantity=50,
    )
    return problem, assignments, [line]


def test_independent_hand_calculation_scales_servings_and_deducts_pantry_once():
    problem, assignments, lines = hand_calculated_case()
    report = FinalPlanningValidator().validate(problem, assignments, lines)
    assert report.status == "passed"
    assert report.purchase_total_sgd == 6


@pytest.mark.parametrize(
    "change,code",
    [
        ({"required_quantity": 0}, "required_quantity"),
        ({"remaining_quantity": 0}, "remaining_quantity"),
        ({"pantry_deduction": 100}, "pantry_deduction"),
        ({"surplus_quantity": 999}, "surplus_quantity"),
        ({"packages": 2, "purchase_cost_sgd": 4, "remaining_quantity": 200, "surplus_quantity": 0}, "demand_coverage"),
    ],
)
def test_demand_mutations_are_checked_against_recipes(change, code):
    problem, assignments, lines = hand_calculated_case()
    lines = [lines[0].model_copy(update=change)]
    report = FinalPlanningValidator().validate(problem, assignments, lines)
    assert report.status == "failed"
    assert any(check.code == code for check in report.checks)


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "extra"])
def test_shopping_line_set_matches_assigned_recipes(mutation):
    problem, assignments, lines = hand_calculated_case()
    if mutation == "missing":
        lines = []
    elif mutation == "duplicate":
        lines = lines * 2
    else:
        lines.append(lines[0].model_copy(update={"ingredient_id": "unneeded"}))
    report = FinalPlanningValidator().validate(problem, assignments, lines)
    assert report.status == "failed"
    assert any(check.code in ("shopping_line_count", "unexpected_shopping_line") for check in report.checks)
    assert next(check for check in report.checks if check.code == "purchase_budget").status != "passed"


@pytest.mark.parametrize(
    "stock",
    [
        {"ingredient_id": "rice", "quantity": None, "unit": "g"},
        {"ingredient_id": "rice", "quantity": 50, "unit": "kg"},
    ],
)
def test_unknown_or_incompatible_pantry_cannot_be_deducted(stock):
    problem, assignments, lines = hand_calculated_case()
    data = problem.model_dump()
    data["pantry"] = [stock]
    problem = FinalPlanningProblem.model_validate(data)
    report = FinalPlanningValidator().validate(problem, assignments, lines)
    assert any(check.code == "pantry_deduction" for check in report.checks)
    corrected = [lines[0].model_copy(update={"pantry_deduction": 0, "remaining_quantity": 300, "surplus_quantity": 0})]
    assert FinalPlanningValidator().validate(problem, assignments, corrected).status == "passed"


def test_unknown_recipe_quantity_cannot_be_filled_in_by_shopping_output():
    problem, assignments, lines = hand_calculated_case()
    data = problem.model_dump()
    data["recipes"][0]["ingredients"][0]["quantity"] = None
    problem = FinalPlanningProblem.model_validate(data)
    report = FinalPlanningValidator().validate(problem, assignments, lines)
    assert report.status == "indeterminate"
    assert any(check.code == "demand_unknown" for check in report.checks)
    assert next(check for check in report.checks if check.code == "purchase_budget").status == "indeterminate"


def test_fully_known_pantry_can_cover_all_demand_without_a_purchase():
    problem, assignments, lines = hand_calculated_case()
    data = problem.model_dump()
    data["pantry"][0]["quantity"] = 500
    problem = FinalPlanningProblem.model_validate(data)
    lines = [
        lines[0].model_copy(
            update={
                "pantry_deduction": 300,
                "remaining_quantity": 0,
                "selected_product_id": None,
                "packages": 0,
                "purchase_cost_sgd": 0,
                "surplus_quantity": 0,
            }
        )
    ]
    report = FinalPlanningValidator().validate(problem, assignments, lines)
    assert report.status == "passed"
    assert report.purchase_total_sgd == 0


def test_duplicate_pantry_records_need_explicit_resolution():
    problem, assignments, lines = hand_calculated_case()
    problem = problem.model_copy(update={"pantry": problem.pantry * 2})
    report = FinalPlanningValidator().validate(problem, assignments, lines)
    assert report.status == "indeterminate"
    assert any(check.code == "pantry_identity" for check in report.checks)


def test_nonfinite_snapshot_price_cannot_produce_a_budget_pass():
    problem, assignments, lines = hand_calculated_case()
    problem = problem.model_copy(
        update={"products": [problem.products[0].model_copy(update={"price_sgd": float("inf")})]}
    )
    report = FinalPlanningValidator().validate(problem, assignments, lines)
    assert report.status == "failed"
    assert any(check.code == "product_numeric" for check in report.checks)
    assert next(check for check in report.checks if check.code == "purchase_budget").status == "indeterminate"
