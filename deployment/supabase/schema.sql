-- UrjaRakshak — Complete Database Schema
-- Compatible with: Supabase, Neon, Railway, local PostgreSQL 14+
--
-- Safe to run on a fresh database. All statements are idempotent.
-- Note: PostgreSQL does NOT support "CREATE POLICY IF NOT EXISTS".
--       Policies are dropped and recreated safely below.
--
-- Run order matters: tables with FK dependencies come after their targets.
-- =========================================================================

-- ── Enable required extensions ───────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- gen_random_uuid()


-- =========================================================================
-- CORE TABLES
-- =========================================================================

-- ── Users ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    email           VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    full_name       VARCHAR(255),
    role            VARCHAR(50)  NOT NULL DEFAULT 'viewer',   -- admin | analyst | viewer
    is_active       BOOLEAN      NOT NULL DEFAULT true,
    is_verified     BOOLEAN      NOT NULL DEFAULT false,
    last_login      TIMESTAMP,
    created_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP    NOT NULL DEFAULT NOW()
);

-- ── Grid Sections (Substations) ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS grid_sections (
    id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    substation_id   VARCHAR(100) UNIQUE NOT NULL,
    name            VARCHAR(255),
    region          VARCHAR(100),
    capacity_mva    DECIMAL(10,2),
    voltage_kv      DECIMAL(8,2),
    location_lat    DECIMAL(10,7),
    location_lng    DECIMAL(10,7),
    status          VARCHAR(50)  NOT NULL DEFAULT 'active',
    created_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP    NOT NULL DEFAULT NOW()
);

-- ── Components ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS components (
    id                  UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    grid_section_id     UUID         NOT NULL REFERENCES grid_sections(id) ON DELETE CASCADE,
    component_id        VARCHAR(100) NOT NULL,
    component_type      VARCHAR(50)  NOT NULL,
    rated_capacity_kva  DECIMAL(10,2),
    efficiency_rating   DECIMAL(5,4),
    age_years           INTEGER,
    resistance_ohms     DECIMAL(10,6),
    length_km           DECIMAL(10,3),
    voltage_kv          DECIMAL(8,2),
    load_factor         DECIMAL(5,4),
    metadata_json       JSONB,
    created_at          TIMESTAMP    NOT NULL DEFAULT NOW(),
    UNIQUE(grid_section_id, component_id)
);

-- ── Analyses ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS analyses (
    id                      UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    grid_section_id         UUID          REFERENCES grid_sections(id) ON DELETE SET NULL,
    substation_id           VARCHAR(100)  NOT NULL,
    input_energy_mwh        DECIMAL(12,4) NOT NULL,
    output_energy_mwh       DECIMAL(12,4) NOT NULL,
    time_window_hours       DECIMAL(8,2)  NOT NULL DEFAULT 24.0,
    expected_loss_mwh       DECIMAL(12,4),
    actual_loss_mwh         DECIMAL(12,4),
    residual_mwh            DECIMAL(12,4),
    residual_percentage     DECIMAL(8,4),
    balance_status          VARCHAR(50)   NOT NULL,
    confidence_score        DECIMAL(5,4),
    measurement_quality     VARCHAR(20),
    physics_result_json     JSONB,
    attribution_result_json JSONB,
    requires_review         BOOLEAN       NOT NULL DEFAULT false,
    reviewed                BOOLEAN       NOT NULL DEFAULT false,
    review_notes            TEXT,
    refusal_reason          TEXT,
    created_by              UUID          REFERENCES users(id) ON DELETE SET NULL,
    created_at              TIMESTAMP     NOT NULL DEFAULT NOW()
);

-- ── Anomaly Results ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS anomaly_results (
    id                    UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    grid_section_id       UUID         REFERENCES grid_sections(id) ON DELETE SET NULL,
    analysis_id           UUID         REFERENCES analyses(id) ON DELETE SET NULL,
    substation_id         VARCHAR(100) NOT NULL,
    is_anomaly            BOOLEAN      NOT NULL DEFAULT false,
    anomaly_score         DECIMAL(5,4) NOT NULL,
    confidence            DECIMAL(5,4) NOT NULL,
    method_used           VARCHAR(50),
    primary_reason        TEXT,
    feature_contributions JSONB,
    recommended_action    TEXT,
    reviewed              BOOLEAN      NOT NULL DEFAULT false,
    action_taken          TEXT,
    created_at            TIMESTAMP    NOT NULL DEFAULT NOW()
);

