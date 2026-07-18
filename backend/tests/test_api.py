"""
API integration tests — auth, RBAC enforcement, core CRUD.

Requires a running Postgres (see conftest.py). Skipped automatically if
TEST_DATABASE_URL is unreachable.
"""
from uuid import uuid4

from tests.conftest import create_user, login, auth_headers, seed_rates


def make_design_payload(name: str, width: float = 4.0, height: float = 3.0) -> dict:
    """Valid DesignCreate body — a single fixed-region window in the canonical
    DesignTree serialization format (spec §13)."""
    return {
        "name": name,
        "outerWidth": width,
        "outerHeight": height,
        "sectionSize": "5",
        "gauge": "18G",
        "tree_json": {
            "id": str(uuid4()),
            "type": "design",
            "name": name,
            "productType": "window",
            "outerWidth": width,
            "outerHeight": height,
            "sectionSize": "5",
            "gauge": "18G",
            "frame": {
                "id": str(uuid4()),
                "type": "frame",
                "width": width,
                "height": height,
                "rootRegion": {
                    "id": str(uuid4()),
                    "type": "region",
                    "x": 0, "y": 0,
                    "width": width, "height": height,
                    "isLeaf": True,
                    "regionType": "fixed",
                },
            },
        },
    }


# ── Auth ──────────────────────────────────────────────────────────

class TestAuth:
    async def test_login_success(self, client, db_session):
        await create_user(db_session, "login@test.com")
        tokens = await login(client, "login@test.com")
        assert "access_token" in tokens
        assert "refresh_token" in tokens

    async def test_login_wrong_password(self, client, db_session):
        await create_user(db_session, "wrongpw@test.com")
        resp = await client.post("/auth/login", json={"email": "wrongpw@test.com", "password": "badpass"})
        assert resp.status_code == 401

    async def test_register_endpoint_removed(self, client):
        """Public /auth/register must not exist — access is invite-only."""
        resp = await client.post("/auth/register", json={
            "email": "anon@test.com", "password": "password123", "name": "Anon"
        })
        assert resp.status_code in (404, 405), \
            f"Expected 404/405 but got {resp.status_code} — public sign-up must be disabled"

    async def test_get_me_returns_role(self, client, db_session):
        await create_user(db_session, "me@test.com", role="sales")
        tokens = await login(client, "me@test.com")
        resp = await client.get("/auth/me", headers=auth_headers(tokens))
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "sales"
        assert data["email"] == "me@test.com"

    async def test_refresh_token(self, client, db_session):
        await create_user(db_session, "refresh@test.com")
        tokens = await login(client, "refresh@test.com")
        resp = await client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    async def test_unauthenticated_request_rejected(self, client):
        resp = await client.get("/auth/me")
        assert resp.status_code == 401  # missing bearer credentials → 401 Unauthorized

    async def test_change_password(self, client, db_session):
        await create_user(db_session, "changepw@test.com", password="oldpassword1")
        h = auth_headers(await login(client, "changepw@test.com", password="oldpassword1"))
        # Wrong current password is rejected.
        bad = await client.post("/auth/change-password", headers=h,
                                json={"current_password": "nope", "new_password": "newpassword1"})
        assert bad.status_code == 400
        # Correct current password updates it; new password then logs in.
        ok = await client.post("/auth/change-password", headers=h,
                               json={"current_password": "oldpassword1", "new_password": "newpassword1"})
        assert ok.status_code == 200
        relogin = await client.post("/auth/login", json={"email": "changepw@test.com", "password": "newpassword1"})
        assert relogin.status_code == 200


# ── Account deletion (anonymization) ──────────────────────────────

class TestAccountDeletion:
    async def test_self_delete_requires_correct_password(self, client, db_session):
        await create_user(db_session, "deleteme@test.com")
        h = auth_headers(await login(client, "deleteme@test.com"))
        resp = await client.request("DELETE", "/auth/me", headers=h,
                                    json={"password": "wrongpassword"})
        assert resp.status_code == 400

    async def test_self_delete_anonymizes_and_invalidates_tokens(self, client, db_session):
        user = await create_user(db_session, "gone@test.com", name="Going Away")
        h = auth_headers(await login(client, "gone@test.com"))
        resp = await client.request("DELETE", "/auth/me", headers=h,
                                    json={"password": "password123"})
        assert resp.status_code == 204
        # Outstanding access token no longer works.
        assert (await client.get("/auth/me", headers=h)).status_code == 401
        # Old credentials no longer log in.
        relogin = await client.post("/auth/login", json={
            "email": "gone@test.com", "password": "password123"})
        assert relogin.status_code == 401
        # PII is scrubbed in place, row survives.
        await db_session.refresh(user)
        assert user.email == f"deleted-{user.id}@anonymized.invalid"
        assert user.name == "Deleted user"
        assert user.deleted_at is not None

    async def test_last_admin_cannot_self_delete(self, client, db_session):
        await create_user(db_session, "lastadmin@test.com", role="admin")
        h = auth_headers(await login(client, "lastadmin@test.com"))
        resp = await client.request("DELETE", "/auth/me", headers=h,
                                    json={"password": "password123"})
        assert resp.status_code == 409
        # With a second admin present, deletion is allowed.
        await create_user(db_session, "otheradmin@test.com", role="admin")
        resp = await client.request("DELETE", "/auth/me", headers=h,
                                    json={"password": "password123"})
        assert resp.status_code == 204

    async def test_admin_delete_anonymizes_user_with_records(self, client, db_session):
        """Deleting a user who created records must not fail on the NOT NULL
        created_by FK, and must not destroy their business records."""
        await create_user(db_session, "boss@test.com", role="admin")
        sales = await create_user(db_session, "worker@test.com", name="Worker")
        sales_h = auth_headers(await login(client, "worker@test.com"))
        cust = await client.post("/customers", headers=sales_h,
                                 json={"name": "Acme Traders", "phone": "9999999999"})
        assert cust.status_code == 201

        admin_h = auth_headers(await login(client, "boss@test.com"))
        resp = await client.delete(f"/users/{sales.id}", headers=admin_h)
        assert resp.status_code == 204
        # Deleted user disappears from the list…
        listed = (await client.get("/users", headers=admin_h)).json()
        assert str(sales.id) not in [u["id"] for u in listed]
        # …but the customer they created survives.
        still_there = await client.get(f"/customers/{cust.json()['id']}", headers=admin_h)
        assert still_there.status_code == 200


# ── RBAC: Rates ────────────────────────────────────────────────────

