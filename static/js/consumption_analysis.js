/**
 * Consumption Analysis Chart
 * 
 * Creates interactive charts for analyzing tank consumption patterns
 */
class ConsumptionChart {
    constructor(containerId, options = {}) {
        this.containerId = containerId;
        this.options = Object.assign({
            title: 'Tank Consumption Analysis',
            subtitle: 'Daily consumption and refill patterns',
            colors: {
                consumption: '#d9534f',
                overnight: '#5bc0de',
                refill: '#5cb85c',
                volume: '#428bca'
            },
            showConsumption: true,
            showOvernight: true,
            showRefills: true
        }, options);
        
        this.chart = null;
        this.data = null;
        this.summary = null;
        
        this.initChart();
    }
    
    initChart() {
        this.chart = Highcharts.chart(this.containerId, {
            chart: {
                zoomType: 'x',
                height: 500
            },
            title: {
                text: this.options.title
            },
            subtitle: {
                text: this.options.subtitle
            },
            xAxis: {
                type: 'datetime',
                title: {
                    text: 'Date'
                }
            },
            yAxis: [{
                // Primary y-axis for consumption/refill
                title: {
                    text: 'Volume (L)'
                },
                min: 0,
                labels: {
                    format: '{value} L'
                }
            }, {
                // Secondary y-axis for average volume
                title: {
                    text: 'Tank Volume (L)'
                },
                opposite: true,
                min: 0,
                labels: {
                    format: '{value} L'
                }
            }],
            tooltip: {
                shared: true,
                crosshairs: true,
                valueDecimals: 1,
                valueSuffix: ' L'
            },
            plotOptions: {
                column: {
                    stacking: 'normal',
                    dataLabels: {
                        enabled: false
                    }
                },
                spline: {
                    marker: {
                        enabled: false
                    }
                }
            },
            legend: {
                enabled: true
            },
            series: [],
            credits: {
                enabled: false
            }
        });
    }
    
