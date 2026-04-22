"""
Claude / OpenAI AI interpretation service.

Falls back gracefully when no API key is configured so the rest of
the application remains fully functional in offline / dev mode.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY: Optional[str] = os.getenv("ANTHROPIC_API_KEY")
OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")


class AIService:
    """Thin wrapper around Claude or OpenAI for analysis interpretation."""

    def __init__(self) -> None:
        self._provider: Optional[str] = None
        self._model: Optional[str] = None
        self._client = None

        if ANTHROPIC_API_KEY:
            try:
                import anthropic  # type: ignore

                self._client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
                self._provider = "anthropic"
                self._model = "claude-3-5-haiku-20241022"
                logger.info("AI service: Claude configured")
            except ImportError:
                logger.warning("anthropic package not installed; falling back")

        if self._client is None and OPENAI_API_KEY:
            try:
                from openai import OpenAI  # type: ignore

                self._client = OpenAI(api_key=OPENAI_API_KEY)
                self._provider = "openai"
                self._model = "gpt-4o-mini"
                logger.info("AI service: OpenAI configured")
            except ImportError:
                logger.warning("openai package not installed; AI unavailable")

        if self._client is None:
            logger.info("AI service: no API key — offline mode")

    @property
    def is_available(self) -> bool:
        return self._client is not None

    @property
    def provider(self) -> Optional[str]:
        return self._provider

    @property
    def model(self) -> Optional[str]:
        return self._model

    async def interpret_analysis(
        self,
        analysis_data: dict,
        language: str = "en",
        detail_level: str = "standard",
    ) -> dict:
        """
        Generate a human-readable interpretation of an energy analysis result.

        Returns a dict with keys:
          summary, key_findings, recommended_actions, risk_level
        """
        if not self.is_available:
            return self._offline_interpretation(analysis_data)

        prompt = self._build_prompt(analysis_data, language, detail_level)

        try:
            if self._provider == "anthropic":
                return await self._call_claude(prompt)
            return await self._call_openai(prompt)
        except Exception as exc:
            logger.error("AI interpretation failed: %s", exc)
            return self._offline_interpretation(analysis_data)

    # ── Private helpers ──────────────────────────────────────────────

    def _build_prompt(self, data: dict, language: str, detail: str) -> str:
        balance = data.get("balance_status", "unknown")
        residual = data.get("residual_pct", 0)
        confidence = data.get("confidence_score", 0)
        hypotheses = data.get("hypotheses", [])

        hyp_text = "\n".join(
            f"- {h.get('cause')}: {h.get('probability', 0):.0%} probability"
            for h in hypotheses[:3]
        )

        detail_instruction = {
            "brief": "Respond in 2–3 sentences.",
            "standard": "Respond with a short paragraph and bullet points.",
            "detailed": "Provide a thorough technical report.",
        }.get(detail, "Respond with a short paragraph and bullet points.")

        return (
            f"You are an energy engineer analysing grid losses for UrjaRakshak.\n"
            f"Balance status: {balance}\n"
            f"Residual loss: {residual:.2f}%\n"
            f"Confidence: {confidence:.0%}\n"
            f"Top hypotheses:\n{hyp_text}\n\n"
            f"Respond in language code '{language}'. {detail_instruction}\n"
            f"Return JSON with keys: summary, key_findings (list), "
            f"recommended_actions (list), risk_level (low/medium/high/critical)."
        )

    async def _call_claude(self, prompt: str) -> dict:
        import json

        message = self._client.messages.create(  # type: ignore[union-attr]
            model=self._model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text
        return json.loads(raw)

    async def _call_openai(self, prompt: str) -> dict:
        import json

        resp = self._client.chat.completions.create(  # type: ignore[union-attr]
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        return json.loads(resp.choices[0].message.content)

    @staticmethod
    def _offline_interpretation(data: dict) -> dict:
        balance = data.get("balance_status", "unknown")
        residual = abs(data.get("residual_pct", 0.0))
        confidence = data.get("confidence_score", 0.5)

        risk_map = {
            "balanced": "low",
            "minor_imbalance": "medium",
            "significant_imbalance": "high",
            "critical_imbalance": "critical",
            "uncertain": "medium",
        }
        risk_level = risk_map.get(balance, "medium")

        return {
            "summary": (
                f"Energy balance status is '{balance}' with a {residual:.2f}% unexplained "
                f"residual and {confidence:.0%} confidence. "
                "Offline mode — AI service not configured."
            ),
            "key_findings": [
                f"Balance status: {balance}",
                f"Residual: {residual:.2f}%",
                f"Confidence: {confidence:.0%}",
            ],
            "recommended_actions": [
                "Review meter calibration records.",
                "Inspect high-loss components identified in analysis.",
                "Configure ANTHROPIC_API_KEY or OPENAI_API_KEY for AI interpretation.",
            ],
            "risk_level": risk_level,
        }


# Module-level singleton
_service: Optional[AIService] = None


def get_ai_service() -> AIService:
    global _service
    if _service is None:
        _service = AIService()
    return _service