class TestRatesRBAC:
    async def test_sales_can_read_rates(self, client, db_session):
        await create_user(db_session, "sales_rates@test.com", role="sales")
        tokens = await login(client, "sales_rates@test.com")
        resp = await client.get("/rates", headers=auth_headers(tokens))
        assert resp.status_code == 200

    async def test_sales_cannot_seed_rates(self, client, db_session):
        await create_user(db_session, "sales_seed@test.com", role="sales")
        tokens = await login(client, "sales_seed@test.com")
        resp = await client.post("/rates/seed", headers=auth_headers(tokens))
        assert resp.status_code == 403

    async def test_owner_can_seed_rates(self, client, db_session):
        await create_user(db_session, "owner_seed@test.com", role="owner")
        tokens = await login(client, "owner_seed@test.com")
        resp = await client.post("/rates/seed", headers=auth_headers(tokens))
        assert resp.status_code == 201

    async def test_admin_can_seed_rates(self, client, db_session):
        await create_user(db_session, "admin_seed@test.com", role="admin")
        tokens = await login(client, "admin_seed@test.com")
        resp = await client.post("/rates/seed", headers=auth_headers(tokens))
        assert resp.status_code in (200, 201)


# ── RBAC: Users ────────────────────────────────────────────────────

class TestUsersRBAC:
    async def test_sales_cannot_list_users(self, client, db_session):
        await create_user(db_session, "sales_users@test.com", role="sales")
        tokens = await login(client, "sales_users@test.com")
        resp = await client.get("/users", headers=auth_headers(tokens))
        assert resp.status_code == 403

    async def test_owner_can_list_users(self, client, db_session):
        await create_user(db_session, "owner_list@test.com", role="owner")
        tokens = await login(client, "owner_list@test.com")
        resp = await client.get("/users", headers=auth_headers(tokens))
        assert resp.status_code == 200

    async def test_admin_can_invite_any_role(self, client, db_session):
        await create_user(db_session, "admin_invite@test.com", role="admin")
        tokens = await login(client, "admin_invite@test.com")
        resp = await client.post("/users", headers=auth_headers(tokens), json={
            "name": "New Owner", "email": "newowner@test.com",
            "password": "password123", "role": "owner",
        })
        assert resp.status_code == 201
        assert resp.json()["role"] == "owner"

    async def test_owner_cannot_invite_admin(self, client, db_session):
        await create_user(db_session, "owner_noadmin@test.com", role="owner")
        tokens = await login(client, "owner_noadmin@test.com")
        resp = await client.post("/users", headers=auth_headers(tokens), json={
            "name": "Bad Admin", "email": "badadmin@test.com",
            "password": "password123", "role": "admin",
        })
        assert resp.status_code == 403

    async def test_owner_can_invite_sales(self, client, db_session):
        await create_user(db_session, "owner_sales@test.com", role="owner")
        tokens = await login(client, "owner_sales@test.com")
        resp = await client.post("/users", headers=auth_headers(tokens), json={
            "name": "New Sales", "email": "newsales@test.com",
            "password": "password123", "role": "sales",
        })
        assert resp.status_code == 201
        assert resp.json()["role"] == "sales"

    async def test_cannot_change_own_role(self, client, db_session):
        user = await create_user(db_session, "self_role@test.com", role="admin")
        tokens = await login(client, "self_role@test.com")
        resp = await client.patch(
            f"/users/{user.id}/role",
            headers=auth_headers(tokens),
            json={"role": "sales"},
        )
        assert resp.status_code == 400

    async def test_duplicate_email_rejected(self, client, db_session):
        await create_user(db_session, "dup@test.com", role="admin")
        tokens = await login(client, "dup@test.com")
        # Try to invite with the same email
        resp = await client.post("/users", headers=auth_headers(tokens), json={
            "name": "Dup", "email": "dup@test.com", "password": "password123", "role": "sales",
        })
        assert resp.status_code == 409


# ── Core CRUD (all roles) ─────────────────────────────────────────

class TestDesignsCRUD:
    async def test_sales_can_create_design(self, client, db_session):
        await create_user(db_session, "sales_design@test.com", role="sales")
        tokens = await login(client, "sales_design@test.com")
        resp = await client.post("/designs", headers=auth_headers(tokens),
                                 json=make_design_payload("Test Window"))
        assert resp.status_code == 201
        assert resp.json()["name"] == "Test Window"

    async def test_all_roles_see_all_designs(self, client, db_session):
        """All roles share the same design pool — no per-user scoping."""
        # Create a design as sales user 1
        await create_user(db_session, "design_creator@test.com", role="sales")
        tokens1 = await login(client, "design_creator@test.com")
        create_resp = await client.post("/designs", headers=auth_headers(tokens1),
                                        json=make_design_payload("Shared Design", width=3.0, height=2.0))
        assert create_resp.status_code == 201

        # Sales user 2 should see it
        await create_user(db_session, "design_viewer@test.com", role="sales")
        tokens2 = await login(client, "design_viewer@test.com")
        list_resp = await client.get("/designs", headers=auth_headers(tokens2))
        assert list_resp.status_code == 200
        names = [d["name"] for d in list_resp.json()]
        assert "Shared Design" in names


class TestDesignThumbnail:
    async def test_thumbnail_svg_and_304(self, client, db_session):
        await create_user(db_session, "thumb@test.com", role="sales")
        h = auth_headers(await login(client, "thumb@test.com"))
        design = (await client.post("/designs", headers=h, json=make_design_payload("Thumb Win"))).json()

        r = await client.get(f"/designs/{design['id']}/thumbnail.svg", headers=h)
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("image/svg+xml")
        assert "cache-control" in r.headers
        assert r.text.lstrip().startswith("<svg")
        etag = r.headers["etag"]

        # Revalidation with the same ETag → 304, no body.
        r304 = await client.get(f"/designs/{design['id']}/thumbnail.svg",
                                headers={**h, "If-None-Match": etag})
        assert r304.status_code == 304
        assert not r304.content

    async def test_thumbnail_404(self, client, db_session):
        await create_user(db_session, "thumb404@test.com", role="sales")
        h = auth_headers(await login(client, "thumb404@test.com"))
        assert (await client.get(f"/designs/{uuid4()}/thumbnail.svg", headers=h)).status_code == 404


