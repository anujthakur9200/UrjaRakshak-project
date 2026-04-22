"""
UrjaRakshak — SQLAlchemy ORM Models
====================================
Defines all database tables with proper types, indexes, and relationships.

Tables:
  users          — Authenticated users with roles
  grid_sections  — Substations / grid regions
  components     — Grid components per section
  analyses       — Every physics analysis stored here
  anomaly_results — ML anomaly detection results
  model_versions  — Track trained ML models

Author: Vipin Baniya
"""

import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Float, Boolean, Integer,
    DateTime, Date, ForeignKey, Text, Index, JSON
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base


def gen_uuid():
    return str(uuid.uuid4())


# ── Users ─────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    role = Column(String(50), nullable=False, default="viewer")  # admin | analyst | viewer
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_login = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Password recovery fields
    date_of_birth = Column(Date, nullable=True)                # stored as DATE
    security_question = Column(String(255), nullable=True)   # e.g. "Mother's maiden name"
    security_answer_hash = Column(String(255), nullable=True)  # bcrypt hash of lowercased answer

    # Relationships
    analyses = relationship("Analysis", back_populates="created_by_user", lazy="selectin")

    def __repr__(self):
        return f"<User {self.email} ({self.role})>"


# ── Grid Sections ─────────────────────────────────────────────────────────

