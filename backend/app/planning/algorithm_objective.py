"""Shared experimental objective: variety, nutrition, ranking, exact checkout.

Usable on partial candidates for search ordering; only score_validated certifies
that a complete candidate passed the independent gate. Not a product default.
"""

from collections import Counter
from itertools import combinations
from math import isfinite

from app.planning.near_duplicate_groups import DishGroups


class AlgorithmObjective:
    def __init__(
        self,
        groups: DishGroups,
        key_by_recipe: dict[str, str],
        ranking_losses: dict[str, float],
        nutrition_scales: dict[str, float] | None = None,
    ):
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

    def terms(self, problem, assignments, report) -> tuple:
        """Ordering only. Unknown similarity is conservatively penalized as a repeat.

        Pair counts grow quadratically for repeated dishes. Ignore staple repeats
        explicitly exempted by the problem. Empty optional positions come first
        as the existing filled-meal rule requires; no safety rule is a soft cost.
        """
        ids = [a.recipe_id for a in assignments if a.role_id not in problem.uncounted_roles]
        related = self.near | self.unknown
        representatives = []
        for key in sorted({self.keys[recipe_id] for recipe_id in ids}):
            if all(tuple(sorted((key, other))) not in related for other in representatives):
                representatives.append(key)
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
                if check.status == "indeterminate" or check.margin is None:
                    raise ValueError("Nutrition evidence is incomplete")
                if check.code not in self.scales:
                    raise ValueError(f"Declare a nutrition normalization scale for {check.code}")
                nutrition += max(0, -check.margin) / self.scales[check.code]
        return (
            empty,
            -len(representatives),
            repetition,
            nutrition,
            sum(self.ranking[a.recipe_id] for a in assignments),
            round(report.purchase_total_sgd * 100),
        )

    def score_validated(self, problem, assignments, report) -> tuple:
        if report.status != "passed":
            raise ValueError("Only independently validated complete candidates may be scored as feasible")
        return self.terms(problem, assignments, report)
