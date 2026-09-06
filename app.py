"""
Fuel Tank Monitoring Web Application

This is the main application file for the web-based fuel tank monitoring system.
It provides a Flask web interface to monitor fuel levels, volume, and flow rates
using Keller pressure sensors connected via K114 converters.
"""
import os
import sys
import csv
import io
import json
import logging
import time
from threading import Thread
from flask import Flask, render_template, jsonify, request, redirect, url_for, flash, Response, send_from_directory
from flask_login import LoginManager, login_required, current_user
from config import Config
from models.database import db, User, Company, Site, Tank, Measurement, Alarm, create_timescale_extensions, setup_timescale_retention
from models.tank_monitor_manager import TankMonitorManager
from auth import auth, login_manager
from admin import admin, init_admin
from datetime import datetime, timedelta
from sqlalchemy import func, and_
from flask_migrate import Migrate
from sqlalchemy.orm import Session

import custom_translations
from custom_translations import gettext as _

# Configure logging
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize Flask application
app = Flask(__name__)
app.config.from_object(Config)
# Initialize Babel for internationalization
custom_translations.init_app(app)
# Development settings - disable caching
if app.config.get('DEBUG', False):
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.jinja_env.auto_reload = True
    
    @app.after_request
    def add_header(response):
        """Add headers to disable caching."""
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '-1'
        return response
    
    @app.context_processor
    def inject_cache_busting():
        """Add cache busting parameter to static file URLs."""
        return {'cache_buster': int(time.time())}

@app.template_filter('timeago')
def timeago_filter(timestamp):
    """Format a timestamp as a 'time ago' string (e.g., "3 hours ago")."""
    now = datetime.now()
    if isinstance(timestamp, str):
        try:
            timestamp = datetime.fromisoformat(timestamp)
        except ValueError:
            return timestamp
    
    diff = now - timestamp
    seconds = diff.total_seconds()
    
    if seconds < 60:

        return _("Just now")
    elif seconds < 3600:
        minutes = int(seconds / 60)

        return _("%(minutes)d minute%(plural)s ago", minutes=minutes, 
                plural='s' if minutes > 1 else '')
    elif seconds < 86400:
        hours = int(seconds / 3600)

        return _("%(hours)d hour%(plural)s ago", hours=hours, 
                plural='s' if hours > 1 else '')
    elif seconds < 604800:
        days = int(seconds / 86400)

        return _("%(days)d day%(plural)s ago", days=days, 
                plural='s' if days > 1 else '')
    else:
        return timestamp.strftime('%Y-%m-%d %H:%M')

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://fuel_tank_user:1980@localhost/fuel_tank_monitoring'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions
db.init_app(app)
migrate = Migrate(app, db)
# Initialize Socket.IO with namespaces


