"""
User management views for the admin blueprint
"""
from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length, Email, ValidationError, Regexp
from flask_wtf import FlaskForm
import re
from . import admin, PASSWORD_PATTERN
from .auth import admin_required, permission_required, Permissions
from .utils import handle_db_errors, log_activity
from models.database import db, User, Company, Site, ActivityLog
from . import ITEMS_PER_PAGE

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

@admin.route('/users')
@admin_required
def users():
    """User list with pagination and search"""
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
    """API endpoint for user list with optimized query and proper validation"""
    # Parameter validation
    try:
        page = max(1, request.args.get('page', 1, type=int))
        search = request.args.get('search', '', type=str)
        role = request.args.get('role', 'all', type=str)
        status = request.args.get('status', 'all', type=str)
        per_page = min(50, request.args.get('per_page', ITEMS_PER_PAGE, type=int))
    except (ValueError, TypeError) as e:
        return jsonify({
            'success': False,
            'message': f'Invalid parameter: {str(e)}'
        }), 400

    # Build query with efficient filtering
    query = User.not_deleted()

    # Apply search filter - optimize by using lower() only once
    if search:
        search_lower = search.lower()
        query = query.filter(
            db.or_(
                db.func.lower(User.username).contains(search_lower),
                db.func.lower(User.email).contains(search_lower),
                db.func.lower(User.first_name).contains(search_lower),
                db.func.lower(User.last_name).contains(search_lower)
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

    # Get total count before pagination for performance
    total_count = query.count()
    
    # Paginate the results
    users = query.offset((page - 1) * per_page).limit(per_page).all()

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
        'total': total_count,
        'page': page,
        'pages': (total_count + per_page - 1) // per_page  # Ceiling division
    })

@admin.route('/users/create', methods=['GET', 'POST'])
@admin_required
@handle_db_errors
def new_user():
    """Create new user with enhanced validation and input sanitization"""
    companies = Company.not_deleted().all()
    sites = Site.not_deleted().all()
    
    form = CreateUserForm()
    
    if form.validate_on_submit():
        # Extract form data
        username = form.username.data.strip()
        email = form.email.data.strip().lower()  # Normalize email
        password = form.password.data
        first_name = form.first_name.data.strip()
        last_name = form.last_name.data.strip()
        role = form.role.data
        is_active = True  # Default to active
        
        # Check if username or email already exists
        if User.query.filter(db.func.lower(User.username) == username.lower()).first():
            flash('Username already exists', 'danger')
            return render_template('admin/user_form.html', form=form, user=None, companies=companies, sites=sites)
        
        if User.query.filter(db.func.lower(User.email) == email.lower()).first():
            flash('Email already exists', 'danger')
            return render_template('admin/user_form.html', form=form, user=None, companies=companies, sites=sites)
        
        # Create new user
        user = User(
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name,
            role=role,
            is_active=is_active
        )
        
        # Set password with validation
        try:
            if not re.match(PASSWORD_PATTERN, password):
                raise ValueError("Password must be at least 8 characters and contain uppercase, lowercase, and digits")
            user.set_password(password)
        except ValueError as e:
            flash(str(e), 'danger')
            return render_template('admin/user_form.html', form=form, user=None, companies=companies, sites=sites)
        
        db.session.add(user)
        
        # Get selected companies and sites (safely)
        company_ids = request.form.getlist('companies')
        site_ids = request.form.getlist('sites')
        
        # Convert IDs to integers safely
        try:
            company_ids = [int(id) for id in company_ids if id.isdigit()]
            site_ids = [int(id) for id in site_ids if id.isdigit()]
        except ValueError:
            flash('Invalid company or site IDs', 'danger')
            return render_template('admin/user_form.html', form=form, user=None, companies=companies, sites=sites)
        
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
    
    return render_template('admin/user_form.html', form=form, user=None, companies=companies, sites=sites)

# Add other user management routes...