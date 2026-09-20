from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.routes.auth import CurrentOperationsViewDependency
from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.repositories.operations import OperationsRepository
from app.schemas.operations import OperationsOverviewResponse, OperationsRunCollectionResponse
from app.schemas.platform import OperationStatus
from app.services.operations import OperationsService

router = APIRouter(prefix="/ops", tags=["operations"])

DatabaseDependency = Annotated[Session, Depends(get_db_session)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]


def get_operations_service(
    database: DatabaseDependency,
    settings: SettingsDependency,
) -> OperationsService:
    return OperationsService(
        repository=OperationsRepository(database),
        settings=settings,
    )


OperationsServiceDependency = Annotated[OperationsService, Depends(get_operations_service)]


@router.get("/overview", response_model=OperationsOverviewResponse)
def get_operations_overview(
    current: CurrentOperationsViewDependency,
    service: OperationsServiceDependency,
) -> OperationsOverviewResponse:
    del current
    return service.overview()


@router.get("/runs", response_model=OperationsRunCollectionResponse)
def list_operation_runs(
    current: CurrentOperationsViewDependency,
    service: OperationsServiceDependency,
    run_type: Annotated[str | None, Query(alias="type", min_length=1, max_length=60)] = None,
    run_status: Annotated[OperationStatus | None, Query(alias="status")] = None,
    since: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> OperationsRunCollectionResponse:
    del current
    return service.list_runs(
        run_type=run_type,
        status=run_status,
        since=since,
        limit=limit,
    )
