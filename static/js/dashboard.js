/**
 * Dashboard JavaScript
 * 
 * Handles the main dashboard functionality and updates
 */

// Global variables
let socket;
let levelChart;
let flowChart;
let isConnected = false;
let lastMeasurements = null;
let chartData = {
    level: [],
    volume: [],
    flowRate: [],
    labels: []
};

// Maximum number of data points to show on charts
const MAX_DATA_POINTS = 60;

// Initialize the dashboard
function initDashboard() {
    // Initialize Socket.IO connection
    socket = io();
    
    // Socket event handlers
    socket.on('connect', handleSocketConnect);
    socket.on('disconnect', handleSocketDisconnect);
    socket.on('measurements', handleMeasurements);
    socket.on('error', handleError);
    
    // Initialize charts
    initCharts();
    
    // Set up button event handlers
    document.getElementById('connect-btn').addEventListener('click', connectToDevice);
    document.getElementById('disconnect-btn').addEventListener('click', disconnectFromDevice);
    document.getElementById('reset-btn').addEventListener('click', resetStatistics);
    document.getElementById('reset-stats-btn').addEventListener('click', resetStatistics);
    
    // Check initial connection status
    checkConnectionStatus();
}

// Handle Socket.IO connection
function handleSocketConnect() {
    //console.log('Connected to server');
    checkConnectionStatus();
}

// Handle Socket.IO disconnection
function handleSocketDisconnect() {
    //console.log('Disconnected from server');
    updateConnectionStatus(false);
}

// Handle incoming measurements
function handleMeasurements(data) {
    //console.log('Received measurements:', data);
    
    // Update last measurements
    lastMeasurements = data.measurements;
    
    // Update UI with new measurements
    updateDashboard(data.measurements);
}

// Handle errors
function handleError(error) {
    console.error('Error:', error);
    showAlert('error', error.message || 'An error occurred');
}

// Dashboard page JavaScript
//let levelChart, flowChart;
const maxDataPoints = 50;
const levelData = [];
const flowData = [];

// Initialize charts
function initCharts() {
    // Level chart
    const levelCtx = document.getElementById('level-chart').getContext('2d');
    levelChart = new Chart(levelCtx, {
        type: 'line',
        data: {
            datasets: [{
                label: 'Level (m)',
                data: levelData,
                borderColor: '#0d6efd',
                backgroundColor: 'rgba(13, 110, 253, 0.1)',
                borderWidth: 2,
                fill: true,
                tension: 0.2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    type: 'time',
                    time: {
                        unit: 'minute',
                        displayFormats: {
                            minute: 'HH:mm:ss'
                        }
                    },
                    title: {
                        display: true,
                        text: 'Time'
                    }
                },
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: 'Level (m)'
                    }
                }
            },
            plugins: {
                legend: {
                    display: true,
                    position: 'top'
                }
            }
        }
    });
    
    // Flow chart
    const flowCtx = document.getElementById('flow-chart').getContext('2d');
    flowChart = new Chart(flowCtx, {
        type: 'line',
        data: {
            datasets: [{
                label: 'Flow Rate (L/min)',
                data: flowData,
                borderColor: '#20c997',
                backgroundColor: function(context) {
                    const value = context.dataset.data[context.dataIndex]?.y;
                    return value >= 0 ? 'rgba(32, 201, 151, 0.1)' : 'rgba(220, 53, 69, 0.1)';
                },
                borderWidth: 2,
                fill: true
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    type: 'time',
                    time: {
                        unit: 'minute',
                        displayFormats: {
                            minute: 'HH:mm:ss'
                        }
                    },
                    title: {
                        display: true,
                        text: 'Time'
                    }
                },
                y: {
                    title: {
                        display: true,
                        text: 'Flow Rate (L/min)'
                    }
                }
            },
            plugins: {
                legend: {
                    display: true,
                    position: 'top'
                }
            }
        }
    });
}

// Update tank visualization
function updateTankVisualization(fillPercent) {
    const tankFill = document.getElementById('tank-fill');
    if (tankFill) {
        // Limit to 0-100%
        fillPercent = Math.max(0, Math.min(100, fillPercent));
        
        // Update fill height
        tankFill.style.height = `${fillPercent}%`;
        
        // Update fill color based on level
        if (fillPercent < 20) {
            tankFill.style.backgroundColor = '#dc3545'; // Red for low level
        } else if (fillPercent < 40) {
            tankFill.style.backgroundColor = '#ffc107'; // Yellow for medium-low
        } else {
            tankFill.style.backgroundColor = '#0d6efd'; // Blue for good level
        }
    }
}

