// Global variables
let tankId = null;
let mainChart = null;
let temperatureChart = null;
let flowRateChart = null;
let pressureChart = null;
let autoRefreshInterval = null;
let forecastChart = null;

// Initialize the page
// More robust tank ID extraction
document.addEventListener('DOMContentLoaded', function() {
    // Get tank ID from the URL
    const pathParts = window.location.pathname.split('/');
    const tanksIndex = pathParts.indexOf('tanks');
    
    if (tanksIndex !== -1 && tanksIndex + 1 < pathParts.length) {
        tankId = pathParts[tanksIndex + 1];
        //console.log("Tank ID extracted from URL:", tankId);
    } else {
        // Try to get tank ID from a data attribute on the page
        const tankElement = document.querySelector('[data-tank-id]');
        if (tankElement) {
            tankId = tankElement.getAttribute('data-tank-id');
            //console.log("Tank ID from data attribute:", tankId);
        } else {
            //console.error("Could not determine tank ID");
            showError("Could not determine tank ID");
            return;
        }
    }
    
    // Initialize date pickers
    initDatePickers();
    
    // Initialize tooltips
    initTooltips();
    
    // Set CSS variables for tank level markers
    const tankLevel = document.getElementById('current-tank-level');
    if (tankLevel) {
        document.documentElement.style.setProperty('--critical-threshold', tankLevel.getAttribute('data-critical-threshold') + '%');
        document.documentElement.style.setProperty('--low-threshold', tankLevel.getAttribute('data-low-threshold') + '%');
        document.documentElement.style.setProperty('--high-threshold', tankLevel.getAttribute('data-high-threshold') + '%');
    }
    
    // Set up event listeners
    setupEventListeners();
    
    // Load initial data
    loadData();
});

/**
 * Updates the statistics section with calculated values from measurement data
 * @param {Array} measurements - Array of measurement objects from the API
 */
function updateStatisticsFromMeasurements(measurements) {
    if (!measurements || measurements.length === 0) {
        // No data available
        document.getElementById('no-data-message').style.display = 'block';
        return;
    }
    
    const element = document.getElementById('no-data-message');
    if (element) {
        element.style.display = 'none';
    }
    
    // Calculate statistics
    let totalLevel = 0;
    let totalVolume = 0;
    let totalFlowRate = 0;
    let totalTemperature = 0;
    let totalPressure = 0;
    
    let minLevel = measurements[0].level;
    let maxLevel = measurements[0].level;
    let minVolume = measurements[0].volume;
    let maxVolume = measurements[0].volume;
    
    // Calculate total and find min/max values
    measurements.forEach(m => {
        if (m.level !== null && !isNaN(m.level)) {
            totalLevel += m.level;
            minLevel = Math.min(minLevel, m.level);
            maxLevel = Math.max(maxLevel, m.level);
        }
        
        if (m.volume !== null && !isNaN(m.volume)) {
            totalVolume += m.volume;
            minVolume = Math.min(minVolume, m.volume);
            maxVolume = Math.max(maxVolume, m.volume);
        }
        
        if (m.flow_rate !== null && !isNaN(m.flow_rate)) {
            totalFlowRate += m.flow_rate;
        }
        
        if (m.temperature !== null && !isNaN(m.temperature)) {
            totalTemperature += m.temperature;
        }
        
        if (m.pressure !== null && !isNaN(m.pressure)) {
            totalPressure += m.pressure;
        }
    });
    
    // Calculate averages
    const avgLevel = totalLevel / measurements.length;
    const avgVolume = totalVolume / measurements.length;
    const avgFlowRate = totalFlowRate / measurements.length;
    const avgTemperature = totalTemperature / measurements.length;
    const avgPressure = totalPressure / measurements.length;
    
    // Calculate volume change (last measurement - first measurement)
    const firstMeasurement = measurements[0];
    const lastMeasurement = measurements[measurements.length - 1];
    const volumeChange = lastMeasurement.volume - firstMeasurement.volume;
    
    // Update the statistics in the DOM
    document.getElementById('avg-level').textContent = avgLevel.toFixed(3) + ' m';
    document.getElementById('min-level').textContent = minLevel.toFixed(3) + ' m';
    document.getElementById('max-level').textContent = maxLevel.toFixed(3) + ' m';
    
    document.getElementById('avg-volume').textContent = avgVolume.toFixed(1) + ' L';
    document.getElementById('min-volume').textContent = minVolume.toFixed(1) + ' L';
    document.getElementById('max-volume').textContent = maxVolume.toFixed(1) + ' L';
    
    document.getElementById('avg-flow').textContent = avgFlowRate.toFixed(2) + ' L/min';
    document.getElementById('volume-change').textContent = volumeChange.toFixed(1) + ' L';
    
    // Update current tank status
    if (lastMeasurement) {
        document.getElementById('current-level').textContent = lastMeasurement.level.toFixed(3) + ' m';
        document.getElementById('current-volume').textContent = lastMeasurement.volume.toFixed(1) + ' L';
        document.getElementById('current-fill').textContent = lastMeasurement.fill_percent.toFixed(1) + '%';
        document.getElementById('last-updated').textContent = new Date(lastMeasurement.timestamp).toLocaleString();
        
        // Update tank visualization
        const tankLevel = document.getElementById('current-tank-level');
        tankLevel.style.height = Math.min(100, Math.max(0, lastMeasurement.fill_percent)) + '%';
        
        // Set color based on fill level
        if (lastMeasurement.fill_percent <= 10) {
            tankLevel.className = 'tank-level critical';
        } else if (lastMeasurement.fill_percent <= 25) {
            tankLevel.className = 'tank-level low';
        } else if (lastMeasurement.fill_percent >= 90) {
            tankLevel.className = 'tank-level high';
        } else {
            tankLevel.className = 'tank-level normal';
        }
    }
}
function setupEventListeners() {
    // Range selector change
    document.getElementById('range-selector').addEventListener('change', function() {
        if (this.value === 'custom') {
            document.getElementById('custom-date-range').style.display = 'flex';
        } else {
            document.getElementById('custom-date-range').style.display = 'none';
            loadData();
        }
    });
    
    // Apply custom range button
    document.getElementById('apply-custom-range').addEventListener('click', loadData);
    
    // Chart type selector
    document.getElementById('chart-type-selector').addEventListener('change', updateChartType);
    
    // Metrics selector
    document.getElementById('metrics-selector').addEventListener('change', updateVisibleMetrics);
    
    // Refresh button
    document.getElementById('refresh-data').addEventListener('click', loadData);
    
    // Auto-refresh toggle
    document.getElementById('auto-refresh-toggle').addEventListener('click', toggleAutoRefresh);
    
    // Zoom reset button
    document.getElementById('zoom-reset').addEventListener('click', resetZoom);
    
    // Download chart image
    document.getElementById('download-chart-image').addEventListener('click', downloadChartImage);
    
    // Toggle annotations
    document.getElementById('toggle-annotations').addEventListener('click', toggleAnnotations);
    
    // Toggle legend
    document.getElementById('toggle-legend').addEventListener('click', toggleLegend);
    
    // Export buttons
    document.getElementById('export-excel').addEventListener('click', exportToExcel);
    document.getElementById('export-pdf').addEventListener('click', exportToPDF);
    
    // Update CSV export link when time range changes
    document.getElementById('range-selector').addEventListener('change', function() {
        updateExportLinks(getTimeRange());
    });
    
    // Toggle chart visibility
    document.querySelectorAll('.toggle-chart').forEach(button => {
        button.addEventListener('click', function() {
            const chartId = this.getAttribute('data-chart');
            const cardBody = this.closest('.card').querySelector('.card-body');
            const icon = this.querySelector('i');
            
            if (cardBody.style.display === 'none') {
                cardBody.style.display = 'block';
                icon.classList.remove('fa-chevron-down');
                icon.classList.add('fa-chevron-up');
            } else {
                cardBody.style.display = 'none';
                icon.classList.remove('fa-chevron-up');
                icon.classList.add('fa-chevron-down');
            }
        });
    });
    
    // Toggle sections
    document.querySelectorAll('.toggle-section').forEach(button => {
        button.addEventListener('click', function() {
            const cardBody = this.closest('.card').querySelector('.card-body');
            const icon = this.querySelector('i');
            
            if (cardBody.style.display === 'none') {
                cardBody.style.display = 'block';
                icon.classList.remove('fa-chevron-down');
                icon.classList.add('fa-chevron-up');
            } else {
                cardBody.style.display = 'none';
                icon.classList.remove('fa-chevron-up');
                icon.classList.add('fa-chevron-down');
            }
        });
    });
}
// Add this function to your JavaScript file or in a <script> tag in the tank_history.html file
function toggleLegend() {
    // Get the chart instance
    const chart = Chart.getChart('mainChart');
    
    if (chart) {
        // Toggle the legend display property
        chart.options.plugins.legend.display = !chart.options.plugins.legend.display;
        
        // Update the chart to reflect the changes
        chart.update();
    }
}


