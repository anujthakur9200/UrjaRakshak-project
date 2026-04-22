"""
Model Handlers — UrjaRakshak python-backend
============================================
Unified interface for all AI model backends used by the AI router.

Each handler exposes a single ``async analyse(data, context)`` coroutine
that returns a normalised ``AnalysisResult`` dict:

    {
        "summary":             str,
        "key_findings":        list[str],
        "recommended_actions": list[str],
        "risk_level":          "low" | "medium" | "high" | "critical",
        "model_used":          str,
        "handler":             str,
    }

All handlers are designed to be **stateless and independently testable**.
"""

from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from app.ai.config import (
    HUGGINGFACE_API_KEY,
    HUGGINGFACE_API_URL,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    OPENAI_API_KEY,
    OPENAI_MODEL,
    budget_tracker,
)

logger = logging.getLogger(__name__)

# Shared timeout (seconds) for external HTTP calls
_HTTP_TIMEOUT = 30


# ─────────────────────────────────────────────────────────────────────
# Base class
# ─────────────────────────────────────────────────────────────────────


class BaseModelHandler(ABC):
    """Abstract base for all model handlers."""

    name: str = "base"

    @abstractmethod
    async def analyse(
        self,
        data: Dict[str, Any],
        context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run analysis and return a normalised result dict."""

    # ── Shared prompt builder ────────────────────────────────────────

    @staticmethod
    def _build_prompt(data: Dict[str, Any], context: Optional[str] = None) -> str:
        balance = data.get("balance_status", "unknown")
        residual = data.get("residual_pct", 0.0)
        confidence = data.get("confidence_score", 0.5)
        hypotheses: List[dict] = data.get("hypotheses", [])

        hyp_lines = "\n".join(
            f"  - {h.get('cause', 'unknown')}: "
            f"{h.get('probability', 0):.0%} probability"
            for h in hypotheses[:3]
        )

        extra = f"\nAdditional context: {context}" if context else ""

        return (
            "You are an energy-grid engineer analysing power losses "
            "for the UrjaRakshak system.\n"
            f"Balance status : {balance}\n"
            f"Residual loss  : {residual:.2f}%\n"
            f"Confidence     : {confidence:.0%}\n"
            f"Top hypotheses :\n{hyp_lines}{extra}\n\n"
            "Return JSON with exactly these keys:\n"
            "  summary, key_findings (list), "
            "recommended_actions (list), risk_level (low/medium/high/critical)."
        )

    # ── Shared response normaliser ───────────────────────────────────

    @classmethod
    def _normalise(
        cls,
        raw: Dict[str, Any],
        model_used: str,
    ) -> Dict[str, Any]:
        return {
            "summary": raw.get("summary", ""),
            "key_findings": raw.get("key_findings", []),
            "recommended_actions": raw.get("recommended_actions", []),
            "risk_level": raw.get("risk_level", "medium"),
            "model_used": model_used,
            "handler": cls.name,
        }


# ─────────────────────────────────────────────────────────────────────
# Rule-based handler (free, instant, no network)
# ─────────────────────────────────────────────────────────────────────


class RuleBasedHandler(BaseModelHandler):
    """
    Deterministic rule-based analysis — zero cost, zero latency.

    Used as the default for simple datasets and as the final fallback
    when all AI models are unavailable.
    """

    name = "rule_based"

    async def analyse(
        self,
        data: Dict[str, Any],
        context: Optional[str] = None,
    ) -> Dict[str, Any]:
        balance: str = data.get("balance_status", "unknown")
        residual: float = abs(data.get("residual_pct", 0.0))
        confidence: float = data.get("confidence_score", 0.5)

        _risk_map = {
            "balanced": "low",
            "minor_imbalance": "medium",
            "significant_imbalance": "high",
            "critical_imbalance": "critical",
            "uncertain": "medium",
        }
        risk_level = _risk_map.get(balance, "medium")

        summary = (
            f"Energy balance status is '{balance}' with a {residual:.2f}% "
            f"unexplained residual and {confidence:.0%} confidence. "
            "Analysis performed by built-in rule-based engine."
        )

        key_findings: List[str] = [
            f"Balance status: {balance}",
            f"Residual loss: {residual:.2f}%",
            f"Confidence: {confidence:.0%}",
        ]

        recommended_actions: List[str] = [
            "Review meter calibration records.",
            "Inspect components with highest calculated loss.",
        ]
        if residual > 10.0:
            recommended_actions.append(
                "Residual exceeds 10% — consider urgent field inspection."
            )

        logger.info("RuleBasedHandler: analysis complete (risk=%s)", risk_level)

        return self._normalise(
            {
                "summary": summary,
                "key_findings": key_findings,
                "recommended_actions": recommended_actions,
                "risk_level": risk_level,
            },
            model_used="rule_based",
        )


# ─────────────────────────────────────────────────────────────────────
# Ollama handler (local LLM, no API cost)
# ─────────────────────────────────────────────────────────────────────


class OllamaHandler(BaseModelHandler):
    """
    Local Ollama LLM handler.

    Requires a running Ollama server (default: http://localhost:11434).
    Raises :class:`RuntimeError` when the server is unreachable so that
    the router can trigger the fallback chain.
    """

    name = "ollama"

    async def analyse(
        self,
        data: Dict[str, Any],
        context: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("httpx is required for Ollama integration") from exc

        prompt = self._build_prompt(data, context)
        payload = {
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "format": "json",
        }

        url = f"{OLLAMA_BASE_URL}/api/generate"
        logger.info("OllamaHandler: calling %s (model=%s)", url, OLLAMA_MODEL)

        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()

        raw = json.loads(response.json().get("response", "{}"))
        logger.info("OllamaHandler: analysis complete")
        return self._normalise(raw, model_used=f"ollama/{OLLAMA_MODEL}")


# ─────────────────────────────────────────────────────────────────────
# HuggingFace handler (free tier)
# ─────────────────────────────────────────────────────────────────────


class HuggingFaceHandler(BaseModelHandler):
    """
    HuggingFace Inference API handler.

    Uses the free inference tier when ``HUGGINGFACE_API_KEY`` is not set,
    or the authenticated tier when the key is available.  Raises
    :class:`RuntimeError` on failure so the router can fall back.
    """

    name = "huggingface"

    async def analyse(
        self,
        data: Dict[str, Any],
        context: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("httpx is required for HuggingFace integration") from exc

        prompt = self._build_prompt(data, context)
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if HUGGINGFACE_API_KEY:
            headers["Authorization"] = f"Bearer {HUGGINGFACE_API_KEY}"

        payload = {
            "inputs": prompt,
            "parameters": {
                "max_new_tokens": 512,
                "return_full_text": False,
            },
        }

        logger.info(
            "HuggingFaceHandler: calling %s (model=%s)",
            HUGGINGFACE_API_URL,
            HUGGINGFACE_API_URL.split("/")[-1],
        )

        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            response = await client.post(
                HUGGINGFACE_API_URL,
                headers=headers,
                json=payload,
            )
            response.raise_for_status()

        resp_body = response.json()
        # HF inference returns a list; take the first generated text
        if isinstance(resp_body, list):
            generated = resp_body[0].get("generated_text", "{}")
        else:
            generated = resp_body.get("generated_text", "{}")

        # The model may wrap JSON in markdown fences; strip them
        generated = generated.strip()
        if generated.startswith("```"):
            generated = generated.split("```")[1].lstrip("json").strip()
            if "```" in generated:
                generated = generated[: generated.index("```")]

        raw = json.loads(generated) if generated.startswith("{") else {}
        logger.info("HuggingFaceHandler: analysis complete")
        return self._normalise(
            raw,
            model_used=f"huggingface/{HUGGINGFACE_API_URL.split('/')[-1]}",
        )


# ─────────────────────────────────────────────────────────────────────
# OpenAI handler (quota-limited, premium)
# ─────────────────────────────────────────────────────────────────────


class OpenAIHandler(BaseModelHandler):
    """
    OpenAI API handler — **reserved for rare, highly-complex tasks only**.

    Raises :class:`RuntimeError` when:
    - ``OPENAI_API_KEY`` is not set, or
    - The monthly quota is exhausted.

    Records every successful call against the shared
    :data:`~app.ai.config.budget_tracker`.
    """

    name = "openai"

    async def analyse(
        self,
        data: Dict[str, Any],
        context: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not configured")

        if not budget_tracker.quota_available:
            raise RuntimeError(
                f"OpenAI monthly quota exhausted "
                f"({budget_tracker.monthly_quota} calls/month)"
            )

        try:
            from openai import AsyncOpenAI  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("openai package is required for OpenAI integration") from exc

        prompt = self._build_prompt(data, context)
        client = AsyncOpenAI(api_key=OPENAI_API_KEY)

        logger.info(
            "OpenAIHandler: calling OpenAI (model=%s, quota_remaining=%d)",
            OPENAI_MODEL,
            budget_tracker.calls_remaining,
        )

        response = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            timeout=_HTTP_TIMEOUT,
        )

        budget_tracker.record_call()
        raw = json.loads(response.choices[0].message.content or "{}")
        logger.info(
            "OpenAIHandler: analysis complete (quota_remaining=%d)",
            budget_tracker.calls_remaining,
        )
        return self._normalise(raw, model_used=f"openai/{OPENAI_MODEL}")
