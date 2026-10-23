"""Optimistic fractional purchase bounds for developer search, not price quotes."""

from collections import defaultdict

from app.planning.meal_beam import MealState, assignments_of
from app.planning.meal_composition import dish_servings


class CompletionBudget:
    def __init__(self, problem, slots, options):
        self.problem, self.slots = problem, slots
        self.by_slot = {s.slot_id: s for s in slots}
        self.recipes = {r.recipe_id: r for r in problem.recipes}
        self.prices = {}
        for product in problem.products:
            if product.available:
                key = (product.ingredient_id, product.package_unit)
                price = product.price_sgd / product.package_quantity
                self.prices[key] = min(price, self.prices.get(key, price))
        # Grant all original pantry to every trip. This is deliberately optimistic:
        # the independent basket consumes it once; a lower bound must never overcharge.
        self.credit = sum(
            p.quantity * self.prices.get((p.ingredient_id, p.unit), 0) for p in problem.pantry if p.quantity is not None
        )
        self.values = {(s.slot_id, o.dishes): self.meal_value(s, o.dishes) for s in slots for o in options[s.slot_id]}
        self.minimum = {
            s.slot_id: min((self.values[s.slot_id, o.dishes] for o in options[s.slot_id]), default=0) for s in slots
        }

    def meal_value(self, slot, dishes):
        assignments = assignments_of(MealState(((slot.slot_id, dishes),)))
        servings = dish_servings(self.problem, assignments)
        return sum(
            line.quantity
            * float(servings.get(i, slot.servings))
            / self.recipes[a.recipe_id].servings
            * self.prices.get((line.ingredient_id, line.unit), 0)
            for i, a in enumerate(assignments)
            for line in self.recipes[a.recipe_id].ingredients
            if line.quantity is not None
        )

    def costs(self, state, *, complete=False):
        costs = defaultdict(float)
        chosen = dict(state.choices)
        for slot in self.slots:
            if slot.slot_id in chosen:
                costs[slot.trip] += self.values[slot.slot_id, chosen[slot.slot_id]]
            elif complete:
                costs[slot.trip] += self.minimum[slot.slot_id]
        return [max(0, value - self.credit) for value in costs.values()]

    def permits(self, state):
        budget = self.problem.purchase_budget_sgd
        return (
            not self.problem.budget_is_hard
            or budget is None
            or all(value <= budget + 1e-7 for value in self.costs(state, complete=True))
        )