    loadData(tankId, days = 30) {
        // Show loading indicator
        if (this.chart) {
            this.chart.showLoading('Loading consumption data...');
        }
        
        // Fetch data from API
        fetch(`/admin/api/tanks/${tankId}/daily-stats?days=${days}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error ${response.status}`);
                }
                return response.json();
            })
            .then(result => {
                if (result.success) {
                    console.log('Raw data from API:', result); // Debug log
                    
                    // Process timestamps to ensure they're valid numbers
                    const processTimeSeries = (series) => {
                        if (!series || !Array.isArray(series)) return [];
                        
                        return series.map(point => {
                            if (Array.isArray(point) && point.length >= 2) {
                                // Convert timestamp to number if it's a string
                                const timestamp = typeof point[0] === 'string' ? 
                                    parseFloat(point[0]) : point[0];
                                
                                // Ensure it's a valid timestamp (not NaN)
                                if (isNaN(timestamp)) {
                                    console.error('Invalid timestamp:', point[0]);
                                    return [0, point[1]]; // Use epoch as fallback
                                }
                                
                                return [timestamp, point[1]];
                            }
                            return point;
                        });
                    };
                    
                    // Process all time series data
                    Object.keys(result.data).forEach(key => {
                        if (Array.isArray(result.data[key])) {
                            result.data[key] = processTimeSeries(result.data[key]);
                        }
                    });
                    
                    this.data = result.data;
                    this.summary = result.summary;
                    this.updateChart();
                    this.updateSummary();
                } else {
                    console.error('Failed to load data:', result.message);
                    this.showError(result.message);
                }
            })
            .catch(error => {
                console.error('Error loading data:', error);
                this.showError('Failed to load consumption data');
            })
            .finally(() => {
                // Hide loading indicator
                if (this.chart) {
                    this.chart.hideLoading();
                }
            });
    }
    
    updateChart() {
        if (!this.chart || !this.data) return;
        
        console.log('Data being used for chart:', JSON.stringify(this.data));
        
        // Clear existing series
        while (this.chart.series.length > 0) {
            this.chart.series[0].remove(false);
        }
        
        // Process data to ensure timestamps are correctly formatted
        const processTimeSeriesData = (dataArray) => {
            if (!dataArray || !Array.isArray(dataArray)) return [];
            
            return dataArray.map(point => {
                // Ensure the timestamp is a number
                if (Array.isArray(point) && point.length >= 2) {
                    // If the timestamp is a string or has decimal points, convert it properly
                    const timestamp = typeof point[0] === 'string' ? 
                        parseFloat(point[0]) : point[0];
                    
                    return [timestamp, point[1]];
                }
                return point;
            });
        };
        
        // Add consumption series with processed data
        if (this.options.showConsumption) {
            this.chart.addSeries({
                name: 'Daily Consumption',
                data: processTimeSeriesData(this.data.daily_consumption),
                color: this.options.colors.consumption,
                type: 'column',
                stack: 'consumption',
                yAxis: 0
            }, false);
        }
        
        // Add overnight consumption series with processed data
        if (this.options.showOvernight) {
            this.chart.addSeries({
                name: 'Overnight Consumption',
                data: processTimeSeriesData(this.data.overnight_consumption),
                color: this.options.colors.overnight,
                type: 'column',
                stack: 'consumption',
                yAxis: 0
            }, false);
        }
        
        // Add refill series with processed data
        if (this.options.showRefills) {
            this.chart.addSeries({
                name: 'Refills',
                data: processTimeSeriesData(this.data.daily_refill),
                color: this.options.colors.refill,
                type: 'column',
                stack: 'refill',
                yAxis: 0
            }, false);
        }
        
        // Add volume series with processed data
        this.chart.addSeries({
            name: 'Average Volume',
            data: processTimeSeriesData(this.data.avg_volume),
            color: this.options.colors.volume,
            type: 'spline',
            yAxis: 1,
            zIndex: 1
        }, false);
        
        // Redraw the chart
        this.chart.redraw();
    }
    
    updateSummary() {
        if (!this.summary) return;
        
        // Update summary statistics in the UI
        const elements = {
            totalConsumption: document.getElementById('total-consumption'),
            avgDailyConsumption: document.getElementById('avg-daily-consumption'),
            avgOvernightConsumption: document.getElementById('avg-overnight-consumption'),
            totalRefill: document.getElementById('total-refill'),
            netChange: document.getElementById('net-change')
        };
        
        // Update each element if it exists
        if (elements.totalConsumption) {
            elements.totalConsumption.textContent = `${this.summary.total_consumption.toFixed(1)} L`;
        }
        if (elements.avgDailyConsumption) {
            elements.avgDailyConsumption.textContent = `${this.summary.avg_daily_consumption.toFixed(1)} L`;
        }
        if (elements.avgOvernightConsumption) {
            elements.avgOvernightConsumption.textContent = `${this.summary.avg_overnight_consumption.toFixed(1)} L`;
        }
        if (elements.totalRefill) {
            elements.totalRefill.textContent = `${this.summary.total_refill.toFixed(1)} L`;
        }
        if (elements.netChange) {
            const netChange = this.summary.net_change;
            const netChangeText = `${Math.abs(netChange).toFixed(1)} L ${netChange >= 0 ? 'increase' : 'decrease'}`;
            elements.netChange.textContent = netChangeText;
        }
    }
    
    showError(message) {
        // Display error message
        const errorElement = document.getElementById(`${this.containerId}-error`);
        if (errorElement) {
            errorElement.textContent = message;
            errorElement.style.display = 'block';
        } else {
            console.error('Error:', message);
        }
        
        // Clear chart
        if (this.chart) {
            while (this.chart.series.length > 0) {
                this.chart.series[0].remove(false);
            }
            this.chart.redraw();
        }
    }
    
    // Public methods for controlling the chart
    toggleRefills(show) {
        this.options.showRefills = show;
        this.updateChart();
    }
    
    toggleConsumption(show) {
        this.options.showConsumption = show;
        this.updateChart();
    }
    
    toggleOvernight(show) {
        this.options.showOvernight = show;
        this.updateChart();
    }
    
    setDateRange(days) {
        if (!this.chart) return;
        
        // Get current tank ID from data
        const tankId = this.data?.tank_id;
        if (!tankId) return;
        
        // Reload data with new date range
        this.loadData(tankId, days);
    }
}

// Pattern Chart for weekly and hourly patterns
class PatternChart {
    constructor(containerId, type, options = {}) {
        this.containerId = containerId;
        this.type = type; // 'weekly' or 'hourly'
        this.options = Object.assign({
            title: type === 'weekly' ? 'Weekly Consumption Pattern' : 'Hourly Consumption Pattern',
            color: '#5bc0de'
        }, options);
        
        this.chart = null;
        this.data = null;
        
        this.initChart();
    }
    
    initChart() {
        const categories = this.type === 'weekly' 
            ? ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
            : Array.from({length: 24}, (_, i) => `${i}:00`);
        
        this.chart = Highcharts.chart(this.containerId, {
            chart: {
                type: 'column',
                height: 300
            },
            title: {
                text: this.options.title
            },
            xAxis: {
                categories: categories,
                title: {
                    text: this.type === 'weekly' ? 'Day of Week' : 'Hour of Day'
                }
            },
            yAxis: {
                title: {
                    text: 'Average Consumption (L)'
                },
                min: 0
            },
            tooltip: {
                formatter: function() {
                    return `<b>${this.x}</b><br/>Average consumption: ${this.y.toFixed(1)} L`;
                }
            },
            plotOptions: {
                column: {
                    pointPadding: 0.2,
                    borderWidth: 0,
                    color: this.options.color
                }
            },
            legend: {
                enabled: false
            },
            credits: {
                enabled: false
            }
        });
    }
    
