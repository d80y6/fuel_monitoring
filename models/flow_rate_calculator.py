"""
Flow Rate Calculator

This module provides the FlowRateCalculator class for calculating flow rates.
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any, Union, Deque
from enum import Enum, auto
from collections import deque
from threading import Lock

logger = logging.getLogger(__name__)


class FlowState(Enum):
    """Represents the current state of the flow system."""
    NORMAL = auto()
    REFILL = auto()
    STABLE = auto()
    HIGH_OUTFLOW = auto()
    LEAK_DETECTED = auto()


class FlowRateCalculator:
    """Calculate flow rates based on volume changes over time.

    Thread-safe: all mutable state is protected by a lock.
    """

    # Constants for thresholds and factors
    STABILITY_THRESHOLD_REFILL = 2.0
    STABILITY_THRESHOLD_NORMAL = 0.5
    STABILITY_THRESHOLD_HIGH_OUTFLOW = 1.0
    DECAY_FACTOR_REFILL = 0.9
    DECAY_FACTOR_NORMAL = 0.5
    DECAY_FACTOR_HIGH_OUTFLOW = 0.8
    SMOOTHING_FACTOR_REFILL = 0.7
    SMOOTHING_FACTOR_NORMAL = 0.5
    SMOOTHING_FACTOR_HIGH_OUTFLOW = 0.8
    MIN_SIGNIFICANT_CHANGE_REFILL = 20.0
    MIN_SIGNIFICANT_CHANGE_NORMAL = 2.0
    MIN_SIGNIFICANT_CHANGE_HIGH_OUTFLOW = 1.0
    STABLE_COUNT_THRESHOLD = 3
    MIN_FLOW_RATE_THRESHOLD = 1.0
    MIN_TIME_DIFF_SECONDS = 5

    # Leak detection constants
    LEAK_FLOW_THRESHOLD = -5.0       # L/min sustained negative flow
    LEAK_SUSTAINED_COUNT = 5         # consecutive readings required

    def __init__(
        self,
        max_history_points=5,
        min_significant_change=5.0,
        smoothing_factor=0.5,
        expected_max_inflow_rate=600.0,
        expected_max_outflow_rate=100.0,
        refill_detection_threshold=100.0,
        high_outflow_threshold=40.0,
        tank_type="fuel"
    ):
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

        self.history = deque(maxlen=max_history_points)
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

        # Leak detection state
        self._leak_candidate_count = 0

        if tank_type == "fuel":
            self.stable_count_threshold = 2
        else:
            self.stable_count_threshold = self.STABLE_COUNT_THRESHOLD

        self._lock = Lock()

        logger.info(f"FlowRateCalculator initialized with max_inflow={expected_max_inflow_rate}L/min, "
                   f"max_outflow={expected_max_outflow_rate}L/min, tank_type={tank_type}")

    def add_measurement(self, volume, timestamp=None):
        """Add a new measurement and calculate flow rate (thread-safe)."""
        with self._lock:
            if volume < 0:
                logger.warning(f"Negative volume measurement received: {volume}L")
                volume = 0.0

            if timestamp is None:
                timestamp = datetime.now()

            if self.history and self._is_outlier(volume):
                logger.warning(f"Outlier volume detected: {volume}L, using previous value")
                if self.last_volume is not None:
                    volume = self.last_volume

            self._check_volume_stability(volume)
            self._update_history(volume, timestamp)
            self._update_total_flow()

            if len(self.history) < 2:
                return 0.0

            if self._should_return_zero_flow_rate():
                self.current_flow_rate = 0.0
                return 0.0

            return self._calculate_flow_rate()

    def _is_outlier(self, volume):
        """Detect if a volume measurement is an outlier."""
        if len(self.history) < 3:
            return False

        recent_volumes = [item[1] for item in self.history]

        median = sorted(recent_volumes)[len(recent_volumes) // 2]
        deviations = [abs(v - median) for v in recent_volumes]
        mad = sorted(deviations)[len(deviations) // 2]

        mad = max(mad, 0.1)

        z_score = 0.6745 * abs(volume - median) / mad

        outlier_threshold = 5.0 if self.flow_state == FlowState.HIGH_OUTFLOW else 3.5

        return z_score > outlier_threshold

    def _check_volume_stability(self, volume):
        """Check if volume is stable compared to last reading."""
        if self.last_volume is None:
            self.last_volume = volume
            return

        volume_diff = abs(volume - self.last_volume)

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

    def _update_history(self, volume, timestamp):
        """Add current reading to history."""
        self.history.append((timestamp, volume))

    def _update_total_flow(self):
        """Track actual volume changes with improved fuel dispensing detection."""
        if len(self.history) < 2:
            return

        prev_timestamp, prev_volume = self.history[-2]
        curr_timestamp, curr_volume = self.history[-1]

        actual_volume_change = curr_volume - prev_volume
        time_diff_seconds = (curr_timestamp - prev_timestamp).total_seconds()

        instantaneous_rate = 0
        if time_diff_seconds > 0:
            instantaneous_rate = (actual_volume_change / time_diff_seconds) * 60

        if instantaneous_rate < -self.high_outflow_threshold:
            significant_change_threshold = self.MIN_SIGNIFICANT_CHANGE_HIGH_OUTFLOW
        elif instantaneous_rate > self.refill_detection_threshold:
            significant_change_threshold = self.MIN_SIGNIFICANT_CHANGE_REFILL
        else:
            significant_change_threshold = self.MIN_SIGNIFICANT_CHANGE_NORMAL

        if actual_volume_change > significant_change_threshold:
            self.total_inflow += actual_volume_change
            logger.info(f"Inflow detected: {actual_volume_change:.1f}L")
        elif actual_volume_change < -significant_change_threshold:
            self.total_outflow += abs(actual_volume_change)

            if instantaneous_rate < -self.high_outflow_threshold:
                logger.info(f"High-rate fuel dispensing detected: {abs(actual_volume_change):.1f}L "
                           f"at approximately {abs(instantaneous_rate):.1f}L/min")
            else:
                logger.info(f"Outflow detected: {abs(actual_volume_change):.1f}L")

    def _should_return_zero_flow_rate(self):
        """Determine if flow rate should be forced to zero."""
        if self.flow_state in (FlowState.REFILL, FlowState.HIGH_OUTFLOW, FlowState.LEAK_DETECTED):
            return False

        return self.stable_volume_counter >= self.stable_count_threshold

    def _calculate_flow_rate(self):
        """Calculate the current flow rate based on recent measurements."""
        latest = self.history[-1]
        previous = self.history[-2]

        time_diff_seconds = (latest[0] - previous[0]).total_seconds()
        time_diff_minutes = time_diff_seconds / 60

        if time_diff_seconds < self.MIN_TIME_DIFF_SECONDS:
            vol_diff = latest[1] - previous[1]

            min_change = (self.MIN_SIGNIFICANT_CHANGE_HIGH_OUTFLOW
                         if self.flow_state == FlowState.HIGH_OUTFLOW
                         else 2.0)

            if abs(vol_diff) < min_change:
                return self.current_flow_rate

        vol_diff = latest[1] - previous[1]

        if time_diff_minutes > 0:
            raw_flow_rate = vol_diff / time_diff_minutes
        else:
            return self._handle_no_significant_change()

        time_confidence = min(1.0, time_diff_seconds / 60.0)
        volume_confidence = min(1.0, abs(vol_diff) / (5.0 * self.min_significant_change))
        self.flow_rate_confidence = time_confidence * volume_confidence

        self._update_flow_state(raw_flow_rate)
        self._check_leak_detection(raw_flow_rate)

        if self.flow_state == FlowState.REFILL:
            significant_change = self.MIN_SIGNIFICANT_CHANGE_REFILL
        elif self.flow_state == FlowState.HIGH_OUTFLOW:
            significant_change = self.MIN_SIGNIFICANT_CHANGE_HIGH_OUTFLOW
        else:
            significant_change = self.MIN_SIGNIFICANT_CHANGE_NORMAL

        if abs(vol_diff) >= significant_change:
            return self._process_significant_flow(raw_flow_rate, vol_diff, time_diff_minutes)
        else:
            return self._handle_no_significant_change()

    def _update_flow_state(self, raw_flow_rate):
        """Update flow state with special handling for high outflow rates."""
        if raw_flow_rate > self.refill_detection_threshold:
            if self.flow_state != FlowState.REFILL:
                self.flow_state = FlowState.REFILL
                logger.info(f"Entered refill mode: detected inflow rate of {raw_flow_rate:.1f}L/min")

        elif raw_flow_rate < -self.high_outflow_threshold:
            if self.flow_state != FlowState.HIGH_OUTFLOW:
                self.flow_state = FlowState.HIGH_OUTFLOW
                logger.info(f"Entered high outflow mode: detected outflow rate of {abs(raw_flow_rate):.1f}L/min")

        elif self.stable_volume_counter >= self.stable_count_threshold:
            if self.flow_state not in (FlowState.NORMAL, FlowState.LEAK_DETECTED):
                prev_state = self.flow_state
                self.flow_state = FlowState.NORMAL
                logger.info(f"Exited {prev_state.name.lower()} mode: volume stabilized")

    def _check_leak_detection(self, raw_flow_rate):
        """Detect sustained negative flow that may indicate a leak."""
        if raw_flow_rate < self.LEAK_FLOW_THRESHOLD:
            self._leak_candidate_count += 1
            if self._leak_candidate_count >= self.LEAK_SUSTAINED_COUNT:
                if self.flow_state != FlowState.LEAK_DETECTED:
                    self.flow_state = FlowState.LEAK_DETECTED
                    logger.warning(f"Leak detected: sustained negative flow of {abs(raw_flow_rate):.1f}L/min "
                                  f"for {self._leak_candidate_count} readings")
        else:
            if self._leak_candidate_count > 0 and self.flow_state == FlowState.LEAK_DETECTED:
                self.flow_state = FlowState.NORMAL
                logger.info("Leak condition cleared: flow returned to normal")
            self._leak_candidate_count = 0

    def _process_significant_flow(self, raw_flow_rate, vol_diff, time_diff):
        """Process flow rate with adaptive smoothing based on flow magnitude."""
        if raw_flow_rate > 0:
            if raw_flow_rate > self.expected_max_inflow_rate:
                logger.warning(
                    f"Unusually high inflow rate detected: {raw_flow_rate:.2f}L/min. "
                    f"Volume change: {vol_diff:.1f}L over {time_diff:.2f} minutes."
                )
                raw_flow_rate = min(raw_flow_rate, self.expected_max_inflow_rate)
        else:
            if abs(raw_flow_rate) > self.expected_max_outflow_rate:
                logger.warning(
                    f"Unusually high outflow rate detected: {raw_flow_rate:.2f}L/min. "
                    f"Volume change: {vol_diff:.1f}L over {time_diff:.2f} minutes."
                )
                raw_flow_rate = max(raw_flow_rate, -self.expected_max_outflow_rate)

        if self.flow_state == FlowState.REFILL:
            smoothing = self.SMOOTHING_FACTOR_REFILL
        elif self.flow_state == FlowState.HIGH_OUTFLOW:
            smoothing = self.SMOOTHING_FACTOR_HIGH_OUTFLOW
        else:
            flow_magnitude = abs(raw_flow_rate)
            if flow_magnitude > 40.0:
                smoothing = 0.7
            elif flow_magnitude > 20.0:
                smoothing = 0.6
            else:
                smoothing = self.smoothing_factor

        if self.last_flow_rate is not None:
            flow_rate = (smoothing * raw_flow_rate) + ((1 - smoothing) * self.last_flow_rate)
        else:
            flow_rate = raw_flow_rate

        self.last_flow_rate = flow_rate

        if flow_rate > 0:
            self.max_inflow_rate = max(self.max_inflow_rate, flow_rate)
        else:
            self.max_outflow_rate = max(self.max_outflow_rate, abs(flow_rate))

        self.current_flow_rate = flow_rate
        return round(flow_rate, 2)

    def _handle_no_significant_change(self):
        """Handle cases where there's no significant change in volume."""
        if self.last_flow_rate is not None and abs(self.last_flow_rate) > 0:
            if self.flow_state == FlowState.REFILL:
                decay_factor = self.DECAY_FACTOR_REFILL
            elif self.flow_state == FlowState.HIGH_OUTFLOW:
                decay_factor = self.DECAY_FACTOR_HIGH_OUTFLOW
            else:
                decay_factor = self.DECAY_FACTOR_NORMAL

            decayed_rate = self.last_flow_rate * decay_factor

            if (abs(decayed_rate) < self.MIN_FLOW_RATE_THRESHOLD and
                self.flow_state not in (FlowState.REFILL, FlowState.HIGH_OUTFLOW, FlowState.LEAK_DETECTED)):
                self.current_flow_rate = 0.0
            else:
                self.current_flow_rate = decayed_rate

            self.last_flow_rate = self.current_flow_rate
        else:
            self.current_flow_rate = 0.0

        return round(self.current_flow_rate, 2)

    def get_statistics(self):
        """Get flow rate statistics."""
        return {
            'current_flow_rate': round(self.current_flow_rate, 2),
            'max_inflow_rate': round(self.max_inflow_rate, 2),
            'max_outflow_rate': round(self.max_outflow_rate, 2),
            'total_inflow': round(self.total_inflow, 1),
            'total_outflow': round(self.total_outflow, 1),
            'flow_rate_confidence': round(self.flow_rate_confidence, 2)
        }

    def reset_statistics(self):
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
        self._leak_candidate_count = 0
        logger.info("Flow rate statistics reset")
        return True