-- ── Model Versions ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS model_versions (
    id                  UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    model_name          VARCHAR(100) NOT NULL,
    version             VARCHAR(50)  NOT NULL,
    model_type          VARCHAR(100),
    n_training_samples  INTEGER,
    contamination_rate  DECIMAL(5,4),
    training_score_mean DECIMAL(8,6),
    training_score_std  DECIMAL(8,6),
    metadata_json       JSONB,
    is_active           BOOLEAN      NOT NULL DEFAULT false,
    trained_at          TIMESTAMP,
    deployed_at         TIMESTAMP,
    created_at          TIMESTAMP    NOT NULL DEFAULT NOW()
);

-- ── Meter Upload Batches ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS meter_upload_batches (
    id               UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    filename         VARCHAR(255) NOT NULL,
    substation_id    VARCHAR(100) NOT NULL,
    row_count        INTEGER      NOT NULL,
    anomalies_detected INTEGER    DEFAULT 0,
    total_energy_kwh DECIMAL(14,4),
    residual_pct     DECIMAL(8,4),
    confidence_score DECIMAL(5,4),
    status           VARCHAR(50)  NOT NULL DEFAULT 'processing',
    error_message    TEXT,
    uploaded_by      UUID         REFERENCES users(id) ON DELETE SET NULL,
    created_at       TIMESTAMP    NOT NULL DEFAULT NOW(),
    completed_at     TIMESTAMP
);

-- ── Meter Readings ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS meter_readings (
    id              UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id        UUID          NOT NULL REFERENCES meter_upload_batches(id) ON DELETE CASCADE,
    meter_id        VARCHAR(100)  NOT NULL,
    substation_id   VARCHAR(100)  NOT NULL,
    timestamp       TIMESTAMP     NOT NULL,
    energy_kwh      DECIMAL(12,4) NOT NULL,
    anomaly_score   DECIMAL(5,4),
    is_anomaly      BOOLEAN       DEFAULT false,
    z_score         DECIMAL(8,4),
    expected_kwh    DECIMAL(12,4),
    residual_kwh    DECIMAL(12,4),
    anomaly_reason  VARCHAR(255),
    created_at      TIMESTAMP     NOT NULL DEFAULT NOW()
);


-- =========================================================================
-- v2.2 — GHI + AI Interpretations + Inspections
-- =========================================================================

-- ── Grid Health Snapshots ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS grid_health_snapshots (
    id                  UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    grid_section_id     UUID         REFERENCES grid_sections(id) ON DELETE CASCADE,
    analysis_id         UUID         REFERENCES analyses(id) ON DELETE SET NULL,
    substation_id       VARCHAR(100) NOT NULL,
    ghi_score           DECIMAL(6,2) NOT NULL,
    classification      VARCHAR(20)  NOT NULL,
    action_required     BOOLEAN      DEFAULT false,
    interpretation      TEXT,
    confidence_in_ghi   DECIMAL(5,4),
    -- GHI sub-scores (0–1)
    pbs                 DECIMAL(6,4),   -- Physics Balance Score
    ass                 DECIMAL(6,4),   -- Anomaly Stability Score
    cs                  DECIMAL(6,4),   -- Confidence Score
    tss                 DECIMAL(6,4),   -- Trend Stability Score
    dis                 DECIMAL(6,4),   -- Data Integrity Score
    -- Risk classification
    inspection_priority VARCHAR(20),
    inspection_category VARCHAR(30),
    urgency             VARCHAR(100),
    created_at          TIMESTAMP    NOT NULL DEFAULT NOW()
);

-- ── AI Interpretations ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ai_interpretations (
    id                                UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id                       UUID         REFERENCES analyses(id) ON DELETE SET NULL,
    grid_section_id                   UUID         REFERENCES grid_sections(id) ON DELETE SET NULL,
    substation_id                     VARCHAR(100) NOT NULL,
    model_name                        VARCHAR(100) NOT NULL,
    model_version                     VARCHAR(50),
    prompt_hash                       VARCHAR(64),
    risk_level                        VARCHAR(20),
    inspection_priority               VARCHAR(20),
    primary_infrastructure_hypothesis TEXT,
    recommended_actions               JSONB,
    confidence_commentary             TEXT,
    trend_assessment                  TEXT,
    estimated_investigation_scope     VARCHAR(30),
    token_usage                       INTEGER      DEFAULT 0,
    error                             TEXT,
    created_at                        TIMESTAMP    NOT NULL DEFAULT NOW()
);

