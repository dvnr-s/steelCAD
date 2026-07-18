"""
Database engine, session factory, and base model.
Uses SQLAlchemy 2.0 async with asyncpg driver.
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    # DATABASE_SSL=true makes asyncpg require TLS with certificate verification.
    # Leave false only when the DB is reached over a trusted private network
    # (e.g. the internal docker-compose network).
    connect_args={"ssl": True} if settings.DATABASE_SSL else {},
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
