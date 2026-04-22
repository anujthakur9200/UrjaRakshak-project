"""
General-purpose utility helpers.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone


def utcnow() -> datetime:
    """Return the current UTC datetime (timezone-aware)."""
    return datetime.now(tz=timezone.utc)


def generate_analysis_id(substation_id: str) -> str:
    """
    Generate a deterministic-looking but unique analysis ID.
    Format: ANA-<substation>-<8-char-uuid-prefix>
    """
    short = str(uuid.uuid4()).replace("-", "")[:8].upper()
    safe_sub = substation_id.upper().replace(" ", "_")[:12]
    return f"ANA-{safe_sub}-{short}"


def generate_event_id() -> str:
    return f"EVT-{str(uuid.uuid4()).replace('-', '').upper()[:12]}"


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Division that returns *default* instead of raising ZeroDivisionError."""
    if denominator == 0.0:
        return default
    return numerator / denominator


def clamp(value: float, lo: float, hi: float) -> float:
    """Clamp value to [lo, hi]."""
    return max(lo, min(hi, value))


def round_dict_floats(d: dict, ndigits: int = 4) -> dict:
    """Recursively round all float values in a nested dict."""
    result = {}
    for k, v in d.items():
        if isinstance(v, float):
            result[k] = round(v, ndigits)
        elif isinstance(v, dict):
            result[k] = round_dict_floats(v, ndigits)
        else:
            result[k] = v
    return result


def fingerprint(data: str) -> str:
    """SHA-256 hex fingerprint of a string (first 16 chars)."""
    return hashlib.sha256(data.encode()).hexdigest()[:16]
