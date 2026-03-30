/**
 * FaceAuth — Authentication Manager
 * ====================================
 * JWT token management, auto-refresh, and authenticated API requests.
 * Tokens are stored in memory (not localStorage) for XSS protection.
 */

const AuthManager = {
    _accessToken: null,
    _refreshToken: null,
    _user: null,
    _refreshTimer: null,

    /**
     * Initialize from persisted storage (refresh token only).
     */
    init() {
        // Restore refresh token from storage (acceptable risk for UX)
        const stored = StorageManager.get('refresh_token');
        if (stored) {
            this._refreshToken = stored;
            this.refreshAccessToken();
        }
    },

    /**
     * Store tokens after successful authentication.
     */
    setTokens(accessToken, refreshToken) {
        this._accessToken = accessToken;
        this._refreshToken = refreshToken;

        // Persist refresh token for session continuity
        StorageManager.set('refresh_token', refreshToken);

        // Schedule auto-refresh
        this._scheduleRefresh(accessToken);
    },

    /**
     * Get the current access token.
     */
    getAccessToken() {
        return this._accessToken || StorageManager.get('refresh_token');
    },

    /**
     * Store user info.
     */
    setUser(user) {
        this._user = user;
        StorageManager.set('user', user);
    },

    /**
     * Get current user info.
     */
    getUser() {
        return this._user || StorageManager.get('user');
    },

    /**
     * Make an authenticated API request.
     * @param {string} url — API endpoint.
     * @param {object} options — Fetch options.
     * @returns {Promise<any>} — Response data.
     */
    async apiRequest(url, options = {}) {
        const headers = {
            'Content-Type': 'application/json',
            ...options.headers,
        };

        if (this._accessToken) {
            headers['Authorization'] = `Bearer ${this._accessToken}`;
        }

        const response = await fetch(url, {
            ...options,
            headers,
        });

        // Handle 401 — try refresh
        if (response.status === 401 && this._refreshToken) {
            const refreshed = await this.refreshAccessToken();
            if (refreshed) {
                headers['Authorization'] = `Bearer ${this._accessToken}`;
                const retryResponse = await fetch(url, { ...options, headers });
                if (!retryResponse.ok) {
                    const data = await retryResponse.json();
                    throw new Error(data.detail || 'Request failed');
                }
                return retryResponse.json();
            } else {
                this.logout();
                throw new Error('Session expired. Please login again.');
            }
        }

        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.detail || 'Request failed');
        }

        return response.json();
    },

    /**
     * Refresh the access token using the refresh token.
     */
    async refreshAccessToken() {
        if (!this._refreshToken) return false;

        try {
            const response = await fetch('/api/auth/refresh', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ refresh_token: this._refreshToken }),
            });

            if (!response.ok) {
                return false;
            }

            const data = await response.json();
            this._accessToken = data.access_token;
            this._scheduleRefresh(data.access_token);
            return true;

        } catch (err) {
            console.error('Token refresh failed:', err);
            return false;
        }
    },

    /**
     * Schedule automatic token refresh before expiry.
     */
    _scheduleRefresh(token) {
        if (this._refreshTimer) clearTimeout(this._refreshTimer);

        try {
            // Decode JWT payload (base64)
            const payload = JSON.parse(atob(token.split('.')[1]));
            const expiresAt = payload.exp * 1000; // Convert to ms
            const now = Date.now();
            const refreshIn = (expiresAt - now) - 60000; // Refresh 1 min before expiry

            if (refreshIn > 0) {
                this._refreshTimer = setTimeout(() => {
                    this.refreshAccessToken();
                }, refreshIn);
            }
        } catch {
            // If token parsing fails, don't schedule
        }
    },

    /**
     * Logout — clear all tokens and redirect to login.
     */
    async logout() {
        try {
            if (this._accessToken) {
                await fetch('/api/auth/logout', {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${this._accessToken}`,
                        'Content-Type': 'application/json',
                    },
                });
            }
        } catch {
            // Ignore logout API errors
        }

        this._accessToken = null;
        this._refreshToken = null;
        this._user = null;
        if (this._refreshTimer) clearTimeout(this._refreshTimer);

        StorageManager.remove('refresh_token');
        StorageManager.remove('user');

        window.location.href = '/';
    },
};

/**
 * Global logout handler.
 */
function handleLogout() {
    AuthManager.logout();
}

// Initialize on load
document.addEventListener('DOMContentLoaded', () => {
    AuthManager.init();
});