    loadData(tankId, days = 30) {
        // Show loading indicator
        if (this.chart) {
            this.chart.showLoading('Loading pattern data...');
        }
        
        // Determine API endpoint based on type
        const endpoint = this.type === 'weekly' 
            ? `/admin/api/tanks/${tankId}/weekly-pattern` 
            : `/admin/api/tanks/${tankId}/hourly-pattern`;
        
        // Fetch data from API
        fetch(`${endpoint}?days=${days}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error ${response.status}`);
                }
                return response.json();
            })
            .then(result => {
                if (result.success) {
                    this.data = result.data;
                    this.updateChart();
                } else {
                    console.error(`Failed to load ${this.type} pattern:`, result.message);
                    this.showError(result.message);
                }
            })
            .catch(error => {
                console.error(`Error loading ${this.type} pattern:`, error);
                this.showError(`Failed to load ${this.type} consumption pattern`);
            })
            .finally(() => {
                // Hide loading indicator
                if (this.chart) {
                    this.chart.hideLoading();
                }
            });
    }
    
    updateChart() {
        if (!this.chart || !this.data) return;
        
        // Clear existing series
        while (this.chart.series.length > 0) {
            this.chart.series[0].remove(false);
        }
        
        // Add data series
        this.chart.addSeries({
            name: 'Average Consumption',
            data: this.data,
            color: this.options.color
        });
        
        // Highlight peak consumption
        const maxValue = Math.max(...this.data);
        const maxIndex = this.data.indexOf(maxValue);
        
        if (maxIndex !== -1) {
            this.chart.series[0].data[maxIndex].update({
                color: '#d9534f',  // Highlight peak in red
                dataLabels: {
                    enabled: true,
                    format: '{y:.1f} L',
                    style: {
                        fontWeight: 'bold'
                    }
                }
            });
        }
    }
    
    showError(message) {
        // Display error message
        const errorElement = document.getElementById(`${this.containerId}-error`);
        if (errorElement) {
            errorElement.textContent = message;
            errorElement.style.display = 'block';
        } else {
            console.error('Error:', message);
        }
        
        // Clear chart
        if (this.chart) {
            while (this.chart.series.length > 0) {
                this.chart.series[0].remove(false);
            }
            this.chart.redraw();
        }
    }
}

// Initialize charts when document is ready
document.addEventListener('DOMContentLoaded', function() {
    // Get tank ID from page
    const tankIdElement = document.getElementById('tank-id');
    if (!tankIdElement) return;
    
    const tankId = tankIdElement.value;
    const daysSelect = document.getElementById('days-select');
    let days = 30; // Default
    
    if (daysSelect) {
        days = parseInt(daysSelect.value);
        
        // Add event listener for days select
        daysSelect.addEventListener('change', function() {
            days = parseInt(this.value);
            loadAllCharts(tankId, days);
        });
    }
    
    // Initialize consumption chart
    const consumptionChart = new ConsumptionChart('consumption-chart', {
        title: 'Tank Consumption Analysis',
        subtitle: `Daily consumption and refill patterns (${days} days)`
    });
    
    // Initialize pattern charts
    const weeklyPatternChart = new PatternChart('weekly-pattern-chart', 'weekly', {
        title: 'Weekly Consumption Pattern',
        color: '#5bc0de'
    });
    
    const hourlyPatternChart = new PatternChart('hourly-pattern-chart', 'hourly', {
        title: 'Hourly Consumption Pattern',
        color: '#5cb85c'
    });
    
    // Function to load all charts
    function loadAllCharts(tankId, days) {
        consumptionChart.loadData(tankId, days);
        weeklyPatternChart.loadData(tankId, days);
        hourlyPatternChart.loadData(tankId, days);
        
        // Update subtitle
        if (consumptionChart.chart) {
            consumptionChart.chart.setSubtitle({
                text: `Daily consumption and refill patterns (${days} days)`
            });
        }
    }
    
    // Load initial data
    loadAllCharts(tankId, days);
    
    // Add event listeners for chart toggles
    const toggleConsumption = document.getElementById('toggle-consumption');
    const toggleOvernight = document.getElementById('toggle-overnight');
    const toggleRefills = document.getElementById('toggle-refills');
    
    if (toggleConsumption) {
        toggleConsumption.addEventListener('change', function() {
            consumptionChart.options.showConsumption = this.checked;
            consumptionChart.updateChart();
        });
    }
    
    if (toggleOvernight) {
        toggleOvernight.addEventListener('change', function() {
            consumptionChart.options.showOvernight = this.checked;
            consumptionChart.updateChart();
        });
    }
    
    if (toggleRefills) {
        toggleRefills.addEventListener('change', function() {
            consumptionChart.options.showRefills = this.checked;
            consumptionChart.updateChart();
        });
    }
});