class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles datetime objects."""
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)



login_manager.init_app(app)

# Create tank monitor manager
tank_monitor_manager = TankMonitorManager(app)

# Register cleanup function to be called when the application shuts down
@app.teardown_appcontext
def cleanup_monitors(exception=None):
    """Clean up tank monitors when the application shuts down."""
    if hasattr(app, 'tank_monitor_manager'):
        app.tank_monitor_manager.cleanup_resources()

# Initialize monitors for all active tanks
with app.app_context():
    """Initialize monitors for all active tanks."""
    tank_monitor_manager.initialize_monitors()

# Register blueprints
app.register_blueprint(auth)
app.register_blueprint(admin, url_prefix='/admin')  # Register with URL prefix

# Initialize TimescaleDB
with app.app_context():
    # Create all tables
    db.create_all()
    
    # Set up TimescaleDB
    create_timescale_extensions()   
    
    # Skip database queries during any database-related commands
    if 'db' in sys.argv:
        # Skip database queries during migrations
        pass
    else:
        # Try to set up TimescaleDB retention, but handle errors gracefully
        try:
            setup_timescale_retention()
        except Exception as e:
            logger.error(f"Error setting up TimescaleDB retention: {str(e)}")
            
        # Create admin user if none exists
        try:
            if not User.query.filter_by(role='admin').first():
                admin_user = User(
                    username='admin',
                    email='admin@example.com',
                    first_name='Admin',
                    last_name='User',
                    role='admin'
                )
                admin_user.set_password('admin')
                db.session.add(admin_user)
                db.session.commit()
                logger.info("Created default admin user")
        except Exception as e:
            logger.error(f"Error checking/creating admin user: {str(e)}")
# Start monitoring all active tanks after app initialization
def start_monitoring_on_startup():
    """Start monitoring all active tanks."""
    logger.info("Starting monitoring for all active tanks on application startup")
    with app.app_context():
        # Use the existing method to start monitoring all tanks
        tank_monitor_manager.start_monitoring_all_active_tanks()

# Start monitoring in a background thread
Thread(target=start_monitoring_on_startup, daemon=True).start()


# Start system monitoring in a background thread


# Helper functions
def get_accessible_tanks():
    """Returns tanks accessible to the current user."""
    if current_user.is_admin():
        return Tank.not_deleted().all()
    elif hasattr(current_user, 'companies') and current_user.companies:
        # Get all sites for user's companies
        company_ids = [company.id for company in current_user.companies]
        sites = Site.not_deleted().filter(Site.company_id.in_(company_ids)).all()
        site_ids = [site.id for site in sites]
        return Tank.not_deleted().filter(Tank.site_id.in_(site_ids)).all()
    elif hasattr(current_user, 'sites') and current_user.sites:
        # Get tanks for user's sites
        site_ids = [site.id for site in current_user.sites]
        return Tank.not_deleted().filter(Tank.site_id.in_(site_ids)).all()
    else:
        return []

def check_tank_access(tank_id):
    """Check if current user has access to the specified tank."""
    if current_user.is_admin():
        return True
    
    with app.app_context():
        tank = db.session.get(Tank, tank_id)
        if not tank:
            return False
        
        # Check if user has access to the tank's site
        if hasattr(current_user, 'sites') and current_user.sites:
            if tank.site in current_user.sites:
                return True
        
        # Check if user has access to the tank's company
        if hasattr(current_user, 'companies') and current_user.companies:
            if tank.site.company in current_user.companies:
                return True
    
    return False

def get_active_alarms_count():
    """Get count of active alarms for accessible tanks."""
    tanks = get_accessible_tanks()
    tank_ids = [tank.id for tank in tanks]
    
    if not tank_ids:
        return 0
    
    return Alarm.query.filter(
        Alarm.tank_id.in_(tank_ids),
        Alarm.acknowledged == False
    ).count()

def get_daily_usage_data():
    # Implement logic to fetch or compute daily usage data
    return {
        'date': '2025-04-01',
        'usage': 1000  # Example value
    }

def get_tank_level_status(tank, measurement=None):
    """
    Get the status of a tank's level (critical, low, normal, high).







    """
    if not measurement:
        measurement = tank.get_latest_measurement()
        if measurement:
            # Convert to dict to avoid session issues
            measurement_data = measurement.to_dict()
            fill_percent = measurement_data['fill_percent']
        else:
            return 'unknown'
    else:
        # If measurement is already provided, get fill_percent
        # Check if it's a dict or an ORM object
        if isinstance(measurement, dict):
            fill_percent = measurement['fill_percent']
        else:
            fill_percent = measurement.fill_percent
    
    if fill_percent is None:

        return _('unknown')
    
    if hasattr(tank, 'critical_level_threshold') and tank.critical_level_threshold is not None:
        if fill_percent <= tank.critical_level_threshold:

            return _('critical')
    
    if hasattr(tank, 'low_level_threshold') and tank.low_level_threshold is not None:
        if fill_percent <= tank.low_level_threshold:

            return _('low')
    
    if hasattr(tank, 'high_level_threshold') and tank.high_level_threshold is not None:
        if fill_percent >= tank.high_level_threshold:

            return _('high')
    

    return _('normal')

# Make helper functions available to templates
@app.context_processor
def utility_processor():
    return {
        'get_accessible_tanks': get_accessible_tanks,
        'get_tank_level_status': get_tank_level_status,
        # Add any other helper functions here
    }

# Make active_alarms_count available to all templates
@app.context_processor
def inject_active_alarms_count():
    """Inject active alarms count into all templates."""
    if current_user.is_authenticated:
        return {'active_alarms_count': get_active_alarms_count()}
    return {'active_alarms_count': 0}

# Routes
@app.context_processor
def inject_now():
    return {'now': datetime.now()}
    
@app.route('/')
def index():
    """Landing page."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    return render_template('index.html', title=_('Fuel Tank Monitoring'))

