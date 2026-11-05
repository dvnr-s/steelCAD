#!/usr/bin/env bash
# SteelCAD — nightly database backup with rotation.
#
# Dumps the production Postgres to backups/steelcad-YYYYmmdd-HHMM.sql.gz and
# deletes dumps older than KEEP_DAYS. Optionally copies each dump off the box
# with rclone, because a backup that lives only on the VM dies with the VM.
#
# Install (once, as the user that ran bootstrap.sh):
#   chmod +x deploy/backup.sh
#   ./deploy/backup.sh                    # run once by hand — must print "ok"
#   (crontab -l 2>/dev/null; echo "30 2 * * * /srv/steelcad/deploy/backup.sh >> /srv/steelcad/backups/backup.log 2>&1") | crontab -
#
# Optional off-box copy: install rclone, configure a remote (`rclone config`),
# then put e.g.  BACKUP_REMOTE=gdrive:steelcad-backups  in .env.
#
# Restore (DESTRUCTIVE — replaces the live database; take a fresh dump first):
#   C="docker compose -f docker-compose.prod.yml -f docker-compose.tls.yml"
#   $C stop backend
#   $C exec -T db psql -U steelcad -d postgres -c "DROP DATABASE steelcad" -c "CREATE DATABASE steelcad OWNER steelcad"
#   gunzip -c backups/steelcad-YYYYmmdd-HHMM.sql.gz | $C exec -T db psql -U steelcad -d steelcad -v ON_ERROR_STOP=1
#   $C start backend

set -euo pipefail

cd "$(dirname "$0")/.."

COMPOSE="docker compose -f docker-compose.prod.yml -f docker-compose.tls.yml"
KEEP_DAYS="${KEEP_DAYS:-14}"
DEST="backups"

# shellcheck disable=SC1091
[ -f .env ] && { set -a; . ./.env; set +a; }
PGUSER="${POSTGRES_USER:-steelcad}"
PGDB="${POSTGRES_DB:-steelcad}"

mkdir -p "$DEST"
chmod 700 "$DEST"   # dumps contain customer PII and password hashes
umask 077

STAMP="$(date +%Y%m%d-%H%M)"
OUT="$DEST/steelcad-$STAMP.sql.gz"
TMP="$OUT.partial"

# Write to a temp name and rename on success, so a failed or interrupted dump
# never sits in the folder looking like a good backup. pipefail makes a
# pg_dump failure fail the pipeline even though gzip succeeded.
$COMPOSE exec -T db pg_dump -U "$PGUSER" -d "$PGDB" --no-owner --clean --if-exists \
    | gzip > "$TMP"

# An empty or truncated dump compresses to a few dozen bytes; a real one with
# the schema alone is several KB. Refuse to keep (or rotate in favour of) junk.
SIZE=$(stat -c %s "$TMP")
if [ "$SIZE" -lt 2048 ] || ! gunzip -t "$TMP" 2>/dev/null; then
    rm -f "$TMP"
    echo "$(date -Is) FAILED: dump was ${SIZE} bytes or corrupt" >&2
    exit 1
fi
mv "$TMP" "$OUT"

# Rotate only after a successful dump, so a run of failures can't delete the
# last good backups.
find "$DEST" -name 'steelcad-*.sql.gz' -mtime +"$KEEP_DAYS" -delete
find "$DEST" -name '*.partial' -delete

if [ -n "${BACKUP_REMOTE:-}" ]; then
    if command -v rclone >/dev/null 2>&1; then
        rclone copy "$OUT" "$BACKUP_REMOTE" \
            || { echo "$(date -Is) WARN: off-box copy to $BACKUP_REMOTE failed" >&2; exit 1; }
    else
        echo "$(date -Is) WARN: BACKUP_REMOTE set but rclone is not installed" >&2
        exit 1
    fi
fi

echo "$(date -Is) ok $OUT ($(du -h "$OUT" | cut -f1))"
