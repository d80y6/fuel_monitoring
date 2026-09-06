/**
 * Tank Monitor JavaScript
 * Handles real-time monitoring and visualization of tank data
 */

class TankMonitor {
    constructor(tankId, options = {}) {
        this.tankId = tankId;
        this.options = Object.assign({
            updateInterval: 30000, // 30 seconds
            chartHistoryPoints: 20,
            showTemperature: true,
            showPressure: true,
            showFlowRate: true,
            animateChanges: true,
            alertThresholds: {
                critical: 10,
                low: 20,
                high: 90
            }
        }, options);
        
        this.data = {
            current: null,
            history: []
        };
        
        this.charts = {};
        this.updateTimer = null;
        this.socket = null;
        
        this.elements = {
            levelValue: document.getElementById(`tank-${tankId}-level-value`),
            volumeValue: document.getElementById(`tank-${tankId}-volume-value`),
            percentValue: document.getElementById(`tank-${tankId}-percent-value`),
            pressureValue: document.getElementById(`tank-${tankId}-pressure-value`),
            temperatureValue: document.getElementById(`tank-${tankId}-temperature-value`),
            flowRateValue: document.getElementById(`tank-${tankId}-flow-rate-value`),
            lastUpdateValue: document.getElementById(`tank-${tankId}-last-update`),
            statusIndicator: document.getElementById(`tank-${tankId}-status`),
            tankVisualization: document.getElementById(`tank-${tankId}-visualization`),
            levelChart: document.getElementById(`tank-${tankId}-level-chart`),
            volumeChart: document.getElementById(`tank-${tankId}-volume-chart`),
            flowRateChart: document.getElementById(`tank-${tankId}-flow-rate-chart`)
        };
    }
    
    /**
     * Initialize the tank monitor
     */
    init() {
        // Fetch initial data
        this.fetchData();
        
        // Set up update timer
        this.updateTimer = setInterval(() => {
            this.fetchData();
        }, this.options.updateInterval);
        
        // Set up WebSocket connection if available
        this.initializeSocket();
        
        // Initialize charts
        this.initializeCharts();
        
        // Set up event listeners
        this.setupEventListeners();
        
        return this;
    }
    
    /**
     * Fetch current tank data from the server
     */
    fetchData() {
        fetch(`/api/tank/${this.tankId}/measurements`)
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    console.error('Error fetching tank data:', data.error);
                    this.updateStatusIndicator('error');
                    return;
                }
                
                // Update data
                const previousData = this.data.current;
                this.data.current = data;
                
                // Add to history (limit to chartHistoryPoints)
                this.data.history.push(data);
                if (this.data.history.length > this.options.chartHistoryPoints) {
                    this.data.history.shift();
                }
                
                // Update UI
                this.updateUI(previousData);
                
