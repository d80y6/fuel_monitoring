"""
Authentication and authorization utilities for the admin blueprint
"""
from functools import wraps
from flask import redirect, url_for, flash, current_app
from flask_login import current_user

def admin_required(f):
    """Decorator to require admin privileges for a route"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin():
            flash('Access denied. Admin privileges required.', 'danger')
            current_app.logger.warning(
                f"Access denied: User {current_user.username if current_user.is_authenticated else 'anonymous'} "
                f"attempted to access admin-only resource: {f.__name__}"
            )
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# Define permission constants
class Permissions:
    VIEW_USERS = 'view_users'
    EDIT_USERS = 'edit_users'
    VIEW_COMPANIES = 'view_companies'
    EDIT_COMPANIES = 'edit_companies'
    VIEW_SITES = 'view_sites'
    EDIT_SITES = 'edit_sites'
    VIEW_TANKS = 'view_tanks'
    EDIT_TANKS = 'edit_tanks'
    VIEW_ALARMS = 'view_alarms'
    EDIT_ALARMS = 'edit_alarms'

# Role-based permissions mapping
ROLE_PERMISSIONS = {
    'admin': ['*'],  # Admin has all permissions
    'company_admin': [
        Permissions.VIEW_USERS,
        Permissions.VIEW_COMPANIES,
        Permissions.VIEW_SITES,
        Permissions.EDIT_SITES,
        Permissions.VIEW_TANKS,
        Permissions.EDIT_TANKS,
        Permissions.VIEW_ALARMS,
        Permissions.EDIT_ALARMS,
    ],
    'user': [
        Permissions.VIEW_COMPANIES,
        Permissions.VIEW_SITES,
        Permissions.VIEW_TANKS,
        Permissions.VIEW_ALARMS,
    ]
}

def permission_required(permission):
    """Decorator to require specific permission for a route"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('Please log in to access this page.', 'warning')
                return redirect(url_for('auth.login'))
            
            # Check permission based on role
            user_permissions = ROLE_PERMISSIONS.get(current_user.role, [])
            if '*' not in user_permissions and permission not in user_permissions:
                flash('Access denied. You do not have permission to access this resource.', 'danger')
                current_app.logger.warning(
                    f"Permission denied: User {current_user.username} attempted to access "
                    f"resource requiring {permission} permission: {f.__name__}"
                )
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator