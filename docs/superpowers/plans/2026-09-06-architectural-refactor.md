# Architectural Refactor: TCP Removal + Frontend Modernization

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove all legacy TCP code, fix the broken SSE real-time pipeline, and modernize the entire frontend with Tailwind CSS, Lucide icons, and Chart.js v4.

**Architecture:** Pure MQTT ingestion model (all TCP paths deleted). SSE broker bridged to MQTT ingestion for live dashboard updates. Jinja2 templates rebuilt with Tailwind CSS utility classes, Lucide icons, and standardized Chart.js v4 charts.

**Tech Stack:** Flask, SQLAlchemy, TimescaleDB, Redis, Tailwind CSS (CDN), Lucide Icons (CDN), Chart.js v4, Vanilla JS (no jQuery)

---

## File Structure

### Files to DELETE
| File | Reason |
|------|--------|
| `utils/tcp_client.py` | Orphaned — zero imports in codebase |
| `utils/__pycache__/tcp_client.cpython-311.pyc` | Cache of dead code |
| `k114_tcp_reader.py` (root) | Legacy duplicate of `models/k114_tcp_reader.py` |
| `test_k114_tcp_reader.py` | Tests only the legacy root-level reader |
| `data/config.json` | Legacy config, app uses `config.py` |
| `models/tank_sensor_connection.py` | TCP connection manager, replaced by MQTT |
| `models/tank_monitor.py` | TCP monitoring thread, replaced by MQTT ingestion |
| `models/tank_monitor_manager.py` | Manages TCP monitors, bypassed by MQTT ingestion |
| `static/css/admin.css` | Replaced by Tailwind |
| `static/css/alarms.css` | Replaced by Tailwind |
| `static/css/dashboard.css` | Replaced by Tailwind |
| `static/css/tank_history.css` | Replaced by Tailwind |
| `static/css/tank_visualization.css` | Replaced by Tailwind |
| `static/css/rtl.css` | Replaced by Tailwind RTL plugin |
| `static/css/settings.css` | Replaced by Tailwind |
| `static/css/reports.css` | Replaced by Tailwind |
| `static/css/main.css` | Replaced by Tailwind |
| `static/js/socket.js` | Dead Socket.IO code |

### Files to MODIFY
| File | Changes |
|------|---------|
| `models/database.py` | Remove `host`, `tcp_port` columns from Tank |
| `models/tank_config.py` | Remove `host`, `tcp_port` fields |
| `config.py` | Remove `HOST`, `TCP_PORT`, `DEVICE_ADDRESS` |
| `forms.py` | Remove TCP fields from TankForm |
| `admin.py` | Remove TCP form handling, remove broken SocketIO imports |
| `blueprints/admin/utils.py` | Remove broken SocketIO import |
| `k114_reader.py` | Remove TCP CLI support |
| `services/mqtt_ingestion.py` | Add `sse_broker.publish()` after batch flush |
| `app.py` | Remove unused imports, verify SSE endpoint |
| `requirements.txt` | No changes needed (Flask-SocketIO already absent) |
| `templates/base.html` | Replace Bootstrap→Tailwind, Font Awesome→Lucide |
| `templates/admin/base.html` | Replace Bootstrap→Tailwind, remove Socket.IO JS |
| `templates/dashboard.html` | Full rebuild with Tailwind + Chart.js v4 |
| `templates/tank_detail.html` | Full rebuild with Tailwind + Chart.js v4 |
| `templates/tank_history.html` | Rebuild with Tailwind |
| `templates/alarms.html` | Rebuild with Tailwind |
| `templates/index.html` | Rebuild with Tailwind |
| All `templates/admin/*.html` | Rebuild with Tailwind |
| `static/js/dashboard.js` | Rewrite for Chart.js v4 |
| `static/js/tank_detail.js` | Rewrite for Chart.js v4 |
| `static/js/tank_history.js` | Rewrite for Chart.js v4 |
| `static/js/alarms.js` | Rewrite for Chart.js v4 |
| `static/js/main.js` | Replace with Tailwind-compatible utilities |
| `static/js/charts.js` | Rewrite for Chart.js v4 |
| `static/js/history.js` | Rewrite for Tailwind |
| `static/js/tank_monitor.js` | Delete (TCP monitor JS) |
| `static/css/style.css` | Replace with Tailwind base styles |

### Files to CREATE
| File | Purpose |
|------|---------|
| `static/js/sse-client.js` | Shared SSE connection manager |
| `static/js/chart-factory.js` | Shared Chart.js v4 factory with defaults |

---

## Slice 1: TCP Cleanup

### Task 1: Delete Orphaned TCP Files

**Files:**
- Delete: `utils/tcp_client.py`
- Delete: `utils/__pycache__/tcp_client.cpython-311.pyc`
- Delete: `k114_tcp_reader.py` (root level)
- Delete: `test_k114_tcp_reader.py`
- Delete: `data/config.json`

- [ ] **Step 1: Delete orphaned files**

```bash
rm -f utils/tcp_client.py utils/__pycache__/tcp_client.cpython-311.pyc
rm -f k114_tcp_reader.py test_k114_tcp_reader.py
rm -f data/config.json
```

- [ ] **Step 2: Verify no imports reference deleted files**

Run: `grep -r "tcp_client\|k114_tcp_reader\|config.json" --include="*.py" --include="*.html" . | grep -v __pycache__ | grep -v ".pyc"`
Expected: Only `models/k114_tcp_reader.py` (the production version) should appear.

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "chore: delete orphaned TCP client files"
```

---

### Task 2: Remove TCP Columns from Database

**Files:**
- Modify: `models/database.py:193-196`

- [ ] **Step 1: Create Alembic migration**

Run: `flask db migrate -m "remove_tcp_columns_from_tank"`
This auto-generates a migration file. If Flask-Migrate is not set up, create the migration manually.

- [ ] **Step 2: Edit the generated migration file**

Find the generated migration in `migrations/versions/`. Edit it to:

```python
"""remove tcp columns from tank

Revision ID: <auto-generated>
Revises: <previous>
Create Date: <auto-generated>
"""
from alembic import op
import sqlalchemy as sa

revision = '<auto-generated>'
down_revision = '<previous>'
branch_labels = None
depends_on = None

def upgrade():
    # Step 1: Make columns nullable first (safe deploy)
    op.alter_column('tank', 'host', nullable=True)
    op.alter_column('tank', 'tcp_port', nullable=True)
    # Step 2: Drop columns
    op.drop_column('tank', 'host')
    op.drop_column('tank', 'tcp_port')

def downgrade():
    op.add_column('tank', sa.Column('host', sa.String(100), nullable=False))
    op.add_column('tank', sa.Column('tcp_port', sa.Integer, server_default='2000'))
