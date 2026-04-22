"""
UrjaRakshak Async Database Configuration
========================================

Compatible with:
- Local PostgreSQL
- Supabase (PgBouncer transaction mode)
- Render deployment
- SQLAlchemy Async + asyncpg

Fixes:
- Disable prepared statements (PgBouncer compatibility)
- Enable SSL automatically for Supabase
- NullPool used with Supabase (Supabase already has pooling)
"""

import logging
import re
from typing import AsyncGenerator
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
    AsyncEngine,
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool
from sqlalchemy import text

from app.config import settings

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Build asyncpg database URL
# ─────────────────────────────────────────────

def _build_database_url() -> tuple[str, bool]:

    url = settings.DATABASE_URL

    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)

    # Detect Supabase by inspecting the hostname (covers both direct connections
    # via *.supabase.co and pooler connections via *.pooler.supabase.com).
    try:
        _hostname = urlparse(url.replace("postgresql+asyncpg://", "postgresql://")).hostname or ""
    except Exception:
        _hostname = url
    is_supabase = _hostname.endswith(".supabase.co") or _hostname.endswith(".supabase.com")

    # remove sslmode query if present
    url = re.sub(r"[?&]sslmode=[^&]*", "", url).rstrip("?&")

    return url, is_supabase


database_url, is_supabase = _build_database_url()


# ─────────────────────────────────────────────
# Engine creation
# ─────────────────────────────────────────────

def create_database_engine() -> AsyncEngine:

    connect_args = {}

    if is_supabase:

        connect_args = {
            "ssl": "require",
            "statement_cache_size": 0,
            "prepared_statement_cache_size": 0,
        }

        logger.info(
            "Supabase detected → SSL enabled, prepared statements disabled"
        )

    engine = create_async_engine(
        database_url,
        echo=settings.DEBUG,
        poolclass=NullPool,  # ⭐ Required for Supabase PgBouncer
        connect_args=connect_args,
    )

    logger.info("Database engine created (asyncpg + NullPool)")

    return engine


engine = create_database_engine()


# ─────────────────────────────────────────────
# Session maker
# ─────────────────────────────────────────────

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)

Base = declarative_base()


# ─────────────────────────────────────────────
# DB dependency
# ─────────────────────────────────────────────

async def get_db() -> AsyncGenerator[AsyncSession, None]:

    async with async_session_maker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ─────────────────────────────────────────────
# DB health check
# ─────────────────────────────────────────────

async def check_database_connection() -> bool:

    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        return True

    except Exception as e:
        logger.error(f"DB health check failed: {e}")
        return False


async def get_database_info():

    try:

        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT version()"))
            version = result.scalar() or "unknown"

        return {
            "connected": True,
            "supabase": is_supabase,
            "ssl": is_supabase,
            "version": version.split(",")[0],
            "driver": database_url.split("://")[0],
        }

    except Exception as e:

        logger.error(f"Failed to get DB info: {e}")

        return {
            "connected": False,
            "error": str(e)
        }


# ─────────────────────────────────────────────
# Initialize DB tables
# ─────────────────────────────────────────────

async def init_db():

    try:

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        logger.info("✅ Database tables created / verified")

    except Exception as e:

        logger.error(f"❌ DB init failed: {e}")
        raise


# ─────────────────────────────────────────────
# Shutdown
# ─────────────────────────────────────────────

async def close_db():

    try:

        await engine.dispose()

        logger.info("✅ DB connections closed")

    except Exception as e:

        logger.error(f"❌ DB close error: {e}")


__all__ = [
    "engine",
    "async_session_maker",
    "Base",
    "get_db",
    "init_db",
    "close_db",
    "check_database_connection",
    "get_database_info",
]
