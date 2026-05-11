/**
 * LAYER 7: TimescaleDB Schema
 * ===========================
 * 
 * Production-grade time-series database schema for SCADA pipeline.
 * 
 * Tables:
 * 1. sensor_readings (hypertable) - Raw sensor data from equipment
 * 2. equipment_metadata - Equipment definitions and attributes
 * 3. alarm_events - Detected anomalies and alarms
 * 
 * Retention Policies:
 * - sensor_readings: 30 days raw data, 1 year compressed
 * - alarm_events: 1 year (auditing)
 * - equipment_metadata: Permanent (reference)
 * 
 * Created: May 8, 2026
 */

-- ============================================================================
-- 1. EQUIPMENT METADATA TABLE (Reference Data)
-- ============================================================================

CREATE TABLE IF NOT EXISTS equipment_metadata (
    equipment_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    location TEXT NOT NULL,
    protocol TEXT NOT NULL,  -- "OPC-UA" or "Modbus"
    equipment_type TEXT NOT NULL,  -- "pump", "compressor", "heater"
    min_value FLOAT,
    max_value FLOAT,
    units TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_equipment_protocol ON equipment_metadata(protocol);
CREATE INDEX IF NOT EXISTS idx_equipment_type ON equipment_metadata(equipment_type);


-- ============================================================================
-- 2. SENSOR READINGS HYPERTABLE (Time-Series Data)
-- ============================================================================

CREATE TABLE IF NOT EXISTS sensor_readings (
    time TIMESTAMP NOT NULL,
    equipment_id TEXT NOT NULL,
    tag TEXT NOT NULL,
    value FLOAT NOT NULL,
    unit TEXT NOT NULL,
    source TEXT NOT NULL,  -- "OPC-UA" or "Modbus"
    quality INT NOT NULL,  -- 0=GOOD, 1=UNCERTAIN, 2=BAD
    sequence_number BIGINT,
    raw_value FLOAT,
    metadata JSONB,
    received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Convert to hypertable for time-series compression
SELECT create_hypertable(
    'sensor_readings',
    'time',
    if_not_exists => TRUE
);

-- Create indexes for fast queries
CREATE INDEX IF NOT EXISTS idx_sensor_readings_equipment_tag
    ON sensor_readings (equipment_id, tag, time DESC);

CREATE INDEX IF NOT EXISTS idx_sensor_readings_source
    ON sensor_readings (source, time DESC);

CREATE INDEX IF NOT EXISTS idx_sensor_readings_quality
    ON sensor_readings (quality, time DESC);

CREATE INDEX IF NOT EXISTS idx_sensor_readings_received
    ON sensor_readings (received_at DESC);

-- Create JSONB index for metadata queries
CREATE INDEX IF NOT EXISTS idx_sensor_readings_metadata
    ON sensor_readings USING GIN (metadata);


-- ============================================================================
-- 3. ALARM EVENTS TABLE (Anomalies)
-- ============================================================================

CREATE TABLE IF NOT EXISTS alarm_events (
    time TIMESTAMP NOT NULL,
    equipment_id TEXT NOT NULL,
    tag TEXT NOT NULL,
    anomaly_type TEXT NOT NULL,  -- "spike", "outlier", "nan", "noise"
    value FLOAT,
    reason TEXT NOT NULL,
    cleaning_action TEXT NOT NULL,
    severity TEXT,  -- "info", "warning", "critical"
    acknowledged BOOLEAN DEFAULT FALSE,
    acknowledged_at TIMESTAMP,
    acknowledged_by TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Convert to hypertable for time-series compression
SELECT create_hypertable(
    'alarm_events',
    'time',
    if_not_exists => TRUE
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_alarm_events_equipment_tag
    ON alarm_events (equipment_id, tag, time DESC);

CREATE INDEX IF NOT EXISTS idx_alarm_events_type
    ON alarm_events (anomaly_type, time DESC);

CREATE INDEX IF NOT EXISTS idx_alarm_events_severity
    ON alarm_events (severity, time DESC);

CREATE INDEX IF NOT EXISTS idx_alarm_events_acknowledged
    ON alarm_events (acknowledged, time DESC);


-- ============================================================================
-- 4. DATA RETENTION POLICIES
-- ============================================================================

-- Compress sensor_readings older than 30 days
SELECT add_retention_policy(
    'sensor_readings',
    INTERVAL '30 days',
    if_not_exists => TRUE
);

-- Compress alarm_events older than 90 days
SELECT add_retention_policy(
    'alarm_events',
    INTERVAL '90 days',
    if_not_exists => TRUE
);

-- Optional: Enable compression for better storage
ALTER TABLE sensor_readings SET (
    timescaledb.compress,
    timescaledb.compress_orderby = 'time DESC',
    timescaledb.compress_segmentby = 'equipment_id,tag'
);

ALTER TABLE alarm_events SET (
    timescaledb.compress,
    timescaledb.compress_orderby = 'time DESC',
    timescaledb.compress_segmentby = 'equipment_id'
);


-- ============================================================================
-- 5. MATERIALIZED VIEWS (Analytics)
-- ============================================================================

-- Real-time equipment status (latest reading per equipment)
CREATE MATERIALIZED VIEW IF NOT EXISTS equipment_status AS
SELECT
    sr.equipment_id,
    sr.tag,
    sr.value,
    sr.unit,
    sr.quality,
    sr.time as last_reading_time,
    sr.source,
    em.name,
    em.location
FROM sensor_readings sr
JOIN equipment_metadata em ON sr.equipment_id = em.equipment_id
WHERE sr.time > CURRENT_TIMESTAMP - INTERVAL '1 minute'
ORDER BY sr.equipment_id, sr.tag, sr.time DESC;

CREATE INDEX IF NOT EXISTS idx_equipment_status_equipment_id
    ON equipment_status (equipment_id);


-- Hourly statistics for each equipment
CREATE MATERIALIZED VIEW IF NOT EXISTS hourly_equipment_stats AS
SELECT
    time_bucket('1 hour', sr.time) as hour,
    sr.equipment_id,
    sr.tag,
    sr.unit,
    COUNT(*) as reading_count,
    AVG(sr.value) as avg_value,
    MIN(sr.value) as min_value,
    MAX(sr.value) as max_value,
    STDDEV_POP(sr.value) as stddev_value,
    SUM(CASE WHEN sr.quality = 0 THEN 1 ELSE 0 END) as good_readings,
    SUM(CASE WHEN sr.quality = 1 THEN 1 ELSE 0 END) as uncertain_readings,
    SUM(CASE WHEN sr.quality = 2 THEN 1 ELSE 0 END) as bad_readings
FROM sensor_readings sr
WHERE sr.time > CURRENT_TIMESTAMP - INTERVAL '7 days'
GROUP BY hour, sr.equipment_id, sr.tag, sr.unit;

CREATE INDEX IF NOT EXISTS idx_hourly_stats_equipment_tag
    ON hourly_equipment_stats (equipment_id, tag, hour DESC);


-- Anomaly summary
CREATE MATERIALIZED VIEW IF NOT EXISTS anomaly_summary AS
SELECT
    time_bucket('1 hour', ae.time) as hour,
    ae.equipment_id,
    ae.tag,
    ae.anomaly_type,
    ae.severity,
    COUNT(*) as event_count,
    SUM(CASE WHEN ae.acknowledged THEN 1 ELSE 0 END) as acknowledged_count,
    SUM(CASE WHEN NOT ae.acknowledged THEN 1 ELSE 0 END) as pending_count
FROM alarm_events ae
WHERE ae.time > CURRENT_TIMESTAMP - INTERVAL '30 days'
GROUP BY hour, ae.equipment_id, ae.tag, ae.anomaly_type, ae.severity;

CREATE INDEX IF NOT EXISTS idx_anomaly_summary_hour
    ON anomaly_summary (hour DESC, severity);


-- ============================================================================
-- 6. HELPER FUNCTIONS
-- ============================================================================

-- Function to insert sensor reading (with validation)
CREATE OR REPLACE FUNCTION insert_sensor_reading(
    p_time TIMESTAMP,
    p_equipment_id TEXT,
    p_tag TEXT,
    p_value FLOAT,
    p_unit TEXT,
    p_source TEXT,
    p_quality INT,
    p_sequence_number BIGINT,
    p_raw_value FLOAT,
    p_metadata JSONB
)
RETURNS VOID AS $$
BEGIN
    INSERT INTO sensor_readings (
        time, equipment_id, tag, value, unit, source,
        quality, sequence_number, raw_value, metadata
    )
    VALUES (
        p_time, p_equipment_id, p_tag, p_value, p_unit, p_source,
        p_quality, p_sequence_number, p_raw_value, p_metadata
    );
EXCEPTION WHEN OTHERS THEN
    RAISE WARNING 'Error inserting sensor reading: %', SQLERRM;
END;
$$ LANGUAGE plpgsql;


-- Function to insert alarm event
CREATE OR REPLACE FUNCTION insert_alarm_event(
    p_time TIMESTAMP,
    p_equipment_id TEXT,
    p_tag TEXT,
    p_anomaly_type TEXT,
    p_value FLOAT,
    p_reason TEXT,
    p_cleaning_action TEXT,
    p_severity TEXT
)
RETURNS VOID AS $$
BEGIN
    INSERT INTO alarm_events (
        time, equipment_id, tag, anomaly_type, value,
        reason, cleaning_action, severity
    )
    VALUES (
        p_time, p_equipment_id, p_tag, p_anomaly_type, p_value,
        p_reason, p_cleaning_action, p_severity
    );
EXCEPTION WHEN OTHERS THEN
    RAISE WARNING 'Error inserting alarm event: %', SQLERRM;
END;
$$ LANGUAGE plpgsql;


-- Function to get equipment health score (based on recent data quality)
CREATE OR REPLACE FUNCTION get_equipment_health(
    p_equipment_id TEXT,
    p_hours INT DEFAULT 24
)
RETURNS TABLE(
    equipment_id TEXT,
    total_readings BIGINT,
    good_readings BIGINT,
    uncertain_readings BIGINT,
    bad_readings BIGINT,
    health_score FLOAT,
    last_reading TIMESTAMP
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        sr.equipment_id,
        COUNT(*) as total_readings,
        SUM(CASE WHEN sr.quality = 0 THEN 1 ELSE 0 END)::BIGINT as good_readings,
        SUM(CASE WHEN sr.quality = 1 THEN 1 ELSE 0 END)::BIGINT as uncertain_readings,
        SUM(CASE WHEN sr.quality = 2 THEN 1 ELSE 0 END)::BIGINT as bad_readings,
        ROUND(
            100.0 * SUM(CASE WHEN sr.quality = 0 THEN 1 ELSE 0 END) / COUNT(*),
            2
        )::FLOAT as health_score,
        MAX(sr.time) as last_reading
    FROM sensor_readings sr
    WHERE sr.equipment_id = p_equipment_id
        AND sr.time > CURRENT_TIMESTAMP - (p_hours || ' hours')::INTERVAL
    GROUP BY sr.equipment_id;
END;
$$ LANGUAGE plpgsql;


-- ============================================================================
-- 7. INITIALIZATION DATA
-- ============================================================================

-- Insert equipment metadata
INSERT INTO equipment_metadata (equipment_id, name, location, protocol, equipment_type, units)
VALUES
    ('pump_1', 'Centrifugal Pump #1', 'Ashkhabad Plant A', 'OPC-UA', 'pump', '°C, PSI, mm/s'),
    ('compressor_1', 'Air Compressor #1', 'Turkmenbashi Plant B', 'OPC-UA', 'compressor', '°C, PSI, m³/h'),
    ('heater_1', 'Industrial Heater #1', 'Balkanabat Plant C', 'Modbus', 'heater', '°C, PSI, kW')
ON CONFLICT (equipment_id) DO NOTHING;


-- ============================================================================
-- 8. QUERIES FOR MONITORING
-- ============================================================================

/*
   Useful queries for Grafana dashboards and monitoring:

-- Get latest readings for all equipment
SELECT equipment_id, tag, value, quality, time
FROM sensor_readings
WHERE time > CURRENT_TIMESTAMP - INTERVAL '1 minute'
ORDER BY equipment_id, tag, time DESC;

-- Get anomalies in last 24 hours
SELECT * FROM alarm_events
WHERE time > CURRENT_TIMESTAMP - INTERVAL '24 hours'
ORDER BY time DESC;

-- Get equipment health score
SELECT * FROM get_equipment_health('pump_1', 24);

-- Get hourly statistics
SELECT * FROM hourly_equipment_stats
WHERE equipment_id = 'pump_1'
ORDER BY hour DESC
LIMIT 24;

-- Get anomaly summary
SELECT * FROM anomaly_summary
WHERE hour > CURRENT_TIMESTAMP - INTERVAL '7 days'
ORDER BY hour DESC;

-- Count readings by quality
SELECT
    equipment_id,
    quality,
    COUNT(*) as count
FROM sensor_readings
WHERE time > CURRENT_TIMESTAMP - INTERVAL '1 hour'
GROUP BY equipment_id, quality
ORDER BY equipment_id, quality;

*/
