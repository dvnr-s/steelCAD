"""
SteelCAD API — FastAPI application entry point.

Assembles all routers and middleware. On startup, creates database tables
if they don't exist (dev convenience — use Alembic migrations in production).
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import engine, Base
from app.models import User, Design, EstimateVersion, Rate  # noqa: F401 — ensure models registered
from app.routers import auth, designs, estimates, rates


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create tables on startup (dev mode). Use Alembic in production."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


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
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routers ───────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(designs.router)
app.include_router(estimates.router)
app.include_router(rates.router)


# ─── Health check ──────────────────────────────────────────────────
@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "service": "steelcad-api"}
