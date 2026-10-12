from datetime import date

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    service: str
    database: str
    # The date the product plans from (Singapore), and the simulated now when one is set (app/core/clock.py).
    today: date
    simulated_today: str | None = None


class AppInfoResponse(BaseModel):
    name: str
    version: str
    environment: str
