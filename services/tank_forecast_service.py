from datetime import datetime, timedelta
from sqlalchemy import text
from models.database import Measurement, Tank, db


class TankForecastService:
    def __init__(self, tank_id, days=30):
        self.tank_id = tank_id
        self.days = days
        self.threshold = datetime.now() - timedelta(days=days)
        self.tank = Tank.query.get(tank_id)
        
    def get_measurements(self):
        """Get recent measurements for the tank."""
        return Measurement.query.filter(
            Measurement.tank_id == self.tank_id,
            Measurement.timestamp >= self.threshold
        ).order_by(Measurement.timestamp.asc()).all()
    
    def get_volume_data(self):
        """Get first and last volume data for consumption calculation."""
        volume_query = text("""
            SELECT 
                (SELECT volume FROM measurement 
                 WHERE tank_id = :tank_id AND timestamp >= :threshold 
                 ORDER BY timestamp ASC LIMIT 1) as first_volume,
                (SELECT volume FROM measurement 
                 WHERE tank_id = :tank_id AND timestamp >= :threshold 
                 ORDER BY timestamp DESC LIMIT 1) as last_volume,
                (SELECT timestamp FROM measurement 
                 WHERE tank_id = :tank_id AND timestamp >= :threshold 
                 ORDER BY timestamp ASC LIMIT 1) as first_timestamp,
                (SELECT timestamp FROM measurement 
                 WHERE tank_id = :tank_id AND timestamp >= :threshold 
                 ORDER BY timestamp DESC LIMIT 1) as last_timestamp
        """)
        
        return db.session.execute(
            volume_query,
            {'tank_id': self.tank_id, 'threshold': self.threshold}
        ).fetchone()
    
    def calculate_consumption_rate(self, first_volume, last_volume, first_timestamp, last_timestamp):
        """Calculate daily consumption rate based on volume change."""
        # Calculate time difference in days
        time_diff = (last_timestamp - first_timestamp).total_seconds() / (24 * 3600)
        
        # Only calculate consumption if volume is decreasing and time difference is significant
        if last_volume < first_volume and time_diff > 0.5:  # At least 12 hours of data
            # Simple daily consumption calculation - no artificial limits
            daily_consumption = (first_volume - last_volume) / time_diff
        
            # Just ensure it's not negative
            daily_consumption = max(0, daily_consumption)
        else:
            # If no consumption detected or time difference too small,
            # use a reasonable default based on recent data
            daily_consumption = 0
        
        return daily_consumption
    
    def calculate_days_remaining(self, last_volume, daily_consumption):
        """Calculate days until tank is empty."""
        # Minimum consumption threshold to avoid division by very small numbers
        MIN_CONSUMPTION = 0.001
        
        if daily_consumption > MIN_CONSUMPTION:
            return last_volume / daily_consumption
        else:
            return float('inf')  # If no significant consumption, return infinity
    
    def generate_forecast_data(self, last_timestamp, last_volume, daily_consumption, days_remaining):
        """Generate forecast data points."""
        forecast_days = min(30, int(days_remaining) + 5) if days_remaining != float('inf') else 30
        
        forecast_data = []
        if daily_consumption > 0:
            for i in range(1, forecast_days + 1):
                forecast_date = last_timestamp + timedelta(days=i)
                forecast_volume = max(0, last_volume - (daily_consumption * i))
                
                forecast_data.append({
                    'date': forecast_date.isoformat(),
                    'volume': round(forecast_volume, 2)
                })
                
        return forecast_data
    
    def get_critical_volume(self, monitor):
        """Calculate critical volume based on tank capacity and threshold."""
        if not self.tank or not hasattr(self.tank, 'critical_level_threshold'):
            return 0
        
        # Calculate tank volume from dimensions
        tank_volume = 3.14159 * (self.tank.tank_diameter/2)**2 * self.tank.tank_height
        
        return tank_volume * self.tank.critical_level_threshold / 100
    
    def format_historical_data(self, measurements):
        """Format historical measurement data."""
        return [
            {
                'date': m.timestamp.isoformat(),
                'volume': round(m.volume, 2)
            } for m in measurements
        ]
    
    def generate_forecast(self, monitor=None):
        """Generate complete forecast data."""
        measurements = self.get_measurements()
        
        if not measurements:
            return {
                'success': True,
                'forecast': None,
                'message': 'Not enough data for forecast'
            }
        
        volume_result = self.get_volume_data()
        
        if not volume_result or volume_result.first_volume is None or volume_result.last_volume is None:
            return {
                'success': True,
                'forecast': None,
                'message': 'Not enough data for forecast'
            }
        
        first_volume = float(volume_result.first_volume)
        last_volume = float(volume_result.last_volume)
        first_timestamp = volume_result.first_timestamp
        last_timestamp = volume_result.last_timestamp
        
        daily_consumption = self.calculate_consumption_rate(
            first_volume, last_volume, first_timestamp, last_timestamp
        )
        
        days_remaining = self.calculate_days_remaining(last_volume, daily_consumption)
        
        # Calculate depletion date
        depletion_date = last_timestamp + timedelta(days=days_remaining) if days_remaining != float('inf') else None
        
        historical_data = self.format_historical_data(measurements)
        forecast_data = self.generate_forecast_data(last_timestamp, last_volume, daily_consumption, days_remaining)
        critical_volume = self.get_critical_volume(monitor)
        
        forecast = {
            'depletion_date': depletion_date.isoformat() if depletion_date else None,
            'days_remaining': round(days_remaining, 1) if days_remaining != float('inf') else None,
            'daily_consumption': round(daily_consumption, 2),
            'weekly_consumption': round(daily_consumption * 7, 2),
            'monthly_consumption': round(daily_consumption * 30, 2),
            'critical_volume': round(critical_volume, 2),
            'data': {
                'historical': historical_data,
                'forecast': forecast_data
            }
        }
        
        return {
            'success': True,
            'forecast': forecast
        }
