> **ARCHIVE — LEGACY FLASK BUILD (2026-09-06).** This document describes the now-deleted Flask-era codebase (Flask/Jinja templates). It is historical reference only and does **NOT** describe the current system, which is a FastAPI + React platform. Do not treat structure, tests, or claims in this file as current.

# Database Migration & Indexing Script

## Overview
This script provides all necessary database migrations for optimizing TimescaleDB performance, including:
- Composite and unique indexes
- TimescaleDB hypertable conversion
- Compression policies
- Continuous aggregate refresh policies
- Data retention and downsample policies

---

## 1. Alembic Migration: Add Missing Indexes and Columns

```python
"""Add missing indexes, columns, and TimescaleDB optimization.

Revision ID: a1b2c3d4e5f6_add_timescale_optimization
Revises: 4f6adc5392e7
Create Date: 2026-09-06

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 'a1b2c3d4e5f6'
down_revision = '4f6adc5392e7'
branch_labels = None
depends_on = None


def upgrade():
    # ── Add missing columns to Tank model ──
    with op.batch_alter_table('tank', schema=None) as batch_op:
        batch_op.add_column(sa.Column('gateway_mac', sa.String(17), nullable=True, index=True))
        batch_op.add_column(sa.Column('sensor_serial_number', sa.BigInteger, nullable=True, unique=True))
        batch_op.add_column(sa.Column('connection_mode', sa.String(20), nullable=True, server_default='mqtt'))
        batch_op.add_column(sa.Column('level_hysteresis', sa.Float, nullable=True))
        batch_op.add_column(sa.Column('flow_threshold', sa.Float, nullable=True))
        batch_op.add_column(sa.Column('pressure_smoothing', sa.Boolean, nullable=True, server_default=True))

    # ── Create composite indexes ──
    # Composite index for gateway MAC + timestamp (most common query pattern)
    op.create_index(
        'idx_measurement_gateway_time',
        'measurement',
        ['gateway_mac', 'timestamp'],
        postgresql_ops={'gateway_mac': 'text_pattern_ops'},
        unique=False,
    )

    # Composite index for tank_id + timestamp DESC (dashboard queries)
    op.create_index(
        'idx_measurement_tank_time_desc',
        'measurement',
        ['tank_id', postgresql.desc(sa.text('timestamp'))],
        unique=False,
    )

    # Composite index for tank_id + timestamp (range queries)
    op.create_index(
        'idx_measurement_tank_timestamp',
        'measurement',
        ['tank_id', 'timestamp'],
        unique=False,
    )

    # Unique index for sensor serial numbers (immutable identifier)
    op.create_unique_constraint(
        'uq_tank_sensor_serial_number',
        'tank',
        ['sensor_serial_number'],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # Index for alarm lookups by tank + acknowledged + timestamp
    op.create_index(
        'idx_alarm_tank_ack_time',
        'alarm',
        ['tank_id', 'acknowledged', 'timestamp'],
        unique=False,
    )

    # Index for tank lookup by gateway MAC
    op.create_index(
        'idx_tank_gateway_mac',
        'tank',
        ['gateway_mac'],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # ── TimescaleDB Hypertable Setup ──
    # Note: This should ideally be run as a separate SQL script via op.execute()
    # but included here for completeness

    op.execute("""
        SELECT create_hypertable(
            'measurement',
            'timestamp',
            if_not_exists => TRUE,
            migrate_data => TRUE,
            chunk_time_interval => interval '1 day'
        );
    """)

    # ── Data Retention Policy ──
    op.execute("""
        SELECT add_retention_policy('measurement', INTERVAL '90 days');
    """)

    # ── Continuous Aggregates ──
    # Hourly materialized view
    op.execute("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS measurements_hourly
        WITH (timescaledb.continuous) AS
        SELECT
            tank_id,
            time_bucket('1 hour', timestamp) AS bucket,
            AVG(pressure) AS avg_pressure,
            AVG(temperature) AS avg_temperature,
            AVG(level) AS avg_level,
            AVG(volume) AS avg_volume,
            AVG(flow_rate) AS avg_flow_rate,
            AVG(fill_percent) AS avg_fill_percent,
            MIN(volume) AS min_volume,
            MAX(volume) AS max_volume,
            COUNT(*) AS reading_count,
            MAX(status) AS max_status
        FROM measurement
        GROUP BY tank_id, bucket;
    """)

    # Daily materialized view
    op.execute("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS measurements_daily
        WITH (timescaledb.continuous) AS
        SELECT
            tank_id,
            time_bucket('1 day', timestamp) AS bucket,
            AVG(pressure) AS avg_pressure,
            AVG(temperature) AS avg_temperature,
            AVG(level) AS avg_level,
            AVG(volume) AS avg_volume,
            AVG(flow_rate) AS avg_flow_rate,
            AVG(fill_percent) AS avg_fill_percent,
            MIN(volume) AS min_volume,
            MAX(volume) AS max_volume,
            COUNT(*) AS reading_count,
            MAX(status) AS max_status
        FROM measurement
        GROUP BY tank_id, bucket;
    """)

    # ── Continuous Aggregate Refresh Policies ──
    # Hourly refresh
    op.execute("""
        SELECT add_continuous_aggregate_refresh_policy('measurements_hourly', INTERVAL '1 hour');
    """)

    # Daily refresh
    op.execute("""
        SELECT add_continuous_aggregate_refresh_policy('measurements_daily', INTERVAL '1 day');
    """)

    # ── Compression Policy ──
    # Enable compression on the measurement hypertable
    op.execute("""
        SELECT add_compression_policy('measurement', INTERVAL '7 days');
    """)

    # Enable compression on continuous aggregates
    op.execute("""
        ALTER MATERIALIZED VIEW measurements_hourly SET (timescaledb.compress);
        ALTER MATERIALIZED VIEW measurements_daily SET (timescaledb.compress);
    """)

    # ── Add compression column annotations ──
    op.execute("""
        ALTER TABLE measurement ALTER COLUMN pressure SET STORAGE EXTERNAL;
        ALTER TABLE measurement ALTER COLUMN temperature SET STORAGE EXTERNAL;
        ALTER TABLE measurement ALTER COLUMN level SET STORAGE EXTERNAL;
        ALTER TABLE measurement ALTER COLUMN volume SET STORAGE EXTERNAL;
        ALTER TABLE measurement ALTER COLUMN flow_rate SET STORAGE EXTERNAL;
        ALTER TABLE measurement ALTER COLUMN fill_percent SET STORAGE EXTERNAL;
    """)


def downgrade():
    # Drop indexes
    op.drop_index('idx_measurement_gateway_time', table_name='measurement')
    op.drop_index('idx_measurement_tank_time_desc', table_name='measurement')
    op.drop_index('idx_measurement_tank_timestamp', table_name='measurement')
    op.drop_index('idx_alarm_tank_ack_time', table_name='alarm')
    op.drop_index('idx_tank_gateway_mac', table_name='tank')

    # Drop unique constraint
    op.drop_constraint('uq_tank_sensor_serial_number', 'tank', type_='unique')

    # Remove columns
    with op.batch_alter_table('tank', schema=None) as batch_op:
        batch_op.drop_column('gateway_mac')
        batch_op.drop_column('sensor_serial_number')
        batch_op.drop_column('connection_mode')
        batch_op.drop_column('level_hysteresis')
        batch_op.drop_column('flow_threshold')
        batch_op.drop_column('pressure_smoothing')

    # Drop materialized views
    op.execute("DROP MATERIALIZED VIEW IF EXISTS measurements_hourly CASCADE;")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS measurements_daily CASCADE;")

    # Remove retention policy
    op.execute("SELECT remove_retention_policy('measurement');")

    # Remove compression policy
    op.execute("SELECT remove_compression_policy('measurement');")
```

