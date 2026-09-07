/**
 * Admin Users Management JavaScript
 * Handles functionality for the admin users management page
 */

document.addEventListener('DOMContentLoaded', function() {
    let currentPage = 1;
    let itemsPerPage = 10;
    let totalUsers = 0;
    let users = [];

    function fetchUsers(page, search, role, status) {
        const params = new URLSearchParams({ page: page, search: search, role: role, status: status });
        fetch('/admin/api/users?' + params.toString())
            .then(response => response.json())
            .then(response => {
                if (response.success) {
                    users = response.users;
                    totalUsers = response.total;
                    renderUsers(users);
                    renderPagination(totalUsers, currentPage, itemsPerPage);
                } else {
                    alert('Error fetching users: ' + response.message);
                    console.error('Error fetching users:', response);
                }
            })
            .catch(error => {
                alert('Error fetching users: ' + error);
                console.error('Error fetching users:', error);
            });
    }

    function renderUsers(users) {
        const userList = document.getElementById('user-list');
        userList.innerHTML = '';

        if (users.length === 0) {
            userList.innerHTML = '<tr><td colspan="7" class="text-center">No users found</td></tr>';
            return;
        }

        users.forEach(user => {
            const lastLogin = user.last_login ? new Date(user.last_login).toLocaleString() : 'Never';

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

            const activeBadge = user.is_active ?
                '<span class="badge bg-success">Active</span>' :
                '<span class="badge bg-danger">Inactive</span>';

            const row = document.createElement('tr');
            row.innerHTML = `<td>${user.username}</td><td>${user.full_name || 'N/A'}</td><td>${user.email}</td><td>${roleBadge}</td><td>${activeBadge}</td><td>${lastLogin}</td><td><div class="btn-group btn-group-sm"><button type="button" class="btn btn-primary edit-user-btn" data-user-id="${user.id}" data-bs-toggle="modal" data-bs-target="#editUserModal"><i class="bi bi-pencil"></i></button><a href="/admin/users/access/${user.id}" class="btn btn-info"><i class="bi bi-key"></i></a><button type="button" class="btn btn-danger delete-user-btn" data-user-id="${user.id}" data-username="${user.username}"><i class="bi bi-trash"></i></button></div></td>`;
            userList.appendChild(row);
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
                fetchUsers(currentPage, document.getElementById('user-search').value, document.getElementById('role-filter').value, document.getElementById('status-filter').value);
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
                fetchUsers(currentPage, document.getElementById('user-search').value, document.getElementById('role-filter').value, document.getElementById('status-filter').value);
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
                fetchUsers(currentPage, document.getElementById('user-search').value, document.getElementById('role-filter').value, document.getElementById('status-filter').value);
            }
        });
        nextLi.appendChild(nextA);
        pagination.appendChild(nextLi);
    }

    fetchUsers(currentPage, '', 'all', 'all');

    document.getElementById('user-search').addEventListener('change', function() {
        currentPage = 1;
        fetchUsers(currentPage, document.getElementById('user-search').value, document.getElementById('role-filter').value, document.getElementById('status-filter').value);
    });

    document.getElementById('role-filter').addEventListener('change', function() {
        currentPage = 1;
        fetchUsers(currentPage, document.getElementById('user-search').value, document.getElementById('role-filter').value, document.getElementById('status-filter').value);
    });

    document.getElementById('status-filter').addEventListener('change', function() {
        currentPage = 1;
        fetchUsers(currentPage, document.getElementById('user-search').value, document.getElementById('role-filter').value, document.getElementById('status-filter').value);
    });

    document.getElementById('save-new-user-btn').addEventListener('click', function() {
        const form = document.getElementById('add-user-form');

        if (!form.checkValidity()) {
            form.reportValidity();
            return;
        }

        const password = document.getElementById('add-password').value;
        const confirmPassword = document.getElementById('add-confirm-password').value;

        if (password !== confirmPassword) {
            alert('Passwords do not match');
            return;
        }

        fetch('/admin/api/users/create', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content
            },
            body: new URLSearchParams(new FormData(form)).toString()
        })
        .then(response => response.json())
        .then(response => {
            if (response.success) {
                document.getElementById('addUserModal').classList.add('hidden');
                fetchUsers(currentPage, document.getElementById('user-search').value, document.getElementById('role-filter').value, document.getElementById('status-filter').value);
                alert(response.message);
                form.reset();
            } else {
                alert('Error adding user: ' + response.message);
            }
        })
        .catch(error => {
            alert('Error adding user: ' + error);
        });
    });

    document.addEventListener('click', function(e) {
        const editBtn = e.target.closest('.edit-user-btn');
        if (editBtn) {
            const userId = editBtn.dataset.userId;
            fetch(`/admin/api/users/${userId}`)
                .then(response => response.json())
                .then(response => {
                    if (response.success) {
                        const user = response.user;
                        document.getElementById('edit-user-id').value = user.id;
                        document.getElementById('edit-username').value = user.username;
                        document.getElementById('edit-email').value = user.email;
                        document.getElementById('edit-first-name').value = user.first_name;
                        document.getElementById('edit-last-name').value = user.last_name;
                        document.getElementById('edit-role').value = user.role;
                        document.getElementById('edit-is-active').checked = user.is_active;
                        document.getElementById('edit-password').value = '';
                        document.getElementById('edit-confirm-password').value = '';
                    } else {
                        alert('Error fetching user: ' + response.message);
                    }
                })
                .catch(error => {
                    alert('Error fetching user: ' + error);
                });
        }

        const deleteBtn = e.target.closest('.delete-user-btn');
        if (deleteBtn) {
            const userId = deleteBtn.dataset.userId;
            const username = deleteBtn.dataset.username;
            if (confirm(`Are you sure you want to delete user "${username}"?`)) {
                fetch(`/admin/api/users/delete/${userId}`, { method: 'POST', headers: { 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]).content } })
                    .then(response => response.json())
                    .then(response => {
                        if (response.success) {
                            fetchUsers(currentPage, document.getElementById('user-search').value, document.getElementById('role-filter').value, document.getElementById('status-filter').value);
                            alert(response.message);
                        } else {
                            alert('Error deleting user: ' + response.message);
                        }
                    })
                    .catch(error => {
                        alert('Error deleting user: ' + error);
                    });
            }
        }
    });

    document.getElementById('update-user-btn').addEventListener('click', function() {
        const form = document.getElementById('edit-user-form');

        if (!form.checkValidity()) {
            form.reportValidity();
            return;
        }

        const password = document.getElementById('edit-password').value;
        const confirmPassword = document.getElementById('edit-confirm-password').value;

        if (password && password !== confirmPassword) {
            alert('Passwords do not match');
            return;
        }

        fetch('/admin/api/users/update', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content
            },
            body: new URLSearchParams(new FormData(form)).toString()
        })
        .then(response => response.json())
        .then(response => {
            if (response.success) {
                document.getElementById('editUserModal').classList.add('hidden');
                fetchUsers(currentPage, document.getElementById('user-search').value, document.getElementById('role-filter').value, document.getElementById('status-filter').value);
                alert(response.message);
            } else {
                alert('Error updating user: ' + response.message);
            }
        })
        .catch(error => {
            alert('Error updating user: ' + error);
        });
    });

    document.getElementById('addUserModal').addEventListener('hidden.bs.modal', function() {
        document.getElementById('add-user-form').reset();
    });
});
