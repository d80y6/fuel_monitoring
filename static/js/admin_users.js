/**
 * Admin Users Management JavaScript
 * Handles functionality for the admin users management page
 */

$(document).ready(function() {
    // Initialize variables
    let currentPage = 1;
    let itemsPerPage = 10;
    let totalUsers = 0;
    let users = [];

    // Function to fetch users
    function fetchUsers(page, search, role, status) {
        $.ajax({
            url: '/admin/api/users',
            method: 'GET',
            data: { 
                page: page, 
                search: search, 
                role: role, 
                status: status 
            },
            dataType: 'json',
            success: function(response) {
                if (response.success) {
                    users = response.users;
                    totalUsers = response.total;
                    renderUsers(users);
                    renderPagination(totalUsers, currentPage, itemsPerPage);
                } else {
                    alert('Error fetching users: ' + response.message);
                    console.error('Error fetching users:', response);
                }
            },
            error: function(error) {
                alert('Error fetching users: ' + error.responseText);
                console.error('Error fetching users:', error);
            }
        });
    }

    // Function to render users
    function renderUsers(users) {
        let userList = $('#user-list');
        userList.empty();
        
        if (users.length === 0) {
            userList.append('<tr><td colspan="7" class="text-center">No users found</td></tr>');
            return;
        }
        
        users.forEach(user => {
            // Format last login
            let lastLogin = user.last_login ? new Date(user.last_login).toLocaleString() : 'Never';
            
            // Create role badge
            let roleBadge = '';
            switch (user.role) {
                case 'admin':
                    roleBadge = '<span class="badge bg-danger">Admin</span>';
                    break;
                case 'company_admin':
                    roleBadge = '<span class="badge bg-warning">Company Admin</span>';
                    break;
                case 'user':
                    roleBadge = '<span class="badge bg-info">User</span>';
                    break;
                default:
                    roleBadge = `<span class="badge bg-secondary">${user.role}</span>`;
            }
            
            // Create active status badge
            let activeBadge = user.is_active ? 
                '<span class="badge bg-success">Active</span>' : 
                '<span class="badge bg-danger">Inactive</span>';
            
            let row = $('<tr>');
            row.append(`<td>${user.username}</td>`);
            row.append(`<td>${user.full_name || 'N/A'}</td>`);
            row.append(`<td>${user.email}</td>`);
            row.append(`<td>${roleBadge}</td>`);
            row.append(`<td>${activeBadge}</td>`);
            row.append(`<td>${lastLogin}</td>`);
            row.append(`<td>
                <div class="btn-group btn-group-sm">
                    <button type="button" class="btn btn-primary edit-user-btn" data-user-id="${user.id}" data-bs-toggle="modal" data-bs-target="#editUserModal">
                        <i class="bi bi-pencil"></i>
                    </button>
                    <a href="/admin/users/access/${user.id}" class="btn btn-info">
                        <i class="bi bi-key"></i>
                    </a>
                    <button type="button" class="btn btn-danger delete-user-btn" data-user-id="${user.id}" data-username="${user.username}">
                        <i class="bi bi-trash"></i>
                    </button>
                </div>
            </td>`);
            userList.append(row);
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
                fetchUsers(
                    currentPage, 
                    $('#user-search').val(), 
                    $('#role-filter').val(), 
                    $('#status-filter').val()
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
                fetchUsers(
                    currentPage, 
                    $('#user-search').val(), 
                    $('#role-filter').val(), 
                    $('#status-filter').val()
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
                fetchUsers(
                    currentPage, 
                    $('#user-search').val(), 
                    $('#role-filter').val(), 
                    $('#status-filter').val()
                );
            }
        });
        nextLi.append(nextA);
        pagination.append(nextLi);
    }

    // Initial fetch
    fetchUsers(currentPage, '', 'all', 'all');

    // Search and filter
    $('#user-search, #role-filter, #status-filter').change(function() {
        currentPage = 1;
        fetchUsers(
            currentPage, 
            $('#user-search').val(), 
            $('#role-filter').val(), 
            $('#status-filter').val()
        );
    });

    // Add user
    $('#save-new-user-btn').click(function() {
        // Validate form
        let form = $('#add-user-form');
        
        if (!form[0].checkValidity()) {
            form[0].reportValidity();
            return;
        }
        
        // Check if passwords match
        let password = $('#add-password').val();
        let confirmPassword = $('#add-confirm-password').val();
        
        if (password !== confirmPassword) {
            alert('Passwords do not match');
            return;
        }
        
        $.ajax({
            url: '/admin/api/users/create',
            method: 'POST',
            data: form.serialize(),
            dataType: 'json',
            success: function(response) {
                if (response.success) {
                    $('#addUserModal').modal('hide');
                    fetchUsers(
                        currentPage, 
                        $('#user-search').val(), 
                        $('#role-filter').val(), 
                        $('#status-filter').val()
                    );
                    alert(response.message);
                    
                    // Reset form
                    form[0].reset();
                } else {
                    alert('Error adding user: ' + response.message);
                }
            },
            error: function(error) {
                alert('Error adding user: ' + error.responseText);
            }
        });
    });

    // Edit user - load data
    $(document).on('click', '.edit-user-btn', function() {
        let userId = $(this).data('user-id');
        
        $.ajax({
            url: `/admin/api/users/${userId}`,
            method: 'GET',
            dataType: 'json',
            success: function(response) {
                if (response.success) {
                    let user = response.user;
                    
                    $('#edit-user-id').val(user.id);
                    $('#edit-username').val(user.username);
                    $('#edit-email').val(user.email);
                    $('#edit-first-name').val(user.first_name);
                    $('#edit-last-name').val(user.last_name);
                    $('#edit-role').val(user.role);
                    $('#edit-is-active').prop('checked', user.is_active);
                    
                    // Clear password fields
                    $('#edit-password').val('');
                    $('#edit-confirm-password').val('');
                } else {
                    alert('Error fetching user: ' + response.message);
                }
            },
            error: function(error) {
                alert('Error fetching user: ' + error.responseText);
            }
        });
    });

    // Edit user - save changes
    $('#update-user-btn').click(function() {
        // Validate form
        let form = $('#edit-user-form');
        
        if (!form[0].checkValidity()) {
            form[0].reportValidity();
            return;
        }
        
        // Check if passwords match if provided
        let password = $('#edit-password').val();
        let confirmPassword = $('#edit-confirm-password').val();
        
        if (password && password !== confirmPassword) {
            alert('Passwords do not match');
            return;
        }
        
        $.ajax({
            url: '/admin/api/users/update',
            method: 'POST',
            data: form.serialize(),
            dataType: 'json',
            success: function(response) {
                if (response.success) {
                    $('#editUserModal').modal('hide');
                    fetchUsers(
                        currentPage, 
                        $('#user-search').val(), 
                        $('#role-filter').val(), 
                        $('#status-filter').val()
                    );
                    alert(response.message);
                } else {
                    alert('Error updating user: ' + response.message);
                }
            },
            error: function(error) {
                alert('Error updating user: ' + error.responseText);
            }
        });
    });

    // Delete user
    $(document).on('click', '.delete-user-btn', function() {
        let userId = $(this).data('user-id');
        let username = $(this).data('username');
        
        if (confirm(`Are you sure you want to delete user "${username}"?`)) {
            $.ajax({
                url: `/admin/api/users/delete/${userId}`,
                method: 'POST',
                dataType: 'json',
                success: function(response) {
                    if (response.success) {
                        fetchUsers(
                            currentPage, 
                            $('#user-search').val(), 
                            $('#role-filter').val(), 
                            $('#status-filter').val()
                        );
                        alert(response.message);
                    } else {
                        alert('Error deleting user: ' + response.message);
                    }
                },
                error: function(error) {
                    alert('Error deleting user: ' + error.responseText);
                }
            });
        }
    });

    // Reset add user form when modal is closed
    $('#addUserModal').on('hidden.bs.modal', function() {
        $('#add-user-form')[0].reset();
    });
});
