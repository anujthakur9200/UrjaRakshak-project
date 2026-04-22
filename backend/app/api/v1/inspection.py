"""
UrjaRakshak — Inspection Workflow API
======================================
POST   /api/v1/inspections/                    — Create inspection ticket manually
GET    /api/v1/inspections/                    — List inspections (filtered)
GET    /api/v1/inspections/{id}                — Get single inspection
PATCH  /api/v1/inspections/{id}                — Update status / findings / resolution
GET    /api/v1/inspections/stats/summary       — Aggregate stats
DELETE /api/v1/inspections/{id}                — Admin only — hard delete

Author: Vipin Baniya
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, update

from app.database import get_db
from app.auth import get_current_active_user, require_analyst, require_admin
from app.models.db_models import Inspection, User, GridSection

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Pydantic schemas ──────────────────────────────────────────────────────

_VALID_STATUSES    = {"OPEN", "IN_PROGRESS", "RESOLVED", "DISMISSED"}
_VALID_PRIORITIES  = {"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFORMATIONAL"}
_VALID_RESOLUTIONS = {
    "TECHNICAL_LOSS_NORMAL", "EQUIPMENT_FAULT",
    "METER_ISSUE", "DATA_QUALITY", "OTHER",
}


class InspectionCreate(BaseModel):
    substation_id:       str = Field(..., min_length=1, max_length=100)
    priority:            str = Field(..., pattern="^(CRITICAL|HIGH|MEDIUM|LOW|INFORMATIONAL)$")
    category:            Optional[str] = None
    urgency:             Optional[str] = None
    description:         Optional[str] = None
    recommended_actions: Optional[List[str]] = None
    analysis_id:         Optional[str] = None


class InspectionUpdate(BaseModel):
    status:           Optional[str] = Field(None, pattern="^(OPEN|IN_PROGRESS|RESOLVED|DISMISSED)$")
    findings:         Optional[str] = None
    resolution_notes: Optional[str] = None
    resolution:       Optional[str] = None
    assigned_to:      Optional[str] = None


def _inspection_to_dict(insp: Inspection) -> Dict[str, Any]:
    return {
        "id":                   insp.id,
        "substation_id":        insp.substation_id,
        "priority":             insp.priority,
        "category":             insp.category,
        "urgency":              insp.urgency,
        "status":               insp.status,
        "description":          insp.description,
        "ai_recommendation":    insp.ai_recommendation,
        "recommended_actions":  insp.recommended_actions,
        "findings":             insp.findings,
        "resolution_notes":     insp.resolution_notes,
        "resolution":           insp.resolution,
        "assigned_to":          insp.assigned_to,
        "analysis_id":          insp.analysis_id,
        "ghi_snapshot_id":      insp.ghi_snapshot_id,
        "created_by":           insp.created_by,
        "created_at":           insp.created_at.isoformat() if insp.created_at else None,
        "updated_at":           insp.updated_at.isoformat() if insp.updated_at else None,
        "closed_at":            insp.closed_at.isoformat() if insp.closed_at else None,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_inspection(
    body: InspectionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_analyst),
) -> Dict[str, Any]:
    """Manually create an inspection ticket."""
    insp = Inspection(
        substation_id=body.substation_id,
        priority=body.priority,
        category=body.category,
        urgency=body.urgency,
        status="OPEN",
        description=body.description,
        recommended_actions=body.recommended_actions,
        analysis_id=body.analysis_id,
        created_by=current_user.id,
    )
    db.add(insp)
    await db.commit()
    await db.refresh(insp)
    logger.info("Inspection created: %s priority=%s by %s", insp.id, insp.priority, current_user.email)
    return {"inspection": _inspection_to_dict(insp), "created": True}


@router.get("/stats/summary")
async def get_inspection_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Aggregated inspection statistics — powers dashboard widgets."""
    total = (await db.execute(select(func.count(Inspection.id)))).scalar() or 0

    # By status
    status_rows = (await db.execute(
        select(Inspection.status, func.count(Inspection.id))
        .group_by(Inspection.status)
    )).fetchall()
    by_status = {r[0]: r[1] for r in status_rows if r[0]}

    # By priority
    priority_rows = (await db.execute(
        select(Inspection.priority, func.count(Inspection.id))
        .group_by(Inspection.priority)
    )).fetchall()
    by_priority = {r[0]: r[1] for r in priority_rows if r[0]}

    # Open critical/high
    critical_open = (await db.execute(
        select(func.count(Inspection.id))
        .where(Inspection.status.in_(["OPEN", "IN_PROGRESS"]))
        .where(Inspection.priority.in_(["CRITICAL", "HIGH"]))
    )).scalar() or 0

    # Top substations by open inspections
    top_rows = (await db.execute(
        select(Inspection.substation_id, func.count(Inspection.id).label("n"))
        .where(Inspection.status.in_(["OPEN", "IN_PROGRESS"]))
        .group_by(Inspection.substation_id)
        .order_by(desc("n"))
        .limit(5)
    )).fetchall()
    top_substations = [{"substation": r[0], "open_count": r[1]} for r in top_rows]

    return {
        "total":           total,
        "critical_open":   critical_open,
        "by_status":       by_status,
        "by_priority":     by_priority,
        "top_substations": top_substations,
    }


