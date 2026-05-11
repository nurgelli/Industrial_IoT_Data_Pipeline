# STEP 4: Messaging — TAMAMLANDI ✅

## 📋 Neler Yapıldı?

### ✅ 1. Katman 4: MQTT Broker Utilities

**Dosya**: `src/layer4_mqtt_broker/mosquitto_helper.py` (~150 satır)

**Özellikler**:

- ✅ Topic manager (topic path building/parsing)
- ✅ Message formatter (JSON serialization)
- ✅ QoS manager (level selection logic)
- ✅ Connection info helper
- ✅ Comprehensive logging

**Sınıflar**:

```python
class MQTTTopicManager:
    build_topic(equipment_id, tag)    # "pump_1", "temperature" → "plant/pump_1/temperature"
    parse_topic(topic)                # Reverse operation
    get_wildcard_pattern()            # → "plant/#"
    get_equipment_pattern(eq_id)      # → "plant/pump_1/#"

class MQTTMessageFormatter:
    format_sensor_reading(reading_dict)    # → JSON string
    parse_sensor_reading(json_str)         # ← JSON string

class MQTTQoSManager:
    AT_MOST_ONCE = 0   # Fire and forget
    AT_LEAST_ONCE = 1  # Default (sensor data)
    EXACTLY_ONCE = 2   # Alarms/config

class MQTTConnectionInfo:
    __init__(host, port)
    get_connection_string()
```

**Topic Structure**:

```
plant/
├── pump_1/
│   ├── temperature
│   ├── pressure
│   └── vibration
├── compressor_1/
│   ├── temperature
│   ├── pressure
│   └── flow_rate
└── heater_1/
    ├── temperature
    ├── pressure
    └── power_consumption
```

---

### ✅ 2. Katman 4b: MQTT Publisher

**Dosya**: `src/layer4_mqtt_broker/mqtt_publisher.py` (~140 satır)

**Özellikler**:

- ✅ Asynchronous MQTT publish
- ✅ Single reading + batch publishing
- ✅ Configurable QoS
- ✅ Connection management
- ✅ Error handling

**Sınıf Yapısı**:

```python
class MQTTPublisher:
    connect()                           # Connect to broker
    publish_reading(reading_dict, topic, qos)    # Single
    publish_batch(batch, topic_prefix, qos)     # Batch
    disconnect()                        # Graceful disconnect
```

**Usage Example**:

```python
publisher = MQTTPublisher(broker_host="localhost", broker_port=1883)
if publisher.connect():
    reading = SensorReading.from_opc_ua(...)
    publisher.publish_reading(reading.to_dict(), "plant/pump_1/temperature", qos=1)
    publisher.disconnect()
```

---

### ✅ 3. Katman 5: MQTT Consumer

**Dosya**: `src/layer5_mqtt_consumer/consumer.py` (~350 satır)

**Özellikler**:

