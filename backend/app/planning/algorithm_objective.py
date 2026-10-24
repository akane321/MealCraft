"""Shared experimental objective: variety, nutrition, ranking, exact checkout.

Usable on partial candidates for search ordering; only score_validated certifies
that a complete candidate passed the independent gate. Not a product default.
"""

from collections import Counter
from itertools import combinations
from math import isfinite

from app.planning.member_coverage import member_can_eat
from app.planning.near_duplicate_groups import DishGroups


class AlgorithmObjective:
    def __init__(
        self,
        groups: DishGroups,
        key_by_recipe: dict[str, str],
        ranking_losses: dict[str, float],
        nutrition_scales: dict[str, float] | None = None,
        *,
        priority: str = "variety",
    ):
        if priority not in {"variety", "price"}:
            raise ValueError("Unknown objective priority")
        self.priority = priority
        self.groups = groups
        self.keys = dict(key_by_recipe)
        self.ranking = dict(ranking_losses)
        self.scales = dict(nutrition_scales or {})
        if set(self.keys) != set(self.ranking) or any(not isfinite(v) or v < 0 for v in self.ranking.values()):
            raise ValueError("Every candidate needs a finite nonnegative ranking loss")
        known = {key for group in groups.groups for key in group}
        if set(self.keys.values()) != known or len(set(self.keys.values())) != len(self.keys):
            raise ValueError("Similarity keys must cover candidates exactly once")
        if any(not isfinite(v) or v <= 0 for v in self.scales.values()):
            raise ValueError("Nutrition scales must be finite and positive")
        self.near = set(groups.near_pairs)
        self.unknown = set(groups.unknown_pairs)

    def ordered(self, terms):
        """Price requests minimize checkout first; ordinary planning is unchanged."""
        values = tuple(terms)
        return (values[-1], *values[:-1]) if self.priority == "price" else values

    def kind_count(self, ids):
        representatives = []
        related = self.near | self.unknown
        for key in sorted({self.keys[rid] for rid in ids}):
            if all(tuple(sorted((key, other))) not in related for other in representatives):
                representatives.append(key)
        return len(representatives)

    def diversity(self, problem, assignments):
        """Whole-table and per-present-member counts over the planning horizon."""
        slots = {s.slot_id: s for s in problem.slots}
        recipes = {r.recipe_id: r for r in problem.recipes}
        member_ids = {}
        filled_slots = {a.slot_id for a in assignments}
        for slot in problem.slots:
            names = [m.name for m in slot.members]
            if len(names) != len(set(names)):
                raise ValueError("Member names must be unique within a slot")
            for name in names:
                if slot.slot_id in filled_slots:
                    member_ids.setdefault(name, [])
        table = []
        for assignment in assignments:
            if assignment.role_id in problem.uncounted_roles:
                continue
            table.append(assignment.recipe_id)
            for member in slots[assignment.slot_id].members:
                if member_can_eat(member, recipes[assignment.recipe_id]):
                    member_ids[member.name].append(assignment.recipe_id)
        counts = {name: self.kind_count(ids) for name, ids in sorted(member_ids.items())}
        return {
            "table_kinds": self.kind_count(table),
            "member_kinds": counts,
            "member_mean": sum(counts.values()) / len(counts) if counts else None,
            "member_min": min(counts.values()) if counts else None,
            "primary_basis": "member_mean" if counts else "table",
        }

    def terms(self, problem, assignments, report, *, partial=False) -> tuple:
        """Ordering only. Unknown similarity is conservatively penalized as a repeat.

        Pair counts grow quadratically for repeated dishes. Ignore staple repeats
        explicitly exempted by the problem. Empty optional positions come first
        as the existing filled-meal rule requires; no safety rule is a soft cost.
        """
        ids = [a.recipe_id for a in assignments if a.role_id not in problem.uncounted_roles]
        related = self.near | self.unknown
        diversity = self.diversity(problem, assignments)
        repetition = sum(
            left == right or tuple(sorted((self.keys[left], self.keys[right]))) in related
            for left, right in combinations(ids, 2)
        )
        filled = Counter(a.slot_id for a in assignments)
        # Search options already enforce structural staple coverage. Only count
        # optional roles; a staple fulfilled by a one-bowl dish is not optional.
        by_slot = {s.slot_id: s for s in problem.slots}
        present = {(a.slot_id, a.role_id) for a in assignments}
        empty = sum(
            not role.required and (slot_id, role.role_id) not in present
            for slot_id in filled
            for role in by_slot[slot_id].composition or []
        )
        empty += sum(not slot.required and slot.slot_id not in filled for slot in problem.slots)
        nutrition = 0.0
        for check in report.checks:
            if check.code.startswith("nutrition_") and not check.hard:
                if (
                    partial
                    and not assignments
                    and any(
                        b.scope == "horizon_average"
                        and b.average_basis == "selected_slots"
                        and check.code == f"nutrition_{b.metric}_{b.scope}"
                        and not b.hard
                        for b in problem.nutrition_bands
                    )
                ):
                    continue
                if check.status == "indeterminate" or check.margin is None:
                    raise ValueError("Nutrition evidence is incomplete")
                if check.code not in self.scales:
                    raise ValueError(f"Declare a nutrition normalization scale for {check.code}")
                nutrition += max(0, -check.margin) / self.scales[check.code]
        return self.ordered(
            (
                empty,
                -(diversity["member_mean"] if diversity["member_mean"] is not None else diversity["table_kinds"]),
                repetition,
                nutrition,
                sum(self.ranking[a.recipe_id] for a in assignments),
                round(report.purchase_total_sgd * 100),
            )
        )

    def score_validated(self, problem, assignments, report) -> tuple:
        if report.status != "passed":
            raise ValueError("Only independently validated complete candidates may be scored as feasible")
        return self.terms(problem, assignments, report)
