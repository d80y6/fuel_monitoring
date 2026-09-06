/**
 * Admin Sites Management JavaScript
 * Handles functionality for the admin sites management page
 */

$(document).ready(function() {
    // Initialize variables
    let currentPage = 1;
    let itemsPerPage = 10;
    let totalSites = 0;
    let sites = [];

    // Function to fetch sites
    function fetchSites(page, search, companyId, status) {
        $.ajax({
            url: '/admin/api/sites',
            method: 'GET',
            data: { 
                page: page, 
                search: search, 
                company_id: companyId, 
                status: status 
            },
            dataType: 'json',
            success: function(response) {
                if (response.success) {
                    sites = response.sites;
                    totalSites = response.total;
                    renderSites(sites);
                    renderPagination(totalSites, currentPage, itemsPerPage);
                } else {
                    alert('Error fetching sites: ' + response.message);
                    console.error('Error fetching sites:', response);
                }
            },
            error: function(error) {
                alert('Error fetching sites: ' + error.responseText);
                console.error('Error fetching sites:', error);
            }
        });
    }

    // Function to render sites
    function renderSites(sites) {
        let siteList = $('#site-list');
        siteList.empty();
        
        if (sites.length === 0) {
            siteList.append('<tr><td colspan="7" class="text-center">No sites found</td></tr>');
            return;
        }
        
        sites.forEach(site => {
            let row = $('<tr>');
            row.append(`<td>${site.name}</td>`);
            row.append(`<td>${site.company_name}</td>`);
            row.append(`<td>${site.address || 'N/A'}</td>`);
            row.append(`<td>${site.contact_name || 'N/A'}</td>`);
            row.append(`<td>${site.tank_count}</td>`);
            row.append(`<td><span class="badge ${site.is_active ? 'bg-success' : 'bg-danger'}">${site.is_active ? 'Active' : 'Inactive'}</span></td>`);
            row.append(`<td>
                <div class="btn-group btn-group-sm">
                    <button type="button" class="btn btn-primary edit-site-btn" data-site-id="${site.id}" data-bs-toggle="modal" data-bs-target="#editSiteModal">
                        <i class="bi bi-pencil"></i>
                    </button>
                    <a href="/admin/sites/${site.id}" class="btn btn-info">
                        <i class="bi bi-eye"></i>
                    </a>
                    <button type="button" class="btn btn-danger delete-site-btn" data-site-id="${site.id}" data-site-name="${site.name}">
                        <i class="bi bi-trash"></i>
                    </button>
                </div>
            </td>`);
            siteList.append(row);
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
                fetchSites(
                    currentPage, 
                    $('#site-search').val(), 
                    $('#company-filter').val(), 
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
                fetchSites(
                    currentPage, 
                    $('#site-search').val(), 
                    $('#company-filter').val(), 
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
                fetchSites(
                    currentPage, 
                    $('#site-search').val(), 
                    $('#company-filter').val(), 
                    $('#status-filter').val()
                );
            }
        });
        nextLi.append(nextA);
        pagination.append(nextLi);
    }

    // Initial fetch
    fetchSites(currentPage, '', 'all', 'all');

    // Search and filter
    $('#site-search, #company-filter, #status-filter').change(function() {
        currentPage = 1;
        fetchSites(
            currentPage, 
            $('#site-search').val(), 
            $('#company-filter').val(), 
            $('#status-filter').val()
        );
    });

    // Add site
    $('#save-new-site-btn').click(function() {
        $.ajax({
            url: '/admin/sites/create',
            method: 'POST',
            data: $('#add-site-form').serialize(),
            dataType: 'json',
            success: function(response) {
                if (response.success) {
                    $('#addSiteModal').modal('hide');
                    fetchSites(
                        currentPage, 
                        $('#site-search').val(), 
                        $('#company-filter').val(), 
                        $('#status-filter').val()
                    );
                    alert(response.message);
                    
                    // Reset form
                    $('#add-site-form')[0].reset();
                } else {
                    alert('Error adding site: ' + response.message);
                }
            },
            error: function(error) {
                alert('Error adding site: ' + error.responseText);
            }
        });
    });

    // Edit site - load data
    $(document).on('click', '.edit-site-btn', function() {
        let siteId = $(this).data('site-id');
        
        // Find site in the current data
        let site = sites.find(s => s.id === siteId);
        
        if (site) {
            $('#edit-site-id').val(site.id);
            $('#edit-name').val(site.name);
            $('#edit-company').val(site.company_id);
            $('#edit-address').val(site.address);
            $('#edit-contact-name').val(site.contact_name);
            $('#edit-contact-email').val(site.contact_email);
            $('#edit-contact-phone').val(site.contact_phone);
            $('#edit-is-active').prop('checked', site.is_active);
        } else {
            alert('Error: Site data not found');
        }
    });

    // Edit site - save changes
    $('#update-site-btn').click(function() {
        $.ajax({
            url: '/admin/sites/edit/' + $('#edit-site-id').val(),
            method: 'POST',
            data: $('#edit-site-form').serialize(),
            dataType: 'json',
            success: function(response) {
                if (response.success) {
                    $('#editSiteModal').modal('hide');
                    fetchSites(
                        currentPage, 
                        $('#site-search').val(), 
                        $('#company-filter').val(), 
                        $('#status-filter').val()
                    );
                    alert(response.message);
                } else {
                    alert('Error updating site: ' + response.message);
                }
            },
            error: function(error) {
                alert('Error updating site: ' + error.responseText);
            }
        });
    });

    // Delete site
    $(document).on('click', '.delete-site-btn', function() {
        let siteId = $(this).data('site-id');
        let siteName = $(this).data('site-name');
        
        if (confirm(`Are you sure you want to delete site "${siteName}"?`)) {
            $.ajax({
                url: '/admin/sites/delete/' + siteId,
                method: 'POST',
                dataType: 'json',
                success: function(response) {
                    if (response.success) {
                        fetchSites(
                            currentPage, 
                            $('#site-search').val(), 
                            $('#company-filter').val(), 
                            $('#status-filter').val()
                        );
                        alert(response.message);
                    } else {
                        alert('Error deleting site: ' + response.message);
                    }
                },
                error: function(error) {
                    alert('Error deleting site: ' + error.responseText);
                }
            });
        }
    });

    // Reset add site form when modal is closed
    $('#addSiteModal').on('hidden.bs.modal', function() {
        $('#add-site-form')[0].reset();
    });
});
