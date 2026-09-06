"""
Configuration for the Fuel Tank Monitoring System

Provides environment-specific configuration classes and validates
that critical secrets are present in production.
"""
import os
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def _require_secret_key():
    """Return the SECRET_KEY from the environment, warning if absent.

    Note: ProductionConfig enforces that SECRET_KEY is set and strong.
    This base-class helper is permissive for development convenience.
    """
    secret = os.environ.get('SECRET_KEY')
    if not secret:
        logger.warning(
            "SECRET_KEY is not set in the environment. "
            "Sessions and CSRF tokens will be insecure. "
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    return secret


class Config:
    """Base configuration.  Shared across all environments."""

    # Flask
    SECRET_KEY = _require_secret_key()

    # Database
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///fuel_tank.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Redis
    REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')

    # Celery
    CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
    CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')

    # MQTT TLS
    MQTT_TLS_ENABLED = os.environ.get('MQTT_TLS_ENABLED', 'false').lower() == 'true'
    MQTT_CA_CERT = os.environ.get('MQTT_CA_CERT', None)
    MQTT_CLIENT_CERT = os.environ.get('MQTT_CLIENT_CERT', None)
    MQTT_CLIENT_KEY = os.environ.get('MQTT_CLIENT_KEY', None)

    # MQTT broker
    MQTT_BROKER = os.environ.get('MQTT_BROKER', 'localhost')
    MQTT_PORT = int(os.environ.get('MQTT_PORT', 1883))
    MQTT_USER = os.environ.get('MQTT_USER')
    MQTT_PASS = os.environ.get('MQTT_PASS')

    # Tank monitoring defaults
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
    SYSTEM_MONITORING_INTERVAL = int(os.environ.get('SYSTEM_MONITORING_INTERVAL', 60))

    # HTTPS / TLS
    PREFERRED_URL_SCHEME = os.environ.get('PREFERRED_URL_SCHEME', 'http')
    FORCE_HTTPS = os.environ.get('FORCE_HTTPS', 'false').lower() == 'true'
    SSL_CERTFILE = os.environ.get('SSL_CERTFILE')
    SSL_KEYFILE = os.environ.get('SSL_KEYFILE')

    # Rate limiting
    RATE_LIMIT_LOGIN_MAX = int(os.environ.get('RATE_LIMIT_LOGIN_MAX', 5))
    RATE_LIMIT_LOGIN_WINDOW = int(os.environ.get('RATE_LIMIT_LOGIN_WINDOW', 900))
    RATE_LIMIT_API_MAX = int(os.environ.get('RATE_LIMIT_API_MAX', 60))
    RATE_LIMIT_API_WINDOW = int(os.environ.get('RATE_LIMIT_API_WINDOW', 60))

    # Internationalisation
    BABEL_DEFAULT_LOCALE = 'en'
    BABEL_DEFAULT_TIMEZONE = 'UTC'
    LANGUAGES = {
        'en': 'English',
        'ar': 'العربية'
    }

    # Session security
    SESSION_COOKIE_SECURE = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = 1800  # 30 minutes

    @classmethod
    def update_from_dict(cls, config_dict):
        """Update configuration from a dictionary."""
        for key, value in config_dict.items():
            if hasattr(cls, key):
                setattr(cls, key, value)


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    TEMPLATES_AUTO_RELOAD = True

    # Development — allow HTTP.
    SESSION_COOKIE_SECURE = False
    FORCE_HTTPS = False


class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    DEBUG = True

    # Use an in-memory database for tests.
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False

    # Don't force HTTPS in tests.
    FORCE_HTTPS = False


class ProductionConfig(Config):
    """Production configuration.

    Enforces strict security: HTTPS, secure cookies, and a non-default secret.
    """

    DEBUG = False

    # --- SECRET_KEY: must be explicitly set in production ---
    SECRET_KEY = os.environ.get('SECRET_KEY')

    # --- HTTPS ---
    PREFERRED_URL_SCHEME = 'https'
    FORCE_HTTPS = True

    # --- Session cookies ---
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Strict'
    PERMANENT_SESSION_LIFETIME = 1800

    def __init__(self):
        super().__init__()
        if not self.SECRET_KEY:
            raise RuntimeError(
                "SECRET_KEY must be set in the environment for ProductionConfig. "
                "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        # Warn if using a weak / default key.
        if self.SECRET_KEY in ('', 'change-me', 'dev-secret-key', 'super-secret'):
            raise RuntimeError(
                "SECRET_KEY appears to be a weak default. "
                "Set a strong random value in your environment."
            )


config_by_name = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
}