@app.route('/dashboard')
@login_required
def dashboard():
    """Dashboard page."""
    tanks = get_accessible_tanks()
    active_alarms_count = get_active_alarms_count()
    
    # Get recent alarms
    tank_ids = [tank.id for tank in tanks]
    recent_alarms = []
    if tank_ids:
        recent_alarms = Alarm.query.filter(
            Alarm.tank_id.in_(tank_ids)
        ).order_by(Alarm.timestamp.desc()).limit(5).all()
    
    # Get tank statistics
    total_tanks = len(tanks)
    connected_tanks = sum(1 for tank in tanks if tank.get_connection_status() == "Connected")
    
    # Count tanks by level status
    critical_tanks = 0
    low_tanks = 0
    normal_tanks = 0
    high_tanks = 0
    
    # Calculate total volume
    total_volume = 0
    
    for tank in tanks:
        measurement = tank.get_latest_measurement()
        if measurement:
            # Convert to dict to avoid session issues
            measurement_dict = measurement.to_dict()
            
            if measurement_dict['fill_percent'] <= tank.critical_level_threshold:
                critical_tanks += 1
            elif measurement_dict['fill_percent'] <= tank.low_level_threshold:
                low_tanks += 1
            elif measurement_dict['fill_percent'] >= tank.high_level_threshold:
                high_tanks += 1
            else:
                normal_tanks += 1
                
            total_volume += measurement_dict['volume']
    
    return render_template('dashboard.html',
                          title=_('Dashboard'),
                          tanks=tanks,
                          recent_alarms=recent_alarms,
                          total_tanks=total_tanks,
                          connected_tanks=connected_tanks,
                          critical_tanks=critical_tanks,
                          low_tanks=low_tanks,
                          normal_tanks=normal_tanks,
                          high_tanks=high_tanks,
                          total_volume=total_volume,
                          active_alarms_count=active_alarms_count)

@app.route('/tanks')
@login_required
def tanks():
    """Tanks overview page."""
    tanks = get_accessible_tanks()

    return render_template('tanks.html', title=_('Tanks Overview'), tanks=tanks)

@app.route('/tanks/<int:tank_id>')
@login_required
def tank_detail(tank_id):
    """Tank detail page."""
    if not check_tank_access(tank_id):

        flash(_('Access denied'), 'danger')
        return redirect(url_for('tanks'))
    
    tank = Tank.query.get_or_404(tank_id)
    measurement = tank.get_latest_measurement()
    
    # Get recent measurements for chart
    recent_measurements = tank.get_recent_measurements(100)
    # Convert to dicts to avoid session issues if needed for JavaScript
    recent_measurement_dicts = [m.to_dict() for m in recent_measurements] if recent_measurements else []
    
    # Get recent alarms
    recent_alarms = Alarm.query.filter_by(
        tank_id=tank_id
    ).order_by(Alarm.timestamp.desc()).limit(5).all()
    
    return render_template('tank_detail.html',
                          title=_('Tank Details'),
                          tank=tank,
                          measurement=measurement,
                          recent_measurements=recent_measurements,
                          recent_measurement_dicts=recent_measurement_dicts,
                          recent_alarms=recent_alarms)

@app.route('/tanks/<int:tank_id>/history')
@login_required
def tank_history(tank_id):
    """Tank measurement history page."""
    if not check_tank_access(tank_id):

        flash(_('Access denied'), 'danger')
        return redirect(url_for('tanks'))
    
    tank = Tank.query.get_or_404(tank_id)
    
    # Get date range from query parameters
    days = request.args.get('days', 7, type=int)
    
    # Calculate time threshold
    threshold = datetime.now() - timedelta(days=days)
    
    # For the template, we don't need to fetch all measurements
    # Just pass the tank and days, and let the frontend fetch data via API
    return render_template('tank_history.html',
                          tank=tank,
                          days=days)

@app.route('/tanks/<int:tank_id>/consumption')
@login_required
def tank_consumption(tank_id):
    """Tank consumption analysis page."""
    if not check_tank_access(tank_id):

        flash(_('Access denied'), 'danger')
        return redirect(url_for('tanks'))
    
    tank = Tank.query.get_or_404(tank_id)
    
    return render_template('tank_consumption.html', tank=tank)