class TestCustomersCRUD:
    async def test_create_and_list_customers(self, client, db_session):
        await create_user(db_session, "sales_cust@test.com", role="sales")
        tokens = await login(client, "sales_cust@test.com")

        # Create
        resp = await client.post("/customers", headers=auth_headers(tokens), json={
            "name": "ACME Corp", "phone": "9999999999",
        })
        assert resp.status_code == 201
        customer_id = resp.json()["id"]

        # List
        list_resp = await client.get("/customers", headers=auth_headers(tokens))
        assert list_resp.status_code == 200
        ids = [c["id"] for c in list_resp.json()]
        assert customer_id in ids

    async def test_sales_cannot_delete_customer(self, client, db_session):
        """Deletes are gated to admin/owner (cascading customer delete is high blast-radius)."""
        await create_user(db_session, "sales_del_cust@test.com", role="sales")
        tokens = await login(client, "sales_del_cust@test.com")
        create_resp = await client.post("/customers", headers=auth_headers(tokens), json={"name": "To Delete"})
        cid = create_resp.json()["id"]
        del_resp = await client.delete(f"/customers/{cid}", headers=auth_headers(tokens))
        assert del_resp.status_code == 403

    async def test_owner_can_delete_customer(self, client, db_session):
        await create_user(db_session, "owner_del_cust@test.com", role="owner")
        tokens = await login(client, "owner_del_cust@test.com")
        create_resp = await client.post("/customers", headers=auth_headers(tokens), json={"name": "To Delete"})
        cid = create_resp.json()["id"]
        del_resp = await client.delete(f"/customers/{cid}", headers=auth_headers(tokens))
        assert del_resp.status_code == 204


# ── Estimate lifecycle (status + finalize lock) ───────────────────

_DESIGN_PAYLOAD = make_design_payload("Lifecycle Window")


class TestEstimateLifecycle:
    async def _setup_estimate_with_frame(self, client, headers, db_session):
        await seed_rates(db_session)  # pricing needs the rate table
        cust = (await client.post("/customers", headers=headers, json={"name": "Lifecycle Co"})).json()["id"]
        design_id = (await client.post("/designs", headers=headers, json=_DESIGN_PAYLOAD)).json()["id"]
        est = (await client.post(f"/customers/{cust}/estimates", headers=headers, json={"title": "Q"})).json()
        await client.post(f"/estimates/{est['id']}/frames", headers=headers,
                          json={"source_design_id": design_id, "quantity": 1})
        return est["id"], design_id

    async def test_create_sets_quote_dates(self, client, db_session):
        await create_user(db_session, "est_dates@test.com", role="sales")
        h = auth_headers(await login(client, "est_dates@test.com"))
        cust = (await client.post("/customers", headers=h, json={"name": "Dates Co"})).json()["id"]
        est = (await client.post(f"/customers/{cust}/estimates", headers=h, json={"title": "Q"})).json()
        assert est["quote_date"] is not None
        assert est["valid_until"] is not None  # defaults to quote_date + 30 days

    async def test_finalize_lock_blocks_edits(self, client, db_session):
        await create_user(db_session, "est_lock@test.com", role="sales")
        h = auth_headers(await login(client, "est_lock@test.com"))
        eid, design_id = await self._setup_estimate_with_frame(client, h, db_session)

        # Move to 'sent'.
        r = await client.patch(f"/estimates/{eid}/status", headers=h, json={"status": "sent"})
        assert r.status_code == 200 and r.json()["status"] == "sent"

        # Editing terms and adding frames are now locked.
        assert (await client.put(f"/estimates/{eid}", headers=h, json={"title": "new"})).status_code == 409
        assert (await client.post(f"/estimates/{eid}/frames", headers=h,
                                  json={"source_design_id": design_id, "quantity": 1})).status_code == 409

        # Reopen to draft re-enables editing.
        assert (await client.patch(f"/estimates/{eid}/status", headers=h, json={"status": "draft"})).status_code == 200
        assert (await client.put(f"/estimates/{eid}", headers=h, json={"title": "new"})).status_code == 200

    async def test_sales_cannot_delete_estimate(self, client, db_session):
        await create_user(db_session, "est_del@test.com", role="sales")
        h = auth_headers(await login(client, "est_del@test.com"))
        eid, _ = await self._setup_estimate_with_frame(client, h, db_session)
        # Deletes are gated to admin/owner.
        assert (await client.delete(f"/estimates/{eid}", headers=h)).status_code == 403

    async def test_duplicate_estimate(self, client, db_session):
        await create_user(db_session, "est_dup@test.com", role="sales")
        h = auth_headers(await login(client, "est_dup@test.com"))
        eid, _ = await self._setup_estimate_with_frame(client, h, db_session)
        # Lock the source to prove duplicate produces an editable draft regardless.
        await client.patch(f"/estimates/{eid}/status", headers=h, json={"status": "sent"})

        dup = await client.post(f"/estimates/{eid}/duplicate", headers=h)
        assert dup.status_code == 201
        body = dup.json()
        assert body["status"] == "draft"
        assert body["id"] != eid
        assert len(body["frames"]) == 1          # frame copied
        assert body["grand_total"] > 0           # re-priced


# ── Frame thumbnails (schematic SVG per estimate frame) ───────────

class TestFrameThumbnail:
    async def test_frame_thumbnail_svg_and_304(self, client, db_session):
        await create_user(db_session, "fthumb@test.com", role="sales")
        h = auth_headers(await login(client, "fthumb@test.com"))
        await seed_rates(db_session)
        cust = (await client.post("/customers", headers=h, json={"name": "Thumb Co"})).json()["id"]
        design_id = (await client.post("/designs", headers=h,
                                       json=make_design_payload("Thumb Frame"))).json()["id"]
        est = (await client.post(f"/customers/{cust}/estimates", headers=h, json={"title": "Q"})).json()
        est = (await client.post(f"/estimates/{est['id']}/frames", headers=h,
                                 json={"source_design_id": design_id, "quantity": 1})).json()
        fid = est["frames"][0]["id"]

        r = await client.get(f"/estimates/{est['id']}/frames/{fid}/thumbnail.svg", headers=h)
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("image/svg+xml")
        assert r.text.lstrip().startswith("<svg")
        etag = r.headers["etag"]

        # Revalidation with the same ETag → 304, no body.
        r304 = await client.get(f"/estimates/{est['id']}/frames/{fid}/thumbnail.svg",
                                headers={**h, "If-None-Match": etag})
        assert r304.status_code == 304
        assert not r304.content

    async def test_frame_thumbnail_404(self, client, db_session):
        await create_user(db_session, "fthumb404@test.com", role="sales")
        h = auth_headers(await login(client, "fthumb404@test.com"))
        await seed_rates(db_session)
        cust = (await client.post("/customers", headers=h, json={"name": "Thumb404 Co"})).json()["id"]
        est = (await client.post(f"/customers/{cust}/estimates", headers=h, json={"title": "Q"})).json()
        assert (await client.get(
            f"/estimates/{est['id']}/frames/{uuid4()}/thumbnail.svg", headers=h,
        )).status_code == 404


# ── Other charges (PR-9 — labor / transport / installation) ───────

