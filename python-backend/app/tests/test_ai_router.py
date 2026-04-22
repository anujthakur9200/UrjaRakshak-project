"""
AI Router Tests — UrjaRakshak python-backend
=============================================
Covers:
  - Complexity scoring (preprocessor)
  - Routing decision logic (all branches)
  - Fallback chain behaviour
  - OpenAI budget tracking
  - Model handler interfaces (mocked)
"""

from __future__ import annotations

import math
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.ai.preprocessor import DataComplexity, compute_complexity
from app.ai.config import OpenAIBudgetTracker
from app.ai.model_handlers import RuleBasedHandler
from app.ai.ai_router import AIRouter, RoutingResult


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────


def _make_handler(name: str, result: dict | None = None, raise_exc: Exception | None = None):
    """Return a mock BaseModelHandler."""
    handler = MagicMock()
    handler.name = name
    if raise_exc is not None:
        handler.analyse = AsyncMock(side_effect=raise_exc)
    else:
        handler.analyse = AsyncMock(
            return_value=result
            or {
                "summary": f"Result from {name}",
                "key_findings": [],
                "recommended_actions": [],
                "risk_level": "low",
                "model_used": name,
                "handler": name,
            }
        )
    return handler


def _rows(n: int, cols: int = 3, anomaly_cols: int = 0) -> list[dict]:
    """Generate *n* synthetic rows with *cols* numeric columns."""
    base = {f"col_{i}": float(i + 1) for i in range(cols)}
    rows = [{**base} for _ in range(n)]
    # Inject obvious anomalies (None values) in the first *anomaly_cols* rows
    for i in range(min(anomaly_cols, n)):
        rows[i]["col_0"] = None
    return rows


# ─────────────────────────────────────────────────────────────────────
# Preprocessor tests
# ─────────────────────────────────────────────────────────────────────


class TestComputeComplexity:
    def test_empty_dataset(self):
        result = compute_complexity([])
        assert result.num_rows == 0
        assert result.num_columns == 0
        assert result.anomaly_count == 0
        assert result.complexity_score == 0.0

    def test_single_dict_treated_as_one_row(self):
        result = compute_complexity({"a": 1, "b": 2})
        assert result.num_rows == 1
        assert result.num_columns == 2

    def test_complexity_formula(self):
        rows = _rows(100, cols=5, anomaly_cols=0)
        result = compute_complexity(rows)
        expected = (100 * 0.4) + (5 * 0.2) + (result.anomaly_count * 0.4)
        assert math.isclose(result.complexity_score, expected, rel_tol=1e-3)

    def test_missing_values_counted_as_anomalies(self):
        rows = [{"a": 1, "b": None}, {"a": 2, "b": 3}]
        result = compute_complexity(rows)
        assert result.missing_value_count == 1
        assert result.anomaly_count >= 1

    def test_all_clean_data_zero_anomalies(self):
        rows = _rows(50, cols=4, anomaly_cols=0)
        result = compute_complexity(rows)
        assert result.anomaly_count == 0

    def test_numeric_columns_detected(self):
        rows = [{"name": "abc", "value": 1.5, "count": 3}]
        result = compute_complexity(rows)
        assert "value" in result.numeric_columns
        assert "count" in result.numeric_columns
        assert "name" not in result.numeric_columns

    def test_extreme_outlier_detected(self):
        # All values are ~1.0 except one extreme outlier
        rows = [{"x": 1.0}] * 20 + [{"x": 1_000_000.0}]
        result = compute_complexity(rows)
        assert result.anomaly_count >= 1

    def test_to_dict_keys(self):
        result = compute_complexity(_rows(10, cols=2))
        d = result.to_dict()
        for key in (
            "num_rows",
            "num_columns",
            "anomaly_count",
            "complexity_score",
            "column_names",
            "numeric_columns",
            "missing_value_count",
            "notes",
        ):
            assert key in d


