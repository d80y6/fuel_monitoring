"""Add missing indexes, columns, and TimescaleDB optimization.

Revision ID: a1b2c3d4e5f6
Revises: 4f6adc5392e7
Create Date: 2026-09-06

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'a1b2c3d4e5f6'
down_revision = '4f6adc5392e7'
branch_labels = None
depends_on = None

def upgrade():
    # Add missing columns to Tank model
    with op.batch_alter_table('tank', schema=None) as batch_op:
        batch_op.add_column(sa.Column('gateway_mac', sa.String(17), nullable=True, index=True))
        batch_op.add_column(sa.Column('sensor_serial_number', sa.BigInteger, nullable=True, unique=True))
        batch_op.add_column(sa.Column('connection_mode', sa.String(20), nullable=True))
        batch_op.add_column(sa.Column('level_hysteresis', sa.Float, nullable=True))
        batch_op.add_column(sa.Column('flow_threshold', sa.Float, nullable=True))
        batch_op.add_column(sa.Column('pressure_smoothing', sa.Boolean, nullable=True, server_default='1'))

    # Create composite indexes
    op.create_index('idx_measurement_gateway_time', 'measurement', ['gateway_mac', 'timestamp'])
    op.create_index('idx_measurement_tank_time_desc', 'measurement', ['tank_id', sa.text('timestamp DESC')])
    op.create_index('idx_measurement_tank_timestamp', 'measurement', ['tank_id', 'timestamp'])
    op.create_unique_constraint('uq_tank_sensor_serial_number', 'tank', ['sensor_serial_number'])
    op.create_index('idx_alarm_tank_ack_time', 'alarm', ['tank_id', 'acknowledged', 'timestamp'])
    op.create_index('idx_tank_gateway_mac', 'tank', ['gateway_mac'], postgresql_where=sa.text("deleted_at IS NULL"))

    # TimescaleDB hypertable
    op.execute("""
        SELECT create_hypertable('measurement', 'timestamp', if_not_exists => TRUE, migrate_data => TRUE, chunk_time_interval => interval '1 day');
    """)

    # Retention policy
    op.execute("SELECT add_retention_policy('measurement', INTERVAL '90 days');")

    # Continuous aggregates
    op.execute("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS measurements_hourly WITH (timescaledb.continuous) AS
        SELECT tank_id, time_bucket('1 hour', timestamp) AS bucket,
               AVG(pressure) AS avg_pressure, AVG(temperature) AS avg_temperature,
               AVG(level) AS avg_level, AVG(volume) AS avg_volume,
               AVG(flow_rate) AS avg_flow_rate, AVG(fill_percent) AS avg_fill_percent,
               MIN(volume) AS min_volume, MAX(volume) AS max_volume,
               COUNT(*) AS reading_count, MAX(status) AS max_status
        FROM measurement GROUP BY tank_id, bucket;
    """)

    op.execute("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS measurements_daily WITH (timescaledb.continuous) AS
        SELECT tank_id, time_bucket('1 day', timestamp) AS bucket,
               AVG(pressure) AS avg_pressure, AVG(temperature) AS avg_temperature,
               AVG(level) AS avg_level, AVG(volume) AS avg_volume,
               AVG(flow_rate) AS avg_flow_rate, AVG(fill_percent) AS avg_fill_percent,
               MIN(volume) AS min_volume, MAX(volume) AS max_volume,
               COUNT(*) AS reading_count, MAX(status) AS max_status
        FROM measurement GROUP BY tank_id, bucket;
    """)

    # Refresh policies
    op.execute("SELECT add_continuous_aggregate_refresh_policy('measurements_hourly', INTERVAL '1 hour');")
    op.execute("SELECT add_continuous_aggregate_refresh_policy('measurements_daily', INTERVAL '1 day');")

    # Compression policy
    op.execute("SELECT add_compression_policy('measurement', INTERVAL '7 days');")
    op.execute("ALTER MATERIALIZED VIEW measurements_hourly SET (timescaledb.compress);")
    op.execute("ALTER MATERIALIZED VIEW measurements_daily SET (timescaledb.compress);")

def downgrade():
    op.drop_index('idx_measurement_gateway_time', table_name='measurement')
    op.drop_index('idx_measurement_tank_time_desc', table_name='measurement')
    op.drop_index('idx_measurement_tank_timestamp', table_name='measurement')
    op.drop_index('idx_alarm_tank_ack_time', table_name='alarm')
    op.drop_index('idx_tank_gateway_mac', table_name='tank')
    op.drop_constraint('uq_tank_sensor_serial_number', 'tank', type_='unique')
    
    with op.batch_alter_table('tank', schema=None) as batch_op:
        batch_op.drop_column('gateway_mac')
        batch_op.drop_column('sensor_serial_number')
        batch_op.drop_column('connection_mode')
        batch_op.drop_column('level_hysteresis')
        batch_op.drop_column('flow_threshold')
        batch_op.drop_column('pressure_smoothing')
    
    op.execute("DROP MATERIALIZED VIEW IF EXISTS measurements_hourly CASCADE;")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS measurements_daily CASCADE;")
    op.execute("SELECT remove_retention_policy('measurement');")
    op.execute("SELECT remove_compression_policy('measurement');")
