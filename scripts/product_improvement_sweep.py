"""Product beam/annealing sweep on the versioned v1 developer set only.

Fixture prices, no model calls. Times include packet construction and validation,
but not HTTP, model parsing or live shopping lookup. No timing cutoff is applied.
"""

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from statistics import median
from time import perf_counter
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.evaluation import runner  # noqa: E402
from app.planning import product_path  # noqa: E402
from app.planning.recipe_quality import dish_kind  # noqa: E402

INPUTS = {
    "ingredient_path": ROOT / "data/ingredients/ingredients.json",
    "recipe_path": ROOT / "data/recipes/recipes.json",
    "scenario_path": ROOT / "data/evaluation/dev/planning-v1.json",
    "fixture_path": ROOT / "data/fixtures/fairprice-products.json",
}


def run(width, steps):
    calls = []
    original = product_path.improve_product_plan

    class Measured(product_path.ProductPlanningEngine):
        def __init__(self):
            super().__init__(overrides={"width": width})

        def plan(self, *args, **kwargs):
            started = perf_counter()
            before = len(calls)
            result = super().plan(*args, **kwargs)
            if len(calls) > before:
                calls[-1]["planning_seconds"] = perf_counter() - started
            return result

    def improve(problem, incumbent, losses, **kwargs):
        started = perf_counter()
        if steps:
            result, trace = original(problem, incumbent, losses, steps=steps, **kwargs)
        else:
            result, trace = incumbent, {"algorithm": "beam-only", "steps": 0}
        elapsed = perf_counter() - started
        recipes = {r.recipe_id: r for r in problem.recipes}
        counted = [a for a in result[0] if a.role_id not in problem.uncounted_roles]
        record = {
            "packet_sha256": hashlib.sha256(problem.model_dump_json().encode()).hexdigest(),
            "candidate_count": len(recipes),
            "slot_count": len(problem.slots),
            "table_kinds": len({dish_kind(recipes[a.recipe_id].title) for a in counted}),
            "checkout_sgd": result[2].purchase_total_sgd,
            "validation": result[2].status,
            "hard_failures": result[2].hard_failure_count,
            "improvement_seconds": elapsed,
            "score_before": trace.get("before"),
            "score_after": trace.get("after"),
        }
        calls.append(record)
        return result, trace

    with (
        patch.object(runner, "ProductPlanningEngine", Measured),
        patch.object(product_path, "improve_product_plan", improve),
    ):
        report = runner.evaluate(**INPUTS, system="product-planner")
    return {"metrics": report["metrics"], "scenarios": report["scenarios"], "calls": calls}


def summarize(parts):
    lines = [
        "# Product beam and annealing: developer parameter sweep",
        "",
        "Fixture-priced v1 developer cases only. This is not held-out or user-study evidence.",
        "The set covers single-dish dinners; it does not establish composed-household acceptance.",
        "Adjacent repeats remain visible under the legacy v1 criterion, even when the weekly score improves.",
        "Each evaluation independently plans each feasible case twice to check determinism.",
        "Times cover the product planning engine, excluding HTTP, LLM parsing and live prices.",
        "No exact reference is run here, so no optimality gap is claimed.",
        "",
        "| Beam width | SA steps | Runs | Hard violations | Legacy failures (range) "
        "| Median plan s | Max plan s | Median improvement s |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    grouped = {}
    for part in parts:
        grouped.setdefault((part["width"], part["steps"]), []).append(part)
    for (width, steps), rows in sorted(grouped.items()):
        calls = [c for row in rows for c in row["result"]["calls"]]
        times = [c["planning_seconds"] for c in calls]
        failures = [r["result"]["metrics"]["failure_case_count"] for r in rows]
        violations = sum(r["result"]["metrics"]["hard_constraint_violation_count"] for r in rows)
        local = [c["improvement_seconds"] for c in calls]
        lines.append(
            f"| {width} | {steps} | {len(rows)} | {violations} | {min(failures)}–{max(failures)} "
            f"| {median(times):.4f} | {max(times):.4f} | {median(local):.4f} |"
        )
    lines += [
        "",
        "No product default is changed by this diagnostic. Raw records include packet hashes,",
        "table-kind counts, checkout totals, per-case outcomes and before/after scores.",
        "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--widths", type=int, nargs="+", default=[8, 16, 32, 64])
    parser.add_argument("--steps", type=int, nargs="+", default=[0, 50, 200])
    args = parser.parse_args()
    if args.repeats < 1 or min(args.widths) < 1 or min(args.steps) < 0:
        parser.error("repeats and widths must be positive; steps must be nonnegative")
    args.output.mkdir(parents=True, exist_ok=True)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    source = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in INPUTS.values()}
    parts = []
    for width in args.widths:
        for steps in args.steps:
            for repeat in range(args.repeats):
                path = args.output / f"w{width}-s{steps}-r{repeat}.json"
                if path.exists():
                    part = json.loads(path.read_text(encoding="utf-8"))
                    if part["commit"] != revision or part["inputs"] != source:
                        raise ValueError(f"Stale run: {path}; use a new output directory")
                else:
                    part = {
                        "commit": revision,
                        "inputs": source,
                        "machine": platform.processor(),
                        "logical_cpus": os.cpu_count(),
                        "python": platform.python_version(),
                        "width": width,
                        "steps": steps,
                        "repeat": repeat,
                        "result": run(width, steps),
                    }
                    path.write_text(json.dumps(part, indent=2) + "\n", encoding="utf-8")
                parts.append(part)
                print(path.name, flush=True)
    (args.output / "README.md").write_text(summarize(parts), encoding="utf-8")


if __name__ == "__main__":
    main()
