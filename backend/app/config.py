"""
Application configuration.
Reads from environment variables with fallbacks for local development.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_JWT_SECRET = "dev-secret-key-change-in-production"
_DEV_DB_CREDENTIALS = "steelcad:steelcad@"
_DEV_CORS_ORIGINS = "http://localhost:5173,http://localhost:3000,http://localhost,http://127.0.0.1:5173,http://127.0.0.1:3000"


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

    # Require TLS on the database connection (set true when the DB is reached
    # over any network you don't control, e.g. a managed Postgres service).
    DATABASE_SSL: bool = False

    # CORS — comma-separated list of allowed origins.
    # Defaults to localhost dev origins; override in production. In production
    # behind the nginx reverse proxy the SPA is same-origin, so this can be
    # empty ("") — set it only when the frontend lives on a different domain.
    CORS_ORIGINS: str = _DEV_CORS_ORIGINS

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
        # A production instance that never set CORS_ORIGINS must not fall back
        # to the permissive localhost dev list — same-origin only instead.
        if self.is_production and self.CORS_ORIGINS == _DEV_CORS_ORIGINS:
            return []
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    def validate_production_secrets(self) -> None:
        """Raise at startup if production is running with insecure defaults.

        Every check here is fatal on purpose: a misconfigured secret must stop
        the deploy, not launch a weakened instance that looks healthy.
        """
        if not self.is_production:
            return
        errors: list[str] = []
        if self.JWT_SECRET_KEY == _DEV_JWT_SECRET:
            errors.append(
                "JWT_SECRET_KEY is the dev default. "
                "Generate a secret with: openssl rand -hex 32"
            )
        if not self.JWT_SECRET_KEY or len(self.JWT_SECRET_KEY) < 32:
            errors.append(
                "JWT_SECRET_KEY is missing or shorter than 32 characters. "
                "Generate one with: openssl rand -hex 32"
            )
        if _DEV_DB_CREDENTIALS in self.DATABASE_URL:
            errors.append(
                "DATABASE_URL uses the default steelcad:steelcad credentials. "
                "Set POSTGRES_PASSWORD to a strong value (openssl rand -hex 16)."
            )
        if "localhost" in self.DATABASE_URL or "127.0.0.1" in self.DATABASE_URL:
            errors.append(
                "DATABASE_URL points at localhost — production must set an "
                "explicit DATABASE_URL for its real database host."
            )
        if "*" in self.cors_origins_list:
            errors.append(
                "CORS_ORIGINS contains a wildcard (*). List the exact frontend "
                "origin(s) instead, e.g. https://steelcad.example.com"
            )
        if errors:
            raise RuntimeError(
                "FATAL: refusing to start with insecure production configuration:\n  - "
                + "\n  - ".join(errors)
            )


@lru_cache()
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()
