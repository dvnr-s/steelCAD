# SteelCAD — Deploy Runbook

Production deployment guide. Follow every step in order on a fresh server.

---

## Prerequisites

- Docker Engine 24+ and Docker Compose v2 (`docker compose`, not `docker-compose`)
- A server with at least 1 GB RAM and 10 GB disk
- A domain name pointed at the server (for HTTPS)
- `git`, `openssl` available on the host

---

## 1. Clone the repository

```bash
git clone <your-repo-url> /srv/steelcad
cd /srv/steelcad
```

---

## 2. Create the environment file

```bash
cp .env.example .env
```

Edit `.env` and fill in every value marked `CHANGE_ME`:

| Variable | Required | Notes |
|---|---|---|
| `APP_ENV` | yes | Set to `production` |
| `DATABASE_URL` | yes | Auto-built from `POSTGRES_*` in compose, but set if running outside Docker |
| `POSTGRES_USER` | yes | Database username |
| `POSTGRES_PASSWORD` | yes | Strong random password |
| `POSTGRES_DB` | yes | Database name |
| `JWT_SECRET_KEY` | **critical** | Generate with `openssl rand -hex 32` |
| `JWT_ALGORITHM` | no | Default: `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | no | Default: `15` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | no | Default: `7` |
| `CORS_ORIGINS` | no | Leave **empty** behind the bundled nginx — the SPA is same-origin. Set it only if the frontend is served from a different domain than the API. |
| `DATABASE_SSL` | no | Default `false`. Set `true` when `DATABASE_URL` points at an external/managed Postgres rather than the internal compose network. |
| `BOOTSTRAP_ADMIN_SECRET` | no | Leave **unset**. Setting it enables the break-glass `POST /auth/bootstrap-admin` endpoint (see §5). |
| `LOG_LEVEL` | no | Default: `INFO` |

Generate the JWT secret:

```bash
openssl rand -hex 32
# paste the output into JWT_SECRET_KEY in .env
```

**The app will refuse to start in production mode if `JWT_SECRET_KEY` is the dev default.**

---

## 3. Run database migrations

Migrations must run before the app serves traffic. The `backend` container has Alembic installed.

```bash
# Start only the database
docker compose -f docker-compose.prod.yml up -d db

# Wait for it to be healthy, then run migrations
docker compose -f docker-compose.prod.yml run --rm backend \
  alembic upgrade head
```

On a **fresh database** this creates all tables. On an **existing database** it applies only the pending migrations — safe to run on every deploy.

---

## 4. Start the application

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

This builds and starts three containers: `db`, `backend`, `frontend`.

Check that all are healthy:

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs backend --tail 40
```

The readiness endpoint verifies the DB connection:

```bash
curl http://localhost/ready
# {"status":"ready"}

curl http://localhost/health
# {"status":"ok","service":"steelcad-api","env":"production"}
```

> **There is no `/api` prefix.** The SPA calls the API at the root (`baseURL: '/'`
> in `frontend/src/api/client.js`) and nginx proxies the bare router prefixes
> (`/auth`, `/estimates`, `/ready`, …) — see `frontend/nginx.conf`.
>
> **Check the body, not just the status code.** Any path nginx does not recognise
> as an API route falls through to the SPA, which returns **`200 text/html`**. So
> `curl -o /dev/null -w '%{http_code}' http://localhost/api/ready` prints `200`
> **even when the backend is completely down** — it is the `index.html` shell, not
> a health check. A readiness probe must assert JSON:
>
> ```bash
> curl -fsS http://localhost/ready | grep -q '"status":"ready"' \
>   && echo "backend up" || echo "BACKEND DOWN"
> ```

---

## 5. Bootstrap the first admin account

Access is invite-only — no public sign-up. You need at least one admin to create other users.

**Create the first admin directly in the DB** (there is no public sign-up; the login
screen only signs in existing users). This is the trusted, recommended path — it needs
container access, which only an operator has. In dev, `python execution/setup.py`
automates this whole section (it creates the account and, when no admin exists yet,
promotes it to admin in the same DB step). In production:

```bash
docker compose -f docker-compose.prod.yml exec backend python - <<'EOF'
import asyncio
from app.database import async_session_factory
from app.models.user import User

async def main():
    from app.services.auth import hash_password
    async with async_session_factory() as db:
        db.add(User(
            email="admin@example.com",
            name="Admin",
            password=hash_password("ChangeMe123!"),
            role="admin",      # first admin bootstraps the system
            is_admin=True,
        ))
        await db.commit()

asyncio.run(main())
EOF
```

After this, log in as the admin and use the **Users** page (`/users`) to invite additional owners and sales users.

