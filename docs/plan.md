# SteelCAD — Professional Designing & Quoting Platform Upgrade

## Context

SteelCAD is a full-stack app (FastAPI + SQLAlchemy async + Postgres / React 19 + Zustand + Konva) for designing steel doors/windows on a canvas and producing GST-inclusive quotes with PDFs. The working tree already holds a coherent uncommitted governance tier (audit trail, soft delete, access control, company settings, quote lifecycle, rate limiting).

A three-way audit (backend, frontend, repo state) found the codebase solid — several initially flagged "critical bugs" were verified false positives (`get_db()` commits per request, so deletes persist; relationships are eager-loaded, so no N+1s; rate updates already validate `gt=0`). The **verified real issues** are: an estimate list query that loads every frame's full `tree_json` just for a count and has no pagination; no rate limit on CPU-heavy PDF generation; estimates of soft-deleted customers still listed; silently swallowed live-pricing errors in the editor; no server-side max bounds on design trees; hardcoded GST 18% / advance 50% / ₹; no way to discover soft-deleted records; no business dashboard; and major test gaps (estimate CRUD/lifecycle untested; frontend has only validator tests).

User approved: all four upgrade areas, commit the current tier as baseline first, testing depth = backend integration + frontend component tests.

## Phase 0 — Baseline commit

1. Start Postgres (`docker-compose up -d db`), set `TEST_DATABASE_URL` (create `steelcad_test` DB if missing).
2. Run `python -m pytest backend/tests -v` and `npm test` in `frontend/` — confirm green.
3. Commit the entire uncommitted working tree on branch `updates` as the baseline.

## Phase 1 — Bug fixes & hardening (one commit)

