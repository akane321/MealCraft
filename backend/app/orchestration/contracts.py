from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

type ScalarValue = str | int | float | bool | None


class ScopeClass(StrEnum):
    DOMAIN_ACTION = "domain_action"
    DOMAIN_QUESTION = "domain_question"
    SOCIAL = "social"
    PARTIALLY_SUPPORTED = "partially_supported"
    OUT_OF_SCOPE = "out_of_scope"
    RESTRICTED = "restricted"
    AMBIGUOUS = "ambiguous"
    ADVERSARIAL = "adversarial"


class AgentRunStatus(StrEnum):
    CREATED = "created"
    NEEDS_CLARIFICATION = "needs_clarification"
    READY_FOR_CONFIRMATION = "ready_for_confirmation"
    RUNNING = "running"
    PREVIEW_READY = "preview_ready"
    COMMITTED = "committed"
    DEGRADED = "degraded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class InteractionType(StrEnum):
    QUICK_REPLY = "quick_reply"
    SINGLE_SELECT = "single_select"
    MULTI_SELECT = "multi_select"
    NUMBER_INPUT = "number_input"
    DATE_RANGE = "date_range"
    QUANTITY_INPUT = "quantity_input"
    CONFIRMATION = "confirmation"
    FREE_TEXT = "free_text"


class ToolEffect(StrEnum):
    READ = "read"
    PREVIEW = "preview"
    COMMIT = "commit"


class ToolSpec(BaseModel):
    name: str
    effect: ToolEffect
    description: str


class CapabilitySpec(BaseModel):
    intent: str
    description: str
    allowed_tools: list[str] = Field(default_factory=list)
    confirmation_required: bool = False


class ScopeDecision(BaseModel):
    scope_class: ScopeClass
    detected_intents: list[str] = Field(default_factory=list)
    supported_segments: list[str] = Field(default_factory=list)
    unsupported_segments: list[str] = Field(default_factory=list)
    should_mutate_state: bool = False
    should_call_tools: bool = False
    requires_clarification: bool = False
    reason_code: str


class InteractionOption(BaseModel):
    id: str
    label: str
    value: ScalarValue


class InteractionRequest(BaseModel):
    type: InteractionType
    prompt: str
    field_path: str | None = None
    question_id: str
    options: list[InteractionOption] = Field(default_factory=list)
    allow_free_text: bool = False
    context_version: int = Field(ge=1)
    plan_revision: int | None = Field(default=None, ge=1)
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def validate_options(self) -> "InteractionRequest":
        option_types = {
            InteractionType.QUICK_REPLY,
            InteractionType.SINGLE_SELECT,
            InteractionType.MULTI_SELECT,
            InteractionType.CONFIRMATION,
        }
        if self.type in option_types and not self.options:
            raise ValueError(f"{self.type} requires at least one option")
        option_ids = [option.id for option in self.options]
        if len(option_ids) != len(set(option_ids)):
            raise ValueError("interaction option IDs must be unique")
        return self


class InteractionAnswer(BaseModel):
    question_id: str
    option_ids: list[str] = Field(default_factory=list)
    free_text: str | None = None
    context_version: int = Field(ge=1)
    plan_revision: int | None = Field(default=None, ge=1)


class EvidenceFact(BaseModel):
    fact_id: str
    kind: str
    value: ScalarValue
    source_type: str
    source_reference: str


class ResponseClaim(BaseModel):
    claim_id: str
    kind: str
    value: ScalarValue
    evidence_fact_id: str | None = None


class GroundingReport(BaseModel):
    total_claims: int
    supported_claim_ids: list[str]
    unsupported_claim_ids: list[str]

    @property
    def grounded_claim_precision(self) -> float:
        if self.total_claims == 0:
            return 1.0
        return len(self.supported_claim_ids) / self.total_claims