-- ── Inspections ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS inspections (
    id                UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    grid_section_id   UUID         REFERENCES grid_sections(id) ON DELETE CASCADE,
    analysis_id       UUID         REFERENCES analyses(id) ON DELETE SET NULL,
    anomaly_result_id UUID         REFERENCES anomaly_results(id) ON DELETE SET NULL,
    ghi_snapshot_id   UUID         REFERENCES grid_health_snapshots(id) ON DELETE SET NULL,
    substation_id     VARCHAR(100) NOT NULL,
    priority          VARCHAR(20)  NOT NULL,
    category          VARCHAR(30),
    urgency           VARCHAR(100),
    status            VARCHAR(20)  NOT NULL DEFAULT 'OPEN',
    assigned_to       UUID         REFERENCES users(id) ON DELETE SET NULL,
    description       TEXT,
    recommended_actions JSONB,
    findings          TEXT,
    resolution_notes  TEXT,
    resolution        VARCHAR(50),
    created_by        UUID         REFERENCES users(id) ON DELETE SET NULL,
    created_at        TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMP    NOT NULL DEFAULT NOW(),
    closed_at         TIMESTAMP
);


-- =========================================================================
-- v2.3 — Multi-Tenancy + Streaming + Drift + Transformer Aging + Audit
-- =========================================================================

-- ── Organizations ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS organizations (
    id                   UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    slug                 VARCHAR(80)  UNIQUE NOT NULL,
    name                 VARCHAR(255) NOT NULL,
    plan                 VARCHAR(50)  NOT NULL DEFAULT 'free',  -- free | starter | pro | enterprise
    api_key_hash         VARCHAR(64)  UNIQUE,                   -- SHA-256 of API key
    max_substations      INTEGER      DEFAULT 5,
    max_analyses_per_day INTEGER      DEFAULT 50,
    contact_email        VARCHAR(255),
    is_active            BOOLEAN      NOT NULL DEFAULT true,
    created_at           TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMP    NOT NULL DEFAULT NOW()
);

-- ── Organization Members ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS organization_members (
    id        UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id    UUID         NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id   UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    org_role  VARCHAR(30)  NOT NULL DEFAULT 'member',   -- owner | admin | analyst | viewer | member
    joined_at TIMESTAMP    NOT NULL DEFAULT NOW(),
    UNIQUE(org_id, user_id)
);

-- ── Live Meter Events (Streaming) ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS live_meter_events (
    id            UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        UUID          REFERENCES organizations(id) ON DELETE SET NULL,
    meter_id      VARCHAR(100)  NOT NULL,
    substation_id VARCHAR(100)  NOT NULL,
    event_ts      TIMESTAMP     NOT NULL,
    received_at   TIMESTAMP     NOT NULL DEFAULT NOW(),
    energy_kwh    DECIMAL(12,4) NOT NULL,
    voltage_v     DECIMAL(10,3),
    current_a     DECIMAL(10,3),
    power_factor  DECIMAL(5,4),
    source        VARCHAR(30)   DEFAULT 'api',
    z_score       DECIMAL(8,4),
    is_anomaly    BOOLEAN       NOT NULL DEFAULT false,
    anomaly_score DECIMAL(5,4),
    anomaly_reason VARCHAR(100)
);

-- ── Per-Meter Stability Scores ─────────────────────────────────────────────
-- Columns aligned exactly with MeterStabilityScore ORM model in db_models.py
CREATE TABLE IF NOT EXISTS meter_stability_scores (
    id               UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           UUID          REFERENCES organizations(id) ON DELETE SET NULL,
    meter_id         VARCHAR(100)  NOT NULL,
    substation_id    VARCHAR(100)  NOT NULL,
    window_size      INTEGER       DEFAULT 30,
    rolling_mean_kwh DECIMAL(12,4),
    rolling_std_kwh  DECIMAL(12,4),
    rolling_cv       DECIMAL(8,6),                          -- coefficient of variation
    stability_score  DECIMAL(6,4)  NOT NULL DEFAULT 0.5,
    trend_slope      DECIMAL(12,8),
    trend_direction  VARCHAR(10),                           -- UP | DOWN | FLAT | UNKNOWN
    anomaly_rate_30d DECIMAL(6,4),
    p5_kwh           DECIMAL(12,4),
    p95_kwh          DECIMAL(12,4),
    total_readings   INTEGER       DEFAULT 0,
    last_reading_kwh DECIMAL(12,4),
    last_reading_ts  TIMESTAMP,
    updated_at       TIMESTAMP     NOT NULL DEFAULT NOW(),
    UNIQUE(meter_id, substation_id)
);

