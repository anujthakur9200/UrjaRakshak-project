"""
UrjaRakshak — Meter Data Upload & Dashboard Feed
=================================================
POST /api/v1/upload/meter-data    — Upload CSV/Excel of meter readings
GET  /api/v1/upload/dashboard     — Live aggregated dashboard data (no auth for demo)
GET  /api/v1/upload/batches       — List upload history
GET  /api/v1/upload/batches/{id}  — Get batch details + anomaly table

Author: Vipin Baniya
"""

import io
import csv
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, text

from app.database import get_db
from app.models.db_models import (
    Analysis, AnomalyResult, GridSection, MeterReading,
    MeterUploadBatch, User,
)
from app.auth import get_current_active_user, require_analyst
from app.services.ghi_service import run_full_ghi_pipeline
from app.core.meter_stability_engine import update_meter_stability

logger = logging.getLogger(__name__)
router = APIRouter()


# ── CSV / Excel parsing ───────────────────────────────────────────────────

REQUIRED_COLUMNS = {"timestamp", "meter_id", "energy_kwh"}
MAX_ROWS = 50_000
ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}


def _parse_csv(content: bytes) -> List[Dict[str, Any]]:
    text_content = content.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text_content))
    rows = list(reader)
    if not rows:
        raise ValueError("CSV file is empty")
    cols = {c.strip().lower() for c in (reader.fieldnames or [])}
    missing = REQUIRED_COLUMNS - cols
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")
    return rows


def _parse_excel(content: bytes) -> List[Dict[str, Any]]:
    """Parse Excel using openpyxl (no pandas dependency)."""
    try:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.active
        rows_iter = ws.iter_rows(values_only=True)
        headers = [str(h).strip().lower() if h is not None else "" for h in next(rows_iter)]
        missing = REQUIRED_COLUMNS - set(headers)
        if missing:
            raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")
        result = []
        for row in rows_iter:
            result.append({headers[i]: row[i] for i in range(len(headers))})
        return result
    except ImportError:
        raise ValueError("Excel parsing requires openpyxl. Use CSV format or install openpyxl.")


def _coerce_row(raw: Dict[str, Any], substation_id: str, batch_id: str) -> Optional[MeterReading]:
    """Convert a raw CSV/Excel row into a MeterReading. Returns None on bad rows."""
    try:
        ts_raw = raw.get("timestamp") or raw.get("Timestamp") or ""
        if isinstance(ts_raw, datetime):
            ts = ts_raw
        else:
            ts_str = str(ts_raw).strip()
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M",
                        "%d/%m/%Y %H:%M", "%m/%d/%Y %H:%M:%S", "%Y-%m-%d"):
                try:
                    ts = datetime.strptime(ts_str, fmt)
                    break
                except ValueError:
                    continue
            else:
                return None  # Unparseable timestamp

        energy_raw = raw.get("energy_kwh") or raw.get("Energy_kWh") or 0
        try:
            energy = float(str(energy_raw).strip())
        except (ValueError, TypeError):
            return None

        if energy < 0:
            return None  # Physically invalid

        meter_id = str(raw.get("meter_id") or raw.get("Meter_ID") or "").strip()
        if not meter_id:
            return None

        return MeterReading(
            batch_id=batch_id,
            meter_id=meter_id,
            substation_id=substation_id,
            timestamp=ts,
            energy_kwh=energy,
        )
    except Exception:
        return None


# ── Statistical anomaly detection (pure numpy, no sklearn overhead) ───────

