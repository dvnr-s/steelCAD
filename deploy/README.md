# Deploying SteelCAD — the short path

Full reference is [`docs/DEPLOY.md`](../docs/DEPLOY.md). This is the condensed
"get it live" version: one VPS, HTTPS included, ~15 minutes.

`deploy/bootstrap.sh` automates §2–§6 and §10 of the runbook. Everything below
is what only you can do (it needs your accounts and your money).

---

## 1. Create the server

Any Ubuntu 24.04 box with ≥2 GB RAM.

**Pick a region in India.** This app is GST/₹-denominated, so its users are in
India, and the editor issues a debounced price preview on every geometry edit.
An EU/US region adds ~150 ms to each of those round trips and the canvas feels
laggy; Bangalore or Mumbai keeps it at ~10–20 ms.

| Provider | Plan | Region | Cost |
|---|---|---|---|
| DigitalOcean | Basic 2 GB | **Bangalore (BLR1)** | ~$12/mo |
| Linode/Akamai | Nanode 2 GB | Mumbai | ~$12/mo |
| Hetzner | CX22 (4 GB) | EU/US only — cheap but far | ~€4/mo |

Use ≥2 GB: the frontend image builds the Vite bundle inside Docker, and
`npm ci` + `vite build` tends to OOM on a 1 GB box. Add swap if you must use one.

**Open ports 22, 80 and 443 in the provider's firewall / security group.** This
is the single most common reason the deploy finishes but the site won't load —
Caddy cannot complete the Let's Encrypt challenge without inbound :80.

## 2. Install Docker

SSH in as root, then:

```bash
curl -fsSL https://get.docker.com | sh
```

## 3. Get the code

```bash
git clone https://github.com/dvnr-s/steelCAD.git /srv/steelcad
cd /srv/steelcad
```

If the repo is private, generate a GitHub personal access token (or add a
deploy key) first — a plain `git clone` will otherwise prompt and fail.

## 4. Run the bootstrap

```bash
./deploy/bootstrap.sh
```

It detects the server's public IP and serves the app at
`https://<your-ip>.sslip.io` with a real, auto-renewing Let's Encrypt
certificate — no domain purchase needed. It will:

1. generate `.env` with strong random `JWT_SECRET_KEY` / `POSTGRES_PASSWORD`
2. apply Alembic migrations (production has no `create_all` safety net)
3. build and start db + backend + frontend + Caddy
4. create the first admin and print its generated password
5. seed the rate table (the pricing engine needs it)
6. smoke-test `https://…/ready` and report the URL

Already own a domain? Point an A record at the server and run:

```bash
SITE_ADDRESS=steelcad.example.com ADMIN_EMAIL=you@example.com ./deploy/bootstrap.sh
```

Re-running is safe: `.env` is never overwritten, migrations are incremental,
rate seeding is idempotent, and the admin is only created if absent.

## 5. Immediately after

- Log in and **change the admin password** from the generated one, then
  `rm .admin-password` (it is gitignored, but it's a plaintext secret on disk).
- Walk the smoke-test checklist in [`docs/DEPLOY.md`](../docs/DEPLOY.md) §10 —
  especially the PDF download, which is the thing most likely to be broken by a
  missing system library.
- Set up backups — [`docs/DEPLOY.md`](../docs/DEPLOY.md) §8. Nothing here backs
  up your database yet.

---

## Updating later

```bash
cd /srv/steelcad && git pull
docker compose -f docker-compose.prod.yml -f docker-compose.tls.yml run --rm backend alembic upgrade head
docker compose -f docker-compose.prod.yml -f docker-compose.tls.yml up -d --build
```

## Troubleshooting

```bash
# always pass BOTH -f flags, or you'll bring up a second, Caddy-less stack
C="docker compose -f docker-compose.prod.yml -f docker-compose.tls.yml"

$C ps                    # who's running
$C logs caddy --tail 40  # TLS / certificate problems
$C logs backend --tail 40
curl -fsS http://127.0.0.1:8080/ready   # bypasses Caddy — is the app itself up?
```

**Check the body, not the status code.** Any unrecognised path falls through to
the SPA, which answers `200 text/html` — so `curl -o /dev/null -w '%{http_code}'`
prints `200` even with the backend completely down. Assert the JSON:

```bash
curl -fsS https://<host>/ready | grep -q '"status":"ready"' && echo up || echo DOWN
```
