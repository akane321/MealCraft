"""Render the household comparison without changing measured values."""

import argparse
import json
from pathlib import Path


def summarize(folder):
    parts = [json.loads((folder / f"steps-{n}.json").read_text(encoding="utf-8")) for n in (0, 50)]
    if parts[0]["commit"] != parts[1]["commit"]:
        raise ValueError("Comparison needs the same source commit")
    lines = [
        "# Product improvement: full-default household comparison",
        "",
        "Five developer households, fixture prices, one run per condition. No held-out data or model calls.",
        "Each condition uses the same product defaults; the only change is enabling 50 annealing proposals.",
        "Distinct dishes below count recipe IDs excluding staples, not near-duplicate or member-mean groups.",
        "Timing covers plan generation and persistence, not HTTP, language-model parsing or live retailer calls.",
        "These single measurements are diagnostic; there is no optimality or statistically significant speed claim.",
        "",
        "| Household | SA steps | Planned | Checks pass | Distinct dishes | Worst repeat | Checkout S$ | Seconds |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for part in parts:
        for case in part["report"]["cases"]:
            name = case["case"]
            m = case.get("metrics", {})
            lines.append(
                f"| {name} | {part['steps']} | {case['outcome']} | {case.get('passed', False)} "
                f"| {m.get('distinct_dishes_excluding_staples', 'n/a')} "
                f"| {m.get('most_uses_of_one_dish', 'n/a')} | {m.get('purchase_total_sgd', 'n/a')} "
                f"| {part['timings'][name]['first']:.2f} |"
            )
    baseline = {c["case"]: c for c in parts[0]["report"]["cases"]}
    improved = {c["case"]: c for c in parts[1]["report"]["cases"]}
    if set(baseline) != set(improved):
        raise ValueError("Comparison needs the same households")
    measures = ("distinct_dishes_excluding_staples", "most_uses_of_one_dish", "purchase_total_sgd")
    unchanged = sum(
        all(baseline[name].get("metrics", {}).get(k) == improved[name].get("metrics", {}).get(k) for k in measures)
        for name in baseline
    )
    lines += [
        "",
        f"In {unchanged} of {len(baseline)} households, distinct dishes, worst repeat and checkout are unchanged.",
        "The table must not be presented as evidence that annealing improves these households.",
        "Investigate proposal acceptance and stage costs before expanding the iteration count or claiming acceptance.",
        "",
        "Raw JSON retains every check and the planned dishes. A passing check is not proof of user preference.",
        "The ten-day household exercises two shopping trips; "
        "this does not replace the separate 14-day regression suite.",
        "",
        f"Source commit: `{parts[0]['commit']}`.",
        "Reproduce with `python scripts/product_household_comparison.py --output <fresh-directory>`",
        "and `python scripts/summarize_product_households.py <fresh-directory>`.",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    (args.folder / "README.md").write_text(summarize(args.folder), encoding="utf-8")
