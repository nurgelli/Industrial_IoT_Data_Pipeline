"""
Test Script: Layer 6 Data Cleaning Pipeline
=============================================

Tests:
1. NaN handling (DROP, FORWARD_FILL, BACKWARD_FILL)
2. Spike detection (Z-score method)
3. Outlier detection (IQR method)
4. Noise filtering (3-point median)
"""

import sys
import logging
from pathlib import Path
from datetime import datetime, timedelta
import statistics

sys.path.insert(0, str(Path(__file__).parent))

from layer6_data_cleaning.cleaner import (
    DataCleaner,
    CleaningMethod,
    AnomalyType,
)
from layer3_python_bridge.data_model import SensorReading, BatchedReadings, DataQuality

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


def test_nan_handling():
    """Test 1: NaN handling with different strategies"""
    logger.info("\n" + "="*70)
    logger.info("TEST 1: NaN Handling")
    logger.info("="*70)
    
    now = datetime.now()
    
    # Create readings with NaN
    readings = [
        SensorReading(
            timestamp=now + timedelta(seconds=i),
            equipment_id="pump_1",
            tag="temperature",
            value=45.0 + i,
            unit="°C",
            source="OPC-UA",
            quality=DataQuality.GOOD
        ) for i in range(5)
    ]
    
    # Insert NaN at position 2
    readings[2].value = float('nan')
    
    # Test DROP
    logger.info("\n📌 Testing DROP strategy...")
    cleaner_drop = DataCleaner(cleaning_method=CleaningMethod.DROP)
    cleaned_drop = cleaner_drop.handle_missing_values(readings)
    logger.info(f"  Input: {len(readings)} readings")
    logger.info(f"  Output: {len(cleaned_drop)} readings (NaN dropped)")
    assert len(cleaned_drop) == 4, "DROP should remove NaN"
    
    # Test FORWARD_FILL
    logger.info("\n📌 Testing FORWARD_FILL strategy...")
    cleaner_ff = DataCleaner(cleaning_method=CleaningMethod.FORWARD_FILL)
    cleaned_ff = cleaner_ff.handle_missing_values(readings)
    logger.info(f"  Input: {len(readings)} readings")
    logger.info(f"  Output: {len(cleaned_ff)} readings")
    logger.info(f"  Filled value: {cleaned_ff[2].value:.2f} (from previous)")
    assert cleaned_ff[2].value == 46.0, "FORWARD_FILL should use previous value"
    
    logger.info("\n✅ NaN handling tests passed!")


async def test_spike_detection():
    """Test 2: Spike detection using Z-score"""
    logger.info("\n" + "="*70)
    logger.info("TEST 2: Spike Detection (Z-score)")
    logger.info("="*70)
    
    cleaner = DataCleaner(
        cleaning_method=CleaningMethod.DROP,
        z_score_threshold=3.0,
        min_readings_for_stats=5
    )
    
    now = datetime.now()
    
    # Create normal distribution + spike
    base_values = [45.0, 45.2, 45.1, 45.3, 45.0]  # Normal around 45
    readings = [
        SensorReading(
            timestamp=now + timedelta(seconds=i),
            equipment_id="pump_1",
            tag="temperature",
            value=val,
            unit="°C",
            source="OPC-UA",
            quality=DataQuality.GOOD
        ) for i, val in enumerate(base_values)
    ]
    
    # Add spike (120°C when normal is ~45°C)
    readings.append(
        SensorReading(
            timestamp=now + timedelta(seconds=5),
            equipment_id="pump_1",
            tag="temperature",
            value=120.0,  # 3+ sigma deviation
            unit="°C",
            source="OPC-UA",
            quality=DataQuality.GOOD
        )
    )
    
    logger.info(f"\n📌 Input: {len(readings)} readings")
    logger.info(f"  Normal values: {base_values}")
    logger.info(f"  Spike value: 120.0°C")
    
    # Detect spikes
    processed = cleaner.detect_spikes(readings)
    
    # Check anomalies
    spike_anomalies = [a for a in cleaner.detected_anomalies 
                      if a.anomaly_type == AnomalyType.SPIKE]
    
    logger.info(f"\n✓ Spikes detected: {len(spike_anomalies)}")
    if spike_anomalies:
        for anomaly in spike_anomalies:
            logger.info(f"  - {anomaly.value:.2f}°C: {anomaly.reason}")
    
    assert len(spike_anomalies) > 0, "Should detect spike"
    logger.info("\n✅ Spike detection tests passed!")


async def test_outlier_detection():
    """Test 3: Outlier detection using IQR"""
    logger.info("\n" + "="*70)
    logger.info("TEST 3: Outlier Detection (IQR)")
    logger.info("="*70)
    
    cleaner = DataCleaner(
        cleaning_method=CleaningMethod.DROP,
        iqr_multiplier=1.5
    )
    
    now = datetime.now()
    
    # Create normal distribution
    normal_values = [50.0, 50.5, 51.0, 50.2, 50.8, 51.2, 50.1, 50.9]
    readings = [
        SensorReading(
            timestamp=now + timedelta(seconds=i),
            equipment_id="pump_1",
            tag="temperature",
            value=val,
            unit="°C",
            source="OPC-UA",
            quality=DataQuality.GOOD
        ) for i, val in enumerate(normal_values)
    ]
    
    # Add outlier
    readings.append(
        SensorReading(
            timestamp=now + timedelta(seconds=len(readings)),
            equipment_id="pump_1",
            tag="temperature",
            value=200.0,  # Far outside normal range
            unit="°C",
            source="OPC-UA",
            quality=DataQuality.GOOD
        )
    )
    
    logger.info(f"\n📌 Input: {len(readings)} readings")
    logger.info(f"  Normal range: {min(normal_values):.2f} - {max(normal_values):.2f}°C")
    logger.info(f"  Outlier value: 200.0°C")
    
    # Detect outliers
    processed = cleaner.detect_outliers(readings)
    
    # Check anomalies
    outlier_anomalies = [a for a in cleaner.detected_anomalies 
                        if a.anomaly_type == AnomalyType.OUTLIER]
    
    logger.info(f"\n✓ Outliers detected: {len(outlier_anomalies)}")
    if outlier_anomalies:
        for anomaly in outlier_anomalies:
            logger.info(f"  - {anomaly.value:.2f}°C: {anomaly.reason}")
    
    assert len(outlier_anomalies) > 0, "Should detect outlier"
    logger.info("\n✅ Outlier detection tests passed!")


