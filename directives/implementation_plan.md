# SteelCAD — Implementation Plan

> A full-stack web app for designing and quoting steel doors/windows.
> Source of truth for the domain model: `directives/design_rules_spec.md`.

---

## Agreed Decisions

| Decision | Choice |
|---|---|
| **Frontend** | React + Vite |
| **Canvas renderer** | Konva.js (react-konva) |
| **Frontend state** | Zustand (tree-shaped design state, undo/redo) |
| **Backend** | FastAPI (Python) |
| **Database** | PostgreSQL |
| **Auth** | JWT (access + refresh tokens), full user accounts |
| **Data isolation** | Shared pool — all users see all designs |
| **Theme** | Light + dark mode with toggle |
| **PDF** | WeasyPrint (server-side, HTML → PDF) |
| **Deployment** | Docker-ready (platform-agnostic) |

---

## V1 Feature Scope

1. **Canvas editor** — draw splits, assign region types, set pane/grill/hardware
2. **Pricing engine** — full tree traversal, all cost formulas from spec §9
3. **Estimate view** — itemized breakdown with discount, GST, advance
4. **Design dashboard** — list, create, load, delete designs
5. **Rate management** — admin page to update material rates
6. **PDF export** — WeasyPrint-rendered professional quotation PDF

> **Not in v1:** collaborative editing, bay window 3D model, per-user data isolation, OAuth.

---

## Project Structure

```
SteelCAD/
├── backend/                  # FastAPI app
│   ├── app/
│   │   ├── main.py           # FastAPI entry point
│   │   ├── config.py         # Settings (DB URL, JWT secret, etc.)
│   │   ├── database.py       # SQLAlchemy async engine + session
│   │   ├── models/           # SQLAlchemy ORM models
│   │   │   ├── user.py
│   │   │   ├── design.py
│   │   │   ├── estimate.py
│   │   │   └── rate.py
│   │   ├── schemas/          # Pydantic schemas (request/response)
│   │   │   ├── user.py
│   │   │   ├── design.py
│   │   │   ├── estimate.py
│   │   │   └── rate.py
│   │   ├── routers/          # API route handlers
│   │   │   ├── auth.py       # /auth/register, /auth/login, /auth/refresh
│   │   │   ├── designs.py    # /designs CRUD
│   │   │   ├── estimates.py  # /designs/{id}/estimate
│   │   │   └── rates.py      # /rates (admin)
│   │   ├── services/
│   │   │   ├── pricing.py    # The pricing engine (pure Python, no DB)
│   │   │   ├── pdf.py        # WeasyPrint PDF generation
│   │   │   └── auth.py       # JWT creation/validation
│   │   └── templates/        # Jinja2 HTML templates for PDF
│   │       └── estimate_pdf.html
│   ├── migrations/           # Alembic migrations
│   ├── tests/
│   │   └── test_pricing.py   # Unit tests for the pricing engine
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/                 # React + Vite app
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── store/
│   │   │   ├── designStore.ts     # Zustand: design tree, selected node
│   │   │   ├── authStore.ts       # Zustand: JWT tokens, user info
│   │   │   └── uiStore.ts         # Zustand: theme, sidebar state
│   │   ├── pages/
│   │   │   ├── LoginPage.tsx
│   │   │   ├── RegisterPage.tsx
│   │   │   ├── DashboardPage.tsx
│   │   │   ├── EditorPage.tsx     # Main canvas editor
│   │   │   ├── EstimatePage.tsx   # Estimate breakdown view
│   │   │   └── RatesPage.tsx      # Admin rate management
│   │   ├── components/
│   │   │   ├── canvas/
│   │   │   │   ├── DesignCanvas.tsx       # Konva Stage + Layer
│   │   │   │   ├── RegionRect.tsx         # Konva Rect for a region
│   │   │   │   ├── SplitLine.tsx          # Konva Line for a split (draggable)
│   │   │   │   ├── GrillOverlay.tsx       # Konva pattern overlay
│   │   │   │   └── DimensionLabels.tsx    # Konva Text labels
│   │   │   ├── panels/
│   │   │   │   ├── PropertiesPanel.tsx    # Right sidebar: region/design props
│   │   │   │   ├── PaneSpecEditor.tsx     # Pane spec form (infill, beading)
│   │   │   │   ├── GrillEditor.tsx        # Grill type + material selector
│   │   │   │   └── HardwareEditor.tsx     # Hinge/lock controls
│   │   │   ├── layout/
│   │   │   │   ├── Sidebar.tsx
│   │   │   │   ├── Toolbar.tsx            # Split tool, region type selector
│   │   │   │   └── ThemeToggle.tsx
│   │   │   └── shared/
│   │   │       ├── Button.tsx
│   │   │       ├── Modal.tsx
│   │   │       └── EstimateBreakdown.tsx
│   │   ├── api/               # Typed API client (fetch wrappers)
│   │   │   ├── client.ts      # Base fetch with JWT injection
│   │   │   ├── designs.ts
│   │   │   ├── estimates.ts
│   │   │   └── rates.ts
│   │   ├── lib/
│   │   │   ├── tree.ts        # Pure tree manipulation helpers
│   │   │   ├── geometry.ts    # Dimension derivation (top-down pass)
│   │   │   └── validators.ts  # Client-side invariant checks (INV-1..10)
│   │   └── styles/
│   │       ├── index.css      # CSS variables, reset, typography
│   │       └── themes.css     # Light/dark mode CSS variables
│   ├── index.html
│   ├── vite.config.ts
│   └── Dockerfile
│
├── docker-compose.yml         # PostgreSQL + backend + frontend
├── directives/
│   └── design_rules_spec.md  # Source of truth (existing)
└── .env                       # Environment variables
```

