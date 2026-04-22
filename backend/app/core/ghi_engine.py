"""
Grid Health Index Engine (GHI) — UrjaRakshak v2.2
===================================================
Computes a physics-grounded composite health score (0–100)
for a grid section from five weighted subscores.

Mathematics:
  GHI = 0.35·PBS + 0.20·ASS + 0.15·CS + 0.15·TSS + 0.15·DIS   (scaled to 100)

Subscores:
  PBS — Physics Balance Score      (thermodynamic residual)
  ASS — Anomaly Stability Score    (exponential decay on anomaly rate)
  CS  — Confidence Score           (direct from physics engine)
  TSS — Trend Stability Score      (rolling residual volatility)
  DIS — Data Integrity Score       (missing / invalid reading ratio)

Classification:
  ≥ 90  → HEALTHY
  ≥ 70  → STABLE
  ≥ 50  → DEGRADED
  ≥ 30  → CRITICAL
   < 30  → SEVERE

Author: Vipin Baniya
"""

import math
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)

# ── Thresholds ────────────────────────────────────────────────────────────

# PBS — residual % thresholds
PBS_NORMAL_PCT  = 1.0   # ≤ 1 % → perfect
PBS_WARNING_PCT = 3.0   # 1–3 % → degrading
PBS_CRITICAL_PCT = 7.0  # 3–7 % → critical
# > 7 % → PBS = 0

# ASS — exponential decay constant
ASS_DECAY_K = 10.0  # exp(-10 × anomaly_rate)

# Classification buckets
GHI_HEALTHY   = 90
GHI_STABLE    = 70
GHI_DEGRADED  = 50
GHI_CRITICAL  = 30

# Component weights (must sum to 1.0)
WEIGHTS = {
    "PBS": 0.35,  # Physics most important
    "ASS": 0.20,
    "CS":  0.15,
    "TSS": 0.15,
    "DIS": 0.15,
}
assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9, "GHI weights must sum to 1.0"


# ── Input / Output dataclasses ─────────────────────────────────────────────

@dataclass
class GHIInputs:
    """
    All inputs required to compute a GHI snapshot.

    Parameters
    ----------
    residual_pct      : abs(actual_loss - expected_loss) / input_energy × 100
    anomaly_rate      : anomalies / total_readings  (fraction, not percent)
    confidence        : physics engine confidence score [0, 1]
    residual_history  : list of recent residual_pct values (for TSS)
    missing_ratio     : fraction of expected readings that are missing [0, 1]
    invalid_ratio     : fraction of readings that failed validation [0, 1]
    """
    residual_pct:     float
    anomaly_rate:     float         # 0.0–1.0
    confidence:       float         # 0.0–1.0
    residual_history: List[float]   # recent residual values (≥ 2 needed for TSS)
    missing_ratio:    float = 0.0   # 0.0–1.0
    invalid_ratio:    float = 0.0   # 0.0–1.0


@dataclass
class GHIComponents:
    """Individual subscore values — useful for debugging and UI display."""
    PBS: float   # Physics Balance Score
    ASS: float   # Anomaly Stability Score
    CS:  float   # Confidence Score
    TSS: float   # Trend Stability Score
    DIS: float   # Data Integrity Score

    def to_dict(self) -> Dict[str, float]:
        return {
            "PBS": round(self.PBS, 4),
            "ASS": round(self.ASS, 4),
            "CS":  round(self.CS, 4),
            "TSS": round(self.TSS, 4),
            "DIS": round(self.DIS, 4),
        }


