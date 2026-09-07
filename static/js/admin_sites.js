/**
 * Admin Sites Management JavaScript
 * Handles functionality for the admin sites management page
 */

document.addEventListener('DOMContentLoaded', function() {
    let currentPage = 1;
    let itemsPerPage = 10;
    let totalSites = 0;
    let sites = [];

    function fetchSites(page, search, companyId, status) {
        const params = new URLSearchParams({ page: page, search: search, company_id: companyId, status: status });
        fetch('/admin/api/sites?' + params.toString())
            .then(response => response.json())
            .then(response => {
                if (response.success) {
                    sites = response.sites;
                    totalSites = response.total;
                    renderSites(sites);
                    renderPagination(totalSites, currentPage, itemsPerPage);
                } else {
                    alert('Error fetching sites: ' + response.message);
                    console.error('Error fetching sites:', response);
                }
            })
            .catch(error => {
                alert('Error fetching sites: ' + error);
                console.error('Error fetching sites:', error);
            });
    }

    function renderSites(sites) {
        const siteList = document.getElementById('site-list');
        siteList.innerHTML = '';

        if (sites.length === 0) {
            siteList.innerHTML = '<tr><td colspan="7" class="text-center">No sites found</td></tr>';
            return;
        }

        sites.forEach(site => {
            const row = document.createElement('tr');
            row.innerHTML = `<td>${site.name}</td><td>${site.company_name}</td><td>${site.address || 'N/A'}</td><td>${site.contact_name || 'N/A'}</td><td>${site.tank_count}</td><td><span class="badge ${site.is_active ? 'bg-success' : 'bg-danger'}">${site.is_active ? 'Active' : 'Inactive'}</span></td><td><div class="btn-group btn-group-sm"><button type="button" class="btn btn-primary edit-site-btn" data-site-id="${site.id}" data-bs-toggle="modal" data-bs-target="#editSiteModal"><i class="bi bi-pencil"></i></button><a href="/admin/sites/${site.id}" class="btn btn-info"><i class="bi bi-eye"></i></a><button type="button" class="btn btn-danger delete-site-btn" data-site-id="${site.id}" data-site-name="${site.name}"><i class="bi bi-trash"></i></button></div></td>`;
            siteList.appendChild(row);
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
                fetchSites(currentPage, document.getElementById('site-search').value, document.getElementById('company-filter').value, document.getElementById('status-filter').value);
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
                fetchSites(currentPage, document.getElementById('site-search').value, document.getElementById('company-filter').value, document.getElementById('status-filter').value);
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
                fetchSites(currentPage, document.getElementById('site-search').value, document.getElementById('company-filter').value, document.getElementById('status-filter').value);
            }
        });
        nextLi.appendChild(nextA);
        pagination.appendChild(nextLi);
    }

    fetchSites(currentPage, '', 'all', 'all');

    document.getElementById('site-search').addEventListener('change', function() {
        currentPage = 1;
        fetchSites(currentPage, document.getElementById('site-search').value, document.getElementById('company-filter').value, document.getElementById('status-filter').value);
    });

    document.getElementById('company-filter').addEventListener('change', function() {
        currentPage = 1;
        fetchSites(currentPage, document.getElementById('site-search').value, document.getElementById('company-filter').value, document.getElementById('status-filter').value);
    });

    document.getElementById('status-filter').addEventListener('change', function() {
        currentPage = 1;
        fetchSites(currentPage, document.getElementById('site-search').value, document.getElementById('company-filter').value, document.getElementById('status-filter').value);
    });

    document.getElementById('save-new-site-btn').addEventListener('click', function() {
        const form = document.getElementById('add-site-form');
        fetch('/admin/sites/create', {
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
                document.getElementById('addSiteModal').classList.add('hidden');
                fetchSites(currentPage, document.getElementById('site-search').value, document.getElementById('company-filter').value, document.getElementById('status-filter').value);
                alert(response.message);
                form.reset();
            } else {
                alert('Error adding site: ' + response.message);
            }
        })
        .catch(error => {
            alert('Error adding site: ' + error);
        });
    });

    document.addEventListener('click', function(e) {
        const editBtn = e.target.closest('.edit-site-btn');
        if (editBtn) {
            const siteId = parseInt(editBtn.dataset.siteId);
            const site = sites.find(s => s.id === siteId);

            if (site) {
                document.getElementById('edit-site-id').value = site.id;
                document.getElementById('edit-name').value = site.name;
                document.getElementById('edit-company').value = site.company_id;
                document.getElementById('edit-address').value = site.address;
                document.getElementById('edit-contact-name').value = site.contact_name;
                document.getElementById('edit-contact-email').value = site.contact_email;
                document.getElementById('edit-contact-phone').value = site.contact_phone;
                document.getElementById('edit-is-active').checked = site.is_active;
            } else {
                alert('Error: Site data not found');
            }
        }

        const deleteBtn = e.target.closest('.delete-site-btn');
        if (deleteBtn) {
            const siteId = deleteBtn.dataset.siteId;
            const siteName = deleteBtn.dataset.siteName;
            if (confirm(`Are you sure you want to delete site "${siteName}"?`)) {
                fetch(`/admin/sites/delete/${siteId}`, { method: 'POST', headers: { 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]).content } })
                    .then(response => response.json())
                    .then(response => {
                        if (response.success) {
                            fetchSites(currentPage, document.getElementById('site-search').value, document.getElementById('company-filter').value, document.getElementById('status-filter').value);
                            alert(response.message);
                        } else {
                            alert('Error deleting site: ' + response.message);
                        }
                    })
                    .catch(error => {
                        alert('Error deleting site: ' + error);
                    });
            }
        }
    });

    document.getElementById('update-site-btn').addEventListener('click', function() {
        const siteId = document.getElementById('edit-site-id').value;
        const form = document.getElementById('edit-site-form');
        fetch('/admin/sites/edit/' + siteId, {
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
                document.getElementById('editSiteModal').classList.add('hidden');
                fetchSites(currentPage, document.getElementById('site-search').value, document.getElementById('company-filter').value, document.getElementById('status-filter').value);
                alert(response.message);
            } else {
                alert('Error updating site: ' + response.message);
            }
        })
        .catch(error => {
            alert('Error updating site: ' + error);
        });
    });

    document.getElementById('addSiteModal').addEventListener('hidden.bs.modal', function() {
        document.getElementById('add-site-form').reset();
    });
});
