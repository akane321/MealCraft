"""Run the arms of protocol v2-multidish on a set of episodes and score them.

Arms without a live model:
- O1 (gold + meal beam) and O2 (gold + CP-SAT) read the gold constraints;
- C (rules + meal beam), E (Strong Rule-only) and F (greedy) read the request
  through the rule parser.

A, B and D call a live model and run only when the owner authorises them
(protocol section 5).

Every arm sees the same packet: the episode's drawn pool and its products,
with the household profile as structured context. Answers are in the common
output shape and are scored by the strict scorer, which recomputes everything.

    python -m app.evaluation.multidish_runner --episodes data/evaluation/dev/v2-multidish/episodes \\
        --json-report docs/evaluation/v2-multidish/dev/latest.json \\
        --markdown-report docs/evaluation/v2-multidish/dev/latest.md
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from app.agent.parser import RuleBasedConstraintParser
from app.core.paths import repository_root
from app.data.allergens import checked_allergens
from app.evaluation.common_output import CommonEpisodeResponse
from app.evaluation.release_catalog import load_release_catalog
from app.evaluation.strict_success import Catalogs, load_tag_implications, score_episode
from app.planning.final_scope_reference import FinalScopeReferencePlanner
from app.planning.meal_beam import MealBeamPlanner, dish_eligible
from app.planning.meal_composition import dish_servings, meal_minutes
from app.planning.meal_cp_sat import MealCpSatLimits, MealCpSatPlanner
from app.schemas.agent import AgentConstraintState
from app.schemas.planning_v2 import FinalPlanningProblem, FinalPlanningSolution, PlanningAssignment

PROTOCOL = "v2-multidish"
NUTRIENTS = ("calories_kcal", "protein_g", "carbohydrate_g", "fat_g", "sodium_mg", "sugar_g")
O2_LIMITS = MealCpSatLimits(max_time_seconds=300.0, max_deterministic_time=300.0)


@dataclass
class Constraints:
    """What an arm understood the household to ask for."""

    household_size: int | None
    allergens: list[str]
    excluded_ingredients: list[str]
    dietary_tags: list[str]
    max_minutes: int | None
    budget_sgd: float | None
    clarify: list[str]
    repetition: dict | None = None


def gold_constraints(episode: dict) -> Constraints:
    gold = episode["gold"]
    hard = gold["applicable_hard_constraints"]
    return Constraints(
        household_size=episode["scenario"]["household_profile"]["household_size"],
        allergens=list(hard["allergens_absent"]),
        excluded_ingredients=list(hard["excluded_ingredients_absent"]),
        dietary_tags=list(hard["dietary_tags_required"]),
        max_minutes=hard["max_cooking_time_minutes"],
        budget_sgd=hard["budget_sgd"],
        clarify=list(gold["required_clarification_fields"]) if gold["class"] == "needs_clarification" else [],
        repetition=hard.get("repetition_requirements"),
    )


def rule_constraints(episode: dict) -> Constraints:
    """The request as the rule parser reads it, on top of the structured profile."""
    scenario = episode["scenario"]
    profile = scenario["household_profile"]
    parsed = RuleBasedConstraintParser().parse(
        scenario["user_request"], current=AgentConstraintState(), acknowledged_unknowns=[], history=[]
    )
    size = profile["household_size"] or parsed.household_size
    return Constraints(
        household_size=size,
        allergens=sorted(set(profile["allergens"]) | set(parsed.allergens or [])),
        excluded_ingredients=sorted(set(profile["excluded_ingredients"]) | set(parsed.excluded_ingredients or [])),
        dietary_tags=sorted(set(profile["dietary_preferences"]) | set(parsed.dietary_preferences or [])),
        max_minutes=parsed.max_cooking_time_minutes,
        budget_sgd=parsed.weekly_budget_sgd,
        clarify=[] if size else ["household_size"],
    )


def build_problem(episode: dict, understood: Constraints) -> FinalPlanningProblem:
    catalog = load_release_catalog()
    scenario = episode["scenario"]
    allergens = {row["normalized_name"]: row["allergens"] for row in catalog.ingredients}
    pool = [catalog.by_slug[slug] for slug in scenario["recipe_candidate_slugs"]]
    allowed = set(scenario["fairprice_product_ids"])
    start = date.fromisoformat(scenario["planning_horizon"]["start_date"])
    return FinalPlanningProblem.model_validate(
        {
            "problem_id": episode["episode_id"],
            "slots": [
                {
                    "slot_id": slot,
                    "planned_date": (start + timedelta(days=index)).isoformat(),
                    "meal_type": "dinner",
                    "servings": understood.household_size,
                    "max_time_minutes": understood.max_minutes,
                    "composition": scenario["household_profile"]["meal_composition"],
                }
                for index, slot in enumerate(scenario["planning_horizon"]["slots"])
            ],
            "recipes": [
                {
                    "recipe_id": r["slug"],
                    "title": r["title"][:240],
                    "servings": r["servings"],
                    "allowed_meal_types": [m for m in r["meal_types"] if m in {"breakfast", "lunch", "dinner", "snack"}]
                    or ["lunch", "dinner"],
                    "total_time_minutes": r["prep_time_minutes"] + r["cook_time_minutes"],
                    "prep_minutes": r["prep_time_minutes"],
                    "cook_minutes": r["cook_time_minutes"],
                    "passive_minutes": 0,
                    "course": r["course"],
                    "dietary_tags": r["dietary_tags"],
                    "allergens": sorted(
                        {a for line in r["ingredients"] for a in allergens.get(line["ingredient"], [])}
                    ),
                    "ingredients": [
                        {"ingredient_id": line["ingredient"], "quantity": line["quantity"], "unit": line["unit"]}
                        for line in r["ingredients"]
                    ],
                    # Release nutrition is not computed; no episode states a target (protocol section 2).
                    "nutrients_per_serving": dict.fromkeys(NUTRIENTS, 0),
                    "cuisine": r["cuisine"],
                }
                for r in pool
            ],
            "pantry": [
                {"ingredient_id": item["ingredient_id"], "quantity": item["quantity"], "unit": item["unit"]}
                for item in scenario["pantry"]
            ],
            "products": [
                {
                    "ingredient_id": p["ingredient_id"],
                    "product_id": p["external_id"],
                    "package_quantity": p["package_size"],
                    "package_unit": p["package_unit"],
                    "price_sgd": p["price_sgd"],
                    "available": p["in_stock"],
                }
                for p in catalog.products
                if p["external_id"] in allowed
            ],
            "allergens": understood.allergens,
            "allergen_vocabulary": sorted(checked_allergens()),
            "excluded_ingredients": understood.excluded_ingredients,
            "dietary_requirements": understood.dietary_tags,
            "purchase_budget_sgd": understood.budget_sgd,
            "repetition_rules": understood.repetition,
            "catalog_version": "release-v2.1",
            "product_snapshot_version": "fairprice-v2-snapshot",
            "policy_version": PROTOCOL,
        }
    )


def respond(episode: dict, system_id: str, problem: FinalPlanningProblem | None, solution, *, why: str = "") -> dict:
    """The common output for one arm's answer."""
    base = {"episode_id": episode["episode_id"], "system_id": system_id}
    if problem is None:  # the arm asked a question instead
        return {
            **base,
            "status": "clarification",
            "clarification": [{"field": f, "question": f"What is your {f}?"} for f in why.split(",")],
        }
    if solution is None or not solution.assignments:
        return {**base, "status": "infeasible", "infeasible": {"conflict": why or "no plan meets every constraint"}}
    servings = dish_servings(problem, solution.assignments)
    total = round(sum(line.purchase_cost_sgd for line in solution.shopping), 2)
    return {
        **base,
        "status": "plan",
        "plan": {
            "assignments": [
                {"slot_id": a.slot_id, "role_id": a.role_id, "recipe_id": a.recipe_id, "servings": float(servings[i])}
                for i, a in enumerate(solution.assignments)
            ],
            "shopping": [
                {
                    "ingredient_id": line.ingredient_id,
                    "required_quantity": line.required_quantity,
                    "unit": line.unit,
                    # Exact: the shopping line rounds its deduction to thousandths for display.
                    "pantry_deduction": (
                        line.required_quantity - line.remaining_quantity
                        if line.required_quantity is not None and line.remaining_quantity is not None
                        else line.pantry_deduction
                    ),
                    "product_id": line.selected_product_id,
                    "packages": line.packages,
                    "line_cost_sgd": line.purchase_cost_sgd,
                }
                for line in solution.shopping
            ],
            "total_cost_sgd": total,
            "within_budget": None if problem.purchase_budget_sgd is None else total <= problem.purchase_budget_sgd,
        },
    }


