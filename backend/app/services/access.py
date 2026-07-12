"""
Access control seam.

Centralizes the row-level authorization rules so that the future move to
multi-branch / multi-tenant scoping lands in ONE place instead of every router.
Today the rule is "creator or admin/owner may mutate"; later this is where a
same-org / same-branch check is added.

All mutating endpoints should call `assert_can_write` (ownership) and, for
estimates, `assert_editable` (finalization lock).
"""
from fastapi import HTTPException, status

from app.models.user import User, ROLE_ADMIN, ROLE_OWNER

_PRIVILEGED = (ROLE_ADMIN, ROLE_OWNER)


def can_write(record, user: User) -> bool:
    """
    True if `user` may mutate `record`.

    Creator (record.created_by == user.id) or an admin/owner. Records without a
    `created_by` attribute (e.g. singletons) fall back to the role check.
    """
    if user.role in _PRIVILEGED:
        return True
    return getattr(record, "created_by", None) == user.id


def assert_can_write(record, user: User) -> None:
    """Raise 403 unless `user` may mutate `record`."""
    if not can_write(record, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only modify items you created.",
        )


def assert_editable(estimate) -> None:
    """
    Raise 409 if the estimate is finalized (status != 'draft').

    Enforces spec PR-7 — once a quote is sent/accepted/rejected its frames and
    commercial terms are locked. Reopen it to draft (status endpoint) to edit.
    """
    if getattr(estimate, "status", "draft") != "draft":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Estimate is '{estimate.status}' and locked. Reopen it to draft to edit.",
        )
