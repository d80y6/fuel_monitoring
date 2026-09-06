/**
 * Tank Detail JavaScript
 * Handles functionality for the tank detail page
 */

document.addEventListener('DOMContentLoaded', function() {
    // Get tank ID from the page
    const tankId = document.getElementById('tank-data')?.getAttribute('data-tank-id');
    if (!tankId) return;
    
    // Initialize tank monitor
    const tankMonitor = new TankMonitor(tankId, {
        updateInterval: 30000, // 30 seconds
        chartHistoryPoints: 50,
        showTemperature: true,
        showPressure: true,
        showFlowRate: true,
        animateChanges: true
    });
    
    tankMonitor.init();
    
    // Initialize level history chart
    initializeLevelHistoryChart(tankId);
    
    // Set up refresh button
    const refreshBtn = document.getElementById('refresh-tank-data');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', function() {
            tankMonitor.fetchData();
        });
    }
    
    // Set up export data button
    const exportBtn = document.getElementById('export-tank-data');
    if (exportBtn) {
        exportBtn.addEventListener('click', function() {
            const hours = document.getElementById('export-hours').value || 24;
            window.location.href = `/download/tank/${tankId}/csv?hours=${hours}`;
        });
    }
    
    // Set up acknowledge alarm buttons
    document.querySelectorAll('.acknowledge-alarm-btn').forEach(button => {
        button.addEventListener('click', function() {
            const alarmId = this.getAttribute('data-alarm-id');
            acknowledgeAlarm(alarmId);
        });
    });
});

/**
 * Initialize level history chart
 */
function initializeLevelHistoryChart(tankId) {
    const levelHistoryChart = document.getElementById('level-history-chart');
    if (!levelHistoryChart) return;
    
    fetch(`/api/tank/${tankId}/history?hours=24`)
        .then(response => response.json())
        .then(data => {
            if (!data || data.error) {
                console.error('Error fetching tank history:', data?.error || 'Unknown error');
                return;
            }
            
            // Prepare data for chart
            const timestamps = data.map(item => {
                const date = new Date(item.timestamp);
                return date.toLocaleString();
            });
            
            const fillLevels = data.map(item => item.fill_percent);
            const volumes = data.map(item => item.volume);
            
            // Create chart
            const chart = new Chart(levelHistoryChart.getContext('2d'), {
                type: 'line',
                data: {
                    labels: timestamps,
                    datasets: [
                        {
                            label: 'Fill Level (%)',
                            data: fillLevels,
                            borderColor: 'rgba(75, 192, 192, 1)',
                            backgroundColor: 'rgba(75, 192, 192, 0.2)',
                            tension: 0.1,
                            yAxisID: 'y'
                        },
                        {
                            label: 'Volume (L)',
                            data: volumes,
                            borderColor: 'rgba(54, 162, 235, 1)',
                            backgroundColor: 'rgba(54, 162, 235, 0.2)',
                            tension: 0.1,
                            yAxisID: 'y1',
                            hidden: true
                        }
                    ]
                },
                options: {
                    responsive: true,
                    interaction: {
                        mode: 'index',
                        intersect: false,
                    },
                    scales: {
                        x: {
                            title: {
                                display: true,
                                text: 'Time'
                            }
                        },
                        y: {
                            type: 'linear',
                            display: true,
                            position: 'left',
                            title: {
                                display: true,
                                text: 'Fill Level (%)'
                            },
                            min: 0,
                            max: 100
                        },
                        y1: {
                            type: 'linear',
                            display: true,
                            position: 'right',
                            title: {
                                display: true,
                                text: 'Volume (L)'
                            },
                            min: 0,
                            grid: {
                                drawOnChartArea: false
                            }
                        }
                    }
                }
            });
        })
        .catch(error => {
            console.error('Error fetching tank history:', error);
        });
}

/**
 * Acknowledge an alarm
 */
function acknowledgeAlarm(alarmId) {
    fetch(`/alarm/${alarmId}/acknowledge`, {
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
