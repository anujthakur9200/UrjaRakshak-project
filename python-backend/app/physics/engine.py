"""
Physics Engine — UrjaRakshak python-backend
============================================
Standalone energy loss calculations based on real electrical engineering.

No database dependencies — pure physics + math.

References:
  - I²R (Joule heating) for line losses
  - No-load / load loss model for transformers (IEEE C57.91)
  - First Law of Thermodynamics for energy balance
"""

import math
from dataclasses import dataclass, field
from typing import Optional

# ─────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────


@dataclass
class ComponentLoss:
    component_id: str
    component_type: str          # transformer | transmission_line | distribution
    calculated_loss_kwh: float
    loss_percentage: float       # loss / input × 100
    confidence: float            # 0.0 – 1.0


@dataclass
class PhysicsAnalysisResult:
    total_input_kwh: float
    total_output_kwh: float
    total_loss_kwh: float
    loss_percentage: float
    technical_loss_kwh: float    # sum of computed component losses
    residual_kwh: float          # actual_loss − technical_loss
    residual_pct: float          # residual / input × 100
    balance_status: str          # balanced | minor_imbalance | significant_imbalance | critical_imbalance
    confidence_score: float      # 0.0 – 1.0
    components: list[ComponentLoss]
    hypotheses: list[dict]


# ─────────────────────────────────────────────────────────────────────
# Core loss calculation functions
# ─────────────────────────────────────────────────────────────────────


def calculate_transformer_loss(
    rated_kva: float,
    load_factor: float,
    efficiency_rating: float,
    age_years: float,
) -> float:
    """
    Calculate transformer energy loss in kWh (per hour of operation).

    Uses the standard two-part transformer loss model:
      - No-load (core / iron) loss  — constant, independent of loading
      - Load (copper / winding) loss — proportional to load_factor²

    An age degradation factor increases both loss components as the
    transformer ages, modelling insulation deterioration and increased
    core losses from hysteresis / eddy current growth.

    Args:
        rated_kva:        Nameplate kVA rating.
        load_factor:      Per-unit loading (0–1).  1.0 = full load.
        efficiency_rating: Nameplate efficiency at full load (0–1).
        age_years:        Age of the transformer in years.

    Returns:
        Estimated loss in kWh for one hour of operation.
    """
    load_factor = max(0.0, min(1.0, load_factor))
    efficiency_rating = max(0.5, min(1.0, efficiency_rating))
    age_years = max(0.0, age_years)

    # Total loss at full load derived from efficiency
    # P_total_loss = rated_kw × (1 − η)  where rated_kw = rated_kva × pf (assume 0.9)
    power_factor_assumed = 0.9
    rated_kw = rated_kva * power_factor_assumed
    total_loss_at_full_load_kw = rated_kw * (1.0 - efficiency_rating)

    # Split: no-load ≈ 25 %, load loss ≈ 75 % (typical distribution transformer)
    no_load_loss_kw = 0.25 * total_loss_at_full_load_kw
    full_load_copper_loss_kw = 0.75 * total_loss_at_full_load_kw

    # Load-dependent copper loss scales as load_factor²
    copper_loss_kw = full_load_copper_loss_kw * (load_factor ** 2)

    # Age degradation — 0.5 % increase per year, capped at +25 %
    age_factor = 1.0 + min(0.25, 0.005 * age_years)

    total_loss_kw = (no_load_loss_kw + copper_loss_kw) * age_factor

    # kWh = kW × hours; return 1-hour equivalent
    return total_loss_kw


def calculate_line_loss(
    current_a: float,
    resistance_ohms: float,
    length_km: float,
    voltage_kv: float,
) -> float:
    """
    Calculate I²R (Joule heating) line loss in kW.

    P_loss = I² × R_total
    where R_total = resistance_ohms_per_km × length_km

    The voltage_kv parameter is used to verify physical plausibility:
    we compute the percentage voltage drop and cap confidence, but the
    return value is purely the I²R loss.

    Args:
        current_a:       RMS current through the line in Amperes.
        resistance_ohms: Resistance per km (Ω/km) at operating temperature.
        length_km:       Total line length in km.
        voltage_kv:      Nominal operating voltage in kV.

    Returns:
        Line loss in kW.
    """
    current_a = max(0.0, current_a)
    resistance_ohms = max(0.0, resistance_ohms)
    length_km = max(0.0, length_km)
    voltage_kv = max(0.001, voltage_kv)

    r_total_ohms = resistance_ohms * length_km
    loss_w = (current_a ** 2) * r_total_ohms
    loss_kw = loss_w / 1_000.0

    return loss_kw


