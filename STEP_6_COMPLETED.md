# STEP 6: TimescaleDB Schema & Database Writing — TAMAMLANDI ✅

## 📋 Neler Yapıldı?

### ✅ 1. TimescaleDB Schema (SQL)

**Dosya**: `src/layer7_timescaledb/schema.sql` (~400 satır)

**3 Temel Tablo**:

```sql
-- 1. SENSOR READINGS (Hypertable - time-series)
CREATE TABLE sensor_readings (
    time TIMESTAMP NOT NULL,
    equipment_id TEXT NOT NULL,
    tag TEXT NOT NULL,
    value FLOAT NOT NULL,
    unit TEXT NOT NULL,
    source TEXT,  -- "OPC-UA" or "Modbus"
    quality INT,  -- 0=GOOD, 1=UNCERTAIN, 2=BAD
    sequence_number BIGINT,
    raw_value FLOAT,
    metadata JSONB
);
-- Hypertable: Auto-compression, data retention

-- 2. ALARM EVENTS (Hypertable - anomalies)
CREATE TABLE alarm_events (
    time TIMESTAMP NOT NULL,
    equipment_id TEXT NOT NULL,
    tag TEXT NOT NULL,
    anomaly_type TEXT,  -- "spike", "outlier", "nan", "noise"
    value FLOAT,
    reason TEXT,
    cleaning_action TEXT,
    severity TEXT,  -- "info", "warning", "critical"
    acknowledged BOOLEAN DEFAULT FALSE
);
-- Hypertable: Auto-compression, 90-day retention

-- 3. EQUIPMENT METADATA (Reference data)
CREATE TABLE equipment_metadata (
    equipment_id TEXT PRIMARY KEY,
    name TEXT,
    location TEXT,
    protocol TEXT,  -- "OPC-UA" or "Modbus"
    equipment_type TEXT,  -- "pump", "compressor", "heater"
    units TEXT
);
-- Regular table: Permanent reference data
```

**İndeksler** (Hızlı sorgular):

```sql
-- Sensor readings indexes
idx_sensor_readings_equipment_tag
idx_sensor_readings_source
idx_sensor_readings_quality
idx_sensor_readings_received

-- Alarm events indexes
idx_alarm_events_equipment_tag
idx_alarm_events_type
idx_alarm_events_severity
idx_alarm_events_acknowledged
```

**Materialized Views** (Analytics):

```sql
-- equipment_status: Latest reading per equipment
-- hourly_equipment_stats: Hourly statistics (count, avg, min, max, stddev)
-- anomaly_summary: Hourly anomaly counts
```

**Data Retention Policy**:

```
sensor_readings: 30 gün raw + 1 yıl compressed (otomatik)
alarm_events: 90 gün (audit trail)
equipment_metadata: Permanent (reference)
```

---

### ✅ 2. Database Client

**Dosya**: `src/layer7_timescaledb/db_client.py` (~450 satır)

**Sınıflar**:

```python
class TimescaleDBClient:
    """Database connection pool + batch writes"""

    # Connection Management
    async def connect()             # Pool oluştur + test
    async def disconnect()          # Graceful shutdown

    # Write Operations
    async def write_sensor_readings(readings)   # Batch insert
    async def write_anomaly_events(anomalies)   # Anomaly logging

    # Query Operations
    async def get_equipment_health(eq_id, hours)
    async def get_recent_anomalies(hours, limit)

    # Statistics
    def get_statistics()            # Read/write counts

class DatabaseWriterCallback:
    """Integrated pipeline callback"""
    async def on_clean_batch_ready(readings, anomalies)
```

**Features**:

✅ **Connection Pooling**

```python
# psycopg2.pool.SimpleConnectionPool (1-N connections)
pool = psycopg2.pool.SimpleConnectionPool(1, 5, ...)
conn = pool.getconn()  # Get from pool
pool.putconn(conn)     # Return to pool
```

✅ **Batch Insert**

```python
# Prepare tuples
data_tuples = [
    (timestamp, equipment_id, tag, value, unit, ...),
    (timestamp, equipment_id, tag, value, unit, ...),
]

# Execute batch (efficient)
cursor.executemany(query, data_tuples)
conn.commit()
```

✅ **Error Handling**

```python
try:
    cursor.executemany(query, data)
    conn.commit()
    self.readings_written += len(data)
except Exception as e:
    self.write_errors += 1
    logger.error(f"Insert failed: {e}")
```

