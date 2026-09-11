"""Idempotent seed of the default admin user.

Upserts by username from ``ADMIN_*`` settings:
    * user missing            -> create (role=admin, is_active=True)  ["created"]
    * user present + force    -> reset password/email/is_active       ["reset"]
    * user present, no force  -> untouched password                   ["exists"]

Never clobbers a changed password on restart unless ``ADMIN_FORCE_PASSWORD``
is explicitly set. Requires a non-empty, policy-compliant ``ADMIN_PASSWORD``.
"""
from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


async def seed_admin(engine: AsyncEngine | None = None) -> str:
    """Upsert the default admin user; returns "created" | "reset" | "exists".

    When no engine is given, the app's default async engine is used (via
    ``async_session_factory``) and its pooled connections released. A
    caller-provided engine is never disposed — ownership stays with the caller.
    """
    from fmp.core.config import settings
    from fmp.core.database import async_session_factory, engine as default_engine
    from fmp.core.security import hash_password, validate_password_complexity
    from fmp.models.user import User

    password = settings.ADMIN_PASSWORD
    if not password:
        raise RuntimeError("ADMIN_PASSWORD must be set to seed the default admin")
    violations = validate_password_complexity(password)
    if violations:
        raise RuntimeError("ADMIN_PASSWORD " + "; ".join(violations))

    if engine is None:
        session_factory = async_session_factory
        owns_engine = True
    else:
        session_factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        owns_engine = False

    try:
        async with session_factory() as session:
            stmt = select(User).where(User.username == settings.ADMIN_USERNAME)
            user = (await session.execute(stmt)).scalar_one_or_none()

            outcome: str
            if user is None:
                session.add(
                    User(
                        username=settings.ADMIN_USERNAME,
                        email=settings.ADMIN_EMAIL,
                        password_hash=hash_password(password),
                        role="admin",
                        is_active=True,
                    )
                )
                outcome = "created"
            elif settings.ADMIN_FORCE_PASSWORD:
                user.password_hash = hash_password(password)
                user.email = settings.ADMIN_EMAIL
                user.is_active = True
                outcome = "reset"
            else:
                outcome = "exists"

            await session.commit()
        return outcome
    finally:
        if owns_engine:
            await default_engine.dispose()


if __name__ == "__main__":
    print(f"seeded admin: {asyncio.run(seed_admin())}")