@app.route('/tanks/<int:tank_id>/calibration', methods=['GET', 'POST'])
@login_required
def tank_calibration(tank_id):
    """Tank calibration page."""
    if not check_tank_access(tank_id):

        flash(_('Access denied'), 'danger')
        return redirect(url_for('tanks'))
    
    tank = Tank.query.get_or_404(tank_id)
    
    if request.method == 'POST':
        # Update tank calibration parameters
        tank.tank_height = float(request.form.get('tank_height', tank.tank_height))
        tank.tank_diameter = float(request.form.get('tank_diameter', tank.tank_diameter))
        tank.fluid_density = float(request.form.get('fluid_density', tank.fluid_density))
        tank.atmospheric_pressure = float(request.form.get('atmospheric_pressure', tank.atmospheric_pressure))
        tank.calibration_factor = float(request.form.get('calibration_factor', tank.calibration_factor))
        
        db.session.commit()
        
        # Update monitor if it exists
        monitor = tank_monitor_manager.get_monitor(tank_id)
        if monitor:
            monitor.tank_height = tank.tank_height
            monitor.tank_diameter = tank.tank_diameter
            monitor.fluid_density = tank.fluid_density
            monitor.atmospheric_pressure = tank.atmospheric_pressure
            monitor.calibration_factor = tank.calibration_factor
            
            # Recalculate tank volume
            monitor.tank_volume = 3.14159 * (tank.tank_diameter/2)**2 * tank.tank_height
        

        flash(_('Calibration updated successfully'), 'success')
        return redirect(url_for('tank_detail', tank_id=tank_id))
    
    return render_template('tank_calibration.html', tank=tank)

@app.route('/alarms')
@login_required
def alarms():
    """Alarms page."""
    tanks = get_accessible_tanks()
    tank_ids = [tank.id for tank in tanks]
    
    # Get filter parameters
    acknowledged = request.args.get('acknowledged', 'false')
    level = request.args.get('level', 'all')
    
    # Build query
    query = Alarm.query.filter(Alarm.tank_id.in_(tank_ids)) if tank_ids else Alarm.query.filter(False)
    
    if acknowledged == 'false':
        query = query.filter_by(acknowledged=False)
    elif acknowledged == 'true':
        query = query.filter_by(acknowledged=True)
    
    if level != 'all':
        query = query.filter_by(level=level)
    
    # Get alarms
    alarms = query.order_by(Alarm.timestamp.desc()).all()
    
    return render_template('alarms.html',
                          alarms=alarms,
                          acknowledged=acknowledged,
                          level=level)

@app.route('/alarms/acknowledge/<int:alarm_id>', methods=['POST'])
@login_required
def acknowledge_alarm(alarm_id):
    """Acknowledge alarm."""
    alarm = Alarm.query.get_or_404(alarm_id)
    
    # Check if user has access to the alarm's tank
    if not check_tank_access(alarm.tank_id):

        flash(_('Access denied'), 'danger')
        return redirect(url_for('alarms'))
    
    # Acknowledge alarm
    alarm.acknowledged = True
    alarm.acknowledged_by = current_user.id
    alarm.acknowledged_at = datetime.now()
    
    db.session.commit()
    

    flash(_('Alarm acknowledged'), 'success')
    return redirect(url_for('alarms'))

import json
from flask import Response, stream_with_context

