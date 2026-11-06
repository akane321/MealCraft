"""Compare the product improvement pass on all full-default developer households."""

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

from app.evaluation import full_default  # noqa: E402
from app.planning import product_path  # noqa: E402
from planning_stage_profile import PlanningStageProfile  # noqa: E402


def interleaved_conditions(widths, steps, repeats):
    """Rotate deterministic condition order each round to reduce order drift."""
    conditions = [(width, step) for width in widths for step in steps]
    scheduled = []
    for repeat in range(repeats):
        offset = repeat % len(conditions)
        for order, condition in enumerate(conditions[offset:] + conditions[:offset]):
            scheduled.append((repeat, order, *condition))
    return scheduled


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--steps", type=int, nargs="+", default=[0, 50])
    parser.add_argument("--widths", type=int, nargs="+", help="Optional product beam widths to compare")
    parser.add_argument("--repeats", type=int, default=1, help="Matched interleaved rounds per condition")
    parser.add_argument("--cases", nargs="+", choices=[c["case"] for c in full_default.CASES])
    parser.add_argument("--profile", action="store_true", help="Record overlapping stage timings separately")
    parser.add_argument("--without-candidate-reuse", action="store_true", help="Diagnostic uncached comparison")
    args = parser.parse_args()
    if min(args.steps) < 0 or len(set(args.steps)) != len(args.steps):
        parser.error("steps must be distinct nonnegative integers")
    if args.widths and (min(args.widths) < 1 or len(set(args.widths)) != len(args.widths)):
        parser.error("widths must be distinct positive integers")
    if args.repeats < 1:
        parser.error("repeats must be positive")
    args.output.mkdir(parents=True, exist_ok=True)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    original = product_path.improve_product_plan
    run_case = full_default.run_case
    build_service = full_default.build_meal_plan_service
    cases = [c for c in full_default.CASES if not args.cases or c["case"] in args.cases]
    widths = args.widths or [None]
    artifacts = {(width, steps): [] for width in widths for steps in args.steps}
    paths = {
        (width, steps): args.output / (f"steps-{steps}.json" if width is None else f"width-{width}-steps-{steps}.json")
        for width in widths
        for steps in args.steps
    }
    existing = [str(path) for path in paths.values() if path.exists()]
    if existing:
        raise ValueError(f"Use a fresh output directory; files exist: {existing}")

    for repeat, order, width, steps in interleaved_conditions(widths, args.steps, args.repeats):
        profiles, improvements = [], []

        def improve(problem, initial, losses, *, _steps=steps, _improvements=improvements, **kwargs):
            if not _steps:
                return initial, {"algorithm": "beam-only", "steps": 0}
            result, trace = original(problem, initial, losses, steps=_steps, **kwargs)
            _improvements.append(trace)
            return result, trace

        def progress(
            plans,
            session,
            case,
            *,
            _steps=steps,
            _improvements=improvements,
            _profiles=profiles,
            _repeat=repeat,
            _order=order,
            _width=width,
        ):
            start = len(_improvements)
            with PlanningStageProfile() if args.profile else nullcontext() as profile:
                result, elapsed = run_case(plans, session, case)
            _profiles.append(
                {
                    "case": case["case"],
                    "stages": profile.snapshot() if profile else None,
                    "improvements": _improvements[start:],
                }
            )
            print(
                f"repeat={_repeat} order={_order} width={_width or 'default'} steps={_steps}: "
                f"{case['case']} {result['outcome']} in {elapsed:.2f}s",
                flush=True,
            )
            return result, elapsed

        def configured_service(*service_args, _width=width, **service_kwargs):
            service = build_service(*service_args, **service_kwargs)
            if _width is not None:
                service.planning_engine = product_path.ProductPlanningEngine(overrides={"width": _width})
            return service

        with (
            patch.object(product_path, "improve_product_plan", improve),
            patch.object(full_default, "run_case", progress),
            patch.object(full_default, "CASES", cases),
            patch.object(full_default, "build_meal_plan_service", configured_service),
            patch.object(
                product_path,
                "ProductMealCandidates",
                product_path.MealBeamPlanner if args.without_candidate_reuse else product_path.ProductMealCandidates,
            ),
        ):
            report, timings = full_default.evaluate(repeats=0)
        artifacts[(width, steps)].append(
            {
                "repeat": repeat,
                "order": order,
                "report": report,
                "timings": timings,
                "stage_profiles": profiles,
            }
        )
        print(f"width={width or 'default'} steps={steps}: passed={report['passed']}", flush=True)

    for (width, steps), runs in artifacts.items():
        artifact = {
            "commit": commit,
            "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "profiler_sha256": hashlib.sha256((ROOT / "scripts/planning_stage_profile.py").read_bytes()).hexdigest(),
            "working_tree_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT)),
            "machine": platform.processor(),
            "logical_cpus": os.cpu_count(),
            "width": width or product_path.BeamLimits().width,
            "width_is_default": width is None,
            "steps": steps,
            "repeats": args.repeats,
            # Keep these aliases for readers of the original one-run format.
            "report": runs[0]["report"],
            "timings": runs[0]["timings"],
            "cases": [c["case"] for c in cases],
            "runs": runs,
            "profiling_enabled": args.profile,
            "candidate_reuse": not args.without_candidate_reuse,
            "schedule": "round-robin rotated condition order",
            "timing_note": "Stage times are inclusive and overlap; profiling adds overhead. Do not sum stages.",
            "scope": (
                "full-default developer households; fixture prices; repeated interleaved developer calibration; "
                "no optimality or default-setting claim"
            ),
        }
        path = paths[(width, steps)]
        path.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
        print(f"{path.name}: all_passed={all(run['report']['passed'] for run in runs)}", flush=True)


if __name__ == "__main__":
    main()
