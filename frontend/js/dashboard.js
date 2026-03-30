/**
 * FaceAuth — Enhanced Dashboard Controller
 * ==========================================
 * Handles all dashboard interactions: overview, profile, sessions,
 * history, audit log, security, face data, and data export.
 * Features: security score, live clock, activity timeline, 
 * password strength, notifications, and responsive sidebar.
 */

let currentPage = 1;
let dashboardData = {};

// ── Section Navigation ───────────────────────────────────────

function showSection(section) {
    document.querySelectorAll('.main-content > section').forEach(s => {
        s.classList.add('hidden');
    });

    const target = document.getElementById(`section-${section}`);
    if (target) target.classList.remove('hidden');

    document.querySelectorAll('.sidebar-link').forEach(l => {
        l.classList.remove('active');
    });
    const activeLink = document.querySelector(`[data-section="${section}"]`);
    if (activeLink) activeLink.classList.add('active');

    // Close mobile sidebar
    document.getElementById('sidebar')?.classList.remove('open');

    // Handle section-specific data & Camera lifecycle
    if (section === 'face') {
        loadFaceStatus();
        // Automatically start camera when navigating to the Face section
        startDashCamera();
    } else if (section === 'voice') {
        // Automatically start voice recording setup when navigating to the Voice section
        if (typeof loadVoiceStatus === 'function') loadVoiceStatus();
    } else {
        // Automatically stop camera and mic when navigating away
        if (typeof stopDashCamera === 'function') {
            stopDashCamera();
        }
        if (window.VoiceManager) window.VoiceManager.stop();
    }

    switch (section) {
        case 'sessions': loadSessions(); break;
        case 'history': loadHistory(1); break;
        case 'profile': loadProfile(); break;
        case 'security': load2FAStatus(); break;
        case 'audit': loadAuditLog(); break;
        case 'vault': loadBiometricVault(); break;
    }
}

function toggleMobileMenu() {
    document.getElementById('sidebar')?.classList.toggle('open');
}


// ── Live Clock ──────────────────────────────────────────────

function updateClock() {
    const el = document.getElementById('live-clock');
    if (!el) return;
    const now = new Date();
    el.textContent = now.toLocaleTimeString('en-US', {
        hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true
    }) + ' · ' + now.toLocaleDateString('en-US', {
        weekday: 'short', month: 'short', day: 'numeric'
    });
}
setInterval(updateClock, 1000);


// ── Security Score ──────────────────────────────────────────

function calculateSecurityScore(profile) {
    let score = 0;
    const checks = {
        password: false,
        face: false,
        voice: false,
        twofa: false,
        email: false,
        recent: true // Default: we assume they reviewed
    };

    // Password set (always true if logged in)
    // Weights: PW(20), Face(30), Voice(20), 2FA(20), Verify(10)
    score = 20; 
    checks.password = true;

    // Face registered
    if (profile.face_registered) {
        checks.face = true;
        score += 30;
    }

    // Voice registered
    if (profile.voice_registered) {
        checks.voice = true;
        score += 20;
    }

    // 2FA enabled
    if (profile.is_2fa_enabled) {
        checks.twofa = true;
        score += 20;
    }

    // Email verified
    if (profile.is_verified) {
        checks.email = true;
        score += 10;
    }

    // Recent activity reviewed
    checks.recent = true;
    score += 0;

    return { score, checks };
}

function renderSecurityScore(score, checks) {
    // Animate main ring
    const circumference = 326.73;
    const offset = circumference - (score / 100) * circumference;
    const ringFill = document.getElementById('score-ring-fill');
    if (ringFill) {
        setTimeout(() => {
            ringFill.style.strokeDashoffset = offset;
            if (score >= 80) ringFill.classList.add('good');
            else if (score >= 50) ringFill.classList.add('medium');
            else ringFill.classList.add('low');
        }, 300);
    }

    // Animate score number
    animateCounter('score-number', score);

    // Update checklist
    const checkItems = {
        'check-password': checks.password,
        'check-face': checks.face,
        'check-voice': checks.voice,
        'check-2fa': checks.twofa,
        'check-email': checks.email,
        'check-recent': checks.recent,
    };

    Object.entries(checkItems).forEach(([id, checked]) => {
        const el = document.getElementById(id);
        if (el) {
            if (checked) {
                el.classList.add('checked');
                el.querySelector('.check-icon').textContent = '✓';
            }
        }
    });

    // Mini sidebar score
    const miniValue = document.getElementById('mini-score-value');
    if (miniValue) miniValue.textContent = score;

    const miniFill = document.getElementById('mini-ring-fill');
    if (miniFill) {
        miniFill.setAttribute('stroke-dasharray', `${score}, 100`);
    }

    const miniStatus = document.getElementById('mini-score-status');
    if (miniStatus) {
        if (score >= 80) miniStatus.textContent = 'Excellent';
        else if (score >= 60) miniStatus.textContent = 'Good';
        else if (score >= 40) miniStatus.textContent = 'Fair';
        else miniStatus.textContent = 'Needs work';
    }
}

function animateCounter(elementId, target) {
    const el = document.getElementById(elementId);
    if (!el) return;
    let current = 0;
    const step = Math.ceil(target / 30);
    const interval = setInterval(() => {
        current += step;
        if (current >= target) {
            current = target;
            clearInterval(interval);
        }
        el.textContent = current;
    }, 30);
}


// ── Security Alerts ─────────────────────────────────────────

