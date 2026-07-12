# SteelCAD — Development & Operations

> Setting up, running, testing, and shipping SteelCAD, plus the gotchas worth knowing.
> The top-level [`README.md`](../README.md) has the condensed quick-start; this is the
> fuller engineering guide.

---

## 1. Prerequisites

- **Docker Desktop** (for Postgres + backend)
- **Node 20+** (for the Vite frontend)
- **Python 3.12+** (for the first-run setup script and local backend tooling)

---

## 2. Local development setup

### 2.1 Start Postgres + backend (Docker)

```bash
docker compose up -d --build      # Postgres on :5432, API on :8000
```

The API creates tables on startup and serves OpenAPI docs at
<http://localhost:8000/docs>.

### 2.2 Start the frontend (Vite)

```bash
cd frontend
npm install
npm run dev                       # http://localhost:5173
```

Vite proxies API paths to `:8000` (see [`vite.config.js`](../frontend/vite.config.js)),
so the SPA talks to the backend same-origin in dev.

### 2.3 Create an admin + seed rates

```bash
python execution/setup.py         # creates the first account, promotes to admin, seeds rates
```

This drives the first-run flow: create the first user directly in the backend
container (accounts are invite-only — there is no public register endpoint), call
`/auth/bootstrap-admin` (works only while no admin exists), then `/rates/seed`.
Afterwards, log in at <http://localhost:5173> and invite further users from the
**Users** page.

---

## 3. Backend hot-reload

The dev compose **bind-mounts** the backend source so `uvicorn --reload` picks up edits
without a rebuild:

```yaml
# docker-compose.yml (backend service)
volumes:
  - ./backend:/app      # host edits are visible in the container
  - /app/venv           # anonymous volume: keep the host venv from shadowing the image's
command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**Why the second volume matters:** the host has a `backend/venv/`. Without the anonymous
`/app/venv` volume, the bind mount would overlay that host venv onto the container and
break imports. The anonymous volume masks it so the image's installed packages win.

**When you still need a rebuild:** changes to `requirements.txt` or the `Dockerfile`
aren't picked up by `--reload`. Rebuild with:

```bash
docker compose up -d --build backend
```

You can confirm a code change is live in the container:

```bash
docker exec steelcad-backend-1 grep -c "<some new symbol>" app/services/<file>.py
docker compose logs backend --tail 5     # look for the watchfiles reload line
```

> The frontend needs no Docker rebuild in dev — Vite hot-reloads automatically.

---

## 4. Testing

```bash
cd backend
./venv/Scripts/python -m pytest            # Windows venv path
# or inside the container:
docker exec steelcad-backend-1 python -m pytest tests/test_pricing.py -q
```

The suite is concentrated on the **pricing engine** — it cross-checks the engine against
the spec's worked examples and guards the subtle rules (void-aware frames, single vs.
double sections, the door-sill exemption, rebate price-neutrality, GST, rounding). Treat
a pricing change as incomplete until these pass.

Frontend lint:

```bash
cd frontend
npx eslint src/...        # or: npm run lint
npx vite build            # type/compile sanity for a change
```

---

## 5. Production deployment

```bash
export POSTGRES_PASSWORD=$(openssl rand -hex 16)
export JWT_SECRET_KEY=$(openssl rand -hex 32)
docker compose -f docker-compose.prod.yml up -d --build
```

Production differences ([`docker-compose.prod.yml`](../docker-compose.prod.yml)):

- Self-contained images — **no** bind mounts, **no** `--reload`.
- Backend runs `--workers 4`.
- **Postgres and the backend are not published** to the host — only **nginx on :80** is.
  nginx serves the static frontend bundle and reverse-proxies the API.
- `JWT_SECRET_KEY` and `POSTGRES_PASSWORD` are **required** — compose fails fast if they
  are unset (no insecure defaults).

After bringing it up, run `python execution/setup.py` against the deployment to create
the first admin and seed rates (point its `BASE` at the host if not localhost).

---

## 6. Configuration reference

See [Backend Reference §4](./BACKEND.md#4-configuration-configpy) for the full env-var
table. Dev defaults live in [`.env`](../.env); **never** ship the dev `JWT_SECRET_KEY` or
DB password to production.

---

## 7. Common tasks ("how do I…")

### Add a new material rate
1. Add the `{item_code, rate, unit, label}` entry to `DEFAULT_RATES` in
   [`pricing.py`](../backend/app/services/pricing.py).
2. Reference its code in the relevant pricing function (`_lookup_rate(...)`).
3. Re-seed (`POST /rates/seed` skips existing codes and adds new ones), or add it
   manually via the admin Rates page.
4. Add/extend a test in `test_pricing.py`.

### Add a region type or change region semantics
This touches **both** sides of the contract — keep them aligned to the spec:
- Backend: pricing (`pricing.py`) + validation (`validation.py`).
- Frontend: geometry/factories (`editorStore.js`), the type picker + editors
  (`PropertiesPanel.jsx`), the canvas rendering (`DesignCanvas.jsx`), and the live
  validator (`validators.js`).
- Update [`directives/design_rules_spec.md`](../directives/design_rules_spec.md) first —
  it's the source of truth.

### Add an API endpoint
Add a route in the relevant `routers/*.py`, request/response Pydantic schemas in
`schemas/*.py`, and (if it's a new path prefix) the Vite dev proxy entry in
`vite.config.js` and the CORS/nginx config as needed. Wire a client helper in
`api/client.js`.

### Inspect or reproduce a quote
Pricing is a pure function — you can reproduce any quote by calling
`price_design(tree, rates)` with the stored `tree_json` and the estimate's
`rate_snapshot`. This is the whole point of the deterministic engine.

---

## 8. Gotchas & troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Backend code change not taking effect | Editing without the dev bind mount, or a `requirements.txt` change | `docker compose up -d --build backend`; for code, ensure the `./backend:/app` mount is present |
| Container import errors after adding the bind mount | Host `backend/venv` shadowing the image venv | Ensure the anonymous `/app/venv` volume is in the compose file |
| Old estimate shows stale prices after a rate change | **By design** — estimates are frozen snapshots | Touch the estimate (edit a frame/term) to trigger `_recompute` |
| Editing a library design didn't change an existing quote | **By design** — frames copy the tree | Re-add the design to the estimate, or edit the frame directly |
| 401 loops / forced logout | Refresh token expired or `JWT_SECRET_KEY` changed | Re-login; don't rotate the secret on a live session |
| Region dimensions show long decimals | Float drift from ratio math | Already handled by `_clean` (store) + `fmtFt`/`_fmt_ft` (display) |
| PDF endpoint errors | WeasyPrint native deps missing | Use the provided Docker image (its Dockerfile installs pango/cairo/etc.) |

---

## 9. Repository conventions

The repo follows a 3-layer convention (see [`AGENTS.md`](../AGENTS.md)):

- **`directives/`** — natural-language SOPs and the domain spec (the source of truth).
- **Orchestration** — the application/decision layer.
- **`execution/`** + backend services — deterministic, testable Python.

Pushing pricing and validation into deterministic, unit-tested code is what keeps
quotations consistent and auditable. When the rules change, update the spec first, then
the code on both sides of the client/server contract.

---

### See also
- [Architecture](./ARCHITECTURE.md) · [Pricing Engine](./PRICING_ENGINE.md) ·
  [Backend](./BACKEND.md) · [Frontend](./FRONTEND.md) · [Domain Model](./DOMAIN_MODEL.md)
