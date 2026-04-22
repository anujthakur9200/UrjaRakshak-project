"""
Model Drift Detection Engine — UrjaRakshak v2.3
================================================
Detects when the Isolation Forest anomaly model has become stale
relative to current grid behaviour.

Two statistical tests are run:
  1. Population Stability Index (PSI) — industry standard for model drift
     PSI < 0.10  → NONE     (stable)
     PSI < 0.20  → MINOR    (monitor)
     PSI < 0.25  → MODERATE (schedule retrain)
     PSI ≥ 0.25  → SEVERE   (retrain immediately)

  2. Kolmogorov-Smirnov two-sample test — non-parametric distribution comparison
     ks_pvalue < 0.05 → distributions are significantly different

  3. Anomaly Rate Shift — simple comparison of reference vs current rate
     |current - reference| > 0.05 → notable shift

If SEVERE drift detected, a retrain is automatically triggered.

Reference window: last 30 days of anomaly scores when model was trained
Evaluation window: last 7 days of anomaly scores

Author: Vipin Baniya
"""

import logging
import math
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func

from app.models.db_models import AnomalyResult, MeterReading, ModelDriftLog, ModelVersion

logger = logging.getLogger(__name__)

# PSI thresholds
PSI_NONE     = 0.10
PSI_MINOR    = 0.20
PSI_MODERATE = 0.25

# Minimum samples needed for reliable test
MIN_REFERENCE_SAMPLES = 30
MIN_EVALUATION_SAMPLES = 10


class DriftDetectionEngine:
    """
    Computes Population Stability Index and KS statistic between
    the reference anomaly score distribution (training time) and
    the current distribution (recent predictions).
    """

    def compute_psi(
        self,
        reference: List[float],
        evaluation: List[float],
        n_buckets: int = 10,
    ) -> Dict[str, Any]:
        """
        Population Stability Index.

        PSI = Σ (actual% - expected%) × ln(actual% / expected%)

        Parameters
        ----------
        reference  : scores from training/reference period
        evaluation : scores from recent evaluation period
        n_buckets  : histogram bin count
        """
        if len(reference) < 2 or len(evaluation) < 2:
            return {"psi": None, "error": "Insufficient samples"}

        # Build buckets from reference distribution
        min_val = min(min(reference), min(evaluation))
        max_val = max(max(reference), max(evaluation))

        if max_val == min_val:
            return {"psi": 0.0, "buckets": n_buckets, "note": "Zero variance — identical distributions"}

        bucket_width = (max_val - min_val) / n_buckets
        edges = [min_val + i * bucket_width for i in range(n_buckets + 1)]
        edges[-1] = max_val + 1e-9  # ensure last value included

        def bucket_counts(values: List[float]) -> List[int]:
            counts = [0] * n_buckets
            for v in values:
                idx = min(int((v - min_val) / bucket_width), n_buckets - 1)
                idx = max(0, idx)
                counts[idx] += 1
            return counts

        ref_counts  = bucket_counts(reference)
        eval_counts = bucket_counts(evaluation)

        n_ref  = len(reference)
        n_eval = len(evaluation)

        psi = 0.0
        bucket_details = []
        for i in range(n_buckets):
            ref_pct  = max(ref_counts[i] / n_ref,   1e-9)  # avoid log(0)
            eval_pct = max(eval_counts[i] / n_eval,  1e-9)
            contrib  = (eval_pct - ref_pct) * math.log(eval_pct / ref_pct)
            psi += contrib
            bucket_details.append({
                "bucket": i,
                "ref_pct":  round(ref_pct, 4),
                "eval_pct": round(eval_pct, 4),
                "contrib":  round(contrib, 6),
            })

        return {
            "psi":            round(psi, 6),
            "n_ref":          n_ref,
            "n_eval":         n_eval,
            "n_buckets":      n_buckets,
            "bucket_details": bucket_details,
        }

    def compute_ks(
        self,
        reference: List[float],
        evaluation: List[float],
    ) -> Dict[str, Any]:
        """
        Two-sample Kolmogorov-Smirnov statistic.
        Returns KS statistic and approximate p-value.

        Implemented without scipy to avoid heavy dependency.
        Uses Hodges (1958) approximation for p-value.
        """
        if len(reference) < 2 or len(evaluation) < 2:
            return {"ks_statistic": None, "ks_pvalue": None}

        n1 = len(reference)
        n2 = len(evaluation)

        sorted_ref  = sorted(reference)
        sorted_eval = sorted(evaluation)

        # Compute empirical CDFs at all combined points
        all_points = sorted(set(sorted_ref + sorted_eval))
        max_diff = 0.0

        for x in all_points:
            cdf1 = sum(1 for v in sorted_ref  if v <= x) / n1
            cdf2 = sum(1 for v in sorted_eval if v <= x) / n2
            max_diff = max(max_diff, abs(cdf1 - cdf2))

        ks_stat = max_diff

        # Approximate p-value using Kolmogorov distribution
        # For large samples: p ≈ 2 * exp(-2 * n_eff * D²)
        n_eff = (n1 * n2) / (n1 + n2)
        try:
            p_approx = 2.0 * math.exp(-2.0 * n_eff * ks_stat ** 2)
            p_approx = min(1.0, max(0.0, p_approx))
        except (OverflowError, ValueError):
            p_approx = 0.0

        return {
            "ks_statistic": round(ks_stat, 6),
            "ks_pvalue":    round(p_approx, 6),
            "significant":  p_approx < 0.05,
        }

    def classify_drift(
        self,
        psi: Optional[float],
        ks_stat: Optional[float],
        rate_shift: float,
    ) -> Tuple[str, bool]:
        """
        Classify drift level and whether retraining is required.
        Returns: (drift_level, requires_retraining)
        """
        if psi is None:
            # Fall back to rate shift only
            if abs(rate_shift) > 0.10:
                return "MODERATE", True
            elif abs(rate_shift) > 0.05:
                return "MINOR", False
            return "NONE", False

        if psi >= PSI_MODERATE:
            return "SEVERE", True
        elif psi >= PSI_MINOR:
            return "MODERATE", True
        elif psi >= PSI_NONE:
            return "MINOR", False
        return "NONE", False


