from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "MealCraft"
    app_version: str = "0.1.0"
    environment: str = "development"
    backend_port: int = 8000
    frontend_port: int = 3000
    database_url: str = "sqlite+pysqlite:///./mealcraft.db"
    cors_origins: list[str] = ["http://localhost:3000"]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