function renderSecurityAlerts(profile) {
    const container = document.getElementById('security-alerts');
    if (!container) return;

    const alerts = [];

    if (!profile.is_2fa_enabled) {
        alerts.push({
            type: 'warning',
            icon: '⚠️',
            title: 'Enable Two-Factor Authentication',
            desc: '2FA adds a critical extra layer of security to prevent unauthorized access.',
            action: `<button class="btn btn-sm btn-outline" onclick="showSection('security')">Enable Now</button>`
        });
    }

    if (!profile.face_registered) {
        alerts.push({
            type: 'warning',
            icon: '📸',
            title: 'Register Face Biometric',
            desc: 'Face login provides fast, secure passwordless authentication.',
            action: `<button class="btn btn-sm btn-outline" onclick="showSection('face')">Set Up</button>`
        });
    }

    if (profile.last_password_change) {
        const lastChange = new Date(profile.last_password_change);
        const daysSince = Math.floor((Date.now() - lastChange) / 86400000);
        if (daysSince > 90) {
            alerts.push({
                type: 'danger',
                icon: '🔑',
                title: 'Password Not Changed Recently',
                desc: `It's been ${daysSince} days since your last password change. Consider updating it.`,
                action: `<button class="btn btn-sm btn-outline" onclick="showSection('security')">Change</button>`
            });
        }
    }

    if (profile.is_2fa_enabled && profile.face_registered && profile.is_verified) {
        alerts.push({
            type: 'success',
            icon: '🛡️',
            title: 'Account Well Protected',
            desc: 'Your account has multiple layers of security enabled.',
            action: ''
        });
    }

    if (alerts.length === 0) {
        alerts.push({
            type: 'info',
            icon: 'ℹ️',
            title: 'All Clear',
            desc: 'No security recommendations at this time.',
            action: ''
        });
    }

    container.innerHTML = alerts.map((a, i) => `
        <div class="security-alert-item ${a.type}" style="animation-delay: ${i * 0.1}s">
            <span class="alert-icon">${a.icon}</span>
            <div class="alert-content">
                <strong>${a.title}</strong>
                <p>${a.desc}</p>
            </div>
            <div class="alert-action">${a.action}</div>
        </div>
    `).join('');
}


// ── Activity Timeline ───────────────────────────────────────

function renderActivityTimeline(history) {
    const container = document.getElementById('activity-timeline');
    if (!container) return;

    if (!history || !history.length) {
        container.innerHTML = '<div class="text-center text-muted" style="padding: 24px;">No recent activity</div>';
        return;
    }

    container.innerHTML = history.slice(0, 8).map((h, i) => {
        const isSuccess = h.success;
        const method = h.login_method || 'unknown';
        const methodIcons = { password: '🔑', face: '📸', '2fa': '🔐' };
        const icon = methodIcons[method] || '🔑';

        return `
            <div class="timeline-item" style="animation-delay: ${i * 0.05}s">
                <div class="timeline-icon ${isSuccess ? 'success' : 'failed'}">
                    ${isSuccess ? '✓' : '✗'}
                </div>
                <div class="timeline-content">
                    <div class="timeline-title">
                        ${isSuccess ? 'Successful login' : 'Failed login attempt'}
                        via <span class="badge badge-info" style="font-size: 10px;">${icon} ${method}</span>
                    </div>
                    <div class="timeline-meta">
                        <span>IP: ${h.ip_address || 'Unknown'}</span>
                        <span>${parseUserAgent(h.user_agent)}</span>
                    </div>
                </div>
                <span class="timeline-time">${formatDate(h.timestamp)}</span>
            </div>
        `;
    }).join('');
}


// ── Load Profile ─────────────────────────────────────────────

async function loadProfile() {
    try {
        const data = await AuthManager.apiRequest('/api/user/profile');
        document.getElementById('profile-username').value = data.username || '';
        document.getElementById('profile-email').value = data.email || '';
        document.getElementById('profile-created').value = data.created_at ? new Date(data.created_at).toLocaleDateString('en-US', { year:'numeric', month:'long', day:'numeric' }) : '—';
        document.getElementById('profile-last-pw').value = data.last_password_change ? formatDate(data.last_password_change) : 'Never changed';
        document.getElementById('profile-display-name').textContent = data.username || 'User';
        document.getElementById('profile-avatar-large').textContent = (data.username || 'U')[0].toUpperCase();
        document.getElementById('profile-role-badge').textContent = data.is_admin ? 'Admin' : 'Member';
        document.getElementById('profile-role-badge').className = data.is_admin ? 'badge badge-warning' : 'badge badge-info';
        document.getElementById('profile-member-since').textContent = data.created_at ? 'Member since ' + new Date(data.created_at).toLocaleDateString('en-US', { year:'numeric', month:'long' }) : '';

        // Profile stats
        const days = data.created_at ? Math.floor((Date.now() - new Date(data.created_at)) / 86400000) : 0;
        document.getElementById('prof-stat-days').textContent = days;
        document.getElementById('prof-stat-logins').textContent = dashboardData.totalLogins || 0;
        document.getElementById('prof-stat-sessions').textContent = dashboardData.totalSessions || 0;
    } catch (e) {
        showToast('Failed to load profile: ' + e.message, 'error');
    }
}