# ── DB-integrated drift check ─────────────────────────────────────────────

async def run_drift_check(
    db: AsyncSession,
    model_name: str = "IsolationForest",
    reference_days: int = 30,
    evaluation_days: int = 7,
) -> Dict[str, Any]:
    """
    Load anomaly scores from DB and run full drift detection.
    Persists a ModelDriftLog record and returns full report.
    """
    engine = DriftDetectionEngine()
    now = datetime.utcnow()

    # Reference window: 30–7 days ago
    ref_start  = now - timedelta(days=reference_days)
    ref_end    = now - timedelta(days=evaluation_days)

    # Evaluation window: last 7 days
    eval_start = now - timedelta(days=evaluation_days)

    # Fetch scores
    ref_rows = (await db.execute(
        select(AnomalyResult.anomaly_score)
        .where(AnomalyResult.created_at >= ref_start)
        .where(AnomalyResult.created_at <  ref_end)
        .limit(2000)
    )).scalars().all()

    eval_rows = (await db.execute(
        select(AnomalyResult.anomaly_score)
        .where(AnomalyResult.created_at >= eval_start)
        .limit(500)
    )).scalars().all()

    ref_scores  = [float(s) for s in ref_rows  if s is not None]
    eval_scores = [float(s) for s in eval_rows if s is not None]

    # Fall back to MeterReading.anomaly_score when AnomalyResult has insufficient samples.
    # This ensures drift detection works immediately after a CSV upload, before any dedicated
    # ML results have been recorded in AnomalyResult.
    if len(ref_scores) < MIN_REFERENCE_SAMPLES:
        mr_ref = (await db.execute(
            select(MeterReading.anomaly_score)
            .where(MeterReading.anomaly_score.isnot(None))
            .where(MeterReading.timestamp >= ref_start)
            .where(MeterReading.timestamp <  ref_end)
            .limit(2000)
        )).scalars().all()
        if len(mr_ref) > len(ref_scores):
            ref_scores = [float(s) for s in mr_ref if s is not None]

    if len(eval_scores) < MIN_EVALUATION_SAMPLES:
        mr_eval = (await db.execute(
            select(MeterReading.anomaly_score)
            .where(MeterReading.anomaly_score.isnot(None))
            .where(MeterReading.timestamp >= eval_start)
            .limit(500)
        )).scalars().all()
        if len(mr_eval) > len(eval_scores):
            eval_scores = [float(s) for s in mr_eval if s is not None]

    # Reference anomaly rate — prefer AnomalyResult, fall back to MeterReading
    ref_anomaly_count = (await db.execute(
        select(func.count(AnomalyResult.id))
        .where(AnomalyResult.is_anomaly == True)
        .where(AnomalyResult.created_at >= ref_start)
        .where(AnomalyResult.created_at <  ref_end)
    )).scalar() or 0
    if ref_anomaly_count == 0:
        ref_anomaly_count = (await db.execute(
            select(func.count(MeterReading.id))
            .where(MeterReading.is_anomaly == True)
            .where(MeterReading.timestamp >= ref_start)
            .where(MeterReading.timestamp <  ref_end)
        )).scalar() or 0
    ref_total = len(ref_scores) or 1
    reference_anomaly_rate = ref_anomaly_count / ref_total

    eval_anomaly_count = (await db.execute(
        select(func.count(AnomalyResult.id))
        .where(AnomalyResult.is_anomaly == True)
        .where(AnomalyResult.created_at >= eval_start)
    )).scalar() or 0
    if eval_anomaly_count == 0:
        eval_anomaly_count = (await db.execute(
            select(func.count(MeterReading.id))
            .where(MeterReading.is_anomaly == True)
            .where(MeterReading.timestamp >= eval_start)
        )).scalar() or 0
    eval_total = len(eval_scores) or 1
    current_anomaly_rate = eval_anomaly_count / eval_total

    rate_shift = current_anomaly_rate - reference_anomaly_rate

    # Check if we have enough data
    sufficient = (
        len(ref_scores)  >= MIN_REFERENCE_SAMPLES and
        len(eval_scores) >= MIN_EVALUATION_SAMPLES
    )

    psi_result = engine.compute_psi(ref_scores, eval_scores) if sufficient else {"psi": None}
    ks_result  = engine.compute_ks(ref_scores, eval_scores)  if sufficient else {"ks_statistic": None, "ks_pvalue": None}

    psi   = psi_result.get("psi")
    ks    = ks_result.get("ks_statistic")
    ksp   = ks_result.get("ks_pvalue")

    drift_level, requires_retraining = engine.classify_drift(psi, ks, rate_shift)

    # Get current active model version
    model_ver = (await db.execute(
        select(ModelVersion)
        .where(ModelVersion.model_name == model_name)
        .where(ModelVersion.is_active == True)
        .order_by(desc(ModelVersion.trained_at))
        .limit(1)
    )).scalar_one_or_none()

    # Persist drift log
    drift_log = ModelDriftLog(
        model_version_id=model_ver.id if model_ver else None,
        model_name=model_name,
        reference_anomaly_rate=round(reference_anomaly_rate, 4),
        current_anomaly_rate=round(current_anomaly_rate, 4),
        drift_magnitude=round(abs(rate_shift), 4),
        psi_score=psi,
        ks_statistic=ks,
        ks_pvalue=ksp,
        drift_level=drift_level,
        requires_retraining=requires_retraining,
        reference_window_days=reference_days,
        evaluation_window_days=evaluation_days,
        n_reference_samples=len(ref_scores),
        n_evaluation_samples=len(eval_scores),
        detected_at=now,
    )
    db.add(drift_log)
    await db.commit()

    logger.info(
        "Drift check: %s | PSI=%.4f | KS=%.4f | rate_shift=%.4f | level=%s retrain=%s",
        model_name,
        psi or 0,
        ks or 0,
        rate_shift,
        drift_level,
        requires_retraining,
    )

    return {
        "model_name":            model_name,
        "drift_level":           drift_level,
        "requires_retraining":   requires_retraining,
        "sufficient_data":       sufficient,
        "psi":                   psi,
        "ks_statistic":          ks,
        "ks_pvalue":             ksp,
        "ks_significant":        ks_result.get("significant"),
        "reference_anomaly_rate": round(reference_anomaly_rate, 4),
        "current_anomaly_rate":   round(current_anomaly_rate, 4),
        "rate_shift":            round(rate_shift, 4),
        "n_reference":           len(ref_scores),
        "n_evaluation":          len(eval_scores),
        "drift_log_id":          drift_log.id,
        "thresholds": {
            "PSI_NONE": PSI_NONE,
            "PSI_MINOR": PSI_MINOR,
            "PSI_MODERATE": PSI_MODERATE,
        },
        "interpretation": _interpret_drift(drift_level, psi, rate_shift, sufficient),
    }


