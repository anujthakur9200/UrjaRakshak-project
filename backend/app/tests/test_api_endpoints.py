"""
API Integration Tests
======================
Tests API request/response contracts without a real DB.
Uses FastAPI TestClient with dependency overrides.

Run: pytest backend/app/tests/ -v

Author: Vipin Baniya
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from app.core.physics_engine import PhysicsEngine, BalanceStatus, PhysicsResult, ComponentLoss


SAMPLE_ANALYSIS_REQUEST = {
    "substation_id": "SS_TEST_001",
    "input_energy_mwh": 1000.0,
    "output_energy_mwh": 975.0,
    "time_window_hours": 24.0,
    "components": [
        {
            "component_id": "TX001",
            "component_type": "transformer",
            "rated_capacity_kva": 1000,
            "efficiency_rating": 0.98,
            "age_years": 5,
        }
    ],
}


def make_mock_physics_result():
    return PhysicsResult(
        balance_status=BalanceStatus.BALANCED,
        input_energy_mwh=1000.0,
        output_energy_mwh=975.0,
        expected_technical_loss_mwh=15.0,
        actual_loss_mwh=25.0,
        residual_mwh=10.0,
        residual_percentage=1.0,
        confidence_score=0.85,
        uncertainty_mwh=5.0,
        measurement_quality="high",
        component_losses=[
            ComponentLoss(
                component_id="TX001",
                component_type="transformer",
                rated_power_kva=1000,
                expected_loss_mwh=15.0,
                loss_percentage=1.5,
                computation_method="transformer_physics_model",
            )
        ],
        timestamp="2025-01-01T00:00:00",
        temperature_celsius=25.0,
        physical_explanation="Normal operation.",
    )


# ── Physics engine unit tests (no FastAPI) ────────────────────────────────

def test_physics_engine_direct():
    """Test physics engine directly without API"""
    engine = PhysicsEngine(min_confidence=0.3, strict_mode=False)
    from app.core.physics_engine import GridComponent
    components = [
        GridComponent(
            component_id="TX001",
            component_type="transformer",
            rated_capacity_kva=1000,
            efficiency_rating=0.98,
        )
    ]
    result = engine.validate_energy_conservation(
        input_energy_mwh=1000.0,
        output_energy_mwh=975.0,
        components=components,
    )
    assert result is not None
    d = result.to_dict()
    assert "status" in d
    assert "energy_balance" in d
    assert d["energy_balance"]["input_mwh"] == 1000.0
    assert d["energy_balance"]["output_mwh"] == 975.0


def test_physics_result_to_dict_complete():
    result = make_mock_physics_result()
    d = result.to_dict()
    required_keys = ["status", "energy_balance", "confidence", "component_losses", "physical_explanation"]
    for k in required_keys:
        assert k in d, f"Missing key: {k}"


def test_physics_result_energy_balance_fields():
    result = make_mock_physics_result()
    d = result.to_dict()
    balance = d["energy_balance"]
    assert "input_mwh" in balance
    assert "output_mwh" in balance
    assert "residual_mwh" in balance
    assert "residual_percentage" in balance


def test_physics_result_confidence_fields():
    result = make_mock_physics_result()
    d = result.to_dict()
    conf = d["confidence"]
    assert "score" in conf
    assert "measurement_quality" in conf
    assert 0.0 <= conf["score"] <= 1.0


# ── Request validation ────────────────────────────────────────────────────

def test_analysis_request_valid_structure():
    """Check that our sample request matches expected Pydantic schema"""
    from app.api.v1.analysis import AnalysisRequest
    req = AnalysisRequest(**SAMPLE_ANALYSIS_REQUEST)
    assert req.substation_id == "SS_TEST_001"
    assert req.input_energy_mwh == 1000.0
    assert len(req.components) == 1


def test_analysis_request_rejects_zero_input():
    from app.api.v1.analysis import AnalysisRequest
    import pydantic
    with pytest.raises((pydantic.ValidationError, ValueError)):
        AnalysisRequest(
            substation_id="SS001",
            input_energy_mwh=0.0,   # Must be > 0
            output_energy_mwh=950.0,
            components=[{"component_id": "T1", "component_type": "transformer", "rated_capacity_kva": 100}],
        )


def test_analysis_request_rejects_empty_components():
    from app.api.v1.analysis import AnalysisRequest
    import pydantic
    with pytest.raises((pydantic.ValidationError, ValueError)):
        AnalysisRequest(
            substation_id="SS001",
            input_energy_mwh=1000.0,
            output_energy_mwh=950.0,
            components=[],   # min_length=1
        )