```

- [ ] **Step 3: Update Tank model in database.py**

Remove lines 193-194 (`host` and `tcp_port` columns). Keep `device_address` and `connection_mode` as they are MQTT-relevant.

```python
# Connection settings (lines 192-196 become):
device_address = db.Column(db.Integer, default=1)
connection_mode = db.Column(db.String(20), default='mqtt')
```

- [ ] **Step 4: Run migration**

Run: `flask db upgrade`
Expected: Migration applies without errors.

- [ ] **Step 5: Verify Tank model**

Run: `python -c "from models.database import Tank; print([c.name for c in Tank.__table__.columns])"`
Expected: `host` and `tcp_port` should NOT be in the list.

- [ ] **Step 6: Commit**

```bash
git add models/database.py migrations/
git commit -m "feat: remove TCP columns from Tank model"
```

---

### Task 3: Remove TCP from Config and Forms

**Files:**
- Modify: `config.py:62-64`
- Modify: `forms.py:85-86`

- [ ] **Step 1: Remove TCP config variables from config.py**

Delete lines 62-64:
```python
# DELETE these lines:
HOST = os.environ.get('FUEL_TANK_HOST') or 'localhost'
TCP_PORT = int(os.environ.get('FUEL_TANK_TCP_PORT') or 2000)
DEVICE_ADDRESS = int(os.environ.get('FUEL_TANK_DEVICE_ADDRESS') or 1)
```

- [ ] **Step 2: Remove TCP fields from TankForm in forms.py**

Delete lines 85-87:
```python
# DELETE these lines:
host = StringField('Host/IP Address', validators=[DataRequired()])
tcp_port = IntegerField('TCP Port', validators=[DataRequired(), NumberRange(min=1, max=65535)])
device_address = IntegerField('Device Address', validators=[DataRequired(), NumberRange(min=1, max=255)])
```

- [ ] **Step 3: Commit**

```bash
git add config.py forms.py
git commit -m "feat: remove TCP config and form fields"
```

---

### Task 4: Remove TCP from Admin Routes and Templates

**Files:**
- Modify: `admin.py:2487-2488, 2541-2542, 2573-2575, 2597-2598, 2765, 3900-3902, 3922-3924`
- Modify: `templates/admin/tank_form.html:64-70`
- Modify: `templates/admin/tank_detail.html:109-114`
- Modify: `templates/admin/create_tank.html:53-59`
- Modify: `templates/admin/edit_tank.html:53-59`

- [ ] **Step 1: Remove TCP fields from tank create handler in admin.py**

In the tank create POST handler (around line 2483-2503), remove the `host` and `tcp_port` assignments:

```python
# In the Tank() constructor, REMOVE these lines:
host = request.form.get('host'),
tcp_port = request.form.get('tcp_port'),
```

- [ ] **Step 2: Remove TCP fields from tank edit handler in admin.py**

Around lines 2573-2575, remove:
```python
# DELETE these lines:
tank.host = host
tank.tcp_port = int(tcp_port) if tcp_port else 2000
```

Also remove the variable extraction for `host` and `tcp_port` from request.form (around lines 2541-2542).

- [ ] **Step 3: Remove TCP from API response in admin.py**

Around line 2765, remove `'tcp_port': tank.tcp_port` from the response dict.

- [ ] **Step 4: Remove TCP fields from form classes in admin.py**

In `CreateTankForm` (line 3900-3901) and `EditTankForm` (line 3922-3923), delete:
```python
host = StringField('Host/IP Address', validators=[DataRequired(), Length(max=100)])
tcp_port = IntegerField('TCP Port', default=2000)
```

- [ ] **Step 5: Remove TCP form fields from admin templates**

In each of the 4 admin templates, remove the TCP Port form field HTML. Example for `templates/admin/tank_form.html` lines 64-70:

```html
<!-- DELETE this entire block: -->
<div class="mb-3">
    <label for="tcp_port" class="form-label">TCP Port *</label>
    <input type="number" class="form-control" id="tcp_port" name="tcp_port" value="{{ tank.tcp_port if tank else 2000 }}" required>
</div>
```

Repeat for `tank_detail.html` (lines 113-114 — the TCP Port display row), `create_tank.html` (lines 53-59), and `edit_tank.html` (lines 53-59).

- [ ] **Step 6: Commit**

```bash
git add admin.py templates/admin/
git commit -m "feat: remove TCP fields from admin routes and templates"
```

---

### Task 5: Delete TCP Monitor Files and Clean Up

**Files:**
- Delete: `models/tank_sensor_connection.py`
- Delete: `models/tank_monitor.py`
- Delete: `models/tank_monitor_manager.py`
- Delete: `static/js/tank_monitor.js`
- Modify: `models/tank_config.py` (remove `host`, `tcp_port` fields)
- Modify: `k114_reader.py` (remove TCP CLI support)
- Modify: `app.py` (remove TankMonitorManager import/usage)

- [ ] **Step 1: Check if TankMonitorManager is used in app.py**

Run: `grep -n "tank_monitor_manager\|TankMonitorManager\|tank_monitor\|TankMonitor" app.py`
If any references exist, remove them. The MQTT ingestion service bypasses this entirely.

- [ ] **Step 2: Remove TCP monitor imports and usage from app.py**

Remove any lines like:
```python
from models.tank_monitor_manager import TankMonitorManager
```
And any initialization/usage of `tank_monitor_manager` in app startup.

- [ ] **Step 3: Remove TCP fields from TankConfig**

In `models/tank_config.py`, remove `self.host`, `self.tcp_port` from `__init__` (lines 32-33), `from_database` (lines 62-63), `to_dict` (lines 114-115), and `from_dict`/`from_json` methods.

- [ ] **Step 4: Remove TCP CLI support from k114_reader.py**

Remove the TCP-related argparse arguments (lines 624-628, 642-646) and the TCP connection branch (lines 727-735) from the `main()` function.

- [ ] **Step 5: Delete TCP monitor files**

```bash
rm -f models/tank_sensor_connection.py models/tank_monitor.py models/tank_monitor_manager.py
rm -f static/js/tank_monitor.js
```

- [ ] **Step 6: Verify no remaining TCP imports**

Run: `grep -rn "import socket\|socket\.socket\|K114TCPReader\|TankSensorConnection\|TankMonitor\|TankMonitorManager" --include="*.py" .`
Expected: Only `models/k114_reader.py` (base class, serial-only) and `models/k114_tcp_reader.py` (which is no longer imported by anything) should appear.

- [ ] **Step 7: Also delete models/k114_tcp_reader.py**

Since `tank_sensor_connection.py` was the only production importer and it's now deleted:
```bash
rm -f models/k114_tcp_reader.py
```

- [ ] **Step 8: Verify app starts**

Run: `python -c "from app import create_app; app = create_app(); print('App created successfully')"`
Expected: No import errors.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "feat: remove all TCP monitoring code, pure MQTT ingestion"
```

---

## Slice 2: Live Dashboard (SSE Fix)

### Task 6: Bridge MQTT Ingestion to SSE Broker

**Files:**
- Modify: `services/mqtt_ingestion.py` (add SSE publish after batch flush)

- [ ] **Step 1: Add SSE broker import to mqtt_ingestion.py**

Add to the import section (after line 25):

```python
# Add this import (will be created in app.py context):
import json as json_mod
from datetime import datetime as dt_mod
```

Note: The `sse_broker` is instantiated in `app.py`. We need to access it from the MQTT service. The cleanest approach is to pass it in or import from app.

- [ ] **Step 2: Modify MqttIngestionService constructor to accept sse_broker**

In `__init__` (line 156), add an `sse_broker` parameter:

```python
def __init__(
    self,
    app,
    broker: str,
    port: int = 1883,
    username: str = None,
    password: str = None,
    ca_cert: str = None,
    client_cert: str = None,
    client_key: str = None,
    sse_broker=None,  # ADD THIS
):
```

And store it:
```python
self._sse_broker = sse_broker  # ADD THIS after line 167
```

- [ ] **Step 3: Add SSE publish call after batch flush**

In `_flush_batch` method (after line 483 `logger.info("Flushed %d measurements to DB", len(to_flush))`), add:

