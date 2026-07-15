# SteelCAD — Frontend Reference

> React single-page app: structure, routing, state, the canvas editor, and the API
> client. For the overall data flow, read [Architecture §8](./ARCHITECTURE.md#8-frontend-internals).

---

## 1. Stack

| Concern | Library |
|---|---|
| UI | React 19 |
| Build/dev server | Vite |
| Canvas | Konva + react-konva |
| State | Zustand (one persisted, one transient store) |
| HTTP | Axios (JWT interceptors) |
| Routing | react-router-dom v7 |
| Notifications | react-hot-toast |
| Icons | lucide-react |

---

## 2. Layout

```
frontend/src/
├── main.jsx              React root (wrapped in ErrorBoundary)
├── App.jsx               Router + route guards (ProtectedRoute, RoleRoute)
├── index.css            Design-system tokens + layout (CSS grid editor shell)
├── api/client.js         Axios instance + interceptors + typed API namespaces
├── store/
│   ├── authStore.js      auth state (persisted) + login/logout/fetchMe
│   └── editorStore.js    the design tree, undo/redo, geometry engine, live price
├── hooks/useThumbnail.js  schematic SVG loader (designs + estimate frames)
├── lib/
│   ├── validators.js     client-side mirror of INV-*/V-* rules (live feedback)
│   ├── canvasDraw.jsx    static tree renderer (thumbnails/previews)
│   └── format.js         fmtFtIn / parseFt / dimLabel (ft-in display + input parsing)
├── components/
│   ├── DesignCanvas.jsx   Konva canvas: render, zoom/pan, drag interactions
│   ├── PropertiesPanel.jsx editors for the selected region
│   ├── NewDesignModal.jsx  create-design dialog
│   ├── ConfirmModal.jsx    useConfirm() dialog hook (replaces window.confirm)
│   ├── ErrorBoundary.jsx   top-level render-error fallback
│   └── TopNav.jsx          top navigation
└── pages/
    ├── LoginPage.jsx             (accounts are invite-only — no register page)
    ├── HomePage.jsx              dashboard + global estimate search
    ├── CustomersPage.jsx · CustomerDetailPage.jsx
    ├── EstimateBuilderPage.jsx   the frames table, terms, status, PDF/BOM
    ├── EditorPage.jsx            the canvas workspace (library + frame modes)
    ├── DashboardPage.jsx         the design library (SVG thumbnails)
    ├── RatesPage.jsx · UsersPage.jsx · SettingsPage.jsx   admin/owner
    └── ActivityPage.jsx · TrashPage.jsx                   admin/owner
```

Vitest suites (`*.test.js(x)`) live beside their sources (`npx vitest run`).

---

## 3. Routing & guards (`App.jsx`)

| Route | Page | Guard |
|---|---|---|
| `/login` | Login (accounts are invite-only) | public |
| `/` | HomePage (dashboard + search) | auth |
| `/customers` | CustomersPage | auth |
| `/customers/:id` | CustomerDetailPage | auth |
| `/estimates/:id` | EstimateBuilderPage | auth |
| `/estimates/:estimateId/frames/:frameId` | EditorPage (frame mode) | auth |
| `/designs` | DashboardPage (library) | auth |
| `/designs/:id` | EditorPage (library mode) | auth |
| `/rates` | RatesPage | **admin/owner** |
| `/users` | UsersPage (invite, roles, resets) | **admin/owner** |
| `/settings` | SettingsPage (company profile) | **admin/owner** |
| `/activity` | ActivityPage (audit feed) | **admin/owner** |
| `/trash` | TrashPage (restore soft-deleted) | **admin/owner** |

`ProtectedRoute` redirects unauthenticated users to `/login`; `RoleRoute` redirects
users lacking the required role to `/`. On boot, `App` calls `fetchMe()` to revalidate
the persisted session.

---

## 4. State stores

### `authStore` (persisted)
Holds `user` and `isAuthenticated`; exposes `login/logout/fetchMe`. The JWTs
themselves live in `localStorage` (read by the Axios interceptor), while the store
persists only `{user, isAuthenticated}` under the key `steelcad-auth`.

### `editorStore` (the heart of the editor)
Owns the design under edit and **all geometry logic**:

- **State** — `tree`, `designId`, `designName`, `isDirty`, `past`/`future` (undo/redo,
  capped at 50), `selectedId`, `addMode` (null | `vertical` | `horizontal`),
  `_snapshot` (drag batching), `livePrice`.
- **Factories** — `makeLeafRegion`, `makeDoorRegion`, `makeWindowRegion`,
  `makeEmptyTree`; `doorHingeCount(height)` for auto-seeded door hinges.
- **Geometry** — `relayout(tree)` recomputes all `x/y/width/height` top-down from the
  frame size + split ratios (idempotent; rounds float drift via `_clean`).
  `snapOffset` snaps splits to a 0.25 ft grid with a 0.5 ft minimum each side.
- **Mutations** — `splitRegion`, `setSplitPosition`, `setFrameSize`, `updateRegion`,
  `collapseRegion`, `addWindowToDoor`. All route through **`_commit`** (push undo, clear
  redo, set dirty). Drags use `beginInteraction`/`endInteraction` to collapse into one
  undo step.

> `editorStore.js` is the frontend mirror of the backend geometry rules — keep it in
> sync with the spec when region semantics change.

---

## 5. The API client (`api/client.js`)

A single Axios instance with two interceptors:

- **Request** — attaches `Authorization: Bearer <access_token>` from `localStorage`.
- **Response** — on **401**, transparently calls `/auth/refresh`, swaps in new tokens,
  and **replays** the original request. Concurrent 401s queue behind a single refresh.
  If refresh fails, it clears storage and redirects to `/login`.

Typed namespaces wrap the endpoints: `authApi`, `designsApi`, `customersApi`,
`estimatesApi`, `ratesApi`, plus the standalone `pricePreview(tree)` used by the editor.

In dev, requests are same-origin and Vite's proxy
([`vite.config.js`](../frontend/vite.config.js)) forwards `/auth`, `/designs`,
`/customers`, `/estimates`, `/price`, `/rates`, `/health` to `http://localhost:8000`. In
prod, nginx serves the bundle and reverse-proxies the API.

---

## 6. The editor (`EditorPage.jsx`)

The workspace is a 3-column CSS grid: legend/validation/pricing on the left, the canvas
center, the properties panel right.

- **Two modes.** `frameMode` (URL has a `frameId`) edits an estimate frame; otherwise it
  edits a library design. Loading and saving branch on this.
- **Canvas sizing.** A `ResizeObserver` measures the canvas cell and feeds
  `width`/`height` to `DesignCanvas`, so the Stage always fills the available area.
- **Live price.** A **600 ms debounced** effect posts the current tree to `/price` and
  stores the result in `livePrice`, which drives the price chip and the breakdown panel.
- **Live validation.** `validateTree(tree)` runs on every change; issues render as
  clickable warnings that select the offending region.
- **Undo/redo & shortcuts.** `Ctrl/Cmd+Z`, `Ctrl/Cmd+Shift+Z` / `Ctrl+Y`; `Esc` exits
  add-mullion mode.

---

## 7. The canvas (`DesignCanvas.jsx`)

A Konva `<Stage>`/`<Layer>` that **projects** the store's tree — it reads geometry and
maps feet ↔ pixels; it owns no geometry of its own.

### Coordinate & view model
- A `view = { scale, tx, ty }` transform: `screen = feet × scale + translation`.
  `px/py` map feet→pixels; `toFeetX/Y` map back. All hit-testing and drag math go
  through these, so zoom/pan need **no** Konva stage transform (keeping drag math
  unchanged).
- **Default fit** — `fitScale` fits the frame to the viewport but never exceeds true
  size (60 px/ft): big frames shrink, small frames stay at true size.
- **Zoom/pan** — mouse-wheel zooms toward the cursor; dragging empty canvas pans; a
  bottom-right toolbar offers −/100%/+/Fit. A pan-drag is distinguished from a click so
  panning doesn't clear the selection.

### Interactions
- **Mullions** are draggable rects with a `dragBoundFunc` clamping them within the parent
  region (minus the 0.5 ft minimum). Drag drives `setSplitPosition`; double-click drives
  `collapseRegion`.
- **Frame handles** (right/bottom/corner) drive `setFrameSize`.
- **Add mode** shows a dashed ghost line previewing a split; clicking places it via
  `splitRegion`.
- **Selection** — clicking a region selects it; clicking empty space (a click, not a
  pan) deselects.

### Visual language
Helper components render domain symbols: `DoorSwing` (the hinge-side swing triangle),
`ConcreteBase` (the in-concrete base hatch for door products), `VoidHatch` (diagonal
hatch on empty `open` regions), and `GrillOverlay` (MS crosshatch / SS horizontal bars).
SS bars come from `lib/grill.js` — the shared bar-count/offset math (mirrored by the
backend's `services/grill.py`), so the drawn bars are exactly the billed bars,
distributed evenly across the region — `gap = height / (bars + 1)` (spec §6.2).
Region dimension labels use `dimLabel` (height×width, decimals cleaned).

---

## 8. The properties panel (`PropertiesPanel.jsx`)

Context-sensitive editors for the selected region, each writing back via `updateRegion`:

- **Type** — `open`/`fixed`/`shutter`/`door`/`louver`; switching type resets dependent
  fields per spec §10.3: shutter/door auto-add hinges (R-4/R-5), and the grill overlay
  survives only onto `fixed`/`shutter` (removed for open/louver/door).
- **Pane** — shutter material, infill (none/glass/jali), beading (gated on infill).
  Shutter regions get a **Shuttering** toggle (single / double, spec §5.7): double shows
  per-side editors (glass-side material + beading, jali-side material + beading), forces
  glass infill, and auto-adds a jali-side (`side: "back"`) hinge set; back to single
  clears the jali fields and strips back-side hardware.
- **Grill** — none / MS square (leaf only) / SS round / SS square; offered on
  fixed/shutter leaves and branches (SS continuity). SS grills show the live billed
  bar count + RFT with a −/+ stepper for the manual `barAdjust` delta (spec §6.2A,
  clamped to 1 bar … one-per-2"; reset-to-auto when adjusted).
- **Hardware** — add/remove hinges and (door-only) locks; front/back groups for
  double-rebate doors ("Front side" / "Other side") and double shutters
  ("Glass shutter" / "Jali shutter").
- **Door options** — hand (left/right) and rebate (single/double).
- **Add window to door** — guided helper to carve a side/top window off a door.
- **Split** — direction + position to subdivide a leaf.

---

## 9. Estimate builder (`EstimateBuilderPage.jsx`)

The frames table for an estimate. Each row shows a frame's name, dimensions, section,
quantity, unit price, and amount, with **inline editing**: click the name to rename;
section/gauge are dropdowns that patch the frame's `tree_json` and reprice. Below, the
commercial terms (discount, advance) and the rolled-up totals. Two PDF actions:
**Download PDF** streams the internal quotation (per-frame cost breakdowns + BOM, for
cross-checking) and **Customer PDF** streams the customer-facing summary
(`/estimates/{id}/pdf/customer` — frame cards with specs and per-frame prices, no cost
breakdown, saved as `SteelCAD_Quotation_…`). The **Add Frame** modal creates a one-off
(new window/door with dimensions + section/gauge) or pulls a copy from the design
library.

---

## 10. Display formatting (`lib/format.js`)

- `fmtFtIn(n)` — feet-and-inches display, the app-wide dimension format
  (`5.5 → "5'6\""`, `5 → "5'"`, `0.75 → "9\""`). Geometry is grid-aligned to
  0.25 ft so inches are always whole; rounding to the nearest inch also absorbs
  float drift.
- `parseFt(str)` — parses a dimension input into decimal feet; accepts decimal
  feet (`5.5`), ft-in in common spellings (`5'6"`, `5' 6`, `5ft 6in`), inches
  only (`66"`), and smart quotes. Returns `null` on garbage.
- `fmtFt(n)` — legacy decimal formatting: rounds off float drift (2 dp) and drops
  trailing zeros (`4.7499999… → "4.75"`, `4.0 → "4"`).
- `dimLabel(region)` — region dimensions in **height × width** order (fabrication
  convention), ft-in formatted. Used by the canvas labels, the properties header,
  and validation messages for consistency.

`components/DimensionInput.jsx` wraps `fmtFtIn`/`parseFt` into a text input that
commits on blur/Enter and reverts on Escape or unparseable input — every
dimension field (new design/frame modals, frame size, split offset) uses it.

> The backend mirrors `fmtFtIn` with `app/services/units.py::fmt_ft_in`, used by
> pricing breakdowns, PDF frame dimensions, and diagram labels — so the editor,
> the API, and the PDFs agree on presentation. Keep the two in sync.

---

## 11. Editor conveniences

- **Exact dimension entry** — frame width/height are editable in the properties
  panel (no selection) and by clicking the frame size labels on the canvas;
  clicking a mullion selects it (panel shows an offset-from-left/top field) and
  its blue side labels are click-to-type. All entries snap to the 3" grid.
- **Dimension labels** — every region shows its H×W label by default; the
  **Dims** button in the tool palette toggles them.
- **Copy/paste** — Ctrl+C / Ctrl+V per region, plus **Ctrl+Shift+V** (or the
  panel button) to apply the copied spec to *every* leaf of the same region
  type in one undo step (`pasteOntoAllSimilar`).
- **Saving** — Ctrl+S everywhere; estimate frames also autosave (1.5 s debounce,
  only when client validation passes, skipped when the estimate is locked).
  Library designs stay manual-save. **Save to Library** in frame mode copies the
  frame's tree into the reusable design library via `POST /designs`.