class GridSection(Base):
    __tablename__ = "grid_sections"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    substation_id = Column(String(100), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=True)
    region = Column(String(100), nullable=True)
    capacity_mva = Column(Float, nullable=True)
    voltage_kv = Column(Float, nullable=True)
    status = Column(String(50), default="active", nullable=False)
    location_lat = Column(Float, nullable=True)
    location_lng = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    components = relationship("Component", back_populates="grid_section", cascade="all, delete-orphan")
    analyses = relationship("Analysis", back_populates="grid_section", cascade="all, delete-orphan")
    anomaly_results = relationship("AnomalyResult", back_populates="grid_section", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<GridSection {self.substation_id}>"


# ── Components ────────────────────────────────────────────────────────────

class Component(Base):
    __tablename__ = "components"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    grid_section_id = Column(UUID(as_uuid=False), ForeignKey("grid_sections.id", ondelete="CASCADE"), nullable=False, index=True)
    component_id = Column(String(100), nullable=False)
    component_type = Column(String(50), nullable=False)    # transformer | line | meter
    rated_capacity_kva = Column(Float, nullable=True)
    efficiency_rating = Column(Float, nullable=True)
    age_years = Column(Float, nullable=True)
    resistance_ohms = Column(Float, nullable=True)
    length_km = Column(Float, nullable=True)
    voltage_kv = Column(Float, nullable=True)
    load_factor = Column(Float, nullable=True)
    status = Column(String(50), default="active")
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    grid_section = relationship("GridSection", back_populates="components")

    __table_args__ = (
        Index("idx_components_grid_section", "grid_section_id"),
        Index("idx_components_type", "component_type"),
    )

    def __repr__(self):
        return f"<Component {self.component_id} ({self.component_type})>"


# ── Analyses ──────────────────────────────────────────────────────────────

class Analysis(Base):
    __tablename__ = "analyses"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    grid_section_id = Column(UUID(as_uuid=False), ForeignKey("grid_sections.id", ondelete="CASCADE"), nullable=True, index=True)
    substation_id = Column(String(100), nullable=False, index=True)  # Denormalized for fast lookup

    # Input values
    input_energy_mwh = Column(Float, nullable=False)
    output_energy_mwh = Column(Float, nullable=False)
    time_window_hours = Column(Float, default=24.0)

    # Physics results
    expected_loss_mwh = Column(Float, nullable=True)
    actual_loss_mwh = Column(Float, nullable=True)
    residual_mwh = Column(Float, nullable=True)
    residual_percentage = Column(Float, nullable=True)
    balance_status = Column(String(50), nullable=True)   # balanced | minor_imbalance | etc.
    confidence_score = Column(Float, nullable=True)
    measurement_quality = Column(String(20), nullable=True)

    # Full result JSON (for detailed view)
    physics_result_json = Column(JSON, nullable=True)
    attribution_result_json = Column(JSON, nullable=True)

    # Workflow
    requires_review = Column(Boolean, default=False)
    reviewed = Column(Boolean, default=False)
    review_notes = Column(Text, nullable=True)
    refusal_reason = Column(Text, nullable=True)

    # User
    created_by = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationships
    grid_section = relationship("GridSection", back_populates="analyses")
    created_by_user = relationship("User", back_populates="analyses")

    __table_args__ = (
        Index("idx_analyses_created_at", "created_at"),
        Index("idx_analyses_substation", "substation_id"),
        Index("idx_analyses_status", "balance_status"),
        Index("idx_analyses_residual", "residual_percentage"),
    )

    def __repr__(self):
        return f"<Analysis {self.substation_id} @ {self.created_at}>"


# ── Anomaly Results ───────────────────────────────────────────────────────

class AnomalyResult(Base):
    __tablename__ = "anomaly_results"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    grid_section_id = Column(UUID(as_uuid=False), ForeignKey("grid_sections.id", ondelete="CASCADE"), nullable=True, index=True)
    analysis_id = Column(UUID(as_uuid=False), ForeignKey("analyses.id", ondelete="SET NULL"), nullable=True)
    substation_id = Column(String(100), nullable=False, index=True)

    # ML results
    is_anomaly = Column(Boolean, nullable=False)
    anomaly_score = Column(Float, nullable=False)
    confidence = Column(Float, nullable=False)
    method_used = Column(String(100), nullable=True)
    primary_reason = Column(Text, nullable=True)
    feature_contributions = Column(JSON, nullable=True)
    recommended_action = Column(Text, nullable=True)

    # Lifecycle
    reviewed = Column(Boolean, default=False)
    action_taken = Column(String(100), nullable=True)  # "inspection_scheduled" | "dismissed" | etc.
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationships
    grid_section = relationship("GridSection", back_populates="anomaly_results")

    __table_args__ = (
        Index("idx_anomaly_created_at", "created_at"),
        Index("idx_anomaly_substation", "substation_id"),
        Index("idx_anomaly_score", "anomaly_score"),
    )

    def __repr__(self):
        return f"<AnomalyResult {self.substation_id} score={self.anomaly_score:.3f}>"


# ── Model Versions ────────────────────────────────────────────────────────

class ModelVersion(Base):
    __tablename__ = "model_versions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    model_name = Column(String(100), nullable=False)
    version = Column(String(50), nullable=False)
    model_type = Column(String(100), nullable=True)          # "IsolationForest"
    n_training_samples = Column(Integer, nullable=True)
    contamination_rate = Column(Float, nullable=True)
    training_score_mean = Column(Float, nullable=True)
    training_score_std = Column(Float, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    is_active = Column(Boolean, default=True)
    trained_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    deployed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_model_versions_name", "model_name"),
        Index("idx_model_versions_active", "is_active"),
    )

    def __repr__(self):
        return f"<ModelVersion {self.model_name} v{self.version}>"


# ── Meter Upload Batch ────────────────────────────────────────────────────

class MeterUploadBatch(Base):
    """Tracks a single CSV/Excel upload session — header record."""
    __tablename__ = "meter_upload_batches"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    filename = Column(String(255), nullable=False)
    substation_id = Column(String(100), nullable=False, index=True)
    row_count = Column(Integer, nullable=False)
    anomalies_detected = Column(Integer, default=0)
    total_energy_kwh = Column(Float, nullable=True)
    residual_pct = Column(Float, nullable=True)
    confidence_score = Column(Float, nullable=True)
    status = Column(String(50), default="processing")  # processing | complete | failed
    error_message = Column(Text, nullable=True)
    uploaded_by = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    readings = relationship("MeterReading", back_populates="batch", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_batch_substation", "substation_id"),
        Index("idx_batch_created_at", "created_at"),
    )

    def __repr__(self):
        return f"<MeterUploadBatch {self.filename} rows={self.row_count}>"


# ── Meter Readings ────────────────────────────────────────────────────────

class MeterReading(Base):
    """Individual meter reading row from uploaded CSV/Excel."""
    __tablename__ = "meter_readings"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    batch_id = Column(UUID(as_uuid=False), ForeignKey("meter_upload_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    meter_id = Column(String(100), nullable=False, index=True)
    substation_id = Column(String(100), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    energy_kwh = Column(Float, nullable=False)

    # Physics + ML results (computed after upload)
    anomaly_score = Column(Float, nullable=True)
    is_anomaly = Column(Boolean, default=False)
    z_score = Column(Float, nullable=True)           # deviation from meter baseline
    expected_kwh = Column(Float, nullable=True)      # physics-predicted expected value
    residual_kwh = Column(Float, nullable=True)      # actual - expected
    anomaly_reason = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    batch = relationship("MeterUploadBatch", back_populates="readings")

    __table_args__ = (
        Index("idx_reading_meter_id", "meter_id"),
        Index("idx_reading_timestamp", "timestamp"),
        Index("idx_reading_anomaly", "is_anomaly"),
        Index("idx_reading_is_anomaly", "is_anomaly"),  # alias for query compatibility
        Index("idx_reading_batch", "batch_id"),
    )

    def __repr__(self):
        return f"<MeterReading {self.meter_id} {self.timestamp} {self.energy_kwh}kWh>"


# ── Grid Health Snapshots ─────────────────────────────────────────────────

class GridHealthSnapshot(Base):
    """
    Computed GHI snapshot for a grid section at a point in time.
    One record per analysis run. Powers GHI trend charts.
    """
    __tablename__ = "grid_health_snapshots"

    id              = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    grid_section_id = Column(UUID(as_uuid=False), ForeignKey("grid_sections.id", ondelete="CASCADE"), nullable=True, index=True)
    analysis_id     = Column(UUID(as_uuid=False), ForeignKey("analyses.id", ondelete="SET NULL"), nullable=True)
    substation_id   = Column(String(100), nullable=False, index=True)

    # GHI result
    ghi_score       = Column(Float, nullable=False)
    classification  = Column(String(20), nullable=False)  # HEALTHY/STABLE/DEGRADED/CRITICAL/SEVERE
    action_required = Column(Boolean, default=False)
    interpretation  = Column(Text, nullable=True)

    # Subscores
    pbs             = Column(Float, nullable=True)  # Physics Balance Score
    ass             = Column(Float, nullable=True)  # Anomaly Stability Score
    cs              = Column(Float, nullable=True)  # Confidence Score
    tss             = Column(Float, nullable=True)  # Trend Stability Score
    dis             = Column(Float, nullable=True)  # Data Integrity Score
    confidence_in_ghi = Column(Float, nullable=True)

    # Risk classification
    inspection_priority = Column(String(20), nullable=True)
    inspection_category = Column(String(30), nullable=True)
    urgency             = Column(String(100), nullable=True)

    created_at      = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    __table_args__ = (
        Index("idx_ghi_created_at",    "created_at"),
        Index("idx_ghi_substation",    "substation_id"),
        Index("idx_ghi_score",         "ghi_score"),
        Index("idx_ghi_classification","classification"),
    )

    def __repr__(self):
        return f"<GridHealthSnapshot {self.substation_id} ghi={self.ghi_score} {self.classification}>"


# ── AI Interpretations ────────────────────────────────────────────────────

class AIInterpretation(Base):
    """
    Stores every AI interpretation call for full audit traceability.
    Prompt hash allows deduplication and prompt drift detection.
    """
    __tablename__ = "ai_interpretations"

    id              = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    analysis_id     = Column(UUID(as_uuid=False), ForeignKey("analyses.id", ondelete="SET NULL"), nullable=True)
    grid_section_id = Column(UUID(as_uuid=False), ForeignKey("grid_sections.id", ondelete="SET NULL"), nullable=True)
    substation_id   = Column(String(100), nullable=False, index=True)

    # Model metadata
    model_name      = Column(String(100), nullable=False)
    model_version   = Column(String(50),  nullable=True)
    prompt_hash     = Column(String(64),  nullable=True, index=True)  # SHA-256 prefix

    # Structured output
    risk_level                      = Column(String(20),  nullable=True)
    inspection_priority             = Column(String(20),  nullable=True)
    primary_infrastructure_hypothesis = Column(Text,       nullable=True)
    recommended_actions             = Column(JSON,        nullable=True)
    confidence_commentary           = Column(Text,        nullable=True)
    trend_assessment                = Column(Text,        nullable=True)
    estimated_investigation_scope   = Column(String(30),  nullable=True)

    # Usage
    token_usage     = Column(Integer, default=0)
    error           = Column(Text, nullable=True)

    created_at      = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    __table_args__ = (
        Index("idx_ai_created_at",    "created_at"),
        Index("idx_ai_substation",    "substation_id"),
        Index("idx_ai_risk_level",    "risk_level"),
        Index("idx_ai_prompt_hash",   "prompt_hash"),
    )

    def __repr__(self):
        return f"<AIInterpretation {self.substation_id} {self.risk_level} model={self.model_name}>"


# ── Inspections ───────────────────────────────────────────────────────────

class Inspection(Base):
    """
    Operational inspection workflow.
    Created when risk classification triggers an action.
    Tracks lifecycle: OPEN → IN_PROGRESS → RESOLVED / DISMISSED.
    """
    __tablename__ = "inspections"

    id              = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    grid_section_id = Column(UUID(as_uuid=False), ForeignKey("grid_sections.id", ondelete="CASCADE"), nullable=True)
    analysis_id     = Column(UUID(as_uuid=False), ForeignKey("analyses.id", ondelete="SET NULL"), nullable=True)
    anomaly_result_id = Column(UUID(as_uuid=False), ForeignKey("anomaly_results.id", ondelete="SET NULL"), nullable=True)
    ghi_snapshot_id = Column(UUID(as_uuid=False), ForeignKey("grid_health_snapshots.id", ondelete="SET NULL"), nullable=True)
    substation_id   = Column(String(100), nullable=False, index=True)

    # Classification
    priority        = Column(String(20), nullable=False)   # CRITICAL/HIGH/MEDIUM/LOW
    category        = Column(String(30), nullable=True)
    urgency         = Column(String(100), nullable=True)

    # Workflow
    status          = Column(String(20), default="OPEN", nullable=False)
    # OPEN | IN_PROGRESS | RESOLVED | DISMISSED
    assigned_to     = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Content
    description     = Column(Text, nullable=True)
    ai_recommendation = Column(Text, nullable=True)
    recommended_actions = Column(JSON, nullable=True)
    findings        = Column(Text, nullable=True)
    resolution_notes = Column(Text, nullable=True)
    resolution      = Column(String(50), nullable=True)
    # TECHNICAL_LOSS_NORMAL / EQUIPMENT_FAULT / METER_ISSUE / DATA_QUALITY / OTHER

    created_by      = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at      = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    closed_at       = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_inspection_substation", "substation_id"),
        Index("idx_inspection_status",     "status"),
        Index("idx_inspection_priority",   "priority"),
        Index("idx_inspection_created_at", "created_at"),
    )

    def __repr__(self):
        return f"<Inspection {self.substation_id} {self.priority} {self.status}>"


# ════════════════════════════════════════════════════════════════════════════
# v2.3 — Multi-Tenancy + Streaming + Per-Meter Stability + Drift + Aging
# ════════════════════════════════════════════════════════════════════════════

# ── Organizations (Multi-Tenant) ──────────────────────────────────────────

class Organization(Base):
    """
    Top-level tenant. Every data record belongs to one org.
    Utilities are billed and isolated at this level.
    """
    __tablename__ = "organizations"

    id             = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    slug           = Column(String(80),  unique=True, nullable=False, index=True)  # url-safe short name
    name           = Column(String(255), nullable=False)
    plan           = Column(String(50),  default="free")          # free | starter | pro | enterprise
    api_key_hash   = Column(String(64),  nullable=True, index=True)  # SHA-256 of API key for API-as-a-Service
    max_substations = Column(Integer, default=5)
    max_analyses_per_day = Column(Integer, default=50)
    contact_email  = Column(String(255), nullable=True)
    is_active      = Column(Boolean, default=True, nullable=False)
    created_at     = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at     = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_org_slug",     "slug"),
        Index("idx_org_api_key",  "api_key_hash"),
        Index("idx_org_active",   "is_active"),
    )

    def __repr__(self):
        return f"<Organization {self.slug} ({self.plan})>"


class OrganizationMember(Base):
    """Maps users to organizations with org-level roles."""
    __tablename__ = "organization_members"

    id          = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    org_id      = Column(UUID(as_uuid=False), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    user_id     = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    org_role    = Column(String(30), default="member")  # owner | admin | analyst | viewer
    joined_at   = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_orgmember_org",  "org_id"),
        Index("idx_orgmember_user", "user_id"),
    )

    def __repr__(self):
        return f"<OrgMember org={self.org_id} user={self.user_id} role={self.org_role}>"


# ── Live Meter Stream ─────────────────────────────────────────────────────

class LiveMeterEvent(Base):
    """
    Individual real-time meter push event from SCADA/AMI systems.
    Ingested via SSE/WebSocket endpoint, persisted for rolling window analysis.
    Older events are pruned after DATA_RETENTION_DAYS.
    """
    __tablename__ = "live_meter_events"

    id             = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    org_id         = Column(UUID(as_uuid=False), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    meter_id       = Column(String(100), nullable=False, index=True)
    substation_id  = Column(String(100), nullable=False, index=True)
    event_ts       = Column(DateTime, nullable=False, index=True)       # meter-reported timestamp
    received_at    = Column(DateTime, default=datetime.utcnow, nullable=False)
    energy_kwh     = Column(Float, nullable=False)
    voltage_v      = Column(Float, nullable=True)
    current_a      = Column(Float, nullable=True)
    power_factor   = Column(Float, nullable=True)
    source         = Column(String(50), default="api")   # api | websocket | mqtt | csv_upload

    # Rolling anomaly result (computed inline on ingest)
    is_anomaly     = Column(Boolean, default=False)
    anomaly_score  = Column(Float, nullable=True)
    z_score        = Column(Float, nullable=True)

    __table_args__ = (
        Index("idx_live_meter_id",       "meter_id"),
        Index("idx_live_substation",     "substation_id"),
        Index("idx_live_event_ts",       "event_ts"),
        Index("idx_live_received_at",    "received_at"),
        Index("idx_live_is_anomaly",     "is_anomaly"),
    )

    def __repr__(self):
        return f"<LiveMeterEvent {self.meter_id} {self.event_ts} {self.energy_kwh}kWh>"


# ── Per-Meter Stability Scores ─────────────────────────────────────────────

class MeterStabilityScore(Base):
    """
    Rolling stability score per meter, recomputed on each new reading.
    Tracks: rolling mean, std dev, z-score percentile, trend slope.
    This is what makes per-meter intelligence possible vs batch-level only.
    """
    __tablename__ = "meter_stability_scores"

    id              = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    org_id          = Column(UUID(as_uuid=False), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)
    meter_id        = Column(String(100), nullable=False, index=True)
    substation_id   = Column(String(100), nullable=False, index=True)

    # Rolling statistics (computed over last N readings)
    window_size     = Column(Integer, default=30)         # readings used
    rolling_mean_kwh = Column(Float, nullable=True)
    rolling_std_kwh  = Column(Float, nullable=True)
    rolling_cv      = Column(Float, nullable=True)        # coefficient of variation = std/mean
    stability_score = Column(Float, nullable=True)        # 0–1, higher = more stable

    # Trend
    trend_slope     = Column(Float, nullable=True)        # kWh/reading, linear regression slope
    trend_direction = Column(String(10), nullable=True)   # UP | DOWN | FLAT
    anomaly_rate_30d = Column(Float, nullable=True)       # fraction of readings flagged in window

    # Z-score percentile bands
    p95_kwh         = Column(Float, nullable=True)
    p5_kwh          = Column(Float, nullable=True)

    # Metadata
    total_readings  = Column(Integer, default=0)
    last_reading_kwh = Column(Float, nullable=True)
    last_reading_ts  = Column(DateTime, nullable=True)
    computed_at     = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at      = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_mstab_meter_id",    "meter_id"),
        Index("idx_mstab_substation",  "substation_id"),
        Index("idx_mstab_score",       "stability_score"),
        Index("idx_mstab_computed_at", "computed_at"),
    )

    def __repr__(self):
        return f"<MeterStabilityScore {self.meter_id} score={self.stability_score}>"


# ── ML Model Drift Log ────────────────────────────────────────────────────

class ModelDriftLog(Base):
    """
    Records drift detection results for the Isolation Forest model.
    If drift exceeds threshold, auto-retraining is triggered.
    Immutable — append-only. Never updated after insert.
    """
    __tablename__ = "model_drift_logs"

    id                  = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    model_version_id    = Column(UUID(as_uuid=False), ForeignKey("model_versions.id", ondelete="SET NULL"), nullable=True)
    model_name          = Column(String(100), nullable=False)

    # Drift metrics
    reference_anomaly_rate  = Column(Float, nullable=True)   # baseline rate when model was trained
    current_anomaly_rate    = Column(Float, nullable=True)   # recent rate
    drift_magnitude         = Column(Float, nullable=True)   # abs(current - reference)
    psi_score               = Column(Float, nullable=True)   # Population Stability Index
    ks_statistic            = Column(Float, nullable=True)   # Kolmogorov-Smirnov test statistic
    ks_pvalue               = Column(Float, nullable=True)

    # Classification
    drift_level         = Column(String(20), nullable=True)  # NONE | MINOR | MODERATE | SEVERE
    requires_retraining = Column(Boolean, default=False)
    retrained           = Column(Boolean, default=False)
    retrain_triggered_at = Column(DateTime, nullable=True)

    # Window
    reference_window_days = Column(Integer, default=30)
    evaluation_window_days = Column(Integer, default=7)
    n_reference_samples   = Column(Integer, nullable=True)
    n_evaluation_samples  = Column(Integer, nullable=True)

    detected_at         = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    __table_args__ = (
        Index("idx_drift_model",       "model_name"),
        Index("idx_drift_detected_at", "detected_at"),
        Index("idx_drift_level",       "drift_level"),
    )

    def __repr__(self):
        return f"<ModelDriftLog {self.model_name} {self.drift_level} psi={self.psi_score}>"


# ── Transformer Aging Records ─────────────────────────────────────────────

class TransformerAgingRecord(Base):
    """
    IEC 60076-7 thermal aging model for distribution transformers.
    Tracks: thermal aging factor, insulation life consumed, estimated RUL.
    Updated on each analysis run for substations with transformer data.
    """
    __tablename__ = "transformer_aging_records"

    id                  = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    org_id              = Column(UUID(as_uuid=False), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)
    component_id        = Column(UUID(as_uuid=False), ForeignKey("components.id", ondelete="CASCADE"), nullable=True)
    substation_id       = Column(String(100), nullable=False, index=True)
    transformer_tag     = Column(String(100), nullable=False)   # e.g. "TX-SS001-01"

    # Nameplate data
    rated_kva           = Column(Float, nullable=True)
    rated_voltage_kv    = Column(Float, nullable=True)
    install_year        = Column(Integer, nullable=True)
    designed_life_years = Column(Float, default=30.0)

    # Thermal model inputs (IEC 60076-7)
    top_oil_temp_c      = Column(Float, nullable=True)          # measured or estimated
    ambient_temp_c      = Column(Float, nullable=True)
    hot_spot_temp_c     = Column(Float, nullable=True)          # computed: Θh = Θo + ΔΘh
    load_factor         = Column(Float, nullable=True)

    # Aging outputs
    thermal_aging_factor = Column(Float, nullable=True)         # V = exp(15000/371 - 15000/(Θh+273)), V=1.0 at 98°C
    life_consumed_pct    = Column(Float, nullable=True)         # cumulative since install
    estimated_rul_years  = Column(Float, nullable=True)         # remaining useful life
    failure_probability  = Column(Float, nullable=True)         # 0–1 over next 12 months
    health_index         = Column(Float, nullable=True)         # 0–100, IEC-based

    # Classification
    condition_class     = Column(String(20), nullable=True)     # GOOD | FAIR | POOR | CRITICAL
    maintenance_flag    = Column(Boolean, default=False)
    replacement_flag    = Column(Boolean, default=False)

    computed_at         = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at          = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_txaging_substation",    "substation_id"),
        Index("idx_txaging_tag",           "transformer_tag"),
        Index("idx_txaging_condition",     "condition_class"),
        Index("idx_txaging_failure_prob",  "failure_probability"),
        Index("idx_txaging_computed_at",   "computed_at"),
    )

    def __repr__(self):
        return f"<TransformerAgingRecord {self.transformer_tag} RUL={self.estimated_rul_years}yr>"


# ── Immutable Audit Ledger ─────────────────────────────────────────────────

class AuditLedger(Base):
    """
    Append-only immutable audit log. NEVER updated. Each row has a
    SHA-256 chain hash linking it to the previous entry for tamper detection.
    
    Utilities require this for regulatory compliance (CERC, CEA in India;
    NERC, FERC in USA; etc.)
    """
    __tablename__ = "audit_ledger"

    id              = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    sequence_no     = Column(Integer, nullable=False, index=True)    # monotonic counter
    org_id          = Column(UUID(as_uuid=False), nullable=True, index=True)
    user_id         = Column(UUID(as_uuid=False), nullable=True)
    user_email      = Column(String(255), nullable=True)             # denormalized for immutability
    user_role       = Column(String(50), nullable=True)

    # Event
    event_type      = Column(String(80), nullable=False, index=True)
    # ANALYSIS_RUN | ANOMALY_FLAGGED | INSPECTION_CREATED | INSPECTION_UPDATED
    # INSPECTION_RESOLVED | MODEL_RETRAINED | DRIFT_DETECTED | API_KEY_USED
    # USER_LOGIN | USER_CREATED | CONFIG_CHANGED | DATA_EXPORTED
    resource_type   = Column(String(50), nullable=True)
    resource_id     = Column(String(100), nullable=True)
    substation_id   = Column(String(100), nullable=True)

    # Payload (structured, no PII in values)
    summary         = Column(Text, nullable=True)
    metadata_json   = Column(JSON, nullable=True)

    # Chain integrity
    entry_hash      = Column(String(64), nullable=False)    # SHA-256 of this entry's content
    prev_hash       = Column(String(64), nullable=True)     # SHA-256 of previous entry

    recorded_at     = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    ip_address      = Column(String(45), nullable=True)     # IPv4 or IPv6

    __table_args__ = (
        Index("idx_audit_recorded_at",  "recorded_at"),
        Index("idx_audit_event_type",   "event_type"),
        Index("idx_audit_org_id",       "org_id"),
        Index("idx_audit_sequence",     "sequence_no"),
    )

    def __repr__(self):
        return f"<AuditLedger #{self.sequence_no} {self.event_type}>"
