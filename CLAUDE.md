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
[`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) go deeper on each area;
[`docs/DEPLOY.md`](docs/DEPLOY.md) is the production runbook,
[`docs/AUTHORIZATION_GAPS.md`](docs/AUTHORIZATION_GAPS.md) documents the authorization
model, and the security/privacy posture lives in
[`docs/SECURITY_HARDENING.md`](docs/SECURITY_HARDENING.md),
[`docs/PRIVACY.md`](docs/PRIVACY.md), and
[`docs/SECRET_SAFETY_AUDIT.md`](docs/SECRET_SAFETY_AUDIT.md). This file is a condensed
pointer for quick orientation — prefer those docs for anything non-trivial.

## Commands

```bash
# Start Postgres + backend (dev, hot-reload via bind mount)
docker compose up -d --build          # Postgres :5432, API :8000, docs at /docs

# Start frontend (separate terminal)
cd frontend && npm install && npm run dev   # http://localhost:5173, proxies API to :8000

# First-run: create an admin user + seed material rates
python execution/setup.py

# Database migrations (Alembic, backend/migrations/versions/)
docker exec steelcad-backend-1 alembic upgrade head    # dev also auto-creates via create_all
docker exec steelcad-backend-1 alembic current

# Backend tests — unit suites (pricing/validation/diagram) run standalone;
# the API integration suite (tests/test_api.py) needs TEST_DATABASE_URL, else it skips
cd backend && ./venv/Scripts/python -m pytest -q
docker exec steelcad-db-1 psql -U steelcad -c "CREATE DATABASE steelcad_test"   # once
docker exec -e TEST_DATABASE_URL=postgresql+asyncpg://steelcad:steelcad@db:5432/steelcad_test \
  steelcad-backend-1 python -m pytest -q              # full suite (98 tests) in container

# Frontend lint / tests / build sanity
cd frontend && npm run lint
npx vitest run
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
422 with error list on failure), `auth.py` (JWT + bcrypt), `pdf.py` (WeasyPrint),
`access.py` (row-level write/delete rules — the single authorization seam),
`audit.py` (append-only activity log), `diagram.py` (server-side SVG schematic of a
tree, embedded per-frame in the quote PDF), `bom.py` (aggregates pricing line items
into a materials summary for the `/estimates/{id}/bom.csv` export), `ratelimit.py`
(slowapi limits on auth/price endpoints).

Routers beyond the core CRUD: `users.py` (invite-only user management), `settings.py`
(singleton `company_settings` — branding, GSTIN, bank details, default terms, GST %,
currency), `dashboard.py` (pipeline/monthly metrics), `trash.py` (list/restore
soft-deleted records), `audit.py` (activity feed).

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

Pages: `HomePage` (dashboard + global estimate search), `CustomersPage`/`CustomerDetailPage`,
`DashboardPage` (design library with SVG thumbnails), `EstimateBuilderPage`,
`EditorPage`, and role-gated admin pages (`RatesPage`, `UsersPage`, `SettingsPage`,
`ActivityPage`, `TrashPage` — see `RoleRoute` in `App.jsx`). Shared UI: `ConfirmModal`
via `useConfirm()` (never `window.confirm`), `ErrorBoundary`, `canvasDraw.jsx` (static
tree renderer shared by thumbnails and previews). Frontend tests are Vitest
(`*.test.js(x)` beside sources).

### Persistence

`designs` (reusable library templates) vs. `estimate_frames` (frozen snapshots inside
an estimate — adding a library design to an estimate **copies** its tree; editing one
never affects the other). `rates` are global, admin/owner-managed, with an append-only
`rate_history`. All tables use UUID PKs; geometry is JSONB with a few denormalized
columns (`outer_width`, `outer_height`, `section_size`, `gauge`) for cheap listing
without parsing JSON.

**Estimate lifecycle**: status flows `draft → sent → accepted | rejected` via
`PATCH /estimates/{id}/status` (plus derived `expired` for sent quotes past
`valid_until`, and `superseded` for old revisions). Non-`draft` estimates are locked
(`assert_editable`); "revise" clones as rev N+1 and supersedes the parent, "duplicate"
copies to a fresh draft. Designs/customers/estimates are **soft-deleted**
(`deleted_at`) and restorable from the Trash page. Schema evolves via Alembic
(`backend/migrations/versions/`, currently 0001–0013); dev startup still runs
`create_all` as a convenience. **That convenience is also a trap — see the DB-parity
warning under "Dev vs. prod": dev schemas are built by `create_all`, so migrations are
only ever exercised for real in production.**

### Dev vs. prod

