"""
Risk Classification Engine — UrjaRakshak v2.2
==============================================
Converts GHI + physics + anomaly data into actionable inspection priorities.

Output structure:
  priority  : CRITICAL / HIGH / MEDIUM / LOW / INFORMATIONAL
  category  : INFRASTRUCTURE / METER / OPERATIONAL / MEASUREMENT / NORMAL
  actions   : List of specific recommended engineering actions
  urgency   : Timeframe for action (e.g. "Within 72 hours")

Ethics contract:
  - No individual-level attribution
  - All outputs are infrastructure-scoped
  - Uncertainty is always quantified
  - Conservative framing by default

Author: Vipin Baniya
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum

logger = logging.getLogger(__name__)


class InspectionPriority(Enum):
    CRITICAL       = "CRITICAL"        # Immediate action — GHI < 30 or residual > 12%
    HIGH           = "HIGH"            # Within 72 hours — GHI 30–49 or residual 8–12%
    MEDIUM         = "MEDIUM"          # Within 30 days — GHI 50–69 or residual 3–8%
    LOW            = "LOW"             # Routine monitoring — GHI 70–89
    INFORMATIONAL  = "INFORMATIONAL"   # No action required — GHI ≥ 90


class InspectionCategory(Enum):
    INFRASTRUCTURE  = "INFRASTRUCTURE"   # Physical component degradation
    METER           = "METER"            # Measurement equipment issue
    OPERATIONAL     = "OPERATIONAL"      # Load/capacity mismatch
    MEASUREMENT     = "MEASUREMENT"      # Data quality issue
    NORMAL          = "NORMAL"           # Within expected parameters


# ── Recommended action library ────────────────────────────────────────────

_ACTIONS: Dict[str, List[str]] = {
    "transformer_check": [
        "Physical inspection of transformer insulation and cooling system",
        "Measure core temperature under load",
        "Test no-load and full-load losses against nameplate values",
    ],
    "line_check": [
        "Thermal imaging scan of overhead/underground lines",
        "Measure resistance on suspect feeders",
        "Check joint and termination connections for oxidation",
    ],
    "meter_calibration": [
        "Retrieve and bench-test suspect meters",
        "Cross-verify with portable reference meter",
        "Check for tampering signs on meter enclosures",
    ],
    "load_audit": [
        "Reconcile feeder load schedules with measured output",
        "Verify demand factor assumptions",
        "Review reactive power compensation settings",
    ],
    "data_quality": [
        "Investigate gaps in SCADA/AMI data feed",
        "Verify meter communication link health",
        "Review timestamp synchronisation across meters",
    ],
    "monitoring": [
        "Increase monitoring frequency to 15-minute intervals",
        "Set residual alert threshold at 3%",
        "Document baseline for trend comparison",
    ],
    "operational": [
        "Review load balancing across feeders",
        "Check capacitor bank operation",
        "Verify protection relay settings",
    ],
}


# ── Output dataclass ──────────────────────────────────────────────────────

@dataclass
class RiskAssessment:
    priority:           InspectionPriority
    category:           InspectionCategory
    urgency:            str                      # Human-readable timeframe
    recommended_actions: List[str]
    reasoning:          str                      # Concise explanation (no accusation)
    confidence:         float                    # 0.0–1.0 confidence in this assessment
    requires_human_review: bool
    ethics_note:        str = (
        "This assessment is infrastructure-scoped. No individual attribution is made. "
        "Human review is required before any operational action."
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "priority":             self.priority.value,
            "category":             self.category.value,
            "urgency":              self.urgency,
            "recommended_actions":  self.recommended_actions,
            "reasoning":            self.reasoning,
            "confidence":           round(self.confidence, 3),
            "requires_human_review": self.requires_human_review,
            "ethics_note":          self.ethics_note,
        }


# ── Classifier ────────────────────────────────────────────────────────────

class RiskClassifier:
    """
    Converts GHI, physics results, and anomaly data into an inspection priority
    with specific engineering recommendations.

    Decision rules are deterministic and explainable — no black-box logic.
    """

    def classify(
        self,
        ghi: float,
        ghi_classification: str,
        residual_pct: float,
        anomaly_rate: float,
        confidence: float,
        pbs: float,
        trend_increasing: bool = False,
        measurement_quality: str = "medium",
    ) -> RiskAssessment:
        """
        Classify inspection priority from GHI and raw metrics.

        Parameters
        ----------
        ghi                : Grid Health Index (0–100)
        ghi_classification : One of HEALTHY/STABLE/DEGRADED/CRITICAL/SEVERE
        residual_pct       : Unexplained residual as percent of input energy
        anomaly_rate       : Fraction of readings flagged as anomalous
        confidence         : Physics engine confidence score
        pbs                : Physics Balance Score from GHI (0–1)
        trend_increasing   : Whether residual is trending upward
        measurement_quality: "high" | "medium" | "low"
        """
        priority, urgency = self._determine_priority(
            ghi, residual_pct, anomaly_rate, trend_increasing
        )
        category = self._determine_category(
            residual_pct, anomaly_rate, confidence, measurement_quality
        )
        actions = self._select_actions(priority, category, residual_pct, anomaly_rate)
        reasoning = self._build_reasoning(
            priority, ghi, residual_pct, anomaly_rate, confidence, trend_increasing
        )

        # Confidence in the risk assessment itself
        assess_confidence = self._assessment_confidence(confidence, measurement_quality)

        return RiskAssessment(
            priority=priority,
            category=category,
            urgency=urgency,
            recommended_actions=actions,
            reasoning=reasoning,
            confidence=assess_confidence,
            requires_human_review=(priority in (
                InspectionPriority.CRITICAL,
                InspectionPriority.HIGH,
                InspectionPriority.MEDIUM,
            )),
        )

    @staticmethod
    def _determine_priority(
        ghi: float,
        residual_pct: float,
        anomaly_rate: float,
        trend_increasing: bool,
    ) -> tuple[InspectionPriority, str]:
        """Deterministic priority mapping from GHI and raw signals."""

        # Hard overrides — physics trumps GHI
        if residual_pct > 12.0 or ghi < 30:
            return InspectionPriority.CRITICAL, "Immediate — within 24 hours"

        if residual_pct > 8.0 or ghi < 50:
            return InspectionPriority.HIGH, "Within 72 hours"

        if residual_pct > 3.0 or ghi < 70:
            # Upgrade to HIGH if trend is worsening
            if trend_increasing and residual_pct > 5.0:
                return InspectionPriority.HIGH, "Within 72 hours (trend worsening)"
            return InspectionPriority.MEDIUM, "Within 30 days"

        if residual_pct > 1.5 or anomaly_rate > 0.03:
            return InspectionPriority.LOW, "Routine monitoring — next scheduled cycle"

        return InspectionPriority.INFORMATIONAL, "No action required"

    @staticmethod
    def _determine_category(
        residual_pct: float,
        anomaly_rate: float,
        confidence: float,
        measurement_quality: str,
    ) -> InspectionCategory:
        """
        Determine the most likely category of issue.
        Uses Occam's Razor: technical causes first, then measurement, then behaviour.
        """
        if measurement_quality == "low" or confidence < 0.5:
            return InspectionCategory.MEASUREMENT

        if residual_pct > 5.0 and anomaly_rate < 0.05:
            # Large residual but low anomaly rate → physical component issue
            return InspectionCategory.INFRASTRUCTURE

        if anomaly_rate > 0.10:
            # High anomaly rate → could be meter issue
            return InspectionCategory.METER

        if residual_pct > 3.0:
            return InspectionCategory.OPERATIONAL

        return InspectionCategory.NORMAL

    @staticmethod
    def _select_actions(
        priority: InspectionPriority,
        category: InspectionCategory,
        residual_pct: float,
        anomaly_rate: float,
    ) -> List[str]:
        """Select relevant action items based on priority and category."""
        actions: List[str] = []

        if priority == InspectionPriority.INFORMATIONAL:
            actions.extend(_ACTIONS["monitoring"][:1])
            return actions

        if category == InspectionCategory.INFRASTRUCTURE:
            if residual_pct > 5.0:
                actions.extend(_ACTIONS["transformer_check"])
            actions.extend(_ACTIONS["line_check"][:2])

        elif category == InspectionCategory.METER:
            actions.extend(_ACTIONS["meter_calibration"])

        elif category == InspectionCategory.OPERATIONAL:
            actions.extend(_ACTIONS["load_audit"])
            actions.extend(_ACTIONS["operational"][:2])

        elif category == InspectionCategory.MEASUREMENT:
            actions.extend(_ACTIONS["data_quality"])

        # Always add monitoring for MEDIUM+
        if priority in (InspectionPriority.CRITICAL, InspectionPriority.HIGH):
            actions.append("Escalate to senior grid engineer before proceeding")
        elif priority == InspectionPriority.MEDIUM:
            actions.extend(_ACTIONS["monitoring"][:2])

        # Deduplicate preserving order
        seen = set()
        return [a for a in actions if not (a in seen or seen.add(a))]

    @staticmethod
    def _build_reasoning(
        priority: InspectionPriority,
        ghi: float,
        residual_pct: float,
        anomaly_rate: float,
        confidence: float,
        trend_increasing: bool,
    ) -> str:
        """Build a concise, non-accusatory reasoning string."""
        parts = [
            f"GHI {ghi:.1f} ({priority.value}).",
            f"Residual {residual_pct:.2f}% of input energy is unexplained by technical losses.",
        ]
        if anomaly_rate > 0:
            parts.append(f"Anomaly detection flagged {anomaly_rate*100:.1f}% of readings.")
        if trend_increasing:
            parts.append("Residual trend is increasing — early degradation signal.")
        parts.append(
            f"Physics engine confidence: {confidence*100:.0f}%. "
            "Infrastructure-level inspection is recommended."
        )
        return " ".join(parts)

    @staticmethod
    def _assessment_confidence(confidence: float, measurement_quality: str) -> float:
        quality_factor = {"high": 1.0, "medium": 0.85, "low": 0.65}.get(
            measurement_quality, 0.75
        )
        return round(confidence * quality_factor, 3)


# ── Singleton ─────────────────────────────────────────────────────────────
risk_classifier = RiskClassifier()
