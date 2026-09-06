
import os
import sys
from alembic import context
from sqlalchemy import engine_from_config, pool
from logging.config import fileConfig







# This is the Alembic Config object
config = context.config



# Interpret the config file for Python logging
fileConfig(config.config_file_name)


# Add your model's MetaData object here
from models.database import db
target_metadata = db.metadata


























# Other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.








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
    # Handle special commands for TimescaleDB that can't run in a transaction
    is_timescaledb_command = False
    for migration_script in context.get_revision_map().iterate_revisions('base', 'head'):
        if hasattr(migration_script, 'module') and migration_script.module:
            if 'timescaledb' in migration_script.module.__doc__.lower():
                is_timescaledb_command = True
                break



    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )



















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