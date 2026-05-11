# STEP 2: Veri Kaynakları — TAMAMLANDI ✅

## 📋 Neler Yapıldı?

### ✅ 1. Katman 1a: OPC-UA Server

**Dosya**: `src/layer1_data_source/opc_ua_server.py` (~250 satır)

**Özellikler**:

- ✅ 3 sanal ekipman (Pump, Compressor, Heater)
- ✅ 3 tag/ekipman (temperature, pressure, vibration/flow/power)
- ✅ Realistic noise simulation:
  - Sinüs dalga (période = 60 saniye)
  - Random perturbation (±2% of range)
  - Drift (çok hafif uzun-vadeli trend)
- ✅ OPC-UA node tree (namespace + objects + variables)
- ✅ Asynchronous asyncua library
- ✅ Value update loop (per 1 saniye)
- ✅ Production logging

**Sınıf Yapısı**:

```python
class VirtualEquipment:
    get_tag_value(tag_name, elapsed_time)  # Sinüs + noise + drift

class OPCUAServer:
    setup_equipment_nodes()      # OPC-UA tree oluş
    run_value_update_loop()      # Periyodik update
    start()                       # Server başlat
    stop()                        # Server durdur
```

**Port**: 4840
**Endpoint**: `opc.tcp://0.0.0.0:4840/`

---

### ✅ 2. Katman 1b: Modbus TCP Server

**Dosya**: `src/layer1_data_source/modbus_server.py` (~220 satır)

**Özellikler**:

- ✅ Aynı 3 ekipmanı Modbus Register'da
- ✅ 9 Holding Register (3 ekipman × 3 tag)
- ✅ Physical → Register conversion (×100 scale)
- ✅ OPC-UA ile senkron değerler (aynı algoritma)
- ✅ Modbus datastore setup (di, coils, HR, IR)
- ✅ Asynchronous pymodbus library
- ✅ Value update loop (per 1 saniye)
- ✅ Production logging

**Sınıf Yapısı**:

```python
class ModbusRegisterSimulation:
    get_value(elapsed_time)  # Sinüs + noise + drift → register (0-65535)

class ModbusTCPServer:
    setup_registers()             # Register mapping oluş
    update_holding_registers()    # Periyodik update
    start()                       # Server başlat
```

