import sys
import os
import datetime
import time
import logging

# Add the parent directory to the path so we can import the app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app, db
from models.database import Measurement, create_timescale_extensions, setup_timescale_retention
from sqlalchemy import text

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("timescaledb_migration.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("timescaledb_migration")

def migrate_to_timescaledb():
    """Migrate existing measurement data to TimescaleDB"""
    with app.app_context():
        try:
            logger.info("Starting TimescaleDB migration...")
            
            # Step 1: Check if TimescaleDB extension is installed
            logger.info("Checking if TimescaleDB extension is installed...")
            result = db.session.execute(text("SELECT extname FROM pg_extension WHERE extname = 'timescaledb';"))
            if result.scalar() is None:
                logger.info("TimescaleDB extension not found. Installing...")
                db.session.execute(text('CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;'))
                db.session.commit()
                logger.info("TimescaleDB extension installed successfully.")
            else:
                logger.info("TimescaleDB extension is already installed.")
            
            # Step 2: Check if measurement table is already a hypertable
            logger.info("Checking if measurement table is already a hypertable...")
            result = db.session.execute(text(
                "SELECT * FROM timescaledb_information.hypertables WHERE hypertable_name = 'measurement';"
            ))
            is_hypertable = result.fetchone() is not None
            
            if is_hypertable:
                logger.info("Measurement table is already a hypertable. Skipping conversion.")
            else:
                # Step 3: Get total count of measurements for progress reporting
                total_measurements = db.session.query(Measurement).count()
                logger.info(f"Total measurements to migrate: {total_measurements}")
                
                # Step 4: Convert measurement table to hypertable
                logger.info("Converting measurement table to TimescaleDB hypertable...")
                db.session.execute(text(
                    "SELECT create_hypertable('measurement', 'timestamp', if_not_exists => TRUE, migrate_data => TRUE);"
                ))
                db.session.commit()
                logger.info("Successfully converted measurement table to hypertable.")
                
                # Step 5: Create index on tank_id and timestamp for better query performance
                logger.info("Creating optimized indexes...")
                db.session.execute(text(
                    "CREATE INDEX IF NOT EXISTS idx_measurement_tank_time ON measurement (tank_id, timestamp DESC);"
                ))
                db.session.commit()
                logger.info("Created optimized indexes.")
            
            # Step 6: Set up continuous aggregation policies
            logger.info("Setting up continuous aggregation policies...")
            setup_timescale_retention()
            logger.info("Continuous aggregation policies set up successfully.")
            
            # Step 7: Analyze the table for query optimization
            logger.info("Analyzing tables for query optimization...")
            db.session.execute(text("ANALYZE measurement;"))
            db.session.commit()
            logger.info("Table analysis complete.")
            
            logger.info("TimescaleDB migration completed successfully!")
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error during TimescaleDB migration: {str(e)}")
            raise

if __name__ == "__main__":
    start_time = time.time()
    try:
        migrate_to_timescaledb()
        elapsed_time = time.time() - start_time
        logger.info(f"Migration completed in {elapsed_time:.2f} seconds")
    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.error(f"Migration failed after {elapsed_time:.2f} seconds: {str(e)}")
        sys.exit(1)
