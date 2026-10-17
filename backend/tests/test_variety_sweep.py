"""The variety sweep: synthetic households through the product path, variety counted by recipe and by kind."""

from app.evaluation import variety_sweep


def test_a_sweep_run_plans_the_demo_household_and_counts_its_variety_both_ways():
    """Dinner with soup for two with a peanut allergy and no pork, at 1.5 times its witness week."""
    free = variety_sweep.synthetic(
        "unbudgeted", variety_sweep.SHAPES["dinner with soup"], size=2, allergens=("peanut",), excluded=("pork",)
    )
    witness = variety_sweep.week_evidence(free)["witness_cost_sgd"]
    case = {
        "run_id": "sweep-test",
        "shape": "dinner with soup",
        "household_size": 2,
        "safety": "peanut, no pork",
        "witness_sgd": witness,
        "budget_factor": 1.5,
        "budget_sgd": round(witness * 1.5, 2),
    }

    row = variety_sweep.run(case)

    assert row["label"] == "feasible" and row["answered"] == "plan" and row["strict_success"], row
    assert row["dishes"] == 21 and row["total_cost_sgd"] <= case["budget_sgd"]
    assert row["distinct_dish_kinds"] <= row["distinct_recipes"] <= row["dishes"]
    assert row["most_uses_of_a_kind"] >= row["most_uses_of_a_recipe"] >= 1


def test_the_summary_counts_weeks_whose_kinds_are_fewer_than_their_recipes_and_weeks_over_budget():
    def row(recipes, kinds, cost, answered="plan"):
        planned = {"dishes": 7, "distinct_recipes": recipes, "distinct_dish_kinds": kinds, "total_cost_sgd": cost}
        return {
            "label": "feasible" if answered == "plan" else "unproven",
            "answered": answered,
            "strict_success": answered == "plan",
            "budget_sgd": 50.0,
            "seconds": 1.0,
            **(planned if answered == "plan" else {}),
        }

    rows = [row(7, 7, 40.0), row(7, 5, 51.0), row(0, 0, 0.0, answered="-")]

    assert variety_sweep.summary(rows) == {
        "runs": 3,
        "label_unproven": 1,
        "label_infeasible": 0,
        "planned": 2,
        "refused": 0,
        "strict_successes": 2,
        "over_budget": 1,
        "dishes": 14,
        "distinct_recipes": 14,
        "distinct_dish_kinds": 12,
        "runs_with_fewer_kinds_than_recipes": 1,
        "slowest_seconds": 1.0,
    }
    assert "| 3 | 1 | 0 | 2 | 0 | 2 | 1 | 14 | 14 | 12 | 1 | 1.0 |" in variety_sweep.markdown(
        {"summary": variety_sweep.summary(rows), "runs": [], "parameters": {}, "inputs": {}}
    )
