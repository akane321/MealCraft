"""Protocol v2-multidish scoring: roles, shares and meal time, recomputed by the scorer's own code."""

from itertools import product

from app.evaluation import strict_success as scorer
from app.evaluation.common_output import parse_response
from app.evaluation.release_catalog import load_release_catalog
from app.planning.meal_composition import meal_minutes as planner_meal_minutes
from app.planning.meal_composition import portion_shares
from app.schemas.planning_v2 import PlanningCompositionPolicy, PlanningRecipeCandidate

COMPOSITION = [
    {"role_id": "main", "courses": ["main"], "required": True},
    {"role_id": "vegetable", "courses": ["side", "salad"], "required": True},
    {"role_id": "soup", "courses": ["soup"], "required": False},
]


def recipe(slug, course, prep, cook, ingredient):
    return {
        "slug": slug,
        "course": course,
        "servings": 4,
        "prep_time_minutes": prep,
        "cook_time_minutes": cook,
        "dietary_tags": [],
        "ingredients": [{"ingredient": ingredient, "quantity": 400.0, "unit": "g"}],
        "nutrition": None,
    }


CATALOGS = scorer.Catalogs.build(
    [
        recipe("chicken", "main", 15, 25, "chicken"),
        recipe("greens", "side", 10, 22, "greens"),
        recipe("broth", "soup", 15, 30, "stock"),
    ],
    [
        {"external_id": f"p-{name}", "package_size": 500.0, "package_unit": "g", "price_sgd": 2.0}
        for name in ("chicken", "greens", "stock")
    ],
    [{"normalized_name": name, "allergens": []} for name in ("chicken", "greens", "stock")],
    tag_implications={},
    checked_allergens=[],
)


def episode(limit=None):
    return {
        "episode_id": "md-dev-001",
        "scenario": {
            "household_profile": {"household_size": 4, "meal_composition": COMPOSITION},
            "planning_horizon": {"start_date": "2026-09-28", "slots": ["mon-dinner"]},
            "recipe_candidate_slugs": ["chicken", "greens", "broth"],
            "fairprice_product_ids": ["p-chicken", "p-greens", "p-stock"],
        },
        "gold": {
            "class": "feasible",
            "applicable_hard_constraints": {"max_cooking_time_minutes": limit},
            "pantry_ground_truth": {},
        },
    }


INGREDIENT = {"chicken": "chicken", "greens": "greens", "broth": "stock"}


def answer(dishes):
    return parse_response(
        "md-dev-001",
        {
            "episode_id": "md-dev-001",
            "system_id": "test",
            "status": "plan",
            "plan": {
                "assignments": [
                    {"slot_id": "mon-dinner", "role_id": role, "recipe_id": slug, "servings": servings}
                    for role, slug, servings in dishes
                ],
                "shopping": [
                    {
                        "ingredient_id": INGREDIENT[slug],
                        "product_id": f"p-{INGREDIENT[slug]}",
                        "packages": 1,
                        "line_cost_sgd": 2.0,
                    }
                    for _, slug, _ in dishes
                ],
                "total_cost_sgd": 2.0 * len(dishes),
            },
        },
    )


def outcomes(score):
    return {check.code: check.outcome for check in score.checks}


def test_a_composed_meal_at_its_shares_is_a_success():
    score = scorer.score_episode(
        episode(limit=120),
        answer([("main", "chicken", 2.4), ("vegetable", "greens", 1.6), ("soup", "broth", 1.6)]),
        CATALOGS,
    )

    assert score.strict_success, [c for c in score.checks if c.blocks_success]
    assert outcomes(score)["meal_roles_filled"] == "passed"


def test_short_servings_a_missing_role_and_a_wrong_course_fail():
    short = scorer.score_episode(episode(), answer([("main", "chicken", 2.0), ("vegetable", "greens", 1.6)]), CATALOGS)
    missing = scorer.score_episode(episode(), answer([("main", "chicken", 4.0)]), CATALOGS)
    wrong = scorer.score_episode(episode(), answer([("main", "broth", 3.0), ("vegetable", "greens", 2.0)]), CATALOGS)

    assert outcomes(short)["servings_feed_household"] == "failed"  # a main at 0.75 of 4 needs 3
    assert outcomes(missing)["meal_roles_filled"] == "failed"
    assert outcomes(wrong)["meal_role_courses"] == "failed"


