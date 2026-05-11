# STEP 3: Protokol Clients — TAMAMLANDI ✅

## 📋 Neler Yapıldı?

### ✅ 1. Katman 2a: OPC-UA Client

**Dosya**: `src/layer2_opc_ua_client/opc_client.py` (~280 satır)

**Özellikler**:

- ✅ Asynchronous OPC-UA client (asyncua)
- ✅ Subscription handler (event-driven)
- ✅ Reconnect logic (exponential backoff)
- ✅ Configuration-driven endpoint
- ✅ Graceful error handling
- ✅ Per-tag subscription
- ✅ Value caching

**Sınıf Yapısı**:

```python
class OPCUAClientSubscriptionHandler:
    datachange_notification()    # OPC-UA datachange event
    event_notification()         # OPC-UA event

class OPCUAClient:
    connect()                    # Connect with retry
    setup_subscriptions()        # Subscribe all tags
    read_node()                  # Single read (one-time)
    get_all_values()            # Get all subscribed values
    disconnect()                 # Graceful disconnect
```

**Key Features**:

- Exponential backoff retry (1s → 60s)
- Max 10 retries
- Subscription-based (event-driven)
- Non-blocking I/O (async/await)

---

### ✅ 2. Katman 2b: Modbus TCP Client

**Dosya**: `src/layer2_opc_ua_client/modbus_client.py` (~230 satır)

**Özellikler**:

- ✅ Asynchronous Modbus client (pymodbus)
- ✅ Polling loop (configurable interval)
- ✅ Reconnect logic (exponential backoff)
- ✅ Register → Physical conversion
- ✅ Configuration-driven registers
- ✅ Error handling ve logging

**Sınıf Yapısı**:

```python
class ModbusTCPClient:
    connect()                    # Connect with retry
    read_registers()             # Read holding registers
    get_all_values()            # Get all configured registers
    polling_loop()              # Continuous polling
    disconnect()                 # Graceful disconnect
```

**Key Features**:

- Polling-based (configurable interval)
- Register scale conversion (e.g., 4520 → 45.20)
- Function code 03 (Read Holding Registers)
- Unit ID: 1 (default slave)

---

### ✅ 3. Katman 3a: Data Model

**Dosya**: `src/layer3_python_bridge/data_model.py` (~120 satır)

**Veri Yapıları**:

```python
@dataclass
class SensorReading:
    timestamp: datetime          # Reading time
    equipment_id: str           # pump_1, compressor_1, heater_1
    tag: str                    # temperature, pressure, vibration, etc.
    value: float                # Physical value (45.23, 120.5, etc.)
    unit: str                   # °C, PSI, mm/s, etc.
    source: str                 # OPC-UA or Modbus
    quality: int                # 0=good, 1=uncertain, 2=bad
    sequence_number: int        # Message ordering
    raw_value: Any              # For Modbus (register value)
    metadata: Dict              # Additional info
```

**Methods**:

- `to_dict()` — Convert to dictionary
- `to_json_str()` — Convert to JSON string
- `from_opc_ua()` — Create from OPC-UA data
- `from_modbus()` — Create from Modbus data

**Batch Structure**:

```python
@dataclass
class BatchedReadings:
    readings: List[SensorReading]  # Batch of readings
    batch_timestamp: datetime      # Batch creation time
    batch_size: int               # Number of readings
    source_types: set             # {'OPC-UA', 'Modbus'}
```

---

### ✅ 4. Katman 3b: Python Bridge (Dual Protocol)

**Dosya**: `src/layer3_python_bridge/bridge.py` (~350 satır)

**Özellikler**:

- ✅ Dual protocol collection (OPC-UA + Modbus)
- ✅ Unified JSON output format
- ✅ Batch buffering (configurable)
- ✅ Async collection loops
- ✅ Configuration-driven
- ✅ Production logging

**Sınıf Yapısı**:

```python
class PythonBridge:
    initialize()                 # Init both clients
    collect_from_opc_ua()       # OPC-UA polling
    collect_from_modbus()       # Modbus polling
    _add_to_batch()             # Add reading to batch
    _flush_batch()              # Flush batch to output
    collection_loop()           # Main async loop
    stop()                      # Graceful shutdown
```

**Batch Flushing Logic**:

1. Buffer size reached (default: 100 readings)
2. Timeout reached (default: 5 seconds)
3. Whichever comes first

**Data Flow**:

```
OPC-UA Client  →  ┐
                   ├→ SensorReading objects → Batch → JSON Output
Modbus Client  →  ┘
```

---

## 🏗️ Veri Akışı (Step 1-3)

```
┌─────────────────────────────────────────────────────────┐
│ LAYER 1: Virtual Equipment (Sanal veri kaynakları)     │
├─────────────────────────────────────────────────────────┤
│ • OPC-UA Server (port 4840)                            │
│ • Modbus TCP Server (port 502)                         │
│ • Sinüs + noise + drift simulation                     │
└─────────────────────┬───────────────────────────────────┘
                      │
        ┌─────────────┴──────────────┐
        │                            │
┌───────▼────────────┐      ┌────────▼─────────────┐
│ LAYER 2a:          │      │ LAYER 2b:            │
│ OPC-UA Client      │      │ Modbus Client        │
│                    │      │                      │
│ • Subscription     │      │ • Polling (1s)       │
│ • Event-driven     │      │ • Register read      │
│ • Reconnect logic  │      │ • Physical convert   │
└───────┬────────────┘      └────────┬─────────────┘
        │                            │
        └─────────────┬──────────────┘
                      │
        ┌─────────────▼──────────────┐
        │ LAYER 3: Python Bridge     │
        ├────────────────────────────┤
        │ • Unified SensorReading    │
        │ • Batch buffering (100 or 5s)
        │ • JSON serialization       │
        │ • Ready for MQTT → DB      │
        └────────────────────────────┘
```

