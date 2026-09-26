"""Runtime settings the operations console may change (ADR-0047).

Each registered key has a meaning, the values it accepts and a default taken from the server
environment. A console override is stored in `runtime_settings`; `runtime_value` returns it, else the
default. A change applies to new requests only.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.platform import RuntimeSetting
from app.planning.beam_planner import BeamLimits
from app.planning.meal_beam import MealBeamLimits


@dataclass(frozen=True)
class RuntimeKey:
    key: str
    label: str
    meaning: str
    default: Callable[[Settings], Any]
    choices: tuple[str, ...] | None = None
    minimum: float | None = None
    maximum: float | None = None
    integer: bool = False
    # Whether the product reads the value through `runtime_value` yet; unwired keys are stored and shown only.
    wired: bool = False

    def check(self, value: Any) -> Any:
        if self.choices is not None:
            if value not in self.choices:
                raise ValueError(f"{self.label} must be one of: {', '.join(self.choices)}.")
            return value
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{self.label} must be a number.")
        if self.integer and value != int(value):
            raise ValueError(f"{self.label} must be a whole number.")
        if not (self.minimum <= value <= self.maximum):
            raise ValueError(f"{self.label} must be between {self.minimum:g} and {self.maximum:g}.")
        return int(value) if self.integer else float(value)


REGISTRY: dict[str, RuntimeKey] = {
    item.key: item
    for item in (
        RuntimeKey(
            "agent_parser_provider",
            "Assistant parser",
            "How the assistant reads a message: the rule-based fixture parser, or the OpenAI model.",
            lambda settings: settings.agent_parser_provider,
            choices=("fixture", "openai"),
            wired=True,
        ),
        RuntimeKey(
            "openai_timeout_seconds",
            "OpenAI timeout (seconds)",
            "How long one OpenAI call may take before it is given up.",
            lambda settings: settings.openai_timeout_seconds,
            minimum=1,
            maximum=300,
            wired=True,
        ),
        RuntimeKey(
            "pricing_mode",
            "Default pricing",
            "Where prices come from when a plan does not say: the stored fixture prices or live FairPrice.",
            lambda settings: "fixture",
            choices=("fixture", "live"),
        ),
        RuntimeKey(
            "planning_capability",
            "Planning capability",
            "full plans the household's meals and dishes (ADR-0046); mvp plans seven one-dish dinners,"
            " kept to reproduce the recorded evaluations.",
            lambda settings: settings.planning_capability,
            choices=("mvp", "full"),
        ),
        RuntimeKey(
            "beam_width",
            "Beam width",
            "How many partial weeks the planner keeps at each step.",
            lambda settings: BeamLimits().width,
            minimum=1,
            maximum=512,
            integer=True,
        ),
        RuntimeKey(
            "beam_max_expansions",
            "Beam search steps",
            "The most steps the planner may take before it stops searching.",
            lambda settings: BeamLimits().max_expansions,
            minimum=1,
            maximum=1_000_000,
            integer=True,
        ),
        RuntimeKey(
            "meal_options_per_slot",
            "Meal options per slot",
            "For meals of several dishes: how many dish combinations are kept for each meal.",
            lambda settings: MealBeamLimits().meal_options_per_slot,
            minimum=1,
            maximum=1024,
            integer=True,
        ),
    )
}


def runtime_value(key: str, settings: Settings, database: Session | None = None) -> Any:
    """The console override of a registered key, else its server default."""

    if database is not None:
        stored = database.get(RuntimeSetting, key)
        if stored is not None:
            return stored.value
    return REGISTRY[key].default(settings)
