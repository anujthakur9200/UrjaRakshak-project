"""
UrjaRakshak — Analysis API v2.3 (Performance-Optimised)
========================================================
Key changes over v2.2:
  - GHI + AI pipeline runs in BackgroundTask (non-blocking)
    → /validate returns physics result immediately (~50ms)
    → GHI/AI written to DB async, poll via GET /{id}
  - Stats summary cached 30s (LRU in-memory)
  - Pagination uses COUNT(*) FILTER subquery (single round-trip)

Author: Vipin Baniya
"""

import logging
import time
from datetime import datetime
from functools import lru_cache
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, BackgroundTasks, Request, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc

from app.core.physics_engine import GridComponent, PhysicsEngine
from app.ml.anomaly_detection import AnomalyFeatures
from app.database import get_db, async_session_maker
from app.models.db_models import (
    Analysis, GridSection, AnomalyResult as DBAnomaly, User,
    GridHealthSnapshot, AIInterpretation, Inspection,
)
from app.auth import get_current_active_user
from app.services.ghi_service import run_full_ghi_pipeline

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Simple in-process stats cache (30s TTL) ──────────────────────────────
_stats_cache: Dict[str, Any] = {}
_stats_cache_ts: float = 0.0
_STATS_TTL = 30.0  # seconds


class AnalysisRequest(BaseModel):
    substation_id: str = Field(..., description="Substation identifier")
    input_energy_mwh: float = Field(..., gt=0)
    output_energy_mwh: float = Field(..., ge=0)
    components: List[Dict[str, Any]] = Field(..., min_length=1)
    time_window_hours: float = Field(24.0, gt=0)

    model_config = {
        "json_schema_extra": {
            "example": {
                "substation_id": "SS001",
                "input_energy_mwh": 1000.0,
                "output_energy_mwh": 975.0,
                "time_window_hours": 24.0,
                "components": [
                    {"component_id": "TX001", "component_type": "transformer",
                     "rated_capacity_kva": 1000, "efficiency_rating": 0.98, "age_years": 10},
                ],
            }
        }
    }


class AnomalyDetectRequest(BaseModel):
    substation_id: str
    input_mwh: float = Field(..., gt=0)
    output_mwh: float = Field(..., ge=0)
    residual_mwh: float
    residual_percent: float
    confidence_score: float = Field(default=0.8, ge=0.0, le=1.0)
    time_of_day_hour: float = Field(default=12.0, ge=0, le=24)
    day_of_week: float = Field(default=1.0, ge=0, le=7)
    analysis_id: Optional[str] = None


async def get_or_create_grid_section(substation_id: str, db: AsyncSession) -> GridSection:
    result = await db.execute(select(GridSection).where(GridSection.substation_id == substation_id))
    section = result.scalar_one_or_none()
    if not section:
        section = GridSection(substation_id=substation_id, status="active")
        db.add(section)
        await db.flush()
    return section


async def _run_ghi_in_background(
    analysis_id: str,
    substation_id: str,
    residual_pct: float,
    confidence: float,
    balance_status: str,
    measurement_quality: str,
    input_mwh: float,
    output_mwh: float,
    expected_loss_mwh: float,
    actual_loss_mwh: float,
    created_by: Optional[str],
) -> None:
    """
    Runs GHI + risk + AI in a background task with its own DB session.
    This keeps /validate response time under 100ms regardless of AI latency.
    """
    try:
        async with async_session_maker() as db:
            await run_full_ghi_pipeline(
                analysis_id=analysis_id,
                substation_id=substation_id,
                residual_pct=residual_pct,
                confidence=confidence,
                balance_status=balance_status,
                measurement_quality=measurement_quality,
                input_mwh=input_mwh,
                output_mwh=output_mwh,
                expected_loss_mwh=expected_loss_mwh,
                actual_loss_mwh=actual_loss_mwh,
                db=db,
                created_by=created_by,
                auto_create_inspection=True,
            )
    except Exception as e:
        logger.warning(f"Background GHI pipeline error for {analysis_id}: {e}")


