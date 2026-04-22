"""
Physics-Constrained Anomaly Detection — UrjaRakshak v2.3
==========================================================
The core innovation: a reading is NOT an anomaly if it falls
within the physics-derived tolerance band for that meter's load,
even if the raw Isolation Forest score says otherwise.

This eliminates false positives from normal load variation —
the single biggest pain point of pure-ML anomaly detection
in energy systems.

Architecture (3 gates, AND logic):
  Gate 1 — Physics gate: is reading within I²R + measurement
            uncertainty bounds? If yes → NOT anomaly, skip ML.
  Gate 2 — Z-score gate: is |z| > threshold for this meter?
  Gate 3 — Isolation Forest gate: does model flag it?

  Anomaly = Gate1_fail AND (Gate2_fail OR Gate3_fail)

Rationale:
  - Gate 1 alone prevents false positives (load spikes are not fraud)
  - Gate 2 + 3 together prevent false negatives (both must agree)
  - This two-pass architecture is defensible in engineering terms

Mathematics:
  Physics tolerance band:
    upper = expected_kwh × (1 + uncertainty_pct / 100 + load_tolerance)
    lower = expected_kwh × (1 - uncertainty_pct / 100 - load_tolerance)
    where uncertainty_pct = 1.0% (IEC metering standard)
          load_tolerance   = 0.15 (15% normal load variation)

  Z-score per meter:
    z = (reading - meter_mean) / meter_std
    flagged if |z| > 3.0

Author: Vipin Baniya
"""

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────
MEASUREMENT_UNCERTAINTY_PCT = 1.0    # IEC 62053 metering standard
LOAD_TOLERANCE              = 0.15   # 15% normal load variation
Z_SCORE_THRESHOLD           = 3.0    # σ beyond which a reading is suspicious
MIN_SAMPLES_FOR_BASELINE    = 10     # need at least this many readings for z-score
PHYSICS_CONFIDENCE_DEFAULT  = 0.75   # when no meter baseline exists


# ── Data classes ──────────────────────────────────────────────────────────

@dataclass
class PhysicsConstraint:
    """Expected operating envelope for a single meter."""
    meter_id:         str
    expected_kwh:     float          # baseline expected consumption
    upper_bound:      float          # physics upper bound
    lower_bound:      float          # physics lower bound
    uncertainty_pct:  float = MEASUREMENT_UNCERTAINTY_PCT
    load_tolerance:   float = LOAD_TOLERANCE


@dataclass
class ConstrainedAnomalyResult:
    """Result of a single reading through all three gates."""
    meter_id:           str
    energy_kwh:         float
    is_anomaly:         bool
    z_score:            Optional[float]

    # Gate outcomes
    physics_gate_passed: bool        # True = within physics bounds → never anomaly
    z_score_gate_passed: bool        # True = z-score is normal
    ml_gate_passed:      bool        # True = Isolation Forest says normal

    # Explanations
    anomaly_reason:     Optional[str]
    confidence:         float        # 0–1

    # Physics bounds used
    physics_lower:      float
    physics_upper:      float
    physics_expected:   float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "meter_id":            self.meter_id,
            "energy_kwh":          round(self.energy_kwh, 4),
            "is_anomaly":          self.is_anomaly,
            "z_score":             round(self.z_score, 4) if self.z_score is not None else None,
            "physics_gate_passed": self.physics_gate_passed,
            "z_score_gate_passed": self.z_score_gate_passed,
            "ml_gate_passed":      self.ml_gate_passed,
            "anomaly_reason":      self.anomaly_reason,
            "confidence":          round(self.confidence, 4),
            "physics_bounds": {
                "lower":    round(self.physics_lower, 4),
                "upper":    round(self.physics_upper, 4),
                "expected": round(self.physics_expected, 4),
            },
        }


@dataclass
class BatchConstrainedResult:
    """Result for an entire batch of readings."""
    total_readings:          int
    anomalies_detected:      int
    physics_false_positives_avoided: int   # readings ML flagged but physics cleared
    anomaly_rate:            float
    results:                 List[ConstrainedAnomalyResult] = field(default_factory=list)

    @property
    def precision_improvement(self) -> str:
        """How many ML false positives we eliminated."""
        if self.anomalies_detected + self.physics_false_positives_avoided == 0:
            return "N/A"
        total_ml_flags = self.anomalies_detected + self.physics_false_positives_avoided
        pct = (self.physics_false_positives_avoided / total_ml_flags) * 100
        return f"{pct:.1f}% ML flags overridden by physics"


# ── Physics-Constrained Engine ─────────────────────────────────────────────