async function updateProfile(e) {
    e.preventDefault();
    const btn = document.getElementById('profile-save-btn');
    btn.disabled = true;
    btn.innerHTML = '<div class="spinner" style="width:16px;height:16px;border-width:2px;"></div> Saving...';
    try {
        await AuthManager.apiRequest('/api/user/profile', {
            method: 'PUT',
            body: JSON.stringify({
                username: document.getElementById('profile-username').value,
                email: document.getElementById('profile-email').value,
            }),
        });
        showToast('Profile updated successfully', 'success');
        // Refresh nav
        const username = document.getElementById('profile-username').value;
        updateUserDisplay(username);
    } catch (e) {
        showToast(e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg> Save Changes';
    }
}


// ── Load Sessions ────────────────────────────────────────────

async function loadSessions() {
    try {
        const data = await AuthManager.apiRequest('/api/user/sessions');
        const container = document.getElementById('sessions-list');

        document.getElementById('sessions-total').textContent = data.total || 0;
        document.getElementById('sessions-max').textContent = data.max_allowed || 5;

        if (!data.sessions.length) {
            container.innerHTML = '<div class="card text-center text-muted">No active sessions</div>';
            return;
        }

        container.innerHTML = data.sessions.map((s, i) => {
            const device = parseUserAgent(s.device_info);
            const deviceIcon = getDeviceIcon(s.device_info);
            const isCurrent = i === 0; // First session is most recent

            return `
                <div class="card session-card ${isCurrent ? 'current' : ''}" style="animation: fadeInUp 0.3s ${i * 0.05}s ease-out both;">
                    <div class="session-device-icon">${deviceIcon}</div>
                    <div class="session-details">
                        <div class="session-name">
                            ${device}
                            ${isCurrent ? '<span class="current-badge">Current</span>' : ''}
                        </div>
                        <div class="session-meta">
                            IP: ${s.ip_address || '—'} · Created: ${formatDate(s.created_at)} · Expires: ${formatDate(s.expires_at)}
                        </div>
                    </div>
                    <button class="btn btn-danger btn-sm" onclick="revokeSession('${s.id}')">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                        Revoke
                    </button>
                </div>
            `;
        }).join('');

    } catch (e) {
        showToast('Failed to load sessions: ' + e.message, 'error');
    }
}

function getDeviceIcon(ua) {
    if (!ua) return '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>';
    if (ua.includes('Mobile') || ua.includes('Android') || ua.includes('iPhone'))
        return '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="5" y="2" width="14" height="20" rx="2" ry="2"/><line x1="12" y1="18" x2="12.01" y2="18"/></svg>';
    return '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>';
}

async function revokeSession(sessionId) {
    try {
        await AuthManager.apiRequest(`/api/user/sessions/${sessionId}`, { method: 'DELETE' });
        showToast('Session revoked', 'success');
        loadSessions();
    } catch (e) {
        showToast(e.message, 'error');
    }
}

async function revokeAllSessions() {
    if (!confirm('Revoke all other sessions? You will remain logged in on this device.')) return;
    try {
        const data = await AuthManager.apiRequest('/api/user/sessions');
        let revoked = 0;
        for (let i = 1; i < data.sessions.length; i++) {
            try {
                await AuthManager.apiRequest(`/api/user/sessions/${data.sessions[i].id}`, { method: 'DELETE' });
                revoked++;
            } catch {}
        }
        showToast(`Revoked ${revoked} session(s)`, 'success');
        loadSessions();
    } catch (e) {
        showToast(e.message, 'error');
    }
}


// ── Load Login History ───────────────────────────────────────

async function loadHistory(page = 1) {
    currentPage = page;
    try {
        const data = await AuthManager.apiRequest(`/api/user/login-history?page=${page}&per_page=15`);
        const tbody = document.getElementById('full-history-body');

        document.getElementById('history-total-info').textContent = `Showing ${data.history.length} of ${data.total} entries`;

        if (!data.history.length) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted">No login history</td></tr>';
            return;
        }

        // Apply client-side filters (server doesn't support filtering)
        let filtered = data.history;
        const methodFilter = document.getElementById('history-filter-method')?.value;
        const statusFilter = document.getElementById('history-filter-status')?.value;

        if (methodFilter) {
            filtered = filtered.filter(h => h.login_method === methodFilter);
        }
        if (statusFilter) {
            filtered = filtered.filter(h => statusFilter === 'success' ? h.success : !h.success);
        }

        tbody.innerHTML = filtered.map(h => `
            <tr>
                <td style="white-space: nowrap;">${formatDate(h.timestamp)}</td>
                <td>
                    <span class="badge badge-info">
                        ${{ password: '🔑', face: '📸', '2fa': '🔐' }[h.login_method] || '🔑'} ${h.login_method || '—'}
                    </span>
                </td>
                <td class="font-mono" style="font-size: var(--text-xs);">${h.ip_address || '—'}</td>
                <td>${parseUserAgent(h.user_agent)}</td>
                <td>${h.success ?
                    '<span class="badge badge-success">✓ Success</span>' :
                    '<span class="badge badge-danger">✗ Failed</span>'
                }</td>
            </tr>
        `).join('');

        document.getElementById('history-prev').disabled = page <= 1;
        document.getElementById('history-next').disabled = page >= data.total_pages;
        document.getElementById('history-page-info').textContent = `Page ${page} of ${data.total_pages}`;

    } catch (e) {
        showToast('Failed to load history: ' + e.message, 'error');
    }
}


// ── Audit Log ────────────────────────────────────────────────

async function loadAuditLog() {
    const container = document.getElementById('audit-timeline');
    if (!container) return;

    try {
        const data = await AuthManager.apiRequest('/api/user/login-history?per_page=30');
        if (!data.history.length) {
            container.innerHTML = '<div class="text-center text-muted" style="padding: 24px;">No audit events yet</div>';
            return;
        }

        container.innerHTML = data.history.map((h, i) => {
            const action = h.success ? 'Successful login' : 'Failed login attempt';
            const method = h.login_method || 'unknown';
            const category = h.success ? 'login' : 'security';

            return `
                <div class="audit-item" style="animation: fadeInUp 0.3s ${i * 0.03}s ease-out both;">
                    <div class="audit-dot ${category}"></div>
                    <div class="audit-text">
                        <strong>${action}</strong> via ${method}
                        ${h.ip_address ? ` from <code style="font-size:11px; opacity:0.7;">${h.ip_address}</code>` : ''}
                        ${h.failure_reason ? ` — <span style="color: var(--accent-red);">${h.failure_reason}</span>` : ''}
                    </div>
                    <span class="audit-time">${formatDate(h.timestamp)}</span>
                </div>
            `;
        }).join('');

    } catch (e) {
        container.innerHTML = '<div class="text-center text-muted" style="padding: 24px;">Failed to load audit log</div>';
    }
}


