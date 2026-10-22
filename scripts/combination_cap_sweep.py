"""Calibrate the meal-combination cap (`product_path.MEAL_COMBINATIONS`) on developer data.

DEVELOPER SET, DIAGNOSTIC. Every full-default case, every shared-dish case (shared arrangement) and every v3
meal-day-week developer episode, planned through the product path as their reports plan them, once per cap. Fixture
prices, no model or paid API call. The cap is a search-breadth parameter: the chosen value is the smallest whose
plans are no worse than at 16,384 by the criterion below (owner, 2026-10-22; ADR-0083). Time is recorded, not judged.

Run from the repository root, one cap at a time on a quiet machine, then the report:

    python scripts/combination_cap_sweep.py run --cap 16384
    python scripts/combination_cap_sweep.py report

A cap's part file (`parts/cap-<n>.json`) is kept, so an interrupted sweep resumes at the next cap.
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

OUT = Path("docs/evaluation/combination-cap-sweep")
EPISODES = Path("data/evaluation/dev/v3-meal-day-week/episodes")
REFERENCE = 16384
SAFETY_CODES = {"no_allergen_violation", "no_excluded_ingredient", "dietary_tags_respected"}
LABEL = "developer data, diagnostic: not held-out evidence"


def _row(scenario, planned, *, safety=0, failed=0, distinct=None, worst=None, price=None, seconds=None) -> dict:
    return {
        "scenario": scenario,
        "planned": planned,
        "safety_violations": safety,
        "failed_checks": failed,
        "distinct": distinct,
        "worst_repeat": worst,
        "price_sgd": price,
        "seconds": seconds,
    }


def _full_default() -> list[dict]:
    """Each case's report run, then one warm run timed (`full_default.evaluate`)."""
    from app.evaluation import full_default

    report, seconds = full_default.evaluate(repeats=1)
    rows = []
    for case in report["cases"]:
        name, m = case["case"], case.get("metrics", {})
        rows.append(
            _row(
                f"full-default/{name}",
                case["outcome"] == "planned",
                failed=sum(not ok for ok in case.get("checks", {}).values()),
                distinct=m.get("distinct_dishes_excluding_staples"),
                worst=m.get("most_uses_of_one_dish"),
                price=m.get("purchase_total_sgd"),
                seconds=seconds[name]["warm"][0],
            )
        )
    return rows


def _shared_dish() -> list[dict]:
    """Each case's shared arrangement, planned twice; the second run is timed (`shared_dish.run_case`)."""
    from app.api.routes.meal_plans import build_meal_plan_service
    from app.data.release_v2 import release_dir
    from app.evaluation import shared_dish
    from app.evaluation.meal_day_week_runner import product_database

    lines = (release_dir() / "recipes.jsonl").read_text("utf-8").splitlines()
    catalog = {"scenario": {"recipe_candidate_slugs": [json.loads(line)["recipe_id"] for line in lines]}}
    rows = []
    with product_database(catalog) as factory, factory() as session:
        plans = build_meal_plan_service(session, shared_dish.HOUSEHOLD_ID)
        facts = shared_dish._facts(session)
        for case in shared_dish.CASES:
            shared_dish.run_case(plans, case, "shared", facts)
            run, taken = shared_dish.run_case(plans, case, "shared", facts)
            m = run.get("metrics", {})
            rows.append(
                _row(
                    f"shared-dish/{case['case']}",
                    run["outcome"] == "planned",
                    safety=run.get("safety_violations", 0),
                    failed=sum(not ok for ok in run.get("checks", {}).values()),
                    distinct=m.get("distinct_dishes_excluding_staples"),
                    worst=m.get("most_uses_of_one_dish"),
                    price=m.get("purchase_total_sgd"),
                    seconds=round(taken, 2),
                )
            )
    return rows


def _meal_day_week() -> list[dict]:
    """Each developer episode once (`meal_day_week_runner.evaluate`); every episode has its own database, so its
    time includes loading that episode's pool."""
    from app.evaluation.meal_day_week_runner import evaluate

    rows = []
    for path in sorted(EPISODES.glob("mdw-dev-*.json")):
        episode = json.loads(path.read_text(encoding="utf-8"))
        started = time.perf_counter()
        row = evaluate([episode])["episodes"][0]
        rows.append(
            _row(
                f"mdw/{episode['episode_id']}",
                row["answered"] == "plan",
                safety=len(SAFETY_CODES & set(row["failed"])),
                failed=len(row["failed"]),
                distinct=row.get("distinct_recipes"),
                worst=row.get("most_uses_of_a_recipe"),
                price=row.get("total_cost_sgd"),
                seconds=round(time.perf_counter() - started, 2),
            )
        )
    return rows