def _validated(solution: FinalPlanningSolution) -> FinalPlanningSolution | None:
    return solution if solution.validation.status == "passed" else None


def run_beam(problem: FinalPlanningProblem):
    solution = MealBeamPlanner().solve(problem)
    return _validated(solution), "no validated plan was found in the bounded search"


def run_exact(problem: FinalPlanningProblem, limits: MealCpSatLimits):
    """CP-SAT warm-started from the meal beam; the better validated plan is the answer (protocol section 6)."""
    beam = _validated(MealBeamPlanner().solve(problem))
    result = MealCpSatPlanner(limits).solve_exact(problem, hint=beam.assignments if beam else None)
    exact = _validated(result.solution) if result.solution else None
    source = "cp_sat"
    if beam is not None and (exact is None or result.objective > _beam_loss(problem) + 0.005):
        exact, source = beam, "warm_start"
    extra = {
        "cp_sat_status": result.status,
        "proven_optimal": result.status == "optimal",
        "answer_source": source,
        "objective": result.objective,
        "best_bound": result.best_bound,
    }
    why = (
        "no plan satisfies every constraint (proven by CP-SAT)"
        if result.status == "infeasible"
        else "no validated plan was found"
    )
    return exact, why, extra


def _beam_loss(problem: FinalPlanningProblem) -> float:
    states = MealBeamPlanner().search_candidates(problem).states
    return min(state.loss for state in states) if states else float("inf")


