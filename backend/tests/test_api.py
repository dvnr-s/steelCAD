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


# ── Tree bounds enforcement on /price ──────────────────────────────

class TestPriceBounds:
    async def test_price_rejects_oversized_tree(self, client, db_session):
        await create_user(db_session, "price_bounds@test.com", role="sales")
        h = auth_headers(await login(client, "price_bounds@test.com"))
        tree = make_design_payload("Huge", width=40.0, height=3.0)["tree_json"]
        resp = await client.post("/price", headers=h, json={"tree_json": tree})
        assert resp.status_code == 422
        assert any("B-1" in e for e in resp.json()["detail"]["validation_errors"])


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
