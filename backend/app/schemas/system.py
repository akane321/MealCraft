from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    service: str
    database: str


class AppInfoResponse(BaseModel):
    name: str
    version: str
    environment: str
