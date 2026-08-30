from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.schemas.system import AppInfoResponse, HealthResponse

router = APIRouter(tags=["system"])

SettingsDependency = Annotated[Settings, Depends(get_settings)]


@router.get("/health", response_model=HealthResponse)
def health_check(settings: SettingsDependency) -> HealthResponse:
    return HealthResponse(
        status="ok",
        service=settings.app_name,
    )


@router.get("/info", response_model=AppInfoResponse)
def application_info(settings: SettingsDependency) -> AppInfoResponse:
    return AppInfoResponse(
        name=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
    )
