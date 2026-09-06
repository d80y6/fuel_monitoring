/**
 * Admin Alarms Management JavaScript
 * Handles functionality for the admin alarms management page
 */

document.addEventListener('DOMContentLoaded', function() {
    let currentPage = 1;
    let itemsPerPage = 20;
    let totalAlarms = 0;
    let alarms = [];

    function fetchAlarms(page, acknowledged, type, tankId) {
        const params = new URLSearchParams({ page: page, acknowledged: acknowledged, type: type, tank_id: tankId });
        fetch('/admin/api/alarms?' + params.toString())
            .then(response => response.json())
            .then(response => {
                if (response.success) {
                    alarms = response.alarms;
                    totalAlarms = response.total;
                    renderAlarms(alarms);
                    renderPagination(totalAlarms, currentPage, itemsPerPage);
                    updateAlarmCounts(response.counts);
                } else {
                    alert('Error fetching alarms: ' + response.message);
                    console.error('Error fetching alarms:', response);
                }
            })
            .catch(error => {
                alert('Error fetching alarms: ' + error);
                console.error('Error fetching alarms:', error);
            });
    }

    function renderAlarms(alarms) {
        const alarmList = document.getElementById('alarm-list');
        alarmList.innerHTML = '';

        if (alarms.length === 0) {
            alarmList.innerHTML = '<tr><td colspan="7" class="text-center">No alarms found</td></tr>';
            return;
        }

        alarms.forEach(alarm => {
            const timestamp = new Date(alarm.timestamp).toLocaleString();

            let typeBadge = '';
            switch (alarm.type) {
                case 'critical_level':
                    typeBadge = '<span class="badge bg-danger">Critical Level</span>';
                    break;
                case 'low_level':
                    typeBadge = '<span class="badge bg-warning">Low Level</span>';
                    break;
                case 'high_level':
                    typeBadge = '<span class="badge bg-warning">High Level</span>';
                    break;
                case 'connection':
                    typeBadge = '<span class="badge bg-danger">Connection</span>';
                    break;
                default:
                    typeBadge = `<span class="badge bg-secondary">${alarm.type}</span>`;
            }

            const acknowledgedBadge = alarm.acknowledged ?
                '<span class="badge bg-success">Acknowledged</span>' :
                '<span class="badge bg-danger">Unacknowledged</span>';

            const value = alarm.value !== null ? alarm.value.toFixed(2) : 'N/A';

            let actionButtons = '';
            if (!alarm.acknowledged) {
                actionButtons += `<button type="button" class="btn btn-sm btn-success acknowledge-alarm-btn" data-alarm-id="${alarm.id}"><i class="bi bi-check-circle"></i></button>`;
            }
            actionButtons += `<button type="button" class="btn btn-sm btn-danger delete-alarm-btn" data-alarm-id="${alarm.id}"><i class="bi bi-trash"></i></button>`;

            const row = document.createElement('tr');
            row.innerHTML = `<td>${timestamp}</td><td><a href="/admin/tanks/${alarm.tank_id}">${alarm.tank_name}</a></td><td>${alarm.site_name}</td><td>${typeBadge}</td><td>${alarm.message}</td><td>${value}</td><td>${acknowledgedBadge}</td><td><div class="btn-group btn-group-sm">${actionButtons}</div></td>`;
            alarmList.appendChild(row);
        });
    }

    function renderPagination(total, currentPage, itemsPerPage) {
        const totalPages = Math.ceil(total / itemsPerPage);
        const pagination = document.getElementById('pagination');
        pagination.innerHTML = '';

        if (totalPages <= 1) {
            return;
        }

        const prevLi = document.createElement('li');
        prevLi.className = 'page-item';
        if (currentPage === 1) {
            prevLi.classList.add('disabled');
        }
        const prevA = document.createElement('a');
        prevA.className = 'page-link';
        prevA.href = '#';
        prevA.textContent = 'Previous';
        prevA.addEventListener('click', function(e) {
            e.preventDefault();
            if (currentPage > 1) {
                currentPage--;
                fetchAlarms(currentPage, document.getElementById('acknowledged-filter').value, document.getElementById('type-filter').value, document.getElementById('tank-filter').value);
            }
        });
        prevLi.appendChild(prevA);
        pagination.appendChild(prevLi);

        for (let i = 1; i <= totalPages; i++) {
            const li = document.createElement('li');
            li.className = 'page-item';
            if (i === currentPage) {
                li.classList.add('active');
            }
            const a = document.createElement('a');
            a.className = 'page-link';
            a.href = '#';
            a.textContent = i;
            a.addEventListener('click', function(e) {
                e.preventDefault();
                currentPage = i;
                fetchAlarms(currentPage, document.getElementById('acknowledged-filter').value, document.getElementById('type-filter').value, document.getElementById('tank-filter').value);
            });
            li.appendChild(a);
            pagination.appendChild(li);
        }

        const nextLi = document.createElement('li');
        nextLi.className = 'page-item';
        if (currentPage === totalPages) {
            nextLi.classList.add('disabled');
        }
        const nextA = document.createElement('a');
        nextA.className = 'page-link';
        nextA.href = '#';
        nextA.textContent = 'Next';
        nextA.addEventListener('click', function(e) {
            e.preventDefault();
            if (currentPage < totalPages) {
                currentPage++;
                fetchAlarms(currentPage, document.getElementById('acknowledged-filter').value, document.getElementById('type-filter').value, document.getElementById('tank-filter').value);
            }
        });
        nextLi.appendChild(nextA);
        pagination.appendChild(nextLi);
    }

    function updateAlarmCounts(counts) {
        document.getElementById('total-alarms').textContent = counts.total;
        document.getElementById('unacknowledged-alarms').textContent = counts.unacknowledged;
        document.getElementById('critical-alarms').textContent = counts.critical;
        document.getElementById('connection-alarms').textContent = counts.connection;
    }

    fetchAlarms(currentPage, 'all', 'all', 'all');

    document.getElementById('acknowledged-filter').addEventListener('change', function() {
        currentPage = 1;
        fetchAlarms(currentPage, document.getElementById('acknowledged-filter').value, document.getElementById('type-filter').value, document.getElementById('tank-filter').value);
    });

    document.getElementById('type-filter').addEventListener('change', function() {
        currentPage = 1;
        fetchAlarms(currentPage, document.getElementById('acknowledged-filter').value, document.getElementById('type-filter').value, document.getElementById('tank-filter').value);
    });

    document.getElementById('tank-filter').addEventListener('change', function() {
        currentPage = 1;
        fetchAlarms(currentPage, document.getElementById('acknowledged-filter').value, document.getElementById('type-filter').value, document.getElementById('tank-filter').value);
    });

    document.addEventListener('click', function(e) {
        const acknowledgeBtn = e.target.closest('.acknowledge-alarm-btn');
        if (acknowledgeBtn) {
            const alarmId = acknowledgeBtn.dataset.alarmId;
            fetch(`/admin/alarms/acknowledge/${alarmId}`, { method: 'POST' })
                .then(response => response.json())
                .then(response => {
                    if (response.success) {
                        fetchAlarms(currentPage, document.getElementById('acknowledged-filter').value, document.getElementById('type-filter').value, document.getElementById('tank-filter').value);
                    } else {
                        alert('Error acknowledging alarm: ' + response.message);
                    }
                })
                .catch(error => {
                    alert('Error acknowledging alarm: ' + error);
                });
        }

        const deleteBtn = e.target.closest('.delete-alarm-btn');
        if (deleteBtn) {
            const alarmId = deleteBtn.dataset.alarmId;
            if (confirm('Are you sure you want to delete this alarm?')) {
                fetch(`/admin/alarms/delete/${alarmId}`, { method: 'POST' })
                    .then(response => response.json())
                    .then(response => {
                        if (response.success) {
                            fetchAlarms(currentPage, document.getElementById('acknowledged-filter').value, document.getElementById('type-filter').value, document.getElementById('tank-filter').value);
                        } else {
                            alert('Error deleting alarm: ' + response.message);
                        }
                    })
                    .catch(error => {
                        alert('Error deleting alarm: ' + error);
                    });
            }
        }
    });

    document.getElementById('acknowledge-all-btn').addEventListener('click', function() {
        if (confirm('Are you sure you want to acknowledge all filtered alarms?')) {
            fetch('/admin/alarms/acknowledge-all', {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: new URLSearchParams({
                    acknowledged: document.getElementById('acknowledged-filter').value,
                    type: document.getElementById('type-filter').value,
                    tank_id: document.getElementById('tank-filter').value
                }).toString()
            })
            .then(response => response.json())
            .then(response => {
                if (response.success) {
                    fetchAlarms(currentPage, document.getElementById('acknowledged-filter').value, document.getElementById('type-filter').value, document.getElementById('tank-filter').value);
                    alert(response.message);
                } else {
                    alert('Error acknowledging alarms: ' + response.message);
                }
            })
            .catch(error => {
                alert('Error acknowledging alarms: ' + error);
            });
        }
    });

    document.getElementById('clear-all-btn').addEventListener('click', function() {
        if (confirm('Are you sure you want to delete all filtered alarms? This action cannot be undone.')) {
            fetch('/admin/alarms/clear-all', {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: new URLSearchParams({
                    acknowledged: document.getElementById('acknowledged-filter').value,
                    type: document.getElementById('type-filter').value,
                    tank_id: document.getElementById('tank-filter').value
                }).toString()
            })
            .then(response => response.json())
            .then(response => {
                if (response.success) {
                    fetchAlarms(currentPage, document.getElementById('acknowledged-filter').value, document.getElementById('type-filter').value, document.getElementById('tank-filter').value);
                    alert(response.message);
                } else {
                    alert('Error clearing alarms: ' + response.message);
                }
            })
            .catch(error => {
                alert('Error clearing alarms: ' + error);
            });
        }
    });

    setInterval(function() {
        fetchAlarms(currentPage, document.getElementById('acknowledged-filter').value, document.getElementById('type-filter').value, document.getElementById('tank-filter').value);
    }, 60000);
});
