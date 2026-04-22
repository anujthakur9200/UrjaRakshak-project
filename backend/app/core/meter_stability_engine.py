"""
Per-Meter Stability Engine — UrjaRakshak v2.3
==============================================
Computes rolling stability score per meter from its historical readings.

Why this matters:
  Batch-level anomaly detection treats all meters the same.
  Per-meter scoring identifies which specific meters are consistently
  unstable vs which are having a one-off spike — completely different
  engineering responses.

Mathematics:
  stability_score = w1·CV_score + w2·trend_score + w3·anomaly_rate_score

  Where:
    CV_score        = 1 / (1 + CV)          CV = std/mean (coefficient of variation)
    trend_score     = 1 / (1 + |slope|)     slope from linear regression
    anomaly_rate    = exp(-5 · anomaly_rate_30d)

  Weights: 0.50 / 0.25 / 0.25

Physics constraint:
  A meter is flagged as UNSTABLE if ANY reading is outside
  physics_lower = mean − 3σ  OR  physics_upper = mean + 3σ
  This is grounded in measurement uncertainty bounds from the
  physics engine, not pure statistics.

Author: Vipin Baniya
"""

import logging
import math
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func

from app.models.db_models import MeterReading, LiveMeterEvent, MeterStabilityScore

logger = logging.getLogger(__name__)

# Weights for composite stability score
W_CV      = 0.50
W_TREND   = 0.25
W_ANOMALY = 0.25

# Window for rolling computation
DEFAULT_WINDOW = 30  # readings


class MeterStabilityEngine:
    """
    Computes and persists per-meter stability scores.
    Called after each upload batch and after each live event ingest.
    """

    def compute_stability(
        self,
        readings: List[float],
        anomaly_flags: Optional[List[bool]] = None,
    ) -> Dict[str, Any]:
        """
        Core computation from a list of kWh readings.

        Parameters
        ----------
        readings      : List of energy readings in chronological order
        anomaly_flags : Optional boolean list same length as readings

        Returns dict with all stability metrics.
        """
        n = len(readings)
        if n < 2:
            return self._insufficient_data_result(n)

        # ── Basic statistics ───────────────────────────────────────────
        mean = sum(readings) / n
        variance = sum((r - mean) ** 2 for r in readings) / n
        std = math.sqrt(variance)

        cv = std / mean if mean > 0 else 1.0   # coefficient of variation

        # Percentile bands (p5, p95)
        sorted_vals = sorted(readings)
        p5_idx  = max(0, int(0.05 * n) - 1)
        p95_idx = min(n - 1, int(0.95 * n))
        p5  = sorted_vals[p5_idx]
        p95 = sorted_vals[p95_idx]

        # ── Linear trend (slope) ───────────────────────────────────────
        slope = self._linear_slope(readings)
        trend_dir = "UP" if slope > 0.05 else ("DOWN" if slope < -0.05 else "FLAT")

        # ── Anomaly rate ───────────────────────────────────────────────
        if anomaly_flags and len(anomaly_flags) == n:
            anomaly_rate = sum(1 for f in anomaly_flags if f) / n
        else:
            # Physics-based: count readings outside mean ± 3σ
            anomaly_rate = sum(
                1 for r in readings if abs(r - mean) > 3 * std
            ) / n if std > 0 else 0.0

        # ── Composite stability score ──────────────────────────────────
        cv_score     = 1.0 / (1.0 + cv)
        trend_score  = 1.0 / (1.0 + abs(slope) / max(mean, 1e-9))
        anomaly_score_comp = math.exp(-5.0 * anomaly_rate)

        stability_score = (
            W_CV      * cv_score +
            W_TREND   * trend_score +
            W_ANOMALY * anomaly_score_comp
        )
        stability_score = max(0.0, min(1.0, stability_score))

        return {
            "window_size":       n,
            "rolling_mean_kwh":  round(mean, 4),
            "rolling_std_kwh":   round(std, 4),
            "rolling_cv":        round(cv, 4),
            "stability_score":   round(stability_score, 4),
            "trend_slope":       round(slope, 6),
            "trend_direction":   trend_dir,
            "anomaly_rate_30d":  round(anomaly_rate, 4),
            "p5_kwh":            round(p5, 4),
            "p95_kwh":           round(p95, 4),
            "physics_lower_3s":  round(mean - 3 * std, 4),
            "physics_upper_3s":  round(mean + 3 * std, 4),
            # Subscores for explainability
            "subscores": {
                "cv_score":      round(cv_score, 4),
                "trend_score":   round(trend_score, 4),
                "anomaly_score": round(anomaly_score_comp, 4),
            },
            "weights": {"CV": W_CV, "TREND": W_TREND, "ANOMALY": W_ANOMALY},
        }

    def classify_z_score(self, value: float, mean: float, std: float) -> Tuple[float, bool]:
        """
        Compute z-score and physics-constrained anomaly flag.

        Returns: (z_score, is_physics_anomaly)
        Physics constraint: anomaly only if |z| > 3.0 AND std > 0
        """
        if std < 1e-9:
            return 0.0, False
        z = (value - mean) / std
        is_anomaly = abs(z) > 3.0
        return round(z, 3), is_anomaly

    @staticmethod
    def _linear_slope(values: List[float]) -> float:
        """Least-squares linear regression slope."""
        n = len(values)
        if n < 2:
            return 0.0
        mean_i = (n - 1) / 2
        mean_v = sum(values) / n
        num = sum((i - mean_i) * (values[i] - mean_v) for i in range(n))
        den = sum((i - mean_i) ** 2 for i in range(n))
        return num / den if abs(den) > 1e-12 else 0.0

    @staticmethod
    def _insufficient_data_result(n: int) -> Dict[str, Any]:
        return {
            "window_size": n,
            "stability_score": None,
            "note": f"Insufficient data ({n} readings). Need at least 2.",
            "rolling_mean_kwh": None, "rolling_std_kwh": None,
            "rolling_cv": None, "trend_slope": None,
            "trend_direction": "UNKNOWN", "anomaly_rate_30d": None,
            "p5_kwh": None, "p95_kwh": None,
        }


