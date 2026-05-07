# Production-Level SCADA Pipeline — Türkmenistan OT Senaryosu

## 📋 Genel Bakış

**Portfolio Projesi**: Türkmenistan'daki enerji tesislerinde kullanılan eski (Modbus RTU/TCP) ve yeni (OPC-UA) SCADA protokollerini birleştiren production-level veri pipeline.

### Temel Özellikler
- ✅ **Dual Protocol Support**: OPC-UA (modern) + Modbus TCP (eski sistemler)
- ✅ **Event-Driven Architecture**: MQTT broker ile asynchronous mesajlaşma
- ✅ **Time-Series Database**: TimescaleDB (PostgreSQL + extension)
- ✅ **Data Quality**: Cleaning pipeline (NaN, spike, noise detection)
- ✅ **ML Anomaly Detection**: Isolation Forest ile predictive maintenance
- ✅ **SCADA Visualization**: Grafana dashboard + ISA-18.2 alarms
- ✅ **Production-Ready**: Docker, logging, fault tolerance, retry logic

---

## 🏗️ Mimari Katmanlar

| # | Katman | Bileşen | Teknoloji | Durum |
|---|--------|---------|-----------|-------|
| **1a** | Veri Kaynağı | OPC-UA Server | asyncua | ✅ |
| **1b** | Veri Kaynağı | **Modbus TCP Server** | pymodbus | 🆕 |
| **2** | Protokol | OPC-UA Client | asyncua | ✅ |
| **3** | Collector | **Python Bridge (Dual)** | asyncua + pymodbus | ⚡ |
| **4** | Broker | MQTT Broker | Eclipse Mosquitto | ✅ |
| **5** | Consumer | MQTT Subscriber | paho-mqtt | ✅ |
| **5b** | Temizleme | **Data Cleaning Pipeline** | pandas + numpy | 🆕 |
| **6-7** | DB | **TimescaleDB (3-tablo schema)** | PostgreSQL + extension | ⚡ |
| **8** | Dashboard | Grafana | Grafana OSS | ✅ |
| **9-10** | Analiz | Analytics + ML | pandas + scikit-learn | ✅ |
| **11** | Alarm | Alert System | Grafana + MQTT | ✅ |
| **12-15** | DevOps | Docker + Docs | Docker Compose | ✅ |

---

## 📊 Veri Akışı

```
[Modbus TCP Server]  →  ┐
                         ├→ [Python Bridge (Dual)]
[OPC-UA Server] →→  →   ┘
      ↓
[OPC-UA Client]
      ↓
[MQTT Broker] (Eclipse Mosquitto)
      ↓
[MQTT Consumer]
      ↓
[Data Cleaning Pipeline]  (NaN / Spike / Noise)
      ↓
[TimescaleDB - 3 Tablo]
  • sensor_readings (hypertable, 30d raw + 1y compressed)
  • equipment_metadata (normal table)
  • alarm_events (hypertable, ISA-18.2 state machine)
      ↓
    ┌─┴──────────────────┬────────────────┐
    ↓                    ↓                 ↓
[Grafana Dashboard] [Analytics Job]  [Anomaly Detection]
    (ISA-101 colors)   (APScheduler)   (Isolation Forest)
    ↓
[Alarm + MQTT Publish] (ISA-18.2: unacked→acked→RTN)
```

---

## 🚀 Quick Start (Hibrit Yaklaşım — 8GB RAM)

### 1️⃣ Ortam Hazırlığı

```bash
# Python venv oluştur
python -m venv venv

# Aktivasyon (Windows)
venv\Scripts\activate

# Paketleri kur
pip install -r requirements.txt
```

### 2️⃣ Docker Servisleri (TimescaleDB + Mosquitto)

```bash
cd docker

# Docker images indir ve başlat
docker-compose up -d

# Kontrol et
docker ps
```

**Beklenen çıktı**:
- `timescaledb` (PostgreSQL + extension)
- `mosquitto` (MQTT broker)

### 3️⃣ Native Servisleri Başlat (Python + Grafana)

Terminal 1 - OPC-UA Server + Modbus Server:
```bash
python src/layer1_data_source/opc_ua_server.py &
python src/layer1_data_source/modbus_server.py &
```

Terminal 2 - Python Bridge (Dual Protocol):
```bash
python src/layer3_python_bridge/bridge.py
```

Terminal 3 - MQTT Consumer + Cleaning:
```bash
python src/layer5_mqtt_consumer/consumer.py
```

Terminal 4 - Grafana:
```bash
# Grafana binary çalıştır (Windows)
grafana\bin\grafana-server.exe
# veya
grafana-server
```

