"""
Layer 3: Python Bridge
Dual protocol collector — OPC-UA + Modbus
Her iki kaynaktan veri topla, unified format'ta output
"""

import asyncio
import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Callable
import json

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils import config
from layer2_opc_ua_client.opc_client import OPCUAClient
from layer2_opc_ua_client.modbus_client import ModbusTCPClient
from layer3_python_bridge.data_model import SensorReading, BatchedReadings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PythonBridge:
    """
    Dual-protocol bridge:
    - OPC-UA subscription (async event-driven)
    - Modbus polling (async polling)
    - Unified JSON output
    - Batch buffering for efficiency
    """
    
    def __init__(self, on_batch_complete: Callable = None):
        self.opc_client = None
        self.modbus_client = None
        self.on_batch_complete = on_batch_complete
        
        # Batch buffering config
        batch_config = config.get('python_bridge', {})
        self.buffer_size = batch_config.get('output', {}).get('batch_size', 100)
        self.buffer_timeout = batch_config.get('output', {}).get('buffer_timeout_sec', 5)
        
        # Current batch
        self.current_batch = BatchedReadings(
            readings=[],
            batch_timestamp=datetime.now(),
            batch_size=0,
            source_types=set()
        )
        self.last_batch_time = datetime.now()
        self.sequence_number = 0
    
    async def initialize(self) -> bool:
        """Initialize both OPC-UA and Modbus clients"""
        try:
            logger.info("Initializing Python Bridge...")
            
            # OPC-UA client
            logger.info("\n[1/4] Initializing OPC-UA client...")
            self.opc_client = OPCUAClient(on_data_change=self._on_opc_data_change)
            
            if not await self.opc_client.connect():
                logger.warning("OPC-UA client failed to connect (will retry)")
            else:
                if not await self.opc_client.setup_subscriptions():
                    logger.warning("OPC-UA subscriptions failed")
            
            # Modbus client
            logger.info("\n[2/4] Initializing Modbus client...")
            self.modbus_client = ModbusTCPClient()
            
            if not await self.modbus_client.connect():
                logger.warning("Modbus client failed to connect (will retry)")
            
            logger.info("\n[3/4] Bridge initialized")
            logger.info("  • OPC-UA: subscription-based (event-driven)")
            logger.info("  • Modbus: polling-based (1s interval)")
            logger.info("  • Buffer: %d readings or %ds timeout" % (self.buffer_size, self.buffer_timeout))
            
            return True
        
        except Exception as e:
            logger.error(f"Failed to initialize bridge: {e}", exc_info=True)
            return False
    
    def _on_opc_data_change(self, node_name: str, value, data):
        """OPC-UA data change callback"""
        try:
            # Parse equipment_id.tag from node_name
            # (Would need more sophisticated parsing in production)
            logger.debug(f"OPC-UA DataChange: {node_name} = {value}")
            
            # Add to batch (simplified)
            # In production, would parse equipment_id and tag properly
        except Exception as e:
            logger.warning(f"Error processing OPC-UA data change: {e}")
    
    async def collect_from_opc_ua(self):
        """Periodically collect from OPC-UA"""
        if not self.opc_client or not self.opc_client.connected:
            logger.debug("OPC-UA client not ready")
            return
        
        try:
            all_values = await self.opc_client.get_all_values()
            
            for key, value in all_values.items():
                try:
                    equipment_id, tag_name = key.split('.')
                    
                    # Get unit from config
                    equipment = config.get_equipment_by_id(equipment_id)
                    if not equipment:
                        continue
                    
                    tag_config = next((t for t in equipment.get('tags', []) if t['name'] == tag_name), None)
                    if not tag_config:
                        continue
                    
                    unit = tag_config.get('unit', '')
                    
                    # Create reading
                    reading = SensorReading.from_opc_ua(
                        equipment_id=equipment_id,
                        tag=tag_name,
                        value=value,
                        unit=unit
                    )
                    
                    self._add_to_batch(reading)
                
                except Exception as e:
                    logger.warning(f"Error processing {key}: {e}")
        
        except Exception as e:
            logger.warning(f"Error collecting from OPC-UA: {e}")
    
    async def collect_from_modbus(self):
        """Periodically collect from Modbus"""
        if not self.modbus_client or not self.modbus_client.connected:
            logger.debug("Modbus client not ready")
            return
        
        try:
            all_values = await self.modbus_client.get_all_values()
            
            for key, physical_value in all_values.items():
                try:
                    equipment_id, tag_name = key.split('.')
                    
                    # Get unit and register info from config
                    equipment = config.get_equipment_by_id(equipment_id)
                    if not equipment:
                        continue
                    
                    tag_config = next((t for t in equipment.get('tags', []) if t['name'] == tag_name), None)
                    if not tag_config:
                        continue
                    
                    unit = tag_config.get('unit', '')
                    
                    # Find register info
                    register_config = next(
                        (r for r in config.get('modbus_server.registers', [])
                         if r.get('equipment_id') == equipment_id and r.get('tag') == tag_name),
                        None
                    )
                    
                    scale = register_config.get('scale', 1.0) if register_config else 1.0
                    raw_value = int(physical_value * 100)  # Reverse calculation
                    
                    # Create reading
                    reading = SensorReading.from_modbus(
                        equipment_id=equipment_id,
                        tag=tag_name,
                        physical_value=physical_value,
                        unit=unit,
                        raw_value=raw_value,
                        scale=scale
                    )
                    
                    self._add_to_batch(reading)
                
                except Exception as e:
                    logger.warning(f"Error processing {key}: {e}")
        
        except Exception as e:
            logger.warning(f"Error collecting from Modbus: {e}")
    
    def _add_to_batch(self, reading: SensorReading):
        """Add reading to batch, flush if needed"""
        self.sequence_number += 1
        reading.sequence_number = self.sequence_number
        
        self.current_batch.add_reading(reading)
        
        # Check if batch should be flushed
        should_flush = False
        
        # 1. Buffer size reached
        if self.current_batch.batch_size >= self.buffer_size:
            logger.debug(f"Batch buffer full ({self.buffer_size} readings)")
            should_flush = True
        
        # 2. Timeout reached
        elapsed = (datetime.now() - self.last_batch_time).total_seconds()
        if elapsed >= self.buffer_timeout and self.current_batch.batch_size > 0:
            logger.debug(f"Batch timeout ({self.buffer_timeout}s, {self.current_batch.batch_size} readings)")
            should_flush = True
        
        if should_flush:
            self._flush_batch()
    
    def _flush_batch(self):
        """Flush current batch to output"""
        if self.current_batch.batch_size == 0:
            return
        
        logger.info(f"📤 Flushing batch: {self.current_batch.batch_size} readings from {self.current_batch.source_types}")
        
        # Output formats
        output_config = config.get('python_bridge.output', {})
        output_format = output_config.get('format', 'json')
        
        if output_format == 'json':
            self._output_json()
        
        # Callback
        if self.on_batch_complete:
            self.on_batch_complete(self.current_batch)
        
        # Reset batch
        self.current_batch = BatchedReadings(
            readings=[],
            batch_timestamp=datetime.now(),
            batch_size=0,
            source_types=set()
        )
        self.last_batch_time = datetime.now()
    
    def _output_json(self):
        """Output batch as JSON"""
        for reading in self.current_batch.readings:
            json_str = reading.to_json_str()
            logger.info(f"  → {json_str}")
    
    async def collection_loop(self):
        """Main collection loop"""
        logger.info("\n[4/4] Starting collection loop...")
        logger.info("Collecting from both OPC-UA (event) and Modbus (polling)")
        
        polling_interval = 1.0  # seconds
        
        while True:
            try:
                # Collect from both sources
                await self.collect_from_opc_ua()
                await self.collect_from_modbus()
                
                # Check timeout flush
                elapsed = (datetime.now() - self.last_batch_time).total_seconds()
                if elapsed >= self.buffer_timeout and self.current_batch.batch_size > 0:
                    self._flush_batch()
                
                await asyncio.sleep(polling_interval)
            
            except Exception as e:
                logger.error(f"Error in collection loop: {e}", exc_info=True)
                await asyncio.sleep(polling_interval)
    
    async def stop(self):
        """Stop bridge"""
        # Flush remaining batch
        if self.current_batch.batch_size > 0:
            logger.info("Flushing remaining batch...")
            self._flush_batch()
        
        if self.opc_client:
            await self.opc_client.disconnect()
        
        if self.modbus_client:
            await self.modbus_client.disconnect()
        
        logger.info("✓ Bridge stopped")


async def main():
    """Main entry point"""
    logger.info("="*80)
    logger.info("LAYER 3: Python Bridge (Dual Protocol)")
    logger.info("="*80)
    
    bridge = PythonBridge()
    
    try:
        # Initialize
        if not await bridge.initialize():
            logger.error("Failed to initialize bridge")
            return
        
        # Run collection loop
        await bridge.collection_loop()
    
    except KeyboardInterrupt:
        logger.info("Received interrupt, stopping...")
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
    finally:
        await bridge.stop()


if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    asyncio.run(main())