def _compute_anomaly_scores(readings: List[MeterReading]) -> List[MeterReading]:
    """
    Per-meter Z-score anomaly detection.
    For each meter, compute mean + std of that meter's readings.
    Flag readings > 2.5 std deviations as anomalous.
    Ethics guardrail: output is 'anomalous_pattern', never 'theft'.
    """
    from collections import defaultdict

    # Group by meter_id
    by_meter: Dict[str, List[MeterReading]] = defaultdict(list)
    for r in readings:
        by_meter[r.meter_id].append(r)

    for meter_id, meter_readings in by_meter.items():
        values = np.array([r.energy_kwh for r in meter_readings], dtype=float)

        if len(values) < 3:
            # Not enough data — assign neutral scores
            for r in meter_readings:
                r.z_score = 0.0
                r.anomaly_score = 0.0
                r.is_anomaly = False
            continue

        mean = float(np.mean(values))
        std = float(np.std(values))
        expected = mean  # Simple baseline: meter's own average

        if std < 1e-6:
            # All readings identical — cannot compute z-score meaningfully
            for r in meter_readings:
                r.z_score = 0.0
                r.expected_kwh = round(expected, 4)
                r.residual_kwh = round(r.energy_kwh - expected, 4)
                r.anomaly_score = 0.0
                r.is_anomaly = False
            continue

        for r in meter_readings:
            z = (r.energy_kwh - mean) / std
            r.z_score = round(float(z), 4)
            r.expected_kwh = round(expected, 4)
            r.residual_kwh = round(r.energy_kwh - expected, 4)

            abs_z = abs(z)
            # Normalised anomaly score in [0, 1]
            r.anomaly_score = round(min(abs_z / 5.0, 1.0), 4)
            r.is_anomaly = abs_z > 2.5

            if r.is_anomaly:
                direction = "high" if z > 0 else "low"
                r.anomaly_reason = (
                    f"Anomalous consumption pattern detected: "
                    f"reading {r.energy_kwh:.2f} kWh is {abs_z:.1f}σ {direction} "
                    f"of this meter's baseline ({mean:.2f} ± {std:.2f} kWh). "
                    f"Requires infrastructure inspection."
                )

    return readings


def _compute_batch_summary(readings: List[MeterReading]) -> Dict[str, Any]:
    """Compute aggregate statistics for a completed batch."""
    if not readings:
        return {"total_energy_kwh": 0.0, "residual_pct": 0.0, "confidence_score": 0.0, "anomalies": 0}

    total_energy = sum(r.energy_kwh for r in readings)
    total_expected = sum(r.expected_kwh for r in readings if r.expected_kwh is not None)
    anomaly_count = sum(1 for r in readings if r.is_anomaly)

    residual_pct = 0.0
    if total_expected > 0:
        residual_pct = round(abs(total_energy - total_expected) / total_expected * 100, 2)

    confidence_score = round(max(0.0, 1.0 - (anomaly_count / max(len(readings), 1)) * 0.5), 3)

    return {
        "total_energy_kwh": round(total_energy, 2),
        "residual_pct": residual_pct,
        "confidence_score": confidence_score,
        "anomalies": anomaly_count,
    }


# ── Upload Endpoint ───────────────────────────────────────────────────────

