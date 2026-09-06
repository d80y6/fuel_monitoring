"""
Authentication Blueprint for the Fuel Tank Monitoring System

This module provides authentication functionality including login, logout,
and password management.
"""
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models.database import db
from flask_wtf import FlaskForm
from models.database import User

from wtforms import StringField, PasswordField, BooleanField, SubmitField, EmailField
from wtforms.validators import DataRequired, EqualTo, Length, Email, ValidationError

class EditProfileForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    email = EmailField('Email', validators=[DataRequired(), Email()])
    phone = StringField('Phone Number', validators=[])  # Added phone field
    submit = SubmitField('Update Profile')
    
    def __init__(self, original_email=None, original_username=None, *args, **kwargs):
        super(EditProfileForm, self).__init__(*args, **kwargs)
        self.original_email = original_email
        self.original_username = original_username
        
    def validate_email(self, email):
        if email.data != self.original_email:
            user = User.query.filter_by(email=email.data).first()
            if user:
                raise ValidationError('Email already exists.')
                
    def validate_username(self, username):
        if username.data != self.original_username:
            user = User.query.filter_by(username=username.data).first()
            if user:
                raise ValidationError('Username already exists.')
class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Login')

# Create blueprint
auth = Blueprint('auth', __name__)

# Initialize login manager
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message_category = 'info'



# Add this class near your other form classes
class ChangePasswordForm(FlaskForm):
    current_password = PasswordField('Current Password', validators=[DataRequired()])
    new_password = PasswordField('New Password', validators=[
        DataRequired(),
        Length(min=8, message='Password must be at least 8 characters long')
    ])
    confirm_password = PasswordField('Confirm New Password', validators=[
        DataRequired(),
        EqualTo('new_password', message='Passwords must match')
    ])
    submit = SubmitField('Change Password')


@auth.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Change user password"""
    form = ChangePasswordForm()
    
    if form.validate_on_submit():
        if not current_user.check_password(form.current_password.data):
            flash('Current password is incorrect', 'danger')
            return redirect(url_for('auth.change_password'))
        
        current_user.set_password(form.new_password.data)
        db.session.commit()
        flash('Your password has been updated successfully', 'success')
        return redirect(url_for('auth.profile'))
    
    return render_template('auth/change_password.html', form=form)


@login_manager.user_loader
def load_user(user_id):
    """Load user by ID"""
    return User.query.get(int(user_id))

@auth.route('/login', methods=['GET', 'POST'])
def login():
    """User login"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = 'remember' in request.form
        form = LoginForm()
        if form.validate_on_submit():
            username = form.username.data
            password = form.password.data
            remember = form.remember_me.data
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user, remember=remember)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        else:
            flash('Invalid username or password', 'danger')
    
    return render_template('auth/login.html', form=LoginForm()) 

@auth.route('/reset_password_request', methods=['GET', 'POST'])
def reset_password_request():
    """Handle password reset requests"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    class ResetPasswordRequestForm(FlaskForm):
        email = StringField('Email', validators=[DataRequired()])
        submit = SubmitField('Request Password Reset')
    
    form = ResetPasswordRequestForm()
    
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            # Here you would generate a token and send reset email
            # For example: send_password_reset_email(user)
            flash('Check your email for instructions to reset your password', 'info')
            return redirect(url_for('auth.login'))
        else:
            flash('Email not found in our records', 'danger')
    
    return render_template('auth/reset_password_request.html', form=form)

@auth.route('/logout')
@login_required
def logout():
    """User logout"""
    logout_user()
    flash('You have been logged out', 'info')
    return redirect(url_for('index'))

@auth.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """User profile view"""
    return render_template('auth/profile.html')

@auth.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    """Edit user profile information"""
    form = EditProfileForm(original_email=current_user.email, original_username=current_user.username)
    
    if request.method == 'GET':
        # Pre-populate form with current user data
        form.username.data = current_user.username
        form.email.data = current_user.email
        # Check if phone attribute exists before trying to access it
        if hasattr(current_user, 'phone'):
            form.phone.data = current_user.phone
    
    if form.validate_on_submit():
        current_user.username = form.username.data
        current_user.email = form.email.data
        
        # Update phone if the field exists in the User model
        if hasattr(current_user, 'phone'):
            current_user.phone = form.phone.data
        
        db.session.commit()
        flash('Profile updated successfully', 'success')
        return redirect(url_for('auth.profile'))
    
    return render_template('auth/edit_profile.html', form=form)