// Then make sure to attach this function to the button click event
document.getElementById('toggle-annotations').addEventListener('click', toggleLegend);
function getTimeRange() {
    const rangeSelector = document.getElementById('range-selector');
    const selectedRange = rangeSelector.value;
    
    const now = new Date();
    let startTime, endTime;
    
    if (selectedRange === 'custom') {
        const startDateInput = document.getElementById('start-date');
        const endDateInput = document.getElementById('end-date');
        
        startTime = new Date(startDateInput.value);
        endTime = new Date(endDateInput.value);
    } else {
        endTime = now;
        
        switch (selectedRange) {
            case '1h':
                startTime = new Date(now.getTime() - (1 * 60 * 60 * 1000));
                break;
            case '6h':
                startTime = new Date(now.getTime() - (6 * 60 * 60 * 1000));
                break;
            case '12h':
                startTime = new Date(now.getTime() - (12 * 60 * 60 * 1000));
                break;
            case '24h':
                startTime = new Date(now.getTime() - (24 * 60 * 60 * 1000));
                break;
            case '7d':
                startTime = new Date(now.getTime() - (7 * 24 * 60 * 60 * 1000));
                break;
            case '30d':
                startTime = new Date(now.getTime() - (30 * 24 * 60 * 60 * 1000));
                break;
            case '90d':
                startTime = new Date(now.getTime() - (90 * 24 * 60 * 60 * 1000));
                break;
            default:
                startTime = new Date(now.getTime() - (7 * 24 * 60 * 60 * 1000));
        }
    }
    
    return {
        start: startTime,
        end: endTime
    };
}

function loadData() {
    showLoading(true);
    
    const timeRange = getTimeRange();
    const selectedMetrics = getSelectedMetrics();
    
    // Update export links
    updateExportLinks(timeRange);
    
    // Determine if we should use hours or days parameter based on the time range
    const diffHours = Math.round((timeRange.end - timeRange.start) / (60 * 60 * 1000));
    
    let url;
    if (diffHours <= 72) {
        // Use hours for shorter time ranges
        url = `/api/tank/${tankId}/history?hours=${diffHours}`;
    } else {
        // Use days for longer time ranges
        const diffDays = Math.ceil(diffHours / 24);
        url = `/api/tank/${tankId}/history?days=${diffDays}`;
    }
    
    //console.log("Fetching data from:", url); // Add logging to debug
    
    // Fetch data from the API
    fetch(url)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! Status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            //console.log("Received data:", data); // Add logging to debug
            
            if (!data.success) {
                throw new Error(data.error || 'Unknown error');
            }
            
            // Check if we have data
            if (!data.measurements || data.measurements.length === 0) {
                const element1 =document.getElementById('no-data-message');
                if (element1) {
                    element1.style.display = 'block';
                }
                const element = document.getElementById('chart-container');
                if (element) {
                    element.style.display = 'none';
                }
                showLoading(false);
                return;
            }

            
            
            // Hide no data message and show chart
            const element = document.getElementById('no-data-message');
            if (element) {
                element.style.display = 'none';
            }
            const element1 = document.getElementById('chart-container');
            if (element) {
                element.style.display = 'block';
            }
            
            // Process and display data
            processAndDisplayData(data.measurements, selectedMetrics);
            
            // Update statistics
            updateStatisticsFromMeasurements(data.measurements);
            
            // Update current status
            updateCurrentStatus(data.measurements[data.measurements.length - 1]);
            
            showLoading(false);
        })
        .catch(error => {
            console.error('Error loading data:', error);
            showError(`Failed to load data: ${error.message}`);
            showLoading(false);
        });

        // After loading measurement data, fetch forecast data
    fetch(`/api/tanks/${tankId}/forecast`)
    .then(response => response.json())
    .then(data => {
        if (data.success && data.forecast) {
            updateForecastData(data.forecast);
        }
    })
    .catch(error => {
        console.error('Error loading forecast data:', error);
    });
}

function processAndDisplayData(measurements, selectedMetrics) {
    // Convert timestamps to Date objects
    const processedData = measurements.map(m => {
        return {
            ...m,
            timestamp: new Date(m.timestamp)
        };
    });
    
    // Create datasets for the chart
    const datasets = [];
    
    selectedMetrics.forEach(metric => {
        if (processedData.some(d => d[metric] !== null && d[metric] !== undefined)) {
            const color = getColorForMetric(metric);
            const yAxisID = getAxisForMetric(metric);
            
            datasets.push({
                label: getLabelForMetric(metric),
                data: processedData.map(d => ({
                    x: d.timestamp,
                    y: d[metric]
                })),
                borderColor: color.border,
                backgroundColor: color.background,
                borderWidth: 2,
                pointRadius: 1,
                pointHoverRadius: 5,
                yAxisID: yAxisID
            });
        }
    });
    
    // Create or update main chart
    const ctx = document.getElementById('mainChart').getContext('2d');
    
    if (mainChart) {
        mainChart.data.datasets = datasets;
        mainChart.options.scales = generateScales(selectedMetrics);
        mainChart.update();
    } else {
        const chartType = getSelectedChartType();
        
        mainChart = new Chart(ctx, {
            type: chartType,
            data: {
                datasets: datasets
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    mode: 'index',
                    intersect: false
                },
                scales: generateScales(selectedMetrics),
                plugins: {
                    zoom: {
                        pan: {
                            enabled: true,
                            mode: 'xy'
                        },
                        zoom: {
                            wheel: {
                                enabled: true
                            },
                            pinch: {
                                enabled: true
                            },
                            mode: 'xy'
                        }
                    },
                    tooltip: {
                        callbacks: {
                            title: function(tooltipItems) {
                                return new Date(tooltipItems[0].parsed.x).toLocaleString();
                            }
                        }
                    },
                    legend: {
                        position: 'top',
                        align: 'center',
                        labels: {
                            boxWidth: 12,
                            usePointStyle: true
                        }
                    }
                }
            }
        });
    }
    
    // Create or update secondary charts if metrics are selected
    updateSecondaryCharts(processedData, selectedMetrics);
}