def run(cap: int, out: Path) -> None:
    from app.planning import product_path

    part = out / "parts" / f"cap-{cap}.json"
    if part.exists():
        print(f"kept {part}")
        return
    product_path.MEAL_COMBINATIONS = cap
    started = time.perf_counter()
    rows = []
    for family in (_full_default, _shared_dish, _meal_day_week):
        rows += family()
        print(f"cap {cap}: {family.__name__} done at {time.perf_counter() - started:.0f} s", flush=True)
    part.parent.mkdir(parents=True, exist_ok=True)
    revision = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False).stdout
    meta = {"cap": cap, "code_commit": revision.strip(), "machine": platform.processor(), "rows": rows}
    part.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8", newline="\n")


def compare(rows: list[dict], reference: list[dict]) -> list[str]:
    """Why a cap's plans are materially worse than the reference cap's; empty when they are not."""
    ref = {r["scenario"]: r for r in reference}
    why = []
    for r in rows:
        base = ref[r["scenario"]]
        name = r["scenario"]
        if base["planned"] and not r["planned"]:
            why.append(f"{name}: refuses where {REFERENCE} plans")
        if r["safety_violations"]:
            why.append(f"{name}: {r['safety_violations']} safety violations")
        if not (base["planned"] and r["planned"]) or base["distinct"] is None:
            continue
        if r["distinct"] < base["distinct"] - 1:
            why.append(f"{name}: {base['distinct'] - r['distinct']} fewer distinct dishes")
        if r["worst_repeat"] > base["worst_repeat"]:
            why.append(f"{name}: worst repeat {r['worst_repeat']} > {base['worst_repeat']}")
        if base["price_sgd"] and r["price_sgd"] > base["price_sgd"] * 1.01 + 1e-9:
            why.append(f"{name}: price S${r['price_sgd']:.2f} > 1% over S${base['price_sgd']:.2f}")
    both = [(r, ref[r["scenario"]]) for r in rows if r["planned"] and ref[r["scenario"]]["planned"]]
    mine, theirs = mean(r["distinct"] for r, _ in both), mean(b["distinct"] for _, b in both)
    if mine < theirs * 0.99:
        why.append(f"mean distinct {mine:.2f} more than 1% under {theirs:.2f}")
    return why


def summary(cap: int, rows: list[dict], reference: list[dict]) -> dict:
    planned = [r for r in rows if r["planned"]]
    ref = {r["scenario"]: r for r in reference}
    priced = [(r, ref[r["scenario"]]) for r in planned if r["price_sgd"] and ref[r["scenario"]]["price_sgd"]]
    return {
        "cap": cap,
        "scenarios": len(rows),
        "planned": len(planned),
        "safety_violations": sum(r["safety_violations"] for r in rows),
        "failed_checks": sum(r["failed_checks"] for r in rows),
        "mean_distinct": round(mean(r["distinct"] for r in planned), 2),
        "worst_repeat": max(r["worst_repeat"] for r in planned),
        "total_price_sgd": round(sum(r["price_sgd"] for r in planned), 2),
        "largest_price_rise_pct": round(max((r["price_sgd"] / b["price_sgd"] - 1) * 100 for r, b in priced), 2),
        "total_seconds": round(sum(r["seconds"] for r in rows), 1),
        "slowest_seconds": max(r["seconds"] for r in rows),
        "materially_worse": compare(rows, reference),
    }


