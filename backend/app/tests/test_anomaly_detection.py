"""
Tests for ML Anomaly Detection Engine
=======================================
Run: pytest backend/app/tests/ -v

Author: Vipin Baniya
"""
import pytest
import numpy as np
from app.ml.anomaly_detection import (
    AnomalyFeatures, AnomalyDetectionEngine, StatisticalDetector,
    IsolationForestDetector, generate_synthetic_training_data,
    SKLEARN_AVAILABLE
)


@pytest.fixture
def sample_normal_features():
    return AnomalyFeatures(
        substation_id="SS001",
        timestamp="2025-01-01T12:00:00",
        input_mwh=500.0,
        output_mwh=480.0,   # 4% loss — normal
        residual_mwh=20.0,
        residual_percent=4.0,
        confidence_score=0.85,
        time_of_day_hour=14.0,
        day_of_week=2.0,
    )


@pytest.fixture
def sample_anomaly_features():
    return AnomalyFeatures(
        substation_id="SS002",
        timestamp="2025-01-01T03:00:00",
        input_mwh=500.0,
        output_mwh=300.0,   # 40% loss — highly anomalous
        residual_mwh=200.0,
        residual_percent=40.0,
        confidence_score=0.55,
        time_of_day_hour=3.0,
        day_of_week=6.0,
    )


@pytest.fixture
def engine():
    e = AnomalyDetectionEngine()
    e.initialize()
    return e


# ── Synthetic data generation ─────────────────────────────────────────────

def test_synthetic_data_shape():
    X, y = generate_synthetic_training_data(n_samples=200)
    assert X.shape == (200, 7), f"Expected (200,7), got {X.shape}"
    assert y.shape == (200,)


def test_synthetic_data_anomaly_rate():
    _, y = generate_synthetic_training_data(n_samples=1000, anomaly_rate=0.05)
    actual_rate = y.mean()
    # Should be close to 5% but due to shuffling, check within 3%
    assert 0.02 <= actual_rate <= 0.08, f"Anomaly rate {actual_rate:.3f} outside expected range"


def test_synthetic_data_physics_validity():
    X, _ = generate_synthetic_training_data(n_samples=200)
    # input_mwh (col 0) must be positive
    assert np.all(X[:, 0] > 0)
    # output_mwh (col 1) must be non-negative
    assert np.all(X[:, 1] >= 0)


def test_synthetic_data_no_nan():
    X, y = generate_synthetic_training_data(n_samples=500)
    assert not np.any(np.isnan(X)), "Training data contains NaN"
    assert not np.any(np.isnan(y))


# ── Feature vector ────────────────────────────────────────────────────────

def test_feature_vector_shape(sample_normal_features):
    vec = sample_normal_features.to_vector()
    assert vec.shape == (7,), f"Expected 7 features, got {vec.shape}"


def test_feature_vector_values(sample_normal_features):
    vec = sample_normal_features.to_vector()
    assert vec[0] == 500.0   # input_mwh
    assert vec[1] == 480.0   # output_mwh
    # hour normalized
    assert abs(vec[5] - 14.0/24.0) < 0.001


# ── Statistical detector ──────────────────────────────────────────────────

def test_statistical_detector_normal(sample_normal_features):
    det = StatisticalDetector()
    is_anomaly, score, reason = det.detect(sample_normal_features)
    assert isinstance(is_anomaly, bool)
    assert 0.0 <= score <= 1.0
    assert isinstance(reason, str)


def test_statistical_detector_high_loss():
    """High residual should be flagged"""
    det = StatisticalDetector()
    features = AnomalyFeatures(
        substation_id="SS_TEST", timestamp="2025-01-01T00:00:00",
        input_mwh=500.0, output_mwh=250.0,   # 50% loss
        residual_mwh=250.0, residual_percent=50.0,
        confidence_score=0.6,
    )
    is_anomaly, score, reason = det.detect(features)
    assert is_anomaly is True
    assert score > 0.3
    assert len(reason) > 0


def test_statistical_detector_negative_residual():
    """Output > input should be flagged as meter error"""
    det = StatisticalDetector()
    features = AnomalyFeatures(
        substation_id="SS_TEST", timestamp="2025-01-01T00:00:00",
        input_mwh=500.0, output_mwh=530.0,   # Output > input
        residual_mwh=-30.0, residual_percent=-6.0,
        confidence_score=0.7,
    )
    is_anomaly, score, reason = det.detect(features)
    assert is_anomaly is True
    assert "meter" in reason.lower() or "negative" in reason.lower() or "reversed" in reason.lower()


