document.addEventListener('DOMContentLoaded', function() {
    let currentPage = 1;
    let itemsPerPage = 10;
    let totalCompanies = 0;
    let companies = [];

    function fetchCompanies(page, search, status) {
        const params = new URLSearchParams({ page: page, search: search, status: status });
        fetch('/admin/api/companies?' + params.toString())
            .then(response => response.json())
            .then(response => {
                if (response.success) {
                    companies = response.companies;
                    totalCompanies = response.total;
                    renderCompanies(companies);
                    renderPagination(totalCompanies, currentPage, itemsPerPage);
                } else {
                    alert('Error fetching companies: ' + response.message);
                    console.error('Error fetching companies:', response);
                }
            })
            .catch(error => {
                alert('Error fetching companies: ' + error);
                console.error('Error fetching companies:', error);
            });
    }

    function renderCompanies(companies) {
        const companyList = document.getElementById('company-list');
        companyList.innerHTML = '';
        companies.forEach(company => {
            const row = document.createElement('tr');
            row.innerHTML = `<td>${company.name}</td><td>${company.contact_person || 'N/A'}</td><td>${company.email || 'N/A'}</td><td>${company.phone || 'N/A'}</td><td>${company.sites.length}</td><td>${company.get_tank_count}</td><td><span class="badge ${company.is_active ? 'bg-success' : 'bg-danger'}">${company.is_active ? 'Active' : 'Inactive'}</span></td><td><div class="btn-group btn-group-sm"><button type="button" class="btn btn-primary edit-company-btn" data-company-id="${company.id}" data-bs-toggle="modal" data-bs-target="#editCompanyModal"><i class="bi bi-pencil"></i></button><a href="/admin/companies/${company.id}" class="btn btn-info"><i class="bi bi-eye"></i></a><button type="button" class="btn btn-danger delete-company-btn" data-company-id="${company.id}" data-company-name="${company.name}"><i class="bi bi-trash"></i></button></div></td>`;
            companyList.appendChild(row);
        });
    }

    function renderPagination(total, currentPage, itemsPerPage) {
        const totalPages = Math.ceil(total / itemsPerPage);
        const pagination = document.getElementById('pagination');
        pagination.innerHTML = '';
        for (let i = 1; i <= totalPages; i++) {
            const li = document.createElement('li');
            li.className = 'page-item';
            const a = document.createElement('a');
            a.className = 'page-link';
            a.href = '#';
            a.textContent = i;
            a.addEventListener('click', function(e) {
                e.preventDefault();
                currentPage = i;
                fetchCompanies(currentPage, document.getElementById('company-search').value, document.getElementById('status-filter').value);
            });
            li.appendChild(a);
            pagination.appendChild(li);
        }
    }

    fetchCompanies(currentPage, '', 'all');

    document.getElementById('company-search').addEventListener('change', function() {
        currentPage = 1;
        fetchCompanies(currentPage, document.getElementById('company-search').value, document.getElementById('status-filter').value);
    });

    document.getElementById('status-filter').addEventListener('change', function() {
        currentPage = 1;
        fetchCompanies(currentPage, document.getElementById('company-search').value, document.getElementById('status-filter').value);
    });

    document.getElementById('save-new-company-btn').addEventListener('click', function() {
        const form = document.getElementById('add-company-form');
        fetch('/admin/companies/create', {
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
                document.getElementById('addCompanyModal').classList.add('hidden');
                fetchCompanies(currentPage, document.getElementById('company-search').value, document.getElementById('status-filter').value);
                alert(response.message);
            } else {
                alert('Error adding company: ' + response.message);
            }
        })
        .catch(error => {
            alert('Error adding company: ' + error);
        });
    });

    document.getElementById('company-list').addEventListener('click', function(e) {
        const editBtn = e.target.closest('.edit-company-btn');
        if (editBtn) {
            const companyId = editBtn.dataset.companyId;
            fetch(`/admin/companies/${companyId}`)
                .then(response => response.json())
                .then(response => {
                    if (response.success) {
                        document.getElementById('edit-company-id').value = response.company.id;
                        document.getElementById('edit-name').value = response.company.name;
                        document.getElementById('edit-contact-person').value = response.company.contact_person;
                        document.getElementById('edit-email').value = response.company.email;
                        document.getElementById('edit-phone').value = response.company.phone;
                        document.getElementById('edit-address').value = response.company.address;
                        document.getElementById('edit-is-active').checked = response.company.is_active;
                    } else {
                        alert('Error fetching company: ' + response.message);
                    }
                })
                .catch(error => {
                    alert('Error fetching company: ' + error);
                });
        }

        const deleteBtn = e.target.closest('.delete-company-btn');
        if (deleteBtn) {
            const companyId = deleteBtn.dataset.companyId;
            const companyName = deleteBtn.dataset.companyName;
            if (confirm(`Are you sure you want to delete company "${companyName}"?`)) {
                fetch(`/admin/companies/delete/${companyId}`, { method: 'POST', headers: { 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]).content } })
                    .then(response => response.json())
                    .then(response => {
                        if (response.success) {
                            fetchCompanies(currentPage, document.getElementById('company-search').value, document.getElementById('status-filter').value);
                            alert(response.message);
                        } else {
                            alert('Error deleting company: ' + response.message);
                        }
                    })
                    .catch(error => {
                        alert('Error deleting company: ' + error);
                    });
            }
        }
    });

    document.getElementById('update-company-btn').addEventListener('click', function() {
        const form = document.getElementById('edit-company-form');
        fetch('/admin/companies/edit', {
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
                document.getElementById('editCompanyModal').classList.add('hidden');
                fetchCompanies(currentPage, document.getElementById('company-search').value, document.getElementById('status-filter').value);
                alert(response.message);
            } else {
                alert('Error updating company: ' + response.message);
            }
        })
        .catch(error => {
            alert('Error updating company: ' + error);
        });
    });
});