@app.route('/tank-updates')
@login_required
def tank_updates():
    """Server-Sent Events (SSE) endpoint for real-time tank updates."""
    # Check if a specific tank_id is requested
    specific_tank_id = request.args.get('tank_id', type=int)
    
    def event_stream():
        # Send initial message

        yield f"data: {json.dumps({'event': 'connected', 'message': _('Connected to tank updates stream')}, cls=DateTimeEncoder)}\n\n"
        
        # Get accessible tanks for this user
        tanks = get_accessible_tanks()
        
        # Filter for specific tank if requested and accessible
        if specific_tank_id:
            tanks = [tank for tank in tanks if tank.id == specific_tank_id]
            if not tanks:  # If the requested tank is not accessible

                yield f"data: {json.dumps({'event': 'error', 'message': _('Tank not accessible')}, cls=DateTimeEncoder)}\n\n"
                return
        
        tank_ids = [tank.id for tank in tanks]
        
        # Start monitoring for these tanks
        for tank_id in tank_ids:
            tank_monitor_manager.start_monitoring(tank_id)
            
        # Keep track of last update time for each tank
        last_updates = {tank_id: datetime.now() - timedelta(minutes=5) for tank_id in tank_ids}
        
        try:
            while True:
                # Check for new measurements for each tank
                for tank_id in tank_ids:
                    with app.app_context():
                        # Use db.session.get() instead of Tank.query.get()
                        tank = db.session.get(Tank, tank_id)
                        if not tank:
                            continue
                            
                        measurement = tank.get_latest_measurement()
                        if not measurement:
                            continue
                            
                        # Check if this is a new measurement
                        if measurement.timestamp > last_updates[tank_id]:
                            # Update last update time
                            last_updates[tank_id] = measurement.timestamp
                            
                            # Convert to dict and send as event
                            data = measurement.to_dict()
                            yield f"data: {json.dumps(data, cls=DateTimeEncoder)}\n\n"
                
                # Sleep to avoid hammering the database
                time.sleep(2)
        except GeneratorExit:
            # Client disconnected
            pass
    
    return Response(stream_with_context(event_stream()),
                   mimetype="text/event-stream",
                   headers={
                       'Cache-Control': 'no-cache',
                       'Connection': 'keep-alive'
                   })

@app.route('/api/tanks/<int:tank_id>/measurements')
@login_required
def api_tank_measurements(tank_id):
    """API endpoint for tank measurements."""
    if not check_tank_access(tank_id):

        return jsonify({'error': _('Access denied')}), 403
    
    tank = Tank.query.get_or_404(tank_id)
    measurement = tank.get_latest_measurement()
    
    if not measurement:

        return jsonify({'error': _('No measurement available')}), 404
    
    # Convert to dict before returning to avoid session issues
    return jsonify(measurement.to_dict())

from services.tank_forecast_service import TankForecastService
from flask import request, jsonify
from datetime import datetime, timedelta
from functools import wraps
import time

# Add a simple caching mechanism
forecast_cache = {}
CACHE_EXPIRY = 3600  # 1 hour in seconds