> **`POST /auth/bootstrap-admin` is disabled by default.** It only responds when the
> `BOOTSTRAP_ADMIN_SECRET` env var is set, and the request must present that exact
> secret (`{"email": "...", "secret": "..."}`). This is a break-glass path — an
> unauthenticated caller must never be able to seize admin during a window where no
> admin exists. Prefer the direct-DB step above; if you do enable the endpoint for a
> one-off promotion, unset `BOOTSTRAP_ADMIN_SECRET` again afterward.

---

## 6. Seed the rate table

The pricing engine requires a populated `rates` table. Seed it with default rates:

```bash
# Get a token first
TOKEN=$(curl -s -X POST http://localhost/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"ChangeMe123!"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

curl -X POST http://localhost/rates/seed \
  -H "Authorization: Bearer $TOKEN"
# {"message":"Seeded 16 rates, skipped 0 existing"}
```

`/rates/seed` is idempotent — it skips rates that already exist, so re-running it
after an upgrade only adds newly introduced ones.

Rates can be adjusted later via the **Rates** page in the app (admin/owner only).

---

## 7. Set up HTTPS (TLS termination)

The app listens on port 80 internally. Put a reverse proxy in front for HTTPS.

### If you don't have a domain yet

You can run on the server's bare IP over plain HTTP, but understand the exposure
before putting real customer data in:

- **JWTs, passwords, and customer PII cross the network in cleartext.** Anyone on
  the path (café Wi-Fi, ISP, hosting network) can read the login POST and replay
  the token. Access tokens last 15 minutes; refresh tokens last 7 days.
- The `Strict-Transport-Security` header the app sends is ignored over plain HTTP,
  and the browser will mark the site "Not secure".

Treat bare-IP HTTP as a **pilot/internal-testing** configuration. Two ways to get
real TLS without buying a domain yet:

1. **Free wildcard-DNS hostname.** `sslip.io` / `nip.io` resolve any IP embedded in
   the name, and Let's Encrypt will issue for them. If your server is `203.0.113.9`,
   `203.0.113.9.sslip.io` works as a real hostname today, and you can swap in your
   own domain later with a one-line Caddyfile change:
   ```
   203.0.113.9.sslip.io {
       reverse_proxy localhost:80
   }
   ```
   (Let's Encrypt will not issue a certificate for a raw IP address, which is why
   the hostname is needed.)
2. **Cloudflare Tunnel**, which terminates TLS on a hostname it gives you and needs
   no inbound ports open at all.

Until TLS is in place, restrict who can reach the box — see §7.1.

### 7.1 Firewall (do this on a bare-IP deploy)

`docker compose … up` publishes port 80 by inserting its own iptables rules, which
bypass UFW's `INPUT` chain — **`ufw deny 80` will not block a published container
port.** Restrict access one of these ways instead:

```bash
# Option A — allow only your office/home IP to reach the app, via Docker's chain
sudo iptables -I DOCKER-USER -p tcp --dport 80 ! -s <YOUR.IP.ADDR>/32 -j DROP

# Option B — bind the published port to loopback and reach it over an SSH tunnel
#   in docker-compose.prod.yml:  ports: ["127.0.0.1:80:80"]
#   then from your laptop:       ssh -L 8080:127.0.0.1:80 user@server
```

Also confirm the database is not exposed — `docker compose -f docker-compose.prod.yml ps`
should show **no published port** for `db` (it is internal-only by design), and SSH
should be key-only.

> **Client IPs must survive the proxy hop.** The backend rate-limits per client
> using `X-Real-IP` (`backend/app/services/ratelimit.py`). `frontend/nginx.conf`
> sets that from `$remote_addr`, and its `set_real_ip_from` block recovers the
> original client address from `X-Forwarded-For` when the connection arrives from a
> private range (i.e. from your own front proxy). Without that, adding Caddy/nginx
> in front would make every request look like it came from the proxy, collapsing
> all users into **one shared rate-limit bucket** — one attacker could then lock
> everyone out of login. If you front the app with a proxy, verify limits are still
> per-client: 6 rapid bad logins from one machine should 429, while another machine
> can still reach the login form.

### Option A — Caddy (recommended, automatic TLS)

Install Caddy on the host, then create `/etc/caddy/Caddyfile`:

```
steelcad.example.com {
    reverse_proxy localhost:80
}
```

```bash
systemctl reload caddy
```

Caddy automatically obtains and renews a Let's Encrypt certificate.

### Option B — nginx + Certbot

```nginx
server {
    listen 80;
    server_name steelcad.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name steelcad.example.com;

    ssl_certificate     /etc/letsencrypt/live/steelcad.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/steelcad.example.com/privkey.pem;

    location / {
        proxy_pass http://localhost:80;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
certbot --nginx -d steelcad.example.com
```

After HTTPS is up, update `CORS_ORIGINS` in `.env` to use `https://steelcad.example.com` and restart:

```bash
docker compose -f docker-compose.prod.yml up -d backend
```

---

## 8. Database backup policy

PostgreSQL data is in the `pgdata` Docker volume. Back it up regularly.