function updateSecondaryCharts(data, selectedMetrics) {
    // Temperature chart
    if (selectedMetrics.includes('temperature')) {
        const tempCtx = document.getElementById('temperatureChart').getContext('2d');
        const tempData = data.filter(d => d.temperature !== null && d.temperature !== undefined);
        
        if (temperatureChart) {
            temperatureChart.data.labels = tempData.map(d => d.timestamp);
            temperatureChart.data.datasets[0].data = tempData.map(d => d.temperature);
            temperatureChart.update();
        } else if (tempData.length > 0) {
            temperatureChart = new Chart(tempCtx, {
                type: 'line',
                data: {
                    labels: tempData.map(d => d.timestamp),
                    datasets: [{
                        label: 'Temperature (°C)',
                        data: tempData.map(d => d.temperature),
                        borderColor: 'rgb(255, 99, 132)',
                        backgroundColor: 'rgba(255, 99, 132, 0.2)',
                        borderWidth: 2,
                        pointRadius: 1,
                        pointHoverRadius: 5
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        x: {
                            type: 'time',
                            time: {
                                unit: getTimeUnit()
                            }
                        },
                        y: {
                            beginAtZero: false
                        }
                    }
                }
            });
        }
        document.getElementById('temperature-card').style.display = 'block';
    } else {
        document.getElementById('temperature-card').style.display = 'none';
    }
    
    // Flow rate chart
    if (selectedMetrics.includes('flow_rate')) {
        const flowCtx = document.getElementById('flowRateChart').getContext('2d');
        const flowData = data.filter(d => d.flow_rate !== null && d.flow_rate !== undefined);
        
        if (flowRateChart) {
            flowRateChart.data.labels = flowData.map(d => d.timestamp);
            flowRateChart.data.datasets[0].data = flowData.map(d => d.flow_rate);
            flowRateChart.update();
        } else if (flowData.length > 0) {
            flowRateChart = new Chart(flowCtx, {
                type: 'line',
                data: {
                    labels: flowData.map(d => d.timestamp),
                    datasets: [{
                        label: 'Flow Rate (L/min)',
                        data: flowData.map(d => d.flow_rate),
                        borderColor: 'rgb(255, 159, 64)',
                        backgroundColor: 'rgba(255, 159, 64, 0.2)',
                        borderWidth: 2,
                        pointRadius: 1,
                        pointHoverRadius: 5
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        x: {
                            type: 'time',
                            time: {
                                unit: getTimeUnit()
                            }
                        },
                        y: {
                            beginAtZero: false
                        }
                    }
                }
            });
        }
        document.getElementById('flow-rate-card').style.display = 'block';
    } else {
        document.getElementById('flow-rate-card').style.display = 'none';
    }
    
    // Pressure chart
    if (selectedMetrics.includes('pressure')) {
        const pressureCtx = document.getElementById('pressureChart').getContext('2d');
        const pressureData = data.filter(d => d.pressure !== null && d.pressure !== undefined);
        
        if (pressureChart) {
            pressureChart.data.labels = pressureData.map(d => d.timestamp);
            pressureChart.data.datasets[0].data = pressureData.map(d => d.pressure);
            pressureChart.update();
        } else if (pressureData.length > 0) {
            pressureChart = new Chart(pressureCtx, {
                type: 'line',
                data: {
                    labels: pressureData.map(d => d.timestamp),
                    datasets: [{
                        label: 'Pressure (bar)',
                        data: pressureData.map(d => d.pressure),
                        borderColor: 'rgb(75, 192, 192)',
                        backgroundColor: 'rgba(75, 192, 192, 0.2)',
                        borderWidth: 2,
                        pointRadius: 1,
                        pointHoverRadius: 5
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        x: {
                            type: 'time',
                            time: {
                                unit: getTimeUnit()
                            }
                        },
                        y: {
                            beginAtZero: false
                        }
                    }
                }
            });
        }
        document.getElementById('pressure-card').style.display = 'block';
    } else {
        document.getElementById('pressure-card').style.display = 'none';
    }
}

    // Helper functions and other functionality...
    
    function updateTankVisualization() {
        // Update tank visualization based on current data
        const fillPercent = parseFloat(document.getElementById('current-fill').textContent);
        if (!isNaN(fillPercent)) {
            const tankLevel = document.getElementById('current-tank-level');
            tankLevel.style.height = `${fillPercent}%`;
            
            // Update color based on thresholds
            const criticalThreshold = parseFloat(tankLevel.getAttribute('data-critical-threshold'));
            const lowThreshold = parseFloat(tankLevel.getAttribute('data-low-threshold'));
            const highThreshold = parseFloat(tankLevel.getAttribute('data-high-threshold'));
            
            if (fillPercent <= criticalThreshold) {
                tankLevel.className = 'tank-level critical';
            } else if (fillPercent <= lowThreshold) {
                tankLevel.className = 'tank-level low';
            } else if (fillPercent >= highThreshold) {
                tankLevel.className = 'tank-level high';
            } else {
                tankLevel.className = 'tank-level normal';
            }
        }
    }
    
    // Additional utility functions...


// Additional functions for tank_history.js

function getSelectedMetrics() {
    const metricsSelector = document.getElementById('metrics-selector');
    return Array.from(metricsSelector.selectedOptions).map(option => option.value);
}

function getSelectedChartType() {
    return document.getElementById('chart-type-selector').value;
}

function getLabelForMetric(metric) {
    const labels = {
        'level': 'Level (m)',
        'volume': 'Volume (L)',
        'fill_percent': 'Fill Percent (%)',
        'flow_rate': 'Flow Rate (L/min)',
        'temperature': 'Temperature (°C)',
        'pressure': 'Pressure (bar)'
    };
    return labels[metric] || metric;
}

function getColorForMetric(metric) {
    const colors = {
        'level': { border: 'rgb(54, 162, 235)', background: 'rgba(54, 162, 235, 0.2)' },
        'volume': { border: 'rgb(75, 192, 192)', background: 'rgba(75, 192, 192, 0.2)' },
        'fill_percent': { border: 'rgb(153, 102, 255)', background: 'rgba(153, 102, 255, 0.2)' },
        'flow_rate': { border: 'rgb(255, 159, 64)', background: 'rgba(255, 159, 64, 0.2)' },
        'temperature': { border: 'rgb(255, 99, 132)', background: 'rgba(255, 99, 132, 0.2)' },
        'pressure': { border: 'rgb(201, 203, 207)', background: 'rgba(201, 203, 207, 0.2)' }
    };
    return colors[metric] || { border: 'rgb(0, 0, 0)', background: 'rgba(0, 0, 0, 0.2)' };
}

function getAxisForMetric(metric) {
    // Group metrics by axis
    if (['temperature', 'pressure'].includes(metric)) {
        return 'y1';
    } else if (['flow_rate'].includes(metric)) {
        return 'y2';
    } else {
        return 'y';
    }
}

function generateScales(selectedMetrics) {
    const scales = {
        x: {
            type: 'time',
            time: {
                unit: getTimeUnit()
            },
            title: {
                display: true,
                text: 'Time'
            }
        },
        y: {
            type: 'linear',
            display: selectedMetrics.some(m => ['level', 'volume', 'fill_percent'].includes(m)),
            position: 'left',
            title: {
                display: true,
                text: 'Level / Volume / Fill %'
            }
        }
    };
    
    // Add secondary y-axes if needed
    if (selectedMetrics.some(m => ['temperature', 'pressure'].includes(m))) {
        scales.y1 = {
            type: 'linear',
            display: true,
            position: 'right',
            grid: {
                drawOnChartArea: false
            },
            title: {
                display: true,
                text: 'Temperature / Pressure'
            }
        };
    }
    
    if (selectedMetrics.includes('flow_rate')) {
        scales.y2 = {
            type: 'linear',
            display: true,
            position: 'right',
            grid: {
                drawOnChartArea: false
            },
            title: {
                display: true,
                text: 'Flow Rate (L/min)'
            }
        };
    }
    
    return scales;
}

function getTimeUnit() {
    const timeRange = getTimeRange();
    const diffHours = (timeRange.end - timeRange.start) / (1000 * 60 * 60);
    
    if (diffHours <= 24) {
        return 'hour';
    } else if (diffHours <= 24 * 7) {
        return 'day';
    } else if (diffHours <= 24 * 30) {
        return 'week';
    } else {
        return 'month';
    }
}

function updateStatistics(statistics) {
    // Update level statistics
    document.getElementById('avg-level').textContent = statistics.level.avg ? `${statistics.level.avg.toFixed(2)} m` : '--';
    document.getElementById('min-level').textContent = statistics.level.min ? `${statistics.level.min.toFixed(2)} m` : '--';
    document.getElementById('max-level').textContent = statistics.level.max ? `${statistics.level.max.toFixed(2)} m` : '--';
    
    // Update volume statistics
    document.getElementById('avg-volume').textContent = statistics.volume.avg ? `${statistics.volume.avg.toFixed(2)} L` : '--';
    document.getElementById('min-volume').textContent = statistics.volume.min ? `${statistics.volume.min.toFixed(2)} L` : '--';
    document.getElementById('max-volume').textContent = statistics.volume.max ? `${statistics.volume.max.toFixed(2)} L` : '--';
    document.getElementById('volume-change').textContent = statistics.volume.change ? `${statistics.volume.change.toFixed(2)} L` : '--';
    
    // Update flow rate statistics
    document.getElementById('avg-flow').textContent = statistics.flow_rate?.avg ? `${statistics.flow_rate.avg.toFixed(2)} L/min` : '--';
    
    // Update temperature & pressure statistics if elements exist
    const avgTempElement = document.getElementById('avg-temp');
    if (avgTempElement) {
        avgTempElement.textContent = statistics.temperature?.avg ? `${statistics.temperature.avg.toFixed(1)} °C` : '--';
    }
    
    const avgPressureElement = document.getElementById('avg-pressure');
    if (avgPressureElement) {
        avgPressureElement.textContent = statistics.pressure?.avg ? `${statistics.pressure.avg.toFixed(2)} bar` : '--';
    }
    
    // Update consumption data if available
    const estimatedConsumptionElement = document.getElementById('estimated-consumption');
    if (estimatedConsumptionElement && statistics.consumption) {
        estimatedConsumptionElement.textContent = `${statistics.consumption.toFixed(2)} L/day`;
    }
}

function updateCurrentStatus(current) {
    if (!current) return;
    
    document.getElementById('current-level').textContent = `${current.level.toFixed(2)} m`;
    document.getElementById('current-volume').textContent = `${current.volume.toFixed(2)} L`;
    document.getElementById('current-fill').textContent = `${current.fill_percent.toFixed(1)} %`;
    document.getElementById('last-updated').textContent = new Date(current.timestamp).toLocaleString();
    
    // Update tank visualization
    const tankLevel = document.getElementById('current-tank-level');
    if (tankLevel) {
        tankLevel.style.height = `${current.fill_percent}%`;
        
        // Update color based on thresholds
        const criticalThreshold = parseFloat(document.querySelector('.tank-level-marker.critical').getAttribute('title').match(/\d+/)[0]);
        const lowThreshold = parseFloat(document.querySelector('.tank-level-marker.low').getAttribute('title').match(/\d+/)[0]);
        const highThreshold = parseFloat(document.querySelector('.tank-level-marker.high').getAttribute('title').match(/\d+/)[0]);
        
        if (current.fill_percent <= criticalThreshold) {
            tankLevel.className = 'tank-level critical';
        } else if (current.fill_percent <= lowThreshold) {
            tankLevel.className = 'tank-level low';
        } else if (current.fill_percent >= highThreshold) {
            tankLevel.className = 'tank-level high';
        } else {
            tankLevel.className = 'tank-level normal';
        }
    }
}

function updateForecastData(forecast) {
    if (!forecast) return;
    
    // Check if forecast elements exist in the DOM
    const depletionDateElement = document.getElementById('depletion-date');
    const daysRemainingElement = document.getElementById('days-remaining');
    const dailyConsumptionElement = document.getElementById('daily-consumption');
    
    if (depletionDateElement) {
        depletionDateElement.textContent = forecast.depletion_date ? 
            new Date(forecast.depletion_date).toLocaleDateString() : 'N/A';
    }
    
    if (daysRemainingElement) {
        daysRemainingElement.textContent = forecast.days_remaining ? 
            `${Math.round(forecast.days_remaining)} days` : 'N/A';
    }
    
    if (dailyConsumptionElement) {
        dailyConsumptionElement.textContent = forecast.daily_consumption ? 
            `${forecast.daily_consumption.toFixed(2)} L` : 'N/A';
    }
    
    // Update weekly and monthly consumption if elements exist
    const weeklyConsumptionElement = document.getElementById('weekly-consumption');
    const monthlyConsumptionElement = document.getElementById('monthly-consumption');
    
    if (weeklyConsumptionElement) {
        weeklyConsumptionElement.textContent = forecast.weekly_consumption ? 
            `${forecast.weekly_consumption.toFixed(2)} L` : 'N/A';
    }
    
    if (monthlyConsumptionElement) {
        monthlyConsumptionElement.textContent = forecast.monthly_consumption ? 
            `${forecast.monthly_consumption.toFixed(2)} L` : 'N/A';
    }
    
    // Update forecast chart if it exists
    const forecastChartElement = document.getElementById('forecastChart');
    if (forecastChartElement && forecast.data) {
        updateForecastChart(forecast);
    }
}

function updateForecastChart(forecast) {
    if (!forecast || !forecast.data) return;
    
    const forecastChartElement = document.getElementById('forecastChart');
    if (!forecastChartElement) return;
    
    const forecastCtx = forecastChartElement.getContext('2d');
    
    // Check if chart already exists
    if (forecastChart) {
        forecastChart.destroy();
    }
    
    // Create forecast chart
    forecastChart = new Chart(forecastCtx, {
        type: 'line',
        data: {
            datasets: [
                {
                    label: 'Historical Volume',
                    data: forecast.data.historical.map(point => ({
                        x: new Date(point.date),
                        y: point.volume
                    })),
                    borderColor: 'rgb(75, 192, 192)',
                    backgroundColor: 'rgba(75, 192, 192, 0.2)',
                    borderWidth: 2,
                    pointRadius: 0
                },
                {
                    label: 'Forecast Volume',
                    data: forecast.data.forecast.map(point => ({
                        x: new Date(point.date),
                        y: point.volume
                    })),
                    borderColor: 'rgb(153, 102, 255)',
                    backgroundColor: 'rgba(153, 102, 255, 0.2)',
                    borderWidth: 2,
                    borderDash: [5, 5],
                    pointRadius: 0
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    type: 'time',
                    time: {
                        unit: 'day'
                    },
                    title: {
                        display: true,
                        text: 'Date'
                    }
                },
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: 'Volume (L)'
                    }
                }
            },
            plugins: {
                tooltip: {
                    mode: 'index',
                    intersect: false
                },
                annotation: {
                    annotations: {
                        criticalLine: {
                            type: 'line',
                            yMin: forecast.critical_volume,
                            yMax: forecast.critical_volume,
                            borderColor: 'rgb(255, 99, 132)',
                            borderWidth: 2,
                            borderDash: [6, 6],
                            label: {
                                content: 'Critical Level',
                                enabled: true,
                                position: 'start'
                            }
                        }
                    }
                }
            }
        }
    });
}

function showLoading(show) {
    const loadingIndicator = document.getElementById('loading-indicator');
    const chartContainer = document.getElementById('chart-container');
    
    if (show) {
        loadingIndicator.style.display = 'flex';
        chartContainer.style.opacity = '0.5';
    } else {
        loadingIndicator.style.display = 'none';
        chartContainer.style.opacity = '1';
    }
}

function showError(message) {
    // Create or update error toast
    const toastContainer = document.querySelector('.toast-container') || 
        (() => {
            const container = document.createElement('div');
            container.className = 'toast-container position-fixed bottom-0 end-0 p-3';
            document.body.appendChild(container);
            return container;
        })();
    
    const toastId = 'error-toast-' + Date.now();
    const toastHtml = `
        <div id="${toastId}" class="toast" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="toast-header bg-danger text-white">
                <strong class="me-auto">Error</strong>
                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
            <div class="toast-body">
                ${message}
            </div>
        </div>
    `;
    
    toastContainer.insertAdjacentHTML('beforeend', toastHtml);
    const toastElement = document.getElementById(toastId);
    const toast = new bootstrap.Toast(toastElement, { autohide: true, delay: 5000 });
    toast.show();
    
    // Auto-remove toast after it's hidden
    toastElement.addEventListener('hidden.bs.toast', () => {
        toastElement.remove();
    });
}

function toggleAutoRefresh() {
    const button = document.getElementById('auto-refresh-toggle');
    
    if (autoRefreshInterval) {
        // Turn off auto-refresh
        clearInterval(autoRefreshInterval);
        autoRefreshInterval = null;
        button.classList.remove('btn-primary');
        button.classList.add('btn-outline-secondary');
    } else {
        // Turn on auto-refresh (every 30 seconds)
        loadData(); // Load immediately
        autoRefreshInterval = setInterval(loadData, 30000);
        button.classList.remove('btn-outline-secondary');
        button.classList.add('btn-primary');
    }
}

function resetZoom() {
    if (mainChart) {
        mainChart.resetZoom();
    }
}

function downloadChartImage() {
    const canvas = document.getElementById('mainChart');
    const image = canvas.toDataURL('image/png', 1.0);
    
    // Create download link
    const downloadLink = document.createElement('a');
    downloadLink.href = image;
    downloadLink.download = `${document.title.replace(' - Measurement History', '')}_chart_${new Date().toISOString().split('T')[0]}.png`;
    document.body.appendChild(downloadLink);
    downloadLink.click();
    document.body.removeChild(downloadLink);
}

function toggleAnnotations() {
    if (mainChart) {
        const annotationsPlugin = mainChart.options.plugins.annotation;
        annotationsPlugin.annotations = annotationsPlugin.annotations ? null : createAnnotations();
        mainChart.update();
    }
}

function createAnnotations() {
    // Create annotations based on tank thresholds
    const criticalThreshold = parseFloat(document.querySelector('.tank-level-marker.critical').getAttribute('title').match(/\d+/)[0]);
    const lowThreshold = parseFloat(document.querySelector('.tank-level-marker.low').getAttribute('title').match(/\d+/)[0]);
    const highThreshold = parseFloat(document.querySelector('.tank-level-marker.high').getAttribute('title').match(/\d+/)[0]);
    
    return {
        criticalLine: {
            type: 'line',
            yMin: criticalThreshold,
            yMax: criticalThreshold,
            borderColor: 'rgb(255, 99, 132)',
            borderWidth: 2,
            borderDash: [6, 6],
            label: {
                content: 'Critical Level',
                enabled: true,
                position: 'start'
            }
        },
        lowLine: {
            type: 'line',
            yMin: lowThreshold,
            yMax: lowThreshold,
            borderColor: 'rgb(255, 159, 64)',
            borderWidth: 2,
            borderDash: [6, 6],
            label: {
                content: 'Low Level',
                enabled: true,
                position: 'start'
            }
        },
        highLine: {
            type: 'line',
            yMin: highThreshold,
            yMax: highThreshold,
            borderColor: 'rgb(54, 162, 235)',
            borderWidth: 2,
            borderDash: [6, 6],
            label: {
                content: 'High Level',
                enabled: true,
                position: 'start'
            }
        }
    };
}

function updateChartType() {
    const chartType = getSelectedChartType();
    
    if (mainChart) {
        // Save current datasets
        const datasets = mainChart.data.datasets;
        
        // Destroy current chart
        mainChart.destroy();
        
        // Create new chart with selected type
        const ctx = document.getElementById('mainChart').getContext('2d');
        mainChart = new Chart(ctx, {
            type: chartType,
            data: {
                datasets: datasets
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    mode: 'index',
                    intersect: false
                },
                scales: generateScales(getSelectedMetrics()),
                plugins: {
                    zoom: {
                        pan: {
                            enabled: true,
                            mode: 'xy'
                        },
                        zoom: {
                            wheel: {
                                enabled: true
                            },
                            pinch: {
                                enabled: true
                            },
                            mode: 'xy'
                        }
                    },
                    tooltip: {
                        callbacks: {
                            title: function(tooltipItems) {
                                return new Date(tooltipItems[0].parsed.x).toLocaleString();
                            }
                        }
                    },
                    legend: {
                        position: 'top',
                        align: 'center',
                        labels: {
                            boxWidth: 12,
                            usePointStyle: true
                        }
                    }
                }
            }
        });
    }
}

