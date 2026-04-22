"""
GHI Service — Orchestrates GHI computation, risk classification,
AI interpretation, inspection creation, and DB persistence.

Author: Vipin Baniya
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func

from app.core.ghi_engine import GHIInputs, GridHealthEngine
from app.core.risk_classification import RiskClassifier
from app.core.ai_interpretation_engine import (
    AIInterpretationInput, get_ai_engine
)
from app.models.db_models import (
    Analysis, AnomalyResult, GridHealthSnapshot,
    AIInterpretation, Inspection, MeterReading,
)

logger = logging.getLogger(__name__)

_ghi_engine  = GridHealthEngine()
_risk_engine = RiskClassifier()


async def run_full_ghi_pipeline(
    *,
    analysis_id: Optional[str],
    substation_id: str,
    residual_pct: float,
    confidence: float,
    balance_status: str,
    measurement_quality: str,
    input_mwh: float,
    output_mwh: float,
    expected_loss_mwh: float,
    actual_loss_mwh: float,
    db: AsyncSession,
    created_by: Optional[str] = None,
    auto_create_inspection: bool = True,
) -> Dict[str, Any]:
    """
    Full pipeline:
      1. Load recent history from DB (for TSS and AI trend context)
      2. Compute GHI
      3. Classify risk
      4. Request AI interpretation
      5. Persist GHI snapshot + AI record
      6. Auto-create inspection ticket if warranted
      7. Return assembled result dict
    """

    # 1. History ──────────────────────────────────────────────────────────
    history = await _load_residual_history(substation_id, db)
    trend   = await _load_trend(substation_id, db)
    anomaly_rate, anomalies_flagged = await _load_anomaly_rate(substation_id, db)

    # 2. GHI ──────────────────────────────────────────────────────────────
    ghi_result = _ghi_engine.compute(GHIInputs(
        residual_pct=residual_pct,
        anomaly_rate=anomaly_rate,
        confidence=confidence,
        residual_history=history,
    ))

    # 3. Risk classification ───────────────────────────────────────────────
    trend_increasing = _is_trend_increasing(history)
    risk = _risk_engine.classify(
        ghi=ghi_result.ghi,
        ghi_classification=ghi_result.classification,
        residual_pct=residual_pct,
        anomaly_rate=anomaly_rate,
        confidence=confidence,
        pbs=ghi_result.components.PBS,
        trend_increasing=trend_increasing,
        measurement_quality=measurement_quality,
    )

    # 4. AI interpretation ────────────────────────────────────────────────
    ai_engine = get_ai_engine()
    ai_result = ai_engine.interpret(AIInterpretationInput(
        substation_id=substation_id,
        timestamp=datetime.utcnow().isoformat(),
        input_mwh=input_mwh,
        output_mwh=output_mwh,
        expected_loss_mwh=expected_loss_mwh,
        actual_loss_mwh=actual_loss_mwh,
        residual_pct=residual_pct,
        balance_status=balance_status,
        measurement_quality=measurement_quality,
        anomaly_rate=anomaly_rate,
        anomalies_flagged=anomalies_flagged,
        ghi=ghi_result.ghi,
        ghi_class=ghi_result.classification,
        pbs=ghi_result.components.PBS,
        ass=ghi_result.components.ASS,
        cs=ghi_result.components.CS,
        tss=ghi_result.components.TSS,
        dis=ghi_result.components.DIS,
        priority=risk.priority.value,
        category=risk.category.value,
        confidence=confidence,
        trend=trend,
    ))

    # 5. Persist ──────────────────────────────────────────────────────────
    ghi_snap = GridHealthSnapshot(
        analysis_id=analysis_id,
        substation_id=substation_id,
        ghi_score=ghi_result.ghi,
        classification=ghi_result.classification,
        action_required=ghi_result.action_required,
        interpretation=ghi_result.interpretation,
        pbs=ghi_result.components.PBS,
        ass=ghi_result.components.ASS,
        cs=ghi_result.components.CS,
        tss=ghi_result.components.TSS,
        dis=ghi_result.components.DIS,
        confidence_in_ghi=ghi_result.confidence_in_ghi,
        inspection_priority=risk.priority.value,
        inspection_category=risk.category.value,
        urgency=risk.urgency,
    )
    db.add(ghi_snap)
    await db.flush()

    ai_record = AIInterpretation(
        analysis_id=analysis_id,
        substation_id=substation_id,
        model_name=ai_result.model_name,
        model_version=ai_result.model_version,
        prompt_hash=ai_result.prompt_hash,
        risk_level=ai_result.risk_level,
        inspection_priority=ai_result.inspection_priority,
        primary_infrastructure_hypothesis=ai_result.primary_infrastructure_hypothesis,
        recommended_actions=ai_result.recommended_actions,
        confidence_commentary=ai_result.confidence_commentary,
        trend_assessment=ai_result.trend_assessment,
        estimated_investigation_scope=ai_result.estimated_investigation_scope,
        token_usage=ai_result.token_usage,
        error=ai_result.error,
    )
    db.add(ai_record)
    await db.flush()

    # 6. Auto-create inspection ───────────────────────────────────────────
    inspection_id = None
    if auto_create_inspection and risk.requires_human_review:
        insp = Inspection(
            analysis_id=analysis_id,
            ghi_snapshot_id=ghi_snap.id,
            substation_id=substation_id,
            priority=risk.priority.value,
            category=risk.category.value,
            urgency=risk.urgency,
            status="OPEN",
            description=ghi_result.interpretation,
            recommended_actions=risk.recommended_actions,
            created_by=created_by,
        )
        db.add(insp)
        await db.flush()
        inspection_id = insp.id

    await db.commit()

    return {
        "ghi":                  ghi_result.to_dict(),
        "risk":                 risk.to_dict(),
        "ai_interpretation":    ai_result.to_dict(),
        "ghi_snapshot_id":      ghi_snap.id,
        "ai_interpretation_id": ai_record.id,
        "inspection_id":        inspection_id,
        "inspection_auto_created": inspection_id is not None,
        "ai_configured":        ai_engine.is_configured,
        "ai_provider":          ai_engine.preferred_provider,
    }


# ── DB helpers ────────────────────────────────────────────────────────────

async def _load_residual_history(substation_id: str, db: AsyncSession) -> List[float]:
    rows = (await db.execute(
        select(Analysis.residual_percentage)
        .where(Analysis.substation_id == substation_id)
        .where(Analysis.residual_percentage.isnot(None))
        .order_by(desc(Analysis.created_at))
        .limit(20)
    )).scalars().all()
    return [float(r) for r in reversed(rows)]


async def _load_trend(substation_id: str, db: AsyncSession) -> List[Dict]:
    rows = (await db.execute(
        select(Analysis.created_at, Analysis.residual_percentage)
        .where(Analysis.substation_id == substation_id)
        .order_by(desc(Analysis.created_at))
        .limit(14)
    )).fetchall()
    return [
        {"ts": r[0].isoformat() if r[0] else "", "residual_pct": round(float(r[1] or 0), 2)}
        for r in reversed(rows)
    ]


async def _load_anomaly_rate(substation_id: str, db: AsyncSession) -> Tuple[float, int]:
    total = (await db.execute(
        select(func.count(AnomalyResult.id))
        .where(AnomalyResult.substation_id == substation_id)
    )).scalar() or 0
    flagged = (await db.execute(
        select(func.count(AnomalyResult.id))
        .where(AnomalyResult.substation_id == substation_id)
        .where(AnomalyResult.is_anomaly == True)
    )).scalar() or 0
    if total > 0:
        return (flagged / total), int(flagged)

    # Fall back to MeterReading records (populated by CSV upload) when no
    # dedicated AnomalyResult records exist yet.
    total_mr = (await db.execute(
        select(func.count(MeterReading.id))
        .where(MeterReading.substation_id == substation_id)
    )).scalar() or 0
    if total_mr > 0:
        flagged_mr = (await db.execute(
            select(func.count(MeterReading.id))
            .where(MeterReading.substation_id == substation_id)
            .where(MeterReading.is_anomaly == True)
        )).scalar() or 0
        return (flagged_mr / total_mr, int(flagged_mr))

    return 0.0, 0


def _is_trend_increasing(history: List[float]) -> bool:
    if len(history) < 3:
        return False
    n = len(history)
    mean_i = (n - 1) / 2
    mean_v = sum(history) / n
    num = sum((i - mean_i) * (history[i] - mean_v) for i in range(n))
    den = sum((i - mean_i) ** 2 for i in range(n))
    if den < 1e-9:
        return False
    return (num / den) > 0.05
