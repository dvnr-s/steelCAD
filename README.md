# SteelCAD

A full-stack web app for **designing and quoting steel doors & windows**. Draw a
frame on a canvas, split it into regions, assign types (open / fixed / shutter /
door / louver), configure panes, grills, and hardware — then generate an itemized,
GST-inclusive estimate and export it as a professional PDF.

The pricing logic is driven by a deterministic domain specification in
[directives/design_rules_spec.md](directives/design_rules_spec.md), which is the
source of truth for the geometry model, validation rules, and cost formulas.

---

## Stack

| Layer | Technology |
|---|---|
| **Frontend** | React 19 + Vite, Konva (canvas), Zustand (state), Axios, react-hot-toast |
| **Backend** | FastAPI, SQLAlchemy 2 (async) + asyncpg, Pydantic v2 |
| **Database** | PostgreSQL 16 |
| **Auth** | JWT (access + refresh tokens), bcrypt password hashing |
| **PDF** | WeasyPrint (server-side HTML → PDF) |
| **Deploy** | Docker / Docker Compose |

---

## Features

- **Canvas editor** — recursive split tree, region typing, live geometry
- **Undo / redo** — full history with `Ctrl+Z` / `Ctrl+Shift+Z` (or `Ctrl+Y`)
- **Live validation** — client-side checks mirror the backend rules and flag
  issues (missing materials, hinges, invalid grills, undersized regions) before save
- **Live pricing** — debounced estimate preview while you edit
- **Itemized estimates** — frame, mullions/transoms, per-region panes, grills,
  hardware → subtotal, discount, GST, grand total, advance
- **PDF export** — download a styled quotation
- **Rate management** — admin-only page to update material rates (existing
  estimates are immutable snapshots and never change)

---

## Project layout

```
SteelCAD/
├── backend/            FastAPI app (models, schemas, routers, services)
├── frontend/           React + Vite app (pages, components, stores)
├── directives/         Domain spec + implementation plan (source of truth)
├── execution/          Operational scripts (first-run setup)
├── docker-compose.yml        Dev stack (Postgres + API, hot-reload)
└── docker-compose.prod.yml   Production stack (Postgres + API + nginx frontend)
```

---

## Quick start (local development)

**Prerequisites:** Docker Desktop, Node 20+, Python 3.12+.

### 1. Start Postgres + backend (Docker)

```bash
docker compose up -d --build       # Postgres on :5432, API on :8000
```

The API auto-creates tables on startup. Browse the OpenAPI docs at
http://localhost:8000/docs.

### 2. Start the frontend (Vite dev server)

```bash
cd frontend
npm install
npm run dev                        # http://localhost:5173 (proxies API to :8000)
```

### 3. Create an admin + seed rates

```bash
python execution/setup.py          # registers an account, promotes to admin, seeds rates
```

Then log in at http://localhost:5173. If rate seeding was skipped, log in and
visit **/rates** once you're an admin.

---

## Production deployment

The production compose file builds self-contained images and serves the frontend
via nginx (which also reverse-proxies the API), so only port 80 is exposed.

```bash
# Required secrets — do NOT use the dev defaults in production:
export POSTGRES_PASSWORD=$(openssl rand -hex 16)
export JWT_SECRET_KEY=$(openssl rand -hex 32)

docker compose -f docker-compose.prod.yml up -d --build
```

The app is then available at http://localhost (port 80). Postgres and the backend
are not published to the host — they're reachable only on the internal compose
network. Run `python execution/setup.py` against the deployment to create the first
admin and seed rates (point `BASE` at the deployed host if it isn't localhost).

> **Note:** the production backend runs with `--workers 4` and no reload. Schema is
> still created on startup; for managed schema changes use Alembic (configured in
> `backend/migrations/`).

---

## Configuration

Environment variables (see [.env](.env) for dev defaults):

| Variable | Purpose | Dev default |
|---|---|---|
| `DATABASE_URL` | Async Postgres DSN | local Postgres |
| `JWT_SECRET_KEY` | Token signing secret — **must be set in prod** | dev placeholder |
| `JWT_ALGORITHM` | JWT algorithm | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access token lifetime | `15` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Refresh token lifetime | `7` |
| `LOG_LEVEL` | Backend log level | `INFO` |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | Postgres credentials | `steelcad` |

---

## Testing

```bash
cd backend
./venv/Scripts/python -m pytest      # pricing engine unit tests (cross-checks spec §9)
```

---

## Architecture notes

This repo follows a 3-layer convention (see [AGENTS.md](AGENTS.md)):

- **Directives** (`directives/`) — natural-language SOPs and the domain spec
- **Orchestration** — decision-making (the agent / app layer)
- **Execution** (`execution/`, backend services) — deterministic Python

Pushing the pricing and validation logic into deterministic, unit-tested code
(`backend/app/services/pricing.py`, `validation.py`) keeps quotations consistent
and auditable.
