from itertools import product

import pytest
from pydantic import ValidationError

from app.core.paths import repository_root
from app.planning.beam_planner import BeamLimits, BeamPlanner, SearchState
from app.planning.constraint_compiler import compile_search_domains
from app.planning.diversity import diversity_loss
from app.planning.exhaustive_oracle import exhaustive_assignments
from app.planning.final_scope_reference import FinalScopeReferencePlanner
from app.planning.final_scope_validator import FinalPlanningValidator
from app.planning.mixed_beam import solve_mixed_beam
from app.planning.mixed_plan_oracle import exhaustive_mixed_plan
from app.planning.mixed_shopping import build_mixed_shopping
from app.planning.search_bounds import SearchBounds
from app.schemas.planning_v2 import FinalPlanningProblem, PlanningAssignment, PlanningDiversityPolicy


def packet():
    return FinalPlanningProblem.model_validate_json(
        (repository_root() / "data/fixtures/planning-v2/diversity-dev-v1.json").read_text(encoding="utf-8")
    )


def report(problem, recipe_ids):
    assignments = [
        PlanningAssignment(slot_id=s.slot_id, recipe_id=r) for s, r in zip(problem.slots, recipe_ids, strict=True)
    ]
    shopping = FinalScopeReferencePlanner()._build_shopping(problem, assignments)
    return FinalPlanningValidator().validate(problem, assignments, shopping)


@pytest.mark.parametrize(
    ("recipes", "code"),
    [
        (["a-chicken", "c-tofu", "a-chicken"], "diversity_recipe_repeat"),
        (["a-chicken", "b-chicken", "d-fish"], "diversity_adjacent_protein"),
    ],
)
def test_validator_rejects_hand_built_violations(recipes, code):
    result = report(packet(), recipes)
    assert result.status == "failed"
    assert any(c.code == code and c.hard for c in result.checks)


def test_core_cap_and_legal_nonadjacent_reuse():
    problem = packet()
    choices = ["a-chicken", "c-tofu", "b-chicken"]
    assert report(problem, choices).status == "passed"
    problem.diversity_policy.max_slots_per_core_ingredient = 1
    assert any(c.code == "diversity_core_cap" for c in report(problem, choices).checks)


@pytest.mark.parametrize("variety,overlap", [(0, 0), (0, 1), (1, 0), (1, 1)])
def test_weight_extremes_preserve_caps_and_match_exhaustive_oracle(variety, overlap):
    problem = packet()
    problem.diversity_policy.diversity_penalty = variety
    problem.diversity_policy.overlap_reward_weight = overlap
    result = BeamPlanner(BeamLimits(width=256)).solve(problem)
    oracle = exhaustive_assignments(problem)
    assert result.status == "feasible"
    assert tuple((a.slot_id, a.recipe_id) for a in result.assignments) == oracle.best_choices
    assert result.trace.diversity_policy == problem.diversity_policy
    # Highest variety weight changes preference, not the feasibility of legal reuse.
    assert report(problem, ["a-chicken", "c-tofu", "b-chicken"]).status == "passed"


def test_missing_classification_is_unknown_not_passed_or_infeasible():
    problem = packet()
    problem.diversity_policy.classifications.clear()
    assert report(problem, ["a-chicken", "c-tofu", "d-fish"]).status == "indeterminate"
    assert BeamPlanner().solve(problem).status == "needs_data"
    assert exhaustive_assignments(problem).status == "needs_data"


def test_unused_missing_classification_does_not_block_known_valid_plan():
    problem = packet()
    del problem.diversity_policy.classifications["e-lentils"]
    assert report(problem, ["a-chicken", "c-tofu", "d-fish"]).status == "passed"


def test_order_independence_and_no_mutation():
    problem = packet()
    before = problem.model_dump_json()
    first = BeamPlanner().solve(problem)
    assert problem.model_dump_json() == before
    problem.slots.reverse()
    problem.recipes.reverse()
    second = BeamPlanner().solve(problem)
    assert first.model_dump() == second.model_dump()


def test_optional_empty_slot_does_not_hide_adjacent_protein():
    problem = packet()
    problem.slots[1].required = False
    assignments = [
        PlanningAssignment(slot_id="s0", recipe_id="a-chicken"),
        PlanningAssignment(slot_id="s2", recipe_id="b-chicken"),
    ]
    shopping = FinalScopeReferencePlanner()._build_shopping(problem, assignments)
    result = FinalPlanningValidator().validate(problem, assignments, shopping)
    assert any(c.code == "diversity_adjacent_protein" for c in result.checks)


