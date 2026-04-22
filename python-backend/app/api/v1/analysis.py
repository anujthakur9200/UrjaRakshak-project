"""
Analysis API — v1
=================
POST /analyze        Run energy balance analysis using the physics engine.
GET  /history        Return paginated mock analysis history.
GET  /{analysis_id}  Return a specific past analysis.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.physics.engine import analyze_energy_balance
from app.schemas.models import (
    AnalysisRequest,
    AnalysisResponse,
    AnalysisHistoryItem,
    ComponentLossOut,
    HypothesisOut,
)
from app.utils.helpers import generate_analysis_id, utcnow

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────
# In-memory store (replaced by DB in production)
# ─────────────────────────────────────────────────────────────────────

_store: dict[str, AnalysisResponse] = {}


# ─────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────


@router.post("/analyze", response_model=AnalysisResponse, status_code=status.HTTP_201_CREATED)
async def run_analysis(body: AnalysisRequest) -> AnalysisResponse:
    """
    Run a physics-based energy balance analysis for a grid section.

    Accepts meter readings (input / output kWh) and component metadata,
    returns full loss breakdown, residual analysis, and ranked hypotheses.
    """
    components_dicts = [c.model_dump() for c in body.components]

    result = analyze_energy_balance(
        input_kwh=body.input_kwh,
        output_kwh=body.output_kwh,
        components=components_dicts,
    )

    analysis_id = generate_analysis_id(body.substation_id)

    response = AnalysisResponse(
        analysis_id=analysis_id,
        substation_id=body.substation_id,
        status="completed",
        total_input_kwh=result.total_input_kwh,
        total_output_kwh=result.total_output_kwh,
        total_loss_kwh=result.total_loss_kwh,
        loss_percentage=result.loss_percentage,
        technical_loss_kwh=result.technical_loss_kwh,
        residual_kwh=result.residual_kwh,
        residual_pct=result.residual_pct,
        balance_status=result.balance_status,
        confidence_score=result.confidence_score,
        components=[
            ComponentLossOut(
                component_id=c.component_id,
                component_type=c.component_type,
                calculated_loss_kwh=c.calculated_loss_kwh,
                loss_percentage=c.loss_percentage,
                confidence=c.confidence,
            )
            for c in result.components
        ],
        hypotheses=[
            HypothesisOut(
                cause=h["cause"],
                probability=h["probability"],
                confidence=h["confidence"],
                description=h.get("description", ""),
                recommended_action=h.get("recommended_action", ""),
            )
            for h in result.hypotheses
        ],
        timestamp=utcnow(),
    )

    _store[analysis_id] = response
    return response


@router.get("/history", response_model=list[AnalysisHistoryItem])
async def get_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    substation_id: Optional[str] = Query(None),
) -> list[AnalysisHistoryItem]:
    """Return paginated analysis history (stored + seed mock data)."""

    items = list(_store.values())

    # Seed a few mock records if the store is empty so the UI has data
    if not items:
        items = _generate_mock_history()

    if substation_id:
        items = [i for i in items if i.substation_id == substation_id]

    # Newest first
    items_sorted = sorted(items, key=lambda i: i.timestamp, reverse=True)
    start = (page - 1) * page_size
    end = start + page_size
    page_items = items_sorted[start:end]

    return [
        AnalysisHistoryItem(
            analysis_id=i.analysis_id,
            substation_id=i.substation_id,
            balance_status=i.balance_status,
            loss_percentage=i.loss_percentage,
            confidence_score=i.confidence_score,
            timestamp=i.timestamp,
        )
        for i in page_items
    ]


@router.get("/{analysis_id}", response_model=AnalysisResponse)
async def get_analysis(analysis_id: str) -> AnalysisResponse:
    """Retrieve a specific analysis by ID."""
    record = _store.get(analysis_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis '{analysis_id}' not found.",
        )
    return record


# ─────────────────────────────────────────────────────────────────────
# Mock seed helpers
# ─────────────────────────────────────────────────────────────────────


def _generate_mock_history() -> list[AnalysisResponse]:
    now = utcnow()
    records = []
    mock_data = [
        ("SS-001", 10000.0, 9720.0, "balanced"),
        ("SS-002", 8500.0, 8100.0, "minor_imbalance"),
        ("SS-003", 12000.0, 11100.0, "significant_imbalance"),
        ("SS-004", 9000.0, 8820.0, "balanced"),
        ("SS-005", 7500.0, 6800.0, "critical_imbalance"),
    ]
    for i, (sub_id, inp, out, status_str) in enumerate(mock_data):
        analysis_id = f"ANA-MOCK-{i+1:04d}"
        loss = inp - out
        loss_pct = round(loss / inp * 100, 3)
        residual = round(loss * 0.4, 2)
        residual_pct = round(residual / inp * 100, 3)
        records.append(
            AnalysisResponse(
                analysis_id=analysis_id,
                substation_id=sub_id,
                status="completed",
                total_input_kwh=inp,
                total_output_kwh=out,
                total_loss_kwh=loss,
                loss_percentage=loss_pct,
                technical_loss_kwh=round(loss * 0.6, 2),
                residual_kwh=residual,
                residual_pct=residual_pct,
                balance_status=status_str,
                confidence_score=round(0.90 - i * 0.05, 2),
                components=[],
                hypotheses=[],
                timestamp=now - timedelta(hours=i * 6),
            )
        )
    return records