```python
# Publish to SSE broker for real-time frontend updates
if self._sse_broker:
    for m in to_flush:
        try:
            self._sse_broker.publish(m.tank_id, {
                'event': 'measurement',
                'tank_id': m.tank_id,
                'timestamp': m.timestamp.isoformat() if m.timestamp else None,
                'pressure': m.pressure,
                'temperature': m.temperature,
                'level': m.level,
                'volume': m.volume,
                'flow_rate': m.flow_rate,
                'fill_percent': m.fill_percent,
                'status': m.status,
            })
        except Exception as exc:
            logger.warning("SSE publish failed for tank %s: %s", m.tank_id, exc)
```

- [ ] **Step 4: Pass sse_broker when creating MqttIngestionService in app.py**

In `app.py`, find where `MqttIngestionService` is instantiated and add `sse_broker=sse_broker`:

```python
mqtt_service = MqttIngestionService(
    app,
    broker=app.config['MQTT_BROKER'],
    port=app.config['MQTT_PORT'],
    username=app.config.get('MQTT_USER'),
    password=app.config.get('MQTT_PASS'),
    ca_cert=app.config.get('MQTT_CA_CERT'),
    client_cert=app.config.get('MQTT_CLIENT_CERT'),
    client_key=app.config.get('MQTT_CLIENT_KEY'),
    sse_broker=sse_broker,  # ADD THIS
)
```

- [ ] **Step 5: Commit**

```bash
git add services/mqtt_ingestion.py app.py
git commit -m "feat: bridge MQTT ingestion to SSE broker for live updates"
```

---

### Task 7: Remove Broken SocketIO References

**Files:**
- Modify: `admin.py:141-144`
- Modify: `blueprints/admin/utils.py:67-68`
- Modify: `templates/admin/base.html:461-573`

- [ ] **Step 1: Remove broken SocketIO import in admin.py**

Around line 141-144, replace:
```python
# DELETE:
try:
    from app import socketio
    socketio.emit('new_activity', {
```

Replace with SSE-compatible or simply remove the emit:
```python
# REPLACE WITH (just log, no real-time emit for admin activity):
logger.info("New activity: %s", activity_data)
```

Or remove the entire try/except block if the emit is not critical.

- [ ] **Step 2: Remove broken SocketIO import in blueprints/admin/utils.py**

Around line 67-68, same pattern — remove the `from app import socketio` and the `socketio.emit()` call.

- [ ] **Step 3: Remove Socket.IO client code from admin/base.html**

Remove lines 461-573 (the entire Socket.IO client initialization and event handlers block). This code tries to use `io()` which is undefined since no Socket.IO library is loaded.

- [ ] **Step 4: Commit**

```bash
git add admin.py blueprints/admin/utils.py templates/admin/base.html
git commit -m "fix: remove broken Socket.IO references"
```

---

### Task 8: Verify SSE Pipeline End-to-End

- [ ] **Step 1: Test SSE broker publish/subscribe**

Run:
```python
python -c "
from app import create_app, sse_broker
app = create_app()
with app.app_context():
    q = sse_broker.subscribe(1)
    sse_broker.publish(1, {'event': 'test', 'level': 50.0})
    print('Queue after publish:', q)
    sse_broker.unsubscribe(1, q)
"
```
Expected: Queue contains `{'event': 'test', 'level': 50.0}`.

- [ ] **Step 2: Verify MQTT ingestion imports work**

Run: `python -c "from services.mqtt_ingestion import MqttIngestionService; print('Import OK')"`
Expected: No errors.

- [ ] **Step 3: Commit verification (if any fixes needed)**

```bash
git add -A
git commit -m "fix: SSE pipeline verification and minor fixes"
```

---

## Slice 3: Design System

### Task 9: Set Up Tailwind CSS and Lucide Icons

**Files:**
- Modify: `templates/base.html`
- Modify: `templates/admin/base.html`

- [ ] **Step 1: Rewrite templates/base.html with Tailwind**

Replace the entire file with:

```html
<!DOCTYPE html>
<html lang="en" class="h-full">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="csrf-token" content="{{ csrf_token() }}">
    <title>{% block title %}Fuel Monitoring{% endblock %}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/lucide@latest"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
    <script>
        tailwind.config = {
            theme: {
                extend: {
                    colors: {
                        primary: { 50: '#eff6ff', 100: '#dbeafe', 200: '#bfdbfe', 300: '#93c5fd', 400: '#60a5fa', 500: '#3b82f6', 600: '#2563eb', 700: '#1d4ed8', 800: '#1e40af', 900: '#1e3a8a' },
                        fuel: { light: '#d1fae5', DEFAULT: '#10b981', dark: '#065f46' },
                    }
                }
            }
        }
    </script>
    <style>
        [x-cloak] { display: none !important; }
    </style>
    {% block styles %}{% endblock %}
</head>
<body class="h-full bg-gray-50 text-gray-900 antialiased">
    <div class="min-h-full">
        {% block navbar %}
        <nav class="bg-white shadow-sm border-b border-gray-200">
            <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                <div class="flex justify-between h-16">
                    <div class="flex items-center gap-8">
                        <a href="{{ url_for('dashboard') }}" class="flex items-center gap-2">
                            <i data-lucide="fuel" class="h-6 w-6 text-primary-600"></i>
                            <span class="font-bold text-lg">Fuel Monitor</span>
                        </a>
                        <div class="hidden md:flex items-center gap-1">
                            <a href="{{ url_for('dashboard') }}" class="px-3 py-2 rounded-md text-sm font-medium text-gray-700 hover:bg-gray-100 hover:text-primary-600 transition">
                                <i data-lucide="layout-dashboard" class="h-4 w-4 inline mr-1"></i> Dashboard
                            </a>
                            <a href="{{ url_for('tank_history_page') }}" class="px-3 py-2 rounded-md text-sm font-medium text-gray-700 hover:bg-gray-100 hover:text-primary-600 transition">
                                <i data-lucide="history" class="h-4 w-4 inline mr-1"></i> History
                            </a>
                            <a href="{{ url_for('alarms_page') }}" class="px-3 py-2 rounded-md text-sm font-medium text-gray-700 hover:bg-gray-100 hover:text-primary-600 transition">
                                <i data-lucide="bell" class="h-4 w-4 inline mr-1"></i> Alarms
                            </a>
                        </div>
                    </div>
                    <div class="flex items-center gap-4">
                        {% if current_user.is_authenticated %}
                        <span class="text-sm text-gray-500">{{ current_user.username }}</span>
                        <a href="{{ url_for('auth.logout') }}" class="text-sm text-gray-500 hover:text-red-600 transition">Logout</a>
                        {% endif %}
                    </div>
                </div>
            </div>
        </nav>
        {% endblock %}

        <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
            {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
            <div class="mb-6 space-y-2">
                {% for category, message in messages %}
                <div class="rounded-lg px-4 py-3 text-sm
                    {% if category == 'error' %}bg-red-50 text-red-800 border border-red-200
                    {% elif category == 'success' %}bg-green-50 text-green-800 border border-green-200
                    {% else %}bg-blue-50 text-blue-800 border border-blue-200{% endif %}">
                    {{ message }}
                </div>
                {% endfor %}
            </div>
            {% endif %}
            {% endwith %}

            {% block content %}{% endblock %}
        </main>
    </div>

    <script>lucide.createIcons();</script>
    {% block scripts %}{% endblock %}
</body>
</html>
```

- [ ] **Step 2: Rewrite templates/admin/base.html with Tailwind**

