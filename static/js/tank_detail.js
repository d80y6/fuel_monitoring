// static/js/tank_detail.js — Tank detail page helpers
function updateTankField(fieldId, value, unit) {
    const el = document.getElementById(fieldId);
    if (el) el.textContent = (value != null ? value : '--') + (unit || '');
}

function addAlarmRow(containerId, alarm) {
    const container = document.getElementById(containerId);
    if (!container) return;
    const badge = alarm.level === 'critical' ? 'bg-red-100 text-red-800' : alarm.level === 'warning' ? 'bg-yellow-100 text-yellow-800' : 'bg-blue-100 text-blue-800';
    const html = `<div class="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
        <div class="flex items-center gap-3">
            <span class="px-2 py-0.5 rounded text-xs font-medium ${badge}">${alarm.type}</span>
            <span class="text-sm">${alarm.message || ''}</span>
        </div>
        <span class="text-xs text-gray-500">${new Date(alarm.timestamp).toLocaleTimeString()}</span>
    </div>`;
    container.insertAdjacentHTML('afterbegin', html);
    if (container.children.length > 10) container.lastElementChild.remove();
}
