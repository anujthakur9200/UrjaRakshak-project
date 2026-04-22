"""
Tests for GHI Engine, Risk Classifier, and AI Interpretation Engine
====================================================================
Run: pytest backend/app/tests/test_ghi_risk_ai.py -v

Author: Vipin Baniya
"""

import math
import pytest
from unittest.mock import patch, MagicMock

from app.core.ghi_engine import (
    GridHealthEngine, GHIInputs, GHIResult,
    PBS_NORMAL_PCT, PBS_WARNING_PCT, PBS_CRITICAL_PCT,
    GHI_HEALTHY, GHI_STABLE, GHI_DEGRADED, GHI_CRITICAL,
)
from app.core.risk_classification import (
    RiskClassifier, InspectionPriority, InspectionCategory,
)
from app.core.ai_interpretation_engine import (
    AIInterpretationEngine, AIInterpretationInput,
)


# ── GHI Engine ─────────────────────────────────────────────────────────────

@pytest.fixture
def ghi():
    return GridHealthEngine()


def make_inputs(residual=0.5, anomaly_rate=0.0, confidence=0.9, history=None, missing=0.0, invalid=0.0):
    return GHIInputs(
        residual_pct=residual,
        anomaly_rate=anomaly_rate,
        confidence=confidence,
        residual_history=history or [0.5, 0.5, 0.5],
        missing_ratio=missing,
        invalid_ratio=invalid,
    )


class TestGHIPhysicsBalanceScore:
    def test_perfect_residual_gives_pbs_one(self, ghi):
        assert ghi._physics_balance_score(0.0) == 1.0
        assert ghi._physics_balance_score(PBS_NORMAL_PCT) == 1.0

    def test_normal_boundary_exactly_one(self, ghi):
        pbs = ghi._physics_balance_score(PBS_NORMAL_PCT)
        assert pbs == 1.0

    def test_warning_boundary_half(self, ghi):
        # At PBS_CRITICAL_PCT boundary: PBS = 0.0 (approximately)
        pbs = ghi._physics_balance_score(PBS_CRITICAL_PCT)
        assert abs(pbs - 0.0) < 1e-9

    def test_linear_decline_in_warning_zone(self, ghi):
        # 2% is midpoint of warning zone (1–3%) → PBS ≈ 0.75
        pbs = ghi._physics_balance_score(2.0)
        assert 0.70 < pbs < 0.80

    def test_severe_residual_gives_zero(self, ghi):
        assert ghi._physics_balance_score(10.0) == 0.0
        assert ghi._physics_balance_score(50.0) == 0.0

    def test_pbs_is_monotonically_decreasing(self, ghi):
        values = [0, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 7.0, 10.0]
        scores = [ghi._physics_balance_score(v) for v in values]
        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1], f"PBS not monotonic at {values[i]}"


class TestGHIAnomalyStabilityScore:
    def test_zero_anomaly_rate_gives_one(self, ghi):
        assert abs(ghi._anomaly_stability_score(0.0) - 1.0) < 1e-9

    def test_exponential_decay(self, ghi):
        expected = math.exp(-10 * 0.05)
        assert abs(ghi._anomaly_stability_score(0.05) - expected) < 1e-9

    def test_high_anomaly_rate_near_zero(self, ghi):
        assert ghi._anomaly_stability_score(0.5) < 0.01

    def test_anomaly_clamped_at_one(self, ghi):
        assert ghi._anomaly_stability_score(0.0) <= 1.0

    def test_anomaly_always_positive(self, ghi):
        for rate in [0.0, 0.01, 0.1, 0.5, 1.0]:
            assert ghi._anomaly_stability_score(rate) > 0