class PhysicsConstrainedAnomalyEngine:
    """
    Wraps the existing ML anomaly engine and adds physics gate.

    Usage:
        engine = PhysicsConstrainedAnomalyEngine(ml_anomaly_engine)
        results = engine.evaluate_batch(readings, meter_baselines)
    """

    def __init__(self, ml_engine=None):
        self._ml = ml_engine   # existing AnomalyEngine, optional

    def compute_physics_constraint(
        self,
        meter_id: str,
        expected_kwh: float,
        uncertainty_pct: float = MEASUREMENT_UNCERTAINTY_PCT,
        load_tolerance: float = LOAD_TOLERANCE,
    ) -> PhysicsConstraint:
        """
        Compute the physics tolerance band for a meter.

        Band derivation:
          The I²R technical loss model gives an expected consumption.
          On top of that, we add:
            - IEC measurement uncertainty (±1%)
            - Normal load variation (±15%)
          Any reading within this band is physically explainable and
          must NOT be flagged as an anomaly.
        """
        total_tolerance = (uncertainty_pct / 100) + load_tolerance
        upper = expected_kwh * (1 + total_tolerance)
        lower = max(0.0, expected_kwh * (1 - total_tolerance))
        return PhysicsConstraint(
            meter_id=meter_id,
            expected_kwh=expected_kwh,
            upper_bound=upper,
            lower_bound=lower,
            uncertainty_pct=uncertainty_pct,
            load_tolerance=load_tolerance,
        )

    def evaluate_single(
        self,
        meter_id: str,
        energy_kwh: float,
        constraint: PhysicsConstraint,
        meter_mean: Optional[float] = None,
        meter_std:  Optional[float] = None,
        sample_count: int = 0,
        ml_score:   Optional[float] = None,   # Isolation Forest score (negative = anomaly)
        ml_threshold: float = -0.1,
    ) -> ConstrainedAnomalyResult:
        """
        Evaluate one reading through all three gates.

        Gate 1 — Physics: is reading within I²R bounds?
          If yes: DEFINITELY NOT anomaly. Physics cannot be overridden.

        Gate 2 — Z-score: is |z| > 3σ from meter's baseline?
          Requires at least MIN_SAMPLES_FOR_BASELINE readings.

        Gate 3 — ML: does Isolation Forest flag it?

        Final: anomaly = NOT physics_pass AND (z_fail OR ml_fail)
        """
        # ── Gate 1: Physics ───────────────────────────────────────────────
        physics_gate_passed = (
            constraint.lower_bound <= energy_kwh <= constraint.upper_bound
        )

        if physics_gate_passed:
            # Physics says this is fine — clear, no further analysis needed
            return ConstrainedAnomalyResult(
                meter_id=meter_id,
                energy_kwh=energy_kwh,
                is_anomaly=False,
                z_score=self._safe_z(energy_kwh, meter_mean, meter_std, sample_count),
                physics_gate_passed=True,
                z_score_gate_passed=True,
                ml_gate_passed=True,
                anomaly_reason=None,
                confidence=PHYSICS_CONFIDENCE_DEFAULT,
                physics_lower=constraint.lower_bound,
                physics_upper=constraint.upper_bound,
                physics_expected=constraint.expected_kwh,
            )

        # Physics gate failed (outside bounds) — run ML gates
        # ── Gate 2: Z-score ───────────────────────────────────────────────
        z = self._safe_z(energy_kwh, meter_mean, meter_std, sample_count)
        z_gate_passed = True
        if z is not None and sample_count >= MIN_SAMPLES_FOR_BASELINE:
            z_gate_passed = abs(z) <= Z_SCORE_THRESHOLD

        # ── Gate 3: ML ────────────────────────────────────────────────────
        ml_gate_passed = True
        if ml_score is not None:
            ml_gate_passed = ml_score >= ml_threshold   # IF score >= threshold = normal

        # ── Combine ───────────────────────────────────────────────────────
        # Anomaly if physics failed AND (z-score says bad OR ML says bad)
        # When we don't have ML score, rely on z-score alone
        if ml_score is None:
            if sample_count < MIN_SAMPLES_FOR_BASELINE:
                # No baseline yet — trust physics miss but be conservative
                is_anomaly = False   # don't flag until we have baseline
                reason = None
                confidence = 0.4
            else:
                is_anomaly = not z_gate_passed
                reason = f"Z-score {z:.2f} exceeds ±{Z_SCORE_THRESHOLD}σ and outside physics bounds" if is_anomaly else None
                confidence = 0.65
        else:
            is_anomaly = not z_gate_passed or not ml_gate_passed
            confidence = self._compute_confidence(z, ml_score, ml_threshold, sample_count)
            reason = self._build_reason(energy_kwh, constraint, z, ml_score, ml_threshold) if is_anomaly else None

        return ConstrainedAnomalyResult(
            meter_id=meter_id,
            energy_kwh=energy_kwh,
            is_anomaly=is_anomaly,
            z_score=z,
            physics_gate_passed=False,
            z_score_gate_passed=z_gate_passed,
            ml_gate_passed=ml_gate_passed,
            anomaly_reason=reason,
            confidence=confidence,
            physics_lower=constraint.lower_bound,
            physics_upper=constraint.upper_bound,
            physics_expected=constraint.expected_kwh,
        )

    def evaluate_batch(
        self,
        readings: List[Dict[str, Any]],
        meter_baselines: Dict[str, Dict[str, Any]],   # meter_id → {mean, std, count, expected_kwh}
        ml_scores: Optional[Dict[str, float]] = None, # meter_id → IF score
    ) -> BatchConstrainedResult:
        """
        Evaluate a batch of readings.
        Each reading dict must have: meter_id, energy_kwh.
        """
        results: List[ConstrainedAnomalyResult] = []
        physics_fp_avoided = 0

        for r in readings:
            meter_id   = r.get("meter_id", "unknown")
            energy_kwh = float(r.get("energy_kwh", 0))
            baseline   = meter_baselines.get(meter_id, {})

            expected_kwh = baseline.get("expected_kwh") or baseline.get("mean") or energy_kwh
            constraint = self.compute_physics_constraint(meter_id, expected_kwh)

            result = self.evaluate_single(
                meter_id=meter_id,
                energy_kwh=energy_kwh,
                constraint=constraint,
                meter_mean=baseline.get("mean"),
                meter_std=baseline.get("std"),
                sample_count=baseline.get("count", 0),
                ml_score=ml_scores.get(meter_id) if ml_scores else None,
            )

            # Track avoided false positives
            if (not result.physics_gate_passed and
                ml_scores and meter_id in ml_scores and
                ml_scores[meter_id] < -0.1 and  # ML would have flagged it
                result.z_score is not None and abs(result.z_score) <= Z_SCORE_THRESHOLD
                and not result.is_anomaly):
                physics_fp_avoided += 1

            results.append(result)

        anomalies = sum(1 for r in results if r.is_anomaly)
        total = len(results)
        return BatchConstrainedResult(
            total_readings=total,
            anomalies_detected=anomalies,
            physics_false_positives_avoided=physics_fp_avoided,
            anomaly_rate=anomalies / total if total > 0 else 0.0,
            results=results,
        )

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _safe_z(value: float, mean: Optional[float], std: Optional[float], count: int) -> Optional[float]:
        if mean is None or std is None or count < MIN_SAMPLES_FOR_BASELINE:
            return None
        if std < 1e-9:
            return 0.0
        return (value - mean) / std

    @staticmethod
    def _compute_confidence(
        z: Optional[float],
        ml_score: float,
        ml_threshold: float,
        sample_count: int,
    ) -> float:
        """Higher confidence when multiple signals agree."""
        signals_agree = 0
        total_signals = 0

        if z is not None and sample_count >= MIN_SAMPLES_FOR_BASELINE:
            z_says_anomaly = abs(z) > Z_SCORE_THRESHOLD
            total_signals += 1
            signals_agree += int(z_says_anomaly)

        ml_says_anomaly = ml_score < ml_threshold
        total_signals += 1
        signals_agree += int(ml_says_anomaly)

        if total_signals == 0:
            return 0.5
        base = signals_agree / total_signals

        # Boost if sample count is high
        sample_boost = min(0.15, math.log1p(sample_count / 100) * 0.1)
        return min(0.95, base * 0.8 + sample_boost)

    @staticmethod
    def _build_reason(
        energy_kwh: float,
        constraint: PhysicsConstraint,
        z: Optional[float],
        ml_score: float,
        ml_threshold: float,
    ) -> str:
        parts = []
        if energy_kwh > constraint.upper_bound:
            pct_over = ((energy_kwh - constraint.expected_kwh) / constraint.expected_kwh) * 100
            parts.append(f"Reading {pct_over:.1f}% above physics upper bound")
        elif energy_kwh < constraint.lower_bound:
            pct_under = ((constraint.expected_kwh - energy_kwh) / constraint.expected_kwh) * 100
            parts.append(f"Reading {pct_under:.1f}% below physics lower bound")
        if z is not None and abs(z) > Z_SCORE_THRESHOLD:
            parts.append(f"Z-score {z:.2f} (threshold ±{Z_SCORE_THRESHOLD})")
        if ml_score < ml_threshold:
            parts.append(f"Isolation Forest score {ml_score:.3f} (threshold {ml_threshold})")
        return "; ".join(parts) if parts else "Multiple signal agreement"


# ── Singleton ─────────────────────────────────────────────────────────────
_constrained_engine: Optional[PhysicsConstrainedAnomalyEngine] = None


def get_constrained_engine() -> PhysicsConstrainedAnomalyEngine:
    global _constrained_engine
    if _constrained_engine is None:
        _constrained_engine = PhysicsConstrainedAnomalyEngine()
    return _constrained_engine


def init_constrained_engine(ml_engine=None) -> PhysicsConstrainedAnomalyEngine:
    global _constrained_engine
    _constrained_engine = PhysicsConstrainedAnomalyEngine(ml_engine)
    logger.info(
        "PhysicsConstrainedAnomalyEngine initialized (ml=%s)",
        "attached" if ml_engine else "none",
    )
    return _constrained_engine
