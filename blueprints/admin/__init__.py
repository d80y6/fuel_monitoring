"""
Admin Blueprint for the Fuel Tank Monitoring System
"""
from flask import Blueprint

admin = Blueprint('admin', __name__, url_prefix='/admin')

# Constants for configuration
CONNECTION_TIMEOUT_MINUTES = 5
ITEMS_PER_PAGE = 10
RECENT_DISCONNECT_HOURS = 1
PASSWORD_PATTERN = r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}'

# Import views after blueprint creation (to avoid circular imports)
from . import dashboard, users, companies, sites, tanks, alarms, utils

# Initialize the admin blueprint
def init_admin(app):
    """Initialize admin blueprint with required components"""
    # Register the blueprint with the app
    app.register_blueprint(admin)
    
    # Add soft delete methods to models if not already present
    from models.database import User, Company, Site, Tank
    
    if not hasattr(User, 'not_deleted'):
        @classmethod
        def user_not_deleted(cls):
            """Query filter for not deleted users."""
            return cls.query.filter_by(deleted_at=None)
        User.not_deleted = user_not_deleted
    
    # Ensure deleted_at columns exist
    with app.app_context():
        utils.ensure_deleted_at_column()
    
    # Add soft delete methods to models
    utils.add_soft_delete_methods()
    
    return admin