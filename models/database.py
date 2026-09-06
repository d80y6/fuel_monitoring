"""
Database Models for the Fuel Tank Monitoring System

This module defines the database models for the application including
users, companies, sites, tanks, measurements, and alarms.
"""
import datetime
from datetime import datetime as dt, timedelta, time
from sqlalchemy import (
    Column, Integer, Float, DateTime, ForeignKey, String,
    Boolean, Text, text, Index, select, func
)
from sqlalchemy.orm import joinedload, aliased
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.hybrid import hybrid_property
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

# Initialize SQLAlchemy
db = SQLAlchemy()

# User-Company association table
user_companies = db.Table('user_companies',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('company_id', db.Integer, db.ForeignKey('company.id'), primary_key=True)
)

# User-Site association table
user_sites = db.Table('user_sites',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('site_id', db.Integer, db.ForeignKey('site.id'), primary_key=True)
)


class SoftDeleteMixin:
    """Mixin that adds soft-delete support to models."""
    deleted_at = db.Column(db.DateTime, nullable=True)

    def soft_delete(self):
        self.deleted_at = func.now()

    def restore(self):
        self.deleted_at = None

    @property
    def is_deleted(self):
        return self.deleted_at is not None

    @classmethod
    def not_deleted(cls):
        return cls.query.filter_by(deleted_at=None)


