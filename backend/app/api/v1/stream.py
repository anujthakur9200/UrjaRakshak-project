"""
Real-Time Streaming API — UrjaRakshak v2.3
===========================================
POST /api/v1/stream/ingest          — Push a single live meter event (SCADA/AMI)
POST /api/v1/stream/ingest/batch    — Push up to 100 events in one call
GET  /api/v1/stream/live/{sub_id}   — Server-Sent Events stream for a substation
GET  /api/v1/stream/simulate/{sub_id} — SSE simulation stream (no real data required)
GET  /api/v1/stream/meter/{meter_id}/stability  — Current stability for one meter
GET  /api/v1/stream/substation/{sub_id}/stability — All meters for a substation
GET  /api/v1/stream/recent/{sub_id} — Last N events for a substation (REST fallback)

SSE format:
  data: {"meter_id":"M01","energy_kwh":142.3,"is_anomaly":false,"z_score":0.3,...}

Design:
  - No external message broker required (works without Redis)
  - In-memory event queues per substation (dict of asyncio.Queue)
  - Meter stability scores updated on every ingest
  - Physics z-score computed per meter against its rolling baseline
  - Rolling window kept to MAX_EVENTS_IN_MEMORY to prevent memory leak

Author: Vipin Baniya
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.database import get_db
from app.auth import get_current_active_user
from app.models.db_models import LiveMeterEvent, MeterReading, MeterStabilityScore, User
from app.core.meter_stability_engine import (
    MeterStabilityEngine, update_meter_stability
)
from app.services.audit_service import AuditService

logger = logging.getLogger(__name__)
router = APIRouter()

# ── In-memory event bus (no Redis dependency) ──────────────────────────────
# Maps substation_id → list of asyncio.Queue (one per active SSE subscriber)
_sse_subscribers: Dict[str, List[asyncio.Queue]] = {}
MAX_EVENTS_IN_MEMORY = 500
MAX_QUEUE_SIZE = 200


def _get_or_create_substation_queues(substation_id: str) -> List[asyncio.Queue]:
    if substation_id not in _sse_subscribers:
        _sse_subscribers[substation_id] = []
    return _sse_subscribers[substation_id]


def _broadcast(substation_id: str, payload: Dict[str, Any]) -> None:
    """Push event to all active SSE queues for this substation."""
    queues = _sse_subscribers.get(substation_id, [])
    dead = []
    for q in queues:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            dead.append(q)  # slow consumer — evict
    for q in dead:
        queues.remove(q)


# ── Pydantic schemas ───────────────────────────────────────────────────────

class MeterEventIn(BaseModel):
    meter_id:      str   = Field(..., min_length=1, max_length=100)
    substation_id: str   = Field(..., min_length=1, max_length=100)
    event_ts:      Optional[str] = None   # ISO8601; defaults to now
    energy_kwh:    float = Field(..., ge=0)
    voltage_v:     Optional[float] = None
    current_a:     Optional[float] = None
    power_factor:  Optional[float] = None
    source:        str = "api"
    org_id:        Optional[str] = None


class BatchIngestIn(BaseModel):
    events: List[MeterEventIn] = Field(..., min_length=1, max_length=100)


# ── Single event ingest ────────────────────────────────────────────────────

@router.post("/ingest", status_code=201)
async def ingest_event(
    body: MeterEventIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """
    Push a single live meter reading.
    Computes z-score against this meter's rolling baseline in real-time.
    Updates MeterStabilityScore and broadcasts to SSE subscribers.
    """
    return await _process_single_event(body, db, current_user)


@router.post("/ingest/batch", status_code=201)
async def ingest_batch(
    body: BatchIngestIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Push up to 100 events in a single call (reduces HTTP overhead for SCADA systems)."""
    results = []
    errors  = []
    for ev in body.events:
        try:
            r = await _process_single_event(ev, db, current_user)
            results.append(r)
        except Exception as e:
            errors.append({"meter_id": ev.meter_id, "error": str(e)})

    return {
        "processed": len(results),
        "errors":    len(errors),
        "results":   results,
        "error_details": errors,
    }