// ── Password Change ──────────────────────────────────────────

async function changePassword(e) {
    e.preventDefault();

    const newPw = document.getElementById('new-password').value;
    const confirmPw = document.getElementById('confirm-password').value;

    if (newPw !== confirmPw) {
        showToast('Passwords do not match', 'error');
        return;
    }

    const btn = document.getElementById('change-pw-btn');
    btn.disabled = true;

    try {
        await AuthManager.apiRequest('/api/user/change-password', {
            method: 'POST',
            body: JSON.stringify({
                current_password: document.getElementById('current-password').value,
                new_password: newPw,
            }),
        });
        showToast('Password changed successfully!', 'success');
        document.getElementById('current-password').value = '';
        document.getElementById('new-password').value = '';
        document.getElementById('confirm-password').value = '';
        resetPasswordStrength();
    } catch (e) {
        showToast(e.message, 'error');
    } finally {
        btn.disabled = false;
    }
}


// ── Password Strength ───────────────────────────────────────

function checkPasswordStrength(password) {
    const bars = document.querySelectorAll('.strength-bar');
    const text = document.getElementById('strength-text');
    const reqs = {
        length: password.length >= 8,
        upper: /[A-Z]/.test(password),
        digit: /\d/.test(password),
        special: /[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]/.test(password),
    };

    // Update requirements
    Object.entries(reqs).forEach(([key, met]) => {
        const el = document.getElementById(`req-${key}`);
        if (el) {
            el.classList.toggle('met', met);
            el.querySelector('.req-icon').textContent = met ? '✓' : '○';
        }
    });

    const score = Object.values(reqs).filter(Boolean).length;
    const levels = ['', 'weak', 'fair', 'good', 'strong'];
    const labels = ['', 'Weak', 'Fair', 'Good', 'Strong'];
    const colors = ['', 'var(--accent-red)', 'var(--accent-orange)', 'var(--accent-cyan)', 'var(--accent-green)'];

    bars.forEach((bar, i) => {
        bar.className = 'strength-bar';
        if (i < score) {
            bar.classList.add('active', levels[score]);
        }
    });

    if (text) {
        text.textContent = password ? labels[score] : '';
        text.style.color = colors[score];
    }
}

function resetPasswordStrength() {
    document.querySelectorAll('.strength-bar').forEach(b => b.className = 'strength-bar');
    const text = document.getElementById('strength-text');
    if (text) text.textContent = '';
    document.querySelectorAll('.req').forEach(r => {
        r.classList.remove('met');
        r.querySelector('.req-icon').textContent = '○';
    });
}

function togglePasswordVis(btn) {
    const input = btn.parentElement.querySelector('.form-input');
    if (input.type === 'password') {
        input.type = 'text';
        btn.textContent = '🙈';
    } else {
        input.type = 'password';
        btn.textContent = '👁️';
    }
}


// ── 2FA ──────────────────────────────────────────────────────

async function load2FAStatus() {
    const user = AuthManager.getUser();
    const badge = document.getElementById('2fa-badge');
    const btn = document.getElementById('2fa-toggle-btn');
    const statVoice = document.getElementById('stat-voice');
    const statVoiceTrend = document.getElementById('stat-voice-trend');
    
    if (statVoice) {
        statVoice.textContent = user.voice_registered ? 'Active' : 'Missing';
        statVoiceTrend.textContent = user.voice_registered ? 'Enrolled' : 'Not Setup';
        statVoiceTrend.className = `stat-trend ${user.voice_registered ? 'up' : 'neutral'}`;
    }

    if (user?.is_2fa_enabled) {
        badge.className = 'badge badge-success';
        badge.textContent = '✓ Enabled';
        btn.textContent = 'Disable 2FA';
        btn.className = 'btn btn-danger';
    } else {
        badge.className = 'badge badge-warning';
        badge.textContent = 'Not Enabled';
        btn.textContent = 'Enable 2FA';
        btn.className = 'btn btn-primary';
    }
}

async function toggle2FA() {
    const user = AuthManager.getUser();

    if (user?.is_2fa_enabled) {
        if (!confirm('Disable two-factor authentication? This will reduce your account security.')) return;
        try {
            await AuthManager.apiRequest('/api/user/disable-2fa', { method: 'POST' });
            user.is_2fa_enabled = false;
            AuthManager.setUser(user);
            load2FAStatus();
            showToast('2FA disabled', 'success');
        } catch (e) { showToast(e.message, 'error'); }
    } else {
        try {
            const data = await AuthManager.apiRequest('/api/user/setup-2fa', { method: 'POST' });
            const setupArea = document.getElementById('2fa-setup-area');
            setupArea.innerHTML = `
                <div class="text-center mb-4">
                    <img src="${data.qr_code}" alt="2FA QR Code" style="width: 200px; border-radius: var(--radius-md); background: white; padding: 8px;">
                    <p class="text-muted mt-2" style="font-size: var(--text-xs);">Scan with your authenticator app</p>
                    <p class="font-mono mt-2" style="font-size: var(--text-xs); word-break: break-all;">Secret: ${data.secret}</p>
                </div>
                <div class="form-group mb-4">
                    <label class="form-label" for="2fa-setup-code">Verification Code</label>
                    <input type="text" class="form-input font-mono" id="2fa-setup-code" maxlength="6" placeholder="000000"
                           style="text-align: center; font-size: var(--text-xl); letter-spacing: 0.3em;">
                </div>
                <button class="btn btn-success btn-full" onclick="confirm2FA('${data.secret}')">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
                    Verify & Enable
                </button>
            `;
            document.getElementById('2fa-toggle-btn').classList.add('hidden');
        } catch (e) {
            showToast(e.message, 'error');
        }
    }
}

