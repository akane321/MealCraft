"""What an ingredient-level baseline arm answers (operations/sprint2-plan/02-baselines.md section 3.1).

A baseline without our catalog cannot name recipe or product ids, so it answers with dishes: name, steps,
cooking time, servings and ingredient lines in grams. Everything else reuses the common output schema
(`app.evaluation.common_output`): the statuses, clarification questions, the infeasible payload and the
constraint claims. Dishes stay dishes here: `baseline_validation` turns the mapped dishes into one-off recipe
candidates for the product's independent validator.

`BaselineAnswer` is what the model is asked for. `episode_id` and `system_id` are not in it: the harness
fills them (`BaselineResponse`), so a model never pays for a retry because it miscopied an id.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from app.evaluation.common_output import (
    ClarificationQuestion,
    ConstraintClaim,
    InfeasiblePayload,
    ResponseStatus,
    StrictModel,
)


class BaselineIngredient(StrictModel):
    name: str = Field(min_length=1)
    quantity_g: float = Field(gt=0, allow_inf_nan=False)


class BaselineDish(StrictModel):
    name: str = Field(min_length=1)
    # The dish role this fills in a meal of several dishes; None in a one-dish meal.
    role_id: str | None = None
    servings: float = Field(gt=0, allow_inf_nan=False)
    cooking_time_minutes: int = Field(ge=0)
    steps: list[str] = Field(min_length=1)
    ingredients: list[BaselineIngredient] = Field(min_length=1)


class BaselineMeal(StrictModel):
    slot_id: str
    dishes: list[BaselineDish] = Field(min_length=1)


class BaselinePlan(StrictModel):
    meals: list[BaselineMeal] = Field(min_length=1)
    total_cost_sgd: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    within_budget: bool | None = None
    constraint_claims: list[ConstraintClaim] = Field(default_factory=list)


class BaselineAnswer(StrictModel):
    status: ResponseStatus
    clarification: list[ClarificationQuestion] = Field(default_factory=list)
    plan: BaselinePlan | None = None
    infeasible: InfeasiblePayload | None = None
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _payload_matches_status(self) -> BaselineAnswer:
        """Exactly the payload its status names: a 'plan' with no plan, or a question carrying a plan, is malformed."""
        present = {
            "plan": self.plan is not None,
            "clarification": bool(self.clarification),
            "infeasible": self.infeasible is not None,
        }
        wrong = sorted(name for name, has in present.items() if has != (name == self.status))
        if wrong:
            raise ValueError(f"status {self.status!r} does not match the payloads given: {', '.join(wrong)}")
        return self


class BaselineResponse(BaselineAnswer):
    """The answer as the harness records it, with the ids the harness filled."""

    episode_id: str
    system_id: str