async def _process_single_event(
    ev: MeterEventIn,
    db: AsyncSession,
    current_user: User,
) -> Dict[str, Any]:
    """Core event processing: persist, score, update stability, broadcast."""
    event_ts = datetime.utcnow()
    if ev.event_ts:
        try:
            event_ts = datetime.fromisoformat(ev.event_ts.replace("Z", "+00:00"))
            # Strip timezone for naive DB storage
            event_ts = event_ts.replace(tzinfo=None)
        except ValueError:
            pass

    # Get meter's rolling baseline for z-score
    stability = (await db.execute(
        select(MeterStabilityScore)
        .where(MeterStabilityScore.meter_id == ev.meter_id)
        .where(MeterStabilityScore.substation_id == ev.substation_id)
    )).scalar_one_or_none()

    z_score = None
    is_anomaly = False
    engine = MeterStabilityEngine()

    if stability and stability.rolling_mean_kwh is not None and stability.rolling_std_kwh is not None:
        z_score, is_anomaly = engine.classify_z_score(
            ev.energy_kwh,
            stability.rolling_mean_kwh,
            stability.rolling_std_kwh,
        )

    # Persist event
    live_event = LiveMeterEvent(
        org_id=ev.org_id or (current_user.id if hasattr(current_user, "org_id") else None),
        meter_id=ev.meter_id,
        substation_id=ev.substation_id,
        event_ts=event_ts,
        energy_kwh=ev.energy_kwh,
        voltage_v=ev.voltage_v,
        current_a=ev.current_a,
        power_factor=ev.power_factor,
        source=ev.source,
        is_anomaly=is_anomaly,
        anomaly_score=min(1.0, abs(z_score) / 5.0) if z_score is not None else None,
        z_score=z_score,
    )
    db.add(live_event)
    await db.flush()

    # Update stability score (async, non-blocking on failure)
    try:
        await update_meter_stability(
            meter_id=ev.meter_id,
            substation_id=ev.substation_id,
            db=db,
        )
    except Exception as e:
        logger.debug("Stability update skipped: %s", e)

    await db.commit()

    payload = {
        "event_id":     live_event.id,
        "meter_id":     ev.meter_id,
        "substation_id": ev.substation_id,
        "event_ts":     event_ts.isoformat(),
        "energy_kwh":   ev.energy_kwh,
        "z_score":      z_score,
        "is_anomaly":   is_anomaly,
        "source":       ev.source,
        "received_at":  datetime.utcnow().isoformat(),
    }

    # Broadcast to SSE subscribers
    _broadcast(ev.substation_id, payload)

    if is_anomaly:
        logger.info(
            "LIVE ANOMALY: %s @ %s z=%.2f kwh=%.2f",
            ev.meter_id, ev.substation_id, z_score or 0, ev.energy_kwh,
        )

    return payload


# ── SSE endpoint ───────────────────────────────────────────────────────────

@router.get("/live/{substation_id}")
async def stream_substation(
    substation_id: str,
    current_user: User = Depends(get_current_active_user),
) -> StreamingResponse:
    """
    Server-Sent Events stream for a substation.
    Client opens this endpoint and receives real-time meter events as they arrive.

    Connection stays open until client disconnects.
    Sends a heartbeat every 30 seconds to keep connection alive.

    Usage (browser):
      const es = new EventSource('/api/v1/stream/live/SS001')
      es.onmessage = (e) => { const data = JSON.parse(e.data); ... }
    """
    queue: asyncio.Queue = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
    queues = _get_or_create_substation_queues(substation_id)
    queues.append(queue)

    logger.info("SSE subscriber connected: substation=%s user=%s", substation_id, current_user.email)

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            # Initial connection acknowledgment
            yield f"data: {json.dumps({'type': 'connected', 'substation_id': substation_id, 'ts': datetime.utcnow().isoformat()})}\n\n"

            while True:
                try:
                    # Wait for event (with 30s heartbeat timeout)
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    event["type"] = "meter_event"
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    # Heartbeat
                    yield f"data: {json.dumps({'type': 'heartbeat', 'ts': datetime.utcnow().isoformat()})}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            # Clean up on disconnect
            try:
                queues.remove(queue)
            except ValueError:
                pass
            logger.info("SSE subscriber disconnected: substation=%s", substation_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # disable nginx buffering
            "Connection": "keep-alive",
        },
    )


