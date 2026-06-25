"""
API integration tests — auth, RBAC enforcement, core CRUD.

Requires a running Postgres (see conftest.py). Skipped automatically if
TEST_DATABASE_URL is unreachable.
"""
import pytest
from tests.conftest import create_user, login, auth_headers


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
        assert resp.status_code == 403  # HTTPBearer returns 403 when no credentials


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
        resp = await client.post("/designs", headers=auth_headers(tokens), json={
            "name": "Test Window",
            "outer_width": 4.0,
            "outer_height": 3.0,
            "section_size": "5",
            "gauge": "18G",
            "tree_json": {
                "productType": "window",
                "type": "frame",
                "width": 4.0,
                "height": 3.0,
                "sectionSize": "5",
                "gauge": "18G",
                "children": [{
                    "type": "region",
                    "regionType": "fixed",
                    "width": 4.0,
                    "height": 3.0,
                }]
            }
        })
        assert resp.status_code == 201
        assert resp.json()["name"] == "Test Window"

    async def test_all_roles_see_all_designs(self, client, db_session):
        """All roles share the same design pool — no per-user scoping."""
        # Create a design as sales user 1
        await create_user(db_session, "design_creator@test.com", role="sales")
        tokens1 = await login(client, "design_creator@test.com")
        create_resp = await client.post("/designs", headers=auth_headers(tokens1), json={
            "name": "Shared Design",
            "outer_width": 3.0, "outer_height": 2.0,
            "section_size": "5", "gauge": "18G",
            "tree_json": {
                "productType": "window", "type": "frame",
                "width": 3.0, "height": 2.0,
                "sectionSize": "5", "gauge": "18G",
                "children": [{"type": "region", "regionType": "fixed", "width": 3.0, "height": 2.0}],
            }
        })
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

    async def test_sales_can_delete_customer(self, client, db_session):
        await create_user(db_session, "sales_del_cust@test.com", role="sales")
        tokens = await login(client, "sales_del_cust@test.com")
        create_resp = await client.post("/customers", headers=auth_headers(tokens), json={"name": "To Delete"})
        cid = create_resp.json()["id"]
        del_resp = await client.delete(f"/customers/{cid}", headers=auth_headers(tokens))
        assert del_resp.status_code == 204


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
