# SteelCAD — Architecture & How It Works

> **Audience:** engineers joining the project who need a complete, accurate mental
> model of the system — what the pieces are, how they communicate, and *why* the
> design is the way it is.
>
> **Scope:** the running system end-to-end. For the business rules themselves, see
> [`directives/design_rules_spec.md`](../directives/design_rules_spec.md); for the cost
> math, see [Pricing Engine](./PRICING_ENGINE.md).

---

## Table of contents

1. [What SteelCAD is](#1-what-steelcad-is)
2. [Core principles](#2-core-principles)
3. [System topology](#3-system-topology)
4. [The domain in one picture: the geometry tree](#4-the-domain-in-one-picture-the-geometry-tree)
5. [Where the domain lives in code](#5-where-the-domain-lives-in-code)
6. [End-to-end flows](#6-end-to-end-flows)
7. [Backend internals](#7-backend-internals)
8. [Frontend internals](#8-frontend-internals)
9. [Validation: the dual-guard model](#9-validation-the-dual-guard-model)
10. [Persistence model](#10-persistence-model)
11. [Security model](#11-security-model)
12. [Key design decisions & trade-offs](#12-key-design-decisions--trade-offs)
13. [Known limitations & future work](#13-known-limitations--future-work)

---

## 1. What SteelCAD is

SteelCAD lets a fabricator **draw** a steel door or window on a canvas, **subdivide**
it into regions (panels), **assign** each region a type and materials (glass, jali,
grills, hinges, locks…), and then **generate an itemized, GST-inclusive quotation**
that can be exported to PDF and grouped per customer.

The product has two halves that meet at one contract:

- **The frontend owns the drawing and interaction.** It never computes a price.
- **The backend owns pricing and validation.** It never renders graphics.

Everything else follows from that split.

---

## 2. Core principles

These four principles explain most of the non-obvious choices in the codebase.

### P1 — The canvas object tree is the single source of truth
Every price, every breakdown line, and every validation result is **derived from
explicit geometry objects** in a tree — never from form fields, global toggles, or
inferred intent. A region is `shutter` because the tree says so, not because a
checkbox is ticked somewhere. (Spec §1.)

### P2 — Pricing and validation are deterministic, server-side, and unit-tested
The cost engine ([`pricing.py`](../backend/app/services/pricing.py)) is **pure Python**:
tree in, breakdown out, no I/O, no randomness. The same tree + same rates always
produce the same quote. This keeps quotations auditable and reproducible, and is why
the engine has a dedicated test suite ([`test_pricing.py`](../backend/tests/test_pricing.py)).

### P3 — Estimates are immutable snapshots
When you price an estimate, the rates used are **frozen** into it (`rate_snapshot`),
and the per-frame breakdown is stored. Updating the global rate table later does **not**
silently change an existing quote (spec PR-6, PR-7). A quote you sent stays the quote
you sent until you deliberately re-touch it.

### P4 — The backend re-derives, it never trusts
On save and on pricing, the backend re-validates the whole tree and re-computes all
geometry and costs from the tree itself. The frontend's numbers are a *preview*; the
server's numbers are *authoritative* (spec §12.3).

---

## 3. System topology

Three processes: a React single-page app, a FastAPI service, and PostgreSQL.

```
                            ┌─────────────────────────────────────────────┐
                            │                  Browser                     │
                            │   React 19 SPA (Vite build)                  │
                            │   • Konva canvas editor                      │
                            │   • Zustand stores (auth, editor)            │
                            │   • Axios client (JWT + auto-refresh)        │
                            └───────────────────┬─────────────────────────┘
                                                │  HTTPS / JSON
                                                │  Authorization: Bearer <access JWT>
                            ┌───────────────────▼─────────────────────────┐
                            │              FastAPI (Uvicorn)               │
                            │  Routers: auth, designs, customers,          │
                            │           estimates, rates                   │
                            │  Services: auth, validation, pricing, pdf    │
                            │  SQLAlchemy 2.0 async ORM                     │
                            └───────────────────┬─────────────────────────┘
                                                │  asyncpg
                            ┌───────────────────▼─────────────────────────┐
                            │              PostgreSQL 16                    │
                            │  users · customers · designs ·               │
                            │  estimates · estimate_frames · rates         │
                            │  (geometry stored as JSONB)                  │
                            └─────────────────────────────────────────────┘
```

### Dev vs. production wiring

| Aspect | Dev (`docker-compose.yml`) | Prod (`docker-compose.prod.yml`) |
|---|---|---|
| Frontend | Vite dev server on `:5173`, proxies API calls to `:8000` (see [`vite.config.js`](../frontend/vite.config.js)) | Static bundle served by **nginx on `:80`**, which also reverse-proxies the API |
| Backend | Uvicorn `--reload`, source **bind-mounted** (`./backend:/app`) so edits hot-reload | Uvicorn `--workers 4`, no reload, self-contained image |
| Postgres | published on `:5432` | **not** published — internal network only |
| Secrets | insecure dev defaults are allowed | `JWT_SECRET_KEY` and `POSTGRES_PASSWORD` are **required** (compose fails without them) |
| Exposed ports | 5173, 8000, 5432 | 80 only |

> **Hot-reload gotcha (dev):** the backend image bakes code in via `COPY . .`. The
> dev compose adds a bind mount (`./backend:/app`) plus an anonymous volume on
> `/app/venv` so the host venv doesn't shadow the image's installed packages. Without
> that bind mount, `--reload` has nothing to reload and code changes need a rebuild.
> See [Development & Operations](./DEVELOPMENT.md#backend-hot-reload).

---

## 4. The domain in one picture: the geometry tree

A design is a **recursive binary tree**. This is the heart of the whole system, so
internalize it before anything else.

```
Design                         productType: "window" | "door"
 └── Frame                     the outer steel boundary (W × H feet)
      └── RootRegion           a rectangular area
           ├── [LEAF]          regionType + paneSpec + overlays[] + hardware[]
           └── [BRANCH] ──► Split   (mullion = vertical | transom = horizontal)
                              ├── ChildRegion A
                              └── ChildRegion B
```

Rules that make it tractable (spec §3, §14):

- **Binary.** Every `Split` produces exactly two child regions. N panels = N−1 nested
  splits.
- **Leaf vs. branch.** A *leaf* region has a `regionType` (`open`/`fixed`/`shutter`/
  `door`/`louver`) and may carry a pane, grills, and hardware. A *branch* region has a
  `Split` and two children, and carries none of those (except an SS-grill "continuity"
  overlay — see [Domain Model](./DOMAIN_MODEL.md)).
- **Geometry is derived top-down.** Only the frame size and each split's *ratio*
  (`position` ∈ (0,1)) are stored as intent. Every region's `x/y/width/height` is
  *recomputed* from them. This recomputation is the `relayout()` function — the single
  source of truth for geometry (see §8).
- **Rectangles only (v1).** No arcs/polygons yet.

A concrete serialized example lives in the spec, [§13](../directives/design_rules_spec.md).
The same JSON is what's stored in `designs.tree_json` and `estimate_frames.tree_json`.

---

## 5. Where the domain lives in code

The spec's concepts map to specific modules. This table is the Rosetta Stone between
the rules and the implementation:

| Spec concept | Frontend | Backend |
|---|---|---|
| Geometry tree, region factories, `relayout`, splitting | [`store/editorStore.js`](../frontend/src/store/editorStore.js) | (received as JSON) |
| Canvas rendering, zoom/pan, drag interactions | [`components/DesignCanvas.jsx`](../frontend/src/components/DesignCanvas.jsx) | — |
| Region/pane/grill/hardware editing UI | [`components/PropertiesPanel.jsx`](../frontend/src/components/PropertiesPanel.jsx) | — |
| Live validation (INV/V rules, pragmatic mirror) | [`lib/validators.js`](../frontend/src/lib/validators.js) | [`services/validation.py`](../backend/app/services/validation.py) |
| Pricing derivation (§9) | *(preview only, via API)* | [`services/pricing.py`](../backend/app/services/pricing.py) |
| Estimate aggregation, recompute, rate snapshot | — | [`routers/estimates.py`](../backend/app/routers/estimates.py) |
| PDF quotation | — | [`services/pdf.py`](../backend/app/services/pdf.py) + [`templates/estimate_pdf.html`](../backend/app/templates/estimate_pdf.html) |

The crucial asymmetry: **`relayout`/geometry math exists on both sides conceptually,
but pricing exists only on the backend.** The frontend asks the backend for a price
preview; it never adds up rupees itself.

---

## 6. End-to-end flows

### 6.1 Authentication & the auto-refresh loop

```
Login form ──login(email,pw)──► POST /auth/login
                                   └─ verify bcrypt hash
                                   └─ issue { access(15m), refresh(7d) } JWTs
        ◄───────────────────────────────────────────────────────────
   authStore stores user; tokens go to localStorage

Every API call:
   Axios request interceptor ── attaches  Authorization: Bearer <access>

On 401 (access expired):
   Axios response interceptor ── POST /auth/refresh { refresh_token }
        ├─ success → swap in new tokens, replay the original request
        └─ failure → clear storage, redirect to /login
   (concurrent 401s queue behind a single refresh; see api/client.js)
```

- Tokens are JWTs signed with `JWT_SECRET_KEY` (HS256). Access tokens carry
  `type:"access"`; refresh carry `type:"refresh"`. The server checks the type so a
  refresh token can't be used as an access token ([`services/auth.py`](../backend/app/services/auth.py)).
- `authStore` is a **persisted** Zustand store (`localStorage` key `steelcad-auth`),
  so a reload keeps you logged in; `App.jsx` calls `fetchMe()` on boot to revalidate.
- **Admin gating** is twofold: the UI hides admin routes (`AdminRoute` in
  [`App.jsx`](../frontend/src/App.jsx)), and the API enforces it server-side via the
  `require_admin` dependency on rate mutations.

### 6.2 Designing & live pricing (the editor loop)

This is the tightest, most important loop in the app.

```
 User drags a mullion / types a region / resizes the frame
        │
        ▼
 editorStore mutation (splitRegion, setSplitPosition, updateRegion, …)
        │  every mutation routes through _commit(): pushes undo history,
        │  sets isDirty, and replaces `tree`
        ▼
 relayout(tree)  ── recompute all x/y/width/height top-down from
        │             frame size + split ratios; round off float drift
        ▼
 React re-renders:
   • DesignCanvas paints the new geometry (Konva)
   • PropertiesPanel reflects the selected region
   • validators.js recomputes issues (instant red flags)
        │
        ▼
 EditorPage effect (debounced 600 ms) ── POST /price { tree_json }
        ▼
 backend price_design(tree, rates) ── returns full itemized breakdown
        ▼
 livePrice in store → PriceDisplay + PricingBreakdown update
```

Key properties:

- **Geometry is local and instant; price is remote and debounced.** Dragging feels
  immediate because the canvas re-renders from the local tree; the rupee figure trails
  by ~600 ms because it round-trips to the authoritative engine.
- **Undo/redo** is a snapshot stack in the store (`past`/`future`, capped at 50). A
  drag uses `beginInteraction`/`endInteraction` so the *entire* drag collapses into one
  undo step instead of hundreds.
- The same `EditorPage` serves two contexts: editing a **library design**
  (`/designs/:id`) and editing a **frame inside an estimate**
  (`/estimates/:estimateId/frames/:frameId`). It branches on `frameMode`.

### 6.3 Building an estimate (customer → quote → PDF)

```
Customer ──► Estimate (EST-####) ──► add Frames (each = a geometry tree × qty)
                                          │
                                          ▼
        any mutation (add/edit/delete frame, change terms)
                                          │
                                          ▼
        _recompute(estimate):  for every frame → price_design(tree, currentRates)
                               store unit_breakdown, unit_subtotal, line_total
                               roll up: subtotal → discount → GST(18%) → grand total → advance
                               freeze rate_snapshot
                                          │
                                          ▼
        GET /estimates/{id}/pdf ──► WeasyPrint renders estimate_pdf.html → PDF bytes
```

- A frame stores a **copy** of the tree (`tree_json`), so editing the frame never
  mutates the library design it came from (`source_design_id` is provenance only).
- `_recompute` runs on **every** estimate mutation and reprices **all** frames with
  the **current** rates — but only when the estimate is touched. This is precisely
  why an untouched old estimate keeps its old numbers (P3): nothing re-prices it until
  you edit it. See [`routers/estimates.py`](../backend/app/routers/estimates.py).

### 6.4 Pricing a single unit (inside the engine)

`price_design(tree, rates)` performs one depth-first traversal and sums four cost
families. Summarized here; full detail in [Pricing Engine](./PRICING_ENGINE.md).

```
1. Frame      window → 4-sided void-aware perimeter
              door   → 3-sided (base is in the concrete); a door region carries no sill
2. Splits     each mullion/transom: double section (2× rate) if it divides two occupied
              regions; single (1× rate) if it borders an empty `open` void
3. Regions    per leaf: structural pane (shutter only) + infill (jali area) +
              beading (perimeter) + hardware (per piece);
              per leaf-or-branch: grill (MS area / SS bar-count)
4. Aggregate  subtotal → discount → taxable → GST 18% → grand total (₹ rounded) → advance
```

---

## 7. Backend internals

### 7.1 Stack

FastAPI + Uvicorn, SQLAlchemy 2.0 **async** ORM over asyncpg, Pydantic v2 schemas,
python-jose for JWT, bcrypt for passwords, WeasyPrint + Jinja2 for PDF.

### 7.2 Request lifecycle

```
HTTP request
  → CORS middleware (allow-list of dev/prod origins)
  → request-logging middleware (method, path, status, duration)
  → router dependency: get_current_user  (decodes Bearer JWT → User)
       └─ (rate mutations) require_admin
  → handler
       └─ get_db dependency yields an AsyncSession:
            • commit on success
            • rollback on any exception
  → response
On any unhandled exception:
  → global handler logs the traceback and returns a clean 500 (no stack leak)
```

The session lifecycle is centralized in [`database.py`](../backend/app/database.py)'s
`get_db()` — handlers call `await db.flush()` to get server-assigned IDs, and the
dependency commits at the end. This means a handler that raises **automatically rolls
back** the whole request.

### 7.3 Layout

```
backend/app/
├── main.py            app assembly, lifespan (create tables in dev), CORS, logging, errors
├── config.py          pydantic-settings; env vars with dev fallbacks
├── database.py        async engine, session factory, get_db dependency, Base
├── logging_config.py  structured logging setup
├── models/            SQLAlchemy ORM tables (user, customer, design, estimate, rate)
├── schemas/           Pydantic request/response models (validation + serialization)
├── routers/           HTTP endpoints (auth, designs, customers, estimates, rates)
├── services/          business logic: auth, validation, pricing, pdf
├── templates/         estimate_pdf.html (Jinja2)
└── migrations/        Alembic (production schema management)
```

The **router → service → model** layering keeps HTTP concerns out of the business
logic. Pricing and validation are plain functions with no FastAPI or DB dependencies,
which is what makes them unit-testable in isolation.

> See [Backend Reference](./BACKEND.md) for the full endpoint catalogue and DB schema.

---

## 8. Frontend internals

### 8.1 Stack & routing

React 19 + Vite, Konva/react-konva for the canvas, Zustand for state, Axios for HTTP,
react-router-dom for routing, react-hot-toast for notifications, lucide-react for icons.

Routes ([`App.jsx`](../frontend/src/App.jsx)) are wrapped in `ProtectedRoute` (requires
auth) or `RoleRoute` (requires one of the listed roles):

```
/login                                          public (accounts are invite-only)
/                       → HomePage              (dashboard + global estimate search)
/customers              → CustomersPage
/customers/:id          → CustomerDetailPage
/estimates/:id          → EstimateBuilderPage   (frames table, terms, PDF/BOM)
/estimates/:eId/frames/:fId → EditorPage        (canvas, frame-edit mode)
/designs                → DashboardPage          (reusable design library, thumbnails)
/designs/:id            → EditorPage            (canvas, library mode)
/rates                  → RatesPage             (admin/owner)
/users                  → UsersPage             (admin/owner — invite, roles, resets)
/settings               → SettingsPage          (admin/owner — company/branding/GST)
/activity               → ActivityPage          (admin/owner — audit feed)
/trash                  → TrashPage             (admin/owner — restore soft-deleted)
```

### 8.2 State: two Zustand stores

- **`authStore`** (persisted) — `user`, `isAuthenticated`, and `login/register/logout/
  fetchMe`. Tokens themselves live in `localStorage` (read by the Axios interceptor),
  not in the store.
- **`editorStore`** — the design under edit and everything around it: `tree`,
  `designId`, `isDirty`, undo `past`/redo `future`, `selectedId`, `addMode`,
  `livePrice`. It also **owns all geometry logic** (region factories, `relayout`,
  splitting, the grid snap).

### 8.3 The geometry engine (`editorStore.js`)

This file is the frontend's counterpart to the backend pricing engine — the place
where the tree is mutated correctly.

- **Factories** — `makeLeafRegion`, `makeDoorRegion`, `makeWindowRegion`,
  `makeEmptyTree` create well-formed nodes (UUIDs, defaults, door hardware auto-seeded
  by `doorHingeCount`).
- **`relayout(tree)`** — recomputes every region's `x/y/width/height` from the frame
  size and split ratios, depth-first. It is **idempotent** and is called after every
  structural change. It also rounds off floating-point drift (`_clean`, to 4 dp) so a
  ratio product like `4.7499999999999999` is stored as a clean `4.75` — keeping saved
  data, validation, and pricing tidy.
- **`snapOffset`** — snaps split positions to a 0.25 ft (3-inch) grid and clamps so
  each side keeps the 0.5 ft minimum.
- **Mutations** (`splitRegion`, `setSplitPosition`, `setFrameSize`, `updateRegion`,
  `collapseRegion`, `addWindowToDoor`) all immutably rebuild the affected branch and
  route through **`_commit`**, which pushes the previous tree onto the undo stack,
  clears redo, and marks the design dirty.
- **Drag batching** — `beginInteraction`/`endInteraction` snapshot the tree at drag
  start and record a single undo step at drag end, so a continuous drag is one
  reversible action.

### 8.4 The canvas (`DesignCanvas.jsx`)

A Konva `<Stage>` with one `<Layer>`. It is a **pure projection** of the store's tree —
it reads geometry and translates feet ↔ pixels; it does not own geometry.

- **View transform.** Screen = `feet × scale + translation`. The component keeps a
  `view = { scale, tx, ty }` and exposes `px/py` (feet→pixels) and `toFeetX/Y`
  (pixels→feet). All hit-testing and drag math go through these, so zoom and pan are
  "free" — no Konva stage transform is applied, which keeps the existing drag math
  unchanged.
- **Fit-but-never-upscale default.** On opening a design, `fitScale` picks a scale that
  fits the frame in the viewport but never exceeds true size (60 px/ft). Big frames
  shrink to fit; small frames stay at true size.
- **Zoom & pan.** Mouse wheel zooms toward the cursor; dragging empty canvas pans; a
  toolbar offers −/100%/+/Fit. A pan-drag is distinguished from a click so panning
  never clears the selection.
- **Interactions.** Mullions are draggable Konva rects with a `dragBoundFunc` clamping
  them to the parent region minus the minimum side; double-clicking a mullion collapses
  the split. Frame-resize handles drive `setFrameSize`. In "add mullion" mode a ghost
  line previews the split before you click.
- **Symbols.** Helper components draw the door swing triangle (`DoorSwing`), the
  in-concrete base hatch for door products (`ConcreteBase`), the diagonal void hatch for
  empty `open` regions (`VoidHatch`), and the grill patterns (`GrillOverlay`).

### 8.5 The properties panel (`PropertiesPanel.jsx`)

Context-sensitive editors for the selected region: region **type** picker, **pane**
spec (shutter material, infill, beading), **grill** type, **hardware** (hinges/locks,
with front/back grouping for double-rebate doors), **door options** (hand, rebate),
**add-window-to-door** helper, and **split** controls. Each editor writes back through
`updateRegion`, so the canvas and price update reactively.

> See [Frontend Reference](./FRONTEND.md) for component-by-component detail.

---

## 9. Validation: the dual-guard model

Validation runs in **two places**, deliberately:

- **Client** ([`lib/validators.js`](../frontend/src/lib/validators.js)) — a pragmatic
  mirror of the rules, run on every edit. It gives instant red flags in the editor
  ("door needs at least one hinge", "shutter needs a material") so the user isn't
  surprised by a server rejection. Clickable issues select the offending region.
- **Server** ([`services/validation.py`](../backend/app/services/validation.py)) — the
  authoritative gate. `validate_design_tree` walks the tree enforcing invariants
  (INV-1…INV-10) and validation rules (V-1…V-18) and returns a list of error strings.
  Design create/update and frame add/update reject with **422** and the error list if
  anything fails.

The client check is a UX convenience; the server check is the contract. The two are
intentionally kept in sync against the same spec sections.

---

## 10. Persistence model

```
users (1) ───< designs            (reusable "library" templates)
users (1) ───< customers (1) ───< estimates (1) ───< estimate_frames
                                        │                    │
                                        │                    └─ tree_json (a COPY)
                                        └─ rate_snapshot (frozen rates)
rates  (global, admin-managed)
```

- **`designs.tree_json`** and **`estimate_frames.tree_json`** are PostgreSQL **JSONB**
  columns holding the entire recursive geometry tree. Alongside, a few denormalized
  columns (`outer_width`, `outer_height`, `section_size`, `gauge`) are kept for cheap
  listing/filtering without parsing the JSON.
- **Designs are a reusable library**; **estimate frames are snapshots**. Adding a
  library design to an estimate **copies** its tree into a frame. Editing the frame
  (or the library design) never affects the other.
- **Estimates carry frozen commercials**: `rate_snapshot`, the per-frame
  `unit_breakdown`, and the rolled-up totals are all stored. They're refreshed only by
  `_recompute`, which only runs when the estimate is mutated.

> Full column-level schema is in [Backend Reference](./BACKEND.md#database-schema).

---

## 11. Security model

- **Authentication** — JWT bearer tokens (access 15 min, refresh 7 days), bcrypt
  password hashing, signed with `JWT_SECRET_KEY`. The refresh endpoint validates the
  token *type* to prevent token-class confusion.
- **Authorization** — all data endpoints require a valid access token
  (`get_current_user`). Row-level rules go through one seam,
  [`services/access.py`](../backend/app/services/access.py): reads are shared
  org-wide; edits require creator or admin/owner (`assert_can_write`); deletes of
  designs/customers/estimates require admin/owner (`require_role`); non-draft
  estimates are read-only (`assert_editable`). Roles are `admin`/`owner`/`sales`;
  accounts are **invite-only** (created via `/users` by admin/owner — there is no
  public register endpoint). Admin bootstrap is a **first-run-only** endpoint
  (`/auth/bootstrap-admin`) that becomes a no-op once any admin exists.
- **Rate limiting** — slowapi limits on the auth and price endpoints.
- **Transport & exposure** — in production, Postgres and the backend are **not**
  published to the host; only nginx on port 80 is. CORS is restricted to an allow-list
  of known origins.
- **Error hygiene** — a global exception handler logs the full traceback server-side
  but returns a generic 500 to the client, so stack traces never leak.

**Current caveats (be aware):**
- Tokens are stored in `localStorage` (XSS-exposed) rather than httpOnly cookies — a
  pragmatic choice for an internal tool.
- *Reads* remain shared org-wide by design (single-company workspace) — only writes and
  deletes are scoped. See [AUTHORIZATION_GAPS.md](./AUTHORIZATION_GAPS.md) for the full
  model and its history.

---

## 12. Key design decisions & trade-offs

| Decision | Why | Trade-off / consequence |
|---|---|---|
| **Pricing is server-side only** | One auditable, testable source of truth; the client can't fudge a quote | Live price has ~600 ms latency (debounced round-trip) |
| **Geometry stored as JSONB, not normalized tables** | The tree is read/written whole, has variable depth, and is never queried *into* | Can't query "all regions with jali" in SQL; must load + walk the tree |
| **Geometry derived from ratios, not absolute coords** | Resizing the frame or dragging a mullion is a single ratio change; everything else recomputes | Every change triggers a full `relayout`; float drift must be rounded (`_clean`) |
| **Estimates snapshot rates & breakdowns** | A sent quote must not change when rates move (PR-7) | Old estimates show stale prices until deliberately re-touched (by design) |
| **Frames copy the tree** | Editing a quote line must not mutate the shared library design | Duplicate geometry data; library edits don't propagate to existing quotes |
| **Window frame is void-aware (4-sided), door is 3-sided** | Match fabrication reality: empty `open` regions carry no steel; a door's base sits in concrete; a door region carries no bottom sill even inside a window | Frame cost needs per-edge occupancy logic, not a simple perimeter (see Pricing Engine) |
| **Two Zustand stores, tokens in localStorage** | Minimal state plumbing for an internal tool | Auth state isn't httpOnly-cookie hardened |
| **Backend code bind-mounted in dev** | Hot-reload without rebuilds | Needs the anonymous `/app/venv` volume to avoid host-venv shadowing |

---

## 13. Known limitations & future work

From the spec's roadmap (§14) and the current code:

- **Geometry is rectangles-only (v1).** Arches, curves, L-shapes are fabricated in
  reality and planned for v2.
- **Section depth is not deducted** from child regions for pricing (matches current
  industry formulas; a future refinement may add it).
- **Reads are shared org-wide** (writes/deletes are role- and creator-scoped via
  `services/access.py`); true multi-tenant scoping is future work.
- **Bay windows / fanlight 3D** are modeled as flags/extras, not true 3D.
- **Deferred door features** — jali on the back of a double-rebate door, finer
  door-leaf panel make-up (§4A.7).
- **Pricing covers materials + hardware only** — no labor/transport/installation
  charges, no glass cost (₹0 label by spec), no margins.
- **Schema management** — Alembic migrations exist (`backend/migrations/versions/`,
  0001+); dev startup additionally runs `create_all` as a convenience. Production
  applies `alembic upgrade head` (see [DEPLOY.md](./DEPLOY.md)).

---

### See also

- [Domain Model](./DOMAIN_MODEL.md) — the concepts in depth
- [Pricing Engine](./PRICING_ENGINE.md) — the cost math, with worked examples
- [Backend Reference](./BACKEND.md) · [Frontend Reference](./FRONTEND.md) ·
  [Development & Operations](./DEVELOPMENT.md)
- [`directives/design_rules_spec.md`](../directives/design_rules_spec.md) — the normative spec
