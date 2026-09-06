/**
 * Admin Site Detail JavaScript
 * Handles functionality for the admin site detail page
 */

document.addEventListener('DOMContentLoaded', function() {
    // Get site ID from the page
    const siteId = document.getElementById('site-data')?.getAttribute('data-site-id');
    if (!siteId) return;
    
    // Initialize tanks table
    initializeTanksTable(siteId);
    
    // Initialize site statistics
    initializeSiteStatistics(siteId);
    
    // Set up refresh button
    const refreshBtn = document.getElementById('refresh-site-data');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', function() {
            refreshSiteData(siteId);
        });
    }
    
    // Set up add tank button
    const addTankBtn = document.getElementById('add-tank-btn');
    if (addTankBtn) {
        addTankBtn.addEventListener('click', function() {
            window.location.href = `/admin/tanks/create?site_id=${siteId}`;
        });
    }
    
    // Set up edit site button
    const editSiteBtn = document.getElementById('edit-site-btn');
    if (editSiteBtn) {
        editSiteBtn.addEventListener('click', function() {
            window.location.href = `/admin/sites/edit/${siteId}`;
        });
    }
    
    // Set up delete site button
    const deleteSiteBtn = document.getElementById('delete-site-btn');
    if (deleteSiteBtn) {
        deleteSiteBtn.addEventListener('click', function() {
            const siteName = this.getAttribute('data-site-name');
            if (confirm(`Are you sure you want to delete site "${siteName}"? This action cannot be undone.`)) {
                fetch(`/admin/sites/delete/${siteId}`, {
                    method: 'POST',
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        showAlert('success', data.message || 'Site deleted successfully');
                        // Redirect to sites list after a short delay
                        setTimeout(() => {
                            window.location.href = '/admin/sites';
                        }, 1500);
                    } else {
                        showAlert('danger', data.message || 'Error deleting site');
                    }
                })
                .catch(error => {
                    console.error('Error deleting site:', error);
                    showAlert('danger', 'Error deleting site: ' + error.message);
                });
            }
        });
    }
    
    // Set up acknowledge alarm buttons
    document.addEventListener('click', function(e) {
        if (e.target.closest('.acknowledge-alarm-btn')) {
            const btn = e.target.closest('.acknowledge-alarm-btn');
            const alarmId = btn.getAttribute('data-alarm-id');
            acknowledgeAlarm(alarmId);
        }
    });
});

/**
 * Initialize tanks table
 */