                // Update charts
                this.updateCharts();
            })
            .catch(error => {
                console.error('Error fetching tank data:', error);
                this.updateStatusIndicator('error');
            });
    }
    
    /**
     * Initialize WebSocket connection for real-time updates
     */
    initializeSocket() {
        if (typeof io !== 'undefined') {
            this.socket = io();
            
            // Join tank room
            this.socket.emit('join_tank', { tank_id: this.tankId });
            
            // Listen for tank updates
            this.socket.on(`tank_update_${this.tankId}`, (data) => {
                const previousData = this.data.current;
                this.data.current = data;
                
                // Add to history (limit to chartHistoryPoints)
                this.data.history.push(data);
                if (this.data.history.length > this.options.chartHistoryPoints) {
                    this.data.history.shift();
                }
                
                // Update UI
                this.updateUI(previousData);
                
                // Update charts
                this.updateCharts();
            });
            
            // Listen for tank alarms
            this.socket.on(`tank_alarm_${this.tankId}`, (alarm) => {
                this.showAlarm(alarm);
            });
        }
    }
    
    /**
     * Initialize charts for tank data visualization
     */
    initializeCharts() {
        // Level/Volume Chart
        if (this.elements.levelChart) {
            this.charts.level = new Chart(this.elements.levelChart.getContext('2d'), {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [
                        {
                            label: 'Fill Level (%)',
                            data: [],
                            borderColor: 'rgba(75, 192, 192, 1)',
                            backgroundColor: 'rgba(75, 192, 192, 0.2)',
                            tension: 0.1,
                            yAxisID: 'y'
                        },
                        {
                            label: 'Volume (L)',
                            data: [],
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
        
        // Flow Rate Chart
        if (this.elements.flowRateChart) {
            this.charts.flowRate = new Chart(this.elements.flowRateChart.getContext('2d'), {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [
                        {
                            label: 'Flow Rate (L/h)',
                            data: [],
                            borderColor: 'rgba(255, 99, 132, 1)',
                            backgroundColor: 'rgba(255, 99, 132, 0.2)',
                            tension: 0.1
                        }
                    ]
                },
                options: {
                    responsive: true,
                    scales: {
                        x: {
                            title: {
                                display: true,
                                text: 'Time'
                            }
                        },
                        y: {
                            title: {
                                display: true,
                                text: 'Flow Rate (L/h)'
                            },
                            min: 0
                        }
                    }
                }
            });
        }
    }
    
    /**
     * Update UI elements with current tank data
     */
    updateUI(previousData) {
        if (!this.data.current) return;
        
        const data = this.data.current;
        const isFirstUpdate = !previousData;
        
        // Update level value
        if (this.elements.levelValue) {
            this.updateElement(this.elements.levelValue, data.level.toFixed(3) + ' m', isFirstUpdate);
        }
        
        // Update volume value
        if (this.elements.volumeValue) {
            this.updateElement(this.elements.volumeValue, data.volume.toFixed(1) + ' L', isFirstUpdate);
        }
        
        // Update percent value
        if (this.elements.percentValue) {
            this.updateElement(this.elements.percentValue, data.fill_percent.toFixed(1) + '%', isFirstUpdate);
        }
        
        // Update pressure value
        if (this.elements.pressureValue && this.options.showPressure) {
            this.updateElement(this.elements.pressureValue, data.pressure.toFixed(3) + ' bar', isFirstUpdate);
        }
        
        // Update temperature value
        if (this.elements.temperatureValue && this.options.showTemperature && data.temperature !== null) {
            this.updateElement(this.elements.temperatureValue, data.temperature.toFixed(1) + ' °C', isFirstUpdate);
        }
        
        // Update flow rate value
        if (this.elements.flowRateValue && this.options.showFlowRate) {
            this.updateElement(this.elements.flowRateValue, data.flow_rate.toFixed(2) + ' L/h', isFirstUpdate);
        }
        
        // Update last update time
        if (this.elements.lastUpdateValue) {
            const date = new Date(data.timestamp);
            this.elements.lastUpdateValue.textContent = date.toLocaleString();
        }
        
        // Update status indicator
        this.updateStatusIndicator(data.status);
        
        // Update tank visualization
        this.updateTankVisualization(data.fill_percent);
    }
    
    /**
     * Update an element with new value, with optional animation
     */
    updateElement(element, newValue, isFirstUpdate) {
        if (this.options.animateChanges && !isFirstUpdate) {
            // Add highlight class
            element.classList.add('highlight');
            
            // Remove highlight class after animation completes
            setTimeout(() => {
                element.classList.remove('highlight');
            }, 1000);
        }
        
        // Update text
        element.textContent = newValue;
    }
    
    /**
     * Update status indicator based on status code
     */
    updateStatusIndicator(status) {
        if (!this.elements.statusIndicator) return;
        
        // Remove all status classes
        this.elements.statusIndicator.classList.remove('status-ok', 'status-warning', 'status-error');
        
        // Add appropriate class based on status
        if (status === 'error' || status === 0) {
            this.elements.statusIndicator.classList.add('status-error');
            this.elements.statusIndicator.textContent = 'Error';
        } else if (status === 1) {
            this.elements.statusIndicator.classList.add('status-ok');
            this.elements.statusIndicator.textContent = 'Normal';
        } else if (status === 2) {
            this.elements.statusIndicator.classList.add('status-warning');
            this.elements.statusIndicator.textContent = 'Warning';
        } else {
            this.elements.statusIndicator.classList.add('status-error');
            this.elements.statusIndicator.textContent = 'Unknown';
        }
    }
    
    /**
     * Update tank visualization based on fill percentage
     */
    updateTankVisualization(fillPercent) {
        if (!this.elements.tankVisualization) return;
        
        // Get tank level element
        const tankLevel = this.elements.tankVisualization.querySelector('.tank-level');
        if (!tankLevel) return;
        
        // Update height based on fill percentage
        tankLevel.style.height = fillPercent + '%';
        
        // Update class based on thresholds
        tankLevel.classList.remove('low', 'critical', 'high');
        
        if (fillPercent <= this.options.alertThresholds.critical) {
            tankLevel.classList.add('critical');
        } else if (fillPercent <= this.options.alertThresholds.low) {
            tankLevel.classList.add('low');
        } else if (fillPercent >= this.options.alertThresholds.high) {
            tankLevel.classList.add('high');
        }
    }
    
    /**
     * Update charts with current data history
     */
    updateCharts() {
        if (this.data.history.length === 0) return;
        
        // Prepare data for charts
        const labels = this.data.history.map(item => {
            const date = new Date(item.timestamp);
            return date.toLocaleTimeString();
        });
        
        const fillPercentData = this.data.history.map(item => item.fill_percent);
        const volumeData = this.data.history.map(item => item.volume);
        const flowRateData = this.data.history.map(item => item.flow_rate);
        
        // Update level/volume chart
        if (this.charts.level) {
            this.charts.level.data.labels = labels;
            this.charts.level.data.datasets[0].data = fillPercentData;
            this.charts.level.data.datasets[1].data = volumeData;
            this.charts.level.update();
        }
        
        // Update flow rate chart
        if (this.charts.flowRate) {
            this.charts.flowRate.data.labels = labels;
            this.charts.flowRate.data.datasets[0].data = flowRateData;
            this.charts.flowRate.update();
        }
    }
    
    /**
     * Show an alarm notification
     */
    showAlarm(alarm) {
        // Create toast notification
        const toastContainer = document.getElementById('toast-container');
        if (!toastContainer) return;
        
        // Create toast element
        const toast = document.createElement('div');
        toast.className = 'toast';
        toast.setAttribute('role', 'alert');
        toast.setAttribute('aria-live', 'assertive');
        toast.setAttribute('aria-atomic', 'true');
        
        // Set toast classes based on alarm type
        if (alarm.type === 'critical_level') {
            toast.classList.add('bg-danger', 'text-white');
        } else if (alarm.type === 'low_level' || alarm.type === 'high_level') {
            toast.classList.add('bg-warning', 'text-dark');
        } else if (alarm.type === 'connection') {
            toast.classList.add('bg-danger', 'text-white');
        } else {
            toast.classList.add('bg-info', 'text-white');
        }
        
        // Format timestamp
        const timestamp = new Date(alarm.timestamp).toLocaleString();
        
        // Set toast content
        toast.innerHTML = `
            <div class="toast-header">
                <strong class="me-auto">Tank Alarm</strong>
                <small>${timestamp}</small>
                <button type="button" class="btn-close" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
            <div class="toast-body">
                ${alarm.message}
            </div>
        `;
        
        // Add toast to container
        toastContainer.appendChild(toast);
        
        // Initialize and show toast
        const bsToast = new bootstrap.Toast(toast, {
            autohide: true,
            delay: 10000
        });
        bsToast.show();
        
        // Play alarm sound if available
        const alarmSound = document.getElementById('alarm-sound');
        if (alarmSound) {
            alarmSound.play().catch(e => {
                //console.log('Could not play alarm sound:', e);
            });
        }
    }
    
    /**
     * Set up event listeners
     */
    setupEventListeners() {
        // Refresh button
        const refreshButton = document.getElementById(`tank-${this.tankId}-refresh`);
        if (refreshButton) {
            refreshButton.addEventListener('click', () => {
                this.fetchData();
            });
        }
        
        // Export data button
        const exportButton = document.getElementById(`tank-${this.tankId}-export`);
        if (exportButton) {
            exportButton.addEventListener('click', () => {
                window.location.href = `/download/tank/${this.tankId}/csv`;
            });
        }
        
        // Acknowledge alarm buttons
        document.querySelectorAll(`.acknowledge-alarm-btn[data-tank-id="${this.tankId}"]`).forEach(button => {
            button.addEventListener('click', () => {
                const alarmId = button.getAttribute('data-alarm-id');
                this.acknowledgeAlarm(alarmId);
            });
        });
    }
    
    /**
     * Acknowledge an alarm
     */
    acknowledgeAlarm(alarmId) {
        fetch(`/alarm/${alarmId}/acknowledge`, {
            method: 'POST'
        })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // Remove alarm from UI or update its status
                    const alarmElement = document.querySelector(`.alarm-item[data-alarm-id="${alarmId}"]`);
                    if (alarmElement) {
                        alarmElement.classList.add('acknowledged');
                        const statusBadge = alarmElement.querySelector('.alarm-status');
                        if (statusBadge) {
                            statusBadge.textContent = 'Acknowledged';
                            statusBadge.classList.remove('bg-danger');
                            statusBadge.classList.add('bg-success');
                        }
                    }
                } else {
                    console.error('Error acknowledging alarm:', data.error);
                }
            })
            .catch(error => {
                console.error('Error acknowledging alarm:', error);
            });
    }
    
    /**
     * Stop monitoring and clean up resources
     */
    destroy() {
        // Clear update timer
        if (this.updateTimer) {
            clearInterval(this.updateTimer);
            this.updateTimer = null;
        }
        
        // Disconnect socket
        if (this.socket) {
            this.socket.disconnect();
            this.socket = null;
        }
        
        // Destroy charts
        for (const chartKey in this.charts) {
            if (this.charts[chartKey]) {
                this.charts[chartKey].destroy();
                this.charts[chartKey] = null;
            }
        }
        
        // Clear data
        this.data = {
            current: null,
            history: []
        };
    }
}