Replace the entire file with a Tailwind sidebar layout. Keep the same navigation structure but use Tailwind utility classes. Remove all Socket.IO JavaScript code. Example structure:

```html
<!DOCTYPE html>
<html lang="en" class="h-full">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="csrf-token" content="{{ csrf_token() }}">
    <title>{% block title %}Admin - Fuel Monitor{% endblock %}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/lucide@latest"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
    <script>
        tailwind.config = { /* same as base.html */ }
    </script>
    {% block styles %}{% endblock %}
</head>
<body class="h-full bg-gray-50">
    <div class="flex h-full">
        <!-- Sidebar -->
        <aside class="w-64 bg-gray-900 text-white flex flex-col">
            <div class="p-4 border-b border-gray-800">
                <a href="{{ url_for('admin.admin_dashboard') }}" class="flex items-center gap-2">
                    <i data-lucide="shield" class="h-6 w-6 text-primary-400"></i>
                    <span class="font-bold">Admin Panel</span>
                </a>
            </div>
            <nav class="flex-1 p-4 space-y-1">
                <a href="{{ url_for('admin.admin_dashboard') }}" class="flex items-center gap-3 px-3 py-2 rounded-md text-sm hover:bg-gray-800 transition">
                    <i data-lucide="layout-dashboard" class="h-4 w-4"></i> Dashboard
                </a>
                <a href="{{ url_for('admin.admin_tanks') }}" class="flex items-center gap-3 px-3 py-2 rounded-md text-sm hover:bg-gray-800 transition">
                    <i data-lucide="database" class="h-4 w-4"></i> Tanks
                </a>
                <a href="{{ url_for('admin.admin_sites') }}" class="flex items-center gap-3 px-3 py-2 rounded-md text-sm hover:bg-gray-800 transition">
                    <i data-lucide="map-pin" class="h-4 w-4"></i> Sites
                </a>
                <a href="{{ url_for('admin.admin_companies') }}" class="flex items-center gap-3 px-3 py-2 rounded-md text-sm hover:bg-gray-800 transition">
                    <i data-lucide="building-2" class="h-4 w-4"></i> Companies
                </a>
                <a href="{{ url_for('admin.admin_users') }}" class="flex items-center gap-3 px-3 py-2 rounded-md text-sm hover:bg-gray-800 transition">
                    <i data-lucide="users" class="h-4 w-4"></i> Users
                </a>
                <a href="{{ url_for('admin.admin_alarms') }}" class="flex items-center gap-3 px-3 py-2 rounded-md text-sm hover:bg-gray-800 transition">
                    <i data-lucide="bell" class="h-4 w-4"></i> Alarms
                </a>
            </nav>
            <div class="p-4 border-t border-gray-800">
                <a href="{{ url_for('dashboard') }}" class="flex items-center gap-3 px-3 py-2 rounded-md text-sm hover:bg-gray-800 transition">
                    <i data-lucide="arrow-left" class="h-4 w-4"></i> Back to Dashboard
                </a>
            </div>
        </aside>

        <!-- Main content -->
        <div class="flex-1 flex flex-col overflow-hidden">
            <header class="bg-white shadow-sm border-b border-gray-200 px-6 py-4">
                <h1 class="text-xl font-semibold">{% block page_title %}{% endblock %}</h1>
            </header>
            <main class="flex-1 overflow-y-auto p-6">
                {% block content %}{% endblock %}
            </main>
        </div>
    </div>

    <script>lucide.createIcons();</script>
    {% block scripts %}{% endblock %}
</body>
</html>
```

- [ ] **Step 3: Commit**

```bash
git add templates/base.html templates/admin/base.html
git commit -m "feat: set up Tailwind CSS and Lucide icons base templates"
```

---

### Task 10: Create Shared JavaScript Modules

**Files:**
- Create: `static/js/sse-client.js`
- Create: `static/js/chart-factory.js`

- [ ] **Step 1: Create SSE client module**

```javascript
// static/js/sse-client.js — Shared SSE connection manager
class SSEClient {
    constructor(url, options = {}) {
        this.url = url;
        this.reconnectDelay = options.reconnectDelay || 3000;
        this.onMessage = options.onMessage || (() => {});
        this.onConnect = options.onConnect || (() => {});
        this.onError = options.onError || (() => {});
        this._eventSource = null;
        this._reconnectTimer = null;
    }

    connect() {
        if (this._eventSource) this._eventSource.close();
        this._eventSource = new EventSource(this.url);

        this._eventSource.onopen = () => {
            console.log('[SSE] Connected to', this.url);
            this.onConnect();
        };

        this._eventSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.event === 'connected') return;
                if (data.event === 'error') {
                    console.warn('[SSE] Server error:', data.message);
                    return;
                }
                this.onMessage(data);
            } catch (e) {
                console.warn('[SSE] Parse error:', e);
            }
        };

        this._eventSource.onerror = () => {
            console.warn('[SSE] Connection lost, reconnecting in', this.reconnectDelay, 'ms');
            this._eventSource.close();
            this.onError();
            this._reconnectTimer = setTimeout(() => this.connect(), this.reconnectDelay);
        };
    }

    disconnect() {
        if (this._reconnectTimer) clearTimeout(this._reconnectTimer);
        if (this._eventSource) this._eventSource.close();
    }
}
```

- [ ] **Step 2: Create Chart.js v4 factory**

```javascript
// static/js/chart-factory.js — Shared Chart.js v4 configuration factory
const ChartFactory = {
    defaultColors: {
        primary: '#3b82f6',
        success: '#10b981',
        danger: '#ef4444',
        warning: '#f59e0b',
        info: '#06b6d4',
        purple: '#8b5cf6',
    },

    createLineChart(ctx, config) {
        return new Chart(ctx, {
            type: 'line',
            data: config.data,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { intersect: false, mode: 'index' },
                plugins: {
                    legend: { position: 'top', labels: { usePointStyle: true, padding: 16 } },
                    tooltip: {
                        backgroundColor: 'rgba(0,0,0,0.8)',
                        padding: 12,
                        titleFont: { size: 13 },
                        bodyFont: { size: 12 },
                    },
                },
                scales: {
                    x: {
                        type: 'time',
                        time: { tooltipFormat: 'PPpp' },
                        grid: { display: false },
                    },
                    y: {
                        beginAtZero: config.beginAtZero !== false,
                        grid: { color: 'rgba(0,0,0,0.05)' },
                    },
                },
                ...config.options,
            },
        });
    },

    createBarChart(ctx, config) {
        return new Chart(ctx, {
            type: 'bar',
            data: config.data,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: 'top', labels: { usePointStyle: true, padding: 16 } },
                },
                scales: {
                    x: { grid: { display: false } },
                    y: { beginAtZero: true, grid: { color: 'rgba(0,0,0,0.05)' } },
                },
                ...config.options,
            },
        });
    },

    formatTime(date) {
        return new Date(date).toLocaleString();
    },

    pushData(chart, label, value, maxPoints = 100) {
        chart.data.labels.push(label);
        chart.data.datasets.forEach(ds => ds.data.push(value));
        if (chart.data.labels.length > maxPoints) {
            chart.data.labels.shift();
            chart.data.datasets.forEach(ds => ds.data.shift());
        }
        chart.update('none');
    },
};
```

- [ ] **Step 3: Commit**

```bash
git add static/js/sse-client.js static/js/chart-factory.js
git commit -m "feat: add shared SSE client and Chart.js v4 factory modules"
```

---

### Task 11: Remove Old CSS Files

