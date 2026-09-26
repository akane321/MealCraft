from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

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
    DataCourse,
    DataMealType,
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
    OpsIngredient,
    OpsIngredientCollection,
    OpsIngredientUpdate,
    OpsProductMapping,
    OpsProductMappingChange,
    OpsProductMappingCollection,
    OpsRecipeCollection,
    OpsRecipeDetail,
    OpsRecipeUpdate,
    OpsRecipeWithdrawal,
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
from app.services.ops_data import DataService, OpsDataConflictError, OpsDataNotFoundError
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


# --- Data: recipes, ingredients and product mappings ---


def _data(current, database: Session) -> DataService:
    return DataService(database, actor_user_id=current.user.id)


@router.get("/data/recipes", response_model=OpsRecipeCollection)
def list_recipes(
    current: CurrentOperationsViewDependency,
    database: DatabaseDependency,
    q: Annotated[str | None, Query(max_length=120)] = None,
    course: Annotated[DataCourse | None, Query()] = None,
    meal_type: Annotated[DataMealType | None, Query()] = None,
    origin: Annotated[Literal["release", "curated"] | None, Query()] = None,
    withdrawn: Annotated[bool | None, Query()] = None,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> OpsRecipeCollection:
    return _data(current, database).recipes(
        query=q, course=course, meal_type=meal_type, origin=origin, withdrawn=withdrawn, offset=offset, limit=limit
    )


@router.get("/data/recipes/{recipe_id}", response_model=OpsRecipeDetail)
def get_recipe(
    recipe_id: int, current: CurrentOperationsViewDependency, database: DatabaseDependency
) -> OpsRecipeDetail:
    try:
        return _data(current, database).recipe(recipe_id)
    except OpsDataNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found") from error


@router.patch("/data/recipes/{recipe_id}", response_model=OpsRecipeDetail)
def update_recipe(
    recipe_id: int, change: OpsRecipeUpdate, current: CurrentOperationsViewDependency, database: DatabaseDependency
) -> OpsRecipeDetail:
    try:
        return _data(current, database).update_recipe(recipe_id, change)
    except OpsDataNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found") from error


@router.post("/data/recipes/{recipe_id}/withdraw", response_model=OpsRecipeDetail)
def withdraw_recipe(
    recipe_id: int,
    withdrawal: OpsRecipeWithdrawal,
    current: CurrentOperationsViewDependency,
    database: DatabaseDependency,
) -> OpsRecipeDetail:
    try:
        return _data(current, database).withdraw_recipe(recipe_id, withdrawal.reason)
    except OpsDataNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found") from error
    except OpsDataConflictError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.post("/data/recipes/{recipe_id}/restore", response_model=OpsRecipeDetail)
def restore_recipe(
    recipe_id: int, current: CurrentOperationsViewDependency, database: DatabaseDependency
) -> OpsRecipeDetail:
    try:
        return _data(current, database).restore_recipe(recipe_id)
    except OpsDataNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found") from error
    except OpsDataConflictError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.get("/data/ingredients", response_model=OpsIngredientCollection)
def list_ingredients(
    current: CurrentOperationsViewDependency,
    database: DatabaseDependency,
    q: Annotated[str | None, Query(max_length=120)] = None,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> OpsIngredientCollection:
    return _data(current, database).ingredients(query=q, offset=offset, limit=limit)


@router.patch("/data/ingredients/{ingredient_id}", response_model=OpsIngredient)
def update_ingredient(
    ingredient_id: int,
    change: OpsIngredientUpdate,
    current: CurrentOperationsViewDependency,
    database: DatabaseDependency,
) -> OpsIngredient:
    try:
        return _data(current, database).update_ingredient(ingredient_id, change)
    except OpsDataNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ingredient not found") from error


@router.get("/data/mappings", response_model=OpsProductMappingCollection)
def list_product_mappings(
    current: CurrentOperationsViewDependency,
    database: DatabaseDependency,
    q: Annotated[str | None, Query(max_length=120)] = None,
    # A mapping status, or "console" for the ones changed or removed here.
    mapping_status: Annotated[
        Literal["mapped", "not_purchased", "removed", "console"] | None, Query(alias="status")
    ] = None,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> OpsProductMappingCollection:
    return _data(current, database).mappings(query=q, status=mapping_status, offset=offset, limit=limit)


@router.put("/data/mappings/{ingredient}", response_model=OpsProductMapping)
def change_product_mapping(
    ingredient: str,
    change: OpsProductMappingChange,
    current: CurrentOperationsViewDependency,
    database: DatabaseDependency,
) -> OpsProductMapping:
    try:
        return _data(current, database).change_mapping(ingredient, change.product)
    except OpsDataNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ingredient not found") from error


@router.delete("/data/mappings/{ingredient}", response_model=OpsProductMapping)
def remove_product_mapping(
    ingredient: str, current: CurrentOperationsViewDependency, database: DatabaseDependency
) -> OpsProductMapping:
    try:
        return _data(current, database).remove_mapping(ingredient)
    except OpsDataNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No mapping for this ingredient") from error
