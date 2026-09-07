"""
Fuel Tank Monitoring Web Application

Security-hardened Flask application for monitoring fuel levels, volume,
and flow rates using Keller pressure sensors connected via K114 converters.
"""
import os
import sys
import csv
import io
import json
import logging
import time
import secrets
from threading import Thread, Lock
from functools import wraps

from flask import Flask, render_template, jsonify, request, redirect, url_for, flash, Response, send_from_directory, stream_with_context
from flask_login import LoginManager, login_required, current_user
from config import Config, DevelopmentConfig, ProductionConfig, config_by_name
from models.database import (
    db, User, Company, Site, Tank, Measurement, Alarm,
    create_timescale_extensions, setup_timescale_retention,
)
from services.mqtt_ingestion import MqttIngestionService
from auth import auth, login_manager
from admin import admin, init_admin
from datetime import datetime, timedelta
from sqlalchemy import func, and_
from flask_migrate import Migrate
from flask_wtf import CSRFProtect

import custom_translations
from custom_translations import gettext as _

# Security imports
from utils.rate_limiter import init_rate_limiter, api_limiter, rate_limit
from utils.security import init_security_middleware

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Application factory helpers
# ---------------------------------------------------------------------------

def _select_config():
    """Return the configuration class based on FLASK_ENV / FLASK_CONFIG."""
    env = os.environ.get('FLASK_ENV', os.environ.get('FLASK_CONFIG', 'development'))
    return config_by_name.get(env, DevelopmentConfig)


# ---------------------------------------------------------------------------
# Flask application
# ---------------------------------------------------------------------------

app = Flask(__name__)
app.config.from_object(_select_config())

