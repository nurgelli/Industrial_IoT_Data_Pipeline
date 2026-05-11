"""
Layer 2b: Modbus TCP Client
Modbus TCP Server'dan polling ile veri okuma
- Asynchronous polling loop
- Reconnect logic with exponential backoff
- Register → physical value conversion
- Logging ve error handling
"""

import asyncio
import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    from pymodbus.client import AsyncModbusTcpClient
except ImportError:
    try:
        # Fallback for older pymodbus
        from pymodbus.client.asynchronous import AsyncModbusTcpClient
    except ImportError:
        logger.error("pymodbus yüklü değil: pip install pymodbus")
        sys.exit(1)


class ModbusTCPClient:
    """Production-level Modbus TCP Client with polling"""
    
    def __init__(self, host: str = None, port: int = None):
        self.host = host or config.get('modbus_server.host', 'localhost')
        self.port = port or config.get('modbus_server.port', 502)
        self.timeout = config.get('modbus_server.timeout_sec', 5)
        
        self.client = AsyncModbusTcpClient(host=self.host, port=self.port, timeout=self.timeout)
        self.connected = False
        
        # Register mapping from config
        self.register_map = self._build_register_map()
        
        # Reconnect config
        self.reconnect_delay = 1
        self.max_reconnect_delay = 60
        self.exponential_base = 2
    
    def _build_register_map(self) -> Dict[int, Dict]:
        """Build register mapping from config"""
        register_map = {}
        register_configs = config.get('modbus_server.registers', [])
        
        for reg_config in register_configs:
            address = reg_config.get('address')
            register_map[address] = {
                'equipment_id': reg_config.get('equipment_id'),
                'tag': reg_config.get('tag'),
                'scale': reg_config.get('scale', 1.0),
            }
        
        return register_map
    
    async def connect(self, retry_count: int = 0) -> bool:
        """
        Connect to Modbus TCP server with exponential backoff
        
        Args:
            retry_count: Recursive retry counter
        
        Returns:
            True if connected, False if max retries exceeded
        """
        max_retries = 10
        
        try:
            logger.info(f"Connecting to Modbus server: {self.host}:{self.port}")
            
            # For newer pymodbus (v3+)
            connected = await self.client.connect()
            
            if not connected:
                raise Exception("Connection refused")
            
            self.connected = True
            logger.info("✓ Modbus TCP Client connected")
            self.reconnect_delay = 1  # Reset delay on successful connect
            return True
        
        except Exception as e:
            self.connected = False
            logger.warning(f"Connection failed (attempt {retry_count + 1}/{max_retries}): {e}")
            
            if retry_count >= max_retries:
                logger.error(f"✗ Failed to connect after {retry_count} retries")
                return False
            
            # Exponential backoff
            wait_time = min(self.reconnect_delay * (self.exponential_base ** retry_count), self.max_reconnect_delay)
            logger.info(f"Retrying in {wait_time:.1f} seconds...")
            await asyncio.sleep(wait_time)
            
            return await self.connect(retry_count + 1)
    
    async def read_registers(self, address: int, count: int = 1) -> Optional[list]:
        """
        Read holding registers from Modbus server
        
        Args:
            address: Starting register address
            count: Number of registers to read
        
        Returns:
            List of register values or None if error
        """
        if not self.connected:
            logger.warning("Not connected, cannot read registers")
            return None
        
        try:
            # Function code 03: Read Holding Registers
            result = await self.client.read_holding_registers(
                address=address,
                count=count,
                unit=1  # Slave unit ID
            )
            
            if hasattr(result, 'registers'):
                return result.registers
            else:
                logger.warning(f"Error reading registers {address}-{address+count-1}")
                return None
        
        except Exception as e:
            logger.warning(f"Error reading registers: {e}")
            return None
    
    async def get_all_values(self) -> Dict[str, float]:
        """
        Read all configured registers and convert to physical values
        
        Returns:
            Dict of {equipment_id.tag: physical_value}
        """
        values = {}
        
        if not self.connected:
            logger.warning("Not connected")
            return values
        
        try:
            for address, reg_info in self.register_map.items():
                equipment_id = reg_info.get('equipment_id')
                tag = reg_info.get('tag')
                scale = reg_info.get('scale', 1.0)
                
                # Read single register
                registers = await self.read_registers(address, count=1)
                
                if registers:
                    raw_value = registers[0]
                    # Conversion: register (0-65535) → physical value
                    # Scale factor (default 100): 4520 → 45.20
                    physical_value = (raw_value / 100) * scale
                    
                    key = f"{equipment_id}.{tag}"
                    values[key] = physical_value
                    
                    logger.debug(f"Register {address}: {key} = {physical_value:.2f}")
            
            return values
        
        except Exception as e:
            logger.error(f"Error getting all values: {e}", exc_info=True)
            return {}
    
    async def polling_loop(self, interval_sec: float = 1.0):
        """
        Continuous polling loop
        
        Args:
            interval_sec: Polling interval in seconds
        """
        logger.info(f"Starting Modbus polling loop (interval={interval_sec}s)")
        
        while True:
            try:
                values = await self.get_all_values()
                
                if values:
                    logger.debug(f"Polled {len(values)} values")
                
                await asyncio.sleep(interval_sec)
            
            except Exception as e:
                logger.error(f"Error in polling loop: {e}", exc_info=True)
                await asyncio.sleep(interval_sec)
    
    async def disconnect(self):
        """Disconnect from Modbus server"""
        try:
            if self.client:
                self.client.close()
            
            self.connected = False
            logger.info("✓ Modbus TCP Client disconnected")
        
        except Exception as e:
            logger.error(f"Error disconnecting: {e}", exc_info=True)


async def main_demo():
    """Demo: Modbus client usage"""
    
    # Create client
    client = ModbusTCPClient()
    
    try:
        # Connect
        if not await client.connect():
            logger.error("Failed to connect")
            return
        
        # Read values once
        logger.info("\n📖 Reading all registers:")
        values = await client.get_all_values()
        for key, value in values.items():
            logger.info(f"  {key}: {value:.2f}")
        
        # Polling loop for 30 seconds
        logger.info("\n📡 Starting polling loop (30 seconds)...")
        
        polling_task = asyncio.create_task(client.polling_loop(interval_sec=1.0))
        
        try:
            await asyncio.wait_for(polling_task, timeout=30)
        except asyncio.TimeoutError:
            polling_task.cancel()
            logger.info("Polling loop stopped")
    
    finally:
        await client.disconnect()


if __name__ == "__main__":
    logger.info("="*80)
    logger.info("LAYER 2b: Modbus TCP Client (Polling)")
    logger.info("="*80)
    
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    asyncio.run(main_demo())
