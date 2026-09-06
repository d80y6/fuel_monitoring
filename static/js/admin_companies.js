$(document).ready(function() {
    // Initialize variables
    let currentPage = 1;
    let itemsPerPage = 10;
    let totalCompanies = 0;
    let companies = [];

    // Function to fetch companies
    function fetchCompanies(page, search, status) {
        $.ajax({
            url: '/admin/api/companies',
            method: 'GET',
            data: { page: page, search: search, status: status },
            dataType: 'json',
            success: function(response) {
                //console.log('diya');
                //console.log(response);
                if (response.success) {
                    companies = response.companies;
                    totalCompanies = response.total;
                    renderCompanies(companies);
                    renderPagination(totalCompanies, currentPage, itemsPerPage);
                } else {
                    alert('Error fetching companies: ' + response.message);
                    console.error('Error fetching companies:', response);
                }
            },
            error: function(error) {
                alert('Error fetching companies: ' + error.responseText);
                console.error('Error fetching companies:', error);
            }
        });
    }

    // Function to render companies
    function renderCompanies(companies) {
        let companyList = $('#company-list');
        companyList.empty();
        companies.forEach(company => {
            let row = $('<tr>');
            row.append(`<td>${company.name}</td>`);
            row.append(`<td>${company.contact_person || 'N/A'}</td>`);
            row.append(`<td>${company.email || 'N/A'}</td>`);
            row.append(`<td>${company.phone || 'N/A'}</td>`);
            row.append(`<td>${company.sites.length}</td>`);
            row.append(`<td>${company.get_tank_count}</td>`);
            row.append(`<td><span class="badge ${company.is_active ? 'bg-success' : 'bg-danger'}">${company.is_active ? 'Active' : 'Inactive'}</span></td>`);
            row.append(`<td>
                <div class="btn-group btn-group-sm">
                    <button type="button" class="btn btn-primary edit-company-btn" data-company-id="${company.id}" data-bs-toggle="modal" data-bs-target="#editCompanyModal">
                        <i class="bi bi-pencil"></i>
                    </button>
                    <a href="/admin/companies/${company.id}" class="btn btn-info">
                        <i class="bi bi-eye"></i>
                    </a>
                    <button type="button" class="btn btn-danger delete-company-btn" data-company-id="${company.id}" data-company-name="${company.name}">
                        <i class="bi bi-trash"></i>
                    </button>
                </div>
            </td>`);
            companyList.append(row);
        });
    }

    // Function to render pagination
    function renderPagination(total, currentPage, itemsPerPage) {
        let totalPages = Math.ceil(total / itemsPerPage);
        let pagination = $('#pagination');
        pagination.empty();
        for (let i = 1; i <= totalPages; i++) {
            let li = $('<li class="page-item">');
            let a = $('<a class="page-link" href="#">' + i + '</a>');
            a.click(function() {
                currentPage = i;
                fetchCompanies(currentPage, $('#company-search').val(), $('#status-filter').val());
            });
            li.append(a);
            pagination.append(li);
        }
    }

    // Initial fetch
    fetchCompanies(currentPage, '', 'all');

    // Search and filter
    $('#company-search, #status-filter').change(function() {
        currentPage = 1;
        fetchCompanies(currentPage, $('#company-search').val(), $('#status-filter').val());
    });

    // Add company
    $('#save-new-company-btn').click(function() {
        $.ajax({
            url: '/admin/companies/create',
            method: 'POST',
            data: $('#add-company-form').serialize(),
            dataType: 'json',
            success: function(response) {
                if (response.success) {
                    $('#addCompanyModal').modal('hide');
                    fetchCompanies(currentPage, $('#company-search').val(), $('#status-filter').val());
                    alert(response.message);
                } else {
                    alert('Error adding company: ' + response.message);
                }
            },
            error: function(error) {
                alert('Error adding company: ' + error.responseText);
            }
        });
    });

    // Edit company
    $('#company-list').on('click', '.edit-company-btn', function() {
        let companyId = $(this).data('company-id');
        $.ajax({
            url: `/admin/companies/${companyId}`,
            method: 'GET',
            dataType: 'json',
            success: function(response) {
                if (response.success) {
                    $('#edit-company-id').val(response.company.id);
                    $('#edit-name').val(response.company.name);
                    $('#edit-contact-person').val(response.company.contact_person);
                    $('#edit-email').val(response.company.email);
                    $('#edit-phone').val(response.company.phone);
                    $('#edit-address').val(response.company.address);
                    $('#edit-is-active').prop('checked', response.company.is_active);
                } else {
                    alert('Error fetching company: ' + response.message);
                }
            },
            error: function(error) {
                alert('Error fetching company: ' + error.responseText);
            }
        });
    });

    $('#update-company-btn').click(function() {
        $.ajax({
            url: '/admin/companies/edit',
            method: 'POST',
            data: $('#edit-company-form').serialize(),
            dataType: 'json',
            success: function(response) {
                if (response.success) {
                    $('#editCompanyModal').modal('hide');
                    fetchCompanies(currentPage, $('#company-search').val(), $('#status-filter').val());
                    alert(response.message);
                } else {
                    alert('Error updating company: ' + response.message);
                }
            },
            error: function(error) {
                alert('Error updating company: ' + error.responseText);
            }
        });
    });

    // Delete company
    $('#company-list').on('click', '.delete-company-btn', function() {
        let companyId = $(this).data('company-id');
        let companyName = $(this).data('company-name');
        if (confirm(`Are you sure you want to delete company "${companyName}"?`)) {
            $.ajax({
                url: `/admin/companies/delete/${companyId}`,
                method: 'POST',
                dataType: 'json',
                success: function(response) {
                    if (response.success) {
                        fetchCompanies(currentPage, $('#company-search').val(), $('#status-filter').val());
                        alert(response.message);
                    } else {
                        alert('Error deleting company: ' + response.message);
                    }
                },
                error: function(error) {
                    alert('Error deleting company: ' + error.responseText);
                }
            });
        }
    });
});
