# SteelCAD — Backend Reference

> FastAPI service: structure, database schema, endpoints, services, and auth.
> For *how it fits together*, read [Architecture](./ARCHITECTURE.md) first.

---

## 1. Stack

| Concern | Library |
|---|---|
| Web framework | FastAPI (Uvicorn ASGI server) |
| ORM | SQLAlchemy 2.0 **async** + asyncpg |
| Validation / serialization | Pydantic v2, pydantic-settings |
| Auth | python-jose (JWT, HS256), bcrypt |
| PDF | WeasyPrint + Jinja2 |
| DB | PostgreSQL 16 (JSONB for geometry) |
| Migrations | Alembic |
| Tests | pytest |

---

## 2. Layout

```
backend/
├── app/
│   ├── main.py            App assembly: lifespan, CORS, request logging, error handler, health
│   ├── config.py          Settings (env vars + dev fallbacks), cached via lru_cache
│   ├── database.py        Async engine, session factory, get_db dependency, Base
│   ├── logging_config.py  Logging setup
│   ├── models/            SQLAlchemy ORM tables
│   │   ├── user.py · customer.py · design.py · estimate.py · rate.py
│   ├── schemas/           Pydantic request/response models
│   │   ├── user.py · customer.py · design.py · estimate.py · rate.py
│   ├── routers/           HTTP endpoints
│   │   ├── auth.py · designs.py · customers.py · estimates.py · rates.py
│   ├── services/          Business logic (no HTTP/DB coupling where possible)
│   │   ├── auth.py        password hashing, JWT, get_current_user / require_admin
│   │   ├── validation.py  validate_design_tree (INV-* / V-*)
│   │   ├── pricing.py     price_design / price_estimate (pure, tested)
│   │   ├── grill.py       SS grill bar math (§6.2/§6.2A) — mirrors frontend lib/grill.js
│   │   └── pdf.py         WeasyPrint rendering
│   └── templates/estimate_pdf.html
├── migrations/            Alembic environment
├── tests/test_pricing.py  Pricing engine unit tests
├── Dockerfile · requirements.txt · pytest.ini · alembic.ini
```

**Layering:** `router → service → model`. Routers handle HTTP; services hold logic;
models are persistence. Pricing and validation are deliberately framework-free
functions so they can be unit-tested without a server or DB.

---

## 3. Application bootstrap (`main.py`)

- **Lifespan** — on startup (dev), `Base.metadata.create_all` creates any missing
  tables as a convenience; production drives schema via Alembic (§8). On shutdown,
  disposes the engine.
- **CORS** — allow-list of dev/prod origins (`localhost:5173`, `localhost`, …).
- **Request logging middleware** — logs `METHOD path → status (Xms)` for every request;
  logs and re-raises on unhandled errors.
- **Global exception handler** — logs the traceback, returns a generic 500 (no stack
  leak to the client).
- **Health** — `GET /health → {status: "ok"}`.

---

## 4. Configuration (`config.py`)

Environment variables (dev defaults in [`.env`](../.env)):

| Variable | Purpose | Dev default |
|---|---|---|
| `DATABASE_URL` | Async Postgres DSN | local Postgres |
| `JWT_SECRET_KEY` | Token signing secret (**required in prod**) | dev placeholder |
| `JWT_ALGORITHM` | JWT algorithm | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access token lifetime | `15` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Refresh token lifetime | `7` |
| `LOG_LEVEL` | Backend log level | `INFO` |

---

## 5. Database schema

All tables use UUID primary keys. Geometry is JSONB.

### `users`
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| email | varchar(255) | unique, indexed |
| password | varchar(255) | bcrypt hash |
| name | varchar(255) | |
| role | varchar(20) | `admin` \| `owner` \| `sales` (invite-only creation) |
| is_admin | bool | legacy flag, kept in sync with `role == "admin"` |
| created_at | timestamptz | |

### `customers`
`id`, `name`, `company?`, `phone?`, `email?`, `address?`, `gstin?`, `created_by → users`,
`created_at`, `updated_at`, `deleted_at?` (soft delete). One customer → many estimates
(cascade delete).

### `designs` (reusable library templates)
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| name, description? | text | |
| **tree_json** | JSONB | the full geometry tree (spec §13) |
| outer_width, outer_height | numeric(6,2) | denormalized for listing |
| section_size, gauge | varchar(4) | denormalized |
| created_by | UUID → users | |
| created_at, updated_at | timestamptz | |
| deleted_at? | timestamptz | soft delete (restorable via `/trash`) |

