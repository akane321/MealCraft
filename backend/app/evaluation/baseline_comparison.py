"""Run every Sprint 2 baseline through one comparison and reporting path."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import traceback
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic_core import to_jsonable_python

from app.evaluation import (
    algorithm_ladder_baseline,
    generic_agent_baseline,
    human_baseline,
    pure_llm_baseline,
    rag_baseline,
    strong_rule_baseline,
)
from app.evaluation.pure_llm_baseline import BaselineResources, EpisodeResult, load_episodes, load_resources

ArmKind = Literal["stochastic", "deterministic", "human"]
RunEpisode = Callable[[dict[str, Any]], EpisodeResult]


@dataclass(frozen=True)
class Arm:
    system_id: str
    kind: ArmKind
    run_episode: RunEpisode


def episode_id(episode: dict[str, Any]) -> str:
    value = str(episode.get("episode_id") or episode.get("scenario_id") or episode.get("id") or "")
    if not value:
        raise ValueError("episode has no episode_id, scenario_id, or id")
    return value


def select_episodes(episodes: Iterable[dict[str, Any]], selected: set[str] | None) -> list[dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for episode in episodes:
        identifier = episode_id(episode)
        if identifier in indexed:
            raise ValueError(f"duplicate evaluation episode identifier: {identifier}")
        indexed[identifier] = episode
    if selected is None:
        return list(indexed.values())
    unknown = sorted(selected - indexed.keys())
    if unknown:
        raise ValueError(f"unknown evaluation episodes: {', '.join(unknown)}")
    return [episode for identifier, episode in indexed.items() if identifier in selected]


def default_arms(
    *,
    resources: BaselineResources,
    human_submissions: list[human_baseline.HumanBaselineSubmission] | None = None,
    selected: set[str] | None = None,
) -> dict[str, Arm]:
    """Construct adapters over the existing arms; no planning logic lives here."""
    wanted = selected or {
        pure_llm_baseline.SYSTEM_ID,
        rag_baseline.SYSTEM_ID,
        generic_agent_baseline.SYSTEM_ID,
        strong_rule_baseline.SYSTEM_ID,
        *algorithm_ladder_baseline.implemented_system_ids(),
        *([human_baseline.SYSTEM_ID] if human_submissions else []),
    }
    submissions = {item.response.episode_id: item for item in human_submissions or []}
    arms: dict[str, Arm] = {}
    if pure_llm_baseline.SYSTEM_ID in wanted:
        pure_model = pure_llm_baseline.create_model()
        arms[pure_llm_baseline.SYSTEM_ID] = Arm(
            pure_llm_baseline.SYSTEM_ID,
            "stochastic",
            lambda episode: pure_llm_baseline.run_episode(episode, model=pure_model, resources=resources),
        )
    if rag_baseline.SYSTEM_ID in wanted:
        rag_model = rag_baseline.create_model()
        rag_catalog = rag_baseline.load_catalog_context()
        arms[rag_baseline.SYSTEM_ID] = Arm(
            rag_baseline.SYSTEM_ID,
            "stochastic",
            lambda episode: rag_baseline.run_episode(
                episode, model=rag_model, resources=resources, catalog=rag_catalog
            ),
        )
    if generic_agent_baseline.SYSTEM_ID in wanted:
        generic_agent = generic_agent_baseline.create_agent()
        arms[generic_agent_baseline.SYSTEM_ID] = Arm(
            generic_agent_baseline.SYSTEM_ID,
            "stochastic",
            lambda episode: generic_agent_baseline.run_episode(episode, agent=generic_agent, resources=resources),
        )
    if strong_rule_baseline.SYSTEM_ID in wanted:
        arms[strong_rule_baseline.SYSTEM_ID] = Arm(
            strong_rule_baseline.SYSTEM_ID,
            "deterministic",
            lambda episode: strong_rule_baseline.run_episode(episode, resources=resources),
        )
    for system_id in algorithm_ladder_baseline.implemented_system_ids():
        if system_id not in wanted:
            continue
        arms[system_id] = Arm(
            system_id,
            "deterministic",
            lambda episode, selected=system_id: algorithm_ladder_baseline.run_episode(
                episode, system_id=selected, resources=resources
            ),
        )
    if human_baseline.SYSTEM_ID in wanted and submissions:
        arms[human_baseline.SYSTEM_ID] = Arm(
            human_baseline.SYSTEM_ID,
            "human",
            lambda episode: human_baseline.run_submission(
                episode, submissions[episode_id(episode)], resources=resources
            ),
        )
    return arms


def _hard_constraints(episode: dict[str, Any], result: EpisodeResult) -> dict[str, bool | None]:
    scenario = episode.get("scenario", episode)
    gold = episode.get("gold") or {}
    declared = gold.get("applicable_hard_constraints") or {}
    profile = scenario.get("household_profile") or {}
    recomputed = result.recomputation
    checks: dict[str, bool | None] = {}

    expected_class = gold.get("class")
    response = result.generation.response
    if expected_class and response is not None:
        expected_status = {"feasible": "plan", "needs_clarification": "clarification", "infeasible": "infeasible"}.get(
            expected_class
        )
        checks["episode_class"] = response.status == expected_status if expected_status else None

    allergens = set(profile.get("allergens") or declared.get("allergens") or [])
    if allergens:
        checks["allergens"] = (
            None
            if recomputed is None or not recomputed.allergens_complete
            else not bool(allergens & set(recomputed.allergens))
        )

    budget = declared.get("budget_sgd", scenario.get("budget_sgd"))
    if budget is not None:
        checks["budget"] = (
            None
            if recomputed is None or recomputed.pricing_status != "complete" or recomputed.purchase_total_sgd is None
            else recomputed.purchase_total_sgd <= float(budget)
        )

    bands = declared.get("nutrition_bands") or []
    if bands:
        if recomputed is None or not recomputed.nutrition_complete:
            checks["nutrition"] = None
        else:
            values = recomputed.nutrition.model_dump()
            checks["nutrition"] = all(
                (band.get("min") is None or values[band["metric"]] >= float(band["min"]))
                and (band.get("max") is None or values[band["metric"]] <= float(band["max"]))
                for band in bands
                if band.get("metric") in values
            )
    return checks


def scored_payload(episode: dict[str, Any], result: EpisodeResult) -> dict[str, Any]:
    raw = to_jsonable_python(pure_llm_baseline.result_payload(result))
    checks = _hard_constraints(episode, result)
    hard_success = bool(result.valid_output and checks and all(value is True for value in checks.values()))
    if not checks:
        hard_success = result.valid_output
    response = result.generation.response
    requires_coverage = bool(response is not None and response.status == "plan")
    verifiable = bool(result.verification and result.verification.verifiable)
    raw["comparison"] = {
        "hard_constraint_checks": checks,
        "hard_constraint_success": hard_success,
        "strict_success": hard_success and (verifiable or not requires_coverage),
        "coverage_adjusted_success": hard_success,
    }
    return raw


def _digest(episode: dict[str, Any]) -> str:
    encoded = json.dumps(episode, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _raw_path(output_dir: Path, arm: Arm, repeat: int, identifier: str) -> Path:
    return output_dir / "raw" / arm.system_id / f"repeat-{repeat:03d}" / f"{identifier}.json"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_comparison(
    *,
    episodes: list[dict[str, Any]],
    arms: list[Arm],
    output_dir: Path,
    repeats: int = 1,
    force_deterministic: bool = False,
) -> dict[str, Any]:
    if repeats < 1:
        raise ValueError("repeats must be at least 1")
    rows: list[dict[str, Any]] = []
    for arm in arms:
        arm_repeats = repeats if arm.kind == "stochastic" else 1
        for repeat in range(1, arm_repeats + 1):
            for episode in episodes:
                identifier = episode_id(episode)
                path = _raw_path(output_dir, arm, repeat, identifier)
                reused = arm.kind == "deterministic" and path.exists() and not force_deterministic
                if reused:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    if payload.get("episode_sha256") != _digest(episode):
                        raise ValueError(f"cached deterministic result has different episode data: {path}")
                else:
                    started = time.perf_counter()
                    try:
                        result = scored_payload(episode, arm.run_episode(episode))
                        payload = {
                            "schema_version": "baseline-comparison-raw-v1",
                            "status": "completed",
                            "arm_kind": arm.kind,
                            "repeat": repeat,
                            "episode_sha256": _digest(episode),
                            "result": result,
                        }
                    except Exception as error:
                        payload = {
                            "schema_version": "baseline-comparison-raw-v1",
                            "status": "failed",
                            "arm_kind": arm.kind,
                            "repeat": repeat,
                            "episode_sha256": _digest(episode),
                            "error": {
                                "type": type(error).__name__,
                                "message": str(error),
                                "elapsed_seconds": time.perf_counter() - started,
                                "traceback": traceback.format_exc(),
                            },
                        }
                    _write_json(path, payload)
                row = {
                    "system_id": arm.system_id,
                    "arm_kind": arm.kind,
                    "repeat": repeat,
                    "episode_id": identifier,
                    "reused": reused,
                    "raw_result": str(path.relative_to(output_dir)),
                    "status": payload.get("status", "completed"),
                }
                if row["status"] == "completed":
                    row.update(payload["result"])
                else:
                    row["error"] = payload["error"]
                rows.append(row)
    report = _report(rows, episodes)
    _write_json(output_dir / "comparison.json", report)
    return report


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _sum_or_none(values: list[int | float | None]) -> int | float | None:
    return (
        None
        if not values or any(value is None for value in values)
        else sum(value for value in values if value is not None)
    )


def _report(rows: list[dict[str, Any]], episodes: list[dict[str, Any]]) -> dict[str, Any]:
    summaries: dict[str, Any] = {}
    for system_id in dict.fromkeys(row["system_id"] for row in rows):
        mine = [row for row in rows if row["system_id"] == system_id]
        completed = [row for row in mine if row["status"] == "completed"]
        coverage = [row["verification"]["coverage"] for row in completed if row.get("verification")]
        generation = [row["generation"] for row in completed]
        recomputations = [row["recomputation"] for row in completed if row.get("recomputation")]
        summaries[system_id] = {
            "runs": len(mine),
            "completed_runs": len(completed),
            "failed_runs": len(mine) - len(completed),
            "episodes": len({row["episode_id"] for row in mine}),
            "mapping_coverage_mean": _mean(coverage),
            "verifiable": sum(bool(row.get("verification") and row["verification"]["verifiable"]) for row in mine),
            "hard_constraint_success": sum(row["comparison"]["hard_constraint_success"] for row in completed),
            "strict_success": sum(row["comparison"]["strict_success"] for row in completed),
            "coverage_adjusted_success": sum(row["comparison"]["coverage_adjusted_success"] for row in completed),
            "nutrition_complete": sum(item["nutrition_complete"] for item in recomputations),
            "allergens_complete": sum(item["allergens_complete"] for item in recomputations),
            "price_complete": sum(item["pricing_status"] == "complete" for item in recomputations),
            "runtime_seconds_total": sum(item["elapsed_seconds"] for item in generation),
            "token_usage": {
                key: _sum_or_none([item["usage"][key] for item in generation])
                for key in ("input_tokens", "output_tokens", "total_tokens")
            },
            "api_model_cost_usd": _sum_or_none([item["usage"]["cost_usd"] for item in generation]),
        }
    return {
        "schema_version": "baseline-comparison-v1",
        "episode_count": len(episodes),
        "episode_sha256": {episode_id(item): _digest(item) for item in episodes},
        "arms": summaries,
        "runs": rows,
    }


def _csv_set(value: str | None) -> set[str] | None:
    return None if value is None else {item.strip() for item in value.split(",") if item.strip()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--arms", help="Comma-separated system IDs; defaults to every available arm")
    parser.add_argument("--episode-ids", help="Comma-separated episode IDs; defaults to all")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--human-submissions", type=Path)
    parser.add_argument("--force-deterministic", action="store_true")
    args = parser.parse_args()

    resources = load_resources()
    submissions = human_baseline.load_submissions(args.human_submissions) if args.human_submissions else None
    selected_ids = _csv_set(args.arms)
    available = default_arms(resources=resources, human_submissions=submissions, selected=selected_ids)
    selected_ids = selected_ids or set(available)
    unknown = sorted(selected_ids - available.keys())
    if unknown:
        raise ValueError(f"unknown or unavailable baseline arms: {', '.join(unknown)}")
    episodes = select_episodes(load_episodes(args.episodes), _csv_set(args.episode_ids))
    report = run_comparison(
        episodes=episodes,
        arms=[available[system_id] for system_id in available if system_id in selected_ids],
        output_dir=args.output_dir,
        repeats=args.repeats,
        force_deterministic=args.force_deterministic,
    )
    print(f"baseline comparison: {len(report['runs'])} runs across {report['episode_count']} episodes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
