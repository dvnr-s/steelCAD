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
| `CORS_ORIGINS` | yes | Your domain, e.g. `https://steelcad.example.com` |
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
curl http://localhost/api/ready
# {"status":"ok"}
```

---

## 5. Bootstrap the first admin account

Access is invite-only — no public sign-up. You need at least one admin to create other users.

**Step 1 — Create an account via the login screen** (any email/password — it will be promoted next).

Or create one directly in the DB:

```bash
docker compose -f docker-compose.prod.yml exec backend python - <<'EOF'
import asyncio
from app.database import AsyncSessionLocal
from app.models.user import User
from app.services.auth import hash_password

async def main():
    async with AsyncSessionLocal() as db:
        user = User(
            email="admin@example.com",
            name="Admin",
            password=hash_password("ChangeMe123!"),
            role="sales",
        )
        db.add(user)
        await db.commit()

asyncio.run(main())
EOF
```

**Step 2 — Promote to admin** (one-time; endpoint becomes a no-op once any admin exists):

```bash
curl -X POST http://localhost/api/auth/bootstrap-admin \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@example.com"}'
# {"message": "admin@example.com is now an admin"}
```

After this, log in as the admin and use the **Users** page (`/users`) to invite additional owners and sales users. The bootstrap endpoint is disabled once an admin exists.

---

## 6. Seed the rate table

The pricing engine requires a populated `rates` table. Seed it with default rates:

```bash
# Get a token first
TOKEN=$(curl -s -X POST http://localhost/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"ChangeMe123!"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

curl -X POST http://localhost/api/rates/seed \
  -H "Authorization: Bearer $TOKEN"
# {"message": "rates seeded"}
```

Rates can be adjusted later via the **Rates** page in the app (admin/owner only).

---

## 7. Set up HTTPS (TLS termination)

The app listens on port 80 internally. Put a reverse proxy in front for HTTPS.

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

---

## 10. Post-deploy smoke test

Run this checklist after every deploy:

- [ ] `curl https://steelcad.example.com/api/health` returns `{"status":"ok"}`
- [ ] `curl https://steelcad.example.com/api/ready` returns `{"status":"ok"}`
- [ ] Login with admin credentials succeeds; JWT token returned
- [ ] `/api/auth/me` returns correct `role: "admin"`
- [ ] Navigate to `/rates` — rate table loads
- [ ] Navigate to `/users` — user list loads; invite a test user
- [ ] Login as the invited user, confirm they can create a customer and an estimate
- [ ] Add a frame to the estimate; verify the total updates
- [ ] Download the PDF from the estimate builder
- [ ] Confirm `POST /auth/register` (old public endpoint) returns 404 or 405
- [ ] As a `sales` user, confirm `/rates` redirects to `/` (role gating works)
- [ ] Check browser console for JS errors on all pages

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
| `CORS_ORIGINS` | localhost variants | Comma-separated allowed origins |
| `LOG_LEVEL` | `INFO` | Python log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
