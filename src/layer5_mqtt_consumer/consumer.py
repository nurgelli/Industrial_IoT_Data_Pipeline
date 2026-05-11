"""
Layer 5: MQTT Consumer
MQTT Broker'dan mesajları oku, batch buffer'a topla
Batch dolu olunca veya timeout olunca downstream'e gönder
"""

import asyncio
import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Callable, Optional, List, Dict
import json

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils import config
from layer3_python_bridge.data_model import SensorReading, BatchedReadings
from layer4_mqtt_broker.mosquitto_helper import MQTTTopicManager, MQTTMessageFormatter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    from paho.mqtt import client as mqtt_client
except ImportError:
    logger.error("paho-mqtt yüklü değil: pip install paho-mqtt")
    sys.exit(1)


class MQTTConsumer:
    """
    MQTT Consumer — mesajları topla ve batch olarak işle
    
    Flow:
    1. MQTT broker'a bağlan
    2. Wildcard pattern (plant/#) ile subscribe
    3. Her mesaj geldiğinde:
       - JSON parse et
       - SensorReading object'ine dönüştür
       - Batch buffer'a ekle
    4. Buffer dolunca veya timeout olunca:
       - Batch'i flush et
       - on_batch_complete callback'i çağır
    """
    
    def __init__(self, on_batch_complete: Callable = None):
        self.client = None
        self.on_batch_complete = on_batch_complete
        
        # MQTT config
        mqtt_config = config.get('mqtt_broker', {})
        self.broker_host = mqtt_config.get('host', 'localhost')
        self.broker_port = mqtt_config.get('port', 1883)
        
        # Consumer config
        consumer_config = config.get('mqtt_consumer', {})
        self.client_id = consumer_config.get('client_id', 'scada_consumer_1')
        
        # Batch config
        self.buffer_size = consumer_config.get('batch', {}).get('buffer_size', 100)
        self.buffer_timeout_sec = consumer_config.get('batch', {}).get('buffer_timeout_sec', 5)
        
        # Current batch
        self.current_batch = BatchedReadings(
            readings=[],
            batch_timestamp=datetime.now(),
            batch_size=0,
            source_types=set()
        )
        self.last_batch_time = datetime.now()
        self.sequence_number = 0
        self.message_count = 0
        
        # Topic manager
        self.topic_manager = MQTTTopicManager()
        self.message_formatter = MQTTMessageFormatter()
        
        # Connected flag
        self.connected = False
        
        # Setup MQTT client
        self._setup_mqtt_client()
    
    def _setup_mqtt_client(self):
        """Setup MQTT client callbacks"""
        self.client = mqtt_client.Client(client_id=self.client_id)
        
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect
        self.client.on_subscribe = self._on_subscribe
    
    def _on_connect(self, client, userdata, flags, rc):
        """Called when client connects to broker"""
        if rc == 0:
            logger.info(f"✓ Connected to MQTT broker ({self.broker_host}:{self.broker_port})")
            self.connected = True
            
            # Subscribe to all topics
            wildcard = self.topic_manager.get_wildcard_pattern()
            client.subscribe(wildcard, qos=1)
            logger.info(f"Subscribed to: {wildcard}")
        else:
            logger.error(f"Connection failed with code {rc}")
            self.connected = False
    
    def _on_disconnect(self, client, userdata, rc):
        """Called when client disconnects from broker"""
        if rc != 0:
            logger.warning(f"Unexpected disconnection (code {rc})")
        else:
            logger.info("Disconnected from broker")
        self.connected = False
    
    def _on_subscribe(self, client, userdata, mid, granted_qos):
        """Called when subscription is acknowledged"""
        logger.debug(f"Subscription acknowledged (QoS: {granted_qos})")
    
    def _on_message(self, client, userdata, msg):
        """Called when message is received"""
        try:
            self.message_count += 1
            
            # Parse topic
            topic = msg.topic
            topic_info = self.topic_manager.parse_topic(topic)
            
            if not topic_info:
                logger.warning(f"Invalid topic: {topic}")
                return
            
            # Parse payload
            payload_str = msg.payload.decode('utf-8')
            payload = self.message_formatter.parse_sensor_reading(payload_str)
            
            if not payload:
                logger.warning(f"Failed to parse payload from {topic}")
                return
            
            # Convert to SensorReading
            reading = self._payload_to_reading(payload, topic_info)
            
            if not reading:
                return
            
            # Add to batch
            self._add_to_batch(reading)
            
            logger.debug(f"Message #{self.message_count}: {topic} = {reading.value} {reading.unit}")
        
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
    
    def _payload_to_reading(self, payload: Dict, topic_info: Dict) -> Optional[SensorReading]:
        """Convert MQTT payload to SensorReading"""
        try:
            # If payload already has all fields (from bridge)
            if 'value' in payload and 'unit' in payload:
                reading = SensorReading(
                    timestamp=datetime.fromisoformat(payload['timestamp']) if 'timestamp' in payload else datetime.now(),
                    equipment_id=payload.get('equipment_id', topic_info['equipment_id']),
                    tag=payload.get('tag', topic_info['tag']),
                    value=payload['value'],
                    unit=payload['unit'],
                    source=payload.get('source', 'MQTT'),
                    quality=payload.get('quality', 0),
                    sequence_number=payload.get('sequence_number'),
                    raw_value=payload.get('raw_value'),
                    metadata=payload.get('metadata')
                )
                return reading
            else:
                logger.warning(f"Incomplete payload: {payload}")
                return None
        
        except Exception as e:
            logger.warning(f"Error converting payload to reading: {e}")
            return None
    
    def _add_to_batch(self, reading: SensorReading):
        """Add reading to batch, flush if needed"""
        self.sequence_number += 1
        reading.sequence_number = self.sequence_number
        
        self.current_batch.add_reading(reading)
        
        # Check if should flush
        should_flush = False
        
        # 1. Buffer size reached
        if self.current_batch.batch_size >= self.buffer_size:
            logger.debug(f"Buffer full ({self.buffer_size} readings)")
            should_flush = True
        
        # 2. Timeout reached
        elapsed = (datetime.now() - self.last_batch_time).total_seconds()
        if elapsed >= self.buffer_timeout_sec and self.current_batch.batch_size > 0:
            logger.debug(f"Buffer timeout ({self.buffer_timeout_sec}s, {self.current_batch.batch_size} readings)")
            should_flush = True
        
        if should_flush:
            self._flush_batch()
    
    def _flush_batch(self):
        """Flush batch to downstream (database)"""
        if self.current_batch.batch_size == 0:
            return
        
        logger.info(f"📤 Flushing batch: {self.current_batch.batch_size} readings from MQTT")
        
        # Log batch summary
        logger.info(f"  Sequence: {self.sequence_number - self.current_batch.batch_size + 1} - {self.sequence_number}")
        logger.info(f"  Time range: {self.current_batch.readings[0].timestamp} - {self.current_batch.readings[-1].timestamp}")
        logger.info(f"  Equipment count: {len(set(r.equipment_id for r in self.current_batch.readings))}")
        logger.info(f"  Tag count: {len(set(r.tag for r in self.current_batch.readings))}")
        
        # Callback (for database writing, cleaning, etc.)
        if self.on_batch_complete:
            try:
                self.on_batch_complete(self.current_batch)
            except Exception as e:
                logger.error(f"Error in batch callback: {e}", exc_info=True)
        
        # Reset batch
        self.current_batch = BatchedReadings(
            readings=[],
            batch_timestamp=datetime.now(),
            batch_size=0,
            source_types=set()
        )
        self.last_batch_time = datetime.now()
    
    async def connect(self) -> bool:
        """Connect to MQTT broker"""
        try:
            logger.info(f"Connecting to MQTT broker: {self.broker_host}:{self.broker_port}")
            self.client.connect(self.broker_host, self.broker_port, keepalive=60)
            
            # Start network loop
            self.client.loop_start()
            
            # Wait for connection
            await asyncio.sleep(2)
            
            if not self.connected:
                logger.error("Failed to connect to MQTT broker")
                return False
            
            return True
        
        except Exception as e:
            logger.error(f"Error connecting to MQTT: {e}", exc_info=True)
            return False
    
    async def flush_on_timeout(self):
        """Periodically flush batch on timeout"""
        while True:
            try:
                await asyncio.sleep(1)
                
                elapsed = (datetime.now() - self.last_batch_time).total_seconds()
                if elapsed >= self.buffer_timeout_sec and self.current_batch.batch_size > 0:
                    self._flush_batch()
            
            except Exception as e:
                logger.error(f"Error in flush task: {e}", exc_info=True)
    
    async def disconnect(self):
        """Disconnect from MQTT broker"""
        try:
            # Flush remaining batch
            if self.current_batch.batch_size > 0:
                logger.info("Flushing remaining batch...")
                self._flush_batch()
            
            self.client.loop_stop()
            self.client.disconnect()
            logger.info("✓ MQTT Consumer disconnected")
        
        except Exception as e:
            logger.error(f"Error disconnecting: {e}", exc_info=True)


async def default_batch_handler(batch: BatchedReadings):
    """Default batch handler (just log)"""
    logger.info(f"Batch received: {batch.batch_size} readings")
    for reading in batch.readings[:3]:  # Log first 3
        logger.info(f"  - {reading.equipment_id}.{reading.tag}: {reading.value} {reading.unit} (source: {reading.source})")
    if batch.batch_size > 3:
        logger.info(f"  ... and {batch.batch_size - 3} more")


async def main():
    """Main entry point"""
    logger.info("="*80)
    logger.info("LAYER 5: MQTT Consumer (Batch Ingestion)")
    logger.info("="*80)
    
    consumer = MQTTConsumer(on_batch_complete=default_batch_handler)
    
    try:
        # Connect
        if not await consumer.connect():
            logger.error("Failed to connect")
            return
        
        logger.info("\n📡 Listening for MQTT messages...")
        logger.info("Waiting for batches...\n")
        
        # Start timeout flush task
        flush_task = asyncio.create_task(consumer.flush_on_timeout())
        
        # Run indefinitely
        await flush_task
    
    except KeyboardInterrupt:
        logger.info("Received interrupt, stopping...")
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
    finally:
        await consumer.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
