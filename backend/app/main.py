"""
SteelCAD API — FastAPI application entry point.

Assembles all routers and middleware. On startup, creates database tables
if they don't exist (dev convenience — use Alembic migrations in production).
"""
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.database import engine, Base
from app.logging_config import configure_logging, get_logger
from app.models import User, Design, Customer, Estimate, EstimateFrame, Rate  # noqa: F401 — ensure models registered
from app.routers import auth, designs, estimates, rates, customers, users

configure_logging()
logger = get_logger("steelcad")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create tables on startup (dev mode). Use Alembic in production."""
    logger.info("SteelCAD API starting up — initializing database schema")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Startup complete — API ready")
    yield
    await engine.dispose()
    logger.info("Shutdown complete — database engine disposed")


app = FastAPI(
    title="SteelCAD API",
    description=(
        "Steel door/window design and quoting API. "
        "Create designs on a canvas, generate itemized estimates, and export PDFs."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# ─── CORS ──────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",   # Vite dev server
        "http://localhost:3000",   # Alternative dev port
        "http://localhost",        # Nginx (production frontend container)
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Request logging ───────────────────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log each request with its method, path, status, and duration."""
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.exception(
            "%s %s — unhandled error after %.1fms",
            request.method, request.url.path, elapsed_ms,
        )
        raise
    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "%s %s → %d (%.1fms)",
        request.method, request.url.path, response.status_code, elapsed_ms,
    )
    return response


# ─── Global error handler ──────────────────────────────────────────
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Catch-all — log the traceback and return a clean 500 (no stack leak)."""
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal server error occurred. Please try again."},
    )


# ─── Routers ───────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(designs.router)
app.include_router(customers.router)
app.include_router(estimates.router)
app.include_router(rates.router)


# ─── Health check ──────────────────────────────────────────────────
@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "service": "steelcad-api"}