# Override DB URI from environment (backward compatibility).
app.config['SQLALCHEMY_DATABASE_URI'] = (
    os.environ.get('DATABASE_URL')
    or app.config.get('SQLALCHEMY_DATABASE_URI')
    or 'sqlite:///fuel_tank.db'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Session security
app.config.setdefault('SESSION_COOKIE_HTTPONLY', True)
app.config.setdefault('SESSION_COOKIE_SAMESITE', 'Lax')

# Initialise internationalisation
custom_translations.init_app(app)

# ---------------------------------------------------------------------------
# Extensions
# ---------------------------------------------------------------------------

db.init_app(app)
migrate = Migrate(app, db)
login_manager.init_app(app)

# CSRF protection (provides csrf_token() in Jinja2 templates)
csrf = CSRFProtect(app)

# Rate limiter (Redis-backed)
init_rate_limiter(app)

# Security headers middleware
init_security_middleware(app)


class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles datetime objects."""
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


# ---------------------------------------------------------------------------
# Development-only cache-busting
# ---------------------------------------------------------------------------

if app.config.get('DEBUG', False):
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.jinja_env.auto_reload = True

    @app.after_request
    def add_header(response):
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '-1'
        return response

    @app.context_processor
    def inject_cache_busting():
        return {'cache_buster': int(time.time())}


# ---------------------------------------------------------------------------
# Template filters
# ---------------------------------------------------------------------------

@app.template_filter('timeago')
def timeago_filter(timestamp):
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


# ---------------------------------------------------------------------------
# SSE with Redis pub/sub (replaces DB polling)
# ---------------------------------------------------------------------------

class SSEBroker:
    """Publishes tank updates via Redis pub/sub so SSE endpoints don't poll."""

    def __init__(self):
        self._subscribers: dict[int, list] = {}  # tank_id -> [queue, ...]
        self._lock = Lock()
        self._redis = None
        self._listener_thread = None

    def _get_redis(self):
        try:
            from redis import Redis
            return Redis.from_url(
                app.config.get('REDIS_URL', 'redis://localhost:6379/0'),
                decode_responses=True,
                socket_timeout=2,
            )
        except Exception:
            return None

    def publish(self, tank_id: int, data: dict):
        """Publish a measurement update for *tank_id*."""
        redis = self._get_redis()
        if redis:
            try:
                redis.publish(f"tank:{tank_id}", json.dumps(data, cls=DateTimeEncoder))
                return
            except Exception:
                pass

        # Fallback: push directly to in-memory queues.
        with self._lock:
            for q in self._subscribers.get(tank_id, []):
                try:
                    q.append(data)
                except Exception:
                    pass

    def subscribe(self, tank_id: int):
        """Return a list that will receive updates for *tank_id*."""
        with self._lock:
            queue = []
            self._subscribers.setdefault(tank_id, []).append(queue)
            return queue

    def unsubscribe(self, tank_id: int, queue: list):
        with self._lock:
            subs = self._subscribers.get(tank_id, [])
            if queue in subs:
                subs.remove(queue)


sse_broker = SSEBroker()

# ---------------------------------------------------------------------------
# MQTT ingestion
# ---------------------------------------------------------------------------

mqtt_ingestion = MqttIngestionService(
    app=app,
    broker=app.config.get('MQTT_BROKER', 'localhost'),
    port=app.config.get('MQTT_PORT', 1883),
    username=app.config.get('MQTT_USER'),
    password=app.config.get('MQTT_PASS'),
    sse_broker=sse_broker,
)


@app.teardown_appcontext
def cleanup_monitors(exception=None):
    mqtt_ingestion.stop()


# ---------------------------------------------------------------------------
# RBAC helper
# ---------------------------------------------------------------------------

def _require_admin():
    """Return True if current_user is an admin, else flash and redirect."""
    if not current_user.is_authenticated or not current_user.is_admin():
        flash(_('Admin access required'), 'danger')
        return False
    return True


# ---------------------------------------------------------------------------
# Tank access helpers
# ---------------------------------------------------------------------------

def get_accessible_tanks():
    if current_user.is_admin():
        return Tank.not_deleted().all()
    elif hasattr(current_user, 'companies') and current_user.companies:
        company_ids = [company.id for company in current_user.companies]
        sites = Site.not_deleted().filter(Site.company_id.in_(company_ids)).all()
        site_ids = [site.id for site in sites]
        return Tank.not_deleted().filter(Tank.site_id.in_(site_ids)).all()
    elif hasattr(current_user, 'sites') and current_user.sites:
        site_ids = [site.id for site in current_user.sites]
        return Tank.not_deleted().filter(Tank.site_id.in_(site_ids)).all()
    else:
        return []


def check_tank_access(tank_id):
    if current_user.is_admin():
        return True
    with app.app_context():
        tank = db.session.get(Tank, tank_id)
        if not tank:
            return False
        if hasattr(current_user, 'sites') and current_user.sites:
            if tank.site in current_user.sites:
                return True
        if hasattr(current_user, 'companies') and current_user.companies:
            if tank.site.company in current_user.companies:
                return True
    return False


def get_active_alarms_count():
    tanks = get_accessible_tanks()
    tank_ids = [tank.id for tank in tanks]
    if not tank_ids:
        return 0
    return Alarm.query.filter(
        Alarm.tank_id.in_(tank_ids),
        Alarm.acknowledged == False
    ).count()


def get_daily_usage_data():
    return {'date': '2025-04-01', 'usage': 1000}


def get_tank_level_status(tank, measurement=None):
    if not measurement:
        measurement = tank.get_latest_measurement()
        if measurement:
            measurement_data = measurement.to_dict()
            fill_percent = measurement_data['fill_percent']
        else:
            return 'unknown'
    else:
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


# ---------------------------------------------------------------------------
# Context processors
# ---------------------------------------------------------------------------

@app.context_processor
def utility_processor():
    return {
        'get_accessible_tanks': get_accessible_tanks,
        'get_tank_level_status': get_tank_level_status,
    }


@app.context_processor
def inject_active_alarms_count():
    if current_user.is_authenticated:
        return {'active_alarms_count': get_active_alarms_count()}
    return {'active_alarms_count': 0}


@app.context_processor
def inject_now():
    return {'now': datetime.now()}


# ---------------------------------------------------------------------------
# Register blueprints
# ---------------------------------------------------------------------------

app.register_blueprint(auth)
app.register_blueprint(admin, url_prefix='/admin')


# ---------------------------------------------------------------------------
# Database initialization
# ---------------------------------------------------------------------------

with app.app_context():
    db.create_all()
    create_timescale_extensions()

    if 'db' not in sys.argv:
        try:
            setup_timescale_retention()
        except Exception as e:
            logger.error("Error setting up TimescaleDB retention: %s", e)

        try:
            if not User.query.filter_by(role='admin').first():
                logger.warning(
                    "No admin user found. Create one with:\n"
                    "  flask shell\n"
                    "  >>> from models.database import db, User\n"
                    "  >>> u = User(username='admin', email='admin@example.com', role='admin')\n"
                    "  >>> u.set_password('YOUR_STRONG_PASSWORD')\n"
                    "  >>> db.session.add(u); db.session.commit()"
                )
        except Exception as e:
            logger.error("Error checking admin user: %s", e)


# ---------------------------------------------------------------------------
# Background threads
# ---------------------------------------------------------------------------

def start_monitoring_on_startup():
    logger.info("Starting MQTT ingestion service...")
    mqtt_ingestion.start()


Thread(target=start_monitoring_on_startup, daemon=True).start()


@app.route('/tank-updates')
@login_required
def tank_updates():
    """SSE endpoint — now backed by Redis pub/sub instead of DB polling."""
    specific_tank_id = request.args.get('tank_id', type=int)

    def event_stream():
        yield f"data: {json.dumps({'event': 'connected', 'message': str(_('Connected to tank updates stream'))}, cls=DateTimeEncoder)}\n\n"

        tanks = get_accessible_tanks()
        if specific_tank_id:
            tanks = [t for t in tanks if t.id == specific_tank_id]
            if not tanks:
                yield f"data: {json.dumps({'event': 'error', 'message': str(_('Tank not accessible'))}, cls=DateTimeEncoder)}\n\n"
                return

        # Subscribe to each tank's channel.
        queues = []
        for tank in tanks:
            q = sse_broker.subscribe(tank.id)
            queues.append((tank.id, q))

        try:
            while True:
                any_data = False
                for tank_id, q in queues:
                    while q:
                        data = q.pop(0)
                        yield f"data: {json.dumps(data, cls=DateTimeEncoder)}\n\n"
                        any_data = True

                if not any_data:
                    time.sleep(0.5)
        except GeneratorExit:
            pass
        finally:
            for tank_id, q in queues:
                sse_broker.unsubscribe(tank_id, q)

    return Response(
        stream_with_context(event_stream()),
        mimetype="text/event-stream",
        headers={'Cache-Control': 'no-cache', 'Connection': 'keep-alive'},
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html', title=_('Fuel Tank Monitoring'))


@app.route('/dashboard')
@login_required
def dashboard():
    tanks = get_accessible_tanks()
    active_alarms_count = get_active_alarms_count()

    tank_ids = [tank.id for tank in tanks]
    recent_alarms = []
    if tank_ids:
        recent_alarms = Alarm.query.filter(
            Alarm.tank_id.in_(tank_ids)
        ).order_by(Alarm.timestamp.desc()).limit(5).all()

    total_tanks = len(tanks)
    connected_tanks = sum(1 for tank in tanks if tank.get_connection_status() == "Connected")

    critical_tanks = 0
    low_tanks = 0
    normal_tanks = 0
    high_tanks = 0

    tank_map = {tank.id: tank for tank in tanks}

    latest_measurements = {}
    if tank_ids:
        subq = db.session.query(
            Measurement.tank_id,
            func.max(Measurement.timestamp).label('max_ts')
        ).filter(Measurement.tank_id.in_(tank_ids)).group_by(Measurement.tank_id).subquery()

        latest = db.session.query(Measurement).join(
            subq,
            and_(Measurement.tank_id == subq.c.tank_id,
                 Measurement.timestamp == subq.c.max_ts)
        ).all()

        for m in latest:
            latest_measurements[m.tank_id] = m

    total_volume = 0
    for tank_id in tank_ids:
        measurement = latest_measurements.get(tank_id)
        if measurement:
            measurement_dict = measurement.to_dict()
            fill = measurement_dict['fill_percent']
            if fill <= tank_map[tank_id].critical_level_threshold:
                critical_tanks += 1
            elif fill <= tank_map[tank_id].low_level_threshold:
                low_tanks += 1
            elif fill >= tank_map[tank_id].high_level_threshold:
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
    tanks = get_accessible_tanks()
    return render_template('tanks.html', title=_('Tanks Overview'), tanks=tanks)


@app.route('/tanks/<int:tank_id>')
@login_required
def tank_detail(tank_id):
    if not check_tank_access(tank_id):
        flash(_('Access denied'), 'danger')
        return redirect(url_for('tanks'))

    tank = Tank.query.get_or_404(tank_id)
    measurement = tank.get_latest_measurement()
    recent_measurements = tank.get_recent_measurements(100)
    recent_measurement_dicts = [m.to_dict() for m in recent_measurements] if recent_measurements else []
    recent_alarms = Alarm.query.filter_by(tank_id=tank_id).order_by(Alarm.timestamp.desc()).limit(5).all()

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
    if not check_tank_access(tank_id):
        flash(_('Access denied'), 'danger')
        return redirect(url_for('tanks'))

    tank = Tank.query.get_or_404(tank_id)
    days = request.args.get('days', 7, type=int)
    return render_template('tank_history.html', tank=tank, days=days)


@app.route('/tanks/<int:tank_id>/consumption')
@login_required
def tank_consumption(tank_id):
    if not check_tank_access(tank_id):
        flash(_('Access denied'), 'danger')
        return redirect(url_for('tanks'))

    tank = Tank.query.get_or_404(tank_id)
    return render_template('tank_consumption.html', tank=tank)


@app.route('/tanks/<int:tank_id>/calibration', methods=['GET', 'POST'])
@login_required
def tank_calibration(tank_id):
    if not check_tank_access(tank_id):
        flash(_('Access denied'), 'danger')
        return redirect(url_for('tanks'))

    tank = Tank.query.get_or_404(tank_id)

    if request.method == 'POST':
        tank.tank_height = float(request.form.get('tank_height', tank.tank_height))
        tank.tank_diameter = float(request.form.get('tank_diameter', tank.tank_diameter))
        tank.fluid_density = float(request.form.get('fluid_density', tank.fluid_density))
        tank.atmospheric_pressure = float(request.form.get('atmospheric_pressure', tank.atmospheric_pressure))
        tank.calibration_factor = float(request.form.get('calibration_factor', tank.calibration_factor))
        db.session.commit()

        flash(_('Calibration updated successfully'), 'success')
        return redirect(url_for('tank_detail', tank_id=tank_id))

    return render_template('tank_calibration.html', tank=tank)


# ---------------------------------------------------------------------------
# Alarms
# ---------------------------------------------------------------------------

@app.route('/alarms')
@login_required
def alarms():
    tanks = get_accessible_tanks()
    tank_ids = [tank.id for tank in tanks]

    acknowledged = request.args.get('acknowledged', 'false')
    level = request.args.get('level', 'all')

    query = Alarm.query.filter(Alarm.tank_id.in_(tank_ids)) if tank_ids else Alarm.query.filter(False)

    if acknowledged == 'false':
        query = query.filter_by(acknowledged=False)
    elif acknowledged == 'true':
        query = query.filter_by(acknowledged=True)

    if level != 'all':
        query = query.filter_by(level=level)

    alarms_list = query.order_by(Alarm.timestamp.desc()).all()

    return render_template('alarms.html',
                           alarms=alarms_list,
                           acknowledged=acknowledged,
                           level=level)


@app.route('/alarms/acknowledge/<int:alarm_id>', methods=['POST'])
@login_required
def acknowledge_alarm(alarm_id):
    """Acknowledge alarm — requires CSRF token (handled by Flask-WTF automatically)."""
    alarm = Alarm.query.get_or_404(alarm_id)

    if not check_tank_access(alarm.tank_id):
        flash(_('Access denied'), 'danger')
        return redirect(url_for('alarms'))

    alarm.acknowledged = True
    alarm.acknowledged_by = current_user.id
    alarm.acknowledged_at = datetime.now()
    db.session.commit()

    flash(_('Alarm acknowledged'), 'success')
    return redirect(url_for('alarms'))


# ---------------------------------------------------------------------------
# API endpoints — all require login + RBAC check
# ---------------------------------------------------------------------------

@app.route('/api/tanks/<int:tank_id>/measurements')
@login_required
@rate_limit(api_limiter)
def api_tank_measurements(tank_id):
    if not check_tank_access(tank_id):
        return jsonify({'error': str(_('Access denied'))}), 403

    tank = Tank.query.get_or_404(tank_id)
    measurement = tank.get_latest_measurement()

    if not measurement:
        return jsonify({'error': str(_('No measurement available'))}), 404

    return jsonify(measurement.to_dict())


@app.route('/api/tank/<int:tank_id>/history')
@login_required
@rate_limit(api_limiter)
def api_tank_history(tank_id):
    if not check_tank_access(tank_id):
        return jsonify({'error': str(_('Access denied'))}), 403

    hours = request.args.get('hours', type=int)
    days = request.args.get('days', type=int)

    end_time = datetime.now()
    if hours:
        start_time = end_time - timedelta(hours=hours)
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
        start_time = end_time - timedelta(hours=24)
        interval = '5 minutes'

    measurements = Measurement.get_aggregated(tank_id, start_time, end_time, interval)

    return jsonify({'success': True, 'measurements': measurements, 'interval': interval})


@app.route('/api/tanks/<int:tank_id>/forecast')
@login_required
@rate_limit(api_limiter)
def api_tank_forecast(tank_id):
    if not check_tank_access(tank_id):
        return jsonify({'error': str(_('Access denied'))}), 403

    try:
        days = request.args.get('days', 30, type=int)
        days = max(1, min(days, 365))
    except (ValueError, TypeError):
        return jsonify({'error': str(_('Invalid days parameter'))}), 400

    cache_key = f"forecast_{tank_id}_{days}"

    @cached_response(cache_key)
    def get_forecast_data():
        from services.tank_forecast_service import TankForecastService
        tank = Tank.query.get_or_404(tank_id)
        forecast_service = TankForecastService(tank_id, days)
        return forecast_service.generate_forecast(None)

    return jsonify(get_forecast_data())


@app.route('/api/tanks/<int:tank_id>/forecast/clear-cache', methods=['POST'])
@login_required
@rate_limit(api_limiter)
def clear_forecast_cache(tank_id):
    if not check_tank_access(tank_id):
        return jsonify({'error': 'Access denied'}), 403

    keys_to_remove = [k for k in forecast_cache.keys() if k.startswith(f"forecast_{tank_id}_")]
    for key in keys_to_remove:
        forecast_cache.pop(key, None)

    return jsonify({'success': True, 'message': 'Cache cleared'})


@app.route('/api/tanks/<int:tank_id>/stats')
@login_required
@rate_limit(api_limiter)
def api_tank_stats(tank_id):
    if not check_tank_access(tank_id):
        return jsonify({'error': 'Access denied'}), 403

    from sqlalchemy import text

    tank = Tank.query.get_or_404(tank_id)
    measurement = tank.get_latest_measurement()
    days = request.args.get('days', 7, type=int)
    threshold = datetime.now() - timedelta(days=days)

    stats_query = text("""
        SELECT
            MIN(volume) as min_volume,
            MAX(volume) as max_volume,
            AVG(volume) as avg_volume,
            COUNT(*) as measurement_count
        FROM measurement
        WHERE tank_id = :tank_id AND timestamp >= :threshold
    """)
    result = db.session.execute(stats_query, {'tank_id': tank_id, 'threshold': threshold}).fetchone()

    volume_query = text("""
        SELECT
            (SELECT volume FROM measurement
             WHERE tank_id = :tank_id AND timestamp >= :threshold
             ORDER BY timestamp ASC LIMIT 1) as first_volume,
            (SELECT volume FROM measurement
             WHERE tank_id = :tank_id AND timestamp >= :threshold
             ORDER BY timestamp DESC LIMIT 1) as last_volume
    """)
    volume_result = db.session.execute(volume_query, {'tank_id': tank_id, 'threshold': threshold}).fetchone()

    if result and result.measurement_count > 0:
        min_volume = float(result.min_volume) if result.min_volume is not None else 0
        max_volume = float(result.max_volume) if result.max_volume is not None else 0
        avg_volume = float(result.avg_volume) if result.avg_volume is not None else 0
        first_volume = float(volume_result.first_volume) if volume_result.first_volume is not None else 0
        last_volume = float(volume_result.last_volume) if volume_result.last_volume is not None else 0
        volume_change = last_volume - first_volume
        daily_consumption = abs(volume_change) / days if days > 0 and volume_change < 0 else 0

        stats = {
            'current_volume': measurement.volume if measurement else 0,
            'current_level': measurement.level if measurement else 0,
            'current_fill_percent': measurement.fill_percent if measurement else 0,
            'min_volume': min_volume, 'max_volume': max_volume, 'avg_volume': avg_volume,
            'volume_change': volume_change, 'daily_consumption': daily_consumption,
            'measurement_count': result.measurement_count,
        }
    else:
        stats = {
            'current_volume': measurement.volume if measurement else 0,
            'current_level': measurement.level if measurement else 0,
            'current_fill_percent': measurement.fill_percent if measurement else 0,
            'min_volume': 0, 'max_volume': 0, 'avg_volume': 0,
            'volume_change': 0, 'daily_consumption': 0, 'measurement_count': 0,
        }

    return jsonify({'tank_id': tank_id, 'stats': stats})


@app.route('/api/alarms')
@login_required
@rate_limit(api_limiter)
def api_alarms():
    tanks = get_accessible_tanks()
    tank_ids = [tank.id for tank in tanks]

    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    page = max(1, page)
    per_page = max(1, min(per_page, 200))

    acknowledged = request.args.get('acknowledged', 'false')
    level = request.args.get('level', 'all')

    query = Alarm.query.filter(Alarm.tank_id.in_(tank_ids)) if tank_ids else Alarm.query.filter(False)

    if acknowledged == 'false':
        query = query.filter_by(acknowledged=False)
    elif acknowledged == 'true':
        query = query.filter_by(acknowledged=True)

    if level != 'all':
        query = query.filter_by(level=level)

    paginated = query.order_by(Alarm.timestamp.desc()).paginate(page=page, per_page=per_page, error_out=False)
    data = [alarm.to_dict() for alarm in paginated.items]

    return jsonify({
        'alarms': data, 'total': paginated.total,
        'page': page, 'per_page': per_page, 'pages': paginated.pages,
    })


@app.route('/api/statistics/daily-usage')
@login_required
@rate_limit(api_limiter)
def daily_usage():
    return jsonify(get_daily_usage_data())


@app.route('/download/tank/<int:tank_id>/csv')
@login_required
def download_tank_csv(tank_id):
    if not check_tank_access(tank_id):
        flash('Access denied', 'danger')
        return redirect(url_for('tanks'))

    from sqlalchemy import text as sql_text

    tank = Tank.query.get_or_404(tank_id)
    days = request.args.get('days', 7, type=int)
    threshold = datetime.now() - timedelta(days=days)

    if days <= 1:
        interval = '1 minute'
    elif days <= 7:
        interval = '15 minutes'
    else:
        interval = '1 hour'

    measurements = Measurement.get_aggregated(tank_id, threshold, datetime.now(), interval)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        _('Timestamp'), _('Pressure (bar)'), _('Temperature (°C)'),
        _('Level (m)'), _('Volume (L)'), _('Flow Rate (L/min)'), _('Fill (%)'), _('Status')
    ])

    for m in measurements:
        writer.writerow([
            m['timestamp'],
            f"{m['pressure']:.4f}" if m['pressure'] is not None else "N/A",
            f"{m['temperature']:.2f}" if m['temperature'] is not None else "N/A",
            f"{m['level']:.3f}" if m['level'] is not None else "N/A",
            f"{m['volume']:.1f}" if m['volume'] is not None else "N/A",
            f"{m['flow_rate']:.2f}" if m['flow_rate'] is not None else "N/A",
            f"{m['fill_percent']:.1f}" if m['fill_percent'] is not None else "N/A",
            f"{m['status']}" if m['status'] is not None else "N/A",
        ])

    output.seek(0)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment;filename=tank_{tank_id}_data_{timestamp}.csv'},
    )