// Update status indicators
function updateStatusIndicators(status) {
    const statusContainer = document.getElementById('status-indicators');
    if (!statusContainer) return;
    
    // Clear current indicators
    statusContainer.innerHTML = '';
    
    // Check if status is a number (raw status byte)
    if (typeof status === 'number') {
        // Convert to binary string
        const statusBits = status.toString(2).padStart(8, '0');
        
        // Create status indicators based on bits
        const statusMap = [
            { bit: 0, label: 'Communication Error', color: 'danger' },
            { bit: 1, label: 'Memory Error', color: 'danger' },
            { bit: 2, label: 'Sensor Error', color: 'danger' },
            { bit: 3, label: 'Math Error', color: 'danger' },
            { bit: 4, label: 'New Min/Max', color: 'info' },
            { bit: 5, label: 'Busy', color: 'warning' },
            { bit: 6, label: 'Negative', color: 'warning' },
            { bit: 7, label: 'Overflow', color: 'danger' }
        ];
        
        // Check each bit and create badge if set
        let hasErrors = false;
        for (let i = 0; i < statusMap.length; i++) {
            const bitIndex = 7 - i; // Reverse order for display
            if (statusBits[bitIndex] === '1') {
                const item = statusMap[i];
                statusContainer.innerHTML += `
                    <span class="status-indicator badge bg-${item.color}">${item.label}</span>
                `;
                if (item.color === 'danger') {
                    hasErrors = true;
                }
            }
        }
        
        // If no errors, show OK status
        if (!hasErrors && status === 0) {
            statusContainer.innerHTML = `
                <span class="status-indicator badge bg-success">System OK</span>
            `;
        }
    }
}

// Update measurement displays
function updateMeasurements(data) {
    // Update basic measurements
    document.getElementById('pressure-value').textContent = `${data.pressure.toFixed(4)} bar`;
    document.getElementById('volume-value').textContent = `${data.volume.toFixed(1)} L`;
    document.getElementById('fill-value').textContent = `${data.fill_percent.toFixed(1)}%`;
    
    // Update temperature if available
    if (data.temperature !== null && data.temperature !== undefined) {
        document.getElementById('temperature-value').textContent = `${data.temperature.toFixed(2)} °C`;
    } else {
        document.getElementById('temperature-value').textContent = 'N/A';
    }
    
    // Update flow rate with direction indicator
    const flowElement = document.getElementById('flow-value');
    let flowText = `${Math.abs(data.flow_rate).toFixed(2)} L/min`;
    
    if (data.flow_rate > 0.5) {
        flowElement.innerHTML = `<span class="flow-positive">+${flowText} ↑</span>`;
    } else if (data.flow_rate < -0.5) {
        flowElement.innerHTML = `<span class="flow-negative">-${flowText} ↓</span>`;
    } else {
        flowElement.innerHTML = `<span class="flow-neutral">${flowText} →</span>`;
    }
    
    // Update statistics
    document.getElementById('min-level-value').textContent = `${data.min_level.toFixed(3)} m`;
    document.getElementById('max-level-value').textContent = `${data.max_level.toFixed(3)} m`;
    document.getElementById('min-volume-value').textContent = `${data.min_volume.toFixed(1)} L`;
    document.getElementById('max-volume-value').textContent = `${data.max_volume.toFixed(1)} L`;
    document.getElementById('total-inflow-value').textContent = `${data.total_inflow.toFixed(1)} L`;
    document.getElementById('total-outflow-value').textContent = `${data.total_outflow.toFixed(1)} L`;
    
    // Update tank capacity
    const tankCapacity = document.getElementById('tank-capacity');
    if (tankCapacity) {
        // Calculate tank capacity in liters
        const diameter = parseFloat(tankCapacity.dataset.diameter || 0);
        const height = parseFloat(tankCapacity.dataset.height || 0);
        const orientation = tankCapacity.dataset.orientation || 'vertical';
        
        if (diameter > 0 && height > 0) {
            const capacityLiters = Math.PI * Math.pow(diameter/2, 2) * height * 1000;
            tankCapacity.textContent = `${capacityLiters.toFixed(1)} L`;
        }
    }
    
    // Update tank visualization
    updateTankVisualization(data.fill_percent);
    
    // Update status indicators
    updateStatusIndicators(data.status);
    
    // Update charts
    const now = new Date();
    
    // Add data to level chart
    levelData.push({
        x: now,
        y: data.level
    });
    
    // Add data to flow chart
    flowData.push({
        x: now,
        y: data.flow_rate
    });
    
    // Limit data points
    if (levelData.length > maxDataPoints) {
        levelData.shift();
    }
    
    if (flowData.length > maxDataPoints) {
        flowData.shift();
    }
    
    // Update charts
    levelChart.update();
    flowChart.update();
}