---

## 2. Standalone SQL Migration Script (Run Against Database)

```sql
-- =============================================
-- Fuel Monitoring Platform — TimescaleDB Optimization
-- Run against PostgreSQL with TimescaleDB extension
-- =============================================

BEGIN;

-- ── 1. Enable TimescaleDB Extension ──
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- ── 2. Convert measurement table to hypertable ──
SELECT create_hypertable(
    'measurement',
    'timestamp',
    if_not_exists => TRUE,
    migrate_data => TRUE,
    chunk_time_interval => interval '1 day'
);

-- ── 3. Create Composite Indexes ──
CREATE INDEX IF NOT EXISTS idx_measurement_gateway_time
    ON measurement (gateway_mac, timestamp);

CREATE INDEX IF NOT EXISTS idx_measurement_tank_time_desc
    ON measurement (tank_id, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_measurement_tank_timestamp
    ON measurement (tank_id, timestamp);

-- ── 4. Create Unique Constraint for Sensor Serial Numbers ──
CREATE UNIQUE INDEX IF NOT EXISTS uq_tank_sensor_serial_number_active
    ON tank (sensor_serial_number)
    WHERE deleted_at IS NULL;

-- ── 5. Index for Tank Lookup by Gateway MAC ──
CREATE INDEX IF NOT EXISTS idx_tank_gateway_mac_active
    ON tank (gateway_mac)
    WHERE deleted_at IS NULL;

-- ── 6. Alarm Lookup Index ──
CREATE INDEX IF NOT EXISTS idx_alarm_tank_ack_time
    ON alarm (tank_id, acknowledged, timestamp);

-- ── 7. Data Retention Policy (90 days) ──
SELECT add_retention_policy('measurement', INTERVAL '90 days');

-- ── 8. Continuous Aggregates ──
CREATE MATERIALIZED VIEW IF NOT EXISTS measurements_hourly
WITH (timescaledb.continuous) AS
SELECT
    tank_id,
    time_bucket('1 hour', timestamp) AS bucket,
    AVG(pressure) AS avg_pressure,
    AVG(temperature) AS avg_temperature,
    AVG(level) AS avg_level,
    AVG(volume) AS avg_volume,
    AVG(flow_rate) AS avg_flow_rate,
    AVG(fill_percent) AS avg_fill_percent,
    MIN(volume) AS min_volume,
    MAX(volume) AS max_volume,
    COUNT(*) AS reading_count,
    MAX(status) AS max_status
FROM measurement
GROUP BY tank_id, bucket;

CREATE MATERIALIZED VIEW IF NOT EXISTS measurements_daily
WITH (timescaledb.continuous) AS
SELECT
    tank_id,
    time_bucket('1 day', timestamp) AS bucket,
    AVG(pressure) AS avg_pressure,
    AVG(temperature) AS avg_temperature,
    AVG(level) AS avg_level,
    AVG(volume) AS avg_volume,
    AVG(flow_rate) AS avg_flow_rate,
    AVG(fill_percent) AS avg_fill_percent,
    MIN(volume) AS min_volume,
    MAX(volume) AS max_volume,
    COUNT(*) AS reading_count,
    MAX(status) AS max_status
FROM measurement
GROUP BY tank_id, bucket;

-- ── 9. Continuous Aggregate Refresh Policies ──
SELECT add_continuous_aggregate_refresh_policy('measurements_hourly', INTERVAL '1 hour');
SELECT add_continuous_aggregate_refresh_policy('measurements_daily', INTERVAL '1 day');

-- ── 10. Compression Policy ──
SELECT add_compression_policy('measurement', INTERVAL '7 days');

-- Enable compression on continuous aggregates
ALTER MATERIALIZED VIEW measurements_hourly SET (timescaledb.compress);
ALTER MATERIALIZED VIEW measurements_daily SET (timescaledb.compress);

-- ── 11. Optimize Column Storage ──
ALTER TABLE measurement ALTER COLUMN pressure SET STORAGE EXTERNAL;
ALTER TABLE measurement ALTER COLUMN temperature SET STORAGE EXTERNAL;
ALTER TABLE measurement ALTER COLUMN level SET STORAGE EXTERNAL;
ALTER TABLE measurement ALTER COLUMN volume SET STORAGE EXTERNAL;
ALTER TABLE measurement ALTER COLUMN flow_rate SET STORAGE EXTERNAL;
ALTER TABLE measurement ALTER COLUMN fill_percent SET STORAGE EXTERNAL;

-- ── 12. Analyze tables for query optimization ──
ANALYZE measurement;
ANALYZE tank;
ANALYZE alarm;

COMMIT;
```

