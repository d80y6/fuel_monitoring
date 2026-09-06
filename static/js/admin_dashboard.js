/**
 * Admin Dashboard JavaScript
 * Handles functionality for the admin dashboard
 */

document.addEventListener('DOMContentLoaded', function() {
    // Fetch system statistics
    fetchSystemStats();
    
    // Initialize charts
    initializeCharts();
    
    // Set up auto-refresh
    setInterval(function() {
        fetchSystemStats();
        updateCharts();
    }, 60000); // Refresh every minute
    
    // Set up refresh button
    const refreshBtn = document.getElementById('refresh-dashboard');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', function() {
            fetchSystemStats();
            updateCharts();
        });
    }
});

/**
 * Fetch system statistics from the server
 */
function fetchSystemStats() {
    fetch('/admin/api/stats')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                updateStatCards(data.stats);
                updateAlarmsList(data.recent_alarms);
                updateActivityFeed(data.recent_activity);
            } else {
                console.error('Error fetching system stats:', data.message);
            }
        })
        .catch(error => {
            console.error('Error fetching system stats:', error);
        });
}

/**
 * Update stat cards with latest data
 */
function updateStatCards(stats) {
    // Update user count
    const userCountElement = document.getElementById('user-count');
    if (userCountElement) {
        userCountElement.textContent = stats.user_count;
    }
    
    // Update company count
    const companyCountElement = document.getElementById('company-count');
    if (companyCountElement) {
        companyCountElement.textContent = stats.company_count;
    }
    
    // Update site count
    const siteCountElement = document.getElementById('site-count');
    if (siteCountElement) {
        siteCountElement.textContent = stats.site_count;
    }
    
    // Update tank count
    const tankCountElement = document.getElementById('tank-count');
    if (tankCountElement) {
        tankCountElement.textContent = stats.tank_count;
    }
    
    // Update connected tank count
    const connectedTankCountElement = document.getElementById('connected-tank-count');
    if (connectedTankCountElement) {
        connectedTankCountElement.textContent = stats.connected_tank_count;
    }
    
    // Update active alarm count
    const activeAlarmCountElement = document.getElementById('active-alarm-count');
    if (activeAlarmCountElement) {
        activeAlarmCountElement.textContent = stats.active_alarm_count;
    }
    
    // Update total volume
    const totalVolumeElement = document.getElementById('total-volume');
    if (totalVolumeElement) {
        totalVolumeElement.textContent = stats.total_volume.toFixed(1) + ' L';
    }
    
    // Update average fill level
    const avgFillLevelElement = document.getElementById('avg-fill-level');
    if (avgFillLevelElement) {
        avgFillLevelElement.textContent = stats.avg_fill_level.toFixed(1) + '%';
    }
    
    // Update server uptime
    const serverUptimeElement = document.getElementById('server-uptime');
    if (serverUptimeElement) {
        serverUptimeElement.textContent = formatUptime(stats.server_uptime);
    }
    
    // Update database size
    const dbSizeElement = document.getElementById('db-size');
    if (dbSizeElement) {
        dbSizeElement.textContent = formatFileSize(stats.db_size);
    }
}

/**
 * Update recent alarms list
 */
