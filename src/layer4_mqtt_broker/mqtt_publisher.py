"""
Bridge Extension: MQTT Publisher
Python Bridge'den MQTT Broker'a publish et
"""

import logging
from typing import Optional
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    from paho.mqtt import client as mqtt_client
except ImportError:
    logger.error("paho-mqtt yüklü değil: pip install paho-mqtt")
    mqtt_client = None


class MQTTPublisher:
    """Publish sensor readings to MQTT broker"""
    
    def __init__(self, broker_host: str = "localhost", broker_port: int = 1883):
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.client = None
        self.connected = False
        
        if mqtt_client:
            self.client = mqtt_client.Client(client_id="scada_publisher_1")
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
    
    def _on_connect(self, client, userdata, flags, rc):
        """Called when connected"""
        if rc == 0:
            logger.info(f"✓ MQTT Publisher connected ({self.broker_host}:{self.broker_port})")
            self.connected = True
        else:
            logger.error(f"Connection failed with code {rc}")
            self.connected = False
    
    def _on_disconnect(self, client, userdata, rc):
        """Called when disconnected"""
        if rc != 0:
            logger.warning(f"Unexpected disconnection (code {rc})")
        self.connected = False
    
    def connect(self) -> bool:
        """Connect to broker"""
        try:
            if not self.client:
                logger.error("MQTT client not available")
                return False
            
            self.client.connect(self.broker_host, self.broker_port, keepalive=60)
            self.client.loop_start()
            
            import time
            time.sleep(1)  # Wait for connection
            
            return self.connected
        
        except Exception as e:
            logger.error(f"Error connecting: {e}")
            return False
    
    def publish_reading(self, reading_dict: dict, topic: str, qos: int = 1) -> bool:
        """
        Publish single reading
        
        Args:
            reading_dict: SensorReading.to_dict()
            topic: MQTT topic (e.g., "plant/pump_1/temperature")
            qos: QoS level (default: 1)
        
        Returns:
            True if published
        """
        try:
            if not self.connected:
                logger.warning("Not connected to MQTT broker")
                return False
            
            payload = json.dumps(reading_dict)
            result = self.client.publish(topic, payload, qos=qos)
            
            if result.rc == mqtt_client.MQTT_ERR_SUCCESS:
                logger.debug(f"Published to {topic}")
                return True
            else:
                logger.warning(f"Publish error: {result.rc}")
                return False
        
        except Exception as e:
            logger.error(f"Error publishing: {e}")
            return False
    
    def publish_batch(self, batch, topic_prefix: str = "plant/", qos: int = 1) -> int:
        """
        Publish entire batch
        
        Args:
            batch: BatchedReadings object
            topic_prefix: MQTT topic prefix
            qos: QoS level
        
        Returns:
            Number of readings published
        """
        published_count = 0
        
        for reading in batch.readings:
            topic = f"{topic_prefix}{reading.equipment_id}/{reading.tag}"
            reading_dict = reading.to_dict()
            
            if self.publish_reading(reading_dict, topic, qos):
                published_count += 1
        
        logger.info(f"Published {published_count}/{batch.batch_size} readings to MQTT")
        return published_count
    
    def disconnect(self):
        """Disconnect from broker"""
        try:
            if self.client:
                self.client.loop_stop()
                self.client.disconnect()
            logger.info("✓ MQTT Publisher disconnected")
        except Exception as e:
            logger.error(f"Error disconnecting: {e}")


if __name__ == "__main__":
    # Test
    from layer3_python_bridge.data_model import SensorReading
    from datetime import datetime
    
    logger.info("Testing MQTT Publisher...")
    
    publisher = MQTTPublisher()
    if publisher.connect():
        # Test reading
        reading = SensorReading.from_opc_ua(
            equipment_id="pump_1",
            tag="temperature",
            value=45.23,
            unit="°C"
        )
        
        topic = f"plant/{reading.equipment_id}/{reading.tag}"
        publisher.publish_reading(reading.to_dict(), topic)
        
        publisher.disconnect()
        logger.info("✓ Test completed")
    else:
        logger.error("Connection failed")
