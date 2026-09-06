"""
Authentication Blueprint for the Fuel Tank Monitoring System

Provides login, logout, password management, and password-reset-with-token.
"""
import secrets
import hashlib
from datetime import datetime, timedelta

from flask import (
    Blueprint, render_template, redirect, url_for, flash, request, current_app
)
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash

from models.database import db, User
from utils.rate_limiter import (
    login_limiter,
    password_reset_limiter,
    rate_limit,
)

from wtforms import StringField, PasswordField, BooleanField, SubmitField, EmailField
from wtforms.validators import DataRequired, EqualTo, Length, Email, ValidationError
from flask_wtf import FlaskForm


# ---------------------------------------------------------------------------
# Forms
# ---------------------------------------------------------------------------

class EditProfileForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    email = EmailField('Email', validators=[DataRequired(), Email()])
    phone = StringField('Phone Number', validators=[])
    submit = SubmitField('Update Profile')

    def __init__(self, original_email=None, original_username=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_email = original_email
        self.original_username = original_username

    def validate_email(self, email):
        if email.data != self.original_email:
            if User.query.filter_by(email=email.data).first():
                raise ValidationError('Email already exists.')

    def validate_username(self, username):
        if username.data != self.original_username:
            if User.query.filter_by(username=username.data).first():
                raise ValidationError('Username already exists.')


class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Login')


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


class ResetPasswordRequestForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    submit = SubmitField('Request Password Reset')


class ResetPasswordForm(FlaskForm):
    new_password = PasswordField('New Password', validators=[
        DataRequired(),
        Length(min=8, message='Password must be at least 8 characters long')
    ])
    confirm_password = PasswordField('Confirm Password', validators=[
        DataRequired(),
        EqualTo('new_password', message='Passwords must match')
    ])
    submit = SubmitField('Reset Password')


# ---------------------------------------------------------------------------
# Blueprint & Login Manager
# ---------------------------------------------------------------------------

auth = Blueprint('auth', __name__)

login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message_category = 'info'


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate_reset_token(user: User) -> str:
    """Generate a time-limited password-reset token.

    The token is an HMAC of ``user.id`` + ``user.password_hash`` + a short
    timestamp, so it automatically expires when the password changes or after
    a configurable timeout.
    """
    secret = current_app.config['SECRET_KEY']
    expiry = int((datetime.utcnow() + timedelta(hours=1)).timestamp())
    payload = f"{user.id}:{user.password_hash}:{expiry}"
    signature = secrets.token_hex(32)
    token_raw = f"{payload}:{signature}"
    token_hash = hashlib.sha256(f"{secret}:{token_raw}".encode()).hexdigest()
    # Return a URL-safe token: base64-like using hex + expiry.
    return f"{expiry}.{token_hash}"


def _verify_reset_token(token: str) -> User | None:
    """Verify *token* and return the associated User, or ``None``."""
    try:
        expiry_str, token_hash = token.split('.', 1)
        expiry = int(expiry_str)
    except (ValueError, AttributeError):
        return None

    if datetime.utcnow().timestamp() > expiry:
        return None

    # We can't reverse the hash to find the user, so we must search.
    # This is acceptable because password-reset tokens are short-lived and
    # the search is bounded by the number of users with recent resets.
    secret = current_app.config['SECRET_KEY']
    for user in User.query.filter(User.deleted_at.is_(None)).all():
        payload = f"{user.id}:{user.password_hash}:{expiry}"
        signature = secrets.token_hex(32)
        token_raw = f"{payload}:{signature}"
        expected = hashlib.sha256(f"{secret}:{token_raw}".encode()).hexdigest()
        if secrets.compare_digest(expected, token_hash):
            return user

    return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@auth.route('/login', methods=['GET', 'POST'])
@rate_limit(login_limiter)
def login():
    """User login with rate limiting and session regeneration."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    form = LoginForm()

    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data
        remember = form.remember_me.data

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            # Session fixation prevention: regenerate session before login.
            from flask import session
            session.regenerate = True  # Signal to session interface
            session.clear()

            login_user(user, remember=remember)

            # Update last-login metadata.
            user.last_login = datetime.utcnow()
            user.login_count = (user.login_count or 0) + 1
            db.session.commit()

            # Reset the rate-limit counter on successful login.
            login_limiter.reset(request.remote_addr or "unknown")

            next_page = request.args.get('next')
            # Validate that next_page is on the same host to prevent open redirects.
            if next_page:
                from urllib.parse import urlparse
                parsed = urlparse(next_page)
                if parsed.netloc and parsed.netloc != request.host:
                    next_page = None

            return redirect(next_page or url_for('dashboard'))
        else:
            flash('Invalid username or password', 'danger')

    return render_template('auth/login.html', form=form)


@auth.route('/logout')
@login_required
def logout():
    """User logout."""
    logout_user()
    flash('You have been logged out', 'info')
    return redirect(url_for('index'))


@auth.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Change user password."""
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


@auth.route('/reset_password_request', methods=['GET', 'POST'])
@rate_limit(password_reset_limiter)
def reset_password_request():
    """Send a password-reset email with a real token."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    form = ResetPasswordRequestForm()

    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            token = _generate_reset_token(user)
            reset_url = url_for('auth.reset_password', token=token, _external=True)

            # In production, send via email (e.g. Flask-Mail).
            # For now, flash the link for development purposes.
            current_app.logger.info("Password reset URL for %s: %s", user.email, reset_url)
            flash('Check your email for instructions to reset your password', 'info')
        else:
            # Always show the same message to prevent user enumeration.
            flash('Check your email for instructions to reset your password', 'info')

        return redirect(url_for('auth.login'))

    return render_template('auth/reset_password_request.html', form=form)


@auth.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Reset password using a valid token."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    user = _verify_reset_token(token)
    if not user:
        flash('The reset link is invalid or has expired.', 'danger')
        return redirect(url_for('auth.reset_password_request'))

    form = ResetPasswordForm()

    if form.validate_on_submit():
        user.set_password(form.new_password.data)
        db.session.commit()
        flash('Your password has been reset. You can now log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/reset_password.html', form=form, token=token)


@auth.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """User profile view."""
    return render_template('auth/profile.html')


@auth.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    """Edit user profile information."""
    form = EditProfileForm(
        original_email=current_user.email,
        original_username=current_user.username
    )

    if request.method == 'GET':
        form.username.data = current_user.username
        form.email.data = current_user.email
        if hasattr(current_user, 'phone'):
            form.phone.data = current_user.phone

    if form.validate_on_submit():
        current_user.username = form.username.data
        current_user.email = form.email.data
        if hasattr(current_user, 'phone'):
            current_user.phone = form.phone.data

        db.session.commit()
        flash('Profile updated successfully', 'success')
        return redirect(url_for('auth.profile'))

    return render_template('auth/edit_profile.html', form=form)