-- ── Model Drift Logs ───────────────────────────────────────────────────────
-- Columns aligned with ModelDriftLog ORM model
CREATE TABLE IF NOT EXISTS model_drift_logs (
    id                  UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID         REFERENCES organizations(id) ON DELETE SET NULL,
    psi                 DECIMAL(8,6),
    drift_level         VARCHAR(20)  NOT NULL,              -- NONE | MINOR | MODERATE | SEVERE
    ks_statistic        DECIMAL(8,6),
    ks_pvalue           DECIMAL(8,6),
    reference_rate      DECIMAL(6,4),
    current_rate        DECIMAL(6,4),
    rate_shift          DECIMAL(6,4),
    n_reference         INTEGER      NOT NULL DEFAULT 0,
    n_evaluation        INTEGER      NOT NULL DEFAULT 0,
    sufficient_data     BOOLEAN      NOT NULL DEFAULT false,
    requires_retraining BOOLEAN      NOT NULL DEFAULT false,
    retrain_triggered   BOOLEAN      NOT NULL DEFAULT false,
    interpretation      TEXT,
    detected_at         TIMESTAMP    NOT NULL DEFAULT NOW()
);

-- ── Transformer Aging Records ──────────────────────────────────────────────
-- Columns aligned with TransformerAgingRecord ORM model (IEC 60076-7)
CREATE TABLE IF NOT EXISTS transformer_aging_records (
    id                   UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id               UUID          REFERENCES organizations(id) ON DELETE SET NULL,
    substation_id        VARCHAR(100)  NOT NULL,
    transformer_tag      VARCHAR(100)  NOT NULL,
    rated_kva            DECIMAL(10,2),
    install_year         INTEGER,
    designed_life_years  DECIMAL(6,2)  DEFAULT 30,
    top_oil_temp_c       DECIMAL(6,2),
    ambient_temp_c       DECIMAL(6,2),
    hot_spot_temp_c      DECIMAL(6,2),
    load_factor          DECIMAL(5,4),
    thermal_aging_factor DECIMAL(10,6),                    -- V from IEC 60076-7 (ref=98°C)
    life_consumed_pct    DECIMAL(6,2),
    estimated_rul_years  DECIMAL(6,2),
    failure_probability  DECIMAL(6,4),
    health_index         DECIMAL(6,2),
    condition_class      VARCHAR(20),                      -- GOOD | FAIR | POOR | CRITICAL
    maintenance_flag     BOOLEAN       DEFAULT false,
    replacement_flag     BOOLEAN       DEFAULT false,
    computed_at          TIMESTAMP     NOT NULL DEFAULT NOW(),
    created_at           TIMESTAMP     NOT NULL DEFAULT NOW(),
    UNIQUE(substation_id, transformer_tag)
);

-- ── Immutable Audit Ledger ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_ledger (
    id            UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    sequence_no   INTEGER      NOT NULL,
    org_id        UUID         REFERENCES organizations(id) ON DELETE SET NULL,
    user_id       UUID         REFERENCES users(id) ON DELETE SET NULL,
    user_email    VARCHAR(255),
    user_role     VARCHAR(50),
    event_type    VARCHAR(80)  NOT NULL,
    resource_type VARCHAR(50),
    resource_id   VARCHAR(100),
    substation_id VARCHAR(100),
    summary       TEXT,
    metadata_json JSONB,
    entry_hash    VARCHAR(64)  NOT NULL,
    prev_hash     VARCHAR(64),
    recorded_at   TIMESTAMP    NOT NULL DEFAULT NOW(),
    ip_address    VARCHAR(45)
);


-- =========================================================================
-- INDEXES
-- =========================================================================