// Update dashboard with new measurements
function updateDashboard(data) {
    // Update current measurements
    document.getElementById('pressure-value').textContent = `${data.pressure.toFixed(4)} bar`;
    document.getElementById('level-value').textContent = `${data.level.toFixed(3)} m`;
    document.getElementById('volume-value').textContent = `${data.volume.toFixed(1)} L`;
    document.getElementById('fill-value').textContent = `${data.fill_percent.toFixed(1)}%`;
    
    // Update temperature if available
    if (data.temperature !== null && data.temperature !== undefined) {
        document.getElementById('temperature-value').textContent = `${data.temperature.toFixed(2)} °C`;
    } else {
        document.getElementById('temperature-value').textContent = 'N/A';
    }
    
    // Update flow rate with direction indicator
    const flowElement = document.getElementById('flow-value');
    let flowText = `${Math.abs(data.flow_rate).toFixed(2)} L/min`;
    
    if (data.flow_rate > 0.5) {
        flowElement.innerHTML = `<span class="flow-positive">+${flowText} ↑</span>`;
    } else if (data.flow_rate < -0.5) {
        flowElement.innerHTML = `<span class="flow-negative">-${flowText} ↓</span>`;
    } else {
        flowElement.innerHTML = `<span class="flow-neutral">${flowText} →</span>`;
    }
    
    // Update statistics
    document.getElementById('min-level-value').textContent = `${data.min_level.toFixed(3)} m`;
    document.getElementById('max-level-value').textContent = `${data.max_level.toFixed(3)} m`;
    document.getElementById('min-volume-value').textContent = `${data.min_volume.toFixed(1)} L`;
    document.getElementById('max-volume-value').textContent = `${data.max_volume.toFixed(1)} L`;
    document.getElementById('total-inflow-value').textContent = `${data.total_inflow.toFixed(1)} L`;
    document.getElementById('total-outflow-value').textContent = `${data.total_outflow.toFixed(1)} L`;
    
    // Update tank capacity
    const tankCapacity = document.getElementById('tank-capacity');
    if (tankCapacity) {
        // Calculate tank capacity in liters
        const diameter = parseFloat(tankCapacity.dataset.diameter || 0);
        const height = parseFloat(tankCapacity.dataset.height || 0);
        const orientation = tankCapacity.dataset.orientation || 'vertical';
        
        if (diameter > 0 && height > 0) {
            const capacityLiters = Math.PI * Math.pow(diameter/2, 2) * height * 1000;
            tankCapacity.textContent = `${capacityLiters.toFixed(1)} L`;
        }
    }
    
    // Update tank visualization
    updateTankVisualization(data.fill_percent);
    
    // Update status indicators
    updateStatusIndicators(data.status);
    
    // Update charts
    const now = new Date();
    
    // Add data to level chart
    levelData.push({
        x: now,
        y: data.level
    });
    
    // Add data to flow chart
    flowData.push({
        x: now,
        y: data.flow_rate
    });
    
    // Limit data points
    if (levelData.length > maxDataPoints) {
        levelData.shift();
    }
    
    if (flowData.length > maxDataPoints) {
        flowData.shift();
    }
    
    // Update charts
    levelChart.update();
    flowChart.update();
}