- ✅ Asynchronous MQTT consumer (paho-mqtt)
- ✅ Wildcard subscription (plant/#)
- ✅ Batch buffering (configurable)
- ✅ Timeout-based flushing
- ✅ Payload parsing (JSON)
- ✅ SensorReading conversion
- ✅ Production logging

**Sınıf Yapısı**:

```python
class MQTTConsumer:
    _setup_mqtt_client()             # Setup callbacks
    _on_connect()                    # Connection handler
    _on_message()                    # Message handler
    _on_disconnect()                 # Disconnect handler
    _on_subscribe()                  # Subscribe handler
    _payload_to_reading()            # JSON → SensorReading
    _add_to_batch()                  # Buffer management
    _flush_batch()                   # Flush trigger
    connect()                        # Async connect
    flush_on_timeout()               # Timeout flush task
    disconnect()                     # Graceful disconnect
```

**Batch Flushing Logic**:

```
On Message:
  ├─ Parse topic
  ├─ Parse JSON payload
  ├─ Create SensorReading
  ├─ Add to batch
  ├─ Check: buffer_size >= 100?
  │  └─ YES → Flush
  └─ Check: timeout >= 5s?
     └─ YES → Flush

On Flush:
  ├─ Log batch summary
  ├─ Call on_batch_complete callback
  ├─ Reset batch
  └─ Update batch_timestamp
```

**Batch Summary Logging**:

```
📤 Flushing batch: 105 readings from MQTT
  Sequence: 1001 - 1105
  Time range: 2026-05-08 10:30:45.123 - 2026-05-08 10:30:50.456
  Equipment count: 3
  Tag count: 9
```

---

## 🏗️ Complete Data Flow (Step 1-4)

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
    │ • Ready for DB write       │
    └────────────────────────────┘
```

---

## 🚀 Docker Containers Setup

### Start Docker Services

```bash
cd docker
docker-compose up -d
```

**Services**:

- **timescaledb** (port 5432)
- **mosquitto** (port 1883, 9001)
- **pgadmin** (port 5050) — optional

### Verify Containers

```bash
docker ps
docker logs scada_mosquitto
docker logs scada_timescaledb
```

---

## 🚀 Run Complete Flow

### Terminal 1 - OPC-UA Server

```bash
python src/layer1_data_source/opc_ua_server.py
```

### Terminal 2 - Modbus Server

```bash
python src/layer1_data_source/modbus_server.py
```

### Terminal 3 - Python Bridge (with MQTT Publisher)

```bash
python src/layer3_python_bridge/bridge.py
```

### Terminal 4 - MQTT Consumer

```bash
python src/layer5_mqtt_consumer/consumer.py
```

**Beklenen Output Flow**:

```
[Terminal 1] OPC-UA Server: Publishing temperature, pressure, vibration
[Terminal 2] Modbus Server: Publishing registers
[Terminal 3] Bridge:
  ✓ OPC-UA Client connected
  ✓ Modbus Client connected
  Collecting from both sources...
  📤 Flushing batch: 50 readings
[Terminal 4] Consumer:
  ✓ Connected to MQTT broker
  Subscribed to: plant/#
  📬 Message #1-50 received...
  📤 Flushing batch: 50 readings from MQTT
```

---

## 📊 MQTT Message Example

**Topic**: `plant/pump_1/temperature`

**Payload** (JSON):

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

---

## 🧪 Test MQTT Manually

### Subscribe to all topics

```bash
mosquitto_sub -h localhost -t "plant/#"
```

### Publish test message

```bash
mosquitto_pub -h localhost -t "plant/test/value" -m '{"value": 123}'
```

---

## 📝 Configuration Reference

### settings.yaml — MQTT Settings

```yaml
mqtt_broker:
  host: '0.0.0.0'
  port: 1883
  topic_structure:
    prefix: 'plant/'
    pattern: '{prefix}{equipment_id}/{tag}'

mqtt_consumer:
  broker: 'localhost'
  port: 1883
  client_id: 'scada_consumer_1'
  batch:
    buffer_size: 100 # Readings before flush
    buffer_timeout_sec: 5 # Seconds before flush
```

### docker/mosquitto.conf

```
listener 1883
protocol mqtt

listener 9001
protocol websockets

persistence true
persistence_file mosquitto.db
persistence_location /mosquitto/data/
```

---

## 🎓 Portfolio Değeri

✅ **Event-Driven Architecture**

- "MQTT pub/sub pattern implementation"
- "Production-grade message broker (Docker)"
- "QoS-aware message delivery"

✅ **Batch Processing**

- "Efficient buffer management"
- "Configurable batch sizing"
- "Timeout-based flushing"

✅ **Message Parsing**

- "JSON serialization/deserialization"
- "Topic-based routing"
- "Data format standardization"

✅ **DevOps & Containerization**

- "Docker Compose setup"
- "Multi-container orchestration"
- "Network bridge communication"

---

## ✅ Completion Checklist

- [x] MQTT topic manager
- [x] Message formatter
- [x] QoS management
- [x] MQTT publisher
- [x] MQTT consumer
- [x] Batch buffering
- [x] Timeout flushing
- [x] JSON payload parsing
- [x] SensorReading conversion
- [x] Docker Compose setup
- [x] Mosquitto configuration
- [x] Error handling & logging

---

## 🎯 Next Step: STEP 5

**Katman 5b: Data Cleaning Pipeline**

- NaN / missing value handling
- Spike detection (Z-score)
- Noise filtering (median)
- Outlier detection (IQR)
- Anomaly logging

---

**Oluşturma Tarihi**: May 8, 2026  
**Step Durumu**: ✅ COMPLETE  
**Tahmin Edilen Süre**: 8 hafta (4/12 tamamlandı - %33)
