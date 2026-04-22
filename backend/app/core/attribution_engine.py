"""
Loss Attribution Engine (LAE)
==============================
Identifies plausible causes of energy losses using multi-hypothesis analysis.

Core Principles:
- NEVER single-cause attribution
- Always probability-weighted outputs
- Avoid false precision
- Present alternative explanations
- Respect epistemic humility
"""

import numpy as np
from dataclasses import dataclass
from typing import List, Dict, Optional, Set
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class LossCause(Enum):
    """Categories of energy loss causes"""
    TECHNICAL_EXPECTED = "technical_expected"
    INFRASTRUCTURE_DEGRADATION = "infrastructure_degradation"
    OPERATIONAL_MISMATCH = "operational_mismatch"
    METER_MALFUNCTION = "meter_malfunction"
    TIMING_MISALIGNMENT = "timing_misalignment"
    LOAD_ESTIMATION_ERROR = "load_estimation_error"
    BEHAVIORAL_IRREGULARITY = "behavioral_irregularity"
    SUSPICIOUS_IMBALANCE = "suspicious_imbalance"
    UNKNOWN = "unknown"


@dataclass
class AttributionHypothesis:
    """Single hypothesis about loss cause"""
    cause: LossCause
    probability: float  # 0.0 to 1.0
    confidence: float  # 0.0 to 1.0
    supporting_evidence: List[str]
    contradicting_evidence: List[str]
    recommended_action: str
    
    def is_actionable(self) -> bool:
        """Determine if this hypothesis warrants action"""
        return self.probability > 0.3 and self.confidence > 0.6


@dataclass
class AttributionResult:
    """Result of multi-cause attribution analysis"""
    hypotheses: List[AttributionHypothesis]
    primary_causes: List[LossCause]
    secondary_causes: List[LossCause]
    residual_unexplained_percent: float
    analysis_quality: str  # "high", "medium", "low"
    requires_human_review: bool
    refusal_reason: Optional[str] = None
    
    def get_sorted_hypotheses(self) -> List[AttributionHypothesis]:
        """Return hypotheses sorted by probability × confidence"""
        return sorted(
            self.hypotheses,
            key=lambda h: h.probability * h.confidence,
            reverse=True
        )