function updateVisibleMetrics() {
    loadData();
}

function exportToExcel() {
    const tankName = document.title.replace(' - Measurement History', '');
    const timeRange = getTimeRange();
    
    // Fetch data for export
    const url = `/api/tanks/${tankId}/export?format=excel&start=${timeRange.start}&end=${timeRange.end}`;
    
    fetch(url)
        .then(response => response.json())
        .then(data => {
            if (!data.measurements || data.measurements.length === 0) {
                showError('No data available to export');
                return;
            }
            
            // Create workbook
            const wb = XLSX.utils.book_new();
            
            // Create worksheet from data
            const ws = XLSX.utils.json_to_sheet(data.measurements.map(m => ({
                Timestamp: new Date(m.timestamp).toLocaleString(),
                'Level (m)': m.level,
                'Volume (L)': m.volume,
                'Fill Percent (%)': m.fill_percent,
                'Flow Rate (L/min)': m.flow_rate || '',
                'Temperature (°C)': m.temperature || '',
                'Pressure (bar)': m.pressure || ''
            })));
            
            // Add worksheet to workbook
            XLSX.utils.book_append_sheet(wb, ws, 'Measurements');
            
            // Generate Excel file and trigger download
            XLSX.writeFile(wb, `${tankName}_data_${new Date().toISOString().split('T')[0]}.xlsx`);
        })
        .catch(error => {
            console.error('Error exporting to Excel:', error);
            showError('Failed to export data to Excel');
        });
}