// Initialize tank monitors when document is ready
document.addEventListener('DOMContentLoaded', function() {
    // Find all tank monitor containers
    const tankMonitorContainers = document.querySelectorAll('[data-tank-monitor]');
    
    // Initialize a monitor for each container
    tankMonitorContainers.forEach(container => {
        const tankId = container.getAttribute('data-tank-id');
        if (tankId) {
            // Get options from data attributes
            const options = {
                updateInterval: parseInt(container.getAttribute('data-update-interval') || '30000'),
                showTemperature: container.getAttribute('data-show-temperature') !== 'false',
                showPressure: container.getAttribute('data-show-pressure') !== 'false',
                showFlowRate: container.getAttribute('data-show-flow-rate') !== 'false',
                animateChanges: container.getAttribute('data-animate-changes') !== 'false',
                alertThresholds: {
                    critical: parseInt(container.getAttribute('data-critical-threshold') || '10'),
                    low: parseInt(container.getAttribute('data-low-threshold') || '20'),
                    high: parseInt(container.getAttribute('data-high-threshold') || '90')
                }
            };
            
            // Create and initialize monitor
            const monitor = new TankMonitor(tankId, options);
            monitor.init();
            
            // Store monitor instance on the container for future reference
            container.tankMonitor = monitor;
        }
    });
});