---

## 3. Index Usage Verification Query

```sql
-- Verify all indexes are being used
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef,
    pg_relation_size(indexrelid) AS index_size
FROM pg_stat_user_indexes
JOIN pg_index ON pg_stat_user_indexes.indexrelid = pg_index.indexrelid
WHERE schemaname = 'public'
    AND tablename IN ('measurement', 'tank', 'alarm')
ORDER BY pg_relation_size(indexrelid) DESC;

-- Check hypertable chunk statistics
SELECT
    hypertable_name,
    chunk_name,
    chunk_schema,
    compressed_chunk_size,
    total_rows
FROM timescaledb_information.chunks
WHERE hypertable_name = 'measurement'
ORDER BY compressed_chunk_size DESC
LIMIT 20;

-- Check compression ratio
SELECT
    table_name,
    compression_state,
    compression_ratio
FROM timescaledb_information.compression_stats
WHERE table_name = 'measurement';
```

---

## 4. Connection Pooling Configuration (pgbouncer recommended)

```ini
# /etc/pgbouncer/pgbouncer.ini
[databases]
fuel_tank_monitoring = host=localhost port=5432 dbname=fuel_tank_monitoring

[pgbouncer]
listen_addr = 0.0.0.0
listen_port = 6432
auth_type = md5
auth_file = /etc/pgbouncer/userlist.txt
pool_mode = transaction
max_client_conn = 1000
default_pool_size = 100
reserve_pool_size = 20
reserve_pool_timeout = 5
server_idle_timeout = 300
server_lifetime = 3600
server_connect_timeout = 10
```

---

## 5. TimescaleDB Configuration Tuning

```sql
-- Set TimescaleDB parallelism for compression
ALTER SYSTEM SET timescaledb.max_background_workers = 4;
ALTER SYSTEM SET timescaledb.max_parallel_workers_per_gather = 2;

-- Increase shared buffers for better compression
ALTER SYSTEM SET shared_buffers = '4GB';
ALTER SYSTEM SET effective_cache_size = '12GB';
ALTER SYSTEM SET work_mem = '64MB';
ALTER SYSTEM SET maintenance_work_mem = '512MB';

-- WAL configuration for high-throughput ingestion
ALTER SYSTEM SET wal_buffers = '64MB';
ALTER SYSTEM SET checkpoint_completion_target = 0.9;
ALTER SYSTEM SET max_wal_size = '4GB';
```
