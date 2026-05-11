# STEP 5: Data Cleaning Pipeline — TAMAMLANDI ✅

## 📋 Neler Yapıldı?

### ✅ 1. Data Cleaning Engine

**Dosya**: `src/layer6_data_cleaning/cleaner.py` (~380 satır)

**Özellikler**:

- ✅ NaN/missing value handling (DROP, FORWARD_FILL, BACKWARD_FILL, INTERPOLATE)
- ✅ Spike detection using Z-score method (threshold: 3σ)
- ✅ Outlier detection using IQR method (1.5×IQR)
- ✅ Noise filtering with 3-point rolling median
- ✅ Anomaly logging and reporting
- ✅ Production-grade error handling

**Sınıflar**:

```python
class DataCleaner:
    """Comprehensive data cleaning and validation"""

    handle_missing_values()     # NaN handling
    detect_spikes()             # Z-score > 3σ
    detect_outliers()           # IQR > 1.5×IQR
    filter_noise()              # 3-point median
    clean_batch()               # Complete pipeline
    get_anomaly_report()        # Statistics

class AnomalyRecord:
    """Represents detected anomaly"""
    timestamp
    equipment_id
    tag
    anomaly_type: AnomalyType
    value: Optional[float]
    reason: str
    cleaning_action: str
    to_dict()  # For logging

class CleaningMethod(Enum):
    DROP = "drop"
    FORWARD_FILL = "forward_fill"
    BACKWARD_FILL = "backward_fill"
    INTERPOLATE = "interpolate"

class AnomalyType(Enum):
    SPIKE = "spike"              # Z-score > 3σ
    OUTLIER = "outlier"          # IQR > 1.5×IQR
    NAN = "nan"                  # Missing value
    NOISE = "noise"              # High frequency
```

---

## 🔧 Detaylı Özellikleri

### 1️⃣ NaN Handling

**4 Strateji**:

```python
# DROP: Satırı tamamen sil
cleaning_method = CleaningMethod.DROP
# Input:  [45.0, 46.0, NaN, 47.0, 48.0]
# Output: [45.0, 46.0,      47.0, 48.0]

# FORWARD_FILL: Önceki değeri kullan
cleaning_method = CleaningMethod.FORWARD_FILL
# Input:  [45.0, 46.0, NaN, 47.0, 48.0]
# Output: [45.0, 46.0, 46.0, 47.0, 48.0]

# BACKWARD_FILL: Sonraki değeri kullan
cleaning_method = CleaningMethod.BACKWARD_FILL
# Input:  [45.0, 46.0, NaN, 47.0, 48.0]
# Output: [45.0, 46.0, 47.0, 47.0, 48.0]

# INTERPOLATE: Doğrusal interpolasyon
cleaning_method = CleaningMethod.INTERPOLATE
# Input:  [45.0, 46.0, NaN, 47.0, 48.0]
# Output: [45.0, 46.0, 46.5, 47.0, 48.0]
```

---

### 2️⃣ Spike Detection (Z-Score Method)

**Principle**:

```
Spike if: |value - mean| > threshold × stdev
          |value - mean| / stdev > 3.0σ
```

**Example**:

```
Normal readings:  [45.0, 45.2, 45.1, 45.3, 44.9]
Mean = 45.1°C, Stdev = 0.15°C

Spike reading: 120.0°C
Z-score = |120.0 - 45.1| / 0.15 = 499.3σ  ← SPIKE! (> 3σ)

Action: Mark as UNCERTAIN quality, log to anomalies
```

**Configuration**:

```yaml
data_cleaning:
  z_score_threshold: 3.0 # Usually 3 or 4
  min_readings_for_stats: 10 # Need 10+ samples
```

---

### 3️⃣ Outlier Detection (IQR Method)

**Principle**:

```
IQR = Q3 - Q1
Lower Bound = Q1 - 1.5 × IQR
Upper Bound = Q3 + 1.5 × IQR

Outlier if: value < Lower Bound OR value > Upper Bound
```

**Example**:

```
Sorted readings: [48, 49, 50, 50, 51, 51, 52]
Q1 (25th percentile) = 49
Q3 (75th percentile) = 51
IQR = 51 - 49 = 2

Lower = 49 - 1.5×2 = 46
Upper = 51 + 1.5×2 = 54

Value 45°C: < 46 → OUTLIER
Value 200°C: > 54 → OUTLIER
```

**Configuration**:

```yaml
data_cleaning:
  iqr_multiplier: 1.5 # Standard value
```

---

### 4️⃣ Noise Filtering (3-Point Median)

**Principle**:

```
Median filter smooths high-frequency noise
Only for readings with GOOD quality status
```

**Example**:

