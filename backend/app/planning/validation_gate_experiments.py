"""Paired offline final-gate diagnostic; unchecked drafts are never product plans."""

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from time import perf_counter

from pydantic import Field, model_validator

from app.planning.beam_planner import BeamLimits, BeamPlanner
from app.planning.developer_experiments import ExperimentCase, ExperimentDataset, digest, source_fingerprint
from app.planning.final_scope_validator import FinalPlanningValidator
from app.planning.input_audit import require_finite_problem
from app.planning.meal_beam import MealBeamLimits, MealBeamPlanner, assignments_of
from app.schemas.planning_v2 import PlanningAssignment


class GateCase(ExperimentCase):
    @model_validator(mode="after")
    def check_packet(self):
        require_finite_problem(self.problem)
        if self.snapshots or self.provider_unavailable:
            raise ValueError("Final-gate comparison requires fixed snapshots")
        return self


class GateDataset(ExperimentDataset):
    cases: list[GateCase] = Field(min_length=1)


def compare_validation_gate(problem, *, width=32, max_expansions=10000):
    """Hold search and shopping fixed; vary whether final validation can veto selection.

    Compiler filters, search-side hard guards, nutrition pruning and dominance
    remain active in both conditions. This is not all-validation-off.
    """
    for name, value, upper in (("width", width, 1000), ("max_expansions", max_expansions, 1000000)):
        if type(value) is not int or not 1 <= value <= upper:
            raise ValueError(f"{name} must be an integer in [1, {upper}]")
    packet = problem.model_copy(deep=True)
    require_finite_problem(packet)
    composed = any(slot.composition is not None for slot in packet.slots)
    limits = (
        MealBeamLimits(width=width, max_expansions=max_expansions) if composed else BeamLimits(width, max_expansions)
    )
    planner = MealBeamPlanner(limits) if composed else BeamPlanner(limits)
    started = perf_counter()
    search = planner.search_candidates(packet)
    candidates = []
    for state in sorted(search.states, key=lambda s: (s.loss, s.choices)):
        assignments = (
            assignments_of(state)
            if composed
            else [PlanningAssignment(slot_id=s, recipe_id=r) for s, r in state.choices]
        )
        shopping = planner._build_shopping(packet, assignments)
        candidates.append({"loss": state.loss, "assignments": assignments, "shopping": shopping})
    generation_seconds = perf_counter() - started
    # Freeze the off condition before running any validator. Audit may observe,
    # but may neither replace nor repair its selected draft.
    unchecked_index = 0 if candidates else None
    gate_start = perf_counter()
    gate_reports = [FinalPlanningValidator().validate(packet, c["assignments"], c["shopping"]) for c in candidates]
    gated_index = next((i for i, r in enumerate(gate_reports) if r.status == "passed"), None)
    gate_seconds = perf_counter() - gate_start
    conditions = {}
    for name, index in (("final_gate_off", unchecked_index), ("final_gate_on", gated_index)):
        candidate = candidates[index] if index is not None else None
        audit_start = perf_counter()
        audit = (
            FinalPlanningValidator().validate(packet, candidate["assignments"], candidate["shopping"])
            if candidate
            else None
        )
        conditions[name] = {
            "selection_status": "draft_selected" if candidate else "no_candidate_selected",
            "candidate_index": index,
            "loss": candidate["loss"] if candidate else None,
            "assignments": [a.model_dump(mode="json") for a in candidate["assignments"]] if candidate else [],
            "shopping": [s.model_dump(mode="json") for s in candidate["shopping"]] if candidate else [],
            "audit": audit.model_dump(mode="json") if audit else None,
            "audit_seconds": perf_counter() - audit_start,
        }
    return {
        "problem_id": packet.problem_id,
        "input_sha256": digest(packet.model_dump(mode="json")),
        "configuration": {
            "engine": "meal-beam" if composed else "one-dish-beam",
            "engine_limits": asdict(limits),
            "width": width,
            "max_expansions": max_expansions,
            "repair_rounds": 0,
            "ranking": "off",
            "seed": None,
            "shopping_policy": "single-product-per-ingredient",
        },
        "search": {k: v for k, v in asdict(search).items() if k != "states"},
        "candidate_count": len(candidates),
        "generation_seconds": generation_seconds,
        "gate_seconds": gate_seconds,
        "conditions": conditions,
        "candidate_checks": [
            {
                "candidate_index": i,
                "status": r.status,
                "failures": [c.model_dump(mode="json") for c in r.checks if c.hard and c.status != "passed"],
            }
            for i, r in enumerate(gate_reports)
        ],
        "claim_scope": "effect of final selection gate on retained component beam candidates only",
        "persistable": False,
    }


def run_gate_experiments(dataset, *, width=32, max_expansions=10000):
    if any(case.snapshots or case.provider_unavailable for case in dataset.cases):
        raise ValueError("Final-gate comparison requires fixed snapshots; repair fixtures are not supported")
    return {
        "protocol": "planning-final-gate-dev-v2",
        "evidence": "developer_diagnostic",
        "dataset_version": dataset.version,
        "dataset_sha256": digest(dataset.model_dump(mode="json")),
        "implementation": source_fingerprint(),
        "runs": [
            {
                "case_id": c.case_id,
                "category": c.category,
                **compare_validation_gate(c.problem, width=width, max_expansions=max_expansions),
            }
            for c in dataset.cases
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--width", type=int, default=32)
    parser.add_argument("--max-expansions", type=int, default=10000)
    args = parser.parse_args()
    raw = args.input.read_bytes()
    dataset = GateDataset.model_validate_json(raw)
    report = run_gate_experiments(dataset, width=args.width, max_expansions=args.max_expansions)
    report["dataset_file_sha256"] = hashlib.sha256(raw).hexdigest()
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
