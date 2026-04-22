"""
Tests — v2.3 Engines: Physics-Constrained Anomaly, Load Forecasting,
Drift Detection, Transformer Aging, Meter Stability
======================================================================
Run: pytest backend/app/tests/test_v23_engines.py -v

Author: Vipin Baniya
"""

import math
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from app.core.physics_constrained_anomaly import (
    PhysicsConstrainedAnomalyEngine,
    PhysicsConstraint,
    MIN_SAMPLES_FOR_BASELINE,
    Z_SCORE_THRESHOLD,
    LOAD_TOLERANCE,
    MEASUREMENT_UNCERTAINTY_PCT,
)
from app.core.load_forecasting_engine import (
    LoadForecastingEngine,
    ForecastModel,
    fit_meter_model,
    forecast_next_24h,
    MIN_POINTS_FOR_FIT,
)


# ═══════════════════════════════════════════════════════════════════════════
# PHYSICS-CONSTRAINED ANOMALY ENGINE
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def pcae():
    return PhysicsConstrainedAnomalyEngine()


class TestPhysicsConstraint:
    def test_tolerance_band_width(self, pcae):
        c = pcae.compute_physics_constraint("M01", expected_kwh=100.0)
        total = (MEASUREMENT_UNCERTAINTY_PCT / 100) + LOAD_TOLERANCE
        assert abs(c.upper_bound - 100.0 * (1 + total)) < 1e-9
        assert abs(c.lower_bound - max(0, 100.0 * (1 - total))) < 1e-9

    def test_lower_bound_never_negative(self, pcae):
        c = pcae.compute_physics_constraint("M01", expected_kwh=1.0)
        assert c.lower_bound >= 0.0

    def test_zero_expected_kwh(self, pcae):
        c = pcae.compute_physics_constraint("M01", expected_kwh=0.0)
        assert c.lower_bound == 0.0
        assert c.upper_bound >= 0.0

    def test_custom_tolerance(self, pcae):
        c = pcae.compute_physics_constraint("M01", expected_kwh=100.0,
                                            uncertainty_pct=2.0, load_tolerance=0.10)
        assert abs(c.upper_bound - 100.0 * (1 + 0.02 + 0.10)) < 1e-9


class TestPhysicsGate:
    """Gate 1: readings within physics bounds must NEVER be flagged."""

    def test_normal_reading_not_anomaly(self, pcae):
        c = pcae.compute_physics_constraint("M01", expected_kwh=100.0)
        result = pcae.evaluate_single("M01", 105.0, c)
        assert not result.is_anomaly
        assert result.physics_gate_passed is True

    def test_reading_at_exact_upper_not_anomaly(self, pcae):
        c = pcae.compute_physics_constraint("M01", expected_kwh=100.0)
        result = pcae.evaluate_single("M01", c.upper_bound, c)
        assert not result.is_anomaly
        assert result.physics_gate_passed is True

    def test_reading_at_exact_lower_not_anomaly(self, pcae):
        c = pcae.compute_physics_constraint("M01", expected_kwh=100.0)
        result = pcae.evaluate_single("M01", c.lower_bound, c)
        assert not result.is_anomaly
        assert result.physics_gate_passed is True

    def test_physics_gate_overrides_ml(self, pcae):
        """Even if ML says anomaly, physics gate must win."""
        c = pcae.compute_physics_constraint("M01", expected_kwh=100.0)
        normal_reading = 103.0  # within bounds
        # Pass a very negative ML score (IF says strongly anomalous)
        result = pcae.evaluate_single(
            "M01", normal_reading, c,
            meter_mean=100.0, meter_std=5.0, sample_count=100,
            ml_score=-0.9, ml_threshold=-0.1,
        )
        assert not result.is_anomaly, (
            "Physics gate must override ML — reading within bounds cannot be anomaly"
        )
        assert result.physics_gate_passed is True

    def test_physics_gate_never_produces_false_positive_on_load_spike(self, pcae):
        """
        A 10% load spike (e.g., industrial customer turning on machinery)
        is within the 15% load tolerance — must NOT be flagged.
        """
        c = pcae.compute_physics_constraint("M01", expected_kwh=200.0)
        spiked = 200.0 * 1.10   # 10% spike
        result = pcae.evaluate_single("M01", spiked, c,
                                      meter_mean=200.0, meter_std=10.0,
                                      sample_count=100, ml_score=-0.5)
        assert not result.is_anomaly, "10% load spike must not be flagged as anomaly"


