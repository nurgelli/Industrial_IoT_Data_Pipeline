-- 1. Saatlik Özet Tablosunu (Continuous Aggregate View) Oluştur
CREATE MATERIALIZED VIEW metrics_hourly_summary
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 hour', timestamp) AS hourly_bucket,
    equipment_id,
    tag,
    AVG(value) AS val_avg,
    MAX(value) AS val_max,
    MIN(value) AS val_min,
    STDDEV(value) AS val_stddev,
    COUNT(value) AS sample_count
FROM metrics_raw
WHERE quality = 'Good' -- Sadece kural motorundan onay almış temiz verileri özetle!
GROUP BY hourly_bucket, equipment_id, tag;

-- 2. Otomatik Yenileme Politikası (Refresh Policy) Ekle
-- Bu politika, her 30 dakikada bir çalışır ve son 3 saatlik zaman dilimindeki 
-- eksik veya yeni gelen verileri tarayarak saatlik özeti günceller.
SELECT add_continuous_aggregate_policy('metrics_hourly_summary',
    start_offset => INTERVAL '3 hours',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '30 minutes');

-- To display state control grouping state
-- SELECT * FROM timescaledb_information.continuous_aggregates;


-- Arka plandaki yenileme politikasının durumunu ve iş istatistiklerini izle
-- SELECT * FROM timescaledb_information.jobs WHERE proc_name = 'policy_refresh_continuous_aggregate';