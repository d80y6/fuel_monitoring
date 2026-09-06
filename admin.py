"""
Admin Blueprint for the Fuel Tank Monitoring System

This module provides admin functionality including user management,
company management, site management, and tank management.
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from models.database import db, User, Company, Site, Tank, Alarm, Measurement, ActivityLog
from wtforms import StringField, TextAreaField, SubmitField, PasswordField, BooleanField
from wtforms import IntegerField, SelectField, FloatField
from wtforms.validators import DataRequired, Length, Email, ValidationError, Regexp
from flask_wtf import FlaskForm
from sqlalchemy import func, text, and_, desc
from datetime import datetime as dt, time, timedelta
from functools import wraps
from threading import Thread

# Constants for configuration
ITEMS_PER_PAGE = 10
CONNECTION_TIMEOUT_MINUTES = 5
RECENT_DISCONNECT_HOURS = 1

# Password validation pattern
PASSWORD_PATTERN = r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$'

# Company management
class CreateCompanyForm(FlaskForm):
    name = StringField('Company Name', validators=[DataRequired(), Length(max=255)])
    address = TextAreaField('Address', validators=[Length(max=1024)])
    contact_name = StringField('Contact Name', validators=[Length(max=255)])
    contact_email = StringField('Contact Email', validators=[Email(), Length(max=255)])
    contact_phone = StringField('Contact Phone', validators=[Length(max=20)])
    submit = SubmitField('Create Company')

class EditCompanyForm(FlaskForm):
    name = StringField('Company Name', validators=[DataRequired(), Length(max=255)])
    address = TextAreaField('Address', validators=[Length(max=1024)])
    contact_name = StringField('Contact Name', validators=[Length(max=255)])
    contact_email = StringField('Contact Email', validators=[Email(), Length(max=255)])
    contact_phone = StringField('Contact Phone', validators=[Length(max=20)])
    submit = SubmitField('Update Company')

# User management forms
class UserForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=64)])
    email = StringField('Email', validators=[DataRequired(), Email(), Length(max=120)])
    first_name = StringField('First Name', validators=[Length(max=64)])
    last_name = StringField('Last Name', validators=[Length(max=64)])
    role = StringField('Role', validators=[DataRequired()])
    
    # Custom password validation
    def validate_password(form, field):
        if field.data and not re.match(PASSWORD_PATTERN, field.data):
            raise ValidationError('Password must be at least 8 characters long and contain at least one uppercase letter, one lowercase letter, and one digit')

class CreateUserForm(UserForm):
    password = PasswordField('Password', validators=[DataRequired()])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired()])
    submit = SubmitField('Create User')
    
    def validate_confirm_password(form, field):
        if field.data != form.password.data:
            raise ValidationError('Passwords do not match')

class EditUserForm(UserForm):
    password = PasswordField('Password', validators=[])
    confirm_password = PasswordField('Confirm Password', validators=[])
    submit = SubmitField('Update User')
    
    def validate_confirm_password(form, field):
        if form.password.data and field.data != form.password.data:
            raise ValidationError('Passwords do not match')

# Create blueprint
admin = Blueprint('admin', __name__, url_prefix='/admin')

# Admin required decorator
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin():
            flash('Access denied. Admin privileges required.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# Error handling decorator
def handle_db_errors(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except ValueError as e:
            flash(str(e), 'danger')
            db.session.rollback()
        except Exception as e:
            flash(f'An error occurred: {str(e)}', 'danger')
            db.session.rollback()
        
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
# Admin dashboard
@admin.route('/', endpoint='admin_index')
@admin_required
def index():
    """Admin dashboard"""
    # Get counts
    user_count = User.not_deleted().count()
    company_count = Company.not_deleted().count()
    site_count = Site.not_deleted().count()
    tank_count = Tank.not_deleted().count()
    alarm_count = Alarm.query.filter_by(acknowledged=False).count()
    # Additional System Information
    system_version = "1.0.0"  # Replace with actual version retrieval
    server_time = dt.now().strftime('%M-%d %H:%M')
    db_size = "Unknown"  # Replace with actual database size retrieval
    active_alarm_count = Alarm.query.filter_by(acknowledged=False).count()
    
    # Count connected tanks
    five_minutes_ago = dt.now() - timedelta(minutes=CONNECTION_TIMEOUT_MINUTES)
    connected_tank_count = Tank.not_deleted().filter(Tank.last_connection >= five_minutes_ago).count()
    
    return render_template('admin/index.html', 
                          user_count=user_count,
                          company_count=company_count,
                          site_count=site_count,
                          tank_count=tank_count,
                          alarm_count=alarm_count,
                          system_version=system_version,
                          server_time=server_time,
                          db_size=db_size,
                          active_alarm_count=active_alarm_count,
                          connected_tank_count=connected_tank_count)

# Alarm management
@admin.route('/alarms', endpoint='alarms_index')
@admin_required
def alarms_view():
    """Alarm list"""
    # Get filter parameters
    acknowledged = request.args.get('acknowledged', 'all')
    level = request.args.get('level', 'all')
    
    # Build query
    query = Alarm.query
    
    if acknowledged != 'all':
        query = query.filter_by(acknowledged=(acknowledged == 'true'))
    
    if level != 'all':
        query = query.filter_by(level=level)
    
    # Get alarms
    alarms = query.order_by(Alarm.timestamp.desc()).all()
    
    return render_template('admin/alarms.html', alarms=alarms, acknowledged=acknowledged, level=level)

@admin.route('/alarms/acknowledge/<int:alarm_id>', methods=['POST'])
@admin_required
@handle_db_errors
def acknowledge_alarm(alarm_id):
    """Acknowledge alarm"""
    alarm = Alarm.query.get_or_404(alarm_id)
    
    # Acknowledge alarm
    alarm.acknowledged = True
    alarm.acknowledged_by = current_user.id
    alarm.acknowledged_at = dt.now()
    
    db.session.commit()
    
    # Check if this is an AJAX request
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'success': True,
            'message': 'Alarm acknowledged successfully'
        })
    
    flash('Alarm acknowledged successfully', 'success')
    return redirect(url_for('admin.alarms_index'))

@admin.route('/alarms/delete/<int:alarm_id>', methods=['POST'])
@admin_required
@handle_db_errors
def delete_alarm(alarm_id):
    """Delete alarm"""
    alarm = Alarm.query.get_or_404(alarm_id)
    
    # Delete alarm
    db.session.delete(alarm)
    db.session.commit()
    
    flash('Alarm deleted successfully', 'success')
    return redirect(url_for('admin.alarms_index'))

@admin.route('/alarms/clear-all', methods=['POST'])
@admin_required
@handle_db_errors
def clear_all_alarms():
    """Clear all alarms"""
    # Get filter parameters
    acknowledged = request.form.get('acknowledged', 'false')
    level = request.form.get('level', 'all')
    
    # Build query
    query = Alarm.query
    
    if acknowledged == 'false':
        query = query.filter_by(acknowledged=False)
    elif acknowledged == 'true':
        query = query.filter_by(acknowledged=True)
    
    if level != 'all':
        query = query.filter_by(level=level)
    
    # Delete alarms
    query.delete()
    db.session.commit()
    
    flash('Alarms cleared successfully', 'success')
    return redirect(url_for('admin.alarms_index'))

# User management
@admin.route('/users')
@admin_required
def users():
    """User list"""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    
    query = User.not_deleted()
    
    if search:
        query = query.filter(
            db.or_(
                User.username.ilike(f'%{search}%'),
                User.email.ilike(f'%{search}%'),
                User.first_name.ilike(f'%{search}%'),
                User.last_name.ilike(f'%{search}%')
            )
        )
    
    pagination = query.paginate(page=page, per_page=ITEMS_PER_PAGE, error_out=False)
    users = pagination.items
    
    return render_template('admin/users.html', 
                          users=users, 
                          current_user=current_user,
                          pagination=pagination,
                          search=search)

@admin.route('/api/users')
@admin_required
def api_users():
    """API endpoint for user list"""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '', type=str)
    role = request.args.get('role', 'all', type=str)
    status = request.args.get('status', 'all', type=str)
    per_page = ITEMS_PER_PAGE

    query = User.not_deleted()

    # Apply search filter
    if search:
        query = query.filter(
            db.or_(
                func.lower(User.username).contains(func.lower(search)),
                func.lower(User.email).contains(func.lower(search)),
                func.lower(User.first_name).contains(func.lower(search)),
                func.lower(User.last_name).contains(func.lower(search))
            )
        )

    # Apply role filter
    if role != 'all':
        query = query.filter_by(role=role)

    # Apply status filter
    if status == 'active':
        query = query.filter_by(is_active=True)
    elif status == 'inactive':
        query = query.filter_by(is_active=False)

    # Paginate the results
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    users = pagination.items

    # Prepare the data for JSON response
    user_data = []
    for user in users:
        user_data.append({
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'full_name': user.get_full_name(),
            'role': user.role,
            'is_active': user.is_active if hasattr(user, 'is_active') else True,
            'created_at': user.created_at.isoformat() if user.created_at else None,
            'last_login': user.last_login.isoformat() if user.last_login else None
        })

    return jsonify({
        'success': True,
        'users': user_data,
        'total': pagination.total,
        'page': page
    })

@admin.route('/api/users/<int:user_id>')
@admin_required
def api_user_detail(user_id):
    """API endpoint for user detail"""
    user = User.query.get_or_404(user_id)
    
    user_data = {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'role': user.role,
        'is_active': user.is_active if hasattr(user, 'is_active') else True,
        'created_at': user.created_at.isoformat() if user.created_at else None,
        'last_login': user.last_login.isoformat() if user.last_login else None
    }
    
    return jsonify({
        'success': True,
        'user': user_data
    })

@admin.route('/users/create', methods=['GET', 'POST'])
@admin_required
@handle_db_errors
def new_user():
    """Create new user"""
    companies = Company.not_deleted().all()
    sites = Site.not_deleted().all()
    
    if request.method == 'POST':
        # Extract form data
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        role = request.form.get('role')
        is_active = 'is_active' in request.form
        
        # Validate required fields
        if not username or not email or not password or not confirm_password or not first_name or not last_name or not role:
            flash('All required fields must be filled', 'danger')
            return render_template('admin/user_form.html', user=None, companies=companies, sites=sites)
        
        # Validate password match
        if password != confirm_password:
            flash('Passwords do not match', 'danger')
            return render_template('admin/user_form.html', user=None, companies=companies, sites=sites)
        
        # Check if username or email already exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'danger')
            return render_template('admin/user_form.html', user=None, companies=companies, sites=sites)
        
        if User.query.filter_by(email=email).first():
            flash('Email already exists', 'danger')
            return render_template('admin/user_form.html', user=None, companies=companies, sites=sites)
        
        # Create new user
        user = User(
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name,
            role=role,
            is_active=is_active
        )
        
        try:
            user.set_password(password)
        except ValueError as e:
            flash(str(e), 'danger')
            return render_template('admin/user_form.html', user=None, companies=companies, sites=sites)
        
        db.session.add(user)
        
        # Get selected companies and sites
        company_ids = request.form.getlist('companies')
        site_ids = request.form.getlist('sites')
        
        # Convert IDs to integers
        company_ids = [int(id) for id in company_ids if id.isdigit()]
        site_ids = [int(id) for id in site_ids if id.isdigit()]
        
        # Assign companies and sites
        if company_ids:
            user.companies = Company.not_deleted().filter(Company.id.in_(company_ids)).all()
        
        if site_ids:
            user.sites = Site.not_deleted().filter(Site.id.in_(site_ids)).all()
        
        db.session.commit()
        
        # Log the activity
        log_activity(
            action="user_created",
            details=f"Created user '{user.username}' with role '{user.role}'"
        )
        
        flash('User created successfully', 'success')
        return redirect(url_for('admin.users'))
    
    return render_template('admin/user_form.html', user=None, companies=companies, sites=sites)

@admin.route('/users/edit/<int:user_id>', methods=['GET', 'POST'])
@admin_required
@handle_db_errors
def edit_user(user_id):
    """Edit user"""
    user = User.query.get_or_404(user_id)
    companies = Company.not_deleted().all()
    sites = Site.not_deleted().all()
    
    # Get user activity logs for display
    user_logs = ActivityLog.query.filter_by(user_id=user_id).order_by(ActivityLog.timestamp.desc()).limit(10).all()
    
    if request.method == 'POST':
        # Extract form data
        email = request.form.get('email')
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        role = request.form.get('role')
        is_active = 'is_active' in request.form
        
        # Validate required fields
        if not email or not first_name or not last_name or not role:
            flash('All required fields must be filled', 'danger')
            return render_template('admin/user_form.html', user=user, companies=companies, sites=sites, user_logs=user_logs)
        
        # Check if email already exists (for another user)
        existing_user = User.query.filter_by(email=email).first()
        if existing_user and existing_user.id != user.id:
            flash('Email already exists', 'danger')
            return render_template('admin/user_form.html', user=user, companies=companies, sites=sites, user_logs=user_logs)
        
        # Store original values for activity log
        original_role = user.role
        original_is_active = user.is_active
        
        # Update user data
        user.email = email
        user.first_name = first_name
        user.last_name = last_name
        user.role = role
        user.is_active = is_active
        
        # Get selected companies and sites
        company_ids = request.form.getlist('companies')
        site_ids = request.form.getlist('sites')
        
        # Convert IDs to integers
        company_ids = [int(id) for id in company_ids if id.isdigit()]
        site_ids = [int(id) for id in site_ids if id.isdigit()]
        
        # Get original access for activity log
        original_companies = [c.id for c in user.companies]
        original_sites = [s.id for s in user.sites]
        
        # Update user's companies and sites
        user.companies = Company.not_deleted().filter(Company.id.in_(company_ids)).all()
        user.sites = Site.not_deleted().filter(Site.id.in_(site_ids)).all()
        
        db.session.commit()
        
        # Log the activity with detailed changes
        changes = []
        if original_role != user.role:
            changes.append(f"role from '{original_role}' to '{user.role}'")
        if original_is_active != user.is_active:
            changes.append(f"status from '{'active' if original_is_active else 'inactive'}' to '{'active' if user.is_active else 'inactive'}'")
        
        added_companies = [c for c in company_ids if c not in original_companies]
        removed_companies = [c for c in original_companies if c not in company_ids]
        added_sites = [s for s in site_ids if s not in original_sites]
        removed_sites = [s for s in original_sites if s not in site_ids]
        
        if added_companies:
            changes.append(f"added {len(added_companies)} companies")
        if removed_companies:
            changes.append(f"removed {len(removed_companies)} companies")
        if added_sites:
            changes.append(f"added {len(added_sites)} sites")
        if removed_sites:
            changes.append(f"removed {len(removed_sites)} sites")
        
        log_details = f"Updated user '{user.username}'"
        if changes:
            log_details += ": " + ", ".join(changes)
            
        log_activity(
            action="user_updated",
            details=log_details
        )
        
        flash('User updated successfully', 'success')
        return redirect(url_for('admin.users'))
    
    return render_template('admin/user_form.html', user=user, companies=companies, sites=sites, user_logs=user_logs)

@admin.route('/api/users/<int:user_id>/reset-password', methods=['POST'])
@admin_required
@handle_db_errors
def reset_user_password(user_id):
    """Reset user password and return new password"""
    user = User.query.get_or_404(user_id)
    
    # Generate a random password
    import random
    import string
    password_length = 12
    password_chars = string.ascii_letters + string.digits + "!@#$%^&*"
    new_password = ''.join(random.choice(password_chars) for i in range(password_length))
    
    # Ensure password meets complexity requirements
    # At least one uppercase, one lowercase, one digit
    while not (any(c.isupper() for c in new_password) and 
               any(c.islower() for c in new_password) and 
               any(c.isdigit() for c in new_password)):
        new_password = ''.join(random.choice(password_chars) for i in range(password_length))
    
    try:
        user.set_password(new_password)
        db.session.commit()
        
        # Log the activity
        log_activity(
            action="password_reset",
            details=f"Reset password for user '{user.username}'"
        )
        
        return jsonify({
            'success': True,
            'password': new_password
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@admin.route('/users/delete/<int:user_id>', methods=['POST'])
@admin_required
@handle_db_errors
def delete_user(user_id):
    """Delete user"""
    user = User.query.get_or_404(user_id)

    # Prevent deleting self
    if user.id == current_user.id:
        flash('Cannot delete yourself', 'danger')
        return redirect(url_for('admin.users'))

    # Store username for activity log
    username = user.username
    # Use soft delete instead of hard delete
    user.soft_delete()
    db.session.commit()

    # Log the activity
    log_activity(
        action="user_deleted",
        details=f"Deleted user '{username}'"
    )

    flash('User deleted successfully', 'success')
    return redirect(url_for('admin.users'))

@admin.route('/users/access/<int:user_id>', methods=['GET', 'POST'])
@admin_required
@handle_db_errors
def user_access(user_id):
    """Manage user access to companies and sites"""
    user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        # Get selected companies and sites
        company_ids = request.form.getlist('companies')
        site_ids = request.form.getlist('sites')
        
        # Convert to integers
        company_ids = [int(id) for id in company_ids if id.isdigit()]
        site_ids = [int(id) for id in site_ids if id.isdigit()]
        
        # Get original access for activity log
        original_companies = [c.id for c in user.companies]
        original_sites = [s.id for s in user.sites]

        # Update user's companies
        user.companies = Company.not_deleted().filter(Company.id.in_(company_ids)).all()
        
        # Update user's sites
        user.sites = Site.not_deleted().filter(Site.id.in_(site_ids)).all()
        
        db.session.commit()
        
        # Log the activity with detailed changes
        added_companies = [c for c in company_ids if c not in original_companies]
        removed_companies = [c for c in original_companies if c not in company_ids]
        added_sites = [s for s in site_ids if s not in original_sites]
        removed_sites = [s for s in original_sites if s not in site_ids]
        
        log_details = f"Updated access for user '{user.username}'"
        if added_companies or removed_companies or added_sites or removed_sites:
            log_details += " - Changes: "
            if added_companies:
                log_details += f"Added {len(added_companies)} companies. "
            if removed_companies:
                log_details += f"Removed {len(removed_companies)} companies. "
            if added_sites:
                log_details += f"Added {len(added_sites)} sites. "
            if removed_sites:
                log_details += f"Removed {len(removed_sites)} sites."
                
        log_activity(
            action="user_access_updated",
            details=log_details
        )

        flash('User access updated successfully', 'success')
        return redirect(url_for('admin.users'))
    
    # Get all companies and sites
    companies = Company.not_deleted().all()
    sites = Site.not_deleted().all()
    
    return render_template('admin/user_access.html', user=user, companies=companies, sites=sites)

@admin.route('/api/companies')
@admin_required
def api_companies():
    """API endpoint for company list"""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '', type=str)
    status = request.args.get('status', 'all', type=str)
    per_page = ITEMS_PER_PAGE

    query = Company.not_deleted()

    # Apply search filter
    if search:
        query = query.filter(func.lower(Company.name).contains(func.lower(search)))

    # Apply status filter (if you have an 'is_active' field)
    # if status != 'all':
    #     query = query.filter_by(is_active=(status == 'active'))

    # Paginate the results
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    companies = pagination.items

    # Prepare the data for JSON response
    company_data = []
    for company in companies:
        company_data.append({
            'id': company.id,
            'name': company.name,
            'contact_person': company.contact_name,
            'email': company.contact_email,
            'phone': company.contact_phone,
            'sites': [{'id': site.id, 'name': site.name} for site in company.sites if site.deleted_at is None],
            'get_tank_count': company.get_tank_count,
            'is_active': True # if you have an is_active field
        })

    return jsonify({
        'success': True,
        'companies': company_data,
        'total': pagination.total,
        'page': page
    })

@admin.route('/companies')
@admin_required
def companies():
    """Company list"""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    
    query = Company.not_deleted()
    
    if search:
        query = query.filter(Company.name.ilike(f'%{search}%'))
    
    pagination = query.paginate(page=page, per_page=ITEMS_PER_PAGE, error_out=False)
    companies = pagination.items
    
    return render_template('admin/companies.html', 
                          companies=companies,
                          pagination=pagination,
                          search=search)

@admin.route('/companies/<int:company_id>')
@admin_required
def company_detail(company_id):
    """Company detail page"""
    company = Company.query.get_or_404(company_id)
    return render_template('admin/company_detail.html', company=company)

@admin.route('/companies/create', methods=['GET', 'POST'])
@login_required
@admin_required
@handle_db_errors
def create_company():
    """Create company"""
    form = CreateCompanyForm()
    if form.validate_on_submit():
        name = form.name.data
        address = form.address.data
        contact_name = form.contact_name.data
        contact_email = form.contact_email.data
        contact_phone = form.contact_phone.data

        # Check if company already exists (case-insensitive)
        existing_company = Company.query.filter(func.lower(Company.name) == func.lower(name)).first()
        if existing_company and existing_company.deleted_at is None:
            flash('Company with that name already exists.', 'danger')
            return redirect(url_for('admin.create_company'))

        company = Company(
            name=name,
            address=address,
            contact_name=contact_name,
            contact_email=contact_email,
            contact_phone=contact_phone
        )
        db.session.add(company)
        db.session.commit()
        flash('Company created successfully!', 'success')
        return redirect(url_for('admin.companies'))

    return render_template('admin/create_company.html', form=form)

@admin.route('/companies/edit/<int:company_id>', methods=['GET', 'POST'])
@admin_required
@handle_db_errors
def edit_company(company_id):
    """Edit company"""
    company = Company.query.get_or_404(company_id)
    form = EditCompanyForm(obj=company)
    
    if form.validate_on_submit():
        # Check if company name already exists (for another company)
        existing_company = Company.query.filter(func.lower(Company.name) == func.lower(form.name.data)).first()
        if existing_company and existing_company.id != company_id and existing_company.deleted_at is None:
            flash('Company name already exists', 'danger')
            return redirect(url_for('admin.edit_company', company_id=company_id))
        
        # Update company
        company.name = form.name.data
        company.address = form.address.data
        company.contact_name = form.contact_name.data
        company.contact_email = form.contact_email.data
        company.contact_phone = form.contact_phone.data
        
        db.session.commit()
        
        flash('Company updated successfully', 'success')
        return redirect(url_for('admin.companies'))
    
    return render_template('admin/edit_company.html', company=company, form=form)

@admin.route('/companies/delete/<int:company_id>', methods=['POST'])
@admin_required
@handle_db_errors
def delete_company(company_id):
    """Delete company"""
    company = Company.query.get_or_404(company_id)
    
    # Check if company has sites
    active_sites = [site for site in company.sites if site.deleted_at is None]
    if active_sites:
        flash('Cannot delete company with sites. Please delete all sites first.', 'danger')
        return redirect(url_for('admin.companies'))
    
    # Use soft delete
    company.soft_delete()
    db.session.commit()
    
    flash('Company deleted successfully', 'success')
    return redirect(url_for('admin.companies'))


# Site management
@admin.route('/sites')
@admin_required
def sites():
    """Site list"""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    company_id = request.args.get('company_id')
    
    query = Site.not_deleted()
    
    if search:
        query = query.filter(Site.name.ilike(f'%{search}%'))
    
    if company_id:
        query = query.filter_by(company_id=company_id)
    
    pagination = query.paginate(page=page, per_page=ITEMS_PER_PAGE, error_out=False)
    sites = pagination.items
    companies = Company.not_deleted().all()
    
    return render_template('admin/sites.html', 
                          sites=sites, 
                          companies=companies,
                          pagination=pagination,
                          search=search,
                          selected_company=company_id)

@admin.route('/sites/<int:site_id>')
@admin_required
def site_detail(site_id):
    """Site detail page"""
    site = Site.query.get_or_404(site_id)
    return render_template('admin/site_detail.html', site=site)

@admin.route('/sites/create', methods=['GET', 'POST'])
@admin_required
@handle_db_errors
def create_site():
    """Create site"""
    if request.method == 'POST':
        name = request.form.get('name')
        address = request.form.get('address')
        location = request.form.get('location')
        company_id = request.form.get('company_id')
        contact_name = request.form.get('contact_name')
        contact_email = request.form.get('contact_email')
        contact_phone = request.form.get('contact_phone')
        contact_info = request.form.get('contact_info')
        is_active = 'is_active' in request.form
        
        # Validate input
        if not name or not company_id:
            flash('Site name and company are required', 'danger')
            return redirect(url_for('admin.create_site'))
        
        # Check if site already exists for this company
        existing_site = Site.not_deleted().filter_by(name=name, company_id=company_id).first()
        if existing_site:
            flash('Site already exists for this company', 'danger')
            return redirect(url_for('admin.create_site'))
        
        # Create site
        site = Site(
            name=name,
            address=address,
            location=location,
            company_id=company_id,
            contact_name=contact_name,
            contact_email=contact_email,
            contact_phone=contact_phone,
            contact_info=contact_info,
            is_active=is_active
        )
        
        db.session.add(site)
        db.session.commit()
        
        flash('Site created successfully', 'success')
        return redirect(url_for('admin.sites'))
    
    # Get companies for dropdown
    companies = Company.not_deleted().all()
    
    # Check if company_id is provided in query parameters
    company_id = request.args.get('company_id')
    
    return render_template('admin/create_site.html', companies=companies, company_id=company_id)

@admin.route('/sites/edit/<int:site_id>', methods=['GET', 'POST'])
@admin_required
@handle_db_errors
def edit_site(site_id):
    """Edit site"""
    site = Site.query.get_or_404(site_id)
    
    if request.method == 'POST':
        name = request.form.get('name')
        address = request.form.get('address')
        location = request.form.get('location')
        company_id = request.form.get('company_id')
        contact_name = request.form.get('contact_name')
        contact_email = request.form.get('contact_email')
        contact_phone = request.form.get('contact_phone')
        contact_info = request.form.get('contact_info')
        is_active = 'is_active' in request.form
        
        # Validate input
        if not name or not company_id:
            flash('Site name and company are required', 'danger')
            return redirect(url_for('admin.edit_site', site_id=site_id))
        
        # Check if site name already exists for this company (for another site)
        existing_site = Site.not_deleted().filter_by(name=name, company_id=company_id).first()
        if existing_site and existing_site.id != site_id:
            flash('Site name already exists for this company', 'danger')
            return redirect(url_for('admin.edit_site', site_id=site_id))
        
        # Update site
        site.name = name
        site.address = address
        site.location = location
        site.company_id = company_id
        site.contact_name = contact_name
        site.contact_email = contact_email
        site.contact_phone = contact_phone
        site.contact_info = contact_info
        site.is_active = is_active
        
        db.session.commit()
        
        flash('Site updated successfully', 'success')
        return redirect(url_for('admin.sites'))
    
    # Get companies for dropdown
    companies = Company.not_deleted().all()
    
    return render_template('admin/edit_site.html', site=site, companies=companies)

@admin.route('/sites/delete/<int:site_id>', methods=['POST'])
@admin_required
@handle_db_errors
def delete_site(site_id):
    """Delete site"""
    site = Site.query.get_or_404(site_id)
    
    # Check if site has tanks
    active_tanks = [tank for tank in site.tanks if tank.deleted_at is None]
    if active_tanks:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': False,
                'message': 'Cannot delete site with tanks. Please delete all tanks first.'
            })
        
        flash('Cannot delete site with tanks', 'danger')
        return redirect(url_for('admin.sites'))
    
    # Use soft delete
    site.soft_delete()
    db.session.commit()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'success': True,
            'message': 'Site deleted successfully'
        })
    
    flash('Site deleted successfully', 'success')
    return redirect(url_for('admin.sites'))



@admin.route('/api/tanks/<int:tank_id>/history')
@admin_required
def api_tank_history(tank_id):
    """Admin API endpoint for tank measurement history using TimescaleDB aggregation."""
    tank = Tank.query.get_or_404(tank_id)

    # Get query parameters
    from_ts = request.args.get('from', type=int)  # in milliseconds
    to_ts = request.args.get('to', type=int)      # in milliseconds
    metrics = request.args.get('metrics', 'level,volume,fill_percent')
    metrics_list = [m for m in metrics.split(',') if m in {
        'level', 'volume', 'flow_rate', 'fill_percent', 'pressure', 'temperature'
    }]

    if not from_ts or not to_ts:
        return jsonify({
            'success': False,
            'message': "Missing 'from' or 'to' timestamp in milliseconds"
        }), 400

    # Convert milliseconds to datetime
    start_time = dt.fromtimestamp(from_ts / 1000.0)
    end_time = dt.fromtimestamp(to_ts / 1000.0)

    # Determine aggregation interval
    delta = end_time - start_time
    total_minutes = delta.total_seconds() / 60
    if total_minutes <= 180:
        interval = '1 minute'
    elif total_minutes <= 1440:
        interval = '5 minutes'
    elif total_minutes <= 10080:
        interval = '1 hour'
    else:
        interval = '6 hours'

    try:
        # Fetch aggregated data
        data = Measurement.get_aggregated(tank_id, start_time, end_time, interval)

        # Optionally filter returned metrics if needed
        if data and isinstance(data, list) and isinstance(data[0], dict):
            filtered_data = []
            for entry in data:
                filtered_entry = {'timestamp': entry['timestamp']}
                for m in metrics_list:
                    if m in entry:
                        filtered_entry[m] = entry[m]
                filtered_data.append(filtered_entry)
        else:
            filtered_data = data  # fallback

        return jsonify({
            'success': True,
            'tank_id': tank_id,
            'from': from_ts,
            'to': to_ts,
            'interval': interval,
            'measurements': filtered_data
        })

    except Exception as e:
        current_app.logger.error(f"Error fetching aggregated history: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Failed to fetch aggregated history: {str(e)}"
        }), 500

@admin.route('/api/tanks/<int:tank_id>/individual-consumption')
@admin_required
def api_tank_individual_consumption(tank_id):
    """API endpoint for individual consumption and refill events"""
    # Validate tank exists and user has access
    tank = Tank.query.get_or_404(tank_id)
    
    try:
        # Get and validate time range parameters
        from_time, to_time = get_time_range_from_request()
        
        # Get parameters with reasonable defaults
        min_volume = request.args.get('min_volume', 100, type=float)
        flow_threshold = request.args.get('flow_threshold', 0.1, type=float)
        max_flow_rate = request.args.get('max_flow_rate', 5000, type=float)  # L/min
        min_duration = request.args.get('min_duration', 5, type=float)  # seconds
        
        # Validate parameters
        if min_volume < 0:
            raise ValueError("min_volume must be a positive number")
        if flow_threshold < 0:
            raise ValueError("flow_threshold must be a positive number")
        if max_flow_rate <= 0:
            raise ValueError("max_flow_rate must be a positive number")
        if min_duration < 0:
            raise ValueError("min_duration must be a positive number")
        
        # Convert milliseconds to datetime objects for database query
        from_datetime = dt.fromtimestamp(from_time // 1000)
        to_datetime = dt.fromtimestamp(to_time // 1000)
        
        # Fetch individual consumption and refill events
        events = fetch_individual_consumption(
            tank_id, from_datetime, to_datetime, 
            min_volume, flow_threshold, max_flow_rate, min_duration
        )
        
        return jsonify({
            'success': True,
            'tank_id': tank_id,
            'from': from_time,
            'to': to_time,
            'consumption_events': events['consumption'],
            'refill_events': events['refill']
        })
        
    except ValueError as e:
        current_app.logger.warning(f"Invalid parameters for individual consumption: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Invalid parameters: {str(e)}"
        }), 400
    except Exception as e:
        current_app.logger.error(f"Error fetching individual consumption: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f"Failed to fetch individual consumption: {str(e)}"
        }), 500

def fetch_individual_consumption(tank_id, from_datetime, to_datetime, min_volume=100, flow_threshold=0.1, 
                                max_flow_rate=5000, min_duration_seconds=5):
    """Fetch individual consumption events for a tank with improved detection
    
    Args:
        tank_id: The ID of the tank
        from_datetime: Start of time range
        to_datetime: End of time range
        min_volume: Minimum volume change to consider as a consumption event
        flow_threshold: Minimum flow rate to consider as active flow
        max_flow_rate: Maximum realistic flow rate (L/min)
        min_duration_seconds: Minimum duration for a valid consumption event
    """
    # Get all measurements within the time range
    measurements = Measurement.query.filter(
        Measurement.tank_id == tank_id,
        Measurement.timestamp >= from_datetime,
        Measurement.timestamp <= to_datetime
    ).order_by(Measurement.timestamp.asc()).all()
    
    if not measurements or len(measurements) < 2:
        return []
    
    # Identify consumption and refill events
    consumption_events = []
    refill_events = []
    current_event = None
    event_type = None  # 'consumption' or 'refill'
    
    for i in range(1, len(measurements)):
        prev_measurement = measurements[i-1]
        curr_measurement = measurements[i]
        
        # Calculate volume change and time difference
        volume_change = prev_measurement.volume - curr_measurement.volume
        time_diff_seconds = (curr_measurement.timestamp - prev_measurement.timestamp).total_seconds()
        
        # Skip if measurements are too close in time (potential sensor noise)
        if time_diff_seconds < 0.1:  # Less than 100ms
            continue
            
        # Determine if this is a consumption or refill
        is_consumption = volume_change > 0
        is_refill = volume_change < -min_volume  # Negative change = volume increase
        
        # Start tracking a new consumption event
        if is_consumption and (current_event is None or event_type != 'consumption'):
            if current_event is not None and event_type == 'refill':
                # Finalize the previous refill event
                finalize_event(current_event, refill_events, min_volume, min_duration_seconds, max_flow_rate)
            
            # Start a new consumption event
            current_event = {
                'start_time': prev_measurement.timestamp.isoformat(),
                'start_volume': prev_measurement.volume,
                'measurements': [
                    {
                        'timestamp': prev_measurement.timestamp.isoformat(),
                        'volume': prev_measurement.volume,
                        'flow_rate': getattr(prev_measurement, 'flow_rate', None)
                    }
                ]
            }
            event_type = 'consumption'
            
        # Start tracking a new refill event
        elif is_refill and (current_event is None or event_type != 'refill'):
            if current_event is not None and event_type == 'consumption':
                # Finalize the previous consumption event
                finalize_event(current_event, consumption_events, min_volume, min_duration_seconds, max_flow_rate)
            
            # Start a new refill event
            current_event = {
                'start_time': prev_measurement.timestamp.isoformat(),
                'start_volume': prev_measurement.volume,
                'measurements': [
                    {
                        'timestamp': prev_measurement.timestamp.isoformat(),
                        'volume': prev_measurement.volume,
                        'flow_rate': getattr(prev_measurement, 'flow_rate', None)
                    }
                ]
            }
            event_type = 'refill'
        
        # Continue tracking the current event
        if current_event is not None:
            current_event['measurements'].append({
                'timestamp': curr_measurement.timestamp.isoformat(),
                'volume': curr_measurement.volume,
                'flow_rate': getattr(curr_measurement, 'flow_rate', None)
            })
            
            # Update end time and volume
            current_event['end_time'] = curr_measurement.timestamp.isoformat()
            current_event['end_volume'] = curr_measurement.volume
            
        # If volume stabilizes (minimal change), end the current event
        if abs(volume_change) < 1 and current_event is not None:
            if event_type == 'consumption':
                finalize_event(current_event, consumption_events, min_volume, min_duration_seconds, max_flow_rate)
            elif event_type == 'refill':
                finalize_event(current_event, refill_events, min_volume, min_duration_seconds, max_flow_rate)
            
            current_event = None
            event_type = None
    
    # Handle any ongoing event at the end of the data
    if current_event is not None:
        if event_type == 'consumption':
            finalize_event(current_event, consumption_events, min_volume, min_duration_seconds, max_flow_rate)
        elif event_type == 'refill':
            finalize_event(current_event, refill_events, min_volume, min_duration_seconds, max_flow_rate)
    
    # Return both consumption and refill events
    return {
        'consumption': consumption_events,
        'refill': refill_events
    }

def finalize_event(event, event_list, min_volume, min_duration_seconds, max_flow_rate):
    """Helper function to finalize and validate an event"""
    if not event or 'start_time' not in event or 'end_time' not in event:
        return
        
    # Calculate event statistics
    start_time = dt.fromisoformat(event['start_time'].replace('Z', '+00:00'))
    end_time = dt.fromisoformat(event['end_time'].replace('Z', '+00:00'))
    
    duration_seconds = max((end_time - start_time).total_seconds(), 0.1)  # Avoid division by zero
    duration_hours = duration_seconds / 3600
    
    volume_change = abs(event['start_volume'] - event['end_volume'])
    
    # Only add events with significant volume change and minimum duration
    if volume_change >= min_volume and duration_seconds >= min_duration_seconds:
        # Calculate flow rate with a realistic maximum
        flow_rate = volume_change / duration_hours if duration_hours > 0 else 0
        capped_flow_rate = min(flow_rate, max_flow_rate * 60)  # Convert max L/min to L/hour
        
        # Add calculated fields
        event['volume_change'] = volume_change
        event['duration_seconds'] = duration_seconds
        event['duration_hours'] = duration_hours
        event['flow_rate'] = capped_flow_rate
        
        # For refill events, use volume_added instead of volume_consumed
        if event['start_volume'] < event['end_volume']:
            event['volume_added'] = volume_change
        else:
            event['volume_consumed'] = volume_change
        
        # Add to the appropriate list
        event_list.append(event)

def fetch_volume_based_consumption(measurements, min_volume):
    """Fall back to volume-based consumption detection when flow rate data is unavailable"""
    consumption_events = []
    current_event = None
    
    for i in range(1, len(measurements)):
        prev_measurement = measurements[i-1]
        curr_measurement = measurements[i]
        
        volume_change = prev_measurement.volume - curr_measurement.volume
        
        # If there's a significant volume decrease, it might be a consumption event
        if volume_change > 0:
            # If we're not tracking an event, start a new one
            if current_event is None:
                current_event = {
                    'start_time': prev_measurement.timestamp.isoformat(),
                    'start_volume': prev_measurement.volume,
                    'measurements': [
                        {
                            'timestamp': prev_measurement.timestamp.isoformat(),
                            'volume': prev_measurement.volume
                        }
                    ]
                }
            
            # Add the current measurement to the event
            current_event['measurements'].append({
                'timestamp': curr_measurement.timestamp.isoformat(),
                'volume': curr_measurement.volume
            })
            
            # Update the end time and volume
            current_event['end_time'] = curr_measurement.timestamp.isoformat()
            current_event['end_volume'] = curr_measurement.volume
            
        # If volume increased or stayed the same, and we're tracking an event
        elif current_event is not None:
            # Calculate event statistics
            volume_consumed = current_event['start_volume'] - current_event['end_volume']
            
            # Only consider it a consumption event if the volume change is significant
            if volume_consumed >= min_volume:
                start_time = dt.fromisoformat(current_event['start_time'].replace('Z', '+00:00'))
                end_time = dt.fromisoformat(current_event['end_time'].replace('Z', '+00:00'))
                duration_hours = (end_time - start_time).total_seconds() / 3600
                
                # Add calculated fields
                current_event['volume_consumed'] = volume_consumed
                current_event['duration_hours'] = round(duration_hours, 2)
                current_event['consumption_rate'] = round(volume_consumed / duration_hours, 2) if duration_hours > 0 else 0
                
                # Add to the list of events
                consumption_events.append(current_event)
            
            # Reset current event
            current_event = None
    
    # Handle the case where the last event is still in progress
    if current_event is not None:
        volume_consumed = current_event['start_volume'] - current_event['end_volume']
        
        if volume_consumed >= min_volume:
            start_time = dt.fromisoformat(current_event['start_time'].replace('Z', '+00:00'))
            end_time = dt.fromisoformat(current_event['end_time'].replace('Z', '+00:00'))
            duration_hours = (end_time - start_time).total_seconds() / 3600
            
            current_event['volume_consumed'] = volume_consumed
            current_event['duration_hours'] = round(duration_hours, 2)
            current_event['consumption_rate'] = round(volume_consumed / duration_hours, 2) if duration_hours > 0 else 0
            
            consumption_events.append(current_event)
    
    return consumption_events

@admin.route('/api/tanks/<int:tank_id>/hourly-stats')
@admin_required
def api_tank_hourly_stats(tank_id):
    """API endpoint for tank hourly statistics
    
    Returns aggregated hourly statistics for a tank including:
    - Volume measurements (min, max, avg)
    - Consumption data (hourly consumption, volume change)
    
    Query parameters:
    - from: Unix timestamp in milliseconds (start of range)
    - to: Unix timestamp in milliseconds (end of range)
    - hours: Number of hours to look back (default: 48, used if from/to not provided)
    """
    # Validate tank exists and user has access
    tank = Tank.query.get_or_404(tank_id)
    
    try:
        # Get and validate time range parameters
        from_time, to_time = get_hourly_time_range_from_request()
        
        # Convert milliseconds to datetime objects for database query
        from_datetime = dt.fromtimestamp(from_time // 1000)
        to_datetime = dt.fromtimestamp(to_time // 1000)
        
        # Fetch data from database
        hourly_data, consumption_data = fetch_tank_hourly_statistics(tank_id, from_datetime, to_datetime)
        
        # Process data into time series format
        time_series = process_hourly_time_series_data(hourly_data, consumption_data)
        
        return jsonify({
            'success': True,
            'tank_id': tank_id,
            'from': from_time,
            'to': to_time,
            'data': time_series
        })
        
    except ValueError as e:
        current_app.logger.warning(f"Invalid parameters for hourly tank stats: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Invalid parameters: {str(e)}"
        }), 400
    except Exception as e:
        current_app.logger.error(f"Error fetching hourly stats: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f"Failed to fetch hourly stats: {str(e)}"
        }), 500


def get_hourly_time_range_from_request():
    """Extract and validate hourly time range parameters from the request"""
    # Get time range from query parameters
    from_time = request.args.get('from', type=int)  # Unix timestamp in milliseconds
    to_time = request.args.get('to', type=int)      # Unix timestamp in milliseconds
    
    # If from/to not provided, use hours parameter
    if from_time is None or to_time is None:
        hours = request.args.get('hours', 48, type=int)
        
        # Validate hours parameter
        if hours <= 0 or hours > 720:  # Max 30 days in hours
            raise ValueError("Hours parameter must be between 1 and 720")
            
        to_time = int(dt.now().timestamp() * 1000)  # Current time in milliseconds
        from_time = to_time - (hours * 60 * 60 * 1000)   # hours ago in milliseconds
    
    # Validate time range
    if from_time >= to_time:
        raise ValueError("'from' timestamp must be earlier than 'to' timestamp")
        
    # Limit the range to prevent performance issues
    max_range = 30 * 24 * 60 * 60 * 1000  # 30 days in milliseconds
    if to_time - from_time > max_range:
        raise ValueError("Time range cannot exceed 30 days for hourly statistics")
        
    return from_time, to_time


def fetch_tank_hourly_statistics(tank_id, from_datetime, to_datetime):
    """Fetch aggregated hourly data and consumption data for a tank"""
    # Get aggregated data with hourly interval
    hourly_data = Measurement.get_aggregated(
        tank_id=tank_id,
        start_time=from_datetime,
        end_time=to_datetime,
        interval='1 hour'
    )
    
    # Get hourly consumption data
    consumption_data = Measurement.get_hourly_consumption(
        tank_id=tank_id,
        start_time=from_datetime,
        end_time=to_datetime
    )
    
    return hourly_data, consumption_data


def process_hourly_time_series_data(hourly_data, consumption_data):
    """Process raw hourly data into time series format for the frontend"""
    time_series = {
        'min_volume': [],
        'max_volume': [],
        'avg_volume': [],
        'volume_change': [],
        'hourly_consumption': []
    }
    
    # Process aggregated data for volume statistics
    for data_point in hourly_data:
        # Ensure we have a valid timestamp
        if 'timestamp' not in data_point:
            continue
            
        try:
            timestamp_dt = dt.fromisoformat(data_point['timestamp'].replace('Z', '+00:00'))
            hour_start = dt.combine(timestamp_dt.date(), 
                                   time(timestamp_dt.hour, 0))
            timestamp_ms = int(hour_start.timestamp() * 1000)
            
            volume = data_point.get('volume')
            
            if volume is not None:
                time_series['min_volume'].append([timestamp_ms, data_point.get('min_volume', volume)])
                time_series['max_volume'].append([timestamp_ms, data_point.get('max_volume', volume)])
                time_series['avg_volume'].append([timestamp_ms, volume])
        except (ValueError, AttributeError, TypeError) as e:
            current_app.logger.warning(f"Error processing hourly data point: {e}")
            continue
    
    # Process consumption data
    for data_point in consumption_data:
        # Ensure we have a valid timestamp
        if not data_point or 'timestamp' not in data_point:
            continue
            
        try:
            timestamp_ms = data_point['timestamp']
            
            # Add consumption data points
            if data_point.get('hourly_consumption') is not None:
                time_series['hourly_consumption'].append([timestamp_ms, data_point['hourly_consumption']])
                
            if data_point.get('volume_change') is not None:
                time_series['volume_change'].append([timestamp_ms, data_point['volume_change']])
        except (ValueError, TypeError) as e:
            current_app.logger.warning(f"Error processing consumption data point: {e}")
            continue
    
    return time_series

@admin.route('/api/tanks/<int:tank_id>/consumption-patterns')
@admin_required
def api_tank_consumption_patterns(tank_id):
    """API endpoint for tank consumption patterns
    
    Returns hourly and weekly consumption patterns for a tank
    
    Query parameters:
    - days: Number of days to analyze (default: 30)
    """
    # Validate tank exists and user has access
    tank = Tank.query.get_or_404(tank_id)
    
    try:
        # Get days parameter
        days = request.args.get('days', 30, type=int)
        
        # Validate days parameter
        if days <= 0 or days > 365:
            raise ValueError("Days parameter must be between 1 and 365")
        
        # Calculate time range
        end_time = dt.now()
        start_time = end_time - timedelta(days=days)
        
        # Get hourly consumption patterns
        hourly_patterns = get_hourly_consumption_patterns(tank_id, start_time, end_time)
        
        # Get weekly consumption patterns
        weekly_patterns = get_weekly_consumption_patterns(tank_id, start_time, end_time)
        
        return jsonify({
            'success': True,
            'tank_id': tank_id,
            'days_analyzed': days,
            'hourly_patterns': hourly_patterns,
            'weekly_patterns': weekly_patterns
        })
        
    except ValueError as e:
        current_app.logger.warning(f"Invalid parameters for consumption patterns: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Invalid parameters: {str(e)}"
        }), 400
    except Exception as e:
        current_app.logger.error(f"Error fetching consumption patterns: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f"Failed to fetch consumption patterns: {str(e)}"
        }), 500

def get_hourly_consumption_patterns(tank_id, start_time, end_time):
    """Get hourly consumption patterns for a tank with improved refill handling"""
    with db.engine.connect() as conn:
        hourly_query = text("""
            WITH refill_days AS (
                -- Identify days with refills to exclude them from hourly patterns
                SELECT 
                    date_trunc('day', timestamp) AS day,
                    MIN(volume) AS min_volume,
                    MAX(volume) AS max_volume
                FROM measurement
                WHERE tank_id = :tank_id
                  AND timestamp BETWEEN :start_time AND :end_time
                  AND volume IS NOT NULL
                GROUP BY date_trunc('day', timestamp)
                HAVING (MAX(volume) - MIN(volume)) > GREATEST(500, 0.10 * MIN(volume))
            ),
            hourly_data AS (
                SELECT 
                    EXTRACT(HOUR FROM m.timestamp) AS hour,
                    m.timestamp,
                    m.volume,
                    LAG(m.volume) OVER (ORDER BY m.timestamp) AS prev_volume,
                    LAG(m.timestamp) OVER (ORDER BY m.timestamp) AS prev_timestamp
                FROM measurement m
                LEFT JOIN refill_days rd ON date_trunc('day', m.timestamp) = rd.day
                WHERE m.tank_id = :tank_id
                  AND m.timestamp BETWEEN :start_time AND :end_time
                  AND m.volume IS NOT NULL
                  -- Exclude days with refills to get more accurate hourly patterns
                  AND rd.day IS NULL
                ORDER BY m.timestamp
            ),
            hourly_consumption AS (
                SELECT 
                    hour,
                    CASE 
                        WHEN prev_volume > volume 
                        AND EXTRACT(EPOCH FROM (timestamp - prev_timestamp)) BETWEEN 60 AND 3600
                        THEN (prev_volume - volume)
                        ELSE 0 
                    END AS consumption,
                    CASE 
                        WHEN prev_volume > volume 
                        AND EXTRACT(EPOCH FROM (timestamp - prev_timestamp)) BETWEEN 60 AND 3600
                        THEN 1
                        ELSE 0 
                    END AS count
                FROM hourly_data
            )
            SELECT 
                hour,
                SUM(consumption) AS total_consumption,
                SUM(count) AS measurement_count
            FROM hourly_consumption
            GROUP BY hour
            ORDER BY hour
        """)
        
        hourly_results = conn.execute(
            hourly_query,
            {"tank_id": tank_id, "start_time": start_time, "end_time": end_time}
        ).fetchall()
        
        # Process results into hourly pattern
        hourly_pattern = [0] * 24
        for row in hourly_results:
            hour = int(row.hour)
            total_consumption = float(row.total_consumption)
            count = int(row.measurement_count)
            
            # Calculate average consumption per hour
            if count > 0:
                hourly_pattern[hour] = round(total_consumption / count, 2)
        
        return hourly_pattern

def get_weekly_consumption_patterns(tank_id, start_time, end_time):
    """Get weekly consumption patterns for a tank with improved refill handling"""
    with db.engine.connect() as conn:
        weekly_query = text("""
            WITH daily_timestamps AS (
                SELECT 
                    date_trunc('day', timestamp) AS day,
                    EXTRACT(DOW FROM timestamp) AS day_of_week,
                    MIN(volume) AS min_volume,
                    MAX(volume) AS max_volume
                FROM measurement
                WHERE tank_id = :tank_id
                  AND timestamp BETWEEN :start_time AND :end_time
                  AND volume IS NOT NULL
                GROUP BY date_trunc('day', timestamp), EXTRACT(DOW FROM timestamp)
            ),
            daily_volumes AS (
                SELECT 
                    date_trunc('day', m.timestamp) AS day,
                    EXTRACT(DOW FROM m.timestamp) AS day_of_week,
                    FIRST_VALUE(m.volume) OVER (PARTITION BY date_trunc('day', m.timestamp) ORDER BY m.timestamp) AS start_volume,
                    LAST_VALUE(m.volume) OVER (PARTITION BY date_trunc('day', m.timestamp) ORDER BY m.timestamp RANGE BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) AS end_volume
                FROM measurement m
                WHERE m.tank_id = :tank_id
                  AND m.timestamp BETWEEN :start_time AND :end_time
                  AND m.volume IS NOT NULL
            ),
            daily_data AS (
                SELECT DISTINCT
                    dt.day,
                    dt.day_of_week,
                    dt.min_volume,
                    dt.max_volume,
                    dv.start_volume,
                    dv.end_volume
                FROM daily_timestamps dt
                JOIN daily_volumes dv ON dt.day = dv.day
            ),
            refill_detection AS (
                SELECT
                    day,
                    day_of_week,
                    start_volume,
                    end_volume,
                    min_volume,
                    max_volume,
                    -- Detect significant increases (refills)
                    -- A refill is detected when max_volume is significantly higher than min_volume (at least 500L or 10%)
                    CASE 
                        WHEN (max_volume - min_volume) > GREATEST(500, 0.10 * min_volume) THEN TRUE
                        ELSE FALSE
                    END AS has_refill
                FROM daily_data
            ),
            daily_consumption AS (
                SELECT 
                    day_of_week,
                    -- Calculate daily consumption
                    -- If there was a refill, consumption = (max_volume - end_volume)
                    -- Otherwise, consumption = (start_volume - end_volume) if positive
                    CASE 
                        WHEN has_refill AND end_volume < max_volume THEN (max_volume - end_volume)
                        WHEN NOT has_refill AND start_volume > end_volume THEN (start_volume - end_volume)
                        ELSE 0 
                    END AS consumption,
                    1 AS count
                FROM refill_detection
            )
            SELECT 
                day_of_week,
                SUM(consumption) AS total_consumption,
                SUM(count) AS day_count
            FROM daily_consumption
            GROUP BY day_of_week
            ORDER BY day_of_week
        """)
        
        weekly_results = conn.execute(
            weekly_query,
            {"tank_id": tank_id, "start_time": start_time, "end_time": end_time}
        ).fetchall()
        
        # Process results into weekly pattern
        weekly_pattern = [0] * 7
        for row in weekly_results:
            day = int(row.day_of_week)
            total_consumption = float(row.total_consumption)
            count = int(row.day_count)
            
            # Calculate average consumption per day
            if count > 0:
                weekly_pattern[day] = round(total_consumption / count, 2)
        
        return weekly_pattern

@admin.route('/tanks/<int:tank_id>/consumption')
@admin_required
def tank_consumption(tank_id):
    """Tank consumption analysis page"""
    # Validate tank exists and user has access
    tank = Tank.query.get_or_404(tank_id)
    
    return render_template('tank_consumption.html', tank=tank)

@admin.route('/api/tanks/<int:tank_id>/weekly-pattern')
@admin_required
def api_tank_weekly_pattern(tank_id):
    """API endpoint for tank weekly consumption pattern"""
    # Validate tank exists and user has access
    tank = Tank.query.get_or_404(tank_id)
    
    try:
        # Get days parameter
        days = request.args.get('days', 30, type=int)
        
        # Validate days parameter
        if days <= 0 or days > 365:
            raise ValueError("Days parameter must be between 1 and 365")
        
        # Calculate time range
        end_time = dt.now()
        start_time = end_time - timedelta(days=days)
        
        # Get weekly consumption pattern
        weekly_pattern = get_weekly_consumption_patterns(tank_id, start_time, end_time)
        
        return jsonify({
            'success': True,
            'tank_id': tank_id,
            'days_analyzed': days,
            'data': weekly_pattern
        })
        
    except ValueError as e:
        current_app.logger.warning(f"Invalid parameters for weekly pattern: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Invalid parameters: {str(e)}"
        }), 400
    except Exception as e:
        current_app.logger.error(f"Error fetching weekly pattern: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f"Failed to fetch weekly pattern: {str(e)}"
        }), 500

@admin.route('/api/tanks/<int:tank_id>/hourly-pattern')
@admin_required
def api_tank_hourly_pattern(tank_id):
    """API endpoint for tank hourly consumption pattern"""
    # Validate tank exists and user has access
    tank = Tank.query.get_or_404(tank_id)
    
    try:
        # Get days parameter
        days = request.args.get('days', 30, type=int)
        
        # Validate days parameter
        if days <= 0 or days > 365:
            raise ValueError("Days parameter must be between 1 and 365")
        
        # Calculate time range
        end_time = dt.now()
        start_time = end_time - timedelta(days=days)
        
        # Get hourly consumption pattern
        hourly_pattern = get_hourly_consumption_patterns(tank_id, start_time, end_time)
        
        return jsonify({
            'success': True,
            'tank_id': tank_id,
            'days_analyzed': days,
            'data': hourly_pattern
        })
        
    except ValueError as e:
        current_app.logger.warning(f"Invalid parameters for hourly pattern: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Invalid parameters: {str(e)}"
        }), 400
    except Exception as e:
        current_app.logger.error(f"Error fetching hourly pattern: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f"Failed to fetch hourly pattern: {str(e)}"
        }), 500

@admin.route('/api/tanks/<int:tank_id>/daily-stats')
@admin_required
def api_tank_daily_stats(tank_id):
    """API endpoint for tank daily statistics"""
    # Validate tank exists and user has access
    tank = Tank.query.get_or_404(tank_id)
    
    try:
        # Get days parameter
        days = request.args.get('days', 30, type=int)
        
        # Get from/to parameters if provided (for custom date ranges)
        from_time_str = request.args.get('from')
        to_time_str = request.args.get('to')
        
        # Validate days parameter
        if days <= 0 or days > 365:
            raise ValueError("Days parameter must be between 1 and 365")
        
        # Calculate time range
        end_time = dt.now()
        start_time = end_time - timedelta(days=days)
        
        # Override with custom date range if provided
        if from_time_str and to_time_str:
            try:
                # Convert millisecond timestamps to datetime
                start_time = dt.fromtimestamp(int(from_time_str) / 1000)
                end_time = dt.fromtimestamp(int(to_time_str) / 1000)
                
                # Calculate actual days for summary
                days = (end_time - start_time).days or 1  # Ensure at least 1 day
            except (ValueError, TypeError, OverflowError) as e:
                raise ValueError(f"Invalid date format: {str(e)}")
        
        # Get daily statistics
        daily_stats = fetch_tank_statistics(tank_id, start_time, end_time)
        
        # Get overnight consumption
        overnight_consumption = fetch_overnight_consumption(tank_id, start_time, end_time)
        
        # Format data for charts
        daily_consumption = []
        daily_refill = []
        avg_volume = []
        
        # Process daily stats
        for stat in daily_stats:
            # Handle the timestamp which could be a Decimal or a datetime
            if hasattr(stat['timestamp'], 'timestamp'):
                # It's a datetime object
                timestamp = int(stat['timestamp'].timestamp() * 1000)
            else:
                # It's likely a Decimal or other numeric type
                # Convert to int or float first to ensure it's a number
                timestamp = int(float(stat['timestamp']))
            
            # Add daily consumption
            daily_consumption.append([timestamp, float(stat['daily_consumption'])])
            
            # Add refill data
            daily_refill.append([timestamp, float(stat['daily_refill'])])
            
            # Add average volume
            avg_volume.append([timestamp, float(stat['end_volume'])])
        
        # Format overnight consumption data
        formatted_overnight = []
        for item in overnight_consumption:
            # Handle the timestamp which could be a Decimal or a datetime
            if hasattr(item[0], 'timestamp'):
                # It's a datetime object
                timestamp = int(item[0].timestamp() * 1000)
            else:
                # It's likely a Decimal or other numeric type
                timestamp = int(float(item[0]))
            
            formatted_overnight.append([timestamp, float(item[1])])
        
        # Calculate summary statistics
        total_consumption = sum(item[1] for item in daily_consumption)
        total_refill = sum(item[1] for item in daily_refill)
        total_overnight = sum(item[1] for item in formatted_overnight)
        
        avg_daily_consumption = total_consumption / days if days > 0 else 0
        avg_overnight_consumption = total_overnight / days if days > 0 else 0
        
        # Calculate net change (with defensive programming)
        first_volume = float(daily_stats[0]['start_volume']) if daily_stats else 0
        last_volume = float(daily_stats[-1]['end_volume']) if daily_stats else 0
        net_change = last_volume - first_volume
        
        return jsonify({
            'success': True,
            'tank_id': tank_id,
            'days_analyzed': days,
            'data': {
                'daily_consumption': daily_consumption,
                'overnight_consumption': formatted_overnight,
                'daily_refill': daily_refill,
                'avg_volume': avg_volume
            },
            'summary': {
                'total_consumption': total_consumption,
                'total_refill': total_refill,
                'avg_daily_consumption': avg_daily_consumption,
                'avg_overnight_consumption': avg_overnight_consumption,
                'net_change': net_change,
                'total_days': days
            }
        })
        
    except ValueError as e:
        current_app.logger.warning(f"Invalid parameters for daily stats: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Invalid parameters: {str(e)}"
        }), 400
    except Exception as e:
        current_app.logger.error(f"Error fetching daily stats: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f"Failed to fetch daily stats: {str(e)}"
        }), 500

def fetch_overnight_consumption(tank_id, from_datetime, to_datetime):
    """Fetch overnight consumption data for a tank"""
    try:
        # Define overnight hours (e.g., 8 PM to 6 AM)
        overnight_start_hour = 20  # 8 PM
        overnight_end_hour = 6     # 6 AM
        
        overnight_query = text("""
            WITH hourly_data AS (
                SELECT 
                    date_trunc('day', timestamp) AS day,
                    EXTRACT(HOUR FROM timestamp) AS hour,
                    timestamp,  -- Include the original timestamp
                    volume,
                    LAG(volume) OVER (ORDER BY timestamp) AS prev_volume,
                    LAG(timestamp) OVER (ORDER BY timestamp) AS prev_timestamp
                FROM measurement
                WHERE tank_id = :tank_id
                  AND timestamp BETWEEN :start_time AND :end_time
                  AND volume IS NOT NULL
                ORDER BY timestamp
            ),
            hourly_consumption AS (
                SELECT 
                    day,
                    hour,
                    CASE 
                        WHEN prev_volume > volume 
                        AND EXTRACT(EPOCH FROM (timestamp - prev_timestamp)) BETWEEN 60 AND 7200
                        THEN (prev_volume - volume)
                        ELSE 0 
                    END AS consumption,
                    -- Is this during overnight hours?
                    CASE 
                        WHEN hour >= :overnight_start OR hour < :overnight_end 
                        THEN TRUE 
                        ELSE FALSE 
                    END AS is_overnight
                FROM hourly_data
                WHERE prev_timestamp IS NOT NULL  -- Ensure we have a previous timestamp
            ),
            daily_overnight AS (
                SELECT 
                    day,
                    SUM(CASE WHEN is_overnight THEN consumption ELSE 0 END) AS overnight_consumption
                FROM hourly_consumption
                GROUP BY day
            )
            SELECT 
                EXTRACT(EPOCH FROM day) * 1000 AS timestamp,
                overnight_consumption
            FROM daily_overnight
            ORDER BY day
        """)
        
        overnight_results = db.session.execute(
            overnight_query,
            {
                "tank_id": tank_id, 
                "start_time": from_datetime, 
                "end_time": to_datetime,
                "overnight_start": overnight_start_hour,
                "overnight_end": overnight_end_hour
            }
        ).fetchall()
        
        # Convert to list of tuples for chart
        overnight_data = []
        for row in overnight_results:
            overnight_data.append([
                row.timestamp,
                float(row.overnight_consumption) if row.overnight_consumption is not None else 0
            ])
        
        return overnight_data
    except Exception as e:
        current_app.logger.error(f"Database error fetching overnight consumption: {e}", exc_info=True)
        raise

def calculate_consumption_summary(consumption_data):
    """Calculate summary statistics for consumption data"""
    if not consumption_data:
        return {
            'total_days': 0,
            'avg_daily_consumption': 0,
            'avg_overnight_consumption': 0,
            'total_consumption': 0,
            'total_refill': 0,
            'net_change': 0
        }
    
    # Calculate totals
    total_days = len(consumption_data)
    total_consumption = sum(d.get('total_consumption', 0) for d in consumption_data)
    total_refill = sum(d.get('total_refill', 0) for d in consumption_data)
    total_daily_consumption = sum(d.get('daily_consumption', 0) for d in consumption_data)
    total_overnight_consumption = sum(d.get('overnight_consumption', 0) for d in consumption_data)
    
    # Calculate averages
    avg_daily_consumption = total_daily_consumption / total_days if total_days > 0 else 0
    avg_overnight_consumption = total_overnight_consumption / total_days if total_days > 0 else 0
    
    # Calculate net change
    net_change = total_refill - total_consumption
    
    return {
        'total_days': total_days,
        'avg_daily_consumption': round(avg_daily_consumption, 2),
        'avg_overnight_consumption': round(avg_overnight_consumption, 2),
        'total_consumption': round(total_consumption, 2),
        'total_refill': round(total_refill, 2),
        'net_change': round(net_change, 2)
    }

def process_time_series_data(daily_data, consumption_data):
    """Process raw data into time series format for the frontend"""
    time_series = {
        'min_volume': [],
        'max_volume': [],
        'avg_volume': [],
        'daily_consumption': [],
        'daily_refill': [],
        'overnight_consumption': [],
        'overnight_refill': [],
        'total_consumption': [],
        'total_refill': []
    }
    
    # Process aggregated data for volume statistics
    try:
        for data_point in daily_data:
            if 'timestamp' not in data_point or 'volume' not in data_point:
                current_app.logger.warning(f"Skipping invalid data point: {data_point}")
                continue
                
            # Parse timestamp safely
            try:
                if isinstance(data_point['timestamp'], str):
                    # Handle different ISO format variations
                    timestamp_str = data_point['timestamp']
                    if 'Z' in timestamp_str:
                        timestamp_str = timestamp_str.replace('Z', '+00:00')
                    if '+' not in timestamp_str and 'T' in timestamp_str and len(timestamp_str) == 19:
                        # No timezone info, assume UTC
                        timestamp_str += '+00:00'
                    timestamp_dt = dt.fromisoformat(timestamp_str)
                else:
                    # Already a datetime object
                    timestamp_dt = data_point['timestamp']
                    
                day_start = dt.combine(timestamp_dt.date(), time(0, 0))
                timestamp_ms = int(day_start.timestamp() * 1000)
                
                volume = data_point['volume']
                
                if volume is not None:
                    time_series['min_volume'].append([timestamp_ms, volume])
                    time_series['max_volume'].append([timestamp_ms, volume])
                    time_series['avg_volume'].append([timestamp_ms, volume])
            except (ValueError, TypeError) as e:
                current_app.logger.warning(f"Error processing timestamp: {e}")
                continue
    except Exception as e:
        current_app.logger.error(f"Error processing daily data: {e}", exc_info=True)
    
    # Process consumption data
    try:
        for data_point in consumption_data:
            if 'timestamp' not in data_point:
                current_app.logger.warning(f"Skipping invalid consumption data point: {data_point}")
                continue
                
            timestamp_ms = data_point['timestamp']
            
            # Add consumption data points - include zero and negative values for completeness
            if data_point.get('daily_consumption') is not None:
                time_series['daily_consumption'].append([timestamp_ms, data_point['daily_consumption']])
                
            if data_point.get('daily_refill') is not None:
                time_series['daily_refill'].append([timestamp_ms, data_point['daily_refill']])
                
            if data_point.get('overnight_consumption') is not None:
                time_series['overnight_consumption'].append([timestamp_ms, data_point['overnight_consumption']])
                
            if data_point.get('overnight_refill') is not None:
                time_series['overnight_refill'].append([timestamp_ms, data_point['overnight_refill']])
                
            if data_point.get('total_consumption') is not None:
                time_series['total_consumption'].append([timestamp_ms, data_point['total_consumption']])
                
            if data_point.get('total_refill') is not None:
                time_series['total_refill'].append([timestamp_ms, data_point['total_refill']])
    except Exception as e:
        current_app.logger.error(f"Error processing consumption data: {e}", exc_info=True)
    
    # Sort all time series by timestamp
    for key in time_series:
        time_series[key] = sorted(time_series[key], key=lambda x: x[0])
    
    return time_series

def fetch_tank_statistics(tank_id, from_datetime, to_datetime):
    """Fetch aggregated data and consumption data for a tank with improved refill detection and day boundary handling"""
    try:
        # Convert datetime to date for comparison
        start_date = from_datetime.date()
        
        # Get both aggregated data and accurate consumption data with previous day's last reading
        daily_query = text("""
            WITH measurement_data AS (
                -- Get all measurements including one day before the start date to get previous day's last reading
                SELECT 
                    timestamp,
                    volume,
                    date_trunc('day', timestamp) AS day
                FROM measurement
                WHERE tank_id = :tank_id
                  AND timestamp BETWEEN (:start_time - INTERVAL '1 day') AND :end_time
                  AND volume IS NOT NULL
                ORDER BY timestamp
            ),
            daily_timestamps AS (
                SELECT 
                    day,
                    MIN(timestamp) AS first_timestamp,
                    MAX(timestamp) AS last_timestamp,
                    MIN(volume) AS min_volume,
                    MAX(volume) AS max_volume
                FROM measurement_data
                GROUP BY day
            ),
            previous_day_last_readings AS (
                -- Get the last reading from each day to use as next day's reference if needed
                SELECT 
                    day,
                    MAX(timestamp) AS last_timestamp
                FROM measurement_data
                GROUP BY day
            ),
            previous_day_values AS (
                -- Join to get the actual volume values
                SELECT 
                    p.day,
                    p.last_timestamp,
                    m.volume AS last_volume
                FROM previous_day_last_readings p
                JOIN measurement_data m ON p.last_timestamp = m.timestamp
            ),
            daily_volumes AS (
                -- Get first and last volume for each day
                SELECT 
                    m.day,
                    -- First value of the day
                    FIRST_VALUE(m.volume) OVER (PARTITION BY m.day ORDER BY m.timestamp) AS start_volume,
                    -- Last value of the day
                    LAST_VALUE(m.volume) OVER (PARTITION BY m.day ORDER BY m.timestamp RANGE BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) AS end_volume,
                    -- Get previous day for reference
                    (m.day - INTERVAL '1 day') AS prev_day
                FROM measurement_data m
                WHERE m.day >= date_trunc('day', :start_date_param)
            ),
            daily_with_previous AS (
                -- Join with previous day's last reading
                SELECT DISTINCT
                    dv.day,
                    dv.start_volume,
                    dv.end_volume,
                    dv.prev_day,
                    pv.last_volume AS prev_day_last_volume
                FROM daily_volumes dv
                LEFT JOIN previous_day_values pv ON dv.prev_day = pv.day
            ),
            daily_data AS (
                SELECT DISTINCT
                    dt.day,
                    dt.min_volume,
                    dt.max_volume,
                    dv.start_volume,
                    dv.end_volume,
                    dv.prev_day_last_volume,
                    -- Use previous day's last volume if it exists and is greater than current day's start volume
                    -- This handles cases where there might be consumption between days
                    CASE 
                        WHEN dv.prev_day_last_volume IS NOT NULL AND dv.prev_day_last_volume > dv.start_volume 
                        THEN dv.prev_day_last_volume
                        ELSE dv.start_volume
                    END AS adjusted_start_volume
                FROM daily_timestamps dt
                JOIN daily_with_previous dv ON dt.day = dv.day
                WHERE dt.day >= date_trunc('day', :start_date_param)
            ),
            refill_detection AS (
                SELECT
                    day,
                    start_volume,
                    adjusted_start_volume,
                    end_volume,
                    min_volume,
                    max_volume,
                    -- Detect significant increases (refills)
                    -- A refill is detected when max_volume is significantly higher than min_volume (at least 500L or 10%)
                    CASE 
                        WHEN (max_volume - min_volume) > GREATEST(500, 0.10 * min_volume) THEN TRUE
                        ELSE FALSE
                    END AS has_refill,
                    -- Calculate refill amount
                    CASE 
                        WHEN (max_volume - min_volume) > GREATEST(500, 0.10 * min_volume) THEN (max_volume - min_volume)
                        ELSE 0 
                    END AS refill_amount
                FROM daily_data
            )
            SELECT 
                EXTRACT(EPOCH FROM day) * 1000 AS timestamp,
                start_volume,
                adjusted_start_volume,
                end_volume,
                min_volume,
                max_volume,
                has_refill,
                refill_amount,
                -- Daily net change using adjusted start volume
                (end_volume - adjusted_start_volume) AS net_change,
                -- Calculate daily consumption - FIXED to account for all consumption and day boundaries
                CASE 
                    WHEN has_refill THEN (adjusted_start_volume - end_volume + refill_amount)
                    WHEN adjusted_start_volume > end_volume THEN (adjusted_start_volume - end_volume)
                    ELSE 0 
                END AS daily_consumption,
                -- Refill amount (already calculated)
                refill_amount AS daily_refill
            FROM refill_detection
            ORDER BY day
        """)
        
        daily_results = db.session.execute(
            daily_query,
            {
                "tank_id": tank_id, 
                "start_time": from_datetime, 
                "end_time": to_datetime,
                "start_date_param": from_datetime  # Add this parameter for date comparison
            }
        ).fetchall()
        
        # Convert to list of dictionaries
        daily_data = []
        for row in daily_results:
            daily_data.append({
                'timestamp': row.timestamp,
                'start_volume': float(row.start_volume) if row.start_volume is not None else None,
                'adjusted_start_volume': float(row.adjusted_start_volume) if row.adjusted_start_volume is not None else None,
                'end_volume': float(row.end_volume) if row.end_volume is not None else None,
                'min_volume': float(row.min_volume) if row.min_volume is not None else None,
                'max_volume': float(row.max_volume) if row.max_volume is not None else None,
                'has_refill': bool(row.has_refill) if row.has_refill is not None else False,
                'net_change': float(row.net_change) if row.net_change is not None else None,
                'daily_refill': float(row.daily_refill) if row.daily_refill is not None else None,
                'daily_consumption': float(row.daily_consumption) if row.daily_consumption is not None else None
            })
        
        return daily_data
    except Exception as e:
        current_app.logger.error(f"Database error fetching tank statistics: {e}", exc_info=True)
        raise

def get_time_range_from_request():
    """Extract and validate time range parameters from the request"""
    # Get time range from query parameters
    from_time = request.args.get('from', type=int)  # Unix timestamp in milliseconds
    to_time = request.args.get('to', type=int)      # Unix timestamp in milliseconds
    
    # If from/to not provided, use days parameter
    if from_time is None or to_time is None:
        days = request.args.get('days', 30, type=int)
        
        # Validate days parameter
        if days <= 0 or days > 365:
            raise ValueError("Days parameter must be between 1 and 365")
            
        to_time = int(dt.now().timestamp() * 1000)  # Current time in milliseconds
        from_time = to_time - (days * 24 * 60 * 60 * 1000)   # days ago in milliseconds
    
    # Validate time range
    if from_time >= to_time:
        raise ValueError("'from' timestamp must be earlier than 'to' timestamp")
    
    # Ensure the range isn't too large
    max_range_ms = 365 * 24 * 60 * 60 * 1000  # 365 days in milliseconds
    if to_time - from_time > max_range_ms:
        raise ValueError(f"Time range exceeds maximum allowed (365 days)")
        
    return from_time, to_time

@admin.route('/api/sites')
@admin_required
def api_sites():
    """API endpoint for site list"""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '', type=str)
    company_id = request.args.get('company_id', 'all', type=str)
    status = request.args.get('status', 'all', type=str)
    per_page = ITEMS_PER_PAGE

    query = Site.not_deleted()

    # Apply search filter
    if search:
        query = query.filter(func.lower(Site.name).contains(func.lower(search)))

    # Apply company filter
    if company_id != 'all':
        query = query.filter_by(company_id=int(company_id))

    # Apply status filter
    if status == 'active':
        query = query.filter_by(is_active=True)
    elif status == 'inactive':
        query = query.filter_by(is_active=False)

    # Paginate the results
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    sites = pagination.items

    # Prepare the data for JSON response
    site_data = []
    for site in sites:
        site_data.append({
            'id': site.id,
            'name': site.name,
            'company_id': site.company_id,
            'company_name': site.company.name,
            'address': site.address,
            'contact_name': site.contact_name,
            'contact_email': site.contact_email,
            'contact_phone': site.contact_phone,
            'is_active': site.is_active,
            'tank_count': len([tank for tank in site.tanks if tank.deleted_at is None])
        })

    return jsonify({
        'success': True,
        'sites': site_data,
        'total': pagination.total,
        'page': page
    })

# Tank management
@admin.route('/tanks', endpoint='tanks_index')
@admin_required
def tanks():
    """Tank list"""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    site_id = request.args.get('site_id')
    company_id = request.args.get('company_id')
    
    query = Tank.not_deleted()
    
    if search:
        query = query.filter(Tank.name.ilike(f'%{search}%'))
    
    if site_id:
        query = query.filter_by(site_id=site_id)
    
    if company_id:
        query = query.join(Site).filter(Site.company_id == company_id)
    
    pagination = query.paginate(page=page, per_page=ITEMS_PER_PAGE, error_out=False)
    tanks = pagination.items
    sites = Site.not_deleted().all()
    companies = Company.not_deleted().all()
    
    return render_template('admin/tanks.html', 
                          tanks=tanks, 
                          sites=sites, 
                          companies=companies,
                          pagination=pagination,
                          search=search,
                          selected_site=site_id,
                          selected_company=company_id)

@admin.route('/tanks/<int:tank_id>')
@admin_required
def tank_detail(tank_id):
    """Tank detail page"""
    tank = Tank.query.get_or_404(tank_id)
    return render_template('admin/tank_detail.html', tank=tank)

@admin.route('/tanks/create', methods=['GET', 'POST'])
@admin_required
def create_tank():
    """Add a new tank."""
    if not current_user.is_admin():
        flash('Access denied', 'danger')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
                
        tank = Tank(
            name = request.form.get('name'),
            description = request.form.get('description'),
            site_id = request.form.get('site_id'),
            host = request.form.get('host'),
            tcp_port = request.form.get('tcp_port'),
            device_address = request.form.get('device_address'),
            tank_orientation = request.form.get('tank_orientation'),
            tank_height = request.form.get('tank_height'),
            tank_diameter = request.form.get('tank_diameter'),
            fluid_density = request.form.get('fluid_density'),
            atmospheric_pressure = request.form.get('atmospheric_pressure'),
            pressure_channel = request.form.get('pressure_channel'),
            temp_channel = request.form.get('temp_channel'),
            calibration_factor = request.form.get('calibration_factor'),
            low_level_threshold = request.form.get('low_level_threshold'),
            critical_level_threshold = request.form.get('critical_level_threshold'),
            high_level_threshold = request.form.get('high_level_threshold'),
            elevation = request.form.get('elevation'),
            is_active = 'is_active' in request.form
            )
        db.session.add(tank)
        db.session.commit()
        
        # Log the activity
        log_activity(
            action="tank_created",
            details=f"Created tank '{tank.name}' for site '{tank.site.name}'"
        )
        
        if is_active:
            try:
                from app import tank_monitor_manager as monitor_manager
                monitor_manager.start_monitoring(tank.id)
            except ImportError:
                flash('Warning: Tank monitoring system not available', 'warning')
        
        flash('Tank created successfully', 'success')
        return redirect(url_for('admin.tanks_index'))
    # Get sites for dropdown
    sites = Site.not_deleted().all()
    
    # Check if site_id is provided in query parameters
    site_id = request.args.get('site_id')
    
    return render_template('admin/create_tank.html', sites=sites, site_id=site_id)

@admin.route('/tanks/edit/<int:tank_id>', methods=['GET', 'POST'])
@admin_required
@handle_db_errors
def edit_tank(tank_id):
    """Edit tank"""
    tank = Tank.query.get_or_404(tank_id)
    
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        site_id = request.form.get('site_id')
        host = request.form.get('host')
        tcp_port = request.form.get('tcp_port')
        device_address = request.form.get('device_address')
        tank_orientation = request.form.get('tank_orientation')
        tank_height = request.form.get('tank_height')
        tank_diameter = request.form.get('tank_diameter')
        fluid_density = request.form.get('fluid_density')
        atmospheric_pressure = request.form.get('atmospheric_pressure')
        pressure_channel = request.form.get('pressure_channel')
        temp_channel = request.form.get('temp_channel')
        calibration_factor = request.form.get('calibration_factor')
        low_level_threshold = request.form.get('low_level_threshold')
        critical_level_threshold = request.form.get('critical_level_threshold')
        high_level_threshold = request.form.get('high_level_threshold')
        elevation = request.form.get('elevation')
        is_active = 'is_active' in request.form
        
        # Validate input
        if not name or not site_id or not host:
            flash('Tank name, site, and host are required', 'danger')
            return redirect(url_for('admin.edit_tank', tank_id=tank_id))
        
        # Check if tank name already exists for this site (for another tank)
        existing_tank = Tank.not_deleted().filter_by(name=name, site_id=site_id).first()
        if existing_tank and existing_tank.id != tank_id:
            flash('Tank name already exists for this site', 'danger')
            return redirect(url_for('admin.edit_tank', tank_id=tank_id))
        
        # Update tank
        tank.name = name
        tank.description = description
        tank.site_id = site_id
        tank.host = host
        tank.tcp_port = int(tcp_port) if tcp_port else 2000
        tank.device_address = int(device_address) if device_address else 1
        tank.tank_orientation = tank_orientation or 'vertical'
        tank.tank_height = float(tank_height) if tank_height else 2.0
        tank.tank_diameter = float(tank_diameter) if tank_diameter else 1.5
        tank.fluid_density = float(fluid_density) if fluid_density else 850
        tank.atmospheric_pressure = float(atmospheric_pressure) if atmospheric_pressure else 0.0
        tank.pressure_channel = int(pressure_channel) if pressure_channel else 1
        tank.temp_channel = int(temp_channel) if temp_channel else 4
        tank.calibration_factor = float(calibration_factor) if calibration_factor else 1.0
        tank.low_level_threshold = float(low_level_threshold) if low_level_threshold else 20.0
        tank.critical_level_threshold = float(critical_level_threshold) if critical_level_threshold else 10.0
        tank.high_level_threshold = float(high_level_threshold) if high_level_threshold else 90.0
        tank.elevation = float(elevation) if elevation else 0.0
        tank.is_active = is_active
        
        db.session.commit()
        
        # Update monitor if it exists
        try:
            from app import tank_monitor_manager as monitor_manager
            monitor = monitor_manager.get_monitor(tank_id)
            if monitor:
                monitor.host = tank.host
                monitor.tcp_port = tank.tcp_port
                monitor.device_address = tank.device_address
                monitor.tank_orientation = tank.tank_orientation
                monitor.tank_height = tank.tank_height
                monitor.tank_diameter = tank.tank_diameter
                monitor.fluid_density = tank.fluid_density
                monitor.atmospheric_pressure = tank.atmospheric_pressure
                monitor.pressure_channel = tank.pressure_channel
                monitor.temp_channel = tank.temp_channel
                monitor.calibration_factor = tank.calibration_factor
                
                # Recalculate tank volume
                monitor.tank_volume = 3.14159 * (tank.tank_diameter/2)**2 * tank.tank_height
                
                # Reconnect to apply new connection settings
                if monitor.connected:
                    monitor.disconnect()
                    monitor.connect()
        except ImportError:
            # If monitor_manager is not available, just continue
            pass
        
        flash('Tank updated successfully', 'success')
        return redirect(url_for('admin.tanks_index'))
    
    # Get sites for dropdown
    sites = Site.not_deleted().all()
    
    return render_template('admin/edit_tank.html', tank=tank, sites=sites)

@admin.route('/tanks/<int:tank_id>/start-monitoring')
@admin_required
@handle_db_errors
def start_monitoring(tank_id):
    """Start monitoring a tank"""
    tank = Tank.query.get_or_404(tank_id)
    
    try:
        from app import tank_monitor_manager as monitor_manager
        success = monitor_manager.start_monitoring(tank_id)
        
        if success:
            # Update last_connection time
            tank.last_connection = dt.now()
            db.session.commit()
            flash('Tank monitoring started successfully', 'success')
        else:
            flash('Failed to start tank monitoring', 'danger')
    except ImportError:
        flash('Tank monitoring system not available', 'danger')
    except Exception as e:
        flash(f'Error starting monitoring: {str(e)}', 'danger')
    
    return redirect(url_for('admin.tank_detail', tank_id=tank_id))

@admin.route('/tanks/<int:tank_id>/stop-monitoring')
@admin_required
@handle_db_errors
def stop_monitoring(tank_id):
    """Stop monitoring a tank"""
    try:
        from app import tank_monitor_manager as monitor_manager
        success = monitor_manager.stop_monitoring(tank_id)
        
        if success:
            flash('Tank monitoring stopped successfully', 'success')
        else:
            flash('Failed to stop tank monitoring', 'danger')
    except ImportError:
        flash('Tank monitoring system not available', 'danger')
    except Exception as e:
        flash(f'Error stopping monitoring: {str(e)}', 'danger')
    
    return redirect(url_for('admin.tank_detail', tank_id=tank_id))

@admin.route('/tanks/delete/<int:tank_id>', methods=['POST'])
@admin_required
@handle_db_errors
def delete_tank(tank_id):
    """Delete tank"""
    tank = Tank.query.get_or_404(tank_id)
    
    # Disconnect monitor if it exists
    try:
        from app import tank_monitor_manager as monitor_manager
        monitor = monitor_manager.get_monitor(tank_id)
        if monitor:
            monitor.stop_monitoring()
            monitor.disconnect()
            del monitor_manager.monitors[tank_id]
    except (ImportError, AttributeError):
        # If monitor_manager is not available or monitor doesn't exist, just continue
        pass
    
    # Use soft delete instead of hard delete
    tank.soft_delete()
    db.session.commit()
    
    # Check if this is an AJAX request
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'success': True,
            'message': 'Tank deleted successfully'
        })
    
    flash('Tank deleted successfully', 'success')
    return redirect(url_for('admin.tanks_index'))


@admin.route('/api/tanks')
@admin_required
def api_tanks():
    """API endpoint for tank list"""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '', type=str)
    company_id = request.args.get('company_id', 'all', type=str)
    site_id = request.args.get('site_id', 'all', type=str)
    status = request.args.get('status', 'all', type=str)
    per_page = ITEMS_PER_PAGE

    query = Tank.not_deleted()

    # Apply search filter
    if search:
        query = query.filter(func.lower(Tank.name).contains(func.lower(search)))

    # Apply company filter
    if company_id != 'all':
        query = query.join(Site).filter(Site.company_id == int(company_id))

    # Apply site filter
    if site_id != 'all':
        query = query.filter(Tank.site_id == int(site_id))

    # Apply status filter
    if status == 'active':
        query = query.filter(Tank.is_active == True)
    elif status == 'inactive':
        query = query.filter(Tank.is_active == False)
    elif status == 'connected':
        # This is a bit more complex as we need to check the last_connection time
        five_minutes_ago = dt.now() - timedelta(minutes=CONNECTION_TIMEOUT_MINUTES)
        query = query.filter(Tank.last_connection >= five_minutes_ago)
    elif status == 'disconnected':
        # Tanks that have never connected or haven't connected in the last 5 minutes
        five_minutes_ago = dt.now() - timedelta(minutes=CONNECTION_TIMEOUT_MINUTES)
        query = query.filter((Tank.last_connection < five_minutes_ago) | (Tank.last_connection == None))

    # Paginate the results
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    tanks = pagination.items

    # Prepare the data for JSON response
    tank_data = []
    for tank in tanks:
        measurement = tank.get_latest_measurement()
        
        tank_data.append({
            'id': tank.id,
            'name': tank.name,
            'site_id': tank.site_id,
            'site_name': tank.site.name,
            'company_id': tank.site.company_id,
            'company_name': tank.site.company.name,
            'description': tank.description,
            'is_active': tank.is_active,
            'host': tank.host,
            'tcp_port': tank.tcp_port,
            'connection_status': tank.get_connection_status(),
            'last_connection': tank.last_connection.isoformat() if tank.last_connection else None,
            'measurement': measurement.to_dict() if measurement else None,
            'low_level_threshold': tank.low_level_threshold,
            'critical_level_threshold': tank.critical_level_threshold,
            'high_level_threshold': tank.high_level_threshold
        })

    return jsonify({
        'success': True,
        'tanks': tank_data,
        'total': pagination.total,
        'page': page
    })

@admin.route('/api/sites/<int:site_id>/stats')
@admin_required
def api_site_stats(site_id):
    """API endpoint for site statistics"""
    site = Site.query.get_or_404(site_id)
    
    # Get all tanks for this site
    tanks = Tank.not_deleted().filter_by(site_id=site_id).all()
    tank_ids = [tank.id for tank in tanks]
    
    # Calculate statistics
    total_tank_count = len(tanks)
    
    # Count active tanks
    active_tank_count = Tank.not_deleted().filter(
        Tank.id.in_(tank_ids),
        Tank.is_active == True
    ).count() if tank_ids else 0
    
    # Count connected tanks
    five_minutes_ago = dt.now() - timedelta(minutes=CONNECTION_TIMEOUT_MINUTES)
    connected_tank_count = Tank.not_deleted().filter(
        Tank.id.in_(tank_ids),
        Tank.last_connection >= five_minutes_ago
    ).count() if tank_ids else 0
    
    # Calculate total volume and average fill level
    total_volume = 0
    total_fill_level = 0
    tanks_with_measurements = 0
    
    for tank_id in tank_ids:
        measurement = Measurement.query.filter_by(tank_id=tank_id).order_by(Measurement.timestamp.desc()).first()
        if measurement:
            total_volume += measurement.volume
            total_fill_level += measurement.fill_percent
            tanks_with_measurements += 1
    
    avg_fill_level = total_fill_level / tanks_with_measurements if tanks_with_measurements > 0 else 0
    
    # Get alarm counts
    total_alarms = Alarm.query.filter(Alarm.tank_id.in_(tank_ids)).count() if tank_ids else 0
    active_alarms = Alarm.query.filter(
        Alarm.tank_id.in_(tank_ids),
        Alarm.acknowledged == False
    ).count() if tank_ids else 0
    
    return jsonify({
        'success': True,
        'site_id': site_id,
        'stats': {
            'total_tank_count': total_tank_count,
            'active_tank_count': active_tank_count,
            'connected_tank_count': connected_tank_count,
            'total_volume': total_volume,
            'avg_fill_level': avg_fill_level,
            'total_alarms': total_alarms,
            'active_alarms': active_alarms
        }
    })

@admin.route('/api/sites/<int:site_id>/tanks')
@admin_required
def api_site_tanks(site_id):
    """API endpoint for site tanks with their latest measurements"""
    site = Site.query.get_or_404(site_id)
    
    tanks = Tank.not_deleted().filter_by(site_id=site_id).all()
    
    # Prepare the data for JSON response
    tank_data = []
    for tank in tanks:
        measurement = tank.get_latest_measurement()
        
        tank_data.append({
            'id': tank.id,
            'name': tank.name,
            'description': tank.description,
            'is_active': tank.is_active,
            'connection_status': tank.get_connection_status(),
            'last_connection': tank.last_connection.isoformat() if tank.last_connection else None,
            'measurement': measurement.to_dict() if measurement else None
        })
    
    return jsonify({
        'success': True,
        'site_id': site_id,
        'tanks': tank_data
    })

@admin.route('/api/sites/<int:site_id>/alarms')
@admin_required
def api_site_alarms(site_id):
    """API endpoint for site alarms"""
    site = Site.query.get_or_404(site_id)
    
    # Get all tanks for this site
    tanks = Tank.not_deleted().filter_by(site_id=site_id).all()
    tank_ids = [tank.id for tank in tanks]
    
    # Get recent alarms for these tanks
    alarms = []
    if tank_ids:
        alarms = Alarm.query.filter(Alarm.tank_id.in_(tank_ids)).order_by(Alarm.timestamp.desc()).limit(10).all()
    
    # Prepare the data for JSON response
    alarm_data = []
    for alarm in alarms:
        tank = Tank.query.get(alarm.tank_id)
        
        alarm_data.append({
            'id': alarm.id,
            'tank_id': alarm.tank_id,
            'tank_name': tank.name if tank else 'Unknown',
            'timestamp': alarm.timestamp.isoformat(),
            'type': alarm.type,
            'message': alarm.message,
            'value': alarm.value,
            'acknowledged': alarm.acknowledged,
            'acknowledged_by': alarm.acknowledged_by,
            'acknowledged_at': alarm.acknowledged_at.isoformat() if alarm.acknowledged_at else None
        })
    
    return jsonify({
        'success': True,
        'site_id': site_id,
        'alarms': alarm_data
    })

@admin.route('/api/companies/<int:company_id>/stats')
@admin_required
def api_company_stats(company_id):
    """API endpoint for company statistics"""
    company = Company.query.get_or_404(company_id)
    
    # Get all sites for this company
    sites = Site.not_deleted().filter_by(company_id=company_id).all()
    site_ids = [site.id for site in sites]
    
    # Get all tanks for these sites
    tanks = []
    tank_ids = []
    if site_ids:
        tanks = Tank.not_deleted().filter(Tank.site_id.in_(site_ids)).all()
        tank_ids = [tank.id for tank in tanks]
    
    # Calculate statistics
    total_site_count = len(sites)
    total_tank_count = len(tanks)
    
    # Count active tanks
    active_tank_count = Tank.not_deleted().filter(
        Tank.id.in_(tank_ids),
        Tank.is_active == True
    ).count() if tank_ids else 0
    
    # Count connected tanks
    five_minutes_ago = dt.now() - timedelta(minutes=CONNECTION_TIMEOUT_MINUTES)
    connected_tank_count = Tank.not_deleted().filter(
        Tank.id.in_(tank_ids),
        Tank.last_connection >= five_minutes_ago
    ).count() if tank_ids else 0
    
    # Calculate total volume and average fill level
    total_volume = 0
    total_fill_level = 0
    tanks_with_measurements = 0
    
    for tank_id in tank_ids:
        measurement = Measurement.query.filter_by(tank_id=tank_id).order_by(Measurement.timestamp.desc()).first()
        if measurement:
            total_volume += measurement.volume
            total_fill_level += measurement.fill_percent
            tanks_with_measurements += 1
    
    avg_fill_level = total_fill_level / tanks_with_measurements if tanks_with_measurements > 0 else 0
    
    # Get alarm counts
    total_alarms = Alarm.query.filter(Alarm.tank_id.in_(tank_ids)).count() if tank_ids else 0
    active_alarms = Alarm.query.filter(
        Alarm.tank_id.in_(tank_ids),
        Alarm.acknowledged == False
    ).count() if tank_ids else 0
    
    return jsonify({
        'success': True,
        'company_id': company_id,
        'stats': {
            'total_site_count': total_site_count,
            'total_tank_count': total_tank_count,
            'active_tank_count': active_tank_count,
            'connected_tank_count': connected_tank_count,
            'total_volume': total_volume,
            'avg_fill_level': avg_fill_level,
            'total_alarms': total_alarms,
            'active_alarms': active_alarms
        }
    })

@admin.route('/api/companies/<int:company_id>/sites')
@admin_required
def api_company_sites(company_id):
    """API endpoint for company sites with their statistics"""
    company = Company.query.get_or_404(company_id)
    
    sites = Site.not_deleted().filter_by(company_id=company_id).all()
    
    # Prepare the data for JSON response
    site_data = []
    for site in sites:
        # Get all tanks for this site
        tanks = Tank.not_deleted().filter_by(site_id=site.id).all()
        tank_ids = [tank.id for tank in tanks]
        
        # Calculate site statistics
        total_volume = 0
        total_fill_level = 0
        tanks_with_measurements = 0
        
        for tank_id in tank_ids:
            measurement = Measurement.query.filter_by(tank_id=tank_id).order_by(Measurement.timestamp.desc()).first()
            if measurement:
                total_volume += measurement.volume
                total_fill_level += measurement.fill_percent
                tanks_with_measurements += 1
        
        avg_fill_level = total_fill_level / tanks_with_measurements if tanks_with_measurements > 0 else 0
        
        # Get active alarm count
        active_alarms = Alarm.query.filter(
            Alarm.tank_id.in_(tank_ids),
            Alarm.acknowledged == False
        ).count() if tank_ids else 0
        
        site_data.append({
            'id': site.id,
            'name': site.name,
            'address': site.address,
            'contact_name': site.contact_name,
            'contact_email': site.contact_email,
            'contact_phone': site.contact_phone,
            'tank_count': len(tanks),
            'total_volume': total_volume,
            'avg_fill_level': avg_fill_level,
            'active_alarms': active_alarms
        })
    
    return jsonify({
        'success': True,
        'company_id': company_id,
        'sites': site_data
    })

@admin.route('/api/companies/<int:company_id>/alarms')
@admin_required
def api_company_alarms(company_id):
    """API endpoint for company alarms"""
    company = Company.query.get_or_404(company_id)
    
    # Get all sites for this company
    sites = Site.not_deleted().filter_by(company_id=company_id).all()
    site_ids = [site.id for site in sites]
    
    # Get all tanks for these sites
    tank_ids = []
    if site_ids:
        tanks = Tank.not_deleted().filter(Tank.site_id.in_(site_ids)).all()
        tank_ids = [tank.id for tank in tanks]
    
    # Get recent alarms for these tanks
    alarms = []
    if tank_ids:
        alarms = Alarm.query.filter(Alarm.tank_id.in_(tank_ids)).order_by(Alarm.timestamp.desc()).limit(10).all()
    
    # Prepare the data for JSON response
    alarm_data = []
    for alarm in alarms:
        tank = Tank.query.get(alarm.tank_id)
        site = Site.query.get(tank.site_id) if tank else None
        
        alarm_data.append({
            'id': alarm.id,
            'tank_id': alarm.tank_id,
            'tank_name': tank.name if tank else 'Unknown',
            'site_id': site.id if site else None,
            'site_name': site.name if site else 'Unknown',
            'timestamp': alarm.timestamp.isoformat(),
            'type': alarm.type,
            'message': alarm.message,
            'value': alarm.value,
            'acknowledged': alarm.acknowledged,
            'acknowledged_by': alarm.acknowledged_by,
            'acknowledged_at': alarm.acknowledged_at.isoformat() if alarm.acknowledged_at else None
        })
    
    return jsonify({
        'success': True,
        'company_id': company_id,
        'alarms': alarm_data
    })

@admin.route('/api/tanks/<int:tank_id>/measurements')
@admin_required
def api_tank_measurements(tank_id):
    """API endpoint for tank measurements"""
    tank = Tank.query.get_or_404(tank_id)
    limit = request.args.get('limit', 100, type=int)
    
    measurements = tank.get_recent_measurements(limit)
    
    return jsonify({
        'success': True,
        'tank_id': tank_id,
        'measurements': [m.to_dict() for m in measurements]
    })
    
@admin.route('/api/tanks/<int:tank_id>/alarms')
@admin_required
def api_tank_alarms(tank_id):
    """API endpoint for tank alarms"""
    tank = Tank.query.get_or_404(tank_id)
    limit = request.args.get('limit', 10, type=int)
    
    alarms = Alarm.query.filter_by(tank_id=tank_id).order_by(Alarm.timestamp.desc()).limit(limit).all()
    
    return jsonify({
        'success': True,
        'tank_id': tank_id,
        'alarms': [a.to_dict() for a in alarms]
    })

@admin.route('/api/statistics/daily-usage')
@admin_required
def api_daily_usage():
    """API endpoint for daily usage statistics"""
    try:
        # Get the last 7 days
        end_date = dt.now()
        start_date = end_date - timedelta(days=7)
        
        # Initialize data structures
        dates = []
        values = []
        
        # Query for each day
        current_date = start_date
        while current_date <= end_date:
            next_date = current_date + timedelta(days=1)
            
            # Calculate total usage for the day
            daily_usage = db.session.query(func.sum(Measurement.volume)).filter(
                Measurement.timestamp >= current_date,
                Measurement.timestamp < next_date
            ).scalar() or 0
            
            # Format date for display
            date_str = current_date.strftime('%Y-%m-%d')
            
            # Add to result arrays
            dates.append(date_str)
            values.append(daily_usage)
            
            # Move to next day
            current_date = next_date
        
        return jsonify({
            'success': True,
            'dates': dates,
            'values': values
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@admin.route('/start-all-monitoring')
@login_required
def start_all_monitoring():
    """Start monitoring all active tanks."""
    if not current_user.is_admin():
        flash('Access denied', 'danger')
        return redirect(url_for('admin.dashboard'))
    
    # Start monitoring in a background thread to avoid blocking
    def start_monitoring_thread():
        with current_app.app_context():
            active_tanks = Tank.query.filter_by(is_active=True).all()
            for tank in active_tanks:
                try:
                    from app import tank_monitor_manager as monitor_manager
                    monitor_manager.start_monitoring(tank.id)
                    current_app.logger.info(f"Started monitoring tank {tank.id} ({tank.name})")
                except Exception as e:
                    current_app.logger.error(f"Failed to start monitoring tank {tank.id} ({tank.name}): {str(e)}")
    
    Thread(target=start_monitoring_thread, daemon=True).start()
    flash('Started monitoring all active tanks', 'success')
    return redirect(url_for('admin.dashboard'))

@admin.route('/stop-all-monitoring')
@login_required
def stop_all_monitoring():
    """Stop monitoring all tanks."""
    if not current_user.is_admin():
        flash('Access denied', 'danger')
        return redirect(url_for('admin.dashboard'))
    
    try:
        from app import tank_monitor_manager as monitor_manager
        monitor_manager.stop_monitoring()
        flash('Stopped monitoring all tanks', 'success')
    except Exception as e:
        current_app.logger.error(f"Error stopping all monitoring: {str(e)}")
        flash(f'Error stopping monitoring: {str(e)}', 'danger')
    
    return redirect(url_for('admin.dashboard'))

@admin.route('/api/reset-all-statistics', methods=['POST'])
@login_required
def reset_all_statistics():
    """Reset statistics for all tanks."""
    if not current_user.is_admin():
        return jsonify({
            'success': False,
            'error': 'Access denied'
        }), 403
    
    try:
        # Get all active tanks
        tanks = Tank.not_deleted().filter_by(is_active=True).all()
        
        # Reset statistics for each tank
        for tank in tanks:
            try:
                from app import tank_monitor_manager as monitor_manager
                monitor_manager.reset_statistics(tank.id)
            except Exception as e:
                current_app.logger.error(f"Error resetting statistics for tank {tank.id}: {str(e)}")
        
        return jsonify({
            'success': True,
            'message': f'Statistics reset for {len(tanks)} tanks'
        })
    except Exception as e:
        current_app.logger.error(f"Error resetting all statistics: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
@admin.route('/activity-log')
@login_required
def activity_log():
    """View activity log."""
    if not current_user.is_admin():
        flash('Access denied', 'danger')
        return redirect(url_for('dashboard'))
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    # Get filter parameters
    user_id = request.args.get('user_id', 'all')
    action = request.args.get('action', 'all')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    
    # Build query
    query = ActivityLog.query
    
    if user_id != 'all' and user_id.isdigit():
        query = query.filter_by(user_id=int(user_id))
    
    if action != 'all':
        query = query.filter_by(action=action)
    
    if date_from:
        try:
            date_from_obj = dt.strptime(date_from, '%Y-%m-%d')
            query = query.filter(ActivityLog.timestamp >= date_from_obj)
        except ValueError:
            flash('Invalid date format for "From" date', 'warning')
    
    if date_to:
        try:
            date_to_obj = dt.strptime(date_to, '%Y-%m-%d')
            date_to_obj = date_to_obj + timedelta(days=1)  # Include the end date
            query = query.filter(ActivityLog.timestamp < date_to_obj)
        except ValueError:
            flash('Invalid date format for "To" date', 'warning')
    
    # Paginate results
    activities = query.order_by(ActivityLog.timestamp.desc()).paginate(page=page, per_page=per_page)
    
    # Get users for filter dropdown
    users = User.query.order_by(User.username).all()
    
    # Get unique actions for filter dropdown
    actions = db.session.query(ActivityLog.action).distinct().order_by(ActivityLog.action).all()
    actions = [a[0] for a in actions]
    
    return render_template('admin/activity_log.html',
                          activities=activities,
                          users=users,
                          actions=actions,
                          user_id=user_id,
                          action=action,
                          date_from=date_from,
                          date_to=date_to)

@admin.route('/api/activity-log')
@admin_required
def api_activity_log():
    """API endpoint for activity log"""
    try:
        # This is a placeholder - in a real application, you would have an ActivityLog model
        # For now, we'll return some sample data
        activities = [
            {
                'timestamp': (dt.now() - timedelta(minutes=5)).isoformat(),
                'user': 'admin',
                'action': 'Login',
                'details': 'Admin user logged in'
            },
            {
                'timestamp': (dt.now() - timedelta(minutes=10)).isoformat(),
                'user': 'admin',
                'action': 'Update',
                'details': 'Updated tank configuration for Tank 1'
            },
            {
                'timestamp': (dt.now() - timedelta(minutes=15)).isoformat(),
                'user': 'admin',
                'action': 'Create',
                'details': 'Created new site "Warehouse 3"'
            },
            {
                'timestamp': (dt.now() - timedelta(minutes=30)).isoformat(),
                'user': 'john',
                'action': 'Acknowledge',
                'details': 'Acknowledged low level alarm for Tank 2'
            },
            {
                'timestamp': (dt.now() - timedelta(hours=1)).isoformat(),
                'user': 'admin',
                'action': 'Create',
                'details': 'Added new user "sarah"'
            }
        ]
        
        return jsonify({
            'success': True,
            'activities': activities
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@admin.route('/deleted-records', methods=['GET'])
@admin_required
def deleted_records():
    """View deleted records"""
    record_type = request.args.get('type', 'users')
    
    if record_type == 'users':
        records = User.query.filter(User.deleted_at != None).all()
        return render_template('admin/deleted_records.html', 
                              records=records, 
                              record_type=record_type,
                              restore_url='admin.restore_user')
    elif record_type == 'companies':
        records = Company.query.filter(Company.deleted_at != None).all()
        return render_template('admin/deleted_records.html', 
                              records=records, 
                              record_type=record_type,
                              restore_url='admin.restore_company')
    elif record_type == 'sites':
        records = Site.query.filter(Site.deleted_at != None).all()
        return render_template('admin/deleted_records.html', 
                              records=records, 
                              record_type=record_type,
                              restore_url='admin.restore_site')
    elif record_type == 'tanks':
        records = Tank.query.filter(Tank.deleted_at != None).all()
        return render_template('admin/deleted_records.html', 
                              records=records, 
                              record_type=record_type,
                              restore_url='admin.restore_tank')
    else:
        flash('Invalid record type', 'danger')
        return redirect(url_for('admin.dashboard'))

@admin.route('/api/deleted-records')
@admin_required
def api_deleted_records():
    """API endpoint for deleted records"""
    record_type = request.args.get('type', 'users')
    page = request.args.get('page', 1, type=int)
    per_page = ITEMS_PER_PAGE
    
    if record_type == 'users':
        query = User.query.filter(User.deleted_at != None)
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        records = pagination.items
        
        data = [{
            'id': user.id,
            'name': user.get_full_name(),
            'username': user.username,
            'email': user.email,
            'deleted_at': user.deleted_at.isoformat() if user.deleted_at else None
        } for user in records]
        
    elif record_type == 'companies':
        query = Company.query.filter(Company.deleted_at != None)
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        records = pagination.items
        
        data = [{
            'id': company.id,
            'name': company.name,
            'contact_name': company.contact_name,
            'contact_email': company.contact_email,
            'deleted_at': company.deleted_at.isoformat() if company.deleted_at else None
        } for company in records]
        
    elif record_type == 'sites':
        query = Site.query.filter(Site.deleted_at != None)
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        records = pagination.items
        
        data = [{
            'id': site.id,
            'name': site.name,
            'company_name': site.company.name if site.company else 'Unknown',
            'address': site.address,
            'deleted_at': site.deleted_at.isoformat() if site.deleted_at else None
        } for site in records]
        
    elif record_type == 'tanks':
        query = Tank.query.filter(Tank.deleted_at != None)
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        records = pagination.items
        
        data = [{
            'id': tank.id,
            'name': tank.name,
            'site_name': tank.site.name if tank.site else 'Unknown',
            'company_name': tank.site.company.name if tank.site and tank.site.company else 'Unknown',
            'deleted_at': tank.deleted_at.isoformat() if tank.deleted_at else None
        } for tank in records]
        
    else:
        return jsonify({
            'success': False,
            'message': 'Invalid record type'
        }), 400
    
    return jsonify({
        'success': True,
        'records': data,
        'total': pagination.total,
        'page': page,
        'type': record_type
    })

@admin.route('/system-settings', methods=['GET', 'POST'])
@admin_required
def system_settings():
    """System settings page"""
    if request.method == 'POST':
        # Update system settings
        # This is a placeholder - in a real application, you would have a SystemSettings model
        flash('System settings updated successfully', 'success')
        return redirect(url_for('admin.system_settings'))
    
    # This is a placeholder - in a real application, you would load settings from a database
    settings = {
        'site_name': 'Fuel Tank Monitoring System',
        'contact_email': 'admin@example.com',
        'measurement_interval': 5,  # minutes
        'default_alarm_threshold': 20,  # percent
        'enable_email_notifications': True,
        'enable_sms_notifications': False
    }
    
    return render_template('admin/system_settings.html', settings=settings)

@admin.route('/backup-database', methods=['GET', 'POST'])
@admin_required
@login_required
def backup_database():
    """Backup the database."""
    if not current_user.is_admin():
        flash('Access denied', 'danger')
        return redirect(url_for('admin.dashboard'))
    
    try:
        import os
        # Create backup directory if it doesn't exist
        backup_dir = os.path.join(current_app.root_path, 'backups')
        os.makedirs(backup_dir, exist_ok=True)
        
        # Generate backup filename with timestamp
        timestamp = dt.now().strftime('%Y%m%d_%H%M%S')
        backup_file = os.path.join(backup_dir, f'backup_{timestamp}.sql')
        
        # Get database URI from config
        db_uri = current_app.config['SQLALCHEMY_DATABASE_URI']
        
        # Check database type
        if db_uri.startswith('sqlite:'):
            # Handle SQLite backup
            sqlite_file = db_uri.replace('sqlite:///', '')
            if not os.path.exists(sqlite_file):
                raise ValueError(f"SQLite database file not found: {sqlite_file}")
            
            import shutil
            shutil.copy2(sqlite_file, backup_file)
            
            # Log the activity
            log_activity(
                action="database_backup",
                details=f"SQLite database backup created: {os.path.basename(backup_file)}"
            )
            
            flash(f'Database backup created successfully: {os.path.basename(backup_file)}', 'success')
            return redirect(url_for('admin.dashboard'))
        
        elif db_uri.startswith('postgresql:'):
            # Parse PostgreSQL URI - handle both formats
            import re
            # Try standard format first
            match = re.match(r'postgresql://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)', db_uri)
            
            if not match:
                # Try alternative format with query parameters
                match = re.match(r'postgresql://([^:]+):([^@]+)@([^:/]+)(?::(\d+))?/([^?]+)', db_uri)
            
            if not match:
                raise ValueError(f"Could not parse PostgreSQL database URI: {db_uri[:10]}...")
            
            username, password, host, port, dbname = match.groups()
            
            # Use default PostgreSQL port if not specified
            port = port or '5432'
            
            # Build pg_dump command
            cmd = [
                'pg_dump',
                '-h', host,
                '-p', port,
                '-U', username,
                '-F', 'c',  # Custom format (compressed)
                '-b',  # Include large objects
                '-v',  # Verbose
                '-f', backup_file,
                dbname
            ]
            
            # Set PGPASSWORD environment variable
            env = os.environ.copy()
            env['PGPASSWORD'] = password
            
            # Execute pg_dump
            import subprocess
            result = subprocess.run(cmd, env=env, capture_output=True, text=True)
            
            if result.returncode != 0:
                raise ValueError(f"pg_dump failed: {result.stderr}")
            
            # Log the activity
            log_activity(
                action="database_backup",
                details=f"PostgreSQL database backup created: {os.path.basename(backup_file)}"
            )
            
            flash(f'Database backup created successfully: {os.path.basename(backup_file)}', 'success')
            return redirect(url_for('admin.dashboard'))
        
        elif db_uri.startswith('mysql:'):
            # Handle MySQL backup
            import re
            match = re.match(r'mysql://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)', db_uri)
            
            if not match:
                raise ValueError("Could not parse MySQL database URI")
            
            username, password, host, port, dbname = match.groups()
            
            # Build mysqldump command
            cmd = [
                'mysqldump',
                '-h', host,
                '-P', port,
                '-u', username,
                f'--password={password}',
                '--single-transaction',
                '--routines',
                '--triggers',
                '--events',
                dbname
            ]
            
            # Execute mysqldump
            import subprocess
            with open(backup_file, 'w') as f:
                result = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, text=True)
            
            if result.returncode != 0:
                raise ValueError(f"mysqldump failed: {result.stderr}")
            
            # Log the activity
            log_activity(
                action="database_backup",
                details=f"MySQL database backup created: {os.path.basename(backup_file)}"
            )
            
            flash(f'Database backup created successfully: {os.path.basename(backup_file)}', 'success')
            return redirect(url_for('admin.dashboard'))
        
        else:
            raise ValueError(f"Unsupported database type: {db_uri.split(':')[0]}")
        
    except Exception as e:
        current_app.logger.error(f"Error backing up database: {str(e)}")
        flash(f'Error backing up database: {str(e)}', 'danger')
    
    return redirect(url_for('admin.dashboard'))

@admin.route('/download-backup/<path:filename>')
@admin_required
def download_backup(filename):
    """Download database backup"""
    import os
    from flask import send_from_directory
    
    # Ensure the filename is safe
    from werkzeug.utils import secure_filename
    safe_filename = secure_filename(os.path.basename(filename))
    
    # Get the backup directory
    backup_dir = os.path.join(current_app.root_path, 'backups')
    
    # Check if the file exists
    if not os.path.exists(os.path.join(backup_dir, safe_filename)):
        flash('Backup file not found', 'danger')
        return redirect(url_for('admin.dashboard'))
    
    # Log the activity
    log_activity(
        action="backup_download",
        details=f"Downloaded database backup: {safe_filename}"
    )
    
    # Send the file
    return send_from_directory(
        directory=backup_dir,
        path=safe_filename,
        as_attachment=True,
        download_name=safe_filename
    )
@admin.route('/restore-backup/<int:backup_id>', methods=['POST'])
@admin_required
def restore_backup(backup_id):
    """Restore database from backup"""
    # This is a placeholder - in a real application, you would implement actual restore logic
    flash('Database restored successfully', 'success')
    return redirect(url_for('admin.backup_database'))

@admin.route('/delete-backup/<int:backup_id>', methods=['POST'])
@admin_required
def delete_backup(backup_id):
    """Delete database backup"""
    # This is a placeholder - in a real application, you would implement actual delete logic
    flash('Backup deleted successfully', 'success')
    return redirect(url_for('admin.backup_database'))

@admin.route('/system-logs')
@admin_required
def system_logs():
    """System logs page"""
    # This is a placeholder - in a real application, you would load logs from a file or database
    logs = [
        {
            'timestamp': '2023-02-01 12:00:00',
            'level': 'INFO',
            'message': 'System started'
        },
        {
            'timestamp': '2023-02-01 12:01:00',
            'level': 'INFO',
            'message': 'User admin logged in'
        },
        {
            'timestamp': '2023-02-01 12:05:00',
            'level': 'WARNING',
            'message': 'Failed login attempt for user john'
        },
        {
            'timestamp': '2023-02-01 12:10:00',
            'level': 'ERROR',
            'message': 'Database connection error'
        },
        {
            'timestamp': '2023-02-01 12:15:00',
            'level': 'INFO',
            'message': 'Database connection restored'
        }
    ]
    
    return render_template('admin/system_logs.html', logs=logs)

@admin.route('/api/system-logs')
@admin_required
def api_system_logs():
    """API endpoint for system logs"""
    # This is a placeholder - in a real application, you would load logs from a file or database
    logs = [
        {
            'timestamp': '2023-02-01 12:00:00',
            'level': 'INFO',
            'message': 'System started'
        },
        {
            'timestamp': '2023-02-01 12:01:00',
            'level': 'INFO',
            'message': 'User admin logged in'
        },
        {
            'timestamp': '2023-02-01 12:05:00',
            'level': 'WARNING',
            'message': 'Failed login attempt for user john'
        },
        {
            'timestamp': '2023-02-01 12:10:00',
            'level': 'ERROR',
            'message': 'Database connection error'
        },
        {
            'timestamp': '2023-02-01 12:15:00',
            'level': 'INFO',
            'message': 'Database connection restored'
        }
    ]
    
    return jsonify({
        'success': True,
        'logs': logs
    })

@admin.route('/api/system-status')
@login_required
def system_status():
    """Get system status for admin dashboard."""
    if not current_user.is_admin():
        return jsonify({'error': 'Access denied'}), 403
    
    # Get statistics
    total_tanks = Tank.not_deleted().count()
    connected_tanks = Tank.not_deleted().filter(
        Tank.last_connection >= (dt.now() - timedelta(minutes=5))
    ).count()
    
    active_alarms = Alarm.query.filter_by(acknowledged=False).count()
    total_users = User.not_deleted().count()
    
    # Get system stats
    try:
        import psutil
        import time
        
        # CPU usage
        cpu_usage = psutil.cpu_percent(interval=1)
        
        # Memory usage
        memory = psutil.virtual_memory()
        memory_usage = memory.percent
        memory_used = memory.used / (1024 * 1024 * 1024)  # GB
        memory_total = memory.total / (1024 * 1024 * 1024)  # GB
        
        # Disk usage
        disk = psutil.disk_usage('/')
        disk_usage = disk.percent
        disk_used = disk.used / (1024 * 1024 * 1024)  # GB
        disk_total = disk.total / (1024 * 1024 * 1024)  # GB
        
        # Network stats
        #net_io = psutil.net_io_counters()
        net_io_1 = psutil.net_io_counters()
        time.sleep(1)
        net_io_2 = psutil.net_io_counters()

        bytes_sent = net_io_2.bytes_sent - net_io_1.bytes_sent
        bytes_recv = net_io_2.bytes_recv - net_io_1.bytes_recv

        # Convert to KB/s or MB/s
        net_sent = bytes_sent / (1024 * 1024)  # KB/s
        net_recv = bytes_recv / (1024 * 1024)  # KB/s

        #net_sent = net_io.bytes_sent / (1024 * 1024)  # MB
        #net_recv = net_io.bytes_recv / (1024 * 1024)  # MB
        
        system_stats = {
            'cpu_usage': cpu_usage,
            'memory_usage': memory_usage,
            'memory_used': round(memory_used, 2),
            'memory_total': round(memory_total, 2),
            'disk_usage': disk_usage,
            'disk_used': round(disk_used, 2),
            'disk_total': round(disk_total, 2),
            'net_sent': round(net_sent, 2),
            'net_recv': round(net_recv, 2)
        }
    except ImportError:
        system_stats = {
            'cpu_usage': 0,
            'memory_usage': 0,
            'memory_used': 0,
            'memory_total': 0,
            'disk_usage': 0,
            'disk_used': 0,
            'disk_total': 0,
            'net_sent': 0,
            'net_recv': 0
        }
    
    return jsonify({
        'success': True,
        'stats': {
            'total_tanks': total_tanks,
            'connected_tanks': connected_tanks,
            'active_alarms': active_alarms,
            'total_users': total_users
        },
        'system': system_stats
    })

# Error handlers for the admin blueprint
@admin.errorhandler(404)
def page_not_found(e):
    return render_template('admin/errors/404.html'), 404

@admin.errorhandler(403)
def forbidden(e):
    return render_template('admin/errors/403.html'), 403

@admin.errorhandler(500)
def internal_server_error(e):
    return render_template('admin/errors/500.html'), 500

# Decorator for handling database errors
def handle_db_errors(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            db.session.rollback()
            flash(f'Database error: {str(e)}', 'danger')
            return redirect(url_for('admin.dashboard'))
    return decorated_function

# Constants
CONNECTION_TIMEOUT_MINUTES = 5
ITEMS_PER_PAGE = 10

# Form classes
class CreateUserForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=64)])
    email = StringField('Email', validators=[DataRequired(), Email(), Length(max=120)])
    password = StringField('Password', validators=[DataRequired(), Length(min=8, max=128)])
    confirm_password = StringField('Confirm Password', validators=[DataRequired(), Length(min=8, max=128)])
    first_name = StringField('First Name', validators=[Length(max=64)])
    last_name = StringField('Last Name', validators=[Length(max=64)])
    role = StringField('Role', validators=[DataRequired()])
    submit = SubmitField('Create User')

class EditUserForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email(), Length(max=120)])
    password = StringField('Password', validators=[Length(min=8, max=128)])
    confirm_password = StringField('Confirm Password', validators=[Length(min=8, max=128)])
    first_name = StringField('First Name', validators=[Length(max=64)])
    last_name = StringField('Last Name', validators=[Length(max=64)])
    role = StringField('Role', validators=[DataRequired()])
    submit = SubmitField('Update User')

# Site form classes
class CreateSiteForm(FlaskForm):
    name = StringField('Site Name', validators=[DataRequired(), Length(max=100)])
    address = TextAreaField('Address', validators=[Length(max=200)])
    location = StringField('Location', validators=[Length(max=200)])
    company_id = StringField('Company', validators=[DataRequired()])
    contact_name = StringField('Contact Name', validators=[Length(max=100)])
    contact_email = StringField('Contact Email', validators=[Email(), Length(max=100)])
    contact_phone = StringField('Contact Phone', validators=[Length(max=20)])
    contact_info = TextAreaField('Additional Contact Info', validators=[Length(max=500)])
    is_active = BooleanField('Active')
    submit = SubmitField('Create Site')

class EditSiteForm(FlaskForm):
    name = StringField('Site Name', validators=[DataRequired(), Length(max=100)])
    address = TextAreaField('Address', validators=[Length(max=200)])
    location = StringField('Location', validators=[Length(max=200)])
    company_id = StringField('Company', validators=[DataRequired()])
    contact_name = StringField('Contact Name', validators=[Length(max=100)])
    contact_email = StringField('Contact Email', validators=[Email(), Length(max=100)])
    contact_phone = StringField('Contact Phone', validators=[Length(max=20)])
    contact_info = TextAreaField('Additional Contact Info', validators=[Length(max=500)])
    is_active = BooleanField('Active')
    submit = SubmitField('Update Site')

# Tank form classes
class CreateTankForm(FlaskForm):
    name = StringField('Tank Name', validators=[DataRequired(), Length(max=100)])
    description = TextAreaField('Description', validators=[Length(max=500)])
    site_id = StringField('Site', validators=[DataRequired()])
    host = StringField('Host/IP Address', validators=[DataRequired(), Length(max=100)])
    tcp_port = IntegerField('TCP Port', default=2000)
    device_address = IntegerField('Device Address', default=1)
    tank_orientation = SelectField('Tank Orientation', choices=[('vertical', 'Vertical'), ('horizontal', 'Horizontal')], default='vertical')
    tank_height = FloatField('Tank Height (meters)', default=2.0)
    tank_diameter = FloatField('Tank Diameter (meters)', default=1.5)
    fluid_density = FloatField('Fluid Density (kg/m³)', default=850)
    atmospheric_pressure = FloatField('Atmospheric Pressure (bar)', default=0.0)
    elevation = FloatField('Elevation (meters)', default=0.0)
    pressure_channel = IntegerField('Pressure Channel', default=1)
    temp_channel = IntegerField('Temperature Channel', default=4)
    calibration_factor = FloatField('Calibration Factor', default=1.0)
    low_level_threshold = FloatField('Low Level Threshold (%)', default=20.0)
    critical_level_threshold = FloatField('Critical Level Threshold (%)', default=10.0)
    high_level_threshold = FloatField('High Level Threshold (%)', default=90.0)
    is_active = BooleanField('Active')
    submit = SubmitField('Create Tank')

class EditTankForm(FlaskForm):
    name = StringField('Tank Name', validators=[DataRequired(), Length(max=100)])
    description = TextAreaField('Description', validators=[Length(max=500)])
    site_id = StringField('Site', validators=[DataRequired()])
    host = StringField('Host/IP Address', validators=[DataRequired(), Length(max=100)])
    tcp_port = IntegerField('TCP Port', default=2000)
    device_address = IntegerField('Device Address', default=1)
    tank_orientation = SelectField('Tank Orientation', choices=[('vertical', 'Vertical'), ('horizontal', 'Horizontal')], default='vertical')
    tank_height = FloatField('Tank Height (meters)', default=2.0)
    tank_diameter = FloatField('Tank Diameter (meters)', default=1.5)
    fluid_density = FloatField('Fluid Density (kg/m³)', default=850)
    atmospheric_pressure = FloatField('Atmospheric Pressure (bar)', default=0.0)
    elevation = FloatField('Elevation (meters)', default=0.0)
    pressure_channel = IntegerField('Pressure Channel', default=1)
    temp_channel = IntegerField('Temperature Channel', default=4)
    calibration_factor = FloatField('Calibration Factor', default=1.0)
    low_level_threshold = FloatField('Low Level Threshold (%)', default=20.0)
    critical_level_threshold = FloatField('Critical Level Threshold (%)', default=10.0)
    high_level_threshold = FloatField('High Level Threshold (%)', default=90.0)
    is_active = BooleanField('Active')
    submit = SubmitField('Update Tank')

# System settings form
class SystemSettingsForm(FlaskForm):
    site_name = StringField('Site Name', validators=[DataRequired(), Length(max=100)])
    contact_email = StringField('Contact Email', validators=[Email(), Length(max=100)])
    measurement_interval = IntegerField('Measurement Interval (minutes)', default=5)
    default_alarm_threshold = IntegerField('Default Alarm Threshold (%)', default=20)
    enable_email_notifications = BooleanField('Enable Email Notifications')
    enable_sms_notifications = BooleanField('Enable SMS Notifications')
    submit = SubmitField('Save Settings')

# Add soft delete functionality to models
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

# Initialize soft delete methods
add_soft_delete_methods()

# Add deleted_at column to models if not already present
def ensure_deleted_at_column():
    """Ensure deleted_at column exists in models"""
    from sqlalchemy import inspect
    
    for model in [User, Company, Site, Tank]:
        inspector = inspect(model)
        if 'deleted_at' not in [c.name for c in inspector.columns]:
            # This would be done via a migration in a real application
            # For now, we'll just print a warning
            print(f"Warning: deleted_at column missing from {model.__name__} model")

# Check for deleted_at column
ensure_deleted_at_column()

# Additional routes for managing user roles and permissions

@admin.route('/roles')
@admin_required
def roles():
    """Role management page"""
    # This is a placeholder - in a real application, you would have a Role model
    roles = [
        {'id': 1, 'name': 'admin', 'description': 'Administrator with full access'},
        {'id': 2, 'name': 'company_admin', 'description': 'Company administrator with access to company data'},
        {'id': 3, 'name': 'user', 'description': 'Regular user with limited access'}
    ]
    
    return render_template('admin/roles.html', roles=roles)

@admin.route('/api/roles')
@admin_required
def api_roles():
    """API endpoint for roles"""
    # This is a placeholder - in a real application, you would have a Role model
    roles = [
        {'id': 1, 'name': 'admin', 'description': 'Administrator with full access'},
        {'id': 2, 'name': 'company_admin', 'description': 'Company administrator with access to company data'},
        {'id': 3, 'name': 'user', 'description': 'Regular user with limited access'}
    ]
    
    return jsonify({
        'success': True,
        'roles': roles
    })

@admin.route('/api/permissions')
@admin_required
def api_permissions():
    """API endpoint for permissions"""
    # This is a placeholder - in a real application, you would have a Permission model
    permissions = [
        {'id': 1, 'name': 'view_users', 'description': 'View user list'},
        {'id': 2, 'name': 'create_users', 'description': 'Create new users'},
        {'id': 3, 'name': 'edit_users', 'description': 'Edit existing users'},
        {'id': 4, 'name': 'delete_users', 'description': 'Delete users'},
        {'id': 5, 'name': 'view_companies', 'description': 'View company list'},
        {'id': 6, 'name': 'create_companies', 'description': 'Create new companies'},
        {'id': 7, 'name': 'edit_companies', 'description': 'Edit existing companies'},
        {'id': 8, 'name': 'delete_companies', 'description': 'Delete companies'},
        {'id': 9, 'name': 'view_sites', 'description': 'View site list'},
        {'id': 10, 'name': 'create_sites', 'description': 'Create new sites'},
        {'id': 11, 'name': 'edit_sites', 'description': 'Edit existing sites'},
        {'id': 12, 'name': 'delete_sites', 'description': 'Delete sites'},
        {'id': 13, 'name': 'view_tanks', 'description': 'View tank list'},
        {'id': 14, 'name': 'create_tanks', 'description': 'Create new tanks'},
        {'id': 15, 'name': 'edit_tanks', 'description': 'Edit existing tanks'},
        {'id': 16, 'name': 'delete_tanks', 'description': 'Delete tanks'},
        {'id': 17, 'name': 'view_alarms', 'description': 'View alarm list'},
        {'id': 18, 'name': 'acknowledge_alarms', 'description': 'Acknowledge alarms'},
        {'id': 19, 'name': 'delete_alarms', 'description': 'Delete alarms'},
        {'id': 20, 'name': 'view_measurements', 'description': 'View measurement data'},
        {'id': 21, 'name': 'system_settings', 'description': 'Manage system settings'},
        {'id': 22, 'name': 'backup_database', 'description': 'Backup and restore database'},
        {'id': 23, 'name': 'view_logs', 'description': 'View system logs'}
    ]
    
    return jsonify({
        'success': True,
        'permissions': permissions
    })

@admin.route('/api/role-permissions')
@admin_required
def api_role_permissions():
    """API endpoint for role permissions"""
    # This is a placeholder - in a real application, you would have a RolePermission model
    role_permissions = {
        'admin': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23],
        'company_admin': [1, 5, 9, 10, 11, 13, 14, 15, 17, 18, 20],
        'user': [5, 9, 13, 17, 20]
    }
    
    role = request.args.get('role', 'admin')
    
    return jsonify({
        'success': True,
        'role': role,
        'permissions': role_permissions.get(role, [])
    })

@admin.route('/api/user-permissions/<int:user_id>')
@admin_required
def api_user_permissions(user_id):
    """API endpoint for user permissions"""
    user = User.query.get_or_404(user_id)
    
    # In a real application, you would get the user's permissions from a database
    # For now, we'll just return permissions based on the user's role
    role_permissions = {
        'admin': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23],
        'company_admin': [1, 5, 9, 10, 11, 13, 14, 15, 17, 18, 20],
        'user': [5, 9, 13, 17, 20]
    }
    
    return jsonify({
        'success': True,
        'user_id': user_id,
        'role': user.role,
        'permissions': role_permissions.get(user.role, [])
    })
@admin.route('/dashboard')
@admin_required
@login_required
def dashboard():
    """Admin dashboard."""
    if not current_user.is_admin():
        flash('Access denied', 'danger')
        return redirect(url_for('dashboard'))
    
    # Get statistics
    total_tanks = Tank.not_deleted().count()
    connected_tanks = Tank.not_deleted().filter(
        Tank.last_connection >= (dt.now() - timedelta(minutes=5))
    ).count()
    
    active_alarms = Alarm.query.filter_by(acknowledged=False).count()
    total_users = User.not_deleted().count()
    
    # Get system stats
    try:
        import psutil
        import platform
        import time
        import os
        import glob

        from datetime import datetime
        
        # Get uptime
        if platform.system() == 'Windows':
            from ctypes import windll
            uptime_seconds = windll.kernel32.GetTickCount64() // 1000
        else:
            uptime_seconds = int(time.time() - psutil.boot_time())
        
        days, remainder = divmod(uptime_seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime = f"{days}d {hours}h {minutes}m {seconds}s"
        
        # Get last backup time
        backup_dir = os.path.join(current_app.root_path, 'backups')
        os.makedirs(backup_dir, exist_ok=True)
        
        backup_files = glob.glob(os.path.join(backup_dir, 'backup_*.sql'))
        if backup_files:
            latest_backup = max(backup_files, key=os.path.getctime)
            last_backup = datetime.fromtimestamp(os.path.getctime(latest_backup)).strftime('%Y-%m-%d %H:%M:%S')
        else:
            last_backup = 'Never'
            
        # Get recent backups
        backups = []
        for backup_file in sorted(backup_files, key=os.path.getctime, reverse=True)[:5]:
            filename = os.path.basename(backup_file)
            file_date = datetime.fromtimestamp(os.path.getctime(backup_file))
            file_size = os.path.getsize(backup_file)
            
            # Format file size
            if file_size < 1024:
                size_str = f"{file_size} B"
            elif file_size < 1024 * 1024:
                size_str = f"{file_size / 1024:.1f} KB"
            else:
                size_str = f"{file_size / (1024 * 1024):.1f} MB"
            
            backups.append({
                'filename': filename,
                'date': file_date,
                'size': size_str
            })
    except Exception as e:
        current_app.logger.error(f"Error getting system stats: {str(e)}")
        uptime = 'Unknown'
        last_backup = 'Unknown'
        backups = []
    
    stats = {
        'total_tanks': total_tanks,
        'connected_tanks': connected_tanks,
        'active_alarms': active_alarms,
        'total_users': total_users,
        'uptime': uptime,
        'last_backup': last_backup
    }
    
    # Get recent activity
    recent_activity = ActivityLog.query.order_by(ActivityLog.timestamp.desc()).limit(5).all()
    
    return render_template('admin/dashboard.html', 
                          stats=stats,
                          recent_activity=recent_activity,
                          backups=backups)

@admin.route('/api/dashboard-chart-data')
@admin_required
def api_dashboard_chart_data():
    """API endpoint for dashboard chart data"""
    chart_type = request.args.get('type', 'volume')
    
    if chart_type == 'volume':
        # Get volume data for the last 7 days
        end_date = dt.now()
        start_date = end_date - timedelta(days=7)
        
        # Initialize data structures
        dates = []
        values = []
        
        # Query for each day
        current_date = start_date
        while current_date <= end_date:
            next_date = current_date + timedelta(days=1)
            
            # Calculate total volume for the day
            daily_volume = 0
            for tank in Tank.not_deleted().all():
                measurement = Measurement.query.filter(
                    Measurement.tank_id == tank.id,
                    Measurement.timestamp >= current_date,
                    Measurement.timestamp < next_date
                ).order_by(Measurement.timestamp.desc()).first()
                
                if measurement:
                    daily_volume += measurement.volume
            
            # Format date for display
            date_str = current_date.strftime('%Y-%m-%d')
            
            # Add to result arrays
            dates.append(date_str)
            values.append(daily_volume)
            
            # Move to next day
            current_date = next_date
        
        return jsonify({
            'success': True,
            'chart_type': chart_type,
            'labels': dates,
            'data': values
        })
    
    elif chart_type == 'alarms':
        # Get alarm counts by type for the last 30 days
        end_date = dt.now()
        start_date = end_date - timedelta(days=30)
        
        # Get all alarms in the period
        alarms = Alarm.query.filter(
            Alarm.timestamp >= start_date,
            Alarm.timestamp <= end_date
        ).all()
        
        # Count alarms by type
        alarm_types = {}
        for alarm in alarms:
            if alarm.type in alarm_types:
                alarm_types[alarm.type] += 1
            else:
                alarm_types[alarm.type] = 1
        
        # Prepare data for chart
        labels = list(alarm_types.keys())
        data = list(alarm_types.values())
        
        return jsonify({
            'success': True,
            'chart_type': chart_type,
            'labels': labels,
            'data': data
        })
    
    else:
        return jsonify({
            'success': False,
            'message': 'Invalid chart type'
        }), 400

# Initialize the admin blueprint with the necessary components
def init_admin(app):
    """Initialize admin blueprint with required components"""
    # Register the blueprint
    #app.register_blueprint(admin)
    
    # Add soft delete query methods to models if not already present
    from models.database import User, Company, Site, Tank
    
    if not hasattr(User, 'not_deleted'):
        @classmethod
        def user_not_deleted(cls):
            """Query filter for not deleted users."""
            return cls.query.filter_by(deleted_at=None)
        User.not_deleted = user_not_deleted

    # Ensure deleted_at columns exist
    with app.app_context():
        ensure_deleted_at_column()
    
    # Add soft delete methods to models
    add_soft_delete_methods()
    
    # Add the get_recent_alarms method to the Site class
    Site.get_recent_alarms = get_recent_alarms
    
    return admin

# Additional utility functions for the admin module

def get_tank_status_counts():
    """Get counts of tanks by status"""
    total_count = Tank.not_deleted().count()
    active_count = Tank.not_deleted().filter_by(is_active=True).count()
    inactive_count = total_count - active_count
    
    # Count connected tanks
    five_minutes_ago = dt.now() - timedelta(minutes=CONNECTION_TIMEOUT_MINUTES)
    connected_count = Tank.not_deleted().filter(Tank.last_connection >= five_minutes_ago).count()
    disconnected_count = total_count - connected_count
    
    # Count tanks by level status
    critical_count = 0
    low_count = 0
    normal_count = 0
    high_count = 0
    
    for tank in Tank.not_deleted().all():
        measurement = tank.get_latest_measurement()
        if measurement:
            if measurement.fill_percent <= tank.critical_level_threshold:
                critical_count += 1
            elif measurement.fill_percent <= tank.low_level_threshold:
                low_count += 1
            elif measurement.fill_percent >= tank.high_level_threshold:
                high_count += 1
            else:
                normal_count += 1
        else:
            # No measurement, count as normal
            normal_count += 1
    
    return {
        'total': total_count,
        'active': active_count,
        'inactive': inactive_count,
        'connected': connected_count,
        'disconnected': disconnected_count,
        'critical': critical_count,
        'low': low_count,
        'normal': normal_count,
        'high': high_count
    }

def get_alarm_counts():
    """Get counts of alarms by status and type"""
    total_count = Alarm.query.count()
    acknowledged_count = Alarm.query.filter_by(acknowledged=True).count()
    unacknowledged_count = total_count - acknowledged_count
    
    # Count alarms by type
    types = {}
    for alarm in Alarm.query.all():
        if alarm.type in types:
            types[alarm.type] += 1
        else:
            types[alarm.type] = 1
    
    # Count alarms by level
    info_count = Alarm.query.filter_by(level='info').count()
    warning_count = Alarm.query.filter_by(level='warning').count()
    danger_count = Alarm.query.filter_by(level='danger').count()
    
    return {
        'total': total_count,
        'acknowledged': acknowledged_count,
        'unacknowledged': unacknowledged_count,
        'types': types,
        'info': info_count,
        'warning': warning_count,
        'danger': danger_count
    }

@admin.route('/api/tank-status-counts')
@admin_required
def api_tank_status_counts():
    """API endpoint for tank status counts"""
    return jsonify({
        'success': True,
        'counts': get_tank_status_counts()
    })

@admin.route('/api/alarm-counts')
@admin_required
def api_alarm_counts():
    """API endpoint for alarm counts"""
    return jsonify({
        'success': True,
        'counts': get_alarm_counts()
    })

@admin.route('/api/recent-activities')
@admin_required
def api_recent_activities():
    """API endpoint for recent activities"""
    # This is a placeholder - in a real application, you would have an Activity model
    activities = [
        {
            'id': 1,
            'user': 'admin',
            'action': 'login',
            'timestamp': (dt.now() - timedelta(minutes=5)).isoformat(),
            'details': 'Admin logged in'
        },
        {
            'id': 2,
            'user': 'admin',
            'action': 'create',
            'timestamp': (dt.now() - timedelta(minutes=10)).isoformat(),
            'details': 'Created new tank "Tank 5"'
        },
        {
            'id': 3,
            'user': 'john',
            'action': 'update',
            'timestamp': (dt.now() - timedelta(minutes=15)).isoformat(),
            'details': 'Updated site "Site 2" details'
        },
        {
            'id': 4,
            'user': 'admin',
            'action': 'acknowledge',
            'timestamp': (dt.now() - timedelta(minutes=20)).isoformat(),
            'details': 'Acknowledged alarm for Tank 3'
        },
        {
            'id': 5,
            'user': 'sarah',
            'action': 'login',
            'timestamp': (dt.now() - timedelta(minutes=25)).isoformat(),
            'details': 'Sarah logged in'
        }
    ]
    
    return jsonify({
        'success': True,
        'activities': activities
    })

@admin.route('/api/system-health')
@admin_required
def api_system_health():
    """API endpoint for system health"""
    # This is a placeholder - in a real application, you would get actual system metrics
    health = {
        'cpu': {
            'usage': 25.5,  # percent
            'temperature': 45.2  # Celsius
        },
        'memory': {
            'total': 8192,  # MB
            'used': 3584,  # MB
            'free': 4608  # MB
        },
        'disk': {
            'total': 100,  # GB
            'used': 45,  # GB
            'free': 55  # GB
        },
        'network': {
            'up': 1.2,  # Mbps
            'down': 5.6  # Mbps
        },
        'database': {
            'connections': 5,
            'size': 256,  # MB
            'performance': 'good'
        },
        'services': {
            'web': 'running',
            'monitoring': 'running',
            'notification': 'running',
            'scheduler': 'running'
        }
    }
    
    return jsonify({
        'success': True,
        'health': health
    })

# Export functions for use in other modules
__all__ = [
    'admin',
    'admin_required',
    'init_admin',
    'get_tank_status_counts',
    'get_alarm_counts',
    'CONNECTION_TIMEOUT_MINUTES',
    'ITEMS_PER_PAGE'
]

# Additional routes for reporting functionality

@admin.route('/reports')
@admin_required
def reports():
    """Reports dashboard"""
    return render_template('admin/reports/index.html')

@admin.route('/reports/usage')
@admin_required
def usage_report():
    """Usage report"""
    # Get filter parameters
    start_date = request.args.get('start_date', (dt.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
    end_date = request.args.get('end_date', dt.now().strftime('%Y-%m-%d'))
    company_id = request.args.get('company_id', 'all')
    site_id = request.args.get('site_id', 'all')
    tank_id = request.args.get('tank_id', 'all')
    
    # Get companies for filter dropdown
    companies = Company.not_deleted().all()
    
    # Get sites for filter dropdown (filtered by company if selected)
    if company_id != 'all':
        sites = Site.not_deleted().filter_by(company_id=int(company_id)).all()
    else:
        sites = Site.not_deleted().all()
    
    # Get tanks for filter dropdown (filtered by site if selected)
    if site_id != 'all':
        tanks = Tank.not_deleted().filter_by(site_id=int(site_id)).all()
    else:
        tanks = Tank.not_deleted().all()
    
    return render_template('admin/reports/usage.html', 
                          start_date=start_date,
                          end_date=end_date,
                          company_id=company_id,
                          site_id=site_id,
                          tank_id=tank_id,
                          companies=companies,
                          sites=sites,
                          tanks=tanks)

@admin.route('/api/reports/usage')
@admin_required
def api_usage_report():
    """API endpoint for usage report data"""
    # Get filter parameters
    start_date_str = request.args.get('start_date', (dt.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
    end_date_str = request.args.get('end_date', dt.now().strftime('%Y-%m-%d'))
    company_id = request.args.get('company_id', 'all')
    site_id = request.args.get('site_id', 'all')
    tank_id = request.args.get('tank_id', 'all')
    
    # Parse dates
    try:
        start_date = dt.strptime(start_date_str, '%Y-%m-%d')
        end_date = dt.strptime(end_date_str, '%Y-%m-%d') + timedelta(days=1)  # Include end date
    except ValueError:
        return jsonify({
            'success': False,
            'message': 'Invalid date format. Use YYYY-MM-DD.'
        }), 400
    
    # Build query for tanks
    tank_query = Tank.not_deleted()
    
    if company_id != 'all':
        tank_query = tank_query.join(Site).filter(Site.company_id == int(company_id))
    
    if site_id != 'all':
        tank_query = tank_query.filter(Tank.site_id == int(site_id))
    
    if tank_id != 'all':
        tank_query = tank_query.filter(Tank.id == int(tank_id))
    
    # Get tanks
    tanks = tank_query.all()
    tank_ids = [tank.id for tank in tanks]
    
    # Initialize result data
    result = {
        'labels': [],
        'datasets': []
    }
    
    # Generate date labels
    current_date = start_date
    while current_date < end_date:
        result['labels'].append(current_date.strftime('%Y-%m-%d'))
        current_date += timedelta(days=1)
    
    # Generate dataset for each tank
    for tank in tanks:
        dataset = {
            'label': f"{tank.name} ({tank.site.name})",
            'data': []
        }
        
        # Get daily usage for each day
        current_date = start_date
        while current_date < end_date:
            next_date = current_date + timedelta(days=1)
            
            # Get first and last measurement for the day
            first_measurement = Measurement.query.filter(
                Measurement.tank_id == tank.id,
                Measurement.timestamp >= current_date,
                Measurement.timestamp < next_date
            ).order_by(Measurement.timestamp).first()
            
            last_measurement = Measurement.query.filter(
                Measurement.tank_id == tank.id,
                Measurement.timestamp >= current_date,
                Measurement.timestamp < next_date
            ).order_by(Measurement.timestamp.desc()).first()
            
            # Calculate daily usage
            if first_measurement and last_measurement:
                daily_usage = first_measurement.volume - last_measurement.volume
                if daily_usage < 0:  # If volume increased, count as 0 usage
                    daily_usage = 0
            else:
                daily_usage = 0
            
            dataset['data'].append(daily_usage)
            
            current_date = next_date
        
        result['datasets'].append(dataset)
    
    return jsonify({
        'success': True,
        'data': result
    })

@admin.route('/reports/alarms')
@admin_required
def alarm_report():
    """Alarm report"""
    # Get filter parameters
    start_date = request.args.get('start_date', (dt.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
    end_date = request.args.get('end_date', dt.now().strftime('%Y-%m-%d'))
    company_id = request.args.get('company_id', 'all')
    site_id = request.args.get('site_id', 'all')
    tank_id = request.args.get('tank_id', 'all')
    alarm_type = request.args.get('type', 'all')
    alarm_level = request.args.get('level', 'all')
    
    # Get companies for filter dropdown
    companies = Company.not_deleted().all()
    
    # Get sites for filter dropdown (filtered by company if selected)
    if company_id != 'all':
        sites = Site.not_deleted().filter_by(company_id=int(company_id)).all()
    else:
        sites = Site.not_deleted().all()
    
    # Get tanks for filter dropdown (filtered by site if selected)
    if site_id != 'all':
        tanks = Tank.not_deleted().filter_by(site_id=int(site_id)).all()
    else:
        tanks = Tank.not_deleted().all()
    
    # Get alarm types for filter dropdown
    alarm_types = db.session.query(Alarm.type).distinct().all()
    alarm_types = [t[0] for t in alarm_types]
    
    # Get alarm levels for filter dropdown
    alarm_levels = db.session.query(Alarm.level).distinct().all()
    alarm_levels = [l[0] for l in alarm_levels]
    
    return render_template('admin/reports/alarms.html', 
                          start_date=start_date,
                          end_date=end_date,
                          company_id=company_id,
                          site_id=site_id,
                          tank_id=tank_id,
                          alarm_type=alarm_type,
                          alarm_level=alarm_level,
                          companies=companies,
                          sites=sites,
                          tanks=tanks,
                          alarm_types=alarm_types,
                          alarm_levels=alarm_levels)

@admin.route('/api/reports/alarms')
@admin_required
def api_alarm_report():
    """API endpoint for alarm report data"""
    # Get filter parameters
    start_date_str = request.args.get('start_date', (dt.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
    end_date_str = request.args.get('end_date', dt.now().strftime('%Y-%m-%d'))
    company_id = request.args.get('company_id', 'all')
    site_id = request.args.get('site_id', 'all')
    tank_id = request.args.get('tank_id', 'all')
    alarm_type = request.args.get('type', 'all')
    alarm_level = request.args.get('level', 'all')
    
    # Parse dates
    try:
        start_date = dt.strptime(start_date_str, '%Y-%m-%d')
        end_date = dt.strptime(end_date_str, '%Y-%m-%d') + timedelta(days=1)  # Include end date
    except ValueError:
        return jsonify({
            'success': False,
            'message': 'Invalid date format. Use YYYY-MM-DD.'
        }), 400
    
    # Build query for alarms
    alarm_query = Alarm.query.filter(
        Alarm.timestamp >= start_date,
        Alarm.timestamp < end_date
    )
    
    # Filter by tank (and implicitly by site and company)
    if tank_id != 'all':
        alarm_query = alarm_query.filter(Alarm.tank_id == int(tank_id))
    elif site_id != 'all':
        # Get all tanks for this site
        tanks = Tank.not_deleted().filter_by(site_id=int(site_id)).all()
        tank_ids = [tank.id for tank in tanks]
        if tank_ids:
            alarm_query = alarm_query.filter(Alarm.tank_id.in_(tank_ids))
        else:
            # No tanks, so no alarms
            return jsonify({
                'success': True,
                'alarms': []
            })
    elif company_id != 'all':
        # Get all sites for this company
        sites = Site.not_deleted().filter_by(company_id=int(company_id)).all()
        site_ids = [site.id for site in sites]
        
        # Get all tanks for these sites
        tanks = Tank.not_deleted().filter(Tank.site_id.in_(site_ids)).all() if site_ids else []
        tank_ids = [tank.id for tank in tanks]
        
        if tank_ids:
            alarm_query = alarm_query.filter(Alarm.tank_id.in_(tank_ids))
        else:
            # No tanks, so no alarms
            return jsonify({
                'success': True,
                'alarms': []
            })
    
    # Filter by alarm type
    if alarm_type != 'all':
        alarm_query = alarm_query.filter(Alarm.type == alarm_type)
    
    # Filter by alarm level
    if alarm_level != 'all':
        alarm_query = alarm_query.filter(Alarm.level == alarm_level)
    
    # Get alarms
    alarms = alarm_query.order_by(Alarm.timestamp.desc()).all()
    
    # Prepare data for response
    alarm_data = []
    for alarm in alarms:
        tank = Tank.query.get(alarm.tank_id)
        site = Site.query.get(tank.site_id) if tank else None
        company = Company.query.get(site.company_id) if site else None
        
        alarm_data.append({
            'id': alarm.id,
            'timestamp': alarm.timestamp.isoformat(),
            'type': alarm.type,
            'level': alarm.level,
            'message': alarm.message,
            'value': alarm.value,
            'acknowledged': alarm.acknowledged,
            'acknowledged_by': alarm.acknowledged_by,
            'acknowledged_at': alarm.acknowledged_at.isoformat() if alarm.acknowledged_at else None,
            'tank_id': alarm.tank_id,
            'tank_name': tank.name if tank else 'Unknown',
            'site_id': site.id if site else None,
            'site_name': site.name if site else 'Unknown',
            'company_id': company.id if company else None,
            'company_name': company.name if company else 'Unknown'
        })
    
    return jsonify({
        'success': True,
        'alarms': alarm_data
    })

@admin.route('/reports/inventory')
@admin_required
def inventory_report():
    """Inventory report"""
    # Get filter parameters
    company_id = request.args.get('company_id', 'all')
    site_id = request.args.get('site_id', 'all')
    
    # Get companies for filter dropdown
    companies = Company.not_deleted().all()
    
    # Get sites for filter dropdown (filtered by company if selected)
    if company_id != 'all':
        sites = Site.not_deleted().filter_by(company_id=int(company_id)).all()
    else:
        sites = Site.not_deleted().all()
    
    return render_template('admin/reports/inventory.html', 
                          company_id=company_id,
                          site_id=site_id,
                          companies=companies,
                          sites=sites)

@admin.route('/api/reports/inventory')
@admin_required
def api_inventory_report():
    """API endpoint for inventory report data"""
    # Get filter parameters
    company_id = request.args.get('company_id', 'all')
    site_id = request.args.get('site_id', 'all')
    
    # Build query for tanks
    tank_query = Tank.not_deleted()
    
    if company_id != 'all':
        tank_query = tank_query.join(Site).filter(Site.company_id == int(company_id))
    
    if site_id != 'all':
        tank_query = tank_query.filter(Tank.site_id == int(site_id))
    
    # Get tanks
    tanks = tank_query.all()
    
    # Prepare data for response
    inventory_data = []
    for tank in tanks:
        measurement = tank.get_latest_measurement()
        
        inventory_data.append({
            'id': tank.id,
            'name': tank.name,
            'site_id': tank.site_id,
            'site_name': tank.site.name,
            'company_id': tank.site.company_id,
            'company_name': tank.site.company.name,
            'volume': measurement.volume if measurement else 0,
            'fill_percent': measurement.fill_percent if measurement else 0,
            'last_updated': measurement.timestamp.isoformat() if measurement else None,
            'status': tank.get_connection_status(),
            'low_level_threshold': tank.low_level_threshold,
            'critical_level_threshold': tank.critical_level_threshold,
            'high_level_threshold': tank.high_level_threshold
        })
    
    return jsonify({
        'success': True,
        'inventory': inventory_data
    })

@admin.route('/reports/export', methods=['GET', 'POST'])
@admin_required
def export_report():
    """Export data to CSV or Excel"""
    if request.method == 'POST':
        # Get export parameters
        export_type = request.form.get('export_type')
        data_type = request.form.get('data_type')
        file_format = request.form.get('file_format')
        
        # Get filter parameters
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        company_id = request.form.get('company_id')
        site_id = request.form.get('site_id')
        tank_id = request.form.get('tank_id')
        
        # This is a placeholder - in a real application, you would generate the export file
        # and return it for download
        
        flash('Export generated successfully', 'success')
        return redirect(url_for('admin.export_report'))
    
    # Get companies for filter dropdown
    companies = Company.not_deleted().all()
    
    # Get sites for filter dropdown
    sites = Site.not_deleted().all()
    
    # Get tanks for filter dropdown
    tanks = Tank.not_deleted().all()
    
    return render_template('admin/reports/export.html',
                          companies=companies,
                          sites=sites,
                          tanks=tanks)

# Routes for restoring soft-deleted records

@admin.route('/users/restore/<int:user_id>', methods=['POST'])
@admin_required
def restore_user(user_id):
    """Restore a soft-deleted user"""
    user = User.query.get_or_404(user_id)
    
    if user.deleted_at is None:
        flash('User is not deleted', 'warning')
        return redirect(url_for('admin.deleted_records', type='users'))
    
    user.restore()
    db.session.commit()
    
    flash('User restored successfully', 'success')
    return redirect(url_for('admin.deleted_records', type='users'))

@admin.route('/companies/restore/<int:company_id>', methods=['POST'])
@admin_required
def restore_company(company_id):
    """Restore a soft-deleted company"""
    company = Company.query.get_or_404(company_id)
    
    if company.deleted_at is None:
        flash('Company is not deleted', 'warning')
        return redirect(url_for('admin.deleted_records', type='companies'))
    
    company.restore()
    db.session.commit()
    
    flash('Company restored successfully', 'success')
    return redirect(url_for('admin.deleted_records', type='companies'))

@admin.route('/sites/restore/<int:site_id>', methods=['POST'])
@admin_required
def restore_site(site_id):
    """Restore a soft-deleted site"""
    site = Site.query.get_or_404(site_id)
    
    if site.deleted_at is None:
        flash('Site is not deleted', 'warning')
        return redirect(url_for('admin.deleted_records', type='sites'))
    
    site.restore()
    db.session.commit()
    
    flash('Site restored successfully', 'success')
    return redirect(url_for('admin.deleted_records', type='sites'))

@admin.route('/tanks/restore/<int:tank_id>', methods=['POST'])
@admin_required
def restore_tank(tank_id):
    """Restore a soft-deleted tank"""
    tank = Tank.query.get_or_404(tank_id)
    
    if tank.deleted_at is None:
        flash('Tank is not deleted', 'warning')
        return redirect(url_for('admin.deleted_records', type='tanks'))
    
    tank.restore()
    db.session.commit()
    
    flash('Tank restored successfully', 'success')
    return redirect(url_for('admin.deleted_records', type='tanks'))

# API routes for restoring soft-deleted records

@admin.route('/api/users/restore/<int:user_id>', methods=['POST'])
@admin_required
def api_restore_user(user_id):
    """API endpoint to restore a soft-deleted user"""
    user = User.query.get_or_404(user_id)
    
    if user.deleted_at is None:
        return jsonify({
            'success': False,
            'message': 'User is not deleted'
        })
    
    user.restore()
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'User restored successfully'
    })

@admin.route('/api/companies/restore/<int:company_id>', methods=['POST'])
@admin_required
def api_restore_company(company_id):
    """API endpoint to restore a soft-deleted company"""
    company = Company.query.get_or_404(company_id)
    
    if company.deleted_at is None:
        return jsonify({
            'success': False,
            'message': 'Company is not deleted'
        })
    
    company.restore()
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Company restored successfully'
    })

@admin.route('/api/sites/restore/<int:site_id>', methods=['POST'])
@admin_required
def api_restore_site(site_id):
    """API endpoint to restore a soft-deleted site"""
    site = Site.query.get_or_404(site_id)
    
    if site.deleted_at is None:
        return jsonify({
            'success': False,
            'message': 'Site is not deleted'
        })
    
    site.restore()
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Site restored successfully'
    })

@admin.route('/api/tanks/restore/<int:tank_id>', methods=['POST'])
@admin_required
def api_restore_tank(tank_id):
    """API endpoint to restore a soft-deleted tank"""
    tank = Tank.query.get_or_404(tank_id)
    
    if tank.deleted_at is None:
        return jsonify({
            'success': False,
            'message': 'Tank is not deleted'
        })
    
    tank.restore()
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Tank restored successfully'
    })

# Routes for permanently deleting soft-deleted records

@admin.route('/users/permanent-delete/<int:user_id>', methods=['POST'])
@admin_required
def permanent_delete_user(user_id):
    """Permanently delete a soft-deleted user"""
    user = User.query.get_or_404(user_id)
    
    if user.deleted_at is None:
        flash('Cannot permanently delete an active user', 'danger')
        return redirect(url_for('admin.deleted_records', type='users'))
    
    db.session.delete(user)
    db.session.commit()
    
    flash('User permanently deleted', 'success')
    return redirect(url_for('admin.deleted_records', type='users'))

@admin.route('/companies/permanent-delete/<int:company_id>', methods=['POST'])
@admin_required
def permanent_delete_company(company_id):
    """Permanently delete a soft-deleted company"""
    company = Company.query.get_or_404(company_id)
    
    if company.deleted_at is None:
        flash('Cannot permanently delete an active company', 'danger')
        return redirect(url_for('admin.deleted_records', type='companies'))
    
    # Check if company has sites
    sites = Site.query.filter_by(company_id=company_id).all()
    if sites:
        flash('Cannot permanently delete a company with sites', 'danger')
        return redirect(url_for('admin.deleted_records', type='companies'))
    
    db.session.delete(company)
    db.session.commit()
    
    flash('Company permanently deleted', 'success')
    return redirect(url_for('admin.deleted_records', type='companies'))

@admin.route('/sites/permanent-delete/<int:site_id>', methods=['POST'])
@admin_required
def permanent_delete_site(site_id):
    """Permanently delete a soft-deleted site"""
    site = Site.query.get_or_404(site_id)
    
    if site.deleted_at is None:
        flash('Cannot permanently delete an active site', 'danger')
        return redirect(url_for('admin.deleted_records', type='sites'))
    
    # Check if site has tanks
    tanks = Tank.query.filter_by(site_id=site_id).all()
    if tanks:
        flash('Cannot permanently delete a site with tanks', 'danger')
        return redirect(url_for('admin.deleted_records', type='sites'))
    
    db.session.delete(site)
    db.session.commit()
    
    flash('Site permanently deleted', 'success')
    return redirect(url_for('admin.deleted_records', type='sites'))

@admin.route('/tanks/permanent-delete/<int:tank_id>', methods=['POST'])
@admin_required
def permanent_delete_tank(tank_id):
    """Permanently delete a soft-deleted tank"""
    tank = Tank.query.get_or_404(tank_id)
    
    if tank.deleted_at is None:
        flash('Cannot permanently delete an active tank', 'danger')
        return redirect(url_for('admin.deleted_records', type='tanks'))
    
    # Delete tank's measurements and alarms
    Measurement.query.filter_by(tank_id=tank_id).delete()
    Alarm.query.filter_by(tank_id=tank_id).delete()
    
    db.session.delete(tank)
    db.session.commit()
    
    flash('Tank permanently deleted', 'success')
    return redirect(url_for('admin.deleted_records', type='tanks'))

# API routes for permanently deleting soft-deleted records

@admin.route('/api/users/permanent-delete/<int:user_id>', methods=['POST'])
@admin_required
def api_permanent_delete_user(user_id):
    """API endpoint to permanently delete a soft-deleted user"""
    user = User.query.get_or_404(user_id)
    
    if user.deleted_at is None:
        return jsonify({
            'success': False,
            'message': 'Cannot permanently delete an active user'
        })
    
    db.session.delete(user)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'User permanently deleted'
    })

@admin.route('/api/companies/permanent-delete/<int:company_id>', methods=['POST'])
@admin_required
def api_permanent_delete_company(company_id):
    """API endpoint to permanently delete a soft-deleted company"""
    company = Company.query.get_or_404(company_id)
    
    if company.deleted_at is None:
        return jsonify({
            'success': False,
            'message': 'Cannot permanently delete an active company'
        })
    
    # Check if company has sites
    sites = Site.query.filter_by(company_id=company_id).all()
    if sites:
        return jsonify({
            'success': False,
            'message': 'Cannot permanently delete a company with sites'
        })
    
    db.session.delete(company)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Company permanently deleted'
    })

@admin.route('/api/sites/permanent-delete/<int:site_id>', methods=['POST'])
@admin_required
def api_permanent_delete_site(site_id):
    """API endpoint to permanently delete a soft-deleted site"""
    site = Site.query.get_or_404(site_id)
    
    if site.deleted_at is None:
        return jsonify({
            'success': False,
            'message': 'Cannot permanently delete an active site'
        })
    
    # Check if site has tanks
    tanks = Tank.query.filter_by(site_id=site_id).all()
    if tanks:
        return jsonify({
            'success': False,
            'message': 'Cannot permanently delete a site with tanks'
        })
    
    db.session.delete(site)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Site permanently deleted'
    })

@admin.route('/api/tanks/permanent-delete/<int:tank_id>', methods=['POST'])
@admin_required
def api_permanent_delete_tank(tank_id):
    """API endpoint to permanently delete a soft-deleted tank"""
    tank = Tank.query.get_or_404(tank_id)
    
    if tank.deleted_at is None:
        return jsonify({
            'success': False,
            'message': 'Cannot permanently delete an active tank'
        })
    
    # Delete tank's measurements and alarms
    Measurement.query.filter_by(tank_id=tank_id).delete()
    Alarm.query.filter_by(tank_id=tank_id).delete()
    
    db.session.delete(tank)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Tank permanently deleted'
    })

# Bulk operations

@admin.route('/users/bulk-action', methods=['POST'])
@admin_required
def bulk_action_users():
    """Perform bulk action on users"""
    action = request.form.get('action')
    user_ids = request.form.getlist('user_ids')
    
    if not user_ids:
        flash('No users selected', 'warning')
        return redirect(url_for('admin.users'))
    
    if action == 'delete':
        # Soft delete users
        for user_id in user_ids:
            user = User.query.get(user_id)
            if user and user.id != current_user.id:  # Prevent deleting self
                user.soft_delete()
        
        db.session.commit()
        flash(f'{len(user_ids)} users deleted', 'success')
    
    elif action == 'activate':
        # Activate users
        for user_id in user_ids:
            user = User.query.get(user_id)
            if user:
                user.is_active = True
        
        db.session.commit()
        flash(f'{len(user_ids)} users activated', 'success')
    
    elif action == 'deactivate':
        # Deactivate users
        for user_id in user_ids:
            user = User.query.get(user_id)
            if user and user.id != current_user.id:  # Prevent deactivating self
                user.is_active = False
        
        db.session.commit()
        flash(f'{len(user_ids)} users deactivated', 'success')
    
    return redirect(url_for('admin.users'))

@admin.route('/companies/bulk-action', methods=['POST'])
@admin_required
def bulk_action_companies():
    """Perform bulk action on companies"""
    action = request.form.get('action')
    company_ids = request.form.getlist('company_ids')
    
    if not company_ids:
        flash('No companies selected', 'warning')
        return redirect(url_for('admin.companies'))
    
    if action == 'delete':
        # Soft delete companies
        for company_id in company_ids:
            company = Company.query.get(company_id)
            if company:
                company.soft_delete()
        
        db.session.commit()
        flash(f'{len(company_ids)} companies deleted', 'success')
    
    return redirect(url_for('admin.companies'))

@admin.route('/sites/bulk-action', methods=['POST'])
@admin_required
def bulk_action_sites():
    """Perform bulk action on sites"""
    action = request.form.get('action')
    site_ids = request.form.getlist('site_ids')
    
    if not site_ids:
        flash('No sites selected', 'warning')
        return redirect(url_for('admin.sites'))
    
    if action == 'delete':
        # Soft delete sites
        for site_id in site_ids:
            site = Site.query.get(site_id)
            if site:
                site.soft_delete()
        
        db.session.commit()
        flash(f'{len(site_ids)} sites deleted', 'success')
    
    elif action == 'activate':
        # Activate sites
        for site_id in site_ids:
            site = Site.query.get(site_id)
            if site:
                site.is_active = True
        
        db.session.commit()
        flash(f'{len(site_ids)} sites activated', 'success')
    
    elif action == 'deactivate':
        # Deactivate sites
        for site_id in site_ids:
            site = Site.query.get(site_id)
            if site:
                site.is_active = False
        
        db.session.commit()
        flash(f'{len(site_ids)} sites deactivated', 'success')
    
    return redirect(url_for('admin.sites'))

@admin.route('/tanks/bulk-action', methods=['POST'])
@admin_required
def bulk_action_tanks():
    """Perform bulk action on tanks"""
    action = request.form.get('action')
    tank_ids = request.form.getlist('tank_ids')
    
    if not tank_ids:
        flash('No tanks selected', 'warning')
        return redirect(url_for('admin.tanks_index'))
    
    if action == 'delete':
        # Soft delete tanks
        for tank_id in tank_ids:
            tank = Tank.query.get(tank_id)
            if tank:
                # Stop monitoring if active
                try:
                    from app import tank_monitor_manager as monitor_manager
                    monitor_manager.stop_monitoring(tank_id)
                except (ImportError, AttributeError):
                    pass
                
                tank.soft_delete()
        
        db.session.commit()
        flash(f'{len(tank_ids)} tanks deleted', 'success')
    
    elif action == 'activate':
        # Activate tanks
        for tank_id in tank_ids:
            tank = Tank.query.get(tank_id)
            if tank:
                tank.is_active = True
                
                # Start monitoring
                try:
                    from app import tank_monitor_manager as monitor_manager
                    monitor_manager.start_monitoring(tank_id)
                except (ImportError, AttributeError):
                    pass
        
        db.session.commit()
        flash(f'{len(tank_ids)} tanks activated', 'success')
    
    elif action == 'deactivate':
        # Deactivate tanks
        for tank_id in tank_ids:
            tank = Tank.query.get(tank_id)
            if tank:
                tank.is_active = False
                
                # Stop monitoring
                try:
                    from app import tank_monitor_manager as monitor_manager
                    monitor_manager.stop_monitoring(tank_id)
                except (ImportError, AttributeError):
                    pass
        
        db.session.commit()
        flash(f'{len(tank_ids)} tanks deactivated', 'success')
    
    return redirect(url_for('admin.tanks_index'))

# Final initialization
if __name__ == '__main__':
    print("This module is not meant to be run directly.")