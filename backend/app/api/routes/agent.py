from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.ingredient_matcher import IngredientMatcher, catalog_aliases, catalog_embedder, catalog_vectors
from app.agent.parser import (
    AgentConfigurationError,
    ConstraintParser,
    ConstraintVocabulary,
    OpenAIConstraintParser,
    RuleBasedConstraintParser,
    catalog_groups,
)
from app.api.routes.auth import CurrentHouseholdCreatePlanCsrfDependency, CurrentHouseholdViewDependency
from app.api.routes.meal_plans import build_meal_plan_service, build_replanning_service
from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.models.recipe import Ingredient
from app.orchestration.run_lifecycle import AgentRunLifecycleError, AgentRunNotFoundError
from app.planning.weekly_planner import WeeklyPlanSelectionError
from app.repositories.agent import AgentSessionRepository
from app.repositories.agent_runs import AgentRunRepository
from app.repositories.household import HouseholdProfileRepository
from app.schemas.agent import (
    AgentConfirmationResponse,
    AgentInteractionInput,
    AgentMessageInput,
    AgentReplanConfirmationResponse,
    AgentRunCollectionResponse,
    AgentRunResponse,
    AgentSessionCollectionResponse,
    AgentSessionResponse,
)
from app.services.agent import (
    AgentSessionNotFoundError,
    AgentSessionNotReadyError,
    AgentSessionService,
    profile_constraints,
)
from app.services.replanning import (
    MealPlanReplanConflictError,
    MealPlanReplanNotFoundError,
)

router = APIRouter(prefix="/agent/sessions", tags=["planning agent"])


def create_constraint_parser(settings: Settings, database: Session | None = None) -> ConstraintParser:
    if settings.agent_parser_provider == "fixture":
        return RuleBasedConstraintParser()
    if settings.openai_api_key is None:
        raise AgentConfigurationError(
            "AGENT_PARSER_PROVIDER=openai requires OPENAI_API_KEY. Use fixture mode for a key-free demo."
        )
    api_key = settings.openai_api_key.get_secret_value()
    # The model writes constraints in the catalog's own ingredient ids, the only words the planner matches;
    # a word outside them is asked about, with the closest ids offered (ingredient_matcher).
    vocabulary = None
    if database is not None:
        names = dict(database.execute(select(Ingredient.normalized_name, Ingredient.display_name)).tuples().all())
        vocabulary = ConstraintVocabulary(
            ingredients=frozenset(names),
            groups=catalog_groups(),
            matcher=IngredientMatcher(
                names, vectors=catalog_vectors(), embed=catalog_embedder(api_key), aliases=catalog_aliases()
            ),
        )
    return OpenAIConstraintParser(
        api_key=api_key,
        model=settings.openai_model,
        vocabulary=vocabulary,
    )


