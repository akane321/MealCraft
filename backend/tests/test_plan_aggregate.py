"""The `plan` aggregate on synthetic records: known, unknown, not applicable, no plan and invalid. No held-out file."""

from types import SimpleNamespace

import pytest

from app.evaluation import plan_aggregate
from app.evaluation.baseline_recomputation import IngredientEvaluationFacts
from app.schemas.planning_v2 import PlanningNutrients


def nutrients(kcal: float, sodium: float = 0.0) -> PlanningNutrients:
    return PlanningNutrients(calories_kcal=kcal, protein_g=0, carbohydrate_g=0, fat_g=0, sodium_mg=sodium, sugar_g=0)


RESOURCES = SimpleNamespace(
    ingredient_facts={
        "rice": IngredientEvaluationFacts(allergens=(), nutrition_per_100g=nutrients(300, 100)),  # 3 kcal, 1 mg a gram
        "secret": IngredientEvaluationFacts(allergens=(), nutrition_per_100g=None),
    },
    checked_allergens=frozenset({"peanut", "shellfish", "tree_nut"}),
)
TAGS = {
    "MAIN": {"meal_role": "protein_main", "contains_staple": False},
    "BOWL": {"meal_role": "one_bowl", "contains_staple": True},
    "STAPLE": {"meal_role": "staple", "contains_staple": True},
    "SNACK": {"meal_role": "snack", "contains_staple": False},
}


@pytest.fixture(autouse=True)
def catalog_tags(monkeypatch):
    monkeypatch.setattr(plan_aggregate, "recipe_tags", lambda: TAGS)


def dish(name="Rice", role="main", reference="MAIN", grams=400.0, ingredient="rice", not_for=()):
    return {
        "name": name,
        "role": role,
        "recipe_reference": reference,
        "not_for": list(not_for),
        "servings": 2.0,
        "grams": grams,
        "ingredient": ingredient,
    }


def record(meals=None, *, allergens=(), complete=True, total=50.0, status="complete", prices=None):
    """A plan record; `meals` is [(date, meal type, [dish, ...])]."""
    meals = [("2026-09-28", "dinner", [dish()])] if meals is None else meals
    flat = [item for _, _, dishes in meals for item in dishes]
    return {
        "status": "answered",
        "valid_output": True,
        "elapsed_seconds": 2.0,
        "calls": 3,
        "cost_usd": 0.25,
        "exchanges": [
            {
                "output": {
                    "plan": {
                        "meals": [
                            {
                                "date": day,
                                "meal_type": kind,
                                "dishes": [
                                    {k: d[k] for k in ("name", "role", "recipe_reference", "not_for")} for d in dishes
                                ],
                            }
                            for day, kind, dishes in meals
                        ]
                    }
                }
            }
        ],
        "response": {
            "plan": {
                "meals": [
                    {
                        "slot_id": "x",
                        "dishes": [
                            {"name": d["name"], "role_id": d["role"], "servings": d["servings"]} for d in dishes
                        ],
                    }
                    for _, _, dishes in meals
                ]
            }
        },
        "scored": {
            "dishes": [
                {
                    "mappings": [
                        {
                            "original_name": d["ingredient"],
                            "quantity_g": d["grams"],
                            "ingredient_id": d["ingredient"],
                            "status": "matched",
                        }
                    ]
                }
                for d in flat
            ],
            "verification": {"gram_coverage": 0.5, "verifiable_dish_share": 1.0},
            "recomputation": {
                "allergens": list(allergens),
                "allergens_complete": complete,
                "pricing_status": status,
                "purchase_total_sgd": total,
                "price_results": prices or [],
            },
            "allergen_safe": True,  # as `score` always says on the held-out interchange
        },
    }


def episode(*constraints, **gold):
    return {"episode_id": "case", "gold": {"hard_constraints": list(constraints), **gold}}


def constraint(field, operator, value, scope="household"):
    return {"field": field, "operator": operator, "value": value, "unit": "x", "scope": scope, "evidence": "x"}


ALLERGIC = constraint("allergens", "exclude", ["peanut"])
BUDGET = constraint("weekly_budget_sgd", "le", 100, "week")


def row(case, plan_record):
    return plan_aggregate.case_row(case, plan_record, RESOURCES)


def test_an_allergen_is_read_from_the_gold_not_from_the_safe_flag_the_interchange_leaves_true():
    assert row(episode(ALLERGIC), record(allergens=["peanut"]))["allergen_violation"] is True
    assert row(episode(ALLERGIC), record())["allergen_violation"] is False
    assert row(episode(), record(allergens=["peanut"]))["allergen_violation"] == plan_aggregate.NOT_APPLICABLE