**Port**: 502
**Registers**: 0-99 (9 ekipman register'ı)

**Register Mapping**:

```
Pump_1:
  - Register 0: temperature (20-80°C)
  - Register 1: pressure (0-150 PSI)
  - Register 2: vibration (0-20 mm/s)

Compressor_1:
  - Register 10: temperature (10-60°C)
  - Register 11: pressure (50-200 PSI)
  - Register 12: flow_rate (0-500 m³/h)

Heater_1:
  - Register 20: temperature (100-300°C)
  - Register 21: pressure (0-100 PSI)
  - Register 22: power_consumption (0-500 kW)
```

---

### ✅ 3. Test Scripts

**`scripts/test_opc_client.py`** (~120 satır)

- OPC-UA server'a connect et
- Equipment nodes'ları list et
- Tag values'ları oku
- Subscription test (real-time updates)

**`scripts/test_modbus_client.py`** (~130 satır)

- Modbus server'a connect et
- Holding registers'ı oku
- Physical value conversion (register → physical)
- Batch read test

**`scripts/test_layer1.py`**

- Test talimatları ve workflow

---

## 🚀 Nasıl Test Etmek?

### Prerequisite

```bash
# venv'i activate et
venv\Scripts\activate

# Required packages yüklü olduğundan emin ol
pip install asyncua pymodbus pyyaml python-json-logger tenacity
```

### Test 1: OPC-UA Server

**Terminal 1** - OPC-UA server başlat:

```bash
python src/layer1_data_source/opc_ua_server.py
```

**Beklenen Output**:

```
================================================================================
LAYER 1a: OPC-UA Server (Virtual SCADA Equipment)
================================================================================
INFO:__main__:OPC-UA Server initialized at opc.tcp://0.0.0.0:4840/
INFO:__main__:Setting up OPC-UA node tree...
INFO:__main__:Equipment folder created: Centrifugal Pump #1 (pump_1)
INFO:__main__:Equipment folder created: Air Compressor #1 (compressor_1)
INFO:__main__:Equipment folder created: Process Heater #1 (heater_1)
INFO:__main__:✓ OPC-UA Server started successfully
INFO:__main__:Starting value update loop...
```

**Terminal 2** - OPC-UA client test:

```bash
python scripts/test_opc_client.py
```

**Beklenen Output**:

```
✓ Connected to OPC-UA server
📍 Equipment: pump_1
  • temperature: 45.23 °C
  • pressure: 75.45 PSI
  • vibration: 2.12 mm/s
📍 Equipment: compressor_1
  • temperature: 35.67 °C
  • pressure: 119.89 PSI
  • flow_rate: 251.34 m³/h
...
✓ OPC-UA Client test completed!
```

---

### Test 2: Modbus TCP Server

**Terminal 1** - Modbus server başlat:

```bash
python src/layer1_data_source/modbus_server.py
```

**Beklenen Output**:

```
================================================================================
LAYER 1b: Modbus TCP Server (Legacy System Support)
================================================================================
INFO:__main__:Setting up Modbus register mapping...
INFO:__main__:Modbus TCP Server starting on 0.0.0.0:502
INFO:__main__:✓ Modbus TCP Server started successfully
INFO:__main__:Starting Modbus register update loop...
```

**Terminal 2** - Modbus client test:

```bash
python scripts/test_modbus_client.py
```

**Beklenen Output**:

```
✓ Connected to Modbus TCP server
  Register 0: pump_1.temperature = 45.23
  Register 1: pump_1.pressure = 75.45
  Register 2: pump_1.vibration = 2.12
  Register 10: compressor_1.temperature = 35.67
  Register 11: compressor_1.pressure = 119.89
  Register 12: compressor_1.flow_rate = 251.34
...
✓ Modbus TCP Client test completed!
```

---

### Test 3: Dual Protocol Synchronization

OPC-UA ve Modbus'tan aynı anda okuyun ve değerleri karşılaştırın:

```bash
# Terminal 1
python src/layer1_data_source/opc_ua_server.py

# Terminal 2
python src/layer1_data_source/modbus_server.py

# Terminal 3
python scripts/test_opc_client.py

# Terminal 4
python scripts/test_modbus_client.py
```

**Karşılaştırma**:

- OPC-UA: 45.23°C
- Modbus: 45.23 (45.23 ÷ 100 = 0.4523 → scaled back to 45.23)

✅ Değerler senkron olmalı!

---

## 📊 Veri Akışı

```
Physical Equipment Simulation (VirtualEquipment)
  ↓ (Sinüs + Noise + Drift)
  ├→ OPC-UA Server (asyncua)        [Port: 4840]
  │   └→ Node Tree (Equipment/Tags)
  │       └→ OPC-UA Client (read/subscribe)
  │
  └→ Modbus TCP Server (pymodbus)   [Port: 502]
      └→ Holding Registers (0-99)
          └→ Modbus Client (read)
```

---

## 🎓 Portfolio Değeri

✅ **Dual Protocol Expertise**

- "OPC-UA (modern SCADA) + Modbus TCP (legacy systems)"
- "Türkmenistan'da %60-70 eski sistem → Modbus"
- "Yeni projeler → OPC-UA"

✅ **Data Simulation**

- "Realistic sensor patterns (sine + noise + drift)"
- "Production-level data generation"
- "Anomaly detection için test data"

✅ **Asynchronous Programming**

- "asyncua ve async/await patterns"
- "Concurrent value updates"
- "Non-blocking I/O"

✅ **Protocol Implementation**

- "OPC-UA node tree architecture"
- "Modbus register mapping"
- "Physical ↔ Register conversion"

---

## 📝 Code Quality

| Metrik         | Durum                          |
| -------------- | ------------------------------ |
| Lines of Code  | 470+                           |
| Logging        | JSON-ready structured          |
| Error Handling | Try-except + graceful shutdown |
| Documentation  | Type hints + docstrings        |
| Configuration  | YAML-based (settings.yaml)     |
| Testing        | 3 test scripts                 |

---

## 🚨 Troubleshooting

### "Port 502 is already in use"

- Modbus port < 1024 → Windows'ta admin privileges gerekir
- **Çözüm**: PowerShell'i "Run as Administrator" ile aç

### "asyncua module not found"

```bash
pip install asyncua
```

### "OPC-UA server connects, but no values"

- Config'de equipment list'i kontrol et
- `config/settings.yaml` → `opc_ua_server.equipment`

### Modbus registers 0 kalmaya devam ediyor

- Server ve client'in aynı `unit` ID'si kullanmasını kontrol et (default: 1)

---

## 📚 Dosya Özeti

| Dosya                     | Satır | Amaç                    |
| ------------------------- | ----- | ----------------------- |
| **opc_ua_server.py**      | 250   | OPC-UA sanal sunucu     |
| **modbus_server.py**      | 220   | Modbus TCP sanal sunucu |
| ****init**.py**           | 12    | Module exports          |
| **test_opc_client.py**    | 120   | OPC-UA test             |
| **test_modbus_client.py** | 130   | Modbus test             |
| **test_layer1.py**        | 30    | Test workflow           |

---

## ✅ Completion Checklist

- [x] OPC-UA server (asyncua)
- [x] Modbus TCP server (pymodbus)
- [x] Virtual equipment simulation
- [x] Realistic noise patterns
- [x] Config-driven setup
- [x] OPC-UA client test
- [x] Modbus client test
- [x] Dual protocol sync test
- [x] Error handling
- [x] Logging
- [x] Documentation

---

## 🎯 Next Step: STEP 3

**Katman 2-3: OPC-UA Client + Python Bridge**

- OPC-UA client subscription
- Modbus client polling
- Unified JSON output format
- MQTT producer setup (preview)

---

**Oluşturma Tarihi**: May 8, 2026  
**Step Durumu**: ✅ COMPLETE  
**Tahmin Edilen Süre**: 8 hafta (2/12 tamamlandı)