### 4️⃣ Test

```bash
# TimescaleDB'ye bağlan
psql -h localhost -U postgres -d scada_prod

# Verileri kontrol et
SELECT COUNT(*) FROM sensor_readings;
SELECT * FROM alarm_events ORDER BY time DESC LIMIT 10;
```

---

## 📁 Proje Yapısı

```
PROJECT-1/
├── src/
│   ├── layer1_data_source/
│   │   ├── opc_ua_server.py      (Katman 1a: 3 sanal ekipman)
│   │   ├── modbus_server.py      (Katman 1b: Modbus TCP)
│   │   └── __init__.py
│   ├── layer2_opc_ua_client/
│   │   ├── opc_client.py         (Katman 2: OPC-UA subscription)
│   │   └── __init__.py
│   ├── layer3_python_bridge/
│   │   ├── bridge.py             (Katman 3: Dual protocol bridge)
│   │   ├── data_model.py         (Ortak JSON format)
│   │   └── __init__.py
│   ├── layer4_mqtt_broker/
│   │   ├── mosquitto_config.py   (MQTT config helper)
│   │   └── __init__.py
│   ├── layer5_mqtt_consumer/
│   │   ├── consumer.py           (Katman 5: Batch buffering)
│   │   └── __init__.py
│   ├── layer5b_cleaning/
│   │   ├── cleaner.py            (NaN / Spike / Noise)
│   │   └── __init__.py
│   ├── layer6_timescaledb/
│   │   ├── schema.sql            (3-tablo schema + retention)
│   │   ├── db_client.py          (Python DB client)
│   │   └── __init__.py
│   ├── layer8_grafana/
│   │   ├── dashboards/
│   │   │   └── main_dashboard.json
│   │   └── provisioning/
│   │       └── datasources/
│   │           └── timescaledb.yml
│   └── layer9_analytics/
│       ├── analytics.py          (APScheduler tasks)
│       ├── anomaly.py            (Isolation Forest)
│       └── __init__.py
│
├── config/
│   ├── settings.yaml             (Ortak config)
│   ├── logging.yaml              (Structured logging)
│   └── equipment_config.json     (Ekipman metadata)
│
├── docker/
│   ├── docker-compose.yml        (TimescaleDB + Mosquitto)
│   ├── timescaledb.dockerfile    (optional: custom image)
│   └── mosquitto.conf
│
├── docs/
│   ├── ARCHITECTURE.md           (Purdue Model harita)
│   ├── BATCH_VS_STREAMING.md     (Kavram açıklaması)
│   ├── MODBUS_VS_OPCUA.md        (Protokol karşılaştırması)
│   ├── OT_SECURITY.md            (MITRE ATT&CK ICS)
│   └── DEPLOYMENT.md             (Prod checklist)
│
├── logs/                         (Runtime logs)
│   ├── bridge.log
│   ├── consumer.log
│   ├── cleaner.log
│   └── analytics.log
│
├── requirements.txt              (Python dependencies)
├── .gitignore
├── docker-compose.yml            (Root docker-compose)
└── README.md                     (Bu dosya)
```

---

## 🔧 Konfigürasyon

### `config/settings.yaml`
```yaml
# OPC-UA
opc_ua:
  endpoint: "opc.tcp://localhost:4840/"
  namespace_idx: 2
  
# Modbus TCP
modbus:
  host: "localhost"
  port: 502
  
# MQTT
mqtt:
  broker: "localhost"
  port: 1883
  topic_prefix: "plant/"
  qos: 1
  
# TimescaleDB
database:
  host: "localhost"
  port: 5432
  user: "postgres"
  password: "postgres_pwd"
  dbname: "scada_prod"
  
# Data Cleaning
cleaning:
  nan_handling: "drop"        # drop, ffill, bfill
  spike_zscore_threshold: 3
  spike_window: 10
  median_window: 3
  
# Anomaly Detection
anomaly:
  contamination: 0.05
  random_state: 42
```

---

## 📈 Batch vs Streaming (Önemli Kavram)

### Batch Processing (Layer 9: Analytics)
- **Ne**: Saatlik/günlük aggregate hesaplamalar
- **Nasıl**: APScheduler ile scheduled job
- **Kod**: `src/layer9_analytics/analytics.py`
- **Örnek**: Moving average, std deviation, daily statistics

### Streaming Processing (Layer 5-5b)
- **Ne**: Her gelen MQTT mesajı işleme (batch buffer)
- **Nasıl**: 100 mesaj veya 5 saniye → DB yazma
- **Kod**: `src/layer5_mqtt_consumer/consumer.py` + `layer5b_cleaning/cleaner.py`
- **Örnek**: Real-time spike detection, data quality check

