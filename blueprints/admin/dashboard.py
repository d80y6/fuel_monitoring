"""
Dashboard views for the admin blueprint
"""
from flask import render_template, jsonify, current_app
from flask_login import login_required, current_user
from . import admin
from .auth import admin_required
from .utils import handle_db_errors
from models.database import db, User, Company, Site, Tank, Alarm, ActivityLog
from datetime import datetime as dt, timedelta
from . import CONNECTION_TIMEOUT_MINUTES

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

@admin.route('/dashboard')
@admin_required
@login_required
def dashboard():
    """Admin dashboard."""
    # Get statistics
    total_tanks = Tank.not_deleted().count()
    five_minutes_ago = dt.now() - timedelta(minutes=CONNECTION_TIMEOUT_MINUTES)
    connected_tanks = Tank.not_deleted().filter(
        Tank.last_connection >= five_minutes_ago
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
            last_backup = dt.fromtimestamp(os.path.getctime(latest_backup)).strftime('%Y-%m-%d %H:%M:%S')
        else:
            last_backup = 'Never'
            
        # Get recent backups
        backups = []
        for backup_file in sorted(backup_files, key=os.path.getctime, reverse=True)[:5]:
            filename = os.path.basename(backup_file)
            file_date = dt.fromtimestamp(os.path.getctime(backup_file))
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

@admin.route('/api/system-status')
@login_required
def system_status():
    """Get system status for admin dashboard."""
    if not current_user.is_admin():
        return jsonify({'error': 'Access denied'}), 403
    
    # Get statistics
    total_tanks = Tank.not_deleted().count()
    five_minutes_ago = dt.now() - timedelta(minutes=CONNECTION_TIMEOUT_MINUTES)
    connected_tanks = Tank.not_deleted().filter(
        Tank.last_connection >= five_minutes_ago
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
        net_io_1 = psutil.net_io_counters()
        time.sleep(1)
        net_io_2 = psutil.net_io_counters()

        bytes_sent = net_io_2.bytes_sent - net_io_1.bytes_sent
        bytes_recv = net_io_2.bytes_recv - net_io_1.bytes_recv

        # Convert to KB/s or MB/s
        net_sent = bytes_sent / (1024 * 1024)  # KB/s
        net_recv = bytes_recv / (1024 * 1024)  # KB/s
        
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