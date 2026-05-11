"""
Layer 4: MQTT Broker Configuration Helper
Docker container'daki Mosquitto'yu configure etmek için utilities
"""

import logging
from typing import Dict, List, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MQTTTopicManager:
    """MQTT topic structure and validation"""
    
    def __init__(self):
        self.prefix = "plant/"
        self.separator = "/"
    
    def build_topic(self, equipment_id: str, tag: str) -> str:
        """
        Build MQTT topic from equipment_id and tag
        
        Example:
            equipment_id: "pump_1"
            tag: "temperature"
            → "plant/pump_1/temperature"
        
        Args:
            equipment_id: Equipment identifier
            tag: Tag/sensor name
        
        Returns:
            Full MQTT topic path
        """
        return f"{self.prefix}{equipment_id}/{tag}"
    
    def parse_topic(self, topic: str) -> Optional[Dict[str, str]]:
        """
        Parse MQTT topic to extract equipment_id and tag
        
        Example:
            "plant/pump_1/temperature" → {"equipment_id": "pump_1", "tag": "temperature"}
        
        Args:
            topic: MQTT topic
        
        Returns:
            Dict with equipment_id and tag, or None if invalid
        """
        if not topic.startswith(self.prefix):
            return None
        
        parts = topic[len(self.prefix):].split(self.separator)
        
        if len(parts) != 2:
            return None
        
        return {
            'equipment_id': parts[0],
            'tag': parts[1]
        }
    
    def get_wildcard_pattern(self) -> str:
        """
        Get wildcard pattern for subscribing to all topics
        
        Returns: "plant/#"
        """
        return f"{self.prefix}#"
    
    def get_equipment_pattern(self, equipment_id: str) -> str:
        """
        Get wildcard pattern for specific equipment
        
        Example: equipment_id="pump_1" → "plant/pump_1/#"
        """
        return f"{self.prefix}{equipment_id}/#"


class MQTTMessageFormatter:
    """Format messages for MQTT transport"""
    
    @staticmethod
    def format_sensor_reading(reading_dict: Dict) -> str:
        """
        Format sensor reading for MQTT
        
        Args:
            reading_dict: SensorReading.to_dict()
        
        Returns:
            JSON string ready for MQTT publish
        """
        import json
        return json.dumps(reading_dict)
    
    @staticmethod
    def parse_sensor_reading(json_str: str) -> Optional[Dict]:
        """
        Parse sensor reading from MQTT message
        
        Args:
            json_str: JSON string from MQTT message
        
        Returns:
            Dict or None if parse error
        """
        import json
        try:
            return json.loads(json_str)
        except Exception as e:
            logger.warning(f"Error parsing MQTT message: {e}")
            return None


class MQTTQoSManager:
    """QoS level management"""
    
    # QoS levels
    AT_MOST_ONCE = 0    # Fire and forget
    AT_LEAST_ONCE = 1   # Broker must deliver (default)
    EXACTLY_ONCE = 2    # Broker must deliver exactly once
    
    @staticmethod
    def get_qos_for_sensor_data() -> int:
        """
        QoS for sensor data (default: AT_LEAST_ONCE)
        
        Reasoning:
        - Not critical if one reading is lost
        - But should not duplicate data
        - Default: QoS 1
        """
        return MQTTQoSManager.AT_LEAST_ONCE
    
    @staticmethod
    def get_qos_for_alerts() -> int:
        """
        QoS for alarms/alerts (default: EXACTLY_ONCE)
        
        Reasoning:
        - Critical that alerts are delivered
        - Must not be duplicated (operator confusion)
        - Default: QoS 2
        """
        return MQTTQoSManager.EXACTLY_ONCE
    
    @staticmethod
    def get_qos_for_config() -> int:
        """
        QoS for configuration changes (default: EXACTLY_ONCE)
        """
        return MQTTQoSManager.EXACTLY_ONCE


class MQTTConnectionInfo:
    """MQTT connection parameters"""
    
    def __init__(self, host: str = "localhost", port: int = 1883):
        self.host = host
        self.port = port
        self.broker_url = f"mqtt://{host}:{port}"
    
    def get_connection_string(self) -> str:
        """Get connection string for clients"""
        return self.broker_url
    
    def __repr__(self):
        return f"MQTT({self.host}:{self.port})"


if __name__ == "__main__":
    # Test topic manager
    logger.info("Testing MQTT Topic Manager...")
    
    manager = MQTTTopicManager()
    
    # Build topic
    topic = manager.build_topic("pump_1", "temperature")
    logger.info(f"Built topic: {topic}")
    assert topic == "plant/pump_1/temperature"
    
    # Parse topic
    parsed = manager.parse_topic(topic)
    logger.info(f"Parsed topic: {parsed}")
    assert parsed == {"equipment_id": "pump_1", "tag": "temperature"}
    
    # Wildcard
    wildcard = manager.get_wildcard_pattern()
    logger.info(f"Wildcard: {wildcard}")
    assert wildcard == "plant/#"
    
    # QoS
    logger.info(f"Sensor data QoS: {MQTTQoSManager.get_qos_for_sensor_data()}")
    logger.info(f"Alert QoS: {MQTTQoSManager.get_qos_for_alerts()}")
    
    # Connection
    conn = MQTTConnectionInfo()
    logger.info(f"Connection: {conn}")
    
    logger.info("✓ All tests passed!")
