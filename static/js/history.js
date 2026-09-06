// History page JavaScript
let historyChart, volumeChart, flowChart;
let historyData = [];
let selectedHours = 6; // Default time range

// Initialize charts
function initCharts() {
    // Main history chart (level & temperature)
    const historyCtx = document.getElementById('history-chart').getContext('2d');
    historyChart = new Chart(historyCtx, {
        type: 'line',
        data: {
            datasets: [
                {
                    label: 'Level (m)',
                    data: [],
                    borderColor: '#0d6efd',
                    backgroundColor: 'rgba(13, 110, 253, 0.1)',
                    borderWidth: 2,
                    fill: false,
                    yAxisID: 'y',
                    tension: 0.2
                },
                {
                    label: 'Temperature (°C)',
                    data: [],
                    borderColor: '#dc3545',
                    backgroundColor: 'rgba(220, 53, 69, 0.1)',
                    borderWidth: 2,
                    fill: false,
                    yAxisID: 'y1',
                    tension: 0.2
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false
            },
            scales: {
                x: {
                    type: 'time',
                    time: {
                        unit: 'hour',
                        displayFormats: {
                            hour: 'HH:mm'
                        }
                    },
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
                        text: 'Level (m)'
                    }
                },
                y1: {
                    type: 'linear',
                    display: true,
                    position: 'right',
                    title: {
                        display: true,
                        text: 'Temperature (°C)'
                    },
                    grid: {
                        drawOnChartArea: false
                    }
                }
            },
            plugins: {
                legend: {
                    display: true,
                    position: 'top'
                },
                tooltip: {
                    callbacks: {
                        title: function(tooltipItems) {
                            return new Date(tooltipItems[0].parsed.x).toLocaleString();
                        }
                    }
                }
            }
        }
    });
    
    // Volume history chart
    const volumeCtx = document.getElementById('volume-history-chart').getContext('2d');
    volumeChart = new Chart(volumeCtx, {
        type: 'line',
        data: {
            datasets: [{
                label: 'Volume (L)',
                data: [],
                borderColor: '#20c997',
                backgroundColor: 'rgba(32, 201, 151, 0.1)',
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
                        unit: 'hour',
                        displayFormats: {
                            hour: 'HH:mm'
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
                        text: 'Volume (L)'
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
    
    // Flow rate history chart
    const flowCtx = document.getElementById('flow-history-chart').getContext('2d');
    flowChart = new Chart(flowCtx, {
        type: 'line',
        data: {
            datasets: [{
                label: 'Flow Rate (L/min)',
                data: [],
                borderColor: '#fd7e14',
                backgroundColor: function(context) {
                    const value = context.dataset.data[context.dataIndex]?.y;
                    return value >= 0 ? 'rgba(253, 126, 20, 0.1)' : 'rgba(13, 110, 253, 0.1)';
                },
                borderWidth: 2,
                fill: false
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    type: 'time',
                    time: {
                        unit: 'hour',
                        displayFormats: {
                            hour: 'HH:mm'
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

// Fetch history data from server
function fetchHistoryData() {
    fetch(`/api/history?hours=${selectedHours}`)
        .then(response => response.json())
        .then(data => {
            historyData = data;
            updateCharts();
            updateTable();
        })
        .catch(error => {
            console.error('Error fetching history data:', error);
        });
}

// Update charts with history data
function updateCharts() {
    if (!historyData || !historyData.length) return;
    
    // Prepare data for charts
    const levelData = [];
    const tempData = [];
    const volumeData = [];
    const flowData = [];
    
    historyData.forEach(item => {
        const timestamp = new Date(item.timestamp);
        
        // Level data
        levelData.push({
            x: timestamp,
            y: item.level
        });
        
        // Temperature data (if available)
        if (item.temperature !== null && item.temperature !== undefined) {
            tempData.push({
                x: timestamp,
                y: item.temperature
            });
        }
        
        // Volume data
        volumeData.push({
            x: timestamp,
            y: item.volume
        });
        
        // Flow rate data
        flowData.push({
            x: timestamp,
            y: item.flow_rate
        });
    });
    
    // Update main history chart
    historyChart.data.datasets[0].data = levelData;
    historyChart.data.datasets[1].data = tempData;
    
    // Update volume chart
    volumeChart.data.datasets[0].data = volumeData;
    
    // Update flow chart
    flowChart.data.datasets[0].data = flowData;
    
    // Update all charts
    historyChart.update();
    volumeChart.update();
    flowChart.update();
}

// Update data table
function updateTable() {
    const tableBody = document.querySelector('#history-table tbody');
    if (!tableBody) return;
    
    // Clear table
    tableBody.innerHTML = '';
    
    // Check if we have data
    if (!historyData || !historyData.length) {
        tableBody.innerHTML = '<tr><td colspan="7" class="text-center">No data available</td></tr>';
        return;
    }
    
    // Add data rows (most recent first)
    historyData.slice().reverse().forEach(item => {
        const row = document.createElement('tr');
        
        // Format timestamp
        const timestamp = new Date(item.timestamp);
        const formattedTime = timestamp.toLocaleString();
        
        // Format temperature
        const tempValue = item.temperature !== null && item.temperature !== undefined
            ? item.temperature.toFixed(2)
            : 'N/A';
        
        // Format flow rate with sign
        let flowText = Math.abs(item.flow_rate).toFixed(2);
        if (item.flow_rate > 0) {
            flowText = `+${flowText}`;
        } else if (item.flow_rate < 0) {
            flowText = `-${flowText}`;
        }
        
        // Create row cells
        row.innerHTML = `
            <td>${formattedTime}</td>
            <td>${item.pressure.toFixed(4)}</td>
            <td>${tempValue}</td>
            <td>${item.level.toFixed(3)}</td>
            <td>${item.volume.toFixed(1)}</td>
            <td>${flowText}</td>
            <td>${item.fill_percent.toFixed(1)}</td>
        `;
        
        tableBody.appendChild(row);
    });
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    initCharts();
    
    // Set up time range buttons
    const timeButtons = document.querySelectorAll('.btn-group button[data-hours]');
    timeButtons.forEach(button => {
        button.addEventListener('click', function() {
            // Update active button
            timeButtons.forEach(btn => btn.classList.remove('active'));
            this.classList.add('active');
            
            // Update selected hours
            selectedHours = parseInt(this.dataset.hours);
            
            // Fetch data with new time range
            fetchHistoryData();
        });
    });
    
    // Initial data fetch
    fetchHistoryData();
    
    // Set up auto-refresh every minute
    setInterval(fetchHistoryData, 60000);
});