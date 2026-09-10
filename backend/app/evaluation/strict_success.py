"""Score one system's answer to one episode against its gold label.

`docs/design/comparative-evaluation-v2.md` section 10 makes Strict End-to-End
Task Success the primary endpoint: an episode counts as a success only if every
applicable requirement holds. This module recomputes each of those requirements
from the frozen facts and the gold label.

Three properties this has to have, and why:

**It recomputes rather than reads claims.** A system that asserts it stayed
under budget is scored against the arithmetic, not against its assertion.
Otherwise the metric rewards confident wording.

**It does its own unit conversion.** Reusing the planner's helper would mean a
bug in that helper marks MealCraft's own output correct - the failure mode
`RISKS.md` R-26 describes, where two components share one wrong implementation
and validation passes. `test_strict_success.py` cross-checks the two tables on
every unit pair the catalogs actually use, so divergence surfaces as a failing
test instead of a silently inflated score.

**Missing data is not a pass.** A check that cannot be evaluated - incompatible
units, an unmapped ingredient - is recorded as indeterminate, and an episode
with an indeterminate hard check is not a success. Treating unverifiable as
satisfied is how a benchmark drifts upward without the system improving.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Literal

from app.evaluation.common_output import CommonEpisodeResponse

CheckOutcome = Literal["passed", "failed", "indeterminate", "not_applicable"]

# Independent of app.planning.grocery_estimator by design; see the module
# docstring. Deliberately small: only the units the committed catalogs use.
_UNIT_BASE: dict[str, tuple[str, float]] = {
    "g": ("mass", 1.0),
    "kg": ("mass", 1000.0),
    "ml": ("volume", 1.0),
    "l": ("volume", 1000.0),
    "tsp": ("volume", 5.0),
    "tbsp": ("volume", 15.0),
    "whole": ("count", 1.0),
    "pc": ("count", 1.0),
    "pcs": ("count", 1.0),
}


def to_base(quantity: float, unit: str | None) -> tuple[str, float] | None:
    """Convert to a canonical base unit, or None when the unit is unknown."""
    if unit is None:
        return None
    entry = _UNIT_BASE.get(unit.strip().lower())
    if entry is None:
        return None
    dimension, factor = entry
    return dimension, quantity * factor


def compatible(quantity: float, unit: str | None, target_unit: str | None) -> float | None:
    source = to_base(quantity, unit)
    target = to_base(1.0, target_unit)
    if source is None or target is None or source[0] != target[0]:
        return None
    return source[1] / target[1]


@dataclass(frozen=True)
class Check:
    code: str
    outcome: CheckOutcome
    detail: str
    hard: bool = True

    @property
    def blocks_success(self) -> bool:
        if self.outcome == "failed":
            return True
        return self.hard and self.outcome == "indeterminate"


@dataclass(frozen=True)
class Tolerances:
    cost_sgd_absolute: float = 0.01
    quantity_relative: float = 1e-6
    nutrition_relative: float = 0.02

    @classmethod
    def from_manifest(cls, manifest: dict[str, Any]) -> Tolerances:
        declared = manifest.get("tolerances") or {}
        return cls(**{key: float(value) for key, value in declared.items()})


@dataclass(frozen=True)
class Catalogs:
    """Frozen facts, keyed for lookup. Built once per run."""

    recipes: dict[str, dict]
    products: dict[str, dict]
    ingredient_allergens: dict[str, str | None]

    @classmethod
    def build(cls, recipes: Iterable[dict], products: Iterable[dict], ingredients: Iterable[dict]) -> Catalogs:
        return cls(
            recipes={row["slug"]: row for row in recipes},
            products={row["external_id"]: row for row in products},
            ingredient_allergens={row["normalized_name"]: row.get("allergen") for row in ingredients},
        )


@dataclass
class EpisodeScore:
    episode_id: str
    system_id: str
    episode_class: str
    schema_failure: bool = False
    checks: list[Check] = field(default_factory=list)

    @property
    def strict_success(self) -> bool:
        if self.schema_failure:
            return False
        return not any(check.blocks_success for check in self.checks)

    @property
    def failed_codes(self) -> list[str]:
        return [c.code for c in self.checks if c.outcome == "failed"]

    @property
    def indeterminate_codes(self) -> list[str]:
        return [c.code for c in self.checks if c.outcome == "indeterminate"]


def schema_failure_score(episode: dict, system_id: str, detail: str) -> EpisodeScore:
    """Unparseable output is an end-to-end failure and a schema failure both."""
    return EpisodeScore(
        episode_id=episode["episode_id"],
        system_id=system_id,
        episode_class=episode["gold"]["class"],
        schema_failure=True,
        checks=[Check("output_schema", "failed", detail)],
    )


def _plan_demand(response: CommonEpisodeResponse, catalogs: Catalogs) -> tuple[dict[str, tuple[float, str]], list[str]]:
    """Aggregate ingredient demand implied by the assignments."""
    demand: dict[str, tuple[float, str]] = {}
    problems: list[str] = []
    assert response.plan is not None
    for assignment in response.plan.assignments:
        recipe = catalogs.recipes.get(assignment.recipe_id)
        if recipe is None:
            continue  # reported separately by the invented-entity check
        scale = assignment.servings / float(recipe["servings"])
        for item in recipe["ingredients"]:
            name, unit = item["ingredient"], item["unit"]
            quantity = float(item["quantity"]) * scale
            if name in demand:
                previous, previous_unit = demand[name]
                converted = compatible(quantity, unit, previous_unit)
                if converted is None:
                    problems.append(f"{name} appears in incompatible units")
                    continue
                demand[name] = (previous + converted, previous_unit)
            else:
                demand[name] = (quantity, unit)
    return demand, problems


def _check_invented_entities(episode: dict, response: CommonEpisodeResponse, catalogs: Catalogs) -> list[Check]:
    scenario = episode["scenario"]
    allowed_recipes = set(scenario["recipe_candidate_slugs"])
    allowed_products = set(scenario["fairprice_product_ids"])
    checks: list[Check] = []

    invented_recipes: list[str] = []
    invented_products: list[str] = []
    if response.plan is not None:
        invented_recipes = sorted(
            {a.recipe_id for a in response.plan.assignments if a.recipe_id not in allowed_recipes}
        )
        invented_products = sorted(
            {
                line.product_id
                for line in response.plan.shopping
                if line.product_id is not None and line.product_id not in allowed_products
            }
        )

    checks.append(
        Check(
            "no_invented_recipe",
            "failed" if invented_recipes else "passed",
            f"outside the frozen candidate pool: {', '.join(invented_recipes)}"
            if invented_recipes
            else "every recipe came from the packet",
        )
    )
    checks.append(
        Check(
            "no_invented_product",
            "failed" if invented_products else "passed",
            f"outside the frozen product snapshot: {', '.join(invented_products)}"
            if invented_products
            else "every product came from the packet",
        )
    )
    return checks


def _check_hard_constraints(episode: dict, response: CommonEpisodeResponse, catalogs: Catalogs) -> list[Check]:
    gold = episode["gold"]["applicable_hard_constraints"]
    assert response.plan is not None
    recipes = [catalogs.recipes.get(a.recipe_id) for a in response.plan.assignments]
    present = [r for r in recipes if r is not None]
    checks: list[Check] = []

    banned_allergens = {str(a).lower() for a in gold.get("allergens_absent") or []}
    hits = sorted(
        {
            f"{r['slug']}:{item['ingredient']}"
            for r in present
            for item in r["ingredients"]
            if (catalogs.ingredient_allergens.get(item["ingredient"]) or "").lower() in banned_allergens
            and banned_allergens
        }
    )
    checks.append(
        Check(
            "no_allergen_violation",
            "not_applicable" if not banned_allergens else ("failed" if hits else "passed"),
            "; ".join(hits) if hits else "no banned allergen appears in the selected recipes",
        )
    )

    excluded = {str(x).lower() for x in gold.get("excluded_ingredients_absent") or []}
    hits = sorted(
        {
            f"{r['slug']}:{item['ingredient']}"
            for r in present
            for item in r["ingredients"]
            if item["ingredient"].lower() in excluded
        }
    )
    checks.append(
        Check(
            "no_excluded_ingredient",
            "not_applicable" if not excluded else ("failed" if hits else "passed"),
            "; ".join(hits) if hits else "no excluded ingredient appears in the selected recipes",
        )
    )

    required_tags = {str(t).lower() for t in gold.get("dietary_tags_required") or []}
    offenders = sorted(
        {r["slug"] for r in present if not required_tags.issubset({str(t).lower() for t in r["dietary_tags"]})}
    )
    checks.append(
        Check(
            "dietary_tags_respected",
            "not_applicable" if not required_tags else ("failed" if offenders else "passed"),
            f"missing required tags: {', '.join(offenders)}"
            if offenders
            else "every selected recipe carries the required tags",
        )
    )

    limit = gold.get("max_cooking_time_minutes")
    if limit is None:
        checks.append(Check("cooking_time_respected", "not_applicable", "no stated time limit"))
    else:
        over = sorted(
            {r["slug"] for r in present if float(r["prep_time_minutes"]) + float(r["cook_time_minutes"]) > float(limit)}
        )
        checks.append(
            Check(
                "cooking_time_respected",
                "failed" if over else "passed",
                f"over {limit} minutes: {', '.join(over)}" if over else f"every recipe fits {limit} minutes",
            )
        )

    return checks


def _check_shopping(
    episode: dict,
    response: CommonEpisodeResponse,
    catalogs: Catalogs,
    tolerances: Tolerances,
) -> list[Check]:
    assert response.plan is not None
    plan = response.plan
    gold_pantry = episode["gold"]["pantry_ground_truth"]
    unknown = {str(x) for x in gold_pantry.get("not_deductible_unknown_quantity") or []}
    known = {row["ingredient_id"]: (float(row["quantity"]), row["unit"]) for row in gold_pantry.get("deductible") or []}

    demand, unit_problems = _plan_demand(response, catalogs)
    lines = {line.ingredient_id: line for line in plan.shopping}
    checks: list[Check] = []

    missing = sorted(set(demand) - set(lines))
    checks.append(
        Check(
            "shopping_covers_plan",
            "failed" if missing else "passed",
            f"the plan needs these but the Shopping List omits them: {', '.join(missing)}"
            if missing
            else "every ingredient the plan needs appears on the Shopping List",
        )
    )

    deducted_unknown = sorted(name for name in unknown if name in lines and lines[name].pantry_deduction > 0)
    checks.append(
        Check(
            "pantry_unknown_not_deducted",
            "not_applicable" if not unknown else ("failed" if deducted_unknown else "passed"),
            f"deducted despite unknown quantity: {', '.join(deducted_unknown)}"
            if deducted_unknown
            else "unknown pantry quantities were not deducted",
        )
    )

    wrong: list[str] = []
    for name, (quantity, unit) in known.items():
        line = lines.get(name)
        if line is None:
            continue
        expected = compatible(quantity, unit, line.unit)
        if expected is None:
            wrong.append(f"{name} (units not comparable)")
        elif abs(line.pantry_deduction - expected) > max(
            tolerances.quantity_relative * max(expected, 1.0), tolerances.quantity_relative
        ):
            wrong.append(f"{name} deducted {line.pantry_deduction}, expected {expected}")
    checks.append(
        Check(
            "pantry_known_deduction_correct",
            "not_applicable" if not known else ("failed" if wrong else "passed"),
            "; ".join(wrong) if wrong else "known pantry quantities were deducted exactly",
        )
    )

    short: list[str] = []
    indeterminate: list[str] = []
    for name, (quantity, unit) in demand.items():
        line = lines.get(name)
        if line is None or line.product_id is None:
            continue
        product = catalogs.products.get(line.product_id)
        if product is None:
            continue
        remaining = max(quantity - line.pantry_deduction, 0.0)
        supplied = compatible(float(product["package_size"]) * line.packages, product["package_unit"], unit)
        if supplied is None:
            indeterminate.append(f"{name} ({product['package_unit']} vs {unit})")
        elif supplied + tolerances.quantity_relative < remaining:
            short.append(f"{name}: {supplied} supplied, {remaining} needed")
    outcome: CheckOutcome = "passed"
    detail = "package counts cover the remaining demand"
    if short:
        outcome, detail = "failed", "; ".join(short)
    elif indeterminate:
        outcome, detail = "indeterminate", "units not comparable: " + "; ".join(indeterminate)
    elif unit_problems:
        outcome, detail = "indeterminate", "; ".join(unit_problems)
    checks.append(Check("packages_cover_demand", outcome, detail))

    cost_problems: list[str] = []
    for line in plan.shopping:
        if line.product_id is None:
            continue
        product = catalogs.products.get(line.product_id)
        if product is None:
            continue
        expected = round(float(product["price_sgd"]) * line.packages, 2)
        if abs(line.line_cost_sgd - expected) > tolerances.cost_sgd_absolute:
            cost_problems.append(f"{line.ingredient_id}: {line.line_cost_sgd} vs {expected}")
    checks.append(
        Check(
            "line_cost_matches_snapshot",
            "failed" if cost_problems else "passed",
            "; ".join(cost_problems) if cost_problems else "line costs match the frozen prices",
        )
    )

    summed = round(sum(line.line_cost_sgd for line in plan.shopping), 2)
    if plan.total_cost_sgd is None:
        checks.append(Check("total_cost_matches_lines", "failed", "no total was reported"))
    else:
        difference = abs(plan.total_cost_sgd - summed)
        checks.append(
            Check(
                "total_cost_matches_lines",
                "passed" if difference <= tolerances.cost_sgd_absolute else "failed",
                f"reported {plan.total_cost_sgd}, lines sum to {summed}",
            )
        )

    budget = episode["gold"]["applicable_hard_constraints"].get("budget_sgd")
    if budget is None:
        checks.append(Check("budget_truthful", "not_applicable", "no stated budget"))
    else:
        actually_within = summed <= float(budget) + tolerances.cost_sgd_absolute
        claimed = plan.within_budget
        if claimed is None:
            checks.append(Check("budget_truthful", "failed", "a budget was stated but no claim was made"))
        elif claimed != actually_within:
            checks.append(
                Check(
                    "budget_truthful",
                    "failed",
                    f"claimed within_budget={claimed}, actual total {summed} against {budget}",
                )
            )
        else:
            checks.append(Check("budget_truthful", "passed", f"total {summed} against budget {budget}"))

    return checks


def _check_claims(response: CommonEpisodeResponse, recomputed: list[Check]) -> Check:
    """A claim of satisfaction must agree with the recomputation."""
    assert response.plan is not None
    outcomes = {check.code: check.outcome for check in recomputed}
    dishonest = [
        claim.code
        for claim in response.plan.constraint_claims
        if claim.satisfied and outcomes.get(claim.code) == "failed"
    ]
    return Check(
        "constraint_claims_truthful",
        "failed" if dishonest else "passed",
        f"claimed satisfied but recomputation disagrees: {', '.join(sorted(dishonest))}"
        if dishonest
        else "no claim contradicts the recomputation",
    )


def score_episode(
    episode: dict,
    response: CommonEpisodeResponse,
    catalogs: Catalogs,
    tolerances: Tolerances | None = None,
) -> EpisodeScore:
    """Apply every requirement that applies to this episode's class."""
    tolerances = tolerances or Tolerances()
    gold = episode["gold"]
    episode_class = gold["class"]
    score = EpisodeScore(
        episode_id=episode["episode_id"],
        system_id=response.system_id,
        episode_class=episode_class,
    )

    expected_status = {
        "feasible": "plan",
        "needs_clarification": "clarification",
        "infeasible": "infeasible",
    }[episode_class]
    score.checks.append(
        Check(
            "status_matches_class",
            "passed" if response.status == expected_status else "failed",
            f"expected {expected_status}, answered {response.status}",
        )
    )

    score.checks.extend(_check_invented_entities(episode, response, catalogs))

    if episode_class == "feasible":
        if response.plan is None:
            score.checks.append(Check("plan_present", "failed", "a feasible episode requires a plan"))
            return score
        score.checks.append(Check("plan_present", "passed", "a plan was returned"))

        required_slots = list(episode["scenario"]["planning_horizon"]["slots"])
        assigned = {a.slot_id for a in response.plan.assignments}
        missing = [slot for slot in required_slots if slot not in assigned]
        score.checks.append(
            Check(
                "required_slots_assigned",
                "failed" if missing else "passed",
                f"unassigned: {', '.join(missing)}" if missing else "every required slot was assigned",
            )
        )

        constraint_checks = _check_hard_constraints(episode, response, catalogs)
        score.checks.extend(constraint_checks)
        shopping_checks = _check_shopping(episode, response, catalogs, tolerances)
        score.checks.extend(shopping_checks)
        score.checks.append(_check_claims(response, constraint_checks + shopping_checks))

    elif episode_class == "needs_clarification":
        asked = {question.field for question in response.clarification}
        required = set(gold.get("required_clarification_fields") or [])
        forbidden = set(gold.get("forbidden_clarification_fields") or [])

        unasked = sorted(required - asked)
        score.checks.append(
            Check(
                "required_clarification_asked",
                "failed" if unasked else "passed",
                f"never asked about: {', '.join(unasked)}" if unasked else "asked about every field the gold requires",
            )
        )
        intruded = sorted(asked & forbidden)
        score.checks.append(
            Check(
                "no_unnecessary_clarification",
                "failed" if intruded else "passed",
                f"asked about information it already had: {', '.join(intruded)}"
                if intruded
                else "asked nothing it was already told",
            )
        )
        score.checks.append(
            Check(
                "no_fabricated_plan",
                "failed" if response.plan is not None else "passed",
                "returned a plan despite missing required information"
                if response.plan is not None
                else "withheld the plan until the question was answered",
            )
        )

    else:  # infeasible
        payload = response.infeasible
        score.checks.append(
            Check(
                "conflict_named",
                "passed" if payload is not None and payload.conflict.strip() else "failed",
                "named the conflict"
                if payload is not None and payload.conflict.strip()
                else "refused without naming the conflict",
            )
        )
        protected = {
            str(x).lower()
            for x in (
                (episode["scenario"]["household_profile"].get("allergens") or [])
                + (episode["scenario"]["household_profile"].get("excluded_ingredients") or [])
            )
        }
        offered = []
        for option in payload.allowed_relaxations if payload else []:
            text = f"{option.description} {option.field or ''}".lower()
            offered.extend(item for item in protected if item and item in text)
        score.checks.append(
            Check(
                "relaxations_exclude_safety",
                "failed" if offered else "passed",
                f"offered to relax a safety constraint: {', '.join(sorted(set(offered)))}"
                if offered
                else "no safety constraint was offered as a relaxation",
            )
        )
        score.checks.append(
            Check(
                "no_fabricated_plan",
                "failed" if response.plan is not None else "passed",
                "returned a plan for an infeasible request"
                if response.plan is not None
                else "did not fabricate compliance",
            )
        )

    return score
