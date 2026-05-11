"""
Layer 1a: OPC-UA Server
Sanal SCADA ekipmanları ile production-level OPC-UA server
- 3 sanal ekipman (Pump, Compressor, Heater)
- Her ekipmanın 3 tag'ı (temperature, pressure, vibration/flow/power)
- Gerçekçi noise patterns (sinüs dalga + random perturbation)
- asyncua library ile server başlangıcı
"""

import asyncio
import logging
import math
import random
from datetime import datetime
from typing import Dict, List, Tuple
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
    from asyncua import Server, ua
    from asyncua.common import ua
except ImportError:
    logger.error("asyncua kütüphanesi yüklü değil. Yükle: pip install asyncua")
    sys.exit(1)


class VirtualEquipment:
    """Sanal ekipman simülasyon modeli"""
    
    def __init__(self, equipment_id: str, name: str, location: str, tags: List[Dict]):
        self.equipment_id = equipment_id
        self.name = name
        self.location = location
        self.tags = tags
        self.time_offset = random.uniform(0, 2 * math.pi)
        self.node_dict = {}  # OPC-UA node references
        
    def get_tag_value(self, tag_name: str, elapsed_time: float) -> float:
        """
        Tag'ın güncel değerini hesapla (sinüs + noise + drift)
        
        Args:
            tag_name: Tag adı (temperature, pressure, vibration vb.)
            elapsed_time: Server başladığından itibaren geçen süre (saniye)
        
        Returns:
            Simüle edilen sensör değeri
        """
        tag_config = next((t for t in self.tags if t['name'] == tag_name), None)
        if not tag_config:
            return 0.0
        
        min_val = tag_config.get('min', 0)
        max_val = tag_config.get('max', 100)
        center = (min_val + max_val) / 2
        amplitude = (max_val - min_val) / 4  # Dalgaların genliği = aralığın 1/4'ü
        
        # Sinüs tabanlı değişim (période = 60 saniye)
        time_factor = (elapsed_time + self.time_offset) / 60.0
        sine_component = amplitude * math.sin(2 * math.pi * time_factor)
        
        # Random noise (±2% of range)
        noise_component = random.uniform(-0.02, 0.02) * (max_val - min_val)
        
        # Drift (çok hafif uzun-vadeli trend)
        drift = 0.001 * (elapsed_time % 3600)  # Her saat içinde küçük drift
        
        value = center + sine_component + noise_component + drift
        
        # Range'de kalmasını garantile
        value = max(min_val, min(max_val, value))
        
        return round(value, 2)


class OPCUAServer:
    """Production-level OPC-UA Server Implementation"""
    
    def __init__(self):
        self.server = None
        self.equipments: List[VirtualEquipment] = []
        self.start_time = None
        self.config = config.get('opc_ua_server', {})
        
    async def setup_equipment_nodes(self):
        """OPC-UA node tree oluştur"""
        logger.info("Setting up OPC-UA node tree...")
        
        # Root namespace
        namespace_idx = self.config.get('namespace_idx', 2)
        namespace_uri = self.config.get('namespace_uri', 'http://opcfoundation.org/SCADA/Demo')
        
        # Namespace register
        idx = await self.server.register_namespace(namespace_uri)
        logger.debug(f"Namespace registered: idx={idx}, uri={namespace_uri}")
        
        # Equipment nodes
        equipment_configs = self.config.get('equipment', [])
        
        for eq_config in equipment_configs:
            equipment_id = eq_config.get('id')
            name = eq_config.get('name')
            location = eq_config.get('location')
            tags = eq_config.get('tags', [])
            
            # Virtual equipment object oluştur
            equipment = VirtualEquipment(equipment_id, name, location, tags)
            
            # Equipment folder node
            eq_folder = await self.server.nodes.objects.add_folder(
                idx, equipment_id
            )
            logger.info(f"Equipment folder created: {name} ({equipment_id})")
            
            # Metadata node
            metadata_var = await eq_folder.add_variable(
                idx, "Metadata",
                {
                    "name": name,
                    "location": location,
                    "protocol": "OPC-UA"
                }
            )
            await metadata_var.set_writable(False)
            
            # Tag variables
            for tag in tags:
                tag_name = tag['name']
                tag_unit = tag.get('unit', '')
                
                # Tag node oluştur
                tag_var = await eq_folder.add_variable(
                    idx, tag_name, 0.0
                )
                
                # Attributes set et
                tag_var.set_writable(False)
                await tag_var.set_data_type(ua.DataType.Float)
                
                # Description
                dv = tag_var.get_attribute(ua.AttributeIds.Description)
                dv.Value.Value = ua.LocalizedText(f"{tag_name} ({tag_unit})")
                await tag_var.set_attribute(ua.AttributeIds.Description, dv)
                
                # Unit (DisplayString olarak)
                equipment.node_dict[tag_name] = tag_var
            
            self.equipments.append(equipment)
            logger.debug(f"Added {len(tags)} tags for {equipment_id}")
    
    async def run_value_update_loop(self):
        """Değerleri periyodik olarak güncelle"""
        logger.info("Starting value update loop...")
        
        while True:
            try:
                elapsed_time = (datetime.now() - self.start_time).total_seconds()
                
                for equipment in self.equipments:
                    for tag in equipment.tags:
                        tag_name = tag['name']
                        
                        # Yeni değer hesapla
                        new_value = equipment.get_tag_value(tag_name, elapsed_time)
                        
                        # OPC-UA node'a yazma
                        if tag_name in equipment.node_dict:
                            node = equipment.node_dict[tag_name]
                            await node.write_value(new_value)
                
                # Her 1 saniye güncelle (publishing_interval_ms = 1000)
                await asyncio.sleep(1.0)
                
            except Exception as e:
                logger.error(f"Error in value update loop: {e}", exc_info=True)
                await asyncio.sleep(1.0)
    
    async def start(self):
        """OPC-UA server başlat"""
        try:
            # Server oluştur
            self.server = Server()
            endpoint = self.config.get('endpoint', 'opc.tcp://0.0.0.0:4840/')
            await self.server.init()
            self.server.set_endpoint(endpoint)
            
            logger.info(f"OPC-UA Server initialized at {endpoint}")
            
            # Nodes setup
            await self.setup_equipment_nodes()
            
            # Server başlat
            await self.server.start()
            logger.info("✓ OPC-UA Server started successfully")
            
            # Start time kaydı
            self.start_time = datetime.now()
            
            # Value update loop'unu başlat
            await self.run_value_update_loop()
            
        except Exception as e:
            logger.error(f"Failed to start OPC-UA server: {e}", exc_info=True)
            raise
        finally:
            if self.server:
                await self.server.stop()
                logger.info("OPC-UA Server stopped")
    
    async def stop(self):
        """OPC-UA server durdur"""
        if self.server:
            await self.server.stop()
            logger.info("✓ OPC-UA Server stopped")


async def main():
    """Main entry point"""
    logger.info("=" * 80)
    logger.info("LAYER 1a: OPC-UA Server (Virtual SCADA Equipment)")
    logger.info("=" * 80)
    
    server = OPCUAServer()
    
    try:
        await server.start()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
        await server.stop()
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    # asyncua Windows'ta ProactorEventLoop gerekebiliyor
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    asyncio.run(main())