---

## 🚀 Nasıl Çalıştırmak?

### Prerequisites

```bash
venv\Scripts\activate
pip install asyncua pymodbus pyyaml python-json-logger tenacity
```

### Test 1: Complete Flow

**Terminal 1** - OPC-UA Server:

```bash
python src/layer1_data_source/opc_ua_server.py
```

**Terminal 2** - Modbus Server:

```bash
python src/layer1_data_source/modbus_server.py
```

**Terminal 3** - Python Bridge:

```bash
python src/layer3_python_bridge/bridge.py
```

**Beklenen Output**:

```
================================================================================
LAYER 3: Python Bridge (Dual Protocol)
================================================================================
Initializing Python Bridge...

[1/4] Initializing OPC-UA client...
✓ OPC-UA Client connected

[2/4] Initializing Modbus client...
✓ Modbus TCP Client connected

[3/4] Bridge initialized
  • OPC-UA: subscription-based (event-driven)
  • Modbus: polling-based (1s interval)
  • Buffer: 100 readings or 5s timeout

[4/4] Starting collection loop...
Collecting from both OPC-UA (event) and Modbus (polling)

📤 Flushing batch: 105 readings from {'OPC-UA', 'Modbus'}
  → {"timestamp": "2026-05-08T10:30:45.123456", "equipment_id": "pump_1", "tag": "temperature", "value": 45.23, "unit": "°C", "source": "OPC-UA", "quality": 0, ...}
  → {"timestamp": "2026-05-08T10:30:45.234567", "equipment_id": "pump_1", "tag": "temperature", "value": 45.24, "unit": "°C", "source": "Modbus", "quality": 0, ...}
  → ...

📤 Flushing batch: 98 readings from {'OPC-UA', 'Modbus'}
  → ...
```

### Test 2: Individual Clients

**OPC-UA Client Test**:

```bash
python src/layer2_opc_ua_client/opc_client.py
```

**Modbus Client Test**:

```bash
python src/layer2_opc_ua_client/modbus_client.py
```

---

## 📊 JSON Output Format

**OPC-UA Source**:

```json
{
  "timestamp": "2026-05-08T10:30:45.123456",
  "equipment_id": "pump_1",
  "tag": "temperature",
  "value": 45.23,
  "unit": "°C",
  "source": "OPC-UA",
  "quality": 0,
  "sequence_number": 1,
  "raw_value": null,
  "metadata": null
}
```

**Modbus Source**:

```json
{
  "timestamp": "2026-05-08T10:30:45.234567",
  "equipment_id": "pump_1",
  "tag": "temperature",
  "value": 45.24,
  "unit": "°C",
  "source": "Modbus",
  "quality": 0,
  "sequence_number": 2,
  "raw_value": 4524,
  "metadata": {
    "scale": 1.0,
    "raw_register": 4524
  }
}
```

---

## 🎓 Portfolio Değeri

✅ **Dual Protocol Expertise**

- "OPC-UA (event-driven) + Modbus (polling) integration"
- "Production-ready client implementation"
- "Reconnect logic with exponential backoff"

✅ **Data Standardization**

- "Unified JSON format for all sources"
- "Quality flags (OPC-UA compatibility)"
- "Batch buffering for efficiency"

✅ **Asynchronous Programming**

- "Async/await patterns throughout"
- "Non-blocking concurrent collection"
- "Graceful error handling"

✅ **Enterprise Architecture**

- "Subscription + polling hybrid"
- "Configuration-driven setup"
- "Logging ve monitoring ready"

---

## 📝 Code Quality

| Metric          | Value |
| --------------- | ----- |
| Total Lines     | 1000+ |
| Files           | 5     |
| Classes         | 7     |
| Async Functions | 15+   |
| Error Handling  | ✅    |
| Type Hints      | ✅    |
| Docstrings      | ✅    |
| Logging         | ✅    |

---

## ✅ Completion Checklist

- [x] OPC-UA client (subscription)
- [x] Modbus client (polling)
- [x] Data model (SensorReading)
- [x] Batch structure (BatchedReadings)
- [x] Python bridge (dual protocol)
- [x] Unified JSON output
- [x] Batch buffering logic
- [x] Reconnect logic
- [x] Error handling
- [x] Logging
- [x] Configuration-driven
- [x] Graceful shutdown

---

## 🎯 Next Step: STEP 4

**Katman 4-5: MQTT Broker + Consumer**

- Docker container: Eclipse Mosquitto
- MQTT publisher (Bridge → MQTT)
- MQTT subscriber + batch writer
- TimescaleDB ready

---

**Oluşturma Tarihi**: May 8, 2026  
**Step Durumu**: ✅ COMPLETE  
**Tahmin Edilen Süre**: 8 hafta (3/12 tamamlandı - %25)