class User(db.Model, UserMixin, SoftDeleteMixin):
    """User model"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(128), nullable=False)
    first_name = db.Column(db.String(64))
    last_name = db.Column(db.String(64))
    role = db.Column(db.String(20), default='user', index=True)
    is_active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(db.DateTime, server_default=func.now())
    updated_at = db.Column(db.DateTime, server_default=func.now(), onupdate=func.now())
    last_login = db.Column(db.DateTime)
    phone = db.Column(db.String(20), nullable=True)
    job_title = db.Column(db.String(100), nullable=True)
    login_count = db.Column(db.Integer, default=0)

    # Relationships
    companies = db.relationship('Company', secondary=user_companies,
                               backref=db.backref('users', lazy='dynamic'),
                               cascade='save-update')
    sites = db.relationship('Site', secondary=user_sites,
                           backref=db.backref('users', lazy='dynamic'),
                           cascade='save-update')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_admin(self):
        return self.role == 'admin'

    def is_company_admin(self):
        return self.role == 'company_admin'

    def has_role(self, role):
        return self.role == role

    def get_full_name(self):
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        elif self.first_name:
            return self.first_name
        elif self.last_name:
            return self.last_name
        return self.username

    def get_id(self):
        return str(self.id)

    def __repr__(self):
        return f'<User {self.username}>'


class Company(db.Model, SoftDeleteMixin):
    """Company model"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    address = db.Column(db.String(200))
    contact_name = db.Column(db.String(100))
    contact_email = db.Column(db.String(100))
    contact_phone = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, server_default=func.now())
    updated_at = db.Column(db.DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    sites = db.relationship('Site', backref='company', lazy=True, cascade='all, delete-orphan')

    @hybrid_property
    def get_tank_count(self):
        return self.tank_count

    @get_tank_count.expression
    def get_tank_count(cls):
        Site_alias = aliased(Site)
        Tank_alias = aliased(Tank)

        return select(func.count(Tank_alias.id)).where(
            Tank_alias.site_id == Site_alias.id,
            Site_alias.company_id == cls.id,
            Site_alias.deleted_at == None,
            Tank_alias.deleted_at == None
        ).scalar_subquery()

    @property
    def tank_count(self):
        return db.session.query(func.count(Tank.id)).join(Site).filter(
            Site.company_id == self.id,
            Site.deleted_at == None,
            Tank.deleted_at == None
        ).scalar() or 0

    def __repr__(self):
        return f'<Company {self.name}>'


class Site(db.Model, SoftDeleteMixin):
    """Site model"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    address = db.Column(db.String(200))
    location = db.Column(db.String(200))
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False, index=True)
    contact_name = db.Column(db.String(100))
    contact_email = db.Column(db.String(100))
    contact_phone = db.Column(db.String(20))
    contact_info = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(db.DateTime, server_default=func.now())

    # Relationships
    tanks = db.relationship('Tank', backref='site', lazy=True, cascade='all, delete-orphan')

    def get_recent_alarms(self, limit=5):
        from sqlalchemy import desc
        tank_ids = [tank.id for tank in self.tanks if tank.deleted_at is None]
        if not tank_ids:
            return []
        return Alarm.query.filter(
            Alarm.tank_id.in_(tank_ids)
        ).order_by(desc(Alarm.timestamp)).limit(limit).all()

    def __repr__(self):
        return f'<Site {self.name}>'


class Tank(db.Model, SoftDeleteMixin):
    """Tank model"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    description = db.Column(db.Text)
    site_id = db.Column(db.Integer, db.ForeignKey('site.id'), nullable=False, index=True)
    gateway_mac = db.Column(db.String(17), nullable=True, index=True)
    sensor_serial_number = db.Column(db.BigInteger, nullable=True, index=True, unique=True)

    # Connection settings
    device_address = db.Column(db.Integer, default=1)
    connection_mode = db.Column(db.String(20), default='mqtt')

    # Tank parameters
    tank_orientation = db.Column(db.String(20), default='vertical')
    tank_height = db.Column(db.Float, default=2.0)
    tank_diameter = db.Column(db.Float, default=1.5)
    fluid_density = db.Column(db.Float, default=850)
    atmospheric_pressure = db.Column(db.Float, default=0.0)
    elevation = db.Column(db.Float, default=2250.0)

    # Sensor settings
    pressure_channel = db.Column(db.Integer, default=1)
    temp_channel = db.Column(db.Integer, default=4)
    calibration_factor = db.Column(db.Float, default=1.0)

    # Alarm thresholds
    low_level_threshold = db.Column(db.Float, default=20.0)
    critical_level_threshold = db.Column(db.Float, default=10.0)
    high_level_threshold = db.Column(db.Float, default=90.0)

    # Status
    is_active = db.Column(db.Boolean, default=True, index=True)
    last_connection = db.Column(db.DateTime)
    connection_status = db.Column(db.String(20), default='disconnected')
    created_at = db.Column(db.DateTime, server_default=func.now())
    updated_at = db.Column(db.DateTime, server_default=func.now(), onupdate=func.now())

    # Custom configuration fields
    level_hysteresis = db.Column(db.Float, default=None)
    flow_threshold = db.Column(db.Float, default=None)
    pressure_smoothing = db.Column(db.Boolean, default=True)

    # Relationships
    measurements = db.relationship('Measurement', backref='tank', lazy=True, cascade='all, delete-orphan')
    alarms = db.relationship('Alarm', backref='tank', lazy=True, cascade='all, delete-orphan')

    __table_args__ = (
        Index('ix_tank_site_active', 'site_id', 'is_active'),
    )

    def get_latest_measurement(self):
        return Measurement.query.filter_by(
            tank_id=self.id
        ).order_by(Measurement.timestamp.desc()).first()

    def get_recent_measurements(self, limit=100):
        return Measurement.query.filter_by(
            tank_id=self.id
        ).order_by(Measurement.timestamp.desc()).limit(limit).all()

    def get_connection_status(self):
        if not self.last_connection:
            return "Disconnected"

        now = datetime.datetime.utcnow()
        five_minutes_ago = now - datetime.timedelta(minutes=5)
        if self.last_connection >= five_minutes_ago:
            return "Connected"

        one_hour_ago = now - datetime.timedelta(hours=1)
        if self.last_connection >= one_hour_ago:
            return "Recently Disconnected"

        return "Disconnected"

    def get_recent_alarms(self, limit=5):
        from sqlalchemy import desc
        return Alarm.query.filter_by(tank_id=self.id).order_by(desc(Alarm.timestamp)).limit(limit).all()

    def get_current_volume(self):
        measurement = self.get_latest_measurement()
        if measurement:
            return measurement.volume
        return 0

    def __repr__(self):
        return f'<Tank {self.name}>'


from models.base_model import BaseModel


class Measurement(db.Model, BaseModel):
    """Measurement model"""
    __tablename__ = 'measurement'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    timestamp = db.Column(db.DateTime, server_default=func.now(), nullable=False)
    tank_id = db.Column(db.Integer, db.ForeignKey('tank.id'), nullable=False)
    pressure = db.Column(db.Float, nullable=False)
    temperature = db.Column(db.Float)
    level = db.Column(db.Float, nullable=False)
    volume = db.Column(db.Float, nullable=False)
    flow_rate = db.Column(db.Float, nullable=False)
    fill_percent = db.Column(db.Float, nullable=False)
    status = db.Column(db.Integer, nullable=False)

    __table_args__ = (
        Index('ix_measurement_tank_timestamp', 'tank_id', 'timestamp'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'tank_id': self.tank_id,
            'timestamp': self.timestamp,
            'pressure': self.pressure,
            'temperature': self.temperature,
            'level': self.level,
            'volume': self.volume,
            'flow_rate': self.flow_rate,
            'fill_percent': self.fill_percent,
            'status': self.status
        }

    @classmethod
    def get_aggregated(cls, tank_id, start_time, end_time, interval='1 hour'):
        """
        Get aggregated measurements using TimescaleDB's time_bucket function.
        """
        sql = text("""
            SELECT
                time_bucket(:interval, timestamp) AS bucket,
                AVG(pressure) AS pressure,
                AVG(temperature) AS temperature,
                AVG(level) AS level,
                AVG(volume) AS volume,
                AVG(flow_rate) AS flow_rate,
                AVG(fill_percent) AS fill_percent,
                MAX(status) AS status
            FROM measurement
            WHERE tank_id = :tank_id
              AND timestamp >= :start_time
              AND timestamp <= :end_time
            GROUP BY bucket
            ORDER BY bucket
        """)

        result = db.session.execute(
            sql,
            {
                'interval': interval,
                'tank_id': tank_id,
                'start_time': start_time,
                'end_time': end_time
            }
        )

        aggregated_data = []
        for row in result:
            aggregated_data.append({
                'timestamp': row.bucket.isoformat(),
                'pressure': float(row.pressure) if row.pressure is not None else None,
                'temperature': float(row.temperature) if row.temperature is not None else None,
                'level': float(row.level) if row.level is not None else None,
                'volume': float(row.volume) if row.volume is not None else None,
                'flow_rate': float(row.flow_rate) if row.flow_rate is not None else None,
                'fill_percent': float(row.fill_percent) if row.fill_percent is not None else None,
                'status': int(row.status) if row.status is not None else None
            })

        return aggregated_data

    @classmethod
    def get_daily_consumption(cls, tank_id, start_time, end_time):
        """
        Calculate daily consumption and refill statistics for a tank.
        """
        with db.engine.connect() as conn:
            daily_stats_query = text("""
                WITH daily_data AS (
                    SELECT
                        date_trunc('day', timestamp) AS day,
                        MIN(timestamp) AS first_timestamp,
                        MAX(timestamp) AS last_timestamp,
                        MIN(volume) AS min_volume,
                        MAX(volume) AS max_volume,
                        FIRST_VALUE(volume) OVER (PARTITION BY date_trunc('day', timestamp) ORDER BY timestamp) AS start_volume,
                        LAST_VALUE(volume) OVER (PARTITION BY date_trunc('day', timestamp) ORDER BY timestamp RANGE BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) AS end_volume
                    FROM measurement
                    WHERE tank_id = :tank_id
                      AND timestamp BETWEEN :start_time AND :end_time
                      AND volume IS NOT NULL
                    GROUP BY date_trunc('day', timestamp)
                )
                SELECT
                    EXTRACT(EPOCH FROM day) * 1000 AS timestamp,
                    start_volume,
                    end_volume,
                    min_volume,
                    max_volume,
                    (end_volume - start_volume) AS net_change,
                    CASE WHEN (max_volume - min_volume) > 0.05 * min_volume THEN
                        (max_volume - min_volume)
                    ELSE 0 END AS daily_refill,
                    CASE WHEN start_volume > end_volume THEN
                        (start_volume - end_volume)
                    ELSE 0 END AS daily_consumption
                FROM daily_data
                ORDER BY day
            """)

            daily_results = conn.execute(
                daily_stats_query,
                {"tank_id": tank_id, "start_time": start_time, "end_time": end_time}
            ).fetchall()

            overnight_query = text("""
                WITH evening_readings AS (
                    SELECT
                        date_trunc('day', timestamp) AS day,
                        LAST_VALUE(volume) OVER (PARTITION BY date_trunc('day', timestamp)
                                                ORDER BY timestamp
                                                RANGE BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) AS evening_volume,
                        LAST_VALUE(timestamp) OVER (PARTITION BY date_trunc('day', timestamp)
                                                   ORDER BY timestamp
                                                   RANGE BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) AS evening_time
                    FROM measurement
                    WHERE tank_id = :tank_id
                      AND timestamp BETWEEN :start_time AND :end_time
                      AND EXTRACT(HOUR FROM timestamp) BETWEEN 18 AND 23
                      AND volume IS NOT NULL
                    GROUP BY date_trunc('day', timestamp), timestamp, volume
                ),
                morning_readings AS (
                    SELECT
                        date_trunc('day', timestamp) AS day,
                        FIRST_VALUE(volume) OVER (PARTITION BY date_trunc('day', timestamp)
                                                 ORDER BY timestamp) AS morning_volume,
                        FIRST_VALUE(timestamp) OVER (PARTITION BY date_trunc('day', timestamp)
                                                    ORDER BY timestamp) AS morning_time
                    FROM measurement
                    WHERE tank_id = :tank_id
                      AND timestamp BETWEEN :start_time AND :end_time
                      AND EXTRACT(HOUR FROM timestamp) BETWEEN 5 AND 9
                      AND volume IS NOT NULL
                    GROUP BY date_trunc('day', timestamp), timestamp, volume
                )
                SELECT
                    EXTRACT(EPOCH FROM e.day + INTERVAL '1 day') * 1000 AS timestamp,
                    e.evening_volume,
                    m.morning_volume,
                    CASE WHEN e.evening_volume > m.morning_volume THEN
                        (e.evening_volume - m.morning_volume)
                    ELSE 0 END AS overnight_consumption,
                    CASE WHEN m.morning_volume > e.evening_volume THEN
                        (m.morning_volume - e.evening_volume)
                    ELSE 0 END AS overnight_refill
                FROM evening_readings e
                JOIN morning_readings m ON e.day = (m.day - INTERVAL '1 day')
                WHERE e.evening_volume IS NOT NULL AND m.morning_volume IS NOT NULL
                ORDER BY e.day
            """)

            overnight_results = conn.execute(
                overnight_query,
                {"tank_id": tank_id, "start_time": start_time, "end_time": end_time}
            ).fetchall()

            daily_data = []
            for row in daily_results:
                data_point = {
                    'timestamp': int(row.timestamp),
                    'start_volume': float(row.start_volume),
                    'end_volume': float(row.end_volume),
                    'min_volume': float(row.min_volume),
                    'max_volume': float(row.max_volume),
                    'net_change': float(row.net_change),
                    'daily_consumption': float(row.daily_consumption),
                    'daily_refill': float(row.daily_refill)
                }

                overnight_data = next((o for o in overnight_results if o.timestamp == row.timestamp), None)
                if overnight_data:
                    data_point['overnight_consumption'] = float(overnight_data.overnight_consumption)
                    data_point['overnight_refill'] = float(overnight_data.overnight_refill)
                else:
                    data_point['overnight_consumption'] = 0.0
                    data_point['overnight_refill'] = 0.0

                data_point['total_consumption'] = data_point['daily_consumption'] + data_point['overnight_consumption']
                data_point['total_refill'] = data_point['daily_refill'] + data_point['overnight_refill']

                daily_data.append(data_point)

            return daily_data

    @classmethod
    def get_hourly_consumption(cls, tank_id, start_time, end_time):
        """Get hourly consumption data for a tank"""
        query = text("""
            WITH hourly_data AS (
                SELECT
                    date_trunc('hour', timestamp) as hour_start,
                    MAX(volume) as max_volume,
                    MIN(volume) as min_volume
                FROM measurement
                WHERE tank_id = :tank_id
                AND timestamp >= :start_time
                AND timestamp <= :end_time
                GROUP BY date_trunc('hour', timestamp)
                ORDER BY hour_start
            )
            SELECT
                EXTRACT(EPOCH FROM hour_start) * 1000 as timestamp,
                max_volume - min_volume as hourly_consumption,
                max_volume - LAG(max_volume) OVER (ORDER BY hour_start) as volume_change
            FROM hourly_data
        """)

        result = db.session.execute(
            query,
            {'tank_id': tank_id, 'start_time': start_time, 'end_time': end_time}
        )

        consumption_data = []
        for row in result:
            data_point = {
                'timestamp': int(row.timestamp) if row.timestamp is not None else None,
                'hourly_consumption': float(row.hourly_consumption) if row.hourly_consumption is not None else None,
                'volume_change': float(row.volume_change) if row.volume_change is not None else None
            }
            consumption_data.append(data_point)

        return consumption_data

    def __repr__(self):
        return f'<Measurement {self.timestamp}>'


class Alarm(db.Model):
    """Alarm model"""
    id = db.Column(db.Integer, primary_key=True)
    tank_id = db.Column(db.Integer, db.ForeignKey('tank.id'), nullable=False, index=True)
    timestamp = db.Column(db.DateTime, server_default=func.now(), index=True)
    type = db.Column(db.String(50), nullable=False, index=True)
    level = db.Column(db.String(20), default='warning', index=True)
    message = db.Column(db.Text, nullable=False)
    value = db.Column(db.Float)
    acknowledged = db.Column(db.Boolean, default=False, index=True)
    acknowledged_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    acknowledged_at = db.Column(db.DateTime)

    # Relationships
    acknowledger = db.relationship('User', backref='acknowledged_alarms')

    __table_args__ = (
        Index('ix_alarm_tank_type_acknowledged', 'tank_id', 'type', 'acknowledged'),
    )

    def to_dict(self):
        """Convert alarm to dictionary with eager-loaded relationships to avoid N+1."""
        return {
            'id': self.id,
            'tank_id': self.tank_id,
            'tank_name': self.tank.name if self.tank else 'Unknown',
            'site_name': self.tank.site.name if self.tank and self.tank.site else 'Unknown',
            'company_name': self.tank.site.company.name if self.tank and self.tank.site and self.tank.site.company else 'Unknown',
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'type': self.type,
            'level': self.level,
            'message': self.message,
            'value': self.value,
            'acknowledged': self.acknowledged,
            'acknowledged_by': self.acknowledged_by,
            'acknowledged_at': self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            'acknowledger_name': self.acknowledger.get_full_name() if self.acknowledger else None
        }

    @staticmethod
    def to_dict_loaded(alarm):
        """Convert an already eager-loaded alarm to dictionary (no N+1)."""
        return alarm.to_dict()

    def __repr__(self):
        return f'<Alarm {self.type} {self.timestamp}>'


class ActivityLog(db.Model):
    """Activity log model for tracking user actions"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    timestamp = db.Column(db.DateTime, server_default=func.now(), index=True)
    action = db.Column(db.String(100), nullable=False)
    details = db.Column(db.Text)
    ip_address = db.Column(db.String(45))

    # Relationships
    user = db.relationship('User', backref='activities')

    def __repr__(self):
        return f'<ActivityLog {self.action} {self.timestamp}>'


def _get_raw_connection(engine):
    """Get a raw psycopg2 connection from the SQLAlchemy engine."""
    import psycopg2
    url = engine.url
    conn = psycopg2.connect(
        dbname=url.database,
        user=url.username,
        password=url.password,
        host=url.host,
        port=url.port
    )
    conn.autocommit = True
    return conn


def create_timescale_extensions():
    """Create TimescaleDB extensions and hypertables using a raw connection."""
    try:
        raw_conn = _get_raw_connection(db.engine)
        cursor = raw_conn.cursor()

        cursor.execute('CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;')

        cursor.execute("SELECT to_regclass('public.measurement');")
        table_exists = cursor.fetchone()[0] is not None

        if table_exists:
            cursor.execute(
                "SELECT create_hypertable('measurement', 'timestamp', if_not_exists => TRUE);"
            )
            print("Successfully created hypertable for measurement table")
        else:
            print("Measurement table does not exist yet")

        cursor.close()
        raw_conn.close()
    except Exception as e:
        print(f"Error creating TimescaleDB extensions: {str(e)}")


def setup_timescale_retention():
    """Set up TimescaleDB retention policies and continuous aggregation."""
    try:
        raw_conn = _get_raw_connection(db.engine)
        cursor = raw_conn.cursor()

        # Ensure hypertable exists
        cursor.execute("""
            SELECT create_hypertable('measurement', 'timestamp',
                                    if_not_exists => TRUE,
                                    migrate_data => TRUE);
        """)

        # Create hourly materialized view
        cursor.execute("""
            CREATE MATERIALIZED VIEW IF NOT EXISTS measurements_hourly
            WITH (timescaledb.continuous) AS
            SELECT
                tank_id,
                time_bucket('1 hour', timestamp) AS bucket,
                AVG(pressure) AS pressure,
                AVG(temperature) AS temperature,
                AVG(level) AS level,
                AVG(volume) AS volume,
                AVG(flow_rate) AS flow_rate,
                AVG(fill_percent) AS fill_percent,
                MAX(status) AS status
            FROM measurement
            GROUP BY tank_id, bucket;
        """)

        # Create daily materialized view
        cursor.execute("""
            CREATE MATERIALIZED VIEW IF NOT EXISTS measurements_daily
            WITH (timescaledb.continuous) AS
            SELECT
                tank_id,
                time_bucket('1 day', timestamp) AS bucket,
                AVG(pressure) AS pressure,
                AVG(temperature) AS temperature,
                AVG(level) AS level,
                AVG(volume) AS volume,
                AVG(flow_rate) AS flow_rate,
                AVG(fill_percent) AS fill_percent,
                MAX(status) AS status
            FROM measurement
            GROUP BY tank_id, bucket;
        """)

        print("Successfully created materialized views")

        # Set retention policy via raw connection (autocommit)
        cursor.execute("""
            SELECT add_retention_policy('measurement', INTERVAL '90 days', if_not_exists => TRUE);
        """)
        print("Successfully set up TimescaleDB retention policies")

        cursor.close()
        raw_conn.close()

    except Exception as e:
        print(f"Error setting up TimescaleDB retention: {str(e)}")
