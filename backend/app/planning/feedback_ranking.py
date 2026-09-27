"""Offline feedback ranking over an already eligible candidate list; default off."""

import argparse
import json
from collections import Counter
from datetime import datetime
from fractions import Fraction
from hashlib import sha256
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

POLICY = "experimental-cooked-share-v1"


class FeedbackEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    event_id: str = Field(min_length=1)
    scope_id: str = Field(min_length=1)
    recipe_id: str = Field(min_length=1)
    outcome: Literal["cooked", "skipped", "swapped"]
    # When the feedback became available, not when the meal was scheduled.
    available_at: AwareDatetime


class ReplayDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    decision_id: str = Field(min_length=1)
    scope_id: str = Field(min_length=1)
    decision_at: AwareDatetime
    eligible_candidates: list[str] = Field(min_length=1)
    outcome_event_id: str = Field(min_length=1)


class FeedbackReplay(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    dataset_version: str = Field(min_length=1)
    source: Literal["synthetic", "developer"]
    events: list[FeedbackEvent]
    decisions: list[ReplayDecision] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_links(self):
        events = {event.event_id: event for event in self.events}
        if len(events) != len(self.events):
            raise ValueError("Feedback event IDs must be unique")
        if len({d.decision_id for d in self.decisions}) != len(self.decisions):
            raise ValueError("Decision IDs must be unique")
        if len({d.outcome_event_id for d in self.decisions}) != len(self.decisions):
            raise ValueError("An outcome event may label only one decision")
        for decision in self.decisions:
            _candidates(decision.eligible_candidates)
            outcome = events.get(decision.outcome_event_id)
            if outcome is None or outcome.scope_id != decision.scope_id:
                raise ValueError("Outcome must exist in the same scope")
            if outcome.recipe_id not in decision.eligible_candidates:
                raise ValueError("Observed choice must belong to the eligible packet")
            if outcome.available_at < decision.decision_at:
                raise ValueError("Outcome cannot predate its decision")
        return self


def _candidates(candidates):
    if any(not isinstance(item, str) or not item.strip() for item in candidates):
        raise ValueError("Candidate IDs must be nonempty strings")
    if len(set(candidates)) != len(candidates):
        raise ValueError("Candidate IDs must be unique")


def accept_candidate_order(eligible: list[str], proposed: list[str]) -> tuple[list[str], str]:
    """Reject additions, deletions and duplicates from any future ranking provider."""
    _candidates(eligible)
    if len(proposed) != len(eligible) or Counter(proposed) != Counter(eligible):
        return list(eligible), "invalid_permutation"
    return list(proposed), "accepted"


def rank_candidates(
    eligible: list[str],
    events: list[FeedbackEvent],
    *,
    scope_id: str,
    decision_at: datetime,
    enabled: bool = False,
) -> dict:
    _candidates(eligible)
    if decision_at.utcoffset() is None:
        raise ValueError("Decision time requires a timezone")
    if len({event.event_id for event in events}) != len(events):
        raise ValueError("Feedback event IDs must be unique")
    result = {"order": list(eligible), "policy": POLICY if enabled else "off", "used_event_ids": []}
    if not enabled:
        return dict(result, reason="disabled")
    history = [e for e in events if e.scope_id == scope_id and e.available_at < decision_at and e.recipe_id in eligible]
    if not history:
        return dict(result, reason="no_prior_feedback")
    totals = Counter(e.recipe_id for e in history)
    cooked = Counter(e.recipe_id for e in history if e.outcome == "cooked")
    scores = {
        recipe: Fraction(cooked[recipe], totals[recipe]) if totals[recipe] else Fraction(0) for recipe in eligible
    }
    order, reason = accept_candidate_order(eligible, sorted(eligible, key=lambda recipe: (-scores[recipe], recipe)))
    return dict(result, order=order, reason=reason, used_event_ids=sorted(e.event_id for e in history))


def replay_feedback(dataset: FeedbackReplay) -> dict:
    events = {event.event_id: event for event in dataset.events}
    rows = []
    for decision in sorted(dataset.decisions, key=lambda d: (d.decision_at, d.decision_id)):
        conditions = {
            name: rank_candidates(
                decision.eligible_candidates,
                dataset.events,
                scope_id=decision.scope_id,
                decision_at=decision.decision_at,
                enabled=enabled,
            )
            for name, enabled in (("off", False), (POLICY, True))
        }
        outcome = events[decision.outcome_event_id]
        rows.append(
            {
                "decision_id": decision.decision_id,
                "outcome": outcome.outcome,
                "observed_recipe_id": outcome.recipe_id,
                "conditions": conditions,
            }
        )
    cooked_rows = [row for row in rows if row["outcome"] == "cooked"]
    return {
        "contract_version": "offline-feedback-replay-v1",
        "dataset_version": dataset.dataset_version,
        "source": dataset.source,
        "input_sha256": sha256(json.dumps(dataset.model_dump(mode="json"), sort_keys=True).encode()).hexdigest(),
        "policy": POLICY,
        "decision_count": len(rows),
        "cooked_choice_count": len(cooked_rows),
        "cooked_choice_top1_matches": {
            name: sum(row["conditions"][name]["order"][0] == row["observed_recipe_id"] for row in cooked_rows)
            for name in ("off", POLICY)
        },
        "claim_scope": "agreement with logged cooked choices; not causal benefit or personalized product quality",
        "rows": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    args = parser.parse_args()
    dataset = FeedbackReplay.model_validate_json(args.input.read_text(encoding="utf-8"))
    print(json.dumps(replay_feedback(dataset), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
