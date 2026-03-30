/**
 * FaceAuth — Utility Functions
 * =============================
 * Shared helper functions for the frontend.
 */

/**
 * Show a toast notification.
 * @param {string} message — The message to display.
 * @param {'success'|'error'|'info'|'warning'} type — Toast type.
 * @param {number} duration — Duration in milliseconds.
 */
function showToast(message, type = 'info', duration = 4000) {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const icons = {
        success: '✅',
        error: '❌',
        info: 'ℹ️',
        warning: '⚠️',
    };

    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.innerHTML = `
        <span>${icons[type] || 'ℹ️'}</span>
        <span style="flex: 1;">${message}</span>
    `;

    // Color accent based on type
    const colors = {
        success: 'var(--accent-green)',
        error: 'var(--accent-red)',
        info: 'var(--accent-cyan)',
        warning: 'var(--accent-orange)',
    };
    toast.style.borderLeft = `3px solid ${colors[type] || colors.info}`;

    container.appendChild(toast);

    // Auto-remove
    setTimeout(() => {
        toast.classList.add('hiding');
        setTimeout(() => toast.remove(), 300);
    }, duration);
}


/**
 * Format an ISO date string to a readable format.
 * @param {string} isoString — ISO 8601 date string.
 * @returns {string} Formatted date.
 */
function formatDate(isoString) {
    if (!isoString) return '—';
    try {
        const date = new Date(isoString);
        const now = new Date();
        const diffMs = now - date;
        const diffMins = Math.floor(diffMs / 60000);
        const diffHours = Math.floor(diffMs / 3600000);
        const diffDays = Math.floor(diffMs / 86400000);

        if (diffMins < 1) return 'Just now';
        if (diffMins < 60) return `${diffMins}m ago`;
        if (diffHours < 24) return `${diffHours}h ago`;
        if (diffDays < 7) return `${diffDays}d ago`;

        return date.toLocaleDateString('en-US', {
            month: 'short',
            day: 'numeric',
            year: date.getFullYear() !== now.getFullYear() ? 'numeric' : undefined,
            hour: '2-digit',
            minute: '2-digit',
        });
    } catch {
        return isoString;
    }
}


/**
 * Truncate a string to a maximum length.
 * @param {string} str — Input string.
 * @param {number} maxLen — Maximum length.
 * @returns {string} Truncated string with ellipsis.
 */
function truncate(str, maxLen = 50) {
    if (!str) return '—';
    return str.length > maxLen ? str.substring(0, maxLen) + '…' : str;
}


/**
 * Debounce a function call.
 * @param {Function} func — Function to debounce.
 * @param {number} wait — Wait time in ms.
 * @returns {Function} Debounced function.
 */
function debounce(func, wait = 300) {
    let timeout;
    return function (...args) {
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(this, args), wait);
    };
}


/**
 * Parse user agent string into a readable device description.
 * @param {string} ua — User agent string.
 * @returns {string} Simplified device description.
 */
function parseUserAgent(ua) {
    if (!ua) return 'Unknown device';

    if (ua.includes('Chrome') && !ua.includes('Edg')) return 'Chrome';
    if (ua.includes('Firefox')) return 'Firefox';
    if (ua.includes('Safari') && !ua.includes('Chrome')) return 'Safari';
    if (ua.includes('Edg')) return 'Edge';
    if (ua.includes('Opera') || ua.includes('OPR')) return 'Opera';

    return truncate(ua, 30);
}


/**
 * Generate a simple device fingerprint based on browser info.
 * Not cryptographically secure — used for session identification.
 * @returns {string} Fingerprint hash.
 */
function getDeviceFingerprint() {
    const data = [
        navigator.userAgent,
        navigator.language,
        screen.width + 'x' + screen.height,
        new Date().getTimezoneOffset(),
    ].join('|');

    // Simple hash
    let hash = 0;
    for (let i = 0; i < data.length; i++) {
        const char = data.charCodeAt(i);
        hash = ((hash << 5) - hash) + char;
        hash |= 0;
    }
    return Math.abs(hash).toString(16).padStart(8, '0');
}