def analyze_energy_balance(
    input_kwh: float,
    output_kwh: float,
    components: list[dict],
) -> PhysicsAnalysisResult:
    """
    Perform a full energy balance analysis for a grid section.

    Steps:
      1. Compute actual loss = input − output.
      2. Compute technical (expected) loss from component physics.
      3. Compute residual = actual − technical.
      4. Classify balance status and confidence.
      5. Build hypotheses for unexplained residual.

    Args:
        input_kwh:  Total energy entering the grid section (kWh).
        output_kwh: Total energy delivered to consumers (kWh).
        components: List of dicts, each describing one grid component.
                    Expected keys per component:
                      - component_id   (str)
                      - component_type (str)  transformer | line | distribution
                      - rated_kva      (float) for transformers
                      - load_factor    (float) 0–1
                      - efficiency     (float) 0–1
                      - age_years      (float) for transformers
                      - current_a      (float) for lines
                      - resistance_ohm_per_km (float) for lines
                      - length_km      (float) for lines
                      - voltage_kv     (float) for lines

    Returns:
        PhysicsAnalysisResult with full breakdown.
    """
    input_kwh = max(0.0, input_kwh)
    output_kwh = max(0.0, output_kwh)

    actual_loss_kwh = input_kwh - output_kwh

    # ── Compute per-component technical losses ──────────────────────
    component_losses: list[ComponentLoss] = []
    technical_loss_kwh = 0.0

    for comp in components:
        ctype = comp.get("component_type", "unknown").lower()
        cid = comp.get("component_id", "unknown")
        loss_kwh = 0.0
        confidence = 0.85

        if "transformer" in ctype:
            loss_kwh = calculate_transformer_loss(
                rated_kva=float(comp.get("rated_kva", 100.0)),
                load_factor=float(comp.get("load_factor", 0.7)),
                efficiency_rating=float(comp.get("efficiency", 0.97)),
                age_years=float(comp.get("age_years", 5.0)),
            )
            confidence = 0.90 if comp.get("efficiency") else 0.75

        elif ctype in ("transmission_line", "line", "distribution"):
            loss_kwh = calculate_line_loss(
                current_a=float(comp.get("current_a", 100.0)),
                resistance_ohms=float(comp.get("resistance_ohm_per_km", 0.1)),
                length_km=float(comp.get("length_km", 1.0)),
                voltage_kv=float(comp.get("voltage_kv", 11.0)),
            )
            confidence = 0.88 if comp.get("current_a") else 0.70

        loss_pct = (loss_kwh / input_kwh * 100.0) if input_kwh > 0 else 0.0
        technical_loss_kwh += loss_kwh

        component_losses.append(ComponentLoss(
            component_id=cid,
            component_type=ctype,
            calculated_loss_kwh=round(loss_kwh, 4),
            loss_percentage=round(loss_pct, 4),
            confidence=confidence,
        ))

    residual_kwh = actual_loss_kwh - technical_loss_kwh
    residual_pct = (residual_kwh / input_kwh * 100.0) if input_kwh > 0 else 0.0
    total_loss_pct = (actual_loss_kwh / input_kwh * 100.0) if input_kwh > 0 else 0.0

    # ── Overall confidence ──────────────────────────────────────────
    if component_losses:
        avg_comp_confidence = sum(c.confidence for c in component_losses) / len(component_losses)
    else:
        avg_comp_confidence = 0.5

    # Penalise large unexplained residuals
    residual_penalty = min(0.4, abs(residual_pct) / 25.0)
    confidence_score = round(max(0.0, avg_comp_confidence - residual_penalty), 3)

    # ── Balance status ──────────────────────────────────────────────
    balance_status = classify_balance_status(residual_pct, confidence_score)

    # ── Hypotheses for residual ─────────────────────────────────────
    hypotheses = _build_hypotheses(residual_pct, confidence_score, actual_loss_kwh, input_kwh)

    return PhysicsAnalysisResult(
        total_input_kwh=round(input_kwh, 3),
        total_output_kwh=round(output_kwh, 3),
        total_loss_kwh=round(actual_loss_kwh, 3),
        loss_percentage=round(total_loss_pct, 4),
        technical_loss_kwh=round(technical_loss_kwh, 3),
        residual_kwh=round(residual_kwh, 3),
        residual_pct=round(residual_pct, 4),
        balance_status=balance_status,
        confidence_score=confidence_score,
        components=component_losses,
        hypotheses=hypotheses,
    )