def report(out: Path) -> None:
    parts = {}
    for path in sorted((out / "parts").glob("cap-*.json")):
        part = json.loads(path.read_text(encoding="utf-8"))
        parts[part["cap"]] = part
    reference = parts[REFERENCE]["rows"]
    caps = sorted(parts)
    summaries = [summary(cap, parts[cap]["rows"], reference) for cap in caps]
    chosen = min(s["cap"] for s in summaries if not s["materially_worse"])
    result = {
        "label": LABEL,
        "reference_cap": REFERENCE,
        "chosen_cap": chosen,
        "criterion": [
            "no scenario changes from planning to refusing",
            "0 safety violations",
            "no scenario loses more than 1 distinct dish, and the mean distinct is within 1%",
            "the worst repeat is never higher",
            "no scenario's total price is more than 1% higher",
        ],
        "code_commits": {cap: parts[cap]["code_commit"] for cap in caps},
        "machine": parts[REFERENCE]["machine"],
        "summary": summaries,
        "rows": {cap: parts[cap]["rows"] for cap in caps},
    }
    (out / "latest.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    (out / "README.md").write_text(markdown(result), encoding="utf-8", newline="\n")
    print(f"chosen cap {chosen}")


def cheaper(result: dict, cap: int) -> int:
    ref = {r["scenario"]: r for r in result["rows"][REFERENCE]}
    return sum(
        1
        for r in result["rows"][cap]
        if r["planned"] and ref[r["scenario"]]["planned"] and r["price_sgd"] < ref[r["scenario"]]["price_sgd"]
    )


def markdown(result: dict) -> str:
    caps = [s["cap"] for s in result["summary"]]
    lines = [
        "# Meal-combination cap sweep",
        "",
        f"> {LABEL.capitalize()}. Fixture prices, no model call, no held-out data.",
        "",
        "`product_path.MEAL_COMBINATIONS` caps the dish combinations a meal's first widening step builds, which sets "
        "how many dishes each of a meal's roles keeps (`meal_beam.integer_root` of the cap per role, never fewer than "
        "three). It is a search-breadth parameter: removing it in task 15 planned no better and took up to hours. "
        "The owner asked (2026-10-22) for the smallest cap that does not materially reduce plan quality against "
        f"the earlier {REFERENCE:,} (ADR-0083).",
        "",
        "## Method",
        "",
        "`python scripts/combination_cap_sweep.py run --cap N` for each cap, one process at a time, then "
        "`python scripts/combination_cap_sweep.py report`. Scenarios: every full-default case (report run, then one "
        "warm run timed), every shared-dish case in the shared arrangement (planned twice, the second timed) and "
        "every v3 meal-day-week developer episode (`mdw-dev-*`, once; each loads its own pool, so its time includes "
        "that). Every cap uses the exact integer root, so a seven-role meal keeps four dishes a role at 16,384 "
        "(`int(16384 ** (1 / 7))` gave three).",
        "",
        f"A cap is materially worse than {REFERENCE:,} when any of these fails:",
        "",
        *(f"- {c};" for c in result["criterion"]),
        "",
        f"**Chosen cap: {result['chosen_cap']:,}**, the smallest that passes every one.",
        "",
        "A cap matters only through the dishes each role keeps: at most `candidates_per_role` (8), else the integer "
        "root. Every cap tried below 16,384 (1,024 to 8,192, doubling) loses on some scenario. "
        "Between 8,192 and 16,384 only six-role meals "
        "(4 dishes a role, 5 from 15,625) and seven-role meals change, and a seven-role meal keeps 3 dishes a role "
        "at any cap below 16,384 = 4^7, as at 8,192, where `seven-with-young-children` repeats a dish three times and "
        "costs 7% more. So no value between them was swept.",
        "",
        "The choice rests on that one scenario: `seven-with-young-children` is the only seven-role meal in the set. "
        "Without it, 8,192 fails only where two scenarios keep 2 fewer distinct dishes at a lower price "
        "(`full-default/four-with-vegetarian` S$22.88 and `shared-dish/weekend-guest` S$31.85 cheaper), and 4,096 "
        "only on five shared-dish prices; a developer set with no seven-role household could have chosen either.",
        "",
        f"The criterion only guards against losses to {REFERENCE:,}; a smaller cap that plans cheaper is not "
        "credited. Scenarios planned cheaper than at "
        f"{REFERENCE:,}: " + ", ".join(f"{cap:,}: {cheaper(result, cap)}" for cap in caps if cap != REFERENCE) + ".",
        "",
        "## Summary",
        "",
        "| Cap | Planned | Safety violations | Failed checks | Mean distinct | Worst repeat | Total price (S$) "
        "| Largest price rise | Total time (s) | Slowest (s) | Materially worse |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for s in result["summary"]:
        worse = "; ".join(s["materially_worse"]) or "no"
        lines.append(
            f"| {s['cap']:,} | {s['planned']}/{s['scenarios']} | {s['safety_violations']} | {s['failed_checks']} "
            f"| {s['mean_distinct']} | {s['worst_repeat']} | {s['total_price_sgd']:.2f} "
            f"| {s['largest_price_rise_pct']:+.2f}% | {s['total_seconds']} | {s['slowest_seconds']} | {worse} |"
        )
    lines += [
        "",
        "## Per scenario",
        "",
        "Distinct dishes / worst repeat / price (S$) / seconds; `refused` when no week was planned.",
        "",
        "| Scenario | " + " | ".join(f"{cap:,}" for cap in caps) + " |",
        "| --- | " + " | ".join("---" for _ in caps) + " |",
    ]
    rows = result["rows"]
    for index, first in enumerate(rows[caps[0]]):
        cells = []
        for cap in caps:
            r = rows[cap][index]
            cells.append(
                f"{r['distinct']} / {r['worst_repeat']} / {r['price_sgd']:.2f} / {r['seconds']}"
                if r["planned"]
                else f"refused / {r['seconds']}"
            )
        lines.append(f"| {first['scenario']} | " + " | ".join(cells) + " |")
    lines += [
        "",
        "## Caveats",
        "",
        "- Developer data only; the chosen cap has not been checked on held-out episodes.",
        f"- Times are one machine ({result['machine']}), one run per cap; they are recorded, not used to choose.",
        "- Distinct dishes count recipes (full-default and shared-dish leave out staples); the product's own search "
        "loss is not exposed by the reports and is not compared.",
        "- Commits per cap are in `latest.json` (`code_commits`).",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("run", "report"))
    parser.add_argument("--cap", type=int)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    if args.command == "run":
        run(args.cap, args.out)
    else:
        report(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
