"""
Config Loader — YAML configuration file reading utility
Centralized configuration management for all microservices
"""

import yaml
import json
import os
from pathlib import Path
from typing import Dict, Any, Optional

class ConfigLoader:
    """Load and manage configuration from YAML files"""
    
    _instance = None
    _config = {}
    
    def __new__(cls):
        """Singleton pattern — one config instance for entire app"""
        if cls._instance is None:
            cls._instance = super(ConfigLoader, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize config loader"""
        self.config_dir = Path(__file__).parent.parent / "config"
        self.settings_file = self.config_dir / "settings.yaml"
        
    def load(self) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        if not self._config:
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    self._config = yaml.safe_load(f)
                print(f"✓ Config loaded from: {self.settings_file}")
            except FileNotFoundError:
                print(f"✗ Config file not found: {self.settings_file}")
                raise
            except yaml.YAMLError as e:
                print(f"✗ YAML parse error: {e}")
                raise
        
        return self._config
    
    def get(self, path: str, default: Any = None) -> Any:
        """
        Get config value by dot-notation path
        
        Example:
            config.get("opc_ua.endpoint")
            config.get("equipment.0.name")
        """
        if not self._config:
            self.load()
        
        keys = path.split(".")
        value = self._config
        
        for key in keys:
            # Array index desteği: "equipment.0.name"
            if key.isdigit():
                value = value[int(key)]
            else:
                if isinstance(value, dict):
                    value = value.get(key)
                else:
                    return default
            
            if value is None:
                return default
        
        return value
    
    def get_opc_ua(self) -> Dict[str, Any]:
        """Get OPC-UA configuration"""
        return self.get("opc_ua_server", {})
    
    def get_modbus(self) -> Dict[str, Any]:
        """Get Modbus configuration"""
        return self.get("modbus_server", {})
    
    def get_mqtt(self) -> Dict[str, Any]:
        """Get MQTT configuration"""
        return self.get("mqtt_broker", {})
    
    def get_database(self) -> Dict[str, Any]:
        """Get database configuration"""
        return self.get("timescaledb", {})
    
    def get_logging(self) -> Dict[str, Any]:
        """Get logging configuration"""
        return self.get("logging", {})
    
    def get_equipment_list(self) -> list:
        """Get list of all equipment configurations"""
        return self.get("opc_ua_server.equipment", [])
    
    def get_equipment_by_id(self, equipment_id: str) -> Optional[Dict]:
        """Get equipment configuration by ID"""
        equipment_list = self.get_equipment_list()
        for eq in equipment_list:
            if eq.get("id") == equipment_id:
                return eq
        return None
    
    def print_config(self, section: str = None):
        """Pretty-print configuration (debug purpose)"""
        if not self._config:
            self.load()
        
        if section:
            data = self.get(section, {})
        else:
            data = self._config
        
        print(json.dumps(data, indent=2, ensure_ascii=False))
    
    def reload(self):
        """Reload configuration from file"""
        self._config = {}
        return self.load()


# Singleton instance
config = ConfigLoader()
config.load()


if __name__ == "__main__":
    # Test configuration loader
    config = ConfigLoader()
    config.load()
    
    print("\n=== OPC-UA Config ===")
    print(f"Endpoint: {config.get('opc_ua_server.endpoint')}")
    
    print("\n=== Modbus Config ===")
    print(f"Host: {config.get('modbus_server.host')}")
    print(f"Port: {config.get('modbus_server.port')}")
    
    print("\n=== MQTT Config ===")
    print(f"Broker: {config.get('mqtt_broker.host')}:{config.get('mqtt_broker.port')}")
    
    print("\n=== Database Config ===")
    db_config = config.get_database()
    print(f"Host: {db_config['connection']['host']}")
    print(f"Database: {db_config['connection']['dbname']}")
    
    print("\n=== Equipment List ===")
    for eq in config.get_equipment_list():
        print(f"  - {eq['id']}: {eq['name']}")
    
    print("\n✓ Configuration loader test passed!")