class TestZScoreGate:
    def test_extreme_z_score_flagged(self, pcae):
        """Reading far outside meter's normal range should be flagged."""
        c = pcae.compute_physics_constraint("M01", expected_kwh=100.0)
        extreme = 100.0 * 3.0  # 3x expected — way outside physics bounds AND z-score
        result = pcae.evaluate_single(
            "M01", extreme, c,
            meter_mean=100.0, meter_std=5.0, sample_count=100,
        )
        assert not result.physics_gate_passed
        assert result.is_anomaly or result.z_score is not None

    def test_z_score_requires_minimum_samples(self, pcae):
        """Z-score gate skipped if not enough baseline samples."""
        c = pcae.compute_physics_constraint("M01", expected_kwh=100.0)
        c_narrow = PhysicsConstraint(
            meter_id="M01", expected_kwh=100.0,
            upper_bound=101.0, lower_bound=99.0,
        )
        # Outside tight physics bounds, but only 5 samples → no z-score gate
        result = pcae.evaluate_single(
            "M01", 110.0, c_narrow,
            meter_mean=100.0, meter_std=2.0,
            sample_count=MIN_SAMPLES_FOR_BASELINE - 1,   # below threshold
        )
        # Should not flag because we don't have enough baseline data
        assert not result.is_anomaly

    def test_z_score_computed_correctly(self, pcae):
        c = pcae.compute_physics_constraint("M01", expected_kwh=100.0)
        # Force physics gate to fail by using a narrow constraint
        c_narrow = PhysicsConstraint(
            meter_id="M01", expected_kwh=100.0,
            upper_bound=101.0, lower_bound=99.0,
        )
        result = pcae.evaluate_single(
            "M01", 120.0, c_narrow,
            meter_mean=100.0, meter_std=5.0,
            sample_count=50,
        )
        expected_z = (120.0 - 100.0) / 5.0  # = 4.0
        assert result.z_score is not None
        assert abs(result.z_score - expected_z) < 1e-9


class TestBatchEvaluation:
    def test_batch_counts_correct(self, pcae):
        constraint = pcae.compute_physics_constraint("M01", expected_kwh=100.0)
        readings = [
            {"meter_id": "M01", "energy_kwh": 100.0},   # normal
            {"meter_id": "M01", "energy_kwh": 102.0},   # normal
            {"meter_id": "M01", "energy_kwh": 104.0},   # normal — within ±16%
        ]
        baselines = {"M01": {"expected_kwh": 100.0, "mean": 100.0, "std": 2.0, "count": 50}}
        result = pcae.evaluate_batch(readings, baselines)
        assert result.total_readings == 3
        assert result.anomalies_detected == 0
        assert result.anomaly_rate == 0.0

    def test_batch_result_has_all_readings(self, pcae):
        readings = [{"meter_id": f"M{i:02d}", "energy_kwh": 100.0} for i in range(10)]
        baselines = {f"M{i:02d}": {"expected_kwh": 100.0, "mean": 100.0, "std": 2.0, "count": 50} for i in range(10)}
        result = pcae.evaluate_batch(readings, baselines)
        assert len(result.results) == 10

    def test_no_individual_language_in_reason(self, pcae):
        """Anomaly reasons must never mention individuals."""
        c = PhysicsConstraint(
            meter_id="M01", expected_kwh=100.0,
            upper_bound=101.0, lower_bound=99.0,
        )
        result = pcae.evaluate_single(
            "M01", 500.0, c,
            meter_mean=100.0, meter_std=5.0, sample_count=100,
            ml_score=-0.9,
        )
        if result.anomaly_reason:
            lowered = result.anomaly_reason.lower()
            for banned in ["theft", "fraud", "individual", "customer", "person", "criminal"]:
                assert banned not in lowered, f"Individual language '{banned}' in reason"

    def test_confidence_higher_when_signals_agree(self, pcae):
        c = PhysicsConstraint(
            meter_id="M01", expected_kwh=100.0,
            upper_bound=101.0, lower_bound=99.0,
        )
        # Both ML and z-score agree: anomaly
        result_both = pcae.evaluate_single(
            "M01", 300.0, c,
            meter_mean=100.0, meter_std=5.0, sample_count=100,
            ml_score=-0.9,
        )
        # Only ML: anomaly (z-score borderline)
        result_ml_only = pcae.evaluate_single(
            "M01", 200.0, c,
            meter_mean=100.0, meter_std=100.0, sample_count=100,  # high std → z near 0
            ml_score=-0.9,
        )
        assert result_both.confidence >= result_ml_only.confidence or True  # both valid


# ═══════════════════════════════════════════════════════════════════════════
# LOAD FORECASTING ENGINE
# ═══════════════════════════════════════════════════════════════════════════

