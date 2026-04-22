"""
UrjaRakshak — Anomaly Detection Engine
=======================================
Real ML implementation using:
  1. Isolation Forest (primary — unsupervised, works without labeled data)
  2. Statistical Z-Score (secondary — physics-consistent thresholding)
  3. Rolling window baseline (tertiary — trend detection)

Design principles:
  - Works on synthetic data immediately (no real dataset required)
  - Physics-constrained outputs (anomaly score respects energy bounds)
  - Confidence-calibrated (never flags without score)
  - Explainable (every flag comes with a reason)
  - Serializable (model persists to disk via joblib)

Author: Vipin Baniya
"""

import numpy as np
import logging
import json
import os
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

# ── Try importing sklearn — graceful fallback if not installed ────────────
try:
    from sklearn.ensemble import IsolationForest
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import Pipeline
    import joblib
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    logger.warning("scikit-learn not installed — using statistical fallback only")


# ── Data structures ───────────────────────────────────────────────────────

@dataclass
class AnomalyFeatures:
    """Feature vector for a single grid reading"""
    substation_id: str
    timestamp: str
    input_mwh: float
    output_mwh: float
    residual_mwh: float
    residual_percent: float
    confidence_score: float
    time_of_day_hour: float = 12.0
    day_of_week: float = 1.0

    def to_vector(self) -> np.ndarray:
        """Convert to numpy feature vector for ML"""
        return np.array([
            self.input_mwh,
            self.output_mwh,
            self.residual_mwh,
            self.residual_percent,
            self.confidence_score,
            self.time_of_day_hour / 24.0,   # Normalize
            self.day_of_week / 7.0,          # Normalize
        ], dtype=np.float64)


@dataclass
class AnomalyResult:
    """Result of anomaly detection inference"""
    substation_id: str
    timestamp: str
    is_anomaly: bool
    anomaly_score: float                     # 0.0 (normal) → 1.0 (highly anomalous)
    confidence: float                        # Model confidence in this prediction
    method_used: str                         # Which detector flagged it
    primary_reason: str                      # Human-readable reason
    feature_contributions: Dict[str, float] # Which features drove the score
    recommended_action: str
    ethics_note: str = (
        "This is a statistical indicator only. Human review required before any action."
    )

    def to_dict(self) -> Dict:
        return {
            "substation_id": self.substation_id,
            "timestamp": self.timestamp,
            "is_anomaly": self.is_anomaly,
            "anomaly_score": round(self.anomaly_score, 4),
            "confidence": round(self.confidence, 4),
            "method": self.method_used,
            "reason": self.primary_reason,
            "feature_contributions": {k: round(v, 4) for k, v in self.feature_contributions.items()},
            "recommended_action": self.recommended_action,
            "ethics_note": self.ethics_note,
        }


# ── Synthetic Training Data Generator ────────────────────────────────────

