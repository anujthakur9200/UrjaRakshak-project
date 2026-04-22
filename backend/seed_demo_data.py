"""
UrjaRakshak — Demo Data Seeder
================================
Run ONCE after first deployment to populate the database with
realistic data so the dashboard is never empty on first open.

Usage:
    python seed_demo_data.py
    python seed_demo_data.py --substations 3 --days 14
    python seed_demo_data.py --reset   # wipe and re-seed

Author: Vipin Baniya
"""

import asyncio
import argparse
import logging
import random
import math
from datetime import datetime, timedelta
from typing import List

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── Realistic substation profiles ─────────────────────────────────────────

SUBSTATIONS = [
    {"id": "SS001", "name": "Indore North", "region": "MP",
     "capacity_mva": 50, "voltage_kv": 33, "lat": 22.756, "lng": 75.862,
     "base_input": 820, "efficiency": 0.977, "anomaly_prob": 0.04},

    {"id": "SS002", "name": "Indore South", "region": "MP",
     "capacity_mva": 40, "voltage_kv": 33, "lat": 22.671, "lng": 75.880,
     "base_input": 650, "efficiency": 0.981, "anomaly_prob": 0.03},

    {"id": "SS003", "name": "Dewas Industrial", "region": "MP",
     "capacity_mva": 100, "voltage_kv": 66, "lat": 22.968, "lng": 76.051,
     "base_input": 1800, "efficiency": 0.962, "anomaly_prob": 0.08},  # Degraded

    {"id": "SS004", "name": "Ujjain Residential", "region": "MP",
     "capacity_mva": 25, "voltage_kv": 11, "lat": 23.178, "lng": 75.785,
     "base_input": 310, "efficiency": 0.988, "anomaly_prob": 0.02},

    {"id": "SS005", "name": "Pithampur MIDC", "region": "MP",
     "capacity_mva": 80, "voltage_kv": 66, "lat": 22.609, "lng": 75.692,
     "base_input": 1400, "efficiency": 0.971, "anomaly_prob": 0.06},
]

COMPONENTS_PER_SUB = {
    "SS001": [
        {"component_id": "TX001-N", "component_type": "transformer",
         "rated_capacity_kva": 25000, "efficiency_rating": 0.982, "age_years": 8},
        {"component_id": "TX002-N", "component_type": "transformer",
         "rated_capacity_kva": 25000, "efficiency_rating": 0.978, "age_years": 14},
        {"component_id": "LINE-N1", "component_type": "distribution_line",
         "rated_capacity_kva": 15000, "resistance_ohms": 0.38, "length_km": 4.2},
    ],
    "SS002": [
        {"component_id": "TX001-S", "component_type": "transformer",
         "rated_capacity_kva": 40000, "efficiency_rating": 0.984, "age_years": 5},
        {"component_id": "LINE-S1", "component_type": "distribution_line",
         "rated_capacity_kva": 20000, "resistance_ohms": 0.29, "length_km": 3.8},
    ],
    "SS003": [
        {"component_id": "TX001-D", "component_type": "transformer",
         "rated_capacity_kva": 60000, "efficiency_rating": 0.975, "age_years": 19},
        {"component_id": "TX002-D", "component_type": "transformer",
         "rated_capacity_kva": 40000, "efficiency_rating": 0.968, "age_years": 22},
        {"component_id": "LINE-D1", "component_type": "distribution_line",
         "rated_capacity_kva": 40000, "resistance_ohms": 0.45, "length_km": 7.1},
    ],
    "SS004": [
        {"component_id": "TX001-U", "component_type": "transformer",
         "rated_capacity_kva": 25000, "efficiency_rating": 0.991, "age_years": 3},
    ],
    "SS005": [
        {"component_id": "TX001-P", "component_type": "transformer",
         "rated_capacity_kva": 50000, "efficiency_rating": 0.979, "age_years": 11},
        {"component_id": "TX002-P", "component_type": "transformer",
         "rated_capacity_kva": 30000, "efficiency_rating": 0.972, "age_years": 16},
        {"component_id": "LINE-P1", "component_type": "distribution_line",
         "rated_capacity_kva": 30000, "resistance_ohms": 0.52, "length_km": 5.9},
    ],
}

