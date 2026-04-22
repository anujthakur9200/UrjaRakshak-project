"""
Streaming API — v1
==================
GET  /events/{substation_id}  SSE stream of live meter events.
POST /ingest                  Ingest a single meter event.
"""

from __future__ import annotations

import asyncio
import json
import random
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from app.schemas.models import IngestResponse, MeterEvent
from app.utils.helpers import generate_event_id, utcnow

router = APIRouter()

# In-memory per-substation event queues (keyed by substation_id)
_queues: dict[str, asyncio.Queue] = {}


def _get_queue(substation_id: str) -> asyncio.Queue:
    if substation_id not in _queues:
        _queues[substation_id] = asyncio.Queue(maxsize=500)
    return _queues[substation_id]


# ─────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────


@router.get("/events/{substation_id}", response_class=StreamingResponse)
async def stream_events(substation_id: str, simulate: bool = False):
    """
    Server-Sent Events stream for a substation.

    Query parameter:
      simulate=true  — inject synthetic meter readings every 2 s
                       (useful for frontend demo without real hardware).
    """
    queue = _get_queue(substation_id)

    async def _event_generator() -> AsyncGenerator[str, None]:
        # Initial connection acknowledgement
        yield _sse("connected", {"substation_id": substation_id, "message": "Stream open"})

        while True:
            if simulate:
                # Generate a synthetic meter event
                event = _synthetic_event(substation_id)
                data = event.model_dump(mode="json")
                yield _sse("meter_reading", data)
                await asyncio.sleep(2.0)
            else:
                try:
                    event_data = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield _sse("meter_reading", event_data)
                except asyncio.TimeoutError:
                    # Heartbeat to keep connection alive
                    yield _sse("heartbeat", {"ts": utcnow().isoformat()})

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/ingest", response_model=IngestResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest_event(event: MeterEvent) -> IngestResponse:
    """
    Ingest a meter event and push it to the substation's SSE queue.

    Returns 202 Accepted immediately; listeners on /events/{substation_id}
    will receive the event asynchronously.
    """
    queue = _get_queue(event.substation_id)

    try:
        queue.put_nowait(event.model_dump(mode="json"))
    except asyncio.QueueFull:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Event queue full — retry later.",
        )

    return IngestResponse(
        received=True,
        event_id=event.event_id,
        message=f"Event queued for substation '{event.substation_id}'",
    )


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────


def _sse(event_type: str, data: dict) -> str:
    """Format a dict as a Server-Sent Event string."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


def _synthetic_event(substation_id: str) -> MeterEvent:
    """Generate a plausible synthetic meter reading for demo purposes."""
    base_energy = random.uniform(85.0, 115.0)
    voltage = random.gauss(230.0, 3.0)
    current = random.gauss(50.0, 5.0)
    pf = random.uniform(0.85, 0.99)

    return MeterEvent(
        event_id=generate_event_id(),
        substation_id=substation_id,
        meter_id=f"MTR-{substation_id}-{random.randint(1, 50):03d}",
        timestamp=utcnow(),
        energy_kwh=round(base_energy, 3),
        voltage_v=round(voltage, 2),
        current_a=round(current, 2),
        power_factor=round(pf, 4),
        event_type="reading",
        metadata={"simulated": True},
    )