@router.post("/validate")
async def validate_grid_section(
    request: AnalysisRequest,
    background_tasks: BackgroundTasks,
    fastapi_request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """
    Physics-based energy conservation validation.

    Returns immediately with physics results (~50ms).
    GHI + AI pipeline runs asynchronously in background.
    Poll GET /analysis/{id} to retrieve the completed GHI data.
    """
    physics_engine: PhysicsEngine = fastapi_request.app.state.physics_engine

    try:
        components = [
            GridComponent(
                component_id=c.get("component_id", "unknown"),
                component_type=c.get("component_type", "generic"),
                rated_capacity_kva=c.get("rated_capacity_kva", 100),
                voltage_kv=c.get("voltage_kv"),
                resistance_ohms=c.get("resistance_ohms"),
                length_km=c.get("length_km"),
                efficiency_rating=c.get("efficiency_rating"),
                age_years=c.get("age_years"),
                load_factor=c.get("load_factor"),
            )
            for c in request.components
        ]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid component data: {str(e)}")

    result = physics_engine.validate_energy_conservation(
        input_energy_mwh=request.input_energy_mwh,
        output_energy_mwh=request.output_energy_mwh,
        components=components,
        time_window_hours=request.time_window_hours,
    )
    result_dict = result.to_dict()

    # Persist physics analysis
    analysis_id = None
    try:
        section = await get_or_create_grid_section(request.substation_id, db)
        analysis = Analysis(
            grid_section_id=section.id,
            substation_id=request.substation_id,
            input_energy_mwh=request.input_energy_mwh,
            output_energy_mwh=request.output_energy_mwh,
            time_window_hours=request.time_window_hours,
            expected_loss_mwh=result.expected_technical_loss_mwh,
            actual_loss_mwh=result.actual_loss_mwh,
            residual_mwh=result.residual_mwh,
            residual_percentage=result.residual_percentage,
            balance_status=result.balance_status.value,
            confidence_score=result.confidence_score,
            measurement_quality=result.measurement_quality,
            physics_result_json=result_dict,
            requires_review=(result.residual_percentage or 0) > 8.0,
            refusal_reason=result.refusal_reason,
            created_by=current_user.id,
        )
        db.add(analysis)
        await db.commit()
        await db.refresh(analysis)
        analysis_id = analysis.id
    except Exception as db_err:
        logger.warning(f"Failed to persist analysis: {db_err}")

    # Kick off GHI + AI as a background task — does NOT block response
    if analysis_id:
        background_tasks.add_task(
            _run_ghi_in_background,
            analysis_id=analysis_id,
            substation_id=request.substation_id,
            residual_pct=result.residual_percentage or 0.0,
            confidence=result.confidence_score,
            balance_status=result.balance_status.value,
            measurement_quality=result.measurement_quality,
            input_mwh=request.input_energy_mwh,
            output_mwh=request.output_energy_mwh,
            expected_loss_mwh=result.expected_technical_loss_mwh,
            actual_loss_mwh=result.actual_loss_mwh,
            created_by=current_user.id,
        )

    return {
        "analysis_id": analysis_id,
        "substation_id": request.substation_id,
        "analysis": result_dict,
        "ghi_status": "processing" if analysis_id else "skipped",
        "ghi_poll_url": f"/api/v1/analysis/{analysis_id}" if analysis_id else None,
        "metadata": {
            "engine": "Physics Truth Engine v2.1",
            "methodology": "First-principles thermodynamics",
            "persisted": analysis_id is not None,
            "ghi_async": True,
        },
    }


@router.post("/anomaly/detect")
async def detect_anomaly(
    request: AnomalyDetectRequest,
    fastapi_request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """ML anomaly detection — Isolation Forest + Statistical ensemble."""
    anomaly_engine = fastapi_request.app.state.anomaly_engine

    features = AnomalyFeatures(
        substation_id=request.substation_id,
        timestamp=datetime.utcnow().isoformat(),
        input_mwh=request.input_mwh,
        output_mwh=request.output_mwh,
        residual_mwh=request.residual_mwh,
        residual_percent=request.residual_percent,
        confidence_score=request.confidence_score,
        time_of_day_hour=request.time_of_day_hour,
        day_of_week=request.day_of_week,
    )

    ml_result = anomaly_engine.detect(features)

    db_id = None
    try:
        section = await get_or_create_grid_section(request.substation_id, db)
        db_anomaly = DBAnomaly(
            grid_section_id=section.id,
            analysis_id=request.analysis_id,
            substation_id=request.substation_id,
            is_anomaly=ml_result.is_anomaly,
            anomaly_score=ml_result.anomaly_score,
            confidence=ml_result.confidence,
            method_used=ml_result.method_used,
            primary_reason=ml_result.primary_reason,
            feature_contributions=ml_result.feature_contributions,
            recommended_action=ml_result.recommended_action,
        )
        db.add(db_anomaly)
        await db.commit()
        await db.refresh(db_anomaly)
        db_id = db_anomaly.id
    except Exception as e:
        logger.warning(f"Failed to persist anomaly result: {e}")

    return {
        "anomaly_result_id": db_id,
        "result": ml_result.to_dict(),
        "metadata": {"model": anomaly_engine.get_model_info()},
    }


@router.get("/stats/summary")
async def get_stats_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """
    Aggregated stats from database — powers dashboard.
    Results cached for 30 seconds to avoid repeated full-table scans.
    """
    global _stats_cache, _stats_cache_ts
    now = time.monotonic()
    if _stats_cache and (now - _stats_cache_ts) < _STATS_TTL:
        return _stats_cache

    # Run all aggregate queries concurrently via gathered coroutines
    from asyncio import gather

    async def q_total():
        return (await db.execute(select(func.count(Analysis.id)))).scalar() or 0

    async def q_avg():
        return (await db.execute(select(func.avg(Analysis.residual_percentage)))).scalar() or 0.0

    async def q_status():
        rows = (await db.execute(
            select(Analysis.balance_status, func.count(Analysis.id)).group_by(Analysis.balance_status)
        )).fetchall()
        return {r[0]: r[1] for r in rows if r[0]}

    async def q_pending():
        return (await db.execute(
            select(func.count(Analysis.id)).where(Analysis.requires_review == True, Analysis.reviewed == False)  # noqa: E712
        )).scalar() or 0

    async def q_anomaly():
        total = (await db.execute(select(func.count(DBAnomaly.id)))).scalar() or 0
        flagged = (await db.execute(
            select(func.count(DBAnomaly.id)).where(DBAnomaly.is_anomaly == True)  # noqa: E712
        )).scalar() or 0
        return total, flagged

    async def q_high_risk():
        rows = (await db.execute(
            select(Analysis.substation_id, func.avg(Analysis.residual_percentage).label("avg_r"))
            .group_by(Analysis.substation_id)
            .having(func.avg(Analysis.residual_percentage) > 8.0)
            .order_by(desc("avg_r")).limit(10)
        )).fetchall()
        return [{"substation": r[0], "avg_residual_pct": round(float(r[1]), 2)} for r in rows]

    async def q_users():
        from app.models.db_models import User as U
        return (await db.execute(select(func.count(U.id)))).scalar() or 0

    async def q_ghi():
        avg = (await db.execute(select(func.avg(GridHealthSnapshot.ghi_score)))).scalar()
        latest = (await db.execute(
            select(GridHealthSnapshot).order_by(desc(GridHealthSnapshot.created_at)).limit(1)
        )).scalar_one_or_none()
        open_i = (await db.execute(
            select(func.count(Inspection.id)).where(Inspection.status == "OPEN")
        )).scalar() or 0
        crit_i = (await db.execute(
            select(func.count(Inspection.id)).where(
                Inspection.status.in_(["OPEN", "IN_PROGRESS"]),
                Inspection.priority == "CRITICAL"
            )
        )).scalar() or 0
        return avg, latest, open_i, crit_i

    total, avg_res, by_status, pending, (anomaly_total, flagged), high_risk, users, (avg_ghi, latest_ghi, open_i, crit_i) = await gather(
        q_total(), q_avg(), q_status(), q_pending(), q_anomaly(), q_high_risk(), q_users(), q_ghi()
    )

    result = {
        "summary": {
            "total_analyses": total,
            "avg_residual_pct": round(float(avg_res), 2),
            "pending_review": pending,
            "total_anomaly_checks": anomaly_total,
            "anomalies_flagged": flagged,
            "anomaly_flag_rate_pct": round(flagged / anomaly_total * 100, 1) if anomaly_total > 0 else 0,
            "registered_users": users,
        },
        "ghi": {
            "avg_ghi": round(float(avg_ghi), 2) if avg_ghi else None,
            "latest_ghi": latest_ghi.ghi_score if latest_ghi else None,
            "latest_classification": latest_ghi.classification if latest_ghi else None,
        },
        "inspections": {"open": open_i, "critical_active": crit_i},
        "by_status": by_status,
        "high_risk_substations": high_risk,
    }

    _stats_cache = result
    _stats_cache_ts = now
    return result


@router.get("/")
async def list_analyses(
    substation_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    query = select(Analysis).order_by(desc(Analysis.created_at))
    if substation_id:
        query = query.where(Analysis.substation_id == substation_id)
    if status:
        query = query.where(Analysis.balance_status == status)
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0
    rows = (await db.execute(query.limit(limit).offset(offset))).scalars().all()
    return {
        "total": total, "limit": limit, "offset": offset,
        "items": [
            {
                "id": a.id, "substation_id": a.substation_id,
                "input_mwh": a.input_energy_mwh, "output_mwh": a.output_energy_mwh,
                "residual_pct": a.residual_percentage, "status": a.balance_status,
                "confidence": a.confidence_score, "requires_review": a.requires_review,
                "created_at": a.created_at.isoformat() if a.created_at else None
            }
            for a in rows
        ],
    }


@router.get("/{analysis_id}")
async def get_analysis(
    analysis_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Get analysis by ID. GHI/AI data appears here once background processing completes."""
    result = await db.execute(select(Analysis).where(Analysis.id == analysis_id))
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    ghi_snap = (await db.execute(
        select(GridHealthSnapshot)
        .where(GridHealthSnapshot.analysis_id == analysis_id)
        .order_by(desc(GridHealthSnapshot.created_at)).limit(1)
    )).scalar_one_or_none()

    ai_interp = (await db.execute(
        select(AIInterpretation)
        .where(AIInterpretation.analysis_id == analysis_id)
        .order_by(desc(AIInterpretation.created_at)).limit(1)
    )).scalar_one_or_none()

    inspection = (await db.execute(
        select(Inspection)
        .where(Inspection.analysis_id == analysis_id)
        .order_by(desc(Inspection.created_at)).limit(1)
    )).scalar_one_or_none()

    response: Dict[str, Any] = {
        "id": analysis.id, "substation_id": analysis.substation_id,
        "input_mwh": analysis.input_energy_mwh, "output_mwh": analysis.output_energy_mwh,
        "time_window_hours": analysis.time_window_hours,
        "residual_pct": analysis.residual_percentage, "status": analysis.balance_status,
        "confidence": analysis.confidence_score, "requires_review": analysis.requires_review,
        "reviewed": analysis.reviewed, "review_notes": analysis.review_notes,
        "refusal_reason": analysis.refusal_reason,
        "physics_result": analysis.physics_result_json,
        "created_at": analysis.created_at.isoformat() if analysis.created_at else None,
        "ghi_ready": ghi_snap is not None,
    }

    if ghi_snap:
        response["ghi"] = {
            "ghi_score": ghi_snap.ghi_score,
            "classification": ghi_snap.classification,
            "action_required": ghi_snap.action_required,
            "interpretation": ghi_snap.interpretation,
            "components": {"PBS": ghi_snap.pbs, "ASS": ghi_snap.ass, "CS": ghi_snap.cs,
                           "TSS": ghi_snap.tss, "DIS": ghi_snap.dis},
            "inspection_priority": ghi_snap.inspection_priority,
            "urgency": ghi_snap.urgency,
        }

    if ai_interp:
        response["ai_interpretation"] = {
            "risk_level": ai_interp.risk_level,
            "inspection_priority": ai_interp.inspection_priority,
            "primary_infrastructure_hypothesis": ai_interp.primary_infrastructure_hypothesis,
            "recommended_actions": ai_interp.recommended_actions,
            "confidence_commentary": ai_interp.confidence_commentary,
            "trend_assessment": ai_interp.trend_assessment,
            "estimated_investigation_scope": ai_interp.estimated_investigation_scope,
            "model_name": ai_interp.model_name,
        }

    if inspection:
        response["inspection"] = {
            "id": inspection.id, "priority": inspection.priority,
            "status": inspection.status, "urgency": inspection.urgency,
            "description": inspection.description,
        }

    return response