✅ **Schema Auto-Initialization**

```python
async def _initialize_schema():
    # Read schema.sql
    # Execute schema DDL
    # Create tables if not exist
    # Create hypertables
    # Create indexes
```

---

## 📊 Complete Data Flow (Step 1-6)

```
┌─────────────────────────────────────────────────────────┐
│ LAYER 1: Virtual Equipment                            │
│ • OPC-UA Server (4840) + Modbus Server (502)          │
│ • Sinüs + noise + drift                               │
└─────────────────┬───────────────────────────────────────┘
                  │
    ┌─────────────┴──────────────┐
    │                            │
┌───▼────────────┐      ┌────────▼─────────┐
│ Layer 2a       │      │ Layer 2b         │
│ OPC-UA Client  │      │ Modbus Client    │
│ Subscription   │      │ Polling (1s)     │
└───┬────────────┘      └────────┬─────────┘
    │                            │
    └─────────────┬──────────────┘
                  │
    ┌─────────────▼──────────────┐
    │ Layer 3: Python Bridge     │
    │ • SensorReading objects    │
    │ • Batch buffering (100/5s) │
    │ • JSON format              │
    └─────────────┬──────────────┘
                  │
    ┌─────────────▼──────────────┐
    │ Layer 4: MQTT Publisher    │
    │ • Topic: plant/eq_id/tag   │
    │ • QoS: 1 (sensor data)     │
    │ • Publish to broker        │
    └─────────────┬──────────────┘
                  │
        ┌─────────▼────────────┐
        │ Eclipse Mosquitto    │
        │ (Docker Container)   │
        │ Port: 1883, 9001     │
        └─────────┬────────────┘
                  │
    ┌─────────────▼──────────────┐
    │ Layer 5: MQTT Consumer     │
    │ • Subscribe: plant/#       │
    │ • Parse JSON               │
    │ • Batch buffer (100/5s)    │
    └─────────────┬──────────────┘
                  │
    ┌─────────────▼──────────────┐
    │ Layer 6: Data Cleaning     │
    │ • NaN handling             │
    │ • Spike detection (Z-score)│
    │ • Outlier detection (IQR)  │
    │ • Noise filtering (median) │
    │ • Anomaly logging          │
    └─────────────┬──────────────┘
                  │
    ┌─────────────▼──────────────────┐
    │ Layer 7: TimescaleDB Writing   │  ← NEW!
    │ • Batch insert readings         │
    │ • Write anomaly events          │
    │ • Connection pooling            │
    │ • Auto-compression (30d→1y)    │
    │ • Materialized views (stats)    │
    └─────────────┬──────────────────┘
                  │
        ┌─────────▼────────────────┐
        │ TimescaleDB              │
        │ (Docker Container)       │
        │ Port: 5432              │
        │ 3 Tables + 3 Views      │
        └────────────────────────┘
```

---

## 🗄️ Database Schema Details

### Table: sensor_readings (Hypertable)

```
Column              | Type      | Description
─────────────────────────────────────────────────────
time                | TIMESTAMP | Reading timestamp (PRIMARY)
equipment_id        | TEXT      | Equipment identifier
tag                 | TEXT      | Sensor tag (temperature, pressure, etc)
value               | FLOAT     | Sensor value
unit                | TEXT      | Unit (°C, PSI, mm/s, etc)
source              | TEXT      | "OPC-UA" or "Modbus"
quality             | INT       | 0=GOOD, 1=UNCERTAIN, 2=BAD
sequence_number     | BIGINT    | Reading sequence
raw_value           | FLOAT     | Original value before cleaning
metadata            | JSONB     | Additional metadata
received_at         | TIMESTAMP | When received
```

**Example Query**:

```sql
-- Get latest temperature readings
SELECT equipment_id, tag, value, time
FROM sensor_readings
WHERE tag = 'temperature'
  AND time > CURRENT_TIMESTAMP - INTERVAL '1 hour'
ORDER BY time DESC
LIMIT 100;

-- Get hourly average
SELECT
  time_bucket('1 hour', time) as hour,
  equipment_id,
  AVG(value) as avg_temp
FROM sensor_readings
WHERE equipment_id = 'pump_1' AND tag = 'temperature'
GROUP BY hour
ORDER BY hour DESC;
```

---

### Table: alarm_events (Hypertable)

