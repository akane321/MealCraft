from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.routes.auth import CurrentOperationsViewDependency
from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.repositories.operations import OperationsRepository
from app.schemas.operations import (
    OperationsOverviewResponse,
    OperationsRunCollectionResponse,
    OperationsSeriesResponse,
    OperationsServiceCheckResponse,
    OperationsServiceCollectionResponse,
    OperationsTaskCollectionResponse,
    OperationsTaskDetail,
    ServiceName,
    TaskKind,
)
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


@router.get("/overview/series", response_model=OperationsSeriesResponse)
def get_operations_series(
    current: CurrentOperationsViewDependency,
    service: OperationsServiceDependency,
) -> OperationsSeriesResponse:
    del current
    return service.series()


@router.get("/tasks", response_model=OperationsTaskCollectionResponse)
def list_tasks(
    current: CurrentOperationsViewDependency,
    service: OperationsServiceDependency,
    kind: Annotated[TaskKind | None, Query(alias="type")] = None,
    task_status: Annotated[str | None, Query(alias="status", min_length=1, max_length=40)] = None,
    since: Annotated[datetime | None, Query()] = None,
    until: Annotated[datetime | None, Query()] = None,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> OperationsTaskCollectionResponse:
    del current
    return service.tasks(kind=kind, status=task_status, since=since, until=until, offset=offset, limit=limit)


@router.get("/tasks/{kind}/{task_id}", response_model=OperationsTaskDetail)
def get_task(
    kind: TaskKind,
    task_id: int,
    current: CurrentOperationsViewDependency,
    service: OperationsServiceDependency,
) -> OperationsTaskDetail:
    del current
    detail = service.task_detail(kind, task_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return detail


@router.get("/services", response_model=OperationsServiceCollectionResponse)
def list_services(
    current: CurrentOperationsViewDependency,
    service: OperationsServiceDependency,
) -> OperationsServiceCollectionResponse:
    del current
    return service.services()


@router.post("/services/{name}/check", response_model=OperationsServiceCheckResponse)
def check_service(
    name: ServiceName,
    current: CurrentOperationsViewDependency,
    service: OperationsServiceDependency,
) -> OperationsServiceCheckResponse:
    del current
    return service.check_service(name)


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
