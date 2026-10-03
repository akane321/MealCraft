from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.routes.auth import CurrentOperationsViewDependency
from app.schemas.operations_data_quality import OpsDataQualitySummary, OpsDroppedCandidateCollection
from app.services.ops_data_quality import DataQualityService

router = APIRouter(prefix="/ops", tags=["operations"])


def get_data_quality_service() -> DataQualityService:
    return DataQualityService.current()


DataQualityServiceDependency = Annotated[DataQualityService, Depends(get_data_quality_service)]


@router.get("/data-quality", response_model=OpsDataQualitySummary)
def data_quality_summary(
    current: CurrentOperationsViewDependency,
    service: DataQualityServiceDependency,
) -> OpsDataQualitySummary:
    del current
    return service.summary()


@router.get("/data-quality/dropped", response_model=OpsDroppedCandidateCollection)
def dropped_candidates(
    current: CurrentOperationsViewDependency,
    service: DataQualityServiceDependency,
    reason: Annotated[str | None, Query(min_length=1, max_length=500)] = None,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> OpsDroppedCandidateCollection:
    del current
    return service.dropped(offset=offset, limit=limit, reason=reason)
