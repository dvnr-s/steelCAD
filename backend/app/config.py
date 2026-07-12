"""
Application configuration.
Reads from environment variables with fallbacks for local development.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_JWT_SECRET = "dev-secret-key-change-in-production"


class Settings(BaseSettings):
    """Application settings — populated from environment variables or .env file."""

    # Environment: "development" or "production"
    APP_ENV: str = "development"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://steelcad:steelcad@localhost:5432/steelcad"

    # JWT Auth
    JWT_SECRET_KEY: str = _DEV_JWT_SECRET
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS — comma-separated list of allowed origins.
    # Defaults to localhost dev origins; override in production.
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000,http://localhost,http://127.0.0.1:5173,http://127.0.0.1:3000"

    # Logging
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        env_file="../.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() == "production"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    def validate_production_secrets(self) -> None:
        """Raise at startup if production is running with insecure defaults."""
        if self.is_production and self.JWT_SECRET_KEY == _DEV_JWT_SECRET:
            raise RuntimeError(
                "FATAL: APP_ENV=production but JWT_SECRET_KEY is the dev default. "
                "Generate a secret with: openssl rand -hex 32"
            )


@lru_cache()
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()
