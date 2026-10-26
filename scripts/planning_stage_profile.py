"""Opt-in, single-thread developer profiling; never stored in product traces."""

from collections import defaultdict
from contextlib import ExitStack
from functools import wraps
from time import perf_counter
from unittest.mock import patch

from app.planning import algorithm_reference
from app.planning.algorithm_objective import AlgorithmObjective
from app.planning.final_scope_validator import FinalPlanningValidator
from app.planning.meal_beam import MealBeamPlanner


class PlanningStageProfile:
    """Inclusive stage durations overlap; do not sum them as elapsed time."""

    def __init__(self, clock=perf_counter):
        self.clock = clock
        self.rows = defaultdict(lambda: {"calls": 0, "seconds": 0.0, "errors": 0})
        self.stack = ExitStack()

    def measure(self, name, function):
        @wraps(function)
        def measured(*args, **kwargs):
            started = self.clock()
            row = self.rows[name]
            row["calls"] += 1
            try:
                return function(*args, **kwargs)
            except Exception:
                row["errors"] += 1
                raise
            finally:
                row["seconds"] += self.clock() - started

        return measured

    def __enter__(self):
        targets = [
            (algorithm_reference, "domains", "annealing_domains"),
            (algorithm_reference, "evaluate", "annealing_proposal"),
            (MealBeamPlanner, "meal_options", "meal_options"),
            (MealBeamPlanner, "_build_shopping", "shopping"),
            (FinalPlanningValidator, "validate", "independent_validation"),
            (AlgorithmObjective, "score_validated", "objective"),
        ]
        try:
            for owner, attribute, label in targets:
                self.stack.enter_context(patch.object(owner, attribute, self.measure(label, getattr(owner, attribute))))
        except Exception:
            self.stack.close()
            raise
        return self

    def __exit__(self, *exc):
        return self.stack.__exit__(*exc)

    def snapshot(self):
        return {name: dict(row) for name, row in sorted(self.rows.items())}
