"""
LAYER 8: Grafana Datasource Provisioning
=========================================

Purpose:
  Automatically configure Grafana datasources (TimescaleDB, Prometheus, etc.)
  via provisioning files. No manual UI configuration needed.

Grafana Provisioning:
  /etc/grafana/provisioning/datasources/ → Datasources loaded automatically
  /etc/grafana/provisioning/dashboards/  → Dashboards loaded automatically

Author: SCADA Team
Date: May 8, 2026
"""

import json
import logging
from typing import Dict, List, Any
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# DATASOURCE PROVISIONER
# ============================================================================

class DatasourceProvisioner:
    """Generate Grafana datasource provisioning files"""
    
    def __init__(self, output_dir: str = "./grafana/provisioning/datasources"):
        self.output_dir = output_dir
        Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    # ========================================================================
    # TIMESCALEDB DATASOURCE
    # ========================================================================
    
    def create_timescaledb_datasource(
        self,
        name: str = "TimescaleDB",
        host: str = "localhost",
        port: int = 5432,
        database: str = "scada_db",
        user: str = "postgres",
        password: str = "postgres",
        ssl_mode: str = "disable"
    ) -> Dict[str, Any]:
        """
        Create TimescaleDB datasource configuration.
        
        Args:
            name: Datasource name in Grafana
            host: Database host
            port: Database port
            database: Database name
            user: Database user
            password: Database password
            ssl_mode: SSL mode (disable, require, verify-ca, verify-full)
            
        Returns:
            Datasource configuration dict
        """
        return {
            "apiVersion": 1,
            "datasources": [
                {
                    "name": name,
                    "type": "postgres",
                    "uid": "timescaledb",
                    "access": "proxy",
                    "url": f"postgresql://{host}:{port}/{database}",
                    "isDefault": True,
                    "editable": True,
                    "jsonData": {
                        "tlsMode": ssl_mode,
                        "sslMode": ssl_mode,
                        "tlsAuth": False,
                        "tlsAuthWithCACert": False,
                        "postgresVersion": 12,
                        "customMetricsNamePrefix": "",
                        "timescaledb": True
                    },
                    "secureJsonData": {
                        "password": password
                    },
                    "database": database,
                    "user": user
                }
            ]
        }
    
    # ========================================================================
    # PROMETHEUS DATASOURCE
    # ========================================================================
    
    def create_prometheus_datasource(
        self,
        name: str = "Prometheus",
        url: str = "http://localhost:9090"
    ) -> Dict[str, Any]:
        """
        Create Prometheus datasource configuration.
        
        Args:
            name: Datasource name
            url: Prometheus URL
            
        Returns:
            Datasource configuration dict
        """
        return {
            "apiVersion": 1,
            "datasources": [
                {
                    "name": name,
                    "type": "prometheus",
                    "uid": "prometheus",
                    "access": "proxy",
                    "url": url,
                    "isDefault": False,
                    "editable": True,
                    "jsonData": {
                        "timeInterval": "30s",
                        "queryTimeout": "30s"
                    }
                }
            ]
        }
    
    # ========================================================================
    # ELASTICSEARCH DATASOURCE (optional)
    # ========================================================================
    
    def create_elasticsearch_datasource(
        self,
        name: str = "Elasticsearch",
        url: str = "http://localhost:9200",
        index: str = "scada-*"
    ) -> Dict[str, Any]:
        """
        Create Elasticsearch datasource configuration.
        
        Args:
            name: Datasource name
            url: Elasticsearch URL
            index: Index pattern
            
        Returns:
            Datasource configuration dict
        """
        return {
            "apiVersion": 1,
            "datasources": [
                {
                    "name": name,
                    "type": "elasticsearch",
                    "uid": "elasticsearch",
                    "access": "proxy",
                    "url": url,
                    "isDefault": False,
                    "editable": True,
                    "jsonData": {
                        "esVersion": "7.0.0",
                        "maxConcurrentShardRequests": 256,
                        "logMessageField": "message",
                        "timeField": "@timestamp",
                        "indexPattern": index
                    }
                }
            ]
        }
    
    # ========================================================================
    # EXPORT PROVISIONING FILES
    # ========================================================================
    
    def save_datasource_config(
        self,
        filename: str,
        config: Dict[str, Any]
    ) -> None:
        """
        Save datasource configuration to YAML file.
        
        Args:
            filename: Output filename (without path)
            config: Datasource configuration dict
        """
        try:
            # Grafana uses YAML for provisioning files
            # We'll use JSON but Grafana accepts both
            filepath = Path(self.output_dir) / filename
            
            with open(filepath, 'w') as f:
                json.dump(config, f, indent=2)
            
            logger.info(f"✅ Saved: {filepath}")
        
        except Exception as e:
            logger.error(f"❌ Error saving config: {e}")
    
    def create_provisioning_files(
        self,
        timescaledb_config: Dict = None,
        prometheus_config: Dict = None,
        elasticsearch_config: Dict = None
    ) -> None:
        """
        Create all provisioning files.
        
        Args:
            timescaledb_config: TimescaleDB config (or use defaults)
            prometheus_config: Prometheus config (or use defaults)
            elasticsearch_config: Elasticsearch config (optional)
        """
        # TimescaleDB
        if timescaledb_config is None:
            timescaledb_config = self.create_timescaledb_datasource()
        self.save_datasource_config("timescaledb.json", timescaledb_config)
        
        # Prometheus
        if prometheus_config is None:
            prometheus_config = self.create_prometheus_datasource()
        self.save_datasource_config("prometheus.json", prometheus_config)
        
        # Elasticsearch (optional)
        if elasticsearch_config is not None:
            self.save_datasource_config("elasticsearch.json", elasticsearch_config)