def test_the_meal_time_limit_applies_to_the_one_cook_estimate():
    dishes = [("main", "chicken", 2.4), ("vegetable", "greens", 1.6), ("soup", "broth", 1.6)]

    assert (
        outcomes(scorer.score_episode(episode(limit=100), answer(dishes), CATALOGS))["cooking_time_respected"]
        == "failed"
    )
    assert (
        outcomes(scorer.score_episode(episode(limit=105), answer(dishes), CATALOGS))["cooking_time_respected"]
        == "passed"
    )


def test_scorer_and_planner_agree_on_shares_and_meal_time():
    policy = PlanningCompositionPolicy()
    roles = ["main", "vegetable", "soup", "dessert", "main-2", "salad"]  # up to six dishes (ADR-0046)
    for size in range(1, 7):
        for chosen in (roles[:size], roles[1 : size + 1] if size < 6 else roles):
            planner = {k: float(v) for k, v in portion_shares(policy, chosen).items()}
            assert scorer.dish_shares(chosen) == planner
    times = [(0, 5), (15, 25), (10, 22), (15, 30), (5, 0), (20, 45)]
    for combination in product(times, repeat=3):
        for size in (1, 2, 3):
            dishes = combination[:size]
            rows = [{"prep_time_minutes": p, "cook_time_minutes": c} for p, c in dishes]
            candidates = [
                PlanningRecipeCandidate.model_validate(
                    {
                        "recipe_id": f"r{i}",
                        "title": "t",
                        "servings": 4,
                        "allowed_meal_types": ["dinner"],
                        "total_time_minutes": p + c,
                        "prep_minutes": p,
                        "cook_minutes": c,
                        "passive_minutes": 0,
                        "ingredients": [{"ingredient_id": "x"}],
                        "nutrients_per_serving": dict.fromkeys(
                            ("calories_kcal", "protein_g", "carbohydrate_g", "fat_g", "sodium_mg", "sugar_g"), 0
                        ),
                    }
                )
                for i, (p, c) in enumerate(dishes)
            ]
            assert scorer.meal_minutes(rows) == planner_meal_minutes(candidates, policy)


def test_the_release_catalog_prices_every_recipe_it_keeps():
    catalog = load_release_catalog()
    priced = {row["ingredient_id"] for row in catalog.products}

    assert len(catalog.recipes) > 5000
    assert all(line["ingredient"] in priced for r in catalog.recipes for line in r["ingredients"])
    assert {r["course"] for r in catalog.recipes} >= {"main", "side", "salad", "soup"}


def test_demand_left_unbought_fails_the_package_check():
    response = answer([("main", "chicken", 2.4), ("vegetable", "greens", 1.6), ("soup", "broth", 1.6)])
    response.plan.shopping[0].product_id = None  # the chicken line buys nothing
    response.plan.shopping[0].packages = 0
    response.plan.shopping[0].line_cost_sgd = 0.0

    score = scorer.score_episode(episode(limit=120), response, CATALOGS)

    assert outcomes(score)["packages_cover_demand"] == "failed"


def test_only_a_stated_repetition_request_is_scored():
    silent = scorer.score_episode(
        episode(limit=120), answer([("main", "chicken", 2.4), ("vegetable", "greens", 1.6)]), CATALOGS
    )
    asked = episode(limit=120)
    asked["gold"]["applicable_hard_constraints"]["repetition_requirements"] = {
        "recipe_counts": [{"recipe_id": "broth", "min_uses": 1}]
    }
    missed = scorer.score_episode(asked, answer([("main", "chicken", 3.0), ("vegetable", "greens", 2.0)]), CATALOGS)

    assert outcomes(silent)["repetition_requests_met"] == "not_applicable"
    assert outcomes(missed)["repetition_requests_met"] == "failed"
