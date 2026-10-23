import json
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.core.paths import repository_root
from app.planning.algorithm_objective import AlgorithmObjective
from app.planning.diversity_greedy import DiversityAwareGreedyPlanner
from app.planning.meal_beam import MealBeamPlanner
from app.planning.near_duplicate_groups import DishGroups, NearDuplicatePolicy, group_candidates
from app.planning.recipe_pair_similarity import RecipePairIndex
from app.schemas.planning_v2 import FinalPlanningProblem, PlanningNutritionBand
from tests.test_planning_meal_composition import NUTRIENTS


def setup_problem(budget=2):
    payload = {
        "problem_id": "diversity-greedy-dev",
        "slots": [
            {
                "slot_id": f"s{i}",
                "planned_date": date(2026, 10, 19) + timedelta(days=i),
                "meal_type": "dinner",
                "servings": 1,
            }
            for i in range(2)
        ],
        "recipes": [
            {
                "recipe_id": key,
                "title": key,
                "servings": 1,
                "allowed_meal_types": ["dinner"],
                "total_time_minutes": 10,
                "course": "main",
                "ingredients": [{"ingredient_id": "rice", "quantity": 100, "unit": "g"}],
                "nutrients_per_serving": {**dict.fromkeys(NUTRIENTS, 0), "calories_kcal": 500},
            }
            for key in ("a", "b", "c")
        ],
        "products": [
            {
                "ingredient_id": "rice",
                "product_id": "rice-bag",
                "package_quantity": 200,
                "package_unit": "g",
                "price_sgd": 2,
            }
        ],
        "purchase_budget_sgd": budget,
        "catalog_version": "dev",
        "product_snapshot_version": "dev",
        "policy_version": "dev",
    }
    problem = FinalPlanningProblem.model_validate(payload)
    groups = DishGroups(NearDuplicatePolicy("dev", 0.2, 0.05, 0.7), (("a", "b"), ("c",)), (), (("a", "b"),))
    objective = AlgorithmObjective(groups, {key: key for key in "abc"}, {"a": 0, "b": 0.01, "c": 0.5})
    return problem, objective


def test_variety_beats_better_ranked_near_duplicate_and_whole_package_is_shared():
    problem, objective = setup_problem()
    solution = DiversityAwareGreedyPlanner(objective).solve(problem)
    assert solution.status == "feasible"
    assert [a.recipe_id for a in solution.assignments] == ["a", "c"]
    assert solution.validation.purchase_total_sgd == 2
    assert sum(row.packages for row in solution.shopping) == 1
    assert objective.score_validated(problem, solution.assignments, solution.validation)[1:3] == (-2, 0)
    # A different algorithm's valid result can use exactly the same final score.
    beam = MealBeamPlanner(local_losses=objective.ranking).solve(problem)
    assert beam.status == "feasible"
    assert objective.score_validated(problem, solution.assignments, solution.validation) <= objective.score_validated(
        problem, beam.assignments, beam.validation
    )


def test_one_cent_over_budget_is_rejected_not_declared_infeasible():
    problem, objective = setup_problem(1.99)
    result = DiversityAwareGreedyPlanner(objective).solve(problem)
    assert result.status == "candidate_rejected"
    assert result.validation.status != "passed"
    with pytest.raises(ValueError, match="independently validated"):
        objective.score_validated(problem, result.assignments, result.validation)


def test_final_independent_validation_rejects_a_week_outside_a_horizon_limit():
    problem, objective = setup_problem()
    problem.nutrition_bands = [PlanningNutritionBand(metric="calories_kcal", scope="horizon_average", upper=400)]
    result = DiversityAwareGreedyPlanner(objective).solve(problem)
    assert result.status == "candidate_rejected"
    assert any(c.code.startswith("nutrition_") and c.status == "failed" for c in result.validation.checks)


def test_same_packet_in_different_recipe_order_is_reproducible():
    problem, objective = setup_problem()
    first = DiversityAwareGreedyPlanner(objective).solve(problem)
    problem.recipes.reverse()
    second = DiversityAwareGreedyPlanner(objective).solve(problem)
    assert first == second


def test_future_locked_meal_cost_prevents_spending_its_budget_early():
    problem, objective = setup_problem(3)
    problem.recipes[0].ingredients[0].ingredient_id = "expensive"
    product = problem.products[0].model_copy(
        update={"product_id": "extra", "ingredient_id": "expensive", "price_sgd": 3}
    )
    problem.products.append(product)
    problem.slots[1].locked_recipe_id = "c"
    result = DiversityAwareGreedyPlanner(objective).solve(problem)
    assert result.status == "feasible"
    assert [a.recipe_id for a in result.assignments] == ["b", "c"]


def test_nutrition_precedes_rank_when_variety_ties():
    problem, base = setup_problem()
    problem.slots = problem.slots[:1]
    problem.recipes[0].nutrients_per_serving.calories_kcal = 200
    problem.recipes[1].nutrients_per_serving.calories_kcal = 200
    problem.nutrition_bands = [PlanningNutritionBand(metric="calories_kcal", scope="per_slot", lower=500, hard=False)]
    objective = AlgorithmObjective(base.groups, base.keys, base.ranking, {"nutrition_calories_kcal_per_slot": 500})
    result = DiversityAwareGreedyPlanner(objective).solve(problem)
    assert result.status == "feasible"
    assert result.assignments[0].recipe_id == "c"