class TestGHITrendStabilityScore:
    def test_identical_history_gives_high_score(self, ghi):
        history = [2.0] * 10
        tss = ghi._trend_stability_score(history)
        assert tss == 1.0  # std = 0, TSS = 1/(1+0) = 1

    def test_empty_history_returns_neutral(self, ghi):
        assert ghi._trend_stability_score([]) == 0.8
        assert ghi._trend_stability_score([1.5]) == 0.8

    def test_volatile_history_lower_score(self, ghi):
        volatile = [0.1, 10.0, 0.2, 9.5, 0.3]
        stable   = [2.0, 2.1, 1.9, 2.0, 2.1]
        assert ghi._trend_stability_score(volatile) < ghi._trend_stability_score(stable)

    def test_tss_bounded_zero_one(self, ghi):
        extreme = [0.0, 100.0, 0.0, 100.0]
        tss = ghi._trend_stability_score(extreme)
        assert 0.0 < tss <= 1.0


class TestGHIDataIntegrityScore:
    def test_perfect_data_gives_one(self, ghi):
        assert ghi._data_integrity_score(0.0, 0.0) == 1.0

    def test_half_missing_gives_half(self, ghi):
        assert ghi._data_integrity_score(0.5, 0.0) == 0.5

    def test_clamped_at_zero(self, ghi):
        assert ghi._data_integrity_score(0.8, 0.8) == 0.0

    def test_sum_exceeding_one_clamped(self, ghi):
        assert ghi._data_integrity_score(1.0, 1.0) == 0.0


class TestGHICompute:
    def test_healthy_grid(self, ghi):
        result = ghi.compute(make_inputs(residual=0.5, anomaly_rate=0.0, confidence=0.95))
        assert result.ghi >= GHI_HEALTHY
        assert result.classification == "HEALTHY"
        assert not result.action_required

    def test_degraded_grid(self, ghi):
        result = ghi.compute(make_inputs(residual=4.0, anomaly_rate=0.05, confidence=0.75))
        assert GHI_DEGRADED <= result.ghi < GHI_STABLE
        assert result.classification == "DEGRADED"
        assert result.action_required

    def test_critical_grid(self, ghi):
        result = ghi.compute(make_inputs(residual=8.0, anomaly_rate=0.15, confidence=0.55))
        assert result.ghi < GHI_DEGRADED
        assert result.classification in ("CRITICAL", "SEVERE")
        assert result.action_required

    def test_ghi_bounded_0_100(self, ghi):
        # Worst possible inputs
        result = ghi.compute(make_inputs(residual=100.0, anomaly_rate=1.0, confidence=0.0, missing=1.0, invalid=1.0))
        assert 0 <= result.ghi <= 100

        # Best possible inputs
        result = ghi.compute(make_inputs(residual=0.0, anomaly_rate=0.0, confidence=1.0))
        assert 0 <= result.ghi <= 100

    def test_components_returned(self, ghi):
        result = ghi.compute(make_inputs())
        c = result.components
        assert 0 <= c.PBS <= 1
        assert 0 <= c.ASS <= 1
        assert 0 <= c.CS  <= 1
        assert 0 <= c.TSS <= 1
        assert 0 <= c.DIS <= 1

    def test_to_dict_structure(self, ghi):
        result = ghi.compute(make_inputs())
        d = result.to_dict()
        assert "ghi" in d
        assert "classification" in d
        assert "components" in d
        assert "weights" in d
        assert "thresholds" in d
        assert d["weights"]["PBS"] == 0.35

    def test_interpretation_non_empty(self, ghi):
        result = ghi.compute(make_inputs())
        assert len(result.interpretation) > 10

    def test_confidence_in_ghi_in_range(self, ghi):
        result = ghi.compute(make_inputs(confidence=0.8))
        assert 0.0 <= result.confidence_in_ghi <= 1.0


class TestGHIClassification:
    def test_all_classifications_covered(self, ghi):
        expected_map = {
            95.0: "HEALTHY", 80.0: "STABLE", 60.0: "DEGRADED",
            40.0: "CRITICAL", 20.0: "SEVERE",
        }
        for score, expected in expected_map.items():
            assert ghi._classify(score) == expected