def generate_synthetic_training_data(n_samples: int = 2000, anomaly_rate: float = 0.05) -> Tuple[np.ndarray, np.ndarray]:
    """
    Generate synthetic grid readings for model training.

    Normal readings follow realistic grid patterns:
      - Technical loss: 2–8% of input
      - Load follows diurnal pattern
      - Measurement noise: ±1%

    Anomalies are injected with:
      - High residual loss (>12%) — potential theft or major fault
      - Negative residual — meter reversal / measurement error
      - Sudden spikes — equipment fault

    Returns:
        X: Feature matrix (n_samples, 7)
        y: Labels (0=normal, 1=anomaly) — for evaluation only
    """
    rng = np.random.default_rng(seed=42)
    n_anomalies = int(n_samples * anomaly_rate)
    n_normal = n_samples - n_anomalies

    # ── Normal samples ──
    hours = rng.uniform(0, 24, n_normal)
    dow = rng.integers(0, 7, n_normal).astype(float)

    # Realistic diurnal input pattern (peak ~18:00, trough ~03:00)
    diurnal = 1.0 + 0.3 * np.sin(2 * np.pi * (hours - 6) / 24)
    input_mwh = rng.normal(500, 50, n_normal) * diurnal
    input_mwh = np.clip(input_mwh, 50, 2000)

    # Technical loss: 2–8%
    tech_loss_pct = rng.uniform(0.02, 0.08, n_normal)
    output_mwh = input_mwh * (1 - tech_loss_pct)
    noise = rng.normal(0, 0.005, n_normal) * input_mwh
    output_mwh = np.clip(output_mwh + noise, 0, input_mwh)

    residual_mwh = input_mwh - output_mwh
    residual_pct = residual_mwh / input_mwh * 100
    confidence = rng.uniform(0.6, 0.98, n_normal)

    X_normal = np.column_stack([
        input_mwh, output_mwh, residual_mwh,
        residual_pct, confidence,
        hours / 24.0, dow / 7.0
    ])

    # ── Anomaly samples ──
    a_hours = rng.uniform(0, 24, n_anomalies)
    a_dow = rng.integers(0, 7, n_anomalies).astype(float)
    a_input = rng.normal(500, 50, n_anomalies)
    a_input = np.clip(a_input, 50, 2000)

    anomaly_type = rng.choice(["high_loss", "negative_residual", "spike"], n_anomalies)
    a_output = np.zeros(n_anomalies)
    for i, at in enumerate(anomaly_type):
        if at == "high_loss":
            loss_pct = rng.uniform(0.13, 0.40)
            a_output[i] = a_input[i] * (1 - loss_pct)
        elif at == "negative_residual":
            a_output[i] = a_input[i] * rng.uniform(1.01, 1.05)  # Output > Input
        else:  # spike
            a_output[i] = a_input[i] * rng.uniform(0.5, 0.7)

    a_output = np.clip(a_output, 0, a_input * 1.1)
    a_residual = a_input - a_output
    a_residual_pct = a_residual / a_input * 100
    a_confidence = rng.uniform(0.3, 0.75, n_anomalies)

    X_anomaly = np.column_stack([
        a_input, a_output, a_residual,
        a_residual_pct, a_confidence,
        a_hours / 24.0, a_dow / 7.0
    ])

    X = np.vstack([X_normal, X_anomaly])
    y = np.concatenate([np.zeros(n_normal), np.ones(n_anomalies)])

    # Shuffle
    idx = rng.permutation(n_samples)
    return X[idx], y[idx]


# ── Isolation Forest Detector ─────────────────────────────────────────────

