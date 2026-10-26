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

from app.evaluation import full_default  # noqa: E402
from app.planning import product_path  # noqa: E402
from planning_stage_profile import PlanningStageProfile  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--steps", type=int, nargs="+", default=[0, 50])
    parser.add_argument("--cases", nargs="+", choices=[c["case"] for c in full_default.CASES])
    parser.add_argument("--profile", action="store_true", help="Record overlapping stage timings separately")
    parser.add_argument("--without-candidate-reuse", action="store_true", help="Diagnostic uncached comparison")
    args = parser.parse_args()
    if min(args.steps) < 0 or len(set(args.steps)) != len(args.steps):
        parser.error("steps must be distinct nonnegative integers")
    args.output.mkdir(parents=True, exist_ok=True)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    original = product_path.improve_product_plan
    run_case = full_default.run_case
    cases = [c for c in full_default.CASES if not args.cases or c["case"] in args.cases]
    for steps in args.steps:
        profiles, improvements = [], []
        path = args.output / f"steps-{steps}.json"
        if path.exists():
            raise ValueError(f"Use a fresh output directory: {path} exists")

        def improve(problem, initial, losses, *, _steps=steps, _improvements=improvements, **kwargs):
            if not _steps:
                return initial, {"algorithm": "beam-only", "steps": 0}
            result, trace = original(problem, initial, losses, steps=_steps, **kwargs)
            _improvements.append(trace)
            return result, trace

        def progress(plans, session, case, *, _steps=steps, _improvements=improvements, _profiles=profiles):
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
            print(f"steps={_steps}: {case['case']} {result['outcome']} in {elapsed:.2f}s", flush=True)
            return result, elapsed

        with (
            patch.object(product_path, "improve_product_plan", improve),
            patch.object(full_default, "run_case", progress),
            patch.object(full_default, "CASES", cases),
            patch.object(
                product_path,
                "ProductMealCandidates",
                product_path.MealBeamPlanner if args.without_candidate_reuse else product_path.ProductMealCandidates,
            ),
        ):
            report, timings = full_default.evaluate(repeats=0)
        artifact = {
            "commit": commit,
            "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "profiler_sha256": hashlib.sha256((ROOT / "scripts/planning_stage_profile.py").read_bytes()).hexdigest(),
            "working_tree_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT)),
            "machine": platform.processor(),
            "logical_cpus": os.cpu_count(),
            "steps": steps,
            "report": report,
            "timings": timings,
            "cases": [c["case"] for c in cases],
            "stage_profiles": profiles,
            "profiling_enabled": args.profile,
            "candidate_reuse": not args.without_candidate_reuse,
            "timing_note": "Stage times are inclusive and overlap; profiling adds overhead. Do not sum stages.",
            "scope": "full-default developer households; fixture prices; one run per condition; no optimality claim",
        }
        path.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
        print(f"{path.name}: passed={report['passed']}", flush=True)


if __name__ == "__main__":
    main()
