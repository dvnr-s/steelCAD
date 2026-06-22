"""
SteelCAD First-Run Setup Script
================================
Run this ONCE after `docker-compose up -d` to:
  1. Wait for the backend to be ready
  2. Register your admin account
  3. Seed the default material rates

Usage:
  python execution/setup.py

Requirements: requests (pip install requests)
"""
import sys
import time
import json

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


def register_admin(email, password, name):
    """Register the user and return tokens."""
    r = requests.post(f"{BASE}/auth/register", json={"email": email, "password": password, "name": name})
    if r.status_code == 409:
        # Already exists — try logging in
        print(f"  Account already exists, logging in...")
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

    print("\n🔑 Registering account...")
    try:
        tokens = register_admin(email, password, name)
        access_token = tokens["access_token"]
        print(f"  ✅ Registered as {email}")
    except Exception as e:
        print(f"  ❌ Registration failed: {e}")
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
