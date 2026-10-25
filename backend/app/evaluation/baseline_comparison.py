"""Offline algorithm comparison wiring only; no paid or formal evaluation entry."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic_core import to_jsonable_python

from app.evaluation import algorithm_ladder_baseline as algorithms
from app.evaluation.baseline_resources import BaselineResources, load_resources


@dataclass(frozen=True)
class Arm:
    system_id: str
    kind: Literal["deterministic", "stochastic"]
    run_episode: Callable[[dict], dict]


def episode_id(episode: dict) -> str:
    value = str(episode.get("episode_id") or episode.get("scenario_id") or episode.get("id") or "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}", value):
        raise ValueError("A development episode needs a safe, nonempty identifier")
    return value


def select_episodes(episodes: Iterable[dict], selected: set[str] | None) -> list[dict]:
    indexed = {}
    for item in episodes:
        identifier = episode_id(item)
        if identifier in indexed:
            raise ValueError(f"duplicate evaluation episode identifier: {identifier}")
        indexed[identifier] = item
    if selected is not None and selected - indexed.keys():
        raise ValueError(f"unknown evaluation episodes: {', '.join(sorted(selected - indexed.keys()))}")
    return [item for key, item in indexed.items() if selected is None or key in selected]


def default_arms(*, resources: BaselineResources, selected: set[str] | None = None) -> dict[str, Arm]:
    wanted = set(algorithms.implemented_system_ids()) if selected is None else selected
    if wanted - set(algorithms.implemented_system_ids()):
        raise ValueError("Only offline algorithm development arms are available; paid and human entries are disabled")
    return {
        system_id: Arm(
            system_id,
            "stochastic" if system_id == "algorithm-rung-6-cp-sat" else "deterministic",
            lambda item, system_id=system_id: algorithms.run_episode(item, system_id=system_id, resources=resources),
        )
        for system_id in algorithms.implemented_system_ids()
        if system_id in wanted
    }


def _digest(episode: dict) -> str:
    return hashlib.sha256(json.dumps(episode, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(to_jsonable_python(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _outcome(result: dict) -> dict:
    validation = result.get("scored", {}).get("validation", {})
    # Missing/skipped validation is unscored, never an automatic pass.
    return {
        "strict_passed": validation.get("strict_passed"),
        "adjusted_passed": validation.get("adjusted_passed"),
        "unverified": validation.get("unverified"),
        "scored": "strict_passed" in validation and "adjusted_passed" in validation,
    }


def run_comparison(*, episodes: list[dict], arms: list[Arm], output_dir: Path, repeats: int = 1) -> dict:
    if repeats < 1:
        raise ValueError("repeats must be at least 1")
    episodes = select_episodes(episodes, None)
    allowed = set(algorithms.implemented_system_ids())
    if any(arm.system_id not in allowed for arm in arms) or len({a.system_id for a in arms}) != len(arms):
        raise ValueError("Only unique offline algorithm arms are available")
    if any(
        any(token in part.casefold() for token in ("heldout", "held-out", "held_out", "holdout", "workbench"))
        for part in output_dir.resolve().parts
    ):
        raise ValueError("Protected output paths are not available")
    # No stale/failure cache and no accidental overwrite of a previous run.
    output_dir.mkdir(parents=True, exist_ok=False)
    rows = []
    for arm in arms:
        for repeat in range(1, (repeats if arm.kind == "stochastic" else 1) + 1):
            for item in episodes:
                identifier = episode_id(item)
                started = time.perf_counter()
                row = {
                    "system_id": arm.system_id,
                    "episode_id": identifier,
                    "repeat": repeat,
                    "arm_kind": arm.kind,
                    "episode_sha256": _digest(item),
                    "development_only": True,
                }
                try:
                    result = arm.run_episode(item)
                    if result.get("system_id") != arm.system_id or result.get("episode_id") != identifier:
                        raise ValueError("Runner result identity differs from the selected arm/episode")
                    row.update(status="completed", result=result, outcome=_outcome(result))
                except Exception as error:
                    row.update(
                        status="failed",
                        error={"type": type(error).__name__, "message": str(error)},
                        outcome={"strict_passed": None, "adjusted_passed": None, "unverified": None, "scored": False},
                    )
                row["elapsed_seconds"] = time.perf_counter() - started
                path = output_dir / "raw" / arm.system_id / f"repeat-{repeat:03d}" / f"{identifier}.json"
                row["raw_result"] = str(path.relative_to(output_dir))
                _write(path, row)
                rows.append(row)
    summary = {}
    for arm in arms:
        mine = [row for row in rows if row["system_id"] == arm.system_id]
        summary[arm.system_id] = {
            "runs": len(mine),
            "failed_runs": sum(row["status"] == "failed" for row in mine),
            "unscored_runs": sum(not row["outcome"]["scored"] for row in mine),
            "strict_passed": sum(row["outcome"]["strict_passed"] is True for row in mine),
            "adjusted_passed": sum(row["outcome"]["adjusted_passed"] is True for row in mine),
            "elapsed_seconds": sum(row["elapsed_seconds"] for row in mine),
        }
    report = {
        "schema_version": "offline-algorithm-comparison-dev-v1",
        "development_only": True,
        "episode_count": len(episodes),
        "arms": summary,
        "runs": rows,
    }
    _write(output_dir / "comparison.json", report)
    return report


def _csv(value: str | None) -> set[str] | None:
    return None if value is None else {part.strip() for part in value.split(",") if part.strip()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--arms", help="Offline algorithm system IDs only")
    parser.add_argument("--episode-ids")
    parser.add_argument("--repeats", type=int, default=1)
    args = parser.parse_args()
    episodes = select_episodes(algorithms.load_development_episodes(args.episodes), _csv(args.episode_ids))
    arms = default_arms(resources=load_resources(), selected=_csv(args.arms))
    report = run_comparison(
        episodes=episodes, arms=list(arms.values()), output_dir=args.output_dir, repeats=args.repeats
    )
    print(f"Offline development only: {len(report['runs'])} runs; no paid or formal evaluation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