def cached_response(key, expiry=CACHE_EXPIRY):
    """Simple decorator for caching responses."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            current_time = time.time()
            
            # Check if we have a valid cached response
            if key in forecast_cache:
                cache_time, cache_data = forecast_cache[key]
                if current_time - cache_time < expiry:
                    return cache_data
            
            # No valid cache, call the original function
            result = f(*args, **kwargs)
            
            # Cache the result
            forecast_cache[key] = (current_time, result)
            return result
        return decorated_function
    return decorator

@app.route('/api/tanks/<int:tank_id>/forecast')
@login_required
def api_tank_forecast(tank_id):
    """API endpoint for tank consumption forecast."""
    if not check_tank_access(tank_id):

        return jsonify({'error': _('Access denied')}), 403
    
    # Validate and sanitize input parameters
    try:
        days = request.args.get('days', 30, type=int)
        if days < 1:
            days = 1
        elif days > 365:  # Set a reasonable upper limit
            days = 365
    except (ValueError, TypeError):

        return jsonify({'error': _('Invalid days parameter')}), 400
    
    # Generate cache key based on tank_id and days
    cache_key = f"forecast_{tank_id}_{days}"
    
    @cached_response(cache_key)
    def get_forecast_data():
        tank = Tank.query.get_or_404(tank_id)
        
        # Create forecast service
        forecast_service = TankForecastService(tank_id, days)
        
        # Get monitor for additional tank data
        monitor = tank_monitor_manager.get_monitor(tank_id)
        if monitor:
            monitor.tank_height = tank.tank_height
            monitor.tank_diameter = tank.tank_diameter
            monitor.fluid_density = tank.fluid_density
            monitor.atmospheric_pressure = tank.atmospheric_pressure
            monitor.calibration_factor = tank.calibration_factor
            
            # Recalculate tank volume
            monitor.tank_volume = 3.14159 * (tank.tank_diameter/2)**2 * tank.tank_height
        
        # Generate forecast
        return forecast_service.generate_forecast(monitor)
    
    return jsonify(get_forecast_data())

# Add a route to clear the cache if needed
@app.route('/api/tanks/<int:tank_id>/forecast/clear-cache', methods=['POST'])
@login_required
def clear_forecast_cache(tank_id):
    """Clear the forecast cache for a specific tank."""
    if not check_tank_access(tank_id):
        return jsonify({'error': 'Access denied'}), 403
    
    # Clear all cache entries for this tank
    keys_to_remove = [k for k in forecast_cache.keys() if k.startswith(f"forecast_{tank_id}_")]
    for key in keys_to_remove:
        forecast_cache.pop(key, None)
    
    return jsonify({'success': True, 'message': 'Cache cleared'})

@app.route('/api/tanks/<int:tank_id>/stats')
@login_required
def api_tank_stats(tank_id):
    """API endpoint for tank statistics."""
    if not check_tank_access(tank_id):
        return jsonify({'error': 'Access denied'}), 403
    
    tank = Tank.query.get_or_404(tank_id)
    measurement = tank.get_latest_measurement()
    
    # Get time range from query parameters
    days = request.args.get('days', 7, type=int)
    
    # Calculate time threshold
    threshold = datetime.now() - timedelta(days=days)
    
    # Use TimescaleDB aggregation for better performance
    from sqlalchemy import text
    
    # Get statistics using TimescaleDB
    stats_query = text("""
        SELECT 
            MIN(volume) as min_volume,
            MAX(volume) as max_volume,
            AVG(volume) as avg_volume,
            COUNT(*) as measurement_count
        FROM measurement
        WHERE tank_id = :tank_id
          AND timestamp >= :threshold
    """)
    
    result = db.session.execute(
        stats_query,
        {'tank_id': tank_id, 'threshold': threshold}
    ).fetchone()
    
    # Get first and last volume for volume change calculation
    volume_query = text("""
        SELECT 
            (SELECT volume FROM measurement 
             WHERE tank_id = :tank_id AND timestamp >= :threshold 
             ORDER BY timestamp ASC LIMIT 1) as first_volume,
            (SELECT volume FROM measurement 
             WHERE tank_id = :tank_id AND timestamp >= :threshold 
             ORDER BY timestamp DESC LIMIT 1) as last_volume
    """)
    
    volume_result = db.session.execute(
        volume_query,
        {'tank_id': tank_id, 'threshold': threshold}
    ).fetchone()
    
    # Calculate statistics
    if result and result.measurement_count > 0:
        min_volume = float(result.min_volume) if result.min_volume is not None else 0
        max_volume = float(result.max_volume) if result.max_volume is not None else 0
        avg_volume = float(result.avg_volume) if result.avg_volume is not None else 0
        
        # Calculate volume change (negative means consumption)
        first_volume = float(volume_result.first_volume) if volume_result.first_volume is not None else 0
        last_volume = float(volume_result.last_volume) if volume_result.last_volume is not None else 0
        volume_change = last_volume - first_volume
        
        # Calculate daily consumption rate
        if days > 0 and volume_change < 0:
            daily_consumption = abs(volume_change) / days
        else:
            daily_consumption = 0
        
        stats = {
            'current_volume': measurement.volume if measurement else 0,
            'current_level': measurement.level if measurement else 0,
            'current_fill_percent': measurement.fill_percent if measurement else 0,
            'min_volume': min_volume,
            'max_volume': max_volume,
            'avg_volume': avg_volume,
            'volume_change': volume_change,
            'daily_consumption': daily_consumption,
            'measurement_count': result.measurement_count
        }
    else:
        stats = {
            'current_volume': measurement.volume if measurement else 0,
            'current_level': measurement.level if measurement else 0,
            'current_fill_percent': measurement.fill_percent if measurement else 0,
            'min_volume': 0,
            'max_volume': 0,
            'avg_volume': 0,
            'volume_change': 0,
            'daily_consumption': 0,
            'measurement_count': 0
        }
    
    return jsonify({
        'tank_id': tank_id,
        'stats': stats
    })

@app.route('/api/tank/<int:tank_id>/history')
@login_required
def api_tank_history(tank_id):
    """API endpoint for tank measurement history with TimescaleDB aggregation"""
    # Get query parameters
    hours = request.args.get('hours', type=int)
    days = request.args.get('days', type=int)
    
    # Calculate time range
    end_time = datetime.now()
    if hours:
        start_time = end_time - timedelta(hours=hours)
        # Choose appropriate interval based on time range
        if hours <= 3:
            interval = '1 minute'
        elif hours <= 24:
            interval = '5 minutes'
        else:
            interval = '15 minutes'
    elif days:
        start_time = end_time - timedelta(days=days)
        if days <= 7:
            interval = '1 hour'
        else:
            interval = '6 hours'
    else:
        # Default: 24 hours with 5-minute intervals
        start_time = end_time - timedelta(hours=24)
        interval = '5 minutes'
    
    # Get aggregated measurements using TimescaleDB
    measurements = Measurement.get_aggregated(tank_id, start_time, end_time, interval)
    
    # Return JSON response
    return jsonify({
        'success': True,
        'measurements': measurements,
        'interval': interval
    })

@app.route('/api/alarms')
@login_required
def api_alarms():
    """API endpoint for alarms."""
    tanks = get_accessible_tanks()
    tank_ids = [tank.id for tank in tanks]
    
    # Get filter parameters
    acknowledged = request.args.get('acknowledged', 'false')
    level = request.args.get('level', 'all')
    
    # Build query
    query = Alarm.query.filter(Alarm.tank_id.in_(tank_ids)) if tank_ids else Alarm.query.filter(False)
    
    if acknowledged == 'false':
        query = query.filter_by(acknowledged=False)
    elif acknowledged == 'true':
        query = query.filter_by(acknowledged=True)
    
    if level != 'all':
        query = query.filter_by(level=level)
    
    # Get alarms
    alarms = query.order_by(Alarm.timestamp.desc()).all()
    
    # Convert to list of dictionaries
    data = [alarm.to_dict() for alarm in alarms]
    
    return jsonify({
        'alarms': data
    })

@app.route('/api/statistics/daily-usage')
def daily_usage():
    # Fetch daily usage data from the database or other source
    daily_usage_data = get_daily_usage_data()
    return jsonify(daily_usage_data)

@app.route('/download/tank/<int:tank_id>/csv')
@login_required
def download_tank_csv(tank_id):
    """Download tank measurement history as CSV."""
    if not check_tank_access(tank_id):
        flash('Access denied', 'danger')
        return redirect(url_for('tanks'))
    
    tank = Tank.query.get_or_404(tank_id)
    
    # Get time range from query parameters
    days = request.args.get('days', 7, type=int)
    
    # Calculate time threshold
    threshold = datetime.now() - timedelta(days=days)
    
    # Determine appropriate interval based on days
    if days <= 1:
        interval = '1 minute'
    elif days <= 7:
        interval = '15 minutes'
    else:
        interval = '1 hour'
    
    # Get aggregated measurements using TimescaleDB
    measurements = Measurement.get_aggregated(tank_id, threshold, datetime.now(), interval)
    
    # Create CSV file in memory
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write headers
    writer.writerow([
        _('Timestamp'), _('Pressure (bar)'), _('Temperature (°C)'),
        _('Level (m)'), _('Volume (L)'), _('Flow Rate (L/min)'), _('Fill (%)'), _('Status')
    ])
    
    # Write data rows
    for m in measurements:
        writer.writerow([
            m['timestamp'],
            f"{m['pressure']:.4f}" if m['pressure'] is not None else "N/A",
            f"{m['temperature']:.2f}" if m['temperature'] is not None else "N/A",
            f"{m['level']:.3f}" if m['level'] is not None else "N/A",
            f"{m['volume']:.1f}" if m['volume'] is not None else "N/A",
            f"{m['flow_rate']:.2f}" if m['flow_rate'] is not None else "N/A",
            f"{m['fill_percent']:.1f}" if m['fill_percent'] is not None else "N/A",
            f"{m['status']}" if m['status'] is not None else "N/A"
        ])
    
    # Prepare response
    output.seek(0)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment;filename=tank_{tank_id}_data_{timestamp}.csv'}
    )


# Error handlers
@app.errorhandler(404)
def page_not_found(e):
    """Handle 404 errors."""

    return render_template('errors/404.html', title=_('Page Not Found')), 404

@app.errorhandler(500)
def server_error(e):
    """Handle 500 errors."""

    return render_template('errors/500.html', title=_('Server Error')), 500

# Static files
@app.route('/favicon.ico')
def favicon():
    """Serve favicon."""
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')

# Graceful shutdown
@app.teardown_appcontext
def shutdown_session(exception=None):
    db.session.remove()

# Main entry point
if __name__ == '__main__':
    # Start the Flask application
    try:
        app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)
    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        # Make sure monitoring is stopped when the app exits
        tank_monitor_manager.stop_monitoring()