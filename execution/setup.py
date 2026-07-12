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


# Runs inside the backend container: creates the user row unless it exists.
# Credentials are passed via environment variables to avoid shell-quoting issues.
_CREATE_USER_SNIPPET = """
import asyncio, os
from sqlalchemy import select
from app.database import async_session_factory
from app.models.user import User
from app.services.auth import hash_password

async def main():
    email = os.environ["SETUP_EMAIL"]
    async with async_session_factory() as db:
        existing = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if existing:
            print("EXISTS")
            return
        db.add(User(
            email=email,
            name=os.environ["SETUP_NAME"],
            password=hash_password(os.environ["SETUP_PASSWORD"]),
            role="sales",  # promoted to admin via /auth/bootstrap-admin next
        ))
        await db.commit()
        print("CREATED")

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
    if "EXISTS" in result.stdout:
        print("  Account already exists, logging in...")
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    return r.json()


def promote_to_admin(access_token, email):
    """
    Directly promote user to admin via a raw SQL call through the backend.
    We expose a one-time admin seed endpoint for this.
    """
    # We'll use the /rates/seed approach — but we need admin first.
    # Instead we promote via the admin-bootstrap endpoint we add below.
    r = requests.post(
        f"{BASE}/auth/bootstrap-admin",
        json={"email": email},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if r.status_code == 200:
        print(f"  ✅ {email} promoted to admin")
        return True
    elif r.status_code == 404:
        print("  ℹ️  Bootstrap endpoint not yet available — you may need to restart backend after update")
        return False
    else:
        print(f"  ⚠️  Could not auto-promote: {r.text}")
        return False


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
    password = input("   Password (min 8 chars): ").strip()

    if len(password) < 8:
        print("❌ Password must be at least 8 characters")
        sys.exit(1)

    print("\n🔑 Creating account (via backend container)...")
    try:
        tokens = register_admin(email, password, name)
        access_token = tokens["access_token"]
        print(f"  ✅ Signed in as {email}")
    except Exception as e:
        print(f"  ❌ Account setup failed: {e}")
        sys.exit(1)

    print("\n👑 Promoting to admin...")
    promote_to_admin(access_token, email)

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
