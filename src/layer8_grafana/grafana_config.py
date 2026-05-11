"""
LAYER 8: Grafana Dashboard Configuration & Management
======================================================

Purpose:
  Create and manage Grafana dashboards programmatically.
  Real-time equipment status, time-series charts, anomaly alerts.

Features:
  - Dashboard creation (Python → JSON → Grafana API)
  - Equipment status panels (gauges, status lights)
  - Time-series charts (temperature, pressure, vibration)
  - Anomaly timeline
  - Health score widgets
  - Alert notification status

Author: SCADA Team
Date: May 8, 2026
"""

import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# GRAFANA DASHBOARD BUILDER
# ============================================================================

class GrafanaDashboard:
    """
    Build Grafana dashboard JSON programmatically.
    
    Grafana expects JSON structure with:
    - Dashboard metadata (title, tags, refresh)
    - Panels (visualizations)
    - Templating (variables)
    - Annotations (events)
    """
    
    def __init__(
        self,
        title: str,
        description: str = "",
        tags: List[str] = None,
        refresh: str = "5s",
        timezone: str = "browser"
    ):
        """
        Initialize dashboard builder.
        
        Args:
            title: Dashboard title
            description: Dashboard description
            tags: Dashboard tags
            refresh: Auto-refresh interval (5s, 10s, 30s, 1m, etc.)
            timezone: Timezone (browser, UTC, etc.)
        """
        self.title = title
        self.description = description
        self.tags = tags or []
        self.refresh = refresh
        self.timezone = timezone
        
        self.panels = []
        self.variables = []
        self.annotations = []
        self.next_panel_id = 1
        self.uid = title.lower().replace(" ", "-")
    
    def add_variable(
        self,
        name: str,
        label: str,
        query: str,
        datasource: str = "TimescaleDB"
    ) -> None:
        """
        Add dashboard variable (for filtering).
        
        Args:
            name: Variable name (used in queries as $name)
            label: Display label
            query: Query to get values
            datasource: Datasource name
        """
        variable = {
            "name": name,
            "label": label,
            "type": "query",
            "datasource": datasource,
            "query": query,
            "multi": False,
            "includeAll": False
        }
        self.variables.append(variable)
    
    def add_equipment_variable(self) -> None:
        """Add equipment selector variable"""
        self.add_variable(
            name="equipment_id",
            label="Equipment",
            query="SELECT DISTINCT equipment_id FROM equipment_metadata ORDER BY equipment_id",
            datasource="TimescaleDB"
        )
    
    def add_time_range_variable(self) -> None:
        """Add time range variable (usually automatic in Grafana)"""
        pass  # Built-in to Grafana UI
    
    # ========================================================================
    # PANEL BUILDERS
    # ========================================================================
    
    def add_gauge_panel(
        self,
        title: str,
        query: str,
        unit: str = "",
        min_value: float = 0,
        max_value: float = 100,
        thresholds: List[float] = None,
        colors: List[str] = None
    ) -> int:
        """
        Add gauge panel (circular indicator).
        
        Args:
            title: Panel title
            query: Datasource query
            unit: Unit (°C, PSI, %, etc.)
            min_value: Gauge minimum
            max_value: Gauge maximum
            thresholds: Threshold values
            colors: Colors for each threshold
            
        Returns:
            Panel ID
        """
        panel_id = self.next_panel_id
        self.next_panel_id += 1
        
        # Default thresholds and colors
        if thresholds is None:
            thresholds = [0, 50, 100]
        if colors is None:
            colors = ["green", "yellow", "red"]
        
        panel = {
            "id": panel_id,
            "type": "gauge",
            "title": title,
            "gridPos": {
                "x": ((panel_id - 1) % 4) * 6,
                "y": ((panel_id - 1) // 4) * 8,
                "w": 6,
                "h": 8
            },
            "targets": [
                {
                    "refId": "A",
                    "query": query
                }
            ],
            "fieldConfig": {
                "defaults": {
                    "unit": unit,
                    "min": min_value,
                    "max": max_value,
                    "thresholds": {
                        "mode": "absolute",
                        "steps": [
                            {"color": colors[i], "value": thresholds[i]}
                            for i in range(len(thresholds))
                        ]
                    }
                }
            },
            "options": {
                "showThresholdLabels": True,
                "showThresholdMarkers": True,
                "orientation": "auto"
            }
        }
        
        self.panels.append(panel)
        return panel_id
    
    def add_timeseries_panel(
        self,
        title: str,
        queries: Dict[str, str],
        unit: str = "",
        yaxis_label: str = ""
    ) -> int:
        """
        Add time-series panel (line chart).
        
        Args:
            title: Panel title
            queries: Dict of {refId: query} (e.g., {"A": "SELECT ...", "B": "SELECT ..."})
            unit: Unit for Y-axis
            yaxis_label: Y-axis label
            
        Returns:
            Panel ID
        """
        panel_id = self.next_panel_id
        self.next_panel_id += 1
        
        targets = [
            {
                "refId": ref_id,
                "query": query
            }
            for ref_id, query in queries.items()
        ]
        
        panel = {
            "id": panel_id,
            "type": "timeseries",
            "title": title,
            "gridPos": {
                "x": 0,
                "y": 100 + (panel_id - 1) * 8,
                "w": 24,
                "h": 8
            },
            "targets": targets,
            "fieldConfig": {
                "defaults": {
                    "unit": unit,
                    "custom": {
                        "lineWidth": 2,
                        "fillOpacity": 10
                    }
                }
            },
            "options": {
                "legend": {
                    "calcs": ["mean", "max", "min"],
                    "displayMode": "list",
                    "placement": "bottom"
                },
                "tooltip": {
                    "mode": "multi",
                    "sort": "none"
                }
            }
        }
        
        self.panels.append(panel)
        return panel_id
    
    def add_stat_panel(
        self,
        title: str,
        query: str,
        unit: str = "",
        color_mode: str = "background",
        graph_mode: str = "area"
    ) -> int:
        """
        Add stat panel (big number with optional graph).
        
        Args:
            title: Panel title
            query: Datasource query
            unit: Unit
            color_mode: "value" or "background"
            graph_mode: "none", "area", or "bar"
            
        Returns:
            Panel ID
        """
        panel_id = self.next_panel_id
        self.next_panel_id += 1
        
        panel = {
            "id": panel_id,
            "type": "stat",
            "title": title,
            "gridPos": {
                "x": ((panel_id - 1) % 6) * 4,
                "y": ((panel_id - 1) // 6) * 4,
                "w": 4,
                "h": 4
            },
            "targets": [
                {
                    "refId": "A",
                    "query": query
                }
            ],
            "fieldConfig": {
                "defaults": {
                    "unit": unit,
                    "color": {
                        "mode": color_mode
                    }
                }
            },
            "options": {
                "graphMode": graph_mode,
                "orientation": "auto",
                "textMode": "auto",
                "colorMode": color_mode
            }
        }
        
        self.panels.append(panel)
        return panel_id
    
    def add_table_panel(
        self,
        title: str,
        query: str
    ) -> int:
        """
        Add table panel (data grid).
        
        Args:
            title: Panel title
            query: Datasource query
            
        Returns:
            Panel ID
        """
        panel_id = self.next_panel_id
        self.next_panel_id += 1
        
        panel = {
            "id": panel_id,
            "type": "table",
            "title": title,
            "gridPos": {
                "x": 0,
                "y": 200 + (panel_id - 1) * 8,
                "w": 24,
                "h": 8
            },
            "targets": [
                {
                    "refId": "A",
                    "query": query
                }
            ],
            "fieldConfig": {
                "defaults": {
                    "custom": {
                        "displayMode": "auto",
                        "align": "auto"
                    }
                }
            },
            "options": {
                "showHeader": True,
                "sortBy": []
            }
        }
        
        self.panels.append(panel)
        return panel_id
    
    def add_alert_status_panel(self) -> int:
        """Add panel showing alert status"""
        query = """
        SELECT
          anomaly_type as "Type",
          COUNT(*) as "Count",
          severity as "Severity"
        FROM alarm_events
        WHERE time > CURRENT_TIMESTAMP - INTERVAL '24 hours'
        GROUP BY anomaly_type, severity
        ORDER BY count DESC
        """
        
        return self.add_table_panel(
            title="Recent Anomalies (24h)",
            query=query
        )
    
    # ========================================================================
    # BUILD DASHBOARD JSON
    # ========================================================================
    
    def build(self) -> Dict[str, Any]:
        """
        Build complete dashboard JSON.
        
        Returns:
            Dashboard JSON structure
        """
        dashboard = {
            "id": None,
            "uid": self.uid,
            "title": self.title,
            "description": self.description,
            "tags": self.tags,
            "timezone": self.timezone,
            "refresh": self.refresh,
            "schemaVersion": 35,
            "version": 0,
            "panels": self.panels,
            "templating": {
                "list": self.variables
            },
            "annotations": {
                "list": self.annotations
            },
            "links": [],
            "time": {
                "from": "now-6h",
                "to": "now"
            }
        }
        
        return dashboard
    
    def to_json(self, pretty: bool = True) -> str:
        """
        Export dashboard as JSON string.
        
        Args:
            pretty: Pretty-print JSON
            
        Returns:
            JSON string
        """
        dashboard = self.build()
        if pretty:
            return json.dumps(dashboard, indent=2)
        return json.dumps(dashboard)
    
    def save_to_file(self, filepath: str) -> None:
        """
        Save dashboard JSON to file.
        
        Args:
            filepath: Output file path
        """
        with open(filepath, 'w') as f:
            f.write(self.to_json(pretty=True))
        logger.info(f"✅ Dashboard saved: {filepath}")


# ============================================================================
# PREDEFINED DASHBOARDS
# ============================================================================

def create_equipment_status_dashboard() -> GrafanaDashboard:
    """
    Create real-time equipment status dashboard.
    
    Panels:
    - Current temperature gauge (pump_1, compressor_1, heater_1)
    - Current pressure gauge (all equipment)
    - Current vibration gauge (pump_1, compressor_1)
    - Recent anomalies table
    """
    dashboard = GrafanaDashboard(
        title="Equipment Status",
        description="Real-time equipment status and key metrics",
        tags=["SCADA", "Equipment", "Realtime"],
        refresh="5s"
    )
    
    # Add equipment selector variable
    dashboard.add_equipment_variable()
    
    # Temperature gauges
    dashboard.add_gauge_panel(
        title="Pump #1 Temperature",
        query="""
            SELECT value FROM sensor_readings
            WHERE equipment_id = 'pump_1' AND tag = 'temperature'
            ORDER BY time DESC LIMIT 1
        """,
        unit="°C",
        min_value=0,
        max_value=100,
        thresholds=[20, 50, 80],
        colors=["green", "yellow", "red"]
    )
    
    dashboard.add_gauge_panel(
        title="Compressor #1 Temperature",
        query="""
            SELECT value FROM sensor_readings
            WHERE equipment_id = 'compressor_1' AND tag = 'temperature'
            ORDER BY time DESC LIMIT 1
        """,
        unit="°C",
        min_value=0,
        max_value=60,
        thresholds=[10, 30, 50],
        colors=["green", "yellow", "red"]
    )
    
    dashboard.add_gauge_panel(
        title="Heater #1 Temperature",
        query="""
            SELECT value FROM sensor_readings
            WHERE equipment_id = 'heater_1' AND tag = 'temperature'
            ORDER BY time DESC LIMIT 1
        """,
        unit="°C",
        min_value=0,
        max_value=150,
        thresholds=[50, 100, 130],
        colors=["green", "yellow", "red"]
    )
    
    # Pressure gauges
    dashboard.add_gauge_panel(
        title="Pump #1 Pressure",
        query="""
            SELECT value FROM sensor_readings
            WHERE equipment_id = 'pump_1' AND tag = 'pressure'
            ORDER BY time DESC LIMIT 1
        """,
        unit="PSI",
        min_value=0,
        max_value=150,
        thresholds=[0, 75, 120],
        colors=["green", "yellow", "red"]
    )
    
    # Vibration gauge
    dashboard.add_gauge_panel(
        title="Pump #1 Vibration",
        query="""
            SELECT value FROM sensor_readings
            WHERE equipment_id = 'pump_1' AND tag = 'vibration'
            ORDER BY time DESC LIMIT 1
        """,
        unit="mm/s",
        min_value=0,
        max_value=20,
        thresholds=[0, 5, 15],
        colors=["green", "yellow", "red"]
    )
    
    # Anomalies table
    dashboard.add_alert_status_panel()
    
    return dashboard


def create_timeseries_dashboard() -> GrafanaDashboard:
    """
    Create time-series trending dashboard.
    
    Panels:
    - Temperature trends (last 24h)
    - Pressure trends (last 24h)
    - Vibration trends (last 24h)
    - Data quality timeline
    """
    dashboard = GrafanaDashboard(
        title="Time-Series Trends",
        description="24-hour historical trending of sensor data",
        tags=["SCADA", "Trending", "Historical"],
        refresh="30s"
    )
    
    dashboard.add_equipment_variable()
    
    # Temperature trends
    dashboard.add_timeseries_panel(
        title="Temperature Trends (Last 24h)",
        queries={
            "A": """
                SELECT
                  time_bucket('1 minute', time) as time,
                  equipment_id,
                  AVG(value) as value
                FROM sensor_readings
                WHERE tag = 'temperature' AND time > CURRENT_TIMESTAMP - INTERVAL '24 hours'
                GROUP BY time_bucket('1 minute', time), equipment_id
                ORDER BY time
            """
        },
        unit="°C",
        yaxis_label="Temperature (°C)"
    )
    
    # Pressure trends
    dashboard.add_timeseries_panel(
        title="Pressure Trends (Last 24h)",
        queries={
            "A": """
                SELECT
                  time_bucket('1 minute', time) as time,
                  equipment_id,
                  AVG(value) as value
                FROM sensor_readings
                WHERE tag = 'pressure' AND time > CURRENT_TIMESTAMP - INTERVAL '24 hours'
                GROUP BY time_bucket('1 minute', time), equipment_id
                ORDER BY time
            """
        },
        unit="PSI",
        yaxis_label="Pressure (PSI)"
    )
    
    # Vibration trends
    dashboard.add_timeseries_panel(
        title="Vibration Trends (Last 24h)",
        queries={
            "A": """
                SELECT
                  time_bucket('1 minute', time) as time,
                  equipment_id,
                  AVG(value) as value
                FROM sensor_readings
                WHERE tag = 'vibration' AND time > CURRENT_TIMESTAMP - INTERVAL '24 hours'
                GROUP BY time_bucket('1 minute', time), equipment_id
                ORDER BY time
            """
        },
        unit="mm/s",
        yaxis_label="Vibration (mm/s)"
    )
    
    return dashboard


def create_anomaly_dashboard() -> GrafanaDashboard:
    """
    Create anomaly and alert dashboard.
    
    Panels:
    - Anomalies by type (last 7 days)
    - Anomaly timeline
    - Equipment health scores
    - Alert acknowledgment status
    """
    dashboard = GrafanaDashboard(
        title="Anomaly & Alert Analysis",
        description="Anomaly detection results and alert status",
        tags=["SCADA", "Anomalies", "Alerts"],
        refresh="10s"
    )
    
    # Anomaly count by type
    dashboard.add_stat_panel(
        title="Spike Anomalies (24h)",
        query="""
            SELECT COUNT(*) as count
            FROM alarm_events
            WHERE anomaly_type = 'spike' AND time > CURRENT_TIMESTAMP - INTERVAL '24 hours'
        """,
        unit="short"
    )
    
    dashboard.add_stat_panel(
        title="Outlier Anomalies (24h)",
        query="""
            SELECT COUNT(*) as count
            FROM alarm_events
            WHERE anomaly_type = 'outlier' AND time > CURRENT_TIMESTAMP - INTERVAL '24 hours'
        """,
        unit="short"
    )
    
    dashboard.add_stat_panel(
        title="NaN Values (24h)",
        query="""
            SELECT COUNT(*) as count
            FROM alarm_events
            WHERE anomaly_type = 'nan' AND time > CURRENT_TIMESTAMP - INTERVAL '24 hours'
        """,
        unit="short"
    )
    
    # Recent anomalies table
    dashboard.add_table_panel(
        title="Recent Anomalies",
        query="""
            SELECT
              time,
              equipment_id,
              tag,
              anomaly_type,
              value,
              reason,
              severity
            FROM alarm_events
            WHERE time > CURRENT_TIMESTAMP - INTERVAL '24 hours'
            ORDER BY time DESC
            LIMIT 50
        """
    )
    
    return dashboard


def create_health_dashboard() -> GrafanaDashboard:
    """
    Create equipment health dashboard.
    
    Panels:
    - Health score per equipment
    - Data quality percentage
    - Unacknowledged alerts
    - Equipment uptime
    """
    dashboard = GrafanaDashboard(
        title="Equipment Health",
        description="Equipment health scores and data quality metrics",
        tags=["SCADA", "Health", "Metrics"],
        refresh="1m"
    )
    
    # Health scores
    dashboard.add_stat_panel(
        title="Pump #1 Health",
        query="""
            SELECT health_score
            FROM get_equipment_health('pump_1', 24)
        """,
        unit="percent"
    )
    
    dashboard.add_stat_panel(
        title="Compressor #1 Health",
        query="""
            SELECT health_score
            FROM get_equipment_health('compressor_1', 24)
        """,
        unit="percent"
    )
    
    dashboard.add_stat_panel(
        title="Heater #1 Health",
        query="""
            SELECT health_score
            FROM get_equipment_health('heater_1', 24)
        """,
        unit="percent"
    )
    
    # Data quality table
    dashboard.add_table_panel(
        title="Equipment Health Details",
        query="""
            SELECT
              equipment_id,
              total_readings,
              good_readings,
              uncertain_readings,
              bad_readings,
              ROUND(health_score, 2) as health_score,
              last_reading
            FROM get_equipment_health('pump_1', 24)
            UNION ALL
            SELECT * FROM get_equipment_health('compressor_1', 24)
            UNION ALL
            SELECT * FROM get_equipment_health('heater_1', 24)
        """
    )
    
    return dashboard


# ============================================================================
# DASHBOARD MANAGER
# ============================================================================

class DashboardManager:
    """Manage all Grafana dashboards"""
    
    def __init__(self, output_dir: str = "./grafana/dashboards"):
        self.output_dir = output_dir
        self.dashboards = {}
        self.logger = logger
    
    def register_dashboard(self, name: str, dashboard: GrafanaDashboard) -> None:
        """Register a dashboard"""
        self.dashboards[name] = dashboard
        self.logger.info(f"📊 Registered dashboard: {name}")
    
    def export_all(self) -> None:
        """Export all dashboards to JSON files"""
        import os
        os.makedirs(self.output_dir, exist_ok=True)
        
        for name, dashboard in self.dashboards.items():
            filepath = f"{self.output_dir}/{name}.json"
            dashboard.save_to_file(filepath)
            self.logger.info(f"💾 Exported: {filepath}")
    
    def create_default_dashboards(self) -> None:
        """Create and register default dashboards"""
        self.register_dashboard(
            "equipment-status",
            create_equipment_status_dashboard()
        )
        
        self.register_dashboard(
            "timeseries-trends",
            create_timeseries_dashboard()
        )
        
        self.register_dashboard(
            "anomaly-analysis",
            create_anomaly_dashboard()
        )
        
        self.register_dashboard(
            "equipment-health",
            create_health_dashboard()
        )


# ============================================================================
# MAIN / TEST
# ============================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    
    # Create dashboard manager
    manager = DashboardManager(output_dir="./grafana/dashboards")
    
    # Create default dashboards
    manager.create_default_dashboards()
    
    # Export all
    manager.export_all()
    
    logger.info("\n✅ Grafana dashboards created successfully!")
    logger.info("   Copy JSON files to Grafana provisioning directory:")
    logger.info("   cp grafana/dashboards/*.json /etc/grafana/provisioning/dashboards/")
