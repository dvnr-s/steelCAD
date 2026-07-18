# Secret-Safety Audit

**Date:** 2026-07-18 · **Scope:** full working tree + all git history (37 commits, all branches)

## Verdict: PASS — no real secrets found in the repository or its history

## What was checked

| Check | Method | Result |
|---|---|---|
| Hardcoded credentials in working tree | Pattern grep for `password/secret/api_key/token = "…"` | Only the labeled dev default and test fixtures |
| Known token formats | AWS `AKIA…`, OpenAI `sk-…`, GitHub `ghp_/gho_/github_pat_`, Google `AIza…`, Slack `xox…`, private-key PEM headers, embedded JWTs (`eyJhbGciOi`) | None, in tree or history |
| Committed env/key files | `git ls-files` + all-history object scan for `.env`, `.pem`, `credentials`, `id_rsa`, etc. | Only `.env.example` (placeholders only: `CHANGE_ME`) |
| Deleted-then-forgotten secrets | Diff-filter and full-history `git grep` across every revision | None |
| Personal data / real emails | All-history email scan | Only fictional test addresses (`a@b.com`, `sales@steel.test`, …) |
| Secret logging | Grep for `print`/`logger` calls referencing password/token/secret | None |
| `.gitignore` coverage | Manual review | Covers `.env*`, `credentials.json`, `token.json` |

## Intentional dev defaults (not leaks — safe by design)

These are publicly visible defaults that only apply in development, with production
guardrails already in place:

- `backend/app/config.py:8` — `_DEV_JWT_SECRET`; `validate_production_secrets()` refuses
  to start in production with this value.
- `docker-compose.yml` — `steelcad` DB password and dev JWT default; the **prod** compose
  file uses `:?` required-variable syntax with no fallback for both `POSTGRES_PASSWORD`
  and `JWT_SECRET_KEY`.
- `backend/alembic.ini:42` — localhost dev DB URL with the dev password.
- `execution/setup.py` — prompts for the admin password interactively and passes it into
  the container via environment variables, never hardcoded.

## Observations (non-secret, informational)

1. **`POST /auth/bootstrap-admin` is unauthenticated** (`backend/app/routers/auth.py:84`).
   It is a no-op once any admin exists, but between first deploy and first setup run,
   anyone who can reach the API can promote an arbitrary existing user to admin. Since
   registration is invite-only the practical window is small; consider requiring a
   logged-in caller or a one-time setup token if the API is internet-exposed before setup.
2. **JWTs are stored in `localStorage`** (`frontend/src/store/authStore.js`), which is
   readable by any XSS payload. Standard trade-off; httpOnly cookies would be stricter.
3. `execution/setup.py` passes `SETUP_PASSWORD` as a `docker compose exec -e` argument,
   which is briefly visible in the host process list during setup. Low risk on a
   single-operator machine.

## Recommendations

- Keep the current pattern: no secrets in code, prod compose requires env-supplied values.
- Optionally add a pre-commit secret scanner (e.g. `gitleaks`) to CI to keep it that way.
- Address observation 1 before exposing a fresh, un-setup deployment to the internet.
