"""
Test: Modbus TCP Client
Layer 1b (Modbus TCP Server) ile bağlantı test et
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.utils import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    from pymodbus.client import ModbusTcpClient
except ImportError:
    try:
        # Fallback for older pymodbus
        from pymodbus.client.sync import ModbusTcpClient
    except ImportError:
        logger.error("pymodbus yüklü değil: pip install pymodbus")
        sys.exit(1)


def test_modbus_client():
    """Modbus TCP server'a bağlan ve register'ları oku"""
    
    modbus_config = config.get('modbus_server', {})
    host = modbus_config.get('host', 'localhost')
    port = modbus_config.get('port', 502)
    
    client = ModbusTcpClient(host=host, port=port, timeout=5)
    
    try:
        logger.info(f"Connecting to {host}:{port}...")
        connected = client.connect()
        
        if not connected:
            logger.error(f"✗ Failed to connect to {host}:{port}")
            logger.info("Make sure Modbus server is running:")
            logger.info("  python src/layer1_data_source/modbus_server.py")
            return False
        
        logger.info("✓ Connected to Modbus TCP server")
        
        # Register mapping oku
        register_configs = modbus_config.get('registers', [])
        equipment_dict = {}
        
        for reg_config in register_configs:
            address = reg_config.get('address')
            equipment_id = reg_config.get('equipment_id')
            tag = reg_config.get('tag')
            scale = reg_config.get('scale', 1.0)
            
            # Read holding register (function code 03)
            response = client.read_holding_registers(
                address=address,
                count=1,
                unit=1  # Slave unit ID
            )
            
            if hasattr(response, 'registers') and len(response.registers) > 0:
                raw_value = response.registers[0]
                physical_value = (raw_value / 100) * scale  # Conversion: register → physical
                
                if equipment_id not in equipment_dict:
                    equipment_dict[equipment_id] = {}
                
                equipment_dict[equipment_id][tag] = physical_value
                
                logger.info(f"  Register {address}: {equipment_id}.{tag} = {physical_value:.2f}")
            else:
                logger.warning(f"  Register {address}: Error reading value")
        
        logger.info("\n📊 Equipment Values Summary:")
        for equipment_id, tags in equipment_dict.items():
            logger.info(f"\n  📍 {equipment_id}:")
            for tag, value in tags.items():
                logger.info(f"    • {tag}: {value:.2f}")
        
        # Read multiple registers test
        logger.info("\n📊 Batch Read Test (all registers):")
        if register_configs:
            min_addr = min(r.get('address', 0) for r in register_configs)
            max_addr = max(r.get('address', 0) for r in register_configs)
            count = max_addr - min_addr + 1
            
            response = client.read_holding_registers(
                address=min_addr,
                count=count,
                unit=1
            )
            
            if hasattr(response, 'registers'):
                logger.info(f"  Read {len(response.registers)} registers from {min_addr} to {max_addr}")
                for i, val in enumerate(response.registers):
                    logger.info(f"    [{min_addr + i}] = {val}")
        
        client.close()
        logger.info("\n✓ Modbus TCP Client test completed!")
        return True
    
    except Exception as e:
        logger.error(f"Connection error: {e}", exc_info=True)
        return False
    
    finally:
        if client:
            client.close()


def main():
    logger.info("="*80)
    logger.info("TEST: Modbus TCP Client")
    logger.info("="*80)
    logger.info("\nMake sure Modbus server is running:")
    logger.info("  python src/layer1_data_source/modbus_server.py\n")
    
    success = test_modbus_client()
    
    if not success:
        logger.error("❌ Test failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