async def get_drift_history(db: AsyncSession, limit: int = 30) -> List[Dict[str, Any]]:
    """Last N drift detection results."""
    rows = (await db.execute(
        select(ModelDriftLog)
        .order_by(desc(ModelDriftLog.detected_at))
        .limit(limit)
    )).scalars().all()

    return [
        {
            "id":                   r.id,
            "model_name":           r.model_name,
            "drift_level":          r.drift_level,
            "requires_retraining":  r.requires_retraining,
            "retrained":            r.retrained,
            "psi_score":            r.psi_score,
            "ks_statistic":         r.ks_statistic,
            "reference_rate":       r.reference_anomaly_rate,
            "current_rate":         r.current_anomaly_rate,
            "drift_magnitude":      r.drift_magnitude,
            "n_reference":          r.n_reference_samples,
            "n_evaluation":         r.n_evaluation_samples,
            "detected_at":          r.detected_at.isoformat() if r.detected_at else None,
        }
        for r in rows
    ]


def _interpret_drift(level: str, psi: Optional[float], rate_shift: float, sufficient: bool) -> str:
    if not sufficient:
        return (
            "Insufficient data for statistical drift testing. "
            "Accumulate at least 30 reference samples and 10 evaluation samples."
        )
    if level == "NONE":
        return "Model distribution is stable. No action required."
    elif level == "MINOR":
        return (
            f"Minor drift detected (PSI={psi:.3f}). "
            "Monitor closely. Anomaly rate shifted by "
            f"{rate_shift:+.1%}. Schedule retrain within 30 days."
        )
    elif level == "MODERATE":
        return (
            f"Moderate drift detected (PSI={psi:.3f}). "
            f"Anomaly rate shifted by {rate_shift:+.1%}. "
            "Retrain recommended within 7 days."
        )
    else:  # SEVERE
        return (
            f"SEVERE drift detected (PSI={psi:.3f}). "
            f"Anomaly rate shifted by {rate_shift:+.1%}. "
            "Immediate model retrain required. Current predictions may be unreliable."
        )


# Singleton
drift_engine = DriftDetectionEngine()