METER_COUNT_PER_SUB = {"SS001": 6, "SS002": 4, "SS003": 10, "SS004": 3, "SS005": 8}


def _diurnal_factor(hour: int) -> float:
    """Realistic 24h load curve: peak 18:00-21:00, trough 02:00-05:00"""
    base = 0.55
    morning = 0.25 * math.sin(math.pi * max(0, hour - 6) / 12)
    evening = 0.35 * math.exp(-0.5 * ((hour - 19) / 2.5) ** 2)
    return max(0.3, base + morning + evening)


def _simulate_physics(sub_profile, day_offset: int, hour: int) -> dict:
    """Simulate one physics analysis for a substation at a given time."""
    rng = random.Random(f"{sub_profile['id']}-{day_offset}-{hour}")
    
    diurnal = _diurnal_factor(hour)
    
    # Gradually degrading substation trend
    trend_factor = 1.0 + (sub_profile['id'] == 'SS003') * day_offset * 0.0015
    
    base = sub_profile["base_input"] * diurnal * trend_factor
    noise = rng.gauss(0, base * 0.02)
    input_mwh = max(10, base + noise)
    
    efficiency = sub_profile["efficiency"]
    # Occasional anomaly
    if rng.random() < sub_profile["anomaly_prob"]:
        efficiency *= rng.uniform(0.88, 0.95)
    
    output_mwh = input_mwh * efficiency * rng.gauss(1.0, 0.005)
    output_mwh = max(0, min(output_mwh, input_mwh * 0.999))
    
    actual_loss = input_mwh - output_mwh
    expected_loss = input_mwh * (1 - sub_profile["efficiency"])
    residual = actual_loss - expected_loss
    residual_pct = abs(residual / input_mwh * 100) if input_mwh > 0 else 0
    confidence = max(0.5, 0.96 - residual_pct * 0.025)
    
    if residual_pct < 1.5:
        status = "balanced"
    elif residual_pct < 4.0:
        status = "minor_imbalance"
    elif residual_pct < 8.0:
        status = "significant_imbalance"
    else:
        status = "critical_imbalance"
    
    return {
        "input_mwh": round(input_mwh, 3),
        "output_mwh": round(output_mwh, 3),
        "expected_loss_mwh": round(expected_loss, 4),
        "actual_loss_mwh": round(actual_loss, 4),
        "residual_mwh": round(residual, 4),
        "residual_pct": round(residual_pct, 2),
        "confidence": round(confidence, 2),
        "status": status,
        "quality": "high" if confidence > 0.85 else "medium",
    }


def _ghi_score(residual_pct: float, confidence: float, anomaly_rate: float) -> tuple:
    """Simplified GHI computation matching the real engine."""
    PBS = max(0.0, 1.0 - max(0, residual_pct - 1) / 6.0)
    ASS = math.exp(-10 * anomaly_rate)
    CS = confidence
    TSS = max(0.5, 1.0 - residual_pct * 0.04)
    DIS = 0.95
    ghi = (0.35 * PBS + 0.20 * ASS + 0.15 * CS + 0.15 * TSS + 0.15 * DIS) * 100
    ghi = round(max(0, min(100, ghi)), 1)
    cls = "HEALTHY" if ghi >= 90 else "STABLE" if ghi >= 70 else "DEGRADED" if ghi >= 50 else "CRITICAL" if ghi >= 30 else "SEVERE"
    return ghi, cls


