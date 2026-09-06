/**
 * Socket.js - WebSocket Communication
 * 
 * Handles WebSocket communication with the server
 */

// Socket.IO connection management
let socket;
let isConnected = false;

// DOM elements
const connectBtn = document.getElementById('connect-btn');
const disconnectBtn = document.getElementById('disconnect-btn');
const connectionStatus = document.getElementById('connection-status');

// Initialize socket connection
function initSocket() {
    // Create socket connection with transport options
    socket = io({
        transports: ['websocket', 'polling'],  // Allow fallback to polling
        reconnectionAttempts: 5,
        reconnectionDelay: 1000
    });
    
    // Connection event
    socket.on('connect', function() {
        isConnected = true;
        updateConnectionStatus(true);
        //console.log('Connected to server');
    });
    
    // Disconnection event
    socket.on('disconnect', function() {
        isConnected = false;
        updateConnectionStatus(false);
        //console.log('Disconnected from server');
    });
    
    // Error event
    socket.on('connect_error', function(error) {
        isConnected = false;
        updateConnectionStatus(false);
        console.error('Connection error:', error);
        // Log more detailed error information
        if (error.description) {
            console.error('Error details:', error.description);
        }
    });
    
    // Measurements event
    socket.on('measurements', function(data) {
        // Dispatch custom event with measurement data
        const event = new CustomEvent('new-measurements', { detail: data });
        document.dispatchEvent(event);
    });
}

// Update connection status UI
function updateConnectionStatus(connected) {
    if (connected) {
        connectionStatus.innerHTML = '<i class="bi bi-circle-fill text-success"></i> Connected';
        connectBtn.disabled = true;
        disconnectBtn.disabled = false;
    } else {
        connectionStatus.innerHTML = '<i class="bi bi-circle-fill text-danger"></i> Disconnected';
        connectBtn.disabled = false;
        disconnectBtn.disabled = true;
    }
}

// Connect button click handler
connectBtn.addEventListener('click', function() {
    if (!isConnected) {
        if (!socket) {
            initSocket();
        } else {
            socket.connect();
        }
    }
});

// Disconnect button click handler
disconnectBtn.addEventListener('click', function() {
    if (isConnected && socket) {
        socket.disconnect();
    }
});

// Reset statistics button click handler (if present)
const resetStatsBtn = document.getElementById('reset-stats-btn');
if (resetStatsBtn) {
    resetStatsBtn.addEventListener('click', function() {
        if (isConnected && socket) {
            socket.emit('reset_statistics');
            //console.log('Statistics reset requested');
        }
    });
}

// Initialize socket on page load
document.addEventListener('DOMContentLoaded', function() {
    initSocket();
});