class TestOtherCharges:
    async def _estimate_with_frame(self, client, headers, db_session):
        await seed_rates(db_session)
        cust = (await client.post("/customers", headers=headers, json={"name": "Charges Co"})).json()["id"]
        design_id = (await client.post("/designs", headers=headers,
                                       json=make_design_payload("Charges Win"))).json()["id"]
        est = (await client.post(f"/customers/{cust}/estimates", headers=headers, json={"title": "Q"})).json()
        r = await client.post(f"/estimates/{est['id']}/frames", headers=headers,
                              json={"source_design_id": design_id, "quantity": 1})
        return r.json()

    async def test_put_charges_recomputes_totals(self, client, db_session):
        await create_user(db_session, "charges@test.com", role="sales")
        h = auth_headers(await login(client, "charges@test.com"))
        est = await self._estimate_with_frame(client, h, db_session)
        assert est["other_charges"] == [] and est["other_charges_total"] == 0

        r = await client.put(f"/estimates/{est['id']}", headers=h, json={
            "other_charges": [
                {"label": "Transport", "amount": 1500},
                {"label": "Installation", "amount": 2000},
            ],
        })
        assert r.status_code == 200
        body = r.json()
        assert body["other_charges_total"] == 3500.0
        assert [c["label"] for c in body["other_charges"]] == ["Transport", "Installation"]
        # Charges join the aggregate before discount/GST: taxable = frames + charges.
        assert body["taxable"] == round(body["subtotal"] + 3500.0, 2)
        assert body["grand_total"] > est["grand_total"]

        # Clearing the charges restores the original totals.
        r = await client.put(f"/estimates/{est['id']}", headers=h, json={"other_charges": []})
        assert r.json()["grand_total"] == est["grand_total"]

    async def test_charges_locked_with_estimate(self, client, db_session):
        await create_user(db_session, "charges_lock@test.com", role="sales")
        h = auth_headers(await login(client, "charges_lock@test.com"))
        est = await self._estimate_with_frame(client, h, db_session)
        await client.patch(f"/estimates/{est['id']}/status", headers=h, json={"status": "sent"})

        r = await client.put(f"/estimates/{est['id']}", headers=h,
                             json={"other_charges": [{"label": "Labor", "amount": 100}]})
        assert r.status_code == 409

    async def test_invalid_charges_rejected(self, client, db_session):
        await create_user(db_session, "charges_bad@test.com", role="sales")
        h = auth_headers(await login(client, "charges_bad@test.com"))
        est = await self._estimate_with_frame(client, h, db_session)

        # Negative amount and empty label are both schema violations.
        for bad in ({"label": "Labor", "amount": -5}, {"label": "", "amount": 10}):
            r = await client.put(f"/estimates/{est['id']}", headers=h, json={"other_charges": [bad]})
            assert r.status_code == 422

    async def test_charges_carry_into_revision_and_pdf(self, client, db_session):
        await create_user(db_session, "charges_rev@test.com", role="sales")
        h = auth_headers(await login(client, "charges_rev@test.com"))
        est = await self._estimate_with_frame(client, h, db_session)
        await client.put(f"/estimates/{est['id']}", headers=h,
                         json={"other_charges": [{"label": "Transport", "amount": 750}]})

        # The PDF renders with charge rows present (template must not error).
        pdf = await client.get(f"/estimates/{est['id']}/pdf", headers=h)
        assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"

        # Revise: the new revision keeps the charges and reprices identically.
        await client.patch(f"/estimates/{est['id']}/status", headers=h, json={"status": "sent"})
        rev = (await client.post(f"/estimates/{est['id']}/revise", headers=h)).json()
        assert rev["other_charges"] == [{"label": "Transport", "amount": 750}]
        assert rev["other_charges_total"] == 750.0


# ── Quote revisions ────────────────────────────────────────────────

class TestRevisions:
    async def _locked_estimate(self, client, h, db_session):
        """Customer + design + estimate with one frame, moved to 'sent'."""
        await seed_rates(db_session)
        cust = (await client.post("/customers", headers=h, json={"name": "Rev Co"})).json()["id"]
        design_id = (await client.post("/designs", headers=h, json=make_design_payload("Rev Win"))).json()["id"]
        est = (await client.post(f"/customers/{cust}/estimates", headers=h, json={"title": "Original"})).json()
        await client.post(f"/estimates/{est['id']}/frames", headers=h,
                          json={"source_design_id": design_id, "quantity": 2})
        r = await client.patch(f"/estimates/{est['id']}/status", headers=h, json={"status": "sent"})
        assert r.status_code == 200
        return r.json()

    async def test_revise_flow(self, client, db_session):
        await create_user(db_session, "revise@test.com", role="sales")
        h = auth_headers(await login(client, "revise@test.com"))
        source = await self._locked_estimate(client, h, db_session)

        r = await client.post(f"/estimates/{source['id']}/revise", headers=h)
        assert r.status_code == 201
        rev = r.json()
        assert rev["revision"] == 2
        assert rev["number"] == source["number"]        # same human-facing number
        assert rev["status"] == "draft"                  # fresh editable draft
        assert rev["parent_id"] == source["id"]
        assert len(rev["frames"]) == 1
        assert rev["grand_total"] == source["grand_total"]  # repriced, same rates

        # Source is now superseded and terminally locked.
        src = (await client.get(f"/estimates/{source['id']}", headers=h)).json()
        assert src["status"] == "superseded"
        assert (await client.patch(f"/estimates/{source['id']}/status", headers=h,
                                   json={"status": "draft"})).status_code == 409
        assert (await client.put(f"/estimates/{source['id']}", headers=h,
                                 json={"title": "x"})).status_code == 409

        # Audit trail recorded the revise.
        from sqlalchemy import select
        from app.models.audit import AuditLog
        rows = (await db_session.execute(
            select(AuditLog).where(AuditLog.action == "estimate.revise")
        )).scalars().all()
        assert any(row.entity_id == rev["id"] for row in rows)

    async def test_revise_draft_409(self, client, db_session):
        await create_user(db_session, "revise_draft@test.com", role="sales")
        h = auth_headers(await login(client, "revise_draft@test.com"))
        cust = (await client.post("/customers", headers=h, json={"name": "Draft Co"})).json()["id"]
        est = (await client.post(f"/customers/{cust}/estimates", headers=h, json={"title": "Q"})).json()
        assert (await client.post(f"/estimates/{est['id']}/revise", headers=h)).status_code == 409

    async def test_revise_superseded_409(self, client, db_session):
        await create_user(db_session, "revise_sup@test.com", role="sales")
        h = auth_headers(await login(client, "revise_sup@test.com"))
        source = await self._locked_estimate(client, h, db_session)
        assert (await client.post(f"/estimates/{source['id']}/revise", headers=h)).status_code == 201
        # Source is superseded now — revising it again must 409.
        assert (await client.post(f"/estimates/{source['id']}/revise", headers=h)).status_code == 409

    async def test_status_cannot_be_set_to_superseded(self, client, db_session):
        await create_user(db_session, "sup_manual@test.com", role="sales")
        h = auth_headers(await login(client, "sup_manual@test.com"))
        cust = (await client.post("/customers", headers=h, json={"name": "Manual Co"})).json()["id"]
        est = (await client.post(f"/customers/{cust}/estimates", headers=h, json={"title": "Q"})).json()
        r = await client.patch(f"/estimates/{est['id']}/status", headers=h, json={"status": "superseded"})
        assert r.status_code == 422  # rejected by the request schema

    async def test_accepted_at_set_and_cleared(self, client, db_session):
        await create_user(db_session, "accepted_at@test.com", role="sales")
        h = auth_headers(await login(client, "accepted_at@test.com"))
        cust = (await client.post("/customers", headers=h, json={"name": "Accept Co"})).json()["id"]
        est = (await client.post(f"/customers/{cust}/estimates", headers=h, json={"title": "Q"})).json()

        from uuid import UUID
        from sqlalchemy import select
        from app.models.estimate import Estimate as EstimateModel
        await client.patch(f"/estimates/{est['id']}/status", headers=h, json={"status": "accepted"})
        row = (await db_session.execute(
            select(EstimateModel).where(EstimateModel.id == UUID(est["id"])))).scalar_one()
        assert row.accepted_at is not None

        await client.patch(f"/estimates/{est['id']}/status", headers=h, json={"status": "draft"})
        await db_session.refresh(row)
        assert row.accepted_at is None  # un-accepting removes it from revenue

    async def test_unique_number_revision_constraint(self, db_session):
        """The composite unique is what the revise race relies on."""
        import pytest
        from sqlalchemy.exc import IntegrityError
        from app.models.estimate import Estimate as EstimateModel
        from app.models.customer import Customer as CustomerModel
        from tests.conftest import create_user as mk_user
        user = await mk_user(db_session, "uq_rev@test.com")
        cust = CustomerModel(name="UQ Co", created_by=user.id)
        db_session.add(cust)
        await db_session.flush()

        def _estimate(rev):
            return EstimateModel(customer_id=cust.id, number=9001, revision=rev, created_by=user.id)

        db_session.add(_estimate(1))
        await db_session.flush()
        db_session.add(_estimate(2))
        await db_session.flush()  # same number, different revision — OK
        with pytest.raises(IntegrityError):
            db_session.add(_estimate(2))
            await db_session.flush()