# ── DB persistence ────────────────────────────────────────────────────────

async def update_meter_stability(
    *,
    meter_id: str,
    substation_id: str,
    db: AsyncSession,
    org_id: Optional[str] = None,
    window: int = DEFAULT_WINDOW,
) -> Optional[Dict[str, Any]]:
    """
    Load the last `window` readings for a meter, compute stability,
    and upsert the MeterStabilityScore record.
    """
    engine = MeterStabilityEngine()

    # Load readings from both upload batches and live events
    batch_rows = (await db.execute(
        select(MeterReading.energy_kwh, MeterReading.is_anomaly, MeterReading.timestamp)
        .where(MeterReading.meter_id == meter_id)
        .where(MeterReading.substation_id == substation_id)
        .order_by(desc(MeterReading.timestamp))
        .limit(window)
    )).fetchall()

    live_rows = (await db.execute(
        select(LiveMeterEvent.energy_kwh, LiveMeterEvent.is_anomaly, LiveMeterEvent.event_ts)
        .where(LiveMeterEvent.meter_id == meter_id)
        .where(LiveMeterEvent.substation_id == substation_id)
        .order_by(desc(LiveMeterEvent.event_ts))
        .limit(window)
    )).fetchall()

    # Combine and sort chronologically
    all_rows = sorted(
        list(batch_rows) + list(live_rows),
        key=lambda r: r[2],
    )[-window:]

    if len(all_rows) < 2:
        return None

    readings      = [float(r[0]) for r in all_rows]
    anomaly_flags = [bool(r[1]) for r in all_rows]
    last_ts       = all_rows[-1][2]
    last_kwh      = all_rows[-1][0]

    metrics = engine.compute_stability(readings, anomaly_flags)

    # Upsert
    existing = (await db.execute(
        select(MeterStabilityScore)
        .where(MeterStabilityScore.meter_id == meter_id)
        .where(MeterStabilityScore.substation_id == substation_id)
    )).scalar_one_or_none()

    if existing:
        existing.window_size       = metrics["window_size"]
        existing.rolling_mean_kwh  = metrics["rolling_mean_kwh"]
        existing.rolling_std_kwh   = metrics["rolling_std_kwh"]
        existing.rolling_cv        = metrics["rolling_cv"]
        existing.stability_score   = metrics["stability_score"]
        existing.trend_slope       = metrics["trend_slope"]
        existing.trend_direction   = metrics["trend_direction"]
        existing.anomaly_rate_30d  = metrics["anomaly_rate_30d"]
        existing.p95_kwh           = metrics["p95_kwh"]
        existing.p5_kwh            = metrics["p5_kwh"]
        existing.total_readings    = len(all_rows)
        existing.last_reading_kwh  = float(last_kwh)
        existing.last_reading_ts   = last_ts
        existing.computed_at       = datetime.utcnow()
        if org_id:
            existing.org_id = org_id
    else:
        rec = MeterStabilityScore(
            org_id=org_id,
            meter_id=meter_id,
            substation_id=substation_id,
            window_size=metrics["window_size"],
            rolling_mean_kwh=metrics["rolling_mean_kwh"],
            rolling_std_kwh=metrics["rolling_std_kwh"],
            rolling_cv=metrics["rolling_cv"],
            stability_score=metrics["stability_score"],
            trend_slope=metrics["trend_slope"],
            trend_direction=metrics["trend_direction"],
            anomaly_rate_30d=metrics["anomaly_rate_30d"],
            p95_kwh=metrics["p95_kwh"],
            p5_kwh=metrics["p5_kwh"],
            total_readings=len(all_rows),
            last_reading_kwh=float(last_kwh),
            last_reading_ts=last_ts,
        )
        db.add(rec)

    await db.flush()
    return metrics


# ── Get stability summary for a substation ───────────────────────────────

async def get_substation_stability_summary(
    substation_id: str, db: AsyncSession
) -> Dict[str, Any]:
    """Return aggregated stability metrics across all meters in a substation."""
    rows = (await db.execute(
        select(MeterStabilityScore)
        .where(MeterStabilityScore.substation_id == substation_id)
    )).scalars().all()

    if not rows:
        return {"substation_id": substation_id, "meter_count": 0, "has_data": False}

    scores = [r.stability_score for r in rows if r.stability_score is not None]
    avg_score = round(sum(scores) / len(scores), 4) if scores else None

    unstable = [r for r in rows if r.stability_score is not None and r.stability_score < 0.5]
    trending_up = [r for r in rows if r.trend_direction == "UP"]

    return {
        "substation_id":       substation_id,
        "meter_count":         len(rows),
        "has_data":            True,
        "avg_stability_score": avg_score,
        "unstable_meters":     len(unstable),
        "trending_up_count":   len(trending_up),
        "meters": [
            {
                "meter_id":        r.meter_id,
                "stability_score": r.stability_score,
                "trend_direction": r.trend_direction,
                "anomaly_rate_30d": r.anomaly_rate_30d,
                "rolling_mean_kwh": r.rolling_mean_kwh,
                "last_reading_kwh": r.last_reading_kwh,
                "last_reading_ts":  r.last_reading_ts.isoformat() if r.last_reading_ts else None,
            }
            for r in sorted(rows, key=lambda x: (x.stability_score or 1.0))
        ],
    }


# Singleton
meter_stability_engine = MeterStabilityEngine()