# ─────────────────────────────────────────────────────────────────────
# OpenAI budget tracker tests
# ─────────────────────────────────────────────────────────────────────


class TestOpenAIBudgetTracker:
    def test_initial_state(self):
        tracker = OpenAIBudgetTracker(monthly_quota=2)
        assert tracker.calls_used == 0
        assert tracker.calls_remaining == 2
        assert tracker.quota_available is True

    def test_record_call_decrements_remaining(self):
        tracker = OpenAIBudgetTracker(monthly_quota=2)
        tracker.record_call()
        assert tracker.calls_used == 1
        assert tracker.calls_remaining == 1
        assert tracker.quota_available is True

    def test_quota_exhausted_after_max_calls(self):
        tracker = OpenAIBudgetTracker(monthly_quota=2)
        tracker.record_call()
        tracker.record_call()
        assert tracker.quota_available is False
        assert tracker.calls_remaining == 0

    def test_calls_remaining_never_negative(self):
        tracker = OpenAIBudgetTracker(monthly_quota=1)
        tracker.record_call()
        tracker.record_call()  # over quota
        assert tracker.calls_remaining == 0

    def test_status_dict_keys(self):
        tracker = OpenAIBudgetTracker(monthly_quota=2)
        status = tracker.status()
        assert "monthly_quota" in status
        assert "calls_used" in status
        assert "calls_remaining" in status
        assert "quota_available" in status

    def test_zero_quota_always_unavailable(self):
        tracker = OpenAIBudgetTracker(monthly_quota=0)
        assert tracker.quota_available is False


# ─────────────────────────────────────────────────────────────────────
# Rule-based handler tests
# ─────────────────────────────────────────────────────────────────────


class TestRuleBasedHandler:
    @pytest.mark.asyncio
    async def test_returns_required_keys(self):
        handler = RuleBasedHandler()
        result = await handler.analyse(
            {
                "balance_status": "balanced",
                "residual_pct": 0.5,
                "confidence_score": 0.9,
                "hypotheses": [],
            }
        )
        for key in ("summary", "key_findings", "recommended_actions", "risk_level", "model_used"):
            assert key in result

    @pytest.mark.asyncio
    async def test_risk_levels(self):
        handler = RuleBasedHandler()
        mapping = {
            "balanced": "low",
            "minor_imbalance": "medium",
            "significant_imbalance": "high",
            "critical_imbalance": "critical",
            "uncertain": "medium",
        }
        for balance_status, expected_risk in mapping.items():
            result = await handler.analyse(
                {"balance_status": balance_status, "residual_pct": 5.0, "confidence_score": 0.8}
            )
            assert result["risk_level"] == expected_risk, (
                f"balance_status={balance_status} should give risk={expected_risk}"
            )

    @pytest.mark.asyncio
    async def test_high_residual_adds_urgent_action(self):
        handler = RuleBasedHandler()
        result = await handler.analyse(
            {"balance_status": "critical_imbalance", "residual_pct": 15.0, "confidence_score": 0.7}
        )
        actions_text = " ".join(result["recommended_actions"])
        assert "urgent" in actions_text.lower() or "10%" in actions_text

    @pytest.mark.asyncio
    async def test_model_used_is_rule_based(self):
        handler = RuleBasedHandler()
        result = await handler.analyse({"balance_status": "unknown"})
        assert result["model_used"] == "rule_based"


# ─────────────────────────────────────────────────────────────────────
# AI Router — routing decision tests
# ─────────────────────────────────────────────────────────────────────