# ── Auto-expiry (derived, read-time) ───────────────────────────────

class TestExpiry:
    async def test_expiry_derivation(self, client, db_session):
        await create_user(db_session, "expiry@test.com", role="sales")
        h = auth_headers(await login(client, "expiry@test.com"))
        cust = (await client.post("/customers", headers=h, json={"name": "Expiry Co"})).json()["id"]
        est = (await client.post(f"/customers/{cust}/estimates", headers=h,
                                 json={"title": "Q", "valid_until": "2020-01-01"})).json()

        # Draft with a past valid_until is NOT expired — only live 'sent' quotes are.
        assert est["is_expired"] is False

        r = (await client.patch(f"/estimates/{est['id']}/status", headers=h, json={"status": "sent"})).json()
        assert r["is_expired"] is True
        listed = (await client.get(f"/customers/{cust}/estimates", headers=h)).json()
        assert listed[0]["is_expired"] is True

        # Accepting an expired quote stays allowed, and acceptance ends expiry.
        r = await client.patch(f"/estimates/{est['id']}/status", headers=h, json={"status": "accepted"})
        assert r.status_code == 200
        assert r.json()["is_expired"] is False

    async def test_expiry_self_corrects_when_validity_extended(self, client, db_session):
        await create_user(db_session, "expiry2@test.com", role="sales")
        h = auth_headers(await login(client, "expiry2@test.com"))
        cust = (await client.post("/customers", headers=h, json={"name": "Extend Co"})).json()["id"]
        est = (await client.post(f"/customers/{cust}/estimates", headers=h,
                                 json={"title": "Q", "valid_until": "2020-01-01"})).json()
        await client.patch(f"/estimates/{est['id']}/status", headers=h, json={"status": "sent"})

        # Editing terms requires draft; extend validity there, then re-send.
        await client.patch(f"/estimates/{est['id']}/status", headers=h, json={"status": "draft"})
        r = (await client.put(f"/estimates/{est['id']}", headers=h, json={"valid_until": "2099-01-01"})).json()
        assert r["is_expired"] is False
        r = (await client.patch(f"/estimates/{est['id']}/status", headers=h, json={"status": "sent"})).json()
        assert r["is_expired"] is False  # no scheduler needed — derived fresh


# ── Soft-delete + restore ─────────────────────────────────────────

class TestSoftDelete:
    async def test_customer_delete_hides_then_restore_brings_back(self, client, db_session):
        await create_user(db_session, "soft_del@test.com", role="owner")
        h = auth_headers(await login(client, "soft_del@test.com"))
        cid = (await client.post("/customers", headers=h, json={"name": "Restore Me"})).json()["id"]

        # Delete → gone from the list and 404 on direct get.
        assert (await client.delete(f"/customers/{cid}", headers=h)).status_code == 204
        listed = [c["id"] for c in (await client.get("/customers", headers=h)).json()]
        assert cid not in listed
        assert (await client.get(f"/customers/{cid}", headers=h)).status_code == 404

        # Restore → back in the list.
        assert (await client.post(f"/customers/{cid}/restore", headers=h)).status_code == 200
        listed = [c["id"] for c in (await client.get("/customers", headers=h)).json()]
        assert cid in listed

    async def test_sales_cannot_restore(self, client, db_session):
        await create_user(db_session, "soft_owner@test.com", role="owner")
        ho = auth_headers(await login(client, "soft_owner@test.com"))
        cid = (await client.post("/customers", headers=ho, json={"name": "X"})).json()["id"]
        await client.delete(f"/customers/{cid}", headers=ho)

        await create_user(db_session, "soft_sales@test.com", role="sales")
        hs = auth_headers(await login(client, "soft_sales@test.com"))
        assert (await client.post(f"/customers/{cid}/restore", headers=hs)).status_code == 403


# ── Trash view ─────────────────────────────────────────────────────