**Files:**
- Delete: `static/css/admin.css`, `static/css/alarms.css`, `static/css/dashboard.css`, `static/css/tank_history.css`, `static/css/tank_visualization.css`, `static/css/rtl.css`, `static/css/settings.css`, `static/css/reports.css`, `static/css/main.css`
- Modify: `static/css/style.css` (keep as minimal Tailwind overrides)

- [ ] **Step 1: Delete old CSS files**

```bash
rm -f static/css/admin.css static/css/alarms.css static/css/dashboard.css
rm -f static/css/tank_history.css static/css/tank_visualization.css
rm -f static/css/rtl.css static/css/settings.css static/css/reports.css static/css/main.css
```

- [ ] **Step 2: Replace style.css with minimal Tailwind overrides**

```css
/* static/css/style.css — Minimal overrides for Tailwind defaults */
.chart-container { position: relative; height: 300px; }
.chart-container canvas { max-height: 100%; }

/* Tank visualization */
.tank-visual { position: relative; width: 100%; max-width: 120px; border: 2px solid #d1d5db; border-radius: 4px; overflow: hidden; }
.tank-fill { position: absolute; bottom: 0; left: 0; right: 0; transition: height 0.5s ease; }
```

- [ ] **Step 3: Commit**

```bash
git add -A static/css/
git commit -m "chore: remove old CSS files, keep minimal Tailwind overrides"
```

---

## Slice 4: Dashboard Page

### Task 12: Rebuild Dashboard Template

**Files:**
- Rewrite: `templates/dashboard.html`

- [ ] **Step 1: Rewrite dashboard.html**

Replace the entire template with Tailwind-based layout. Use the shared `sse-client.js` and `chart-factory.js` modules.

Key sections:
1. **Stat cards row** — Total Tanks, Connected, Alarms, Total Volume (each with Lucide icon)
2. **Tank status grid** — Cards showing each tank with SVG visualization, level bar, key metrics
3. **Main chart** — Real-time fuel levels for all tanks (Chart.js v4 line chart)
4. **Recent alarms table** — Last 5 alarms with severity badges

```html
{% extends "base.html" %}
{% block title %}Dashboard - Fuel Monitor{% endblock %}

{% block content %}
<div class="space-y-6">
    <!-- Stat Cards -->
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div class="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
            <div class="flex items-center justify-between">
                <div>
                    <p class="text-sm font-medium text-gray-500">Total Tanks</p>
                    <p class="text-2xl font-bold text-gray-900" id="stat-total">{{ tanks|length }}</p>
                </div>
                <div class="p-3 bg-primary-50 rounded-lg">
                    <i data-lucide="database" class="h-6 w-6 text-primary-600"></i>
                </div>
            </div>
        </div>
        <div class="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
            <div class="flex items-center justify-between">
                <div>
                    <p class="text-sm font-medium text-gray-500">Connected</p>
                    <p class="text-2xl font-bold text-green-600" id="stat-connected">{{ connected_count }}</p>
                </div>
                <div class="p-3 bg-green-50 rounded-lg">
                    <i data-lucide="wifi" class="h-6 w-6 text-green-600"></i>
                </div>
            </div>
        </div>
        <div class="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
            <div class="flex items-center justify-between">
                <div>
                    <p class="text-sm font-medium text-gray-500">Active Alarms</p>
                    <p class="text-2xl font-bold text-red-600" id="stat-alarms">{{ alarm_count }}</p>
                </div>
                <div class="p-3 bg-red-50 rounded-lg">
                    <i data-lucide="alert-triangle" class="h-6 w-6 text-red-600"></i>
                </div>
            </div>
        </div>
        <div class="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
            <div class="flex items-center justify-between">
                <div>
                    <p class="text-sm font-medium text-gray-500">Total Volume</p>
                    <p class="text-2xl font-bold text-gray-900" id="stat-volume">{{ "%.1f"|format(total_volume) }} L</p>
                </div>
                <div class="p-3 bg-purple-50 rounded-lg">
                    <i data-lucide="droplets" class="h-6 w-6 text-purple-600"></i>
                </div>
            </div>
        </div>
    </div>

    <!-- Real-time Chart -->
    <div class="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
        <h2 class="text-lg font-semibold mb-4">Real-time Fuel Levels</h2>
        <div class="chart-container" style="height: 350px;">
            <canvas id="realtimeChart"></canvas>
        </div>
    </div>

    <!-- Tank Grid -->
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {% for tank in tanks %}
        <a href="{{ url_for('tank_detail_page', tank_id=tank.id) }}"
           class="block bg-white rounded-xl shadow-sm border border-gray-200 p-5 hover:shadow-md transition"
           data-tank-id="{{ tank.id }}">
            <div class="flex items-center justify-between mb-3">
                <h3 class="font-semibold text-gray-900">{{ tank.name }}</h3>
                <span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium
                    {% if tank.connection_status == 'connected' %}bg-green-100 text-green-800
                    {% else %}bg-red-100 text-red-800{% endif %}">
                    {{ tank.connection_status|capitalize }}
                </span>
            </div>
            <div class="flex items-end gap-4">
                <div class="flex-1">
                    <div class="tank-visual h-32">
                        <div class="tank-fill bg-primary-500" style="height: {{ tank.fill_percent|default(0) }}%"></div>
                    </div>
                </div>
                <div class="flex-1 space-y-1 text-sm">
                    <div class="flex justify-between"><span class="text-gray-500">Level</span><span class="font-medium" data-field="level">{{ "%.2f"|format(tank.level|default(0)) }} m</span></div>
                    <div class="flex justify-between"><span class="text-gray-500">Volume</span><span class="font-medium" data-field="volume">{{ "%.1f"|format(tank.volume|default(0)) }} L</span></div>
                    <div class="flex justify-between"><span class="text-gray-500">Fill</span><span class="font-medium" data-field="fill">{{ "%.0f"|format(tank.fill_percent|default(0)) }}%</span></div>
                    <div class="flex justify-between"><span class="text-gray-500">Temp</span><span class="font-medium" data-field="temp">{{ "%.1f"|format(tank.temperature|default(0)) }} C</span></div>
                </div>
            </div>
        </a>
        {% endfor %}
    </div>

    <!-- Recent Alarms -->
    <div class="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
        <h2 class="text-lg font-semibold mb-4">Recent Alarms</h2>
        <div class="overflow-x-auto">
            <table class="w-full text-sm">
                <thead><tr class="border-b border-gray-200 text-left text-gray-500">
                    <th class="pb-2 font-medium">Tank</th>
                    <th class="pb-2 font-medium">Type</th>
                    <th class="pb-2 font-medium">Level</th>
                    <th class="pb-2 font-medium">Time</th>
                </tr></thead>
                <tbody id="alarms-table" class="divide-y divide-gray-100">
                    {% for alarm in recent_alarms %}
                    <tr>
                        <td class="py-2">{{ alarm.tank_name }}</td>
                        <td class="py-2"><span class="px-2 py-0.5 rounded text-xs font-medium
                            {% if alarm.level == 'critical' %}bg-red-100 text-red-800
                            {% elif alarm.level == 'warning' %}bg-yellow-100 text-yellow-800
                            {% else %}bg-blue-100 text-blue-800{% endif %}">{{ alarm.type }}</span></td>
                        <td class="py-2">{{ alarm.value }}</td>
                        <td class="py-2 text-gray-500">{{ alarm.timestamp.strftime('%H:%M') }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
</div>
{% endblock %}

{% block scripts %}
<script src="{{ url_for('static', filename='js/sse-client.js') }}"></script>
<script src="{{ url_for('static', filename='js/chart-factory.js') }}"></script>
<script>
document.addEventListener('DOMContentLoaded', () => {
    lucide.createIcons();

    // Real-time chart
    const ctx = document.getElementById('realtimeChart').getContext('2d');
    const colors = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4'];
    const tankData = {};
    const chart = new Chart(ctx, {
        type: 'line',
        data: { labels: [], datasets: [] },
        options: {
            responsive: true, maintainAspectRatio: false,
            interaction: { intersect: false, mode: 'index' },
            scales: {
                x: { type: 'time', time: { tooltipFormat: 'HH:mm' }, grid: { display: false } },
                y: { beginAtZero: true, title: { display: true, text: 'Level (m)' }, grid: { color: 'rgba(0,0,0,0.05)' } },
            },
            plugins: { legend: { position: 'top', labels: { usePointStyle: true } } },
        },
    });

    // Initialize datasets for each tank
    {% for tank in tanks %}
    tankData[{{ tank.id }}] = { label: '{{ tank.name }}', data: [], borderColor: colors[{{ loop.index0 }} % colors.length] };
    chart.data.datasets.push(tankData[{{ tank.id }}]);
    {% endfor %}

    // SSE connection
    const sse = new SSEClient('/tank-updates', {
        onMessage: (data) => {
            if (!data.tank_id || !tankData[data.tank_id]) return;
            const now = new Date();
            chart.data.labels.push(now);
            tankData[data.tank_id].data.push(data.level);
            if (chart.data.labels.length > 100) {
                chart.data.labels.shift();
                chart.data.datasets.forEach(ds => ds.data.shift());
            }
            chart.update('none');

            // Update tank card
            const card = document.querySelector(`[data-tank-id="${data.tank_id}"]`);
            if (card) {
                const setField = (f, v) => { const el = card.querySelector(`[data-field="${f}"]`); if (el) el.textContent = v; };
                setField('level', data.level?.toFixed(2) + ' m');
                setField('volume', data.volume?.toFixed(1) + ' L');
                setField('fill', data.fill_percent?.toFixed(0) + '%');
                setField('temp', data.temperature?.toFixed(1) + ' C');
            }
        }
    });
    sse.connect();
});
</script>
{% endblock %}
```