async function confirm2FA(secret) {
    const code = document.getElementById('2fa-setup-code').value;
    if (code.length !== 6) {
        showToast('Enter a 6-digit code', 'error');
        return;
    }

    try {
        const data = await AuthManager.apiRequest('/api/user/enable-2fa', {
            method: 'POST',
            body: JSON.stringify({ code, secret }),
        });

        const user = AuthManager.getUser();
        user.is_2fa_enabled = true;
        AuthManager.setUser(user);

        const setupArea = document.getElementById('2fa-setup-area');
        setupArea.innerHTML = `
            <div class="alert alert-warning mb-4">
                <span>⚠️</span>
                <span>Save these recovery codes! They will not be shown again.</span>
            </div>
            <div class="card card-compact font-mono" style="font-size: var(--text-sm);">
                ${data.recovery_codes.map(c => `<div style="padding: 4px 0;">${c}</div>`).join('')}
            </div>
        `;

        document.getElementById('2fa-toggle-btn').classList.remove('hidden');
        load2FAStatus();
        showToast('2FA enabled successfully!', 'success');

    } catch (e) {
        showToast(e.message, 'error');
    }
}


// ── Face Data ────────────────────────────────────────────────

function loadFaceStatus() {
    const user = AuthManager.getUser();
    const badge = document.getElementById('face-status-badge');
    if (badge) {
        if (user?.face_registered) {
            badge.className = 'badge badge-success';
            badge.textContent = '✓ Enrolled';
        } else {
            badge.className = 'badge badge-warning';
            badge.textContent = 'Not Enrolled';
        }
    }
}

function startDashCamera() {
    CameraManager.init('dash-camera', {
        onReady: () => {
            document.getElementById('dash-status-text').textContent = 'Camera ready';
            document.getElementById('dash-status-dot').classList.add('success');
            document.getElementById('face-start-btn').textContent = '🟢 Camera Active';
            document.getElementById('face-start-btn').disabled = true;
        },
        onError: (err) => {
            document.getElementById('dash-status-text').textContent = err;
            document.getElementById('dash-status-dot').classList.add('error');
        },
    });
}

function stopDashCamera() {
    CameraManager.stop();
    document.getElementById('dash-status-text').textContent = 'Camera off';
    document.getElementById('dash-status-dot').className = 'status-dot';
    document.getElementById('face-start-btn').textContent = 'Start Camera';
    document.getElementById('face-start-btn').disabled = false;
}

async function updateFace() {
    if (!CameraManager.isActive()) {
        showToast('Start the camera first', 'warning');
        return;
    }

    const imageData = CameraManager.captureFrame('dash-camera', 'dash-canvas');
    if (!imageData) {
        showToast('Failed to capture frame', 'error');
        return;
    }

    try {
        await AuthManager.apiRequest('/api/face/update', {
            method: 'PUT',
            body: JSON.stringify({ face_image: imageData }),
        });
        showToast('Face data updated successfully!', 'success');
        document.getElementById('dash-face-guide').classList.add('detected');
        
        // Turn off camera on success
        setTimeout(() => {
            document.getElementById('dash-face-guide').classList.remove('detected');
            stopDashCamera();
        }, 1500);
    } catch (e) {
        showToast(e.message, 'error');
    }
}

async function verifyFace() {
    if (!CameraManager.isActive()) {
        showToast('Start the camera first', 'warning');
        return;
    }

    const imageData = CameraManager.captureFrame('dash-camera', 'dash-canvas');
    if (!imageData) {
        showToast('Failed to capture frame', 'error');
        return;
    }

    try {
        const data = await AuthManager.apiRequest('/api/face/verify', {
            method: 'POST',
            body: JSON.stringify({ face_image: imageData }),
        });

        if (data.verified) {
            showToast(`Face verified! Confidence: ${data.confidence}%`, 'success');
            document.getElementById('dash-face-guide').classList.add('detected');
            
            // Turn off camera on success
            setTimeout(() => {
                document.getElementById('dash-face-guide').classList.remove('detected');
                stopDashCamera();
            }, 1500);
        } else {
            showToast('Face verification failed', 'error');
            document.getElementById('dash-face-guide').classList.add('error');
            setTimeout(() => {
                document.getElementById('dash-face-guide').classList.remove('error');
            }, 3000);
        }
    } catch (e) {
        showToast(e.message, 'error');
    }
}

function confirmDeleteFace() {
    if (!confirm('Permanently delete your face biometric data? This cannot be undone.')) return;
    showToast('Face data deletion is not available in this version.', 'info');
}


// ── Data Export ──────────────────────────────────────────────

async function exportData(format) {
    try {
        if (format === 'csv') {
            const token = AuthManager._accessToken;
            const res = await fetch(`/api/user/export-data?format=csv`, {
                headers: { 'Authorization': `Bearer ${token}` },
            });
            const blob = await res.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'faceauth_data.csv';
            a.click();
            URL.revokeObjectURL(url);
            showToast('CSV exported successfully', 'success');
        } else {
            const data = await AuthManager.apiRequest('/api/user/export-data?format=json');
            const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'faceauth_data.json';
            a.click();
            URL.revokeObjectURL(url);
            showToast('JSON exported successfully', 'success');
        }
    } catch (e) {
        showToast('Export failed: ' + e.message, 'error');
    }
}