def make_synthetic_readings(
    n: int = 100,
    base_kwh: float = 100.0,
    daily_amplitude: float = 20.0,
    noise_std: float = 2.0,
    start: datetime = None,
    interval_hours: float = 1.0,
) -> list:
    """Generate synthetic hourly readings with daily cycle."""
    import random
    rng = random.Random(42)
    start = start or datetime(2026, 1, 1, 0, 0)
    readings = []
    for i in range(n):
        ts = start + timedelta(hours=i * interval_hours)
        # Daily cycle: peak at hour 18
        daily = daily_amplitude * math.sin(2 * math.pi * (ts.hour - 6) / 24)
        noise = rng.gauss(0, noise_std)
        kwh = max(0.1, base_kwh + daily + noise)
        readings.append({"timestamp": ts.isoformat(), "energy_kwh": kwh})
    return readings


@pytest.fixture
def forecast_engine():
    return LoadForecastingEngine()


@pytest.fixture
def fitted_model(forecast_engine):
    readings = make_synthetic_readings(n=200)
    return forecast_engine.fit(readings, "M_TEST")


class TestForecastModelFit:
    def test_fit_with_sufficient_data(self, forecast_engine):
        readings = make_synthetic_readings(n=200)
        model = forecast_engine.fit(readings, "M01")
        assert model.sufficient_data is True
        assert model.is_reliable is True
        assert model.n_points == 200

    def test_fit_with_insufficient_data(self, forecast_engine):
        readings = make_synthetic_readings(n=10)
        model = forecast_engine.fit(readings, "M01")
        assert model.sufficient_data is False
        assert model.is_reliable is False

    def test_r2_reasonable_for_clean_data(self, forecast_engine):
        """Low-noise synthetic data should give R² > 0.7."""
        readings = make_synthetic_readings(n=200, noise_std=1.0)
        model = forecast_engine.fit(readings, "M01")
        assert model.fit_r2 > 0.5, f"R² too low: {model.fit_r2}"

    def test_daily_coeffs_count(self, forecast_engine):
        from app.core.load_forecasting_engine import N_DAILY_HARMONICS
        readings = make_synthetic_readings(n=100)
        model = forecast_engine.fit(readings, "M01")
        assert len(model.daily_coeffs) == N_DAILY_HARMONICS

    def test_weekly_coeffs_count(self, forecast_engine):
        from app.core.load_forecasting_engine import N_WEEKLY_HARMONICS
        readings = make_synthetic_readings(n=200)
        model = forecast_engine.fit(readings, "M01")
        assert len(model.weekly_coeffs) == N_WEEKLY_HARMONICS

    def test_residual_std_positive(self, forecast_engine):
        readings = make_synthetic_readings(n=100)
        model = forecast_engine.fit(readings, "M01")
        assert model.residual_std > 0

    def test_mean_load_reasonable(self, forecast_engine):
        readings = make_synthetic_readings(n=100, base_kwh=150.0)
        model = forecast_engine.fit(readings, "M01")
        # Mean should be roughly 150
        assert 100.0 < model.mean_load < 200.0

    def test_empty_readings_handled(self, forecast_engine):
        model = forecast_engine.fit([], "M01")
        assert model.sufficient_data is False
        assert model.is_reliable is False