---

## Backend — FastAPI

### Technology Choices
- **FastAPI** + **Uvicorn** (async ASGI server)
- **SQLAlchemy 2.0** (async ORM) + **asyncpg** (PostgreSQL async driver)
- **Alembic** (database migrations)
- **Pydantic v2** (validation and serialization)
- **python-jose** (JWT)
- **passlib[bcrypt]** (password hashing)
- **WeasyPrint** (PDF generation)
- **Jinja2** (HTML templating for PDF)

### Data Models

#### `users`
```
id          UUID PK
email       VARCHAR UNIQUE NOT NULL
password    VARCHAR NOT NULL (bcrypt hash)
is_admin    BOOLEAN DEFAULT false
created_at  TIMESTAMP
```

#### `designs`
```
id              UUID PK
name            VARCHAR NOT NULL
description     TEXT
tree_json       JSONB NOT NULL    — the full geometry tree
outer_width     NUMERIC(6,2)
outer_height    NUMERIC(6,2)
section_size    VARCHAR(4)        — "5" | "6" | "10"
gauge           VARCHAR(4)        — "18G" | "16G"
created_by      UUID FK → users.id
created_at      TIMESTAMP
updated_at      TIMESTAMP
```

#### `estimate_versions`
```
id              UUID PK
design_id       UUID FK → designs.id
version_number  INTEGER
rate_snapshot   JSONB NOT NULL    — frozen copy of all rates at generation time
breakdown_json  JSONB NOT NULL    — full itemized breakdown
subtotal        NUMERIC(10,2)
discount_type   VARCHAR           — "PERCENTAGE" | "FLAT"
discount_value  NUMERIC(10,2)
taxable         NUMERIC(10,2)
gst             NUMERIC(10,2)
grand_total     INTEGER           — nearest rupee
advance_pct     NUMERIC(5,2)
created_at      TIMESTAMP
```

#### `rates`
```
id          UUID PK
item_code   VARCHAR UNIQUE NOT NULL   — e.g. "SECTION_5_18G"
rate        NUMERIC(10,2) NOT NULL
unit        VARCHAR NOT NULL          — "per RFT" | "per sqft" | "per piece"
label       VARCHAR NOT NULL          — human-readable
updated_at  TIMESTAMP
```

### API Endpoints

```
POST   /auth/register            → create user
POST   /auth/login               → return access + refresh token
POST   /auth/refresh             → exchange refresh → new access token
GET    /auth/me                  → current user info

GET    /designs                  → list all designs (paginated)
POST   /designs                  → create new design
GET    /designs/{id}             → get design by ID
PUT    /designs/{id}             → update design (full tree replace)
DELETE /designs/{id}             → delete design

POST   /designs/{id}/estimate    → run pricing, create EstimateVersion, return breakdown
GET    /designs/{id}/estimates   → list estimate versions for a design
GET    /estimates/{id}           → get specific estimate version
GET    /estimates/{id}/pdf       → download PDF (WeasyPrint)

GET    /rates                    → list all rates
PUT    /rates/{item_code}        → update a rate (admin only)
POST   /rates/seed               → seed default rates from spec §9.2 (admin only)
```

### Pricing Engine (`services/pricing.py`)

Pure Python module — no DB access, no side effects. Takes the design tree JSON + rate lookup dict and returns the full breakdown. Fully unit-testable.

Key functions:
```python
def price_design(tree: dict, rates: dict, discount_type: str, discount_value: float, advance_pct: float) -> EstimateBreakdown
def compute_frame_cost(frame: dict, section_rate: float) -> LineItem
def compute_split_costs(tree: dict, section_rate: float) -> list[LineItem]
def compute_region_costs(region: dict, rates: dict) -> RegionBreakdown
def compute_pane_cost(region: dict, rates: dict) -> float
def compute_grill_cost(overlay: dict, region: dict, rates: dict) -> float
def compute_hardware_cost(hw: dict, rates: dict) -> float
```

---

## Frontend — React + Vite

### Canvas Architecture (Konva.js)

The canvas renders the design tree as nested Konva shapes:

```
Stage
└── Layer
    ├── RegionRect[] (filled rectangles, click to select)
    ├── SplitLine[] (draggable lines, on drag end → update split.position)
    ├── GrillOverlay[] (pattern lines on grilled regions)
    ├── DimensionLabels[] (Text nodes showing width/height in ft)
    └── SelectionHighlight (rect stroke on selected region)
```