# ============================================================================
# DASHBOARD PROVISIONING
# ============================================================================

def create_dashboard_provisioning_config(
    dashboards_dir: str = "/etc/grafana/provisioning/dashboards"
) -> Dict[str, Any]:
    """
    Create dashboard provisioning configuration.
    
    This file tells Grafana where to find dashboard JSON files.
    
    Args:
        dashboards_dir: Path to dashboards directory
        
    Returns:
        Dashboard provisioning config
    """
    return {
        "apiVersion": 1,
        "providers": [
            {
                "name": "SCADA Dashboards",
                "type": "file",
                "uid": "scada-dashboards",
                "allowUiUpdates": True,
                "options": {
                    "path": dashboards_dir,
                    "folderId": 0
                }
            }
        ]
    }


# ============================================================================
# DOCKER COMPOSE INTEGRATION
# ============================================================================

def create_grafana_docker_compose_section() -> Dict[str, Any]:
    """
    Create Grafana service section for docker-compose.yml
    
    Returns:
        Docker service configuration
    """
    return {
        "grafana": {
            "image": "grafana/grafana:latest",
            "container_name": "scada_grafana",
            "ports": ["3000:3000"],
            "environment": {
                "GF_SECURITY_ADMIN_USER": "admin",
                "GF_SECURITY_ADMIN_PASSWORD": "admin",
                "GF_INSTALL_PLUGINS": "grafana-clock-panel,grafana-simple-json-datasource",
                "GF_SECURITY_ALLOW_EMBED_INITIATION": "true"
            },
            "volumes": [
                "grafana_data:/var/lib/grafana",
                "./grafana/provisioning/datasources:/etc/grafana/provisioning/datasources",
                "./grafana/provisioning/dashboards:/etc/grafana/provisioning/dashboards"
            ],
            "depends_on": ["timescaledb", "prometheus"],
            "networks": ["scada_network"],
            "healthcheck": {
                "test": ["CMD", "curl", "-f", "http://localhost:3000/api/health"],
                "interval": "10s",
                "timeout": "5s",
                "retries": 5
            }
        }
    }


# ============================================================================
# ALERT NOTIFICATION CHANNELS
# ============================================================================

class NotificationChannelProvisioner:
    """Create notification channels for alerts"""
    
    def __init__(self, output_dir: str = "./grafana/provisioning/notifiers"):
        self.output_dir = output_dir
        Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    def create_email_notifier(
        self,
        name: str = "SCADA Email",
        addresses: List[str] = None
    ) -> Dict[str, Any]:
        """Create email notification channel"""
        return {
            "apiVersion": 1,
            "notifiers": [
                {
                    "name": name,
                    "type": "email",
                    "uid": "scada-email",
                    "isDefault": True,
                    "settings": {
                        "addresses": ";".join(addresses or ["admin@example.com"])
                    }
                }
            ]
        }
    
    def create_slack_notifier(
        self,
        name: str = "SCADA Slack",
        webhook_url: str = "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
    ) -> Dict[str, Any]:
        """Create Slack notification channel"""
        return {
            "apiVersion": 1,
            "notifiers": [
                {
                    "name": name,
                    "type": "slack",
                    "uid": "scada-slack",
                    "isDefault": False,
                    "settings": {
                        "url": webhook_url,
                        "channel": "#scada-alerts",
                        "username": "SCADA Bot"
                    }
                }
            ]
        }
    
    def create_pagerduty_notifier(
        self,
        name: str = "SCADA PagerDuty",
        service_key: str = "YOUR_SERVICE_KEY"
    ) -> Dict[str, Any]:
        """Create PagerDuty notification channel"""
        return {
            "apiVersion": 1,
            "notifiers": [
                {
                    "name": name,
                    "type": "pagerduty",
                    "uid": "scada-pagerduty",
                    "isDefault": False,
                    "settings": {
                        "integrationKey": service_key
                    }
                }
            ]
        }


# ============================================================================
# MAIN / TEST
# ============================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    
    logger.info("\n" + "="*70)
    logger.info("🔧 GRAFANA PROVISIONING SETUP")
    logger.info("="*70 + "\n")
    
    # Create datasource provisioner
    provisioner = DatasourceProvisioner()
    
    # Create provisioning files
    logger.info("📋 Creating datasource provisioning files...")
    provisioner.create_provisioning_files()
    
    # Create dashboard provisioning config
    logger.info("📊 Creating dashboard provisioning config...")
    dashboard_config = create_dashboard_provisioning_config()
    with open("./grafana/provisioning/dashboards/dashboards.yaml", 'w') as f:
        json.dump(dashboard_config, f, indent=2)
    
    # Create notification channels
    logger.info("📨 Creating notification channels...")
    notif_provisioner = NotificationChannelProvisioner()
    email_notif = notif_provisioner.create_email_notifier(
        addresses=["ops@example.com"]
    )
    with open("./grafana/provisioning/notifiers/email.json", 'w') as f:
        json.dump(email_notif, f, indent=2)
    
    logger.info("\n" + "="*70)
    logger.info("✅ GRAFANA PROVISIONING COMPLETE!")
    logger.info("="*70)
    logger.info("\nNext steps:")
    logger.info("1. Copy provisioning files to /etc/grafana/provisioning/")
    logger.info("2. Restart Grafana: docker restart scada_grafana")
    logger.info("3. Access Grafana: http://localhost:3000")
    logger.info("4. Default login: admin / admin\n")
