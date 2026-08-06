
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Equipment
CREATE TABLE IF NOT EXISTS equipment (
    equipment_id    VARCHAR(50)     PRIMARY KEY,
    equipment_type  VARCHAR(50)     NOT NULL,
    description     TEXT,
    location        VARCHAR(100),
    install_date    DATE,
    created_at      TIMESTAMPTZ     DEFAULT NOW()
);

-- base val
INSERT INTO equipment (equipment_id, equipment_type, description, location) VALUES
    ('centrifugal_pump', 'Pump',       'Main process centrifugal pump', 'Production Area A'),
    ('gas_compressor',   'Compressor', 'Natural gas compression unit',  'Compressor Station 1'),
    ('storage_tank',     'Tank',       'Crude oil storage tank',        'Tank Farm B')
ON CONFLICT (equipment_id) DO NOTHING;

-- TimescaleDB Hypertable

CREATE TABLE IF NOT EXISTS metrics_raw (
    timestamp       TIMESTAMPTZ         NOT NULL,
    equipment_id    VARCHAR(50)         NOT NULL,
    tag             VARCHAR(50)         NOT NULL,
    value           DOUBLE PRECISION    NOT NULL,
    quality         VARCHAR(10)         NOT NULL DEFAULT 'Good',  -- Good/bad
    source          VARCHAR(20)         NOT NULL DEFAULT 'unknown' -- opcua-mod
);


SELECT create_hypertable(
    'metrics_raw',
    'timestamp',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);


-- LIFO
CREATE INDEX IF NOT EXISTS idx_metrics_equip_tag_time
    ON metrics_raw (equipment_id, tag, timestamp DESC);

-- Quality index: "WHERE quality = 'Good'
CREATE INDEX IF NOT EXISTS idx_metrics_quality
    ON metrics_raw (quality, timestamp DESC);

-- System alarm
CREATE TABLE IF NOT EXISTS system_alerts (
    timestamp           TIMESTAMPTZ         NOT NULL,
    equipment_id        VARCHAR(50)         NOT NULL,
    tag                 VARCHAR(50)         NOT NULL,
    current_value       DOUBLE PRECISION,
    historical_mean     DOUBLE PRECISION,
    z_score             DOUBLE PRECISION,
    severity            VARCHAR(20)         DEFAULT 'CRITICAL',
    alert_type          VARCHAR(50)         DEFAULT 'STATISTICAL_ANOMALY'
);

SELECT create_hypertable(
    'system_alerts',
    'timestamp',
    chunk_time_interval => INTERVAL '7 days', 
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS idx_alerts_equip_time
    ON system_alerts (equipment_id, timestamp DESC);

-- CONTINUOUS AGGREGATE
CREATE MATERIALIZED VIEW IF NOT EXISTS metrics_hourly
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', timestamp) AS bucket,
    equipment_id,
    tag,
    AVG(value) AS mean_value,
    MAX(value) AS max_value,
    MIN(value) AS min_value,
    STDDEV(value) AS stddev_value,
    COUNT(*) AS sample_count,
    COUNT(*) FILTER (WHERE quality = 'Good') AS good_count,
    COUNT(*) FILTER (WHERE quality = 'Bad') AS bad_count
FROM metrics_raw
GROUP BY bucket, equipment_id, tag
WITH NO DATA;  -- refresh policy 

-- Continuous Aggregate policy
SELECT add_continuous_aggregate_policy('metrics_hourly',
    start_offset => INTERVAL '3 hour',   
    end_offset   => INTERVAL '1 hour',    
    schedule_interval => INTERVAL '1 hour' 
);


-- COMPRESSION: 7 day before
ALTER TABLE metrics_raw SET (
    timescaledb.compress,
    timescaledb.compress_orderby = 'timestamp DESC',
    timescaledb.compress_segmentby = 'equipment_id, tag'
);

SELECT add_compression_policy('metrics_raw', INTERVAL '7 days');

SELECT add_retention_policy('metrics_raw', INTERVAL '90 days');

-- Aproving
DO $$
BEGIN
    RAISE NOTICE '------';
    RAISE NOTICE 'SCADA Pipeline Schema successfully created!';
    RAISE NOTICE 'Tables: equipment, metrics_raw, system_alerts';
    RAISE NOTICE 'Hypertables: metrics_raw, system_alerts';
    RAISE NOTICE 'Continuous Aggregate: metrics_hourly';
END $$;
