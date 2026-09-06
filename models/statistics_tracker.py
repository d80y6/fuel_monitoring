"""
Statistics Tracker

This module provides the StatisticsTracker class for tracking tank statistics.
"""
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class StatisticsTracker:
    """Track statistics for a tank."""
    
    def __init__(self, tank_config):
        self.tank_config = tank_config
        self.reset_statistics()
    
    def reset_statistics(self):
        """Reset all statistics."""
        self.stats = {
            'min_level': float('inf'),
            'max_level': float('-inf'),
            'avg_level': 0,
            'level_count': 0,
            'min_volume': float('inf'),
            'max_volume': float('-inf'),
            'avg_volume': 0,
            'volume_count': 0,
            'min_flow_rate': float('inf'),
            'max_flow_rate': float('-inf'),
            'avg_flow_rate': 0,
            'flow_rate_count': 0,
            'last_update': None
        }
        return self.stats
    
    def update_statistics(self, measurement_data):
        """Update statistics with new measurement data."""
        # Update level statistics
        if 'level' in measurement_data:
            level = measurement_data['level']
            self.stats['min_level'] = min(self.stats['min_level'], level)
            self.stats['max_level'] = max(self.stats['max_level'], level)
            
            # Update average
            self.stats['avg_level'] = (self.stats['avg_level'] * self.stats['level_count'] + level) / (self.stats['level_count'] + 1)
            self.stats['level_count'] += 1
        
        # Update volume statistics
        if 'volume' in measurement_data:
            volume = measurement_data['volume']
            self.stats['min_volume'] = min(self.stats['min_volume'], volume)
            self.stats['max_volume'] = max(self.stats['max_volume'], volume)
            
            # Update average
            self.stats['avg_volume'] = (self.stats['avg_volume'] * self.stats['volume_count'] + volume) / (self.stats['volume_count'] + 1)
            self.stats['volume_count'] += 1
        
        # Update flow rate statistics
        if 'flow_rate' in measurement_data:
            flow_rate = measurement_data['flow_rate']
            self.stats['min_flow_rate'] = min(self.stats['min_flow_rate'], flow_rate)
            self.stats['max_flow_rate'] = max(self.stats['max_flow_rate'], flow_rate)
            
            # Update average
            self.stats['avg_flow_rate'] = (self.stats['avg_flow_rate'] * self.stats['flow_rate_count'] + flow_rate) / (self.stats['flow_rate_count'] + 1)
            self.stats['flow_rate_count'] += 1
        
        # Update last update time
        self.stats['last_update'] = measurement_data.get('timestamp', datetime.now())
        
        return self.stats
    
    def get_statistics(self):
        """Get current statistics."""
        return self.stats
    def _parse_timestamp(self, ts):
        """
        Parse a timestamp string or return datetime if already parsed.
        Returns None if parsing fails.
        """
        if isinstance(ts, datetime):
            return ts
        if isinstance(ts, str):
            try:
                return datetime.fromisoformat(ts.replace('Z', '+00:00'))
            except ValueError:
                try:
                    return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S.%f")
                except ValueError:
                    logger.error(f"Could not parse timestamp: {ts}")
        return None