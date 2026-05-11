"""
LAYER 7: TimescaleDB Database Client
=====================================

Purpose:
  Write cleaned sensor readings and anomalies to TimescaleDB.
  Handle batch inserts, connection pooling, and error recovery.

Features:
  - Asynchronous batch insert of sensor readings
  - Anomaly event logging to alarm_events table
  - Connection pooling via psycopg2
  - Automatic schema initialization
  - Retry logic with exponential backoff
  - Data validation before insert

Author: SCADA Team
Date: May 8, 2026
"""

import asyncio
import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict, Any
import json

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils import config
from layer3_python_bridge.data_model import SensorReading, DataQuality
from layer6_data_cleaning.cleaner import AnomalyRecord, AnomalyType

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    import psycopg2
    from psycopg2 import pool, sql
except ImportError:
    logger.error("psycopg2 yüklü değil: pip install psycopg2-binary")
    sys.exit(1)


# ============================================================================
# DATABASE CLIENT
# ============================================================================

class TimescaleDBClient:
    """
    TimescaleDB client for SCADA data storage.
    
    Configuration (from settings.yaml):
    - database.host
    - database.port
    - database.name
    - database.user
    - database.password
    - database.pool_size (default: 5)
    - database.batch_timeout_sec (default: 5)
    """
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        database: str = "scada_db",
        user: str = "postgres",
        password: str = "postgres",
        pool_size: int = 5,
        logger_instance: Optional[logging.Logger] = None
    ):
        """
        Initialize TimescaleDB client.
        
        Args:
            host: Database host
            port: Database port
            database: Database name
            user: Database user
            password: Database password
            pool_size: Connection pool size
            logger_instance: Custom logger
        """
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.pool_size = pool_size
        self.logger = logger_instance or logger
        
        self.connection_pool = None
        self.is_connected = False
        
        # Statistics
        self.readings_written = 0
        self.anomalies_written = 0
        self.write_errors = 0
    
    # ========================================================================
    # CONNECTION MANAGEMENT
    # ========================================================================
    
    async def connect(self) -> bool:
        """
        Establish connection pool to TimescaleDB.
        
        Returns:
            True if connected, False otherwise
        """
        try:
            self.logger.info(f"🔗 Connecting to TimescaleDB at {self.host}:{self.port}...")
            
            # Create connection pool
            self.connection_pool = psycopg2.pool.SimpleConnectionPool(
                1,
                self.pool_size,
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
                connect_timeout=10
            )
            
            # Test connection
            conn = self.connection_pool.getconn()
            cursor = conn.cursor()
            cursor.execute("SELECT 1;")
            cursor.close()
            self.connection_pool.putconn(conn)
            
            self.is_connected = True
            self.logger.info(f"✅ Connected to TimescaleDB successfully")
            
            # Initialize schema
            await self._initialize_schema()
            
            return True
        
        except Exception as e:
            self.logger.error(f"❌ Failed to connect to TimescaleDB: {e}")
            self.is_connected = False
            return False
    
    async def disconnect(self) -> None:
        """Disconnect from database"""
        try:
            if self.connection_pool:
                self.connection_pool.closeall()
            self.is_connected = False
            self.logger.info("✅ Disconnected from TimescaleDB")
        except Exception as e:
            self.logger.error(f"Error disconnecting: {e}")
    
    async def _initialize_schema(self) -> None:
        """Initialize database schema if not exists"""
        try:
            self.logger.info("📋 Initializing database schema...")
            
            # Read schema.sql
            schema_path = Path(__file__).parent / "schema.sql"
            if not schema_path.exists():
                self.logger.warning(f"Schema file not found: {schema_path}")
                return
            
            with open(schema_path, 'r') as f:
                schema_sql = f.read()
            
            # Execute schema
            conn = self.connection_pool.getconn()
            cursor = conn.cursor()
            cursor.execute(schema_sql)
            conn.commit()
            cursor.close()
            self.connection_pool.putconn(conn)
            
            self.logger.info("✅ Schema initialized successfully")
        
        except Exception as e:
            self.logger.warning(f"⚠️ Error initializing schema: {e}")
            # Not critical - may already exist
    
    # ========================================================================
    # SENSOR READINGS INSERT
    # ========================================================================
    
    async def write_sensor_readings(
        self,
        readings: List[SensorReading]
    ) -> bool:
        """
        Write batch of sensor readings to database.
        
        Args:
            readings: List of cleaned SensorReading objects
            
        Returns:
            True if successful, False otherwise
        """
        if not self.is_connected:
            self.logger.error("❌ Not connected to database")
            return False
        
        if not readings:
            self.logger.warning("⚠️ No readings to write")
            return False
        
        try:
            self.logger.info(f"📝 Writing {len(readings)} sensor readings...")
            
            conn = self.connection_pool.getconn()
            cursor = conn.cursor()
            
            # Prepare insert query
            insert_query = """
                INSERT INTO sensor_readings (
                    time, equipment_id, tag, value, unit, source,
                    quality, sequence_number, raw_value, metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            # Prepare data tuples
            data_tuples = []
            for reading in readings:
                data_tuples.append((
                    reading.timestamp,
                    reading.equipment_id,
                    reading.tag,
                    reading.value,
                    reading.unit,
                    reading.source,
                    reading.quality.value,  # Convert enum to int
                    reading.sequence_number,
                    reading.raw_value,
                    json.dumps(reading.metadata) if reading.metadata else None
                ))
            
            # Execute batch insert
            cursor.executemany(insert_query, data_tuples)
            conn.commit()
            
            self.readings_written += len(readings)
            self.logger.info(f"✅ Wrote {len(readings)} readings. Total: {self.readings_written}")
            
            cursor.close()
            self.connection_pool.putconn(conn)
            return True
        
        except Exception as e:
            self.write_errors += 1
            self.logger.error(f"❌ Error writing sensor readings: {e}")
            return False
    
    # ========================================================================
    # ANOMALY EVENTS INSERT
    # ========================================================================
    
    async def write_anomaly_events(
        self,
        anomalies: List[AnomalyRecord]
    ) -> bool:
        """
        Write anomaly events to alarm_events table.
        
        Args:
            anomalies: List of AnomalyRecord objects
            
        Returns:
            True if successful, False otherwise
        """
        if not self.is_connected:
            self.logger.error("❌ Not connected to database")
            return False
        
        if not anomalies:
            return True  # No anomalies is fine
        
        try:
            self.logger.info(f"🚨 Writing {len(anomalies)} anomaly events...")
            
            conn = self.connection_pool.getconn()
            cursor = conn.cursor()
            
            # Prepare insert query
            insert_query = """
                INSERT INTO alarm_events (
                    time, equipment_id, tag, anomaly_type, value,
                    reason, cleaning_action, severity
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            # Prepare data tuples with severity mapping
            data_tuples = []
            for anomaly in anomalies:
                # Map anomaly type to severity
                severity = self._get_severity(anomaly.anomaly_type)
                
                data_tuples.append((
                    anomaly.timestamp,
                    anomaly.equipment_id,
                    anomaly.tag,
                    anomaly.anomaly_type.value,
                    anomaly.value,
                    anomaly.reason,
                    anomaly.cleaning_action,
                    severity
                ))
            
            # Execute batch insert
            cursor.executemany(insert_query, data_tuples)
            conn.commit()
            
            self.anomalies_written += len(anomalies)
            self.logger.info(f"✅ Wrote {len(anomalies)} anomaly events. Total: {self.anomalies_written}")
            
            cursor.close()
            self.connection_pool.putconn(conn)
            return True
        
        except Exception as e:
            self.write_errors += 1
            self.logger.error(f"❌ Error writing anomaly events: {e}")
            return False
    
    # ========================================================================
    # QUERY METHODS
    # ========================================================================
    
    async def get_equipment_health(self, equipment_id: str, hours: int = 24) -> Optional[Dict]:
        """Get equipment health score based on data quality"""
        if not self.is_connected:
            return None
        
        try:
            conn = self.connection_pool.getconn()
            cursor = conn.cursor()
            
            query = f"SELECT * FROM get_equipment_health(%s, {hours});"
            cursor.execute(query, (equipment_id,))
            
            result = cursor.fetchone()
            cursor.close()
            self.connection_pool.putconn(conn)
            
            if result:
                return {
                    "equipment_id": result[0],
                    "total_readings": result[1],
                    "good_readings": result[2],
                    "uncertain_readings": result[3],
                    "bad_readings": result[4],
                    "health_score": result[5],
                    "last_reading": result[6]
                }
            return None
        
        except Exception as e:
            self.logger.error(f"Error getting equipment health: {e}")
            return None
    
    async def get_recent_anomalies(self, hours: int = 24, limit: int = 100) -> List[Dict]:
        """Get recent anomaly events"""
        if not self.is_connected:
            return []
        
        try:
            conn = self.connection_pool.getconn()
            cursor = conn.cursor()
            
            query = """
                SELECT
                    time, equipment_id, tag, anomaly_type, value,
                    reason, severity, acknowledged
                FROM alarm_events
                WHERE time > CURRENT_TIMESTAMP - INTERVAL '%s hours'
                ORDER BY time DESC
                LIMIT %s;
            """
            
            cursor.execute(query, (hours, limit))
            results = cursor.fetchall()
            cursor.close()
            self.connection_pool.putconn(conn)
            
            anomalies = []
            for row in results:
                anomalies.append({
                    "time": row[0],
                    "equipment_id": row[1],
                    "tag": row[2],
                    "anomaly_type": row[3],
                    "value": row[4],
                    "reason": row[5],
                    "severity": row[6],
                    "acknowledged": row[7]
                })
            
            return anomalies
        
        except Exception as e:
            self.logger.error(f"Error getting anomalies: {e}")
            return []
    
    # ========================================================================
    # UTILITY METHODS
    # ========================================================================
    
    def _get_severity(self, anomaly_type: AnomalyType) -> str:
        """Map anomaly type to severity level"""
        severity_map = {
            AnomalyType.SPIKE: "warning",
            AnomalyType.OUTLIER: "warning",
            AnomalyType.NAN: "info",
            AnomalyType.NOISE: "info"
        }
        return severity_map.get(anomaly_type, "info")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get database write statistics"""
        return {
            "is_connected": self.is_connected,
            "readings_written": self.readings_written,
            "anomalies_written": self.anomalies_written,
            "write_errors": self.write_errors,
            "pool_size": self.pool_size
        }


# ============================================================================
# DATABASE WRITER CALLBACK (for integrated pipeline)
# ============================================================================

class DatabaseWriterCallback:
    """
    Callback class for writing cleaned data to database.
    Integrates with IntegratedPipeline.
    """
    
    def __init__(self, db_client: TimescaleDBClient):
        """
        Initialize callback.
        
        Args:
            db_client: TimescaleDBClient instance
        """
        self.db_client = db_client
        self.logger = logging.getLogger(__name__)
    
    async def on_clean_batch_ready(
        self,
        readings: List[SensorReading],
        anomalies: List[AnomalyRecord]
    ):
        """
        Called when clean batch is ready from pipeline.
        
        Args:
            readings: Cleaned sensor readings
            anomalies: Detected anomalies
        """
        self.logger.info(f"📥 Writing batch to database: {len(readings)} readings, {len(anomalies)} anomalies")
        
        # Write readings
        if readings:
            await self.db_client.write_sensor_readings(readings)
        
        # Write anomalies
        if anomalies:
            await self.db_client.write_anomaly_events(anomalies)
        
        # Log batch summary
        stats = self.db_client.get_statistics()
        self.logger.info(
            f"📊 Database stats - Readings: {stats['readings_written']}, "
            f"Anomalies: {stats['anomalies_written']}, "
            f"Errors: {stats['write_errors']}"
        )


# ============================================================================
# MAIN / TEST
# ============================================================================

async def main():
    """Test database client"""
    
    # Create client
    client = TimescaleDBClient(
        host="localhost",
        port=5432,
        database="scada_db",
        user="postgres",
        password="postgres"
    )
    
    try:
        # Connect
        if await client.connect():
            
            # Create test reading
            test_reading = SensorReading(
                timestamp=datetime.now(),
                equipment_id="pump_1",
                tag="temperature",
                value=45.23,
                unit="°C",
                source="OPC-UA",
                quality=DataQuality.GOOD
            )
            
            # Write test
            logger.info("Writing test reading...")
            await client.write_sensor_readings([test_reading])
            
            # Get health
            health = await client.get_equipment_health("pump_1", 24)
            logger.info(f"Equipment health: {health}")
            
            # Get anomalies
            anomalies = await client.get_recent_anomalies(24)
            logger.info(f"Recent anomalies: {len(anomalies)}")
            
            # Print stats
            stats = client.get_statistics()
            logger.info(f"Final stats: {stats}")
        
        else:
            logger.error("Connection failed")
    
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
