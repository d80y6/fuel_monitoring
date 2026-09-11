"""Async SQLAlchemy 2.0 engine, session factory, and declarative base."""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from fmp.core.config import get_settings

settings = get_settings()

_ENGINE_KWARGS: dict = {
    "echo": settings.DB_ECHO,
    "pool_pre_ping": True,
    "pool_recycle": 300,
}
if settings.TESTING:
    # pytest-asyncio runs each test on its own event loop; a shared connection
    # pool cannot migrate between loops, so tests get a connection-per-use pool.
    _ENGINE_KWARGS["poolclass"] = NullPool
else:
    _ENGINE_KWARGS.update({
        "pool_size": settings.DB_POOL_SIZE,
        "max_overflow": settings.DB_MAX_OVERFLOW,
    })


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


engine = create_async_engine(settings.postgres_dsn, **_ENGINE_KWARGS)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Dedicated NULL-POOL engine for short-lived-loop contexts (Celery prefork).
# Celery tasks call asyncio.run() per task: a fresh loop per invocation, closed
# afterwards. Pooled asyncpg connections created on loop A are later checked
# out on loop B → "Event loop is closed" / "attached to a different loop"
# RuntimeErrors. NullPool creates AND closes the connection inside the SAME
# asyncio.run() loop, so there is no cross-loop reuse — deterministic.
_NULL_POOL_ENGINE_KWARGS = {"echo": settings.DB_ECHO, "poolclass": NullPool}
celery_engine = create_async_engine(settings.postgres_dsn, **_NULL_POOL_ENGINE_KWARGS)
celery_session_factory = async_sessionmaker(
    celery_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a scoped AsyncSession."""
    async with async_session_factory() as session:
        yield session