class TestTrash:
    async def test_trash_lists_deleted_and_restores(self, client, db_session):
        await create_user(db_session, "trash_owner@test.com", role="owner")
        h = auth_headers(await login(client, "trash_owner@test.com"))

        # Delete one of each entity.
        cust = (await client.post("/customers", headers=h, json={"name": "Trash Cust"})).json()["id"]
        design = (await client.post("/designs", headers=h, json=make_design_payload("Trash Design"))).json()["id"]
        cust2 = (await client.post("/customers", headers=h, json={"name": "Keeper"})).json()["id"]
        est = (await client.post(f"/customers/{cust2}/estimates", headers=h, json={"title": "Trash Est"})).json()["id"]
        await client.delete(f"/customers/{cust}", headers=h)
        await client.delete(f"/designs/{design}", headers=h)
        await client.delete(f"/estimates/{est}", headers=h)

        trash = (await client.get("/trash", headers=h)).json()
        assert cust in [c["id"] for c in trash["customers"]]
        assert design in [d["id"] for d in trash["designs"]]
        est_row = next(e for e in trash["estimates"] if e["id"] == est)
        assert est_row["customer_deleted"] is False

        # Restore each; audit rows recorded.
        assert (await client.post(f"/customers/{cust}/restore", headers=h)).status_code == 200
        assert (await client.post(f"/designs/{design}/restore", headers=h)).status_code == 200
        assert (await client.post(f"/estimates/{est}/restore", headers=h)).status_code == 200
        trash = (await client.get("/trash", headers=h)).json()
        assert not trash["customers"] and not trash["designs"] and not trash["estimates"]

        from sqlalchemy import select
        from app.models.audit import AuditLog
        actions = {a.action for a in (await db_session.execute(select(AuditLog))).scalars().all()}
        assert {"customer.restore", "design.restore", "estimate.restore"} <= actions

    async def test_trash_403_for_sales(self, client, db_session):
        await create_user(db_session, "trash_sales@test.com", role="sales")
        h = auth_headers(await login(client, "trash_sales@test.com"))
        assert (await client.get("/trash", headers=h)).status_code == 403

    async def test_restore_estimate_of_deleted_customer_409(self, client, db_session):
        await create_user(db_session, "trash_order@test.com", role="owner")
        h = auth_headers(await login(client, "trash_order@test.com"))
        cust = (await client.post("/customers", headers=h, json={"name": "Order Co"})).json()["id"]
        est = (await client.post(f"/customers/{cust}/estimates", headers=h, json={"title": "Q"})).json()["id"]
        await client.delete(f"/estimates/{est}", headers=h)
        await client.delete(f"/customers/{cust}", headers=h)

        trash = (await client.get("/trash", headers=h)).json()
        est_row = next(e for e in trash["estimates"] if e["id"] == est)
        assert est_row["customer_deleted"] is True

        r = await client.post(f"/estimates/{est}/restore", headers=h)
        assert r.status_code == 409
        assert "customer" in r.json()["detail"].lower()

        # Restore the customer first, then the estimate goes through.
        assert (await client.post(f"/customers/{cust}/restore", headers=h)).status_code == 200
        assert (await client.post(f"/estimates/{est}/restore", headers=h)).status_code == 200


# ── Settings (company profile) RBAC ───────────────────────────────

class TestSettingsRBAC:
    async def test_sales_can_read_company(self, client, db_session):
        await create_user(db_session, "settings_read@test.com", role="sales")
        h = auth_headers(await login(client, "settings_read@test.com"))
        assert (await client.get("/settings/company", headers=h)).status_code == 200

    async def test_sales_cannot_update_company(self, client, db_session):
        await create_user(db_session, "settings_write@test.com", role="sales")
        h = auth_headers(await login(client, "settings_write@test.com"))
        assert (await client.put("/settings/company", headers=h, json={"name": "X"})).status_code == 403

    async def test_owner_can_update_company(self, client, db_session):
        await create_user(db_session, "settings_owner@test.com", role="owner")
        h = auth_headers(await login(client, "settings_owner@test.com"))
        r = await client.put("/settings/company", headers=h, json={"name": "Acme Steel"})
        assert r.status_code == 200 and r.json()["name"] == "Acme Steel"


# ── Commercial settings: GST snapshot + advance fallback ──────────

class TestCommercialSettings:
    async def test_gst_snapshot_immutable_and_advance_fallback(self, client, db_session):
        await seed_rates(db_session)
        await create_user(db_session, "commercial@test.com", role="owner")
        h = auth_headers(await login(client, "commercial@test.com"))
        cust = (await client.post("/customers", headers=h, json={"name": "GST Co"})).json()["id"]
        design_id = (await client.post("/designs", headers=h, json=make_design_payload("GST Win"))).json()["id"]

        # Estimate created under the default settings → snapshots 18%.
        est_old = (await client.post(f"/customers/{cust}/estimates", headers=h, json={"title": "Old"})).json()
        assert est_old["gst_pct"] == 18
        est_old = (await client.post(f"/estimates/{est_old['id']}/frames", headers=h,
                                     json={"source_design_id": design_id, "quantity": 1})).json()
        gst_at_18 = est_old["gst"]
        assert gst_at_18 > 0

        # Change the company defaults.
        r = await client.put("/settings/company", headers=h,
                             json={"gst_pct": 12, "default_advance_pct": 30})
        assert r.status_code == 200 and r.json()["gst_pct"] == 12

        # New estimate (advance omitted) → snapshots 12% and falls back to 30%.
        est_new = (await client.post(f"/customers/{cust}/estimates", headers=h, json={"title": "New"})).json()
        assert est_new["gst_pct"] == 12
        assert est_new["advance_pct"] == 30
        est_new = (await client.post(f"/estimates/{est_new['id']}/frames", headers=h,
                                     json={"source_design_id": design_id, "quantity": 1})).json()
        assert est_new["gst"] == round(est_new["taxable"] * 0.12, 2)

        # Explicit advance still wins over the fallback.
        est_exp = (await client.post(f"/customers/{cust}/estimates", headers=h,
                                     json={"title": "Explicit", "advance_pct": 70})).json()
        assert est_exp["advance_pct"] == 70

        # Recomputing the OLD estimate (terms update) must keep its frozen 18%.
        est_old = (await client.put(f"/estimates/{est_old['id']}", headers=h,
                                    json={"title": "Old renamed"})).json()
        assert est_old["gst_pct"] == 18
        assert est_old["gst"] == gst_at_18

        # A duplicate is a new quote — it picks up the current 12% setting.
        dup = (await client.post(f"/estimates/{est_old['id']}/duplicate", headers=h)).json()
        assert dup["gst_pct"] == 12


# ── Estimate listing: pagination, search, frame_count ──────────────