```
Column              | Type      | Description
─────────────────────────────────────────────────────
time                | TIMESTAMP | Event timestamp (PRIMARY)
equipment_id        | TEXT      | Source equipment
tag                 | TEXT      | Source tag
anomaly_type        | TEXT      | "spike", "outlier", "nan", "noise"
value               | FLOAT     | Anomalous value
reason              | TEXT      | Human-readable reason
cleaning_action     | TEXT      | Action taken
severity            | TEXT      | "info", "warning", "critical"
acknowledged        | BOOLEAN   | Operator acknowledged?
acknowledged_at     | TIMESTAMP | When acknowledged
acknowledged_by     | TEXT      | Who acknowledged
notes               | TEXT      | Notes
```

**Example Query**:

```sql
-- Get unacknowledged critical alarms
SELECT * FROM alarm_events
WHERE severity = 'critical' AND NOT acknowledged
ORDER BY time DESC;

-- Get anomaly statistics by type
SELECT
  anomaly_type,
  COUNT(*) as count,
  AVG(value) as avg_value
FROM alarm_events
WHERE time > CURRENT_TIMESTAMP - INTERVAL '24 hours'
GROUP BY anomaly_type;
```

---

### Table: equipment_metadata

```
Column              | Type      | Description
─────────────────────────────────────────────────────
equipment_id        | TEXT      | Primary key
name                | TEXT      | Equipment name
location            | TEXT      | Physical location
protocol            | TEXT      | "OPC-UA" or "Modbus"
equipment_type      | TEXT      | "pump", "compressor", "heater"
min_value           | FLOAT     | Min operating value
max_value           | FLOAT     | Max operating value
units               | TEXT      | Units (comma-separated)
created_at          | TIMESTAMP | Created date
updated_at          | TIMESTAMP | Last update
```

---

## 🚀 Configuration (settings.yaml)

```yaml
database:
  # Connection settings
  host: 'localhost'
  port: 5432
  name: 'scada_db'
  user: 'postgres'
  password: 'postgres'

  # Connection pool
  pool_size: 5
  pool_timeout_sec: 10

  # Data retention
  retention:
    sensor_readings_days: 30 # 30 days raw
    sensor_readings_compressed_days: 365 # 1 year compressed
    alarm_events_days: 90 # 90 days (audit)

  # Compression
  enable_compression: true
```

---

## 🧪 Test Suite

**Dosya**: `scripts/test_layer7.py` (~350 satır)

**Tests**:

```python
test_connection()                # Connect/disconnect
test_sensor_readings_write()     # Batch insert readings
test_anomaly_events_write()      # Insert anomalies
test_query_methods()             # get_equipment_health(), get_recent_anomalies()
test_statistics()                # Statistics tracking
test_database_writer_callback()  # IntegratedPipeline integration
```

**Run Tests**:

```bash
# Make sure TimescaleDB is running
docker-compose up -d

# Run tests
python scripts/test_layer7.py
```

**Expected Output**:

```
TEST 1: Connection Management
  ✓ Connected successfully
  ✓ Schema initialized
  ✓ Disconnected

TEST 2: Sensor Readings Write
  ✓ Wrote 10 readings
  ✓ Readings written: 10

TEST 3: Anomaly Events Write
  ✓ Wrote 3 anomalies
  ✓ Anomalies written: 3

TEST 4: Query Methods
  ✓ Equipment health: 100% (10 good / 10 total)
  ✓ Recent anomalies: 3 events found

TEST 5: Statistics Tracking
  ✓ Connected
  ✓ Readings: 5, Anomalies: 1
  ✓ Errors: 0

TEST 6: DatabaseWriterCallback
  ✓ Callback executed successfully

✅ ALL TESTS PASSED!
```

---

## 🔄 Integration with Pipeline

**Complete Flow**:

```
MQTT Consumer
  ↓ (batch ready)
DataCleaner
  ↓ (clean batch)
DatabaseWriterCallback  ← NEW!
  ├─ write_sensor_readings(readings)
  ├─ write_anomaly_events(anomalies)
  └─ get_statistics()
```

**Code Example**:

```python
from layer7_timescaledb import TimescaleDBClient, DatabaseWriterCallback
from integrated_pipeline import IntegratedPipeline

# Create database client
db_client = TimescaleDBClient(
    host="localhost",
    port=5432,
    database="scada_db",
    user="postgres",
    password="postgres"
)

# Create callback
db_callback = DatabaseWriterCallback(db_client)

# Create pipeline with database integration
pipeline = IntegratedPipeline(
    on_clean_batch_ready=db_callback.on_clean_batch_ready
)

# Start
await db_client.connect()
await pipeline.start()

# Now data flows:
# MQTT → Consumer → Cleaner → Database ✓
```

