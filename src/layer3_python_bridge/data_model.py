"""
Data Model: Unified JSON format for all sources
OPC-UA ve Modbus'tan gelen veriler ortak formatta
"""

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum


class DataQuality(Enum):
    """OPC-UA Quality flags"""
    GOOD = 0
    UNCERTAIN = 1
    BAD = 2


@dataclass
class SensorReading:
    """
    Unified sensor reading format
    OPC-UA ve Modbus'tan gelen veriler bu formatta
    """
    timestamp: datetime           # Reading time
    equipment_id: str            # Equipment identifier
    tag: str                      # Tag/sensor name
    value: float                  # Physical value (temperature, pressure, etc.)
    unit: str                     # Unit (°C, PSI, mm/s, etc.)
    source: str                   # Data source (OPC-UA or Modbus)
    quality: int = DataQuality.GOOD.value  # Quality flag (0=good, 1=uncertain, 2=bad)
    sequence_number: Optional[int] = None  # Message sequence for ordering
    raw_value: Optional[Any] = None        # Raw value before conversion (for Modbus)
    metadata: Optional[Dict[str, Any]] = None  # Additional metadata
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary (for JSON serialization)"""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        data['quality'] = self.quality
        data['source'] = self.source
        return data
    
    def to_json_str(self) -> str:
        """Convert to JSON string"""
        import json
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_opc_ua(cls, equipment_id: str, tag: str, value: float, unit: str,
                   quality: int = DataQuality.GOOD.value) -> 'SensorReading':
        """Create from OPC-UA data"""
        return cls(
            timestamp=datetime.now(),
            equipment_id=equipment_id,
            tag=tag,
            value=value,
            unit=unit,
            source='OPC-UA',
            quality=quality
        )
    
    @classmethod
    def from_modbus(cls, equipment_id: str, tag: str, physical_value: float,
                   unit: str, raw_value: int, scale: float = 1.0) -> 'SensorReading':
        """Create from Modbus data"""
        return cls(
            timestamp=datetime.now(),
            equipment_id=equipment_id,
            tag=tag,
            value=physical_value,
            unit=unit,
            source='Modbus',
            quality=DataQuality.GOOD.value,
            raw_value=raw_value,
            metadata={'scale': scale, 'raw_register': raw_value}
        )


@dataclass
class BatchedReadings:
    """Batch of sensor readings (for efficient database writing)"""
    readings: list  # List[SensorReading]
    batch_timestamp: datetime
    batch_size: int
    source_types: set  # {'OPC-UA', 'Modbus'} or both
    
    def add_reading(self, reading: SensorReading):
        """Add reading to batch"""
        self.readings.append(reading)
        self.batch_size += 1
        self.source_types.add(reading.source)
    
    def to_dict_list(self) -> list:
        """Convert all readings to dict list"""
        return [r.to_dict() for r in self.readings]
    
    def clear(self):
        """Clear batch"""
        self.readings = []
        self.batch_size = 0
        self.source_types = set()


if __name__ == "__main__":
    # Test data model
    
    # OPC-UA reading
    opc_reading = SensorReading.from_opc_ua(
        equipment_id='pump_1',
        tag='temperature',
        value=45.23,
        unit='°C',
        quality=DataQuality.GOOD.value
    )
    
    print("OPC-UA Reading:")
    print(opc_reading.to_json_str())
    print()
    
    # Modbus reading
    modbus_reading = SensorReading.from_modbus(
        equipment_id='pump_1',
        tag='temperature',
        physical_value=45.23,
        unit='°C',
        raw_value=4523,
        scale=1.0
    )
    
    print("Modbus Reading:")
    print(modbus_reading.to_json_str())
    print()
    
    # Batch
    batch = BatchedReadings(
        readings=[opc_reading, modbus_reading],
        batch_timestamp=datetime.now(),
        batch_size=2,
        source_types={'OPC-UA', 'Modbus'}
    )
    
    print(f"Batch: {batch.batch_size} readings from {batch.source_types}")
    for reading in batch.to_dict_list():
        print(f"  - {reading['equipment_id']}.{reading['tag']}: {reading['value']} {reading['unit']} ({reading['source']})")
