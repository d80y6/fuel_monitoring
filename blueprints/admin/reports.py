"""
Reporting views for the admin blueprint
"""
from flask import render_template, request, jsonify
from flask_login import login_required
from . import admin
from .auth import admin_required
from .utils import handle_db_errors, validate_date_range
from models.database import db, Company, Site, Tank, Alarm, Measurement
from datetime import datetime as dt, timedelta
from sqlalchemy import func

@admin.route('/api/reports/usage')
@admin_required
def api_usage_report():
    """API endpoint for usage report data with input validation"""
    try:
        # Get and validate date range
        start_date_str = request.args.get('start_date', (dt.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
        end_date_str = request.args.get('end_date', dt.now().strftime('%Y-%m-%d'))
        start_date, end_date = validate_date_range(start_date_str, end_date_str, max_days=365)
        
        # Include end of end_date
        end_date = end_date + timedelta(days=1)
        
        # Validate other parameters
        company_id = request.args.get('company_id', 'all')
        site_id = request.args.get('site_id', 'all')
        tank_id = request.args.get('tank_id', 'all')
        
        # Validate numeric IDs
        if company_id != 'all' and not company_id.isdigit():
            return jsonify({'success': False, 'message': 'Invalid company ID'}), 400
        if site_id != 'all' and not site_id.isdigit():
            return jsonify({'success': False, 'message': 'Invalid site ID'}), 400
        if tank_id != 'all' and not tank_id.isdigit():
            return jsonify({'success': False, 'message': 'Invalid tank ID'}), 400
        
        # Build query for tanks
        tank_query = Tank.not_deleted()
        
        if company_id != 'all':
            tank_query = tank_query.join(Site).filter(Site.company_id == int(company_id))
        
        if site_id != 'all':
            tank_query = tank_query.filter(Tank.site_id == int(site_id))
        
        if tank_id != 'all':
            tank_query = tank_query.filter(Tank.id == int(tank_id))
        
        # Get tanks
        tanks = tank_query.all()
        
        # Rest of the function implementation...
        # ...
        
        return jsonify({
            'success': True,
            'data': result
        })
    except ValueError as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    except Exception as e:
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'}), 500