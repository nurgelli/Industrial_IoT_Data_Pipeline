"""
Test Script: Layer 8 Grafana Dashboard & Visualization
=======================================================

Tests:
1. Dashboard creation (Equipment Status)
2. Dashboard JSON generation
3. Datasource provisioning
4. Dashboard export to files
5. Notification channel setup
"""

import sys
import json
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from layer8_grafana.grafana_config import (
    GrafanaDashboard,
    DashboardManager,
    create_equipment_status_dashboard,
    create_timeseries_dashboard,
    create_anomaly_dashboard,
    create_health_dashboard,
)
from layer8_grafana.datasource_provisioner import (
    DatasourceProvisioner,
    NotificationChannelProvisioner,
)

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


def test_dashboard_creation():
    """Test 1: Dashboard creation"""
    logger.info("\n" + "="*70)
    logger.info("TEST 1: Dashboard Creation")
    logger.info("="*70)
    
    logger.info("\n📌 Creating Equipment Status dashboard...")
    dashboard = create_equipment_status_dashboard()
    
    assert dashboard is not None, "Dashboard should be created"
    assert dashboard.title == "Equipment Status", "Title should match"
    assert len(dashboard.panels) > 0, "Should have panels"
    
    logger.info(f"✅ Dashboard created: {dashboard.title}")
    logger.info(f"   Panels: {len(dashboard.panels)}")
    logger.info(f"   Variables: {len(dashboard.variables)}")
    
    logger.info("\n✅ Dashboard creation tests passed!")
    return dashboard


def test_dashboard_json_generation(dashboard):
    """Test 2: Dashboard JSON generation"""
    logger.info("\n" + "="*70)
    logger.info("TEST 2: Dashboard JSON Generation")
    logger.info("="*70)
    
    logger.info("\n📌 Building dashboard JSON...")
    dashboard_json = dashboard.build()
    
    assert isinstance(dashboard_json, dict), "Should return dict"
    assert "title" in dashboard_json, "Should have title"
    assert "panels" in dashboard_json, "Should have panels"
    assert "uid" in dashboard_json, "Should have uid"
    
    logger.info(f"✅ Dashboard JSON built successfully")
    logger.info(f"   Keys: {list(dashboard_json.keys())}")
    
    logger.info("\n📌 Converting to JSON string...")
    json_str = dashboard.to_json(pretty=False)
    
    assert isinstance(json_str, str), "Should return string"
    assert len(json_str) > 100, "Should have content"
    
    parsed = json.loads(json_str)  # Validate JSON
    logger.info(f"✅ Valid JSON generated: {len(json_str)} characters")
    
    logger.info("\n✅ Dashboard JSON generation tests passed!")
    return dashboard_json


def test_dashboard_manager():
    """Test 3: Dashboard Manager"""
    logger.info("\n" + "="*70)
    logger.info("TEST 3: Dashboard Manager")
    logger.info("="*70)
    
    logger.info("\n📌 Creating DashboardManager...")
    manager = DashboardManager(output_dir="./test_dashboards")
    
    logger.info("📌 Creating default dashboards...")
    manager.create_default_dashboards()
    
    assert len(manager.dashboards) > 0, "Should have dashboards"
    logger.info(f"✅ Created {len(manager.dashboards)} dashboards:")
    for name in manager.dashboards.keys():
        logger.info(f"   - {name}")
    
    logger.info("\n✅ Dashboard Manager tests passed!")


def test_datasource_provisioning():
    """Test 4: Datasource Provisioning"""
    logger.info("\n" + "="*70)
    logger.info("TEST 4: Datasource Provisioning")
    logger.info("="*70)
    
    logger.info("\n📌 Creating DatasourceProvisioner...")
    provisioner = DatasourceProvisioner(output_dir="./test_provisioning/datasources")
    
    # TimescaleDB datasource
    logger.info("📌 Creating TimescaleDB datasource config...")
    ts_config = provisioner.create_timescaledb_datasource(
        name="TestTimescaleDB",
        host="localhost",
        port=5432,
        database="scada_db"
    )
    
    assert "datasources" in ts_config, "Should have datasources key"
    assert len(ts_config["datasources"]) > 0, "Should have at least one datasource"
    ds = ts_config["datasources"][0]
    assert ds["type"] == "postgres", "Type should be postgres"
    assert ds["name"] == "TestTimescaleDB", "Name should match"
    
    logger.info(f"✅ TimescaleDB datasource created: {ds['name']}")
    
    # Prometheus datasource
    logger.info("📌 Creating Prometheus datasource config...")
    prom_config = provisioner.create_prometheus_datasource(
        name="TestPrometheus",
        url="http://localhost:9090"
    )
    
    assert "datasources" in prom_config, "Should have datasources key"
    prom_ds = prom_config["datasources"][0]
    assert prom_ds["type"] == "prometheus", "Type should be prometheus"
    
    logger.info(f"✅ Prometheus datasource created: {prom_ds['name']}")
    
    logger.info("\n✅ Datasource provisioning tests passed!")