// ── Notifications ────────────────────────────────────────────

function toggleNotifications() {
    document.getElementById('notification-panel')?.classList.toggle('open');
}

function clearNotifications() {
    document.getElementById('notif-list').innerHTML = '<div class="text-center text-muted" style="padding: 24px;">No notifications</div>';
    document.getElementById('notif-badge').textContent = '0';
}

// Toggle notification panel from bell
document.addEventListener('DOMContentLoaded', () => {
    const notifBtn = document.getElementById('nav-notifications');
    if (notifBtn) notifBtn.addEventListener('click', toggleNotifications);
});


// ── User Display Helpers ─────────────────────────────────────

function updateUserDisplay(username) {
    const initial = (username || 'U')[0].toUpperCase();
    const els = {
        'nav-user': username,
        'nav-avatar': initial,
        'welcome-name': username,
        'sidebar-username': username,
        'sidebar-avatar': initial,
    };
    Object.entries(els).forEach(([id, val]) => {
        const el = document.getElementById(id);
        if (el) el.textContent = val;
    });
}


// ── Dashboard Initialization ─────────────────────────────────

async function initDashboard() {
    // Check auth
    if (!AuthManager.getAccessToken()) {
        window.location.href = '/';
        return;
    }

    // Try to refresh token
    const refreshed = await AuthManager.refreshAccessToken();
    if (!refreshed && !AuthManager._accessToken) {
        window.location.href = '/';
        return;
    }

    // Start clock
    updateClock();

    // Load user profile
    try {
        const profile = await AuthManager.apiRequest('/api/user/profile');
        AuthManager.setUser(profile);

        // Update displays
        updateUserDisplay(profile.username);
        document.getElementById('sidebar-role').textContent = profile.is_admin ? 'Administrator' : 'Member';

        // Stats
        document.getElementById('stat-face').textContent = profile.face_registered ? '✓ Active' : '✗ None';
        document.getElementById('stat-face').style.color = profile.face_registered ? 'var(--accent-green)' : 'var(--accent-red)';
        document.getElementById('stat-face-trend').textContent = profile.face_registered ? 'Active' : 'Set up';
        document.getElementById('stat-face-trend').className = profile.face_registered ? 'stat-trend up' : 'stat-trend neutral';

        document.getElementById('stat-2fa').textContent = profile.is_2fa_enabled ? 'Enabled' : 'Off';
        document.getElementById('stat-2fa').style.color = profile.is_2fa_enabled ? 'var(--accent-green)' : 'var(--accent-orange)';
        document.getElementById('stat-2fa-trend').textContent = profile.is_2fa_enabled ? 'Active' : 'Enable';
        document.getElementById('stat-2fa-trend').className = profile.is_2fa_enabled ? 'stat-trend up' : 'stat-trend neutral';

        const statVoice = document.getElementById('stat-voice');
        const statVoiceTrend = document.getElementById('stat-voice-trend');
        if (statVoice) {
            statVoice.textContent = profile.voice_registered ? 'Active' : 'Missing';
            statVoice.style.color = profile.voice_registered ? 'var(--accent-green)' : 'var(--accent-orange)';
            statVoiceTrend.textContent = profile.voice_registered ? 'Enrolled' : 'Not Set';
            statVoiceTrend.className = `stat-trend ${profile.voice_registered ? 'up' : 'neutral'}`;
        }
        
        // Render voice credential vault state
        const vaultSection = document.querySelector('.face-info-card:has(#current-passphrase-display)');
        if (profile.voice_registered) {
            if (vaultSection) vaultSection.classList.remove('hidden');
            loadVoiceCredentials();
        } else {
            // Hide vault if not registered
            if (vaultSection) vaultSection.classList.add('hidden');
        }

        // Security score
        const { score, checks } = calculateSecurityScore(profile);
        renderSecurityScore(score, checks);
        renderSecurityAlerts(profile);

        // Welcome subtitle with time
        const hour = new Date().getHours();
        const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening';
        document.getElementById('welcome-subtitle').textContent = `${greeting}! Here's your account overview and security summary.`;

    } catch (e) {
        console.error('Failed to load profile:', e);
    }

    // Load sessions count
    try {
        const sessions = await AuthManager.apiRequest('/api/user/sessions');
        dashboardData.totalSessions = sessions.total;
        animateCounter('stat-sessions', sessions.total);
        document.getElementById('stat-sessions-max').textContent = `of ${sessions.max_allowed}`;
        document.getElementById('stat-sessions-max').className = 'stat-trend neutral';
    } catch { /* ignore */ }

    // Load recent history
    try {
        const history = await AuthManager.apiRequest('/api/user/login-history?per_page=8');
        dashboardData.totalLogins = history.total;
        animateCounter('stat-logins', history.total);
        document.getElementById('stat-logins-trend').textContent = `Total`;
        document.getElementById('stat-logins-trend').className = 'stat-trend neutral';

        // Render timeline
        renderActivityTimeline(history.history);

        // Notification count (only failed logins today)
        const today = new Date().toDateString();
        const failedToday = history.history.filter(h => !h.success && new Date(h.timestamp).toDateString() === today).length;
        if (failedToday > 0) {
            document.getElementById('notif-badge').textContent = failedToday;
            document.getElementById('notif-list').innerHTML = `
                <div class="notif-item unread">
                    <span style="font-size: var(--text-lg);">⚠️</span>
                    <div>
                        <strong style="font-size: var(--text-sm);">${failedToday} failed login attempt(s) today</strong>
                        <p class="text-muted" style="font-size: var(--text-xs); margin: 2px 0 0;">Review your login history for details.</p>
                    </div>
                </div>
            `;
        }
    } catch { /* ignore */ }
}

