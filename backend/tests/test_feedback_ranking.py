from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.core.paths import repository_root
from app.planning.feedback_ranking import (
    POLICY,
    FeedbackEvent,
    FeedbackReplay,
    accept_candidate_order,
    rank_candidates,
    replay_feedback,
)


def dataset():
    return FeedbackReplay.model_validate_json(
        (repository_root() / "data/fixtures/planning-v2/feedback-ranking-developer-v1.json").read_text(encoding="utf-8")
    )


def rank(events, **options):
    return rank_candidates(
        ["a", "b"], events, scope_id="synthetic-home", decision_at=datetime(2026, 1, 2, tzinfo=UTC), **options
    )


def test_default_off_keeps_order_and_reads_no_feedback():
    result = rank(dataset().events)
    assert result == {"order": ["a", "b"], "policy": "off", "used_event_ids": [], "reason": "disabled"}


def test_enabled_uses_only_prior_feedback_from_same_scope():
    data = dataset()
    before = data.model_dump_json()
    result = rank(data.events, enabled=True)
    assert result["order"] == ["b", "a"]
    assert result["used_event_ids"] == ["prior-a", "prior-b"]
    assert data.model_dump_json() == before


@pytest.mark.parametrize("proposed", [["a", "b", "unsafe"], ["a"], ["a", "a"], ["unsafe", "b"]])
def test_invalid_proposals_cannot_change_candidate_membership(proposed):
    assert accept_candidate_order(["a", "b"], proposed) == (["a", "b"], "invalid_permutation")


def test_ties_use_recipe_id_and_input_events_can_be_shuffled():
    events = [
        FeedbackEvent(
            event_id=r, scope_id="synthetic-home", recipe_id=r, outcome="cooked", available_at="2026-01-01T00:00:00Z"
        )
        for r in ["b", "a"]
    ]
    assert rank(events, enabled=True)["order"] == ["a", "b"]
    assert rank(events, enabled=True) == rank(list(reversed(events)), enabled=True)


def test_feedback_at_decision_time_and_cold_start_do_not_change_order():
    event = FeedbackEvent(
        event_id="now", scope_id="synthetic-home", recipe_id="b", outcome="cooked", available_at="2026-01-02T00:00:00Z"
    )
    assert rank([event], enabled=True)["reason"] == "no_prior_feedback"
    assert rank([], enabled=True)["order"] == ["a", "b"]


def test_replay_is_reproducible_and_reports_both_matches_and_misses():
    result = replay_feedback(dataset())
    assert result == replay_feedback(dataset())
    assert result["decision_count"] == 3
    assert result["cooked_choice_count"] == 2
    assert result["cooked_choice_top1_matches"] == {"off": 1, POLICY: 1}
    for row in result["rows"][:2]:
        assert row["conditions"][POLICY]["used_event_ids"] == ["prior-a", "prior-b"]


@pytest.mark.parametrize(
    "change", ["future_label", "scope", "candidate", "duplicate_event", "duplicate_decision", "heldout"]
)
def test_replay_refuses_invalid_links_and_unsupported_source(change):
    data = dataset().model_dump(mode="json")
    if change == "future_label":
        data["events"][3]["available_at"] = "2025-01-01T00:00:00Z"
    elif change == "scope":
        data["events"][3]["scope_id"] = "different"
    elif change == "candidate":
        data["decisions"][0]["eligible_candidates"] = ["a"]
    elif change == "duplicate_event":
        data["events"].append(data["events"][0])
    elif change == "duplicate_decision":
        data["decisions"].append(data["decisions"][0])
    else:
        data["source"] = "heldout"
    with pytest.raises(ValidationError):
        FeedbackReplay.model_validate(data)


def test_naive_time_and_duplicate_candidate_ids_are_rejected():
    with pytest.raises(ValueError, match="timezone"):
        rank_candidates(["a"], [], scope_id="home", decision_at=datetime(2026, 1, 1))
    with pytest.raises(ValueError, match="unique"):
        accept_candidate_order(["a", "a"], ["a", "a"])


@pytest.mark.parametrize("enabled", [False, True])
def test_filtered_candidate_pipeline_stays_valid_with_ranking_on_or_off(enabled):
    from app.planning.constraint_compiler import compile_search_domains
    from app.planning.mixed_shopping import build_mixed_shopping, validate_mixed_shopping
    from app.schemas.planning_v2 import PlanningAssignment
    from tests.test_mixed_shopping import packet

    problem = packet()
    base = problem.recipes[0]
    problem = problem.model_copy(
        update={
            "recipes": [
                base,
                base.model_copy(update={"recipe_id": "b"}),
                base.model_copy(update={"recipe_id": "unsafe", "allergens": ["peanut"]}),
            ],
            "allergens": ["peanut"],
            "allergen_vocabulary": ["peanut"],
        }
    )
    original = problem.model_dump_json()
    events = dataset().events + [
        FeedbackEvent(
            event_id="unsafe-history",
            scope_id="synthetic-home",
            recipe_id="unsafe",
            outcome="cooked",
            available_at="2026-01-01T00:00:00Z",
        )
    ]
    selected = []
    for slot in compile_search_domains(problem).slots:
        eligible = list(slot.eligible_recipe_ids)
        assert "unsafe" not in eligible
        result = rank_candidates(
            eligible, events, scope_id="synthetic-home", decision_at=datetime(2026, 1, 2, tzinfo=UTC), enabled=enabled
        )
        assert set(result["order"]) == set(eligible)
        assert "unsafe-history" not in result["used_event_ids"]
        selected.append(PlanningAssignment(slot_id=slot.slot_id, recipe_id=result["order"][0]))
    shopping = build_mixed_shopping(problem, selected)
    assert shopping.status == "feasible"
    assert validate_mixed_shopping(problem, selected, shopping) == ()
    assert problem.model_dump_json() == original
