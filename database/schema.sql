```sql
-- ============================================================
-- AI HEALTH SURVEILLANCE & EARLY DISEASE DETECTION SYSTEM
-- Database: PostgreSQL
-- Schema Version: 1.0
-- ============================================================

-- Create database separately if required:
-- CREATE DATABASE health_surveillance_db;

-- ============================================================
-- 1. USERS TABLE
-- Stores registered users, health officials, and administrators.
-- ============================================================

CREATE TABLE IF NOT EXISTS users (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    full_name VARCHAR(150) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,

    role VARCHAR(30) NOT NULL DEFAULT 'user'
        CHECK (role IN ('user', 'health_official', 'admin')),

    phone VARCHAR(20),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_verified BOOLEAN NOT NULL DEFAULT FALSE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_role
    ON users(role);

CREATE INDEX IF NOT EXISTS idx_users_active
    ON users(is_active);


-- ============================================================
-- 2. REGIONS TABLE
-- Stores geographical information for disease surveillance.
-- Supports national, state, district, and local dashboards.
-- ============================================================

CREATE TABLE IF NOT EXISTS regions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    region_name VARCHAR(150) NOT NULL,

    region_type VARCHAR(30) NOT NULL
        CHECK (
            region_type IN (
                'national',
                'state',
                'district',
                'city',
                'locality'
            )
        ),

    parent_region_id BIGINT
        REFERENCES regions(id) ON DELETE RESTRICT,

    latitude DOUBLE PRECISION
        CHECK (latitude IS NULL OR latitude BETWEEN -90 AND 90),

    longitude DOUBLE PRECISION
        CHECK (longitude IS NULL OR longitude BETWEEN -180 AND 180),

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (parent_region_id, region_name)
);

CREATE INDEX IF NOT EXISTS idx_regions_parent
    ON regions(parent_region_id);

CREATE INDEX IF NOT EXISTS idx_regions_type
    ON regions(region_type);


-- ============================================================
-- 3. DISEASES TABLE
-- Stores disease information used by the AI prediction system.
-- ============================================================

CREATE TABLE IF NOT EXISTS diseases (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    disease_name VARCHAR(150) NOT NULL UNIQUE,
    description TEXT,

    severity VARCHAR(20) NOT NULL DEFAULT 'medium'
        CHECK (severity IN ('low', 'medium', 'high', 'critical')),

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_diseases_name
    ON diseases(disease_name);


-- ============================================================
-- 4. HEALTH REPORTS TABLE
-- Stores health complaints and symptom reports submitted by users.
-- AI predictions are assessments, not confirmed diagnoses.
-- ============================================================

CREATE TABLE IF NOT EXISTS health_reports (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    user_id BIGINT NOT NULL
        REFERENCES users(id) ON DELETE RESTRICT,

    disease_id BIGINT
        REFERENCES diseases(id) ON DELETE SET NULL,

    disease_name VARCHAR(150),

    region_id BIGINT
        REFERENCES regions(id) ON DELETE RESTRICT,

    symptoms JSONB NOT NULL DEFAULT '[]'::JSONB,

    description TEXT,

    status VARCHAR(30) NOT NULL DEFAULT 'pending'
        CHECK (
            status IN (
                'pending',
                'under_review',
                'reviewed',
                'closed'
            )
        ),

    ai_prediction VARCHAR(150),
    ai_confidence DOUBLE PRECISION
        CHECK (
            ai_confidence IS NULL
            OR ai_confidence BETWEEN 0 AND 1
        ),

    reviewed_by BIGINT
        REFERENCES users(id) ON DELETE SET NULL,

    reviewed_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CHECK (jsonb_typeof(symptoms) = 'array')
);

CREATE INDEX IF NOT EXISTS idx_health_reports_user
    ON health_reports(user_id);

CREATE INDEX IF NOT EXISTS idx_health_reports_region
    ON health_reports(region_id);

CREATE INDEX IF NOT EXISTS idx_health_reports_status
    ON health_reports(status);

CREATE INDEX IF NOT EXISTS idx_health_reports_created
    ON health_reports(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_health_reports_disease
    ON health_reports(disease_name);

CREATE INDEX IF NOT EXISTS idx_health_reports_symptoms
    ON health_reports USING GIN(symptoms);


-- ============================================================
-- 5. ALERTS TABLE
-- Stores outbreak alerts, regional health warnings, and AI alerts.
-- ============================================================

CREATE TABLE IF NOT EXISTS alerts (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    title VARCHAR(200) NOT NULL,
    description TEXT NOT NULL,

    alert_type VARCHAR(50) NOT NULL DEFAULT 'health'
        CHECK (
            alert_type IN (
                'health',
                'outbreak',
                'hotspot',
                'anomaly',
                'system'
            )
        ),

    severity VARCHAR(20) NOT NULL DEFAULT 'medium'
        CHECK (
            severity IN ('low', 'medium', 'high', 'critical')
        ),

    region_id BIGINT
        REFERENCES regions(id) ON DELETE RESTRICT,

    disease_id BIGINT
        REFERENCES diseases(id) ON DELETE SET NULL,

    status VARCHAR(20) NOT NULL DEFAULT 'active'
        CHECK (
            status IN ('active', 'acknowledged', 'resolved')
        ),

    created_by BIGINT
        REFERENCES users(id) ON DELETE SET NULL,

    acknowledged_by BIGINT
        REFERENCES users(id) ON DELETE SET NULL,

    resolved_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_alerts_region
    ON alerts(region_id);

CREATE INDEX IF NOT EXISTS idx_alerts_severity
    ON alerts(severity);

CREATE INDEX IF NOT EXISTS idx_alerts_status
    ON alerts(status);

CREATE INDEX IF NOT EXISTS idx_alerts_created
    ON alerts(created_at DESC);


-- ============================================================
-- 6. AUDIT LOGS TABLE
-- Records security-sensitive actions for accountability.
-- Avoid storing passwords, tokens, or unnecessary health details.
-- ============================================================

CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    actor_user_id BIGINT
        REFERENCES users(id) ON DELETE SET NULL,

    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(100) NOT NULL,
    resource_id VARCHAR(100),

    outcome VARCHAR(20) NOT NULL DEFAULT 'success'
        CHECK (outcome IN ('success', 'failure')),

    details JSONB NOT NULL DEFAULT '{}'::JSONB,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CHECK (jsonb_typeof(details) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_actor
    ON audit_logs(actor_user_id);

CREATE INDEX IF NOT EXISTS idx_audit_logs_action
    ON audit_logs(action);

CREATE INDEX IF NOT EXISTS idx_audit_logs_created
    ON audit_logs(created_at DESC);


-- ============================================================
-- 7. AUTOMATIC UPDATED_AT TRIGGER
-- Maintains updated_at whenever a record is modified.
-- ============================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


DROP TRIGGER IF EXISTS trg_users_updated_at ON users;

CREATE TRIGGER trg_users_updated_at
BEFORE UPDATE ON users
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();


DROP TRIGGER IF EXISTS trg_diseases_updated_at ON diseases;

CREATE TRIGGER trg_diseases_updated_at
BEFORE UPDATE ON diseases
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();


DROP TRIGGER IF EXISTS trg_health_reports_updated_at ON health_reports;

CREATE TRIGGER trg_health_reports_updated_at
BEFORE UPDATE ON health_reports
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();


DROP TRIGGER IF EXISTS trg_alerts_updated_at ON alerts;

CREATE TRIGGER trg_alerts_updated_at
BEFORE UPDATE ON alerts
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();


-- ============================================================
-- 8. DAILY HEALTH REPORT SUMMARY VIEW
-- Provides report counts grouped by day and region.
-- ============================================================

CREATE OR REPLACE VIEW daily_health_report_summary AS
SELECT
    DATE(created_at AT TIME ZONE 'Asia/Kolkata') AS report_date,
    region_id,
    COUNT(*) AS total_reports,
    COUNT(*) FILTER (WHERE status = 'pending') AS pending_reports,
    COUNT(*) FILTER (WHERE status = 'under_review') AS reports_under_review,
    COUNT(*) FILTER (WHERE status = 'reviewed') AS reviewed_reports,
    COUNT(*) FILTER (WHERE status = 'closed') AS closed_reports
FROM health_reports
GROUP BY
    DATE(created_at AT TIME ZONE 'Asia/Kolkata'),
    region_id;


-- ============================================================
-- 9. DISEASE TREND SUMMARY VIEW
-- Supports disease analytics and historical reporting.
-- ============================================================

CREATE OR REPLACE VIEW daily_disease_trends AS
SELECT
    DATE(created_at AT TIME ZONE 'Asia/Kolkata') AS report_date,
    region_id,
    LOWER(TRIM(disease_name)) AS disease_name,
    COUNT(*) AS report_count
FROM health_reports
WHERE disease_name IS NOT NULL
  AND TRIM(disease_name) <> ''
GROUP BY
    DATE(created_at AT TIME ZONE 'Asia/Kolkata'),
    region_id,
    LOWER(TRIM(disease_name));


-- ============================================================
-- END OF SCHEMA
-- ============================================================
```