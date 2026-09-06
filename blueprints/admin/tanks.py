"""
Tank management views for the admin blueprint
"""
from flask import render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from sqlalchemy import func, text, and_, desc
from . import admin
from .auth import admin_required, permission_required
from .utils import handle_db_errors, log_activity
from models.database import db, Tank, Site, Measurement, Alarm
from datetime import datetime as dt, timedelta
from . import CONNECTION_TIMEOUT_MINUTES, ITEMS_PER_PAGE

# Existing code...

@admin.route('/api/sites/<int:site_id>/tanks')
@admin_required
def api_site_tanks(site_id):
    """API endpoint for site tanks with their latest measurements - optimized version"""
    # Validate site exists
    site = Site.query.get_or_404(site_id)
    
    # Create a subquery to get the latest measurement timestamp for each tank
    latest_measurement_subq = db.session.query(
        Measurement.tank_id,
        func.max(Measurement.timestamp).label('max_timestamp')
    ).group_by(Measurement.tank_id).subquery('latest_measurement')
    
    # Join the tanks table with the latest measurements subquery
    # This eliminates the N+1 query pattern by fetching all data in one query
    query = db.session.query(
        Tank, Measurement
    ).outerjoin(
        latest_measurement_subq, 
        Tank.id == latest_measurement_subq.c.tank_id
    ).outerjoin(
        Measurement,
        and_(
            Measurement.tank_id == latest_measurement_subq.c.tank_id,
            Measurement.timestamp == latest_measurement_subq.c.max_timestamp
        )
    ).filter(
        Tank.site_id == site_id,
        Tank.deleted_at == None
    )
    
    # Execute the query
    results = query.all()
    
    # Prepare the data for JSON response
    tank_data = []
    for tank, measurement in results:
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