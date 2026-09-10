from itertools import product

import pytest

from app.core.paths import repository_root
from app.planning.beam_planner import BeamLimits, BeamPlanner, SearchState
from app.planning.constraint_compiler import compile_search_domains
from app.planning.final_scope_reference import FinalScopeReferencePlanner
from app.planning.search_bounds import SearchBounds
from app.schemas.planning_v2 import FinalPlanningProblem


def scenario(bands=None):
    data = FinalPlanningProblem.model_validate_json(
        (repository_root() / "data/fixtures/planning-v2/final-scope-multislot.json").read_text(encoding="utf-8")
    ).model_dump()
    base = data["recipes"][0]
    recipes = []
    for i, name in enumerate("abc"):
        recipe = dict(base, recipe_id=name, total_time_minutes=5 + i * 5)
        recipe["nutrients_per_serving"] = dict(base["nutrients_per_serving"], protein_g=10 + i * 20)
        recipes.append(recipe)
    slot = data["slots"][0]
    data.update(
        recipes=recipes,
        slots=[dict(slot, slot_id=str(i), locked_recipe_id=None, max_time_minutes=60) for i in range(3)],
        nutrition_bands=bands or [],
        purchase_budget_sgd=None,
    )
    return FinalPlanningProblem.model_validate(data)


def context(problem):
    slots = sorted(problem.slots, key=FinalScopeReferencePlanner._slot_key)
    return SearchBounds(problem, slots, {s.slot_id: s for s in compile_search_domains(problem).slots})


def loss(bounds, choices):
    total = 0
    previous = []
    for slot, recipe in choices:
        total += (
            bounds.costs[slot, recipe]
            + previous.count(recipe) * 0.1
            + (0.35 if previous and previous[-1] == recipe else 0)
        )
        previous.append(recipe)
    return total


def test_lower_bound_never_exceeds_any_exhaustive_completion():
    bounds = context(scenario())
    for length in range(4):
        for prefix in product("abc", repeat=length):
            choices = tuple((str(i), recipe) for i, recipe in enumerate(prefix))
            state = SearchState(choices, loss(bounds, choices))
            lower = bounds.loss_lower_bound(state, length)
            for suffix in product("abc", repeat=3 - length):
                complete = choices + tuple((str(i + length), recipe) for i, recipe in enumerate(suffix))
                assert lower <= loss(bounds, complete) + 1e-12


@pytest.mark.parametrize("scope", ["per_day", "horizon_average"])
def test_nutrition_bounds_preserve_every_valid_completion(scope):
    problem = scenario([{"metric": "protein_g", "scope": scope, "lower": 60, "upper": 90, "hard": True}])
    bounds = context(problem)
    for choices in product("abc", repeat=3):
        total = sum(bounds.recipes[r].nutrients_per_serving.protein_g for r in choices)
        if 60 <= total <= 90:
            for length in range(4):
                state = SearchState(tuple((str(i), r) for i, r in enumerate(choices[:length])))
                assert bounds.nutrition_possible(state, length)
    assert not bounds.nutrition_possible(SearchState((("0", "c"), ("1", "c"))), 2)


def test_dominance_preserves_last_recipe_and_servings():
    problem = scenario()
    bounds = context(problem)
    abc = SearchState((("0", "a"), ("1", "b"), ("2", "c")))
    bac = SearchState((("0", "b"), ("1", "a"), ("2", "c")))
    acb = SearchState((("0", "a"), ("1", "c"), ("2", "b")))
    assert bounds.dominance_key(abc) == bounds.dominance_key(bac)
    assert bounds.dominance_key(abc) != bounds.dominance_key(acb)
    problem.slots[0].servings += 1
    assert context(problem).dominance_key(abc) != context(problem).dominance_key(bac)


def test_wide_beam_matches_exhaustive_objective_on_small_packet():
    problem = scenario()
    bounds = context(problem)
    expected = min(
        loss(bounds, tuple((str(i), r) for i, r in enumerate(choices))) for choices in product("abc", repeat=3)
    )
    result = BeamPlanner(BeamLimits(width=100)).solve(problem)
    assert result.status == "feasible"
    choices = tuple((a.slot_id, a.recipe_id) for a in result.assignments)
    assert loss(bounds, choices) == pytest.approx(expected)


def test_impossible_lower_target_is_pruned_without_global_infeasibility_claim():
    problem = scenario([{"metric": "protein_g", "scope": "per_day", "lower": 1000, "hard": True}])
    result = BeamPlanner().solve(problem)
    assert result.status == "candidate_rejected"
    assert any("nutrition_pruned=3" in warning for warning in result.trace.warnings)


def test_daily_pruning_does_not_use_nutrients_from_another_date():
    from datetime import timedelta

    problem = scenario([{"metric": "protein_g", "scope": "per_day", "lower": 60, "hard": True}])
    problem.slots[1].planned_date += timedelta(days=1)
    problem.slots[2].planned_date += timedelta(days=1)
    # Day one has just one slot whose maximum is 50, even if day two can supply 100.
    assert not context(problem).nutrition_possible(SearchState(), 0)


def test_optional_only_dates_do_not_assume_a_horizon_denominator():
    from datetime import timedelta

    problem = scenario([{"metric": "protein_g", "scope": "horizon_average", "lower": 60, "hard": True}])
    problem.slots[2].planned_date += timedelta(days=1)
    problem.slots[2].required = False
    # Two meals of 30 on day one and skipping day two gives observed-day average 60.
    assert context(problem).nutrition_possible(SearchState((("0", "b"), ("1", "b"))), 2)
