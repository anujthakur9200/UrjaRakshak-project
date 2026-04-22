"""
Physics Engine Tests — UrjaRakshak python-backend
==================================================
Covers: transformer loss, line loss, energy balance analysis,
        balance classification, and hypothesis generation.
"""

from __future__ import annotations

import math
import pytest

from app.physics.engine import (
    ComponentLoss,
    PhysicsAnalysisResult,
    analyze_energy_balance,
    calculate_line_loss,
    calculate_transformer_loss,
    classify_balance_status,
)


# ─────────────────────────────────────────────────────────────────────
# Transformer loss tests
# ─────────────────────────────────────────────────────────────────────


class TestTransformerLoss:
    def test_returns_positive_loss(self):
        loss = calculate_transformer_loss(
            rated_kva=100.0,
            load_factor=0.8,
            efficiency_rating=0.97,
            age_years=5.0,
        )
        assert loss > 0.0, "Transformer loss must be positive"

    def test_higher_load_factor_increases_loss(self):
        base = calculate_transformer_loss(100.0, 0.5, 0.97, 5.0)
        high = calculate_transformer_loss(100.0, 1.0, 0.97, 5.0)
        assert high > base, "Loss should increase with higher load factor"

    def test_older_transformer_has_more_loss(self):
        young = calculate_transformer_loss(100.0, 0.8, 0.97, 0.0)
        old = calculate_transformer_loss(100.0, 0.8, 0.97, 40.0)
        assert old > young, "Older transformer should have higher losses"

    def test_age_degradation_capped_at_25pct(self):
        # At age 50 and age 200, the loss should be the same (cap reached)
        loss_50 = calculate_transformer_loss(100.0, 0.8, 0.97, 50.0)
        loss_200 = calculate_transformer_loss(100.0, 0.8, 0.97, 200.0)
        assert math.isclose(loss_50, loss_200, rel_tol=1e-6), (
            "Age degradation should be capped at 25 %"
        )

    def test_load_factor_clamped_to_zero(self):
        loss_neg = calculate_transformer_loss(100.0, -1.0, 0.97, 5.0)
        loss_zero = calculate_transformer_loss(100.0, 0.0, 0.97, 5.0)
        assert math.isclose(loss_neg, loss_zero, rel_tol=1e-6)

    def test_high_efficiency_reduces_loss(self):
        low_eff = calculate_transformer_loss(100.0, 0.8, 0.90, 5.0)
        high_eff = calculate_transformer_loss(100.0, 0.8, 0.99, 5.0)
        assert high_eff < low_eff, "Higher efficiency should yield lower losses"


# ─────────────────────────────────────────────────────────────────────
# Line loss tests
# ─────────────────────────────────────────────────────────────────────


class TestLineLoss:
    def test_i_squared_r_formula(self):
        """Loss = I² × R_total; verify against manual calculation."""
        current_a = 100.0
        resistance_ohm_per_km = 0.1
        length_km = 10.0
        expected_kw = (current_a ** 2) * (resistance_ohm_per_km * length_km) / 1000.0

        result = calculate_line_loss(current_a, resistance_ohm_per_km, length_km, 11.0)
        assert math.isclose(result, expected_kw, rel_tol=1e-9)

    def test_zero_current_gives_zero_loss(self):
        loss = calculate_line_loss(0.0, 0.1, 10.0, 11.0)
        assert loss == 0.0

    def test_longer_line_increases_loss(self):
        short = calculate_line_loss(100.0, 0.1, 5.0, 11.0)
        long_ = calculate_line_loss(100.0, 0.1, 20.0, 11.0)
        assert long_ > short

    def test_higher_resistance_increases_loss(self):
        low_r = calculate_line_loss(100.0, 0.05, 10.0, 11.0)
        high_r = calculate_line_loss(100.0, 0.20, 10.0, 11.0)
        assert high_r > low_r

    def test_returns_kw_not_w(self):
        """100 A, 1 Ω/km, 1 km → 10 000 W → 10 kW."""
        loss = calculate_line_loss(100.0, 1.0, 1.0, 11.0)
        assert math.isclose(loss, 10.0, rel_tol=1e-9)


# ─────────────────────────────────────────────────────────────────────
# Energy balance analysis tests
# ─────────────────────────────────────────────────────────────────────


