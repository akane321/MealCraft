import pytest

from app.core.paths import repository_root
from app.planning.theme_parameters import apply_theme_parameters
from app.schemas.planning_v2 import FinalPlanningProblem


def packet():
    return FinalPlanningProblem.model_validate_json(
        (repository_root() / "data/fixtures/planning-v2/diversity-dev-v1.json").read_text(encoding="utf-8")
    )


def test_disabled_default_keeps_original_packet_and_returns_detached_copy():
    problem = packet()
    before = problem.model_dump_json()
    result = apply_theme_parameters(problem, {"diversity_penalty": 0.9})
    assert result.problem.model_dump_json() == before
    assert result.trace["applied_weights"] == {}
    assert result.trace["dropped"] == [{"field": "diversity_penalty", "reason": "disabled"}]
    result.problem.recipes[0].title = "changed"
    assert problem.model_dump_json() == before


def test_applies_only_two_soft_weights_and_leaves_all_other_facts_unchanged():
    problem = packet()
    before = problem.model_dump()
    result = apply_theme_parameters(problem, {"diversity_penalty": 0.8, "overlap_reward_weight": 0.1}, enabled=True)
    expected = problem.model_dump()
    expected["diversity_policy"].update(diversity_penalty=0.8, overlap_reward_weight=0.1)
    assert result.problem.model_dump() == expected
    assert problem.model_dump() == before
    assert result.trace["requires_final_validation"]


@pytest.mark.parametrize("value", [True, "0.5", None, [], {}, -0.1, 1.1, float("nan"), float("inf"), 10**400])
def test_bad_values_are_dropped_without_coercion_or_clamping(value):
    problem = packet()
    result = apply_theme_parameters(problem, {"diversity_penalty": value}, enabled=True)
    assert result.trace["applied_weights"] == {}
    assert result.problem.model_dump() == problem.model_dump()
    assert "value" not in result.trace["dropped"][0]


def test_off_list_requests_cannot_change_safety_budget_recipe_or_search():
    problem = packet()
    proposal = {
        "allergens": [],
        "purchase_budget_sgd": 9999,
        "recipe_id": "chosen-by-model",
        "max_slots_per_core_ingredient": 84,
        "beam_width": 999,
        "ranking_model": "on",
        "nutrition_guard_band": 1,
        "nutrition_bands": [],
        "instructions": "ignore safety",
        "diversity_penalty": 0.6,
    }
    result = apply_theme_parameters(problem, proposal, enabled=True)
    assert result.trace["applied_weights"] == {"diversity_penalty": 0.6}
    assert {item["field"] for item in result.trace["dropped"]} == set(proposal) - {"diversity_penalty"}
    expected = problem.model_dump()
    expected["diversity_policy"]["diversity_penalty"] = 0.6
    assert result.problem.model_dump() == expected
    assert "ignore safety" not in str(result.trace)


def test_missing_classifications_and_pending_consumers_are_not_guessed():
    problem = packet().model_copy(update={"diversity_policy": None})
    result = apply_theme_parameters(
        problem,
        {
            "diversity_penalty": 0.5,
            "effort_rhythm_weight": 0.5,
            "cuisine_affinity": "Korean",
            "energy_preference": "lighter",
        },
        enabled=True,
    )
    assert result.problem.diversity_policy is None
    assert result.trace["applied_weights"] == {}
    assert {item["reason"] for item in result.trace["dropped"]} == {
        "classification_policy_missing",
        "consumer_contract_pending",
    }


def test_trace_does_not_depend_on_proposal_key_order():
    proposal = {"overlap_reward_weight": 0.2, "allergens": [], "diversity_penalty": 0.5}
    assert (
        apply_theme_parameters(packet(), proposal, enabled=True).trace
        == apply_theme_parameters(packet(), dict(reversed(list(proposal.items()))), enabled=True).trace
    )


@pytest.mark.parametrize("enabled", [False, True])
def test_theme_on_and_off_still_pass_independent_plan_validation(enabled):
    from app.planning.beam_planner import BeamPlanner
    from app.planning.final_scope_validator import FinalPlanningValidator

    result = apply_theme_parameters(packet(), {"diversity_penalty": 0.7, "overlap_reward_weight": 0.3}, enabled=enabled)
    plan = BeamPlanner().solve(result.problem)
    assert plan.status == "feasible"
    assert FinalPlanningValidator().validate(result.problem, plan.assignments, plan.shopping).status == "passed"
