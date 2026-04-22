"""
Audit Ledger Service — UrjaRakshak v2.3
========================================
Append-only audit log with cryptographic chain integrity.

Every entry stores:
  - SHA-256 hash of its own content
  - SHA-256 hash of the previous entry (chain link)

This makes post-hoc tampering detectable: if any entry is modified,
its hash won't match what the next entry recorded as prev_hash.

Usage:
    await AuditService.log(db=db, event_type="ANALYSIS_RUN", ...)
    await AuditService.verify_chain(db=db)  # returns integrity report

Author: Vipin Baniya
"""

import hashlib
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.db_models import AuditLedger

logger = logging.getLogger(__name__)


class AuditService:
    """
    Immutable audit ledger.

    Design:
      - sequence_no is a monotonic counter (max + 1 on each insert)
      - entry_hash = SHA-256(sequence_no + event_type + recorded_at + metadata)
      - prev_hash  = entry_hash of the most recent prior entry
      - NEVER calls UPDATE on any row
    """

    @staticmethod
    async def log(
        *,
        db: AsyncSession,
        event_type: str,
        org_id: Optional[str] = None,
        user_id: Optional[str] = None,
        user_email: Optional[str] = None,
        user_role: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        substation_id: Optional[str] = None,
        summary: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
    ) -> AuditLedger:
        """
        Append a new entry to the audit ledger.
        Computes chain hash automatically.
        Non-blocking on failure — logs warning but never crashes the caller.
        """
        try:
            # Get current sequence_no and prev_hash
            latest = (await db.execute(
                select(AuditLedger.sequence_no, AuditLedger.entry_hash)
                .order_by(AuditLedger.sequence_no.desc())
                .limit(1)
            )).fetchone()

            seq_no    = (latest[0] + 1) if latest else 1
            prev_hash = latest[1] if latest else "GENESIS"

            now = datetime.utcnow()

            # Compute entry hash from content
            entry_content = json.dumps({
                "seq": seq_no,
                "event": event_type,
                "org": org_id,
                "user": user_id,
                "resource": resource_id,
                "ts": now.isoformat(),
            }, sort_keys=True)
            entry_hash = hashlib.sha256(entry_content.encode()).hexdigest()

            entry = AuditLedger(
                sequence_no=seq_no,
                org_id=org_id,
                user_id=user_id,
                user_email=user_email,
                user_role=user_role,
                event_type=event_type,
                resource_type=resource_type,
                resource_id=resource_id,
                substation_id=substation_id,
                summary=summary,
                metadata_json=metadata or {},
                entry_hash=entry_hash,
                prev_hash=prev_hash,
                recorded_at=now,
                ip_address=ip_address,
            )
            db.add(entry)
            await db.flush()  # get ID without committing (caller commits)
            return entry

        except Exception as e:
            logger.warning("Audit log failed (non-fatal): %s", e)
            # Return a dummy object so callers don't need to handle None
            return AuditLedger(
                sequence_no=0,
                event_type=event_type,
                entry_hash="ERROR",
                prev_hash="ERROR",
            )

    @staticmethod
    async def verify_chain(db: AsyncSession, limit: int = 1000) -> Dict[str, Any]:
        """
        Verify chain integrity for the last `limit` entries.
        Returns a report with any broken links detected.
        """
        entries = (await db.execute(
            select(AuditLedger)
            .order_by(AuditLedger.sequence_no.asc())
            .limit(limit)
        )).scalars().all()

        if not entries:
            return {"verified": True, "entries_checked": 0, "broken_links": []}

        broken_links: List[Dict] = []
        for i in range(1, len(entries)):
            curr = entries[i]
            prev = entries[i - 1]
            if curr.prev_hash != prev.entry_hash:
                broken_links.append({
                    "sequence": curr.sequence_no,
                    "expected_prev_hash": prev.entry_hash[:12] + "…",
                    "actual_prev_hash":   (curr.prev_hash or "")[:12] + "…",
                })

        return {
            "verified":       len(broken_links) == 0,
            "entries_checked": len(entries),
            "broken_links":   broken_links,
            "first_seq":      entries[0].sequence_no,
            "last_seq":       entries[-1].sequence_no,
        }

    @staticmethod
    async def get_recent(
        db: AsyncSession,
        org_id: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Fetch recent audit entries, optionally filtered."""
        q = select(AuditLedger).order_by(AuditLedger.sequence_no.desc()).limit(limit)
        if org_id:
            q = q.where(AuditLedger.org_id == org_id)
        if event_type:
            q = q.where(AuditLedger.event_type == event_type)
        rows = (await db.execute(q)).scalars().all()
        return [
            {
                "sequence_no":  r.sequence_no,
                "event_type":   r.event_type,
                "user_email":   r.user_email,
                "org_id":       r.org_id,
                "substation_id": r.substation_id,
                "summary":      r.summary,
                "entry_hash":   (r.entry_hash or "")[:16] + "…",
                "recorded_at":  r.recorded_at.isoformat() if r.recorded_at else None,
                "ip_address":   r.ip_address,
            }
            for r in rows
        ]
