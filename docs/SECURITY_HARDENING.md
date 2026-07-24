# Pre-Deployment Security Hardening

**Date:** 2026-07-23 · **Scope:** backend auth, rate limiting, PDF rendering, input
validation, and geometry/pricing guards.

This is the **second hardening wave**. The first shipped in
[`Pre-deployment security hardening (#6)`](https://github.com/) — startup secret
validation, `APP_ENV=production` on the prod compose, nginx security headers + proxy-regex
fix, tighter rate limits, and TLS to the DB. That wave lives in the git history and
[`docs/DEPLOY.md`](DEPLOY.md); this document covers the changes made **after** it.

Related audits: [`docs/PRIVACY.md`](PRIVACY.md) (PII data map, log/response scrubbing,
account deletion) and [`docs/SECRET_SAFETY_AUDIT.md`](SECRET_SAFETY_AUDIT.md) (repo/history
secret scan). Observation #1 of the secret-safety audit — the unauthenticated
`bootstrap-admin` endpoint — is **closed** by this wave (see §2).

---

## Summary

| # | Area | Threat closed | Key files |
|---|---|---|---|
| 1 | Session invalidation | Leaked/old token outlives a password change or account deletion | `models/user.py`, `services/auth.py`, `routers/auth.py`, `routers/users.py`, migration `0013` |
| 2 | `bootstrap-admin` lockdown | Unauthenticated caller seizes admin during a zero-admin window | `config.py`, `routers/auth.py`, `execution/setup.py`, `docs/DEPLOY.md` |
| 3 | Rate-limit client identity | Reverse proxy collapses every user into one bucket → trivial DoS | `services/ratelimit.py` |
| 4 | PDF rendering | HTML injection + SSRF / local-file read via user-controlled fields | `services/pdf.py` |
| 5 | Input validation caps | Unbounded / malformed fields stored and rendered into PDFs | `schemas/customer.py`, `schemas/company.py`, `schemas/estimate.py`, `services/pricing.py` |
| 6 | Geometry & pricing guards | Mispricing from an inconsistent tree; 500s from malformed frames | `services/validation.py`, `routers/estimates.py`, `directives/design_rules_spec.md` |

All regression tests are pure (no DB, no WeasyPrint native libs) and run on the Windows
host: [`backend/tests/test_security.py`](../backend/tests/test_security.py), plus additions
to `test_pricing.py` and `test_validation.py`.

---

## 1. Session invalidation via a credential watermark

**Threat.** Access/refresh tokens were valid until expiry regardless of password changes.
A leaked token (or one held by a user whose password was just reset, or whose account was
deleted) stayed usable until it expired on its own — up to the refresh-token lifetime.

**Change.** Every `User` now carries a `password_changed_at` watermark
(`models/user.py`, migration `0013`, backfilled to `created_at` for existing rows). Both
token minters embed it as a `pwd` claim (integer microseconds):

- `create_access_token(user)` / `create_refresh_token(user)` now take the **user**, not a
  bare id, and stamp `pwd = _pwd_watermark(user)`.
- `get_current_user` and `POST /auth/refresh` reject any token whose `pwd` claim does not
  equal the user's current watermark (`token_watermark_matches`). A token minted **before**
  the claim existed has no `pwd` and is likewise rejected — upgrading forces one fresh login.
- `mark_password_changed(user)` bumps the watermark and is called on **every** credential
  event: self-service change (`PATCH /auth/change-password`), admin/owner reset
  (`POST /users/{id}/reset-password`), and account anonymization (`anonymize_user`).

Microsecond precision is deliberate — a token minted in the same wall-clock second as a
password change must not collide with the new watermark and survive revocation.

**Also.** The admin/owner password reset now writes an audit entry
(`user.password_reset`) — previously it did not.

**Tests.** `test_security.py`: fresh token validates; token rejected after change; refresh
token rejected after change; legacy (no-`pwd`) token rejected; watermark moves forward.

---

## 2. `POST /auth/bootstrap-admin` lockdown

**Threat.** The endpoint promoted an email to admin whenever **zero** admins existed, with
no authentication. Between first deploy and first setup, anyone who could reach the API
could seize admin. (This was observation #1 of the secret-safety audit.)

**Change.**

- New `BOOTSTRAP_ADMIN_SECRET` config (`config.py`), **empty by default → endpoint
  disabled**. The endpoint now requires the request to present that exact secret
  (`{"email": "...", "secret": "..."}`), compared in constant time (`secrets.compare_digest`).
  An unset server secret means "disabled", not "any secret works".
- The trusted first-run path no longer touches the HTTP endpoint at all.
  `execution/setup.py` creates the first user **and promotes them to admin directly in the
  DB** in one step (it has host-side docker access, which only an operator has). The old
  `promote_to_admin()` HTTP call is gone.
- [`docs/DEPLOY.md`](DEPLOY.md) rewritten: the recommended path is direct-DB admin creation;
  `bootstrap-admin` is documented as a disabled-by-default break-glass path, to be re-disabled
  (unset the env var) after any one-off use.

**Net:** on a fresh deploy the endpoint is inert unless an operator explicitly opts in.

---

## 3. Rate-limit key = real client IP behind the proxy

**Threat.** In production the backend port is **not** published — nginx is the only client,
and uvicorn is not told to trust that proxy hop. So Starlette's `request.client.host` (what
slowapi's stock `get_remote_address` returns) is **nginx's internal IP for every request**.
Keyed on that, all callers share one bucket: a single actor sending 5 login attempts/minute
exhausts the `5/minute` login limit **for the whole company** — an unauthenticated, low-effort
DoS. Same for the PDF (`10/minute`) and price (`120/minute`) limits.

**Change.** New `client_ip()` key function (`services/ratelimit.py`), wired into the shared
`Limiter`. It keys on nginx's authoritative `X-Real-IP` (nginx sets
`proxy_set_header X-Real-IP $remote_addr`, overwriting anything the client sent), and falls
back to the socket address in dev where there is no proxy. It deliberately does **not** parse
the leftmost `X-Forwarded-For`, which a client could spoof to rotate identity and dodge every
limit.

**Tests.** `test_security.py`: two clients through one proxy socket key on distinct IPs;
dev fallback to socket address; a client-prepended `X-Real-IP` tail is ignored.

**Follow-up (deploy rehearsal, 2026-07-24) — the guarantee stops at the *first* proxy.**
`client_ip()` trusts `X-Real-IP` because the bundled nginx sets it from `$remote_addr`.
That holds only while nginx is the edge. Add a second proxy in front for TLS — exactly
what [`DEPLOY.md`](DEPLOY.md) §7 recommends — and `$remote_addr` becomes *that* proxy's
address for every request, silently restoring the original single-bucket DoS while every
test still passes.

`frontend/nginx.conf` now closes this with the realip module: `set_real_ip_from` for the
private ranges (`10/8`, `172.16/12`, `192.168/16`, `127/8`) plus
`real_ip_header X-Forwarded-For` and `real_ip_recursive on`. A front proxy on the
Docker/host network is a trusted hop, so the original client address is recovered and
`$remote_addr` — and therefore `X-Real-IP` — is correct again. A caller reaching the
container directly from the public internet has a **public** source address, is not a
trusted hop, and so still cannot spoof identity via `X-Forwarded-For`.

Verified end-to-end against the production images: with the header set to `1.2.3.4`,
six rapid bad logins returned `429`; a request carrying `5.6.7.8` got a fresh bucket
(`401`) while `1.2.3.4` stayed limited.

> **Residual risk.** The private ranges are trusted wholesale. On a public VPS that is
> correct (external clients are public-addressed). If this container is ever exposed
> directly to an untrusted *private* network, narrow `set_real_ip_from` to the proxy's
> exact address — noted in `nginx.conf` and `DEPLOY.md` §7.1.

---

## 4. PDF rendering — HTML injection + SSRF / local-file read

**Threat.** User-controlled fields (customer name/address/notes, estimate terms, company
branding) flow straight into the quotation templates and are rendered by WeasyPrint. Two
problems:

1. The Jinja `Environment` did **not** autoescape → any authenticated user could inject HTML
   into the PDF.
2. WeasyPrint's default URL fetcher will resolve `file://` and `http(s)://` references — so an
   injected `<img src="file:///etc/passwd">` or `src="http://169.254.169.254/…">` becomes
   local-file disclosure or a blind SSRF **from the API host**.

**Change** (`services/pdf.py`, two layers):

- `_build_env()` builds the Jinja env with `autoescape=select_autoescape(["html","xml"])` and
  is used by **both** the internal and customer-facing renderers. Markup in a field is now
  rendered as inert text.
- `_data_only_url_fetcher()` permits **only** inline `data:` URIs and is passed to every
  `HTML(...).write_pdf()` call. The company logo (a `data:` URL) still works; every other
  scheme raises. See also §5 — the logo field is independently constrained to `data:image/`.

**Tests.** `test_security.py`: hostile `name`/`notes` are escaped; `file://`,
`http://169.254.169.254/…`, `https://internal/…`, and uppercase `FILE://` all raise in the
fetcher.

---

## 5. Input validation caps

**Threat.** Free-text fields were unbounded and, for email, unvalidated. They are stored and
rendered into PDFs, so an oversized or malformed value could balloon the document or (before
§4) inject markup.

**Change.**

- **Customer** (`schemas/customer.py`) — `CustomerCreate`/`CustomerUpdate` now cap `company`
  (255), `phone` (40), `address` (500), `gstin` (20), and validate `email` as `EmailStr`. The
  read-side base stays permissive (plain `str`) so a legacy row that predates these caps never
  fails to serialize.
- **Company settings** (`schemas/company.py`) — length caps on all text fields; `logo_data_url`
  capped (~700 KB) and constrained by a validator to an inline `data:image/` URI (never a
  `file://`/`http(s)://` URL WeasyPrint would fetch server-side).
- **Estimate discount** (`schemas/estimate.py` + `services/pricing.py`) — a `PERCENTAGE`
  discount > 100% is rejected by a model validator on create/update; pricing **also** clamps
  `min(discount_value, 100)` in both `price_design` and `_apply_commercial_terms` as defense in
  depth against a stored/legacy value driving the total negative. `FLAT` is unaffected (it's an
  absolute ₹ amount, already clamped to the subtotal).

**Tests.** `test_security.py`: over-100% percentage rejected on create/update; pricing clamps a
runaway value to a non-negative total; FLAT over 100 still allowed; logo rejects
non-`data:` URIs; customer rejects bad email and over-long address.

---

## 6. Geometry & pricing robustness (V-22 / V-23)

These are correctness guards rather than classic security fixes, but they close the same class
of "server trusts client input" gap and were made in the same pass. Both are now in the spec
([`directives/design_rules_spec.md`](../directives/design_rules_spec.md) §11, §12.2).

- **V-22 — stored geometry must match the tree that derives it.** The backend re-derives all
  dimensions from frame size + split ratios and does not trust client-supplied `width`/`height`.
  V-22 enforces that contract as a validation guard: the root region must span the frame, and
  each child of a split must equal the parent scaled by the split `position` (within a `0.001` ft
  tolerance, comfortably above the frontend's `1e-4` cleaning precision). An inconsistent tree —
  buggy client or hand-edited JSON — is rejected instead of mispriced.
- **V-23 — `sectionSize` and `gauge` must be present.** Pricing derives the section rate from
  them; a one-off frame tree arrives as a raw dict, so a missing field would otherwise `KeyError`
  inside pricing. V-23 rejects it in validation first.
- **`_recompute` now catches `KeyError` as well as `ValueError`** (`routers/estimates.py`) →
  a malformed **already-stored** frame re-priced on an estimate edit surfaces as `422`, not an
  uncaught `500`. New frames are guarded earlier by V-23.

**Tests.** `test_validation.py`: consistent vertical/horizontal splits pass; inconsistent
child width/height rejected; root-vs-frame mismatch rejected; sub-tolerance drift passes;
missing `sectionSize`/`gauge` rejected. `test_pricing.py`: missing section field raises
`KeyError` (the case the router now catches).

---

## Operational notes

- **Migration.** `0013_user_password_changed_at` adds the watermark column (`NOT NULL`,
  `server_default now()`, then backfilled to `created_at`). Run `alembic upgrade head` on
  deploy. See the DB-parity note in [`CLAUDE.md`](../CLAUDE.md) — dev auto-creates via
  `create_all`, so **only production actually exercises the migration**; run it against a
  copy of prod before shipping.
- **New env var.** `BOOTSTRAP_ADMIN_SECRET` — leave unset in normal operation (endpoint
  disabled). Set it only for a deliberate break-glass promotion, then unset it.
- **Deploying the token change is a forced logout.** Existing tokens have no `pwd` claim and
  are rejected after upgrade — every user re-authenticates once. This is intended.

### Deploy rehearsal — 2026-07-24

The production images were built and run end-to-end locally (isolated compose project, fresh
volume) before shipping. What it confirmed, and what it changed:

**Verified against the production images.** Migrations `0001→0014` apply cleanly to an empty
database; `APP_ENV=production` boots 4 workers and refuses to start on a dev/short
`JWT_SECRET_KEY` or default DB credentials; `/docs`, `/redoc`, `/openapi.json` are `404` at the
backend; HSTS + CSP + `nosniff` + `X-Frame-Options: DENY` present on API responses; login
limit returns `429` on the 6th attempt; unauthenticated `/customers` is `401`; a malformed tree
is `422`; `POST /auth/register` is gone (`404`); Postgres and the backend publish no host port.
The full quote flow — customer → estimate → frame → price → BOM CSV → **WeasyPrint PDF**
(valid `%PDF-`, ~18 KB) → `sent` status → `409` on editing a locked estimate — works. The PDF
path is only testable in-container, so this is the first real exercise of it.

**Found and fixed.**
- *Schema drift (migration `0014`).* `alembic revision --autogenerate` against the migrated
  database emitted two `ALTER`s: `estimates.quote_date` and `company_settings.updated_at` are
  `NOT NULL` on the ORM models (so `create_all` enforces them in dev) but were left nullable by
  migrations `0004`/`0005` — production had weaker constraints than dev and every test.
  Latent rather than live (the ORM supplies defaults on both), now closed. The probe is part
  of the deploy procedure ([`DEPLOY.md`](DEPLOY.md) §9).
- *Rate-limit identity behind a second proxy* — see §3 follow-up above.
- *Runbook commands that could not work.* `DEPLOY.md` documented `/api/...` paths, but the SPA
  calls the API at the root and nginx proxies bare prefixes. `POST /api/auth/login` returns
  `405`, so the documented rate-seeding step failed outright. Worse, **`GET /api/ready` returns
  `200 text/html`** — the SPA fallback — so a status-code-only readiness check passes *while the
  backend is down*. Corrected to root paths, with the body assertion spelled out.