// Run on page load
document.addEventListener('DOMContentLoaded', initDashboard);

// Cleanup camera on leave
window.addEventListener('beforeunload', () => {
    CameraManager.stop();
});

// Close notification panel when clicking outside
document.addEventListener('click', (e) => {
    const panel = document.getElementById('notification-panel');
    const bell = document.getElementById('nav-notifications');
    if (panel?.classList.contains('open') && !panel.contains(e.target) && !bell?.contains(e.target)) {
        panel.classList.remove('open');
    }
});

// ── Voice Biometrics Enrollment ──────────────────────────────────

let voiceSamples = [];

async function loadVoiceStatus() {
    try {
        const user = await AuthManager.apiRequest('/api/user/profile');
        
        const badge = document.getElementById('voice-status-badge');
        if (user.voice_registered) {
            badge.textContent = 'Enrolled';
            badge.className = 'badge badge-success';
        } else {
            badge.textContent = 'Not Enrolled';
            badge.className = 'badge badge-warning';
        }

        voiceSamples = [];
        updateVoiceSampleCount();
    } catch (err) {
        console.error('Failed to load voice status:', err);
    }
}

function updateVoiceSampleCount() {
    const countSpan = document.getElementById('voice-sample-count');
    if (countSpan) countSpan.textContent = voiceSamples.length;
    
    // Update visual dots
    [1, 2, 3].forEach(i => {
        const dot = document.getElementById(`voice-dot-${i}`);
        const path = document.getElementById(`sig-path-${i}`);
        if (dot) {
            dot.classList.toggle('completed', i <= voiceSamples.length);
            dot.classList.toggle('active', i === voiceSamples.length + 1);
        }
        if (path) {
            path.classList.toggle('revealed', i <= voiceSamples.length);
        }
    });
    
    const submitBtn = document.getElementById('voice-submit-btn');
    if (submitBtn) {
        submitBtn.disabled = voiceSamples.length < 3;
    }
    
    const progressText = document.getElementById('voice-enrollment-progress');
    if (voiceSamples.length >= 3) {
        progressText.innerHTML = `<span class="text-success">Ready to Save (3/3 Samples)</span>`;
    }
}

async function startVoiceEnrollment() {
    if (voiceSamples.length >= 3) return; // Max samples reached

    try {
        const hasMic = await window.VoiceManager.requestPermission();
        if (!hasMic) throw new Error("Microphone permission denied.");

        const btn = document.getElementById('voice-record-btn');
        btn.innerHTML = '🔴 Recording...';
        btn.classList.add('recording');
        
        const statusBadge = document.getElementById('voice-signal-status');
        statusBadge.textContent = 'RECORDING';
        statusBadge.classList.add('recording');
        
        document.getElementById('voice-scanning-bar').classList.add('active');
        document.getElementById('voice-enroll-error').classList.add('hidden');

        window.VoiceManager.startRecording();
        window.VoiceManager.startVisualizer('enroll-voice-visualizer');
        
        // Start volume monitoring
        window._volInterval = setInterval(() => {
            const vol = window.VoiceManager.getVolume();
            const fill = document.getElementById('volume-meter-fill');
            if (fill) fill.style.height = `${Math.min(100, vol * 300)}%`;
            
            if (vol > 0.05) {
                statusBadge.textContent = 'SIGNAL OPTIMAL';
                statusBadge.style.color = 'var(--accent-cyan)';
            } else {
                statusBadge.textContent = 'LOW SIGNAL';
                statusBadge.style.color = 'var(--accent-red)';
            }
        }, 50);
    } catch (err) {
        const errDiv = document.getElementById('voice-enroll-error');
        document.getElementById('voice-enroll-error-text').textContent = err.message;
        errDiv.classList.remove('hidden');
    }
}

async function stopVoiceEnrollment() {
    if (voiceSamples.length >= 3) return;
    if (!window.VoiceManager.mediaRecorder || window.VoiceManager.mediaRecorder.state !== 'recording') return;
    
    const btn = document.getElementById('voice-record-btn');
    btn.innerHTML = '🎙️ Hold to Record';
    btn.classList.remove('recording');
    
    const statusBadge = document.getElementById('voice-signal-status');
    statusBadge.textContent = 'PROCESSING';
    statusBadge.classList.remove('recording');
    statusBadge.style.color = '';
    
    document.getElementById('voice-scanning-bar').classList.remove('active');
    
    if (window._volInterval) {
        clearInterval(window._volInterval);
        const fill = document.getElementById('volume-meter-fill');
        if (fill) fill.style.height = '0%';
    }

    try {
        const audioBlob = await window.VoiceManager.stopRecording();
        window.VoiceManager.stopVisualizer();

        // Ensure clip isn't too short (basic check for <0.125s)
        if (audioBlob.size < 1000) {
            throw new Error("Recording too short. Please speak clearly into the microphone.");
        }

        voiceSamples.push(audioBlob);
        updateVoiceSampleCount();

        // Clear canvas gracefully
        const canvas = document.getElementById('enroll-voice-visualizer');
        const ctx = canvas.getContext('2d');
        ctx.fillStyle = 'rgba(10, 11, 14, 0.2)'; 
        ctx.fillRect(0, 0, canvas.width, canvas.height);

    } catch (err) {
        const errDiv = document.getElementById('voice-enroll-error');
        document.getElementById('voice-enroll-error-text').textContent = err.message;
        errDiv.classList.remove('hidden');
    }
}