// Listen for new measurements
document.addEventListener('new-measurements', function(event) {
    updateMeasurements(event.detail);
});

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    initCharts();
    
    // Set tank capacity data attributes
    const tankCapacity = document.getElementById('tank-capacity');
    if (tankCapacity) {
        // Get tank dimensions from the page
        const diameterElement = document.querySelector('[data-tank-diameter]');
        const heightElement = document.querySelector('[data-tank-height]');
        const orientationElement = document.querySelector('[data-tank-orientation]');
        
        if (diameterElement && heightElement && orientationElement) {
            tankCapacity.dataset.diameter = diameterElement.dataset.tankDiameter;
            tankCapacity.dataset.height = heightElement.dataset.tankHeight;
            tankCapacity.dataset.orientation = orientationElement.dataset.tankOrientation;
        }
    }
});
// Update status indicators
function updateStatusIndicators(status) {
    const statusContainer = document.getElementById('status-indicators');
    statusContainer.innerHTML = '';
    
    // Convert status to binary and interpret
    const statusBinary = status.toString(2).padStart(8, '0');
    const statusFlags = [
        { bit: 0, name: 'Communication Error', color: 'danger' },
        { bit: 1, name: 'Memory Error', color: 'danger' },
        { bit: 2, name: 'Sensor Error', color: 'danger' },
        { bit: 3, name: 'Math Error', color: 'danger' },
        { bit: 4, name: 'New Min/Max', color: 'info' },
        { bit: 5, name: 'Busy', color: 'warning' },
        { bit: 6, name: 'Negative', color: 'warning' },
        { bit: 7, name: 'Overflow', color: 'danger' }
    ];
    
    // Check if any status flags are set
    let anyFlagSet = false;
    
    // Add badges for active status flags
    for (let i = 0; i < statusFlags.length; i++) {
        const flag = statusFlags[i];
        const bitPosition = 7 - flag.bit; // Reverse bit order for display
        
        if (statusBinary[bitPosition] === '1') {
            const badge = document.createElement('span');
            badge.className = `badge bg-${flag.color} me-1 mb-1`;
            badge.textContent = flag.name;
            statusContainer.appendChild(badge);
            anyFlagSet = true;
        }
    }
    
    // If no flags are set, show "Normal" status
    if (!anyFlagSet) {
        const badge = document.createElement('span');
        badge.className = 'badge bg-success me-1 mb-1';
        badge.textContent = 'Normal';
        statusContainer.appendChild(badge);
    }
}

// Connect to device
function connectToDevice() {
    socket.emit('connect_device', {}, (response) => {
        if (response.success) {
            showAlert('success', 'Connected to device');
            updateConnectionStatus(true);
        } else {
            showAlert('danger', `Failed to connect: ${response.message}`);
        }
    });
}

// Disconnect from device
function disconnectFromDevice() {
    socket.emit('disconnect_device', {}, (response) => {
        if (response.success) {
            showAlert('info', 'Disconnected from device');
            updateConnectionStatus(false);
        } else {
            showAlert('danger', `Failed to disconnect: ${response.message}`);
        }
    });
}

// Reset statistics
function resetStatistics() {
    socket.emit('reset_statistics', {}, (response) => {
        if (response.success) {
            showAlert('success', 'Statistics reset');
        } else {
            showAlert('danger', `Failed to reset statistics: ${response.message}`);
        }
    });
}

// Update connection status
function updateConnectionStatus(connected) {
    isConnected = connected;
    
    const statusElement = document.getElementById('connection-status');
    const connectBtn = document.getElementById('connect-btn');
    const disconnectBtn = document.getElementById('disconnect-btn');
    
    if (connected) {
        statusElement.innerHTML = '<i class="bi bi-circle-fill text-success"></i> Connected';
        connectBtn.disabled = true;
        disconnectBtn.disabled = false;
    } else {
        statusElement.innerHTML = '<i class="bi bi-circle-fill text-danger"></i> Disconnected';
        connectBtn.disabled = false;
        disconnectBtn.disabled = true;
    }
}

// Check connection status
function checkConnectionStatus() {
    socket.emit('check_connection', {}, (response) => {
        updateConnectionStatus(response.connected);
    });
}

// Show alert message
function showAlert(type, message) {
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    // Insert at the top of the content area
    const container = document.querySelector('.container-fluid');
    container.insertBefore(alertDiv, container.firstChild);
    
    // Auto-dismiss after 5 seconds
    setTimeout(() => {
        alertDiv.classList.remove('show');
        setTimeout(() => alertDiv.remove(), 150);
    }, 5000);
}

// Initialize with socket connection
document.addEventListener('DOMContentLoaded', function() {
    // Socket connection is handled in socket.js
    // This will automatically connect and set up event listeners
    initDashboard();
});