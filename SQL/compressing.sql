-- 1. Sıkıştırma mekanizmasını metrics_raw tablosu için aktif et.
-- Veriyi neye göre gruplayacağımızı (segmentby) ve neye göre sıralayacağımızı (orderby) seçiyoruz.
ALTER TABLE metrics_raw SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'equipment_id, tag',
    timescaledb.compress_orderby = 'timestamp DESC'
);

-- 2. Otomatik Sıkıştırma Politikası Ekle.
-- 7 günden daha eski olan tüm günlük veri paketlerini (chunks) otomatik olarak sıkıştır.
SELECT add_compression_policy('metrics_raw', INTERVAL '7 days');

-- Compressing right now
-- SELECT compress_chunk(c) FROM show_chunks('metrics_raw') c;

-- This policy is automatically remove data from the disk which is older than 30 days
-- SELECT add_retention_policy('metrics_raw', INTERVAL '30 days');

-- To display what was compressed
-- SELECT * FROM chunk_compression_stats('metrics_raw');