def real_recipe_problem(candidate_count=3):
    root = repository_root()
    calibration = json.loads((root / "docs/evaluation/algorithm-dev/near-duplicates.json").read_text(encoding="utf-8"))
    policy = NearDuplicatePolicy(**calibration["policy"])
    slugs = ["tofu-vegetable-soba", "tofu-mushroom-soba", "tomato-lentil-stew"]
    catalog = {r["slug"]: r for r in json.loads((root / "data/recipes/recipes.json").read_text(encoding="utf-8"))}
    slugs += [slug for slug in sorted(catalog) if slug not in slugs][: max(0, candidate_count - 3)]
    sources = [catalog[slug] for slug in slugs]
    projected = [
        SimpleNamespace(
            external_id=None,
            slug=r["slug"],
            title=r["title"],
            recipe_ingredients=[
                SimpleNamespace(ingredient=SimpleNamespace(normalized_name=i["ingredient"])) for i in r["ingredients"]
            ],
        )
        for r in sources
    ]
    keys = {slug: f"slug:{slug}" for slug in slugs}
    groups = group_candidates(list(keys.values()), RecipePairIndex(projected), policy)
    assert tuple(sorted((keys[slugs[0]], keys[slugs[1]]))) in groups.near_pairs
    problem, _ = setup_problem(100)
    data = problem.model_dump()
    data["recipes"] = [
        {
            "recipe_id": r["slug"],
            "title": r["title"],
            "servings": r["servings"],
            "allowed_meal_types": ["dinner"],
            "total_time_minutes": r["prep_time_minutes"] + r["cook_time_minutes"],
            "course": "main",
            "nutrients_per_serving": r["nutrition"],
            "dietary_tags": r["dietary_tags"],
            "ingredients": [
                {"ingredient_id": i["ingredient"], "quantity": i["quantity"], "unit": i["unit"]}
                for i in r["ingredients"]
            ],
        }
        for r in sources
    ]
    # Real recipe content, deliberately synthetic products: this is an integration
    # test, not a real retail-price or budget-performance claim.
    ingredients = sorted({(i["ingredient"], i["unit"]) for r in sources for i in r["ingredients"]})
    data["products"] = [
        {
            "product_id": f"synthetic-{n}",
            "ingredient_id": ingredient,
            "package_unit": unit,
            "package_quantity": 1000,
            "price_sgd": 1,
        }
        for n, (ingredient, unit) in enumerate(ingredients)
    ]
    problem = FinalPlanningProblem.model_validate(data)
    losses = [0, 0.01, 0.5] + [0.5 + i * 0.01 for i in range(len(slugs) - 3)]
    objective = AlgorithmObjective(groups, keys, dict(zip(slugs, losses, strict=True)))
    return problem, objective


def test_calibrated_real_recipe_signals_reach_greedy_selection_with_explicit_synthetic_prices():
    problem, objective = real_recipe_problem()
    result = DiversityAwareGreedyPlanner(objective).solve(problem)
    assert result.status == "feasible"
    assert [a.recipe_id for a in result.assignments] == [problem.recipes[0].recipe_id, problem.recipes[2].recipe_id]


def test_composed_meals_use_existing_role_constraints_and_independent_validator():
    from tests.test_planning_meal_composition import problem as composed_problem

    problem = composed_problem()
    keys = {r.recipe_id: r.recipe_id for r in problem.recipes}
    groups = DishGroups(
        NearDuplicatePolicy("composed-test", 0.2, 0.05, 0.7), tuple((key,) for key in sorted(keys)), (), ()
    )
    objective = AlgorithmObjective(groups, keys, dict.fromkeys(keys, 0))
    result = DiversityAwareGreedyPlanner(objective).solve(problem)
    assert result.status == "feasible"
    assert {a.role_id for a in result.assignments} >= {"main", "vegetable"}
    assert "peanut-slaw" not in {a.recipe_id for a in result.assignments}


def test_unknown_pairs_do_not_earn_variety_credit():
    problem, base = setup_problem()
    groups = DishGroups(base.groups.policy, (("a",), ("b",), ("c",)), (("a", "c"),), (("a", "b"),))
    objective = AlgorithmObjective(groups, base.keys, base.ranking)
    result = DiversityAwareGreedyPlanner(objective).solve(problem)
    assert result.status == "feasible"
    assert objective.score_validated(problem, result.assignments, result.validation)[1:3] == (-1, 1)


def test_optional_meal_is_filled_when_affordable():
    problem, objective = setup_problem()
    problem.slots[1].required = False
    result = DiversityAwareGreedyPlanner(objective).solve(problem)
    assert result.status == "feasible"
    assert {a.slot_id for a in result.assignments} == {"s0", "s1"}
