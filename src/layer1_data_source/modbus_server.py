"""
Layer 1b: Modbus TCP Server
Eski sistemler için Modbus TCP protokolü desteği
- Aynı 3 ekipmanı Modbus Holding Registers olarak
- 9 register (3 ekipman × 3 tag)
- OPC-UA ile senkron değerler
- pymodbus library ile server başlangıcı
"""

import asyncio
import logging
import math
import random
from datetime import datetime
from typing import Dict, List
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils import config

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

try:
    from pymodbus.server import AsyncModbusServ  # pymodbus v3+
    from pymodbus.datastore import ModbusSequentialDataBlock, ModbusSlaveContext, ModbusServerContext
except ImportError:
    try:
        # Fallback for older pymodbus version
        from pymodbus.server.asynchronous import StartAsyncTCPServer
        from pymodbus.datastore import ModbusSequentialDataBlock, ModbusSlaveContext, ModbusServerContext
    except ImportError:
        logger.error("pymodbus kütüphanesi yüklü değil. Yükle: pip install pymodbus")
        sys.exit(1)


class ModbusRegisterSimulation:
    """Modbus Register Simülasyon Modeli"""
    
    def __init__(self, equipment_id: str, tag_name: str, min_val: float, max_val: float):
        self.equipment_id = equipment_id
        self.tag_name = tag_name
        self.min_val = min_val
        self.max_val = max_val
        self.center = (min_val + max_val) / 2
        self.amplitude = (max_val - min_val) / 4
        self.time_offset = random.uniform(0, 2 * math.pi)
        
    def get_value(self, elapsed_time: float) -> int:
        """
        Modbus register değerini hesapla (0-65535 aralığında)
        
        Conversion:
        - Physical value (float) → Modbus register (int 0-65535)
        - Example: Temperature 45.2°C → 4520 (÷100 conversion)
        
        Args:
            elapsed_time: Server başladığından itibaren geçen süre (saniye)
        
        Returns:
            Modbus register value (0-65535)
        """
        # Sinüs + noise + drift (OPC-UA ile aynı algoritma)
        time_factor = (elapsed_time + self.time_offset) / 60.0
        sine_component = self.amplitude * math.sin(2 * math.pi * time_factor)
        noise_component = random.uniform(-0.02, 0.02) * (self.max_val - self.min_val)
        drift = 0.001 * (elapsed_time % 3600)
        
        physical_value = self.center + sine_component + noise_component + drift
        physical_value = max(self.min_val, min(self.max_val, physical_value))
        
        # Physical value → Register conversion
        # Ölçek: 100 (örn. 45.2°C → 4520)
        register_value = int(physical_value * 100)
        
        # 16-bit sınırında tutma (0-65535)
        register_value = max(0, min(65535, register_value))
        
        return register_value


class ModbusTCPServer:
    """Production-level Modbus TCP Server Implementation"""
    
    def __init__(self):
        self.host = None
        self.port = None
        self.server = None
        self.start_time = None
        self.registers = {}  # Register mapping: address → simulation object
        self.config = config.get('modbus_server', {})
        self.setup_registers()
        
    def setup_registers(self):
        """Modbus register mapping oluştur"""
        logger.info("Setting up Modbus register mapping...")
        
        register_configs = self.config.get('registers', [])
        
        for reg_config in register_configs:
            address = reg_config.get('address')
            equipment_id = reg_config.get('equipment_id')
            tag = reg_config.get('tag')
            
            # Equipment config'ından min/max değerleri bul
            equipment = config.get_equipment_by_id(equipment_id)
            if not equipment:
                logger.warning(f"Equipment not found: {equipment_id}")
                continue
            
            tag_config = next((t for t in equipment.get('tags', []) if t['name'] == tag), None)
            if not tag_config:
                logger.warning(f"Tag not found: {equipment_id}.{tag}")
                continue
            
            min_val = tag_config.get('min', 0)
            max_val = tag_config.get('max', 100)
            
            # Register simulation object
            sim = ModbusRegisterSimulation(equipment_id, tag, min_val, max_val)
            self.registers[address] = sim
            
            logger.debug(f"Register {address}: {equipment_id}.{tag} ({min_val}-{max_val})")
    
    async def update_holding_registers(self, context):
        """Holding registers'ı periyodik olarak güncelle"""
        logger.info("Starting Modbus register update loop...")
        self.start_time = datetime.now()
        
        while True:
            try:
                elapsed_time = (datetime.now() - self.start_time).total_seconds()
                
                # Her register için yeni değer hesapla
                for address, simulation in self.registers.items():
                    new_value = simulation.get_value(elapsed_time)
                    
                    # Holding registers context'e yazma
                    context.setValues(3, address, [new_value])  # 3 = Holding Registers
                
                # Her 1 saniye güncelle
                await asyncio.sleep(1.0)
                
            except Exception as e:
                logger.error(f"Error updating Modbus registers: {e}", exc_info=True)
                await asyncio.sleep(1.0)
    
    async def start(self):
        """Modbus TCP server başlat"""
        try:
            self.host = self.config.get('host', '0.0.0.0')
            self.port = self.config.get('port', 502)
            
            logger.info(f"Modbus TCP Server starting on {self.host}:{self.port}")
            
            # Datastore setup
            store = ModbusSlaveContext(
                di=ModbusSequentialDataBlock(0, [0] * 100),  # Discrete inputs
                co=ModbusSequentialDataBlock(0, [0] * 100),  # Coils
                hr=ModbusSequentialDataBlock(0, [0] * 100),  # Holding registers
                ir=ModbusSequentialDataBlock(0, [0] * 100),  # Input registers
            )
            context = ModbusServerContext(slaves={1: store}, single=False)
            
            # Modbus TCP server başlat (pymodbus v3 kullanıyor)
            try:
                # Try new API (pymodbus >= 3.0)
                server = AsyncModbusServ(
                    host=self.host,
                    port=self.port,
                    context=context
                )
                await server.serve_forever()
                
            except Exception as e:
                logger.debug(f"New API failed ({e}), trying legacy API...")
                # Fallback to legacy API
                from pymodbus.server.asynchronous import StartAsyncTCPServer
                await StartAsyncTCPServer(context, address=(self.host, self.port))
            
            logger.info("✓ Modbus TCP Server started successfully")
            
            # Register update loop'unu başlat
            await self.update_holding_registers(context)
            
        except Exception as e:
            logger.error(f"Failed to start Modbus TCP server: {e}", exc_info=True)
            raise
        finally:
            logger.info("Modbus TCP Server stopped")


async def main():
    """Main entry point"""
    logger.info("=" * 80)
    logger.info("LAYER 1b: Modbus TCP Server (Legacy System Support)")
    logger.info("=" * 80)
    
    server = ModbusTCPServer()
    
    try:
        await server.start()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    # Windows için event loop policy
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    asyncio.run(main())
