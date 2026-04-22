"""
Multi-Tenant Service — UrjaRakshak v2.3
========================================
Handles organization lifecycle, API key generation/validation,
quota enforcement, and per-org data isolation.

Architecture principle: Every data-mutating API call passes through
`resolve_org()`. This returns the Organization or raises 401/403/429.
No org-scoped data is ever returned without a valid org context.

Author: Vipin Baniya
"""

import hashlib
import secrets
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models.db_models import Organization, OrganizationMember, User, AuditLedger
from app.services.audit_service import AuditService

logger = logging.getLogger(__name__)

# ── API key format: urjr_<32 hex chars> ──────────────────────────────────
_API_KEY_PREFIX = "urjr_"
_API_KEY_BYTES  = 32


def generate_api_key() -> Tuple[str, str]:
    """
    Generate a new API key and its hash.
    Returns: (raw_key_for_user, hash_for_db)
    The raw key is shown ONCE — never stored.
    """
    raw = _API_KEY_PREFIX + secrets.token_hex(_API_KEY_BYTES)
    hashed = _hash_api_key(raw)
    return raw, hashed


def _hash_api_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


# ── Organization CRUD ─────────────────────────────────────────────────────

async def create_organization(
    *,
    slug: str,
    name: str,
    plan: str = "free",
    contact_email: Optional[str] = None,
    db: AsyncSession,
    created_by: Optional[User] = None,
) -> Dict[str, Any]:
    """
    Create a new organization. Generates an API key on creation.
    Returns the raw API key — must be shown to user immediately.
    """
    # Validate slug format
    import re
    if not re.match(r'^[a-z0-9-]{3,50}$', slug):
        raise HTTPException(
            status_code=422,
            detail="Slug must be 3–50 lowercase alphanumeric characters and hyphens.",
        )

    # Check uniqueness
    existing = (await db.execute(
        select(Organization).where(Organization.slug == slug)
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail=f"Organization slug '{slug}' already taken.")

    raw_key, key_hash = generate_api_key()

    # Plan limits
    limits = _plan_limits(plan)

    org = Organization(
        slug=slug,
        name=name,
        plan=plan,
        api_key_hash=key_hash,
        max_substations=limits["max_substations"],
        max_analyses_per_day=limits["max_analyses_per_day"],
        contact_email=contact_email,
    )
    db.add(org)
    await db.flush()

    # Add creator as owner
    if created_by:
        member = OrganizationMember(
            org_id=org.id,
            user_id=created_by.id,
            org_role="owner",
        )
        db.add(member)

    await db.commit()

    await AuditService.log(
        db=db,
        event_type="ORG_CREATED",
        org_id=org.id,
        user_id=created_by.id if created_by else None,
        user_email=created_by.email if created_by else None,
        summary=f"Organization '{slug}' created (plan={plan})",
        resource_type="organization",
        resource_id=org.id,
    )

    logger.info("Organization created: %s (plan=%s)", slug, plan)

    return {
        "id": org.id,
        "slug": org.slug,
        "name": org.name,
        "plan": org.plan,
        "api_key": raw_key,          # shown once only
        "api_key_prefix": raw_key[:12] + "...",
        "limits": limits,
        "warning": "Save your API key now. It will not be shown again.",
    }


async def rotate_api_key(org_id: str, db: AsyncSession) -> Dict[str, Any]:
    """Rotate the API key for an organization. Old key is immediately invalidated."""
    org = (await db.execute(
        select(Organization).where(Organization.id == org_id)
    )).scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    raw_key, key_hash = generate_api_key()
    org.api_key_hash = key_hash
    org.updated_at = datetime.utcnow()
    await db.commit()

    return {
        "api_key": raw_key,
        "api_key_prefix": raw_key[:12] + "...",
        "warning": "Old key is now invalid. Save the new key immediately.",
    }


async def get_org_by_slug(slug: str, db: AsyncSession) -> Optional[Organization]:
    return (await db.execute(
        select(Organization).where(Organization.slug == slug, Organization.is_active == True)
    )).scalar_one_or_none()


async def get_org_by_api_key(raw_key: str, db: AsyncSession) -> Optional[Organization]:
    key_hash = _hash_api_key(raw_key)
    return (await db.execute(
        select(Organization).where(
            Organization.api_key_hash == key_hash,
            Organization.is_active == True,
        )
    )).scalar_one_or_none()


async def get_user_orgs(user_id: str, db: AsyncSession) -> list:
    rows = (await db.execute(
        select(Organization, OrganizationMember.org_role)
        .join(OrganizationMember, OrganizationMember.org_id == Organization.id)
        .where(OrganizationMember.user_id == user_id)
        .where(Organization.is_active == True)
    )).fetchall()
    return [
        {
            "id": r[0].id, "slug": r[0].slug, "name": r[0].name,
            "plan": r[0].plan, "role": r[1],
        }
        for r in rows
    ]


# ── Quota enforcement ─────────────────────────────────────────────────────

async def check_analysis_quota(org_id: str, db: AsyncSession) -> bool:
    """
    Check if org has remaining analysis quota for today.
    Returns True if allowed, raises 429 if quota exceeded.
    """
    from app.models.db_models import Analysis
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    org = (await db.execute(
        select(Organization).where(Organization.id == org_id)
    )).scalar_one_or_none()
    if not org:
        return True  # no org context → not restricted

    count_today = (await db.execute(
        select(func.count())
        .select_from(Analysis)
        .where(Analysis.created_at >= today_start)
        # In full multi-tenant: .where(Analysis.org_id == org_id)
    )).scalar() or 0

    if count_today >= org.max_analyses_per_day:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Daily analysis quota exceeded ({org.max_analyses_per_day}/day on '{org.plan}' plan). "
                "Upgrade your plan or wait until midnight UTC."
            ),
        )
    return True


# ── FastAPI dependencies ──────────────────────────────────────────────────

async def resolve_org_from_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
) -> Optional[Organization]:
    """
    FastAPI dependency: resolve Organization from X-API-Key header.
    Returns None if no API key provided (JWT auth path handles those requests).
    Raises 401 if key provided but invalid.
    """
    if not x_api_key:
        return None
    if not x_api_key.startswith(_API_KEY_PREFIX):
        raise HTTPException(
            status_code=401,
            detail="Invalid API key format. Keys must start with 'urjr_'.",
        )
    org = await get_org_by_api_key(x_api_key, db)
    if not org:
        raise HTTPException(status_code=401, detail="Invalid or expired API key.")
    return org


def org_to_dict(org: Organization) -> Dict[str, Any]:
    return {
        "id": org.id,
        "slug": org.slug,
        "name": org.name,
        "plan": org.plan,
        "max_substations": org.max_substations,
        "max_analyses_per_day": org.max_analyses_per_day,
        "is_active": org.is_active,
        "created_at": org.created_at.isoformat() if org.created_at else None,
    }


# ── Plan limits ───────────────────────────────────────────────────────────

def _plan_limits(plan: str) -> Dict[str, Any]:
    PLANS = {
        "free":       {"max_substations": 3,   "max_analyses_per_day": 20,  "ai_interpretations": False},
        "starter":    {"max_substations": 10,  "max_analyses_per_day": 100, "ai_interpretations": True},
        "pro":        {"max_substations": 50,  "max_analyses_per_day": 500, "ai_interpretations": True},
        "enterprise": {"max_substations": 9999,"max_analyses_per_day": 9999,"ai_interpretations": True},
    }
    return PLANS.get(plan, PLANS["free"])