# ---------------------------------------------------------------------------
# Response caching for forecasts
# ---------------------------------------------------------------------------

forecast_cache = {}
CACHE_EXPIRY = 3600


def cached_response(key, expiry=CACHE_EXPIRY):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            current_time = time.time()
            if key in forecast_cache:
                cache_time, cache_data = forecast_cache[key]
                if current_time - cache_time < expiry:
                    return cache_data
            result = f(*args, **kwargs)
            forecast_cache[key] = (current_time, result)
            return result
        return decorated_function
    return decorator


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------

@app.errorhandler(404)
def page_not_found(e):
    return render_template('errors/404.html', title=_('Page Not Found')), 404


@app.errorhandler(500)
def server_error(e):
    return render_template('errors/500.html', title=_('Server Error')), 500


# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(
        os.path.join(app.root_path, 'static'), 'favicon.ico',
        mimetype='image/vnd.microsoft.icon',
    )


# ---------------------------------------------------------------------------
# Session teardown
# ---------------------------------------------------------------------------

@app.teardown_appcontext
def shutdown_session(exception=None):
    db.session.remove()


# ---------------------------------------------------------------------------
# Rate-limit headers (applied to every response)
# ---------------------------------------------------------------------------

@app.after_request
def add_rate_limit_headers(response):
    headers = getattr(request, '_rate_limit_headers', None)
    if not headers:
        from flask import g
        headers = getattr(g, 'rate_limit_headers', None)
    if headers:
        for k, v in headers.items():
            response.headers[k] = str(v)
    return response


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    ssl_cert = app.config.get('SSL_CERTFILE')
    ssl_key = app.config.get('SSL_KEYFILE')
    ssl_context = (ssl_cert, ssl_key) if ssl_cert and ssl_key else None

    try:
        app.run(
            host='0.0.0.0',
            port=5000,
            debug=app.config.get('DEBUG', False),
            threaded=True,
            ssl_context=ssl_context,
        )
    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        mqtt_ingestion.stop()