function updateAlarmsList(alarms) {
    const alarmsList = document.getElementById('recent-alarms-list');
    if (!alarmsList) return;
    
    // Clear current list
    alarmsList.innerHTML = '';
    
    if (alarms.length === 0) {
        alarmsList.innerHTML = '<div class="text-center text-muted">No recent alarms</div>';
        return;
    }
    
    // Add each alarm to the list
    alarms.forEach(alarm => {
        // Format timestamp
        const timestamp = new Date(alarm.timestamp).toLocaleString();
        
        // Create alarm type badge
        let typeBadge = '';
        switch (alarm.type) {
            case 'critical_level':
                typeBadge = '<span class="badge bg-danger">Critical Level</span>';
                break;
            case 'low_level':
                typeBadge = '<span class="badge bg-warning">Low Level</span>';
                break;
            case 'high_level':
                typeBadge = '<span class="badge bg-warning">High Level</span>';
                break;
            case 'connection':
                typeBadge = '<span class="badge bg-danger">Connection</span>';
                break;
            default:
                typeBadge = `<span class="badge bg-secondary">${alarm.type}</span>`;
        }
        
        // Create acknowledged badge
        let acknowledgedBadge = alarm.acknowledged ? 
            '<span class="badge bg-success">Acknowledged</span>' : 
            '<span class="badge bg-danger">Unacknowledged</span>';
        
        // Create alarm item
        const alarmItem = document.createElement('div');
        alarmItem.className = 'alarm-item';
        alarmItem.innerHTML = `
            <div class="alarm-header">
                <div class="alarm-title">${typeBadge} ${alarm.tank_name}</div>
                <div class="alarm-time">${timestamp}</div>
            </div>
            <div class="alarm-message">${alarm.message}</div>
            <div class="alarm-footer">
                <div class="alarm-tank">${alarm.site_name}</div>
                <div class="alarm-status">${acknowledgedBadge}</div>
            </div>
        `;
        
        // Add appropriate class based on alarm type
        if (alarm.type === 'critical_level' || alarm.type === 'connection') {
            alarmItem.classList.add('critical');
        } else if (alarm.type === 'low_level' || alarm.type === 'high_level') {
            alarmItem.classList.add('warning');
        }
        
        alarmsList.appendChild(alarmItem);
    });
}

/**
 * Update activity feed
 */
function updateActivityFeed(activities) {
    const activityFeed = document.getElementById('activity-feed');
    if (!activityFeed) return;
    
    // Clear current feed
    activityFeed.innerHTML = '';
    
    if (activities.length === 0) {
        activityFeed.innerHTML = '<div class="text-center text-muted">No recent activity</div>';
        return;
    }
    
    // Add each activity to the feed
    activities.forEach(activity => {
        // Format timestamp
        const timestamp = new Date(activity.timestamp).toLocaleString();
        
        // Create icon based on activity type
        let iconClass = 'bi-info-circle';
        switch (activity.type) {
            case 'login':
                iconClass = 'bi-box-arrow-in-right';
                break;
            case 'logout':
                iconClass = 'bi-box-arrow-left';
                break;
            case 'user_created':
                iconClass = 'bi-person-plus';
                break;
            case 'user_updated':
                iconClass = 'bi-person-gear';
                break;
            case 'tank_created':
                iconClass = 'bi-database-add';
                break;
            case 'tank_updated':
                iconClass = 'bi-database-gear';
                break;
            case 'alarm_acknowledged':
                iconClass = 'bi-check-circle';
                break;
        }
        
        // Create activity item
        const activityItem = document.createElement('div');
        activityItem.className = 'activity-item';
        activityItem.innerHTML = `
            <div class="activity-icon">
                <i class="bi ${iconClass}"></i>
            </div>
            <div class="activity-content">
                <div class="activity-title">${activity.message}</div>
                <div class="activity-time">${timestamp}</div>
            </div>
        `;
        
        activityFeed.appendChild(activityItem);
    });
}

/**
 * Initialize dashboard charts
 */