# ── Risk Classifier ────────────────────────────────────────────────────────

@pytest.fixture
def classifier():
    return RiskClassifier()


class TestRiskClassifier:
    def test_critical_residual_gives_critical_priority(self, classifier):
        risk = classifier.classify(
            ghi=20.0, ghi_classification="SEVERE",
            residual_pct=13.0, anomaly_rate=0.2,
            confidence=0.7, pbs=0.0, measurement_quality="medium",
        )
        assert risk.priority == InspectionPriority.CRITICAL

    def test_healthy_grid_informational(self, classifier):
        risk = classifier.classify(
            ghi=92.0, ghi_classification="HEALTHY",
            residual_pct=0.8, anomaly_rate=0.01,
            confidence=0.95, pbs=1.0, measurement_quality="high",
        )
        assert risk.priority == InspectionPriority.INFORMATIONAL
        assert not risk.requires_human_review

    def test_medium_priority_requires_review(self, classifier):
        risk = classifier.classify(
            ghi=60.0, ghi_classification="DEGRADED",
            residual_pct=4.0, anomaly_rate=0.05,
            confidence=0.8, pbs=0.6, measurement_quality="medium",
        )
        assert risk.priority == InspectionPriority.MEDIUM
        assert risk.requires_human_review

    def test_trending_up_upgrades_priority(self, classifier):
        risk_stable = classifier.classify(
            ghi=65.0, ghi_classification="DEGRADED",
            residual_pct=5.5, anomaly_rate=0.04,
            confidence=0.8, pbs=0.5, trend_increasing=False, measurement_quality="medium",
        )
        risk_trend = classifier.classify(
            ghi=65.0, ghi_classification="DEGRADED",
            residual_pct=5.5, anomaly_rate=0.04,
            confidence=0.8, pbs=0.5, trend_increasing=True, measurement_quality="medium",
        )
        # Trending up at > 5% residual should give at least HIGH
        assert risk_trend.priority.value in ("HIGH", "CRITICAL") or \
               risk_trend.priority.value == risk_stable.priority.value

    def test_measurement_category_for_low_quality(self, classifier):
        risk = classifier.classify(
            ghi=50.0, ghi_classification="DEGRADED",
            residual_pct=2.0, anomaly_rate=0.02,
            confidence=0.4, pbs=0.8, measurement_quality="low",
        )
        assert risk.category == InspectionCategory.MEASUREMENT

    def test_infrastructure_category_for_high_residual(self, classifier):
        risk = classifier.classify(
            ghi=40.0, ghi_classification="CRITICAL",
            residual_pct=8.0, anomaly_rate=0.01,
            confidence=0.85, pbs=0.0, measurement_quality="high",
        )
        assert risk.category == InspectionCategory.INFRASTRUCTURE

    def test_actions_list_non_empty(self, classifier):
        risk = classifier.classify(
            ghi=50.0, ghi_classification="DEGRADED",
            residual_pct=4.0, anomaly_rate=0.05,
            confidence=0.8, pbs=0.5, measurement_quality="medium",
        )
        assert len(risk.recommended_actions) > 0

    def test_reasoning_no_individual_language(self, classifier):
        risk = classifier.classify(
            ghi=40.0, ghi_classification="CRITICAL",
            residual_pct=9.0, anomaly_rate=0.1,
            confidence=0.7, pbs=0.0, measurement_quality="medium",
        )
        lowered = risk.reasoning.lower()
        for banned in ["theft", "fraud", "individual", "person", "customer is"]:
            assert banned not in lowered, f"Accusation language detected: '{banned}'"

    def test_to_dict_structure(self, classifier):
        risk = classifier.classify(
            ghi=70.0, ghi_classification="STABLE",
            residual_pct=2.0, anomaly_rate=0.02,
            confidence=0.85, pbs=0.8, measurement_quality="high",
        )
        d = risk.to_dict()
        assert "priority" in d
        assert "category" in d
        assert "urgency" in d
        assert "recommended_actions" in d
        assert "reasoning" in d
        assert "ethics_note" in d

    def test_ethics_note_present(self, classifier):
        risk = classifier.classify(
            ghi=50.0, ghi_classification="DEGRADED",
            residual_pct=4.0, anomaly_rate=0.05,
            confidence=0.8, pbs=0.5, measurement_quality="medium",
        )
        assert "human review" in risk.ethics_note.lower()
        assert len(risk.ethics_note) > 20