async def seed(n_substations: int, n_days: int, reset: bool):
    import os
    os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/urjarakshak")
    os.environ.setdefault("SECRET_KEY", "seed-script-dev-key-NOT-for-production-ok")
    os.environ.setdefault("ENVIRONMENT", "development")

    from app.database import engine, Base, init_db, async_session_maker
    from app.models import db_models  # register all models
    from app.models.db_models import (
        User, GridSection, Component, Analysis, GridHealthSnapshot,
        Inspection, MeterUploadBatch, MeterReading, AnomalyResult,
        TransformerAgingRecord, AuditLedger,
    )
    from app.auth import pwd_context
    import uuid

    log.info("Initialising database schema…")
    await init_db()

    async with async_session_maker() as db:
        from sqlalchemy import select, func, text

        # --- Optional reset ---
        if reset:
            log.warning("Resetting demo data…")
            for model in [AuditLedger, TransformerAgingRecord, Inspection,
                          GridHealthSnapshot, AnomalyResult, Analysis,
                          MeterReading, MeterUploadBatch, Component, GridSection]:
                await db.execute(text(f"DELETE FROM {model.__tablename__} WHERE 1=1"))
            await db.commit()
            log.info("Reset complete.")

        # --- Admin user ---
        existing = (await db.execute(select(User).where(User.email == "admin@urjarakshak.dev"))).scalar_one_or_none()
        if not existing:
            admin = User(
                id=str(uuid.uuid4()),
                email="admin@urjarakshak.dev",
                hashed_password=pwd_context.hash("demo1234"),
                full_name="Demo Admin",
                role="admin",
                is_active=True,
                is_verified=True,
            )
            db.add(admin)
            await db.flush()
            user_id = admin.id
            log.info("Created admin user: admin@urjarakshak.dev / demo1234")
        else:
            user_id = existing.id
            log.info("Admin user already exists.")

        subs_to_seed = SUBSTATIONS[:n_substations]
        now = datetime.utcnow()
        start_date = now - timedelta(days=n_days)

        for sub_profile in subs_to_seed:
            sid = sub_profile["id"]

            # Grid section
            existing_sec = (await db.execute(
                select(GridSection).where(GridSection.substation_id == sid)
            )).scalar_one_or_none()
            if existing_sec:
                section = existing_sec
                log.info(f"  {sid}: section exists, adding analyses")
            else:
                section = GridSection(
                    id=str(uuid.uuid4()),
                    substation_id=sid,
                    name=sub_profile["name"],
                    region=sub_profile["region"],
                    capacity_mva=sub_profile["capacity_mva"],
                    voltage_kv=sub_profile["voltage_kv"],
                    location_lat=sub_profile["lat"],
                    location_lng=sub_profile["lng"],
                    status="active",
                )
                db.add(section)
                await db.flush()
                log.info(f"  {sid}: created section")

                # Components
                for comp_data in COMPONENTS_PER_SUB.get(sid, []):
                    db.add(Component(
                        id=str(uuid.uuid4()),
                        grid_section_id=section.id,
                        **comp_data,
                        status="active",
                    ))

            await db.flush()

            # Analyses — 2 per day (morning peak + evening peak)
            hours_to_seed = [9, 19]
            analyses_added = 0
            residual_history = []

            for day_offset in range(n_days):
                for hour in hours_to_seed:
                    ts = start_date + timedelta(days=day_offset, hours=hour)
                    phys = _simulate_physics(sub_profile, day_offset, hour)
                    residual_history.append(phys["residual_pct"])

                    analysis = Analysis(
                        id=str(uuid.uuid4()),
                        grid_section_id=section.id,
                        substation_id=sid,
                        input_energy_mwh=phys["input_mwh"],
                        output_energy_mwh=phys["output_mwh"],
                        time_window_hours=12.0,
                        expected_loss_mwh=phys["expected_loss_mwh"],
                        actual_loss_mwh=phys["actual_loss_mwh"],
                        residual_mwh=phys["residual_mwh"],
                        residual_percentage=phys["residual_pct"],
                        balance_status=phys["status"],
                        confidence_score=phys["confidence"],
                        measurement_quality=phys["quality"],
                        physics_result_json=phys,
                        requires_review=phys["residual_pct"] > 8.0,
                        reviewed=False,
                        created_by=user_id,
                        created_at=ts,
                    )
                    db.add(analysis)
                    await db.flush()

                    # GHI snapshot every 4th analysis
                    if analyses_added % 4 == 0:
                        anomaly_rate = sub_profile["anomaly_prob"] * random.uniform(0.7, 1.4)
                        ghi, cls = _ghi_score(phys["residual_pct"], phys["confidence"], anomaly_rate)
                        db.add(GridHealthSnapshot(
                            id=str(uuid.uuid4()),
                            analysis_id=analysis.id,
                            substation_id=sid,
                            ghi_score=ghi,
                            classification=cls,
                            pbs=round(max(0, 1 - phys["residual_pct"] / 8), 3),
                            ass=round(math.exp(-10 * anomaly_rate), 3),
                            cs=round(phys["confidence"], 3),
                            tss=round(max(0.5, 1 - phys["residual_pct"] * 0.04), 3),
                            dis=0.95,
                            action_required=ghi < 70,
                            inspection_priority="HIGH" if ghi < 50 else "MEDIUM" if ghi < 70 else "LOW",
                            urgency="48h" if ghi < 50 else "7d",
                            interpretation=f"GHI {ghi} — {cls}. Residual {phys['residual_pct']}%.",
                            created_at=ts,
                        ))
                    analyses_added += 1

            await db.commit()
            log.info(f"  {sid}: added {analyses_added} analyses")

            # Inspections — 1–2 per degraded substation
            if sub_profile["anomaly_prob"] > 0.05:
                db.add(Inspection(
                    id=str(uuid.uuid4()),
                    substation_id=sid,
                    priority="HIGH" if sub_profile["anomaly_prob"] > 0.07 else "MEDIUM",
                    status="OPEN",
                    urgency="48h",
                    category="ENERGY_LOSS",
                    description=(
                        f"Elevated residual loss detected at {sub_profile['name']}. "
                        f"Anomaly rate {sub_profile['anomaly_prob']*100:.0f}% over 30-day window. "
                        f"Physics analysis suggests infrastructure degradation."
                    ),
                    recommended_actions=[
                        "Perform transformer impedance test",
                        "Verify meter calibration on high-consumption feeders",
                        "Check for unauthorized load connections",
                    ],
                    created_by=user_id,
                    created_at=now - timedelta(days=2),
                ))
            
            # Transformer aging records
            for comp_data in COMPONENTS_PER_SUB.get(sid, []):
                if comp_data["component_type"] == "transformer":
                    age = comp_data.get("age_years", 10)
                    life_consumed = min(0.99, age / 30 * (1 + sub_profile["anomaly_prob"] * 3))
                    health_index = round((1 - life_consumed) * 100, 1)
                    condition = "GOOD" if health_index > 75 else "FAIR" if health_index > 50 else "POOR" if health_index > 25 else "CRITICAL"
                    remaining = round(max(0, (1 - life_consumed) * 30 / (1 + sub_profile["anomaly_prob"])), 1)
                    db.add(TransformerAgingRecord(
                        id=str(uuid.uuid4()),
                        substation_id=sid,
                        transformer_tag=comp_data["component_id"],
                        install_year=datetime.utcnow().year - int(age),
                        age_years=round(age, 1),
                        load_factor=0.65 + sub_profile["anomaly_prob"] * 3,
                        ambient_temp_c=32.0,
                        hot_spot_temp_c=round(85 + age * 0.8 + sub_profile["anomaly_prob"] * 20, 1),
                        aging_factor_v=round(1.0 + (age - 10) * 0.05 if age > 10 else 0.8, 3),
                        health_index=health_index,
                        condition=condition,
                        remaining_life_years=remaining,
                        failure_probability_12m=round(max(0, min(1, life_consumed - 0.5) * 0.8), 3),
                        recommended_action="Schedule oil analysis" if condition == "POOR" else "Routine monitoring",
                        created_at=now - timedelta(hours=6),
                    ))

        await db.commit()
        log.info("Seed complete.")

        # Summary
        from sqlalchemy import text as sql_text
        total_a = (await db.execute(sql_text("SELECT COUNT(*) FROM analyses"))).scalar()
        total_g = (await db.execute(sql_text("SELECT COUNT(*) FROM grid_health_snapshots"))).scalar()
        total_i = (await db.execute(sql_text("SELECT COUNT(*) FROM inspections"))).scalar()
        print("\n" + "="*50)
        print("✅  Demo data seeded successfully")
        print(f"   Substations : {n_substations}")
        print(f"   Analyses    : {total_a}")
        print(f"   GHI snapshots: {total_g}")
        print(f"   Inspections : {total_i}")
        print(f"   Login        : admin@urjarakshak.dev / demo1234")
        print("="*50 + "\n")

    await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="Seed UrjaRakshak demo data")
    parser.add_argument("--substations", type=int, default=5, choices=[1,2,3,4,5])
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--reset", action="store_true", help="Wipe existing demo data first")
    args = parser.parse_args()

    asyncio.run(seed(args.substations, args.days, args.reset))


if __name__ == "__main__":
    main()
