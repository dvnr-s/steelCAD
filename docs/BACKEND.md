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

- **Lifespan** — on startup, `Base.metadata.create_all` creates any missing tables
  (dev convenience; production should use Alembic). On shutdown, disposes the engine.
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
| is_admin | bool | default false — gates rate management |
| created_at | timestamptz | |

### `customers`
`id`, `name`, `company?`, `phone?`, `email?`, `address?`, `gstin?`, `created_by → users`,
`created_at`, `updated_at`. One customer → many estimates (cascade delete).

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

### `estimates`
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| customer_id | UUID → customers | cascade delete, indexed |
| number | int | human-friendly `EST-####` sequence |
| title?, notes? | | |
| status | varchar(20) | `draft` \| `final` |
| discount_type? | varchar(20) | `PERCENTAGE` \| `FLAT` |
| discount_value | numeric(12,2) | |
| advance_pct | numeric(5,2) | default 50 |
| **rate_snapshot** | JSONB | frozen rates at last recompute |
| subtotal, discount_amount, taxable, gst | numeric(12,2) | rolled-up totals |
| grand_total, advance_amount | int | rupee-rounded |
| created_by | UUID → users | |
| created_at, updated_at | | |

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

All endpoints require a Bearer access token unless marked **public**. Rate mutations
require **admin**.

### Auth (`/auth`)
| Method | Path | Purpose |
|---|---|---|
| POST | `/auth/register` | **public** — create account, returns `{access, refresh}` |
| POST | `/auth/login` | **public** — login, returns tokens |
| POST | `/auth/refresh` | **public** — exchange a refresh token for new tokens |
| GET | `/auth/me` | current user |
| POST | `/auth/bootstrap-admin` | **first-run only** — promote an email to admin if no admin exists yet |

### Designs (`/designs`) — the reusable library
| Method | Path | Purpose |
|---|---|---|
| GET | `/designs` | list (paginated: `skip`, `limit`) |
| POST | `/designs` | create (validates tree → 422 on errors) |
| GET | `/designs/{id}` | fetch one |
| PUT | `/designs/{id}` | update (re-validates tree) |
| DELETE | `/designs/{id}` | delete |

### Customers (`/customers`)
Standard CRUD: `GET /customers`, `POST /customers`, `GET/PUT/DELETE /customers/{id}`.

### Estimates (customer-scoped, multi-frame)
| Method | Path | Purpose |
|---|---|---|
| GET | `/customers/{cid}/estimates` | list a customer's estimates |
| POST | `/customers/{cid}/estimates` | create an estimate |
| GET | `/estimates/{id}` | full detail (frames + totals) |
| PUT | `/estimates/{id}` | update terms (title/notes/status/discount/advance) → recompute |
| DELETE | `/estimates/{id}` | delete |
| POST | `/estimates/{id}/frames` | add a frame (from a library design or a one-off tree) → recompute |
| PUT | `/estimates/{id}/frames/{fid}` | update a frame (name / quantity / tree) → recompute |
| DELETE | `/estimates/{id}/frames/{fid}` | remove a frame → recompute |
| GET | `/estimates/{id}/pdf` | download the quotation PDF |
| POST | `/price` | **stateless** price preview (used by the canvas; no persistence) |

### Rates (`/rates`)
| Method | Path | Purpose |
|---|---|---|
| GET | `/rates` | list all rates (any user) |
| PUT | `/rates/{item_code}` | **admin** — update a rate |
| POST | `/rates/seed` | **admin** — seed defaults (skips existing codes) |

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

### `generate_estimate_pdf` (pdf.py)
Renders `estimate_pdf.html` (Jinja2, with a `money` filter for Indian-grouped numbers)
to PDF bytes via WeasyPrint. The route streams it with a
`Content-Disposition: attachment` header.

---

## 8. Migrations

Alembic is configured in `backend/migrations/` and `alembic.ini`. In **dev**, tables
are auto-created on startup (`create_all`). In **production**, prefer Alembic for
controlled schema evolution rather than relying on `create_all`.

---

## 9. Testing

```bash
cd backend
./venv/Scripts/python -m pytest          # all tests
./venv/Scripts/python -m pytest tests/test_pricing.py -v
```

The suite focuses on the pricing engine — it cross-checks the engine output against the
spec's worked examples and guards the subtle frame/split rules (void-aware frames,
single vs. double sections, the door-sill exemption, rebate price-neutrality, GST and
rounding).

> Within Docker (dev), the bind mount means tests can also run inside the container:
> `docker exec steelcad-backend-1 python -m pytest tests/test_pricing.py`.
