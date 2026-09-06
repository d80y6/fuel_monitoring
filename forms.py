from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, SelectField, FloatField, TextAreaField
from wtforms import IntegerField, DecimalField, FileField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError, Optional, NumberRange
from models.database import User

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Sign In')

class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=4, max=64)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    first_name = StringField('First Name', validators=[DataRequired(), Length(max=64)])
    last_name = StringField('Last Name', validators=[DataRequired(), Length(max=64)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=8)])
    password2 = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    company = SelectField('Company', coerce=int, validators=[Optional()])
    submit = SubmitField('Register')
    
    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user is not None:
            raise ValidationError('Username already taken. Please use a different username.')
    
    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user is not None:
            raise ValidationError('Email already registered. Please use a different email address.')

class PasswordResetForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    submit = SubmitField('Request Password Reset')

class CompanyForm(FlaskForm):
    name = StringField('Company Name', validators=[DataRequired(), Length(max=100)])
    address = StringField('Address', validators=[Length(max=200)])
    city = StringField('City', validators=[Length(max=100)])
    state = StringField('State/Province', validators=[Length(max=100)])
    country = StringField('Country', validators=[Length(max=100)])
    postal_code = StringField('Postal Code', validators=[Length(max=20)])
    phone = StringField('Phone', validators=[Length(max=20)])
    email = StringField('Email', validators=[Email(), Length(max=120)])
    website = StringField('Website', validators=[Length(max=200)])
    logo = FileField('Company Logo')
    submit = SubmitField('Save Company')

class SiteForm(FlaskForm):
    name = StringField('Site Name', validators=[DataRequired(), Length(max=100)])
    address = StringField('Address', validators=[Length(max=200)])
    city = StringField('City', validators=[Length(max=100)])
    state = StringField('State/Province', validators=[Length(max=100)])
    country = StringField('Country', validators=[Length(max=100)])
    postal_code = StringField('Postal Code', validators=[Length(max=20)])
    latitude = FloatField('Latitude', validators=[Optional(), NumberRange(min=-90, max=90)])
    longitude = FloatField('Longitude', validators=[Optional(), NumberRange(min=-180, max=180)])
    timezone = SelectField('Timezone', validators=[DataRequired()])
    company = SelectField('Company', coerce=int, validators=[DataRequired()])
    submit = SubmitField('Save Site')

class TankForm(FlaskForm):
    name = StringField('Tank Name', validators=[DataRequired(), Length(max=100)])
    description = TextAreaField('Description', validators=[Length(max=200)])
    fluid_type = SelectField('Fluid Type', choices=[
        ('diesel', 'Diesel'),
        ('gasoline', 'Gasoline'),
        ('kerosene', 'Kerosene'),
        ('oil', 'Oil'),
        ('water', 'Water'),
        ('other', 'Other')
    ])
    fluid_density = FloatField('Fluid Density (kg/m³)', validators=[DataRequired(), NumberRange(min=0)])
    tank_orientation = SelectField('Tank Orientation', choices=[
        ('vertical', 'Vertical'),
        ('horizontal', 'Horizontal')
    ])
    tank_height = FloatField('Tank Height/Length (m)', validators=[DataRequired(), NumberRange(min=0)])
    tank_diameter = FloatField('Tank Diameter (m)', validators=[DataRequired(), NumberRange(min=0)])
    atmospheric_pressure = FloatField('Atmospheric Pressure (bar)', validators=[NumberRange(min=0)])
    calibration_factor = FloatField('Calibration Factor', validators=[NumberRange(min=0.1, max=10)])
    
    # Connection settings
    pressure_channel = IntegerField('Pressure Channel', validators=[DataRequired(), NumberRange(min=1)])
    temp_channel = IntegerField('Temperature Channel', validators=[DataRequired(), NumberRange(min=1)])
    update_interval = FloatField('Update Interval (s)', validators=[DataRequired(), NumberRange(min=0.1)])
    
    site = SelectField('Site', coerce=int, validators=[DataRequired()])
    submit = SubmitField('Save Tank')

class AlarmSettingsForm(FlaskForm):
    low_level_threshold = FloatField('Low Level Threshold (%)', validators=[DataRequired(), NumberRange(min=0, max=100)])
    high_level_threshold = FloatField('High Level Threshold (%)', validators=[DataRequired(), NumberRange(min=0, max=100)])
    leak_detection_threshold = FloatField('Leak Detection Threshold (L/hour)', validators=[DataRequired(), NumberRange(min=0)])
    enable_email_notifications = BooleanField('Enable Email Notifications')
    enable_sms_notifications = BooleanField('Enable SMS Notifications')
    notification_recipients = TextAreaField('Notification Recipients (comma-separated)', validators=[Length(max=500)])
    submit = SubmitField('Save Alarm Settings')

class UserForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=4, max=64)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    first_name = StringField('First Name', validators=[DataRequired(), Length(max=64)])
    last_name = StringField('Last Name', validators=[DataRequired(), Length(max=64)])
    role = SelectField('Role', choices=[
        ('admin', 'Administrator'),
        ('company_admin', 'Company Manager'),
        ('user', 'User')
    ])
    is_active = BooleanField('Active')
    password = PasswordField('New Password', validators=[Optional(), Length(min=8)])
    password2 = PasswordField('Confirm New Password', validators=[EqualTo('password')])
    companies = SelectField('Companies', coerce=int, validators=[Optional()])
    sites = SelectField('Sites', coerce=int, validators=[Optional()])
    submit = SubmitField('Save User')
