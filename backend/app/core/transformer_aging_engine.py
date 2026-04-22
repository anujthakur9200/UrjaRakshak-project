"""
Transformer Aging Engine — UrjaRakshak v2.3
============================================
IEC 60076-7 Power Transformer Thermal Aging Model.

The standard defines transformer aging through the Arrhenius equation
applied to paper insulation degradation. Hot-spot temperature is the
primary driver of aging — every 6°C increase halves insulation life
(the "6-degree rule").

Physics:

  1. Hot-spot temperature (IEC 60076-7 Eq. 3):
     Θh = Θamb + ΔΘo_rated × K^(2×n) + ΔΘh_rated × K^(2×m)

     Where:
       Θamb      = ambient temperature (°C)
       ΔΘo_rated = rated top-oil temperature rise (typically 55°C)
       ΔΘh_rated = rated hot-spot rise over top-oil (typically 23°C)
       K         = load factor (actual load / rated load)
       n, m      = oil and winding exponents (ONAN: 0.8, 1.3)

  2. Thermal aging factor (V) per IEC 60076-7 Eq. 2:
     V = exp( 15000/383 − 15000/(Θh + 273) )

     Normal aging at 98°C hot-spot gives V = 1.0.
     At 110°C → V ≈ 3.5 (ages 3.5× faster)
     At 80°C  → V ≈ 0.13 (ages 5× slower)

  3. Remaining Useful Life:
     RUL = (designed_life − years_installed) / V
     Clamped to [0, designed_life]

  4. Failure probability over next 12 months (logistic model):
     life_consumed_pct = years_installed × V / designed_life
     p_fail = 1 / (1 + exp(−10 × (life_consumed_pct − 0.75)))

  5. Health Index (0–100):
     HI = max(0, 100 × (1 − life_consumed_pct))

IEC reference: IEC 60076-7:2018 "Power transformers — Part 7:
Loading guide for mineral-oil-immersed power transformers"

Author: Vipin Baniya
"""

import logging
import math
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.models.db_models import Component, TransformerAgingRecord

logger = logging.getLogger(__name__)

# IEC 60076-7 reference temperature (°C) — normal aging rate at this hot-spot
REFERENCE_HOTSPOT_C = 98.0

# Activation energy constant (K) per IEC 60076-7
ACTIVATION_ENERGY = 15000.0

# Reference temperature in Kelvin
REFERENCE_TEMP_K = 371.0  # 98°C + 273K — IEC 60076-7 rated reference (V=1.0 at 98°C hotspot)
# Using the standard value: V=1 at Θh=98°C
# V = exp(15000/383 − 15000/(98+273)) = exp(39.16 − 40.43) = exp(-1.27)... 
# IEC actually uses: V = exp((E_A/R)(1/T_ref - 1/T_hs))
# Standard simplified: V = exp(15000/383 - 15000/(Θh+273))

# ONAN (Oil Natural Air Natural) cooling exponents
N_OIL = 0.8   # top-oil rise exponent
M_WINDING = 1.3  # winding gradient exponent

# Default temperature rises (IEC Table 2 for ONAN, 65°C winding rise class)
DELTA_THETA_O_RATED = 55.0   # rated top-oil temperature rise over ambient (°C)
DELTA_THETA_H_RATED = 23.0   # rated hot-spot rise over top-oil at rated load (°C)

# Condition classification thresholds (health index)
HI_GOOD     = 80.0
HI_FAIR     = 60.0
HI_POOR     = 40.0
# below 40 → CRITICAL


