"""
Test fixtures — async SQLAlchemy + FastAPI test client.

Integration tests require a running Postgres. Set TEST_DATABASE_URL or they will
be skipped. In CI the workflow provides a Postgres service container.

  TEST_DATABASE_URL=postgresql+asyncpg://steelcad:steelcad@localhost:5432/steelcad_test
"""
import os
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://steelcad:steelcad@localhost:5432/steelcad_test",
)


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: requires a running Postgres instance")


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    """Session-scoped engine pointing at the test DB."""
    engine = create_async_engine(TEST_DB_URL, echo=False)
    try:
        # Quick connection check — skip all integration tests if no DB available
        async with engine.connect():
            pass
    except Exception as exc:
        pytest.skip(f"Postgres not available at {TEST_DB_URL}: {exc}")
        return

    from app.database import Base
    from app.models import User, Design, Customer, Estimate, EstimateFrame, Rate  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine):
    """Function-scoped session that rolls back after each test."""
    async with test_engine.connect() as conn:
        await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)
        try:
            yield session
        finally:
            await session.close()
            await conn.rollback()


@pytest_asyncio.fixture
async def client(test_engine, db_session):
    """
    Async HTTP client against the FastAPI app, with DB overridden to use
    the test session (all mutations roll back after each test).
    """
    from app.main import app
    from app.database import get_db
    from app.services.ratelimit import limiter

    # The limiter uses a process-wide in-memory store keyed by client IP. Every
    # test shares the same IP, so login/refresh limits would trip mid-suite.
    # Disable it for integration tests (rate-limit behaviour is exercised in
    # isolation where relevant).
    limiter.enabled = False

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# ── Helper factories ───────────────────────────────────────────────

async def create_user(db_session, email: str, password: str = "password123",
                      name: str = "Test User", role: str = "sales"):
    from app.models.user import User, ROLE_ADMIN
    from app.services.auth import hash_password
    user = User(
        email=email, name=name,
        password=hash_password(password),
        role=role,
        is_admin=(role == ROLE_ADMIN),
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def seed_rates(db_session):
    """Insert the spec §9.2 default rate table (pricing needs it)."""
    from app.models.rate import Rate
    from app.services.pricing import DEFAULT_RATES
    for r in DEFAULT_RATES:
        db_session.add(Rate(**r))
    await db_session.flush()


async def login(client, email: str, password: str = "password123") -> dict:
    resp = await client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()


def auth_headers(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}
