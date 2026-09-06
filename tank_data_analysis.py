from datetime import datetime
import math

# Function to compensate for temperature changes in fluid density
def compensate_density(temperature_C):
    base_density = 835  # kg/m³ at 15°C for diesel
    density_change_per_degree = 0.0023  # ~0.2% per degree Celsius
    return base_density * (1 - (temperature_C - 15) * density_change_per_degree)

# Function to calculate the level (height) from pressure and temperature
def calculate_level(pressure_pa, temperature_C):
    fluid_density = compensate_density(temperature_C)
    level_m = pressure_pa / (fluid_density * 9.79955)  # height in meters
    return level_m

# Simple moving average filter
class LevelFilter:
    def __init__(self, window_size=5):
        self.window_size = window_size
        self.readings = []

    def filter(self, new_level):
        self.readings.append(new_level)
        if len(self.readings) > self.window_size:
            self.readings.pop(0)  # Remove oldest reading
        return sum(self.readings) / len(self.readings)  # Return average

# Exponential smoothing filter
class ExponentialSmoothing:
    def __init__(self, alpha=0.1):
        self.alpha = alpha
        self.smoothed_level = None

    def filter(self, new_level):
        if self.smoothed_level is None:
            self.smoothed_level = new_level
        else:
            self.smoothed_level = self.alpha * new_level + (1 - self.alpha) * self.smoothed_level
        return self.smoothed_level

# Alert system for level threshold and rate of change
class LevelAlert:
    def __init__(self, threshold_level, threshold_rate):
        self.threshold_level = threshold_level
        self.threshold_rate = threshold_rate
        self.last_level = None
        self.last_time = None

    def check_alert(self, current_level, current_time):
        if self.last_level is not None:
            level_change = abs(current_level - self.last_level)
            time_diff = (current_time - self.last_time).total_seconds()  # Assuming `current_time` is a datetime object
            rate_of_change = level_change / time_diff

            if current_level > self.threshold_level:
                print("Warning: Level exceeds the threshold!")
            if rate_of_change > self.threshold_rate:
                print("Warning: Rapid level change detected!")
        
        # Store current values for next check
        self.last_level = current_level
        self.last_time = current_time

# Function to calculate the volume for a horizontal cylindrical tank
def calculate_volume_horizontal_cylindrical(length, radius, level):
    if level > 2 * radius:
        raise ValueError("Liquid level cannot be greater than the tank diameter")

    # Calculate the volume using the formula for a horizontal cylindrical tank
    volume = length * (radius**2 * math.acos((radius - level) / radius) - (radius - level) * math.sqrt(2 * radius * level - level**2))
    return volume

# Main class that manages level processing with smoothing, filtering, and alerting
class FuelLevelManager:
    def __init__(self):
        self.level_filter = LevelFilter(window_size=5)
        self.smoothing = ExponentialSmoothing(alpha=0.1)
        self.alert = LevelAlert(threshold_level=3.0, threshold_rate=0.5)

    def process_sensor_data(self, pressure_pa, temperature_C, current_time):
        # Compensate for temperature and calculate the level
        calculated_level = calculate_level(pressure_pa, temperature_C)

        # Apply smoothing filter
        smoothed_level = self.level_filter.filter(calculated_level)
        smoothed_level = self.smoothing.filter(smoothed_level)

        # Check for alerts
        self.alert.check_alert(smoothed_level, current_time)

        return smoothed_level

    def get_tank_volume(self, length, radius, level):
        # Calculate the volume for a horizontal cylindrical tank
        return calculate_volume_horizontal_cylindrical(length, radius, level)

# Example usage
if __name__ == "__main__":
    # Instantiate the fuel level manager
    fuel_manager = FuelLevelManager()

    # Example sensor data
    pressure_pa = 0.1916 * 100000  # in Pascals (for example)
    temperature_C = 23.09  # temperature in °C
    current_time = datetime.now()  # current timestamp

    # Process sensor data and get the smoothed level
    smoothed_level = fuel_manager.process_sensor_data(pressure_pa, temperature_C, current_time)
    
    # Output the smoothed level
    print(f"Smoothed Level: {smoothed_level:.2f} meters")

    # Example tank dimensions and liquid level
    length = 8.16   # meters
    radius = 1.975    # meters (diameter = 4 meters)
    level = smoothed_level  # Using the smoothed level from the sensor

    # Get the volume of the fuel in the tank
    volume = fuel_manager.get_tank_volume(length, radius, level)
    print(f"Volume of fuel: {volume*1000:.2f} cubic meters")
