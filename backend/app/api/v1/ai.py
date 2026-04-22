"""
UrjaRakshak — AI & GHI API Routes
====================================
POST /api/v1/ai/interpret/{analysis_id}    — Run full GHI+AI pipeline on existing analysis
GET  /api/v1/ai/ghi/latest/{substation}    — Latest GHI snapshot for a substation
GET  /api/v1/ai/ghi/history/{substation}   — GHI trend history
GET  /api/v1/ai/interpretation/{id}        — Get single AI interpretation
GET  /api/v1/ai/status                     — AI engine configuration status
GET  /api/v1/ai/ghi/dashboard              — Aggregated GHI data for dashboard

Author: Vipin Baniya
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func

from app.database import get_db
from app.auth import get_current_active_user, require_analyst
from app.models.db_models import (
    Analysis, GridHealthSnapshot, AIInterpretation, Inspection, User
)
from app.services.ghi_service import run_full_ghi_pipeline
from app.core.ai_interpretation_engine import get_ai_engine

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Engine status ─────────────────────────────────────────────────────────

@router.get("/status")
async def ai_engine_status(
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Check AI engine configuration and capability."""
    engine = get_ai_engine()
    return {
        "configured":        engine.is_configured,
        "preferred_provider": engine.preferred_provider,
        "min_confidence_threshold": engine.MIN_CONFIDENCE_THRESHOLD,
        "supported_providers": ["anthropic", "groq", "openai"],
        "models": {
            "anthropic": "claude-haiku-4-5-20251001",
            "groq":      "llama3-8b-8192",
            "openai":    "gpt-4o-mini",
        },
        "offline_mode": not engine.is_configured,
        "offline_note": (
            None if engine.is_configured
            else "Set ANTHROPIC_API_KEY, GROQ_API_KEY, or OPENAI_API_KEY env var to enable live AI interpretation."
        ),
    }


# ── Trigger full GHI + AI pipeline on an existing analysis ───────────────

@router.post("/interpret/{analysis_id}")
async def run_ghi_and_interpret(
    analysis_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_analyst),
) -> Dict[str, Any]:
    """
    Trigger the full GHI + Risk + AI pipeline for an existing analysis.
    If a GHI snapshot already exists for this analysis, returns existing result
    without re-running (idempotent — avoids burning AI tokens).
    """
    # Load analysis
    analysis = (await db.execute(
        select(Analysis).where(Analysis.id == analysis_id)
    )).scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    # Check if already computed
    existing_ghi = (await db.execute(
        select(GridHealthSnapshot)
        .where(GridHealthSnapshot.analysis_id == analysis_id)
        .order_by(desc(GridHealthSnapshot.created_at))
        .limit(1)
    )).scalar_one_or_none()

    existing_ai = (await db.execute(
        select(AIInterpretation)
        .where(AIInterpretation.analysis_id == analysis_id)
        .order_by(desc(AIInterpretation.created_at))
        .limit(1)
    )).scalar_one_or_none()

    if existing_ghi and existing_ai:
        return {
            "analysis_id": analysis_id,
            "cached": True,
            "ghi_snapshot": _ghi_snap_to_dict(existing_ghi),
            "ai_interpretation": _ai_to_dict(existing_ai),
            "message": "GHI and AI interpretation already computed for this analysis.",
        }

    # Run pipeline
    result = await run_full_ghi_pipeline(
        analysis_id=analysis_id,
        substation_id=analysis.substation_id,
        residual_pct=analysis.residual_percentage or 0.0,
        confidence=analysis.confidence_score or 0.5,
        balance_status=analysis.balance_status or "unknown",
        measurement_quality=analysis.measurement_quality or "medium",
        input_mwh=analysis.input_energy_mwh or 0.0,
        output_mwh=analysis.output_energy_mwh or 0.0,
        expected_loss_mwh=analysis.expected_loss_mwh or 0.0,
        actual_loss_mwh=analysis.actual_loss_mwh or 0.0,
        db=db,
        created_by=current_user.id,
    )

    return {"analysis_id": analysis_id, "cached": False, **result}


# ── GHI snapshots ─────────────────────────────────────────────────────────