def _dish_cost(problem: FinalPlanningProblem, recipe, share: float, servings: int) -> float:
    cheapest: dict[str, float] = {}
    for p in problem.products:
        per_gram = p.price_sgd / p.package_quantity
        cheapest[p.ingredient_id] = min(cheapest.get(p.ingredient_id, per_gram), per_gram)
    return sum(
        i.quantity * servings * share / recipe.servings * cheapest.get(i.ingredient_id, 0.0) for i in recipe.ingredients
    )


def rule_selector(problem: FinalPlanningProblem, *, greedy: bool) -> FinalPlanningSolution:
    """E: per role, the cheapest then quickest eligible dish, not the previous day's, fitting the meal time.
    F: per role, the same first dish every day."""
    assignments: list[PlanningAssignment] = []
    previous: dict[str, str] = {}
    for slot in problem.slots:
        chosen: list = []
        for role in slot.composition or []:
            options = [r for r in problem.recipes if r.course in role.courses and dish_eligible(problem, slot, r)]
            share = 0.5 if role.role_id != "main" else 0.75
            options.sort(
                key=lambda r: (
                    (r.total_time_minutes, r.recipe_id)
                    if greedy
                    else (round(_dish_cost(problem, r, share, slot.servings), 2), r.total_time_minutes, r.recipe_id)
                )
            )
            for recipe in options:
                if not greedy and previous.get(role.role_id) == recipe.recipe_id:
                    continue
                if recipe.recipe_id in {r.recipe_id for _, r in chosen}:
                    continue
                trial = [r for _, r in chosen] + [recipe]
                if (
                    slot.max_time_minutes is not None
                    and meal_minutes(trial, problem.composition_policy) > slot.max_time_minutes
                ):
                    continue
                chosen.append((role.role_id, recipe))
                break
        for role_id, recipe in chosen:
            assignments.append(PlanningAssignment(slot_id=slot.slot_id, role_id=role_id, recipe_id=recipe.recipe_id))
            previous[role_id] = recipe.recipe_id
    shopping = FinalScopeReferencePlanner()._build_shopping(problem, assignments)
    report = FinalScopeReferencePlanner().validator.validate(problem, assignments, shopping)
    return FinalPlanningSolution(
        problem_id=problem.problem_id,
        status="feasible",
        assignments=assignments,
        shopping=shopping,
        validation=report,
        trace={"algorithm": "rule-selector", "algorithm_version": "multidish-rules-v1", "deterministic": True},
    )


