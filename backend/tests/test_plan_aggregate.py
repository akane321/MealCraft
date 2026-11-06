"""The `plan` aggregate on synthetic records: known, unknown, not applicable, no plan and invalid. No held-out file."""

from types import SimpleNamespace

import pytest

from app.evaluation import plan_aggregate
from app.evaluation.baseline_recomputation import IngredientEvaluationFacts
from app.evaluation.pure_llm_baseline import case_episode
from app.schemas.planning_v2 import PlanningNutrients


def nutrients(kcal: float, sodium: float = 0.0) -> PlanningNutrients:
    return PlanningNutrients(calories_kcal=kcal, protein_g=0, carbohydrate_g=0, fat_g=0, sodium_mg=sodium, sugar_g=0)


RESOURCES = SimpleNamespace(
    ingredient_facts={
        "rice": IngredientEvaluationFacts(allergens=(), nutrition_per_100g=nutrients(300, 100)),  # 3 kcal, 1 mg a gram
        "secret": IngredientEvaluationFacts(allergens=(), nutrition_per_100g=None),
        "peanuts": IngredientEvaluationFacts(allergens=("peanut",), nutrition_per_100g=nutrients(600, 0)),
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


def episode(*constraints, horizon_days=None, **gold):
    case = {"episode_id": "case", "horizon_days": horizon_days}
    return case | {"gold": {"hard_constraints": [constraint("household_size", "eq", 2), *constraints], **gold}}


def constraint(field, operator, value, scope="household", **extra):
    return {"field": field, "operator": operator, "value": value, "unit": "x", "scope": scope, "evidence": "x"} | extra


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


MEMBER = constraint("allergens", "exclude", ["peanut"], "member", target_member_ids=["Ann"])
TWO = constraint("members", "eq", [{"member_id": "Ann", "allergens": ["peanut"]}, {"member_id": "Bob"}])


def peanut_plan(*dishes):
    return record([("2026-09-28", "dinner", list(dishes))], allergens=["peanut"])


def test_one_members_allergen_is_unknown_only_on_the_dish_that_holds_it_marked_for_that_member():
    marked = peanut_plan(dish(ingredient="peanuts", not_for=["ann"]))  # the plan's name, the gold's id
    found = row(episode(MEMBER), marked)
    assert found["allergen_violation"] is None and found["marked_not_for"] is True
    assert row(episode(TWO), marked)["allergen_violation"] is None
    assert row(episode(MEMBER), peanut_plan(dish(ingredient="peanuts")))["allergen_violation"] is True


def test_a_not_for_on_another_dish_or_for_someone_else_hides_no_member_violation():
    other_dish = peanut_plan(dish(ingredient="peanuts"), dish(name="Rice", not_for=["Ann"]))
    assert row(episode(MEMBER), other_dish)["allergen_violation"] is True
    someone_else = peanut_plan(dish(ingredient="peanuts", not_for=["Bob"]))
    assert row(episode(TWO), someone_else)["allergen_violation"] is True
    # Every arm alike: this is the same record whichever arm wrote it, and only `not_for` differs.
    unknown_name = peanut_plan(dish(ingredient="peanuts", not_for=["Mum"]))
    assert row(episode(MEMBER), unknown_name)["allergen_violation"] is None  # may be Ann under another id


def test_a_household_allergen_stays_a_violation_whatever_the_marks_say():
    marked = peanut_plan(dish(ingredient="peanuts", not_for=["Ann"]))
    assert row(episode(ALLERGIC), marked)["allergen_violation"] is True


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


def test_the_periods_come_from_the_request_not_from_the_plans_own_span():
    fortnight = [("2026-09-28", "dinner", [dish()]), ("2026-10-11", "dinner", [dish()])]
    assert row(episode(BUDGET, horizon_days=7), record(fortnight, total=150.0))["over_budget"] is True
    assert row(episode(BUDGET, horizon_days=14), record(total=150.0))["over_budget"] is None


def test_planned_days_and_meals_are_set_against_the_request():
    types = constraint("meal_types", "eq", ["lunch", "dinner"])
    plans = [
        row(episode(types, horizon_days=2), record()),  # one dinner of four meals
        row(episode(types, horizon_days=1), record([("2026-09-28", k, [dish()]) for k in ("lunch", "dinner")])),
        row(episode(), record()),
    ]
    days = plan_aggregate._coverage(plans, "days")
    assert days == {
        "known_n": 2,
        "unknown_n": 1,
        "short_n": 1,
        "exact_n": 1,
        "over_n": 0,
        "planned_mean": 1.0,
        "requested_mean": 1.5,
    }
    assert plan_aggregate._coverage(plans, "meals")["short_n"] == 1


def test_a_case_keeps_its_horizon_for_the_aggregate():
    case = {"id": "c", "turns": ["hello"], "horizon_days": 5, "gold": {}, "source": {"kind": "authored"}}
    assert plan_aggregate.requested_slots(case_episode(case)) == (5, None)


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


def test_per_person_is_the_cases_household_whatever_servings_the_arm_claims():
    limit = constraint("sodium_limit_mg", "le", 150, "meal")  # 400 mg in the dish
    claims_many = record([("2026-09-28", "dinner", [dish() | {"servings": 40.0}])])
    assert row(episode(limit), claims_many)["nutrition_out_of_bounds"] is True  # 200 mg a person, not 10
    family = {"episode_id": "case", "gold": {"hard_constraints": [limit, TWO]}}
    assert row(family, claims_many)["nutrition_out_of_bounds"] is True  # two members
    four = constraint("household_size", "eq", 4)
    assert row({"gold": {"hard_constraints": [limit, four]}}, record())["nutrition_out_of_bounds"] is False


def test_no_household_or_an_attendance_leaves_per_person_unknown():
    limit = constraint("sodium_limit_mg", "le", 1, "meal")
    silent = {"episode_id": "case", "gold": {"hard_constraints": [limit]}}
    assert row(silent, record())["nutrition_out_of_bounds"] is None
    assert row(silent, record())["meals"][0]["energy_floor"] is None
    away = constraint("attendance", "eq", [{"date": "2026-09-28", "meal_type": "dinner", "absent_member_ids": ["x"]}])
    assert row(episode(limit, away), record())["nutrition_out_of_bounds"] is None


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
    assert found["gram_coverage"] == 0.5 and found["price_sgd"] == 50.0


def test_one_fault_leaves_a_known_allergen_hit_and_a_requested_budget_standing():
    broken = record(allergens=["peanut"], total=150.0)
    del broken["exchanges"][0]["output"]["plan"]["meals"]
    found = row(episode(ALLERGIC, BUDGET, horizon_days=7), broken)
    assert found["allergen_violation"] is True and found["over_budget"] is True and found["scoring_error"] is True


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
    report = plan_aggregate.aggregate(rows, min_cell_n=1, product="mealcraft")["systems"]["arm"]
    assert report["calls_counted_as"] == "model_calls"
    overall = report["overall"]
    assert overall["remaining_n"] == 8 and overall["plans_n"] == 4
    assert (overall["no_plan_n"], overall["call_failed_n"], overall["missing_n"]) == (1, 1, 1)
    assert overall["invalid_output"] == {"numerator_n": 1, "of_all_cases_n": 8, "rate": 0.125}
    budget = overall["hard_constraints"]["over_budget"]
    assert budget == {
        "violations_n": 1,
        "known_n": 2,
        "unknown_n": 1,
        "not_applicable_n": 1,
        "applicable_n": 3,
        "violation_rate": 0.5,
        "violation_rate_lower": 0.333333,
        "violation_rate_upper": 0.666667,
        "stated_cases_n": 7,
        "stated_without_plan_n": 4,
        "unknown_known_lines_over_n": 0,
    }
    assert overall["quality"]["price_sgd"] == {"mean": 100.0, "known_n": 2, "unknown_n": 2}
    assert overall["quality"]["pricing_status"] == {"complete": 2, "needs_data": 2}
    assert overall["verifiability"]["gram_coverage"] == {"mean": 0.5, "known_n": 4, "unknown_n": 0}
    assert overall["cost"]["records_n"] == 7 and overall["cost"]["calls_total"] == 16
    assert overall["cost"]["usd_total"] == 2.0 and overall["cost"]["elapsed_seconds_total"] == 11.0


def test_no_plan_gives_no_rates_and_no_division():
    stated = dict.fromkeys(plan_aggregate.HARD, False)
    answer = {"status": "no_plan", "stated": stated, "elapsed_seconds": 1.0, "calls": 0, "usd": 0.0}
    overall = plan_aggregate.summary([answer])
    assert overall["plans_n"] == 0 and overall["hard_constraints"]["over_budget"]["violation_rate"] is None
    assert overall["quality"]["price_sgd"]["mean"] is None


def test_small_cells_are_withheld_as_in_the_other_aggregates():
    rows = rows_for("arm", [(episode(BUDGET), record())] * 5) + rows_for("arm", [(episode(BUDGET), record())], "intent")
    for number, built in enumerate(rows):
        built["case"] = f"case{number}"
    body = plan_aggregate.aggregate(rows, min_cell_n=5, product="mealcraft")["systems"]["arm"]
    assert "withheld" in body["cells"] and "plans_n" in body["overall"]
    assert body["by_category"]["intent"] == {"withheld": "fewer than 5 remaining cases"}
    assert "hard_constraints" not in body["by_language"]["en"]


def test_a_cell_with_enough_cases_but_one_known_shows_no_rate_price_or_bound():
    one_known = [(episode(BUDGET), record(total=150.0))] + [
        (episode(BUDGET), record(total=None, status="needs_data")) for _ in range(5)
    ]
    rows = rows_for("arm", one_known)
    overall = plan_aggregate.aggregate(rows, min_cell_n=5, product="mealcraft")["systems"]["arm"]["overall"]
    assert overall["remaining_n"] == 6
    budget = overall["hard_constraints"]["over_budget"]
    assert budget["known_n"] == 1 and budget["unknown_n"] == 5 and budget["applicable_n"] == 6
    assert budget["withheld"] == "fewer than 5 known cases"
    assert not {"violations_n", "violation_rate", "violation_rate_lower", "violation_rate_upper"} & set(budget)
    price = overall["quality"]["price_sgd"]
    assert "mean" not in price and price["known_n"] == 1 and price["unknown_n"] == 5


def test_a_lone_small_known_value_takes_the_smallest_other_with_it():
    small = rows_for("arm", [(episode(BUDGET), record(total=150.0))], "intent")
    middle = rows_for("arm", [(episode(BUDGET), record(total=50.0))] * 6, "planning")
    large = rows_for("arm", [(episode(BUDGET), record(total=50.0))] * 8, "multi_turn")
    needs = [(episode(BUDGET), record(total=None, status="needs_data"))] * 5
    rows = small + rows_for("arm", needs, "intent") + middle + large
    groups = plan_aggregate._groups(rows, lambda built: built["category"], 5)
    blocks = {name: body["hard_constraints"]["over_budget"] for name, body in groups.items()}
    assert "withheld" in blocks["intent"] and "withheld" in blocks["planning"]
    assert "violation_rate" in blocks["multi_turn"]


def test_meal_checks_are_guarded_by_the_cases_behind_them_not_the_meals():
    week = [("2026-09-28", "dinner", [dish()])] + [(f"2026-09-{day}", "lunch", [dish()]) for day in range(20, 27)]
    rows = rows_for("arm", [(episode(), record(week))]) + rows_for("arm", [(episode(), None)] * 5)
    core = plan_aggregate.aggregate(rows, min_cell_n=5, product="mealcraft")["systems"]["arm"]["overall"]
    block = core["meal_likeness"]["no_non_meal_dish"]
    assert block["known_n"] == 8 and block["known_cases_n"] == 1 and "passes_n" not in block


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
    report = plan_aggregate.comparison(product + other, "mealcraft", min_cell_n=1)
    within = report["comparisons"]["rag"]["within_budget"]
    assert within["paired_n"] == 2 and within["product_rate"] == 0.5 and within["baseline_rate"] == 1.0
    assert within["product_unpaired_n"] == 1 and within["baseline_unpaired_n"] == 0
    assert report["comparisons"]["rag"]["allergen_safe"]["paired_n"] == 0
    assert "success" not in report["comparisons"]["rag"]
    assert plan_aggregate.comparison(product, "mealcraft", min_cell_n=1) == {
        "not_computed": "at least one baseline is required"
    }
    guarded = plan_aggregate.comparison(product + other, "mealcraft", min_cell_n=3)["comparisons"]["rag"][
        "within_budget"
    ]
    assert guarded == {
        "paired_n": 2,
        "product_unpaired_n": 1,
        "baseline_unpaired_n": 0,
        "withheld": "fewer than 3 paired cases",
    }


def test_the_calls_are_labelled_by_what_they_count():
    rows = rows_for("mealcraft/ablation/x", [(episode(), record())]) + rows_for("rag", [(episode(), record())])
    systems = plan_aggregate.aggregate(rows, min_cell_n=1, product="mealcraft")["systems"]
    assert systems["mealcraft/ablation/x"]["calls_counted_as"] == "messages"
    assert systems["rag"]["calls_counted_as"] == "model_calls"