class TestAnalyzeEnergyBalance:
    _base_components = [
        {
            "component_id": "TX-001",
            "component_type": "transformer",
            "rated_kva": 500.0,
            "load_factor": 0.75,
            "efficiency": 0.97,
            "age_years": 8.0,
        },
        {
            "component_id": "LN-001",
            "component_type": "transmission_line",
            "current_a": 200.0,
            "resistance_ohm_per_km": 0.1,
            "length_km": 5.0,
            "voltage_kv": 11.0,
        },
    ]

    def test_returns_correct_type(self):
        result = analyze_energy_balance(10000.0, 9700.0, self._base_components)
        assert isinstance(result, PhysicsAnalysisResult)

    def test_actual_loss_equals_input_minus_output(self):
        input_kwh = 10000.0
        output_kwh = 9700.0
        result = analyze_energy_balance(input_kwh, output_kwh, self._base_components)
        expected_loss = input_kwh - output_kwh
        assert math.isclose(result.total_loss_kwh, expected_loss, rel_tol=1e-6)

    def test_residual_equals_loss_minus_technical(self):
        result = analyze_energy_balance(10000.0, 9700.0, self._base_components)
        expected_residual = round(result.total_loss_kwh - result.technical_loss_kwh, 3)
        assert math.isclose(result.residual_kwh, expected_residual, rel_tol=1e-4)

    def test_component_losses_populated(self):
        result = analyze_energy_balance(10000.0, 9700.0, self._base_components)
        assert len(result.components) == 2
        for comp in result.components:
            assert isinstance(comp, ComponentLoss)
            assert comp.calculated_loss_kwh >= 0.0
            assert 0.0 <= comp.confidence <= 1.0

    def test_confidence_between_zero_and_one(self):
        result = analyze_energy_balance(10000.0, 9700.0, self._base_components)
        assert 0.0 <= result.confidence_score <= 1.0

    def test_balanced_scenario_classified_correctly(self):
        """Very small residual should give 'balanced' status."""
        # Make output almost equal to input (< 2 % loss)
        input_kwh = 10000.0
        output_kwh = 9990.0  # 0.1 % loss — essentially all technical
        result = analyze_energy_balance(input_kwh, output_kwh, self._base_components)
        # With very small residual, should not be critical
        assert result.balance_status in ("balanced", "minor_imbalance")

    def test_large_residual_raises_severity(self):
        """
        Large unaccounted loss (17 %) should yield significant/critical imbalance
        or 'uncertain' when the residual is so large it drives confidence below 0.5.
        Either way the result must NOT be 'balanced' or 'minor_imbalance'.
        """
        result = analyze_energy_balance(10000.0, 8300.0, self._base_components)
        assert result.balance_status not in ("balanced", "minor_imbalance"), (
            f"Expected a high-severity status for a 17% residual, got '{result.balance_status}'"
        )

    def test_hypotheses_sorted_by_probability(self):
        result = analyze_energy_balance(10000.0, 9200.0, self._base_components)
        probs = [h["probability"] for h in result.hypotheses]
        assert probs == sorted(probs, reverse=True)

    def test_empty_components_still_returns_result(self):
        result = analyze_energy_balance(10000.0, 9700.0, [])
        assert isinstance(result, PhysicsAnalysisResult)
        assert result.technical_loss_kwh == 0.0


# ─────────────────────────────────────────────────────────────────────
# Balance classification tests
# ─────────────────────────────────────────────────────────────────────


class TestClassifyBalanceStatus:
    @pytest.mark.parametrize("residual_pct,confidence,expected", [
        (0.5,  0.90, "balanced"),
        (1.9,  0.85, "balanced"),
        (2.5,  0.80, "minor_imbalance"),
        (4.9,  0.75, "minor_imbalance"),
        (5.0,  0.70, "significant_imbalance"),
        (9.9,  0.65, "significant_imbalance"),
        (10.0, 0.60, "critical_imbalance"),
        (25.0, 0.55, "critical_imbalance"),
        (5.0,  0.40, "uncertain"),           # low confidence → uncertain
        (0.1,  0.00, "uncertain"),
    ])
    def test_classification(self, residual_pct, confidence, expected):
        result = classify_balance_status(residual_pct, confidence)
        assert result == expected, (
            f"residual={residual_pct}%, confidence={confidence} → "
            f"expected '{expected}', got '{result}'"
        )

    def test_negative_residual_uses_absolute_value(self):
        # Negative residual (output > expected) should still classify on magnitude
        result = classify_balance_status(-7.0, 0.80)
        assert result == "significant_imbalance"
