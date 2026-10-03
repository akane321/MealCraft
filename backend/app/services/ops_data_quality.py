from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.paths import repository_root
from app.schemas.operations_data_quality import (
    OpsDataQualityArtifact,
    OpsDataQualityCoverage,
    OpsDataQualityEstimatedShare,
    OpsDataQualityIssue,
    OpsDataQualityNutrition,
    OpsDataQualitySummary,
    OpsDroppedCandidate,
    OpsDroppedCandidateCollection,
)

CURRENT_RELEASE = "v2.1"
QUALITY_SUMMARY = "quality_summary.json"
RELEASE_MANIFEST = "release_manifest.json"
DROPPED_RECORDS = "dropped.jsonl"
NonNegativeInt = Annotated[int, Field(ge=0)]
ModelT = TypeVar("ModelT", bound=BaseModel)


class _CoverageArtifact(BaseModel):
    model_config = ConfigDict(extra="ignore")

    released_recipes: int = Field(ge=0)
    enrichment_set: int = Field(ge=0)
    released_ingredients: int = Field(ge=0)
    recipes_with_every_field: int = Field(ge=0)


class _EstimatedShareArtifact(BaseModel):
    model_config = ConfigDict(extra="ignore")

    servings: float = Field(ge=0, le=1)
    times: float = Field(ge=0, le=1)
    ingredient_amounts: float = Field(ge=0, le=1)


class _NutritionArtifact(BaseModel):
    model_config = ConfigDict(extra="ignore")

    median_energy_kcal: float | None = Field(default=None, ge=0)


class _QualitySummaryArtifact(BaseModel):
    model_config = ConfigDict(extra="ignore")

    release_version: str
    created_at: datetime
    coverage: _CoverageArtifact
    by_cuisine: dict[str, NonNegativeInt]
    by_course: dict[str, NonNegativeInt]
    by_source: dict[str, NonNegativeInt]
    estimated_share: _EstimatedShareArtifact
    dropped_by_reason: dict[str, NonNegativeInt]
    allergen_rules_pending_human: int = Field(ge=0)
    nutrition_per_serving: _NutritionArtifact


class _ReleaseManifestArtifact(BaseModel):
    model_config = ConfigDict(extra="ignore")

    release_version: str
    schema_version: str
    created_at: datetime