```
Noisy input:  [50.0, 50.3, 49.8, 50.1, 49.9, 50.2]
Window [50.0, 50.3, 49.8] → Median = 50.0
Window [50.3, 49.8, 50.1] → Median = 50.1
Window [49.8, 50.1, 49.9] → Median = 49.9
Window [50.1, 49.9, 50.2] → Median = 50.1

Smoothed:     [50.0, 50.1, 49.9, 50.1, ...]
```

---

## 📊 Complete Data Flow (Step 1-5)

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
    │ Layer 6: Data Cleaning     │  ← NEW!
    │ • NaN handling             │
    │ • Spike detection (Z-score)│
    │ • Outlier detection (IQR)  │
    │ • Noise filtering (median) │
    │ • Anomaly logging          │
    │ • Output: Clean data ✓     │
    └─────────────┬──────────────┘
                  │
                  ↓
    (Layer 7: Database Writing - TBD)
```

---

## 🚀 Integrated Pipeline

**Dosya**: `src/integrated_pipeline.py` (~300 satır)

**Purpose**: MQTT Consumer + Data Cleaner + Downstream Callback

**Sınıf**:

```python
class IntegratedPipeline:
    """Complete pipeline: MQTT Consumer → Data Cleaner → Output"""

    async def start()              # Start pipeline
    async def stop()               # Stop gracefully
    async def _on_batch_from_consumer()  # Handle batches
    def get_statistics()           # Get metrics
```

**Data Flow**:

```python
# 1. MQTT Consumer receives batch (100 readings or 5s)
consumer.on_batch_complete()
    ↓
# 2. Trigger cleaning pipeline
cleaner.clean_batch(batch)
    ├─ Step 1: handle_missing_values()
    ├─ Step 2: detect_spikes()
    ├─ Step 3: detect_outliers()
    ├─ Step 4: filter_noise()
    └─ Result: (clean_readings, anomalies)
    ↓
# 3. Call downstream callback
on_clean_batch_ready(clean_readings, anomalies)
    ↓
# 4. Ready for Layer 7 (Database writing)
```

**Usage**:

```python
async def database_writer(clean_readings, anomalies):
    """Downstream consumer - will write to DB in Layer 7"""
    logger.info(f"Received {len(clean_readings)} clean readings")

# Create and start pipeline
pipeline = IntegratedPipeline(
    on_clean_batch_ready=database_writer,
    on_anomaly_detected=handle_anomaly
)

await pipeline.start()
# Now listening to MQTT → Cleaning → Database
```

---

## 🧪 Test Suite

**Dosya**: `scripts/test_layer6.py` (~350 satır)

**Tests**:

```python
test_nan_handling()           # Test all 4 strategies
test_spike_detection()        # Z-score detection
test_outlier_detection()      # IQR detection
test_noise_filtering()        # Median filter
test_complete_pipeline()      # Full pipeline with mixed issues
```

**Run Tests**:

```bash
python scripts/test_layer6.py
```

**Expected Output**:

```
TEST 1: NaN Handling
  ✓ DROP strategy: 5 → 4 readings
  ✓ FORWARD_FILL: filled value = 46.0
  ✓ BACKWARD_FILL: correct interpolation

TEST 2: Spike Detection (Z-score)
  ✓ Normal distribution around 45°C
  ✓ Spike at 120°C detected (z=499.3σ)
  ✓ Marked as UNCERTAIN quality

TEST 3: Outlier Detection (IQR)
  ✓ Normal range: 50.0-51.2°C
  ✓ Outlier at 200°C detected
  ✓ Bounds correctly calculated

TEST 4: Noise Filtering (3-Point Median)
  ✓ Input: [50.0, 50.3, 49.8, 50.1, 49.9, 50.2]
  ✓ Output: smoothed values

TEST 5: Complete Pipeline
  ✓ 50 readings with NaN, spike, outlier
  ✓ Output: 48-49 clean readings
  ✓ Anomalies: 3 detected (1 NaN, 1 spike, 1 outlier)

✅ ALL TESTS PASSED!
```

---

## 📝 Configuration

### settings.yaml — Data Cleaning Settings

```yaml
# ============================================
# 6. Data Cleaning & Validation (STEP 5)
# ============================================
data_cleaning:
  # NaN handling strategy
  method: 'drop' # drop, forward_fill, backward_fill, interpolate

  # Spike detection (Z-score)
  # Spike if |value - mean| > z_score_threshold × stdev
  z_score_threshold: 3.0

  # Outlier detection (IQR)
  # Outlier if value < Q1 - iqr_multiplier×IQR or value > Q3 + iqr_multiplier×IQR
  iqr_multiplier: 1.5

  # Noise filtering (rolling median)
  rolling_window_size: 3

  # Minimum readings for statistical analysis
  min_readings_for_stats: 10

  # Enable anomaly logging
  log_anomalies: true
