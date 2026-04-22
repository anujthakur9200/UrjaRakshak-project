"""
AI Router Configuration — UrjaRakshak python-backend
=====================================================
Central configuration for model selection thresholds, API parameters,
and OpenAI monthly budget tracking.

OpenAI is treated as a scarce resource (≤ OPENAI_MONTHLY_QUOTA calls
per calendar month).  All other routing prefers free / local options.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

# ─────────────────────────────────────────────────────────────────────
# Complexity routing thresholds
# ─────────────────────────────────────────────────────────────────────

# complexity_score = (num_rows * 0.4) + (num_columns * 0.2) + (anomaly_count * 0.4)
COMPLEXITY_RULE_BASED_MAX: float = 1000.0   # below → rule-based (free, instant)
COMPLEXITY_OLLAMA_MAX: float = 5000.0        # below → Ollama only
COMPLEXITY_HYBRID_MAX: float = 8000.0        # below → Ollama → HuggingFace fallback
# >= COMPLEXITY_HYBRID_MAX → OpenAI (if quota) else full fallback chain

# ─────────────────────────────────────────────────────────────────────
# API keys (from environment)
# ─────────────────────────────────────────────────────────────────────

OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
HUGGINGFACE_API_KEY: Optional[str] = os.getenv("HUGGINGFACE_API_KEY")
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3")

# HuggingFace inference endpoint / model
HUGGINGFACE_MODEL: str = os.getenv(
    "HUGGINGFACE_MODEL",
    "mistralai/Mistral-7B-Instruct-v0.1",
)
HUGGINGFACE_API_URL: str = (
    f"https://api-inference.huggingface.co/models/{HUGGINGFACE_MODEL}"
)

# OpenAI model
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# ─────────────────────────────────────────────────────────────────────
# OpenAI monthly quota tracking
# ─────────────────────────────────────────────────────────────────────

# Maximum number of OpenAI calls allowed per calendar month.
# Default 2 reflects a nearly-expired key with minimal credits.
OPENAI_MONTHLY_QUOTA: int = int(os.getenv("OPENAI_MONTHLY_QUOTA", "2"))


@dataclass
class OpenAIBudgetTracker:
    """
    In-process tracker for OpenAI API usage within the current calendar month.

    A production deployment should persist this to a database or Redis so the
    counter survives restarts.  For now an in-memory counter suffices because
    the quota is very small (1-2 calls / month) and the risk of one extra call
    due to a restart is acceptable.
    """

    monthly_quota: int = OPENAI_MONTHLY_QUOTA
    _calls_this_month: int = field(default=0, repr=False)
    _tracking_month: int = field(
        default_factory=lambda: datetime.now(tz=timezone.utc).month,
        repr=False,
    )

    def _reset_if_new_month(self) -> None:
        current_month = datetime.now(tz=timezone.utc).month
        if current_month != self._tracking_month:
            self._calls_this_month = 0
            self._tracking_month = current_month

    @property
    def calls_used(self) -> int:
        self._reset_if_new_month()
        return self._calls_this_month

    @property
    def calls_remaining(self) -> int:
        return max(0, self.monthly_quota - self.calls_used)

    @property
    def quota_available(self) -> bool:
        return self.calls_remaining > 0

    def record_call(self) -> None:
        """Increment the counter after a successful OpenAI call."""
        self._reset_if_new_month()
        self._calls_this_month += 1

    def status(self) -> dict:
        return {
            "monthly_quota": self.monthly_quota,
            "calls_used": self.calls_used,
            "calls_remaining": self.calls_remaining,
            "quota_available": self.quota_available,
        }


# Module-level singleton — shared across the entire application lifetime.
budget_tracker = OpenAIBudgetTracker()