async function submitVoiceSamples() {
    if (voiceSamples.length < 3) return;

    const btn = document.getElementById('voice-submit-btn');
    const originalText = btn.innerHTML;
    btn.innerHTML = '<div class="spinner"></div> Processing AI Encodings...';
    btn.disabled = true;

    try {
        const phrase = document.getElementById('enroll-phrase').value.trim();
        
        // Passphrase word count validation (min 3 words)
        const words = phrase.split(/\s+/).filter(w => w.length > 0);
        if (words.length < 3) {
            throw new Error("Security phrase must contain at least 3 words for robust matching.");
        }
        
        const formData = new FormData();
        
        voiceSamples.forEach((blob, idx) => {
            formData.append('audios', blob, `sample_${idx}.webm`);
        });
        formData.append('phrase', phrase);

        const response = await fetch('/api/voice/enroll', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${AuthManager.getAccessToken()}`
            },
            body: formData
        });

        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || 'Enrollment failed');

        showToast('Voice Identity successfully enrolled! ✓', 'success');
        voiceSamples = [];
        updateVoiceSampleCount();
        loadVoiceStatus();
        document.getElementById('enroll-phrase').value = '';

    } catch (err) {
        const errDiv = document.getElementById('voice-enroll-error');
        document.getElementById('voice-enroll-error-text').textContent = err.message;
        errDiv.classList.remove('hidden');
    } finally {
        btn.innerHTML = originalText;
    }
}

function resetVoiceEnrollment() {
    if (voiceSamples.length > 0 && !confirm('Clear all recorded voice samples?')) return;
    
    voiceSamples = [];
    updateVoiceSampleCount();
    document.getElementById('voice-enroll-error').classList.add('hidden');
    showToast('Voice samples cleared', 'info');
}

// ── Voice Credentials Management ──────────────────────────────

let currentVoicePhrase = null;

async function loadVoiceCredentials() {
    try {
        const data = await AuthManager.apiRequest('/api/voice/credentials');
        currentVoicePhrase = data.phrase;
        updatePassphraseUI();
    } catch (e) {
        console.error('Failed to load voice credentials');
    }
}

function updatePassphraseUI() {
    const el = document.getElementById('current-passphrase-display');
    if (el) {
        el.textContent = currentVoicePhrase ? '●'.repeat(8) : 'Not Enrolled';
    }
}

let isPhraseVisible = false;
function togglePassphraseVisibility() {
    const el = document.getElementById('current-passphrase-display');
    if (!el || !currentVoicePhrase) return;
    isPhraseVisible = !isPhraseVisible;
    el.textContent = isPhraseVisible ? currentVoicePhrase : '●'.repeat(8);
}

async function updateVoicePassphrase() {
    const input = document.getElementById('update-phrase-input');
    const phrase = input.value.trim();
    
    if (!phrase || phrase.split(' ').length < 3) {
        showToast('Phrase must be at least 3 words', 'error');
        return;
    }
    
    try {
        await AuthManager.apiRequest('/api/voice/credentials', 'PUT', { phrase });
        currentVoicePhrase = phrase;
        input.value = '';
        updatePassphraseUI();
        showToast('Passphrase updated successfully!', 'success');
    } catch (e) {
        showToast('Failed to update passphrase', 'error');
    }
}

function downloadVoiceKey() {
    if (!currentVoicePhrase) {
        showToast('Please enroll voice first', 'error');
        return;
    }
    
    const user = AuthManager.getUser();
    const data = {
        username: user.username,
        biometric_type: "VOICE_ID",
        security_challenge_phrase: currentVoicePhrase,
        generated_at: new Date().toISOString(),
        instruction: "Speak this phrase during Multi-Modal Fusion Login."
    };
    
    const blob = new Blob([JSON.stringify(data, null, 4)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `voice_key_${user.username}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    
    showToast('Voice Key downloaded safely', 'success');
}

async function loadBiometricVault() {
    const faceImg = document.getElementById('vault-face-img');
    const facePlaceholder = document.getElementById('vault-face-placeholder');
    const voicePlayer = document.getElementById('vault-voice-player');
    const voicePlaceholder = document.getElementById('vault-voice-placeholder');
    const audioElement = document.getElementById('vault-audio-element');

    if (!faceImg || !voicePlayer) return;

    // Reset view
    faceImg.classList.add('hidden');
    facePlaceholder.classList.remove('hidden');
    voicePlayer.classList.add('hidden');
    voicePlaceholder.classList.remove('hidden');

    try {
        const data = await AuthManager.apiRequest('/api/auth/biometric-data');

        // Handle Face
        if (data.has_face && data.face_image) {
            faceImg.src = data.face_image;
            faceImg.classList.remove('hidden');
            facePlaceholder.classList.add('hidden');
        } else {
            facePlaceholder.innerHTML = '<p class="text-warning" style="padding: 20px;">⚠️ Face data not enrolled</p>';
        }

        // Handle Voice
        if (data.has_voice && data.voice_sample) {
            audioElement.src = data.voice_sample;
            voicePlayer.classList.remove('hidden');
            voicePlaceholder.classList.add('hidden');
        } else {
            voicePlaceholder.innerHTML = '<p class="text-warning" style="padding: 20px;">⚠️ Voice data not enrolled</p>';
        }

    } catch (e) {
        console.error('Vault error:', e);
        showToast('Failed to load biometric vault: ' + e.message, 'error');
        facePlaceholder.innerHTML = '<p class="text-danger" style="padding: 20px;">❌ Error loading face</p>';
        voicePlaceholder.innerHTML = '<p class="text-danger" style="padding: 20px;">❌ Error loading voice</p>';
    }
}