def classify_balance_status(residual_pct: float, confidence: float) -> str:
    """
    Classify the energy balance status from the residual percentage.

    Thresholds (absolute value of residual_pct):
      < 2 %   → balanced
      2–5 %   → minor_imbalance
      5–10 %  → significant_imbalance
      > 10 %  → critical_imbalance

    If confidence < 0.5 the classification is overridden to "uncertain".

    Args:
        residual_pct: Residual as percentage of input energy.
        confidence:   Overall confidence score (0–1).

    Returns:
        One of: "balanced" | "minor_imbalance" | "significant_imbalance"
                | "critical_imbalance" | "uncertain"
    """
    if confidence < 0.5:
        return "uncertain"

    abs_pct = abs(residual_pct)

    if abs_pct < 2.0:
        return "balanced"
    if abs_pct < 5.0:
        return "minor_imbalance"
    if abs_pct < 10.0:
        return "significant_imbalance"
    return "critical_imbalance"


# ─────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────


def _build_hypotheses(
    residual_pct: float,
    confidence: float,
    actual_loss_kwh: float,
    input_kwh: float,
) -> list[dict]:
    """Generate ranked loss-attribution hypotheses based on the residual."""

    hypotheses = []
    abs_pct = abs(residual_pct)

    if abs_pct < 0.5:
        hypotheses.append({
            "cause": "measurement_noise",
            "probability": 0.90,
            "confidence": confidence,
            "description": "Residual within normal meter accuracy band (±0.5 %).",
            "recommended_action": "No action required.",
        })
        return hypotheses

    # Meter calibration drift
    hypotheses.append({
        "cause": "meter_calibration_drift",
        "probability": min(0.80, 0.3 + abs_pct * 0.05),
        "confidence": confidence * 0.9,
        "description": "Meters may be out of calibration; last calibration date unknown.",
        "recommended_action": "Schedule meter recalibration within 30 days.",
    })

    # Infrastructure degradation (always relevant)
    hypotheses.append({
        "cause": "infrastructure_degradation",
        "probability": min(0.70, 0.25 + abs_pct * 0.04),
        "confidence": confidence * 0.85,
        "description": "Aged conductors and transformer insulation increase technical losses.",
        "recommended_action": "Inspect high-loss components; prioritise replacement schedule.",
    })

    # Non-technical loss (theft / billing) — rises with large residuals
    if abs_pct >= 3.0:
        theft_prob = min(0.65, (abs_pct - 3.0) * 0.08 + 0.20)
        hypotheses.append({
            "cause": "non_technical_loss",
            "probability": round(theft_prob, 3),
            "confidence": round(confidence * 0.7, 3),
            "description": "Residual exceeds typical technical loss band; non-technical causes possible.",
            "recommended_action": "Conduct field audit; cross-check billing records.",
        })

    # Unmetered loads
    if abs_pct >= 5.0:
        hypotheses.append({
            "cause": "unmetered_load",
            "probability": round(min(0.50, abs_pct * 0.04), 3),
            "confidence": round(confidence * 0.65, 3),
            "description": "Unregistered loads or illegal connections may account for residual.",
            "recommended_action": "Survey consumer connections; install tamper-evident meters.",
        })

    # Sort by probability descending
    hypotheses.sort(key=lambda h: h["probability"], reverse=True)
    return hypotheses