CREATE INDEX IF NOT EXISTS idx_analyses_created_at    ON analyses(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_analyses_substation    ON analyses(substation_id);
CREATE INDEX IF NOT EXISTS idx_analyses_status        ON analyses(balance_status);
CREATE INDEX IF NOT EXISTS idx_analyses_residual      ON analyses(residual_percentage);

CREATE INDEX IF NOT EXISTS idx_anomaly_created_at     ON anomaly_results(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_anomaly_substation     ON anomaly_results(substation_id);
CREATE INDEX IF NOT EXISTS idx_anomaly_score          ON anomaly_results(anomaly_score DESC);

CREATE INDEX IF NOT EXISTS idx_components_section     ON components(grid_section_id);
CREATE INDEX IF NOT EXISTS idx_components_type        ON components(component_type);

CREATE INDEX IF NOT EXISTS idx_batch_substation       ON meter_upload_batches(substation_id);
CREATE INDEX IF NOT EXISTS idx_batch_created_at       ON meter_upload_batches(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_reading_batch          ON meter_readings(batch_id);
CREATE INDEX IF NOT EXISTS idx_reading_meter          ON meter_readings(meter_id);
CREATE INDEX IF NOT EXISTS idx_reading_timestamp      ON meter_readings(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_reading_anomaly        ON meter_readings(is_anomaly) WHERE is_anomaly = true;

CREATE INDEX IF NOT EXISTS idx_ghi_created_at         ON grid_health_snapshots(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ghi_substation         ON grid_health_snapshots(substation_id);
CREATE INDEX IF NOT EXISTS idx_ghi_score              ON grid_health_snapshots(ghi_score);
CREATE INDEX IF NOT EXISTS idx_ghi_classification     ON grid_health_snapshots(classification);

CREATE INDEX IF NOT EXISTS idx_ai_created_at          ON ai_interpretations(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_substation          ON ai_interpretations(substation_id);
CREATE INDEX IF NOT EXISTS idx_ai_risk_level          ON ai_interpretations(risk_level);
CREATE INDEX IF NOT EXISTS idx_ai_prompt_hash         ON ai_interpretations(prompt_hash);

CREATE INDEX IF NOT EXISTS idx_inspection_substation  ON inspections(substation_id);
CREATE INDEX IF NOT EXISTS idx_inspection_status      ON inspections(status);
CREATE INDEX IF NOT EXISTS idx_inspection_priority    ON inspections(priority);
CREATE INDEX IF NOT EXISTS idx_inspection_created_at  ON inspections(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_org_slug               ON organizations(slug);
CREATE INDEX IF NOT EXISTS idx_org_api_key            ON organizations(api_key_hash);
CREATE INDEX IF NOT EXISTS idx_org_active             ON organizations(is_active);

CREATE INDEX IF NOT EXISTS idx_orgmember_org          ON organization_members(org_id);
CREATE INDEX IF NOT EXISTS idx_orgmember_user         ON organization_members(user_id);

CREATE INDEX IF NOT EXISTS idx_live_substation        ON live_meter_events(substation_id, event_ts DESC);
CREATE INDEX IF NOT EXISTS idx_live_meter             ON live_meter_events(meter_id, event_ts DESC);
CREATE INDEX IF NOT EXISTS idx_live_anomaly           ON live_meter_events(is_anomaly) WHERE is_anomaly = true;
CREATE INDEX IF NOT EXISTS idx_live_received          ON live_meter_events(received_at DESC);

CREATE INDEX IF NOT EXISTS idx_stability_substation   ON meter_stability_scores(substation_id);
CREATE INDEX IF NOT EXISTS idx_stability_meter        ON meter_stability_scores(meter_id);
CREATE INDEX IF NOT EXISTS idx_stability_score        ON meter_stability_scores(stability_score);

CREATE INDEX IF NOT EXISTS idx_drift_detected_at      ON model_drift_logs(detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_drift_level            ON model_drift_logs(drift_level);
CREATE INDEX IF NOT EXISTS idx_drift_retrain          ON model_drift_logs(requires_retraining) WHERE requires_retraining = true;

CREATE INDEX IF NOT EXISTS idx_txaging_substation     ON transformer_aging_records(substation_id);
CREATE INDEX IF NOT EXISTS idx_txaging_tag            ON transformer_aging_records(transformer_tag);
CREATE INDEX IF NOT EXISTS idx_txaging_condition      ON transformer_aging_records(condition_class);
CREATE INDEX IF NOT EXISTS idx_txaging_failure_prob   ON transformer_aging_records(failure_probability DESC);
CREATE INDEX IF NOT EXISTS idx_txaging_computed       ON transformer_aging_records(computed_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_audit_sequence  ON audit_ledger(sequence_no);
CREATE INDEX IF NOT EXISTS idx_audit_recorded_at      ON audit_ledger(recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_event_type       ON audit_ledger(event_type);
CREATE INDEX IF NOT EXISTS idx_audit_org              ON audit_ledger(org_id);


-- =========================================================================
-- ROW LEVEL SECURITY
-- Supabase/Postgres RLS: backend uses service-role key → bypasses RLS.
-- All policies below allow all operations (service role bypass pattern).
-- "CREATE POLICY IF NOT EXISTS" is NOT valid SQL — policies are dropped first.
-- =========================================================================

ALTER TABLE users                  ENABLE ROW LEVEL SECURITY;
ALTER TABLE grid_sections          ENABLE ROW LEVEL SECURITY;
ALTER TABLE components             ENABLE ROW LEVEL SECURITY;
ALTER TABLE analyses               ENABLE ROW LEVEL SECURITY;
ALTER TABLE anomaly_results        ENABLE ROW LEVEL SECURITY;
ALTER TABLE model_versions         ENABLE ROW LEVEL SECURITY;
ALTER TABLE meter_upload_batches   ENABLE ROW LEVEL SECURITY;
ALTER TABLE meter_readings         ENABLE ROW LEVEL SECURITY;
ALTER TABLE grid_health_snapshots  ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_interpretations     ENABLE ROW LEVEL SECURITY;
ALTER TABLE inspections            ENABLE ROW LEVEL SECURITY;
ALTER TABLE organizations          ENABLE ROW LEVEL SECURITY;
ALTER TABLE organization_members   ENABLE ROW LEVEL SECURITY;
ALTER TABLE live_meter_events      ENABLE ROW LEVEL SECURITY;
ALTER TABLE meter_stability_scores ENABLE ROW LEVEL SECURITY;
ALTER TABLE model_drift_logs       ENABLE ROW LEVEL SECURITY;
ALTER TABLE transformer_aging_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_ledger           ENABLE ROW LEVEL SECURITY;

-- Drop existing policies before recreating (PostgreSQL has no IF NOT EXISTS for policies)
DO $$ 
DECLARE
  tbl TEXT;
  pol TEXT;
BEGIN
  FOR tbl, pol IN
    SELECT tablename, policyname 
    FROM pg_policies 
    WHERE schemaname = 'public'
      AND tablename IN (
        'users','grid_sections','components','analyses','anomaly_results',
        'model_versions','meter_upload_batches','meter_readings',
        'grid_health_snapshots','ai_interpretations','inspections',
        'organizations','organization_members','live_meter_events',
        'meter_stability_scores','model_drift_logs',
        'transformer_aging_records','audit_ledger'
      )
  LOOP
    EXECUTE format('DROP POLICY IF EXISTS %I ON %I', pol, tbl);
  END LOOP;
END $$;

-- Service-role full access (backend uses service key, bypasses RLS)
CREATE POLICY "service_all_users"           ON users                  FOR ALL USING (true);
CREATE POLICY "service_all_grid"            ON grid_sections          FOR ALL USING (true);
CREATE POLICY "service_all_components"      ON components             FOR ALL USING (true);
CREATE POLICY "service_all_analyses"        ON analyses               FOR ALL USING (true);
CREATE POLICY "service_all_anomalies"       ON anomaly_results        FOR ALL USING (true);
CREATE POLICY "service_all_model_versions"  ON model_versions         FOR ALL USING (true);
CREATE POLICY "service_all_batches"         ON meter_upload_batches   FOR ALL USING (true);
CREATE POLICY "service_all_readings"        ON meter_readings         FOR ALL USING (true);
CREATE POLICY "service_all_ghi"             ON grid_health_snapshots  FOR ALL USING (true);
CREATE POLICY "service_all_ai"              ON ai_interpretations     FOR ALL USING (true);
CREATE POLICY "service_all_inspections"     ON inspections            FOR ALL USING (true);
CREATE POLICY "service_all_orgs"            ON organizations          FOR ALL USING (true);
CREATE POLICY "service_all_orgmembers"      ON organization_members   FOR ALL USING (true);
CREATE POLICY "service_all_live_events"     ON live_meter_events      FOR ALL USING (true);
CREATE POLICY "service_all_stability"       ON meter_stability_scores FOR ALL USING (true);
CREATE POLICY "service_all_drift"           ON model_drift_logs       FOR ALL USING (true);
CREATE POLICY "service_all_aging"           ON transformer_aging_records FOR ALL USING (true);
CREATE POLICY "service_all_audit"           ON audit_ledger           FOR ALL USING (true);