function initializeCharts() {
    // Tank fill levels chart
    const tankLevelsCtx = document.getElementById('tank-levels-chart');
    if (tankLevelsCtx) {
        fetch('/admin/api/charts/tank-levels')
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    const tankLevelsChart = new Chart(tankLevelsCtx, {
                        type: 'bar',
                        data: {
                            labels: data.labels,
                            datasets: [{
                                label: 'Fill Level (%)',
                                data: data.values,
                                backgroundColor: data.values.map(value => {
                                    if (value <= 10) return 'rgba(220, 53, 69, 0.7)'; // Critical
                                    if (value <= 20) return 'rgba(255, 193, 7, 0.7)'; // Low
                                    if (value >= 90) return 'rgba(255, 193, 7, 0.7)'; // High
                                    return 'rgba(13, 110, 253, 0.7)'; // Normal
                                }),
                                borderColor: data.values.map(value => {
                                    if (value <= 10) return 'rgb(220, 53, 69)'; // Critical
                                    if (value <= 20) return 'rgb(255, 193, 7)'; // Low
                                    if (value >= 90) return 'rgb(255, 193, 7)'; // High
                                    return 'rgb(13, 110, 253)'; // Normal
                                }),
                                borderWidth: 1
                            }]
                        },
                        options: {
                            responsive: true,
                            scales: {
                                y: {
                                    beginAtZero: true,
                                    max: 100,
                                    title: {
                                        display: true,
                                        text: 'Fill Level (%)'
                                    }
                                },
                                x: {
                                    title: {
                                        display: true,
                                        text: 'Tank'
                                    }
                                }
                            }
                        }
                    });
                    window.tankLevelsChart = tankLevelsChart;
                } else {
                    console.error('Error fetching tank levels data:', data.message);
                }
            })
            .catch(error => {
                console.error('Error fetching tank levels data:', error);
            });
    }
    
    // Daily usage chart
    const dailyUsageCtx = document.getElementById('daily-usage-chart');
    if (dailyUsageCtx) {
        fetch('/admin/api/charts/daily-usage')
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    const dailyUsageChart = new Chart(dailyUsageCtx, {
                        type: 'line',
                        data: {
                            labels: data.labels,
                            datasets: [{
                                label: 'Daily Usage (L)',
                                data: data.values,
                                backgroundColor: 'rgba(40, 167, 69, 0.2)',
                                borderColor: 'rgba(40, 167, 69, 1)',
                                borderWidth: 2,
                                tension: 0.1,
                                fill: true
                            }]
                        },
                        options: {
                            responsive: true,
                            scales: {
                                y: {
                                    beginAtZero: true,
                                    title: {
                                        display: true,
                                        text: 'Volume (L)'
                                    }
                                },
                                x: {
                                    title: {
                                        display: true,
                                        text: 'Date'
                                    }
                                }
                            }
                        }
                    });
                    
                    window.dailyUsageChart = dailyUsageChart;
                } else {
                    console.error('Error fetching daily usage data:', data.message);
                }
            })
            .catch(error => {
                console.error('Error fetching daily usage data:', error);
            });
    }
    
    // Alarm distribution chart
    const alarmDistributionCtx = document.getElementById('alarm-distribution-chart');
    if (alarmDistributionCtx) {
        fetch('/admin/api/charts/alarm-distribution')
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    const alarmDistributionChart = new Chart(alarmDistributionCtx, {
                        type: 'doughnut',
                        data: {
                            labels: data.labels,
                            datasets: [{
                                data: data.values,
                                backgroundColor: [
                                    'rgba(220, 53, 69, 0.7)',  // Critical level
                                    'rgba(255, 193, 7, 0.7)',  // Low level
                                    'rgba(255, 193, 7, 0.7)',  // High level
                                    'rgba(220, 53, 69, 0.7)',  // Connection
                                    'rgba(108, 117, 125, 0.7)' // Other
                                ],
                                borderColor: [
                                    'rgb(220, 53, 69)',  // Critical level
                                    'rgb(255, 193, 7)',  // Low level
                                    'rgb(255, 193, 7)',  // High level
                                    'rgb(220, 53, 69)',  // Connection
                                    'rgb(108, 117, 125)' // Other
                                ],
                                borderWidth: 1
                            }]
                        },
                        options: {
                            responsive: true,
                            plugins: {
                                legend: {
                                    position: 'right'
                                }
                            }
                        }
                    });
                    
                    window.alarmDistributionChart = alarmDistributionChart;
                } else {
                    console.error('Error fetching alarm distribution data:', data.message);
                }
            })
            .catch(error => {
                console.error('Error fetching alarm distribution data:', error);
            });
    }
    
    // Connection status chart
    const connectionStatusCtx = document.getElementById('connection-status-chart');
    if (connectionStatusCtx) {
        fetch('/admin/api/charts/connection-status')
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    const connectionStatusChart = new Chart(connectionStatusCtx, {
                        type: 'pie',
                        data: {
                            labels: ['Connected', 'Disconnected', 'Inactive'],
                            datasets: [{
                                data: [
                                    data.connected_count,
                                    data.disconnected_count,
                                    data.inactive_count
                                ],
                                backgroundColor: [
                                    'rgba(40, 167, 69, 0.7)',  // Connected
                                    'rgba(220, 53, 69, 0.7)',  // Disconnected
                                    'rgba(108, 117, 125, 0.7)' // Inactive
                                ],
                                borderColor: [
                                    'rgb(40, 167, 69)',  // Connected
                                    'rgb(220, 53, 69)',  // Disconnected
                                    'rgb(108, 117, 125)' // Inactive
                                ],
                                borderWidth: 1
                            }]
                        },
                        options: {
                            responsive: true,
                            plugins: {
                                legend: {
                                    position: 'right'
                                }
                            }
                        }
                    });
                    
                    window.connectionStatusChart = connectionStatusChart;
                } else {
                    console.error('Error fetching connection status data:', data.message);
                }
            })
            .catch(error => {
                console.error('Error fetching connection status data:', error);
            });
    }
}

