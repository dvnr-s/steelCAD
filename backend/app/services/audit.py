"""
Audit recording helper. Call record_audit(...) from mutating handlers.

Failures are swallowed deliberately — an audit write must never break the user's
action. The row is flushed within the request's transaction so it commits together.
"""
from app.logging_config import get_logger
from app.models.audit import AuditLog

logger = get_logger("steelcad.audit")


async def record_audit(db, actor, action: str, entity_type: str,
                       entity_id=None, summary: str | None = None) -> None:
    try:
        # SAVEPOINT: if this INSERT fails, only the savepoint rolls back — the
        # caller's transaction stays usable (a bare failed flush would poison it).
        async with db.begin_nested():
            db.add(AuditLog(
                actor_id=getattr(actor, "id", None),
                action=action,
                entity_type=entity_type,
                entity_id=str(entity_id) if entity_id is not None else None,
                summary=summary,
            ))
    except Exception:  # noqa: BLE001 — auditing must never break the request
        logger.exception("Failed to record audit event %s", action)