# ── REST endpoints for meter data ─────────────────────────────────────────

@router.get("/recent/{substation_id}")
async def get_recent_events(
    substation_id: str,
    limit: int = Query(default=50, le=200),
    meter_id: Optional[str] = None,
    anomalies_only: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Last N live meter events for a substation (REST fallback for SSE).

    Falls back to batch-uploaded MeterReading rows when no LiveMeterEvent
    records exist for the substation, so the Stream page shows data
    immediately after a CSV upload.
    """
    q = (
        select(LiveMeterEvent)
        .where(LiveMeterEvent.substation_id == substation_id)
        .order_by(desc(LiveMeterEvent.event_ts))
        .limit(limit)
    )
    if meter_id:
        q = q.where(LiveMeterEvent.meter_id == meter_id)
    if anomalies_only:
        q = q.where(LiveMeterEvent.is_anomaly == True)

    rows = (await db.execute(q)).scalars().all()

    # If no live events exist, fall back to batch-uploaded meter readings
    if not rows:
        fq = (
            select(MeterReading)
            .where(MeterReading.substation_id == substation_id)
            .order_by(desc(MeterReading.timestamp))
            .limit(limit)
        )
        if meter_id:
            fq = fq.where(MeterReading.meter_id == meter_id)
        if anomalies_only:
            fq = fq.where(MeterReading.is_anomaly == True)
        batch_rows = (await db.execute(fq)).scalars().all()
        return {
            "substation_id": substation_id,
            "count": len(batch_rows),
            "events": [
                {
                    "id":            r.id,
                    "meter_id":      r.meter_id,
                    "event_ts":      r.timestamp.isoformat() if r.timestamp else None,
                    "energy_kwh":    r.energy_kwh,
                    "z_score":       r.z_score,
                    "is_anomaly":    r.is_anomaly,
                    "anomaly_score": r.anomaly_score,
                    "source":        "csv_upload",
                }
                for r in batch_rows
            ],
        }

    return {
        "substation_id": substation_id,
        "count": len(rows),
        "events": [
            {
                "id":          r.id,
                "meter_id":    r.meter_id,
                "event_ts":    r.event_ts.isoformat() if r.event_ts else None,
                "energy_kwh":  r.energy_kwh,
                "z_score":     r.z_score,
                "is_anomaly":  r.is_anomaly,
                "anomaly_score": r.anomaly_score,
                "source":      r.source,
            }
            for r in rows
        ],
    }


@router.get("/meter/{meter_id}/stability")
async def get_meter_stability(
    meter_id: str,
    substation_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Current stability score and metrics for a single meter."""
    rec = (await db.execute(
        select(MeterStabilityScore)
        .where(MeterStabilityScore.meter_id == meter_id)
        .where(MeterStabilityScore.substation_id == substation_id)
    )).scalar_one_or_none()

    if not rec:
        raise HTTPException(
            status_code=404,
            detail=f"No stability data for meter '{meter_id}'. Push at least 2 readings first.",
        )

    return {
        "meter_id":         rec.meter_id,
        "substation_id":    rec.substation_id,
        "stability_score":  rec.stability_score,
        "window_size":      rec.window_size,
        "rolling_mean_kwh": rec.rolling_mean_kwh,
        "rolling_std_kwh":  rec.rolling_std_kwh,
        "rolling_cv":       rec.rolling_cv,
        "trend_direction":  rec.trend_direction,
        "trend_slope":      rec.trend_slope,
        "anomaly_rate_30d": rec.anomaly_rate_30d,
        "p5_kwh":           rec.p5_kwh,
        "p95_kwh":          rec.p95_kwh,
        "total_readings":   rec.total_readings,
        "last_reading_kwh": rec.last_reading_kwh,
        "last_reading_ts":  rec.last_reading_ts.isoformat() if rec.last_reading_ts else None,
        "computed_at":      rec.computed_at.isoformat() if rec.computed_at else None,
    }


@router.get("/substation/{substation_id}/stability")
async def get_substation_stability(
    substation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Stability scores for all meters in a substation, sorted worst-first."""
    from app.core.meter_stability_engine import get_substation_stability_summary
    return await get_substation_stability_summary(substation_id, db)


@router.get("/subscribers")
async def get_subscriber_count(
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """How many active SSE connections exist per substation. For monitoring."""
    return {
        "total_connections": sum(len(qs) for qs in _sse_subscribers.values()),
        "by_substation": {
            sid: len(qs)
            for sid, qs in _sse_subscribers.items()
            if qs
        },
    }


# ── Simulation SSE endpoint ────────────────────────────────────────────────

@router.get("/simulate/{substation_id}")
async def simulate_live_stream(
    substation_id: str,
    meter_count: int = Query(default=10, ge=1, le=50),
    interval_ms: int = Query(default=2000, ge=500, le=10000),
    baseline_min_kwh: float = Query(default=3.0, ge=0.1, le=1000.0, description="Min baseline energy per meter (kWh)"),
    baseline_max_kwh: float = Query(default=8.0, ge=0.1, le=1000.0, description="Max baseline energy per meter (kWh)"),
    anomaly_pct: float = Query(default=5.0, ge=0.0, le=50.0, description="Anomaly injection probability (%)"),
    current_user: User = Depends(get_current_active_user),
) -> StreamingResponse:
    """
    Server-Sent Events stream that generates simulated meter readings for a
    substation. Useful for demos and UI development without real SCADA data.

    Each event simulates a realistic energy reading with configurable anomaly
    injection probability, baseline range, and update interval.

    Query params:
      meter_count       — number of simulated meters (1–50, default 10)
      interval_ms       — milliseconds between events (500–10000, default 2000)
      baseline_min_kwh  — min baseline energy per meter (default 3.0 kWh)
      baseline_max_kwh  — max baseline energy per meter (default 8.0 kWh)
      anomaly_pct       — anomaly injection probability in percent (default 5%)
    """
    import random

    # Validate baseline range
    if baseline_min_kwh >= baseline_max_kwh:
        raise HTTPException(
            status_code=422,
            detail="baseline_min_kwh must be less than baseline_max_kwh"
        )

    anomaly_prob = anomaly_pct / 100.0

    # Per-meter rolling baselines (mean, std) seeded from substation_id for reproducibility
    rng = random.Random(hash(substation_id) % (2**32))
    std_range = max(0.1, (baseline_max_kwh - baseline_min_kwh) * 0.15)
    baselines: Dict[str, Dict[str, float]] = {
        f"SIM-{substation_id}-M{i+1:02d}": {
            "mean": rng.uniform(baseline_min_kwh, baseline_max_kwh),
            "std": rng.uniform(std_range * 0.25, std_range),
        }
        for i in range(meter_count)
    }
    meter_ids = list(baselines.keys())
    interval_s = interval_ms / 1000.0

    async def simulation_generator() -> AsyncGenerator[str, None]:
        try:
            yield f"data: {json.dumps({'type': 'connected', 'substation_id': substation_id, 'meter_count': meter_count, 'ts': datetime.utcnow().isoformat()})}\n\n"

            while True:
                meter_id = rng.choice(meter_ids)
                baseline = baselines[meter_id]
                mean, std = baseline["mean"], baseline["std"]

                # Inject anomaly with configurable probability
                is_anomaly = rng.random() < anomaly_prob
                if is_anomaly:
                    # Spike or drop
                    direction = rng.choice([1, -1])
                    energy = round(mean + direction * rng.uniform(3.0 * std, 5.0 * std), 3)
                    energy = max(0.0, energy)
                    z_score = round((energy - mean) / std, 2) if std > 0 else 0.0
                else:
                    energy = round(max(0.0, rng.gauss(mean, std)), 3)
                    z_score = round((energy - mean) / std, 2) if std > 0 else 0.0

                event = {
                    "type": "meter_event",
                    "meter_id": meter_id,
                    "substation_id": substation_id,
                    "energy_kwh": energy,
                    "is_anomaly": is_anomaly,
                    "z_score": z_score,
                    "event_ts": datetime.utcnow().isoformat(),
                    "source": "simulation",
                }
                yield f"data: {json.dumps(event)}\n\n"

                # Also broadcast to any SSE subscribers for this substation
                _broadcast(substation_id, event)

                await asyncio.sleep(interval_s)

        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        simulation_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