class TransformerAgingEngine:
    """
    IEC 60076-7 thermal aging model.
    All methods are pure functions — no DB access.
    """

    def compute_hotspot_temperature(
        self,
        ambient_temp_c: float,
        load_factor: float,
        delta_theta_o_rated: float = DELTA_THETA_O_RATED,
        delta_theta_h_rated: float = DELTA_THETA_H_RATED,
        n: float = N_OIL,
        m: float = M_WINDING,
    ) -> float:
        """
        IEC 60076-7 Equation 3: Hot-spot temperature.

        Θh = Θamb + ΔΘo_rated × K^(2n) + ΔΘh_rated × K^(2m)
        """
        k = max(0.0, load_factor)
        delta_o = delta_theta_o_rated * (k ** (2 * n))
        delta_h = delta_theta_h_rated * (k ** (2 * m))
        return ambient_temp_c + delta_o + delta_h

    def compute_aging_factor(self, hotspot_temp_c: float) -> float:
        """
        IEC 60076-7 Equation 2: Thermal aging acceleration factor V.

        V = exp(15000/383 − 15000/(Θh + 273))

        V = 1.0 at Θh = 98°C (reference point)
        V > 1.0 → faster aging (hot-spot above reference)
        V < 1.0 → slower aging (hot-spot below reference)
        """
        theta_k = hotspot_temp_c + 273.15  # Kelvin
        try:
            v = math.exp(
                ACTIVATION_ENERGY / REFERENCE_TEMP_K -
                ACTIVATION_ENERGY / theta_k
            )
        except (OverflowError, ZeroDivisionError):
            v = 1000.0  # extreme overheat
        return round(max(0.0, v), 6)

    def compute_aging(
        self,
        *,
        install_year: Optional[int],
        designed_life_years: float = 30.0,
        load_factor: float = 0.7,
        ambient_temp_c: float = 30.0,
        rated_kva: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Full aging computation for a transformer.
        Returns all metrics needed for condition assessment.
        """
        current_year = datetime.utcnow().year
        years_installed = float(current_year - install_year) if install_year else 10.0
        years_installed = max(0.0, years_installed)

        # Step 1: Hot-spot temperature
        hotspot = self.compute_hotspot_temperature(ambient_temp_c, load_factor)

        # Step 2: Thermal aging factor
        v = self.compute_aging_factor(hotspot)

        # Step 3: Equivalent aging in real years
        equivalent_age = years_installed * v

        # Step 4: Life consumed
        life_consumed_pct = min(1.0, equivalent_age / designed_life_years)

        # Step 5: Remaining useful life
        rul_years = max(0.0, (designed_life_years - equivalent_age) / v)
        rul_years = min(rul_years, designed_life_years)

        # Step 6: Failure probability over next 12 months (logistic)
        # P(fail) rises steeply as life_consumed passes 75%
        try:
            p_fail = 1.0 / (1.0 + math.exp(-10.0 * (life_consumed_pct - 0.75)))
        except OverflowError:
            p_fail = 1.0
        p_fail = round(min(1.0, max(0.0, p_fail)), 4)

        # Step 7: Health index
        health_index = round(max(0.0, 100.0 * (1.0 - life_consumed_pct)), 2)

        # Step 8: Condition class
        condition_class = self._classify_condition(health_index)

        # Maintenance / replacement flags
        maintenance_flag  = health_index < HI_FAIR or v > 3.0
        replacement_flag  = health_index < HI_POOR or rul_years < 2.0

        return {
            "years_installed":      round(years_installed, 1),
            "designed_life_years":  designed_life_years,
            "load_factor":          round(load_factor, 3),
            "ambient_temp_c":       round(ambient_temp_c, 1),
            "hotspot_temp_c":       round(hotspot, 2),
            "thermal_aging_factor": round(v, 4),
            "equivalent_age_years": round(equivalent_age, 2),
            "life_consumed_pct":    round(life_consumed_pct * 100, 2),
            "estimated_rul_years":  round(rul_years, 2),
            "failure_probability":  p_fail,
            "health_index":         health_index,
            "condition_class":      condition_class,
            "maintenance_flag":     maintenance_flag,
            "replacement_flag":     replacement_flag,
            "iec_reference":        "IEC 60076-7:2018",
            "physics": {
                "hotspot_formula": "Θh = Θamb + ΔΘo_rated×K^(2n) + ΔΘh_rated×K^(2m)",
                "aging_formula":   "V = exp(15000/383 − 15000/(Θh+273))",
                "n_oil":           N_OIL,
                "m_winding":       M_WINDING,
            },
        }

    def _classify_condition(self, health_index: float) -> str:
        if health_index >= HI_GOOD:   return "GOOD"
        elif health_index >= HI_FAIR: return "FAIR"
        elif health_index >= HI_POOR: return "POOR"
        return "CRITICAL"

    def sensitivity_analysis(
        self,
        base_load: float,
        base_ambient: float,
        install_year: Optional[int],
        designed_life: float = 30.0,
    ) -> List[Dict[str, Any]]:
        """
        What-if analysis: how does RUL change across load scenarios?
        Useful for load redistribution decisions.
        """
        scenarios = []
        for load in [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1]:
            result = self.compute_aging(
                install_year=install_year,
                designed_life_years=designed_life,
                load_factor=load,
                ambient_temp_c=base_ambient,
            )
            scenarios.append({
                "load_factor": load,
                "hotspot_c":   result["hotspot_temp_c"],
                "aging_factor": result["thermal_aging_factor"],
                "rul_years":   result["estimated_rul_years"],
                "health_index": result["health_index"],
                "condition":   result["condition_class"],
            })
        return scenarios


# ── DB-integrated aging computation ──────────────────────────────────────

async def compute_and_persist_aging(
    *,
    substation_id: str,
    transformer_tag: str,
    db: AsyncSession,
    org_id: Optional[str] = None,
    component_id: Optional[str] = None,
    rated_kva: Optional[float] = None,
    rated_voltage_kv: Optional[float] = None,
    install_year: Optional[int] = None,
    designed_life_years: float = 30.0,
    load_factor: float = 0.7,
    ambient_temp_c: float = 30.0,
) -> Dict[str, Any]:
    """Compute aging and upsert TransformerAgingRecord."""
    engine = TransformerAgingEngine()
    metrics = engine.compute_aging(
        install_year=install_year,
        designed_life_years=designed_life_years,
        load_factor=load_factor,
        ambient_temp_c=ambient_temp_c,
        rated_kva=rated_kva,
    )

    # Upsert
    existing = (await db.execute(
        select(TransformerAgingRecord)
        .where(TransformerAgingRecord.substation_id == substation_id)
        .where(TransformerAgingRecord.transformer_tag == transformer_tag)
    )).scalar_one_or_none()

    if existing:
        existing.load_factor           = load_factor
        existing.ambient_temp_c        = ambient_temp_c
        existing.hot_spot_temp_c       = metrics["hotspot_temp_c"]
        existing.thermal_aging_factor  = metrics["thermal_aging_factor"]
        existing.life_consumed_pct     = metrics["life_consumed_pct"]
        existing.estimated_rul_years   = metrics["estimated_rul_years"]
        existing.failure_probability   = metrics["failure_probability"]
        existing.health_index          = metrics["health_index"]
        existing.condition_class       = metrics["condition_class"]
        existing.maintenance_flag      = metrics["maintenance_flag"]
        existing.replacement_flag      = metrics["replacement_flag"]
        existing.computed_at           = datetime.utcnow()
    else:
        rec = TransformerAgingRecord(
            org_id=org_id,
            component_id=component_id,
            substation_id=substation_id,
            transformer_tag=transformer_tag,
            rated_kva=rated_kva,
            rated_voltage_kv=rated_voltage_kv,
            install_year=install_year,
            designed_life_years=designed_life_years,
            load_factor=load_factor,
            ambient_temp_c=ambient_temp_c,
            hot_spot_temp_c=metrics["hotspot_temp_c"],
            thermal_aging_factor=metrics["thermal_aging_factor"],
            life_consumed_pct=metrics["life_consumed_pct"],
            estimated_rul_years=metrics["estimated_rul_years"],
            failure_probability=metrics["failure_probability"],
            health_index=metrics["health_index"],
            condition_class=metrics["condition_class"],
            maintenance_flag=metrics["maintenance_flag"],
            replacement_flag=metrics["replacement_flag"],
        )
        db.add(rec)

    await db.flush()
    return {**metrics, "substation_id": substation_id, "transformer_tag": transformer_tag}


async def get_fleet_aging_summary(db: AsyncSession) -> Dict[str, Any]:
    """Aggregate aging health across all tracked transformers."""
    rows = (await db.execute(select(TransformerAgingRecord))).scalars().all()
    if not rows:
        return {"transformer_count": 0, "has_data": False}

    critical = [r for r in rows if r.condition_class == "CRITICAL"]
    poor     = [r for r in rows if r.condition_class == "POOR"]
    replace_soon = [r for r in rows if r.estimated_rul_years is not None and r.estimated_rul_years < 3.0]

    avg_hi = sum(r.health_index or 0 for r in rows) / len(rows)

    return {
        "transformer_count": len(rows),
        "has_data":          True,
        "avg_health_index":  round(avg_hi, 2),
        "critical_count":    len(critical),
        "poor_count":        len(poor),
        "replace_within_3yr": len(replace_soon),
        "by_condition": {
            "GOOD":     sum(1 for r in rows if r.condition_class == "GOOD"),
            "FAIR":     sum(1 for r in rows if r.condition_class == "FAIR"),
            "POOR":     len(poor),
            "CRITICAL": len(critical),
        },
        "transformers": [
            {
                "substation_id":      r.substation_id,
                "transformer_tag":    r.transformer_tag,
                "health_index":       r.health_index,
                "condition_class":    r.condition_class,
                "estimated_rul_years": r.estimated_rul_years,
                "failure_probability": r.failure_probability,
                "maintenance_flag":   r.maintenance_flag,
                "replacement_flag":   r.replacement_flag,
                "computed_at":        r.computed_at.isoformat() if r.computed_at else None,
            }
            for r in sorted(rows, key=lambda x: (x.health_index or 100))
        ],
    }


# Singleton
aging_engine = TransformerAgingEngine()
