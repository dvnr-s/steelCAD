"""
Application configuration.
Reads from environment variables with fallbacks for local development.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings — populated from environment variables or .env file."""

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://steelcad:steelcad@localhost:5432/steelcad"

    # JWT Auth
    JWT_SECRET_KEY: str = "dev-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    model_config = SettingsConfigDict(
        env_file="../.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()