class DataQualityService:
    """Read registered release artifacts without accepting filesystem input from a caller."""

    def __init__(self, release_directory: Path, release_version: str = CURRENT_RELEASE) -> None:
        self.release_directory = release_directory
        self.release_version = release_version

    @classmethod
    def current(cls) -> DataQualityService:
        directory = repository_root() / "data-engineering" / "data" / "release" / CURRENT_RELEASE
        return cls(directory)

    def summary(self) -> OpsDataQualitySummary:
        issues: list[OpsDataQualityIssue] = []
        artifacts = self._artifacts((QUALITY_SUMMARY, RELEASE_MANIFEST), issues)
        summary = self._load_model(QUALITY_SUMMARY, _QualitySummaryArtifact, issues)
        manifest = self._load_model(RELEASE_MANIFEST, _ReleaseManifestArtifact, issues)

        if summary is not None and summary.release_version != self.release_version:
            issues.append(self._version_issue(QUALITY_SUMMARY, summary.release_version))
        if manifest is not None and manifest.release_version != self.release_version:
            issues.append(self._version_issue(RELEASE_MANIFEST, manifest.release_version))

        if summary is None:
            return OpsDataQualitySummary(
                status="degraded",
                release_version=self.release_version,
                schema_version=manifest.schema_version if manifest else None,
                generated_at=manifest.created_at if manifest else None,
                coverage=None,
                by_cuisine=None,
                by_course=None,
                by_source=None,
                estimated_share=None,
                nutrition=None,
                dropped_by_reason=None,
                allergen_rules_pending_human=None,
                artifacts=artifacts,
                issues=issues,
            )

        coverage = OpsDataQualityCoverage.model_validate(summary.coverage.model_dump())
        nutrition = OpsDataQualityNutrition(
            complete_recipes=coverage.recipes_with_every_field,
            total_recipes=coverage.released_recipes,
            median_energy_kcal=summary.nutrition_per_serving.median_energy_kcal,
        )
        return OpsDataQualitySummary(
            status="degraded" if issues else "available",
            release_version=self.release_version,
            schema_version=manifest.schema_version if manifest else None,
            generated_at=summary.created_at,
            coverage=coverage,
            by_cuisine=summary.by_cuisine,
            by_course=summary.by_course,
            by_source=summary.by_source,
            estimated_share=OpsDataQualityEstimatedShare.model_validate(summary.estimated_share.model_dump()),
            nutrition=nutrition,
            dropped_by_reason=summary.dropped_by_reason,
            allergen_rules_pending_human=summary.allergen_rules_pending_human,
            artifacts=artifacts,
            issues=issues,
        )

    def dropped(self, *, offset: int, limit: int, reason: str | None) -> OpsDroppedCandidateCollection:
        issues: list[OpsDataQualityIssue] = []
        artifact = self._artifact(DROPPED_RECORDS, issues)
        path = self.release_directory / DROPPED_RECORDS
        if artifact is None:
            return OpsDroppedCandidateCollection(
                status="degraded",
                release_version=self.release_version,
                items=[],
                total=None,
                offset=offset,
                limit=limit,
                next_offset=None,
                skipped_records=0,
                artifact=None,
                issues=issues,
            )

        records: list[OpsDroppedCandidate] = []
        invalid_json_lines: list[int] = []
        invalid_record_lines: list[int] = []
        try:
            with path.open(encoding="utf-8") as source:
                for line_number, line in enumerate(source, start=1):
                    if not line.strip():
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        invalid_json_lines.append(line_number)
                        continue
                    try:
                        record = OpsDroppedCandidate.model_validate(payload)
                    except ValidationError:
                        invalid_record_lines.append(line_number)
                        continue
                    if reason is None or record.reason == reason:
                        records.append(record)
        except OSError:
            issues.append(self._issue(DROPPED_RECORDS, "unreadable", "The registered artifact cannot be read."))
            return OpsDroppedCandidateCollection(
                status="degraded",
                release_version=self.release_version,
                items=[],
                total=None,
                offset=offset,
                limit=limit,
                next_offset=None,
                skipped_records=0,
                artifact=artifact,
                issues=issues,
            )

        self._append_line_issue(issues, "invalid_json", invalid_json_lines)
        self._append_line_issue(issues, "invalid_record", invalid_record_lines)
        total = len(records)
        page = records[offset : offset + limit]
        next_offset = offset + len(page) if offset + len(page) < total else None
        skipped = len(invalid_json_lines) + len(invalid_record_lines)
        return OpsDroppedCandidateCollection(
            status="degraded" if issues else "available",
            release_version=self.release_version,
            items=page,
            total=total,
            offset=offset,
            limit=limit,
            next_offset=next_offset,
            skipped_records=skipped,
            artifact=artifact,
            issues=issues,
        )

    def _load_model(self, name: str, model: type[ModelT], issues: list[OpsDataQualityIssue]) -> ModelT | None:
        path = self.release_directory / name
        if not path.is_file():
            if not self._has_issue(issues, name, "missing"):
                issues.append(self._issue(name, "missing", "The registered artifact is missing."))
            return None
        if self._has_issue(issues, name, "unreadable"):
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            issues.append(self._issue(name, "invalid_json", "The registered artifact is not valid JSON."))
            return None
        try:
            return model.model_validate(payload)
        except ValidationError:
            issues.append(self._issue(name, "invalid_contract", "The registered artifact does not match its contract."))
            return None

    def _artifacts(self, names: tuple[str, ...], issues: list[OpsDataQualityIssue]) -> list[OpsDataQualityArtifact]:
        artifacts: list[OpsDataQualityArtifact] = []
        for name in names:
            artifact = self._artifact(name, issues)
            if artifact is not None:
                artifacts.append(artifact)
        return artifacts

    def _artifact(self, name: str, issues: list[OpsDataQualityIssue]) -> OpsDataQualityArtifact | None:
        path = self.release_directory / name
        if not path.is_file():
            issues.append(self._issue(name, "missing", "The registered artifact is missing."))
            return None
        try:
            content = path.read_bytes()
            updated_at = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        except OSError:
            issues.append(self._issue(name, "unreadable", "The registered artifact cannot be read."))
            return None
        return OpsDataQualityArtifact(
            name=name,
            sha256=hashlib.sha256(content).hexdigest(),
            size_bytes=len(content),
            updated_at=updated_at,
        )

    def _version_issue(self, artifact: str, actual: str) -> OpsDataQualityIssue:
        return self._issue(
            artifact,
            "release_mismatch",
            f"The artifact declares release {actual!r}, not the registered release {self.release_version!r}.",
        )

    @staticmethod
    def _issue(artifact: str, code: str, detail: str) -> OpsDataQualityIssue:
        return OpsDataQualityIssue(artifact=artifact, code=code, detail=detail)

    @staticmethod
    def _has_issue(issues: list[OpsDataQualityIssue], artifact: str, code: str) -> bool:
        return any(issue.artifact == artifact and issue.code == code for issue in issues)

    def _append_line_issue(self, issues: list[OpsDataQualityIssue], code: str, line_numbers: list[int]) -> None:
        if not line_numbers:
            return
        shown = ", ".join(str(line) for line in line_numbers[:5])
        suffix = "" if len(line_numbers) <= 5 else f" and {len(line_numbers) - 5} more"
        issues.append(
            self._issue(
                DROPPED_RECORDS,
                code,
                f"Skipped {len(line_numbers)} record(s) at line(s) {shown}{suffix}.",
            )
        )
