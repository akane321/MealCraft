"""Developer-only Planning ablations; never a product validation bypass."""

import argparse
import hashlib
import json
import platform
from dataclasses import asdict
from pathlib import Path
from time import perf_counter
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.planning.beam_planner import BeamLimits, BeamPlanner
from app.planning.final_scope_reference import FinalScopeReferencePlanner
from app.planning.final_scope_validator import FinalPlanningValidator
from app.planning.input_audit import require_finite_problem
from app.planning.meal_composition import require_one_dish_slots
from app.planning.snapshot_repair import RetrievalUnavailable, solve_with_repair, validate_product_snapshot
from app.planning.workbench import FileSnapshots
from app.schemas.planning_v2 import FinalPlanningProblem

PRESETS = ("beam", "greedy", "variety_off", "overlap_off", "repair_off")


class ExperimentCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str = Field(min_length=1)
    category: str = Field(min_length=1)
    problem: FinalPlanningProblem
    snapshots: list[dict] = Field(default_factory=list)
    provider_unavailable: bool = False

    @model_validator(mode="after")
    def check_packet(self):
        require_finite_problem(self.problem)
        require_one_dish_slots(self.problem)
        if self.provider_unavailable and self.snapshots:
            raise ValueError("Unavailable provider cannot also supply snapshots")
        provider = FileSnapshots(self.snapshots)
        for _ in self.snapshots:
            validate_product_snapshot(provider.retrieve(()))
        return self


class ExperimentDataset(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str = Field(min_length=1)
    source: Literal["synthetic", "developer"]
    cases: list[ExperimentCase] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_cases(self):
        ids = [case.case_id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("Case IDs must be unique")
        return self


class UnavailableProvider:
    def retrieve(self, demands):
        raise RetrievalUnavailable("Developer fixture provider unavailable")


def digest(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def source_fingerprint():
    """Hash executable app sources, including uncommitted changes, with normalized newlines."""
    root = Path(__file__).resolve().parents[1]
    files = {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_text(encoding="utf-8-sig").encode()).hexdigest()
        for p in sorted(root.rglob("*.py"))
    }
    return {"app_source_sha256": digest(files), "python": platform.python_version()}


def run_experiments(dataset, *, repeats=1, width=32, max_expansions=10000, repair_rounds=1):
    """Run paired conditions on detached packets and audit the final snapshot afresh.

    These are component diagnostics on one-dish slots, not end-to-end scores.
    The reference greedy selector is not the evaluation B1 strong rule baseline.
    """
    for name, value, minimum, maximum in (
        ("repeats", repeats, 1, 20),
        ("width", width, 1, 1000),
        ("max_expansions", max_expansions, 1, 1000000),
        ("repair_rounds", repair_rounds, 0, 10),
    ):
        if type(value) is not int or not minimum <= value <= maximum:
            raise ValueError(f"{name} must be an integer in [{minimum}, {maximum}]")
    rows = []
    for case in dataset.cases:
        for preset in PRESETS:
            problem = case.problem.model_copy(deep=True)
            weight = {"variety_off": "diversity_penalty", "overlap_off": "overlap_reward_weight"}.get(preset)
            if weight and (problem.diversity_policy is None or getattr(problem.diversity_policy, weight) == 0):
                rows.append(
                    {
                        "case_id": case.case_id,
                        "preset": preset,
                        "status": "not_applicable",
                        "reason": "No active explicit weight to remove",
                    }
                )
                continue
            if weight:
                problem.diversity_policy = problem.diversity_policy.model_copy(update={weight: 0.0})
            rounds = 0 if preset == "repair_off" else repair_rounds
            for repeat in range(repeats):
                provider = UnavailableProvider() if case.provider_unavailable else FileSnapshots(case.snapshots)
                planner = (
                    FinalScopeReferencePlanner()
                    if preset == "greedy"
                    else BeamPlanner(BeamLimits(width, max_expansions))
                )
                started = perf_counter()
                result = solve_with_repair(problem, provider, max_rounds=rounds, planner=planner)
                solve_seconds = perf_counter() - started
                last = result.attempts[-1]
                # A degraded observation is recorded but was not adopted by repair.
                used = next(
                    a
                    for a in reversed(result.attempts)
                    if a.snapshot_version == result.solution.validation.product_snapshot_version
                )
                audit_problem = problem.model_copy(
                    deep=True,
                    update={"products": list(used.products), "product_snapshot_version": used.snapshot_version},
                )
                audit_started = perf_counter()
                audit = FinalPlanningValidator().validate(
                    audit_problem, result.solution.assignments, result.solution.shopping
                )
                audit_seconds = perf_counter() - audit_started
                output = result.solution.model_dump(mode="json")
                rows.append(
                    {
                        "case_id": case.case_id,
                        "category": case.category,
                        "preset": preset,
                        "repeat": repeat,
                        "status": result.solution.status,
                        "stop_reason": result.stop_reason,
                        "input_sha256": digest(case.model_dump(mode="json")),
                        "effective_problem_sha256": digest(problem.model_dump(mode="json")),
                        "effective_weights": problem.diversity_policy.model_dump(mode="json")
                        if problem.diversity_policy
                        else None,
                        "configuration": {
                            "width": None if preset == "greedy" else width,
                            "max_expansions": None if preset == "greedy" else max_expansions,
                            "repair_rounds": rounds,
                            "ranking": "off",
                            "validation": "on",
                            "seed": None,
                        },
                        "solve_seconds": solve_seconds,
                        "audit_seconds": audit_seconds,
                        "solution_sha256": digest(output),
                        "solution": output,
                        "audit": audit.model_dump(mode="json"),
                        "last_observed_snapshot": last.snapshot_version,
                        "attempts": [asdict(a) for a in result.attempts],
                        "failures": [
                            {"code": c.code, "status": c.status, "scope_id": c.scope_id, "detail": c.detail}
                            for c in audit.checks
                            if c.hard and c.status != "passed"
                        ],
                    }
                )
    # Pydantic evidence in repair attempts is serialized without discarding provenance.
    for row in rows:
        for attempt in row.get("attempts", []):
            attempt["products"] = [p.model_dump(mode="json") for p in attempt["products"]]
            if attempt["retrieval"] is not None:
                attempt["retrieval"] = attempt["retrieval"].model_dump(mode="json")
    return {
        "protocol": "planning-component-ablation-dev-v1",
        "evidence": "developer_diagnostic",
        "dataset_version": dataset.version,
        "dataset_sha256": digest(dataset.model_dump(mode="json")),
        "implementation": source_fingerprint(),
        "repeats": repeats,
        "presets": list(PRESETS),
        "deferred": ["validation_off", "learned_ranking_off", "composed_meals", "console_integration"],
        "category_counts": {
            category: sum(c.category == category for c in dataset.cases)
            for category in sorted({c.category for c in dataset.cases})
        },
        "runs": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--width", type=int, default=32)
    parser.add_argument("--max-expansions", type=int, default=10000)
    parser.add_argument("--repair-rounds", type=int, default=1)
    args = parser.parse_args()
    raw = args.input.read_bytes()
    dataset = ExperimentDataset.model_validate_json(raw)
    result = run_experiments(
        dataset,
        repeats=args.repeats,
        width=args.width,
        max_expansions=args.max_expansions,
        repair_rounds=args.repair_rounds,
    )
    result["dataset_file_sha256"] = hashlib.sha256(raw).hexdigest()
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
