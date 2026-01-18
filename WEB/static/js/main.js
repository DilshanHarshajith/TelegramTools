// TelegramTools Web UI - Main JavaScript

// Utility function to show notifications
function showNotification(message, type = 'info') {
    // Simple console logging for now
    console.log(`[${type.toUpperCase()}] ${message}`);

    // You can enhance this with toast notifications later
    if (type === 'error') {
        alert(`Error: ${message}`);
    }
}

// Utility function to format timestamps
function formatTimestamp(date) {
    return new Date(date).toLocaleString();
}

// Export for use in other scripts
window.TelegramTools = {
    showNotification,
    formatTimestamp
};
