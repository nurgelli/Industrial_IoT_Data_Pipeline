"""
LAYER 6: Data Cleaning Pipeline.

Purpose:
  Clean and validate sensor readings before database storage:
  1. NaN/missing value handling (drop, forward-fill, backward-fill)
  2. Spike detection using Z-score (threshold: 3σ)
  3. Noise filtering with 3-point rolling median
  4. Outlier detection using IQR (interquartile range)
  5. Anomaly logging to dedicated structure

Author: SCADA Team
Date: May 8, 2026
"""

import asyncio
import logging
import math
import statistics
from typing import List, Optional, Callable, Dict, Any
from datetime import datetime
from enum import Enum
from collections import deque

from src.layer3_python_bridge.data_model import SensorReading, BatchedReadings, DataQuality


# ============================================================================
# ENUMS & CONSTANTS
# ============================================================================

class CleaningMethod(Enum):
    """NaN handling strategies"""
    DROP = "drop"                    # Remove row
    FORWARD_FILL = "forward_fill"    # Use previous value
    BACKWARD_FILL = "backward_fill"  # Use next value
    INTERPOLATE = "interpolate"      # Linear interpolation


class AnomalyType(Enum):
    """Anomaly classification"""
    SPIKE = "spike"                  # Z-score > 3σ
    OUTLIER = "outlier"              # IQR > 1.5×IQR
    NAN = "nan"                      # Missing value
    NOISE = "noise"                  # High frequency variation


class AnomalyRecord:
    """
    Represents a detected anomaly for logging.
    
    Attributes:
        timestamp: When anomaly occurred
        equipment_id: Source equipment
        tag: Source tag
        anomaly_type: Type of anomaly
        value: Original value (may be NaN)
        reason: Human-readable explanation
        cleaning_action: What was done (e.g., "removed", "interpolated")
    """
    
    def __init__(
        self,
        timestamp: datetime,
        equipment_id: str,
        tag: str,
        anomaly_type: AnomalyType,
        value: Optional[float],
        reason: str,
        cleaning_action: str
    ):
        self.timestamp = timestamp
        self.equipment_id = equipment_id
        self.tag = tag
        self.anomaly_type = anomaly_type
        self.value = value
        self.reason = reason
        self.cleaning_action = cleaning_action
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/storage"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "equipment_id": self.equipment_id,
            "tag": self.tag,
            "anomaly_type": self.anomaly_type.value,
            "value": self.value,
            "reason": self.reason,
            "cleaning_action": self.cleaning_action
        }


# ============================================================================
# DATA CLEANER CLASS
# ============================================================================

