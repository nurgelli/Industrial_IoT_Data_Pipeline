"""
Layer 2: OPC-UA Client
OPC-UA Server'dan veri subscription ile okuma
- Asynchronous subscription handler
- Reconnect logic with exponential backoff
- Logging ve error handling
"""

import asyncio
import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Callable, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    from asyncua import Client, ua
    from asyncua.common import ua
except ImportError:
    logger.error("asyncua yüklü değil: pip install asyncua")
    sys.exit(1)


class OPCUAClientSubscriptionHandler:
    """OPC-UA subscription handler — datachange events"""
    
    def __init__(self, on_data_change: Callable = None):
        self.on_data_change = on_data_change
        self.last_values = {}
        self.change_count = 0
    
    def datachange_notification(self, node, val, data):
        """Called when subscribed variable changes"""
        try:
            self.change_count += 1
            node_name = node.nodeid.to_string()
            
            logger.debug(f"DataChange [{self.change_count}]: {node_name} = {val}")
            
            # Store value
            self.last_values[node_name] = {
                'value': val,
                'timestamp': datetime.now(),
                'data': data
            }
            
            # Callback trigger
            if self.on_data_change:
                self.on_data_change(node_name, val, data)
        
        except Exception as e:
            logger.error(f"Error in datachange_notification: {e}", exc_info=True)
    
    def event_notification(self, event):
        """Called when subscribed event occurs"""
        logger.debug(f"Event: {event}")