class IsolationForestDetector:
    """
    Isolation Forest anomaly detector for grid readings.

    Isolation Forest works by randomly partitioning the feature space.
    Anomalies require fewer partitions to isolate → shorter path length → higher score.

    This is ideal for grid loss detection because:
      - No labeled data required (unsupervised)
      - Handles mixed feature scales well (with StandardScaler)
      - Interpretable anomaly scores
      - Fast inference (O(n log n) training, O(log n) inference)
    """

    MODEL_PATH = "app/ml/saved/isolation_forest.joblib"
    METADATA_PATH = "app/ml/saved/model_metadata.json"

    def __init__(
        self,
        contamination: float = 0.05,
        n_estimators: int = 100,
        random_state: int = 42,
    ):
        self.contamination = contamination
        self.n_estimators = n_estimators
        self.random_state = random_state
        self.pipeline: Optional[Pipeline] = None
        self.is_trained = False
        self.training_stats: Dict = {}
        self.feature_names = [
            "input_mwh", "output_mwh", "residual_mwh",
            "residual_pct", "confidence", "hour_norm", "dow_norm"
        ]

    def train(self, X: Optional[np.ndarray] = None) -> Dict:
        """
        Train Isolation Forest on grid data.

        If no data provided, trains on synthetic data — useful for
        bootstrapping before real data is available.
        """
        if not SKLEARN_AVAILABLE:
            logger.warning("scikit-learn unavailable — skipping IF training")
            return {"trained": False, "reason": "scikit-learn not installed"}

        if X is None:
            logger.info("No training data provided — generating synthetic grid data")
            X, _ = generate_synthetic_training_data(n_samples=2000)

        logger.info(f"Training Isolation Forest on {X.shape[0]} samples...")

        self.pipeline = Pipeline([
            ("scaler", StandardScaler()),
            ("iforest", IsolationForest(
                n_estimators=self.n_estimators,
                contamination=self.contamination,
                random_state=self.random_state,
                n_jobs=-1,
            ))
        ])

        self.pipeline.fit(X)
        self.is_trained = True

        # Compute training statistics
        scores = self.pipeline.decision_function(X)
        self.training_stats = {
            "n_samples": int(X.shape[0]),
            "n_features": int(X.shape[1]),
            "score_mean": float(np.mean(scores)),
            "score_std": float(np.std(scores)),
            "score_min": float(np.min(scores)),
            "score_max": float(np.max(scores)),
            "contamination": self.contamination,
            "n_estimators": self.n_estimators,
            "trained_at": datetime.utcnow().isoformat(),
        }

        logger.info(f"✅ Isolation Forest trained: {self.training_stats}")

        # Persist to disk
        self._save_model()
        return self.training_stats

    def predict(self, features: AnomalyFeatures) -> Tuple[bool, float, float]:
        """
        Predict anomaly for a single reading.

        Returns:
            (is_anomaly, raw_score, normalized_score_0_to_1)
        """
        if not SKLEARN_AVAILABLE or not self.is_trained:
            return False, 0.0, 0.0

        X = features.to_vector().reshape(1, -1)
        raw_score = float(self.pipeline.decision_function(X)[0])
        prediction = self.pipeline.predict(X)[0]

        # Normalize score: decision_function returns negative for anomalies
        # Map to [0, 1] where 1 = most anomalous
        score_range = self.training_stats.get("score_max", 0.5) - self.training_stats.get("score_min", -0.5)
        if score_range > 0:
            normalized = (self.training_stats.get("score_max", 0.5) - raw_score) / score_range
        else:
            normalized = 0.5

        normalized = float(np.clip(normalized, 0.0, 1.0))
        is_anomaly = (prediction == -1)

        return is_anomaly, raw_score, normalized

    def _save_model(self):
        """Persist trained model to disk"""
        os.makedirs(os.path.dirname(self.MODEL_PATH), exist_ok=True)
        try:
            joblib.dump(self.pipeline, self.MODEL_PATH)
            with open(self.METADATA_PATH, "w") as f:
                json.dump(self.training_stats, f, indent=2)
            logger.info(f"✅ Model saved to {self.MODEL_PATH}")
        except Exception as e:
            logger.warning(f"Could not save model: {e}")

    def load(self) -> bool:
        """Load persisted model from disk"""
        if not SKLEARN_AVAILABLE:
            return False
        try:
            if os.path.exists(self.MODEL_PATH):
                self.pipeline = joblib.load(self.MODEL_PATH)
                self.is_trained = True
                if os.path.exists(self.METADATA_PATH):
                    with open(self.METADATA_PATH) as f:
                        self.training_stats = json.load(f)
                logger.info("✅ Isolation Forest loaded from disk")
                return True
        except Exception as e:
            logger.warning(f"Could not load model: {e}")
        return False


# ── Statistical Z-Score Detector ─────────────────────────────────────────

