from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_serializer
from pydantic.json_schema import SkipJsonSchema

from app.orchestration.contracts import (
    AgentRunStatus,
    InteractionAnswer,
    InteractionRequest,
    ScopeDecision,
    ToolEffect,
    ToolRunStatus,
)
from app.schemas.household_rules import HouseholdPlanning, PlanningPreferences
from app.schemas.meal_plan import (
    MEAL_ORDER,
    MealPlanEventType,
    MealPlanReplanEventResponse,
    MealPlanShape,
    WeeklyMealPlanResponse,
)
from app.schemas.product import PricingMode
from app.schemas.recommendation import (
    NO_COOKING_TIME_LIMIT,
    AvailableIngredientInput,
    DietaryPreference,
    HealthPreference,
    NutritionTargets,
)

AgentSessionStatus = Literal["collecting", "ready", "planned"]
AgentMessageRole = Literal["user", "assistant", "system"]
AgentParserProvider = Literal["fixture", "openai"]


class AgentMessageInput(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    # The household's week this message changes (a dish's Swap, Keep, Skip or Can't buy). A conversation
    # that planned no week of its own takes that week on, and changes it from then on.
    plan_id: int | None = Field(default=None, ge=1)


class AgentInteractionInput(InteractionAnswer):
    pass


class AgentPreferenceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    context_version: int = Field(ge=1)
    planning_preferences: PlanningPreferences


class AgentMessageResponse(BaseModel):
    id: int
    role: AgentMessageRole
    content: str
    created_at: datetime


class UnmatchedTermSuggestion(BaseModel):
    """A word the planner cannot check, the field it was meant for, and catalog ids it might mean."""

    term: str
    field: Literal["excluded_ingredients", "available_ingredients", "allergens"]
    options: list[str] = Field(default_factory=list)


class AgentConstraintExtraction(BaseModel):
    household_size: int | None = Field(default=None, ge=1, le=12)
    max_cooking_time_minutes: int | None = Field(default=None, ge=5, le=240)
    budget_per_meal_sgd: float | None = Field(default=None, gt=0, le=1000)
    weekly_budget_sgd: float | None = Field(default=None, gt=0, le=7000)
    allergens: list[str] | None = None
    excluded_ingredients: list[str] | None = None
    dietary_preferences: list[DietaryPreference] | None = None
    requires_halal: bool | None = None
    health_preferences: list[HealthPreference] | None = None
    planning_preferences: PlanningPreferences | None = None
    nutrition_targets: NutritionTargets | None = None
    max_sodium_mg_per_meal: float | None = Field(default=None, ge=100, le=5000)
    available_ingredients: list[AvailableIngredientInput] | None = None
    acknowledged_unknown_quantities: list[str] = Field(default_factory=list)
    pricing_mode: PricingMode | None = None
    max_uses_per_recipe: int | None = Field(
        default=None,
        ge=1,
        le=7,
        description=(
            "How many times one dish may be served in the week, only when the user says so: 1 when they ask "
            "for no repeats (don't repeat any dish, no dish twice, 不要重复, 一周不重样); a larger number only "
            "when they state it (at most twice is 2). Null when the message says nothing about repeating."
        ),
    )
    plan_day_count: int | None = Field(
        default=None,
        ge=1,
        le=14,
        description=(
            "How many days the plan covers, only when the user asks for fewer than a week or for a stated number "
            "of days: tomorrow's dinner, tonight, today is 1; this weekend is 2; the next 3 days, 接下来三天 is 3. "
            "At most 14. Null when the message does not say how many days (the plan then covers the week)."
        ),
    )
    plan_meals: list[Literal["breakfast", "lunch", "dinner"]] | None = Field(
        default=None,
        description=(
            "Which meals of each day to plan, only when the user names them for this plan: dinner tonight, "
            "tomorrow's dinner, dinners only, 只要晚餐 is [dinner]. Null when the message does not narrow the meals."
        ),
    )
    medical_request_detected: bool = False
    assistant_summary: str | None = None
    # Filled by the server, never by the model: words the household used that match no
    # ingredient or allergen the planner can check. They are asked about, not dropped.
    unmatched_terms: list[str] = Field(default_factory=list)
    # Server-only as well, and left out of the schema the model fills (SkipJsonSchema).
    unmatched_suggestions: SkipJsonSchema[list[UnmatchedTermSuggestion]] = Field(default_factory=list)

    @field_validator("plan_meals")
    @classmethod
    def _meals_in_order(cls, meals):
        # Each meal once, in the order they are eaten; none left is no narrowing.
        return [meal for meal in MEAL_ORDER if meal in (meals or ())] or None


class AgentConstraintState(BaseModel):
    household_size: int | None = None
    # A conversation with no saved household starts with no time limit, not one it never stated.
    max_cooking_time_minutes: int = NO_COOKING_TIME_LIMIT
    budget_per_meal_sgd: float | None = None
    weekly_budget_sgd: float | None = None
    allergens: list[str] = Field(default_factory=list)
    excluded_ingredients: list[str] = Field(default_factory=list)
    dietary_preferences: list[DietaryPreference] = Field(default_factory=list)
    requires_halal: bool = False
    health_preferences: list[HealthPreference] = Field(default_factory=list)
    planning_preferences: PlanningPreferences = Field(default_factory=PlanningPreferences)
    nutrition_targets: NutritionTargets = Field(default_factory=NutritionTargets)
    max_sodium_mg_per_meal: float | None = None
    available_ingredients: list[AvailableIngredientInput] = Field(default_factory=list)
    pricing_mode: PricingMode = "fixture"
    # Which meals and dishes this week plans (ADR-0046); None is the household default.
    plan_shape: MealPlanShape | None = None
    # How often one dish may be served in the week; 1 is "no repeats". None: repeats are avoided, not forbidden.
    max_uses_per_recipe: int | None = None
    # The dishes of a week the household found monotonous: a new week avoids them while enough others remain.
    avoid_recipe_ids: list[int] = Field(default_factory=list, max_length=200)
    # The week's first day: what the request said ("next week", "from Wednesday"), else today or tomorrow
    # (agent/plan_dates.py). A day already past by the time the week is planned becomes today.
    start_date: date | None = None
    # How many days the plan covers (1 to 14): fewer than a week for "dinner tonight", "this weekend", "the next 3
    # days" (agent/plan_dates.py). Left out of the dump when 7, like the household key (and the two fields below).
    day_count: int = Field(default=7, ge=1, le=14)
    # The weekly budget before it is pro-rated to a plan of fewer days or meals (saved, or stated per week):
    # every change of days or meals pro-rates from it, and a week restores it. None until a short plan needs it.
    base_weekly_budget_sgd: float | None = None
    # The household's meals while a plan names fewer of them (plan_shape then holds only those): a week restores it.
    usual_plan_shape: MealPlanShape | None = None
    # The saved household's members, rules and limits (layer 08); a size the conversation states replaces its
    # members and who is home. None: a conversation with no saved household.
    household: HouseholdPlanning | None = None

    @model_serializer(mode="wrap")
    def _no_household_key(self, handler):
        # Without a household block a state dumps as before the field existed (digests, stored checkpoints).
        data = handler(self)
        if self.day_count == 7 and isinstance(data, dict):
            data.pop("day_count", None)
        for field in ("base_weekly_budget_sgd", "usual_plan_shape"):
            if getattr(self, field) is None and isinstance(data, dict):
                data.pop(field, None)
        if self.household is None and isinstance(data, dict):
            data.pop("household", None)
        if self.planning_preferences == PlanningPreferences() and isinstance(data, dict):
            data.pop("planning_preferences", None)
        if not self.requires_halal and isinstance(data, dict):
            data.pop("requires_halal", None)
        return data


class AgentReplanDraft(BaseModel):
    event_type: MealPlanEventType | None = None
    entry_id: int | None = Field(default=None, gt=0)
    # The day named so far, kept when that day holds several dishes and the dish is still to be asked.
    day_index: int | None = Field(default=None, ge=1, le=14)
    unavailable_ingredient: str | None = None
    reason: str | None = None
    # A lock of a whole named meal ("don't change Monday's dinner"): every dish of the entry's meal.
    whole_meal: bool = False


class AgentRunCheckpointResponse(BaseModel):
    id: int
    sequence: int
    stage: str
    status: str
    state_digest: str
    state_payload: dict
    evidence_references: list[dict]
    created_at: datetime

    model_config = {"from_attributes": True}


class AgentToolExecutionResponse(BaseModel):
    id: int
    sequence: int
    tool_name: str
    effect: ToolEffect
    status: ToolRunStatus
    arguments_digest: str
    result_reference: str | None
    provider_mode: str | None
    error_code: str | None
    started_at: datetime
    completed_at: datetime

    model_config = {"from_attributes": True}


class AgentRunResponse(BaseModel):
    id: int
    agent_session_id: int
    intent: str
    status: AgentRunStatus
    input_digest: str
    context_version: int
    plan_revision: int | None
    scope_decision: dict | None
    run_config: dict | None = Field(default=None, validation_alias="model_config")
    checkpoint_version: int
    max_llm_calls: int
    used_llm_calls: int
    max_tool_calls: int
    used_tool_calls: int
    max_retrieval_retries: int
    used_retrieval_retries: int
    max_planning_attempts: int
    used_planning_attempts: int
    max_wall_seconds: int
    max_api_cost_usd: Decimal | None
    used_api_cost_usd: Decimal
    deadline_at: datetime
    termination_reason_code: str | None
    error_code: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    checkpoints: list[AgentRunCheckpointResponse] = Field(default_factory=list)
    tool_executions: list[AgentToolExecutionResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class AgentRunCollectionResponse(BaseModel):
    items: list[AgentRunResponse]


class AgentSessionResponse(BaseModel):
    id: int
    status: AgentSessionStatus
    parser_provider: AgentParserProvider
    constraints: AgentConstraintState
    missing_fields: list[str]
    clarification_questions: list[str]
    messages: list[AgentMessageResponse]
    plan_id: int | None
    replan_draft: AgentReplanDraft
    pending_replan: MealPlanReplanEventResponse | None
    context_version: int = Field(ge=1)
    last_scope_decision: ScopeDecision | None
    pending_interaction: InteractionRequest | None
    latest_run: AgentRunResponse | None = None
    can_confirm: bool
    # The household's name for it (None: its first message stands in) and when it was pinned (None: not pinned).
    title: str | None = None
    pinned_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class AgentSessionLabel(BaseModel):
    """Rename (a blank title goes back to the first message) or pin a conversation; a field left out stays."""

    title: str | None = Field(default=None, max_length=120)
    pinned: bool | None = None


class AgentSessionCollectionResponse(BaseModel):
    items: list[AgentSessionResponse]


class AgentConfirmationResponse(BaseModel):
    session: AgentSessionResponse
    plan: WeeklyMealPlanResponse


class AgentReplanConfirmationResponse(BaseModel):
    session: AgentSessionResponse
    event: MealPlanReplanEventResponse
    plan: WeeklyMealPlanResponse
