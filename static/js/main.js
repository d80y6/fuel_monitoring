/**
 * Main Application JavaScript
 * Handles common functionality across the application
 */

document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
    
    // Initialize popovers
    var popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    var popoverList = popoverTriggerList.map(function (popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl);
    });
    
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
        const alerts = document.querySelectorAll('.alert-dismissible');
        alerts.forEach(function(alert) {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
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
        overlay.className = 'loading-overlay';
        overlay.innerHTML = `
            <div class="loading-content">
                <div class="loading-spinner"></div>
                <div class="loading-text">${message}</div>
            </div>
        `;
        document.body.appendChild(overlay);
    }
    
    function hideLoading() {
        const overlay = document.querySelector('.loading-overlay');
        if (overlay) {
            overlay.remove();
        }
    }
    
    // Expose loading functions globally
    window.showLoading = showLoading;
    window.hideLoading = hideLoading;
    
    // Add loading indicator to forms with data-loading attribute
    document.querySelectorAll('form[data-loading]').forEach(function(form) {
        form.addEventListener('submit', function() {
            const message = this.getAttribute('data-loading') || 'Processing...';
            showLoading(message);
        });
    });
    
    // Add loading indicator to links with data-loading attribute
    document.querySelectorAll('a[data-loading]').forEach(function(link) {
        link.addEventListener('click', function(event) {
            // Skip if the link has target="_blank" or if the user is holding Ctrl/Cmd
            if (this.target === '_blank' || event.ctrlKey || event.metaKey) {
                return;
            }
            
            const message = this.getAttribute('data-loading') || 'Loading...';
            showLoading(message);
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
                    element.textContent = getRelativeTimeString(date);
                } else {
                    element.textContent = formatDate(date, format);
                }
            } catch (error) {
                console.error('Error formatting date:', error);
            }
        }
    });
    
    // Format numbers
    document.querySelectorAll('[data-format-number]').forEach(function(element) {
        const number = parseFloat(element.textContent.trim());
        if (!isNaN(number)) {
            try {
                const format = element.getAttribute('data-format-number');
                const decimals = parseInt(element.getAttribute('data-decimals') || '2');
                
                if (format === 'percent') {
                    element.textContent = `${number.toFixed(decimals)}%`;
                } else if (format === 'currency') {
                    const currency = element.getAttribute('data-currency') || '$';
                    element.textContent = `${currency}${number.toFixed(decimals)}`;
                } else {
                    element.textContent = number.toFixed(decimals);
                }
            } catch (error) {
                console.error('Error formatting number:', error);
            }
        }
    });
    
    // Helper function to format date
    function formatDate(date, format) {
        if (format === 'short') {
            return date.toLocaleDateString();
        } else if (format === 'long') {
            return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
        } else {
            return date.toLocaleString();
        }
    }
    
    // Helper function to get relative time string
    function getRelativeTimeString(date) {
        const now = new Date();
        const diffMs = now - date;
        const diffSec = Math.round(diffMs / 1000);
        const diffMin = Math.round(diffSec / 60);
        const diffHour = Math.round(diffMin / 60);
        const diffDay = Math.round(diffHour / 24);
        
        if (diffSec < 60) {
            return 'just now';
        } else if (diffMin < 60) {
            return `${diffMin} minute${diffMin > 1 ? 's' : ''} ago`;
        } else if (diffHour < 24) {
            return `${diffHour} hour${diffHour > 1 ? 's' : ''} ago`;
        } else if (diffDay < 7) {
            return `${diffDay} day${diffDay > 1 ? 's' : ''} ago`;
        } else {
            return formatDate(date, 'short');
        }
    }
});