ARMS = ("O1", "O2", "C", "E", "F")


def run_arm(arm: str, episode: dict) -> tuple[dict, dict]:
    understood = gold_constraints(episode) if arm in {"O1", "O2"} else rule_constraints(episode)
    if understood.clarify:
        return respond(episode, arm, None, None, why=",".join(understood.clarify)), {}
    problem = build_problem(episode, understood)
    if arm in {"O1", "C"}:
        solution, why = run_beam(problem)
        return respond(episode, arm, problem, solution, why=why), {}
    if arm == "O2":
        solution, why, extra = run_exact(problem, O2_LIMITS)
        return respond(episode, arm, problem, solution, why=why), extra
    solution = rule_selector(problem, greedy=arm == "F")
    complete = all(
        {a.role_id for a in solution.assignments if a.slot_id == slot.slot_id}
        >= {r.role_id for r in slot.composition if r.required}
        for slot in problem.slots
    )
    return respond(
        episode, arm, problem, solution if complete else None, why="a required dish role could not be filled"
    ), {}


def _plan_shape(answer: dict, episode: dict) -> dict:
    """Secondary measures strict success does not score (v2 section 11): variety and cost."""
    plan = answer.get("plan")
    if not plan:
        return {}
    order = {slot: i for i, slot in enumerate(episode["scenario"]["planning_horizon"]["slots"])}
    by_role: dict[str | None, dict[int, str]] = {}
    for a in plan["assignments"]:
        by_role.setdefault(a["role_id"], {})[order[a["slot_id"]]] = a["recipe_id"]
    repeats = sum(
        days.get(i) is not None and days.get(i) == days.get(i + 1) for days in by_role.values() for i in order.values()
    )
    return {
        "distinct_recipes": len({a["recipe_id"] for a in plan["assignments"]}),
        "dishes": len(plan["assignments"]),
        "adjacent_repeats": repeats,
        "total_cost_sgd": plan["total_cost_sgd"],
    }


def scorer_catalogs() -> Catalogs:
    catalog = load_release_catalog()
    return Catalogs.build(
        catalog.recipes,
        catalog.products,
        catalog.ingredients,
        tag_implications=load_tag_implications(repository_root() / "data/recipes/dietary-tag-implications.json"),
        checked_allergens=checked_allergens(),
    )


def evaluate(episodes: list[dict], arms: tuple[str, ...] = ARMS) -> dict:
    catalogs = scorer_catalogs()
    rows = []
    for episode in episodes:
        for arm in arms:
            started = time.perf_counter()
            answer, extra = run_arm(arm, episode)
            seconds = time.perf_counter() - started
            score = score_episode(episode, CommonEpisodeResponse.model_validate(answer), catalogs)
            extra = {**extra, **_plan_shape(answer, episode)}
            rows.append(
                {
                    "episode_id": episode["episode_id"],
                    "class": episode["gold"]["class"],
                    "category": episode["category"],
                    "arm": arm,
                    "strict_success": score.strict_success,
                    "failed": score.failed_codes,
                    "indeterminate": score.indeterminate_codes,
                    "answered": answer["status"],
                    "seconds": round(seconds, 3),
                    **extra,
                }
            )
    summary = {}
    for arm in arms:
        mine = [r for r in rows if r["arm"] == arm]
        times = sorted(r["seconds"] for r in mine)
        summary[arm] = {
            "strict_success": sum(r["strict_success"] for r in mine),
            "episodes": len(mine),
            "by_class": {
                c: f"{sum(r['strict_success'] for r in mine if r['class'] == c)}/{sum(r['class'] == c for r in mine)}"
                for c in sorted({r["class"] for r in mine})
            },
            "median_seconds": round(statistics.median(times), 3),
            "p95_seconds": round(times[max(0, round(0.95 * len(times)) - 1)], 3),
            "failure_mechanisms": dict(
                sorted({code: sum(code in r["failed"] for r in mine) for r in mine for code in r["failed"]}.items())
            ),
        }
        planned = [r for r in mine if "dishes" in r]
        summary[arm]["mean_distinct_recipes"] = (
            round(statistics.mean(r["distinct_recipes"] for r in planned), 2) if planned else None
        )
        summary[arm]["adjacent_repeats"] = sum(r["adjacent_repeats"] for r in planned)
        if arm == "O2":
            summary[arm]["proven_optimal"] = sum(bool(r.get("proven_optimal")) for r in mine)
            summary[arm]["answers_from_warm_start"] = sum(r.get("answer_source") == "warm_start" for r in mine)
    return {
        "protocol": PROTOCOL,
        "machine": f"{platform.processor() or platform.machine()} ({platform.system()})",
        "summary": summary,
        "episodes": rows,
    }