def test_unknown_allergens_are_unknown_but_one_present_is_still_a_violation():
    assert row(episode(ALLERGIC), record(complete=False))["allergen_violation"] is None
    assert row(episode(ALLERGIC), record(allergens=["peanut"], complete=False))["allergen_violation"] is True
    unchecked = constraint("allergens", "exclude", ["kiwi"])
    assert row(episode(unchecked), record())["allergen_violation"] is None


def test_an_allergen_name_outside_the_vocabulary_is_read_through_the_keywords():
    prawn = constraint("allergens", "exclude", ["prawn"])
    assert row(episode(prawn), record(allergens=["shellfish"]))["allergen_violation"] is True
    chinese = constraint("allergens", "exclude", ["花生"])
    assert row(episode(chinese), record(allergens=["peanut"]))["allergen_violation"] is True


def test_one_members_allergen_on_a_dish_marked_not_for_someone_is_unknown():
    member = constraint("allergens", "exclude", ["peanut"], "member")
    marked = record([("2026-09-28", "dinner", [dish(not_for=["Ann"])])], allergens=["peanut"])
    assert row(episode(member), marked)["allergen_violation"] is None
    assert row(episode(member), record(allergens=["peanut"]))["allergen_violation"] is True
    nested = constraint("members", "eq", [{"member_id": "Ann", "allergens": ["peanut"]}])
    assert row(episode(nested), marked)["allergen_violation"] is None


@pytest.mark.parametrize(
    ("total", "status", "want"),
    [
        (100.0, "complete", False),
        (100.01, "complete", True),
        (None, "needs_data", None),
        (None, "limit_exceeded", None),
    ],
)
def test_the_budget_needs_a_recomputed_total_and_unknown_is_never_a_pass(total, status, want):
    assert row(episode(BUDGET), record(total=total, status=status))["over_budget"] is want


def test_a_case_stating_no_budget_is_not_applicable_and_the_expected_fields_also_state_one():
    assert row(episode(), record(total=999.0))["over_budget"] == plan_aggregate.NOT_APPLICABLE
    assert row(episode(expected_fields={"weekly_budget_sgd": 10}), record(total=11.0))["over_budget"] is True


def test_the_priced_lines_alone_can_show_an_unknown_total_over_budget_and_stay_unknown():
    lines = [{"purchase_cost_sgd": 150.0}, {"purchase_cost_sgd": None}]
    found = row(episode(BUDGET), record(total=None, status="needs_data", prices=lines))
    assert found["over_budget"] is None and found["known_lines_over"] is True


def test_past_seven_days_the_total_proves_over_budget_only():
    fortnight = [("2026-09-28", "dinner", [dish()]), ("2026-10-11", "dinner", [dish()])]
    assert row(episode(BUDGET), record(fortnight, total=250.0))["over_budget"] is True
    assert row(episode(BUDGET), record(fortnight, total=150.0))["over_budget"] is None
    whole = constraint("weekly_budget_sgd", "le", 100, "plan")
    assert row(episode(whole), record(fortnight, total=150.0))["over_budget"] is True
    assert row(episode(whole), record(fortnight, total=90.0))["over_budget"] is False


def test_an_over_total_with_a_pantry_stated_is_unknown_as_the_recomputation_buys_everything():
    pantry = constraint("pantry", "include", [{"ingredient": "rice", "quantity": 100, "unit": "g"}])
    assert row(episode(BUDGET, pantry), record(total=150.0))["over_budget"] is None
    assert row(episode(BUDGET, pantry), record(total=90.0))["over_budget"] is False


def test_a_budget_of_a_scope_a_total_cannot_answer_is_unknown():
    assert row(episode(constraint("weekly_budget_sgd", "le", 10, "meal")), record())["over_budget"] is None


def test_sodium_per_person_per_meal_and_per_day():
    # 400 g of rice is 400 mg, for two: 200 mg a person.
    assert row(episode(constraint("sodium_limit_mg", "le", 199, "meal")), record())["nutrition_out_of_bounds"] is True
    assert row(episode(constraint("sodium_limit_mg", "le", 200, "meal")), record())["nutrition_out_of_bounds"] is False
    day = [("2026-09-28", "lunch", [dish()]), ("2026-09-28", "dinner", [dish()])]
    limit = constraint("sodium_limit_mg", "le", 399, "day")
    assert row(episode(limit), record(day))["nutrition_out_of_bounds"] is True
    roomy = constraint("sodium_limit_mg", "le", 500, "day")
    assert row(episode(roomy), record(day))["nutrition_out_of_bounds"] is False
    share = constraint("dinner_sodium_share", "eq", 0.3)
    assert row(episode(roomy, share), record(day))["nutrition_out_of_bounds"] is True


