from dataclasses import replace
from datetime import timedelta

import pytest

from app.planning.grocery_estimator import price_evidence
from app.planning.mixed_purchase_handoff import prepare_mixed_purchase
from app.planning.mixed_shopping import build_mixed_shopping
from tests.test_mixed_shopping import assignments, packet
from tests.test_planning_product_input import observation


def inputs(problem=None):
    problem = problem or packet()
    observations = {
        p.product_id: observation(
            external_id=p.product_id,
            package_size=p.package_quantity,
            package_unit=p.package_unit,
            price_sgd=p.price_sgd,
        )
        for p in problem.products
    }
    evidence = {
        key: price_evidence(p, mode="fixture", query="rice", parser_version=None) for key, p in observations.items()
    }
    return problem, assignments(), build_mixed_shopping(problem, assignments()), observations, evidence


def test_preserves_both_allocations_prices_and_pantry_once():
    args = inputs()
    result = prepare_mixed_purchase(*args)
    assert result["status"] == "ready_for_contract_review"
    assert result["purchase_total_cents"] == 350
    assert len(result["items"]) == 1
    line = result["items"][0]
    assert (line["required_quantity"], line["pantry_deduction"], line["remaining_quantity"]) == (300, 50, 250)
    assert sorted(a["purchase_cost_cents"] for a in line["allocations"]) == [150, 200]
    assert {a["evidence"]["fact_id"] for a in line["allocations"]} == {e.fact_id for e in args[4].values()}
    assert prepare_mixed_purchase(*args) == result
    args[3]["150"].price_sgd = 999
    args[4]["150"].query = "changed"
    assert next(a for a in line["allocations"] if a["planning_product_id"] == "150")["product"]["price_sgd"] == 2
    assert all(a["evidence"]["query"] == "rice" for a in line["allocations"])


@pytest.mark.parametrize(
    "field,value", [("price_sgd", 1), ("package_size", 151), ("package_unit", "kg"), ("in_stock", False)]
)
def test_rejects_observation_that_does_not_match_solved_packet(field, value):
    args = inputs()
    args[3]["150"] = args[3]["150"].model_copy(update={field: value})
    result = prepare_mixed_purchase(*args)
    assert result["issues"] == ["allocation_observation_mismatch"]
    assert "items" not in result


@pytest.mark.parametrize("which", [3, 4])
def test_missing_observation_or_price_evidence(which):
    args = inputs()
    args[which].pop("150")
    assert prepare_mixed_purchase(*args)["issues"] == ["allocation_observation_or_evidence_missing"]


@pytest.mark.parametrize("field,value", [("fact_id", "another-fact"), ("mode", "live"), ("source", "fairprice")])
def test_evidence_mismatch_is_not_silently_repaired(field, value):
    args = inputs()
    args[4]["150"] = args[4]["150"].model_copy(update={field: value})
    assert prepare_mixed_purchase(*args)["issues"] == ["allocation_evidence_mismatch"]


def test_observation_time_mismatch():
    args = inputs()
    args[4]["150"].fetched_at += timedelta(days=1)
    assert prepare_mixed_purchase(*args)["status"] == "not_ready"


@pytest.mark.parametrize(
    "mode,source", [("live", "fairprice"), ("cache", "fairprice"), ("snapshot", "release_snapshot")]
)
def test_preserves_accepted_evidence_modes(mode, source):
    args = inputs()
    for key, product in args[3].items():
        product.source = "fairprice"
        args[4][key] = price_evidence(product, mode=mode, source=source, query="rice", parser_version="test")
    result = prepare_mixed_purchase(*args)
    assert result["status"] == "ready_for_contract_review"
    assert {a["evidence"]["mode"] for a in result["items"][0]["allocations"]} == {mode}


def test_rechecks_forged_total_and_budget():
    problem, selected, shopping, observations, evidence = inputs()
    forged = replace(shopping, purchase_total_sgd=0)
    assert "purchase_total" in prepare_mixed_purchase(problem, selected, forged, observations, evidence)["issues"]
    low = problem.model_copy(update={"purchase_budget_sgd": 3.49})
    assert "purchase_budget" in prepare_mixed_purchase(low, selected, shopping, observations, evidence)["issues"]
    fractional = problem.model_copy(update={"purchase_budget_sgd": 3.501})
    assert prepare_mixed_purchase(fractional, selected, shopping, observations, evidence)["issues"] == [
        "budget_not_whole_cents"
    ]


