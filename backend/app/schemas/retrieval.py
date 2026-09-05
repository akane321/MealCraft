from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

RetrievalMode = Literal["live", "cache", "fixture"]
RetrievalStatus = Literal["success", "degraded", "unavailable"]
RetrievalProvider = Literal["fairprice", "youtube", "fixture"]
ExternalSource = Literal["fairprice", "youtube"]


class RetrievalTrace(BaseModel):
    """Auditable metadata shared by every external retrieval boundary."""

    requested_source: ExternalSource
    provider_used: RetrievalProvider
    mode: RetrievalMode
    status: RetrievalStatus
    query: str
    fetched_at: datetime
    parser_version: str
    candidate_count: int = Field(ge=0)
    selected_external_id: str | None = None
    warnings: list[str] = Field(default_factory=list)


class RetrievalEvidenceItem(BaseModel):
    """A typed item for future RAG packets; it is evidence, not a model answer."""

    source: ExternalSource
    external_id: str
    title: str
    url: str
    fetched_at: datetime
    facts: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class RetrievalEvidencePacket(BaseModel):
    purpose: Literal["grocery_grounding", "cooking_support", "recipe_supplement"]
    query: str
    generated_at: datetime
    items: list[RetrievalEvidenceItem]
    warnings: list[str] = Field(default_factory=list)


class TutorialVideoResponse(BaseModel):
    video_id: str
    title: str
    channel_title: str
    watch_url: str
    embed_url: str
    thumbnail_url: str | None = None
    duration_seconds: int | None = Field(default=None, ge=0)
    language_hint: str | None = None
    relevance_score: float = Field(ge=0)
    match_reasons: list[str]


class TutorialRecommendationResponse(BaseModel):
    recipe_slug: str
    recipe_title: str
    query: str
    selected_video: TutorialVideoResponse | None
    retrieval: RetrievalTrace
    warning: str | None = None
