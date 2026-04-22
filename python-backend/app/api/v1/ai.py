"""
AI / ML API — v1
=================
POST /interpret/{analysis_id}  AI interpretation of a stored analysis.
GET  /status                   AI service status.
GET  /ghi/dashboard            Grid Health Index dashboard data.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
import random

from fastapi import APIRouter, HTTPException, status

from app.ai.claude_service import get_ai_service
from app.api.v1.analysis import _store as _analysis_store
from app.schemas.models import (
    AIInterpretRequest,
    AIInterpretResponse,
    AIStatusResponse,
    GHIDashboardResponse,
)
from app.utils.helpers import utcnow

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────


@router.post("/interpret/{analysis_id}", response_model=AIInterpretResponse)
async def interpret_analysis(
    analysis_id: str,
    body: AIInterpretRequest,
) -> AIInterpretResponse:
    """
    Generate an AI-powered narrative interpretation of a stored analysis.

    Falls back to a rule-based offline interpretation when no API key
    is configured.
    """
    record = _analysis_store.get(analysis_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis '{analysis_id}' not found.",
        )

    ai = get_ai_service()
    result = await ai.interpret_analysis(
        analysis_data=record.model_dump(),
        language=body.language,
        detail_level=body.detail_level,
    )

    return AIInterpretResponse(
        analysis_id=analysis_id,
        summary=result.get("summary", ""),
        key_findings=result.get("key_findings", []),
        recommended_actions=result.get("recommended_actions", []),
        risk_level=result.get("risk_level", "medium"),
        generated_at=utcnow(),
        model_used=ai.model or "offline",
    )


@router.get("/status", response_model=AIStatusResponse)
async def get_ai_status() -> AIStatusResponse:
    """Return the current AI service configuration status."""
    ai = get_ai_service()
    return AIStatusResponse(
        available=ai.is_available,
        provider=ai.provider,
        model=ai.model,
        message=(
            f"AI service online via {ai.provider} ({ai.model})"
            if ai.is_available
            else "No AI API key configured — offline mode active"
        ),
    )


@router.get("/ghi/dashboard", response_model=GHIDashboardResponse)
async def ghi_dashboard() -> GHIDashboardResponse:
    """
    Return Grid Health Index (GHI) dashboard data.

    In production this is computed from real-time meter telemetry and
    ML models.  Here we return a plausible synthetic snapshot.
    """
    # Derive a pseudo-stable GHI score from the current minute so the
    # value drifts slowly between refreshes (deterministic enough for demo).
    minute_seed = datetime.now(tz=timezone.utc).minute
    random.seed(minute_seed)

    ghi_score = round(random.uniform(62.0, 88.0), 1)

    risk_level = (
        "low" if ghi_score >= 80 else
        "medium" if ghi_score >= 65 else
        "high"
    )

    trend = random.choice(["improving", "stable", "declining"])

    return GHIDashboardResponse(
        ghi_score=ghi_score,
        risk_level=risk_level,
        components={
            "meter_health":        round(random.uniform(0.70, 0.98), 3),
            "infrastructure":      round(random.uniform(0.65, 0.95), 3),
            "loss_ratio":          round(random.uniform(0.72, 0.96), 3),
            "anomaly_frequency":   round(random.uniform(0.60, 0.92), 3),
            "maintenance_score":   round(random.uniform(0.68, 0.94), 3),
        },
        trend=trend,
        last_updated=utcnow(),
    )