function exportToPDF() {
    const tankName = document.title.replace(' - Measurement History', '');
    
    // Create PDF document
    const { jsPDF } = window.jspdf;
    const doc = new jsPDF('landscape');
    
    // Add title
    doc.setFontSize(18);
    doc.text(`${tankName} - Measurement History`, 14, 22);
    
    // Add date range
    const timeRange = getTimeRange();
    doc.setFontSize(12);
    doc.text(`Period: ${new Date(timeRange.start).toLocaleDateString()} to ${new Date(timeRange.end).toLocaleDateString()}`, 14, 30);
    
    // Add main chart
    const mainCanvas = document.getElementById('mainChart');
    const mainChartImg = mainCanvas.toDataURL('image/png', 1.0);
    doc.addImage(mainChartImg, 'PNG', 14, 35, 270, 100);
    
    // Add statistics
    doc.text('Statistics', 14, 145);
    
    // Add current status
    doc.text(`Current Level: ${document.getElementById('current-level').textContent}`, 14, 155);
    doc.text(`Current Volume: ${document.getElementById('current-volume').textContent}`, 14, 162);
    doc.text(`Fill Percentage: ${document.getElementById('current-fill').textContent}`, 14, 169);
    
    // Add timestamp
    doc.setFontSize(10);
    doc.text(`Generated on ${new Date().toLocaleString()}`, 14, 200);
    
    // Save PDF
    doc.save(`${tankName}_report_${new Date().toISOString().split('T')[0]}.pdf`);
}

