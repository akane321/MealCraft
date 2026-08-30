from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    service: str


class AppInfoResponse(BaseModel):
    name: str
    version: str
    environment: str