---

## 📊 Helper Functions (SQL)

```sql
-- Get equipment health score (data quality %)
SELECT * FROM get_equipment_health('pump_1', 24);
-- Returns: health_score = 98.5% (good readings / total)

-- Hourly statistics (from materialized view)
SELECT * FROM hourly_equipment_stats
WHERE equipment_id = 'pump_1'
ORDER BY hour DESC
LIMIT 24;

-- Anomaly summary
SELECT * FROM anomaly_summary
WHERE hour > CURRENT_TIMESTAMP - INTERVAL '7 days'
ORDER BY hour DESC;
```

---

## 🎓 Portfolio Değeri

✅ **Time-Series Database Architecture**

- "Production-grade TimescaleDB schema"
- "Hypertable design for sensor data"
- "Auto-compression policy implementation"

✅ **Data Persistence**

- "Batch insert optimization"
- "Connection pooling (psycopg2)"
- "Transaction management"

✅ **Data Retention & Compliance**

- "30-day raw data policy"
- "1-year compressed retention"
- "Automated data archival"

✅ **Analytics Ready**

- "Materialized views for dashboards"
- "Equipment health scoring function"
- "Anomaly aggregation queries"

✅ **SQL Expertise**

- "DDL: CREATE TABLE, CREATE HYPERTABLE"
- "Indexes: Range, JSONB, composite"
- "Functions: PL/pgSQL stored procedures"
- "Views: Materialized views for performance"

---

## ✅ Completion Checklist

- [x] Schema design (3 tables + 3 views)
- [x] Hypertable setup (compression + retention)
- [x] Index creation (fast queries)
- [x] Equipment metadata table
- [x] Sensor readings hypertable
- [x] Alarm events hypertable
- [x] Materialized views (stats, health, anomalies)
- [x] Data retention policies
- [x] Connection pooling (SimpleConnectionPool)
- [x] Batch insert (executemany)
- [x] Query methods (equipment health, anomalies)
- [x] Error handling & retry logic
- [x] Statistics tracking
- [x] DatabaseWriterCallback for pipeline
- [x] Configuration in settings.yaml
- [x] Comprehensive test suite (test_layer7.py)

---

## 🎯 Next Steps

### STEP 7: Grafana Dashboard & Visualization

- Real-time equipment status dashboard
- Time-series charts (temperature, pressure, vibration)
- Anomaly timeline
- Health score gauges
- Alert notification system

---

**Oluşturma Tarihi**: May 8, 2026  
**Step Durumu**: ✅ COMPLETE  
**Tahmin Edilen Süre**: 8 hafta (6/12 tamamlandı - %50)  
**Portfolio Değeri**: ⭐⭐⭐⭐⭐ (Database Architecture + SQL Expertise)

---

## 📚 Files Created

1. `src/layer7_timescaledb/schema.sql` — Complete schema (~400 lines)
2. `src/layer7_timescaledb/db_client.py` — Database client (~450 lines)
3. `src/layer7_timescaledb/__init__.py` — Module exports
4. `scripts/test_layer7.py` — Test suite (~350 lines)
5. Updated `config/settings.yaml` — Database configuration section

---

## 🐳 Docker Services

```bash
# Start all services
docker-compose up -d

# Services:
# - timescaledb (port 5432) ← Layer 7
# - mosquitto (port 1883)
# - pgadmin (port 5050) — optional for DB management

# Access databases
psql -h localhost -U postgres -d scada_db

# View TimescaleDB logs
docker logs scada_timescaledb
```

---

## 🔍 Monitoring Queries

```sql
-- Current data volume
SELECT
  count(*) as total_readings,
  min(time) as oldest,
  max(time) as newest
FROM sensor_readings;

-- Equipment status
SELECT * FROM equipment_status
ORDER BY equipment_id;

-- Anomaly distribution
SELECT anomaly_type, COUNT(*) as count
FROM alarm_events
WHERE time > CURRENT_TIMESTAMP - INTERVAL '24 hours'
GROUP BY anomaly_type;
```

---

**LAYER 7 READY FOR PRODUCTION! ✅**
