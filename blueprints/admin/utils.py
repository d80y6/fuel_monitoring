"""
Utility functions for the admin blueprint
"""
from functools import wraps
from flask import flash, redirect, url_for, current_app, request
from models.database import db, User, Company, Site, Tank, ActivityLog
from datetime import datetime as dt

def handle_db_errors(f):
    """Decorator to handle database errors and provide consistent error handling"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except ValueError as e:
            flash(str(e), 'danger')
            db.session.rollback()
            current_app.logger.warning(f"Validation error in {f.__name__}: {str(e)}")
        except Exception as e:
            flash(f'An error occurred: {str(e)}', 'danger')
            db.session.rollback()
            current_app.logger.error(f"Database error in {f.__name__}: {str(e)}", exc_info=True)
        
        # Determine where to redirect based on the function name
        if 'user' in f.__name__:
            return redirect(url_for('admin.users'))
        elif 'company' in f.__name__:
            return redirect(url_for('admin.companies'))
        elif 'site' in f.__name__:
            return redirect(url_for('admin.sites'))
        elif 'tank' in f.__name__:
            return redirect(url_for('admin.tanks_index'))
        else:
            return redirect(url_for('admin.dashboard'))
    return decorated_function

def log_activity(action, details=None, user=None, ip_address=None):
    """Log an activity in the database.
    
    Args:
        action: The action performed
        details: Additional details about the action
        user: The user who performed the action (defaults to current_user)
        ip_address: The IP address of the user (defaults to request.remote_addr)
    """
    from flask_login import current_user
    
    try:
        if user is None and current_user.is_authenticated:
            user = current_user
        
        if ip_address is None:
            ip_address = request.remote_addr
        
        activity = ActivityLog(
            user_id=user.id if user else None,
            action=action,
            details=details,
            ip_address=ip_address
        )
        
        db.session.add(activity)
        db.session.commit()
        
        # Emit socket.io event for real-time updates
        try:
            from app import socketio
            socketio.emit('new_activity', {
                'id': activity.id,
                'timestamp': activity.timestamp.isoformat(),
                'user': {
                    'id': user.id,
                    'username': user.username
                } if user else None,
                'action': action,
                'details': details
            }, namespace='/admin')
        except ImportError:
            current_app.logger.warning("SocketIO not available for activity logging")
        
        return True
    except Exception as e:
        current_app.logger.error(f"Error logging activity: {str(e)}")
        db.session.rollback()
        return False

def add_soft_delete_methods():
    """Add soft delete methods to models"""
    
    def soft_delete(self):
        """Soft delete a record"""
        self.deleted_at = dt.now()
    
    def restore(self):
        """Restore a soft-deleted record"""
        self.deleted_at = None
    
    # Add methods to models
    for model in [User, Company, Site, Tank]:
        model.soft_delete = soft_delete
        model.restore = restore
        
        # Add class method for querying not deleted records
        @classmethod
        def not_deleted(cls):
            return cls.query.filter(cls.deleted_at == None)
        
        model.not_deleted = not_deleted

def ensure_deleted_at_column():
    """Ensure deleted_at column exists in models"""
    from sqlalchemy import inspect
    
    for model in [User, Company, Site, Tank]:
        inspector = inspect(model)
        if 'deleted_at' not in [c.name for c in inspector.columns]:
            # This would be done via a migration in a real application
            # For now, we'll just print a warning
            current_app.logger.warning(f"Warning: deleted_at column missing from {model.__name__} model")

def validate_date_range(start_date_str, end_date_str, max_days=365):
    """Validate a date range and return parsed dates
    
    Args:
        start_date_str: Start date string in format YYYY-MM-DD
        end_date_str: End date string in format YYYY-MM-DD
        max_days: Maximum number of days allowed between start and end
        
    Returns:
        tuple: (start_date, end_date) as datetime objects
        
    Raises:
        ValueError: If dates are invalid or range exceeds max_days
    """
    if not start_date_str or not end_date_str:
        raise ValueError("Both start and end dates are required")
    
    try:
        start_date = dt.strptime(start_date_str, '%Y-%m-%d')
        end_date = dt.strptime(end_date_str, '%Y-%m-%d')
    except ValueError:
        raise ValueError("Invalid date format. Use YYYY-MM-DD.")
    
    if start_date > end_date:
        raise ValueError("Start date must be before end date")
    
    if (end_date - start_date).days > max_days:
        raise ValueError(f"Date range cannot exceed {max_days} days")
    
    return start_date, end_date