**Manual backup:**

```bash
docker compose -f docker-compose.prod.yml exec db \
  pg_dump -U steelcad steelcad | gzip > /backup/steelcad-$(date +%Y%m%d).sql.gz
```

**Automated daily backup** (add to host crontab):

```bash
# crontab -e
0 2 * * * docker compose -f /srv/steelcad/docker-compose.prod.yml exec -T db \
  pg_dump -U steelcad steelcad | gzip > /backup/steelcad-$(date +\%Y\%m\%d).sql.gz
```

**Restore from backup:**

```bash
gunzip -c /backup/steelcad-20260101.sql.gz | \
  docker compose -f docker-compose.prod.yml exec -T db \
  psql -U steelcad steelcad
```

Keep at least 7 days of backups. Test restores periodically.

---

## 9. Deploy updates

```bash
cd /srv/steelcad
git pull

# Rebuild and restart
docker compose -f docker-compose.prod.yml up -d --build

# Run any new migrations
docker compose -f docker-compose.prod.yml run --rm backend alembic upgrade head
```

Zero-downtime: `up -d --build` replaces containers one at a time. The DB migration step is idempotent.

**Verify the migrated schema still matches the ORM models.** Dev builds its schema
with `create_all` and never runs the migrations, so a model change shipped without a
matching migration works in dev and silently diverges in production. Alembic can
prove there is no gap — this must print an empty `upgrade()`:

```bash
docker compose -f docker-compose.prod.yml run --rm backend sh -c \
  'alembic revision --autogenerate -m drift_probe --rev-id drift_probe >/dev/null 2>&1; \
   sed -n "/def upgrade/,/### end/p" migrations/versions/drift_probe_drift_probe.py; \
   rm -f migrations/versions/drift_probe_drift_probe.py'
# expected:
#   def upgrade() -> None:
#       # ### commands auto generated by Alembic - please adjust! ###
#       pass
```

Any emitted `op.*` call is real drift: production's schema differs from what the code
expects. Write a migration for it rather than editing the database by hand. (This
check is what produced migration `0014`, which restored two `NOT NULL` constraints
that existed in dev but never in production.)

---

## 10. Post-deploy smoke test

Run this checklist after every deploy:

- [ ] `curl https://steelcad.example.com/health` returns `{"status":"ok",...}` — **check the body**, not the status code (see §4)
- [ ] `curl https://steelcad.example.com/ready` returns `{"status":"ready"}`
- [ ] Login with admin credentials succeeds; JWT token returned
- [ ] `/auth/me` returns correct `role: "admin"`
- [ ] Navigate to `/rates` — rate table loads
- [ ] Navigate to `/users` — user list loads; invite a test user
- [ ] Login as the invited user, confirm they can create a customer and an estimate
- [ ] Add a frame to the estimate; verify the total updates
- [ ] Download the PDF from the estimate builder
- [ ] Confirm `POST /auth/register` (old public endpoint) returns 404 or 405
- [ ] As a `sales` user, confirm `/rates` redirects to `/` (role gating works)
- [ ] Check browser console for JS errors on all pages
- [ ] Interactive docs are off: `/docs`, `/redoc`, `/openapi.json` must **not** return
      FastAPI pages (they return the SPA shell through nginx, and 404 at the backend)
- [ ] Security headers present: `curl -sD- -o/dev/null https://…/health | grep -i
      'strict-transport\|content-security'`
- [ ] Rate limiting bites: 6 rapid bad logins → the last returns `429`
- [ ] `GET /customers` with no token returns `401`
- [ ] `POST /price` with a malformed tree returns `422`

---

## Environment variable reference

| Variable | Default | Description |
|---|---|---|
| `APP_ENV` | `development` | `production` enables startup checks and disables `create_all` |
| `DATABASE_URL` | — | Full async DSN (`postgresql+asyncpg://...`) |
| `POSTGRES_USER` | `steelcad` | Postgres username |
| `POSTGRES_PASSWORD` | — | Postgres password (required in prod) |
| `POSTGRES_DB` | `steelcad` | Postgres database name |
| `JWT_SECRET_KEY` | dev default | **Must be overridden in production** (`openssl rand -hex 32`) |
| `JWT_ALGORITHM` | `HS256` | Signing algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | Access token TTL |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh token TTL |
| `CORS_ORIGINS` | localhost variants | Comma-separated allowed origins. In production the dev default is treated as unset (same-origin only); a `*` wildcard is a fatal startup error. |
| `DATABASE_SSL` | `false` | Require TLS on the DB connection (set `true` for managed/external Postgres) |
| `BOOTSTRAP_ADMIN_SECRET` | `""` (disabled) | Shared secret enabling `POST /auth/bootstrap-admin`. Keep unset outside a one-off bootstrap. |
| `LOG_LEVEL` | `INFO` | Python log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