1. **Estimate list pagination + no tree_json load** — [backend/app/routers/estimates.py](backend/app/routers/estimates.py#L218-L242) `list_estimates`: add `limit` (default 50, max 200) / `offset` / `q` params; 404 if customer missing or soft-deleted (also fixes the deleted-customer leak); use `.options(noload(Estimate.frames))` + correlated `COUNT` scalar subquery for `frame_count` (frames are `lazy="selectin"` — without `noload` every frame's JSONB loads). Factor as `_summary_stmt()` for reuse in Phase 4. Frontend: pass params through `estimatesApi.listForCustomer`.
2. **PDF rate limit** — `@limiter.limit("10/minute")` + `request: Request` on `download_estimate_pdf` (pattern already on `price_preview`).
3. **Stale-price indicator** — [frontend/src/pages/EditorPage.jsx](frontend/src/pages/EditorPage.jsx#L274-L286): on pricing fetch failure keep old price, set `priceStale`, render amber "price outdated" chip with retry.
4. **Max-bounds tree validation** — new `validate_tree_bounds()` in [backend/app/services/validation.py](backend/app/services/validation.py): width ≤ 30 ft, height ≤ 20 ft, max depth 8, max 200 nodes, iterative walk. Call from `validate_design_tree` and directly in `price_preview` (bounds-only, since preview prices in-progress trees).
5. **sort_order race (cheap)** — `_get_estimate_or_404(..., for_update=True)` using `.with_for_update(of=Estimate)` in `add_frame`/`duplicate_frame`. If `of=` conflicts with the `joinedload`, drop the lock and document (cosmetic race) — don't burn time.
6. **Audit transaction hardening** — [backend/app/services/audit.py](backend/app/services/audit.py): wrap add+flush in `async with db.begin_nested()` so a failed audit write can't poison the caller's transaction (logging already exists).

Tests: pagination/404/frame_count cases; PDF 429 after 11 calls (monkeypatch `generate_estimate_pdf` — avoids WeasyPrint/GTK on Windows); new `backend/tests/test_validation.py` for bounds (pure, no DB); `/price` 422 on oversized tree.

## Phase 2 — Configurable GST / advance / currency (one commit)

- **Migration `0009_commercial_settings.py`**: `company_settings` gains `gst_pct` (default 18), `default_advance_pct` (default 50), `currency_symbol` (default ₹); `estimates` gains `gst_pct` (default 18) — a per-estimate snapshot, same reproducibility philosophy as `rate_snapshot`.
- [backend/app/services/pricing.py](backend/app/services/pricing.py): `gst_pct: float = 18.0` param on `_apply_commercial_terms` / `price_design` / `price_estimate`; replace `taxable * 0.18`.
- [backend/app/routers/estimates.py](backend/app/routers/estimates.py): `create_estimate` snapshots company `gst_pct` and falls back to `default_advance_pct` when `advance_pct` omitted (`EstimateCreate.advance_pct` becomes optional); `_recompute` uses the **frozen** `estimate.gst_pct` (a GST settings change never silently reprices existing estimates); `duplicate_estimate` snapshots current settings.
- PDF ([backend/app/services/pdf.py](backend/app/services/pdf.py) + template): dynamic `GST ({{ gst_pct }}%)` label and company currency symbol.
- Frontend: "Commercial defaults" card in SettingsPage; EstimateBuilder GST label uses `est.gst_pct`. Frontend ₹ helpers deferred (backend/PDF — what customers see — honor the symbol).

Tests: `gst_pct=12` math in `test_pricing.py`; settings change → new estimate uses 12%, existing estimate keeps 18% through recompute; advance fallback.

## Phase 3 — Professional quoting features (independent commits)

### 3.1 Quote revisions — duplicate-as-revision, superseded parent
Chosen over status-based reopen because reopening mutates what the customer was actually sent; reuses the proven `duplicate_estimate` machinery and the existing finalization lock makes superseded immutable for free.
- **Migration `0010_estimate_revisions.py`**: `estimates.revision` int default 1, `parent_id` UUID FK (SET NULL), `accepted_at` timestamp (for dashboard revenue), drop unique on `number` (read constraint name from `0003_unique_estimate_number.py` first), add `UNIQUE(number, revision)`.
- New `POST /estimates/{id}/revise`: 409 on draft ("edit directly") or superseded ("revise latest"); copies via factored `_copy_estimate()`; same number, `revision+1`, `parent_id`, status draft, fresh `quote_date` + company `gst_pct`; nested-transaction retry on the unique constraint; source → `superseded`; audit `estimate.revise`.
- Status `superseded` added; cannot be set manually or transitioned away from. `set_estimate_status` sets `accepted_at` when moving to accepted. Reopen-to-draft stays for "sent by mistake" — UI copy must distinguish it from Revise.
- Frontend: "EST-0007 rev 2" display, Revise button on locked estimates (navigates to new draft), superseded banner, rev/superseded badges in customer estimate list. PDF filename/header include rev.

### 3.2 Auto-expiry — derived flag, no cron
`is_expired = status == "sent" and valid_until < today`, computed at read time in `_detail` and list endpoints (self-correcting when `valid_until` edited; no scheduler). Accepting an expired quote stays allowed. Frontend: orange `expired` badge + "consider revising" hint.

### 3.3 Trash view
- New `backend/app/routers/trash.py`: `GET /trash` (admin/owner) returning soft-deleted customers/designs/estimates (limit 100 each, estimates via `_summary_stmt`). Register in `main.py`.
- Guard: restoring an estimate whose customer is deleted → 409 "Restore the customer first". Add missing `record_audit` calls to all three existing restore endpoints.
- Frontend: `TrashPage.jsx` at `/trash` (admin/owner route), TopNav link, restore buttons; add `/trash` to Vite proxy.

### 3.4 BOM CSV export
`GET /estimates/{id}/bom.csv` reusing [backend/app/services/bom.py](backend/app/services/bom.py) `build_bom`; `csv.writer` + UTF-8 BOM (Excel ₹ handling); "BOM CSV" button next to Download PDF.

Tests: revise flow (rev 2 draft, parent superseded, 409 cases, unique constraint, audit row, repriced totals); expiry derivation; trash list + role 403 + restore-order 409 + audit; BOM CSV content/aggregation.

## Phase 4 — Business dashboard + estimates search (one commit)

Customers/designs search already exists — remaining work is estimates search + dashboard.
- New `backend/app/routers/dashboard.py`: `GET /dashboard/metrics` — pipeline `GROUP BY status` (counts + `SUM(grand_total)`, excluding deleted/superseded and deleted customers), monthly accepted revenue via `date_trunc('month', accepted_at)` last 6 months, active customer/design counts, 5 recent estimates.
- Global `GET /estimates?q=&status=&limit=&offset=` — ILIKE on title + customer name, numeric `q` also matches number; reuses `_summary_stmt`.
- Frontend routing: `/` → new `HomePage.jsx` (dashboard); Customers moves to `/customers`; design library stays at `/designs`. Update `App.jsx`, `TopNav.jsx`, and `navigate('/')` references in CustomersPage.
- `HomePage.jsx`: status metric cards, monthly revenue as simple CSS bars (no chart dep), recent-estimates table, debounced (300 ms) global quote search — same pattern as CustomersPage.

Tests: metrics math with mixed seeded statuses; search by title/customer/number; status filter; pagination.

## Phase 5 — UX & editor polish (one commit)

- **Design thumbnails**: `GET /designs/{id}/thumbnail.svg` reusing [backend/app/services/diagram.py](backend/app/services/diagram.py) `tree_to_svg`, with `Cache-Control` + ETag/304. `<img>` can't carry the JWT, so a `useThumbnail` hook fetches via axios as blob → object URL, cached in a module Map keyed `id:updated_at`. Render in design library cards.
- **Modal responsiveness**: shared `.modal-card { width: min(var(--modal-w,520px), calc(100vw - 32px)); max-height: 90vh }` in `index.css`, applied to AddFrame/NewDesign/ChangePassword/Confirm/customer modals (replacing fixed inline widths).
- **Canvas keyboard access (minimal)**: `listLeafIds(tree)` in editorStore; Tab/Shift+Tab + arrow keys cycle region selection in EditorPage keydown handler; canvas wrapper `tabIndex={0}` `role="application"`.

Tests: thumbnail content-type/404/304; `listLeafIds` unit test.

## Phase 6 — Test infrastructure + final verification (one commit)

- Add `@testing-library/react` + `jest-dom` + `user-event`, `setupTests.js`, wire `test.setupFiles` in `vite.config.js` (currently empty).
- Vitest suites: `editorStore.test.js` (splitRegion, collapseRegion, setFrameSize, undo/redo, copy/paste, door-vs-window defaults); `EstimateBuilderPage.test.jsx` (totals rows incl. dynamic GST label, locked banner, expired badge — mocked API); `HomePage.test.jsx` (metrics render, search debounce with fake timers).
- Split backend tests into `test_estimates.py`/`test_dashboard.py` if `test_api.py` exceeds ~800 lines. CI needs no structural change (Postgres service already configured).

## Testing criteria (approval summary)

**Backend (pytest, Postgres via TEST_DATABASE_URL, auto-skip without it):** estimate CRUD + lifecycle + finalization lock, revision flow incl. concurrency constraint, expiry derivation, soft-delete/trash/restore incl. role 403s and restore-order 409, pagination + search, GST snapshot propagation and immutability through recompute, BOM CSV, thumbnail endpoint, audit rows for every mutating action, tree bounds validation, PDF rate limit (mocked renderer).
**Frontend (Vitest + Testing Library):** editorStore mutation/undo-redo invariants, EstimateBuilder totals/lock/expiry rendering, HomePage metrics + debounce, `listLeafIds`.
**Manual/E2E checklist:** `alembic upgrade head` (0008→0010) + downgrade on a dev-DB copy; pre-existing estimates show rev 1 / GST 18% / unchanged totals; browser flow create → send → revise → accept with PDF showing "rev 2" and configured GST; trash delete/restore per entity as owner + denied as sales; BOM CSV opens in Excel; `npm run lint && npm test && npm run build` green; editor Tab-cycling; modals usable at 375 px; CI green on `updates`.

## Risks / notes

- `with_for_update(of=Estimate)` may conflict with the customer joinedload — documented fallback is dropping the lock (cosmetic race only).
- Migration 0010 must reference the exact unique-constraint name created in 0003 — read it before writing the drop.
- PDF endpoint tests mock WeasyPrint (no GTK on Windows); CI on Ubuntu could add one real render test later.
- Rate limiter keys by IP — one office NAT shares the PDF limit; acceptable for a single shop.
- Frontend ₹ symbol config deferred (backend/PDF honor it).

## Critical files

`backend/app/routers/estimates.py`, `backend/app/services/pricing.py`, `backend/app/models/estimate.py`, `backend/app/services/validation.py`, `backend/migrations/versions/0009*/0010*`, `frontend/src/pages/EstimateBuilderPage.jsx`, `frontend/src/pages/EditorPage.jsx`, `frontend/src/api/client.js`, `frontend/src/App.jsx`, new: `backend/app/routers/trash.py`, `backend/app/routers/dashboard.py`, `frontend/src/pages/HomePage.jsx`, `frontend/src/pages/TrashPage.jsx`.
