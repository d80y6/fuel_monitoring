/**
 * Main Application JavaScript
 * Handles common functionality across the application
 */

document.addEventListener('DOMContentLoaded', function() {
    // Sidebar toggle functionality
    const sidebarToggle = document.getElementById('sidebar-toggle');
    const sidebar = document.getElementById('sidebar');
    const mainContent = document.getElementById('main-content');
    
    if (sidebarToggle && sidebar && mainContent) {
        sidebarToggle.addEventListener('click', function() {
            sidebar.classList.toggle('show');
            sidebarToggle.classList.toggle('show');
            mainContent.classList.toggle('expanded');
        });
    }
    
    // Auto-dismiss alerts after 5 seconds
    setTimeout(function() {
        document.querySelectorAll('[data-dismiss="alert"]').forEach(function(alert) {
            alert.style.transition = 'opacity 0.3s';
            alert.style.opacity = '0';
            setTimeout(function() { alert.remove(); }, 300);
        });
    }, 5000);
    
    // Handle form validation
    const forms = document.querySelectorAll('.needs-validation');
    Array.from(forms).forEach(function(form) {
        form.addEventListener('submit', function(event) {
            if (!form.checkValidity()) {
                event.preventDefault();
                event.stopPropagation();
            }
            form.classList.add('was-validated');
        }, false);
    });
    
    // Handle confirmation dialogs
    document.querySelectorAll('[data-confirm]').forEach(function(element) {
        element.addEventListener('click', function(event) {
            const message = this.getAttribute('data-confirm');
            if (!confirm(message)) {
                event.preventDefault();
            }
        });
    });
    
    // Handle loading overlay
    function showLoading(message = 'Loading...') {
        const overlay = document.createElement('div');
        overlay.className = 'fixed inset-0 z-50 flex items-center justify-center bg-black/50';
        overlay.innerHTML = `
            <div class="bg-white rounded-xl p-6 shadow-xl text-center">
                <div class="animate-spin h-8 w-8 border-4 border-primary-500 border-t-transparent rounded-full mx-auto mb-3"></div>
                <p class="text-sm text-gray-700">${message}</p>
            </div>
        `;
        document.body.appendChild(overlay);
    }
    
    function hideLoading() {
        const overlay = document.querySelector('.fixed.inset-0.z-50');
        if (overlay) overlay.remove();
    }
    
    window.showLoading = showLoading;
    window.hideLoading = hideLoading;
    
    document.querySelectorAll('form[data-loading]').forEach(function(form) {
        form.addEventListener('submit', function() {
            showLoading(this.getAttribute('data-loading') || 'Processing...');
        });
    });
    
    // Format dates
    document.querySelectorAll('[data-format-date]').forEach(function(element) {
        const timestamp = element.textContent.trim();
        if (timestamp) {
            try {
                const date = new Date(timestamp);
                const format = element.getAttribute('data-format-date');
                if (format === 'relative') {
                    const now = new Date();
                    const diff = Math.round((now - date) / 1000);
                    if (diff < 60) element.textContent = 'just now';
                    else if (diff < 3600) element.textContent = `${Math.round(diff/60)}m ago`;
                    else if (diff < 86400) element.textContent = `${Math.round(diff/3600)}h ago`;
                    else element.textContent = `${Math.round(diff/86400)}d ago`;
                } else {
                    element.textContent = date.toLocaleString();
                }
            } catch (e) { console.error('Date format error:', e); }
        }
    });
    
    // Format numbers
    document.querySelectorAll('[data-format-number]').forEach(function(element) {
        const number = parseFloat(element.textContent.trim());
        if (!isNaN(number)) {
            const decimals = parseInt(element.getAttribute('data-decimals') || '2');
            const format = element.getAttribute('data-format-number');
            if (format === 'percent') element.textContent = `${number.toFixed(decimals)}%`;
            else element.textContent = number.toFixed(decimals);
        }
    });
});
