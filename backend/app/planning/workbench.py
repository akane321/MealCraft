"""Offline Planning workbench; does not modify production routes or persisted plans."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from app.planning.beam_planner import BeamLimits, BeamPlanner
from app.planning.exhaustive_oracle import exhaustive_assignments
from app.planning.input_audit import nonfinite_issues
from app.planning.mixed_beam import solve_mixed_beam
from app.planning.mixed_plan_oracle import exhaustive_mixed_plan
from app.planning.mixed_repair import solve_mixed_with_repair
from app.planning.package_optimizer import optimize_packages
from app.planning.package_validator import validate_packages
from app.planning.relaxation_search import RelaxationChange, propose_relaxations
from app.planning.snapshot_repair import ProductSnapshot, RetrievalUnavailable, solve_with_repair
from app.planning.whole_plan_scoring import WholePlanPolicy, score_plan
from app.schemas.planning_v2 import FinalPlanningProblem, PlanningProductOption
from app.schemas.retrieval import RetrievalTrace


def reject_nonfinite(value):
    issues = nonfinite_issues(value)
    if issues:
        print(json.dumps({"status": "invalid_input", "issues": [asdict(i) for i in issues]}, allow_nan=False))
        raise SystemExit(2)


class FileSnapshots:
    def __init__(self, snapshots):
        self.snapshots = iter(snapshots)

    def retrieve(self, demands):
        try:
            value = next(self.snapshots)
        except StopIteration as exc:
            raise RetrievalUnavailable("No additional fixture snapshots") from exc
        trace = RetrievalTrace.model_validate(value["trace"])
        if trace.mode != "fixture" or trace.provider_used != "fixture":
            raise ValueError("The offline workbench accepts fixture snapshots only")
        products = tuple(PlanningProductOption.model_validate(p) for p in value["products"])
        reject_nonfinite({"snapshot": {"products": [p.model_dump() for p in products]}})
        return ProductSnapshot(value["version"], products, trace)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "operation", choices=["plan", "mixed-plan", "oracle", "mixed-oracle", "packages", "relax", "repair"]
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("--options", type=Path, help="Explicit relaxation choices or ordered fixture snapshots")
    parser.add_argument("--width", type=int, default=32)
    parser.add_argument("--limit", type=int, default=10000)
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--whole-plan", action="store_true", help="Opt into experimental finalist scoring")
    parser.add_argument("--cp-sat", action="store_true", help="Optional package solver for packages or mixed-oracle")
    parser.add_argument("--mixed-packages", action="store_true", help="Use mixed shopping for relax or repair")
    args = parser.parse_args()
    if args.mixed_packages and args.operation not in ("relax", "repair"):
        parser.error("--mixed-packages is supported for relax and repair only")
    if args.whole_plan and args.operation not in ("plan", "mixed-plan", "oracle", "mixed-oracle", "repair"):
        parser.error("--whole-plan is supported for plan, mixed-plan, oracle, mixed-oracle and repair only")
    if args.cp_sat and args.operation not in ("packages", "mixed-oracle"):
        parser.error("--cp-sat is supported for packages and mixed-oracle only")
    scoring = WholePlanPolicy() if args.whole_plan else None
    data = json.loads(args.input.read_text(encoding="utf-8-sig"))
    reject_nonfinite(data)
    if args.operation == "packages":
        products = [PlanningProductOption.model_validate(p) for p in data["products"]]
        reject_nonfinite({"products": [p.model_dump() for p in products]})
        if args.cp_sat:
            from app.planning.package_cp_sat import solve_packages_cp_sat

            output = asdict(
                solve_packages_cp_sat(data["ingredient_id"], data.get("required"), data.get("unit"), products)
            )
            print(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False))
            return
        result = optimize_packages(
            data["ingredient_id"], data.get("required"), data.get("unit"), products, max_combinations=args.limit
        )
        output = asdict(result)
        output["validation"] = (
            list(validate_packages(data["ingredient_id"], data["required"], data["unit"], result, products))
            if result.status == "optimal"
            else ["not_completed"]
        )
    else:
        problem = FinalPlanningProblem.model_validate(data)
        reject_nonfinite(problem.model_dump())
        if args.operation == "plan":
            solution = BeamPlanner(BeamLimits(args.width, args.limit), scoring).solve(problem)
            output = solution.model_dump(mode="json")
            if scoring and solution.status == "feasible":
                output["experimental_score"] = asdict(score_plan(problem, solution.assignments, scoring))
        elif args.operation == "mixed-plan":
            output = asdict(
                solve_mixed_beam(problem, limits=BeamLimits(args.width, args.limit), scoring_policy=scoring)
            )
        elif args.operation == "oracle":
            output = asdict(exhaustive_assignments(problem, max_combinations=args.limit, scoring_policy=scoring))
        elif args.operation == "mixed-oracle":
            output = asdict(
                exhaustive_mixed_plan(
                    problem, max_assignments=args.limit, use_cp_sat=args.cp_sat, scoring_policy=scoring
                )
            )
        else:
            if args.options is None:
                parser.error("--options is required for repair and relax")
            options = json.loads(args.options.read_text(encoding="utf-8-sig"))
            reject_nonfinite({"options": options})
            if args.operation == "relax":
                output = asdict(
                    propose_relaxations(
                        problem,
                        tuple(RelaxationChange(**o) for o in options),
                        max_combinations=args.limit,
                        mixed_packages=args.mixed_packages,
                    )
                )
            else:
                result = (
                    solve_mixed_with_repair(
                        problem,
                        FileSnapshots(options),
                        max_rounds=args.rounds,
                        limits=BeamLimits(args.width, args.limit),
                        scoring_policy=scoring,
                    )
                    if args.mixed_packages
                    else solve_with_repair(
                        problem,
                        FileSnapshots(options),
                        max_rounds=args.rounds,
                        planner=BeamPlanner(BeamLimits(args.width, args.limit), scoring),
                    )
                )
                output = {
                    "solution": asdict(result.solution)
                    if args.mixed_packages
                    else result.solution.model_dump(mode="json"),
                    "stop_reason": result.stop_reason,
                    "attempts": [
                        {
                            "snapshot_version": a.snapshot_version,
                            "planning_status": a.planning_status,
                            "demands": [asdict(d) for d in a.demands],
                            "products": [p.model_dump(mode="json") for p in a.products],
                            "retrieval": a.retrieval.model_dump(mode="json") if a.retrieval else None,
                        }
                        for a in result.attempts
                    ],
                }
    print(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
