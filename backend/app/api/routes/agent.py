from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.agent.parser import (
    AgentConfigurationError,
    ConstraintParser,
    OpenAIConstraintParser,
    RuleBasedConstraintParser,
)
from app.api.routes.meal_plans import get_meal_plan_service, get_replanning_service
from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.planning.weekly_planner import WeeklyPlanSelectionError
from app.repositories.agent import AgentSessionRepository
from app.schemas.agent import (
    AgentConfirmationResponse,
    AgentMessageInput,
    AgentReplanConfirmationResponse,
    AgentSessionCollectionResponse,
    AgentSessionResponse,
)
from app.services.agent import (
    AgentSessionNotFoundError,
    AgentSessionNotReadyError,
    AgentSessionService,
)
from app.services.replanning import (
    MealPlanReplanConflictError,
    MealPlanReplanNotFoundError,
)

router = APIRouter(prefix="/agent/sessions", tags=["planning agent"])


def create_constraint_parser(settings: Settings) -> ConstraintParser:
    if settings.agent_parser_provider == "fixture":
        return RuleBasedConstraintParser()
    if settings.openai_api_key is None:
        raise AgentConfigurationError(
            "AGENT_PARSER_PROVIDER=openai requires OPENAI_API_KEY. Use fixture mode for a key-free demo."
        )
    return OpenAIConstraintParser(
        api_key=settings.openai_api_key.get_secret_value(),
        model=settings.openai_model,
    )


def get_agent_service(
    database: Annotated[Session, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AgentSessionService:
    try:
        parser = create_constraint_parser(settings)
    except AgentConfigurationError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
    return AgentSessionService(
        repository=AgentSessionRepository(database),
        parser=parser,
        meal_plan_service=get_meal_plan_service(database),
        replanning_service=get_replanning_service(database),
        max_history_messages=settings.agent_max_history_messages,
    )


AgentServiceDependency = Annotated[AgentSessionService, Depends(get_agent_service)]


@router.post("", response_model=AgentSessionResponse, status_code=status.HTTP_201_CREATED)
def create_agent_session(
    payload: AgentMessageInput,
    service: AgentServiceDependency,
) -> AgentSessionResponse:
    return service.create(payload.message)


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
) -> AgentSessionResponse:
    try:
        return service.reply(session_id, payload.message)
    except AgentSessionNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent session not found") from error
    except AgentSessionNotReadyError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.post("/{session_id}/confirm", response_model=AgentConfirmationResponse)
def confirm_agent_session(
    session_id: int,
    service: AgentServiceDependency,
) -> AgentConfirmationResponse:
    try:
        return service.confirm(session_id)
    except AgentSessionNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent session not found") from error
    except AgentSessionNotReadyError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except WeeklyPlanSelectionError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error


@router.post("/{session_id}/replan/confirm", response_model=AgentReplanConfirmationResponse)
def confirm_agent_replan(
    session_id: int,
    service: AgentServiceDependency,
) -> AgentReplanConfirmationResponse:
    try:
        return service.confirm_replan(session_id)
    except AgentSessionNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent session not found") from error
    except MealPlanReplanNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except (AgentSessionNotReadyError, MealPlanReplanConflictError) as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.post("/{session_id}/replan/discard", response_model=AgentSessionResponse)
def discard_agent_replan(
    session_id: int,
    service: AgentServiceDependency,
) -> AgentSessionResponse:
    try:
        return service.discard_replan(session_id)
    except AgentSessionNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent session not found") from error
    except AgentSessionNotReadyError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
