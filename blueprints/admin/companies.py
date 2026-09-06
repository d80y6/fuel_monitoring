"""
Company management views for the admin blueprint
"""
from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required
from sqlalchemy import func
from . import admin
from .auth import admin_required, permission_required, Permissions
from .utils import handle_db_errors, log_activity
from models.database import db, Company, Site, Tank, Alarm, Measurement
from datetime import datetime as dt, timedelta
from . import CONNECTION_TIMEOUT_MINUTES, ITEMS_PER_PAGE

# Other company endpoints...

@admin.route('/api/companies/<int:company_id>/stats')
@admin_required
def api_company_stats(company_id):
    """API endpoint for company statistics - optimized to avoid N+1 queries"""
    # Verify company exists
    company = Company.query.get_or_404(company_id)
    
    # Get all site IDs for this company efficiently
    site_ids = db.session.query(Site.id).filter(
        Site.company_id == company_id,
        Site.deleted_at == None
    ).all()
    site_ids = [s[0] for s in site_ids]
    
    # No sites? Return empty stats
    if not site_ids:
        return jsonify({
            'success': True,
            'company_id': company_id,
            'stats': {
                'total_site_count': 0,
                'total_tank_count': 0,
                'active_tank_count': 0,
                'connected_tank_count': 0,
                'total_volume': 0,
                'avg_fill_level': 0,
                'total_alarms': 0,
                'active_alarms': 0
            }
        })
    
    # Get tank counts in a single query
    five_minutes_ago = dt.now() - timedelta(minutes=CONNECTION_TIMEOUT_MINUTES)
    tank_stats = db.session.query(
        func.count(Tank.id).label('total_count'),
        func.sum(case((Tank.is_active == True, 1), else_=0)).label('active_count'),
        func.sum(case((Tank.last_connection >= five_minutes_ago, 1), else_=0)).label('connected_count')
    ).filter(
        Tank.site_id.in_(site_ids),
        Tank.deleted_at == None
    ).first()
    
    # Get tank IDs for measurement queries
    tank_ids = db.session.query(Tank.id).filter(
        Tank.site_id.in_(site_ids),
        Tank.deleted_at == None
    ).all()
    tank_ids = [t[0] for t in tank_ids]
    
    # Get alarm counts in a single query
    alarm_stats = db.session.query(
        func.count(Alarm.id).label('total_count'),
        func.sum(case((Alarm.acknowledged == False, 1), else_=0)).label('active_count')
    ).filter(
        Alarm.tank_id.in_(tank_ids)
    ).first()
    
    # Get latest measurements for volume calculations efficiently
    latest_measurements_subq = db.session.query(
        Measurement.tank_id,
        func.max(Measurement.timestamp).label('max_timestamp')
    ).filter(
        Measurement.tank_id.in_(tank_ids)
    ).group_by(Measurement.tank_id).subquery()
    
    measurements = db.session.query(
        Measurement
    ).join(
        latest_measurements_subq,
        and_(
            Measurement.tank_id == latest_measurements_subq.c.tank_id,
            Measurement.timestamp == latest_measurements_subq.c.max_timestamp
        )
    ).all()
    
    # Calculate total volume and average fill level
    total_volume = sum(m.volume for m in measurements if m.volume is not None)
    fill_levels = [m.fill_percent for m in measurements if m.fill_percent is not None]
    avg_fill_level = sum(fill_levels) / len(fill_levels) if fill_levels else 0
    
    # Return the stats
    return jsonify({
        'success': True,
        'company_id': company_id,
        'stats': {
            'total_site_count': len(site_ids),
            'total_tank_count': tank_stats.total_count if tank_stats else 0,
            'active_tank_count': tank_stats.active_count if tank_stats else 0,
            'connected_tank_count': tank_stats.connected_count if tank_stats else 0,
            'total_volume': total_volume,
            'avg_fill_level': avg_fill_level,
            'total_alarms': alarm_stats.total_count if alarm_stats else 0,
            'active_alarms': alarm_stats.active_count if alarm_stats else 0
        }
    })