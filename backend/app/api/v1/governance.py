"""
Intelligence & Governance API — UrjaRakshak v2.3
=================================================
Organizations (Multi-Tenant):
  POST /api/v1/org/                    — Create organization
  GET  /api/v1/org/                    — List my organizations
  GET  /api/v1/org/{slug}              — Get org detail
  POST /api/v1/org/{slug}/rotate-key   — Rotate API key
  GET  /api/v1/org/{slug}/quota        — Check today's quota

Model Governance:
  GET  /api/v1/org/drift/check         — Run drift detection now
  GET  /api/v1/org/drift/history       — Last N drift results

Transformer Aging:
  POST /api/v1/org/aging/compute       — Compute aging for a transformer
  GET  /api/v1/org/aging/fleet         — Fleet-wide aging summary
  GET  /api/v1/org/aging/{sub}/{tag}   — Single transformer aging record

Audit:
  GET  /api/v1/org/audit/recent        — Recent audit log entries
  GET  /api/v1/org/audit/verify        — Chain integrity check

Author: Vipin Baniya
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.database import get_db
from app.auth import get_current_active_user, require_admin, require_analyst
from app.models.db_models import (
    Organization, TransformerAgingRecord, User,
)
from app.services.tenant_service import (
    create_organization, get_org_by_slug, get_user_orgs,
    rotate_api_key, check_analysis_quota, org_to_dict,
)
from app.services.audit_service import AuditService
from app.core.drift_detection_engine import run_drift_check, get_drift_history
from app.core.transformer_aging_engine import (
    compute_and_persist_aging, get_fleet_aging_summary, aging_engine,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Organization endpoints ────────────────────────────────────────────────

class OrgCreate(BaseModel):
    slug:          str = Field(..., min_length=3, max_length=50, pattern=r'^[a-z0-9-]+$')
    name:          str = Field(..., min_length=2, max_length=255)
    plan:          str = Field(default="free", pattern=r'^(free|starter|pro|enterprise)$')
    contact_email: Optional[str] = None


@router.post("/")
async def create_org(
    body: OrgCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Create a new organization. API key shown once — save immediately."""
    result = await create_organization(
        slug=body.slug,
        name=body.name,
        plan=body.plan,
        contact_email=body.contact_email,
        db=db,
        created_by=current_user,
    )
    await AuditService.log(
        db=db,
        event_type="ORG_CREATED",
        user_id=current_user.id,
        user_email=current_user.email,
        summary=f"Created org '{body.slug}'",
    )
    await db.commit()
    return result


