"""The server-side planning capability of ADR-0036 section 6.

`mvp` (the default and the Sprint 1 demonstration) plans one dish a meal;
`full` admits meal compositions. A request for a switched-off capability is
refused with a plain reason, never reduced to the MVP shape.
"""

from app.core.config import get_settings


class PlanningCapabilityError(ValueError):
    pass


def require_composition_enabled(composition) -> None:
    if composition is not None and get_settings().planning_capability != "full":
        raise PlanningCapabilityError(
            "Meals of several dishes are switched off on this server. "
            "Plan one dish a meal, or ask an operator to switch on the full planning capability."
        )
