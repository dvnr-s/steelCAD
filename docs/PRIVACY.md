# Personal data map & privacy audit

Audited 2026-07-18. This documents every place SteelCAD collects, stores,
transmits, or logs personal data, and the controls around each flow. Update it
whenever a new field, integration, or log statement touches personal data.

## 1. What personal data exists, and where it enters

| Data | Collected at | Stored in | Who can read it |
|---|---|---|---|
| Staff email, name | `POST /users` invite form (UsersPage), first-run `execution/setup.py` | `users` table | Own profile via `/auth/me`; full list admin/owner-only via `GET /users` |
| Staff password | Login form, invite form, change/reset password forms | `users.password` — **bcrypt hash only**, never plaintext | Nobody — never returned by any endpoint |
| Customer name, company, phone, email, address, GSTIN | CustomersPage / CustomerDetailPage forms → `POST/PUT /customers` | `customers` table (soft-deleted rows retained) | All authenticated staff (org-wide reads by design); embedded in estimate responses (`CustomerBrief`) and quotation PDFs |
| Company (seller) address, phone, email, GSTIN, bank details, logo | SettingsPage → `PUT /settings/company` (admin/owner) | `company_settings` singleton | All authenticated staff; printed on every PDF |
| JWT access/refresh tokens | Issued by `POST /auth/login` / `/auth/refresh` | Browser `localStorage` (see §5) | The browser session |
| Client IP address | slowapi rate limiter on auth/price/PDF endpoints | In-memory only, never persisted or logged | Nobody |
| Actor identity in audit trail | Every mutating endpoint via `record_audit` | `audit_log` (actor **UUID** + summary; summaries may contain customer names, never emails/phones) | Admin/owner via `GET /audit` |

Not collected anywhere: dates of birth, payment card data, device fingerprints,
analytics identifiers.

## 2. Where data travels

- **Browser ↔ API**: JSON over the nginx/Vite proxy; JWT in the
  `Authorization` header. HTTPS + HSTS in production.
- **API ↔ PostgreSQL**: all persistence. Customer PII lives in `customers`
  and is denormalized into nothing else (estimates reference it by FK).
- **PDF/CSV exports**: quotation PDFs embed customer name/address/phone/GSTIN
  and company details — that is their business purpose. Generated in-process
  by WeasyPrint; nothing leaves the server.
- **Server logs**: request logging emits method, path, status, duration, and a
  random request ID only. No bodies, no query strings, no user identifiers,
  no IPs. Uvicorn access logs are suppressed.

## 3. Third-party services

| Service | What it receives | Notes |
|---|---|---|
| Google Fonts (`fonts.googleapis.com` / `gstatic.com`, via `@import` in `frontend/src/index.css`) | Requesting browser's IP + user agent | The **only** external call in the entire app. No user data fields are sent. To eliminate it entirely, self-host the Inter/JetBrains Mono woff2 files. |

There are no analytics, error-tracking, payment, email, or AI SDKs anywhere in
the codebase. The backend makes zero outbound network calls.

## 4. Password handling

- bcrypt with per-password salt (`services/auth.py`); plaintext exists only in
  the request body en route to the hash function.
- Never logged, never returned in any response schema, never stored elsewhere.
- Login is rate-limited (10/min) and burns an equal-cost bcrypt check when the
  email doesn't exist, so response timing can't be used to enumerate accounts.
- First-run setup reads the password with `getpass` (no terminal echo).

## 5. Browser storage

- **No cookies are used at all** (auth is header-based).
- `localStorage` holds the JWT access/refresh tokens and a persisted auth
  flag + **role only**. Email and name are deliberately excluded from the
  persisted store and are re-fetched from `/auth/me` on boot.
- Known trade-off: tokens in `localStorage` are readable by injected scripts
  (XSS). Mitigations: strict production CSP, React's default escaping, no
  third-party scripts. Moving tokens to `httpOnly` cookies (plus CSRF
  protection) is the recommended future hardening.

## 6. API response filtering

- Every endpoint serializes through an explicit Pydantic `response_model`;
  ORM rows are never returned raw. `UserResponse` excludes the password hash;
  `CustomerListItem` / `CustomerBrief` / trash entries expose only the fields
  each view needs.
- `/ready` returns a generic message on failure — the raw exception (which can
  embed the database DSN and its password) stays in the server log.
- Reads are intentionally org-wide (single-company workspace); row-level write
  rules live in `services/access.py`. See `AUTHORIZATION_GAPS.md`.

## 7. Data deletion

- **Staff accounts**: `DELETE /auth/me` (self-service, password-confirmed,
  refused for the last remaining admin) and `DELETE /users/{id}` (admin) both
  **anonymize**: email → `deleted-<uuid>@anonymized.invalid`, name →
  "Deleted user", password → random unusable hash, `deleted_at` set. The row
  survives because `created_by` FKs on designs/customers/estimates are NOT
  NULL; outstanding JWTs die because auth rejects deleted users. Migration
  `0012_user_deleted_at`.
- **Customers**: soft-delete (`deleted_at`) via admin/owner, restorable from
  Trash. Note: soft-deleted customer PII is retained indefinitely — if you
  need true erasure (e.g. a GDPR/DPDP request), a hard-purge of trashed
  customers is the missing piece and should hard-delete the row (estimates
  cascade).
- **Audit log**: append-only by design; contains actor UUIDs and customer
  names in summaries. Anonymizing a user does not rewrite history, but the
  actor's name resolves to "Deleted user" once anonymized.
