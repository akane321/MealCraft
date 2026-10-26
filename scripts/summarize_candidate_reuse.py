"""Render a same-source, same-output developer candidate-reuse comparison."""

import argparse
import json
from pathlib import Path


def summarize(folder):
    before, after = [
        json.loads((folder / mode / "steps-50.json").read_text(encoding="utf-8")) for mode in ("uncached", "cached")
    ]
    for key in ("commit", "script_sha256", "profiler_sha256", "cases", "steps", "profiling_enabled"):
        if before[key] != after[key]:
            raise ValueError(f"Comparison differs in {key}")
    if before["working_tree_dirty"] or after["working_tree_dirty"]:
        raise ValueError("Comparison requires committed source")
    if before["candidate_reuse"] or not after["candidate_reuse"]:
        raise ValueError("Expected uncached and cached conditions")
    if before["report"] != after["report"]:
        raise ValueError("Candidate reuse changed the household report")
    lines = [
        "# Reusing product meal candidates",
        "",
        "Fixed developer households and fixture prices; no LLM or held-out inputs.",
        "Both conditions use the same committed source, seed, 50 proposals and search settings.",
        "The full household reports, including meals, checks and prices, are identical.",
        "One sequential measurement per condition; timings are diagnostic, not a statistical speed claim.",
        "Profiling adds overhead. Stage durations include nested calls and must not be summed.",
        "",
        "| Household | Reuse | Total s | Candidate-generation calls | SA domains s | SA proposals s |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for part in (before, after):
        for row in part["stage_profiles"]:
            stages = row["stages"] or {}
            lines.append(
                f"| {row['case']} | {part['candidate_reuse']} | {part['timings'][row['case']]['first']:.3f} "
                f"| {stages.get('meal_options', {}).get('calls', 'n/a')} "
                f"| {stages.get('annealing_domains', {}).get('seconds', 0):.3f} "
                f"| {stages.get('annealing_proposal', {}).get('seconds', 0):.3f} |"
            )
    lines += [
        "",
        "This removes duplicate computation; it does not establish improved menu quality or an optimal-price gap.",
        "Provenance and detailed results: [uncached](uncached/steps-50.json), [cached](cached/steps-50.json).",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    (args.folder / "README.md").write_text(summarize(args.folder), encoding="utf-8")