function updateExportLinks(timeRange) {
    // Update CSV export link
    const csvLink = document.getElementById('export-csv');
    const baseUrl = csvLink.href.split('?')[0];
    
    // Calculate days parameter based on time range
    const diffMs = timeRange.end - timeRange.start;
    const diffDays = Math.ceil(diffMs / (1000 * 60 * 60 * 24));
    
    csvLink.href = `${baseUrl}?days=${diffDays}`;
}

// Initialize event listeners for collapsible sections
document.querySelectorAll('.toggle-chart, .toggle-section').forEach(button => {
    button.addEventListener('click', function() {
        const target = this.getAttribute('data-chart') || this.getAttribute('data-section');
        const cardBody = this.closest('.card').querySelector('.card-body');
        const icon = this.querySelector('i');
        
        if (cardBody.style.display === 'none') {
            cardBody.style.display = 'block';
            icon.classList.remove('fa-chevron-down');
            icon.classList.add('fa-chevron-up');
        } else {
            cardBody.style.display = 'none';
            icon.classList.remove('fa-chevron-up');
            icon.classList.add('fa-chevron-down');
        }
    });
});

// Event listeners for event details
document.querySelectorAll('.event-details').forEach(button => {
    button.addEventListener('click', function() {
        const eventId = this.getAttribute('data-event-id');
        showEventDetails(eventId);
    });
});

function showEventDetails(eventId) {
    // Fetch event details
    fetch(`/api/events/${eventId}`)
        .then(response => response.json())
        .then(data => {
            if (!data.event) {
                showError('Event details not found');
                return;
            }
            
            // Populate modal with event details
            const contentDiv = document.getElementById('event-details-content');
            
            let html = `
                <div class="row">
                    <div class="col-md-6">
                        <p><strong>Event ID:</strong> ${data.event.id}</p>
                        <p><strong>Type:</strong> <span class="badge bg-${data.event.type_class}">${data.event.type}</span></p>
                        <p><strong>Timestamp:</strong> ${new Date(data.event.timestamp).toLocaleString()}</p>
                        <p><strong>Description:</strong> ${data.event.description}</p>
                    </div>
                    <div class="col-md-6">
                        <p><strong>Level:</strong> ${data.event.level.toFixed(2)} m</p>
                        <p><strong>Volume:</strong> ${data.event.volume.toFixed(2)} L</p>
                        <p><strong>Fill Percentage:</strong> ${data.event.fill_percent.toFixed(1)}%</p>
                        <p><strong>Flow Rate:</strong> ${data.event.flow_rate ? data.event.flow_rate.toFixed(2) + ' L/min' : 'N/A'}</p>
                    </div>
                </div>
            `;
            
            // Add notes if available
            if (data.event.notes) {
                html += `
                    <div class="row mt-3">
                        <div class="col-12">
                            <h6>Notes:</h6>
                            <div class="p-3 bg-light rounded">
                                ${data.event.notes}
                            </div>
                        </div>
                    </div>
                `;
            }
            
            // Add related measurements if available
            if (data.related_measurements && data.related_measurements.length > 0) {
                html += `
                    <div class="row mt-3">
                        <div class="col-12">
                            <h6>Related Measurements:</h6>
                            <div class="table-responsive">
                                <table class="table table-sm">
                                    <thead>
                                        <tr>
                                            <th>Timestamp</th>
                                            <th>Level (m)</th>
                                            <th>Volume (L)</th>
                                            <th>Fill (%)</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                `;
                
                data.related_measurements.forEach(m => {
                    html += `
                        <tr>
                            <td>${new Date(m.timestamp).toLocaleString()}</td>
                            <td>${m.level.toFixed(2)}</td>
                            <td>${m.volume.toFixed(2)}</td>
                            <td>${m.fill_percent.toFixed(1)}</td>
                        </tr>
                    `;
                });
                
                html += `
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                `;
            }
            
            contentDiv.innerHTML = html;
            
            // Show modal
            const modal = new bootstrap.Modal(document.getElementById('eventDetailsModal'));
            modal.show();
        })
        .catch(error => {
            console.error('Error fetching event details:', error);
            showError('Failed to load event details');
        });
}

// Initialize date pickers with default values
function initDatePickers() {
    const now = new Date();
    const oneWeekAgo = new Date();
    oneWeekAgo.setDate(now.getDate() - 7);
    
    const startDateInput = document.getElementById('start-date');
    const endDateInput = document.getElementById('end-date');
    
    startDateInput.value = oneWeekAgo.toISOString().slice(0, 16);
    endDateInput.value = now.toISOString().slice(0, 16);
}

// Initialize tooltips
function initTooltips() {
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
}

