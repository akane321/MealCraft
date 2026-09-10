from app.core.paths import repository_root
from app.planning.input_audit import audit_problem
from app.schemas.planning_v2 import FinalPlanningProblem


def packet():
    path = repository_root() / "data/fixtures/planning-v2/mixed-package-developer.json"
    return FinalPlanningProblem.model_validate_json(path.read_text(encoding="utf-8"))


def test_current_schema_accepts_infinity_but_audit_identifies_exact_path():
    data = packet().model_dump()
    data["recipes"][0]["nutrients_per_serving"]["protein_g"] = float("inf")
    problem = FinalPlanningProblem.model_validate(data)
    issues = audit_problem(problem)
    assert [(i.path, i.code, i.severity) for i in issues] == [
        ("recipes[0].nutrients_per_serving.protein_g", "nonfinite_number", "invalid")
    ]


def test_missing_recipe_amount_and_unknown_pantry_have_distinct_meanings():
    problem = packet()
    problem.recipes[0].ingredients[0].quantity = None
    problem.pantry[0].quantity = None
    result = {i.code: i.severity for i in audit_problem(problem)}
    assert result == {"unknown_recipe_quantity": "missing", "unknown_pantry_quantity": "policy"}


def test_duplicate_ids_and_fractional_cents_are_reported():
    problem = packet()
    problem.products[0].price_sgd = 0.001
    problem.products.append(problem.products[0].model_copy())
    issues = audit_problem(problem)
    assert sum(i.code == "ambiguous_identity" for i in issues) == 2
    assert sum(i.code == "fractional_cent_price" for i in issues) == 2


def test_audit_does_not_mutate_or_treat_empty_allergens_as_missing():
    problem = packet()
    problem.recipes[0].allergens = []
    before = problem.model_dump_json()
    assert audit_problem(problem) == ()
    assert problem.model_dump_json() == before


def test_blank_version_is_reported_and_output_is_stable():
    problem = packet().model_copy(update={"catalog_version": " "})
    issues = audit_problem(problem)
    assert issues == audit_problem(problem)
    assert issues[0].code == "missing_version"