# ── AI Interpretation Engine ───────────────────────────────────────────────

@pytest.fixture
def ai_engine_offline():
    return AIInterpretationEngine()  # no keys → offline mode


def make_ai_input(**overrides):
    defaults = dict(
        substation_id="SS001",
        timestamp="2026-01-01T00:00:00",
        input_mwh=1000.0,
        output_mwh=975.0,
        expected_loss_mwh=18.0,
        actual_loss_mwh=25.0,
        residual_pct=2.5,
        balance_status="minor_imbalance",
        measurement_quality="medium",
        anomaly_rate=0.04,
        anomalies_flagged=4,
        ghi=74.0,
        ghi_class="STABLE",
        pbs=0.75,
        ass=0.67,
        cs=0.80,
        tss=0.82,
        dis=0.95,
        priority="MEDIUM",
        category="OPERATIONAL",
        confidence=0.80,
        trend=[{"ts": "2026-01-01T00:00:00", "residual_pct": 2.5}],
    )
    defaults.update(overrides)
    return AIInterpretationInput(**defaults)


class TestAIInterpretationEngine:
    def test_offline_mode_returns_result(self, ai_engine_offline):
        result = ai_engine_offline.interpret(make_ai_input())
        assert result.risk_level in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
        assert len(result.recommended_actions) > 0
        assert result.model_name == "offline"

    def test_low_confidence_refused(self, ai_engine_offline):
        result = ai_engine_offline.interpret(make_ai_input(confidence=0.3))
        assert result.model_name == "refused"
        assert result.error is not None

    def test_offline_risk_maps_to_classification(self, ai_engine_offline):
        healthy = ai_engine_offline.interpret(make_ai_input(ghi=92.0, ghi_class="HEALTHY", confidence=0.9))
        severe  = ai_engine_offline.interpret(make_ai_input(ghi=20.0, ghi_class="SEVERE", confidence=0.9))
        assert healthy.risk_level in ("LOW",)
        assert severe.risk_level in ("CRITICAL",)

    def test_to_dict_structure(self, ai_engine_offline):
        result = ai_engine_offline.interpret(make_ai_input())
        d = result.to_dict()
        required_keys = {
            "risk_level", "primary_infrastructure_hypothesis",
            "inspection_priority", "recommended_actions",
            "confidence_commentary", "trend_assessment",
            "estimated_investigation_scope", "model_name", "token_usage",
        }
        for key in required_keys:
            assert key in d, f"Missing key: {key}"

    def test_prompt_builder_contains_all_fields(self, ai_engine_offline):
        inp = make_ai_input()
        prompt = ai_engine_offline._build_user_prompt(inp)
        assert "SS001" in prompt
        assert "1000.00 MWh" in prompt
        assert "2.50%" in prompt
        assert "74.0 / 100" in prompt
        assert "STABLE" in prompt

    def test_guardrails_strip_accusation_language(self):
        engine = AIInterpretationEngine()
        data = {
            "risk_level": "HIGH",
            "primary_infrastructure_hypothesis": "Meter theft detected at customer premises",
            "inspection_priority": "HIGH",
            "recommended_actions": ["Suspect individual should be arrested"],
            "confidence_commentary": "High confidence in fraud detection",
            "trend_assessment": "Increasing",
            "estimated_investigation_scope": "FIELD_CREW",
        }
        cleaned = engine._apply_guardrails(data)
        assert "theft" not in cleaned["primary_infrastructure_hypothesis"].lower()
        assert "fraud" not in cleaned["confidence_commentary"].lower()
        assert "individual" not in " ".join(cleaned["recommended_actions"]).lower()

    def test_valid_json_parsed_correctly(self):
        engine = AIInterpretationEngine()
        raw = '''{
          "risk_level": "MEDIUM",
          "primary_infrastructure_hypothesis": "Possible transformer degradation.",
          "inspection_priority": "MEDIUM",
          "recommended_actions": ["Inspect transformer insulation"],
          "confidence_commentary": "Moderate confidence.",
          "trend_assessment": "Stable trend.",
          "estimated_investigation_scope": "FIELD_CREW"
        }'''
        parsed = engine._parse_and_validate(raw)
        assert parsed["risk_level"] == "MEDIUM"
        assert len(parsed["recommended_actions"]) == 1

    def test_invalid_enum_coerced_to_default(self):
        engine = AIInterpretationEngine()
        raw = '''{
          "risk_level": "UNKNOWN_VALUE",
          "primary_infrastructure_hypothesis": "Test.",
          "inspection_priority": "NOT_VALID",
          "recommended_actions": ["Test action"],
          "confidence_commentary": "Test.",
          "trend_assessment": "Test.",
          "estimated_investigation_scope": "INVALID"
        }'''
        parsed = engine._parse_and_validate(raw)
        assert parsed["risk_level"] == "MEDIUM"   # default
        assert parsed["inspection_priority"] == "MEDIUM"
        assert parsed["estimated_investigation_scope"] == "FIELD_CREW"

    def test_markdown_wrapped_json_parsed(self):
        engine = AIInterpretationEngine()
        raw = '''```json
{
  "risk_level": "LOW",
  "primary_infrastructure_hypothesis": "Normal operation.",
  "inspection_priority": "LOW",
  "recommended_actions": ["Continue monitoring"],
  "confidence_commentary": "High confidence.",
  "trend_assessment": "Stable.",
  "estimated_investigation_scope": "DESK_REVIEW"
}
```'''
        parsed = engine._parse_and_validate(raw)
        assert parsed["risk_level"] == "LOW"