@router.post("/meter-data")
async def upload_meter_data(
    file: UploadFile = File(...),
    substation_id: str = Form(...),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_analyst),
) -> Dict[str, Any]:
    """
    Upload a CSV or Excel file of meter readings.
    Runs per-meter Z-score anomaly detection on the uploaded data.
    Results are stored in the database and accessible via /dashboard.

    CSV format:
        timestamp,meter_id,energy_kwh
        2026-01-01 00:00:00,MTR001,12.5
        ...
    """
    # Validate file extension
    filename = file.filename or "upload.csv"
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Accepted: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:  # 10 MB limit
        raise HTTPException(status_code=413, detail="File too large. Maximum 10 MB.")

    # Parse file
    try:
        if ext == ".csv":
            raw_rows = _parse_csv(content)
        else:
            raw_rows = _parse_excel(content)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    if len(raw_rows) > MAX_ROWS:
        raise HTTPException(
            status_code=422,
            detail=f"File contains {len(raw_rows):,} rows. Maximum allowed: {MAX_ROWS:,}."
        )

    # Create batch record
    batch = MeterUploadBatch(
        filename=filename,
        substation_id=substation_id,
        row_count=len(raw_rows),
        status="processing",
        uploaded_by=current_user.id,
    )
    db.add(batch)
    await db.flush()  # get batch.id

    # Parse rows into ORM objects
    readings: List[MeterReading] = []
    skipped = 0
    for raw in raw_rows:
        r = _coerce_row(raw, substation_id, batch.id)
        if r is not None:
            readings.append(r)
        else:
            skipped += 1

    if not readings:
        batch.status = "failed"
        batch.error_message = "No valid readings could be parsed from the file."
        await db.commit()
        raise HTTPException(status_code=422, detail=batch.error_message)

    # Run anomaly detection
    readings = _compute_anomaly_scores(readings)

    # Compute batch summary
    summary = _compute_batch_summary(readings)
    batch.total_energy_kwh = summary["total_energy_kwh"]
    batch.residual_pct = summary["residual_pct"]
    batch.confidence_score = summary["confidence_score"]
    batch.anomalies_detected = summary["anomalies"]
    batch.status = "complete"
    batch.completed_at = datetime.utcnow()

    # Bulk insert readings
    for r in readings:
        db.add(r)

    await db.commit()
    await db.refresh(batch)

    # ── Post-upload analytics: create Analysis + GHI snapshot ────────────
    # This populates the tables that Dashboard, GHI, and Inspections pages query.
    analysis = None
    try:
        total_expected_kwh = sum(
            r.expected_kwh for r in readings if r.expected_kwh is not None
        )
        total_energy_kwh_val = summary["total_energy_kwh"]
        input_mwh = round(total_energy_kwh_val / 1000.0, 4)
        # When expected == 0 (e.g. all readings had < 3 samples), treat as no-loss
        output_mwh = round(total_expected_kwh / 1000.0, 4) if total_expected_kwh > 0 else input_mwh
        actual_loss_mwh = round(abs(total_energy_kwh_val - total_expected_kwh) / 1000.0, 4)
        residual_pct = summary["residual_pct"]

        if residual_pct > 8.0:
            balance_status = "critical_imbalance"
        elif residual_pct > 5.0:
            balance_status = "significant_imbalance"
        elif residual_pct > 3.0:
            balance_status = "minor_imbalance"
        elif residual_pct > 1.0:
            balance_status = "balanced"
        else:
            balance_status = "balanced"

        analysis = Analysis(
            substation_id=substation_id,
            input_energy_mwh=input_mwh,
            output_energy_mwh=output_mwh,
            time_window_hours=24.0,
            expected_loss_mwh=0.0,
            actual_loss_mwh=actual_loss_mwh,
            residual_mwh=actual_loss_mwh,
            residual_percentage=residual_pct,
            balance_status=balance_status,
            confidence_score=summary["confidence_score"],
            measurement_quality="medium",
            requires_review=residual_pct > 3.0,
            created_by=current_user.id,
        )
        db.add(analysis)
        await db.flush()
        await db.commit()  # persist Analysis independently of GHI pipeline

        await run_full_ghi_pipeline(
            analysis_id=analysis.id,
            substation_id=substation_id,
            residual_pct=residual_pct,
            confidence=summary["confidence_score"],
            balance_status=balance_status,
            measurement_quality="medium",
            input_mwh=input_mwh,
            output_mwh=output_mwh,
            expected_loss_mwh=0.0,
            actual_loss_mwh=actual_loss_mwh,
            db=db,
            created_by=current_user.id,
        )

        # Populate per-meter stability scores so the Stream page can show data.
        unique_meter_ids = {r.meter_id for r in readings}
        for mid in unique_meter_ids:
            try:
                await update_meter_stability(
                    meter_id=mid,
                    substation_id=substation_id,
                    db=db,
                )
            except Exception as stability_err:
                logger.debug("Stability update skipped for meter %s: %s", mid, stability_err)
        await db.commit()

    except Exception as exc:  # pragma: no cover
        logger.warning("Post-upload GHI pipeline failed (batch and analysis still saved): %s", exc)
        await db.rollback()

    # Build anomaly sample for response (top 10 by anomaly score)
    top_anomalies = sorted(
        [r for r in readings if r.is_anomaly],
        key=lambda r: abs(r.z_score or 0),
        reverse=True,
    )[:10]

    return {
        "batch_id": batch.id,
        "analysis_id": analysis.id if analysis is not None else None,
        "status": "complete",
        "filename": filename,
        "substation_id": substation_id,
        "rows_received": len(raw_rows),
        "rows_parsed": len(readings),
        "rows_skipped": skipped,
        "summary": {
            "total_energy_kwh": summary["total_energy_kwh"],
            "residual_pct": summary["residual_pct"],
            "confidence_score": summary["confidence_score"],
            "anomalies_detected": summary["anomalies"],
            "anomaly_rate_pct": round(summary["anomalies"] / len(readings) * 100, 1) if readings else 0,
        },
        "anomaly_sample": [
            {
                "meter_id": r.meter_id,
                "timestamp": r.timestamp.isoformat(),
                "energy_kwh": r.energy_kwh,
                "expected_kwh": r.expected_kwh,
                "z_score": r.z_score,
                "anomaly_score": r.anomaly_score,
                "reason": r.anomaly_reason,
            }
            for r in top_anomalies
        ],
        "ethics_note": (
            "Anomalous patterns indicate infrastructure inspection priority. "
            "individual_tracking is disabled — no person-level attribution is produced. "
            "Individual-level determination requires human review. "
            "This system does not make accusation-level determinations."
        ),
    }