---

## 🛡️ Modbus vs OPC-UA (Portfolio Farkı)

| Özellik | Modbus TCP | OPC-UA |
|---------|-----------|--------|
| **Protokol** | Binary, TCP üstü | Binary, TCP/TLS üstü |
| **Port** | 502 | 4840 |
| **Veri Modeli** | Simple (register) | Complex (node tree) |
| **Güvenlik** | Yok | TLS + authentication |
| **Türkmenistan** | %60-70 eski sistemler | Yeni kurulumlar |
| **Portfolio Değeri** | "Eski sistemleri anlıyor" | "Modern SCADA expert" |
| **Kod Örneği** | `src/layer1_data_source/modbus_server.py` | `src/layer1_data_source/opc_ua_server.py` |

**Stratejik Mesaj**: "Her iki protokolü production'da kullanabilirim."

---

## 🚨 ISA-18.2 Alarm State Machine

```
[Alarm Triggered]
        ↓
    UNACKED (flashing)
        ↓ (operator clicks)
    ACKED (steady)
        ↓ (condition recovers)
    RTN (return to normal)
        ↓
    [Alarm History Logged]
```

**Implementasyon**: `src/layer9_analytics/anomaly.py` + Grafana Alert

---

## 📊 TimescaleDB Schema (Katman 7)

### 3 Tablo:

**1. sensor_readings** (Hypertable — time-series)
```sql
CREATE TABLE sensor_readings (
  time TIMESTAMPTZ NOT NULL,
  equipment_id INTEGER NOT NULL,
  tag VARCHAR NOT NULL,
  value FLOAT NOT NULL,
  quality INTEGER,  -- 0=good, 1=uncertain, 2=bad
  source VARCHAR,   -- 'OPC-UA' or 'Modbus'
  is_clean BOOLEAN  -- true=after cleaning pipeline
);

SELECT create_hypertable('sensor_readings', 'time', if_not_exists => TRUE);
```

**2. equipment_metadata** (Normal table)
```sql
CREATE TABLE equipment_metadata (
  id SERIAL PRIMARY KEY,
  name VARCHAR NOT NULL,
  location VARCHAR,
  protocol VARCHAR,
  min_limit FLOAT,
  max_limit FLOAT,
  unit VARCHAR
);
```

**3. alarm_events** (Hypertable — ISA-18.2)
```sql
CREATE TABLE alarm_events (
  time TIMESTAMPTZ NOT NULL,
  equipment_id INTEGER NOT NULL,
  alarm_type VARCHAR,
  state VARCHAR,  -- UNACKED, ACKED, RTN
  reason TEXT,
  anomaly_score FLOAT
);

SELECT create_hypertable('alarm_events', 'time', if_not_exists => TRUE);
```

**Retention Policy**:
```sql
-- Raw veri: 30 gün
SELECT add_retention_policy('sensor_readings', INTERVAL '30 days', if_not_exists => TRUE);

-- Compressed: 1 yıl
SELECT add_compression_policy('sensor_readings', INTERVAL '1 year', if_not_exists => TRUE);
```

---

## 🐳 Docker Stratejisi (8GB RAM için)

### Docker'a Al ✅
- **TimescaleDB**: PostgreSQL + extension kurulumu karmaşık
- **Mosquitto**: Hafif, config yönetimi kolay

### Native Çalıştır ⚡
- **Grafana**: Debug sırasında tarayıcı reload hızlıdır
- **Python Servisleri**: Kod değişikliği → anında restart

### RAM Dağılımı
```
TimescaleDB         ~350MB
Mosquitto           ~15MB
Docker daemon       ~250MB
Grafana             ~150MB
Python (4 servis)   ~400MB
IDE (VS Code)       ~500MB
Tarayıcı            ~400MB
─────────────────────────
Toplam            ~2.1GB (8GB'ın %26'sı — konforlu!)
```

---

## 🔐 Logging & Observability

**Structured Logging** (JSON format):
```python
# Her servis kendi log dosyasına
import logging
from pythonjsonlogger import jsonlogger

logger = logging.getLogger(__name__)
handler = logging.FileHandler('logs/bridge.log')
formatter = jsonlogger.JsonFormatter()
handler.setFormatter(formatter)
logger.addHandler(handler)

# Çıktı:
# {"timestamp": "2026-05-07T10:30:45Z", "level": "INFO", "service": "bridge", "message": "OPC-UA connected"}
```