Dev bind-mounts `backend/` into the container (`./backend:/app` + anonymous
`/app/venv` volume so the host venv doesn't shadow installed packages) so
`uvicorn --reload` picks up edits live — **but `requirements.txt`/Dockerfile changes
need `docker compose up -d --build backend`**. Prod uses self-contained images, no
reload, `--workers 4`, and only exposes nginx on `:80` (Postgres/backend are internal
only); `JWT_SECRET_KEY`/`POSTGRES_PASSWORD` are required (no insecure defaults).

**⚠️ Dev and prod build the schema differently — this is a real, recurring source of
production-only failures.** Dev startup runs SQLAlchemy `create_all`, which materializes
whatever the current ORM models declare and **silently skips the Alembic migrations**.
Production does *not* run `create_all`; its schema is only ever what the migrations built.
Consequences to keep in mind on every schema change:

- A column/constraint added to a model but **not** to a migration works in dev and breaks
  in prod. Adding a migration is mandatory, not optional — the model change alone is a bug.
- The dev DB has drifted from the migration history before (its physical schema didn't
  match `alembic_version`). So a migration that `DROP`s or renames an old constraint/column
  can fail in dev even when it's correct, and vice-versa. **Before writing a
  drop/rename/alter migration, verify the object actually exists in the target DB**
  (`docker exec steelcad-db-1 psql -U steelcad -d steelcad -c "\d+ <table>"`) and prefer
  `IF EXISTS` / `IF NOT EXISTS` guards (see migration 0010's `DROP CONSTRAINT IF EXISTS`).
- **Test migrations against a copy of the production schema, not just a fresh dev DB** — a
  fresh dev DB is built by `create_all` and never exercises the migration you just wrote.
- WeasyPrint has no native libs on the Windows host, so PDF-rendering tests must run in the
  container (`docker exec … steelcad-backend-1 python -m pytest -q`), not on the host.

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
- **Authorization** goes through one seam, `backend/app/services/access.py`: reads are
  shared org-wide; edits require creator or admin/owner (`assert_can_write`); deletes
  of designs/customers/estimates require admin/owner (`require_role`); non-draft
  estimates are locked (`assert_editable`). Roles are `admin` / `owner` / `sales`
  (invite-only user creation via `/users`). Route any new mutation through this seam —
  see `docs/AUTHORIZATION_GAPS.md` for the model.
- **Security is a standing requirement, not a phase.** This app is being hardened for a
  real deployment ([`docs/SECURITY_HARDENING.md`](docs/SECURITY_HARDENING.md) is the
  running record; [`docs/PRIVACY.md`](docs/PRIVACY.md) covers PII). Hold the line on the
  invariants already established — don't regress them:
  - **The backend re-derives and never trusts the client.** Any new geometry/pricing input
    is re-validated server-side (`validation.py`, invariants INV-* / rules V-*); the
    frontend's numbers are a preview only. New user-controlled fields get length caps and
    type validation in the Pydantic schema.
  - **Anything user-controlled that reaches a PDF must stay escaped.** Templates render via
    the autoescaping Jinja env in `services/pdf.py`, and WeasyPrint uses the `data:`-only
    URL fetcher — do not bypass either (it reopens HTML-injection / SSRF / local-file read).
  - **Auth tokens carry a credential watermark** (`password_changed_at` → `pwd` claim). Any
    new credential-changing path must call `mark_password_changed(user)` so old tokens are
    revoked.
  - **Rate-limit new sensitive endpoints** via the shared `limiter`, and never key limiting
    on the socket peer in prod (it's always nginx — see `services/ratelimit.py`).
  - **No secrets in code, no insecure prod defaults.** Prod refuses to boot on a dev/short
    JWT secret or default DB creds (`config.validate_production_secrets`); keep it that way.
  When a change has a security dimension, note it in `docs/SECURITY_HARDENING.md`.
- **Keep docs in lockstep with the change, and surface decisions instead of guessing.**
  This is a documentation-first repo: the spec and `docs/` are treated as source of truth,
  so a change isn't done until the docs that describe it are updated in the same pass —
  `directives/design_rules_spec.md` for any rule/geometry change, the relevant `docs/*.md`
  for behavior, `docs/DEPLOY.md` for anything ops/config (new env vars, migration steps),
  and this file when a convention or high-level structure shifts. Prune or fix stale lines
  you pass through (e.g. an out-of-date migration count) rather than leaving contradictions.
  And when a task is ambiguous or a decision is genuinely the user's to make — where to put
  something, which of two viable approaches, an assumption that changes the outcome —
  **ask a focused question before acting** rather than picking silently and reworking later.
  Pick the obvious default only when there is one; flag the assumption when you do.