// Initialize the page when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    initDatePickers();
    initTooltips();
    
    // Set CSS variables for tank level markers
    const tankLevel = document.getElementById('current-tank-level');
    if (tankLevel) {
        document.documentElement.style.setProperty('--critical-threshold', tankLevel.getAttribute('data-critical-threshold') + '%');
        document.documentElement.style.setProperty('--low-threshold', tankLevel.getAttribute('data-low-threshold') + '%');
        document.documentElement.style.setProperty('--high-threshold', tankLevel.getAttribute('data-high-threshold') + '%');
    }
});
// Individual Consumption Events Visualization
let consumptionChart = null;



function displayConsumptionData(events) {
    // Update table
    updateConsumptionTable(events);
    
    // Update chart
    updateConsumptionChart(events);
}

function updateConsumptionTable(events) {
    const tableBody = document.getElementById('consumption-table-body');
    
    if (!events || events.length === 0) {
        tableBody.innerHTML = '<tr><td colspan="5" class="text-center">No consumption events found for the selected criteria</td></tr>';
        return;
    }
    
    let tableContent = '';
    events.forEach(event => {
        // Get values from the correct properties
        const startTime = new Date(event.start_time).toLocaleString();
        const endTime = new Date(event.end_time).toLocaleString();
        
        // Calculate duration in hours:minutes:seconds
        const durationHours = event.duration_hours || 0;
        const totalMinutes = durationHours * 60;
        const hours = Math.floor(totalMinutes / 60);
        const minutes = Math.floor(totalMinutes % 60);
        const seconds = Math.floor((totalMinutes * 60) % 60);
        const formattedDuration = `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
        
        // Get volume and rate
        const volumeConsumed = event.volume_consumed || 0;
        const consumptionRate = event.consumption_rate || 0;
        
        tableContent += `
            <tr>
                <td>${startTime}</td>
                <td>${endTime}</td>
                <td>${formattedDuration}</td>
                <td>${volumeConsumed.toFixed(2)} L</td>
                <td>${(consumptionRate / 60).toFixed(2)} L/min</td>
            </tr>
        `;
    });
    
    tableBody.innerHTML = tableContent;
    // Add click event to show details
    document.querySelectorAll('.consumption-event-row').forEach(row => {
        row.addEventListener('click', function() {
            const eventIndex = this.getAttribute('data-event-index');
            showMeasurementDetails(events[eventIndex]);
        });
    });
}

function updateConsumptionChart(events) {
    const ctx = document.getElementById('consumptionChart').getContext('2d');
    
    // Prepare data for chart
    const chartData = {
        labels: events.map(event => new Date(event.start_time)),
        datasets: [
            {
                label: 'Volume Consumed (L)',
                data: events.map(event => ({
                    x: new Date(event.start_time),
                    y: event.volume_consumed
                })),
                backgroundColor: 'rgba(54, 162, 235, 0.5)',
                borderColor: 'rgba(54, 162, 235, 1)',
                borderWidth: 1
            },
            {
                label: 'Consumption Rate (L/min)',
                data: events.map(event => ({
                    x: new Date(event.start_time),
                    y: event.consumption_rate / 60 // Convert from L/hour to L/min
                })),
                backgroundColor: 'rgba(255, 99, 132, 0.5)',
                borderColor: 'rgba(255, 99, 132, 1)',
                borderWidth: 1,
                yAxisID: 'y1'
            }
        ]
    };
    
    // Destroy existing chart if it exists
    if (consumptionChart) {
        consumptionChart.destroy();
    }
    
    // Create new chart
    consumptionChart = new Chart(ctx, {
        type: 'bar',
        data: chartData,
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    type: 'time',
                    time: {
                        unit: 'day',
                        displayFormats: {
                            day: 'MMM d, HH:mm'
                        }
                    },
                    title: {
                        display: true,
                        text: 'Date & Time'
                    }
                },
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: 'Volume Consumed (L)'
                    }
                },
                y1: {
                    beginAtZero: true,
                    position: 'right',
                    grid: {
                        drawOnChartArea: false
                    },
                    title: {
                        display: true,
                        text: 'Consumption Rate (L/min)'
                    }
                }
            },
            plugins: {
                tooltip: {
                    callbacks: {
                        title: function(tooltipItems) {
                            return new Date(tooltipItems[0].raw.x).toLocaleString();
                        },
                        label: function(context) {
                            let label = context.dataset.label || '';
                            if (label) {
                                label += ': ';
                            }
                            if (context.parsed.y !== null) {
                                label += context.parsed.y.toFixed(2);
                            }
                            return label;
                        }
                    }
                },
                legend: {
                    position: 'top'
                }
            }
        }
    });
}

// Add a function to show consumption details when clicking on a table row
function setupConsumptionTableInteractivity() {
    document.getElementById('consumption-table-body').addEventListener('click', function(e) {
        const row = e.target.closest('tr');
        if (!row) return;
        
        // Remove highlight from all rows
        const allRows = document.querySelectorAll('#consumption-table-body tr');
        allRows.forEach(r => r.classList.remove('consumption-event-highlight'));
        
        // Add highlight to clicked row
        row.classList.add('consumption-event-highlight');
        
        // Get the index of the clicked row
        const rowIndex = Array.from(allRows).indexOf(row);
        
        // Highlight the corresponding bar in the chart
        if (consumptionChart && rowIndex >= 0) {
            // This is a simple approach - for more complex highlighting,
            // you might need to use Chart.js plugins
            consumptionChart.data.datasets.forEach((dataset) => {
                dataset.backgroundColor = dataset.data.map((_, i) => 
                    i === rowIndex 
                        ? (dataset.label.includes('Volume') ? 'rgba(54, 162, 235, 0.8)' : 'rgba(255, 99, 132, 0.8)') 
                        : (dataset.label.includes('Volume') ? 'rgba(54, 162, 235, 0.5)' : 'rgba(255, 99, 132, 0.5)')
                );
            });
            consumptionChart.update();
        }
    });
}

// Add a function to show measurement details
function showMeasurementDetails(event) {
    // Create a modal to show the detailed measurements
    const modalId = 'measurementDetailsModal';
    let modal = document.getElementById(modalId);
    
    if (!modal) {
        // Create modal if it doesn't exist
        const modalHTML = `
            <div class="modal fade" id="${modalId}" tabindex="-1" aria-labelledby="${modalId}Label" aria-hidden="true">
                <div class="modal-dialog modal-lg">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title" id="${modalId}Label">Consumption Event Details</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                        </div>
                        <div class="modal-body">
                            <div id="measurement-details-content"></div>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        document.body.insertAdjacentHTML('beforeend', modalHTML);
        modal = document.getElementById(modalId);
    }
    
    // Populate modal content
    const contentDiv = document.getElementById('measurement-details-content');
    
    // Format the measurements table
    let measurementsTable = '<table class="table table-sm table-striped">';
    measurementsTable += '<thead><tr><th>Timestamp</th><th>Volume (L)</th></tr></thead><tbody>';
    
    event.measurements.forEach(m => {
        measurementsTable += `<tr>
            <td>${new Date(m.timestamp).toLocaleString()}</td>
            <td>${m.volume.toFixed(2)}</td>
            <td>${flowRate}</td>
        </tr>`;
    });
    
    measurementsTable += '</tbody></table>';
    
    // Calculate additional statistics
    const volumeDifference = event.start_volume - event.end_volume;
    const durationSeconds = (new Date(event.end_time) - new Date(event.start_time)) / 1000;
    
    contentDiv.innerHTML = `
        <div class="row mb-3">
            <div class="col-md-6">
                <h6>Event Summary</h6>
                <table class="table table-sm">
                    <tr>
                        <th>Start Time:</th>
                        <td>${new Date(event.start_time).toLocaleString()}</td>
                    </tr>
                    <tr>
                        <th>End Time:</th>
                        <td>${new Date(event.end_time).toLocaleString()}</td>
                    </tr>
                    <tr>
                        <th>Duration:</th>
                        <td>${durationSeconds.toFixed(2)} seconds</td>
                    </tr>
                    <tr>
                        <th>Volume Consumed:</th>
                        <td>${event.volume_consumed.toFixed(2)} L</td>
                    </tr>
                    <tr>
                        <th>Consumption Rate:</th>
                        <td>${(event.consumption_rate / 60).toFixed(2)} L/min</td>
                    </tr>
                </table>
            </div>
            <div class="col-md-6">
                <h6>Volume Change</h6>
                <table class="table table-sm">
                    <tr>
                        <th>Start Volume:</th>
                        <td>${event.start_volume.toFixed(2)} L</td>
                    </tr>
                    <tr>
                        <th>End Volume:</th>
                        <td>${event.end_volume.toFixed(2)} L</td>
                    </tr>
                    <tr>
                        <th>Volume Difference:</th>
                        <td>${volumeDifference.toFixed(2)} L</td>
                    </tr>
                </table>
            </div>
        </div>
        
        <h6>Individual Measurements</h6>
        <div class="table-responsive">
            ${measurementsTable}
        </div>
    `;
    
    // Show the modal
    const bsModal = new bootstrap.Modal(modal);
    bsModal.show();
}

// Helper function to format duration in hours:minutes:seconds
function formatDuration(seconds) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    
    return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

// Initialize consumption data when page loads
document.addEventListener('DOMContentLoaded', function() {
    // Add event listener for the Apply Filter button
    document.getElementById('apply-consumption-filter').addEventListener('click', fetchIndividualConsumption);
    
    // Add event listener for the Refresh button
    document.getElementById('refresh-consumption').addEventListener('click', fetchIndividualConsumption);
    
    // Initial fetch of consumption data
    fetchIndividualConsumption();
    
    // Add event listener for time range changes to update consumption data
    document.getElementById('range-selector').addEventListener('change', function() {
        // Only fetch if the consumption section is visible
        if (!document.querySelector('[data-section="consumption"]').classList.contains('collapsed')) {
            fetchIndividualConsumption();
        }
    });
});

// Update the fetchIndividualConsumption function
function fetchIndividualConsumption() {
    const tankId = document.getElementById('tank-id').value;
    const minVolume = document.getElementById('min-volume-filter').value || 100;
    const flowThreshold = document.getElementById('flow-threshold').value || 0.1;
    // Get the current time range from the main chart
    let timeRange = getTimeRangeParameters();
    
    // Show loading state
    document.getElementById('consumption-table-body').innerHTML = 
        '<tr><td colspan="5" class="text-center"><div class="spinner-border spinner-border-sm text-primary" role="status"></div> Loading consumption data...</td></tr>';
    
    // Fetch data from API
    fetch(`/admin/api/tanks/${tankId}/individual-consumption?from=${timeRange.from}&to=${timeRange.to}&min_volume=${minVolume}&flow_threshold=${flowThreshold}`)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! Status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.success) {
                console.log('Consumption data received:', data.events);
                
                if (Array.isArray(data.events)) {
                    displayConsumptionData(data.events);
                    
                    // Setup table interactivity after data is loaded
                    setupConsumptionTableInteractivity();
                    
                    // Add double-click event to show measurement details
                    const tableBody = document.getElementById('consumption-table-body');
                    tableBody.addEventListener('dblclick', function(e) {
                        const row = e.target.closest('tr');
                        if (!row) return;
                        
                        const rowIndex = Array.from(tableBody.querySelectorAll('tr')).indexOf(row);
                        if (rowIndex >= 0 && data.events[rowIndex]) {
                            showMeasurementDetails(data.events[rowIndex]);
                        }
                    });
                } else {
                    console.error('Expected events to be an array but got:', typeof data.events);
                    document.getElementById('consumption-table-body').innerHTML = 
                        '<tr><td colspan="5" class="text-center text-danger">Error: Invalid data format received</td></tr>';
                }
            } else {
                console.error('Error fetching consumption data:', data.message);
                document.getElementById('consumption-table-body').innerHTML = 
                    `<tr><td colspan="5" class="text-center text-danger">Error: ${data.message}</td></tr>`;
            }
        })
        .catch(error => {
            console.error('Failed to fetch consumption data:', error);
            document.getElementById('consumption-table-body').innerHTML = 
                `<tr><td colspan="5" class="text-center text-danger">Failed to load consumption data: ${error.message}</td></tr>`;
        });
}