class OPCUAClient:
    """Production-level OPC-UA Client with subscription"""
    
    def __init__(self, endpoint: str = None, on_data_change: Callable = None):
        self.endpoint = endpoint or config.get('opc_ua_client.server_endpoint', 'opc.tcp://localhost:4840/')
        self.client = Client(url=self.endpoint)
        self.on_data_change = on_data_change
        self.subscription = None
        self.handler = None
        self.subscribed_nodes = {}
        self.connected = False
        
        # Reconnect config
        self.reconnect_config = config.get('opc_ua_client.reconnect', {})
        self.reconnect_enabled = self.reconnect_config.get('enabled', True)
        self.reconnect_delay = self.reconnect_config.get('initial_delay_sec', 1)
        self.max_reconnect_delay = self.reconnect_config.get('max_delay_sec', 60)
        self.exponential_base = self.reconnect_config.get('exponential_base', 2)
        self.max_retries = self.reconnect_config.get('max_retries', 10)
    
    async def connect(self, retry_count: int = 0) -> bool:
        """
        Connect to OPC-UA server with exponential backoff
        
        Args:
            retry_count: Recursive retry counter
        
        Returns:
            True if connected, False if max retries exceeded
        """
        try:
            logger.info(f"Connecting to OPC-UA server: {self.endpoint}")
            await self.client.connect()
            self.connected = True
            logger.info("✓ OPC-UA Client connected")
            self.reconnect_delay = self.reconnect_config.get('initial_delay_sec', 1)
            return True
        
        except Exception as e:
            self.connected = False
            logger.warning(f"Connection failed (attempt {retry_count + 1}/{self.max_retries}): {e}")
            
            if not self.reconnect_enabled or retry_count >= self.max_retries:
                logger.error(f"✗ Failed to connect after {retry_count} retries")
                return False
            
            # Exponential backoff
            wait_time = min(self.reconnect_delay * (self.exponential_base ** retry_count), self.max_reconnect_delay)
            logger.info(f"Retrying in {wait_time:.1f} seconds...")
            await asyncio.sleep(wait_time)
            
            return await self.connect(retry_count + 1)
    
    async def setup_subscriptions(self):
        """Setup subscriptions for all equipment tags"""
        if not self.connected:
            logger.warning("Not connected, skipping subscription setup")
            return False
        
        try:
            # Create subscription handler
            self.handler = OPCUAClientSubscriptionHandler(on_data_change=self.on_data_change)
            
            # Subscription config
            sub_config = config.get('opc_ua_client.subscription', {})
            publishing_interval = sub_config.get('publishing_interval_ms', 1000)
            max_notifications = sub_config.get('max_notifications_per_publish', 100)
            lifetime_count = sub_config.get('lifetime_count', 3)
            
            # Create subscription
            self.subscription = await self.client.create_subscription(
                period=publishing_interval,
                handler=self.handler
            )
            
            logger.info(f"✓ Subscription created (period={publishing_interval}ms)")
            
            # Subscribe to all equipment tags
            equipment_list = config.get_equipment_list()
            namespace_idx = 2
            
            for equipment in equipment_list:
                equipment_id = equipment.get('id')
                
                for tag in equipment.get('tags', []):
                    tag_name = tag['name']
                    
                    try:
                        # Build node path
                        eq_node = await self.client.nodes.objects.get_child([f"{namespace_idx}:{equipment_id}"])
                        tag_node = await eq_node.get_child([f"{namespace_idx}:{tag_name}"])
                        
                        # Subscribe
                        await self.subscription.subscribe_data_change(tag_node)
                        
                        self.subscribed_nodes[f"{equipment_id}.{tag_name}"] = tag_node
                        logger.debug(f"Subscribed: {equipment_id}.{tag_name}")
                    
                    except Exception as e:
                        logger.warning(f"Failed to subscribe {equipment_id}.{tag_name}: {e}")
            
            logger.info(f"✓ Subscribed to {len(self.subscribed_nodes)} tags")
            return True
        
        except Exception as e:
            logger.error(f"Error setting up subscriptions: {e}", exc_info=True)
            return False
    
    async def read_node(self, equipment_id: str, tag_name: str) -> Optional[float]:
        """Read single node value (one-time read)"""
        try:
            if not self.connected:
                logger.warning("Not connected, cannot read")
                return None
            
            namespace_idx = 2
            eq_node = await self.client.nodes.objects.get_child([f"{namespace_idx}:{equipment_id}"])
            tag_node = await eq_node.get_child([f"{namespace_idx}:{tag_name}"])
            value = await tag_node.read_value()
            
            return value
        
        except Exception as e:
            logger.warning(f"Error reading {equipment_id}.{tag_name}: {e}")
            return None
    
    async def disconnect(self):
        """Disconnect from OPC-UA server"""
        try:
            if self.subscription:
                await self.subscription.delete()
            
            if self.client:
                await self.client.disconnect()
            
            self.connected = False
            logger.info("✓ OPC-UA Client disconnected")
        
        except Exception as e:
            logger.error(f"Error disconnecting: {e}", exc_info=True)
    
    async def get_all_values(self) -> Dict[str, float]:
        """Get current values from all subscribed tags"""
        values = {}
        
        for node_key in self.subscribed_nodes:
            try:
                equipment_id, tag_name = node_key.split('.')
                value = await self.read_node(equipment_id, tag_name)
                if value is not None:
                    values[node_key] = value
            except Exception as e:
                logger.warning(f"Error getting value for {node_key}: {e}")
        
        return values


async def main_demo():
    """Demo: OPC-UA client usage"""
    
    async def on_data_change(node_name: str, value, data):
        """Callback when data changes"""
        logger.info(f"📊 Data changed: {node_name} = {value}")
    
    # Create client
    client = OPCUAClient(on_data_change=on_data_change)
    
    try:
        # Connect
        if not await client.connect():
            logger.error("Failed to connect")
            return
        
        # Setup subscriptions
        if not await client.setup_subscriptions():
            logger.error("Failed to setup subscriptions")
            return
        
        # Run for 30 seconds
        logger.info("\n📡 Listening for data changes (30 seconds)...")
        await asyncio.sleep(30)
        
        # Read all values
        logger.info("\n📖 Current values:")
        all_values = await client.get_all_values()
        for key, value in all_values.items():
            logger.info(f"  {key}: {value}")
    
    finally:
        await client.disconnect()


if __name__ == "__main__":
    logger.info("="*80)
    logger.info("LAYER 2: OPC-UA Client (Subscription Handler)")
    logger.info("="*80)
    
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    asyncio.run(main_demo())
