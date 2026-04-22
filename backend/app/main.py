"""
UrjaRakshak Backend — Production Build
======================================

Features
- ML anomaly detection (Isolation Forest)
- Physics-based validation engine
- JWT authentication + RBAC
- Rate limiting
- Prometheus metrics
- Database persistence
- Graceful startup
- CORS configured for frontend

Author: Vipin Baniya
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Dict, Any
import logging

from app.config import settings
from app.database import (
    init_db,
    close_db,
    check_database_connection,
    get_database_info
)

# Engines
from app.core.physics_engine import PhysicsEngine
from app.core.attribution_engine import AttributionEngine
from app.core.ai_interpretation_engine import init_ai_engine
from app.core.physics_constrained_anomaly import init_constrained_engine
from app.core.load_forecasting_engine import get_forecast_engine

# ML
from app.ml.anomaly_detection import anomaly_engine as ml_anomaly_engine

# Middleware
from app.middleware import RateLimitMiddleware, MetricsMiddleware, metrics

# Routers
from app.api.v1 import (
    analysis,
    grid,
    upload,
    inspection,
    ai,
    auth_routes,
    stream,
    governance
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# Core engines
# ─────────────────────────────────────────────────────────────

physics_engine = PhysicsEngine(
    temperature_celsius=settings.PHYSICS_TEMPERATURE_CELSIUS,
    min_confidence=settings.PHYSICS_MIN_CONFIDENCE,
    strict_mode=settings.ENABLE_STRICT_ETHICS,
)

attribution_engine = AttributionEngine(
    conservative_mode=settings.ENABLE_STRICT_ETHICS
)


# ─────────────────────────────────────────────────────────────
# Application lifespan
# ─────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):

    logger.info("⚡ Starting UrjaRakshak Backend")

    # Database
    try:
        await init_db()

        if await check_database_connection():
            logger.info("✅ Database connected")
        else:
            logger.warning("⚠ Database unavailable — degraded mode")

    except Exception as e:
        logger.warning(f"⚠ DB startup warning: {e}")

    # ML engine
    try:
        ml_info = ml_anomaly_engine.initialize()
        logger.info(f"✅ ML Engine ready: {ml_info}")
    except Exception as e:
        logger.warning(f"⚠ ML init failed: {e}")

    # AI engine
    try:
        ai_eng = init_ai_engine(
            anthropic_key=settings.ANTHROPIC_API_KEY,
            openai_key=settings.OPENAI_API_KEY,
            groq_key=settings.GROQ_API_KEY,
        )
        logger.info(f"✅ AI engine configured: {ai_eng.is_configured}")
    except Exception as e:
        logger.warning(f"⚠ AI engine error: {e}")

    # Physics constrained anomaly engine
    try:
        constrained_engine = init_constrained_engine(
            ml_engine=ml_anomaly_engine
        )
        app.state.constrained_anomaly_engine = constrained_engine
        logger.info("✅ Physics anomaly engine active")
    except Exception as e:
        logger.warning(f"⚠ Physics anomaly engine failed: {e}")

    # Forecast engine
    try:
        forecast_engine = get_forecast_engine()
        app.state.forecast_engine = forecast_engine
        logger.info("✅ Load forecast engine active")
    except Exception as e:
        logger.warning(f"⚠ Forecast engine error: {e}")

    app.state.physics_engine = physics_engine
    app.state.attribution_engine = attribution_engine
    app.state.anomaly_engine = ml_anomaly_engine
    app.state.startup_time = datetime.utcnow()

    logger.info("✅ UrjaRakshak ready")

    yield

    logger.info("🛑 Shutting down")
    await close_db()


# ─────────────────────────────────────────────────────────────
# FastAPI App
# ─────────────────────────────────────────────────────────────

app = FastAPI(
    title="UrjaRakshak API",
    description="Physics-based Energy Integrity & Grid Loss Analysis",
    version="2.3.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json"
)


# ─────────────────────────────────────────────────────────────
# CORS (Frontend access)
# ─────────────────────────────────────────────────────────────

_cors_kwargs: dict = dict(
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
if settings.CORS_ALLOW_ORIGIN_REGEX:
    _cors_kwargs["allow_origin_regex"] = settings.CORS_ALLOW_ORIGIN_REGEX

app.add_middleware(CORSMiddleware, **_cors_kwargs)


# ─────────────────────────────────────────────────────────────
# Other middleware
# ─────────────────────────────────────────────────────────────

app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(RateLimitMiddleware, max_requests=60, window_seconds=60)
app.add_middleware(MetricsMiddleware)


# ─────────────────────────────────────────────────────────────
# Routers
# ─────────────────────────────────────────────────────────────

app.include_router(auth_routes.router, prefix="/api/v1/auth", tags=["Auth"])
app.include_router(analysis.router, prefix="/api/v1/analysis", tags=["Analysis"])
app.include_router(grid.router, prefix="/api/v1/grid", tags=["Grid"])
app.include_router(upload.router, prefix="/api/v1/upload", tags=["Upload"])
app.include_router(inspection.router, prefix="/api/v1/inspections", tags=["Inspections"])
app.include_router(ai.router, prefix="/api/v1/ai", tags=["AI"])
app.include_router(stream.router, prefix="/api/v1/stream", tags=["Streaming"])
app.include_router(governance.router, prefix="/api/v1/org", tags=["Governance"])


# ─────────────────────────────────────────────────────────────
# System endpoints
# ─────────────────────────────────────────────────────────────

@app.get("/")
async def root() -> Dict[str, Any]:

    return {
        "name": "UrjaRakshak",
        "status": "operational",
        "version": "2.3.0",
        "developer": "Vipin Baniya"
    }


@app.get("/health")
async def health() -> Dict[str, Any]:

    db_info = await get_database_info()

    return {
        "status": "healthy" if db_info.get("connected") else "degraded",
        "timestamp": datetime.utcnow().isoformat(),
        "database": db_info
    }


@app.get("/metrics")
async def prometheus_metrics():

    return PlainTextResponse(
        metrics.to_prometheus_text(),
        media_type="text/plain"
    )


# ─────────────────────────────────────────────────────────────
# Global exception handler
# ─────────────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):

    logger.error(f"Unhandled error: {exc}", exc_info=True)

    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error"
        }
    )


# ─────────────────────────────────────────────────────────────
# Local dev runner
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.is_development
    )
