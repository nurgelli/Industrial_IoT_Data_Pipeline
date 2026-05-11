"""
Test: OPC-UA Client
Layer 1a (OPC-UA Server) ile bağlantı test et
"""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.utils import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    from asyncua import Client
except ImportError:
    logger.error("asyncua yüklü değil: pip install asyncua")
    sys.exit(1)


async def test_opc_client():
    """OPC-UA server'a bağlan ve values oku"""
    
    client = Client(url=config.get('opc_ua_server.endpoint', 'opc.tcp://localhost:4840/'))
    
    try:
        logger.info(f"Connecting to {client.url}...")
        async with client:
            logger.info("✓ Connected to OPC-UA server")
            
            # Root objects node
            root = client.nodes.root
            logger.info(f"Root node: {root}")
            
            # Equipment nodes oku
            equipment_list = config.get_equipment_list()
            
            for equipment in equipment_list:
                equipment_id = equipment.get('id')
                logger.info(f"\n📍 Equipment: {equipment_id}")
                
                try:
                    # Equipment folder node
                    eq_node = await client.nodes.objects.get_child([f"2:{equipment_id}"])
                    
                    # Tag values oku
                    for tag in equipment.get('tags', []):
                        tag_name = tag['name']
                        try:
                            tag_node = await eq_node.get_child([f"2:{tag_name}"])
                            value = await tag_node.read_value()
                            unit = tag.get('unit', '')
                            logger.info(f"  • {tag_name}: {value} {unit}")
                        except Exception as e:
                            logger.warning(f"  • {tag_name}: Error reading value ({e})")
                
                except Exception as e:
                    logger.warning(f"Equipment node not found: {e}")
            
            # Subscribe test
            logger.info("\n📊 Subscription Test (5 seconds):")
            equipment = equipment_list[0]
            equipment_id = equipment.get('id')
            tag = equipment.get('tags', [])[0]
            tag_name = tag['name']
            
            try:
                eq_node = await client.nodes.objects.get_child([f"2:{equipment_id}"])
                tag_node = await eq_node.get_child([f"2:{tag_name}"])
                
                # Handler
                class SubHandler:
                    def __init__(self):
                        self.count = 0
                    
                    def datachange_notification(self, node, val, data):
                        self.count += 1
                        logger.info(f"  [{self.count}] {tag_name} changed: {val}")
                
                handler = SubHandler()
                sub = await client.create_subscription(100, handler)
                await sub.subscribe_data_change(tag_node)
                
                # 5 saniye dinle
                await asyncio.sleep(5)
                await sub.delete()
                
            except Exception as e:
                logger.error(f"Subscription error: {e}")
    
    except Exception as e:
        logger.error(f"Connection error: {e}")
        return False
    
    logger.info("\n✓ OPC-UA Client test completed!")
    return True


async def main():
    logger.info("="*80)
    logger.info("TEST: OPC-UA Client")
    logger.info("="*80)
    logger.info("\nMake sure OPC-UA server is running:")
    logger.info("  python src/layer1_data_source/opc_ua_server.py\n")
    
    await asyncio.sleep(2)
    success = await test_opc_client()
    
    if not success:
        logger.error("❌ Test failed!")
        sys.exit(1)


if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    asyncio.run(main())
