from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "MealCraft"
    app_version: str = "0.1.0"
    environment: str = "development"
    backend_port: int = 8000
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
    agent_max_history_messages: int = 20
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-5.4-mini"
    auth_cookie_name: str = Field(default="mealcraft_session", min_length=1, max_length=80)
    auth_csrf_cookie_name: str = Field(default="mealcraft_csrf", min_length=1, max_length=80)
    auth_cookie_secure: bool | None = None
    auth_session_ttl_hours: int = Field(default=168, ge=1, le=720)
    auth_last_seen_interval_seconds: int = Field(default=300, ge=0, le=3600)
    auth_login_max_failures: int = Field(default=5, ge=1, le=20)
    auth_login_lock_minutes: int = Field(default=15, ge=1, le=1440)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def effective_auth_cookie_secure(self) -> bool:
        if self.auth_cookie_secure is not None:
            return self.auth_cookie_secure
        return self.environment.casefold() not in {"development", "test"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