@dataclass
class GHIResult:
    ghi: float                   # 0–100
    classification: str          # HEALTHY / STABLE / DEGRADED / CRITICAL / SEVERE
    components: GHIComponents
    interpretation: str          # One-line human-readable summary
    action_required: bool
    confidence_in_ghi: float     # How much we trust this GHI (based on data quality)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ghi": self.ghi,
            "classification": self.classification,
            "interpretation": self.interpretation,
            "action_required": self.action_required,
            "confidence_in_ghi": round(self.confidence_in_ghi, 3),
            "components": self.components.to_dict(),
            "weights": WEIGHTS,
            "thresholds": {
                "HEALTHY":  f">= {GHI_HEALTHY}",
                "STABLE":   f"{GHI_STABLE}–{GHI_HEALTHY}",
                "DEGRADED": f"{GHI_DEGRADED}–{GHI_STABLE}",
                "CRITICAL": f"{GHI_CRITICAL}–{GHI_DEGRADED}",
                "SEVERE":   f"< {GHI_CRITICAL}",
            },
        }


# ── Engine ─────────────────────────────────────────────────────────────────

class GridHealthEngine:
    """
    Computes the Grid Health Index (GHI) — a single executive-level metric
    summarising the integrity and reliability of a grid section.

    Designed to be:
      - Physics-weighted  (PBS carries 35 % of the score)
      - Noise-resistant   (smooth piecewise degradation, not step function)
      - Explainable       (every subscore has a clear formula)
      - Hard to game      (anomaly rate uses exponential penalty)
    """

    def compute(self, inputs: GHIInputs) -> GHIResult:
        """
        Main entry point. Computes all subscores and returns GHIResult.
        """
        # Clamp all inputs to valid ranges
        residual_pct = max(0.0, inputs.residual_pct)
        anomaly_rate = max(0.0, min(1.0, inputs.anomaly_rate))
        confidence   = max(0.0, min(1.0, inputs.confidence))
        missing      = max(0.0, min(1.0, inputs.missing_ratio))
        invalid      = max(0.0, min(1.0, inputs.invalid_ratio))

        # Compute subscores
        pbs = self._physics_balance_score(residual_pct)
        ass = self._anomaly_stability_score(anomaly_rate)
        cs  = confidence                             # direct normalised value
        tss = self._trend_stability_score(inputs.residual_history)
        dis = self._data_integrity_score(missing, invalid)

        comps = GHIComponents(PBS=pbs, ASS=ass, CS=cs, TSS=tss, DIS=dis)

        # Weighted sum → scale to 0–100
        raw = (
            WEIGHTS["PBS"] * pbs +
            WEIGHTS["ASS"] * ass +
            WEIGHTS["CS"]  * cs  +
            WEIGHTS["TSS"] * tss +
            WEIGHTS["DIS"] * dis
        )
        ghi = round(raw * 100.0, 2)
        ghi = max(0.0, min(100.0, ghi))  # safety clamp

        classification = self._classify(ghi)
        interpretation = self._interpret(ghi, classification, residual_pct, anomaly_rate)
        action_required = classification in ("CRITICAL", "SEVERE", "DEGRADED")

        # Confidence in GHI itself depends on data quality
        confidence_in_ghi = round((dis + cs) / 2.0, 3)

        result = GHIResult(
            ghi=ghi,
            classification=classification,
            components=comps,
            interpretation=interpretation,
            action_required=action_required,
            confidence_in_ghi=confidence_in_ghi,
        )

        logger.debug(
            "GHI computed: ghi=%.2f class=%s PBS=%.3f ASS=%.3f CS=%.3f TSS=%.3f DIS=%.3f",
            ghi, classification, pbs, ass, cs, tss, dis,
        )
        return result

    # ── Subscore formulas ─────────────────────────────────────────────────

    @staticmethod
    def _physics_balance_score(residual_pct: float) -> float:
        """
        Piecewise linear degradation on thermodynamic residual.

        residual ≤ 1 %       → PBS = 1.0   (perfect)
        1 % < residual ≤ 3 % → PBS ∈ [0.5, 1.0)   (linear decline)
        3 % < residual ≤ 7 % → PBS ∈ [0.0, 0.5)   (steeper decline)
        residual > 7 %       → PBS = 0.0   (severe)
        """
        r = residual_pct
        if r <= PBS_NORMAL_PCT:
            return 1.0
        elif r <= PBS_WARNING_PCT:
            return 1.0 - ((r - PBS_NORMAL_PCT) / (PBS_WARNING_PCT - PBS_NORMAL_PCT)) * 0.5
        elif r <= PBS_CRITICAL_PCT:
            return 0.5 - ((r - PBS_WARNING_PCT) / (PBS_CRITICAL_PCT - PBS_WARNING_PCT)) * 0.5
        else:
            return 0.0

    @staticmethod
    def _anomaly_stability_score(anomaly_rate: float) -> float:
        """
        Exponential penalty for anomaly frequency.
        ASS = exp(-10 × anomaly_rate)

        anomaly_rate = 0.00 → ASS = 1.000
        anomaly_rate = 0.05 → ASS = 0.607
        anomaly_rate = 0.10 → ASS = 0.368
        anomaly_rate = 0.20 → ASS = 0.135
        anomaly_rate = 0.50 → ASS ≈ 0.007
        """
        return math.exp(-ASS_DECAY_K * anomaly_rate)

    @staticmethod
    def _trend_stability_score(residual_history: List[float]) -> float:
        """
        Inverse of rolling residual volatility (std deviation).
        TSS = 1 / (1 + σ)   where σ = std(residual_history)

        More volatile → lower score.
        If < 2 data points available → returns 0.8 (neutral, not penalised for lack of data).
        """
        if len(residual_history) < 2:
            return 0.8  # neutral default — not enough history to penalise

        vals = [max(0.0, v) for v in residual_history]
        mean = sum(vals) / len(vals)
        variance = sum((v - mean) ** 2 for v in vals) / len(vals)
        std = math.sqrt(variance)
        return 1.0 / (1.0 + std)

    @staticmethod
    def _data_integrity_score(missing_ratio: float, invalid_ratio: float) -> float:
        """
        Penalises missing and invalid readings.
        DIS = 1 - (missing_ratio + invalid_ratio)  clamped to [0, 1]
        """
        return max(0.0, min(1.0, 1.0 - (missing_ratio + invalid_ratio)))

    @staticmethod
    def _classify(ghi: float) -> str:
        if ghi >= GHI_HEALTHY:  return "HEALTHY"
        if ghi >= GHI_STABLE:   return "STABLE"
        if ghi >= GHI_DEGRADED: return "DEGRADED"
        if ghi >= GHI_CRITICAL: return "CRITICAL"
        return "SEVERE"

    @staticmethod
    def _interpret(ghi: float, classification: str, residual_pct: float, anomaly_rate: float) -> str:
        """Generate a one-line human-readable interpretation."""
        anomaly_pct = round(anomaly_rate * 100, 1)
        base = f"GHI {ghi:.1f} — {classification}. "

        if classification == "HEALTHY":
            return base + f"Residual {residual_pct:.2f}%, anomaly rate {anomaly_pct}%. Normal operation."
        elif classification == "STABLE":
            return base + f"Residual {residual_pct:.2f}%, anomaly rate {anomaly_pct}%. Continue monitoring."
        elif classification == "DEGRADED":
            return base + (
                f"Residual {residual_pct:.2f}%, anomaly rate {anomaly_pct}%. "
                "Schedule infrastructure inspection within 30 days."
            )
        elif classification == "CRITICAL":
            return base + (
                f"Residual {residual_pct:.2f}%, anomaly rate {anomaly_pct}%. "
                "Priority inspection required within 72 hours."
            )
        else:  # SEVERE
            return base + (
                f"Residual {residual_pct:.2f}%, anomaly rate {anomaly_pct}%. "
                "Immediate inspection required. Integrity compromised."
            )


# ── Singleton ─────────────────────────────────────────────────────────────
ghi_engine = GridHealthEngine()