```

---

## 🎓 Portfolio Değeri

✅ **Data Quality Management**

- "Production-grade data cleaning pipeline"
- "Multiple anomaly detection strategies"
- "Statistical analysis (Z-score, IQR methods)"

✅ **Signal Processing**

- "Noise filtering with median smoothing"
- "Rolling window calculations"
- "Spike and outlier detection"

✅ **Data Validation**

- "Missing value handling strategies"
- "Quality flags (GOOD, UNCERTAIN, BAD)"
- "Comprehensive anomaly reporting"

✅ **Async Pipeline Architecture**

- "Event-driven batch processing"
- "Callback-based downstream communication"
- "Graceful error handling"

---

## 🔄 Data Quality Levels

After cleaning, readings have quality levels:

```python
class DataQuality(Enum):
    GOOD = 0         # ✓ Passed all checks
    UNCERTAIN = 1    # ⚠️ Spike/outlier flagged
    BAD = 2          # ❌ Removed or invalid

# During cleaning:
if spike_detected:
    reading.quality = DataQuality.UNCERTAIN
    reading.metadata["z_score"] = z_value

if nan_detected and method == DROP:
    # Remove entirely

if outlier_detected:
    reading.quality = DataQuality.UNCERTAIN
```

---

## 📊 Anomaly Report Example

```python
pipeline.get_statistics()
# Returns:
{
    "batches_processed": 15,
    "readings_processed": 1523,
    "anomalies_found": 47,
    "cleaner_report": {
        "total_anomalies": 47,
        "by_type": {
            "spike": 12,
            "outlier": 18,
            "nan": 14,
            "noise": 3
        },
        "anomalies": [
            {
                "timestamp": "2026-05-08T10:30:45.123456",
                "equipment_id": "pump_1",
                "tag": "temperature",
                "anomaly_type": "spike",
                "value": 150.23,
                "reason": "Z-score spike: 5.67σ (threshold: 3.0σ)",
                "cleaning_action": "flagged_uncertain"
            },
            ...
        ]
    }
}
```

---

## 🚀 Usage Example: Complete Flow

```python
# Terminal 1: OPC-UA Server
python src/layer1_data_source/opc_ua_server.py

# Terminal 2: Modbus Server
python src/layer1_data_source/modbus_server.py

# Terminal 3: Python Bridge (publishes to MQTT)
python src/layer3_python_bridge/bridge.py

# Terminal 4: Integrated Pipeline (consumes from MQTT, cleans data)
python src/integrated_pipeline.py

# Beklenen Flow:
[Terminal 3] Bridge: 📤 Flushing batch: 100 readings to MQTT
[Terminal 4] Pipeline: 📥 Batch received: 100 readings
             Cleaner: 🧹 Cleaning pipeline: NaN, spike, outlier detection...
             Cleaner: ✅ Batch cleaning complete: 98 good readings, 2 anomalies
             Pipeline: 🔄 Calling downstream callback
             Database: 📊 Ready to write 98 clean readings to TimescaleDB
```

---

## ✅ Completion Checklist

- [x] NaN/missing value handling (DROP, FORWARD_FILL, BACKWARD_FILL, INTERPOLATE)
- [x] Spike detection (Z-score > 3σ)
- [x] Outlier detection (IQR > 1.5×IQR)
- [x] Noise filtering (3-point median)
- [x] Anomaly logging and reporting
- [x] AnomalyRecord dataclass with to_dict()
- [x] Complete cleaning pipeline (clean_batch method)
- [x] IntegratedPipeline class (Consumer + Cleaner)
- [x] Configuration in settings.yaml
- [x] Comprehensive test suite (test_layer6.py)
- [x] Production logging and error handling
- [x] Callback mechanism for downstream processing

---

## 🎯 Next Steps

### STEP 6: TimescaleDB Schema & Database Writing

- Create time-series database schema (3 tables)
- Implement batch insert logic
- Connection pooling (psycopg2)
- Data retention policies (30 days raw, 1 year compressed)
- Anomaly event logging to database

---

**Oluşturma Tarihi**: May 8, 2026  
**Step Durumu**: ✅ COMPLETE  
**Tahmin Edilen Süre**: 8 hafta (5/12 tamamlandı - %42)  
**Portfolio Değeri**: ⭐⭐⭐⭐⭐ (Data Quality + Signal Processing)

---

## 📚 Files Created

1. `src/layer6_data_cleaning/cleaner.py` — DataCleaner class (~380 lines)
2. `src/layer6_data_cleaning/__init__.py` — Module exports
3. `src/integrated_pipeline.py` — Consumer + Cleaner orchestrator (~300 lines)
4. `scripts/test_layer6.py` — Comprehensive test suite (~350 lines)
5. Updated `config/settings.yaml` — Data cleaning configuration section