def test_nutrition_without_facts_or_a_usable_scope_is_unknown_and_with_no_limit_not_applicable():
    no_facts = record([("2026-09-28", "dinner", [dish(ingredient="secret")])])
    assert row(episode(constraint("sodium_limit_mg", "le", 500, "meal")), no_facts)["nutrition_out_of_bounds"] is None
    assert row(episode(constraint("sodium_limit_mg", "le", 500, "plan")), record())["nutrition_out_of_bounds"] is None
    enabled = constraint("sodium_limit_enabled", "eq", True)
    assert row(episode(enabled), record())["nutrition_out_of_bounds"] is None
    assert row(episode(), record())["nutrition_out_of_bounds"] == plan_aggregate.NOT_APPLICABLE


def test_a_real_excess_is_reported_even_when_another_meal_cannot_be_computed():
    mixed = [("2026-09-28", "lunch", [dish(ingredient="secret")]), ("2026-09-28", "dinner", [dish()])]
    limit = constraint("sodium_limit_mg", "le", 100, "meal")
    assert row(episode(limit), record(mixed))["nutrition_out_of_bounds"] is True


def test_the_development_gold_states_budget_allergens_and_bands_as_well():
    gold = {"applicable_hard_constraints": {"budget_sgd": 10, "allergens_absent": ["peanut"], "nutrition_bands": []}}
    found = row({"episode_id": "case", "gold": gold}, record(allergens=["peanut"], total=11.0))
    assert found["over_budget"] is True and found["allergen_violation"] is True
    band = {"metric": "sodium_mg", "scope": "per_serving", "max": 100}
    gold["applicable_hard_constraints"]["nutrition_bands"] = [band]
    assert row({"episode_id": "case", "gold": gold}, record())["nutrition_out_of_bounds"] is True


def meals_of(*dishes, kind="dinner"):
    return row(episode(), record([("2026-09-28", kind, list(dishes))]))["meals"]


def test_the_meal_checks_are_full_defaults_on_the_catalogs_tags():
    assert meals_of(dish(), dish(role="staple", reference="STAPLE", name="Bun"))[0]["filling_core"] is True
    assert meals_of(dish())[0]["filling_core"] is False  # a protein main with no staple
    assert meals_of(dish(reference="BOWL"))[0]["filling_core"] is True
    assert meals_of(dish(reference="SNACK"))[0]["no_non_meal_dish"] is False
    assert meals_of(dish())[0]["no_non_meal_dish"] is True
    assert meals_of(dish(), kind="breakfast") == []


def test_a_dish_naming_no_catalog_recipe_leaves_the_tag_checks_unknown_unless_a_known_dish_settles_one():
    unnamed = meals_of(dish(reference=None))[0]
    assert unnamed["filling_core"] is None and unnamed["no_non_meal_dish"] is None
    assert meals_of(dish(reference="NOPE"))[0]["filling_core"] is None
    settled = meals_of(dish(reference=None, name="Own"), dish(role="snack", reference="SNACK"))[0]
    assert settled["filling_core"] is None and settled["no_non_meal_dish"] is False


def test_two_dishes_of_one_role_both_count():
    assert meals_of(dish(), dish(reference="SNACK", name="Crisps"))[0]["no_non_meal_dish"] is False


def test_the_energy_floor_counts_a_person_at_the_table_and_a_line_without_facts_is_unknown():
    assert meals_of(dish(grams=4000.0))[0]["energy_floor"] is True  # 6000 kcal a person
    assert meals_of(dish(grams=1.0))[0]["energy_floor"] is False
    assert meals_of(dish(ingredient="secret"))[0]["energy_floor"] is None


def test_a_case_stating_its_own_structure_is_not_applicable_for_the_full_defaults_core():
    case = episode(constraint("meal_structure", "eq", {"dinner": {"protein_mains": 1}}))
    assert row(case, record())["meals"][0]["filling_core"] == plan_aggregate.NOT_APPLICABLE


def test_a_malformed_record_is_counted_not_fatal():
    broken = record()
    del broken["exchanges"][0]["output"]["plan"]["meals"]
    found = row(episode(BUDGET), broken)
    assert found["status"] == "plan" and found["scoring_error"] is True and found["over_budget"] is None


def test_a_plan_the_scorer_failed_on_stays_in_the_denominator_as_unknown():
    failed = record()
    failed["scored"] = {"error": "ValueError: boom"}
    found = row(episode(ALLERGIC, BUDGET), failed)
    assert found["scoring_error"] is True and found["allergen_violation"] is None and found["over_budget"] is None


