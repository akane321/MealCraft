from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.schemas.system import AppInfoResponse, HealthResponse

router = APIRouter(tags=["system"])

SettingsDependency = Annotated[Settings, Depends(get_settings)]
DatabaseDependency = Annotated[Session, Depends(get_db_session)]


@router.get("/health", response_model=HealthResponse)
def health_check(settings: SettingsDependency, database: DatabaseDependency) -> HealthResponse:
    try:
        database.execute(text("SELECT 1"))
    except SQLAlchemyError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection failed",
        ) from error

    return HealthResponse(
        status="ok",
        service=settings.app_name,
        database="connected",
    )


@router.get("/info", response_model=AppInfoResponse)
def application_info(settings: SettingsDependency) -> AppInfoResponse:
    return AppInfoResponse(
        name=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
    )
