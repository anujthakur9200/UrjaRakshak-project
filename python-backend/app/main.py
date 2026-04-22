"""
UrjaRakshak python-backend — FastAPI entry point
=================================================

Features:
  - CORS (all origins in development; restrict in production)
  - Health check at /health
  - API v1 routers (analysis, grid, stream, ai)
  - Lifespan context for startup / shutdown
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import analysis, grid, stream, ai as ai_router
from app.db.config import check_db, get_db_info, init_db, close_db

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Lifespan
# ─────────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("⚡ Starting UrjaRakshak python-backend")

    try:
        await init_db()
        if await check_db():
            logger.info("✅ Database connected")
        else:
            logger.warning("⚠  Database unavailable — degraded mode")
    except Exception as exc:
        logger.warning("⚠  DB startup warning: %s", exc)

    app.state.startup_time = datetime.now(tz=timezone.utc)
    logger.info("✅ UrjaRakshak python-backend ready")

    yield

    logger.info("🛑 Shutting down")
    await close_db()


# ─────────────────────────────────────────────────────────────────────
# Application
# ─────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="UrjaRakshak API",
    description=(
        "Physics-based Energy Integrity & Grid Loss Analysis platform. "
        "Validates energy conservation, computes technical losses, and "
        "attributes unexplained residuals using real electrical-engineering "
        "principles."
    ),
    version="3.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)


# ─────────────────────────────────────────────────────────────────────
# Middleware
# ─────────────────────────────────────────────────────────────────────

_raw_origins = os.getenv("ALLOWED_ORIGINS", "*")
_allowed_origins = (
    [o.strip() for o in _raw_origins.split(",") if o.strip()]
    if _raw_origins != "*"
    else ["*"]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,   # set ALLOWED_ORIGINS env var to restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(GZipMiddleware, minimum_size=1000)


# ─────────────────────────────────────────────────────────────────────
# Routers
# ─────────────────────────────────────────────────────────────────────

app.include_router(analysis.router, prefix="/api/v1/analysis", tags=["Analysis"])
app.include_router(grid.router,     prefix="/api/v1/grid",     tags=["Grid"])
app.include_router(stream.router,   prefix="/api/v1/stream",   tags=["Streaming"])
app.include_router(ai_router.router, prefix="/api/v1/ai",      tags=["AI"])


# ─────────────────────────────────────────────────────────────────────
# System endpoints
# ─────────────────────────────────────────────────────────────────────


@app.get("/", tags=["System"])
async def root() -> Dict[str, Any]:
    return {
        "name": "UrjaRakshak",
        "description": "Physics-based energy integrity platform",
        "status": "operational",
        "version": "3.0.0",
        "docs": "/api/docs",
    }


@app.get("/health", tags=["System"])
async def health() -> Dict[str, Any]:
    db_info = await get_db_info()
    overall = "healthy" if db_info.get("connected") else "degraded"
    return {
        "status": overall,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "database": db_info,
    }


# ─────────────────────────────────────────────────────────────────────
# Global exception handler
# ─────────────────────────────────────────────────────────────────────


@app.exception_handler(Exception)
async def global_exception_handler(request, exc: Exception):
    logger.error("Unhandled error: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"},
    )


# ─────────────────────────────────────────────────────────────────────
# Local dev runner
# ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
    )
