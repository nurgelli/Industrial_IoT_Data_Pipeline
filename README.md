# Industrial IoT Data Pipeline — Oil & Gas Production Analytics

> **End-to-End SCADA-Grade Data Engineering Portfolio Project**
> Simulating real-world field instrumentation through OPC-UA and Modbus TCP, streaming into a time-series database, with statistical anomaly detection and operational dashboarding.

---

## Table of Contents

1. [Project Overview & Motivation](#1-project-overview--motivation)
2. [System Architecture](#2-system-architecture)
3. [Technology Stack & Why Each Was Chosen](#3-technology-stack--why-each-was-chosen)
4. [Industrial Protocols Deep Dive](#4-industrial-protocols-deep-dive)
5. [Data Simulation Engine](#5-data-simulation-engine)
6. [Protocol Bridge & Unified Data Schema](#6-protocol-bridge--unified-data-schema)
7. [Message Broker Layer — MQTT](#7-message-broker-layer--mqtt)
8. [Time-Series Storage — TimescaleDB](#8-time-series-storage--timescaledb)
9. [Data Quality Rule Engine](#9-data-quality-rule-engine)
10. [Statistical Anomaly Detection Engine](#10-statistical-anomaly-detection-engine)
11. [Operational Dashboard — Grafana](#11-operational-dashboard--grafana)
12. [Containerization Strategy](#12-containerization-strategy)
13. [Getting Started](#13-getting-started)
14. [Current Project Status](#14-current-project-status)
15. [Known Gaps & Roadmap](#15-known-gaps--roadmap)
16. [Interview Defense — Why Did You Choose This?](#16-interview-defense--why-did-you-choose-this)

---

## 1. Project Overview & Motivation

### What This Project Is

This project replicates the core data infrastructure of an oil and gas production facility — from field-level sensors to executive-level dashboards — using open-source, production-grade tooling.

It models three physical assets commonly found in upstream O&G operations:

| Asset                | Key Measurements                                                                     |
| -------------------- | ------------------------------------------------------------------------------------ |
| **Centrifugal Pump** | Flow rate (m³/h), Suction Pressure (bar), Discharge Pressure (bar), Vibration (mm/s) |
| **Gas Compressor**   | Bearing Temperature (°C), Shaft Speed (RPM)                                          |
| **Storage Tank**     | Level (%), Temperature (°C)                                                          |

### Why This Domain?

Major O&G operators (Petronas, Dragon Oil, ADNOC, TotalEnergies) run ICS/SCADA infrastructure at scale. A data engineer or analyst candidate who can demonstrate practical knowledge of **industrial protocols, time-series databases, and anomaly detection** stands out from candidates with generic ETL or business intelligence backgrounds.

### What Problem Does This Solve?

In real production plants, the challenge is not just collecting data — it is collecting it reliably, validating its quality, persisting it efficiently, and surfacing anomalies in real time before equipment failure. This project replicates that entire chain in a single-machine development environment.

---

## 2. System Architecture

> [High-Level SCADA Pipeline Architecture](./assets/system_arch_diagram.png)

## 3. Technology Stack & Why Each Was Chosen

| Component                 | Technology             | Industrial Justification                                                                                                                             |
| ------------------------- | ---------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Protocol — OPC-UA**     | `asyncua` (Python)     | ISA-95 / IEC 62541 compliant. Standard for DCS/SCADA interoperability. Used by Siemens, ABB, Honeywell PLCs.                                         |
| **Protocol — Modbus TCP** | `pymodbus` (Python)    | IEEE-2011. Legacy standard in 80%+ of existing field devices. Any O&G engineer recognizes this.                                                      |
| **Message Bus**           | Eclipse Mosquitto MQTT | OASIS standard. Lightweight publish/subscribe for constrained networks. QoS levels (0/1/2) mirror industrial reliability guarantees.                 |
| **Time-Series DB**        | TimescaleDB            | PostgreSQL extension purpose-built for time-series. Hypertables auto-partition by time. 10-100x faster than vanilla Postgres for time-range queries. |
| **Anomaly Detection**     | NumPy Z-Score          | Sliding-window statistical control chart (analogous to Shewhart rules used in process control). No ML model overhead; interpretable and auditable.   |
| **Visualization**         | Grafana OSS            | De-facto standard for operational dashboards. Native TimescaleDB plugin. Used by Chevron, Shell, and most industrial IoT vendors.                    |
| **Containerization**      | Docker Compose         | Reproducible deployment. Production services isolated in a bridged network.                                                                          |
| **Async Runtime**         | Python asyncio         | Non-blocking I/O essential for high-frequency sensor polling without thread overhead.                                                                |

---

## 4. Industrial Protocols Deep Dive

### 4.1 OPC-UA (IEC 62541)

> [UaExpert OPC-UA Address Space Validation](./assets/opc_ua_expert.png)

OPC-UA (Open Platform Communications Unified Architecture) is the successor to OPC Classic. It provides:

- **Subscription model**: Server pushes data only when values change (deadband-filtered). No unnecessary network traffic.
- **Information modeling**: Hierarchical object tree (Objects → Equipment → Tag) maps directly to ISA-95 equipment hierarchy.
- **Security**: X.509 certificates, message signing and encryption (not implemented in this dev simulator but the hook is present).

In this project, the simulator (`simul_factory.py`) acts as the OPC-UA **Server**, and the bridge (`bridge.py`) acts as the OPC-UA **Client** with subscriptions at 500ms intervals.

**Why subscription over polling for OPC-UA?** Because OPC-UA servers (Siemens S7-1500, Rockwell ControlLogix) are designed to push on-change. Polling them is resource-wasteful and defeats the protocol's design intent.

### 4.2 Modbus TCP (IEEE 2011)

Modbus is a request/response protocol operating on a register map:

| Register Type     | Address Range | Access     | Used For                         |
| ----------------- | ------------- | ---------- | -------------------------------- |
| Holding Registers | 40001–49999   | Read/Write | Process variables (this project) |
| Input Registers   | 30001–39999   | Read Only  | Direct sensor inputs             |
| Coils             | 00001–09999   | Read/Write | Digital outputs                  |
| Discrete Inputs   | 10001–19999   | Read Only  | Digital inputs                   |

**Scaling convention used in this project:**

Since Modbus registers are 16-bit unsigned integers (0–65535), floating-point values are scaled:

```
Flow (m³/h):  raw_register / 10   → e.g., 1200 → 120.0 m³/h
Pressure (bar): raw_register / 100 → e.g., 250 → 2.50 bar
Temperature (°C): raw_register / 10 → e.g., 723 → 72.3°C
```

**Why polling for Modbus?** Because Modbus TCP has no push mechanism — it is fundamentally a master/slave protocol. The master (bridge) must request data on a defined scan rate. 1-second scan rate is typical for process variables in O&G.

---

## 5. Data Simulation Engine

**File:** `simul_factory.py`

### Physics-Based Process Simulation

Rather than random data, the simulator uses **Gaussian-noise Random Walk** to model realistic sensor behavior:

```python
new_val = current_value + drift_term + gaussian_noise
new_val = clip(new_val, physical_minimum, physical_maximum)
```

This produces:

- **Drift**: Gradual trending (e.g., bearing temperature slowly rising as compressor hours accumulate)
- **Gaussian Noise**: Natural sensor measurement noise (standard deviation tuned per instrument type)
- **Clipping**: Hard physical limits (tank can't exceed 100% or drop below 0%)

| Parameter           | Base Value | Drift     | Noise σ | Range     |
| ------------------- | ---------- | --------- | ------- | --------- |
| Pump Flow           | 120.0 m³/h | +0.05     | 0.2     | 0–200     |
| Suction Pressure    | 2.5 bar    | 0.0       | 0.02    | 1–5       |
| Discharge Pressure  | 34.8 bar   | +0.1      | 0.15    | 20–45     |
| Pump Vibration      | 3.8 mm/s   | +0.01     | 0.05    | 0–15      |
| Bearing Temperature | 72.3°C     | +0.1      | 0.3     | 30–95     |
| Compressor RPM      | 1450       | ±5 random | 2.0     | 1400–1500 |
| Tank Level          | 65.2%      | −0.02     | 0.05    | 0–100     |
| Tank Temperature    | 28.4°C     | +0.02     | 0.1     | −10–50    |

### Dual-Protocol Publishing

The simulator writes to **both** OPC-UA server nodes and Modbus TCP registers simultaneously, in every scan cycle (1 second). This allows the bridge to demonstrate reading the same physical process through two different industrial protocols — a common scenario when migrating legacy Modbus systems to OPC-UA.

---

## 6. Protocol Bridge & Unified Data Schema

**File:** `bridge.py`

### Unified JSON Schema

All data entering the MQTT bus conforms to a single schema regardless of source protocol:

```json
{
  "source": "opc_ua | modbus_tcp",
  "equipment_id": "centrifugal_pump | gas_compressor | storage_tank",
  "tag": "flow | vibration | bearing_temperature | ...",
  "value": 120.5,
  "timestamp": "2024-01-15T10:32:00.123456+00:00",
  "quality": "Good | Bad"
}
```

**Why a unified schema?** In production SCADA systems, data from different PLCs, RTUs, and historians must be normalized before storage. Schema heterogeneity is a primary cause of data quality issues. By normalizing at the bridge layer, all downstream consumers (database worker, anomaly engine) are protocol-agnostic.

### OPC-UA: Subscription Architecture

```
OpcSubHandler (datachange_notification callback)
    └── node_map: {NodeId → (equipment_id, tag_name)}
        └── On value change: serialize → MQTT publish
```

The `node_map` dictionary allows the single handler callback to route notifications from any number of nodes — scalable to hundreds of tags without code changes.

### Modbus TCP: Polling Architecture

```
modbus_polling_loop() [asyncio Task]
    └── Every 1 second:
        ├── Read 10 Holding Registers (FC03)
        ├── Apply scaling factors
        └── Publish 8 process variables to MQTT
```

The polling loop runs as a separate asyncio task, completely non-blocking relative to the OPC-UA subscription handler.

---

## 7. Message Broker Layer — MQTT

> [MQTT Topic Topology via MQTT Explorer](./assets/mqtt_explorer.png)

**Broker:** Eclipse Mosquitto 2.1 (Docker)

### Topic Hierarchy

```
plant/
  ├── centrifugal_pump/
  │     ├── flow
  │     ├── suction_pressure
  │     ├── discharge_pressure
  │     └── vibration
  ├── gas_compressor/
  │     ├── bearing_temperature
  │     └── rpm
  └── storage_tank/
        ├── level
        └── temperature

alerts/
  └── critical/
        ├── centrifugal_pump/vibration
        ├── gas_compressor/bearing_temperature
        └── ...
```

### QoS Level Selection

All process data is published at **QoS 1** (at-least-once delivery). This guarantees:

- No data point is silently lost due to network issues
- The broker acknowledges receipt before the publisher considers the message delivered

QoS 2 (exactly-once) is intentionally avoided: the overhead of a 4-way handshake is not justified for high-frequency sensor data where occasional duplicates are handled by the database layer's idempotency.

### Why MQTT Over Direct Database Writes?

| Concern               | Direct DB Write              | MQTT + Worker                                          |
| --------------------- | ---------------------------- | ------------------------------------------------------ |
| **Protocol mismatch** | Bridge must know DB schema   | Bridge is schema-agnostic                              |
| **Backpressure**      | Bridge stalls on DB slowness | MQTT broker buffers messages                           |
| **Fan-out**           | Only one consumer            | Unlimited subscribers (analytics, dashboard, alerting) |
| **Decoupling**        | Bridge and DB are coupled    | Services deployable independently                      |

---

## 8. Time-Series Storage — TimescaleDB

**File:** `db_worker.py` | **Image:** `timescale/timescaledb:latest-pg15`

### Database Schema

```sql
-- Equipment metadata (relational)
CREATE TABLE equipment (
    equipment_id    VARCHAR(50) PRIMARY KEY,
    equipment_type  VARCHAR(50),
    location        VARCHAR(100),
    install_date    DATE
);

-- Main time-series table (TimescaleDB Hypertable)
CREATE TABLE metrics_raw (
    timestamp       TIMESTAMPTZ     NOT NULL,
    equipment_id    VARCHAR(50)     NOT NULL,
    tag             VARCHAR(50)     NOT NULL,
    value           DOUBLE PRECISION NOT NULL,
    quality         VARCHAR(10)     NOT NULL,  -- 'Good' | 'Bad'
    source          VARCHAR(20)     NOT NULL   -- 'opc_ua' | 'modbus_tcp'
);

-- Convert to Hypertable (auto-partitioned by time)
SELECT create_hypertable('metrics_raw', 'timestamp');

-- Composite index for equipment + time queries (most common access pattern)
CREATE INDEX ON metrics_raw (equipment_id, tag, timestamp DESC);

-- Alert log table
CREATE TABLE system_alerts (
    timestamp        TIMESTAMPTZ     NOT NULL,
    equipment_id     VARCHAR(50)     NOT NULL,
    tag              VARCHAR(50)     NOT NULL,
    current_value    DOUBLE PRECISION,
    historical_mean  DOUBLE PRECISION,
    z_score          DOUBLE PRECISION,
    severity         VARCHAR(20),
    alert_type       VARCHAR(50)
);

SELECT create_hypertable('system_alerts', 'timestamp');
```

### Why TimescaleDB Over Vanilla PostgreSQL?

**Hypertable partitioning**: TimescaleDB automatically partitions data into time-based chunks. A query like `WHERE timestamp > NOW() - INTERVAL '24 hours'` only scans the last chunk, not the entire table.

**Compression**: Native columnar compression reduces storage by 90%+ for time-series data with long retention windows.

**Continuous Aggregates**: Materialized views that automatically refresh. Pre-compute hourly averages so Grafana doesn't recalculate them on every dashboard load.

```sql
-- Hourly statistical summary (auto-refreshed)
CREATE MATERIALIZED VIEW metrics_hourly
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', timestamp) AS bucket,
    equipment_id,
    tag,
    AVG(value)   AS mean,
    MAX(value)   AS max,
    MIN(value)   AS min,
    STDDEV(value) AS stddev,
    COUNT(*)     AS sample_count
FROM metrics_raw
WHERE quality = 'Good'
GROUP BY bucket, equipment_id, tag;
```

### Fault Tolerance & Edge Buffering: Dual-Channel Store-and-Forward (SaF)

Endüstriyel ağlarda ağ kesintileri (network drop, DNS resolution failure, VPN lag) kaçınılmaz bir gerçektir. Bu tür kesintilerde TimescaleDB bağlantı havuzu (`asyncpg.pool`) çöktüğünde veri kaybını (%0 data loss garantisi) önlemek adına **SQLite tabanlı Store-and-Forward** mimarisi geliştirilmiştir.

Mekaniğin mühendislik detayları şunlardır:

1. **Asenkron Disk I/O (Non-Blocking):** `db_worker.py`, yüksek frekanslı MQTT veri akışını engellememek için, TimescaleDB'ye yazma başarısız olduğunda verileri senkron olan `sqlite3` kütüphanesine `loop.run_in_executor` kullanarak thread-pool üzerinden devrederek diske yazar.
2. **Çift Kanallı İzolasyon (Dual-Channel Isolation):** Sensör verileri (`metrics_raw`) ve Anomali motoru çıktıları (`system_alerts`) farklı şemalara sahiptir. SQLite yerel tamponuna (`local_buffer.db`) veriler yazılırken `target_table` kolonu ile etiketlenir.
3. **Otomatik İletim (Forwarding):** Arka planda çalışan `forward_local_buffer_task` daemon'u, ağın stabilize olup olmadığını periyodik (5 sn) olarak yoklar. Bağlantı kurulduğunda, SQLite diskinde bekleyen verileri tarihsel sırayla (FIFO) okur, `copy_records_to_table` metoduyla asenkron ve bulk olarak TimescaleDB'ye yazar ve başarılı olan ID'leri yerel tampondan tamamen temizler.


> [Stop timescaleddb simulation ](./assets/docker_stop_timescaledb.png)

> [Local buffer ](./assets/local_buffer_starting.png)

> [DB Worker Terminal Logs - Network Drop & Recovery Simulation](./assets/docker_logs.png)

> [From local buffer to main DB](./assets/from_local_to_db.png)

### Ingestion Worker Architecture

```
MQTT Broker
    │ (messages arrive on a paho thread)
    ▼
handle_mqtt_message()      ← MQTT thread (cannot use asyncio directly)
    │ loop.call_soon_threadsafe()
    ▼
msg_queue (asyncio.Queue)  ← Thread-safe handoff point
    │
    ▼
consume_queue()            ← asyncio task (main event loop)
    │
    ├── evaluate_data_quality()
    ├── append to metrics_buffer or alerts_buffer
    │
    ▼
flush_buffers()            ← triggered by size (100 rows) OR time (1 sec)
    │
    ▼
asyncpg COPY               ← Bulk insert via PostgreSQL binary COPY protocol
    │                         (fastest possible ingestion method)
    ▼
TimescaleDB
```

**Why asyncio.Queue as the handoff?** The paho-mqtt client runs its own internal thread. Calling asyncio functions from a non-asyncio thread causes race conditions. `call_soon_threadsafe` is the correct pattern for bridging threaded and async code.

**Why bulk COPY instead of INSERT?** PostgreSQL's `COPY` binary protocol is 5–10x faster than parameterized `INSERT` for batch workloads. At 8 tags × 1 Hz × 2 protocols = ~16 records/second, bulk insert keeps database overhead negligible.

---

## 9. Data Quality Rule Engine

**File:** `tmscaledb_worker.py` — `evaluate_data_quality()`

Three data quality rules are implemented, aligned with ISA-88/ISA-95 data quality conventions:

### Rule 1: Range Validation (Out-of-Range Detection)

```
IF value < physical_minimum OR value > physical_maximum:
    quality = "Bad"
```

| Equipment        | Tag                 | Min   | Max    |
| ---------------- | ------------------- | ----- | ------ |
| centrifugal_pump | flow                | 0.0   | 200.0  |
| centrifugal_pump | vibration           | 0.0   | 12.0   |
| gas_compressor   | bearing_temperature | 10.0  | 95.0   |
| gas_compressor   | rpm                 | 0.0   | 1600.0 |
| storage_tank     | level               | 0.0   | 100.0  |
| storage_tank     | temperature         | −20.0 | 60.0   |

### Rule 2: Stale Data Detection (Frozen Signal)

```
IF current_value == previous_value (5 consecutive readings):
    quality = "Bad"
    → Signal: sensor failure, disconnected transmitter, or PLC write error
```

A frozen signal is one of the most common failure modes in industrial instrumentation. A pressure transmitter with a blocked impulse line will read a constant value indefinitely.

### Rule 3: Communication Timeout (Heartbeat Monitoring)

```
IF time_since_last_reading > 5 seconds:
    write a "Bad" quality record to database
    → Signal: field device offline, network cable pulled, PLC fault
```

This rule runs as a separate asyncio task that sweeps all known sensors every second.

**Why write a "Bad" record instead of skipping?** Because the absence of a record is indistinguishable from a database write failure. An explicit "Bad" quality record with the last known value preserves the audit trail and allows Grafana to show a gap in the "Good only" view while still maintaining the timeline.

---

## 10. Statistical Anomaly Detection Engine

**File:** `anomaly_engine.py`

### Z-Score Method (Statistical Process Control)

The anomaly engine implements a **sliding window Z-score** test — the computational equivalent of a Shewhart control chart used in process engineering:

```
Given: a window of the last N=30 observations for a sensor tag
μ  = mean(window)
σ  = std(window)
z  = (current_value − μ) / σ

IF |z| > 3.0: ANOMALY — current value is > 3 standard deviations from recent baseline
```

At σ=3.0, a false positive rate of 0.27% is expected for normally distributed process data. This threshold is intentionally conservative to minimize alarm fatigue — a serious operational problem in real control rooms.

### Design Decisions

**Minimum window size (15 readings)**: No statistics are computed until 15 readings are collected. This prevents false alarms during startup when the window contains only 1–2 points and variance is undefined.

**Frozen-signal guard (`std > 0.001`)**: If a sensor is stuck at a constant value (frozen signal), std ≈ 0 and Z-score division would produce infinity. The guard condition skips statistics for frozen signals — which are already handled by Rule 2 in the data quality engine.

**Loop prevention**: The engine subscribes to `plant/#` but explicitly ignores `alerts/critical/#` topics to prevent feedback loops where its own alerts trigger re-analysis.

**Thread-loop bridge**: The anomaly engine's MQTT callback runs on paho's thread, but alarm publishing is an async operation. `asyncio.run_coroutine_threadsafe()` safely schedules coroutines from a non-async thread.

### Alarm Payload

```json
{
  "alert_type": "STATISTICAL_ANOMALY",
  "equipment_id": "gas_compressor",
  "tag": "bearing_temperature",
  "current_value": 94.7,
  "historical_mean": 72.3,
  "z_score": 4.82,
  "severity": "CRITICAL",
  "timestamp": "2024-01-15T10:32:00Z"
}
```

### What This Detects (Real-World Scenarios)

| Anomaly                 | Physics                                   | Expected Signal                    |
| ----------------------- | ----------------------------------------- | ---------------------------------- |
| Pump cavitation         | Vapor bubble formation → flow instability | Sudden flow drop + vibration spike |
| Bearing failure (early) | Increased friction → heat generation      | Bearing temp rising, Z > 3         |
| Seal leak               | Pressure differential reduces             | Discharge pressure drop            |
| Tank overflow risk      | Level trending toward 100%                | Level Z-score rising               |

---

## 11. Operational Dashboard — Grafana

**Image:** `grafana/grafana-oss:10.4.2`

> **Status: Planned — not yet implemented**

### Dashboard 1: Real-Time SCADA View

> [Grafana Dashboard - SCADA View](./assets/grafana_dash.png)

Intended panels:

- **Pump Flow** — Time series, last 30 minutes, 1s resolution
- **Suction / Discharge Pressure** — Dual-axis comparison, safety band overlay
- **Pump Vibration** — Threshold line at 7.5 mm/s (ISO 10816 alarm zone)
- **Compressor Bearing Temperature** — Gauge with color zones (green/yellow/red)
- **Compressor RPM** — Stat panel with deviation from setpoint
- **Tank Level** — Bar gauge with high-high alarm at 90%
- **Active Alerts Table** — Live feed from `system_alerts`

### Dashboard 2: Executive Summary & Analytics

> [Grafana Dashboard - Anomaly and Quality Analytics](./assets/grafana_anomaly.png)

Intended panels:

- **Equipment Availability (%)** — Based on "Good" quality ratio
- **Anomaly Frequency (weekly)** — Bar chart from `system_alerts` aggregated
- **Mean Time Between Anomalies** — Per equipment
- **Data Quality Score** — Good/Bad ratio trend

### Key Grafana SQL Patterns

```sql
-- Real-time flow reading (last 10 min at native resolution)
SELECT timestamp, value
FROM metrics_raw
WHERE equipment_id = 'centrifugal_pump'
  AND tag = 'flow'
  AND quality = 'Good'
  AND $__timeFilter(timestamp)
ORDER BY timestamp;

-- Hourly anomaly count from alerts table
SELECT
    time_bucket('1 hour', timestamp) AS time,
    equipment_id,
    COUNT(*) AS alert_count
FROM system_alerts
WHERE $__timeFilter(timestamp)
GROUP BY time, equipment_id
ORDER BY time;
```

---

## 12. Containerization Strategy

**File:** `compose.yaml`

### Running Services

| Service                | Image                               | Port | Purpose                   |
| ---------------------- | ----------------------------------- | ---- | ------------------------- |
| `modbus_server_docker` | `oitc/modbus-server:2.1.0`          | 5020 | Modbus TCP register store |
| `mqtt_broker_docker`   | `eclipse-mosquitto:2.1-alpine`      | 1883 | MQTT message bus          |
| `timescaledb_docker`   | `timescale/timescaledb:latest-pg15` | 5432 | Time-series database      |
| `scada_grafana`        | `grafana/grafana-oss:10.4.2`        | 3000 | Visualization dashboard   |

### Memory Optimization (8GB RAM Environment)

TimescaleDB is tuned for constrained resources:

```yaml
command: >
  postgres
  -c shared_buffers=1GB          # 12.5% of RAM (PostgreSQL recommendation)
  -c work_mem=32MB               # Per-query sort/hash memory
  -c maintenance_work_mem=256MB  # VACUUM, index builds
  -c effective_cache_size=3GB    # Query planner hint (not allocated)
  -c max_wal_size=2GB            # WAL flush frequency control
```

### Network Isolation

All containers communicate on an internal Docker bridge network (`industrial_network`). No service exposes its internal port to `0.0.0.0` — only explicitly declared port mappings are accessible from the host. This mirrors production network segmentation between OT (Operational Technology) and IT zones.

### Python Services (Currently Host-Resident)

The following Python services currently run directly on the host machine and are **not yet containerized**:

- `simul_factory.py` — OPC-UA server + Modbus writer
- `bridge.py` — Protocol bridge
- `anomaly_engine.py` — Statistical anomaly detection
- `tmscaledb_worker.py` — DB ingestion worker

> **Planned**: Each service will receive its own `Dockerfile` and be added to `compose.yaml` for fully self-contained deployment via `docker compose up`.

---

## 13. Getting Started

### Prerequisites

```
Docker Desktop ≥ 4.x
Python ≥ 3.11
8GB RAM (minimum recommended)
```

### Step 1: Start Infrastructure Containers

```bash
docker compose up -d
```

Verify containers:

```bash
docker compose ps
# Expected: modbus_server, mosquitto, timescaledb, grafana — all Up
```

### Step 2: Install Python Dependencies

```bash
pip install asyncua pymodbus paho-mqtt numpy asyncpg
```

### Step 3: Initialize Database Schema

```bash
# Connect to TimescaleDB
psql postgresql://postgres:123@localhost:5432/scada_db

# Run schema SQL (see /sql/schema.sql)
\i sql/schema.sql
```

### Step 4: Start Python Services (in separate terminals)

```bash
# Terminal 1 — Data Simulator
python simul_factory.py

# Terminal 2 — Protocol Bridge
python bridge.py

# Terminal 3 — DB Ingestion Worker
python tmscaledb_worker.py

# Terminal 4 — Anomaly Detection Engine
python anomaly_engine.py
```

### Step 5: Verify Data Flow

```bash
# Terminal 5 — MQTT Monitor
python test_mqtt.py
```

Expected output:

```
Topic: plant/centrifugal_pump/flow     | Src: opc_ua   | Tag: flow  | Val: 120.45 | Quality: Good
Topic: plant/gas_compressor/rpm        | Src: modbus_tcp | Tag: rpm  | Val: 1449.0 | Quality: Good
```

### Step 6: Access Grafana

Navigate to `http://localhost:3000` — default credentials: `admin / 123`

Add TimescaleDB as a data source: `Host: timescaledb:5432 | DB: scada_db`

---


## 14. Known Gaps & Roadmap


### Data Engineering Improvements

- **Continuous Aggregates**: Hourly/daily materialized views in TimescaleDB are designed but not yet created.
- **Compression Policy**: TimescaleDB compression on chunks older than 7 days (planned, not implemented).
- **Dead-letter queue**: Failed database writes currently log an error and discard data. A retry queue should be added.

### Analytics Improvements

- **Fault injection scenarios**: The simulator does not yet generate known failure signatures (cavitation, bearing overheat). Adding these makes anomaly detection demonstrably testable.
- **Isolation Forest / LSTM**: Z-score covers univariate anomalies. Multivariate methods (e.g., pump flow vs. pressure differential) would catch more complex failure modes.

### Operational Improvements

- **Grafana provisioning**: Dashboards and data sources should be defined as YAML files under `grafana/provisioning/` so they are pre-loaded on first container start.
- **Health check endpoints**: Each Python service should expose a `/health` HTTP endpoint for container orchestration readiness probes.
- **Structured logging (JSON)**: Replace plaintext logs with structured JSON for ingestion into ELK or Loki.

---

## 16. Interview Defense — Why Did You Choose This?

### "Why MQTT and not Kafka?"

MQTT is the correct choice for **field-to-edge** communication. Kafka is designed for **high-throughput, durable, ordered log streaming** between application services. At 16 messages/second from a small facility simulation, Kafka's overhead (Zookeeper/KRaft, replication, partition management) is unjustified. In real O&G plants, MQTT is the standard for PLC-to-historian communication; Kafka appears at the data center aggregation layer — exactly the pattern reflected in this architecture.

### "Why TimescaleDB and not InfluxDB?"

TimescaleDB is PostgreSQL. This means: standard SQL, mature JOIN semantics, foreign key constraints for equipment metadata, full ACID compliance, and a skills transferable to any data engineering role. InfluxDB uses Flux (a proprietary query language), has no relational join capability, and the company has had significant licensing uncertainty. For an enterprise portfolio, PostgreSQL-native solutions reduce vendor lock-in risk.

### "How does your data quality rule engine work?"

Three rules execute in the ingestion worker before any record reaches the database: range validation (physics-based bounds), frozen signal detection (consecutive identical readings), and communication timeout monitoring (heartbeat check). Records are not discarded — they are marked `quality = 'Bad'` and persisted. This preserves audit trails and enables root-cause analysis. Downstream analytics and dashboards filter on `quality = 'Good'` for operational displays.

### "Is your anomaly detection production-ready?"

The current implementation is appropriate for a single-node development environment and correctly demonstrates the statistical pattern. For production: the window state should be externalized to Redis (so the engine can restart without losing history), the Z-score threshold should be tunable per-tag (not global), and the system should integrate with an enterprise alarm management system (ISA-18.2 compliant) rather than raw MQTT alerts.

### "What would you do differently with more time?"

1. Add fault injection to the simulator (deliberate cavitation scenario) to make anomaly detection demonstrably effective.
2. Implement Grafana dashboard provisioning as code.
3. Containerize all Python services for true one-command deployment.
4. Add a multivariate anomaly method (Isolation Forest on pump flow/pressure ratio).
5. Write integration tests that verify the full pipeline end-to-end: simulator → bridge → MQTT → DB worker → database row count assertion.

---

## License

MIT License. This project is a portfolio artifact for data engineering and industrial IoT demonstration purposes. It is not intended for deployment in safety-critical production environments without appropriate engineering review.