- [ ] **Step 2: Commit**

```bash
git add templates/dashboard.html
git commit -m "feat: rebuild dashboard with Tailwind CSS and real-time SSE"
```

---

### Task 13: Rewrite Dashboard JavaScript

**Files:**
- Rewrite: `static/js/dashboard.js`

- [ ] **Step 1: Rewrite dashboard.js**

The dashboard template now has inline SSE + chart logic (from Task 12). The external `dashboard.js` should be a lightweight supplement:

```javascript
// static/js/dashboard.js — Dashboard-specific helpers
// Core dashboard logic is inline in the template for SSE/chart coupling.
// This file provides utility functions used by the dashboard.

function formatNumber(num, decimals = 1) {
    if (num == null || isNaN(num)) return '--';
    return Number(num).toFixed(decimals);
}

function getStatusColor(status) {
    return status === 'connected' ? 'text-green-600' : 'text-red-600';
}

function getAlarmBadgeClass(level) {
    const classes = { critical: 'bg-red-100 text-red-800', warning: 'bg-yellow-100 text-yellow-800', info: 'bg-blue-100 text-blue-800' };
    return classes[level] || 'bg-gray-100 text-gray-800';
}
```

- [ ] **Step 2: Commit**

```bash
git add static/js/dashboard.js
git commit -m "refactor: simplify dashboard.js for Tailwind-based dashboard"
```

---

## Slice 5: Tank Detail Page

### Task 14: Rebuild Tank Detail Template

**Files:**
- Rewrite: `templates/tank_detail.html`

- [ ] **Step 1: Rewrite tank_detail.html**

Replace the entire template. Use Tailwind layout with:
- Breadcrumb navigation
- Tank info sidebar (sensor, gateway, connection status)
- Current status cards (level, volume, fill %, temperature, flow rate)
- Three Chart.js v4 charts (main level chart, temperature, flow rate)
- Time range selector buttons
- Recent alarms table
- SSE-powered live updates via `sse-client.js`

The template should extend `base.html` (not `admin/base.html`) and use the same Tailwind design system as the dashboard.

Key structure:

