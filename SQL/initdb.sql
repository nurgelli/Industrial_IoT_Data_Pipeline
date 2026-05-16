-- 1. Ekipman Meta-Data Tablosu (İlişkisel Katman)
CREATE TABLE IF NOT EXISTS equipments (
    equipment_id VARCHAR(50) PRIMARY KEY,
    equipment_name VARCHAR(100) NOT NULL,
    facility_zone VARCHAR(50) NOT NULL
);

-- Meta-data örnek verileri besleme
INSERT INTO equipments (equipment_id, equipment_name, facility_zone) VALUES
('centrifugal_pump', 'Main centerfugal Pump - P101', 'Zone-A'),
('gas_compressor', 'Gas compressor - C201', 'Zone-B'),
('storage_tank', 'Raw petrol storing tank - T301')
ON CONFLICT (equipment_id) DO NOTHING;

-- 2. Zaman Serisi Ham Veri Tablosu (Telemetri Katmanı)
CREATE TABLE IF NOT EXISTS metrics_raw (
    timestamp TIMESTAMPTZ NOT NULL,
    equipment_id VARCHAR(50) NOT NULL,
    tag VARCHAR(50) NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    quality VARCHAR(10) NOT NULL,
    source VARCHAR(20) NOT NULL,
    CONSTRAINT fk_equipment FOREIGN KEY (equipment_id) REFERENCES equipments(equipment_id)
);

-- 3. Tabloyu TimescaleDB Hypertable Yapısına Dönüştürme (Zaman Bölümlemesi)
-- 8GB RAM sınırından dolayı chunk (parça) boyutunu zaman bazlı 1 gün olarak kilitliyoruz.
SELECT create_hypertable('metrics_raw', 'timestamp', chunk_time_interval => INTERVAL '1 day', if_not_exists => TRUE);

-- 4. Endüstriyel Zaman Serisi İndeksleme Stratejisi
-- Grafana ve Analitik servisleri veriyi çekerken her zaman "Belirli bir ekipmanın, belirli bir tagine ait zaman serisi" şeklinde sorgu atar.
-- PostgreSQL varsayılan olarak timestamp indeksi açar, biz bileşik (Composite) indeks ekliyoruz.
CREATE INDEX IF NOT EXISTS idx_metrics_perf 
ON metrics_raw (equipment_id, tag, timestamp DESC);