@router.get("/ghi/latest/{substation_id}")
async def get_latest_ghi(
    substation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Latest GHI snapshot for a substation."""
    snap = (await db.execute(
        select(GridHealthSnapshot)
        .where(GridHealthSnapshot.substation_id == substation_id)
        .order_by(desc(GridHealthSnapshot.created_at))
        .limit(1)
    )).scalar_one_or_none()

    if not snap:
        raise HTTPException(
            status_code=404,
            detail=f"No GHI data found for substation '{substation_id}'. Run a physics analysis first.",
        )
    return _ghi_snap_to_dict(snap)


@router.get("/ghi/history/{substation_id}")
async def get_ghi_history(
    substation_id: str,
    limit: int = Query(default=30, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """GHI trend history for a substation — used for time-series chart."""
    rows = (await db.execute(
        select(GridHealthSnapshot)
        .where(GridHealthSnapshot.substation_id == substation_id)
        .order_by(desc(GridHealthSnapshot.created_at))
        .limit(limit)
    )).scalars().all()

    history = [_ghi_snap_to_dict(s) for s in reversed(rows)]
    avg_ghi = (
        round(sum(s["ghi_score"] for s in history) / len(history), 2)
        if history else None
    )
    return {
        "substation_id": substation_id,
        "count": len(history),
        "avg_ghi": avg_ghi,
        "history": history,
    }


@router.get("/ghi/dashboard")
async def get_ghi_dashboard(
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Aggregated GHI data for the main dashboard.
    Public endpoint — no auth required (reads aggregate metrics only).
    """
    # Total GHI snapshots
    total_snaps = (await db.execute(select(func.count(GridHealthSnapshot.id)))).scalar() or 0

    # Latest GHI per substation
    latest_rows = (await db.execute(
        select(
            GridHealthSnapshot.substation_id,
            func.max(GridHealthSnapshot.created_at).label("latest_ts"),
        )
        .group_by(GridHealthSnapshot.substation_id)
    )).fetchall()

    substations_summary: List[Dict] = []
    for row in latest_rows:
        snap = (await db.execute(
            select(GridHealthSnapshot)
            .where(GridHealthSnapshot.substation_id == row[0])
            .where(GridHealthSnapshot.created_at == row[1])
            .limit(1)
        )).scalar_one_or_none()
        if snap:
            substations_summary.append({
                "substation_id":     snap.substation_id,
                "ghi_score":         snap.ghi_score,
                "classification":    snap.classification,
                "action_required":   snap.action_required,
                "inspection_priority": snap.inspection_priority,
                "updated_at":        snap.created_at.isoformat() if snap.created_at else None,
            })

    # Sort by GHI ascending (worst first)
    substations_summary.sort(key=lambda x: x["ghi_score"])

    # Classification distribution
    class_rows = (await db.execute(
        select(GridHealthSnapshot.classification, func.count(GridHealthSnapshot.id))
        .group_by(GridHealthSnapshot.classification)
    )).fetchall()
    by_classification = {r[0]: r[1] for r in class_rows if r[0]}

    # Average GHI across all time
    avg_ghi_all = (await db.execute(
        select(func.avg(GridHealthSnapshot.ghi_score))
    )).scalar()

    # Open inspections
    open_inspections = (await db.execute(
        select(func.count(Inspection.id))
        .where(Inspection.status.in_(["OPEN", "IN_PROGRESS"]))
    )).scalar() or 0

    critical_open = (await db.execute(
        select(func.count(Inspection.id))
        .where(Inspection.status.in_(["OPEN", "IN_PROGRESS"]))
        .where(Inspection.priority.in_(["CRITICAL", "HIGH"]))
    )).scalar() or 0

    # Recent GHI trend (last 20 snapshots, any substation)
    recent = (await db.execute(
        select(
            GridHealthSnapshot.created_at,
            GridHealthSnapshot.ghi_score,
            GridHealthSnapshot.classification,
            GridHealthSnapshot.substation_id,
        )
        .order_by(desc(GridHealthSnapshot.created_at))
        .limit(20)
    )).fetchall()
    trend = [
        {
            "ts":          r[0].isoformat() if r[0] else None,
            "ghi":         r[1],
            "class":       r[2],
            "substation":  r[3],
        }
        for r in reversed(recent)
    ]

    # AI interpretation count
    total_ai = (await db.execute(select(func.count(AIInterpretation.id)))).scalar() or 0
    ai_live  = (await db.execute(
        select(func.count(AIInterpretation.id))
        .where(AIInterpretation.model_name.notin_(["offline", "refused"]))
    )).scalar() or 0

    return {
        "has_data":            total_snaps > 0,
        "total_ghi_snapshots": total_snaps,
        "total_ai_interpretations": total_ai,
        "live_ai_interpretations":  ai_live,
        "avg_ghi_all_time":    round(float(avg_ghi_all), 2) if avg_ghi_all else None,
        "by_classification":   by_classification,
        "open_inspections":    open_inspections,
        "critical_open":       critical_open,
        "substations":         substations_summary,
        "trend":               trend,
    }


# ── AI interpretation retrieval ────────────────────────────────────────────

@router.get("/interpretation/{interpretation_id}")
async def get_ai_interpretation(
    interpretation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Retrieve a stored AI interpretation by ID."""
    record = (await db.execute(
        select(AIInterpretation).where(AIInterpretation.id == interpretation_id)
    )).scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="AI interpretation not found")
    return _ai_to_dict(record)


@router.get("/interpretation/by-analysis/{analysis_id}")
async def get_ai_by_analysis(
    analysis_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Get the AI interpretation for a specific analysis."""
    record = (await db.execute(
        select(AIInterpretation)
        .where(AIInterpretation.analysis_id == analysis_id)
        .order_by(desc(AIInterpretation.created_at))
        .limit(1)
    )).scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="No AI interpretation found for this analysis")
    return _ai_to_dict(record)


# ── Serialisers ────────────────────────────────────────────────────────────

def _ghi_snap_to_dict(snap: GridHealthSnapshot) -> Dict[str, Any]:
    return {
        "id":                snap.id,
        "substation_id":     snap.substation_id,
        "analysis_id":       snap.analysis_id,
        "ghi_score":         snap.ghi_score,
        "classification":    snap.classification,
        "action_required":   snap.action_required,
        "interpretation":    snap.interpretation,
        "inspection_priority": snap.inspection_priority,
        "inspection_category": snap.inspection_category,
        "urgency":           snap.urgency,
        "confidence_in_ghi": snap.confidence_in_ghi,
        "components": {
            "PBS": snap.pbs, "ASS": snap.ass,
            "CS":  snap.cs,  "TSS": snap.tss, "DIS": snap.dis,
        },
        "created_at": snap.created_at.isoformat() if snap.created_at else None,
    }


def _ai_to_dict(rec: AIInterpretation) -> Dict[str, Any]:
    return {
        "id":                     rec.id,
        "analysis_id":            rec.analysis_id,
        "substation_id":          rec.substation_id,
        "model_name":             rec.model_name,
        "model_version":          rec.model_version,
        "prompt_hash":            rec.prompt_hash,
        "risk_level":             rec.risk_level,
        "inspection_priority":    rec.inspection_priority,
        "primary_infrastructure_hypothesis": rec.primary_infrastructure_hypothesis,
        "recommended_actions":    rec.recommended_actions,
        "confidence_commentary":  rec.confidence_commentary,
        "trend_assessment":       rec.trend_assessment,
        "estimated_investigation_scope": rec.estimated_investigation_scope,
        "token_usage":            rec.token_usage,
        "error":                  rec.error,
        "created_at":             rec.created_at.isoformat() if rec.created_at else None,
    }


# ── Load Forecasting ───────────────────────────────────────────────────────

from app.models.db_models import MeterReading
from app.core.load_forecasting_engine import (
    LoadForecastingEngine, fit_meter_model, forecast_next_24h,
)

_forecast_engine_inst = LoadForecastingEngine()


@router.get("/forecast/{meter_id}")
async def get_meter_forecast(
    meter_id: str,
    substation_id: Optional[str] = None,
    hours_ahead: int = Query(default=24, le=168),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """
    Forecast next N hours of load for a meter using Fourier + linear trend.
    Requires at least 48 historical readings.
    Forecast band is physics-constrained (±16% tolerance).
    """
    # Load historical readings
    query = (
        select(MeterReading)
        .where(MeterReading.meter_id == meter_id)
        .order_by(MeterReading.timestamp.desc())
        .limit(2000)
    )
    if substation_id:
        query = query.where(MeterReading.substation_id == substation_id)
    rows = (await db.execute(query)).scalars().all()

    if len(rows) < 2:
        raise HTTPException(
            status_code=404,
            detail=f"Not enough readings for meter '{meter_id}'. "
                   "Need at least 48 readings for a reliable forecast.",
        )

    readings = [
        {
            "timestamp":  r.timestamp.isoformat() if r.timestamp else None,
            "energy_kwh": float(r.energy_kwh or 0),
        }
        for r in reversed(rows)
        if r.timestamp and r.energy_kwh is not None
    ]

    summary, model = fit_meter_model(readings, meter_id)

    if not model.is_reliable:
        return {
            "meter_id":        meter_id,
            "reliable":        False,
            "reason":          "Insufficient data quality for reliable forecast",
            "model_summary":   summary,
            "forecast":        [],
        }

    from datetime import datetime as _dt
    reference_ts = _dt.fromisoformat(readings[0]["timestamp"]) if readings else _dt.utcnow()
    forecast_pts = forecast_next_24h(
        model=model,
        from_ts=_dt.utcnow(),
        interval_hours=max(1, hours_ahead // 24),
        reference_ts=reference_ts,
    )

    return {
        "meter_id":      meter_id,
        "reliable":      True,
        "model_summary": summary,
        "forecast":      forecast_pts[:hours_ahead],
        "interpretation": (
            f"R²={summary['fit_r2']:.3f} — "
            + ("Good fit. " if summary["fit_r2"] > 0.7 else "Moderate fit. ")
            + f"Trend: {summary['trend_slope_kwh_per_hour']:+.4f} kWh/hr. "
            + f"Forecast horizon: {hours_ahead}h."
        ),
    }


@router.post("/forecast/{meter_id}/evaluate")
async def evaluate_reading_vs_forecast(
    meter_id: str,
    actual_kwh: float,
    timestamp: str,
    substation_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """
    Check whether a specific reading is within its forecasted band.
    Returns deviation analysis and whether the reading is a forecast anomaly.
    """
    from datetime import datetime as _dt
    try:
        ts = _dt.fromisoformat(timestamp.replace("Z", ""))
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid timestamp format. Use ISO 8601.")

    query = (
        select(MeterReading)
        .where(MeterReading.meter_id == meter_id)
        .order_by(MeterReading.timestamp.desc())
        .limit(2000)
    )
    if substation_id:
        query = query.where(MeterReading.substation_id == substation_id)
    rows = (await db.execute(query)).scalars().all()

    if len(rows) < 10:
        return {
            "meter_id":          meter_id,
            "forecast_available": False,
            "reason":            "Not enough historical data",
        }

    readings = [
        {"timestamp": r.timestamp.isoformat(), "energy_kwh": float(r.energy_kwh or 0)}
        for r in reversed(rows)
        if r.timestamp and r.energy_kwh is not None
    ]
    _, model = fit_meter_model(readings, meter_id)
    reference_ts = _dt.fromisoformat(readings[0]["timestamp"])
    result = _forecast_engine_inst.evaluate_reading(model, actual_kwh, ts, reference_ts)
    result["meter_id"] = meter_id
    return result


# ── Conversational AI Chat ────────────────────────────────────────────────

class ChatRequest(BaseModel):
    substation_id: str
    question: str


@router.post("/chat")
async def ai_chat(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """
    Conversational AI chat endpoint.
    Accepts a substation_id and free-form question.
    Fetches the latest analysis as context, then answers using the AI engine.
    """
    engine = get_ai_engine()

    # Build context string from latest analysis (if available)
    context: Optional[str] = None
    analysis = (await db.execute(
        select(Analysis)
        .where(Analysis.substation_id == request.substation_id)
        .order_by(desc(Analysis.created_at))
        .limit(1)
    )).scalar_one_or_none()

    if analysis:
        from datetime import datetime as _dt
        ts_str = (
            analysis.created_at.strftime('%Y-%m-%d %H:%M')
            if isinstance(analysis.created_at, _dt)
            else str(analysis.created_at) if analysis.created_at
            else 'N/A'
        )
        context = (
            f"Substation: {request.substation_id}\n"
            f"Latest analysis ({ts_str}):\n"
            f"  Input energy:     {analysis.input_energy_mwh or 0:.2f} MWh\n"
            f"  Output energy:    {analysis.output_energy_mwh or 0:.2f} MWh\n"
            f"  Residual loss:    {analysis.residual_percentage or 0:.2f}%\n"
            f"  Balance status:   {analysis.balance_status or 'unknown'}\n"
            f"  Confidence:       {(analysis.confidence_score or 0) * 100:.0f}%\n"
        )
    else:
        context = (
            f"Substation: {request.substation_id}\n"
            "No analysis data found for this substation yet. "
            "The user may need to upload meter data and run a physics analysis first."
        )

    result = engine.chat_answer(question=request.question, context=context)
    return {
        "answer": result["answer"],
        "model": result["model"],
        "substation_id": request.substation_id,
        "has_context": analysis is not None,
        "error": result.get("error"),
    }