@router.get("/my")
async def list_my_orgs(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """List all organizations the current user belongs to."""
    orgs = await get_user_orgs(current_user.id, db)
    return {"organizations": orgs, "count": len(orgs)}


@router.get("/{slug}")
async def get_org(
    slug: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Get organization details by slug."""
    org = await get_org_by_slug(slug, db)
    if not org:
        raise HTTPException(status_code=404, detail=f"Organization '{slug}' not found.")
    return org_to_dict(org)


@router.post("/{slug}/rotate-key")
async def rotate_org_key(
    slug: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_analyst),
) -> Dict[str, Any]:
    """Rotate the API key for an organization. Old key immediately invalid."""
    org = await get_org_by_slug(slug, db)
    if not org:
        raise HTTPException(status_code=404, detail=f"Organization '{slug}' not found.")
    result = await rotate_api_key(org.id, db)
    await AuditService.log(
        db=db,
        event_type="API_KEY_ROTATED",
        org_id=org.id,
        user_id=current_user.id,
        user_email=current_user.email,
        summary=f"API key rotated for org '{slug}'",
    )
    await db.commit()
    return result


@router.get("/{slug}/quota")
async def get_quota(
    slug: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Check today's analysis quota for an organization."""
    from datetime import datetime
    from app.models.db_models import Analysis
    from sqlalchemy import func

    org = await get_org_by_slug(slug, db)
    if not org:
        raise HTTPException(status_code=404, detail="Not found")

    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    used_today = (await db.execute(
        select(func.count()).select_from(Analysis)
        .where(Analysis.created_at >= today)
    )).scalar() or 0

    return {
        "org": slug,
        "plan": org.plan,
        "limit_per_day": org.max_analyses_per_day,
        "used_today": used_today,
        "remaining": max(0, org.max_analyses_per_day - used_today),
        "exhausted": used_today >= org.max_analyses_per_day,
    }


# ── Drift detection ───────────────────────────────────────────────────────

@router.get("/drift/check")
async def check_drift(
    reference_days: int = Query(default=30, ge=7, le=90),
    evaluation_days: int = Query(default=7, ge=1, le=30),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_analyst),
) -> Dict[str, Any]:
    """
    Run drift detection now.
    Computes PSI + KS test between reference and evaluation windows.
    If SEVERE drift detected, flags for model retrain.
    """
    result = await run_drift_check(
        db=db,
        reference_days=reference_days,
        evaluation_days=evaluation_days,
    )
    await AuditService.log(
        db=db,
        event_type="DRIFT_CHECK_RUN",
        user_id=current_user.id,
        user_email=current_user.email,
        summary=f"Drift check: level={result['drift_level']} PSI={result.get('psi')}",
        metadata={"drift_level": result["drift_level"], "psi": result.get("psi")},
    )
    await db.commit()
    return result


@router.get("/drift/history")
async def drift_history(
    limit: int = Query(default=30, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Last N drift detection results."""
    history = await get_drift_history(db, limit=limit)
    return {"count": len(history), "history": history}


# ── Transformer aging ─────────────────────────────────────────────────────

class AgingComputeRequest(BaseModel):
    substation_id:        str
    transformer_tag:      str
    install_year:         Optional[int] = None
    designed_life_years:  float = Field(default=30.0, gt=0)
    load_factor:          float = Field(default=0.7, ge=0, le=2.0)
    ambient_temp_c:       float = Field(default=30.0, ge=-20, le=60)
    rated_kva:            Optional[float] = None
    rated_voltage_kv:     Optional[float] = None
    org_id:               Optional[str] = None


@router.post("/aging/compute")
async def compute_aging(
    body: AgingComputeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_analyst),
) -> Dict[str, Any]:
    """
    Compute IEC 60076-7 thermal aging for a transformer.
    Persists result and returns full aging report.
    """
    result = await compute_and_persist_aging(
        substation_id=body.substation_id,
        transformer_tag=body.transformer_tag,
        db=db,
        org_id=body.org_id,
        rated_kva=body.rated_kva,
        rated_voltage_kv=body.rated_voltage_kv,
        install_year=body.install_year,
        designed_life_years=body.designed_life_years,
        load_factor=body.load_factor,
        ambient_temp_c=body.ambient_temp_c,
    )
    # Sensitivity analysis
    result["scenarios"] = aging_engine.sensitivity_analysis(
        base_load=body.load_factor,
        base_ambient=body.ambient_temp_c,
        install_year=body.install_year,
        designed_life=body.designed_life_years,
    )
    await AuditService.log(
        db=db,
        event_type="AGING_COMPUTED",
        user_id=current_user.id,
        user_email=current_user.email,
        substation_id=body.substation_id,
        summary=(
            f"Aging computed: {body.transformer_tag} "
            f"HI={result.get('health_index')} "
            f"RUL={result.get('estimated_rul_years')}yr"
        ),
    )
    await db.commit()
    return result


@router.get("/aging/fleet")
async def fleet_aging(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Fleet-wide transformer aging summary — all tracked transformers."""
    return await get_fleet_aging_summary(db)


@router.get("/aging/{substation_id}/{transformer_tag}")
async def get_transformer_aging(
    substation_id: str,
    transformer_tag: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Get the latest aging record for a specific transformer."""
    rec = (await db.execute(
        select(TransformerAgingRecord)
        .where(TransformerAgingRecord.substation_id == substation_id)
        .where(TransformerAgingRecord.transformer_tag == transformer_tag)
        .order_by(desc(TransformerAgingRecord.computed_at))
        .limit(1)
    )).scalar_one_or_none()

    if not rec:
        raise HTTPException(
            status_code=404,
            detail=f"No aging record for '{transformer_tag}' at '{substation_id}'. Run /aging/compute first.",
        )

    return {
        "substation_id":       rec.substation_id,
        "transformer_tag":     rec.transformer_tag,
        "rated_kva":           rec.rated_kva,
        "install_year":        rec.install_year,
        "designed_life_years": rec.designed_life_years,
        "load_factor":         rec.load_factor,
        "ambient_temp_c":      rec.ambient_temp_c,
        "hot_spot_temp_c":     rec.hot_spot_temp_c,
        "thermal_aging_factor": rec.thermal_aging_factor,
        "life_consumed_pct":   rec.life_consumed_pct,
        "estimated_rul_years": rec.estimated_rul_years,
        "failure_probability": rec.failure_probability,
        "health_index":        rec.health_index,
        "condition_class":     rec.condition_class,
        "maintenance_flag":    rec.maintenance_flag,
        "replacement_flag":    rec.replacement_flag,
        "computed_at":         rec.computed_at.isoformat() if rec.computed_at else None,
    }


# ── Audit ─────────────────────────────────────────────────────────────────

@router.get("/audit/recent")
async def get_audit_log(
    limit: int = Query(default=50, le=500),
    event_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_analyst),
) -> Dict[str, Any]:
    """Recent audit log entries (most recent first)."""
    entries = await AuditService.get_recent(db, event_type=event_type, limit=limit)
    return {"count": len(entries), "entries": entries}


@router.get("/audit/verify")
async def verify_audit_chain(
    limit: int = Query(default=500, le=5000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    """
    Verify SHA-256 chain integrity of the audit ledger.
    Any broken links indicate tampering or data corruption.
    """
    report = await AuditService.verify_chain(db, limit=limit)
    return report