def markdown(report: dict, inputs: dict) -> str:
    lines = [
        f"# Protocol {PROTOCOL}: developer set",
        "",
        "Generated by `python -m app.evaluation.multidish_runner`. Live-model arms (A, B, D) did not run.",
        f"Machine: {report['machine']}.",
        "",
        "| Arm | Strict success | By class | Median s | p95 s | Distinct recipes | Adjacent repeats "
        "| Failure mechanisms |",
        "| --- | ---: | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for arm, s in report["summary"].items():
        classes = ", ".join(f"{k} {v}" for k, v in s["by_class"].items())
        mechanisms = ", ".join(f"{k} {v}" for k, v in s["failure_mechanisms"].items()) or "-"
        lines.append(
            f"| {arm} | {s['strict_success']}/{s['episodes']} | {classes} | {s['median_seconds']} | {s['p95_seconds']} "
            f"| {s['mean_distinct_recipes']} | {s['adjacent_repeats']} | {mechanisms} |"
        )
    o2 = report["summary"].get("O2")
    if o2:
        lines += [
            "",
            f"O2: CP-SAT proved optimality on {o2['proven_optimal']} episodes; "
            f"{o2['answers_from_warm_start']} answers are the warm-start plan because CP-SAT ended worse.",
        ]
    lines += [
        "",
        "O1 and O2 read the gold constraints and are bounds, not competitors (protocol section 5).",
        "Counts only, no per-category rates (ADR-0028).",
        "",
        "## Inputs",
        "",
    ]
    lines += [f"- `{path}`: `{digest}`" for path, digest in sorted(inputs.items())]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--episodes", type=Path, required=True)
    parser.add_argument("--arms", default=",".join(ARMS))
    parser.add_argument("--json-report", type=Path, required=True)
    parser.add_argument("--markdown-report", type=Path, required=True)
    args = parser.parse_args()
    root = repository_root()
    files = sorted(args.episodes.glob("*.json"))
    episodes = [json.loads(path.read_text(encoding="utf-8")) for path in files]
    report = evaluate(episodes, tuple(args.arms.split(",")))
    inputs = {
        str(path.resolve().relative_to(root)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in files
    }
    for fixed in (
        "data-engineering/data/release/v2.1/recipes.jsonl",
        "data-engineering/data/release/v2.1/ingredients.jsonl",
        "data/products/fairprice-v2-snapshot.json",
    ):
        inputs[fixed] = hashlib.sha256((root / fixed).read_bytes()).hexdigest()
    report["inputs"] = inputs
    args.json_report.parent.mkdir(parents=True, exist_ok=True)
    args.json_report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.markdown_report.write_text(markdown(report, inputs), encoding="utf-8")
    for arm, s in report["summary"].items():
        print(f"{arm}: {s['strict_success']}/{s['episodes']} {s['by_class']} median {s['median_seconds']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
