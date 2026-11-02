"""Class and field scorer for held-out intent cases (draft; needs an independent review and registered definitions).

It compares one system output with the expected action and expected fields of a gold block, and nothing else:
`reference_answer`, `rubric`, `preserve` and every other key are never read. It decides only what the output slots
and the echoed fields can show. Everything else is `not_scorable`, which is reported as such and is never a wrong
answer: planning feasibility needs the validator and the sealed catalog adjudication, question answering needs the
rubric, and actions such as a swap or a budget change are not visible in the slots. A limits-type refusal is not
visible either: the product states it as a reply or a question, so an expected refusal that shows only one is
`not_scorable` (a known gap the sealed side decides on).

It loads no sealed file. The caller passes one gold mapping and one output; the scoring definitions are not
pre-registered yet, so this is apparatus and not a result.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from app.evaluation.conversation_adapter import UnifiedOutput
from app.evaluation.field_mapping import MAPPED_FIELDS, NO_COOKING_TIME_LIMIT, map_request_fields

OBSERVABLE_ACTIONS = ("plan", "clarify", "refuse", "food_qa")
LIST_FIELDS = {"allergens", "excluded_ingredients", "dietary_requirements", "meal_types"}
# The product states a limits-type refusal (budget impossible and the like) as a reply or a question, never in the
# refusal slot, so a refusal expected of it cannot be told from a plain answer or question.
LIMITS_REFUSAL_SHOWS_AS = ("food_qa", "clarify")


class IntentVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    outcome: Literal["pass", "fail", "not_scorable"]
    reasons: list[str]


def observed_action(output: UnifiedOutput) -> str:
    """The action the output slots show. A plan next to a refusal or a question is a plan, not a clean refusal."""
    if output.plan is not None:
        return "plan"
    if output.refusal:
        return "refuse"
    if output.clarification:
        return "clarify"
    if output.answer:
        return "food_qa"
    return "none"


def _normal(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip().lower()
    if isinstance(value, list):
        return frozenset(repr(_normal(item)) for item in value)
    return value


def _same(stated: Any, want: Any) -> bool:
    # True is not 1: a boolean never matches a number.
    return isinstance(stated, bool) == isinstance(want, bool) and _normal(stated) == _normal(want)


def _silence_satisfies(name: str, want: Any) -> bool:
    """An expected value of "none" cannot be told from silence in the echo, so silence satisfies it.

    That is a false flag (the product drops it), an empty list or None, and the no-limit cooking time. A stated value
    against it still fails.
    """
    if name == "cooking_time_minutes" and want == NO_COOKING_TIME_LIMIT:
        return True
    return want is None or want is False or want == "" or (isinstance(want, (list, dict)) and not want)


def score_intent(gold: Mapping[str, Any], output: UnifiedOutput) -> IntentVerdict:
    if gold.get("kind") != "intent":
        return IntentVerdict(outcome="not_scorable", reasons=["only intent cases are scored here"])
    expected = gold.get("expected_fields") or {}
    if "action" not in expected:
        raise ValueError("a gold block needs expected_fields.action")
    fail: list[str] = []
    unknown: list[str] = []
    action = expected["action"]
    if action not in OBSERVABLE_ACTIONS:
        unknown.append(f"action {action} cannot be seen in the output slots")
    elif action == "refuse" and observed_action(output) in LIMITS_REFUSAL_SHOWS_AS:
        unknown.append(
            f"action refuse: the product states a limits refusal as a {observed_action(output)}, not a refusal"
        )
    elif observed_action(output) != action:
        fail.append(f"action: expected {action}, observed {observed_action(output)}")
    mapped = map_request_fields(output.request_fields).fields
    for name, want in expected.items():
        if name == "action":
            continue
        if name not in MAPPED_FIELDS:
            unknown.append(f"{name} cannot be read from the echoed fields")
        elif name not in mapped:
            if _silence_satisfies(name, want):
                continue
            fail.append(f"{name}: not stated")
        elif not _same(mapped[name], want):
            fail.append(f"{name}: stated value differs from the expected one")
    if fail:
        return IntentVerdict(outcome="fail", reasons=fail)
    if unknown:
        return IntentVerdict(outcome="not_scorable", reasons=unknown)
    return IntentVerdict(outcome="pass", reasons=[])