```html
{% extends "base.html" %}
{% block title %}{{ tank.name }} - Fuel Monitor{% endblock %}

{% block content %}
<nav class="flex items-center gap-2 text-sm text-gray-500 mb-6">
    <a href="{{ url_for('dashboard') }}" class="hover:text-primary-600">Dashboard</a>
    <i data-lucide="chevron-right" class="h-4 w-4"></i>
    <span class="text-gray-900 font-medium">{{ tank.name }}</span>
</nav>

<div class="grid grid-cols-1 lg:grid-cols-4 gap-6">
    <!-- Tank Info Sidebar -->
    <div class="lg:col-span-1 space-y-4">
        <div class="bg-white rounded-xl shadow-sm border p-5">
            <h2 class="font-semibold mb-3">Tank Info</h2>
            <dl class="space-y-2 text-sm">
                <div class="flex justify-between"><dt class="text-gray-500">Gateway</dt><dd class="font-mono text-xs">{{ tank.gateway_mac }}</dd></div>
                <div class="flex justify-between"><dt class="text-gray-500">Serial</dt><dd class="font-mono text-xs">{{ tank.sensor_serial_number }}</dd></div>
                <div class="flex justify-between"><dt class="text-gray-500">Status</dt><dd><span class="px-2 py-0.5 rounded-full text-xs font-medium {{ 'bg-green-100 text-green-800' if tank.connection_status == 'connected' else 'bg-red-100 text-red-800' }}">{{ tank.connection_status }}</span></dd></div>
                <div class="flex justify-between"><dt class="text-gray-500">Height</dt><dd>{{ tank.tank_height }} m</dd></div>
                <div class="flex justify-between"><dt class="text-gray-500">Diameter</dt><dd>{{ tank.tank_diameter }} m</dd></div>
            </dl>
        </div>

        <!-- Current Status -->
        <div class="bg-white rounded-xl shadow-sm border p-5">
            <h2 class="font-semibold mb-3">Current Status</h2>
            <div class="space-y-3">
                <div class="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                    <div class="flex items-center gap-2"><i data-lucide="gauge" class="h-4 w-4 text-primary-600"></i><span class="text-sm">Level</span></div>
                    <span class="font-semibold" id="current-level">{{ "%.3f"|format(tank.level|default(0)) }} m</span>
                </div>
                <div class="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                    <div class="flex items-center gap-2"><i data-lucide="droplets" class="h-4 w-4 text-primary-600"></i><span class="text-sm">Volume</span></div>
                    <span class="font-semibold" id="current-volume">{{ "%.1f"|format(tank.volume|default(0)) }} L</span>
                </div>
                <div class="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                    <div class="flex items-center gap-2"><i data-lucide="percent" class="h-4 w-4 text-primary-600"></i><span class="text-sm">Fill</span></div>
                    <span class="font-semibold" id="current-fill">{{ "%.0f"|format(tank.fill_percent|default(0)) }}%</span>
                </div>
                <div class="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                    <div class="flex items-center gap-2"><i data-lucide="thermometer" class="h-4 w-4 text-primary-600"></i><span class="text-sm">Temperature</span></div>
                    <span class="font-semibold" id="current-temp">{{ "%.1f"|format(tank.temperature|default(0)) }} C</span>
                </div>
                <div class="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                    <div class="flex items-center gap-2"><i data-lucide="activity" class="h-4 w-4 text-primary-600"></i><span class="text-sm">Flow Rate</span></div>
                    <span class="font-semibold" id="current-flow">{{ "%.2f"|format(tank.flow_rate|default(0)) }} L/h</span>
                </div>
            </div>
        </div>
    </div>

    <!-- Main Content -->
    <div class="lg:col-span-3 space-y-6">
        <!-- Time Range Selector -->
        <div class="flex items-center gap-2 flex-wrap">
            <button onclick="setRange(1)" class="range-btn px-3 py-1.5 text-sm rounded-lg border border-gray-300 hover:bg-primary-50 hover:border-primary-300 transition">1h</button>
            <button onclick="setRange(3)" class="range-btn px-3 py-1.5 text-sm rounded-lg border border-gray-300 hover:bg-primary-50 hover:border-primary-300 transition">3h</button>
            <button onclick="setRange(6)" class="range-btn px-3 py-1.5 text-sm rounded-lg border border-gray-300 hover:bg-primary-50 hover:border-primary-300 transition">6h</button>
            <button onclick="setRange(24)" class="range-btn px-3 py-1.5 text-sm rounded-lg border border-gray-300 bg-primary-50 border-primary-300 font-medium transition">24h</button>
            <button onclick="setRange(168)" class="range-btn px-3 py-1.5 text-sm rounded-lg border border-gray-300 hover:bg-primary-50 hover:border-primary-300 transition">7d</button>
            <button onclick="setRange(720)" class="range-btn px-3 py-1.5 text-sm rounded-lg border border-gray-300 hover:bg-primary-50 hover:border-primary-300 transition">30d</button>
        </div>

        <!-- Main Chart -->
        <div class="bg-white rounded-xl shadow-sm border p-5">
            <h3 class="font-semibold mb-4">Fuel Level</h3>
            <div style="height: 350px;"><canvas id="mainChart"></canvas></div>
        </div>

        <!-- Secondary Charts -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div class="bg-white rounded-xl shadow-sm border p-5">
                <h3 class="font-semibold mb-4">Temperature</h3>
                <div style="height: 200px;"><canvas id="tempChart"></canvas></div>
            </div>
            <div class="bg-white rounded-xl shadow-sm border p-5">
                <h3 class="font-semibold mb-4">Flow Rate</h3>
                <div style="height: 200px;"><canvas id="flowChart"></canvas></div>
            </div>
        </div>

        <!-- Recent Alarms -->
        <div class="bg-white rounded-xl shadow-sm border p-5">
            <h3 class="font-semibold mb-4">Recent Alarms</h3>
            <div id="alarms-list" class="space-y-2">
                {% for alarm in recent_alarms %}
                <div class="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                    <div class="flex items-center gap-3">
                        <span class="px-2 py-0.5 rounded text-xs font-medium {{ 'bg-red-100 text-red-800' if alarm.level == 'critical' else 'bg-yellow-100 text-yellow-800' if alarm.level == 'warning' else 'bg-blue-100 text-blue-800' }}">{{ alarm.type }}</span>
                        <span class="text-sm">{{ alarm.message }}</span>
                    </div>
                    <span class="text-xs text-gray-500">{{ alarm.timestamp.strftime('%H:%M') }}</span>
                </div>
                {% endfor %}
            </div>
        </div>
    </div>
</div>
{% endblock %}

{% block scripts %}
<script src="{{ url_for('static', filename='js/sse-client.js') }}"></script>
<script src="{{ url_for('static', filename='js/chart-factory.js') }}"></script>
<script>
const TANK_ID = {{ tank.id }};
let currentRange = 24;

// Initialize charts using ChartFactory
const mainCtx = document.getElementById('mainChart').getContext('2d');
const tempCtx = document.getElementById('tempChart').getContext('2d');
const flowCtx = document.getElementById('flowChart').getContext('2d');

const mainChart = new Chart(mainCtx, {
    type: 'line', data: { labels: [], datasets: [
        { label: 'Level (m)', data: [], borderColor: '#3b82f6', backgroundColor: 'rgba(59,130,246,0.1)', fill: true, tension: 0.3 },
    ]}, options: { responsive: true, maintainAspectRatio: false, scales: { x: { type: 'time', time: { tooltipFormat: 'HH:mm' }, grid: { display: false } }, y: { beginAtZero: true, grid: { color: 'rgba(0,0,0,0.05)' } } }, plugins: { legend: { display: false } } }
});

const tempChart = new Chart(tempCtx, {
    type: 'line', data: { labels: [], datasets: [
        { label: 'Temp (C)', data: [], borderColor: '#f59e0b', tension: 0.3 },
    ]}, options: { responsive: true, maintainAspectRatio: false, scales: { x: { type: 'time', grid: { display: false } }, y: { grid: { color: 'rgba(0,0,0,0.05)' } } }, plugins: { legend: { display: false } } }
});

const flowChart = new Chart(flowCtx, {
    type: 'line', data: { labels: [], datasets: [
        { label: 'Flow (L/h)', data: [], borderColor: '#10b981', tension: 0.3 },
    ]}, options: { responsive: true, maintainAspectRatio: false, scales: { x: { type: 'time', grid: { display: false } }, y: { beginAtZero: true, grid: { color: 'rgba(0,0,0,0.05)' } } }, plugins: { legend: { display: false } } }
});

// Load historical data
async function loadHistory(hours) {
    const resp = await fetch(`/api/tank/${TANK_ID}/history?hours=${hours}`);
    const data = await resp.json();
    if (!data.measurements) return;

    mainChart.data.labels = data.measurements.map(m => new Date(m.timestamp));
    mainChart.data.datasets[0].data = data.measurements.map(m => m.level);
    mainChart.update();

    tempChart.data.labels = data.measurements.map(m => new Date(m.timestamp));
    tempChart.data.datasets[0].data = data.measurements.map(m => m.temperature);
    tempChart.update();

    flowChart.data.labels = data.measurements.map(m => new Date(m.timestamp));
    flowChart.data.datasets[0].data = data.measurements.map(m => m.flow_rate);
    flowChart.update();
}

function setRange(hours) {
    currentRange = hours;
    document.querySelectorAll('.range-btn').forEach(b => { b.classList.remove('bg-primary-50', 'border-primary-300', 'font-medium'); });
    event.target.classList.add('bg-primary-50', 'border-primary-300', 'font-medium');
    loadHistory(hours);
}

// SSE live updates
const sse = new SSEClient(`/tank-updates?tank_id=${TANK_ID}`, {
    onMessage: (data) => {
        if (data.tank_id !== TANK_ID) return;
        const now = new Date();

        // Update status cards
        document.getElementById('current-level').textContent = data.level?.toFixed(3) + ' m';
        document.getElementById('current-volume').textContent = data.volume?.toFixed(1) + ' L';
        document.getElementById('current-fill').textContent = data.fill_percent?.toFixed(0) + '%';
        document.getElementById('current-temp').textContent = data.temperature?.toFixed(1) + ' C';
        document.getElementById('current-flow').textContent = data.flow_rate?.toFixed(2) + ' L/h';

        // Push to charts
        [mainChart, tempChart, flowChart].forEach(c => {
            c.data.labels.push(now);
            c.data.datasets[0].data.push(c === mainChart ? data.level : c === tempChart ? data.temperature : data.flow_rate);
            if (c.data.labels.length > 100) { c.data.labels.shift(); c.data.datasets[0].data.shift(); }
            c.update('none');
        });
    }
});

document.addEventListener('DOMContentLoaded', () => {
    lucide.createIcons();
    loadHistory(currentRange);
    sse.connect();
});
</script>
{% endblock %}
```