// Helper function to get current time range parameters
function getTimeRangeParameters() {
    // This should match the logic used in your main chart time range selection
    const rangeSelector = document.getElementById('range-selector');
    const selectedRange = rangeSelector.value;
    
    let from, to;
    
    if (selectedRange === 'custom') {
        const startDate = document.getElementById('start-date').value;
        const endDate = document.getElementById('end-date').value;
        
        from = new Date(startDate).getTime();
        to = new Date(endDate).getTime();
    } else {
        to = Date.now();
        
        switch (selectedRange) {
            case '1h': from = to - (60 * 60 * 1000); break;
            case '6h': from = to - (6 * 60 * 60 * 1000); break;
            case '12h': from = to - (12 * 60 * 60 * 1000); break;
            case '24h': from = to - (24 * 60 * 60 * 1000); break;
            case '7d': from = to - (7 * 24 * 60 * 60 * 1000); break;
            case '30d': from = to - (30 * 24 * 60 * 60 * 1000); break;
            case '90d': from = to - (90 * 24 * 60 * 60 * 1000); break;
            default: from = to - (7 * 24 * 60 * 60 * 1000); // Default to 7 days
        }    }
    
    return { from, to };
}

// Event listeners
document.addEventListener('DOMContentLoaded', function() {
    // Add event listener for the filter button
    document.getElementById('apply-consumption-filter').addEventListener('click', fetchIndividualConsumption);
    
    // Add event listener for time range changes to update consumption data
    document.getElementById('range-selector').addEventListener('change', function() {
        if (this.value !== 'custom') {
            fetchIndividualConsumption();
        }
    });
    
    document.getElementById('apply-custom-range').addEventListener('click', fetchIndividualConsumption);
    
    // Initial fetch of consumption data
    fetchIndividualConsumption();
    
    // Add event listener for the toggle button
    document.querySelector('[data-section="consumption"]').addEventListener('click', function() {
        const icon = this.querySelector('i');
        const cardBody = this.closest('.card').querySelector('.card-body');
        
        if (icon.classList.contains('fa-chevron-up')) {
            icon.classList.replace('fa-chevron-up', 'fa-chevron-down');
            cardBody.style.display = 'none';
        } else {
            icon.classList.replace('fa-chevron-down', 'fa-chevron-up');
            cardBody.style.display = 'block';
            
            // Refresh the chart when section is expanded
            if (consumptionChart) {
                consumptionChart.resize();
            }
        }
    });
});