// static/js/chart-factory.js — Shared Chart.js v4 configuration factory
const ChartFactory = {
    defaultColors: {
        primary: '#3b82f6',
        success: '#10b981',
        danger: '#ef4444',
        warning: '#f59e0b',
        info: '#06b6d4',
        purple: '#8b5cf6',
    },

    createLineChart(ctx, config) {
        return new Chart(ctx, {
            type: 'line',
            data: config.data,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { intersect: false, mode: 'index' },
                plugins: {
                    legend: { position: 'top', labels: { usePointStyle: true, padding: 16 } },
                    tooltip: {
                        backgroundColor: 'rgba(0,0,0,0.8)',
                        padding: 12,
                        titleFont: { size: 13 },
                        bodyFont: { size: 12 },
                    },
                },
                scales: {
                    x: {
                        type: 'time',
                        time: { tooltipFormat: 'PPpp' },
                        grid: { display: false },
                    },
                    y: {
                        beginAtZero: config.beginAtZero !== false,
                        grid: { color: 'rgba(0,0,0,0.05)' },
                    },
                },
                ...config.options,
            },
        });
    },

    createBarChart(ctx, config) {
        return new Chart(ctx, {
            type: 'bar',
            data: config.data,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: 'top', labels: { usePointStyle: true, padding: 16 } },
                },
                scales: {
                    x: { grid: { display: false } },
                    y: { beginAtZero: true, grid: { color: 'rgba(0,0,0,0.05)' } },
                },
                ...config.options,
            },
        });
    },

    formatTime(date) {
        return new Date(date).toLocaleString();
    },

    pushData(chart, label, value, maxPoints = 100) {
        chart.data.labels.push(label);
        chart.data.datasets.forEach(ds => ds.data.push(value));
        if (chart.data.labels.length > maxPoints) {
            chart.data.labels.shift();
            chart.data.datasets.forEach(ds => ds.data.shift());
        }
        chart.update('none');
    },
};