function initializeTanksTable(siteId) {
    const tanksTable = document.getElementById('site-tanks-table');
    if (!tanksTable) return;
    
    fetch(`/admin/api/sites/${siteId}/tanks`)
        .then(response => response.json())
        .then(data => {
            if (!data.success) {
                console.error('Error fetching site tanks:', data.message);
                return;
            }
            
            const tanks = data.tanks;
            const tableBody = tanksTable.querySelector('tbody');
            
            if (!tableBody) return;
            
            // Clear existing rows
            tableBody.innerHTML = '';
            
            if (tanks.length === 0) {
                tableBody.innerHTML = '<tr><td colspan="7" class="text-center">No tanks found for this site</td></tr>';
                return;
            }
            
            // Add rows for each tank
            tanks.forEach(tank => {
                // Create fill level badge with appropriate color
                let fillLevelBadge = '';
                if (tank.measurement) {
                    const fillPercent = tank.measurement.fill_percent;
                    let badgeClass = 'bg-primary';
                    
                    if (fillPercent <= tank.critical_level_threshold) {
                        badgeClass = 'bg-danger';
                    } else if (fillPercent <= tank.low_level_threshold) {
                        badgeClass = 'bg-warning';
                    } else if (fillPercent >= tank.high_level_threshold) {
                        badgeClass = 'bg-warning';
                    }
                    
                    fillLevelBadge = `<span class="badge ${badgeClass}">${fillPercent.toFixed(1)}%</span>`;
                } else {
                    fillLevelBadge = '<span class="badge bg-secondary">N/A</span>';
                }
                
                // Create connection status badge
                let connectionBadge = '';
                switch (tank.connection_status) {
                    case 'Connected':
                        connectionBadge = '<span class="badge bg-success">Connected</span>';
                        break;
                    case 'Recently Disconnected':
                        connectionBadge = '<span class="badge bg-warning">Recently Disconnected</span>';
                        break;
                    default:
                        connectionBadge = '<span class="badge bg-danger">Disconnected</span>';
                }
                
                // Create active status badge
                const activeBadge = tank.is_active ? 
                    '<span class="badge bg-success">Active</span>' : 
                    '<span class="badge bg-danger">Inactive</span>';
                
                // Create row
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td>${tank.name}</td>
                    <td>${fillLevelBadge}</td>
                    <td>${tank.measurement ? tank.measurement.volume.toFixed(1) + ' L' : 'N/A'}</td>
                    <td>${tank.measurement ? tank.measurement.flow_rate.toFixed(2) + ' L/h' : 'N/A'}</td>
                    <td>${connectionBadge}</td>
                    <td>${activeBadge}</td>
                    <td>
                        <div class="btn-group btn-group-sm">
                            <a href="/admin/tanks/${tank.id}" class="btn btn-info">
                                <i class="bi bi-eye"></i>
                            </a>
                            <a href="/admin/tanks/edit/${tank.id}" class="btn btn-primary">
                                <i class="bi bi-pencil"></i>
                            </a>
                            <button type="button" class="btn btn-danger delete-tank-btn" 
                                    data-tank-id="${tank.id}" data-tank-name="${tank.name}">
                                <i class="bi bi-trash"></i>
                            </button>
                        </div>
                    </td>
                `;
                
                tableBody.appendChild(row);
            });
            
            // Set up delete tank buttons
            document.querySelectorAll('.delete-tank-btn').forEach(button => {
                button.addEventListener('click', function() {
                    const tankId = this.getAttribute('data-tank-id');
                    const tankName = this.getAttribute('data-tank-name');
                    
                    if (confirm(`Are you sure you want to delete tank "${tankName}"? This action cannot be undone.`)) {
                        fetch(`/admin/tanks/delete/${tankId}`, {
                            method: 'POST',
                            headers: {
                                'X-Requested-With': 'XMLHttpRequest'
                            }
                        })
                        .then(response => response.json())
                        .then(data => {
                            if (data.success) {
                                showAlert('success', data.message || 'Tank deleted successfully');
                                // Refresh tanks table
                                initializeTanksTable(siteId);
                                // Refresh site statistics
                                initializeSiteStatistics(siteId);
                            } else {
                                showAlert('danger', data.message || 'Error deleting tank');
                            }
                        })
                        .catch(error => {
                            console.error('Error deleting tank:', error);
                            showAlert('danger', 'Error deleting tank: ' + error.message);
                        });
                    }
                });
            });
        })
        .catch(error => {
            console.error('Error fetching site tanks:', error);
        });
}

/**
 * Initialize site statistics
 */
function initializeSiteStatistics(siteId) {
    fetch(`/admin/api/sites/${siteId}/stats`)
        .then(response => response.json())
        .then(data => {
            if (!data.success) {
                console.error('Error fetching site statistics:', data.message);
                return;
            }
            
            const stats = data.stats;
            
            // Update statistics
            document.getElementById('total-tanks')?.textContent = stats.tank_count;
            document.getElementById('active-tanks')?.textContent = stats.active_tank_count;
            document.getElementById('connected-tanks')?.textContent = stats.connected_tank_count;
            document.getElementById('total-volume')?.textContent = stats.total_volume.toFixed(1) + ' L';
            document.getElementById('avg-fill-level')?.textContent = stats.avg_fill_level.toFixed(1) + '%';
            document.getElementById('total-alarms')?.textContent = stats.total_alarms;
            document.getElementById('active-alarms')?.textContent = stats.active_alarms;
        })
        .catch(error => {
            console.error('Error fetching site statistics:', error);
        });
}

/**
 * Refresh all site data
 */
function refreshSiteData(siteId) {
    // Show loading indicator
    const refreshBtn = document.getElementById('refresh-site-data');
    if (refreshBtn) {
        const originalContent = refreshBtn.innerHTML;
        refreshBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Refreshing...';
        refreshBtn.disabled = true;
        
        // Refresh data
        Promise.all([
            initializeTanksTable(siteId),
            initializeSiteStatistics(siteId)
        ])
        .finally(() => {
            // Restore button state
            setTimeout(() => {
                refreshBtn.innerHTML = originalContent;
                refreshBtn.disabled = false;
            }, 500);
        });
    } else {
        // If no refresh button, just refresh the data
        initializeTanksTable(siteId);
        initializeSiteStatistics(siteId);
    }
}

/**
 * Acknowledge an alarm
 */
function acknowledgeAlarm(alarmId) {
    fetch(`/admin/alarms/acknowledge/${alarmId}`, {
        method: 'POST'
    })
        .then(response => {
            if (!response.ok) {
                throw new Error('Failed to acknowledge alarm');
            }
            return response.json();
        })
        .then(data => {
            // Update UI to show alarm as acknowledged
            const alarmRow = document.querySelector(`tr[data-alarm-id="${alarmId}"]`);
            if (alarmRow) {
                const statusCell = alarmRow.querySelector('.alarm-status');
                if (statusCell) {
                    statusCell.innerHTML = '<span class="badge bg-success">Acknowledged</span>';
                }
                
                // Remove acknowledge button
                const actionCell = alarmRow.querySelector('.alarm-actions');
                if (actionCell) {
                    actionCell.innerHTML = '<span class="text-muted">No actions available</span>';
                }
            }
            
            // Show success message
            showAlert('success', 'Alarm acknowledged successfully');
            
            // Refresh site statistics
            const siteId = document.getElementById('site-data')?.getAttribute('data-site-id');
            if (siteId) {
                initializeSiteStatistics(siteId);
            }
        })
        .catch(error => {
            console.error('Error acknowledging alarm:', error);
            showAlert('danger', 'Error acknowledging alarm: ' + error.message);
        });
}

/**
 * Show an alert message
 */
function showAlert(type, message) {
    const alertContainer = document.getElementById('alert-container');
    if (!alertContainer) return;
    
    const alert = document.createElement('div');
    alert.className = `alert alert-${type} alert-dismissible fade show`;
    alert.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;
    
    alertContainer.innerHTML = '';
    alertContainer.appendChild(alert);
    
    // Auto-dismiss after 5 seconds
    setTimeout(() => {
        alert.classList.remove('show');
        setTimeout(() => {
            alertContainer.removeChild(alert);
        }, 150);
    }, 5000);
}