def test_fully_stocked_ingredient_needs_no_price_record():
    problem = packet()
    problem = problem.model_copy(update={"pantry": [problem.pantry[0].model_copy(update={"quantity": 300})]})
    args = inputs(problem)
    result = prepare_mixed_purchase(*args[:3], {}, {})
    assert result["status"] == "ready_for_contract_review"
    assert result["purchase_total_cents"] == 0
    assert result["items"][0]["allocations"] == []


def test_existing_planner_alias_preserves_original_external_id():
    problem = packet()
    problem = problem.model_copy(
        update={"products": [p.model_copy(update={"product_id": f"{p.product_id}@rice"}) for p in problem.products]}
    )
    args = inputs(problem)
    for key, product in args[3].items():
        product.external_id = key.removesuffix("@rice")
        args[4][key] = price_evidence(product, mode="fixture", query="rice", parser_version=None)
    result = prepare_mixed_purchase(*args)
    assert result["status"] == "ready_for_contract_review"
    assert {a["product"]["external_id"] for a in result["items"][0]["allocations"]} == {"100", "150"}


def test_two_prices_cannot_share_one_fact():
    problem = packet()
    # One physical observation can be explicitly mapped to two ingredients,
    # but the two aliases must not assign different prices to that same fact.
    recipe = problem.recipes[0]
    problem = problem.model_copy(
        update={
            "recipes": [
                recipe.model_copy(
                    update={
                        "ingredients": [
                            recipe.ingredients[0],
                            recipe.ingredients[0].model_copy(update={"ingredient_id": "rice-flour"}),
                        ]
                    }
                )
            ],
            "pantry": [],
            "purchase_budget_sgd": None,
            "products": [
                problem.products[0],
                problem.products[0].model_copy(
                    update={"ingredient_id": "rice-flour", "product_id": "150@rice-flour", "price_sgd": 3}
                ),
            ],
        }
    )
    args = inputs(problem)
    product = args[3]["150@rice-flour"]
    product.external_id = "150"
    args[4]["150@rice-flour"] = price_evidence(product, mode="fixture", query="rice-flour", parser_version=None)
    assert prepare_mixed_purchase(*args)["issues"] == ["conflicting_price_fact"]


def test_three_meals_with_six_dishes_share_one_pantry_and_basket():
    from app.planning.purchasing_comparison import compare_purchasing
    from app.schemas.planning_v2 import FinalPlanningProblem, PlanningAssignment
    from tests.test_planning_meal_composition import problem as composed_problem
    from tests.test_planning_meal_composition import recipe

    roles = [{"role_id": "main", "courses": ["main"]}] + [
        {"role_id": f"side-{index}", "courses": ["side"]} for index in range(5)
    ]
    dishes = [recipe(role["role_id"], role["courses"][0], 0, 0, calories=100, ingredient="rice") for role in roles]
    for dish in dishes:
        dish["allowed_meal_types"] = ["breakfast", "lunch", "dinner"]
    data = composed_problem().model_dump(mode="json")
    slot = data["slots"][0]
    data.update(
        recipes=dishes,
        slots=[
            dict(slot, slot_id=meal, meal_type=meal, composition=roles) for meal in ("breakfast", "lunch", "dinner")
        ],
        products=[p.model_dump() for p in packet().products],
        pantry=[p.model_dump() for p in packet().pantry],
    )
    problem = FinalPlanningProblem.model_validate(data)
    selected = [
        PlanningAssignment(slot_id=slot.slot_id, role_id=role["role_id"], recipe_id=role["role_id"])
        for slot in problem.slots
        for role in roles
    ]
    comparison = compare_purchasing(problem, selected)
    assert comparison["status"] == "compared"
    # Each meal: 400g * (0.4 main + 5 * 0.28 sides) = 720g.
    for basket in ("whole_horizon", "per_slot"):
        row = comparison[basket]["lines"][0]
        assert (row["required_quantity"], row["pantry_deduction"], row["remaining_quantity"]) == (2160, 50, 2110)
    observations, evidence = inputs()[3:]
    result = prepare_mixed_purchase(problem, selected, build_mixed_shopping(problem, selected), observations, evidence)
    assert result["status"] == "ready_for_contract_review"
    assert len(result["items"]) == 1
    assert result["items"][0]["remaining_quantity"] == 2110
