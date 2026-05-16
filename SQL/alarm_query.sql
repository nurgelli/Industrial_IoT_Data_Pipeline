-- Sistem Kritik Alarm Günlüğü Tablosu
CREATE TABLE IF NOT EXISTS system_alerts (
    timestamp TIMESTAMPTZ NOT NULL,
    equipment_id VARCHAR(50) NOT NULL,
    tag VARCHAR(50) NOT NULL,
    current_value DOUBLE PRECISION NOT NULL,
    historical_mean DOUBLE PRECISION NOT NULL,
    z_score DOUBLE PRECISION NOT NULL,
    severity VARCHAR(20) NOT NULL,
    alert_type VARCHAR(50) NOT NULL,
    CONSTRAINT fk_alert_equipment FOREIGN KEY (equipment_id) REFERENCES equipments(equipment_id)
);

-- Alarmları da zaman serisi olarak hypertable'a dönüştürüyoruz (7 günlük chunk boyutu idealdir)
SELECT create_hypertable('system_alerts', 'timestamp', chunk_time_interval => INTERVAL '7 days', if_not_exists => TRUE);

-- Performans İndeksi
CREATE INDEX IF NOT EXISTS idx_alerts_perf ON system_alerts (equipment_id, timestamp DESC);