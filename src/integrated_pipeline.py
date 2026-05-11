"""
INTEGRATED PIPELINE: MQTT Consumer → Data Cleaner → Output
===========================================================

Purpose:
  Complete data flow from MQTT consumption to cleaned output.
  Consumer batches readings from MQTT, Cleaner processes them.

Flow:
  MQTTConsumer receives messages
    ↓ (every 100 readings or 5s)
  on_batch_complete() callback triggered
    ↓
  DataCleaner.clean_batch() processes readings
    1. Handle NaN
    2. Detect spikes (Z-score)
    3. Detect outliers (IQR)
    4. Filter noise (median)
    ↓
  Result: clean readings + anomalies
    ↓
  Ready for database writing (Layer 7)

Author: SCADA Team
Date: May 8, 2026
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional, Callable

sys.path.insert(0, str(Path(__file__).parent))
from utils import config
from layer5_mqtt_consumer.consumer import MQTTConsumer
from layer6_data_cleaning.cleaner import DataCleaner, CleaningMethod
from layer3_python_bridge.data_model import BatchedReadings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


class IntegratedPipeline:
    """
    Complete pipeline: MQTT Consumer + Data Cleaner.
    
    Configuration (from settings.yaml):
    - mqtt: broker config
    - cleaning: method, thresholds, etc.
    """
    
    def __init__(
        self,
        on_clean_batch_ready: Optional[Callable] = None,
        on_anomaly_detected: Optional[Callable] = None,
    ):
        """
        Initialize pipeline.
        
        Args:
            on_clean_batch_ready: Callback when batch is cleaned and ready
                                  signature: async def callback(readings, anomalies)
            on_anomaly_detected: Callback for each anomaly found
                                 signature: async def callback(anomaly_record)
        """
        
        # Load configuration
        mqtt_config = config.get_mqtt()
        cleaning_config = config.get("data_cleaning", {})
        
        # Initialize components
        self.consumer = MQTTConsumer(
            on_batch_complete=self._on_batch_from_consumer
        )
        
        # Determine cleaning method
        method_str = cleaning_config.get("method", "drop").lower()
        method_map = {
            "drop": CleaningMethod.DROP,
            "forward_fill": CleaningMethod.FORWARD_FILL,
            "backward_fill": CleaningMethod.BACKWARD_FILL,
            "interpolate": CleaningMethod.INTERPOLATE,
        }
        cleaning_method = method_map.get(method_str, CleaningMethod.DROP)
        
        self.cleaner = DataCleaner(
            cleaning_method=cleaning_method,
            z_score_threshold=cleaning_config.get("z_score_threshold", 3.0),
            iqr_multiplier=cleaning_config.get("iqr_multiplier", 1.5),
            rolling_window_size=cleaning_config.get("rolling_window_size", 3),
            min_readings_for_stats=cleaning_config.get("min_readings_for_stats", 10),
            logger=logger
        )
        
        # Callbacks
        self.on_clean_batch_ready = on_clean_batch_ready
        self.on_anomaly_detected = on_anomaly_detected
        
        # Setup cleaner callbacks
        if on_anomaly_detected:
            self.cleaner.on_anomaly_detected = on_anomaly_detected
        
        # Counters
        self.batches_processed = 0
        self.readings_processed = 0
        self.anomalies_found = 0
        
        logger.info("✅ IntegratedPipeline initialized")
    
    async def _on_batch_from_consumer(self, batch: BatchedReadings):
        """
        Callback from MQTTConsumer when batch is ready.
        
        Args:
            batch: BatchedReadings from consumer
        """
        logger.info(f"📥 Batch received from consumer: {len(batch.readings)} readings")
        
        # Clean the batch
        cleaned_readings, anomalies = await self.cleaner.clean_batch(batch)
        
        self.batches_processed += 1
        self.readings_processed += len(cleaned_readings)
        self.anomalies_found += len(anomalies)
        
        logger.info(
            f"📊 Pipeline stats - Batches: {self.batches_processed}, "
            f"Readings: {self.readings_processed}, "
            f"Anomalies: {self.anomalies_found}"
        )
        
        # Call downstream callback
        if self.on_clean_batch_ready:
            logger.info(f"🔄 Calling downstream callback with {len(cleaned_readings)} clean readings")
            await self.on_clean_batch_ready(cleaned_readings, anomalies)
    
    async def start(self):
        """
        Start the pipeline.
        
        Sequence:
        1. Connect to MQTT broker
        2. Subscribe to plant/# pattern
        3. Start consumer loop
        4. Pipeline ready to receive data
        """
        try:
            logger.info("🚀 Starting IntegratedPipeline...")
            
            # Connect consumer
            if not await self.consumer.connect():
                logger.error("❌ Failed to connect to MQTT broker")
                return False
            
            logger.info("✅ Pipeline started and listening for MQTT messages")
            return True
        
        except Exception as e:
            logger.error(f"❌ Error starting pipeline: {e}", exc_info=True)
            return False
    
    async def stop(self):
        """Stop the pipeline gracefully."""
        try:
            logger.info("🛑 Stopping IntegratedPipeline...")
            await self.consumer.disconnect()
            logger.info("✅ Pipeline stopped")
        except Exception as e:
            logger.error(f"❌ Error stopping pipeline: {e}", exc_info=True)
    
    def get_statistics(self) -> dict:
        """Get pipeline statistics."""
        return {
            "batches_processed": self.batches_processed,
            "readings_processed": self.readings_processed,
            "anomalies_found": self.anomalies_found,
            "cleaner_anomaly_history": len(self.cleaner.detected_anomalies),
            "cleaner_report": self.cleaner.get_anomaly_report(),
        }


# ============================================================================
# EXAMPLE DOWNSTREAM CONSUMER (Ready for Layer 7: Database)
# ============================================================================

async def example_database_writer(cleaned_readings, anomalies):
    """
    Example callback for writing cleaned data to database.
    
    This is a placeholder for Layer 7 (TimescaleDB writing).
    
    Args:
        cleaned_readings: List of cleaned SensorReading objects
        anomalies: List of AnomalyRecord objects
    """
    logger.info(
        f"📤 DATABASE LAYER (Layer 7) would receive: "
        f"{len(cleaned_readings)} readings, {len(anomalies)} anomalies"
    )
    
    # In Layer 7, this will:
    # 1. Convert readings to database format
    # 2. Batch insert to TimescaleDB
    # 3. Log anomalies to alarm_events table
    # 4. Update last_write timestamp
    
    await asyncio.sleep(0.1)  # Simulate DB write
    logger.info(f"✅ Mock database write complete")


# ============================================================================
# MAIN / TEST
# ============================================================================

async def main():
    """Test the integrated pipeline."""
    
    # Create pipeline with database writer callback
    pipeline = IntegratedPipeline(
        on_clean_batch_ready=example_database_writer
    )
    
    try:
        # Start pipeline
        if await pipeline.start():
            logger.info("🎯 Pipeline running. Waiting for MQTT messages...")
            
            # Keep running until interrupted
            while True:
                await asyncio.sleep(1)
                stats = pipeline.get_statistics()
                if stats["batches_processed"] > 0:
                    logger.info(f"📊 Current stats: {stats}")
        else:
            logger.error("Failed to start pipeline")
    
    except KeyboardInterrupt:
        logger.info("⏹️ Received interrupt signal")
    
    finally:
        await pipeline.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Pipeline terminated by user")
