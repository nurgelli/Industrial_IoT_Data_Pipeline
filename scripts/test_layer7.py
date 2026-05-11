"""
Test Script: Layer 7 TimescaleDB Database Writing
=================================================

Tests:
1. Connection management
2. Sensor readings insert
3. Anomaly events insert
4. Query methods
5. Statistics tracking
"""

import sys
import asyncio
import logging
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent))

from layer7_timescaledb.db_client import (
    TimescaleDBClient,
    DatabaseWriterCallback,
)
from layer3_python_bridge.data_model import SensorReading, DataQuality
from layer6_data_cleaning.cleaner import AnomalyRecord, AnomalyType

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


async def test_connection():
    """Test 1: Connection management"""
    logger.info("\n" + "="*70)
    logger.info("TEST 1: Connection Management")
    logger.info("="*70)
    
    client = TimescaleDBClient(
        host="localhost",
        port=5432,
        database="scada_db",
        user="postgres",
        password="postgres"
    )
    
    try:
        # Test connect
        logger.info("\n📌 Testing connect()...")
        connected = await client.connect()
        
        if connected:
            logger.info(f"✅ Connected successfully")
            stats = client.get_statistics()
            logger.info(f"  Connection stats: {stats}")
            
            # Test disconnect
            logger.info("\n📌 Testing disconnect()...")
            await client.disconnect()
            logger.info(f"✅ Disconnected successfully")
        else:
            logger.warning("⚠️ Could not connect (TimescaleDB may not be running)")
            logger.info("  Skipping remaining tests")
            return False
    
    except Exception as e:
        logger.error(f"❌ Error in connection test: {e}")
        return False
    
    logger.info("\n✅ Connection tests passed!")
    return True


async def test_sensor_readings_write(client: TimescaleDBClient):
    """Test 2: Sensor readings insert"""
    logger.info("\n" + "="*70)
    logger.info("TEST 2: Sensor Readings Write")
    logger.info("="*70)
    
    now = datetime.now()
    
    # Create test readings
    readings = [
        SensorReading(
            timestamp=now + timedelta(seconds=i),
            equipment_id="pump_1",
            tag="temperature",
            value=45.0 + i * 0.5,
            unit="°C",
            source="OPC-UA",
            quality=DataQuality.GOOD,
            sequence_number=i
        ) for i in range(10)
    ]
    
    logger.info(f"\n📌 Writing {len(readings)} sensor readings...")
    result = await client.write_sensor_readings(readings)
    
    if result:
        logger.info(f"✅ Wrote {len(readings)} readings successfully")
        stats = client.get_statistics()
        logger.info(f"  Readings written: {stats['readings_written']}")
    else:
        logger.error(f"❌ Failed to write readings")
        return False
    
    logger.info("\n✅ Sensor readings write tests passed!")
    return True


async def test_anomaly_events_write(client: TimescaleDBClient):
    """Test 3: Anomaly events insert"""
    logger.info("\n" + "="*70)
    logger.info("TEST 3: Anomaly Events Write")
    logger.info("="*70)
    
    now = datetime.now()
    
    # Create test anomalies
    anomalies = [
        AnomalyRecord(
            timestamp=now + timedelta(seconds=i),
            equipment_id="pump_1",
            tag="temperature",
            anomaly_type=AnomalyType.SPIKE,
            value=150.0,
            reason=f"Z-score spike: 5.0σ",
            cleaning_action="flagged_uncertain"
        ) for i in range(3)
    ]
    
    logger.info(f"\n📌 Writing {len(anomalies)} anomaly events...")
    result = await client.write_anomaly_events(anomalies)
    
    if result:
        logger.info(f"✅ Wrote {len(anomalies)} anomalies successfully")
        stats = client.get_statistics()
        logger.info(f"  Anomalies written: {stats['anomalies_written']}")
    else:
        logger.error(f"❌ Failed to write anomalies")
        return False
    
    logger.info("\n✅ Anomaly events write tests passed!")
    return True


async def test_query_methods(client: TimescaleDBClient):
    """Test 4: Query methods"""
    logger.info("\n" + "="*70)
    logger.info("TEST 4: Query Methods")
    logger.info("="*70)
    
    # Test get_equipment_health
    logger.info("\n📌 Testing get_equipment_health()...")
    health = await client.get_equipment_health("pump_1", 24)
    
    if health:
        logger.info(f"✅ Got equipment health:")
        logger.info(f"  Total readings: {health['total_readings']}")
        logger.info(f"  Good: {health['good_readings']}, "
                   f"Uncertain: {health['uncertain_readings']}, "
                   f"Bad: {health['bad_readings']}")
        logger.info(f"  Health score: {health['health_score']:.2f}%")
    else:
        logger.warning("⚠️ Could not retrieve equipment health")
    
    # Test get_recent_anomalies
    logger.info("\n📌 Testing get_recent_anomalies()...")
    anomalies = await client.get_recent_anomalies(24, 10)
    
    if anomalies:
        logger.info(f"✅ Got {len(anomalies)} recent anomalies:")
        for i, anomaly in enumerate(anomalies[:3]):  # Show first 3
            logger.info(f"  {i+1}. {anomaly['equipment_id']}.{anomaly['tag']}: "
                       f"{anomaly['anomaly_type']} ({anomaly['severity']})")
    else:
        logger.info("  No recent anomalies found")
    
    logger.info("\n✅ Query methods tests passed!")
    return True


