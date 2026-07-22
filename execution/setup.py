"""
SteelCAD First-Run Setup Script
================================
Run this ONCE after `docker-compose up -d` to:
  1. Wait for the backend to be ready
  2. Create your admin account (accounts are invite-only — the first user is
     created directly in the database via the backend container)
  3. Seed the default material rates

Usage:
  python execution/setup.py

Requirements: requests (pip install requests), Docker running the compose stack
"""
import getpass
import subprocess
import sys
import time

try:
    import requests
except ImportError:
    print("Installing 'requests'...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "-q"])
    import requests

BASE = "http://localhost:8000"


def wait_for_backend(timeout=60):
    """Poll /health until the backend responds."""
    print("⏳ Waiting for backend to start...", end="", flush=True)
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get(f"{BASE}/health", timeout=2)
            if r.status_code == 200:
                print(" ✅")
                return True
        except Exception:
            pass
        print(".", end="", flush=True)
        time.sleep(2)
    print(" ❌ timed out")
    return False


# Runs inside the backend container: creates the first user and, when the
# system has no admin yet, promotes them to admin directly in the DB. This is
# the trusted first-run seam (host-side docker access), so it does NOT depend on
# the /auth/bootstrap-admin HTTP endpoint — that endpoint stays disabled unless
# BOOTSTRAP_ADMIN_SECRET is explicitly set. Credentials pass via env vars to
# avoid shell-quoting issues.
_CREATE_USER_SNIPPET = """
import asyncio, os
from sqlalchemy import select, func
from app.database import async_session_factory
from app.models.user import User, ROLE_ADMIN

async def main():
    from app.services.auth import hash_password
    email = os.environ["SETUP_EMAIL"]
    async with async_session_factory() as db:
        admin_count = (await db.execute(
            select(func.count(User.id)).where(User.role == ROLE_ADMIN, User.deleted_at.is_(None))
        )).scalar() or 0
        first_admin = admin_count == 0  # first-ever admin bootstraps the system

        existing = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if existing:
            if first_admin and existing.deleted_at is None:
                existing.role = ROLE_ADMIN
                existing.is_admin = True
                await db.commit()
                print("PROMOTED")
            else:
                print("EXISTS")
            return
        db.add(User(
            email=email,
            name=os.environ["SETUP_NAME"],
            password=hash_password(os.environ["SETUP_PASSWORD"]),
            role=ROLE_ADMIN if first_admin else "sales",
            is_admin=first_admin,
        ))
        await db.commit()
        print("CREATED_ADMIN" if first_admin else "CREATED")

asyncio.run(main())
"""


def register_admin(email, password, name):
    """Create the first user (invite-only system — no public register endpoint),
    then log in over HTTP and return tokens."""
    result = subprocess.run(
        [
            "docker", "compose", "exec", "-T",
            "-e", f"SETUP_EMAIL={email}",
            "-e", f"SETUP_NAME={name}",
            "-e", f"SETUP_PASSWORD={password}",
            "backend", "python", "-c", _CREATE_USER_SNIPPET,
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Could not create user in backend container: {result.stderr.strip()}")
    out = result.stdout
    if "CREATED_ADMIN" in out or "PROMOTED" in out:
        print(f"  ✅ {email} is the admin account")
    elif "EXISTS" in out:
        print("  Account already exists, logging in...")
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    return r.json()


def seed_rates(access_token):
    """POST /rates/seed with admin token."""
    r = requests.post(
        f"{BASE}/rates/seed",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if r.status_code in (200, 201):
        data = r.json()
        print(f"  ✅ Rates seeded: {data.get('message', 'done')}")
        return True
    elif r.status_code == 403:
        print("  ⚠️  Not admin yet — rates not seeded. Promote to admin first, then re-run.")
        return False
    else:
        print(f"  ❌ Seed failed: {r.text}")
        return False


def main():
    print("\n🔧 SteelCAD First-Run Setup\n" + "─" * 40)

    if not wait_for_backend():
        print("\n❌ Backend is not running.")
        print("   Make sure Docker Desktop is running and you have run:")
        print("   docker-compose up -d")
        sys.exit(1)

    print("\n📋 Admin Account Setup")
    print("   This account will have access to rate management.")
    email = input("   Email: ").strip()
    name  = input("   Name:  ").strip()
    # getpass: the password must not be echoed to the terminal or scrollback.
    password = getpass.getpass("   Password (min 8 chars): ").strip()

    if len(password) < 8:
        print("❌ Password must be at least 8 characters")
        sys.exit(1)

    print("\n🔑 Creating admin account (via backend container)...")
    try:
        tokens = register_admin(email, password, name)
        access_token = tokens["access_token"]
        print(f"  ✅ Signed in as {email}")
    except Exception as e:
        print(f"  ❌ Account setup failed: {e}")
        sys.exit(1)

    print("\n💰 Seeding default material rates...")
    seed_rates(access_token)

    print("\n" + "─" * 40)
    print("✅ Setup complete!")
    print(f"\n   Open: http://localhost:5173")
    print(f"   Login with: {email}")
    print("\n   If rates were not seeded (not yet admin),")
    print("   log in and visit /rates → click seed.")


if __name__ == "__main__":
    main()
