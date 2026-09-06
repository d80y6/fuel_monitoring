"""
Alarm management views for the admin blueprint
"""
from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from sqlalchemy import func, desc, and_
from . import admin
from .auth import admin_required, permission_required, Permissions
from .utils import handle_db_errors, log_activity
from models.database import db, Alarm, Tank, Site, User

@admin.route('/alarms', endpoint='alarms_index')
@admin_required
def alarms_view():
    """Alarm list with optimized query building and validation"""
    # Get filter parameters with validation
    acknowledged = request.args.get('acknowledged', 'all')
    level = request.args.get('level', 'all')
    days = min(90, max(1, request.args.get('days', 7, type=int) or 7))
    
    # Build query with proper parameter validation
    query = Alarm.query
    
    if acknowledged != 'all':
        if acknowledged == 'true':
            query = query.filter(Alarm.acknowledged == True)
        elif acknowledged == 'false':
            query = query.filter(Alarm.acknowledged == False)
    
    if level != 'all' and level in ['info', 'warning', 'danger', 'critical']:
        query = query.filter(Alarm.level == level)
    
    # Get alarms with joined data to avoid N+1 queries
    query = query.join(
        Tank, Alarm.tank_id == Tank.id
    ).join(
        Site, Tank.site_id == Site.id
    ).add_columns(
        Tank.name.label('tank_name'),
        Site.name.label('site_name')
    ).order_by(Alarm.timestamp.desc())
    
    # Execute the query
    alarms_with_details = query.all()
    
    # Prepare results
    alarms_data = []
    for alarm, tank_name, site_name in alarms_with_details:
        acknowledger = None
        if alarm.acknowledged and alarm.acknowledged_by:
            acknowledger = User.query.get(alarm.acknowledged_by)
            
        alarms_data.append({
            'alarm': alarm,
            'tank_name': tank_name, 
            'site_name': site_name,
            'acknowledger': acknowledger
        })
    
    return render_template(
        'admin/alarms.html', 
        alarms=alarms_data, 
        acknowledged=acknowledged, 
        level=level,
        days=days
    )

@admin.route('/api/alarms')
@admin_required
def api_alarms():
    """API endpoint for alarms with optimized query and pagination"""
    try:
        # Validate and sanitize parameters
        page = max(1, request.args.get('page', 1, type=int))
        per_page = min(100, max(10, request.args.get('per_page', 20, type=int)))
        acknowledged = request.args.get('acknowledged', 'all')
        level = request.args.get('level', 'all')
        tank_id = request.args.get('tank_id', 'all')
        site_id = request.args.get('site_id', 'all')
        company_id = request.args.get('company_id', 'all')
        from_date = request.args.get('from_date')
        to_date = request.args.get('to_date')
        
        # Build the query
        query = db.session.query(
            Alarm, 
            Tank.name.label('tank_name'), 
            Site.name.label('site_name'),
            Site.company_id
        ).join(
            Tank, Alarm.tank_id == Tank.id
        ).join(
            Site, Tank.site_id == Site.id
        )
        
        # Apply filters
        if acknowledged != 'all':
            if acknowledged == 'true':
                query = query.filter(Alarm.acknowledged == True)
            elif acknowledged == 'false':
                query = query.filter(Alarm.acknowledged == False)
            
        if level != 'all':
            query = query.filter(Alarm.level == level)
            
        if tank_id != 'all' and tank_id.isdigit():
            query = query.filter(Alarm.tank_id == int(tank_id))
            
        if site_id != 'all' and site_id.isdigit():
            query = query.filter(Site.id == int(site_id))
            
        if company_id != 'all' and company_id.isdigit():
            query = query.filter(Site.company_id == int(company_id))
            
        if from_date:
            try:
                from_date_obj = datetime.strptime(from_date, '%Y-%m-%d')
                query = query.filter(Alarm.timestamp >= from_date_obj)
            except ValueError:
                # Invalid date format, ignore this filter
                pass
                
        if to_date:
            try:
                to_date_obj = datetime.strptime(to_date, '%Y-%m-%d') + timedelta(days=1)
                query = query.filter(Alarm.timestamp < to_date_obj)
            except ValueError:
                # Invalid date format, ignore this filter
                pass
        
        # Order by timestamp descending
        query = query.order_by(Alarm.timestamp.desc())
        
        # Get total count for pagination
        total_count = query.count()
        
        # Apply pagination
        alarms_page = query.offset((page - 1) * per_page).limit(per_page).all()
        
        # Prepare results
        alarms_data = []
        for alarm, tank_name, site_name, company_id in alarms_page:
            alarm_dict = {
                'id': alarm.id,
                'tank_id': alarm.tank_id,
                'tank_name': tank_name,
                'site_name': site_name,
                'company_id': company_id,
                'timestamp': alarm.timestamp.isoformat(),
                'type': alarm.type,
                'level': alarm.level,
                'message': alarm.message,
                'value': alarm.value,
                'acknowledged': alarm.acknowledged,
                'acknowledged_by': alarm.acknowledged_by,
                'acknowledged_at': alarm.acknowledged_at.isoformat() if alarm.acknowledged_at else None
            }
            alarms_data.append(alarm_dict)
        
        return jsonify({
            'success': True,
            'alarms': alarms_data,
            'total': total_count,
            'page': page,
            'pages': (total_count + per_page - 1) // per_page
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@admin.route('/alarms/acknowledge/<int:alarm_id>', methods=['POST'])
@admin_required
@handle_db_errors
def acknowledge_alarm(alarm_id):
    """Acknowledge alarm with proper validation and security"""
    alarm = Alarm.query.get_or_404(alarm_id)
    
    # Prevent double acknowledgment
    if alarm.acknowledged:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': False,
                'message': 'Alarm already acknowledged'
            })
        flash('Alarm already acknowledged', 'info')
        return redirect(url_for('admin.alarms_index'))
    
    # Acknowledge alarm
    alarm.acknowledged = True
    alarm.acknowledged_by = current_user.id
    alarm.acknowledged_at = datetime.now()
    
    db.session.commit()
    
    # Log activity
    log_activity(
        action="alarm_acknowledged",
        details=f"Acknowledged alarm #{alarm.id} of type '{alarm.type}'"
    )
    
    # Check if this is an AJAX request
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'success': True,
            'message': 'Alarm acknowledged successfully'
        })
    
    flash('Alarm acknowledged successfully', 'success')
    return redirect(url_for('admin.alarms_index'))