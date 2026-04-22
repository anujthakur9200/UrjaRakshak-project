"""
AI Router — UrjaRakshak python-backend
=======================================
Cost-conscious, resilient AI routing engine.

Routing decision tree
---------------------
Given::

    complexity_score = (num_rows × 0.4) + (num_columns × 0.2) + (anomaly_count × 0.4)

1. ``anomaly_count == 0``  **or**  ``complexity_score < 1000``
   → Rule-based (free, instant, no network)

2. ``1000 ≤ complexity_score < 5000``
   → Ollama (local, zero cost) with Rule-based fallback

3. ``5000 ≤ complexity_score < 8000``
   → Ollama → HuggingFace → Rule-based (fallback chain)

4. ``complexity_score ≥ 8000``  **and**  OpenAI monthly quota available
   → OpenAI (premium, quota-limited) with full fallback chain on failure

5. ``complexity_score ≥ 8000``  **and**  quota exhausted
   → Ollama → HuggingFace → Rule-based

Every routing decision and outcome is logged at INFO level.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.ai.config import (
    COMPLEXITY_HYBRID_MAX,
    COMPLEXITY_OLLAMA_MAX,
    COMPLEXITY_RULE_BASED_MAX,
    budget_tracker,
)
from app.ai.model_handlers import (
    BaseModelHandler,
    HuggingFaceHandler,
    OllamaHandler,
    OpenAIHandler,
    RuleBasedHandler,
)
from app.ai.preprocessor import DataComplexity, compute_complexity

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Routing result
# ─────────────────────────────────────────────────────────────────────


@dataclass
class RoutingResult:
    """Full outcome of a single routing decision."""

    analysis: Dict[str, Any]          # normalised model output
    handler_used: str                  # name of the handler that succeeded
    complexity: DataComplexity         # pre-computed complexity summary
    routing_decision: str              # human-readable explanation
    fallbacks_triggered: List[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "analysis": self.analysis,
            "handler_used": self.handler_used,
            "complexity": self.complexity.to_dict(),
            "routing_decision": self.routing_decision,
            "fallbacks_triggered": self.fallbacks_triggered,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
        }


# ─────────────────────────────────────────────────────────────────────
# Router
# ─────────────────────────────────────────────────────────────────────


class AIRouter:
    """
    Smart AI router that selects the cheapest model capable of handling
    the given data complexity, with an automatic fallback chain.

    Parameters
    ----------
    rule_handler:
        Override the :class:`~app.ai.model_handlers.RuleBasedHandler`.
        Useful for testing.
    ollama_handler:
        Override the :class:`~app.ai.model_handlers.OllamaHandler`.
    hf_handler:
        Override the :class:`~app.ai.model_handlers.HuggingFaceHandler`.
    openai_handler:
        Override the :class:`~app.ai.model_handlers.OpenAIHandler`.
    """

    def __init__(
        self,
        rule_handler: Optional[BaseModelHandler] = None,
        ollama_handler: Optional[BaseModelHandler] = None,
        hf_handler: Optional[BaseModelHandler] = None,
        openai_handler: Optional[BaseModelHandler] = None,
    ) -> None:
        self._rule = rule_handler or RuleBasedHandler()
        self._ollama = ollama_handler or OllamaHandler()
        self._hf = hf_handler or HuggingFaceHandler()
        self._openai = openai_handler or OpenAIHandler()

    # ── Public API ───────────────────────────────────────────────────

    async def route(
        self,
        data: Any,
        context: Optional[str] = None,
    ) -> RoutingResult:
        """
        Analyse *data*, select the appropriate model, and return results.

        Parameters
        ----------
        data:
            Raw dataset — either a list of row dicts or a single dict.
        context:
            Optional free-text context injected into the AI prompt.

        Returns
        -------
        RoutingResult
            Contains the analysis output, the handler actually used,
            complexity metrics, and the routing decision explanation.
        """
        start = time.monotonic()

        complexity = compute_complexity(data)
        chain, decision = self._select_chain(complexity)

        logger.info(
            "AIRouter: score=%.1f anomalies=%d rows=%d → decision='%s' chain=%s",
            complexity.complexity_score,
            complexity.anomaly_count,
            complexity.num_rows,
            decision,
            [h.name for h in chain],
        )

        # Extract the normalised analysis_data dict for model handlers.
        # If *data* is already a dict (e.g. analysis result), use it directly;
        # otherwise build a minimal summary from the DataComplexity object.
        if isinstance(data, dict):
            analysis_data = data
        else:
            analysis_data = {
                "balance_status": "unknown",
                "residual_pct": 0.0,
                "confidence_score": 0.5,
                "hypotheses": [],
                "complexity": complexity.to_dict(),
            }

        fallbacks_triggered: List[str] = []
        last_error: Optional[Exception] = None

        for handler in chain:
            try:
                result = await handler.analyse(analysis_data, context)
                elapsed = time.monotonic() - start
                logger.info(
                    "AIRouter: handler='%s' succeeded in %.3fs",
                    handler.name,
                    elapsed,
                )
                return RoutingResult(
                    analysis=result,
                    handler_used=handler.name,
                    complexity=complexity,
                    routing_decision=decision,
                    fallbacks_triggered=fallbacks_triggered,
                    elapsed_seconds=elapsed,
                )
            except Exception as exc:
                logger.warning(
                    "AIRouter: handler='%s' failed (%s); trying next in chain",
                    handler.name,
                    exc,
                )
                fallbacks_triggered.append(handler.name)
                last_error = exc

        # All handlers failed — this should never happen because
        # RuleBasedHandler has no external dependencies, but handle it anyway.
        elapsed = time.monotonic() - start
        logger.error(
            "AIRouter: all handlers failed (last error: %s); returning empty result",
            last_error,
        )
        return RoutingResult(
            analysis={
                "summary": "All analysis backends unavailable.",
                "key_findings": [],
                "recommended_actions": ["Check system configuration."],
                "risk_level": "medium",
                "model_used": "none",
                "handler": "none",
            },
            handler_used="none",
            complexity=complexity,
            routing_decision=decision,
            fallbacks_triggered=fallbacks_triggered,
            elapsed_seconds=elapsed,
        )

    # ── Private helpers ──────────────────────────────────────────────

    def _select_chain(
        self,
        complexity: DataComplexity,
    ) -> tuple[List[BaseModelHandler], str]:
        """
        Return an ordered handler chain and a human-readable decision string.

        The first handler in the chain is tried first; subsequent handlers
        are only called if the preceding one raises an exception.
        """
        score = complexity.complexity_score
        anomalies = complexity.anomaly_count

        # ── Rule 1: trivial data — always free ───────────────────────
        if anomalies == 0 or score < COMPLEXITY_RULE_BASED_MAX:
            return (
                [self._rule],
                f"rule_based (score={score:.1f} < {COMPLEXITY_RULE_BASED_MAX} "
                f"or anomalies=0)",
            )

        # ── Rule 2: moderate complexity — Ollama only ────────────────
        if score < COMPLEXITY_OLLAMA_MAX:
            return (
                [self._ollama, self._rule],
                f"ollama (score={score:.1f} < {COMPLEXITY_OLLAMA_MAX})",
            )

        # ── Rule 3: high complexity — Ollama + HF fallback ───────────
        if score < COMPLEXITY_HYBRID_MAX:
            return (
                [self._ollama, self._hf, self._rule],
                f"ollama→huggingface (score={score:.1f} < {COMPLEXITY_HYBRID_MAX})",
            )

        # ── Rule 4+: very high complexity ────────────────────────────
        if budget_tracker.quota_available:
            return (
                [self._openai, self._ollama, self._hf, self._rule],
                f"openai (score={score:.1f} >= {COMPLEXITY_HYBRID_MAX}, "
                f"quota_remaining={budget_tracker.calls_remaining})",
            )

        # Quota exhausted — skip OpenAI entirely
        return (
            [self._ollama, self._hf, self._rule],
            f"ollama→huggingface (score={score:.1f} >= {COMPLEXITY_HYBRID_MAX}, "
            "openai_quota_exhausted)",
        )


# ─────────────────────────────────────────────────────────────────────
# Module-level singleton
# ─────────────────────────────────────────────────────────────────────

_router: Optional[AIRouter] = None


def get_ai_router() -> AIRouter:
    """Return the shared :class:`AIRouter` singleton."""
    global _router
    if _router is None:
        _router = AIRouter()
    return _router
