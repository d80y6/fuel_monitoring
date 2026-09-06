"""
Database migration support for the Fuel Tank Monitoring System
"""
from flask_migrate import Migrate
from models.database import db

migrate = Migrate()

def init_app(app):
    """Initialize migration support"""
    migrate.init_app(app, db)

def upgrade():
    # ... other operations ...
    with op.batch_alter_table('company', schema=None) as batch_op:
        batch_op.add_column(sa.Column('deleted_at', sa.DateTime(), nullable=True))
    
    # ... other operations ...
    
    with op.batch_alter_table('site', schema=None) as batch_op:
        batch_op.add_column(sa.Column('deleted_at', sa.DateTime(), nullable=True))
    
    with op.batch_alter_table('tank', schema=None) as batch_op:
        batch_op.add_column(sa.Column('deleted_at', sa.DateTime(), nullable=True))