class TestEstimateListing:
    async def test_pagination_and_search(self, client, db_session):
        await create_user(db_session, "est_list@test.com", role="sales")
        h = auth_headers(await login(client, "est_list@test.com"))
        cust = (await client.post("/customers", headers=h, json={"name": "List Co"})).json()["id"]
        numbers = []
        for i in range(5):
            est = (await client.post(f"/customers/{cust}/estimates", headers=h,
                                     json={"title": f"Quote {i}"})).json()
            numbers.append(est["number"])

        base = f"/customers/{cust}/estimates"
        listed = (await client.get(base, headers=h)).json()
        assert len(listed) == 5
        assert [e["number"] for e in listed] == sorted(numbers, reverse=True)

        page = (await client.get(f"{base}?limit=2", headers=h)).json()
        assert [e["number"] for e in page] == sorted(numbers, reverse=True)[:2]

        page = (await client.get(f"{base}?limit=2&offset=4", headers=h)).json()
        assert len(page) == 1

        found = (await client.get(f"{base}?q=Quote 3", headers=h)).json()
        assert [e["title"] for e in found] == ["Quote 3"]

        # A numeric term also matches the estimate number.
        found = (await client.get(f"{base}?q={numbers[0]}", headers=h)).json()
        assert numbers[0] in [e["number"] for e in found]

        assert (await client.get(f"{base}?limit=201", headers=h)).status_code == 422

    async def test_list_404_on_missing_customer(self, client, db_session):
        await create_user(db_session, "est_list404@test.com", role="sales")
        h = auth_headers(await login(client, "est_list404@test.com"))
        from uuid import uuid4
        assert (await client.get(f"/customers/{uuid4()}/estimates", headers=h)).status_code == 404

    async def test_list_404_on_deleted_customer(self, client, db_session):
        """Estimates of a soft-deleted customer must not leak through the list."""
        await create_user(db_session, "est_listdel@test.com", role="owner")
        h = auth_headers(await login(client, "est_listdel@test.com"))
        cust = (await client.post("/customers", headers=h, json={"name": "Gone Co"})).json()["id"]
        await client.post(f"/customers/{cust}/estimates", headers=h, json={"title": "Q"})
        assert (await client.delete(f"/customers/{cust}", headers=h)).status_code == 204
        assert (await client.get(f"/customers/{cust}/estimates", headers=h)).status_code == 404

    async def test_frame_count_in_summary(self, client, db_session):
        await seed_rates(db_session)
        await create_user(db_session, "est_fc@test.com", role="sales")
        h = auth_headers(await login(client, "est_fc@test.com"))
        cust = (await client.post("/customers", headers=h, json={"name": "FC Co"})).json()["id"]
        design_id = (await client.post("/designs", headers=h, json=make_design_payload("FC Win"))).json()["id"]
        est = (await client.post(f"/customers/{cust}/estimates", headers=h, json={"title": "Q"})).json()
        for _ in range(2):
            r = await client.post(f"/estimates/{est['id']}/frames", headers=h,
                                  json={"source_design_id": design_id, "quantity": 1})
            assert r.status_code == 200
        listed = (await client.get(f"/customers/{cust}/estimates", headers=h)).json()
        assert listed[0]["frame_count"] == 2
        assert listed[0]["grand_total"] > 0


# ── Dashboard metrics + global estimate search ─────────────────────

class TestDashboard:
    async def _seed(self, client, db_session, h):
        """Two customers; estimates across statuses incl. one accepted with a
        frame (real revenue), one superseded, and one on a deleted customer."""
        await seed_rates(db_session)
        c1 = (await client.post("/customers", headers=h, json={"name": "Metric Alpha"})).json()["id"]
        c2 = (await client.post("/customers", headers=h, json={"name": "Metric Beta"})).json()["id"]
        design = (await client.post("/designs", headers=h, json=make_design_payload("Metric Win"))).json()["id"]

        drafts = [(await client.post(f"/customers/{c1}/estimates", headers=h,
                                     json={"title": f"Draft {i}"})).json() for i in range(2)]

        accepted = (await client.post(f"/customers/{c1}/estimates", headers=h, json={"title": "Winner"})).json()
        accepted = (await client.post(f"/estimates/{accepted['id']}/frames", headers=h,
                                      json={"source_design_id": design, "quantity": 1})).json()
        await client.patch(f"/estimates/{accepted['id']}/status", headers=h, json={"status": "accepted"})

        # A sent quote that gets revised → source superseded (excluded from pipeline).
        sent = (await client.post(f"/customers/{c1}/estimates", headers=h, json={"title": "Sent Q"})).json()
        await client.post(f"/estimates/{sent['id']}/frames", headers=h,
                          json={"source_design_id": design, "quantity": 1})
        await client.patch(f"/estimates/{sent['id']}/status", headers=h, json={"status": "sent"})
        await client.post(f"/estimates/{sent['id']}/revise", headers=h)  # rev 2 draft + superseded source

        # Estimate under a customer that then gets deleted (excluded everywhere).
        ghost = (await client.post(f"/customers/{c2}/estimates", headers=h, json={"title": "Ghost"})).json()
        await client.delete(f"/customers/{c2}", headers=h)

        return {"drafts": drafts, "accepted": accepted, "sent": sent, "ghost": ghost, "c1": c1}

    async def test_metrics_math(self, client, db_session):
        await create_user(db_session, "dash@test.com", role="owner")
        h = auth_headers(await login(client, "dash@test.com"))
        seeded = await self._seed(client, db_session, h)

        m = (await client.get("/dashboard/metrics", headers=h)).json()
        pipeline = {p["status"]: p for p in m["pipeline"]}

        # 2 plain drafts + 1 revision draft; superseded and ghost excluded.
        assert pipeline["draft"]["count"] == 3
        assert pipeline["accepted"]["count"] == 1
        assert pipeline["accepted"]["total"] == seeded["accepted"]["grand_total"]
        assert "superseded" not in pipeline
        assert "sent" not in pipeline  # it was revised away

        # Accepted this month shows up in monthly revenue.
        assert sum(r["total"] for r in m["monthly_revenue"]) == seeded["accepted"]["grand_total"]

        assert m["active_customers"] == 1  # Beta was deleted
        assert m["active_designs"] == 1
        recent_ids = [e["id"] for e in m["recent_estimates"]]
        assert seeded["ghost"]["id"] not in recent_ids
        assert seeded["sent"]["id"] not in recent_ids  # superseded

    async def test_global_search(self, client, db_session):
        await create_user(db_session, "gsearch@test.com", role="owner")
        h = auth_headers(await login(client, "gsearch@test.com"))
        seeded = await self._seed(client, db_session, h)

        # By title.
        found = (await client.get("/estimates?q=Winner", headers=h)).json()
        assert [e["id"] for e in found] == [seeded["accepted"]["id"]]

        # By customer name — everything under Metric Alpha (ghost customer excluded).
        found = (await client.get("/estimates?q=Metric Alpha", headers=h)).json()
        assert seeded["ghost"]["id"] not in [e["id"] for e in found]
        assert len(found) >= 4

        # By number.
        num = seeded["accepted"]["number"]
        found = (await client.get(f"/estimates?q={num}", headers=h)).json()
        assert num in [e["number"] for e in found]

        # Status filter + pagination.
        drafts = (await client.get("/estimates?status=draft", headers=h)).json()
        assert {e["status"] for e in drafts} == {"draft"}
        page = (await client.get("/estimates?status=draft&limit=2&offset=2", headers=h)).json()
        assert len(page) == len(drafts) - 2