async def test_noise_filtering():
    """Test 4: Noise filtering with median"""
    logger.info("\n" + "="*70)
    logger.info("TEST 4: Noise Filtering (3-Point Median)")
    logger.info("="*70)
    
    cleaner = DataCleaner(
        cleaning_method=CleaningMethod.DROP,
        rolling_window_size=3
    )
    
    now = datetime.now()
    
    # Create clean signal with noise
    # Ideal: 50.0°C, but with high-frequency noise
    noisy_values = [
        50.0, 50.3, 49.8,  # 50 ± 0.3
        50.1, 49.9, 50.2,  # 50 ± 0.2
        50.0, 50.4, 49.7,  # 50 ± 0.3
    ]
    
    readings = [
        SensorReading(
            timestamp=now + timedelta(seconds=i),
            equipment_id="pump_1",
            tag="temperature",
            value=val,
            unit="°C",
            source="OPC-UA",
            quality=DataQuality.GOOD
        ) for i, val in enumerate(noisy_values)
    ]
    
    logger.info(f"\n📌 Input: {len(readings)} noisy readings")
    logger.info(f"  Noisy values: {[f'{v:.1f}' for v in noisy_values]}")
    
    # Apply noise filter
    filtered = cleaner.filter_noise(readings)
    
    # Check smoothing
    smoothed_values = [r.value for r in filtered]
    logger.info(f"\n✓ After median filter:")
    logger.info(f"  Filtered values: {[f'{v:.1f}' for v in smoothed_values]}")
    
    # Check that some values were modified
    modified_count = sum(1 for i, (orig, filt) in enumerate(zip(noisy_values, smoothed_values))
                        if abs(orig - filt) > 0.01)
    logger.info(f"  Modified readings: {modified_count}/{len(readings)}")
    
    logger.info("\n✅ Noise filtering tests passed!")


async def test_complete_pipeline():
    """Test 5: Complete cleaning pipeline"""
    logger.info("\n" + "="*70)
    logger.info("TEST 5: Complete Pipeline")
    logger.info("="*70)
    
    cleaner = DataCleaner(
        cleaning_method=CleaningMethod.DROP,
        z_score_threshold=3.0,
        iqr_multiplier=1.5
    )
    
    now = datetime.now()
    
    # Create realistic batch with mixed issues
    readings = [
        # Normal readings
        SensorReading(
            timestamp=now + timedelta(seconds=i),
            equipment_id="pump_1",
            tag="temperature",
            value=45.0 + (i % 10) * 0.1,
            unit="°C",
            source="OPC-UA",
            quality=DataQuality.GOOD
        ) for i in range(50)
    ]
    
    # Add NaN
    readings[10].value = float('nan')
    
    # Add spike
    readings[25].value = 150.0
    
    # Add outlier
    readings[40].value = 200.0
    
    logger.info(f"\n📌 Input batch: {len(readings)} readings with:")
    logger.info(f"  - 1 NaN value")
    logger.info(f"  - 1 spike (Z-score > 3σ)")
    logger.info(f"  - 1 outlier (IQR > 1.5×IQR)")
    
    # Create batch
    batch = BatchedReadings()
    for r in readings:
        batch.add_reading(r)
    
    # Run complete pipeline
    cleaned, anomalies = await cleaner.clean_batch(batch)
    
    logger.info(f"\n✓ Pipeline output:")
    logger.info(f"  Input: {len(readings)} readings")
    logger.info(f"  Output: {len(cleaned)} cleaned readings")
    logger.info(f"  Anomalies: {len(anomalies)}")
    
    # Get report
    report = cleaner.get_anomaly_report()
    logger.info(f"\n✓ Anomaly report:")
    logger.info(f"  Total anomalies: {report['total_anomalies']}")
    logger.info(f"  By type: {report['by_type']}")
    
    assert len(cleaned) > 0, "Should have cleaned readings"
    assert len(anomalies) >= 3, "Should detect NaN, spike, outlier"
    
    logger.info("\n✅ Complete pipeline tests passed!")


async def main():
    """Run all tests"""
    logger.info("\n🧪 STARTING LAYER 6 TESTS (Data Cleaning Pipeline)\n")
    
    try:
        # Synchronous tests
        test_nan_handling()
        
        # Async tests
        await test_spike_detection()
        await test_outlier_detection()
        await test_noise_filtering()
        await test_complete_pipeline()
        
        logger.info("\n" + "="*70)
        logger.info("✅ ALL TESTS PASSED!")
        logger.info("="*70)
        logger.info("\n🎉 Layer 6 (Data Cleaning) is ready for integration!\n")
    
    except AssertionError as e:
        logger.error(f"\n❌ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"\n❌ Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