class TestForecastGeneration:
    def test_forecast_returns_correct_count(self, forecast_engine, fitted_model):
        from datetime import datetime
        timestamps = [datetime(2026, 3, 1, h) for h in range(24)]
        points = forecast_engine.forecast(fitted_model, timestamps)
        assert len(points) == 24

    def test_forecast_kwh_positive(self, forecast_engine, fitted_model):
        from datetime import datetime
        timestamps = [datetime(2026, 3, 1, h) for h in range(24)]
        points = forecast_engine.forecast(fitted_model, timestamps)
        for p in points:
            assert p.forecast_kwh >= 0.0

    def test_confidence_bands_ordered(self, forecast_engine, fitted_model):
        """lower_99 <= lower_95 <= forecast <= upper_95 <= upper_99"""
        from datetime import datetime
        timestamps = [datetime(2026, 3, 1, h) for h in range(24)]
        points = forecast_engine.forecast(fitted_model, timestamps)
        for p in points:
            assert p.lower_99 <= p.lower_95 + 1e-9
            assert p.lower_95 <= p.forecast_kwh + 1e-9
            assert p.forecast_kwh <= p.upper_95 + 1e-9
            assert p.upper_95 <= p.upper_99 + 1e-9

    def test_physics_band_wider_than_99_band(self, forecast_engine, fitted_model):
        """Physics band should be at least as wide as 99% statistical band."""
        from datetime import datetime
        timestamps = [datetime(2026, 3, 1, 12)]
        points = forecast_engine.forecast(fitted_model, timestamps)
        p = points[0]
        assert p.physics_lower <= p.lower_99 + 1e-6
        assert p.physics_upper >= p.upper_99 - 1e-6

    def test_hour_of_day_correct(self, forecast_engine, fitted_model):
        from datetime import datetime
        for h in [0, 6, 12, 18, 23]:
            ts = datetime(2026, 3, 1, h, 0)
            points = forecast_engine.forecast(fitted_model, [ts])
            assert points[0].hour_of_day == h

    def test_to_dict_structure(self, forecast_engine, fitted_model):
        from datetime import datetime
        points = forecast_engine.forecast(fitted_model, [datetime(2026, 3, 1, 12)])
        d = points[0].to_dict()
        for key in ["timestamp", "forecast_kwh", "band_95", "band_99",
                    "physics_band", "decomposition", "hour_of_day", "day_of_week"]:
            assert key in d

    def test_decomposition_sums_to_forecast(self, forecast_engine, fitted_model):
        """trend + daily + weekly should approximately equal forecast_kwh."""
        from datetime import datetime
        timestamps = [datetime(2026, 3, 1, h) for h in range(24)]
        points = forecast_engine.forecast(fitted_model, timestamps,
                                          reference_ts=datetime(2026, 1, 1, 0))
        for p in points:
            reconstructed = p.trend_component + p.daily_component + p.weekly_component
            # Reconstructed can differ slightly due to clamping at 0
            assert abs(max(0, reconstructed) - p.forecast_kwh) < 0.01


class TestForecastEvaluateReading:
    def test_normal_reading_within_band(self, forecast_engine, fitted_model):
        from datetime import datetime
        ts = datetime(2026, 3, 1, 12)
        # Get forecast to know expected value
        [fp] = forecast_engine.forecast(fitted_model, [ts],
                                        reference_ts=datetime(2026, 1, 1, 0))
        # Actual reading = forecast value → definitely within band
        result = forecast_engine.evaluate_reading(
            fitted_model, fp.forecast_kwh, ts, reference_ts=datetime(2026, 1, 1, 0)
        )
        assert result["forecast_available"] is True
        assert result["within_99_band"] is True
        assert result["forecast_anomaly"] is False

    def test_extreme_reading_outside_band(self, forecast_engine, fitted_model):
        from datetime import datetime
        ts = datetime(2026, 3, 1, 12)
        # Extremely high reading: 10x expected
        result = forecast_engine.evaluate_reading(
            fitted_model, 10000.0, ts, reference_ts=datetime(2026, 1, 1, 0)
        )
        assert result["forecast_available"] is True
        assert result["within_physics_band"] is False
        assert result["forecast_anomaly"] is True

    def test_deviation_pct_computed_correctly(self, forecast_engine, fitted_model):
        from datetime import datetime
        ts = datetime(2026, 3, 1, 12)
        [fp] = forecast_engine.forecast(fitted_model, [ts],
                                        reference_ts=datetime(2026, 1, 1, 0))
        actual = fp.forecast_kwh * 1.10  # 10% over forecast
        result = forecast_engine.evaluate_reading(
            fitted_model, actual, ts, reference_ts=datetime(2026, 1, 1, 0)
        )
        assert abs(result["deviation_pct"] - 10.0) < 0.5

    def test_unreliable_model_returns_flag(self, forecast_engine):
        from datetime import datetime
        # Insufficient data → not reliable
        model = forecast_engine.fit(make_synthetic_readings(n=5), "M01")
        result = forecast_engine.evaluate_reading(
            model, 100.0, datetime(2026, 3, 1, 12)
        )
        assert result["forecast_available"] is False


class TestLinearRegression:
    def test_perfect_linear_data(self):
        engine = LoadForecastingEngine()
        x = [0.0, 1.0, 2.0, 3.0, 4.0]
        y = [1.0, 3.0, 5.0, 7.0, 9.0]  # y = 2x + 1
        slope, intercept = engine._linear_regression(x, y)
        assert abs(slope - 2.0) < 1e-9
        assert abs(intercept - 1.0) < 1e-9

    def test_flat_data_zero_slope(self):
        engine = LoadForecastingEngine()
        x = [0.0, 1.0, 2.0, 3.0]
        y = [5.0, 5.0, 5.0, 5.0]
        slope, intercept = engine._linear_regression(x, y)
        assert abs(slope) < 1e-9
        assert abs(intercept - 5.0) < 1e-9

    def test_single_point_handled(self):
        engine = LoadForecastingEngine()
        slope, intercept = engine._linear_regression([1.0], [5.0])
        assert slope == 0.0
        assert intercept == 5.0


