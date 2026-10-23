"""Ingest and score manually created meal plans for the human baseline.

This module is an evaluation input adapter, not a planner.  Human submissions
use the common :class:`BaselineResponse` shape and enter the same scoring
pipeline as every other Sprint 2 baseline.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator, model_validator

from app.evaluation.baseline_output import BaselineResponse, StrictModel
from app.evaluation.pure_llm_baseline import (
    BaselineResources,
    EpisodeResult,
    GenerationResult,
    ModelUsage,
    load_episodes,
    load_resources,
    result_payload,
    score_generation,
)

SYSTEM_ID = "human-manual-planning"


class HumanSubmissionMetadata(StrictModel):
    """Comparison metadata recorded by the human-study facilitator."""

    annotator_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    completion_time_seconds: float = Field(gt=0)
    tools_used: list[str] = Field(default_factory=list)

    @field_validator("annotator_id", "run_id")
    @classmethod
    def identifier_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("identifier must not be blank")
        return value

    @field_validator("tools_used")
    @classmethod
    def tools_must_be_distinct_and_named(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values]
        if any(not value for value in cleaned):
            raise ValueError("tools_used entries must not be blank")
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("tools_used entries must be unique")
        return cleaned


class HumanBaselineSubmission(StrictModel):
    """One recorded human result and the common baseline response it produced."""

    metadata: HumanSubmissionMetadata
    response: BaselineResponse

    @model_validator(mode="after")
    def validate_common_response(self) -> HumanBaselineSubmission:
        if self.response.system_id != SYSTEM_ID:
            raise ValueError(f"response.system_id must be {SYSTEM_ID!r}")
        if self.response.status == "plan":
            if self.response.plan is None or not self.response.plan.meals:
                raise ValueError("a plan response must contain at least one meal")
            for meal in self.response.plan.meals:
                if not meal.dishes:
                    raise ValueError("every submitted meal must contain at least one dish")
                for dish in meal.dishes:
                    if not dish.ingredients:
                        raise ValueError("every submitted dish must contain at least one ingredient")
        elif self.response.plan is not None:
            raise ValueError("clarification and infeasible responses must not contain a plan")
        return self


def load_submissions(path: Path) -> list[HumanBaselineSubmission]:
    """Load strict JSON submissions from one file or a directory of files."""
    files = sorted(path.glob("*.json")) if path.is_dir() else [path]
    submissions: list[HumanBaselineSubmission] = []
    for file in files:
        payload = json.loads(file.read_text(encoding="utf-8"))
        rows = payload if isinstance(payload, list) else payload.get("submissions", [payload])
        if not isinstance(rows, list):
            raise ValueError(f"{file}: submissions must be a list")
        submissions.extend(HumanBaselineSubmission.model_validate(row) for row in rows)
    return submissions


def run_submission(
    episode: dict[str, Any],
    submission: HumanBaselineSubmission,
    *,
    resources: BaselineResources,
) -> EpisodeResult:
    """Send a human-authored response through the shared baseline scorer."""
    episode_id = str(episode.get("episode_id") or episode.get("scenario_id") or episode.get("id") or "")
    if not episode_id:
        raise ValueError("episode has no episode_id, scenario_id, or id")
    if submission.response.episode_id != episode_id:
        raise ValueError("submission episode_id does not match the evaluation episode")
    generated = GenerationResult(
        response=submission.response,
        attempts=1,
        elapsed_seconds=submission.metadata.completion_time_seconds,
        usage=ModelUsage(input_tokens=0, output_tokens=0, total_tokens=0, cost_usd=0.0),
        parse_errors=(),
    )
    return score_generation(episode, generated, system_id=SYSTEM_ID, resources=resources)


def _index_unique(items: list[Any], identifier: Any, *, label: str) -> dict[str, Any]:
    indexed: dict[str, Any] = {}
    for item in items:
        key = identifier(item)
        if not key:
            raise ValueError(f"{label} has no episode identifier")
        if key in indexed:
            raise ValueError(f"duplicate {label} episode identifier: {key}")
        indexed[key] = item
    return indexed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--episodes", type=Path, required=True)
    parser.add_argument("--submissions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    episodes = _index_unique(
        load_episodes(args.episodes),
        lambda row: str(row.get("episode_id") or row.get("scenario_id") or row.get("id") or ""),
        label="evaluation",
    )
    submissions = _index_unique(
        load_submissions(args.submissions),
        lambda row: row.response.episode_id,
        label="human submission",
    )
    if episodes.keys() != submissions.keys():
        missing = sorted(episodes.keys() - submissions.keys())
        unknown = sorted(submissions.keys() - episodes.keys())
        raise ValueError(f"submission coverage mismatch; missing={missing}, unknown={unknown}")

    resources = load_resources()
    results = [
        run_submission(episode, submissions[episode_id], resources=resources)
        for episode_id, episode in episodes.items()
    ]
    report = {
        "system_id": SYSTEM_ID,
        "episodes": [
            {
                "metadata": submissions[result.episode_id].metadata.model_dump(mode="json"),
                **result_payload(result),
            }
            for result in results
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"human baseline: {sum(result.valid_output for result in results)}/{len(results)} valid outputs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