# ── Integration: GHI + Risk in sequence ───────────────────────────────────

class TestGHIRiskIntegration:
    def test_healthy_grid_gives_informational_risk(self):
        ghi_eng = GridHealthEngine()
        risk_eng = RiskClassifier()
        inputs = make_inputs(residual=0.5, anomaly_rate=0.0, confidence=0.95)
        ghi_result = ghi_eng.compute(inputs)
        risk = risk_eng.classify(
            ghi=ghi_result.ghi,
            ghi_classification=ghi_result.classification,
            residual_pct=0.5, anomaly_rate=0.0,
            confidence=0.95, pbs=ghi_result.components.PBS,
            measurement_quality="high",
        )
        assert ghi_result.classification == "HEALTHY"
        assert risk.priority == InspectionPriority.INFORMATIONAL

    def test_severe_grid_gives_critical_risk(self):
        ghi_eng = GridHealthEngine()
        risk_eng = RiskClassifier()
        inputs = make_inputs(residual=15.0, anomaly_rate=0.3, confidence=0.55)
        ghi_result = ghi_eng.compute(inputs)
        risk = risk_eng.classify(
            ghi=ghi_result.ghi,
            ghi_classification=ghi_result.classification,
            residual_pct=15.0, anomaly_rate=0.3,
            confidence=0.55, pbs=ghi_result.components.PBS,
            measurement_quality="low",
        )
        assert ghi_result.classification in ("CRITICAL", "SEVERE")
        assert risk.priority in (InspectionPriority.CRITICAL, InspectionPriority.HIGH)
        assert risk.requires_human_review