class DataCleaner:
    """
    Comprehensive data cleaning and validation.
    
    Configuration (from settings.yaml):
    - cleaning_method: "drop" | "forward_fill" | "backward_fill" | "interpolate"
    - z_score_threshold: 3.0 (default)
    - iqr_multiplier: 1.5 (default)
    - rolling_window_size: 3 (for median filter)
    - min_readings_for_stats: 10 (minimum samples for Z-score calculation)
    """
    
    def __init__(
        self,
        cleaning_method: CleaningMethod = CleaningMethod.DROP,
        z_score_threshold: float = 3.0,
        iqr_multiplier: float = 1.5,
        rolling_window_size: int = 3,
        min_readings_for_stats: int = 10,
        logger: Optional[logging.Logger] = None
    ):
        self.cleaning_method = cleaning_method
        self.z_score_threshold = z_score_threshold
        self.iqr_multiplier = iqr_multiplier
        self.rolling_window_size = rolling_window_size
        self.min_readings_for_stats = min_readings_for_stats
        
        self.logger = logger or logging.getLogger(__name__)
        
        # Keep rolling window of values per (equipment_id, tag) for stats
        self.value_histories: Dict[tuple, deque] = {}
        
        # Store anomalies for reporting
        self.detected_anomalies: List[AnomalyRecord] = []
        
        # Callbacks for external handling
        self.on_anomaly_detected: Optional[Callable[[AnomalyRecord], None]] = None
    
    # ========================================================================
    # NaN / MISSING VALUE HANDLING
    # ========================================================================
    
    def handle_missing_values(
        self,
        readings: List[SensorReading]
    ) -> List[SensorReading]:
        """
        Handle NaN/missing values according to configured strategy.
        
        Args:
            readings: List of potentially NaN-containing readings
            
        Returns:
            Cleaned readings (possibly fewer if DROP method)
        """
        cleaned = []
        
        for i, reading in enumerate(readings):
            if math.isnan(reading.value):
                # Log anomaly
                anomaly = AnomalyRecord(
                    timestamp=reading.timestamp,
                    equipment_id=reading.equipment_id,
                    tag=reading.tag,
                    anomaly_type=AnomalyType.NAN,
                    value=None,
                    reason="Missing sensor value (NaN)",
                    cleaning_action=self.cleaning_method.value
                )
                self.detected_anomalies.append(anomaly)
                if self.on_anomaly_detected:
                    self.on_anomaly_detected(anomaly)
                
                # Handle according to method
                if self.cleaning_method == CleaningMethod.DROP:
                    self.logger.warning(
                        f"Dropping NaN reading: {reading.equipment_id}.{reading.tag}"
                    )
                    continue
                
                elif self.cleaning_method == CleaningMethod.FORWARD_FILL:
                    if cleaned:  # Use previous value
                        reading.value = cleaned[-1].value
                        reading.metadata = {"filled": "forward_fill"}
                        self.logger.info(
                            f"Forward-filled NaN: {reading.equipment_id}.{reading.tag} = {reading.value}"
                        )
                    else:
                        # No previous value, skip
                        continue
                
                elif self.cleaning_method == CleaningMethod.BACKWARD_FILL:
                    # Look ahead for next non-NaN value
                    next_val = None
                    for j in range(i + 1, len(readings)):
                        if not math.isnan(readings[j].value):
                            next_val = readings[j].value
                            break
                    
                    if next_val is not None:
                        reading.value = next_val
                        reading.metadata = {"filled": "backward_fill"}
                        self.logger.info(
                            f"Backward-filled NaN: {reading.equipment_id}.{reading.tag} = {reading.value}"
                        )
                    else:
                        # No future value, skip
                        continue
            
            cleaned.append(reading)
        
        return cleaned
    
    # ========================================================================
    # SPIKE DETECTION (Z-SCORE)
    # ========================================================================
    
    def detect_spikes(
        self,
        readings: List[SensorReading]
    ) -> List[SensorReading]:
        """
        Detect spikes using Z-score method (> 3σ from mean).
        
        Args:
            readings: Cleaned readings
            
        Returns:
            Same readings (marked with quality flags if spike detected)
        """
        # Group by (equipment_id, tag)
        groups = {}
        for reading in readings:
            key = (reading.equipment_id, reading.tag)
            if key not in groups:
                groups[key] = []
            groups[key].append(reading)
        
        # Analyze each group
        processed = []
        for (eq_id, tag), group_readings in groups.items():
            key = (eq_id, tag)
            
            # Update rolling history
            if key not in self.value_histories:
                self.value_histories[key] = deque(maxlen=50)
            
            for reading in group_readings:
                self.value_histories[key].append(reading.value)
            
            # Only check if enough history
            if len(self.value_histories[key]) < self.min_readings_for_stats:
                processed.extend(group_readings)
                continue
            
            # Calculate statistics
            values = list(self.value_histories[key])
            mean = statistics.mean(values)
            stdev = statistics.stdev(values) if len(values) > 1 else 0
            
            # Check each reading for spike
            for reading in group_readings:
                if stdev > 0:
                    z_score = abs((reading.value - mean) / stdev)
                    
                    if z_score > self.z_score_threshold:
                        # Spike detected!
                        anomaly = AnomalyRecord(
                            timestamp=reading.timestamp,
                            equipment_id=eq_id,
                            tag=tag,
                            anomaly_type=AnomalyType.SPIKE,
                            value=reading.value,
                            reason=f"Z-score spike: {z_score:.2f}σ (threshold: {self.z_score_threshold}σ)",
                            cleaning_action="flagged_uncertain"
                        )
                        self.detected_anomalies.append(anomaly)
                        if self.on_anomaly_detected:
                            self.on_anomaly_detected(anomaly)
                        
                        # Mark as UNCERTAIN quality
                        reading.quality = DataQuality.UNCERTAIN
                        reading.metadata = {
                            "z_score": z_score,
                            "mean": mean,
                            "stdev": stdev,
                            "spike_detected": True
                        }
                        
                        self.logger.warning(
                            f"Spike detected: {eq_id}.{tag} = {reading.value:.2f} (z={z_score:.2f})"
                        )
                
                processed.append(reading)
        
        return processed
    
    # ========================================================================
    # OUTLIER DETECTION (IQR METHOD)
    # ========================================================================
    
    def detect_outliers(
        self,
        readings: List[SensorReading]
    ) -> List[SensorReading]:
        """
        Detect outliers using Interquartile Range (IQR) method.
        
        Outlier if: value < Q1 - 1.5×IQR or value > Q3 + 1.5×IQR
        
        Args:
            readings: Readings (possibly with spike flags)
            
        Returns:
            Same readings (marked with quality flags if outlier)
        """
        # Group by (equipment_id, tag)
        groups = {}
        for reading in readings:
            key = (reading.equipment_id, reading.tag)
            if key not in groups:
                groups[key] = []
            groups[key].append(reading)
        
        processed = []
        for (eq_id, tag), group_readings in groups.items():
            key = (eq_id, tag)
            
            if len(group_readings) < 4:
                # Not enough for meaningful Q1/Q3
                processed.extend(group_readings)
                continue
            
            # Calculate quartiles
            values = sorted([r.value for r in group_readings])
            n = len(values)
            q1_idx = n // 4
            q3_idx = 3 * n // 4
            
            q1 = values[q1_idx]
            q3 = values[q3_idx]
            iqr = q3 - q1
            
            lower_bound = q1 - self.iqr_multiplier * iqr
            upper_bound = q3 + self.iqr_multiplier * iqr
            
            # Check each reading
            for reading in group_readings:
                if reading.value < lower_bound or reading.value > upper_bound:
                    # Outlier!
                    anomaly = AnomalyRecord(
                        timestamp=reading.timestamp,
                        equipment_id=eq_id,
                        tag=tag,
                        anomaly_type=AnomalyType.OUTLIER,
                        value=reading.value,
                        reason=f"IQR outlier: {reading.value:.2f} outside [{lower_bound:.2f}, {upper_bound:.2f}]",
                        cleaning_action="flagged_uncertain"
                    )
                    self.detected_anomalies.append(anomaly)
                    if self.on_anomaly_detected:
                        self.on_anomaly_detected(anomaly)
                    
                    # Mark as UNCERTAIN quality (unless already BAD from spike)
                    if reading.quality != DataQuality.BAD:
                        reading.quality = DataQuality.UNCERTAIN
                    
                    reading.metadata = reading.metadata or {}
                    reading.metadata.update({
                        "q1": q1,
                        "q3": q3,
                        "iqr": iqr,
                        "lower_bound": lower_bound,
                        "upper_bound": upper_bound,
                        "outlier_detected": True
                    })
                    
                    self.logger.warning(
                        f"Outlier detected: {eq_id}.{tag} = {reading.value:.2f}"
                    )
                
                processed.append(reading)
        
        return processed
    
    # ========================================================================
    # NOISE FILTERING (3-POINT MEDIAN)
    # ========================================================================
    
    def filter_noise(
        self,
        readings: List[SensorReading]
    ) -> List[SensorReading]:
        """
        Apply 3-point rolling median filter to reduce noise.
        
        Only filters if:
        - Reading quality is still GOOD
        - Not a detected spike/outlier
        
        Args:
            readings: Readings with potential spike/outlier flags
            
        Returns:
            Same readings (values smoothed if noise filter applied)
        """
        # Group by (equipment_id, tag)
        groups = {}
        for i, reading in enumerate(readings):
            key = (reading.equipment_id, reading.tag)
            if key not in groups:
                groups[key] = []
            groups[key].append((i, reading))
        
        # Keep original order
        result = [None] * len(readings)
        
        for (eq_id, tag), indexed_readings in groups.items():
            values = [r[1].value for r in indexed_readings]
            
            # Apply 3-point median filter
            if len(values) >= 3:
                for j, (orig_idx, reading) in enumerate(indexed_readings):
                    # Skip if quality is not GOOD
                    if reading.quality != DataQuality.GOOD:
                        result[orig_idx] = reading
                        continue
                    
                    # Get 3-point window (center ± 1)
                    if j == 0:
                        window = values[0:2]  # First point: [0, 1]
                    elif j == len(values) - 1:
                        window = values[-2:]  # Last point: [n-2, n-1]
                    else:
                        window = values[j-1:j+2]  # Middle: [j-1, j, j+1]
                    
                    # Apply median
                    median_val = statistics.median(window)
                    
                    # Check if smoothing changed value significantly (> 10%)
                    if abs(median_val - reading.value) > abs(reading.value) * 0.1:
                        reading.value = median_val
                        reading.metadata = reading.metadata or {}
                        reading.metadata["noise_filtered"] = True
                        reading.metadata["original_value"] = values[j]
                        
                        self.logger.debug(
                            f"Noise filtered: {eq_id}.{tag} {values[j]:.2f} → {median_val:.2f}"
                        )
                    
                    result[orig_idx] = reading
            else:
                # Not enough for median filter
                for orig_idx, reading in indexed_readings:
                    result[orig_idx] = reading
        
        return result
    
    # ========================================================================
    # MAIN CLEANING PIPELINE
    # ========================================================================
    
    async def clean_batch(
        self,
        batch: BatchedReadings
    ) -> tuple[List[SensorReading], List[AnomalyRecord]]:
        """
        Run complete cleaning pipeline on a batch.
        
        Pipeline:
        1. Handle missing values (NaN)
        2. Detect spikes (Z-score)
        3. Detect outliers (IQR)
        4. Filter noise (3-point median)
        
        Args:
            batch: Batch of readings from MQTT consumer
            
        Returns:
            Tuple of (cleaned_readings, anomalies_detected)
        """
        self.logger.info(
            f"🧹 Starting cleaning pipeline on {len(batch.readings)} readings"
        )
        
        # Reset anomalies for this batch
        batch_anomalies = []
        
        # Step 1: Handle missing values
        readings = self.handle_missing_values(batch.readings)
        self.logger.info(f"  ✓ NaN handling: {len(batch.readings)} → {len(readings)} readings")
        
        # Step 2: Detect spikes
        readings = self.detect_spikes(readings)
        spike_count = sum(1 for a in self.detected_anomalies[-len(batch.readings):] 
                         if a.anomaly_type == AnomalyType.SPIKE)
        if spike_count > 0:
            self.logger.info(f"  ✓ Spike detection: {spike_count} spikes flagged")
        
        # Step 3: Detect outliers
        readings = self.detect_outliers(readings)
        outlier_count = sum(1 for a in self.detected_anomalies[-len(batch.readings):] 
                           if a.anomaly_type == AnomalyType.OUTLIER)
        if outlier_count > 0:
            self.logger.info(f"  ✓ Outlier detection: {outlier_count} outliers flagged")
        
        # Step 4: Filter noise
        readings = self.filter_noise(readings)
        self.logger.info(f"  ✓ Noise filtering: complete")
        
        # Collect batch-specific anomalies
        batch_anomalies = [
            a for a in self.detected_anomalies 
            if batch.readings[0].timestamp <= a.timestamp <= batch.readings[-1].timestamp
        ]
        
        self.logger.info(
            f"✅ Batch cleaning complete: {len(readings)} good readings, "
            f"{len(batch_anomalies)} anomalies detected"
        )
        
        return readings, batch_anomalies
    
    def get_anomaly_report(self) -> Dict[str, Any]:
        """Generate summary report of detected anomalies"""
        counts = {}
        for anomaly in self.detected_anomalies:
            type_name = anomaly.anomaly_type.value
            counts[type_name] = counts.get(type_name, 0) + 1
        
        return {
            "total_anomalies": len(self.detected_anomalies),
            "by_type": counts,
            "anomalies": [a.to_dict() for a in self.detected_anomalies[-100:]]  # Last 100
        }


# ============================================================================
# MAIN / TEST
# ============================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    
    logger = logging.getLogger(__name__)
    
    # Example usage
    cleaner = DataCleaner(
        cleaning_method=CleaningMethod.DROP,
        z_score_threshold=3.0,
        iqr_multiplier=1.5
    )
    
    # Create sample readings with anomalies
    now = datetime.now()
    samples = [
        SensorReading(
            timestamp=now,
            equipment_id="pump_1",
            tag="temperature",
            value=45.0,
            unit="°C",
            source="OPC-UA",
            quality=DataQuality.GOOD
        ),
        SensorReading(
            timestamp=now,
            equipment_id="pump_1",
            tag="temperature",
            value=45.5,
            unit="°C",
            source="OPC-UA",
            quality=DataQuality.GOOD
        ),
        SensorReading(
            timestamp=now,
            equipment_id="pump_1",
            tag="temperature",
            value=150.0,  # SPIKE!
            unit="°C",
            source="OPC-UA",
            quality=DataQuality.GOOD
        ),
    ]
    
    print("Sample readings created. Cleaner ready for STEP 5 integration.")