- [ ] **Step 2: Commit**

```bash
git add templates/tank_detail.html
git commit -m "feat: rebuild tank detail page with Tailwind and Chart.js v4"
```

---

### Task 15: Rewrite Tank Detail JavaScript

**Files:**
- Rewrite: `static/js/tank_detail.js`

- [ ] **Step 1: Rewrite tank_detail.js**

The core logic is inline in the template (Task 14). This external file provides reusable helpers:

```javascript
// static/js/tank_detail.js — Tank detail page helpers
// Core chart/SSE logic is inline in the template for tight coupling.

function updateTankField(fieldId, value, unit) {
    const el = document.getElementById(fieldId);
    if (el) el.textContent = (value != null ? value : '--') + (unit || '');
}

function addAlarmRow(containerId, alarm) {
    const container = document.getElementById(containerId);
    if (!container) return;
    const badge = alarm.level === 'critical' ? 'bg-red-100 text-red-800' : alarm.level === 'warning' ? 'bg-yellow-100 text-yellow-800' : 'bg-blue-100 text-blue-800';
    const html = `<div class="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
        <div class="flex items-center gap-3">
            <span class="px-2 py-0.5 rounded text-xs font-medium ${badge}">${alarm.type}</span>
            <span class="text-sm">${alarm.message || ''}</span>
        </div>
        <span class="text-xs text-gray-500">${new Date(alarm.timestamp).toLocaleTimeString()}</span>
    </div>`;
    container.insertAdjacentHTML('afterbegin', html);
    if (container.children.length > 10) container.lastElementChild.remove();
}
```

- [ ] **Step 2: Commit**

```bash
git add static/js/tank_detail.js
git commit -m "refactor: simplify tank_detail.js for Tailwind-based page"
```

---

## Slice 6: Remaining Pages

### Task 16: Rebuild Tank History Page

**Files:**
- Rewrite: `templates/tank_history.html`
- Rewrite: `static/js/tank_history.js`

- [ ] **Step 1: Rewrite tank_history.html**

Use the same Tailwind design system. Key sections:
- Time range selector (preset + custom date picker)
- Main chart with zoom/pan (chartjs-plugin-zoom)
- Temperature and Flow Rate secondary charts
- Statistics summary cards
- Export buttons (CSV, Excel, PDF)
- Tank visualization sidebar

Extend `base.html`. Use Chart.js v4 with zoom plugin.

- [ ] **Step 2: Rewrite tank_history.js**

Modernize the 1374-line file to use Chart.js v4 API and Tailwind-compatible DOM manipulation.

- [ ] **Step 3: Commit**

```bash
git add templates/tank_history.html static/js/tank_history.js
git commit -m "feat: rebuild tank history page with Tailwind and Chart.js v4"
```

---

### Task 17: Rebuild Alarms Page

**Files:**
- Rewrite: `templates/alarms.html`
- Rewrite: `static/js/alarms.js`

- [ ] **Step 1: Rewrite alarms.html**

Tailwind-based with:
- Collapsible filter panel (status, severity, tank, date range)
- Dynamic paginated table (JS-rendered, not hardcoded)
- Acknowledge All button
- Export CSV button
- Responsive column hiding

- [ ] **Step 2: Rewrite alarms.js**

Dynamic pagination, filter API calls, acknowledge actions — all using fetch() and Tailwind DOM updates.

- [ ] **Step 3: Commit**

```bash
git add templates/alarms.html static/js/alarms.js
git commit -m "feat: rebuild alarms page with Tailwind and dynamic pagination"
```

---

### Task 18: Rebuild Landing Page

**Files:**
- Rewrite: `templates/index.html`

- [ ] **Step 1: Rewrite index.html**

Modern landing page with Tailwind:
- Hero section with gradient background
- Feature cards with Lucide icons
- Call-to-action buttons
- No Bootstrap jumbotron pattern

- [ ] **Step 2: Commit**

```bash
git add templates/index.html
git commit -m "feat: rebuild landing page with Tailwind"
```

---

### Task 19: Rebuild Admin Templates

**Files:**
- Rewrite: `templates/admin/dashboard.html`
- Rewrite: `templates/admin/tanks.html`
- Rewrite: `templates/admin/tank_detail.html`
- Rewrite: `templates/admin/sites.html`
- Rewrite: `templates/admin/tank_form.html`
- Rewrite: `templates/admin/create_tank.html`
- Rewrite: `templates/admin/edit_tank.html`
- Rewrite: `static/js/charts.js`
- Rewrite: `static/js/main.js`

- [ ] **Step 1: Rewrite admin/dashboard.html**

Extend `admin/base.html`. Tailwind stat cards, system monitoring charts (CPU/Memory/Disk), recent activity table, quick actions grid.

- [ ] **Step 2: Rewrite admin/tanks.html**

Extend `admin/base.html`. Dynamic filterable/paginated tank table with Tailwind. Start/Stop monitoring buttons. Bulk actions.

- [ ] **Step 3: Rewrite admin/tank_detail.html**

Extend `admin/base.html` (FIX: currently extends `base.html` which is wrong). Tank info, status, charts, alarms.

- [ ] **Step 4: Rewrite admin/sites.html**

Extend `admin/base.html`. Sites table with Google Maps integration (keep existing API). Filter form.

- [ ] **Step 5: Rewrite admin tank form templates**

Remove TCP fields. Use Tailwind form components. Gateway MAC + sensor serial number fields instead of host/tcp_port.

- [ ] **Step 6: Rewrite static/js/charts.js**

Replace with Chart.js v4 factory (or import chart-factory.js).

- [ ] **Step 7: Rewrite static/js/main.js**

Tailwind-compatible utility functions (replace jQuery-dependent code).

- [ ] **Step 8: Commit**

```bash
git add templates/admin/ static/js/charts.js static/js/main.js
git commit -m "feat: rebuild all admin templates with Tailwind"
```

---

### Task 20: Final Cleanup and Verification

- [ ] **Step 1: Remove dead JS files**

```bash
rm -f static/js/socket.js static/js/tank_monitor.js
```

- [ ] **Step 2: Verify no Bootstrap references remain**

Run: `grep -r "bootstrap\|Bootstrap" --include="*.html" --include="*.css" templates/ static/`
Expected: No results (all Bootstrap references should be gone).

- [ ] **Step 3: Verify no Font Awesome references remain**

Run: `grep -r "font-awesome\|fontawesome\|fas \|far " --include="*.html" templates/`
Expected: No results.

- [ ] **Step 4: Verify no Socket.IO references remain**

Run: `grep -r "socket.io\|socketio\|Socket.IO\|io(" --include="*.html" --include="*.js" templates/ static/`
Expected: No results.

- [ ] **Step 5: Verify no jQuery references remain**

Run: `grep -r "jquery\|jQuery\|\$(" --include="*.html" --include="*.js" templates/ static/`
Expected: No results (or minimal if any third-party lib needs it).

- [ ] **Step 6: Verify app starts cleanly**

Run: `python -c "from app import create_app; app = create_app(); print('OK')"`
Expected: No import errors.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "chore: final cleanup - remove dead files, verify no legacy references"
```
