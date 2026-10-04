from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "MealCraft"
    app_version: str = "0.1.0"
    environment: str = "development"
    frontend_port: int = 3000
    database_url: str = "sqlite+pysqlite:///./mealcraft.db"
    cors_origins: list[str] = ["http://localhost:3000"]
    fairprice_base_url: str = "https://www.fairprice.com.sg"
    fairprice_timeout_seconds: float = 12.0
    fairprice_cache_ttl_minutes: int = 15
    product_fixture_path: str = "data/fixtures/fairprice-products.json"
    youtube_timeout_seconds: float = 12.0
    youtube_fixture_path: str = "data/fixtures/youtube-tutorials.json"
    youtube_api_key: SecretStr | None = None
    agent_parser_provider: Literal["fixture", "openai"] = "fixture"
    # "full" is the days/meals/dish-roles product (ADR-0046).
    # "mvp" reproduces the recorded seven one-dish dinner evaluations.
    planning_capability: Literal["mvp", "full"] = "full"
    agent_max_history_messages: int = 20
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-5.4-mini"
    # A slow model must not hang the chat: past this the turn is read with the rule parser instead.
    openai_timeout_seconds: float = Field(default=15.0, gt=0, le=300)
    # How long the planner reuses the recipes it loaded; 0 loads them for every plan (tests).
    planning_pool_cache_seconds: int = 300
    auth_cookie_name: str = Field(default="mealcraft_session", min_length=1, max_length=80)
    auth_csrf_cookie_name: str = Field(default="mealcraft_csrf", min_length=1, max_length=80)
    auth_cookie_secure: bool | None = None
    auth_session_ttl_hours: int = Field(default=168, ge=1, le=720)
    auth_last_seen_interval_seconds: int = Field(default=300, ge=0, le=3600)
    auth_login_max_failures: int = Field(default=5, ge=1, le=20)
    auth_login_lock_minutes: int = Field(default=15, ge=1, le=1440)
    # ADR-0047: fixed console accounts, "email:password:Display Name;..." created or updated at start-up.
    admin_accounts: str = ""
    ops_worker_poll_seconds: float = Field(default=1.0, gt=0, le=60)
    ops_worker_lease_seconds: float = Field(default=30.0, gt=0, le=3600)
    ops_worker_heartbeat_seconds: float = Field(default=10.0, gt=0, le=1200)
    ops_worker_job_timeout_seconds: float = Field(default=900.0, gt=0, le=21600)
    ops_worker_max_attempts: int = Field(default=3, ge=1, le=20)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_worker_timing(self) -> "Settings":
        if self.ops_worker_heartbeat_seconds >= self.ops_worker_lease_seconds:
            raise ValueError("ops worker heartbeat must be shorter than its lease")
        return self

    @property
    def effective_auth_cookie_secure(self) -> bool:
        if self.auth_cookie_secure is not None:
            return self.auth_cookie_secure
        return self.environment.casefold() not in {"development", "test"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