**Log Seviyeleri**:
- `DEBUG`: Detailed flow (subscription events)
- `INFO`: Key actions (connection, batch write)
- `WARNING`: Anomalies (spike detected)
- `ERROR`: Failures (DB connection lost, retry logic)

---

## 🧪 Test Senaryosu

### 1. Dual Protocol Bağlantı
```bash
python src/layer1_data_source/opc_ua_server.py &
python src/layer1_data_source/modbus_server.py &
python src/layer3_python_bridge/bridge.py

# Logs'a bak:
# "OPC-UA client subscribed to 6 nodes"
# "Modbus polling started: 3 registers/sec"
# "Bridge producing unified JSON stream"
```

### 2. MQTT Mesajlaşma
```bash
# Terminal A: Consumer başlat
python src/layer5_mqtt_consumer/consumer.py

# Terminal B: MQTT test mesajı gönder
mosquitto_pub -h localhost -t "plant/pump_1/temperature" -m '{"value": 45.2, "timestamp": 1234567890}'

# Consumer output:
# "Received message: plant/pump_1/temperature"
# "Batch buffer: 1/100 messages (0s elapsed)"
```

### 3. Data Cleaning
```bash
# Consumer içinden anomali inject et
# Spike: 45.2°C → 150°C (normal 30-50°C aralığı)

# Cleaning pipeline output:
# "Spike detected: z-score=4.2 (threshold=3.0)"
# "After median filter: 45.5°C (cleaned)"
# "Clean record written to sensor_readings"
```

### 4. TimescaleDB Doğrulama
```sql
-- Connection
psql -h localhost -U postgres -d scada_prod

-- Tablo boyutları
SELECT tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename))
FROM pg_tables WHERE tablename IN ('sensor_readings', 'equipment_metadata', 'alarm_events');

-- Son 10 kayıt (son 1 saat)
SELECT time, equipment_id, tag, value, quality, source FROM sensor_readings 
WHERE time > NOW() - INTERVAL '1 hour' 
ORDER BY time DESC 
LIMIT 10;

-- Alarm history
SELECT * FROM alarm_events WHERE state != 'RTN' ORDER BY time DESC;
```

---

## 🎯 Portfolio Özeti (Mülakata Hazırlamak)

**Sorulan Sorular & Cevaplar**:

1. **"Dual protocol support neden önemli?"**
   - Türkmenistan'da Modbus %60-70 yaygın, OPC-UA sadece yeni projeler. İkisini birleştirmek "hem eski hem yeni sistemi yönetebiliyor" anlamı.

2. **"Data cleaning neden bu kadar önemli?"**
   - Sensor arızaları production'da her zaman olur. NaN, spike, noise filtering olmadan ML modelleri hata yapar.

3. **"Neden TimescaleDB?"**
   - Plain PostgreSQL'den 10-100x hızlı zaman serisi sorguları. Compression (1 yıl) ile storage optimize.

4. **"ISA-18.2 nedir?"**
   - SCADA alarm standardı. Alarm state machine (unacked→acked→RTN) uyguladığım gösteriyor işi cidiye aldığımı.

5. **"Docker strateji neden hibrid?"**
   - 8GB RAM sınırlı. Stateful servisler (DB, broker) Docker'da; debug servisleri native çalıştırıp hızlı restart.

6. **"Logging nasıl?"**
   - Structured JSON logging. Prod ortamda log analysis tool'larına (ELK, Splunk) kolayca entegre.

7. **"Anomaly detection algoritması?"**
   - Isolation Forest (scikit-learn). 5% contamination rate ile unsupervised anomalies bulur.

---

## 📚 Sonraki Adımlar

- [ ] **Step 2**: Katman 1a-1b (OPC-UA + Modbus Server)
- [ ] **Step 3**: Katman 2-3 (OPC-UA Client + Python Bridge)
- [ ] **Step 4**: Katman 4-5 (MQTT + Consumer)
- [ ] **Step 5**: Katman 5b (Data Cleaning Pipeline)
- [ ] **Step 6**: Katman 6-7 (TimescaleDB Schema)
- [ ] **Step 7**: Katman 8-11 (Grafana + Analytics + Alarm)
- [ ] **Step 8**: Docker Compose + Deployment

---

## 📞 İletişim & Notlar

**Son Güncelleme**: May 7, 2026
**Portfolio Hedefi**: Dragon Oil / Petronas / Türkmengaz SCADA pozisyonları
**Tahmini Tamamlanma**: ~8 hafta (full implementation)

---

## 📄 Lisans

MIT License — Açık kaynak, akademik / portfolyo kullanımı