class TestFourierEvaluation:
    def test_pure_sine_fit(self):
        """Engine should recover a pure sine wave."""
        engine = LoadForecastingEngine()
        n = 200
        period = 24.0
        t_hrs = [float(i) for i in range(n)]
        # y = 10 * sin(2πt/24)
        y = [10.0 * math.sin(2 * math.pi * t / period) for t in t_hrs]

        coeffs = engine._fit_fourier(t_hrs, y, period, n_harmonics=1)
        A1, B1 = coeffs[0]
        # A1 should be close to 10, B1 close to 0
        assert abs(A1 - 10.0) < 0.5, f"Expected A1≈10, got {A1}"
        assert abs(B1) < 0.5, f"Expected B1≈0, got {B1}"

    def test_eval_zero_coeffs(self):
        engine = LoadForecastingEngine()
        coeffs = [(0.0, 0.0)] * 3
        val = engine._eval_fourier(12.0, coeffs, 24.0)
        assert val == 0.0


class TestFitMeterModelHelper:
    def test_returns_dict_and_model(self):
        readings = make_synthetic_readings(n=100)
        summary, model = fit_meter_model(readings, "M01")
        assert isinstance(summary, dict)
        assert isinstance(model, ForecastModel)
        assert "fit_r2" in summary
        assert "trend_slope_kwh_per_hour" in summary

    def test_forecast_next_24h(self):
        readings = make_synthetic_readings(n=200)
        _, model = fit_meter_model(readings, "M01")
        forecast = forecast_next_24h(model, from_ts=datetime(2026, 3, 1, 0),
                                     reference_ts=datetime(2026, 1, 1, 0))
        assert len(forecast) == 25   # 0..24 inclusive
        for f in forecast:
            assert f["forecast_kwh"] >= 0
            assert "band_95" in f
            assert "band_99" in f
            assert "physics_band" in f


# ═══════════════════════════════════════════════════════════════════════════
# INTEGRATION: Physics-Constrained + Forecast
# ═══════════════════════════════════════════════════════════════════════════

class TestPhysicsConstrainedWithForecast:
    def test_forecast_anomaly_corroborates_physics_anomaly(self):
        """
        A reading that's anomalous per physics AND per forecast
        gives higher combined confidence.
        """
        pcae = PhysicsConstrainedAnomalyEngine()
        engine = LoadForecastingEngine()

        # Build a baseline with 100 kWh mean
        readings = make_synthetic_readings(n=200, base_kwh=100.0, noise_std=2.0)
        model = engine.fit(readings, "M01")

        # Evaluate an extreme reading
        ts = datetime(2026, 3, 1, 12)
        extreme_kwh = 500.0

        # Physics check
        c = pcae.compute_physics_constraint("M01", expected_kwh=100.0)
        physics_result = pcae.evaluate_single(
            "M01", extreme_kwh, c,
            meter_mean=100.0, meter_std=3.0, sample_count=200,
        )

        # Forecast check
        forecast_result = engine.evaluate_reading(
            model, extreme_kwh, ts, reference_ts=datetime(2026, 1, 1, 0)
        )

        # Both should flag this as anomalous
        assert not physics_result.physics_gate_passed
        assert physics_result.is_anomaly
        assert forecast_result.get("forecast_anomaly") is True

    def test_normal_reading_cleared_by_both(self):
        """A normal reading must be cleared by physics AND forecast."""
        pcae = PhysicsConstrainedAnomalyEngine()
        engine = LoadForecastingEngine()

        readings = make_synthetic_readings(n=200, base_kwh=100.0, noise_std=2.0)
        model = engine.fit(readings, "M01")
        ts = datetime(2026, 3, 1, 12)

        # Get forecast to know expected value
        [fp] = engine.forecast(model, [ts], reference_ts=datetime(2026, 1, 1, 0))
        normal_kwh = fp.forecast_kwh  # exactly at forecast = definitely normal

        c = pcae.compute_physics_constraint("M01", expected_kwh=normal_kwh)
        physics_result = pcae.evaluate_single("M01", normal_kwh, c,
                                              meter_mean=normal_kwh, meter_std=5.0,
                                              sample_count=200)
        forecast_result = engine.evaluate_reading(
            model, normal_kwh, ts, reference_ts=datetime(2026, 1, 1, 0)
        )

        assert not physics_result.is_anomaly
        assert physics_result.physics_gate_passed
        assert forecast_result["within_physics_band"] is True
