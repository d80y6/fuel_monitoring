/**
 * Calibration.js - Tank Calibration
 * 
 * Handles the tank calibration functionality
 */

// Update measurements from socket
function updateMeasurements(data) {
    // Update current measurements
    document.getElementById('pressure-value').textContent = data.pressure.toFixed(4) + ' bar';
    document.getElementById('level-value').textContent = data.level.toFixed(3) + ' m';
    document.getElementById('volume-value').textContent = data.volume.toFixed(1) + ' L';
}

// Initialize with socket connection
document.addEventListener('DOMContentLoaded', function() {
    // Socket connection is handled in socket.js
    
    // Add event listener for calibration form
    const calibrationForm = document.querySelector('form');
    if (calibrationForm) {
        calibrationForm.addEventListener('submit', function(event) {
            // Form submission is handled by the server
            // No need to prevent default
            
            // Disable the button during submission to prevent double-clicks
            const calibrateBtn = document.getElementById('calibrate-btn');
            if (calibrateBtn) {
                calibrateBtn.disabled = true;
                calibrateBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Calibrating...';
                
                // Re-enable after a short delay (in case the form submission fails)
                setTimeout(() => {
                    calibrateBtn.disabled = false;
                    calibrateBtn.innerHTML = '<i class="bi bi-tools"></i> Calibrate';
                }, 3000);
            }
        });
    }
    
    // If socket is available, set up event listener for measurements
    if (typeof socket !== 'undefined' && socket) {
        socket.on('measurements', function(data) {
            updateMeasurements(data);
        });
    }
});