**Coordinate system**: The canvas uses a pixel-space viewport. Feet ↔ pixels conversion: `pixels = feet × SCALE_FACTOR` (e.g., 80px/ft).

**Split dragging**: SplitLine is a Konva.Line with `draggable=true`. On `dragmove`, it clamps to min 0.5ft from edges. On `dragend`, updates `split.position` ratio in Zustand store.

**Region click**: Clicking a RegionRect selects it and opens the PropertiesPanel.

**Add split**: Toolbar button, then click on a leaf region to trigger the split modal (choose direction + initial position).

### Zustand Store Shape (`designStore.ts`)

```typescript
interface DesignStore {
  design: Design | null;          // full tree (mirrors backend JSON)
  selectedNodeId: string | null;
  history: Design[];              // for undo
  historyIndex: number;
  
  // Actions
  loadDesign: (design: Design) => void;
  updateDesign: (patch: Partial<Design>) => void;
  selectNode: (id: string | null) => void;
  addSplit: (regionId: string, direction: 'horizontal' | 'vertical', position: number) => void;
  removeSplit: (regionId: string) => void;
  updateRegion: (regionId: string, patch: Partial<Region>) => void;
  setRegionType: (regionId: string, type: RegionType) => void;
  setPaneSpec: (regionId: string, spec: PaneSpec) => void;
  addGrillOverlay: (regionId: string, overlay: GrillOverlay) => void;
  removeGrillOverlay: (regionId: string) => void;
  setHardware: (regionId: string, hardware: Hardware[]) => void;
  undo: () => void;
  redo: () => void;
}
```

### Tree Operations (`lib/tree.ts`)

Pure functional operations on the design tree:
- `findNode(tree, id) → Node`
- `updateNode(tree, id, patch) → Tree` (immutable)
- `addSplit(tree, regionId, direction, position) → Tree`
- `removeSplit(tree, regionId) → Tree`
- `recomputeDimensions(tree) → Tree` (top-down dimension pass)
- `applyInvariants(tree) → ValidationResult`

### Theme System

CSS custom properties approach:
```css
:root[data-theme="light"] {
  --color-bg: #f8f9fa;
  --color-surface: #ffffff;
  --color-border: #dee2e6;
  --color-accent: #2563eb;
  /* ... */
}
:root[data-theme="dark"] {
  --color-bg: #0d1117;
  --color-surface: #161b22;
  --color-border: #30363d;
  --color-accent: #58a6ff;
  /* ... */
}
```

---

## PDF Export

WeasyPrint renders a styled HTML template to PDF server-side.

The estimate PDF will include:
- Header: company logo placeholder, date, design name
- Design summary: dimensions, section size, gauge
- Itemized cost table: frame, splits (mullions/transoms), each region's costs, grill, hardware
- Subtotal → discount → taxable amount → GST (18%) → **Grand Total**
- Advance payment amount

---

## Auth Flow

- `POST /auth/register` → hash password, create user, return tokens
- `POST /auth/login` → verify password, return `access_token` (15min) + `refresh_token` (7d)
- `POST /auth/refresh` → validate refresh token, return new access token
- All protected routes require `Authorization: Bearer <access_token>`
- Frontend: Zustand `authStore` holds tokens. Axios/fetch interceptor auto-refreshes on 401.

---

## Phased Delivery Plan

### Phase 1 — Foundation (Backend)
1. Project scaffold (FastAPI + Docker Compose with PostgreSQL)
2. Database models + Alembic migrations
3. Auth endpoints (register, login, refresh)
4. Rates model + seed endpoint (all rates from spec §9.2)
5. Design CRUD endpoints
6. Pricing engine — pure Python unit-testable module
7. Estimate endpoint (runs pricing, stores version)

### Phase 2 — Canvas (Frontend)
1. Vite + React scaffold
2. CSS design system (tokens, light/dark, typography)
3. Auth pages (login, register)
4. Dashboard page (design list, create new, delete)
5. Editor page shell (Konva stage, sidebar, toolbar)
6. Design tree rendering (regions as rects, splits as draggable lines)
7. Region selection + properties panel (type, paneSpec, grill, hardware)
8. Live pricing (fetch estimate from backend on change)

### Phase 3 — Polish & Export
1. Estimate view page (full breakdown table)
2. PDF export (WeasyPrint template, download endpoint)
3. Rate management page (admin-only)
4. Grill visual overlays on canvas (crosshatch for MS, horizontal bars for SS)
5. Dimension labels on canvas
6. Undo/redo
7. Validation feedback (toast messages for V-1..V-15)

### Phase 4 — Production Readiness
1. Docker Compose production config
2. Environment variable management
3. CORS configuration
4. Basic error handling + logging
5. README and deployment docs

---

## Resolved Questions

- ✅ **Rate management**: Admin-only. Users table has `is_admin` flag. Only admins can update rates.
- ✅ **Design ownership**: Show "Created by: [name]" on dashboard. Users table has `name` field.
- ✅ **Bay window**: Skipped for v1. Not in schema.
- ✅ **Estimate versioning**: Show latest estimate only in v1. Backend still stores versions (immutable per PR-7).
