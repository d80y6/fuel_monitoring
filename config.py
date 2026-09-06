"""
Configuration for the Fuel Tank Monitoring System

This module defines configuration settings for the application.
"""
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    """Base configuration."""
    # Flask settings
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-for-development-only'
    
    # Database settings
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///fuel_tank.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Tank monitoring settings
    HOST = os.environ.get('FUEL_TANK_HOST') or 'localhost'
    TCP_PORT = int(os.environ.get('FUEL_TANK_TCP_PORT') or 2000)
    DEVICE_ADDRESS = int(os.environ.get('FUEL_TANK_DEVICE_ADDRESS') or 1)
    TANK_ORIENTATION = os.environ.get('FUEL_TANK_ORIENTATION') or 'vertical'
    TANK_DIAMETER = float(os.environ.get('FUEL_TANK_DIAMETER') or 1.5)
    TANK_HEIGHT = float(os.environ.get('FUEL_TANK_HEIGHT') or 2.0)
    FLUID_DENSITY = float(os.environ.get('FUEL_TANK_FLUID_DENSITY') or 840)
    ATMOSPHERIC_PRESSURE = float(os.environ.get('FUEL_TANK_ATMOSPHERIC_PRESSURE') or 0.0)
    CALIBRATION_FACTOR = float(os.environ.get('FUEL_TANK_CALIBRATION_FACTOR') or 1.0)
    PRESSURE_CHANNEL = int(os.environ.get('FUEL_TANK_PRESSURE_CHANNEL') or 1)
    TEMP_CHANNEL = int(os.environ.get('FUEL_TANK_TEMP_CHANNEL') or 4)
    UPDATE_INTERVAL = int(os.environ.get('FUEL_TANK_UPDATE_INTERVAL') or 5)
    DATA_LOG_ENABLED = os.environ.get('FUEL_TANK_DATA_LOG_ENABLED', 'false').lower() == 'true'
    DATA_LOG_FILE = os.environ.get('FUEL_TANK_DATA_LOG_FILE') or 'data/fuel_tank_data.csv'
    
    # System monitoring
    ENABLE_SYSTEM_MONITORING = os.environ.get('ENABLE_SYSTEM_MONITORING', 'True').lower() in ('true', '1', 't')
    SYSTEM_MONITORING_INTERVAL = int(os.environ.get('SYSTEM_MONITORING_INTERVAL', 60))  # seconds
    
    # Add to your existing Config class
    BABEL_DEFAULT_LOCALE = 'en'
    BABEL_DEFAULT_TIMEZONE = 'UTC'
    LANGUAGES = {
        'en': 'English',
        'ar': 'العربية'
    }
    
    @classmethod
    def update_from_dict(cls, config_dict):
        """Update configuration from dictionary"""
        for key, value in config_dict.items():
            if hasattr(cls, key):
                setattr(cls, key, value)
    
    @classmethod
    def save_to_env_file(cls):
        """Save current configuration to .env file"""
        env_file = os.path.join(os.path.dirname(__file__), '.env')
        with open(env_file, 'w') as f:
            f.write(f"SECRET_KEY={cls.SECRET_KEY}\n")
            f.write(f"FUEL_TANK_HOST={cls.HOST}\n")
            f.write(f"FUEL_TANK_TCP_PORT={cls.TCP_PORT}\n")
            f.write(f"FUEL_TANK_DEVICE_ADDRESS={cls.DEVICE_ADDRESS}\n")
            f.write(f"FUEL_TANK_ORIENTATION={cls.TANK_ORIENTATION}\n")
            f.write(f"FUEL_TANK_DIAMETER={cls.TANK_DIAMETER}\n")
            f.write(f"FUEL_TANK_HEIGHT={cls.TANK_HEIGHT}\n")
            f.write(f"FUEL_TANK_FLUID_DENSITY={cls.FLUID_DENSITY}\n")
            f.write(f"FUEL_TANK_ATMOSPHERIC_PRESSURE={cls.ATMOSPHERIC_PRESSURE}\n")
            f.write(f"FUEL_TANK_CALIBRATION_FACTOR={cls.CALIBRATION_FACTOR}\n")
            f.write(f"FUEL_TANK_PRESSURE_CHANNEL={cls.PRESSURE_CHANNEL}\n")
            f.write(f"FUEL_TANK_TEMP_CHANNEL={cls.TEMP_CHANNEL}\n")
            f.write(f"FUEL_TANK_UPDATE_INTERVAL={cls.UPDATE_INTERVAL}\n")
            f.write(f"FUEL_TANK_DATA_LOG_ENABLED={'true' if cls.DATA_LOG_ENABLED else 'false'}\n")
            f.write(f"FUEL_TANK_DATA_LOG_FILE={cls.DATA_LOG_FILE}\n")