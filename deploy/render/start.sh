#!/usr/bin/env bash
# SteelCAD on Render — container entrypoint for Dockerfile.render.
#
# One Render web service runs both processes: nginx on Render's $PORT (public)
# and uvicorn on 127.0.0.1:8000 (loopback only). Keeping the API off the public
# interface preserves the invariant services/ratelimit.py relies on: the only
# thing that can reach the backend is our own nginx, so X-Real-IP is trustworthy.
set -euo pipefail

# Render's connection string is postgresql://…; SQLAlchemy needs the asyncpg driver.
case "${DATABASE_URL:-}" in
    postgres://*)   DATABASE_URL="postgresql+asyncpg://${DATABASE_URL#postgres://}" ;;
    postgresql://*) DATABASE_URL="postgresql+asyncpg://${DATABASE_URL#postgresql://}" ;;
esac
export DATABASE_URL

cd /app

# Production has no create_all safety net — migrations are the only schema builder.
echo "==> alembic upgrade head"
alembic upgrade head

echo "==> first-run setup (admin + rates, idempotent)"
PYTHONPATH=/app python /opt/steelcad/first_run.py

sed -i "s/listen 80;/listen ${PORT:-10000};/" /etc/nginx/conf.d/default.conf

echo "==> starting uvicorn (127.0.0.1:8000) and nginx (:${PORT:-10000})"
uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers "${WEB_CONCURRENCY:-1}" &
nginx -g 'daemon off;' &

# If either process dies, exit so Render restarts the whole container.
wait -n
exit $?
