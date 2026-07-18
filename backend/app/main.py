"""
SteelCAD API — FastAPI application entry point.
"""
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import get_settings
from app.services.ratelimit import limiter
from app.database import engine, Base
from app.logging_config import configure_logging, get_logger
from app.models import User, Design, Customer, Estimate, EstimateFrame, Rate  # noqa: F401
from app.models.company import CompanySettings  # noqa: F401
from app.models.audit import AuditLog  # noqa: F401
from app.models.rate import RateHistory  # noqa: F401
from app.routers import (
    auth, designs, estimates, rates, customers, users,
    settings as settings_router, audit as audit_router, trash as trash_router,
    dashboard as dashboard_router,
)

configure_logging()
logger = get_logger("steelcad")
settings = get_settings()

# ─── Rate limiter is the shared instance from app.services.ratelimit ──


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Validate secrets, create tables on startup. Use Alembic in production."""
    settings.validate_production_secrets()
    logger.info("SteelCAD API starting up (env=%s)", settings.APP_ENV)
    if not settings.is_production:
        # Dev convenience: auto-create tables. Production uses `alembic upgrade head`.
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    logger.info("Startup complete — API ready")
    yield
    await engine.dispose()
    logger.info("Shutdown complete")


app = FastAPI(
    title="SteelCAD API",
    description=(
        "Steel door/window design and quoting API. "
        "Create designs on a canvas, generate itemized estimates, and export PDFs."
    ),
    version="1.0.0",
    lifespan=lifespan,
    # Interactive API docs are a dev convenience only — don't serve the
    # OpenAPI schema or docs UIs from a production deployment.
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
)

# ─── Rate limiter error handler ────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ─── CORS (origins from env var) ───────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Security headers ──────────────────────────────────────────────
def apply_security_headers(response) -> None:
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if settings.is_production:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'"


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    apply_security_headers(response)
    return response


# ─── Request logging with request-ID ──────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = str(uuid.uuid4())[:8]
    request.state.request_id = request_id
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.exception(
            "[%s] %s %s — unhandled error after %.1fms",
            request_id, request.method, request.url.path, elapsed_ms,
        )
        raise
    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "[%s] %s %s → %d (%.1fms)",
        request_id, request.method, request.url.path, response.status_code, elapsed_ms,
    )
    response.headers["X-Request-ID"] = request_id
    return response


# ─── Global error handler ──────────────────────────────────────────
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    # This handler runs on Starlette's outermost middleware, so the header/
    # logging middlewares never see its response — set the correlation ID and
    # security headers here. The exception itself (stack trace, driver errors)
    # goes to the server log only; the client gets a generic message plus the
    # request ID to quote when reporting the problem.
    request_id = getattr(request.state, "request_id", None) or str(uuid.uuid4())[:8]
    logger.exception(
        "[%s] Unhandled exception on %s %s", request_id, request.method, request.url.path
    )
    response = JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "An internal server error occurred. Please try again.",
            "request_id": request_id,
        },
    )
    response.headers["X-Request-ID"] = request_id
    apply_security_headers(response)
    return response


# ─── Routers ───────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(designs.router)
app.include_router(customers.router)
app.include_router(estimates.router)
app.include_router(rates.router)
app.include_router(settings_router.router)
app.include_router(audit_router.router)
app.include_router(trash_router.router)
app.include_router(dashboard_router.router)


# ─── Health / readiness ────────────────────────────────────────────
@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "service": "steelcad-api", "env": settings.APP_ENV}


@app.get("/ready", tags=["Health"])
async def readiness(request: Request):
    """Readiness check — verifies the database is reachable."""
    from sqlalchemy import text
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception as exc:
        logger.error("Readiness check failed: %s", exc)
        # Detail stays in the server log only — the raw exception can embed the
        # DB DSN (host, user, password), which must never reach a client.
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "not_ready", "detail": "Database unreachable"},
        )