def test_locked_repetition_cannot_be_forced_by_search():
    problem = packet()
    problem.slots[0].locked_recipe_id = "a-chicken"
    problem.slots[2].locked_recipe_id = "a-chicken"
    assert BeamPlanner().solve(problem).status == "candidate_rejected"


def test_overlap_reward_prefers_shared_herb_and_is_bounded():
    problem = packet()
    problem.diversity_policy.diversity_penalty = 0
    problem.diversity_policy.overlap_reward_weight = 1
    assert diversity_loss(problem, ["a-chicken"], "c-tofu") < diversity_loss(problem, ["a-chicken"], "e-lentils")
    for choices in product([r.recipe_id for r in problem.recipes], repeat=len(problem.slots)):
        score = sum(diversity_loss(problem, list(choices[:i]), r) for i, r in enumerate(choices))
        assert -0.10 <= score <= 0


def test_bound_accounts_for_future_negative_rewards():
    problem = packet()
    problem.diversity_policy.diversity_penalty = 0
    problem.diversity_policy.overlap_reward_weight = 1
    slots = sorted(problem.slots, key=FinalScopeReferencePlanner._slot_key)
    domains = {s.slot_id: s for s in compile_search_domains(problem).slots}
    bounds = SearchBounds(problem, slots, domains)
    optimum = exhaustive_assignments(problem).best_loss
    assert bounds.loss_lower_bound(SearchState(), 0) <= optimum


@pytest.mark.parametrize(
    "field,value",
    [
        ("diversity_penalty", float("nan")),
        ("overlap_reward_weight", float("inf")),
        ("overlap_reward_weight", 1000000),
        ("diversity_penalty", -1),
        ("max_slots_per_core_ingredient", 0),
        ("max_slots_per_core_ingredient", True),
        ("classification_rule", " "),
        ("unexpected", 1),
    ],
)
def test_controlled_parameters_reject_invalid_values(field, value):
    data = packet().diversity_policy.model_dump()
    data[field] = value
    with pytest.raises(ValidationError):
        PlanningDiversityPolicy.model_validate(data)


def test_classification_cannot_name_nonexistent_core():
    data = packet().model_dump()
    data["diversity_policy"]["classifications"]["a-chicken"]["core_ingredient_ids"].append("invented")
    with pytest.raises(ValidationError):
        FinalPlanningProblem.model_validate(data)


def test_core_in_another_recipe_still_counts_and_never_earns_overlap():
    problem = packet()
    problem.diversity_policy.max_slots_per_core_ingredient = 1
    tofu = next(r for r in problem.recipes if r.recipe_id == "c-tofu")
    chicken = next(r for r in problem.recipes if r.recipe_id == "a-chicken")
    tofu.ingredients.append(chicken.ingredients[0].model_copy(deep=True))
    result = report(problem, ["a-chicken", "c-tofu", "d-fish"])
    assert any(c.code == "diversity_core_cap" for c in result.checks)


def test_validator_does_not_trust_search_guard(monkeypatch):
    monkeypatch.setattr("app.planning.beam_planner.permits_extension", lambda *args: True)
    problem = packet()
    problem.slots[0].locked_recipe_id = "a-chicken"
    problem.slots[2].locked_recipe_id = "a-chicken"
    result = BeamPlanner().solve(problem)
    assert result.status == "candidate_rejected"
    assert any(c.code == "diversity_recipe_repeat" for c in result.validation.checks)


def test_mixed_shopping_obeys_same_caps_and_objective():
    problem = packet()
    beam = solve_mixed_beam(problem, limits=BeamLimits(width=256))
    oracle = exhaustive_mixed_plan(problem)
    assert beam.status == "feasible"
    assert beam.choices == oracle.best_choices
    assert beam.loss == pytest.approx(oracle.best_loss)
    assignments = [
        PlanningAssignment(slot_id=s.slot_id, recipe_id=r)
        for s, r in zip(problem.slots, ["a-chicken", "c-tofu", "a-chicken"], strict=True)
    ]
    assert build_mixed_shopping(problem, assignments).status == "candidate_rejected"
    problem.diversity_policy.classifications.clear()
    assignments[-1].recipe_id = "d-fish"
    assert build_mixed_shopping(problem, assignments).status == "needs_data"
    assert exhaustive_mixed_plan(problem).status == "incomplete_evidence"
