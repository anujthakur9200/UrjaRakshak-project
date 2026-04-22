"""
Data Preprocessor — UrjaRakshak python-backend
===============================================
Analyses an input dataset (dict or list of dicts) and produces a
:class:`DataComplexity` summary that the AI router uses to select the
most appropriate model.

Complexity formula
------------------
    complexity_score = (num_rows * 0.4) + (num_columns * 0.2) + (anomaly_count * 0.4)

Anomaly heuristics
------------------
A cell is flagged as an anomaly when **any** of the following holds:

* Numeric value is exactly 0 in a column whose median is non-zero and
  the value deviates from the median by more than 3 × IQR (extreme outlier).
* Value is ``None`` / ``NaN`` / empty string.
* Numeric value is negative in a column where all other values are
  non-negative (sign anomaly).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Union

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Public data classes
# ─────────────────────────────────────────────────────────────────────


@dataclass
class DataComplexity:
    """Summary of dataset characteristics used for routing decisions."""

    num_rows: int
    num_columns: int
    anomaly_count: int
    complexity_score: float
    column_names: List[str] = field(default_factory=list)
    numeric_columns: List[str] = field(default_factory=list)
    missing_value_count: int = 0
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "num_rows": self.num_rows,
            "num_columns": self.num_columns,
            "anomaly_count": self.anomaly_count,
            "complexity_score": self.complexity_score,
            "column_names": self.column_names,
            "numeric_columns": self.numeric_columns,
            "missing_value_count": self.missing_value_count,
            "notes": self.notes,
        }


# ─────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────


def _is_missing(value: Any) -> bool:
    """Return True if ``value`` represents a missing / null observation."""
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def _try_float(value: Any) -> Optional[float]:
    """Return ``float(value)`` or *None* if conversion fails."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _iqr_bounds(values: List[float]) -> tuple[float, float]:
    """Return (lower_fence, upper_fence) using 1.5 × IQR rule."""
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    if n < 4:
        return (-math.inf, math.inf)

    q1_idx = n // 4
    q3_idx = (3 * n) // 4
    q1 = sorted_vals[q1_idx]
    q3 = sorted_vals[q3_idx]
    iqr = q3 - q1

    lower = q1 - 3.0 * iqr  # 3 × IQR → extreme outliers only
    upper = q3 + 3.0 * iqr
    return lower, upper


# ─────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────


def compute_complexity(
    data: Union[Sequence[Dict[str, Any]], Dict[str, Any]],
) -> DataComplexity:
    """
    Analyse *data* and return a :class:`DataComplexity` instance.

    Parameters
    ----------
    data:
        Either a **list of row dicts** (the common CSV-parsed form) or a
        **single dict** (treated as one row).

    Returns
    -------
    DataComplexity
        Populated with row/column counts, anomaly counts, and a
        pre-computed complexity score.
    """
    # Normalise input
    if isinstance(data, dict):
        rows: List[Dict[str, Any]] = [data]
    else:
        rows = list(data)

    if not rows:
        return DataComplexity(
            num_rows=0,
            num_columns=0,
            anomaly_count=0,
            complexity_score=0.0,
            notes=["Empty dataset — no analysis possible."],
        )

    num_rows = len(rows)
    column_names: List[str] = list(rows[0].keys())
    num_columns = len(column_names)
    notes: List[str] = []

    # ── Per-column analysis ──────────────────────────────────────────
    anomaly_count = 0
    missing_value_count = 0
    numeric_columns: List[str] = []

    for col in column_names:
        col_values = [row.get(col) for row in rows]
        missing = [v for v in col_values if _is_missing(v)]
        missing_value_count += len(missing)
        anomaly_count += len(missing)

        # Only analyse numeric columns further
        numeric_vals: List[float] = []
        for v in col_values:
            if not _is_missing(v):
                fv = _try_float(v)
                if fv is not None:
                    numeric_vals.append(fv)

        if not numeric_vals:
            continue  # non-numeric column — skip outlier detection

        numeric_columns.append(col)

        # Sign anomaly: negatives in a predominantly non-negative column
        negatives = [v for v in numeric_vals if v < 0]
        non_negatives = [v for v in numeric_vals if v >= 0]
        if negatives and len(non_negatives) > len(negatives):
            anomaly_count += len(negatives)

        # Extreme outlier detection via 3 × IQR fence
        if len(numeric_vals) >= 4:
            lower, upper = _iqr_bounds(numeric_vals)
            outliers = [v for v in numeric_vals if v < lower or v > upper]
            anomaly_count += len(outliers)
            if outliers:
                notes.append(
                    f"Column '{col}': {len(outliers)} extreme outlier(s) detected."
                )

    if missing_value_count:
        notes.append(f"{missing_value_count} missing value(s) across all columns.")

    # ── Complexity score ─────────────────────────────────────────────
    complexity_score = (
        num_rows * 0.4
        + num_columns * 0.2
        + anomaly_count * 0.4
    )

    logger.debug(
        "Preprocessor: rows=%d cols=%d anomalies=%d score=%.1f",
        num_rows,
        num_columns,
        anomaly_count,
        complexity_score,
    )

    return DataComplexity(
        num_rows=num_rows,
        num_columns=num_columns,
        anomaly_count=anomaly_count,
        complexity_score=round(complexity_score, 2),
        column_names=column_names,
        numeric_columns=numeric_columns,
        missing_value_count=missing_value_count,
        notes=notes,
    )
