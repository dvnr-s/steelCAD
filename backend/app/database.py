"""
Database engine, session factory, and base model.
Uses SQLAlchemy 2.0 async with asyncpg driver.
"""
import ssl

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()


def build_connect_args() -> dict:
    """asyncpg connect_args honoring DATABASE_SSL.

    When enabled, an explicit default SSLContext enforces TLS with full
    certificate and hostname verification. Shared with Alembic's env.py so
    migrations use the same transport security as the app. Leave DATABASE_SSL
    false only when the DB is reached over a trusted private network (e.g.
    the internal docker-compose network).
    """
    if not settings.DATABASE_SSL:
        return {}
    return {"ssl": ssl.create_default_context()}


engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    connect_args=build_connect_args(),
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


async def get_db():
    """
    FastAPI dependency — yields an async database session.
    Commits on success, rolls back on exception.
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
