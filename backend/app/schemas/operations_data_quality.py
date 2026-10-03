from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

DataQualityStatus = Literal["available", "degraded"]
NonNegativeInt = Annotated[int, Field(ge=0)]


class OpsDataQualityIssue(BaseModel):
    artifact: str
    code: str
    detail: str


class OpsDataQualityArtifact(BaseModel):
    name: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)
    updated_at: datetime


class OpsDataQualityCoverage(BaseModel):
    released_recipes: int = Field(ge=0)
    enrichment_set: int = Field(ge=0)
    released_ingredients: int = Field(ge=0)
    recipes_with_every_field: int = Field(ge=0)


class OpsDataQualityEstimatedShare(BaseModel):
    servings: float = Field(ge=0, le=1)
    times: float = Field(ge=0, le=1)
    ingredient_amounts: float = Field(ge=0, le=1)


class OpsDataQualityNutrition(BaseModel):
    complete_recipes: int = Field(ge=0)
    total_recipes: int = Field(ge=0)
    median_energy_kcal: float | None = Field(default=None, ge=0)


class OpsDataQualitySummary(BaseModel):
    status: DataQualityStatus
    release_version: str
    schema_version: str | None
    generated_at: datetime | None
    coverage: OpsDataQualityCoverage | None
    by_cuisine: dict[str, NonNegativeInt] | None
    by_course: dict[str, NonNegativeInt] | None
    by_source: dict[str, NonNegativeInt] | None
    estimated_share: OpsDataQualityEstimatedShare | None
    nutrition: OpsDataQualityNutrition | None
    dropped_by_reason: dict[str, NonNegativeInt] | None
    allergen_rules_pending_human: int | None = Field(default=None, ge=0)
    artifacts: list[OpsDataQualityArtifact]
    issues: list[OpsDataQualityIssue]


class OpsDroppedCandidate(BaseModel):
    candidate_id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=500)
    reason: str = Field(min_length=1, max_length=500)


class OpsDroppedCandidateCollection(BaseModel):
    status: DataQualityStatus
    release_version: str
    items: list[OpsDroppedCandidate]
    total: int | None = Field(default=None, ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1)
    next_offset: int | None = Field(default=None, ge=0)
    skipped_records: int = Field(ge=0)
    artifact: OpsDataQualityArtifact | None
    issues: list[OpsDataQualityIssue]
