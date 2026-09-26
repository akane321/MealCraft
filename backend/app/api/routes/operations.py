from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.agent.parser import AgentConfigurationError
from app.api.routes.agent import create_constraint_parser
from app.api.routes.auth import CurrentOperationsViewDependency
from app.core.config import Settings, get_settings
from app.core.runtime_config import REGISTRY
from app.db.session import get_db_session
from app.repositories.operations import OperationsRepository
from app.schemas.operations import (
    ExperimentCollection,
    ExperimentRequest,
    ExperimentRun,
    OperationsOverviewResponse,
    OperationsReplay,
    OperationsReplayCollection,
    OperationsRunCollectionResponse,
    OperationsSeriesResponse,
    OperationsServiceCheckResponse,
    OperationsServiceCollectionResponse,
    OperationsTaskCollectionResponse,
    OperationsTaskDetail,
    OpsDeleted,
    OpsUserCollection,
    OpsUserDetail,
    OpsUserUpdate,
    ReplayAgentOverrides,
    ReplayPlanningOverrides,
    RuntimeSettingChange,
    RuntimeSettingCollection,
    RuntimeSettingHistory,
    ServiceName,
    TaskKind,
)
from app.schemas.platform import OperationStatus
from app.services.operations import OperationsService
from app.services.ops_replay import ReplayNotFoundError, ReplayService, ReplayUnavailableError
from app.services.ops_settings import SettingsService
from app.services.ops_users import OpsUserConflictError, OpsUserNotFoundError, UsersService

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


# --- Slice 2 (ADR-0047): Debugging, Experiments & configuration, Users. ---


@router.post("/replay/agent/{run_id}", response_model=OperationsReplay)
def replay_agent_turn(
    run_id: int,
    current: CurrentOperationsViewDependency,
    database: DatabaseDependency,
    settings: SettingsDependency,
    overrides: ReplayAgentOverrides | None = None,
) -> OperationsReplay:
    overrides = overrides or ReplayAgentOverrides()
    try:
        parser = create_constraint_parser(settings, database, provider=overrides.parser)
        return ReplayService(database, actor_user_id=current.user.id).replay_agent(run_id, overrides, parser)
    except ReplayNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found") from error
    except (ReplayUnavailableError, AgentConfigurationError) as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.post("/replay/planning/{run_id}", response_model=OperationsReplay)
def replay_planning_run(
    run_id: int,
    current: CurrentOperationsViewDependency,
    database: DatabaseDependency,
    overrides: ReplayPlanningOverrides | None = None,
) -> OperationsReplay:
    try:
        return ReplayService(database, actor_user_id=current.user.id).replay_planning(
            run_id, overrides or ReplayPlanningOverrides()
        )
    except ReplayNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found") from error
    except ReplayUnavailableError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.get("/replays", response_model=OperationsReplayCollection)
def list_replays(
    current: CurrentOperationsViewDependency,
    database: DatabaseDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> OperationsReplayCollection:
    return ReplayService(database, actor_user_id=current.user.id).list(limit)


@router.get("/replays/{replay_id}", response_model=OperationsReplay)
def get_replay(
    replay_id: int, current: CurrentOperationsViewDependency, database: DatabaseDependency
) -> OperationsReplay:
    replay = ReplayService(database, actor_user_id=current.user.id).get(replay_id)
    if replay is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Replay not found")
    return replay


@router.get("/config", response_model=RuntimeSettingCollection)
def list_runtime_settings(
    current: CurrentOperationsViewDependency, database: DatabaseDependency, settings: SettingsDependency
) -> RuntimeSettingCollection:
    del current
    return SettingsService(database, settings).list()


@router.get("/config/history", response_model=RuntimeSettingHistory)
def runtime_setting_history(
    current: CurrentOperationsViewDependency,
    database: DatabaseDependency,
    settings: SettingsDependency,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> RuntimeSettingHistory:
    del current
    return SettingsService(database, settings).history(limit)


@router.put("/config/{key}", response_model=RuntimeSettingCollection)
def change_runtime_setting(
    key: str,
    change: RuntimeSettingChange,
    current: CurrentOperationsViewDependency,
    database: DatabaseDependency,
    settings: SettingsDependency,
) -> RuntimeSettingCollection:
    if key not in REGISTRY:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="There is no such setting")
    try:
        return SettingsService(database, settings).change(key, change.value, actor_user_id=current.user.id)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error


@router.get("/experiments", response_model=ExperimentCollection)
def list_experiments(
    current: CurrentOperationsViewDependency,
    database: DatabaseDependency,
    settings: SettingsDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> ExperimentCollection:
    del current
    return SettingsService(database, settings).experiments(limit)


@router.post("/experiments", response_model=ExperimentRun)
def run_experiment(
    payload: ExperimentRequest,
    current: CurrentOperationsViewDependency,
    database: DatabaseDependency,
    settings: SettingsDependency,
) -> ExperimentRun:
    try:
        return SettingsService(database, settings).run_experiment(payload, actor_user_id=current.user.id)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error


def _users(current, database: Session) -> UsersService:
    return UsersService(database, actor_user_id=current.user.id)


@router.get("/users", response_model=OpsUserCollection)
def list_users(
    current: CurrentOperationsViewDependency,
    database: DatabaseDependency,
    q: Annotated[str | None, Query(max_length=120)] = None,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> OpsUserCollection:
    return _users(current, database).list(query=q, offset=offset, limit=limit)


@router.get("/users/{user_id}", response_model=OpsUserDetail)
def get_user(user_id: int, current: CurrentOperationsViewDependency, database: DatabaseDependency) -> OpsUserDetail:
    try:
        return _users(current, database).get(user_id)
    except OpsUserNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found") from error


@router.patch("/users/{user_id}", response_model=OpsUserDetail)
def update_user(
    user_id: int, change: OpsUserUpdate, current: CurrentOperationsViewDependency, database: DatabaseDependency
) -> OpsUserDetail:
    try:
        return _users(current, database).update(user_id, change)
    except OpsUserNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found") from error
    except OpsUserConflictError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.delete("/users/{user_id}/conversations", response_model=OpsDeleted)
def delete_user_conversations(
    user_id: int, current: CurrentOperationsViewDependency, database: DatabaseDependency
) -> OpsDeleted:
    try:
        return OpsDeleted(deleted=_users(current, database).delete_conversations(user_id))
    except OpsUserNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found") from error


@router.delete("/users/{user_id}/plans", response_model=OpsDeleted)
def delete_user_plans(
    user_id: int, current: CurrentOperationsViewDependency, database: DatabaseDependency
) -> OpsDeleted:
    try:
        return OpsDeleted(deleted=_users(current, database).delete_plans(user_id))
    except OpsUserNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found") from error


@router.delete("/users/{user_id}", response_model=OpsDeleted)
def delete_user(user_id: int, current: CurrentOperationsViewDependency, database: DatabaseDependency) -> OpsDeleted:
    try:
        _users(current, database).delete(user_id)
    except OpsUserNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found") from error
    except OpsUserConflictError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return OpsDeleted(deleted=1)
