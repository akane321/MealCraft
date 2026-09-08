"""Conservative bounds for the current reference objective and normalized packets."""

from collections import Counter
from math import isfinite

from app.planning.final_scope_scoring import local_recipe_loss


class SearchBounds:
    def __init__(self, problem, slots, domains):
        self.problem = problem
        self.slots = slots
        self.domains = domains
        self.recipes = {recipe.recipe_id: recipe for recipe in problem.recipes}
        self.by_slot = {slot.slot_id: slot for slot in slots}
        self.costs = {
            (slot.slot_id, recipe_id): local_recipe_loss(
                self.recipes[recipe_id],
                max_time_minutes=slot.max_time_minutes,
                health_preferences=problem.health_preferences,
            )
            for slot in slots
            for recipe_id in domains[slot.slot_id].eligible_recipe_ids
        }

    def loss_lower_bound(self, state, next_index):
        # Ignore future repetition increments and adjacency, both nonnegative.
        counts = Counter(recipe for _, recipe in state.choices)
        bound = state.loss
        for slot in self.slots[next_index:]:
            domain = self.domains[slot.slot_id]
            if domain.must_assign:
                bound += min(
                    (self.costs[slot.slot_id, recipe] + 0.1 * counts[recipe] for recipe in domain.eligible_recipe_ids),
                    default=float("inf"),
                )
        return bound

    def nutrition_possible(self, state, next_index):
        for band in self.problem.nutrition_bands:
            if not band.hard or band.scope == "per_slot":
                continue
            dates = {slot.planned_date for slot in self.slots}
            # The existing validator averages only dates with selected meals.
            # Avoid assuming a fixed denominator when a date can be skipped.
            mandatory_dates = {slot.planned_date for slot in self.slots if self.domains[slot.slot_id].must_assign}
            if band.scope == "horizon_average" and dates != mandatory_dates:
                continue
            groups = [dates] if band.scope == "horizon_average" else [{day} for day in sorted(dates)]
            for group in groups:
                selected = [
                    (slot, recipe) for slot, recipe in state.choices if self.by_slot[slot].planned_date in group
                ]
                remaining = [slot for slot in self.slots[next_index:] if slot.planned_date in group]
                if not selected and not any(self.domains[slot.slot_id].must_assign for slot in remaining):
                    continue  # This date may be absent from the final report.
                current = sum(
                    getattr(self.recipes[recipe].nutrients_per_serving, band.metric) for _, recipe in selected
                )
                low = high = current
                for slot in remaining:
                    domain = self.domains[slot.slot_id]
                    values = [
                        getattr(self.recipes[recipe].nutrients_per_serving, band.metric)
                        for recipe in domain.eligible_recipe_ids
                    ]
                    if not domain.must_assign:
                        values.append(0.0)
                    if not values:
                        return False
                    low += min(values)
                    high += max(values)
                divisor = len(dates) if band.scope == "horizon_average" else 1
                low, high = low / divisor, high / divisor
                if not isfinite(low) or not isfinite(high):
                    continue
                if band.lower is not None and high < band.lower - 1e-6:
                    return False
                if band.upper is not None and low > band.upper + 1e-6:
                    return False
        return True

    def dominance_key(self, state):
        # Same per-day recipe multiset and serving basis preserves nutrition,
        # demand, recipe counts, selected dates and every future continuation.
        # Last recipe preserves the next adjacency penalty. Past loss may differ.
        meals = Counter(
            (str(self.by_slot[slot].planned_date), recipe, self.by_slot[slot].servings)
            for slot, recipe in state.choices
        )
        return tuple(sorted(meals.items())), state.choices[-1][1] if state.choices else None
