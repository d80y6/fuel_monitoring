// static/js/dashboard.js — Dashboard-specific helpers
// Core dashboard logic is inline in the template for SSE/chart coupling.
// This file provides utility functions used by the dashboard.

function formatNumber(num, decimals = 1) {
    if (num == null || isNaN(num)) return '--';
    return Number(num).toFixed(decimals);
}

function getStatusColor(status) {
    return status === 'connected' ? 'text-green-600' : 'text-red-600';
}

function getAlarmBadgeClass(level) {
    const classes = { critical: 'bg-red-100 text-red-800', warning: 'bg-yellow-100 text-yellow-800', info: 'bg-blue-100 text-blue-800' };
    return classes[level] || 'bg-gray-100 text-gray-800';
}
