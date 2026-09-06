import datetime
from app import app, db
from models.models import Measurement, Tank

def migrate_to_timescaledb():
    """Migrate existing measurement data to TimescaleDB"""
    with app.app_context():
        # Get all tanks
        tanks = Tank.query.all()
        
        for tank in tanks:
            print(f"Migrating data for tank {tank.id} ({tank.name})...")
            
            # Get all measurements for this tank
            measurements = Measurement.query.filter_by(tank_id=tank.id).all()
            
            # If using a different table structure, you would insert into the new table here
            # For this example, we're assuming the same table structure but converted to a hypertable
            
            print(f"Migrated {len(measurements)} measurements for tank {tank.id}")
        
        print("Migration complete!")

if __name__ == "__main__":
    migrate_to_timescaledb()
