"""
Async SQLAlchemy database configuration.

Reads DATABASE_URL from environment.  Supports:
  - Local PostgreSQL
  - Supabase (NullPool + SSL + disabled prepared statements)
  - SQLite (for local dev / testing)
"""

from __future__ import annotations

import logging
import os
import re
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

logger = logging.getLogger(__name__)

DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./urjarakshak.db")


def _normalise_url(raw: str) -> tuple[str, bool]:
    """Translate plain postgres:// URLs to asyncpg scheme; detect Supabase."""
    url = raw
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)

    is_supabase = ".supabase.co" in url

    # Strip any ?sslmode=… added by platform env-vars
    url = re.sub(r"[?&]sslmode=[^&]*", "", url).rstrip("?&")
    return url, is_supabase


_db_url, _is_supabase = _normalise_url(DATABASE_URL)


def _build_engine() -> AsyncEngine:
    connect_args: dict = {}

    if _is_supabase:
        connect_args = {
            "ssl": "require",
            "statement_cache_size": 0,
            "prepared_statement_cache_size": 0,
        }
        logger.info("Supabase detected — SSL on, prepared-statements off")
        return create_async_engine(
            _db_url,
            echo=os.getenv("DEBUG", "false").lower() == "true",
            poolclass=NullPool,
            connect_args=connect_args,
        )

    if _db_url.startswith("sqlite"):
        # aiosqlite doesn't support NullPool; use default StaticPool for tests
        from sqlalchemy.pool import StaticPool

        return create_async_engine(
            _db_url,
            echo=os.getenv("DEBUG", "false").lower() == "true",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

    return create_async_engine(
        _db_url,
        echo=os.getenv("DEBUG", "false").lower() == "true",
        poolclass=NullPool,
    )


engine: AsyncEngine = _build_engine()

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    pass


# ─────────────────────────────────────────────────────────────────────
# FastAPI dependency
# ─────────────────────────────────────────────────────────────────────


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ─────────────────────────────────────────────────────────────────────
# Lifecycle helpers
# ─────────────────────────────────────────────────────────────────────


async def init_db() -> None:
    """Create all tables (idempotent)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created / verified")


async def close_db() -> None:
    await engine.dispose()
    logger.info("Database connections closed")


async def check_db() -> bool:
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.error("DB health check failed: %s", exc)
        return False


async def get_db_info() -> dict:
    try:
        is_sqlite = _db_url.startswith("sqlite")
        version_query = "SELECT sqlite_version()" if is_sqlite else "SELECT version()"
        async with engine.begin() as conn:
            result = await conn.execute(text(version_query))
            version = result.scalar() or "unknown"
        return {
            "connected": True,
            "supabase": _is_supabase,
            "ssl": _is_supabase,
            "version": version.split(",")[0],
            "driver": _db_url.split("://")[0],
        }
    except Exception as exc:
        return {"connected": False, "error": str(exc)}


__all__ = [
    "engine",
    "async_session_maker",
    "Base",
    "get_db",
    "init_db",
    "close_db",
    "check_db",
    "get_db_info",
]