# ── Dashboard Data Feed ───────────────────────────────────────────────────

@router.get("/dashboard")
async def get_dashboard_data(
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Live aggregated dashboard data — no auth required (public metrics).
    Returns latest analysis, meter upload stats, anomaly summary, and trend data.
    Replaces all hardcoded frontend values.
    """

    # ── Latest analysis ──────────────────────────────────────────────
    latest_row = (await db.execute(
        select(Analysis).order_by(desc(Analysis.created_at)).limit(1)
    )).scalar_one_or_none()

    latest_analysis = None
    if latest_row:
        latest_analysis = {
            "substation_id": latest_row.substation_id,
            "input_energy_mwh": latest_row.input_energy_mwh,
            "output_energy_mwh": latest_row.output_energy_mwh,
            "residual_pct": round(latest_row.residual_percentage or 0.0, 2),
            "confidence_score": round((latest_row.confidence_score or 0.0) * 100, 1),
            "balance_status": latest_row.balance_status,
            "requires_review": latest_row.requires_review,
            "created_at": latest_row.created_at.isoformat() if latest_row.created_at else None,
        }
        # Derive technical loss %
        if latest_row.input_energy_mwh and latest_row.input_energy_mwh > 0:
            tech_loss = ((latest_row.input_energy_mwh - latest_row.output_energy_mwh)
                         / latest_row.input_energy_mwh * 100)
            latest_analysis["technical_loss_pct"] = round(tech_loss, 2)
        else:
            latest_analysis["technical_loss_pct"] = 0.0

    # ── Aggregate stats ──────────────────────────────────────────────
    total_analyses = (await db.execute(select(func.count(Analysis.id)))).scalar() or 0
    avg_residual = (await db.execute(select(func.avg(Analysis.residual_percentage)))).scalar() or 0.0
    avg_confidence = (await db.execute(select(func.avg(Analysis.confidence_score)))).scalar() or 0.0
    pending_review = (await db.execute(
        select(func.count(Analysis.id)).where(
            Analysis.requires_review == True, Analysis.reviewed == False
        )
    )).scalar() or 0

    # ── Meter upload stats ───────────────────────────────────────────
    total_batches = (await db.execute(select(func.count(MeterUploadBatch.id)))).scalar() or 0
    total_readings = (await db.execute(select(func.count(MeterReading.id)))).scalar() or 0
    total_anomalies_meter = (await db.execute(
        select(func.count(MeterReading.id)).where(MeterReading.is_anomaly == True)
    )).scalar() or 0

    # Latest batch
    latest_batch_row = (await db.execute(
        select(MeterUploadBatch).where(MeterUploadBatch.status == "complete")
        .order_by(desc(MeterUploadBatch.created_at)).limit(1)
    )).scalar_one_or_none()
    latest_batch = None
    if latest_batch_row:
        latest_batch = {
            "batch_id": latest_batch_row.id,
            "filename": latest_batch_row.filename,
            "substation_id": latest_batch_row.substation_id,
            "row_count": latest_batch_row.row_count,
            "anomalies_detected": latest_batch_row.anomalies_detected,
            "total_energy_kwh": latest_batch_row.total_energy_kwh,
            "residual_pct": latest_batch_row.residual_pct,
            "confidence_score": round((latest_batch_row.confidence_score or 0) * 100, 1),
            "created_at": latest_batch_row.created_at.isoformat() if latest_batch_row.created_at else None,
        }

    # ── Anomaly detection stats ──────────────────────────────────────
    total_anomaly_checks = (await db.execute(select(func.count(AnomalyResult.id)))).scalar() or 0
    flagged_count = (await db.execute(
        select(func.count(AnomalyResult.id)).where(AnomalyResult.is_anomaly == True)
    )).scalar() or 0

    # ── Balance status distribution ──────────────────────────────────
    status_rows = (await db.execute(
        select(Analysis.balance_status, func.count(Analysis.id))
        .group_by(Analysis.balance_status)
    )).fetchall()
    by_status = {r[0]: r[1] for r in status_rows if r[0]}

    # ── Recent analyses trend (last 10) ─────────────────────────────
    recent_rows = (await db.execute(
        select(
            Analysis.created_at,
            Analysis.residual_percentage,
            Analysis.confidence_score,
            Analysis.substation_id,
        ).order_by(desc(Analysis.created_at)).limit(10)
    )).fetchall()
    trend = [
        {
            "ts": r[0].isoformat() if r[0] else None,
            "residual_pct": round(r[1] or 0, 2),
            "confidence": round((r[2] or 0) * 100, 1),
            "substation": r[3],
        }
        for r in reversed(recent_rows)  # chronological order
    ]

    # ── High-risk substations ────────────────────────────────────────
    high_risk_rows = (await db.execute(
        select(
            Analysis.substation_id,
            func.avg(Analysis.residual_percentage).label("avg_r"),
            func.count(Analysis.id).label("n"),
        )
        .group_by(Analysis.substation_id)
        .having(func.avg(Analysis.residual_percentage) > 8.0)
        .order_by(desc("avg_r")).limit(5)
    )).fetchall()
    high_risk = [
        {"substation": r[0], "avg_residual_pct": round(float(r[1]), 2), "analyses": r[2]}
        for r in high_risk_rows
    ]

    # ── Has data? ────────────────────────────────────────────────────
    has_data = total_analyses > 0 or total_readings > 0

    return {
        "has_data": has_data,
        "latest_analysis": latest_analysis,
        "latest_batch": latest_batch,
        "aggregates": {
            "total_analyses": total_analyses,
            "avg_residual_pct": round(float(avg_residual), 2),
            "avg_confidence_pct": round(float(avg_confidence) * 100, 1),
            "pending_review": pending_review,
            "total_anomaly_checks": total_anomaly_checks,
            "anomalies_flagged": flagged_count,
            "anomaly_flag_rate_pct": round(flagged_count / total_anomaly_checks * 100, 1) if total_anomaly_checks > 0 else 0.0,
            "total_batches_uploaded": total_batches,
            "total_meter_readings": total_readings,
            "total_meter_anomalies": total_anomalies_meter,
            "meter_anomaly_rate_pct": round(total_anomalies_meter / total_readings * 100, 1) if total_readings > 0 else 0.0,
        },
        "by_status": by_status,
        "high_risk_substations": high_risk,
        "trend": trend,
    }


# ── Batch list + detail ───────────────────────────────────────────────────

@router.get("/batches")
async def list_batches(
    substation_id: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """List all meter upload batches."""
    query = select(MeterUploadBatch).order_by(desc(MeterUploadBatch.created_at))
    if substation_id:
        query = query.where(MeterUploadBatch.substation_id == substation_id)
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
    rows = (await db.execute(query.limit(limit).offset(offset))).scalars().all()
    return {
        "total": total, "limit": limit, "offset": offset,
        "items": [
            {
                "batch_id": b.id, "filename": b.filename,
                "substation_id": b.substation_id, "row_count": b.row_count,
                "anomalies_detected": b.anomalies_detected,
                "total_energy_kwh": b.total_energy_kwh,
                "residual_pct": b.residual_pct,
                "confidence_score": b.confidence_score,
                "status": b.status,
                "created_at": b.created_at.isoformat() if b.created_at else None,
            }
            for b in rows
        ],
    }


@router.get("/batches/{batch_id}")
async def get_batch(
    batch_id: str,
    limit: int = 50,
    anomalies_only: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Get batch header + top anomaly readings."""
    batch = (await db.execute(
        select(MeterUploadBatch).where(MeterUploadBatch.id == batch_id)
    )).scalar_one_or_none()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    query = (
        select(MeterReading)
        .where(MeterReading.batch_id == batch_id)
        .order_by(desc(MeterReading.anomaly_score))
        .limit(limit)
    )
    if anomalies_only:
        query = query.where(MeterReading.is_anomaly == True)

    readings = (await db.execute(query)).scalars().all()

    return {
        "batch_id": batch.id, "filename": batch.filename,
        "substation_id": batch.substation_id, "row_count": batch.row_count,
        "anomalies_detected": batch.anomalies_detected,
        "total_energy_kwh": batch.total_energy_kwh,
        "residual_pct": batch.residual_pct,
        "confidence_score": batch.confidence_score,
        "status": batch.status,
        "created_at": batch.created_at.isoformat() if batch.created_at else None,
        "readings": [
            {
                "meter_id": r.meter_id, "timestamp": r.timestamp.isoformat(),
                "energy_kwh": r.energy_kwh, "expected_kwh": r.expected_kwh,
                "z_score": r.z_score, "anomaly_score": r.anomaly_score,
                "is_anomaly": r.is_anomaly, "reason": r.anomaly_reason,
            }
            for r in readings
        ],
    }