class TestAIRouterDecisions:
    """Tests for the routing decision logic using mocked handlers."""

    def _make_router(self, openai_quota: int = 2):
        """Create a router with all-mock handlers and controlled quota."""
        rule = _make_handler("rule_based")
        ollama = _make_handler("ollama")
        hf = _make_handler("huggingface")
        openai = _make_handler("openai")
        tracker = OpenAIBudgetTracker(monthly_quota=openai_quota)
        router = AIRouter(
            rule_handler=rule,
            ollama_handler=ollama,
            hf_handler=hf,
            openai_handler=openai,
        )
        # Patch the module-level budget_tracker used inside _select_chain
        router._tracker = tracker  # not used directly; patch module attr instead
        return router, rule, ollama, hf, openai, tracker

    @pytest.mark.asyncio
    async def test_zero_anomalies_uses_rule_based(self):
        rule = _make_handler("rule_based")
        ollama = _make_handler("ollama")
        hf = _make_handler("huggingface")
        openai = _make_handler("openai")
        router = AIRouter(
            rule_handler=rule, ollama_handler=ollama, hf_handler=hf, openai_handler=openai
        )
        # 100 rows, 5 cols, 0 anomalies → score = 41 (< 1000)
        data = _rows(100, cols=5, anomaly_cols=0)
        result = await router.route(data)
        assert result.handler_used == "rule_based"
        rule.analyse.assert_awaited_once()
        ollama.analyse.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_low_complexity_uses_rule_based(self):
        rule = _make_handler("rule_based")
        ollama = _make_handler("ollama")
        router = AIRouter(rule_handler=rule, ollama_handler=ollama)
        # score < 1000
        data = _rows(10, cols=3, anomaly_cols=0)
        result = await router.route(data)
        assert result.handler_used == "rule_based"

    @pytest.mark.asyncio
    async def test_moderate_complexity_uses_ollama(self):
        """Score in [1000, 5000) with anomalies > 0 → Ollama."""
        rule = _make_handler("rule_based")
        ollama = _make_handler("ollama")
        hf = _make_handler("huggingface")
        openai = _make_handler("openai")
        router = AIRouter(
            rule_handler=rule, ollama_handler=ollama, hf_handler=hf, openai_handler=openai
        )

        # Use _select_chain directly with a crafted DataComplexity to avoid
        # relying on the preprocessor producing exactly the right score.
        from app.ai.preprocessor import DataComplexity

        comp = DataComplexity(
            num_rows=2000,
            num_columns=5,
            anomaly_count=500,  # ensures anomaly_count > 0
            complexity_score=2000.0,  # in [1000, 5000)
        )
        with patch("app.ai.ai_router.budget_tracker") as mock_tracker:
            mock_tracker.quota_available = True
            mock_tracker.calls_remaining = 2
            chain, decision = router._select_chain(comp)

        assert chain[0].name == "ollama", f"Expected ollama first, got {chain[0].name}"

    @pytest.mark.asyncio
    async def test_high_complexity_uses_ollama_then_hf_fallback(self):
        rule = _make_handler("rule_based")
        ollama = _make_handler("ollama", raise_exc=RuntimeError("ollama down"))
        hf = _make_handler("huggingface")
        openai = _make_handler("openai")

        with patch("app.ai.ai_router.budget_tracker") as mock_tracker:
            mock_tracker.quota_available = True
            mock_tracker.calls_remaining = 2

            router = AIRouter(
                rule_handler=rule, ollama_handler=ollama, hf_handler=hf, openai_handler=openai
            )
            # Craft data with score in [5000, 8000) by using a dict that bypasses
            # the preprocessor — instead test _select_chain directly
            from app.ai.preprocessor import DataComplexity

            comp = DataComplexity(
                num_rows=10000,
                num_columns=5,
                anomaly_count=100,
                complexity_score=6000.0,
            )
            chain, decision = router._select_chain(comp)
            # Should be ollama → hf → rule
            assert chain[0].name == "ollama"
            assert chain[1].name == "huggingface"
            assert chain[2].name == "rule_based"

    @pytest.mark.asyncio
    async def test_very_high_complexity_with_quota_uses_openai(self):
        with patch("app.ai.ai_router.budget_tracker") as mock_tracker:
            mock_tracker.quota_available = True
            mock_tracker.calls_remaining = 1

            rule = _make_handler("rule_based")
            ollama = _make_handler("ollama")
            hf = _make_handler("huggingface")
            openai = _make_handler("openai")
            router = AIRouter(
                rule_handler=rule, ollama_handler=ollama, hf_handler=hf, openai_handler=openai
            )

            from app.ai.preprocessor import DataComplexity

            comp = DataComplexity(
                num_rows=10000,
                num_columns=10,
                anomaly_count=500,
                complexity_score=9000.0,
            )
            chain, decision = router._select_chain(comp)
            assert chain[0].name == "openai"

    @pytest.mark.asyncio
    async def test_very_high_complexity_quota_exhausted_skips_openai(self):
        with patch("app.ai.ai_router.budget_tracker") as mock_tracker:
            mock_tracker.quota_available = False
            mock_tracker.calls_remaining = 0

            rule = _make_handler("rule_based")
            ollama = _make_handler("ollama")
            hf = _make_handler("huggingface")
            openai = _make_handler("openai")
            router = AIRouter(
                rule_handler=rule, ollama_handler=ollama, hf_handler=hf, openai_handler=openai
            )

            from app.ai.preprocessor import DataComplexity

            comp = DataComplexity(
                num_rows=10000,
                num_columns=10,
                anomaly_count=500,
                complexity_score=9000.0,
            )
            chain, decision = router._select_chain(comp)
            assert chain[0].name == "ollama"
            # OpenAI must not appear
            assert all(h.name != "openai" for h in chain)

    @pytest.mark.asyncio
    async def test_fallback_chain_triggered_on_primary_failure(self):
        """When Ollama fails, the router falls back to the next handler."""
        rule = _make_handler("rule_based")
        ollama = _make_handler("ollama", raise_exc=RuntimeError("ollama unavailable"))
        hf = _make_handler("huggingface")
        openai = _make_handler("openai")
        router = AIRouter(
            rule_handler=rule, ollama_handler=ollama, hf_handler=hf, openai_handler=openai
        )

        # Use a crafted complexity that routes to ollama first
        from app.ai.preprocessor import DataComplexity

        comp = DataComplexity(
            num_rows=2000,
            num_columns=5,
            anomaly_count=500,
            complexity_score=2000.0,
        )

        # Patch compute_complexity so the router uses our crafted complexity
        with patch("app.ai.ai_router.compute_complexity", return_value=comp), \
             patch("app.ai.ai_router.budget_tracker") as mock_tracker:
            mock_tracker.quota_available = True
            mock_tracker.calls_remaining = 2
            result = await router.route([{"x": 1}])

        assert result.handler_used == "rule_based"
        assert "ollama" in result.fallbacks_triggered

    @pytest.mark.asyncio
    async def test_routing_result_has_required_fields(self):
        rule = _make_handler("rule_based")
        router = AIRouter(rule_handler=rule)
        data = _rows(5, cols=2)
        result = await router.route(data)
        assert isinstance(result, RoutingResult)
        assert isinstance(result.complexity, DataComplexity)
        assert isinstance(result.routing_decision, str)
        assert isinstance(result.elapsed_seconds, float)
        assert result.elapsed_seconds >= 0.0

    @pytest.mark.asyncio
    async def test_to_dict_serialisable(self):
        import json

        rule = _make_handler("rule_based")
        router = AIRouter(rule_handler=rule)
        result = await router.route(_rows(5))
        serialised = json.dumps(result.to_dict())
        assert len(serialised) > 0

    @pytest.mark.asyncio
    async def test_dict_input_passed_directly_to_handler(self):
        rule = _make_handler("rule_based")
        router = AIRouter(rule_handler=rule)
        data = {
            "balance_status": "minor_imbalance",
            "residual_pct": 3.0,
            "confidence_score": 0.8,
            "hypotheses": [],
        }
        result = await router.route(data)
        # Dict input with few/no anomalies → rule-based
        assert result.handler_used == "rule_based"
        called_data = rule.analyse.call_args[0][0]
        assert called_data["balance_status"] == "minor_imbalance"