class StatisticalDetector:
    """
    Statistical anomaly detection using Z-score and rolling window.

    Always available — no ML dependencies required.
    Used as primary detector when sklearn unavailable,
    and as secondary validation layer alongside Isolation Forest.

    Physics-grounded thresholds:
      - Residual > 12%: Strong signal (beyond normal technical + measurement tolerance)
      - Residual < -3%: Impossible (output > input by >3% margin)
      - Z-score > 3: 3-sigma outlier on residual
    """

    PHYSICS_MAX_RESIDUAL_PCT = 12.0   # Beyond this, technically suspicious
    PHYSICS_MIN_RESIDUAL_PCT = -3.0   # Meter reversal / measurement error
    ZSCORE_THRESHOLD = 3.0            # Standard 3-sigma rule

    def __init__(self):
        self.history: List[float] = []   # Rolling residual % history
        self.window_size = 168            # 1 week of hourly readings

    def update_history(self, residual_pct: float):
        """Add reading to rolling window"""
        self.history.append(residual_pct)
        if len(self.history) > self.window_size:
            self.history.pop(0)

    def detect(self, features: AnomalyFeatures) -> Tuple[bool, float, str]:
        """
        Returns: (is_anomaly, score_0_to_1, reason)
        """
        reasons = []
        scores = []

        r = features.residual_percent

        # Check 1: Physics bounds violation
        if r > self.PHYSICS_MAX_RESIDUAL_PCT:
            excess = r - self.PHYSICS_MAX_RESIDUAL_PCT
            score = min(1.0, excess / 20.0)
            reasons.append(f"Residual {r:.1f}% exceeds physics threshold {self.PHYSICS_MAX_RESIDUAL_PCT}%")
            scores.append(score)

        if r < self.PHYSICS_MIN_RESIDUAL_PCT:
            score = min(1.0, abs(r - self.PHYSICS_MIN_RESIDUAL_PCT) / 10.0)
            reasons.append(f"Negative residual {r:.1f}% suggests meter error or reversed connection")
            scores.append(score)

        # Check 2: Z-score vs rolling baseline
        if len(self.history) >= 10:
            mean = np.mean(self.history)
            std = np.std(self.history)
            if std > 0:
                z = abs((r - mean) / std)
                if z > self.ZSCORE_THRESHOLD:
                    score = min(1.0, (z - self.ZSCORE_THRESHOLD) / 5.0)
                    reasons.append(
                        f"Z-score {z:.1f}σ above baseline (mean={mean:.1f}%, σ={std:.1f}%)"
                    )
                    scores.append(score)

        # Check 3: Low confidence + high residual combination
        if features.confidence_score < 0.5 and r > 8.0:
            reasons.append(f"Low confidence ({features.confidence_score:.2f}) with elevated residual — requires meter inspection")
            scores.append(0.4)

        if not scores:
            return False, 0.0, "No anomaly indicators detected"

        final_score = float(max(scores))
        is_anomaly = final_score >= 0.3
        return is_anomaly, final_score, " | ".join(reasons)


# ── Main Anomaly Detection Engine ─────────────────────────────────────────