### `estimates`
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| customer_id | UUID → customers | cascade delete, indexed |
| number | int | human-friendly `EST-####` sequence; unique with `revision` |
| revision | int | default 1 — "revise" clones as N+1, parent becomes `superseded` |
| parent_id? | UUID → estimates | revision chain provenance |
| title?, notes? | | |
| status | varchar(20) | `draft` \| `sent` \| `accepted` \| `rejected` \| `superseded` |
| quote_date?, valid_until? | date | sent quotes past `valid_until` report a derived `expired` flag |
| terms? | text | quotation terms & conditions (defaults from company settings) |
| accepted_at? | timestamptz | stamped on acceptance |
| discount_type? | varchar(20) | `PERCENTAGE` \| `FLAT` |
| discount_value | numeric(12,2) | |
| advance_pct | numeric(5,2) | default 50 (default configurable in company settings) |
| gst_pct | numeric(5,2) | snapshot of the company GST % at creation (default 18) |
| **rate_snapshot** | JSONB | frozen rates at last recompute |
| subtotal, discount_amount, taxable, gst | numeric(12,2) | rolled-up totals |
| grand_total, advance_amount | int | rupee-rounded |
| created_by | UUID → users | |
| created_at, updated_at | | |
| deleted_at? | timestamptz | soft delete |

### `company_settings` (singleton, id=1)
Seller identity for the quotation PDF and commercial defaults: `name`,
`logo_data_url?`, `address?`, `phone?`, `email?`, `gstin?`, `bank_details?`,
`default_terms?`, `gst_pct` (default 18), `default_advance_pct` (default 50),
`currency_symbol` (default ₹). Managed by admin/owner via `/settings`.

### `audit_log` & `rate_history`
Append-only. `audit_log(actor_id?, action, entity_type, entity_id?, summary,
created_at)` records who did what (status changes, deletes, rate edits, …);
`rate_history(item_code, old_rate, new_rate, actor_id?, created_at)` tracks every
rate change.

### `estimate_frames` (snapshots within an estimate)
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| estimate_id | UUID → estimates | cascade delete, indexed |
| source_design_id? | UUID → designs | provenance; `SET NULL` if the design is deleted |
| name | varchar(255) | |
| **tree_json** | JSONB | a **copy** of the geometry |
| outer_width, outer_height, section_size, gauge | | denormalized |
| quantity | int | |
| **unit_breakdown** | JSONB | frozen per-unit price breakdown |
| unit_subtotal, line_total | numeric(12,2) | |
| sort_order | int | display order |
| created_at | | |

### `rates` (global, admin-managed)
`item_code` (PK-like), `rate`, `unit`, `label`. Seeded from `DEFAULT_RATES`.

```
users ─< designs
users ─< customers ─< estimates ─< estimate_frames ─(source)─> designs
                          └─ rate_snapshot (JSONB)
rates (global)
```

---

## 6. API reference

All endpoints require a Bearer access token unless marked **public**. Row-level rules
(creator-or-admin/owner writes, admin/owner deletes, non-draft estimate lock) are
enforced via [`services/access.py`](../backend/app/services/access.py).

### Auth (`/auth`)
| Method | Path | Purpose |
|---|---|---|
| POST | `/auth/login` | **public** — login, returns `{access, refresh}` (rate-limited) |
| POST | `/auth/refresh` | **public** — exchange a refresh token for new tokens |
| GET | `/auth/me` | current user |
| POST | `/auth/change-password` | change own password (requires current password) |
| POST | `/auth/bootstrap-admin` | **first-run only** — promote an email to admin if no admin exists yet |

There is **no public register endpoint** — accounts are invite-only via `/users`.

### Users (`/users`) — admin/owner
List users, create (invite) a user with a role, change a role, reset a password,
delete a user (admin only). Owners can only manage `sales` users.

### Designs (`/designs`) — the reusable library
| Method | Path | Purpose |
|---|---|---|
| GET | `/designs` | list (paginated: `skip`, `limit`; search: `q`) |
| POST | `/designs` | create (validates tree → 422 on errors) |
| GET | `/designs/{id}` | fetch one |
| GET | `/designs/{id}/thumbnail.svg` | server-rendered schematic thumbnail |
| PUT | `/designs/{id}` | update (re-validates tree) |
| DELETE | `/designs/{id}` | soft delete (admin/owner) |
| POST | `/designs/{id}/restore` | restore from trash |

### Customers (`/customers`)
CRUD with search (`q` matches name/company/phone), soft delete + `POST
/customers/{id}/restore`.

### Estimates (customer-scoped, multi-frame)
| Method | Path | Purpose |
|---|---|---|
| GET | `/estimates` | global search (`q`, `status`) across all customers |
| GET | `/customers/{cid}/estimates` | list a customer's estimates (`q` searchable) |
| POST | `/customers/{cid}/estimates` | create an estimate |
| GET | `/estimates/{id}` | full detail (frames + totals) |
| PUT | `/estimates/{id}` | update terms (title/notes/valid_until/terms/discount/advance) → recompute |
| PATCH | `/estimates/{id}/status` | status transition (draft/sent/accepted/rejected) — audited |
| POST | `/estimates/{id}/duplicate` | copy to a fresh draft (new number, rev 1) |
| POST | `/estimates/{id}/revise` | clone as revision N+1; parent becomes `superseded` |
| DELETE | `/estimates/{id}` | soft delete (admin/owner); `POST .../restore` undoes |
| POST | `/estimates/{id}/frames` | add a frame (from a library design or a one-off tree) → recompute |
| PUT | `/estimates/{id}/frames/{fid}` | update a frame (name / quantity / tree) → recompute |
| POST | `/estimates/{id}/frames/{fid}/duplicate` | copy a frame within the estimate |
| GET | `/estimates/{id}/frames/{fid}/thumbnail.svg` | server-rendered frame schematic (ETag on `estimate.updated_at`) |
| DELETE | `/estimates/{id}/frames/{fid}` | remove a frame → recompute |
| GET | `/estimates/{id}/pdf` | download the internal quotation PDF (per-frame cost breakdowns + BOM) |
| GET | `/estimates/{id}/pdf/customer` | download the customer-facing summary PDF (frame cards, no cost breakdown) |
| GET | `/estimates/{id}/bom.csv` | download the aggregated bill of materials |
| POST | `/price` | **stateless** price preview (used by the canvas; rate-limited) |

