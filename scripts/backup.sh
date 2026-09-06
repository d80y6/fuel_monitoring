#!/bin/bash
# Daily backup script for PostgreSQL/TimescaleDB
PG_HOST="${PG_HOST:-localhost}"
PG_PORT="${PG_PORT:-5432}"
PG_DB="${PG_DB:-fuel_tank_monitoring}"
PG_USER="${PG_USER:-fuel_tank_user}"
BACKUP_DIR="${BACKUP_DIR:-/backups}"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

# Full database backup
pg_dump -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" \
    --format=custom \
    --file="$BACKUP_DIR/fuel_backup_$DATE.pgbackup" \
    --verbose

# WAL archiving
pg_start_backup "fuel_backup_$DATE" 2>/dev/null
# ... archiving logic

echo "Backup completed: $BACKUP_DIR/fuel_backup_$DATE.pgbackup"
# Keep only last 30 days
find "$BACKUP_DIR" -name "fuel_backup_*.pgbackup" -mtime +30 -delete
