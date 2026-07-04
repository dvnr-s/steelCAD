# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

SteelCAD is a full-stack app for designing and quoting steel doors & windows: draw a
frame on a canvas, subdivide it into regions, assign types/materials/hardware, and
generate an itemized, GST-inclusive estimate exportable as a PDF.

The pricing/geometry rules are governed by a normative spec,
[`directives/design_rules_spec.md`](directives/design_rules_spec.md) — treat it as the
source of truth. When a region type or pricing rule changes, update the spec first,
then the code on both sides of the client/server contract.

**Full engineering docs live in `docs/`** — read [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
first for the complete system model (data flow, request lifecycles, design trade-offs).
[`docs/DOMAIN_MODEL.md`](docs/DOMAIN_MODEL.md), [`docs/PRICING_ENGINE.md`](docs/PRICING_ENGINE.md),
[`docs/BACKEND.md`](docs/BACKEND.md), [`docs/FRONTEND.md`](docs/FRONTEND.md), and
[`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) go deeper on each area. This file is a
condensed pointer for quick orientation — prefer those docs for anything non-trivial.

## Commands

```bash
# Start Postgres + backend (dev, hot-reload via bind mount)
docker compose up -d --build          # Postgres :5432, API :8000, docs at /docs

# Start frontend (separate terminal)
cd frontend && npm install && npm run dev   # http://localhost:5173, proxies API to :8000

# First-run: create an admin user + seed material rates
python execution/setup.py

# Backend tests (pricing engine — the only test suite)
cd backend && ./venv/Scripts/python -m pytest       # or: pytest tests/test_pricing.py -v
docker exec steelcad-backend-1 python -m pytest tests/test_pricing.py -q   # via container

# Frontend lint / build sanity
cd frontend && npm run lint
npx vite build

# Rebuild backend after requirements.txt/Dockerfile changes (--reload won't pick these up)
docker compose up -d --build backend

# Production
export POSTGRES_PASSWORD=$(openssl rand -hex 16)
export JWT_SECRET_KEY=$(openssl rand -hex 32)
docker compose -f docker-compose.prod.yml up -d --build
```

Treat a pricing change as incomplete until `test_pricing.py` passes — it cross-checks
the engine against the spec's worked examples (void-aware frames, single vs. double
sections, the door-sill exemption, rebate price-neutrality, GST, rounding).

## Architecture

Three processes: React 19 SPA (Vite + Konva canvas + Zustand) ↔ FastAPI (SQLAlchemy 2
async) ↔ PostgreSQL 16. **The frontend owns drawing/interaction and never computes a
price; the backend owns pricing/validation and never renders graphics.**

### The geometry tree (the heart of the system)

A design is a recursive binary tree: `Design → Frame → Region`, where a `Region` is
either a **leaf** (`regionType`: open/fixed/shutter/door/louver + pane/grills/hardware)
or a **branch** (a `Split` — mullion/transom — with exactly two child regions). Only
frame size and each split's ratio are stored as intent; every region's `x/y/width/height`
is *recomputed* from them via `relayout()`. This tree is stored as-is (PostgreSQL JSONB)
in `designs.tree_json` and `estimate_frames.tree_json`.

`relayout`/geometry logic is duplicated conceptually on both sides
([`frontend/src/store/editorStore.js`](frontend/src/store/editorStore.js) for canvas
rendering, backend just receives/returns JSON) — **but pricing exists only on the
backend** ([`backend/app/services/pricing.py`](backend/app/services/pricing.py)). The
frontend requests a price preview; it never adds up rupees itself.

### Four principles that explain most non-obvious design choices

1. **The tree is the single source of truth** — every price/validation result derives
   from explicit geometry nodes, never from form fields or inferred intent.
2. **Pricing/validation are deterministic, server-side, pure functions** — no I/O, no
   randomness, unit-tested (`backend/tests/test_pricing.py`).
3. **Estimates are immutable snapshots** — `rate_snapshot` and per-frame breakdowns are
   frozen at price time; changing the global rate table later does *not* alter existing
   estimates until that estimate is next touched (`_recompute` in `routers/estimates.py`).
4. **The backend re-derives, never trusts** — on every save/price call it re-validates
   and re-computes geometry/costs from the tree itself; the frontend's numbers are a
   preview only.

### Backend layout (`backend/app/`)

`router → service → model` layering. Routers (`routers/`) handle HTTP only; services
(`services/`) hold framework-free business logic (pricing, validation, auth, PDF) so
they're unit-testable without a server or DB; `models/` are SQLAlchemy ORM tables.
Key services: `pricing.py` (`price_design`/`price_estimate`, pure), `validation.py`
(`validate_design_tree`, enforces spec invariants INV-1…10 and rules V-1…18, returns
422 with error list on failure), `auth.py` (JWT + bcrypt), `pdf.py` (WeasyPrint).

### Frontend layout (`frontend/src/`)

Two Zustand stores: `authStore` (persisted, JWT-adjacent state) and `editorStore` (the
design tree, undo/redo stack capped at 50, all geometry mutations — `splitRegion`,
`setSplitPosition`, `setFrameSize`, `updateRegion`, `collapseRegion` — all routed
through `_commit`). `DesignCanvas.jsx` is a pure Konva projection of the store's tree
(feet↔pixels via a `view` transform; no Konva stage transform, so zoom/pan don't
disturb drag math). `lib/validators.js` is a client-side mirror of the server
validation rules for instant feedback. `EditorPage.jsx` serves both a library design
(`/designs/:id`) and an estimate frame (`/estimates/:id/frames/:fid`) — branches on
`frameMode`. Live price is a 600ms-debounced POST to `/price`.

### Persistence

`designs` (reusable library templates) vs. `estimate_frames` (frozen snapshots inside
an estimate — adding a library design to an estimate **copies** its tree; editing one
never affects the other). `rates` are global and admin-managed
(`require_admin` dependency). All tables use UUID PKs; geometry is JSONB with a few
denormalized columns (`outer_width`, `outer_height`, `section_size`, `gauge`) for cheap
listing without parsing JSON.

### Dev vs. prod

Dev bind-mounts `backend/` into the container (`./backend:/app` + anonymous
`/app/venv` volume so the host venv doesn't shadow installed packages) so
`uvicorn --reload` picks up edits live — **but `requirements.txt`/Dockerfile changes
need `docker compose up -d --build backend`**. Prod uses self-contained images, no
reload, `--workers 4`, and only exposes nginx on `:80` (Postgres/backend are internal
only); `JWT_SECRET_KEY`/`POSTGRES_PASSWORD` are required (no insecure defaults).

## Conventions

- **Adding/changing a region type or pricing rule touches both sides of the contract**:
  update `directives/design_rules_spec.md` first, then backend `pricing.py` +
  `validation.py`, then frontend `editorStore.js` (factories/relayout),
  `PropertiesPanel.jsx` (editors), `DesignCanvas.jsx` (rendering), `validators.js`
  (live mirror). See `docs/DEVELOPMENT.md` §7 for the fuller "how do I…" recipes.
- **New material rate**: add to `DEFAULT_RATES` in `pricing.py`, reference it via
  `_lookup_rate(...)`, re-seed or add via the admin Rates page, extend
  `test_pricing.py`.
- This repo follows a 3-layer convention described in [`AGENTS.md`](AGENTS.md)
  (directives = SOPs/spec, orchestration = decision-making, execution = deterministic
  code) — in this codebase that maps to `directives/` (spec), the app itself
  (orchestration), and `execution/` + backend services (deterministic Python).
- No per-user data scoping yet: `created_by` is recorded on designs/customers but not
  enforced as access control — any authenticated user can read/modify any of them.
  Don't assume ownership checks exist unless you add them.
