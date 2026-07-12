# Authorization model

**Status:** RESOLVED (M2.1). Row-level rules are enforced through one seam,
[`app/services/access.py`](../backend/app/services/access.py), so the future
multi-branch / multi-tenant scoping lands in a single place.

## Current rules

- **Reads** stay shared org-wide (single-company workspace).
- **Edits** (designs, customers, estimates, frames) → creator (`created_by == user.id`)
  or admin/owner, via `assert_can_write(record, user)`.
- **Deletes** of designs / customers / estimates → `require_role("admin", "owner")`
  (cascading customer delete is the highest blast-radius operation).
- **Estimates** additionally enforce a finalization lock via `assert_editable` —
  a non-`draft` estimate is read-only until reopened (spec PR-7).
- The front end hides delete controls for users who lack the role, to avoid
  surprise 403s (dashboard cards, customer cards, estimate rows).

---

## Historical context (the original gap)

Previously every endpoint required only a valid login, so **any** authenticated
user — including `sales` — could edit and delete anyone's records. `created_by` was
stored but never enforced. The notes below are kept for reference.

## What IS protected (for contrast)

| Area | Rule | Where |
|---|---|---|
| Rates — update / seed | `admin` or `owner` only | [rates.py:36](../backend/app/routers/rates.py#L36), [:59](../backend/app/routers/rates.py#L59) |
| Users — list / create / change role | `admin` or `owner` | [users.py](../backend/app/routers/users.py) |
| Users — delete | `admin` only | [users.py:115](../backend/app/routers/users.py#L115) |

## What is NOT scoped (the gap)

| Resource | Endpoints with no ownership/role check | File |
|---|---|---|
| **Designs** | list, get, **update**, **delete** — any user can edit/delete any design in the shared library | [designs.py](../backend/app/routers/designs.py) |
| **Customers** | list, get, **update**, **delete** — any user can edit/delete any customer | [customers.py](../backend/app/routers/customers.py) |
| **Estimates** | get, **update**, **delete**, add/update/delete **frames**, download PDF — any user can mutate any estimate for any customer | [estimates.py](../backend/app/routers/estimates.py) |

Notably, a `sales` user can permanently **delete** another user's customer
(cascading to all that customer's estimates and frames — see the `ondelete="CASCADE"`
chain in [estimate.py](../backend/app/models/estimate.py)) with no guard.

## Decision needed (per resource)

1. **Shared workspace (status quo)** — accept that all logged-in staff share one
   pool. Simplest; fine if the whole team is trusted. No code change.
2. **Creator-scoped writes** — only `created_by` (or an admin/owner) may
   update/delete. Reads stay shared. Add a helper like
   `require_owner_or_role(record.created_by, user, "admin", "owner")` to each
   mutating handler.
3. **Role-gated deletes** — keep edits open but restrict `delete` to `admin`/`owner`.
   Cheapest mitigation for the highest-blast-radius operation (cascading customer delete).

If we do (2) or (3), the front end also needs to hide/disable delete buttons for
users who lack permission (e.g. the trash icon on the dashboard design cards and
the customer/estimate lists), otherwise they'll get 403s.
