/**
 * FaceAuth — Main Application Logic
 * ====================================
 * Global initialization, service worker registration,
 * and shared application state.
 */

const App = {
    version: '1.0.0',
    name: 'FaceAuth',

    /**
     * Check if the application backend is reachable.
     */
    async healthCheck() {
        try {
            const response = await fetch('/api/health');
            const data = await response.json();
            return data.status === 'healthy';
        } catch {
            return false;
        }
    },

    /**
     * Check online/offline status and show notification.
     */
    initConnectivityMonitor() {
        window.addEventListener('online', () => {
            showToast('Connection restored', 'success');
        });

        window.addEventListener('offline', () => {
            showToast('You are offline. Some features may be unavailable.', 'warning');
        });
    },

    /**
     * Initialize keyboard shortcuts.
     */
    initKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            // Escape to close modals
            if (e.key === 'Escape') {
                const modals = document.querySelectorAll('.modal-overlay.active');
                modals.forEach(m => m.classList.remove('active'));
            }
        });
    },
};

// Global initialization
document.addEventListener('DOMContentLoaded', () => {
    App.initConnectivityMonitor();
    App.initKeyboardShortcuts();
});
