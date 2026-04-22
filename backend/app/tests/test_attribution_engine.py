"""
Tests for Loss Attribution Engine
===================================
Run: pytest backend/app/tests/ -v

Author: Vipin Baniya
"""
import pytest
from app.core.attribution_engine import AttributionEngine, LossAttributionEngine, LossCause


@pytest.fixture
def engine():
    return AttributionEngine(conservative_mode=True)


@pytest.fixture
def permissive_engine():
    return AttributionEngine(conservative_mode=False)


def test_engine_initializes(engine):
    assert engine is not None
    assert engine.conservative_mode is True


def test_permissive_engine_initializes(permissive_engine):
    assert permissive_engine.conservative_mode is False


def test_conservative_threshold_higher():
    """Conservative mode should use stricter thresholds than permissive"""
    conservative = AttributionEngine(conservative_mode=True)
    permissive = AttributionEngine(conservative_mode=False)
    # In conservative mode, accusation threshold should be higher
    assert conservative.conservative_threshold >= permissive.conservative_threshold


def test_loss_cause_enum_values():
    """All expected loss causes should be present"""
    causes = [c.value for c in LossCause]
    assert "technical_expected" in causes
    assert "meter_malfunction" in causes
    assert "infrastructure_degradation" in causes


def test_attribution_engine_is_loss_attribution_engine():
    """AttributionEngine should be a subclass of LossAttributionEngine"""
    e = AttributionEngine(conservative_mode=True)
    assert isinstance(e, LossAttributionEngine)