def rows_for(system_id, records, category="planning"):
    built = []
    for number, (case, kept) in enumerate(records):
        common = {"case": f"c{number}", "system_id": system_id, "category": category, "language": "en"}
        built.append(common | {"source": "authored"} | row(case, kept))
    return built


def test_the_summary_keeps_numerators_denominators_and_every_case():
    invalid = {"status": "answered", "valid_output": False, "elapsed_seconds": 1.0, "calls": 1, "cost_usd": 0.5}
    failed = {"status": "call_failed", "valid_output": False, "elapsed_seconds": 1.0, "calls": 2, "cost_usd": 0.5}
    answer = {
        "status": "answered",
        "valid_output": True,
        "elapsed_seconds": 1.0,
        "calls": 1,
        "cost_usd": 0.0,
        "response": {"plan": None},
    }
    rows = rows_for(
        "arm",
        [
            (episode(BUDGET), record(total=150.0)),
            (episode(BUDGET), record(total=50.0)),
            (episode(BUDGET), record(total=None, status="needs_data")),
            (episode(), record(total=None, status="needs_data")),
            (episode(BUDGET), invalid),
            (episode(BUDGET), failed),
            (episode(BUDGET), answer),
            (episode(BUDGET), None),
        ],
    )
    overall = plan_aggregate.aggregate(rows, min_cell_n=1)["systems"]["arm"]["overall"]
    assert overall["remaining_n"] == 8 and overall["plans_n"] == 4
    assert (overall["no_plan_n"], overall["call_failed_n"], overall["missing_n"]) == (1, 1, 1)
    assert overall["invalid_output"] == {"numerator_n": 1, "of_all_cases_n": 8, "rate": 0.125}
    budget = overall["hard_constraints"]["over_budget"]
    assert budget == {
        "numerator_n": 1,
        "known_n": 2,
        "unknown_n": 1,
        "not_applicable_n": 1,
        "rate": 0.5,
        "unknown_known_lines_over_n": 0,
    }
    assert overall["quality"]["price_sgd"] == {"mean": 100.0, "known_n": 2, "unknown_n": 2}
    assert overall["quality"]["pricing_status"] == {"complete": 2, "needs_data": 2}
    assert overall["verifiability"]["gram_coverage"] == {"mean": 0.5, "known_n": 4, "unknown_n": 0}
    assert overall["cost"]["records_n"] == 7 and overall["cost"]["calls_total"] == 16
    assert overall["cost"]["usd_total"] == 2.0 and overall["cost"]["elapsed_seconds_total"] == 11.0


def test_no_plan_gives_no_rates_and_no_division():
    overall = plan_aggregate.summary([{"status": "no_plan", "elapsed_seconds": 1.0, "calls": 0, "usd": 0.0}])
    assert overall["plans_n"] == 0 and overall["hard_constraints"]["over_budget"]["rate"] is None
    assert overall["quality"]["price_sgd"]["mean"] is None


def test_small_cells_are_withheld_as_in_the_other_aggregates():
    rows = rows_for("arm", [(episode(BUDGET), record())] * 5) + rows_for("arm", [(episode(BUDGET), record())], "intent")
    for number, built in enumerate(rows):
        built["case"] = f"case{number}"
    body = plan_aggregate.aggregate(rows, min_cell_n=5)["systems"]["arm"]
    assert "withheld" in body["cells"] and "plans_n" in body["overall"]
    assert body["by_category"]["intent"] == {"withheld": "fewer than 5 remaining cases"}
    assert "hard_constraints" not in body["by_language"]["en"]


def test_the_comparison_pairs_only_what_both_arms_know_and_never_reads_no_plan_as_a_failed_constraint():
    cases = [(episode(BUDGET), record(total=150.0)), (episode(BUDGET), record(total=50.0))]
    product = rows_for("mealcraft", [*cases, (episode(BUDGET), record(total=50.0)), (episode(), record())])
    answer = {"status": "answered", "valid_output": True, "response": {"plan": None}}
    other = rows_for(
        "rag",
        [
            (episode(BUDGET), record(total=50.0)),
            (episode(BUDGET), record(total=50.0)),
            (episode(BUDGET), answer),
            (episode(), record()),
        ],
    )
    report = plan_aggregate.comparison(product + other, "mealcraft")
    within = report["comparisons"]["rag"]["within_budget"]
    assert within["paired_n"] == 2 and within["product_rate"] == 0.5 and within["baseline_rate"] == 1.0
    assert within["product_unpaired_n"] == 1 and within["baseline_unpaired_n"] == 0
    assert report["comparisons"]["rag"]["allergen_safe"]["paired_n"] == 0
    assert "success" not in report["comparisons"]["rag"]
    assert plan_aggregate.comparison(product, "mealcraft") == {"not_computed": "at least one baseline is required"}
