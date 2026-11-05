"""
SteelCAD on Render — idempotent first-run setup, executed by start.sh on every boot.

Render's free tier has no shell, so the two steps deploy/bootstrap.sh performs
over `docker compose exec` (create the first admin, seed the rate table) run
here instead, inside the container, after migrations and before serving.

Safe on every restart:
  - the admin is created only if INITIAL_ADMIN_EMAIL does not already exist, so
    a password changed in the app is never reset by a redeploy;
  - rate seeding reuses the /rates/seed route logic, which skips existing codes.
"""
import asyncio
import os
import sys

from pydantic import BaseModel, EmailStr
from sqlalchemy import select

from app.database import async_session_factory, engine
from app.models.user import User
from app.routers.rates import seed_rates
from app.services.auth import hash_password


class _EmailCheck(BaseModel):
    email: EmailStr


async def main() -> None:
    email = os.environ.get("INITIAL_ADMIN_EMAIL", "").strip()
    password = os.environ.get("INITIAL_ADMIN_PASSWORD", "")

    async with async_session_factory() as db:
        if email and password:
            # /auth/login parses the body with EmailStr, so an address it would
            # reject (e.g. a .local domain) yields an admin that can never sign
            # in. Refuse to boot rather than leave that trap behind.
            try:
                _EmailCheck(email=email)
            except Exception:
                sys.exit(f"first_run: INITIAL_ADMIN_EMAIL={email!r} is not an address the login endpoint accepts")

            if await db.scalar(select(User).where(User.email == email)):
                print(f"first_run: admin {email} already exists — leaving it alone")
            else:
                db.add(User(
                    email=email,
                    name="Admin",
                    password=hash_password(password),
                    role="admin",
                    is_admin=True,
                ))
                await db.commit()
                print(f"first_run: created admin {email}")
        else:
            print("first_run: INITIAL_ADMIN_EMAIL/PASSWORD not set — skipping admin creation")

        # The pricing engine needs a populated rate table; seed as any admin.
        admin = await db.scalar(select(User).where(User.role == "admin").limit(1))
        if admin is None:
            print("first_run: no admin exists yet — skipping rate seeding")
        else:
            result = await seed_rates(db=db, user=admin)
            await db.commit()
            print(f"first_run: {result['message']}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