# ── Tree bounds enforcement on /price ──────────────────────────────

class TestPriceBounds:
    async def test_price_rejects_oversized_tree(self, client, db_session):
        await create_user(db_session, "price_bounds@test.com", role="sales")
        h = auth_headers(await login(client, "price_bounds@test.com"))
        tree = make_design_payload("Huge", width=40.0, height=3.0)["tree_json"]
        resp = await client.post("/price", headers=h, json={"tree_json": tree})
        assert resp.status_code == 422
        assert any("B-1" in e for e in resp.json()["detail"]["validation_errors"])


# ── BOM CSV export ─────────────────────────────────────────────────

class TestBomCsv:
    async def test_bom_csv_content_and_aggregation(self, client, db_session):
        await seed_rates(db_session)
        await create_user(db_session, "bom@test.com", role="sales")
        h = auth_headers(await login(client, "bom@test.com"))
        cust = (await client.post("/customers", headers=h, json={"name": "BOM Co"})).json()["id"]
        design_id = (await client.post("/designs", headers=h, json=make_design_payload("BOM Win"))).json()["id"]
        est = (await client.post(f"/customers/{cust}/estimates", headers=h, json={"title": "Q"})).json()
        # Two frames of the same design (qty 2 and 1) — Frame RFT must aggregate ×3.
        await client.post(f"/estimates/{est['id']}/frames", headers=h,
                          json={"source_design_id": design_id, "quantity": 2})
        await client.post(f"/estimates/{est['id']}/frames", headers=h,
                          json={"source_design_id": design_id, "quantity": 1})

        r = await client.get(f"/estimates/{est['id']}/bom.csv", headers=h)
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/csv")
        assert "attachment" in r.headers["content-disposition"]

        text = r.content.decode("utf-8")
        assert text.startswith("\ufeff")  # Excel BOM
        lines = [ln for ln in text.lstrip("\ufeff").splitlines() if ln]
        assert lines[0] == "Item,Quantity,Unit,Cost"

        # The 4×3 window frame = 14 RFT per unit; 3 units total = 42 RFT.
        frame_row = next(ln for ln in lines if ln.startswith("Frame,"))
        assert frame_row.split(",")[1] == "42.0"

    async def test_bom_csv_404_on_deleted(self, client, db_session):
        await create_user(db_session, "bom404@test.com", role="owner")
        h = auth_headers(await login(client, "bom404@test.com"))
        cust = (await client.post("/customers", headers=h, json={"name": "B Co"})).json()["id"]
        est = (await client.post(f"/customers/{cust}/estimates", headers=h, json={"title": "Q"})).json()["id"]
        await client.delete(f"/estimates/{est}", headers=h)
        assert (await client.get(f"/estimates/{est}/bom.csv", headers=h)).status_code == 404


# ── PDF rate limit ─────────────────────────────────────────────────

class TestPdfRateLimit:
    async def test_pdf_429_after_limit(self, client, db_session, monkeypatch):
        """11th PDF download within a minute must be rejected (10/minute).
        The renderer is mocked — WeasyPrint needs GTK, unavailable on Windows CI."""
        from app.routers import estimates as estimates_router
        from app.services.ratelimit import limiter

        monkeypatch.setattr(estimates_router, "generate_estimate_pdf",
                            lambda estimate, company: b"%PDF-1.4 fake")

        await create_user(db_session, "pdf_rl@test.com", role="sales")
        h = auth_headers(await login(client, "pdf_rl@test.com"))
        cust = (await client.post("/customers", headers=h, json={"name": "PDF Co"})).json()["id"]
        eid = (await client.post(f"/customers/{cust}/estimates", headers=h, json={"title": "Q"})).json()["id"]

        limiter.enabled = True  # the client fixture disables it globally
        try:
            codes = []
            for _ in range(11):
                codes.append((await client.get(f"/estimates/{eid}/pdf", headers=h)).status_code)
        finally:
            limiter.enabled = False
        assert codes[:10] == [200] * 10
        assert codes[10] == 429


# ── Customer-facing PDF ────────────────────────────────────────────

class TestCustomerPdf:
    async def test_customer_pdf_download(self, client, db_session, monkeypatch):
        """The customer endpoint serves a PDF under a 'Quotation' filename.
        The renderer is mocked — WeasyPrint needs GTK, unavailable on Windows CI."""
        from app.routers import estimates as estimates_router
        monkeypatch.setattr(estimates_router, "generate_customer_estimate_pdf",
                            lambda estimate, company: b"%PDF-1.4 fake")

        await create_user(db_session, "cust_pdf@test.com", role="sales")
        h = auth_headers(await login(client, "cust_pdf@test.com"))
        cust = (await client.post("/customers", headers=h, json={"name": "PDF Co"})).json()["id"]
        eid = (await client.post(f"/customers/{cust}/estimates", headers=h, json={"title": "Q"})).json()["id"]

        resp = await client.get(f"/estimates/{eid}/pdf/customer", headers=h)
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert "SteelCAD_Quotation_EST-" in resp.headers["content-disposition"]

    async def test_customer_pdf_404_on_deleted(self, client, db_session):
        await create_user(db_session, "cust_pdf404@test.com", role="owner")
        h = auth_headers(await login(client, "cust_pdf404@test.com"))
        cust = (await client.post("/customers", headers=h, json={"name": "B Co"})).json()["id"]
        est = (await client.post(f"/customers/{cust}/estimates", headers=h, json={"title": "Q"})).json()["id"]
        await client.delete(f"/estimates/{est}", headers=h)
        assert (await client.get(f"/estimates/{est}/pdf/customer", headers=h)).status_code == 404


# ── Health endpoints ───────────────────────────────────────────────

class TestHealth:
    async def test_health(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    async def test_readiness(self, client):
        resp = await client.get("/ready")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ready"
