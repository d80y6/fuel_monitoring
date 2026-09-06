"""
Flow Rate Calculator

This module provides the FlowRateCalculator class for calculating flow rates.
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any, Union, Deque
from enum import Enum, auto
from collections import deque

logger = logging.getLogger(__name__)

class FlowState(Enum):
    """Represents the current state of the flow system."""
    NORMAL = auto()
    REFILL = auto()
    STABLE = auto()
    HIGH_OUTFLOW = auto()  # New state for high outflow detection

class FlowRateCalculator:
    """Calculate flow rates based on volume changes over time.
    
    Example:
        calculator = FlowRateCalculator()
        calculator.add_measurement(100.0)  # Initial volume
        # Wait a minute
        flow_rate = calculator.add_measurement(90.0)  # Volume decreased by 10L
        print(f"Current flow rate: {flow_rate} L/min")  # Should show around -10 L/min
        
        # Get statistics
        stats = calculator.get_statistics()
        print(f"Total outflow: {stats['total_outflow']} L")
    """
    
    # Constants for thresholds and factors
    STABILITY_THRESHOLD_REFILL = 2.0
    STABILITY_THRESHOLD_NORMAL = 0.5
    STABILITY_THRESHOLD_HIGH_OUTFLOW = 1.0  # New constant for high outflow
    DECAY_FACTOR_REFILL = 0.9
    DECAY_FACTOR_NORMAL = 0.5
    DECAY_FACTOR_HIGH_OUTFLOW = 0.8  # New constant for high outflow
    SMOOTHING_FACTOR_REFILL = 0.7
    SMOOTHING_FACTOR_NORMAL = 0.5
    SMOOTHING_FACTOR_HIGH_OUTFLOW = 0.8  # New constant for high outflow
    MIN_SIGNIFICANT_CHANGE_REFILL = 20.0
    MIN_SIGNIFICANT_CHANGE_NORMAL = 2.0  # Reduced from 5.0 to detect smaller changes
    MIN_SIGNIFICANT_CHANGE_HIGH_OUTFLOW = 1.0  # Very sensitive for fuel dispensing
    STABLE_COUNT_THRESHOLD = 3
    MIN_FLOW_RATE_THRESHOLD = 1.0
    MIN_TIME_DIFF_SECONDS = 5  # Minimum time difference for accurate calculation
    
    def __init__(
        self, 
        max_history_points: int = 5,
        min_significant_change: float = 5.0,
        smoothing_factor: float = 0.5,
        expected_max_inflow_rate: float = 600.0,   # Maximum refill rate (positive)
        expected_max_outflow_rate: float = 100.0,  # Maximum consumption rate (negative)
        refill_detection_threshold: float = 100.0, # Threshold to detect refill operations
        high_outflow_threshold: float = 40.0,      # Threshold to detect high outflow
        tank_type: str = "fuel"                    # Type of tank for specialized behavior
    ) -> None:
        """
        Initialize the flow rate calculator with configurable parameters.
        
        Args:
            max_history_points: Maximum number of history points to keep
            min_significant_change: Minimum volume change to consider significant (liters)
            smoothing_factor: Factor for exponential smoothing (0-1)
            expected_max_inflow_rate: Expected maximum inflow rate in L/min (positive)
            expected_max_outflow_rate: Expected maximum outflow rate in L/min (positive value)
            refill_detection_threshold: Flow rate threshold to detect refill operations (L/min)
            high_outflow_threshold: Flow rate threshold to detect high outflow (L/min)
            tank_type: Type of tank for specialized behavior ("fuel", "water", etc.)
        """
        # Input validation
        if max_history_points <= 1:
            raise ValueError("max_history_points must be greater than 1")
        if not 0 <= smoothing_factor <= 1:
            raise ValueError("smoothing_factor must be between 0 and 1")
        if min_significant_change < 0:
            raise ValueError("min_significant_change must be non-negative")
            
        self.max_history_points = max_history_points
        self.min_significant_change = min_significant_change
        self.smoothing_factor = smoothing_factor
        self.expected_max_inflow_rate = expected_max_inflow_rate
        self.expected_max_outflow_rate = expected_max_outflow_rate
        self.refill_detection_threshold = refill_detection_threshold
        self.high_outflow_threshold = high_outflow_threshold
        self.tank_type = tank_type
        
        # Initialize data structures
        self.history: Deque[Tuple[datetime, float]] = deque(maxlen=max_history_points)
        self.current_flow_rate = 0.0
        self.max_inflow_rate = 0.0
        self.max_outflow_rate = 0.0
        self.total_inflow = 0.0
        self.total_outflow = 0.0
        self.last_flow_rate = None
        self.last_volume = None
        self.flow_state = FlowState.NORMAL
        self.stable_volume_counter = 0
        self.flow_rate_confidence = 0.0
        
        # Adjust parameters based on tank type
        if tank_type == "fuel":
            # Fuel tanks need faster response for dispensing
            self.stable_count_threshold = 2  # Faster stabilization
        else:
            # Default values for other tank types
            self.stable_count_threshold = self.STABLE_COUNT_THRESHOLD
        
        logger.info(f"FlowRateCalculator initialized with max_inflow={expected_max_inflow_rate}L/min, "
                   f"max_outflow={expected_max_outflow_rate}L/min, tank_type={tank_type}")

    def add_measurement(self, volume: float, timestamp: Optional[datetime] = None) -> float:
        """
        Add a new measurement and calculate flow rate
        
        Args:
            volume: Current volume in liters
            timestamp: Current timestamp or None for now
            
        Returns:
            float: Current flow rate in liters per minute (positive for inflow, negative for outflow)
        """
        # Data validation
        if volume < 0:
            logger.warning(f"Negative volume measurement received: {volume}L")
            volume = 0.0
            
        if timestamp is None:
            timestamp = datetime.now()
        
        # Check for outliers if we have history
        if self.history and self._is_outlier(volume):
            logger.warning(f"Outlier volume detected: {volume}L, using previous value")
            if self.last_volume is not None:
                volume = self.last_volume  # Use previous value instead
        
        self._check_volume_stability(volume)
        self._update_history(volume, timestamp)
        self._update_total_flow()
        
        # Need at least two points to calculate flow rate
        if len(self.history) < 2:
            return 0.0
        
        # If volume is stable and not in special modes, force flow rate to zero after several readings
        if self._should_return_zero_flow_rate():
            self.current_flow_rate = 0.0
            return 0.0
        
        return self._calculate_flow_rate()
    
    def _is_outlier(self, volume: float) -> bool:
        """Detect if a volume measurement is an outlier."""
        if len(self.history) < 3:
            return False
            
        # Get recent volumes
        recent_volumes = [item[1] for item in self.history]
        
        # Calculate median and median absolute deviation (MAD)
        median = sorted(recent_volumes)[len(recent_volumes) // 2]
        deviations = [abs(v - median) for v in recent_volumes]
        mad = sorted(deviations)[len(deviations) // 2]
        
        # If MAD is too small, use a minimum value to avoid division by zero
        mad = max(mad, 0.1)
        
        # Calculate modified z-score
        z_score = 0.6745 * abs(volume - median) / mad
        
        # Typically, z-score > 3.5 is considered an outlier
        # For fuel dispensing, we use a higher threshold to allow for rapid changes
        outlier_threshold = 5.0 if self.flow_state == FlowState.HIGH_OUTFLOW else 3.5
        
        return z_score > outlier_threshold
    
    def _check_volume_stability(self, volume: float) -> None:
        """Check if volume is stable compared to last reading."""
        if self.last_volume is None:
            self.last_volume = volume
            return
            
        volume_diff = abs(volume - self.last_volume)
        
        # Different stability threshold based on flow state
        if self.flow_state == FlowState.REFILL:
            stability_threshold = self.STABILITY_THRESHOLD_REFILL
        elif self.flow_state == FlowState.HIGH_OUTFLOW:
            stability_threshold = self.STABILITY_THRESHOLD_HIGH_OUTFLOW
        else:
            stability_threshold = self.STABILITY_THRESHOLD_NORMAL
        
        if volume_diff < stability_threshold:
            self.stable_volume_counter += 1
            logger.debug(f"Stable volume detected: {volume:.1f}L (diff: {volume_diff:.2f}L, counter: {self.stable_volume_counter})")
        else:
            self.stable_volume_counter = 0
            logger.debug(f"Volume change detected: {volume:.1f}L (diff: {volume_diff:.2f}L)")
            
        self.last_volume = volume
    
    def _update_history(self, volume: float, timestamp: datetime) -> None:
        """Add current reading to history."""
        self.history.append((timestamp, volume))
    
    def _update_total_flow(self) -> None:
        """Track actual volume changes with improved fuel dispensing detection."""
        if len(self.history) < 2:
            return
            
        prev_timestamp, prev_volume = list(self.history)[-2]
        curr_timestamp, curr_volume = list(self.history)[-1]
        
        actual_volume_change = curr_volume - prev_volume
        time_diff_seconds = (curr_timestamp - prev_timestamp).total_seconds()
        
        # Calculate instantaneous flow rate for detection purposes
        instantaneous_rate = 0
        if time_diff_seconds > 0:
            instantaneous_rate = (actual_volume_change / time_diff_seconds) * 60  # L/min
        
        # Special handling for fuel dispensing (high negative flow rates)
        if instantaneous_rate < -self.high_outflow_threshold:  # High outflow
            # This is likely active dispensing - use lower threshold
            significant_change_threshold = self.MIN_SIGNIFICANT_CHANGE_HIGH_OUTFLOW
        elif instantaneous_rate > self.refill_detection_threshold:  # High inflow
            # This is likely refilling - use higher threshold
            significant_change_threshold = self.MIN_SIGNIFICANT_CHANGE_REFILL
        else:
            # Normal operation - use standard threshold
            significant_change_threshold = self.MIN_SIGNIFICANT_CHANGE_NORMAL
        
        # Track inflow/outflow with appropriate thresholds
        if actual_volume_change > significant_change_threshold:
            self.total_inflow += actual_volume_change
            logger.info(f"Inflow detected: {actual_volume_change:.1f}L")
        elif actual_volume_change < -significant_change_threshold:
            self.total_outflow += abs(actual_volume_change)
            
            # Log with different levels based on flow rate
            if instantaneous_rate < -self.high_outflow_threshold:
                logger.info(f"High-rate fuel dispensing detected: {abs(actual_volume_change):.1f}L " 
                           f"at approximately {abs(instantaneous_rate):.1f}L/min")
            else:
                logger.info(f"Outflow detected: {abs(actual_volume_change):.1f}L")
    
    def _should_return_zero_flow_rate(self) -> bool:
        """Determine if flow rate should be forced to zero."""
        # Don't force zero during special modes
        if self.flow_state == FlowState.REFILL or self.flow_state == FlowState.HIGH_OUTFLOW:
            return False
            
        # Force zero if volume has been stable for several readings
        return self.stable_volume_counter >= self.stable_count_threshold
    
    def _calculate_flow_rate(self) -> float:
        """Calculate the current flow rate based on recent measurements."""
        latest = list(self.history)[-1]
        previous = list(self.history)[-2]
        
        # Calculate time difference in seconds and minutes
        time_diff_seconds = (latest[0] - previous[0]).total_seconds()
        time_diff_minutes = time_diff_seconds / 60
        
        # For very short intervals, we need special handling
        if time_diff_seconds < self.MIN_TIME_DIFF_SECONDS:
            # For very rapid readings, use the last known good flow rate
            # unless there's a significant volume change
            vol_diff = latest[1] - previous[1]
            
            # If we're in high outflow mode, use a lower threshold
            min_change = (self.MIN_SIGNIFICANT_CHANGE_HIGH_OUTFLOW 
                         if self.flow_state == FlowState.HIGH_OUTFLOW 
                         else 2.0)
                         
            if abs(vol_diff) < min_change:
                return self.current_flow_rate  # Return last calculated rate
        
        # Calculate volume difference
        vol_diff = latest[1] - previous[1]
        
        # Calculate raw flow rate
        if time_diff_minutes > 0:
            raw_flow_rate = vol_diff / time_diff_minutes
        else:
            return self._handle_no_significant_change()
        
        # Calculate confidence based on time difference and volume change
        time_confidence = min(1.0, time_diff_seconds / 60.0)  # Higher confidence with longer time intervals
        volume_confidence = min(1.0, abs(vol_diff) / (5.0 * self.min_significant_change))
        self.flow_rate_confidence = time_confidence * volume_confidence
        
        # Check for flow state changes
        self._update_flow_state(raw_flow_rate)
        
        # Use different significant change thresholds based on flow state
        if self.flow_state == FlowState.REFILL:
            significant_change = self.MIN_SIGNIFICANT_CHANGE_REFILL
        elif self.flow_state == FlowState.HIGH_OUTFLOW:
            significant_change = self.MIN_SIGNIFICANT_CHANGE_HIGH_OUTFLOW
        else:
            significant_change = self.MIN_SIGNIFICANT_CHANGE_NORMAL
        
        # Only calculate if volume change is significant
        if abs(vol_diff) >= significant_change:
            return self._process_significant_flow(raw_flow_rate, vol_diff, time_diff_minutes)
        else:
            return self._handle_no_significant_change()
    
    def _update_flow_state(self, raw_flow_rate: float) -> None:
        """Update flow state with special handling for high outflow rates."""
        # Detect refill mode (positive flow)
        if raw_flow_rate > self.refill_detection_threshold:
            if self.flow_state != FlowState.REFILL:
                self.flow_state = FlowState.REFILL
                logger.info(f"Entered refill mode: detected inflow rate of {raw_flow_rate:.1f}L/min")
        
        # Detect high outflow mode (negative flow)
        elif raw_flow_rate < -self.high_outflow_threshold:
            if self.flow_state != FlowState.HIGH_OUTFLOW:
                self.flow_state = FlowState.HIGH_OUTFLOW
                logger.info(f"Entered high outflow mode: detected outflow rate of {abs(raw_flow_rate):.1f}L/min")
        
        # Exit special modes if stable
        elif self.stable_volume_counter >= self.stable_count_threshold:
            if self.flow_state != FlowState.NORMAL:
                prev_state = self.flow_state
                self.flow_state = FlowState.NORMAL
                logger.info(f"Exited {prev_state.name.lower()} mode: volume stabilized")
    
    def _process_significant_flow(self, raw_flow_rate: float, vol_diff: float, time_diff: float) -> float:
        """Process flow rate with adaptive smoothing based on flow magnitude."""
        # Validate against expected maximum rates
        if raw_flow_rate > 0:  # Inflow (positive)
            if raw_flow_rate > self.expected_max_inflow_rate:
                logger.warning(
                    f"Unusually high inflow rate detected: {raw_flow_rate:.2f}L/min. "
                    f"Volume change: {vol_diff:.1f}L over {time_diff:.2f} minutes."
                )
                raw_flow_rate = min(raw_flow_rate, self.expected_max_inflow_rate)
        else:  # Outflow (negative)
            if abs(raw_flow_rate) > self.expected_max_outflow_rate:
                logger.warning(
                    f"Unusually high outflow rate detected: {raw_flow_rate:.2f}L/min. "
                    f"Volume change: {vol_diff:.1f}L over {time_diff:.2f} minutes."
                )
                raw_flow_rate = max(raw_flow_rate, -self.expected_max_outflow_rate)
        
        # Determine appropriate smoothing factor based on flow state and magnitude
        if self.flow_state == FlowState.REFILL:
            smoothing = self.SMOOTHING_FACTOR_REFILL
        elif self.flow_state == FlowState.HIGH_OUTFLOW:
            # Less smoothing for high outflow to be more responsive
            smoothing = self.SMOOTHING_FACTOR_HIGH_OUTFLOW
        else:
            # Adaptive smoothing based on flow rate magnitude
            # Higher flow rates get less smoothing for faster response
            flow_magnitude = abs(raw_flow_rate)
            if flow_magnitude > 40.0:  # High flow
                smoothing = 0.7
            elif flow_magnitude > 20.0:  # Medium flow
                smoothing = 0.6
            else:  # Low flow
                smoothing = self.smoothing_factor
        
        # Apply smoothing if we have a previous flow rate
        if self.last_flow_rate is not None:
            flow_rate = (smoothing * raw_flow_rate) + ((1 - smoothing) * self.last_flow_rate)
        else:
            flow_rate = raw_flow_rate
        
        self.last_flow_rate = flow_rate
        
        # Update max rates
        if flow_rate > 0:  # Inflow (positive)
            self.max_inflow_rate = max(self.max_inflow_rate, flow_rate)
        else:  # Outflow (negative)
            self.max_outflow_rate = max(self.max_outflow_rate, abs(flow_rate))
            
        self.current_flow_rate = flow_rate
        return round(flow_rate, 2)
    
    def _handle_no_significant_change(self) -> float:
        """Handle cases where there's no significant change in volume."""
        # If volume is stable but we haven't reached the threshold yet, decay the flow rate
        if self.last_flow_rate is not None and abs(self.last_flow_rate) > 0:
            # Select decay factor based on flow state
            if self.flow_state == FlowState.REFILL:
                decay_factor = self.DECAY_FACTOR_REFILL
            elif self.flow_state == FlowState.HIGH_OUTFLOW:
                decay_factor = self.DECAY_FACTOR_HIGH_OUTFLOW
            else:
                decay_factor = self.DECAY_FACTOR_NORMAL
                
            decayed_rate = self.last_flow_rate * decay_factor
            
            # Only force to zero in normal mode and if rate is very small
            if (abs(decayed_rate) < self.MIN_FLOW_RATE_THRESHOLD and 
                self.flow_state != FlowState.REFILL and 
                self.flow_state != FlowState.HIGH_OUTFLOW):
                self.current_flow_rate = 0.0
            else:
                self.current_flow_rate = decayed_rate
                
            self.last_flow_rate = self.current_flow_rate
        else:
            self.current_flow_rate = 0.0
        
        return round(self.current_flow_rate, 2)
    
    def get_statistics(self) -> Dict[str, float]:
        """
        Get flow rate statistics.
        
        Returns:
            dict: Dictionary with flow rate statistics
        """
        return {
            'current_flow_rate': round(self.current_flow_rate, 2),
            'max_inflow_rate': round(self.max_inflow_rate, 2),
            'max_outflow_rate': round(self.max_outflow_rate, 2),
            'total_inflow': round(self.total_inflow, 1),
            'total_outflow': round(self.total_outflow, 1),
            'flow_rate_confidence': round(self.flow_rate_confidence, 2)
        }
    
    def reset_statistics(self) -> bool:
        """Reset flow rate statistics."""
        self.history.clear()
        self.current_flow_rate = 0.0
        self.max_inflow_rate = 0.0
        self.max_outflow_rate = 0.0
        self.total_inflow = 0.0
        self.total_outflow = 0.0
        self.last_flow_rate = None
        self.last_volume = None
        self.stable_volume_counter = 0
        self.flow_state = FlowState.NORMAL
        self.flow_rate_confidence = 0.0
        logger.info("Flow rate statistics reset")
        return True