@router.get("/")
async def list_inspections(
    substation_id: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    priority:      Optional[str] = None,
    limit:         int = Query(default=30, le=200),
    offset:        int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """List inspections with optional filters."""
    query = select(Inspection).order_by(
        # CRITICAL first, then by creation time
        desc(Inspection.created_at)
    )
    if substation_id:
        query = query.where(Inspection.substation_id == substation_id)
    if status_filter:
        query = query.where(Inspection.status == status_filter.upper())
    if priority:
        query = query.where(Inspection.priority == priority.upper())

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0
    rows = (await db.execute(query.limit(limit).offset(offset))).scalars().all()

    return {
        "total":  total,
        "limit":  limit,
        "offset": offset,
        "items":  [_inspection_to_dict(i) for i in rows],
    }


@router.get("/{inspection_id}")
async def get_inspection(
    inspection_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Get a single inspection by ID."""
    insp = (await db.execute(
        select(Inspection).where(Inspection.id == inspection_id)
    )).scalar_one_or_none()
    if not insp:
        raise HTTPException(status_code=404, detail="Inspection not found")
    return _inspection_to_dict(insp)


@router.patch("/{inspection_id}")
async def update_inspection(
    inspection_id: str,
    body: InspectionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_analyst),
) -> Dict[str, Any]:
    """
    Update inspection status, findings, or resolution.
    Transitions:
      OPEN → IN_PROGRESS → RESOLVED / DISMISSED
    Setting status=RESOLVED or DISMISSED auto-sets closed_at.
    """
    insp = (await db.execute(
        select(Inspection).where(Inspection.id == inspection_id)
    )).scalar_one_or_none()
    if not insp:
        raise HTTPException(status_code=404, detail="Inspection not found")

    # Apply updates
    if body.status is not None:
        new_status = body.status.upper()
        if new_status not in _VALID_STATUSES:
            raise HTTPException(status_code=422, detail=f"Invalid status: {new_status}")
        insp.status = new_status
        if new_status in ("RESOLVED", "DISMISSED"):
            insp.closed_at = datetime.utcnow()

    if body.findings is not None:
        insp.findings = body.findings
    if body.resolution_notes is not None:
        insp.resolution_notes = body.resolution_notes
    if body.resolution is not None:
        res = body.resolution.upper()
        if res not in _VALID_RESOLUTIONS:
            raise HTTPException(status_code=422, detail=f"Invalid resolution: {res}")
        insp.resolution = res
    if body.assigned_to is not None:
        insp.assigned_to = body.assigned_to

    insp.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(insp)

    logger.info(
        "Inspection %s updated: status=%s by %s",
        inspection_id, insp.status, current_user.email,
    )
    return {"inspection": _inspection_to_dict(insp), "updated": True, "human_review_required": True, "note": "Human review required before any field action. Infrastructure-scoped guidance only."}


@router.delete("/{inspection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_inspection(
    inspection_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Hard delete — admin only."""
    insp = (await db.execute(
        select(Inspection).where(Inspection.id == inspection_id)
    )).scalar_one_or_none()
    if not insp:
        raise HTTPException(status_code=404, detail="Inspection not found")
    await db.delete(insp)
    await db.commit()
    logger.warning("Inspection %s deleted by admin %s", inspection_id, current_user.email)
