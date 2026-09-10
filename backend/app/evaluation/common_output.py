"""The single answer shape every compared system must produce.

`docs/design/comparative-evaluation-v2.md` section 9 requires one output schema
across MealCraft, the Rule-only baseline, the context-matched LLM-only baseline,
the plain assistant and human manual planning. Without it, a comparison silently
becomes a comparison of output formats: the system whose native shape is easiest
to read scores best, and a model that writes a good plan in prose scores zero
for reasons that have nothing to do with planning.

So this is deliberately not MealCraft's internal solution type. It carries only
what a system can honestly be asked for - what it decided, what it selected, and
what it claims - and none of the internal machinery a baseline has no way to
produce. A validation report, a search trace or a rejection matrix would be
unanswerable for an LLM-only condition and would tilt the comparison.

Section 9 also fixes the consequence of malformed output: it counts as an
end-to-end failure and is separately reported as a schema failure, so that
"could not follow the format" never quietly disappears into "planned badly".
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ResponseStatus = Literal["plan", "clarification", "infeasible"]


class StrictModel(BaseModel):
    """Unknown fields are rejected.

    A system that invents an output field is making a claim nobody agreed to
    score, and silently dropping it would hide that.
    """

    model_config = ConfigDict(extra="forbid")


class ClarificationQuestion(StrictModel):
    field: str = Field(description="the missing input, named as in the gold label")
    question: str


class SlotAssignment(StrictModel):
    slot_id: str
    recipe_id: str
    servings: float = Field(gt=0)


class ShoppingLine(StrictModel):
    ingredient_id: str
    required_quantity: float | None = Field(default=None, ge=0)
    unit: str | None = None
    pantry_deduction: float = Field(default=0.0, ge=0)
    product_id: str | None = None
    packages: int = Field(default=0, ge=0)
    line_cost_sgd: float = Field(default=0.0, ge=0)


class ConstraintClaim(StrictModel):
    """What the system asserts it satisfied.

    Scored against a recomputation, never trusted. A system that claims a
    constraint held when it did not is failing differently from one that
    reports the violation honestly, and the two must stay distinguishable.
    """

    code: str
    satisfied: bool
    detail: str | None = None


class RelaxationOption(StrictModel):
    """A change the user could choose to make an infeasible request feasible.

    Never a safety constraint. Offering to drop an allergen is a failure, not an
    accommodation, and scoring treats it as one.
    """

    description: str
    field: str | None = None


class PlanPayload(StrictModel):
    assignments: list[SlotAssignment]
    shopping: list[ShoppingLine] = Field(default_factory=list)
    total_cost_sgd: float | None = Field(default=None, ge=0)
    within_budget: bool | None = None
    constraint_claims: list[ConstraintClaim] = Field(default_factory=list)


class InfeasiblePayload(StrictModel):
    conflict: str
    allowed_relaxations: list[RelaxationOption] = Field(default_factory=list)


class CommonEpisodeResponse(StrictModel):
    """One system's answer to one episode."""

    episode_id: str
    system_id: str = Field(description="which system produced this, for paired analysis")
    status: ResponseStatus

    clarification: list[ClarificationQuestion] = Field(default_factory=list)
    plan: PlanPayload | None = None
    infeasible: InfeasiblePayload | None = None

    warnings: list[str] = Field(default_factory=list)
    evidence_references: list[str] = Field(default_factory=list)


class SchemaFailure(Exception):
    """Raised when a system's output cannot be read as a response at all."""

    def __init__(self, episode_id: str, detail: str) -> None:
        super().__init__(f"{episode_id}: {detail}")
        self.episode_id = episode_id
        self.detail = detail


def parse_response(episode_id: str, payload: str | dict) -> CommonEpisodeResponse:
    """Read one system's answer, or raise `SchemaFailure`.

    Callers record the failure and score the episode as unsuccessful. They must
    not repair the payload: a rescued answer is not the answer the system gave,
    and repairing for one system and not another is exactly the asymmetry the
    common schema exists to prevent.
    """
    try:
        if isinstance(payload, str):
            return CommonEpisodeResponse.model_validate_json(payload)
        return CommonEpisodeResponse.model_validate(payload)
    except Exception as error:  # noqa: BLE001 - reported, never repaired
        raise SchemaFailure(episode_id, str(error)) from error
