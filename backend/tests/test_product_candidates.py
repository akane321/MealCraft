from dataclasses import replace

import pytest

from app.planning.algorithm_reference import AnnealingPlanner
from app.planning.meal_beam import MealBeamPlanner
from app.planning.product_candidates import ProductMealCandidates
from tests.test_diversity_greedy import setup_problem


def test_beam_and_annealing_reuse_options_without_changing_result(monkeypatch):
    problem, objective = setup_problem()
    plain = MealBeamPlanner(local_losses=objective.ranking)
    seed = plain.solve(problem)
    expected = AnnealingPlanner(objective, plain, seed=3, steps=30).solve(problem, initial=seed)
    calls = []
    original = MealBeamPlanner.meal_options

    def counted(self, problem, slot):
        calls.append(slot.slot_id)
        return original(self, problem, slot)

    monkeypatch.setattr(MealBeamPlanner, "meal_options", counted)
    cached = ProductMealCandidates(local_losses=objective.ranking)
    actual_seed = cached.solve(problem)
    actual = AnnealingPlanner(objective, cached, seed=3, steps=30).solve(problem, initial=actual_seed)
    assert actual_seed == seed
    assert actual == expected
    assert calls == [s.slot_id for s in problem.slots]


@pytest.mark.parametrize("change", ["price", "recipe", "slot", "ranking", "limits"])
def test_candidate_cache_invalidates_when_inputs_change(change, monkeypatch):
    problem, objective = setup_problem()
    cached = ProductMealCandidates(local_losses=objective.ranking)
    original = MealBeamPlanner.meal_options
    calls = []

    def counted(self, problem, slot):
        calls.append(slot.slot_id)
        return original(self, problem, slot)

    monkeypatch.setattr(MealBeamPlanner, "meal_options", counted)
    slot = problem.slots[0]
    cached.meal_options(problem, slot)
    if change == "price":
        problem.products[0].price_sgd = 3
    elif change == "recipe":
        problem.recipes[0].total_time_minutes = 99
    elif change == "slot":
        slot = slot.model_copy(update={"locked_recipe_id": "b"})
    elif change == "ranking":
        cached.local_losses["a"] = 0.9
    else:
        cached.limits = replace(cached.limits, candidates_per_role=1)
    actual = cached.meal_options(problem, slot)
    assert len(calls) == 2
    assert actual == original(cached, problem, slot)


def test_candidate_cache_preserves_widening_evidence_and_isolates_lists(monkeypatch):
    problem, _ = setup_problem()

    def empty(self, problem, slot):
        self.last_step_tried = 123
        return []

    monkeypatch.setattr(MealBeamPlanner, "meal_options", empty)
    cached = ProductMealCandidates()
    options = cached.meal_options(problem, problem.slots[0])
    options.append("caller mutation")
    cached.last_step_tried = 0
    assert cached.meal_options(problem, problem.slots[0]) == []
    assert cached.last_step_tried == 123