class LossAttributionEngine:
    """
    Multi-hypothesis engine for attributing energy losses to probable causes.
    
    Design Philosophy:
    - Complex phenomena rarely have single causes
    - Multiple plausible explanations can coexist
    - Uncertainty increases with distance from measurement
    - Human judgment required for final decisions
    """
    
    # Thresholds for automated classification
    HIGH_CONFIDENCE_THRESHOLD = 0.7
    MEDIUM_CONFIDENCE_THRESHOLD = 0.5
    SIGNIFICANT_PROBABILITY_THRESHOLD = 0.3
    HUMAN_REVIEW_THRESHOLD = 0.4  # Multiple causes above this → human review
    
    def __init__(self, enable_conservative_mode: bool = True):
        """
        Initialize Loss Attribution Engine.
        
        Args:
            enable_conservative_mode: If True, require human review for ambiguous cases
        """
        self.conservative_mode = enable_conservative_mode
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
    def attribute_losses(
        self,
        residual_mwh: float,
        residual_percentage: float,
        confidence_score: float,
        grid_context: Dict,
        historical_patterns: Optional[Dict] = None
    ) -> AttributionResult:
        """
        Perform multi-hypothesis attribution of energy losses.
        
        Args:
            residual_mwh: Unexplained energy loss in MWh
            residual_percentage: Loss as percentage of input
            confidence_score: Confidence in measurements (0-1)
            grid_context: Dict with grid operational context
            historical_patterns: Optional historical data for pattern matching
            
        Returns:
            AttributionResult with multiple weighted hypotheses
        """
        self.logger.info(f"Attributing loss: {residual_mwh:.2f} MWh ({residual_percentage:.2f}%)")
        
        # Generate all plausible hypotheses
        hypotheses = self._generate_hypotheses(
            residual_mwh=residual_mwh,
            residual_percentage=residual_percentage,
            confidence_score=confidence_score,
            grid_context=grid_context,
            historical_patterns=historical_patterns
        )
        
        # Normalize probabilities to sum to 1.0
        total_prob = sum(h.probability for h in hypotheses)
        if total_prob > 0:
            for h in hypotheses:
                h.probability = h.probability / total_prob
        
        # Classify primary and secondary causes
        primary_causes = [
            h.cause for h in hypotheses
            if h.probability > self.SIGNIFICANT_PROBABILITY_THRESHOLD
        ]
        
        secondary_causes = [
            h.cause for h in hypotheses
            if 0.1 < h.probability <= self.SIGNIFICANT_PROBABILITY_THRESHOLD
        ]
        
        # Assess analysis quality
        analysis_quality = self._assess_analysis_quality(
            hypotheses=hypotheses,
            confidence_score=confidence_score
        )
        
        # Determine if human review is required
        requires_review = self._requires_human_review(
            hypotheses=hypotheses,
            residual_percentage=residual_percentage,
            analysis_quality=analysis_quality
        )
        
        # Check for refusal conditions
        refusal_reason = self._check_refusal_conditions(
            confidence_score=confidence_score,
            analysis_quality=analysis_quality,
            hypotheses=hypotheses
        )
        
        # Calculate unexplained residual
        explained_percent = sum(
            h.probability * 100 for h in hypotheses
            if h.cause != LossCause.UNKNOWN
        )
        unexplained_percent = 100 - explained_percent
        
        result = AttributionResult(
            hypotheses=hypotheses,
            primary_causes=primary_causes,
            secondary_causes=secondary_causes,
            residual_unexplained_percent=unexplained_percent,
            analysis_quality=analysis_quality,
            requires_human_review=requires_review,
            refusal_reason=refusal_reason
        )
        
        self.logger.info(f"Attribution complete: {len(primary_causes)} primary causes, "
                        f"{unexplained_percent:.1f}% unexplained, "
                        f"Human review: {requires_review}")
        
        return result
    
    def _generate_hypotheses(
        self,
        residual_mwh: float,
        residual_percentage: float,
        confidence_score: float,
        grid_context: Dict,
        historical_patterns: Optional[Dict]
    ) -> List[AttributionHypothesis]:
        """Generate all plausible hypotheses for the observed loss"""
        hypotheses = []
        
        # Hypothesis 1: Infrastructure Degradation
        hypotheses.append(self._assess_infrastructure_degradation(
            residual_mwh, residual_percentage, grid_context
        ))
        
        # Hypothesis 2: Meter Malfunction
        hypotheses.append(self._assess_meter_issues(
            residual_mwh, confidence_score, grid_context
        ))
        
        # Hypothesis 3: Timing Misalignment
        hypotheses.append(self._assess_timing_issues(
            residual_mwh, grid_context
        ))
        
        # Hypothesis 4: Operational Mismatch
        hypotheses.append(self._assess_operational_issues(
            residual_mwh, residual_percentage, grid_context
        ))
        
        # Hypothesis 5: Load Estimation Error
        hypotheses.append(self._assess_estimation_errors(
            residual_mwh, residual_percentage, grid_context
        ))
        
        # Hypothesis 6: Behavioral Irregularity
        hypotheses.append(self._assess_behavioral_patterns(
            residual_mwh, residual_percentage, grid_context, historical_patterns
        ))
        
        # Hypothesis 7: Suspicious Imbalance (only if other causes insufficient)
        hypotheses.append(self._assess_suspicious_patterns(
            residual_mwh, residual_percentage, grid_context, historical_patterns
        ))
        
        # Hypothesis 8: Unknown causes
        hypotheses.append(AttributionHypothesis(
            cause=LossCause.UNKNOWN,
            probability=0.1,  # Always reserve some probability for unknown
            confidence=0.3,
            supporting_evidence=["Residual not fully explained by known causes"],
            contradicting_evidence=[],
            recommended_action="Continue monitoring for pattern emergence"
        ))
        
        return hypotheses
    
    def _assess_infrastructure_degradation(
        self, residual_mwh: float, residual_percentage: float, grid_context: Dict
    ) -> AttributionHypothesis:
        """Assess likelihood of infrastructure aging/degradation"""
        evidence_for = []
        evidence_against = []
        probability = 0.2  # Base probability
        
        # Check component age
        avg_age = grid_context.get("average_component_age_years", 0)
        if avg_age > 20:
            probability += 0.3
            evidence_for.append(f"Average component age: {avg_age} years (>20)")
        elif avg_age > 15:
            probability += 0.15
            evidence_for.append(f"Average component age: {avg_age} years")
        else:
            evidence_against.append(f"Components relatively new ({avg_age} years)")
        
        # Check maintenance history
        maintenance_score = grid_context.get("maintenance_score", 1.0)
        if maintenance_score < 0.5:
            probability += 0.2
            evidence_for.append(f"Poor maintenance history (score: {maintenance_score:.2f})")
        
        # Check loss magnitude (degradation usually causes gradual increase)
        if 2 < residual_percentage < 6:
            probability += 0.1
            evidence_for.append("Loss magnitude consistent with degradation")
        elif residual_percentage > 10:
            evidence_against.append("Loss too high for typical degradation")
        
        # Confidence based on data availability
        confidence = 0.7 if avg_age > 0 else 0.4
        
        return AttributionHypothesis(
            cause=LossCause.INFRASTRUCTURE_DEGRADATION,
            probability=min(probability, 0.8),
            confidence=confidence,
            supporting_evidence=evidence_for,
            contradicting_evidence=evidence_against,
            recommended_action="Conduct infrastructure health assessment; prioritize aged components"
        )
    
    def _assess_meter_issues(
        self, residual_mwh: float, confidence_score: float, grid_context: Dict
    ) -> AttributionHypothesis:
        """Assess likelihood of meter malfunction or calibration drift"""
        evidence_for = []
        evidence_against = []
        probability = 0.15  # Base probability
        
        # Low confidence often indicates measurement issues
        if confidence_score < 0.6:
            probability += 0.25
            evidence_for.append(f"Low confidence score: {confidence_score:.2f}")
        else:
            evidence_against.append(f"High confidence in measurements ({confidence_score:.2f})")
        
        # Check last calibration date
        days_since_calibration = grid_context.get("days_since_last_calibration", 0)
        if days_since_calibration > 730:  # >2 years
            probability += 0.2
            evidence_for.append(f"Meters not calibrated in {days_since_calibration} days")
        
        # Sudden changes suggest meter issues
        if grid_context.get("loss_pattern") == "sudden_change":
            probability += 0.15
            evidence_for.append("Sudden change in loss pattern (consistent with meter failure)")
        
        confidence = 0.6 if days_since_calibration > 0 else 0.4
        
        return AttributionHypothesis(
            cause=LossCause.METER_MALFUNCTION,
            probability=min(probability, 0.7),
            confidence=confidence,
            supporting_evidence=evidence_for,
            contradicting_evidence=evidence_against,
            recommended_action="Schedule meter calibration; verify CT/PT ratios"
        )
    
    def _assess_timing_issues(
        self, residual_mwh: float, grid_context: Dict
    ) -> AttributionHypothesis:
        """Assess likelihood of time synchronization problems"""
        evidence_for = []
        evidence_against = []
        probability = 0.1
        
        # Check if timestamps are synchronized
        has_time_sync = grid_context.get("ntp_synchronized", False)
        if not has_time_sync:
            probability += 0.3
            evidence_for.append("Meters not NTP synchronized")
        else:
            evidence_against.append("Meters properly time-synchronized")
        
        # Small losses more likely timing-related
        residual_pct = abs(residual_mwh / grid_context.get("input_mwh", 1)) * 100
        if residual_pct < 2:
            probability += 0.15
            evidence_for.append(f"Small loss magnitude ({residual_pct:.1f}%) consistent with timing")
        
        confidence = 0.7 if "ntp_synchronized" in grid_context else 0.3
        
        return AttributionHypothesis(
            cause=LossCause.TIMING_MISALIGNMENT,
            probability=probability,
            confidence=confidence,
            supporting_evidence=evidence_for,
            contradicting_evidence=evidence_against,
            recommended_action="Verify NTP synchronization; check meter timestamp accuracy"
        )
    
    def _assess_operational_issues(
        self, residual_mwh: float, residual_percentage: float, grid_context: Dict
    ) -> AttributionHypothesis:
        """Assess operational mismatches (switching, load transfers, etc.)"""
        evidence_for = []
        evidence_against = []
        probability = 0.1
        
        # Check for recent switching operations
        if grid_context.get("recent_switching_operations", 0) > 0:
            probability += 0.25
            evidence_for.append("Recent switching operations in network")
        
        # Check for load transfer events
        if grid_context.get("load_transfer_events", 0) > 0:
            probability += 0.2
            evidence_for.append("Load transfer events during measurement period")
        
        confidence = 0.6
        
        return AttributionHypothesis(
            cause=LossCause.OPERATIONAL_MISMATCH,
            probability=probability,
            confidence=confidence,
            supporting_evidence=evidence_for,
            contradicting_evidence=evidence_against,
            recommended_action="Review operational logs; verify network topology data"
        )
    
    def _assess_estimation_errors(
        self, residual_mwh: float, residual_percentage: float, grid_context: Dict
    ) -> AttributionHypothesis:
        """Assess load estimation or billing errors"""
        evidence_for = []
        probability = 0.15
        
        # If many unmetered connections
        unmetered_fraction = grid_context.get("unmetered_load_fraction", 0)
        if unmetered_fraction > 0.1:
            probability += 0.2
            evidence_for.append(f"Significant unmetered load ({unmetered_fraction:.1%})")
        
        confidence = 0.5
        
        return AttributionHypothesis(
            cause=LossCause.LOAD_ESTIMATION_ERROR,
            probability=probability,
            confidence=confidence,
            supporting_evidence=evidence_for,
            contradicting_evidence=[],
            recommended_action="Review load estimation methodology; increase metering coverage"
        )
    
    def _assess_behavioral_patterns(
        self, 
        residual_mwh: float,
        residual_percentage: float,
        grid_context: Dict,
        historical_patterns: Optional[Dict]
    ) -> AttributionHypothesis:
        """Assess unusual behavioral patterns (non-malicious)"""
        evidence_for = []
        probability = 0.1
        confidence = 0.4
        
        if historical_patterns:
            # Check for seasonal patterns
            if historical_patterns.get("has_seasonal_pattern", False):
                evidence_for.append("Seasonal consumption pattern detected")
                probability += 0.1
        
        return AttributionHypothesis(
            cause=LossCause.BEHAVIORAL_IRREGULARITY,
            probability=probability,
            confidence=confidence,
            supporting_evidence=evidence_for,
            contradicting_evidence=[],
            recommended_action="Analyze consumption patterns; conduct customer surveys"
        )
    
    def _assess_suspicious_patterns(
        self,
        residual_mwh: float,
        residual_percentage: float,
        grid_context: Dict,
        historical_patterns: Optional[Dict]
    ) -> AttributionHypothesis:
        """
        Assess suspicious imbalances - ONLY after ruling out other causes.
        
        CRITICAL: This is NOT proof of theft. It indicates an unexplained
        imbalance that requires investigation.
        """
        evidence_for = []
        evidence_against = []
        probability = 0.05  # Start very low
        
        # Only consider if loss is significant
        if residual_percentage < 5:
            evidence_against.append("Loss too small to warrant investigation")
            return AttributionHypothesis(
                cause=LossCause.SUSPICIOUS_IMBALANCE,
                probability=0.05,
                confidence=0.3,
                supporting_evidence=[],
                contradicting_evidence=evidence_against,
                recommended_action="No action - below investigation threshold"
            )
        
        # Check for patterns consistent with intentional bypassing
        if historical_patterns:
            if historical_patterns.get("nocturnal_pattern", False):
                probability += 0.15
                evidence_for.append("Unusual nighttime energy imbalance pattern")
            
            if historical_patterns.get("consistent_daily_pattern", False):
                probability += 0.1
                evidence_for.append("Consistent daily imbalance pattern")
        
        # High unexplained loss after ruling out other causes
        if residual_percentage > 8:
            probability += 0.2
            evidence_for.append(f"High unexplained loss: {residual_percentage:.1f}%")
        
        # Always require human review for this category
        confidence = 0.4  # Deliberately low - requires investigation
        
        return AttributionHypothesis(
            cause=LossCause.SUSPICIOUS_IMBALANCE,
            probability=min(probability, 0.5),  # Cap at 50%
            confidence=confidence,
            supporting_evidence=evidence_for,
            contradicting_evidence=evidence_against,
            recommended_action=("Physical infrastructure inspection required; "
                              "verify metering integrity; check for unauthorized connections "
                              "(following due process)")
        )
    
    def _assess_analysis_quality(
        self, hypotheses: List[AttributionHypothesis], confidence_score: float
    ) -> str:
        """Assess overall quality of attribution analysis"""
        # Average confidence across hypotheses
        avg_confidence = np.mean([h.confidence for h in hypotheses])
        
        # Check for dominant hypothesis
        max_prob = max(h.probability for h in hypotheses)
        
        if avg_confidence > 0.7 and max_prob > 0.5:
            return "high"
        elif avg_confidence > 0.5:
            return "medium"
        else:
            return "low"
    
    def _requires_human_review(
        self,
        hypotheses: List[AttributionHypothesis],
        residual_percentage: float,
        analysis_quality: str
    ) -> bool:
        """Determine if human review is required"""
        # Always require review if multiple significant causes
        significant_causes = [
            h for h in hypotheses
            if h.probability > self.HUMAN_REVIEW_THRESHOLD
        ]
        if len(significant_causes) > 2:
            return True
        
        # Require review for high losses
        if residual_percentage > 7:
            return True
        
        # Require review for low quality analysis
        if analysis_quality == "low" and residual_percentage > 3:
            return True
        
        # Always review suspicious imbalances
        for h in hypotheses:
            if h.cause == LossCause.SUSPICIOUS_IMBALANCE and h.probability > 0.2:
                return True
        
        return False
    
    def _check_refusal_conditions(
        self,
        confidence_score: float,
        analysis_quality: str,
        hypotheses: List[AttributionHypothesis]
    ) -> Optional[str]:
        """Check if we should refuse to provide attribution"""
        if not self.conservative_mode:
            return None
        
        if confidence_score < 0.3:
            return "Measurement confidence too low for reliable attribution"
        
        if analysis_quality == "low" and max(h.probability for h in hypotheses) < 0.3:
            return "No dominant hypothesis; data insufficient for attribution"
        
        return None


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    lae = LossAttributionEngine(enable_conservative_mode=True)
    
    grid_context = {
        "average_component_age_years": 22,
        "maintenance_score": 0.6,
        "days_since_last_calibration": 900,
        "ntp_synchronized": True,
        "recent_switching_operations": 0,
        "unmetered_load_fraction": 0.05,
        "input_mwh": 1000
    }
    
    result = lae.attribute_losses(
        residual_mwh=60.0,
        residual_percentage=6.0,
        confidence_score=0.75,
        grid_context=grid_context
    )
    
    print("\n=== Attribution Result ===")
    print(f"Analysis Quality: {result.analysis_quality}")
    print(f"Requires Human Review: {result.requires_human_review}")
    print(f"Unexplained: {result.residual_unexplained_percent:.1f}%")
    
    print("\n=== Top Hypotheses ===")
    for h in result.get_sorted_hypotheses()[:3]:
        print(f"\n{h.cause.value}:")
        print(f"  Probability: {h.probability:.2%}")
        print(f"  Confidence: {h.confidence:.2f}")
        print(f"  Action: {h.recommended_action}")


# Alias for v2 compatibility (main.py imports AttributionEngine)
class AttributionEngine(LossAttributionEngine):
    """Alias for v2 compatibility — wraps LossAttributionEngine with v2 API."""
    def __init__(self, conservative_mode: bool = True):
        super().__init__(enable_conservative_mode=conservative_mode)
        self.conservative_mode = conservative_mode
        # Expose threshold for tests and introspection
        # Conservative mode = higher threshold to accuse (less likely to flag)
        self.conservative_threshold = 0.5 if conservative_mode else 0.3
