/**
 * FaceAuth — Client-Side Face Detection
 * =======================================
 * Lightweight client-side face detection for UI guidance.
 * Uses the canvas overlay to draw face position hints.
 * (Server-side face_recognition handles actual matching.)
 */

const FaceDetectionUI = {
    _interval: null,

    /**
     * Start periodic face detection quality checks.
     * Sends frames to the backend quality-check endpoint
     * and updates the UI with results.
     * 
     * @param {string} videoId - Camera video element ID  
     * @param {string} canvasId - Overlay canvas element ID
     * @param {string} guideId - Face guide element ID
     * @param {string} qualityFillId - Quality meter fill element ID
     * @param {string} qualityTextId - Quality text element ID
     * @param {number} intervalMs - Check interval in milliseconds
     */
    start(videoId, canvasId, guideId, qualityFillId, qualityTextId, intervalMs = 2000) {
        this.stop(); // Clear any existing interval

        this._interval = setInterval(async () => {
            const imageData = CameraManager.captureFrame(videoId, canvasId);
            if (!imageData) return;

            try {
                const response = await fetch('/api/face/quality-check', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ face_image: imageData }),
                });

                if (!response.ok) return;
                const data = await response.json();

                this._updateUI(data, guideId, qualityFillId, qualityTextId);
            } catch {
                // Silently ignore errors during periodic checks
            }
        }, intervalMs);
    },

    /**
     * Update UI elements based on quality check results.
     */
    _updateUI(data, guideId, qualityFillId, qualityTextId) {
        const guide = document.getElementById(guideId);
        const fill = document.getElementById(qualityFillId);
        const text = document.getElementById(qualityTextId);

        if (!guide) return;

        if (data.face_detected && data.quality) {
            const score = data.quality.overall_score;

            // Update face guide
            guide.classList.remove('error');
            guide.classList.toggle('detected', score >= 85);

            // Extra visual feedback for the circular guide
            if (score >= 85) {
                guide.style.borderColor = 'var(--accent-blue)';
            } else {
                guide.style.borderColor = '';
            }

            // Update quality meter
            if (fill) {
                fill.style.width = `${score}%`;
                fill.className = `quality-fill ${score >= 85 ? 'high' : score >= 60 ? 'medium' : 'low'}`;
            }

            // Update quality text
            if (text) {
                text.textContent = `Face quality: ${score}%`;
                text.style.color = score >= 85 ? 'var(--accent-green)' : score >= 60 ? 'var(--accent-orange)' : 'var(--accent-red)';
            }
        } else {
            // No face detected
            guide.classList.remove('detected');
            guide.classList.add('error');

            if (fill) {
                fill.style.width = '0%';
            }
            if (text) {
                text.textContent = 'Face quality: No face detected';
                text.style.color = 'var(--text-muted)';
            }
        }
    },

    /**
     * Stop periodic face detection.
     */
    stop() {
        if (this._interval) {
            clearInterval(this._interval);
            this._interval = null;
        }
    },

    /**
     * Draw face bounding box on the canvas overlay.
     * @param {string} canvasId - Canvas element ID
     * @param {object} faceLocation - {top, right, bottom, left}
     * @param {string} color - Border color
     */
    drawFaceBox(canvasId, faceLocation, color = '#00d2ff') {
        const canvas = document.getElementById(canvasId);
        if (!canvas) return;

        const ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        const { top, right, bottom, left } = faceLocation;
        const width = right - left;
        const height = bottom - top;

        // Draw rounded rectangle
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.setLineDash([5, 5]);
        ctx.beginPath();
        ctx.roundRect(left, top, width, height, 8);
        ctx.stroke();
        ctx.setLineDash([]);

        // Label
        ctx.fillStyle = color;
        ctx.font = '12px Inter, sans-serif';
        ctx.fillText('Face Detected', left, top - 8);
    },
};