/**
 * Update all charts with fresh data
 */
function updateCharts() {
    // Update tank fill levels chart
    if (window.tankLevelsChart) {
        fetch('/admin/api/charts/tank-levels')
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    window.tankLevelsChart.data.labels = data.labels;
                    window.tankLevelsChart.data.datasets[0].data = data.values;
                    window.tankLevelsChart.data.datasets[0].backgroundColor = data.values.map(value => {
                        if (value <= 10) return 'rgba(220, 53, 69, 0.7)'; // Critical
                        if (value <= 20) return 'rgba(255, 193, 7, 0.7)'; // Low
                        if (value >= 90) return 'rgba(255, 193, 7, 0.7)'; // High
                        return 'rgba(13, 110, 253, 0.7)'; // Normal
                    });
                    window.tankLevelsChart.data.datasets[0].borderColor = data.values.map(value => {
                        if (value <= 10) return 'rgb(220, 53, 69)'; // Critical
                        if (value <= 20) return 'rgb(255, 193, 7)'; // Low
                        if (value >= 90) return 'rgb(255, 193, 7)'; // High
                        return 'rgb(13, 110, 253)'; // Normal
                    });
                    window.tankLevelsChart.update();
                }
            })
            .catch(error => {
                console.error('Error updating tank levels chart:', error);
            });
    }
    
    // Update daily usage chart
    if (window.dailyUsageChart) {
        fetch('/admin/api/charts/daily-usage')
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    window.dailyUsageChart.data.labels = data.labels;
                    window.dailyUsageChart.data.datasets[0].data = data.values;
                    window.dailyUsageChart.update();
                }
            })
            .catch(error => {
                console.error('Error updating daily usage chart:', error);
            });
    }
    
    // Update alarm distribution chart
    if (window.alarmDistributionChart) {
        fetch('/admin/api/charts/alarm-distribution')
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    window.alarmDistributionChart.data.labels = data.labels;
                    window.alarmDistributionChart.data.datasets[0].data = data.values;
                    window.alarmDistributionChart.update();
                }
            })
            .catch(error => {
                console.error('Error updating alarm distribution chart:', error);
            });
    }
    
    // Update connection status chart
    if (window.connectionStatusChart) {
        fetch('/admin/api/charts/connection-status')
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    window.connectionStatusChart.data.datasets[0].data = [
                        data.connected_count,
                        data.disconnected_count,
                        data.inactive_count
                    ];
                    window.connectionStatusChart.update();
                }
            })
            .catch(error => {
                console.error('Error updating connection status chart:', error);
            });
    }
}

/**
 * Format uptime in a human-readable format
 */
function formatUptime(seconds) {
    const days = Math.floor(seconds / 86400);
    seconds %= 86400;
    const hours = Math.floor(seconds / 3600);
    seconds %= 3600;
    const minutes = Math.floor(seconds / 60);
    seconds %= 60;
    
    let result = '';
    if (days > 0) {
        result += `${days}d `;
    }
    if (hours > 0 || days > 0) {
        result += `${hours}h `;
    }
    if (minutes > 0 || hours > 0 || days > 0) {
        result += `${minutes}m `;
    }
    result += `${seconds}s`;
    
    return result;
}

/**
 * Format file size in a human-readable format
 */
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}