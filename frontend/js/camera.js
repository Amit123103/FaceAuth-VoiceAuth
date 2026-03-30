/**
 * FaceAuth — WebRTC Camera Manager
 * ==================================
 * Handles camera initialization, frame capture, and lifecycle.
 */

const CameraManager = {
    _stream: null,
    _videoElement: null,

    /**
     * Initialize camera stream and attach to a video element.
     * @param {string} videoId — ID of the <video> element.
     * @param {object} callbacks — { onReady, onError }
     */
    async init(videoId, callbacks = {}) {
        const video = document.getElementById(videoId);
        if (!video) {
            console.error(`Video element #${videoId} not found`);
            callbacks.onError?.('Video element not found');
            return;
        }

        this._videoElement = video;

        // Camera constraints — prefer front-facing camera
        const constraints = {
            video: {
                facingMode: 'user',
                width: { ideal: 640 },
                height: { ideal: 480 },
            },
            audio: false,
        };

        try {
            // Request camera access
            const stream = await navigator.mediaDevices.getUserMedia(constraints);
            this._stream = stream;
            video.srcObject = stream;

            // Wait for video to be ready
            await new Promise((resolve) => {
                video.onloadedmetadata = () => {
                    video.play();
                    resolve();
                };
            });

            console.log('Camera initialized successfully');
            callbacks.onReady?.();

        } catch (err) {
            console.error('Camera initialization failed:', err);

            let message = 'Camera access denied';
            if (err.name === 'NotAllowedError') {
                message = 'Camera permission denied. Please allow camera access.';
            } else if (err.name === 'NotFoundError') {
                message = 'No camera found on this device.';
            } else if (err.name === 'NotReadableError') {
                message = 'Camera is in use by another application.';
            }

            callbacks.onError?.(message);
        }
    },

    /**
     * Capture the current frame from the video element and return as base64.
     * 
     * @param {string} videoId - The video element ID
     * @param {string} canvasId - The canvas element ID
     * @param {number} maxWidth - Optional width for downsizing (increases performance)
     * @returns {string|null} - Base64 encoded JPEG image
     */
    captureFrame(videoId, canvasId, maxWidth = null) {
        const video = document.getElementById(videoId);
        const canvas = document.getElementById(canvasId);
        if (!video || !canvas || !video.videoWidth) return null;

        const ctx = canvas.getContext('2d');
        
        let width = video.videoWidth;
        let height = video.videoHeight;

        // Downscale if requested (improves server-side detection speed)
        if (maxWidth && width > maxWidth) {
            height = (maxWidth / width) * height;
            width = maxWidth;
        }

        canvas.width = width;
        canvas.height = height;

        // Flip horizontally to match the mirrored video
        ctx.translate(width, 0);
        ctx.scale(-1, 1);
        ctx.drawImage(video, 0, 0, width, height);
        ctx.setTransform(1, 0, 0, 1, 0, 0);

        return canvas.toDataURL('image/jpeg', 0.85);
    },

    /**
     * Capture multiple frames over a time period (for liveness detection).
     * @param {string} videoId — Video element ID.
     * @param {string} canvasId — Canvas element ID.
     * @param {number} count — Number of frames to capture.
     * @param {number} intervalMs — Milliseconds between captures.
     * @returns {Promise<string[]>} Array of base64 image strings.
     */
    captureMultipleFrames(videoId, canvasId, count = 5, intervalMs = 500) {
        return new Promise((resolve) => {
            const frames = [];
            let captured = 0;

            const interval = setInterval(() => {
                const frame = this.captureFrame(videoId, canvasId);
                if (frame) {
                    frames.push(frame);
                    captured++;
                }

                if (captured >= count) {
                    clearInterval(interval);
                    resolve(frames);
                }
            }, intervalMs);
        });
    },

    /**
     * Stop the camera stream and release resources.
     */
    stop() {
        if (this._stream) {
            this._stream.getTracks().forEach(track => track.stop());
            this._stream = null;
        }
        if (this._videoElement) {
            this._videoElement.srcObject = null;
            this._videoElement = null;
        }
    },

    /**
     * Check if camera is currently active.
     */
    isActive() {
        return this._stream !== null && this._stream.active;
    },
};