def test_notification_channels():
    """Test 5: Notification Channels"""
    logger.info("\n" + "="*70)
    logger.info("TEST 5: Notification Channels")
    logger.info("="*70)
    
    logger.info("\n📌 Creating NotificationChannelProvisioner...")
    notifier = NotificationChannelProvisioner(output_dir="./test_provisioning/notifiers")
    
    # Email notifier
    logger.info("📌 Creating Email notifier...")
    email_config = notifier.create_email_notifier(
        name="TestEmail",
        addresses=["test@example.com", "ops@example.com"]
    )
    
    assert "notifiers" in email_config, "Should have notifiers key"
    email_notif = email_config["notifiers"][0]
    assert email_notif["type"] == "email", "Type should be email"
    
    logger.info(f"✅ Email notifier created: {email_notif['name']}")
    
    # Slack notifier
    logger.info("📌 Creating Slack notifier...")
    slack_config = notifier.create_slack_notifier(
        name="TestSlack",
        webhook_url="https://hooks.slack.com/services/TEST/TEST/TEST"
    )
    
    assert "notifiers" in slack_config, "Should have notifiers key"
    slack_notif = slack_config["notifiers"][0]
    assert slack_notif["type"] == "slack", "Type should be slack"
    
    logger.info(f"✅ Slack notifier created: {slack_notif['name']}")
    
    # PagerDuty notifier
    logger.info("📌 Creating PagerDuty notifier...")
    pagerduty_config = notifier.create_pagerduty_notifier(
        name="TestPagerDuty",
        service_key="TEST_KEY"
    )
    
    assert "notifiers" in pagerduty_config, "Should have notifiers key"
    pagerduty_notif = pagerduty_config["notifiers"][0]
    assert pagerduty_notif["type"] == "pagerduty", "Type should be pagerduty"
    
    logger.info(f"✅ PagerDuty notifier created: {pagerduty_notif['name']}")
    
    logger.info("\n✅ Notification channel tests passed!")


def test_all_dashboards():
    """Test 6: All predefined dashboards"""
    logger.info("\n" + "="*70)
    logger.info("TEST 6: All Predefined Dashboards")
    logger.info("="*70)
    
    dashboards = [
        ("Equipment Status", create_equipment_status_dashboard()),
        ("Time-Series Trends", create_timeseries_dashboard()),
        ("Anomaly Analysis", create_anomaly_dashboard()),
        ("Equipment Health", create_health_dashboard()),
    ]
    
    for name, dashboard in dashboards:
        logger.info(f"\n📌 Testing {name}...")
        
        # Validate structure
        assert dashboard.title == name, f"Title should be {name}"
        assert len(dashboard.panels) > 0, "Should have panels"
        
        # Validate JSON
        json_str = dashboard.to_json(pretty=False)
        parsed = json.loads(json_str)
        assert "title" in parsed, "Should have title in JSON"
        
        logger.info(f"✅ {name} dashboard valid")
        logger.info(f"   Panels: {len(dashboard.panels)}")
    
    logger.info("\n✅ All dashboards tests passed!")


async def main():
    """Run all tests"""
    logger.info("\n🧪 STARTING LAYER 8 TESTS (Grafana Dashboard & Visualization)\n")
    
    try:
        # Test 1: Dashboard creation
        dashboard = test_dashboard_creation()
        
        # Test 2: JSON generation
        test_dashboard_json_generation(dashboard)
        
        # Test 3: Dashboard Manager
        test_dashboard_manager()
        
        # Test 4: Datasource provisioning
        test_datasource_provisioning()
        
        # Test 5: Notification channels
        test_notification_channels()
        
        # Test 6: All dashboards
        test_all_dashboards()
        
        logger.info("\n" + "="*70)
        logger.info("✅ ALL TESTS PASSED!")
        logger.info("="*70)
        logger.info("\n🎉 Layer 8 (Grafana) is ready for integration!\n")
        logger.info("Next steps:")
        logger.info("1. Start Docker services: docker-compose up -d")
        logger.info("2. Access Grafana: http://localhost:3000")
        logger.info("3. Default login: admin / admin")
        logger.info("4. Dashboards will auto-provision from ./grafana/provisioning/\n")
    
    except AssertionError as e:
        logger.error(f"\n❌ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"\n❌ Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
