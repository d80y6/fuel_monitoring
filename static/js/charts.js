// Chart configuration and utilities

// Set default Chart.js options
Chart.defaults.font.family = "'Helvetica Neue', 'Helvetica', 'Arial', sans-serif";
Chart.defaults.font.size = 12;
Chart.defaults.color = '#666';
Chart.defaults.plugins.tooltip.backgroundColor = 'rgba(0, 0, 0, 0.7)';
Chart.defaults.plugins.legend.labels.usePointStyle = true;

// Color schemes
const colorSchemes = {
    blue: {
        primary: '#007bff',
        secondary: 'rgba(0, 123, 255, 0.1)'
    },
    green: {
        primary: '#28a745',
        secondary: 'rgba(40, 167, 69, 0.1)'
    },
    red: {
        primary: '#dc3545',
        secondary: 'rgba(220, 53, 69, 0.1)'
    },
    yellow: {
        primary: '#ffc107',
        secondary: 'rgba(255, 193, 7, 0.1)'
    },
    cyan: {
        primary: '#17a2b8',
        secondary: 'rgba(23, 162, 184, 0.1)'
    },
    orange: {
        primary: '#fd7e14',
        secondary: 'rgba(253, 126, 20, 0.1)'
    }
};

// Create a gradient background
function createGradient(ctx, colorStart, colorEnd) {
    const gradient = ctx.createLinearGradient(0, 0, 0, 400);
    gradient.addColorStop(0, colorStart);
    gradient.addColorStop(1, colorEnd);
    return gradient;
}

// Format time for chart labels
function formatTime(date) {
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

// Format date for chart labels
function formatDate(date) {
    return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

// Format date and time for chart labels
function formatDateTime(date) {
    return `${formatDate(date)} ${formatTime(date)}`;
}

// Create a responsive chart
function createResponsiveChart(canvasId, type, data, options) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;
    
    const ctx = canvas.getContext('2d');
    
    // Merge default options with provided options
    const defaultOptions = {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: {
                position: 'top',
            },
            tooltip: {
                mode: 'index',
                intersect: false
            }
        }
    };
    
    const mergedOptions = { ...defaultOptions, ...options };
    
    return new Chart(ctx, {
        type: type,
        data: data,
        options: mergedOptions
    });
}

// Update chart with new data
function updateChart(chart, labels, datasets) {
    if (!chart) return;
    
    chart.data.labels = labels;
    
    datasets.forEach((dataset, index) => {
        if (chart.data.datasets[index]) {
            chart.data.datasets[index].data = dataset.data;
            
            // Update other properties if provided
            if (dataset.label) chart.data.datasets[index].label = dataset.label;
            if (dataset.borderColor) chart.data.datasets[index].borderColor = dataset.borderColor;
            if (dataset.backgroundColor) chart.data.datasets[index].backgroundColor = dataset.backgroundColor;
        }
    });
    
    chart.update();
}

// Create a tank level gauge chart
function createTankGauge(canvasId, value, options = {}) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;
    
    const ctx = canvas.getContext('2d');
    
    // Default options
    const defaultOptions = {
        min: 0,
        max: 100,
        title: 'Tank Level',
        unit: '%',
        thresholds: [20, 40]
    };
    
    const mergedOptions = { ...defaultOptions, ...options };
    
    return new Chart(ctx, {
        type: 'gauge',
        data: {
            datasets: [{
                value: value,
                minValue: mergedOptions.min,
                maxValue: mergedOptions.max,
                backgroundColor: ['#dc3545', '#ffc107', '#28a745'],
                thresholds: mergedOptions.thresholds
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            title: {
                display: true,
                text: mergedOptions.title
            },
            valueLabel: {
                display: true,
                formatter: (value) => `${value.toFixed(1)}${mergedOptions.unit}`
            }
        }
    });
}