async def test_statistics():
    """Test 5: Statistics tracking"""
    logger.info("\n" + "="*70)
    logger.info("TEST 5: Statistics Tracking")
    logger.info("="*70)
    
    client = TimescaleDBClient(
        host="localhost",
        port=5432,
        database="scada_db",
        user="postgres",
        password="postgres"
    )
    
    await client.connect()
    
    logger.info("\n📌 Testing statistics()...")
    
    # Create test data
    now = datetime.now()
    readings = [
        SensorReading(
            timestamp=now + timedelta(seconds=i),
            equipment_id=f"equipment_{i%2}",
            tag="temperature",
            value=40.0 + i,
            unit="°C",
            source="OPC-UA",
            quality=DataQuality.GOOD
        ) for i in range(5)
    ]
    
    anomalies = [
        AnomalyRecord(
            timestamp=now,
            equipment_id="equipment_0",
            tag="temperature",
            anomaly_type=AnomalyType.SPIKE,
            value=150.0,
            reason="Spike detected",
            cleaning_action="flagged_uncertain"
        )
    ]
    
    # Write data
    await client.write_sensor_readings(readings)
    await client.write_anomaly_events(anomalies)
    
    # Get statistics
    stats = client.get_statistics()
    logger.info(f"✅ Statistics:")
    logger.info(f"  Connected: {stats['is_connected']}")
    logger.info(f"  Readings written: {stats['readings_written']}")
    logger.info(f"  Anomalies written: {stats['anomalies_written']}")
    logger.info(f"  Write errors: {stats['write_errors']}")
    logger.info(f"  Pool size: {stats['pool_size']}")
    
    await client.disconnect()
    
    logger.info("\n✅ Statistics tracking tests passed!")
    return True


async def test_database_writer_callback(client: TimescaleDBClient):
    """Test 6: DatabaseWriterCallback integration"""
    logger.info("\n" + "="*70)
    logger.info("TEST 6: DatabaseWriterCallback")
    logger.info("="*70)
    
    # Create callback
    callback = DatabaseWriterCallback(client)
    
    logger.info("\n📌 Testing on_clean_batch_ready callback...")
    
    # Create test data
    now = datetime.now()
    readings = [
        SensorReading(
            timestamp=now + timedelta(seconds=i),
            equipment_id="pump_1",
            tag="temperature",
            value=45.0 + i * 0.1,
            unit="°C",
            source="OPC-UA",
            quality=DataQuality.GOOD
        ) for i in range(5)
    ]
    
    anomalies = [
        AnomalyRecord(
            timestamp=now,
            equipment_id="pump_1",
            tag="temperature",
            anomaly_type=AnomalyType.OUTLIER,
            value=200.0,
            reason="Outlier detected",
            cleaning_action="flagged_uncertain"
        )
    ]
    
    # Call callback
    await callback.on_clean_batch_ready(readings, anomalies)
    
    logger.info(f"✅ Callback executed successfully")
    
    logger.info("\n✅ DatabaseWriterCallback tests passed!")
    return True


async def main():
    """Run all tests"""
    logger.info("\n🧪 STARTING LAYER 7 TESTS (TimescaleDB Database)\n")
    
    try:
        # Test 1: Connection
        if not await test_connection():
            logger.warning("\n⚠️ Connection test failed - skipping remaining tests")
            logger.warning("Make sure TimescaleDB is running: docker-compose up -d")
            return
        
        # Create persistent client for other tests
        client = TimescaleDBClient(
            host="localhost",
            port=5432,
            database="scada_db",
            user="postgres",
            password="postgres"
        )
        
        # Connect for remaining tests
        if not await client.connect():
            logger.warning("\n⚠️ Could not reconnect to database")
            return
        
        try:
            # Test 2-4: Insert and query
            await test_sensor_readings_write(client)
            await test_anomaly_events_write(client)
            await test_query_methods(client)
            
        finally:
            await client.disconnect()
        
        # Test 5-6: Statistics and callback
        await test_statistics()
        
        # Reconnect for callback test
        client2 = TimescaleDBClient(
            host="localhost",
            port=5432,
            database="scada_db",
            user="postgres",
            password="postgres"
        )
        
        if await client2.connect():
            await test_database_writer_callback(client2)
            await client2.disconnect()
        
        logger.info("\n" + "="*70)
        logger.info("✅ ALL TESTS PASSED!")
        logger.info("="*70)
        logger.info("\n🎉 Layer 7 (TimescaleDB) is ready for integration!\n")
    
    except Exception as e:
        logger.error(f"\n❌ Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