def get_agent_service(
    database: Annotated[Session, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    current: CurrentHouseholdViewDependency,
) -> AgentSessionService:
    try:
        parser = create_constraint_parser(settings, database)
    except AgentConfigurationError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
    household_id = current.active_membership.household_id
    profile = HouseholdProfileRepository(database, household_id=household_id).get_current()
    return AgentSessionService(
        repository=AgentSessionRepository(database, household_id=household_id),
        run_repository=AgentRunRepository(database, household_id=household_id),
        parser=parser,
        meal_plan_service=build_meal_plan_service(database, household_id, current.user.id),
        replanning_service=build_replanning_service(database, household_id),
        actor_user_id=current.user.id,
        household_id=household_id,
        max_history_messages=settings.agent_max_history_messages,
        starting_constraints=(
            profile_constraints(HouseholdProfileRepository.current_version(profile)) if profile else None
        ),
    )


AgentServiceDependency = Annotated[AgentSessionService, Depends(get_agent_service)]
IdempotencyKey = Annotated[str | None, Header(alias="Idempotency-Key")]


@router.post("", response_model=AgentSessionResponse, status_code=status.HTTP_201_CREATED)
def create_agent_session(
    payload: AgentMessageInput,
    service: AgentServiceDependency,
    _current: CurrentHouseholdCreatePlanCsrfDependency,
) -> AgentSessionResponse:
    try:
        return service.create(payload.message)
    except AgentRunLifecycleError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.get("", response_model=AgentSessionCollectionResponse)
def list_agent_sessions(
    service: AgentServiceDependency,
    limit: Annotated[int, Query(ge=1, le=20)] = 5,
) -> AgentSessionCollectionResponse:
    return service.list_recent(limit=limit)


@router.get("/{session_id}", response_model=AgentSessionResponse)
def get_agent_session(session_id: int, service: AgentServiceDependency) -> AgentSessionResponse:
    agent_session = service.get(session_id)
    if agent_session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent session not found")
    return agent_session


@router.post("/{session_id}/messages", response_model=AgentSessionResponse)
def reply_to_agent_session(
    session_id: int,
    payload: AgentMessageInput,
    service: AgentServiceDependency,
    _current: CurrentHouseholdCreatePlanCsrfDependency,
    idempotency_key: IdempotencyKey = None,
) -> AgentSessionResponse:
    try:
        return service.reply(session_id, payload.message, idempotency_key=idempotency_key)
    except AgentSessionNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent session not found") from error
    except AgentSessionNotReadyError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except AgentRunLifecycleError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.post("/{session_id}/interactions", response_model=AgentSessionResponse)
def answer_agent_interaction(
    session_id: int,
    payload: AgentInteractionInput,
    service: AgentServiceDependency,
    _current: CurrentHouseholdCreatePlanCsrfDependency,
    idempotency_key: IdempotencyKey = None,
) -> AgentSessionResponse:
    try:
        return service.answer_interaction(session_id, payload, idempotency_key=idempotency_key)
    except AgentSessionNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent session not found") from error
    except AgentSessionNotReadyError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except AgentRunLifecycleError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.post("/{session_id}/confirm", response_model=AgentConfirmationResponse)
def confirm_agent_session(
    session_id: int,
    service: AgentServiceDependency,
    _current: CurrentHouseholdCreatePlanCsrfDependency,
    idempotency_key: IdempotencyKey = None,
) -> AgentConfirmationResponse:
    try:
        return service.confirm(session_id, idempotency_key=idempotency_key)
    except AgentSessionNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent session not found") from error
    except AgentSessionNotReadyError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except WeeklyPlanSelectionError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error
    except AgentRunLifecycleError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.post("/{session_id}/replan/confirm", response_model=AgentReplanConfirmationResponse)
def confirm_agent_replan(
    session_id: int,
    service: AgentServiceDependency,
    _current: CurrentHouseholdCreatePlanCsrfDependency,
    idempotency_key: IdempotencyKey = None,
) -> AgentReplanConfirmationResponse:
    try:
        return service.confirm_replan(session_id, idempotency_key=idempotency_key)
    except AgentSessionNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent session not found") from error
    except MealPlanReplanNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except (AgentSessionNotReadyError, MealPlanReplanConflictError) as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except AgentRunLifecycleError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.post("/{session_id}/replan/discard", response_model=AgentSessionResponse)
def discard_agent_replan(
    session_id: int,
    service: AgentServiceDependency,
    _current: CurrentHouseholdCreatePlanCsrfDependency,
    idempotency_key: IdempotencyKey = None,
) -> AgentSessionResponse:
    try:
        return service.discard_replan(session_id, idempotency_key=idempotency_key)
    except AgentSessionNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent session not found") from error
    except AgentSessionNotReadyError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except AgentRunLifecycleError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.get("/{session_id}/runs", response_model=AgentRunCollectionResponse)
def list_agent_runs(
    session_id: int,
    service: AgentServiceDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AgentRunCollectionResponse:
    try:
        return service.list_runs(session_id, limit=limit)
    except AgentSessionNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent session not found") from error


@router.get("/{session_id}/runs/{run_id}", response_model=AgentRunResponse)
def get_agent_run(session_id: int, run_id: int, service: AgentServiceDependency) -> AgentRunResponse:
    try:
        return service.get_run(session_id, run_id)
    except AgentRunNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent run not found") from error


@router.post("/{session_id}/runs/{run_id}/cancel", response_model=AgentRunResponse)
def cancel_agent_run(
    session_id: int,
    run_id: int,
    service: AgentServiceDependency,
    _current: CurrentHouseholdCreatePlanCsrfDependency,
) -> AgentRunResponse:
    try:
        return service.cancel_run(session_id, run_id)
    except AgentRunNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent run not found") from error
    except AgentRunLifecycleError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
