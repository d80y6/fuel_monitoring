// Tank Detail Page Controller
class TankDetailController {
    constructor(tankId) {
        this.tankId = tankId;
        this.levelChart = null;
        this.consumptionChart = null;
        this.selectedPeriod = 7; // Default to 7 days
        this.customFromTime = null;
        this.customToTime = null;
        
        // Make sure to define all handler methods before initializing
        this.initEventListeners();
        this.initCustomDatePickers();
        this.loadInitialData();
    }
    
    initEventListeners() {
        // Use arrow functions to preserve 'this' context
        
        // Time range selector
        document.querySelectorAll('.time-range-selector .btn').forEach(btn => {
            btn.addEventListener('click', (e) => this.handlePeriodSelection(e, btn));
        });
        
        // Custom range form
        const customRangeForm = document.getElementById('custom-range-form');
        if (customRangeForm) {
            customRangeForm.addEventListener('submit', (e) => this.handleCustomRangeSubmit(e));
        }
        
        const cancelCustomRange = document.getElementById('cancel-custom-range');
        if (cancelCustomRange) {
            cancelCustomRange.addEventListener('click', () => this.handleCancelCustomRange());
        }
        
        // Refresh button
        const refreshBtn = document.getElementById('refresh-tank-data');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => this.refreshData());
        }
        
        // Delete tank button
        const deleteBtn = document.getElementById('delete-tank-btn');
        if (deleteBtn) {
            deleteBtn.addEventListener('click', () => this.handleDeleteTankClick());
        }
        
        const confirmDeleteBtn = document.getElementById('confirm-delete-tank');
        if (confirmDeleteBtn) {
            confirmDeleteBtn.addEventListener('click', () => this.handleConfirmDeleteTank());
        }
        
        // Acknowledge alarm buttons (using event delegation)
        document.addEventListener('click', (e) => {
            if (e.target.closest('.acknowledge-alarm-btn')) {
                this.handleAcknowledgeAlarm(e.target.closest('.acknowledge-alarm-btn'));
            }
        });
        
        // Window resize
        window.addEventListener('resize', () => this.handleWindowResize());
    }
    
    // Initialize date pickers for custom range
    initCustomDatePickers() {
        const now = new Date();
        const sevenDaysAgo = new Date(now.getTime() - (7 * 24 * 60 * 60 * 1000));
        
        // Format dates for datetime-local input
        const toDateStr = now.toISOString().slice(0, 16);
        const fromDateStr = sevenDaysAgo.toISOString().slice(0, 16);
        
        const fromDateInput = document.getElementById('custom-from-date');
        const toDateInput = document.getElementById('custom-to-date');
        
        if (fromDateInput) fromDateInput.value = fromDateStr;
        if (toDateInput) toDateInput.value = toDateStr;
    }
    
    // Handle period selection button click
    handlePeriodSelection(event, button) {
        const period = button.getAttribute('data-period');
        
        // Update active button
        document.querySelectorAll('.time-range-selector .btn').forEach(btn => {
            btn.classList.remove('active');
        });
        button.classList.add('active');
        
        // Handle custom range button differently
        if (period === 'custom') {
            const customRangePicker = document.getElementById('custom-range-picker');
            if (customRangePicker) {
                customRangePicker.style.display = 'block';
            }
            return;
        }
        
        // Hide custom range picker for predefined periods
        const customRangePicker = document.getElementById('custom-range-picker');
        if (customRangePicker) {
            customRangePicker.style.display = 'none';
        }
        
        // Update selected period
        this.selectedPeriod = period;
        
        // Reset custom time range
        this.customFromTime = null;
        this.customToTime = null;
        
        // Refresh data
        this.refreshData();
    }
    
    // Handle custom range form submission
    handleCustomRangeSubmit(e) {
        e.preventDefault();
        
        const fromDateInput = document.getElementById('custom-from-date');
        const toDateInput = document.getElementById('custom-to-date');
        
        if (!fromDateInput || !toDateInput) {
            this.showAlert('danger', 'Date input fields not found');
            return;
        }
        
        const fromDate = new Date(fromDateInput.value);
        const toDate = new Date(toDateInput.value);
        
        if (this.validateDateRange(fromDate, toDate)) {
            this.customFromTime = fromDate.getTime();
            this.customToTime = toDate.getTime();
            this.selectedPeriod = 'custom';
            
            this.refreshData();
        }
    }
    
    // Handle cancel custom range button click
    handleCancelCustomRange() {
        const customRangePicker = document.getElementById('custom-range-picker');
        if (customRangePicker) {
            customRangePicker.style.display = 'none';
        }
        
        // Reset to default period (7 days)
        this.selectedPeriod = 7;
        this.customFromTime = null;
        this.customToTime = null;
        
        // Update active button
        document.querySelectorAll('.time-range-selector .btn').forEach(btn => {
            btn.classList.remove('active');
        });
        const defaultBtn = document.querySelector('.time-range-selector .btn[data-period="7"]');
        if (defaultBtn) {
            defaultBtn.classList.add('active');
        }
        
        // Refresh data
        this.refreshData();
    }
    
    // Refresh data
    refreshData() {
        this.fetchTankMeasurements();
        this.fetchTankDailyStats();
    }
    
    // Handle delete tank button click
    handleDeleteTankClick() {
        const deleteBtn = document.getElementById('delete-tank-btn');
        const tankName = deleteBtn?.getAttribute('data-tank-name') || 'this tank';
        
        const tankNameElement = document.getElementById('delete-tank-name');
        if (tankNameElement) {
            tankNameElement.textContent = tankName;
        }
        
        // Show modal
        const deleteModal = new bootstrap.Modal(document.getElementById('deleteTankModal'));
        if (deleteModal) {
            deleteModal.show();
        }
    }
    
    // Handle confirm delete tank button click
    handleConfirmDeleteTank() {
        fetch(`/admin/tanks/delete/${this.tankId}`, {
            method: 'POST',
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(data => {
            if (data.success) {
                window.location.href = '/admin/tanks';
            } else {
                const deleteModal = bootstrap.Modal.getInstance(document.getElementById('deleteTankModal'));
                if (deleteModal) {
                    deleteModal.hide();
                }
                this.showAlert('danger', data.message || 'Error deleting tank');
            }
        })
        .catch(error => {
            console.error('Error deleting tank:', error);
            const deleteModal = bootstrap.Modal.getInstance(document.getElementById('deleteTankModal'));
            if (deleteModal) {
                deleteModal.hide();
            }
            this.showAlert('danger', 'Error deleting tank: ' + error.message);
        });
    }
    
    // Handle acknowledge alarm button click
    handleAcknowledgeAlarm(button) {
        try {
            if (!button) return;
            
            const alarmId = button.getAttribute('data-alarm-id');
            if (!alarmId) {
                console.error('No alarm ID found on button');
                return;
            }
            
            this.acknowledgeAlarm(alarmId);
        } catch (error) {
            console.error('Error in acknowledge alarm handler:', error);
            this.showAlert('danger', 'An error occurred while processing your request');
        }
    }
    
    // Acknowledge alarm
    acknowledgeAlarm(alarmId) {
        fetch(`/admin/alarms/acknowledge/${alarmId}`, {
            method: 'POST',
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(data => {
            if (data.success) {
                // Update the alarm status in the UI
                const row = document.querySelector(`tr[data-alarm-id="${alarmId}"]`);
                if (row) {
                    const statusCell = row.querySelector('.alarm-status');
                    const actionsCell = row.querySelector('.alarm-actions');
                    
                    if (statusCell) {
                        statusCell.innerHTML = '<span class="badge bg-success">Acknowledged</span>';
                    }
                    
                    if (actionsCell) {
                        actionsCell.innerHTML = '';
                    }
                }
                
                this.showAlert('success', data.message || 'Alarm acknowledged successfully');
            } else {
                this.showAlert('danger', data.message || 'Error acknowledging alarm');
            }
        })
        .catch(error => {
            console.error('Error acknowledging alarm:', error);
            this.showAlert('danger', 'Error acknowledging alarm: ' + error.message);
        });
    }
    
    // Handle window resize
    handleWindowResize() {
        if (this.levelChart) {
            this.levelChart.resize();
        }
        if (this.consumptionChart) {
            this.consumptionChart.resize();
        }
    }
    
    // Load initial data
    loadInitialData() {
        this.fetchTankMeasurements();
        this.fetchTankDailyStats();
    }
    
    // Show alert
    showAlert(type, message) {
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
    
    // Show loading indicator
    showLoading(show = true) {
        const loadingElement = document.getElementById('chart-loading');
        if (loadingElement) {
            loadingElement.style.display = show ? 'block' : 'none';
        }
        
        // Optionally dim the charts while loading
        const charts = document.querySelectorAll('.chart-container');
        charts.forEach(chart => {
            if (show) {
                chart.classList.add('opacity-50');
            } else {
                chart.classList.remove('opacity-50');
            }
        });
    }
    
    // Get time range based on selected period
    getTimeRange() {
        const now = new Date();
        let fromTime, toTime;
        
        if (this.selectedPeriod === 'custom' && this.customFromTime && this.customToTime) {
            // Use custom time range
            fromTime = this.customFromTime;
            toTime = this.customToTime;
        } else {
            // Use predefined period
            toTime = now.getTime();
            fromTime = toTime - (parseInt(this.selectedPeriod) * 24 * 60 * 60 * 1000);
        }
        
        return { fromTime, toTime };
    }
    
    // Fetch data with standardized error handling
    fetchData(url, successCallback, errorMessage = 'Error fetching data') {
        this.showLoading(true);
        
        return fetch(url)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                this.showLoading(false);
                if (data.success) {
                    successCallback(data);
                } else {
                    this.showAlert('danger', data.message || errorMessage);
                }
                return data;
            })
            .catch(error => {
                this.showLoading(false);
                console.error(`${errorMessage}:`, error);
                this.showAlert('danger', `${errorMessage}: ${error.message}`);
                return null;
            });
    }
    
    // Fetch tank measurements
    fetchTankMeasurements() {
        const { fromTime, toTime } = this.getTimeRange();
        const url = `/admin/api/tanks/${this.tankId}/history?from=${fromTime}&to=${toTime}&metrics=level,volume,fill_percent`;
        
        return this.fetchData(
            url,
            data => {
                if (data.measurements && data.measurements.length > 0) {
                    const transformedData = this.transformMeasurementData(data.measurements);
                    this.updateLevelChart(transformedData);
                } else {
                    this.showAlert('warning', 'No measurement data available for the selected period');
                }
            },
            'Error fetching tank measurements'
        );
    }
    
    // Transform measurement data for charts
    transformMeasurementData(measurements) {
        const transformedData = {
            level: [],
            volume: [],
            fill_percent: []
        };
        
        measurements.forEach(measurement => {
            // Convert ISO timestamp to milliseconds
            const timestamp = new Date(measurement.timestamp).getTime();
            
            if (measurement.level !== null && measurement.level !== undefined) {
                transformedData.level.push([timestamp, measurement.level]);
            }
            
            if (measurement.volume !== null && measurement.volume !== undefined) {
                transformedData.volume.push([timestamp, measurement.volume]);
            }
            
            if (measurement.fill_percent !== null && measurement.fill_percent !== undefined) {
                transformedData.fill_percent.push([timestamp, measurement.fill_percent]);
            }
        });
        
        return transformedData;
    }
    
    // Fetch tank daily statistics
    fetchTankDailyStats() {
        const { fromTime, toTime } = this.getTimeRange();
        const url = `/admin/api/tanks/${this.tankId}/daily-stats?from=${fromTime}&to=${toTime}`;
        
        return this.fetchData(
            url,
            data => {
                if (data.data) {
                    this.updateConsumptionChart(data.data);
                } else {
                    this.showAlert('warning', 'No consumption data available for the selected period');
                }
            },
            'Error fetching tank daily statistics'
        );
    }
    
    // Update level chart with time series data
    updateLevelChart(timeSeriesData) {
        if (!timeSeriesData) {
            console.warn('No time series data provided for level chart');
            return;
        }
        
        const chartCanvas = this.getElement('#levelChart');
        if (!chartCanvas) {
            console.error('Level chart canvas not found');
            return;
        }
        
        const hasData = timeSeriesData.fill_percent?.length > 0 || 
                       timeSeriesData.volume?.length > 0 || 
                       timeSeriesData.level?.length > 0;
                       
        if (!hasData) {
            console.warn('No valid data points for level chart');
            return;
        }
        
        // Prepare data for chart
        const datasets = [];
        
        // Add fill level dataset if available
        if (timeSeriesData.fill_percent && timeSeriesData.fill_percent.length > 0) {
            datasets.push({
                label: 'Fill Level (%)',
                data: timeSeriesData.fill_percent.map(point => ({
                    x: new Date(point[0]),
                    y: point[1]
                })),
                borderColor: 'rgba(75, 192, 192, 1)',
                backgroundColor: 'rgba(75, 192, 192, 0.2)',
                tension: 0.1,
                yAxisID: 'y'
            });
        }
        
        // Add volume dataset if available
        if (timeSeriesData.volume && timeSeriesData.volume.length > 0) {
            datasets.push({
                label: 'Volume (L)',
                data: timeSeriesData.volume.map(point => ({
                    x: new Date(point[0]),
                    y: point[1]
                })),
                borderColor: 'rgba(54, 162, 235, 1)',
                backgroundColor: 'rgba(54, 162, 235, 0.2)',
                tension: 0.1,
                yAxisID: 'y1',
                hidden: true
            });
        }
        
        // Add level dataset if available
        if (timeSeriesData.level && timeSeriesData.level.length > 0) {
            datasets.push({
                label: 'Level (m)',
                data: timeSeriesData.level.map(point => ({
                    x: new Date(point[0]),
                    y: point[1]
                })),
                borderColor: 'rgba(255, 159, 64, 1)',
                backgroundColor: 'rgba(255, 159, 64, 0.2)',
                tension: 0.1,
                yAxisID: 'y2',
                hidden: true
            });
        }
        
        const ctx = chartCanvas.getContext('2d');
        
        // Create or update chart
        if (this.levelChart) {
            this.levelChart.data.datasets = datasets;
            this.levelChart.options.scales.x.time.unit = this.selectedPeriod <= 2 ? 'hour' : 'day';
            this.levelChart.update();
        } else {
            this.levelChart = new Chart(ctx, {
                type: 'line',
                data: {
                    datasets: datasets
                },
                options: {
                    responsive: true,
                    interaction: {
                        mode: 'index',
                        intersect: false,
                    },
                    scales: {
                        x: {
                            type: 'time',
                            time: {
                                unit: this.selectedPeriod <= 2 ? 'hour' : 'day'
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
                        },
                        y2: {
                            type: 'linear',
                            display: true,
                            position: 'right',
                            title: {
                                display: true,
                                text: 'Level (m)'
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
    }
    
    // Update consumption chart with time series data
    updateConsumptionChart(timeSeriesData) {
        if (!timeSeriesData) {
            console.warn('No time series data provided for consumption chart');
            return;
        }
        
        const chartCanvas = this.getElement('#consumptionChart');
        if (!chartCanvas) {
            console.error('Consumption chart canvas not found');
            return;
        }
        
        // Create datasets for consumption and refill
        const datasets = [];
        
        // Add consumption dataset if available
        if (timeSeriesData.daily_consumption && timeSeriesData.daily_consumption.length > 0) {
            datasets.push({
                label: 'Consumption (L)',
                data: timeSeriesData.daily_consumption.map(point => ({
                    // Convert string timestamp to number by parsing the first part before the decimal
                    x: new Date(parseInt(point[0])),
                    y: point[1]
                })),
                backgroundColor: 'rgba(255, 99, 132, 0.8)',
                borderColor: 'rgba(255, 99, 132, 1)',
                borderWidth: 1,
                type: 'bar'
            });
        }
        
        // Add refill dataset if available
        if (timeSeriesData.daily_refill && timeSeriesData.daily_refill.length > 0) {
            datasets.push({
                label: 'Refill (L)',
                data: timeSeriesData.daily_refill.map(point => ({
                    // Convert string timestamp to number by parsing the first part before the decimal
                    x: new Date(parseInt(point[0])),
                    y: point[1]
                })),
                backgroundColor: 'rgba(75, 192, 192, 0.8)',
                borderColor: 'rgba(75, 192, 192, 1)',
                borderWidth: 1,
                type: 'bar'
            });
        }
        
        console.log('Consumption chart datasets:', datasets); // Debug log
        
        const ctx = chartCanvas.getContext('2d');
        
        // Create or update chart
        if (this.consumptionChart) {
            this.consumptionChart.data.datasets = datasets;
            this.consumptionChart.update();
        } else {
            this.consumptionChart = new Chart(ctx, {
                type: 'bar',
                data: {
                    datasets: datasets
                },
                options: {
                    responsive: true,
                    scales: {
                        x: {
                            type: 'time',
                            time: {
                                unit: 'day',
                                tooltipFormat: 'MMM d, yyyy'
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
                            callbacks: {
                                title: function(tooltipItems) {
                                    return new Date(tooltipItems[0].parsed.x).toLocaleDateString();
                                },
                                label: function(context) {
                                    const value = context.parsed.y;
                                    const datasetLabel = context.dataset.label || '';
                                    return `${datasetLabel}: ${value.toFixed(1)} L`;
                                }
                            }
                        },
                        legend: {
                            display: true,
                            position: 'top'
                        }
                    }
                }
            });
        }
    }
    
    // Validate custom date range
    validateDateRange(fromDate, toDate) {
        if (!fromDate || !toDate) {
            this.showAlert('danger', 'Please select both start and end dates');
            return false;
        }
        
        const now = new Date();
        const oneYearAgo = new Date();
        oneYearAgo.setFullYear(now.getFullYear() - 1);
        
        if (fromDate >= toDate) {
            this.showAlert('danger', 'Start date must be before end date');
            return false;
        }
        
        if (toDate > now) {
            this.showAlert('danger', 'End date cannot be in the future');
            return false;
        }
        
        const timeDiff = toDate - fromDate;
        const daysDiff = timeDiff / (1000 * 60 * 60 * 24);
        
        if (daysDiff > 365) {
            this.showAlert('warning', 'Selected range is over a year - data may be limited or performance affected');
        }
        
        if (fromDate < oneYearAgo) {
            this.showAlert('warning', 'Selected range starts more than a year ago - historical data may be limited');
        }
        
        return true;
    }
    
    // Safe element getter with error handling
    getElement(selector, errorMessage = null) {
        const element = document.querySelector(selector);
        if (!element && errorMessage) {
            console.error(errorMessage || `Element not found: ${selector}`);
        }
        return element;
    }
}

// Initialize controller when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    const tankDataElement = document.getElementById('tank-data');
    if (tankDataElement) {
        const tankId = tankDataElement.getAttribute('data-tank-id');
        if (tankId) {
            new TankDetailController(tankId);
        } else {
            console.error('Tank ID not found');
        }
    } else {
        console.error('Tank data element not found');
    }
});