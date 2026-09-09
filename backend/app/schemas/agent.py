from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.orchestration.contracts import (
    AgentRunStatus,
    InteractionAnswer,
    InteractionRequest,
    ScopeDecision,
    ToolEffect,
    ToolRunStatus,
)
from app.schemas.meal_plan import (
    MealPlanEventType,
    MealPlanReplanEventResponse,
    WeeklyMealPlanResponse,
)
from app.schemas.product import PricingMode
from app.schemas.recommendation import (
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


class AgentInteractionInput(InteractionAnswer):
    pass


class AgentMessageResponse(BaseModel):
    id: int
    role: AgentMessageRole
    content: str
    created_at: datetime


class AgentConstraintExtraction(BaseModel):
    household_size: int | None = Field(default=None, ge=1, le=12)
    max_cooking_time_minutes: int | None = Field(default=None, ge=5, le=240)
    budget_per_meal_sgd: float | None = Field(default=None, gt=0, le=1000)
    weekly_budget_sgd: float | None = Field(default=None, gt=0, le=7000)
    allergens: list[str] | None = None
    excluded_ingredients: list[str] | None = None
    dietary_preferences: list[DietaryPreference] | None = None
    health_preferences: list[HealthPreference] | None = None
    nutrition_targets: NutritionTargets | None = None
    max_sodium_mg_per_meal: float | None = Field(default=None, ge=100, le=5000)
    available_ingredients: list[AvailableIngredientInput] | None = None
    acknowledged_unknown_quantities: list[str] = Field(default_factory=list)
    pricing_mode: PricingMode | None = None
    medical_request_detected: bool = False
    assistant_summary: str | None = None


class AgentConstraintState(BaseModel):
    household_size: int | None = None
    max_cooking_time_minutes: int = 60
    budget_per_meal_sgd: float | None = None
    weekly_budget_sgd: float | None = None
    allergens: list[str] = Field(default_factory=list)
    excluded_ingredients: list[str] = Field(default_factory=list)
    dietary_preferences: list[DietaryPreference] = Field(default_factory=list)
    health_preferences: list[HealthPreference] = Field(default_factory=list)
    nutrition_targets: NutritionTargets = Field(default_factory=NutritionTargets)
    max_sodium_mg_per_meal: float | None = None
    available_ingredients: list[AvailableIngredientInput] = Field(default_factory=list)
    pricing_mode: PricingMode = "fixture"


class AgentReplanDraft(BaseModel):
    event_type: MealPlanEventType | None = None
    entry_id: int | None = Field(default=None, gt=0)
    unavailable_ingredient: str | None = None
    reason: str | None = None


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
    created_at: datetime
    updated_at: datetime


class AgentSessionCollectionResponse(BaseModel):
    items: list[AgentSessionResponse]


class AgentConfirmationResponse(BaseModel):
    session: AgentSessionResponse
    plan: WeeklyMealPlanResponse


class AgentReplanConfirmationResponse(BaseModel):
    session: AgentSessionResponse
    event: MealPlanReplanEventResponse
    plan: WeeklyMealPlanResponse