Non-`draft` estimates reject mutations (409) until reopened — revise instead.

### Rates (`/rates`)
| Method | Path | Purpose |
|---|---|---|
| GET | `/rates` | list all rates (any user) |
| PUT | `/rates/{item_code}` | **admin/owner** — update a rate (recorded in `rate_history`) |
| POST | `/rates/seed` | **admin/owner** — seed defaults (skips existing codes) |

### Settings, dashboard, audit, trash
`GET/PUT /settings/company` (admin/owner — branding, GSTIN, bank details, default
terms, GST %, currency); `GET /dashboard/*` (pipeline + monthly metrics);
`GET /audit` (activity feed, admin/owner); `GET /trash` + restore endpoints
(admin/owner).

Interactive OpenAPI docs are served at `http://localhost:8000/docs`.

---

## 7. Key service behaviors

### `validate_design_tree` (validation.py)
Walks the tree, enforcing invariants (INV-1…INV-10) and validation rules (V-1…V-18);
returns a list of human-readable error strings (empty = valid). Called on every design
create/update and frame add/update; failures return **422** with `{validation_errors:
[...]}`.

### `_recompute` (estimates.py)
The estimate's heartbeat. On any estimate or frame mutation it:
1. loads the **current** rate table,
2. reprices **every** frame via `price_design`,
3. stores each frame's `unit_breakdown` / `unit_subtotal` / `line_total`,
4. rolls up `subtotal → discount → GST → grand_total → advance`,
5. freezes `rate_snapshot`.

Because it only runs on mutation, an untouched estimate keeps its prior numbers (the
intentional "immutable snapshot" behavior).

### `generate_estimate_pdf` / `generate_customer_estimate_pdf` (pdf.py)
Two parallel render paths, both Jinja2 → WeasyPrint, streamed with a
`Content-Disposition: attachment` header (with a `money` filter for Indian-grouped
numbers). `generate_estimate_pdf` renders `estimate_pdf.html` — the **internal**
document with per-component costs and the BOM, used to cross-check an estimate.
`generate_customer_estimate_pdf` renders `estimate_customer_pdf.html` — the
**customer-facing** summary: one card per frame (diagram, dimensions, section, a
price-free spec line derived from the frozen `unit_breakdown` *labels*, and
qty × unit price), plus the standard totals box. It deliberately shares no code with
the internal renderer so changes to one can never leak into the other; item
*descriptions* (which embed ₹ rates) must never reach the customer template.

---

## 8. Migrations

Alembic is configured in `backend/migrations/` and `alembic.ini`; versioned migrations
live in `backend/migrations/versions/` (0001_initial_schema onward). Apply with
`alembic upgrade head` (in the container: `docker exec steelcad-backend-1 alembic
upgrade head`). In **dev**, startup additionally runs `create_all` as a convenience;
migrations use `IF EXISTS` guards where needed so both bootstrap paths converge.
**Production** applies migrations explicitly — see [DEPLOY.md](./DEPLOY.md).

---

## 9. Testing

```bash
cd backend
./venv/Scripts/python -m pytest -q                 # unit suites (pricing/validation/diagram)
./venv/Scripts/python -m pytest tests/test_pricing.py -v

# Full suite incl. API integration tests (needs a Postgres + TEST_DATABASE_URL):
docker exec steelcad-db-1 psql -U steelcad -c "CREATE DATABASE steelcad_test"   # once
docker exec -e TEST_DATABASE_URL=postgresql+asyncpg://steelcad:steelcad@db:5432/steelcad_test \
  steelcad-backend-1 python -m pytest -q
```

Suites: `test_pricing.py` cross-checks the engine against the spec's worked examples
(void-aware frames, single vs. double sections, the door-sill exemption, rebate
price-neutrality, GST, rounding); `test_validation.py` covers the tree validator;
`test_grill.py` pins the shared SS bar math (counts, pitch, offsets);
`test_diagram.py` covers the SVG schematic renderer; `test_api.py` is the HTTP
integration suite (auth, RBAC, estimate lifecycle, revisions, soft delete, PDF/BOM) —
it skips itself unless `TEST_DATABASE_URL` is set. CI (`.github/workflows/ci.yml`)
runs all of them against a Postgres service container.