def test_statistical_z_score_detection():
    """After building history, Z-score outlier should be detected"""
    det = StatisticalDetector()
    # Feed normal history
    for _ in range(50):
        det.update_history(4.0)  # Normal ~4% loss
    # Now test an outlier
    outlier = AnomalyFeatures(
        substation_id="SS_TEST", timestamp="2025-01-01T00:00:00",
        input_mwh=500.0, output_mwh=350.0,
        residual_mwh=150.0, residual_percent=30.0,
        confidence_score=0.8,
    )
    is_anomaly, score, reason = det.detect(outlier)
    assert is_anomaly is True
    assert "z-score" in reason.lower() or "sigma" in reason.lower() or "baseline" in reason.lower()


# ── Isolation Forest ──────────────────────────────────────────────────────

@pytest.mark.skipif(not SKLEARN_AVAILABLE, reason="scikit-learn not installed")
def test_isolation_forest_trains():
    detector = IsolationForestDetector(n_estimators=10)  # Fast for tests
    X, _ = generate_synthetic_training_data(n_samples=200)
    stats = detector.train(X)
    assert detector.is_trained is True
    assert stats["n_samples"] == 200
    assert "trained_at" in stats


@pytest.mark.skipif(not SKLEARN_AVAILABLE, reason="scikit-learn not installed")
def test_isolation_forest_predict_returns_valid_scores():
    detector = IsolationForestDetector(n_estimators=10)
    X, _ = generate_synthetic_training_data(n_samples=200)
    detector.train(X)

    features = AnomalyFeatures(
        substation_id="SS001", timestamp="2025-01-01T12:00:00",
        input_mwh=500.0, output_mwh=480.0,
        residual_mwh=20.0, residual_percent=4.0,
        confidence_score=0.85,
    )
    is_anomaly, raw_score, normalized = detector.predict(features)
    assert isinstance(is_anomaly, bool)
    assert 0.0 <= normalized <= 1.0


# ── Full engine ───────────────────────────────────────────────────────────

def test_engine_initializes(engine):
    assert engine.is_ready is True


def test_engine_detects_normal(engine, sample_normal_features):
    result = engine.detect(sample_normal_features)
    assert hasattr(result, "is_anomaly")
    assert hasattr(result, "anomaly_score")
    assert 0.0 <= result.anomaly_score <= 1.0
    assert 0.0 <= result.confidence <= 1.0


def test_engine_flags_high_loss(engine):
    features = AnomalyFeatures(
        substation_id="SS_HIGH", timestamp="2025-01-01T00:00:00",
        input_mwh=500.0, output_mwh=250.0,   # 50% loss
        residual_mwh=250.0, residual_percent=50.0,
        confidence_score=0.5,
    )
    result = engine.detect(features)
    assert result.is_anomaly is True
    assert result.anomaly_score > 0.5


def test_engine_result_has_ethics_note(engine, sample_normal_features):
    """Every result must include ethics note"""
    result = engine.detect(sample_normal_features)
    assert len(result.ethics_note) > 10


def test_engine_result_has_recommended_action(engine, sample_anomaly_features):
    result = engine.detect(sample_anomaly_features)
    assert result.recommended_action is not None
    assert len(result.recommended_action) > 10


def test_engine_result_serializable(engine, sample_normal_features):
    """to_dict() must work without exceptions"""
    result = engine.detect(sample_normal_features)
    d = result.to_dict()
    assert "is_anomaly" in d
    assert "anomaly_score" in d
    assert "confidence" in d
    assert "ethics_note" in d
    assert "recommended_action" in d


def test_engine_model_info(engine):
    info = engine.get_model_info()
    assert "model_type" in info
    assert "ethical_constraints" in info
    assert info["ethical_constraints"]["individual_tracking"] is False
    assert info["ethical_constraints"]["accusation_output"] is False


def test_engine_high_confidence_not_set_without_signal(engine):
    """Low residual reading should not produce high confidence anomaly"""
    features = AnomalyFeatures(
        substation_id="SS001", timestamp="2025-01-01T12:00:00",
        input_mwh=500.0, output_mwh=488.0,   # 2.4% loss — well within normal
        residual_mwh=12.0, residual_percent=2.4,
        confidence_score=0.92,
    )
    result = engine.detect(features)
    # Should NOT be flagged as anomaly with high confidence
    if result.is_anomaly:
        assert result.confidence < 0.6, "Should not have high confidence for normal reading"
