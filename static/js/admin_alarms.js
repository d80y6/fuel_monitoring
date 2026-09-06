/**
 * Admin Alarms Management JavaScript
 * Handles functionality for the admin alarms management page
 */

$(document).ready(function() {
    // Initialize variables
    let currentPage = 1;
    let itemsPerPage = 20;
    let totalAlarms = 0;
    let alarms = [];

    // Function to fetch alarms
    function fetchAlarms(page, acknowledged, type, tankId) {
        $.ajax({
            url: '/admin/api/alarms',
            method: 'GET',
            data: { 
                page: page, 
                acknowledged: acknowledged, 
                type: type,
                tank_id: tankId
            },
            dataType: 'json',
            success: function(response) {
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
            },
            error: function(error) {
                alert('Error fetching alarms: ' + error.responseText);
                console.error('Error fetching alarms:', error);
            }
        });
    }

    // Function to render alarms
    function renderAlarms(alarms) {
        let alarmList = $('#alarm-list');
        alarmList.empty();
        
        if (alarms.length === 0) {
            alarmList.append('<tr><td colspan="7" class="text-center">No alarms found</td></tr>');
            return;
        }
        
        alarms.forEach(alarm => {
            // Format timestamp
            let timestamp = new Date(alarm.timestamp).toLocaleString();
            
            // Create alarm type badge
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
            
            // Create acknowledged badge
            let acknowledgedBadge = alarm.acknowledged ? 
                '<span class="badge bg-success">Acknowledged</span>' : 
                '<span class="badge bg-danger">Unacknowledged</span>';
            
            // Format value
            let value = alarm.value !== null ? alarm.value.toFixed(2) : 'N/A';
            
            // Create action buttons
            let actionButtons = '';
            if (!alarm.acknowledged) {
                actionButtons += `
                    <button type="button" class="btn btn-sm btn-success acknowledge-alarm-btn" data-alarm-id="${alarm.id}">
                        <i class="bi bi-check-circle"></i>
                    </button>
                `;
            }
            actionButtons += `
                <button type="button" class="btn btn-sm btn-danger delete-alarm-btn" data-alarm-id="${alarm.id}">
                    <i class="bi bi-trash"></i>
                </button>
            `;
            
            let row = $('<tr>');
            row.append(`<td>${timestamp}</td>`);
            row.append(`<td><a href="/admin/tanks/${alarm.tank_id}">${alarm.tank_name}</a></td>`);
            row.append(`<td>${alarm.site_name}</td>`);
            row.append(`<td>${typeBadge}</td>`);
            row.append(`<td>${alarm.message}</td>`);
            row.append(`<td>${value}</td>`);
            row.append(`<td>${acknowledgedBadge}</td>`);
            row.append(`<td>
                <div class="btn-group btn-group-sm">
                    ${actionButtons}
                </div>
            </td>`);
            alarmList.append(row);
        });
    }

    // Function to render pagination
    function renderPagination(total, currentPage, itemsPerPage) {
        let totalPages = Math.ceil(total / itemsPerPage);
        let pagination = $('#pagination');
        pagination.empty();
        
        if (totalPages <= 1) {
            return;
        }
        
        // Previous button
        let prevLi = $('<li class="page-item">');
        if (currentPage === 1) {
            prevLi.addClass('disabled');
        }
        let prevA = $('<a class="page-link" href="#">Previous</a>');
        prevA.click(function(e) {
            e.preventDefault();
            if (currentPage > 1) {
                currentPage--;
                fetchAlarms(
                    currentPage, 
                    $('#acknowledged-filter').val(), 
                    $('#type-filter').val(),
                    $('#tank-filter').val()
                );
            }
        });
        prevLi.append(prevA);
        pagination.append(prevLi);
        
        // Page numbers
        for (let i = 1; i <= totalPages; i++) {
            let li = $('<li class="page-item">');
            if (i === currentPage) {
                li.addClass('active');
            }
            let a = $('<a class="page-link" href="#">' + i + '</a>');
            a.click(function(e) {
                e.preventDefault();
                currentPage = i;
                fetchAlarms(
                    currentPage, 
                    $('#acknowledged-filter').val(), 
                    $('#type-filter').val(),
                    $('#tank-filter').val()
                );
            });
            li.append(a);
            pagination.append(li);
        }
        
        // Next button
        let nextLi = $('<li class="page-item">');
        if (currentPage === totalPages) {
            nextLi.addClass('disabled');
        }
        let nextA = $('<a class="page-link" href="#">Next</a>');
        nextA.click(function(e) {
            e.preventDefault();
            if (currentPage < totalPages) {
                currentPage++;
                fetchAlarms(
                    currentPage, 
                    $('#acknowledged-filter').val(), 
                    $('#type-filter').val(),
                    $('#tank-filter').val()
                );
            }
        });
        nextLi.append(nextA);
        pagination.append(nextLi);
    }

    // Function to update alarm counts
    function updateAlarmCounts(counts) {
        $('#total-alarms').text(counts.total);
        $('#unacknowledged-alarms').text(counts.unacknowledged);
        $('#critical-alarms').text(counts.critical);
        $('#connection-alarms').text(counts.connection);
    }

    // Initial fetch
    fetchAlarms(currentPage, 'all', 'all', 'all');

    // Filter change
    $('#acknowledged-filter, #type-filter, #tank-filter').change(function() {
        currentPage = 1;
        fetchAlarms(
            currentPage, 
            $('#acknowledged-filter').val(), 
            $('#type-filter').val(),
            $('#tank-filter').val()
        );
    });

    // Acknowledge alarm
    $(document).on('click', '.acknowledge-alarm-btn', function() {
        let alarmId = $(this).data('alarm-id');
        
        $.ajax({
            url: `/admin/alarms/acknowledge/${alarmId}`,
            method: 'POST',
            dataType: 'json',
            success: function(response) {
                if (response.success) {
                    fetchAlarms(
                        currentPage, 
                        $('#acknowledged-filter').val(), 
                        $('#type-filter').val(),
                        $('#tank-filter').val()
                    );
                } else {
                    alert('Error acknowledging alarm: ' + response.message);
                }
            },
            error: function(error) {
                alert('Error acknowledging alarm: ' + error.responseText);
            }
        });
    });

    // Delete alarm
    $(document).on('click', '.delete-alarm-btn', function() {
        let alarmId = $(this).data('alarm-id');
        
        if (confirm('Are you sure you want to delete this alarm?')) {
            $.ajax({
                url: `/admin/alarms/delete/${alarmId}`,
                method: 'POST',
                dataType: 'json',
                success: function(response) {
                    if (response.success) {
                        fetchAlarms(
                            currentPage, 
                            $('#acknowledged-filter').val(), 
                            $('#type-filter').val(),
                            $('#tank-filter').val()
                        );
                    } else {
                        alert('Error deleting alarm: ' + response.message);
                    }
                },
                error: function(error) {
                    alert('Error deleting alarm: ' + error.responseText);
                }
            });
        }
    });

    // Acknowledge all alarms
    $('#acknowledge-all-btn').click(function() {
        if (confirm('Are you sure you want to acknowledge all filtered alarms?')) {
            $.ajax({
                url: '/admin/alarms/acknowledge-all',
                method: 'POST',
                data: {
                    acknowledged: $('#acknowledged-filter').val(),
                    type: $('#type-filter').val(),
                    tank_id: $('#tank-filter').val()
                },
                dataType: 'json',
                success: function(response) {
                    if (response.success) {
                        fetchAlarms(
                            currentPage, 
                            $('#acknowledged-filter').val(), 
                            $('#type-filter').val(),
                            $('#tank-filter').val()
                        );
                        alert(response.message);
                    } else {
                        alert('Error acknowledging alarms: ' + response.message);
                    }
                },
                error: function(error) {
                    alert('Error acknowledging alarms: ' + error.responseText);
                }
            });
        }
    });

    // Clear all alarms
    $('#clear-all-btn').click(function() {
        if (confirm('Are you sure you want to delete all filtered alarms? This action cannot be undone.')) {
            $.ajax({
                url: '/admin/alarms/clear-all',
                method: 'POST',
                data: {
                    acknowledged: $('#acknowledged-filter').val(),
                    type: $('#type-filter').val(),
                    tank_id: $('#tank-filter').val()
                },
                dataType: 'json',
                success: function(response) {
                    if (response.success) {
                        fetchAlarms(
                            currentPage, 
                            $('#acknowledged-filter').val(), 
                            $('#type-filter').val(),
                            $('#tank-filter').val()
                        );
                        alert(response.message);
                    } else {
                        alert('Error clearing alarms: ' + response.message);
                    }
                },
                error: function(error) {
                    alert('Error clearing alarms: ' + error.responseText);
                }
            });
        }
    });

    // Set up auto-refresh
    setInterval(function() {
        fetchAlarms(
            currentPage, 
            $('#acknowledged-filter').val(), 
            $('#type-filter').val(),
            $('#tank-filter').val()
        );
    }, 60000); // Refresh every minute
});
