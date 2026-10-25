"""Reuse unchanged meal options within one product planner instance."""

from app.planning.meal_beam import MealBeamPlanner


class ProductMealCandidates(MealBeamPlanner):
    """Beam and annealing share options, never search states or validation reports."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._option_context = None
        self._options = {}

    def meal_options(self, problem, slot):
        # Compare values, not object identity: packets, slots and ranking maps
        # can be edited between calls. A new request owns a new planner instance.
        context = (
            problem.model_dump_json(),
            self.limits,
            None if self.local_losses is None else tuple(sorted(self.local_losses.items())),
        )
        if context != self._option_context:
            self._options.clear()
            self._option_context = context
        key = slot.model_dump_json()
        if key not in self._options:
            options = super().meal_options(problem, slot)
            self._options[key] = (tuple(options), self.last_step_tried)
        options, self.last_step_tried = self._options[key]
        # MealOption is immutable; callers receive their own list container.
        return list(options)
