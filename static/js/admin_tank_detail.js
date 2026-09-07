/**
 * Admin Tank Detail JavaScript
 * Handles functionality for the admin tank detail page
 */

document.addEventListener('DOMContentLoaded', function() {
    // Get tank ID from the page
    const tankId = document.querySelector('[data-tank-id]').getAttribute('data-tank-id');
    
    if (!tankId) {
        console.error('Tank ID not found on page');
        return;
    }
    
    // Function to fetch measurements for chart
    function fetchMeasurements() {
        fetch(`/admin/api/tanks/${tankId}/measurements`)
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    createLevelChart(data.measurements);
                } else {
                    console.error('Error fetching measurements:', data.message);
                }
            })
            .catch(error => {
                console.error('Error fetching measurements:', error);
            });
    }
    
    // Function to create level chart
    function createLevelChart(measurements) {
        if (!measurements || measurements.length === 0) {
            return;
        }
        
        // Reverse measurements to show oldest first
        measurements = measurements.reverse();
        
        const ctx = document.getElementById('levelChart').getContext('2d');
        const chart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: measurements.map(m => {
                    const date = new Date(m.timestamp);
                    return date.toLocaleString();
                }),
                datasets: [
                    {
                        label: 'Fill Level (%)',
                        data: measurements.map(m => m.fill_percent),
                        borderColor: 'rgba(75, 192, 192, 1)',
                        backgroundColor: 'rgba(75, 192, 192, 0.2)',
                        tension: 0.1,
                        yAxisID: 'y'
                    },
                    {
                        label: 'Volume (L)',
                        data: measurements.map(m => m.volume),
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
    }
    
    // Fetch measurements and create chart
    fetchMeasurements();
    
    // Set up refresh button
    const refreshBtn = document.getElementById('refresh-data');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', function() {
            location.reload();
        });
    }
    
    // Set up auto-refresh
    setInterval(function() {
        location.reload();
    }, 5 * 60 * 1000); // Refresh every 5 minutes
    
    // Set up export button
    const exportBtn = document.getElementById('export-data');
    if (exportBtn) {
        exportBtn.addEventListener('click', function() {
            window.location.href = `/download/tank/${tankId}/csv?hours=24`;
        });
    }
    
    // Set up alarm acknowledgement buttons
    document.querySelectorAll('.acknowledge-alarm-btn').forEach(function(button) {
        button.addEventListener('click', function() {
            const alarmId = this.getAttribute('data-alarm-id');
            
            fetch(`/admin/alarms/acknowledge/${alarmId}`, {
                method: 'POST', headers: { 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]).content }
            })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        // Reload the page to show updated alarm status
                        location.reload();
                    } else {
                        alert('Error acknowledging alarm: ' + data.message);
                    }
                })
                .catch(error => {
                    console.error('Error acknowledging alarm:', error);
                    alert('Error acknowledging alarm: ' + error.message);
                });
        });
    });
    
    // Set up tank connection test button
    const testConnectionBtn = document.getElementById('test-connection');
    if (testConnectionBtn) {
        testConnectionBtn.addEventListener('click', function() {
            // Show loading state
            const originalText = this.innerHTML;
            this.innerHTML = '<i class="bi bi-arrow-repeat"></i> Testing...';
            this.disabled = true;
            
            fetch(`/admin/api/tanks/${tankId}/test-connection`, {
                method: 'POST', headers: { 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]).content }
            })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        alert('Connection successful! Tank is reachable.');
                    } else {
                        alert('Connection failed: ' + data.message);
                    }
                })
                .catch(error => {
                    console.error('Error testing connection:', error);
                    alert('Error testing connection: ' + error.message);
                })
                .finally(() => {
                    // Reset button state
                    this.innerHTML = originalText;
                    this.disabled = false;
                });
        });
    }
    
    // Set up tank calibration button
    const calibrateBtn = document.getElementById('calibrate-tank');
    if (calibrateBtn) {
        calibrateBtn.addEventListener('click', function() {
            const knownVolume = prompt('Enter the known volume in liters:');
            
            if (knownVolume === null) {
                // User cancelled
                return;
            }
            
            // Validate input
            const volume = parseFloat(knownVolume);
            if (isNaN(volume) || volume <= 0) {
                alert('Please enter a valid volume greater than zero.');
                return;
            }
            
            // Show loading state
            const originalText = this.innerHTML;
            this.innerHTML = '<i class="bi bi-arrow-repeat"></i> Calibrating...';
            this.disabled = true;
            
            fetch(`/admin/api/tanks/${tankId}/calibrate`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content
                },
                body: JSON.stringify({ known_volume: volume })
            })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        alert(`Calibration successful! New calibration factor: ${data.calibration_factor.toFixed(4)}`);
                        location.reload();
                    } else {
                        alert('Calibration failed: ' + data.message);
                    }
                })
                .catch(error => {
                    console.error('Error calibrating tank:', error);
                    alert('Error calibrating tank: ' + error.message);
                })
                .finally(() => {
                    // Reset button state
                    this.innerHTML = originalText;
                    this.disabled = false;
                });
        });
    }
    
    // Set up tank reset button
    const resetBtn = document.getElementById('reset-tank');
    if (resetBtn) {
        resetBtn.addEventListener('click', function() {
            if (confirm('Are you sure you want to reset all tank data? This will clear all measurements and alarms for this tank.')) {
                // Show loading state
                const originalText = this.innerHTML;
                this.innerHTML = '<i class="bi bi-arrow-repeat"></i> Resetting...';
                this.disabled = true;
                
                fetch(`/admin/api/tanks/${tankId}/reset`, {
                    method: 'POST', headers: { 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]).content }
                })
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            alert('Tank data reset successfully!');
                            location.reload();
                        } else {
                            alert('Reset failed: ' + data.message);
                        }
                    })
                    .catch(error => {
                        console.error('Error resetting tank:', error);
                        alert('Error resetting tank: ' + error.message);
                    })
                    .finally(() => {
                        // Reset button state
                        this.innerHTML = originalText;
                        this.disabled = false;
                    });
            }
        });
    }
});