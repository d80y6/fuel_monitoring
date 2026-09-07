import os
import sys
from alembic import context
from alembic.script import ScriptDirectory
from sqlalchemy import pool
from logging.config import fileConfig

# This is the Alembic Config object
config = context.config

# Interpret the config file for Python logging
fileConfig(config.config_file_name)

# Add your model's MetaData object here
from models.database import db
target_metadata = db.metadata


def run_migrations_offline():
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode."""
    # Retrieve the script directory directly from the config
    script = ScriptDirectory.from_config(config)
    
    # Check if any revision contains TimescaleDB logic
    is_timescaledb_command = False
    for migration_script in script.walk_revisions():
        if hasattr(migration_script, 'module') and migration_script.module:
            doc = getattr(migration_script.module, '__doc__', '') or ''
            if 'timescaledb' in doc.lower():
                is_timescaledb_command = True
                break

    # Get the Flask app's engine provided by Flask-Migrate
    connectable = config.attributes.get('engine', None)

    if connectable is None:
        # Fallback to current Flask app context if direct attribute isn't populated
        from flask import current_app
        connectable = current_app.extensions['migrate'].db.engine

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Set transaction_per_migration for TimescaleDB commands
            transaction_per_migration=is_timescaledb_command
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
