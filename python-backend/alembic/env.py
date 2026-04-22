"""
Alembic migration environment — async SQLAlchemy.
"""

from __future__ import annotations

import asyncio
import os
import re
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

# Alembic Config object
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import the metadata from our app so Alembic can autogenerate migrations
try:
    from app.db.config import Base  # noqa: F401 — registers all mapped models
    target_metadata = Base.metadata
except Exception:
    target_metadata = None  # type: ignore[assignment]


def _get_url() -> str:
    raw = os.getenv("DATABASE_URL", config.get_main_option("sqlalchemy.url", ""))
    if raw.startswith("postgresql://"):
        raw = raw.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif raw.startswith("postgres://"):
        raw = raw.replace("postgres://", "postgresql+asyncpg://", 1)
    # Strip sslmode param — asyncpg handles SSL via connect_args
    raw = re.sub(r"[?&]sslmode=[^&]*", "", raw).rstrip("?&")
    return raw


def run_migrations_offline() -> None:
    url = _get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = create_async_engine(_get_url())
    async with engine.begin() as conn:
        await conn.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