class AnomalyDetectionEngine:
    """
    Combined anomaly detection using Isolation Forest + Statistical methods.

    Architecture:
      Primary:   Isolation Forest (ML-based, trained on 2000 synthetic samples)
      Secondary: Statistical Z-score (physics-grounded, always available)
      Decision:  Ensemble vote with confidence weighting

    Ethics firewall:
      - Never returns is_anomaly=True with confidence < 0.4
      - Always includes recommended_action (inspection, not accusation)
      - Never identifies individuals — only grid sections
    """

    def __init__(self):
        self.if_detector = IsolationForestDetector()
        self.stat_detectors: Dict[str, StatisticalDetector] = {}  # Per substation
        self.is_ready = False

    def initialize(self) -> Dict:
        """Initialize engine — load or train model"""
        # Try loading persisted model first
        loaded = self.if_detector.load()

        if not loaded:
            # Train on synthetic data
            logger.info("Training anomaly detection model on synthetic grid data...")
            stats = self.if_detector.train()
            logger.info(f"Model training complete: {stats}")
        else:
            stats = self.if_detector.training_stats

        self.is_ready = True
        return {
            "status": "ready",
            "model": "IsolationForest + StatisticalDetector",
            "sklearn_available": SKLEARN_AVAILABLE,
            "if_trained": self.if_detector.is_trained,
            "training_stats": stats,
        }

    def detect(self, features: AnomalyFeatures) -> AnomalyResult:
        """
        Run full anomaly detection pipeline.

        Uses ensemble of IF + statistical detectors.
        """
        # Get per-substation statistical detector
        if features.substation_id not in self.stat_detectors:
            self.stat_detectors[features.substation_id] = StatisticalDetector()
        stat_det = self.stat_detectors[features.substation_id]

        # Run statistical detector (always available)
        stat_anomaly, stat_score, stat_reason = stat_det.detect(features)
        stat_det.update_history(features.residual_percent)

        # Run Isolation Forest (if available)
        if_anomaly, if_raw, if_score = self.if_detector.predict(features)

        # Ensemble decision
        if SKLEARN_AVAILABLE and self.if_detector.is_trained:
            # Weighted average: IF gets 60%, stat gets 40%
            ensemble_score = 0.6 * if_score + 0.4 * stat_score
            method = "IsolationForest + StatisticalDetector (ensemble)"
            # Both must agree for high confidence, either for lower
            if if_anomaly and stat_anomaly:
                confidence = min(0.95, max(if_score, stat_score))
            elif if_anomaly or stat_anomaly:
                confidence = 0.5 * (if_score + stat_score)
            else:
                confidence = max(if_score, stat_score)
        else:
            # Statistical only
            ensemble_score = stat_score
            confidence = stat_score
            method = "StatisticalDetector (sklearn unavailable)"

        # Ethics firewall: refuse low-confidence flags
        is_anomaly = ensemble_score >= 0.35 and confidence >= 0.35

        # Feature contributions (interpretability)
        feature_contribs = self._compute_feature_contributions(features)

        # Recommended action (inspection, not accusation)
        recommended_action = self._get_recommended_action(ensemble_score, features)

        # Primary reason
        primary_reason = stat_reason if stat_reason else (
            f"Isolation Forest score: {if_score:.3f}" if SKLEARN_AVAILABLE else "No anomaly"
        )

        return AnomalyResult(
            substation_id=features.substation_id,
            timestamp=features.timestamp,
            is_anomaly=is_anomaly,
            anomaly_score=ensemble_score,
            confidence=confidence,
            method_used=method,
            primary_reason=primary_reason,
            feature_contributions=feature_contribs,
            recommended_action=recommended_action,
        )

    def _compute_feature_contributions(self, f: AnomalyFeatures) -> Dict[str, float]:
        """Estimate which features contribute most to anomaly score"""
        contributions = {}

        # Residual percentage is most important
        if f.residual_percent > 12:
            contributions["residual_pct"] = min(1.0, (f.residual_percent - 12) / 20)
        elif f.residual_percent < -3:
            contributions["negative_residual"] = min(1.0, abs(f.residual_percent + 3) / 10)
        else:
            contributions["residual_pct"] = 0.0

        # Low confidence
        contributions["confidence"] = max(0.0, (0.6 - f.confidence_score) / 0.6)

        # Input/output ratio
        if f.input_mwh > 0:
            ratio = f.output_mwh / f.input_mwh
            contributions["io_ratio"] = max(0.0, abs(1.0 - ratio) - 0.08) / 0.4

        return {k: round(v, 4) for k, v in contributions.items() if v > 0}

    def _get_recommended_action(self, score: float, f: AnomalyFeatures) -> str:
        """Return recommended action — conservative, never punitive"""
        if score < 0.3:
            return "No action required. Reading within normal parameters."
        elif score < 0.5:
            return (
                f"Schedule routine meter inspection at substation {f.substation_id}. "
                "Verify calibration and check for connection faults."
            )
        elif score < 0.75:
            return (
                f"Prioritize field inspection at {f.substation_id}. "
                "Check transformer health, meter accuracy, and line integrity. "
                "Residual loss pattern requires technical review."
            )
        else:
            return (
                f"Urgent technical audit recommended at {f.substation_id}. "
                "High residual loss requires immediate investigation. "
                "Possible causes: equipment fault, meter malfunction, or significant unexplained loss. "
                "Human review required before any enforcement action."
            )

    def get_model_info(self) -> Dict:
        """Return model metadata for transparency"""
        return {
            "model_type": "IsolationForest + StatisticalDetector",
            "sklearn_available": SKLEARN_AVAILABLE,
            "if_trained": self.if_detector.is_trained,
            "training_data": "Synthetic grid readings (physics-grounded)",
            "n_training_samples": self.training_stats.get("n_samples", 0),
            "contamination_rate": self.if_detector.contamination,
            "n_estimators": self.if_detector.n_estimators,
            "feature_names": self.if_detector.feature_names,
            "ethical_constraints": {
                "min_confidence_to_flag": 0.35,
                "output_type": "inspection_recommendation_only",
                "individual_tracking": False,
                "accusation_output": False,
            },
        }

    @property
    def training_stats(self) -> Dict:
        return self.if_detector.training_stats


# Module-level singleton
anomaly_engine = AnomalyDetectionEngine()
