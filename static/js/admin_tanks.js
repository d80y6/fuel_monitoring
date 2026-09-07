/**
 * Admin Tanks JavaScript
 * Handles functionality for the admin tanks page
 */

document.addEventListener('DOMContentLoaded', function() {
    // Initialize variables
    let currentPage = 1;
    let itemsPerPage = 10;
    let totalTanks = 0;
    
    // Function to fetch tanks
    function fetchTanks(page, search, companyId, siteId, status) {
        // Show loading indicator
        const tankList = document.getElementById('tank-list');
        if (tankList) {
            tankList.innerHTML = `
                <tr>
                    <td colspan="8" class="text-center">
                        <div class="spinner-border text-primary" role="status">
                            <span class="visually-hidden">Loading...</span>
                        </div>
                        <p class="mt-2">Loading tanks...</p>
                    </td>
                </tr>
            `;
        }
        
        // Build query parameters
        const params = new URLSearchParams({
            page: page,
            search: search || '',
            company_id: companyId || 'all',
            site_id: siteId || 'all',
            status: status || 'all'
        });
        
        // Fetch tanks from API
        fetch(`/admin/api/tanks?${params.toString()}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error('Network response was not ok');
                }
                return response.json();
            })
            .then(data => {
                if (data.success) {
                    // Update variables
                    totalTanks = data.total;
                    
                    // Render tanks and pagination
                    renderTanks(data.tanks);
                    renderPagination(totalTanks, currentPage, itemsPerPage);
                } else {
                    showAlert('danger', data.message || 'Error fetching tanks');
                }
            })
            .catch(error => {
                console.error('Error fetching tanks:', error);
                showAlert('danger', 'Error fetching tanks: ' + error.message);
                
                // Show error in table
                if (tankList) {
                    tankList.innerHTML = `
                        <tr>
                            <td colspan="8" class="text-center text-danger">
                                <i class="bi bi-exclamation-triangle"></i> 
                                Error loading tanks: ${error.message}
                            </td>
                        </tr>
                    `;
                }
            });
    }
    
    // Function to render tanks
    function renderTanks(tanks) {
        const tankList = document.getElementById('tank-list');
        if (!tankList) return;
        
        // Clear existing rows
        tankList.innerHTML = '';
        
        if (tanks.length === 0) {
            tankList.innerHTML = `
                <tr>
                    <td colspan="8" class="text-center">
                        <i class="bi bi-info-circle"></i> No tanks found matching your criteria.
                    </td>
                </tr>
            `;
            return;
        }
        
        // Add rows for each tank
        tanks.forEach(tank => {
            // Create fill level badge with appropriate color
            let fillLevelBadge = '';
            if (tank.measurement) {
                const fillPercent = tank.measurement.fill_percent;
                let badgeClass = 'bg-primary';
                
                if (fillPercent <= tank.critical_level_threshold) {
                    badgeClass = 'bg-danger';
                } else if (fillPercent <= tank.low_level_threshold) {
                    badgeClass = 'bg-warning';
                } else if (fillPercent >= tank.high_level_threshold) {
                    badgeClass = 'bg-warning';
                }
                
                fillLevelBadge = `<span class="badge ${badgeClass}">${fillPercent.toFixed(1)}%</span>`;
            } else {
                fillLevelBadge = '<span class="badge bg-secondary">N/A</span>';
            }
            
            // Create connection status badge
            let connectionBadge = '';
            switch (tank.connection_status) {
                case 'Connected':
                    connectionBadge = '<span class="badge bg-success">Connected</span>';
                    break;
                case 'Recently Disconnected':
                    connectionBadge = '<span class="badge bg-warning">Recently Disconnected</span>';
                    break;
                default:
                    connectionBadge = '<span class="badge bg-danger">Disconnected</span>';
            }
            
            // Create active status badge
            const activeBadge = tank.is_active ? 
                '<span class="badge bg-success">Active</span>' : 
                '<span class="badge bg-danger">Inactive</span>';
            
            // Create row
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${tank.name}</td>
                <td>${tank.company_name}</td>
                <td>${tank.site_name}</td>
                <td>${fillLevelBadge}</td>
                <td>${tank.measurement ? tank.measurement.volume.toFixed(1) + ' L' : 'N/A'}</td>
                <td>${connectionBadge}</td>
                <td>${activeBadge}</td>
                <td>
                    <div class="btn-group btn-group-sm">
                        <a href="/admin/tanks/${tank.id}" class="btn btn-info">
                            <i class="bi bi-eye"></i>
                        </a>
                        <a href="/admin/tanks/edit/${tank.id}" class="btn btn-primary">
                            <i class="bi bi-pencil"></i>
                        </a>
                        <button type="button" class="btn btn-danger delete-tank-btn" 
                                data-tank-id="${tank.id}" data-tank-name="${tank.name}">
                            <i class="bi bi-trash"></i>
                        </button>
                    </div>
                </td>
            `;
            
            tankList.appendChild(row);
        });
    }

    // Function to render pagination
    function renderPagination(total, currentPage, itemsPerPage) {
        const pagination = document.getElementById('pagination');
        if (!pagination) return;
        
        pagination.innerHTML = '';
        
        const totalPages = Math.ceil(total / itemsPerPage);
        if (totalPages <= 1) return;
        
        // Previous button
        const prevLi = document.createElement('li');
        prevLi.className = `page-item ${currentPage === 1 ? 'disabled' : ''}`;
        const prevLink = document.createElement('a');
        prevLink.className = 'page-link';
        prevLink.href = '#';
        prevLink.innerHTML = '&laquo;';
        prevLink.addEventListener('click', function(e) {
            e.preventDefault();
            if (currentPage > 1) {
                currentPage--;
                fetchTanks(
                    currentPage,
                    document.getElementById('tank-search').value,
                    document.getElementById('company-filter').value,
                    document.getElementById('site-filter').value,
                    document.getElementById('status-filter').value
                );
            }
        });
        prevLi.appendChild(prevLink);
        pagination.appendChild(prevLi);
        
        // Page numbers
        const maxPages = 5; // Maximum number of page links to show
        let startPage = Math.max(1, currentPage - Math.floor(maxPages / 2));
        let endPage = Math.min(totalPages, startPage + maxPages - 1);
        
        if (endPage - startPage + 1 < maxPages) {
            startPage = Math.max(1, endPage - maxPages + 1);
        }
        
        for (let i = startPage; i <= endPage; i++) {
            const li = document.createElement('li');
            li.className = `page-item ${i === currentPage ? 'active' : ''}`;
            const link = document.createElement('a');
            link.className = 'page-link';
            link.href = '#';
            link.textContent = i;
            link.addEventListener('click', function(e) {
                e.preventDefault();
                currentPage = i;
                fetchTanks(
                    currentPage,
                    document.getElementById('tank-search').value,
                    document.getElementById('company-filter').value,
                    document.getElementById('site-filter').value,
                    document.getElementById('status-filter').value
                );
            });
            li.appendChild(link);
            pagination.appendChild(li);
        }
        
        // Next button
        const nextLi = document.createElement('li');
        nextLi.className = `page-item ${currentPage === totalPages ? 'disabled' : ''}`;
        const nextLink = document.createElement('a');
        nextLink.className = 'page-link';
        nextLink.href = '#';
        nextLink.innerHTML = '&raquo;';
        nextLink.addEventListener('click', function(e) {
            e.preventDefault();
            if (currentPage < totalPages) {
                currentPage++;
                fetchTanks(
                    currentPage,
                    document.getElementById('tank-search').value,
                    document.getElementById('company-filter').value,
                    document.getElementById('site-filter').value,
                    document.getElementById('status-filter').value
                );
            }
        });
        nextLi.appendChild(nextLink);
        pagination.appendChild(nextLi);
    }

    // Function to show alert
    function showAlert(type, message) {
        const alertContainer = document.getElementById('alert-container');
        if (!alertContainer) return;
        
        const alert = document.createElement('div');
        alert.className = `alert alert-${type} alert-dismissible fade show`;
        alert.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        `;
        
        alertContainer.innerHTML = '';
        alertContainer.appendChild(alert);
        
        // Auto-dismiss after 5 seconds
        setTimeout(() => {
            alert.classList.remove('show');
            setTimeout(() => {
                alertContainer.removeChild(alert);
            }, 150);
        }, 5000);
    }

    // Initial fetch
    const tankSearch = document.getElementById('tank-search');
    const companyFilter = document.getElementById('company-filter');
    const siteFilter = document.getElementById('site-filter');
    const statusFilter = document.getElementById('status-filter');
    
    if (tankSearch && companyFilter && siteFilter && statusFilter) {
        fetchTanks(
            currentPage,
            tankSearch.value,
            companyFilter.value,
            siteFilter.value,
            statusFilter.value
        );
        
        // Set up search and filter events
        tankSearch.addEventListener('input', debounce(function() {
            currentPage = 1;
            fetchTanks(
                currentPage,
                tankSearch.value,
                companyFilter.value,
                siteFilter.value,
                statusFilter.value
            );
        }, 500));
        
        companyFilter.addEventListener('change', function() {
            currentPage = 1;
            
            // Update site filter options based on selected company
            updateSiteOptions(companyFilter.value);
            
            fetchTanks(
                currentPage,
                tankSearch.value,
                companyFilter.value,
                siteFilter.value,
                statusFilter.value
            );
        });
        
        siteFilter.addEventListener('change', function() {
            currentPage = 1;
            fetchTanks(
                currentPage,
                tankSearch.value,
                companyFilter.value,
                siteFilter.value,
                statusFilter.value
            );
        });
        
        statusFilter.addEventListener('change', function() {
            currentPage = 1;
            fetchTanks(
                currentPage,
                tankSearch.value,
                companyFilter.value,
                siteFilter.value,
                statusFilter.value
            );
        });
    }

    // Function to update site options based on selected company
    function updateSiteOptions(companyId) {
        const siteFilter = document.getElementById('site-filter');
        if (!siteFilter) return;
        
        // Keep the first option (All Sites)
        const firstOption = siteFilter.options[0];
        siteFilter.innerHTML = '';
        siteFilter.appendChild(firstOption);
        
        if (companyId === 'all') {
            // If 'All Companies' is selected, show all sites
            const allSites = Array.from(document.querySelectorAll('#all-sites-data option'));
            allSites.forEach(site => {
                const option = document.createElement('option');
                option.value = site.value;
                option.textContent = site.textContent;
                siteFilter.appendChild(option);
            });
        } else {
            // If a specific company is selected, show only its sites
            const companySites = Array.from(document.querySelectorAll(`#all-sites-data option[data-company-id="${companyId}"]`));
            companySites.forEach(site => {
                const option = document.createElement('option');
                option.value = site.value;
                option.textContent = site.textContent;
                siteFilter.appendChild(option);
            });
        }
        
        // Reset site filter to 'All Sites'
        siteFilter.value = 'all';
    }

    // Delete tank functionality
    document.addEventListener('click', function(e) {
        if (e.target.closest('.delete-tank-btn')) {
            const btn = e.target.closest('.delete-tank-btn');
            const tankId = btn.getAttribute('data-tank-id');
            const tankName = btn.getAttribute('data-tank-name');
            
            if (confirm(`Are you sure you want to delete tank "${tankName}"? This action cannot be undone.`)) {
                fetch(`/admin/tanks/delete/${tankId}`, {
                    method: 'POST',
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest',
                        'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content
                    }
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        showAlert('success', data.message || 'Tank deleted successfully');
                        fetchTanks(
                            currentPage,
                            tankSearch.value,
                            companyFilter.value,
                            siteFilter.value,
                            statusFilter.value
                        );
                    } else {
                        showAlert('danger', data.message || 'Error deleting tank');
                    }
                })
                .catch(error => {
                    console.error('Error deleting tank:', error);
                    showAlert('danger', 'Error deleting tank: ' + error.message);
                });
            }
        }
    });

    // Debounce function to limit how often a function can be called
    function debounce(func, wait) {
        let timeout;
        return function() {
            const context = this;
            const args = arguments;
            clearTimeout(timeout);
            timeout = setTimeout(() => {
                func.apply(context, args);
            }, wait);
        };
    }
});
