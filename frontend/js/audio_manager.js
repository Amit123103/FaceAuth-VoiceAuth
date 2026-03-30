/**
 * AudioManager 
 * Handles WebRTC microphone access, audio recording, and UI waveform visualization.
 */
class AudioManager {
    constructor() {
        this.stream = null;
        this.mediaRecorder = null;
        this.audioChunks = [];
        this.audioContext = null;
        this.analyser = null;
        this.animationFrameId = null;
    }

    async requestPermission() {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            throw new Error("Audio capture is not supported in this browser.");
        }
        
        try {
            this.stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
            return true;
        } catch (err) {
            console.error("Microphone access denied:", err);
            return false;
        }
    }

    startRecording() {
        if (!this.stream) throw new Error("Stream not initialized. Call requestPermission first.");
        
        this.audioChunks = [];
        // Using optimal container for voice, fallback to whatever browser supports
        const options = MediaRecorder.isTypeSupported('audio/webm') ? { mimeType: 'audio/webm' } : {};
        
        this.mediaRecorder = new MediaRecorder(this.stream, options);
        
        this.mediaRecorder.ondataavailable = (event) => {
            if (event.data.size > 0) {
                this.audioChunks.push(event.data);
            }
        };
        
        this.mediaRecorder.start();
    }

    stopRecording() {
        return new Promise((resolve) => {
            if (!this.mediaRecorder) return resolve(null);
            
            this.mediaRecorder.onstop = () => {
                const audioBlob = new Blob(this.audioChunks, { type: this.mediaRecorder.mimeType });
                resolve(audioBlob);
            };
            
            this.mediaRecorder.stop();
        });
    }

    startVisualizer(canvasId) {
        const canvas = document.getElementById(canvasId);
        if (!canvas || !this.stream) return;
        
        const canvasCtx = canvas.getContext('2d');
        
        // Initialize Web Audio API for visualization
        this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
        this.analyser = this.audioContext.createAnalyser();
        
        const source = this.audioContext.createMediaStreamSource(this.stream);
        source.connect(this.analyser);
        
        this.analyser.fftSize = 512;
        const bufferLength = this.analyser.frequencyBinCount;
        const dataArray = new Uint8Array(bufferLength);
        
        const draw = () => {
            this.animationFrameId = requestAnimationFrame(draw);
            
            this.analyser.getByteFrequencyData(dataArray);
            
            canvasCtx.fillStyle = 'rgba(10, 11, 14, 0.3)'; // Slightly more trail
            canvasCtx.fillRect(0, 0, canvas.width, canvas.height);
            
            const barWidth = (canvas.width / bufferLength) * 2.2;
            let barHeight;
            let x = 0;
            
            // Center line
            const centerY = canvas.height / 2;

            canvasCtx.shadowBlur = 15;
            canvasCtx.shadowColor = 'rgba(0, 210, 255, 0.5)';
            
            for (let i = 0; i < bufferLength; i++) {
                barHeight = (dataArray[i] / 255) * (canvas.height * 0.85);
                
                // Color gradient (Royal Blue -> Cyan)
                const hue = 200 + (barHeight / canvas.height) * 40;
                canvasCtx.fillStyle = `hsl(${hue}, 100%, 65%)`;
                
                // Symmetric bars (Up and Down from center)
                canvasCtx.fillRect(x, centerY - barHeight / 2, barWidth - 1, barHeight);
                
                x += barWidth;
            }
            
            canvasCtx.shadowBlur = 0; // Reset for next frame
        };
        
        draw();
    }

    /**
     * Get real-time RMS volume (0.0 to 1.0)
     */
    getVolume() {
        if (!this.analyser) return 0;
        const dataArray = new Uint8Array(this.analyser.frequencyBinCount);
        this.analyser.getByteTimeDomainData(dataArray);
        
        let sum = 0;
        for (let i = 0; i < dataArray.length; i++) {
            const val = (dataArray[i] - 128) / 128;
            sum += val * val;
        }
        return Math.sqrt(sum / dataArray.length);
    }

    stopVisualizer() {
        if (this.animationFrameId) cancelAnimationFrame(this.animationFrameId);
        // Clean up audio context
        if (this.audioContext && this.audioContext.state !== 'closed') {
            this.audioContext.close();
        }
    }

    stop() {
        this.stopVisualizer();
        if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
            this.mediaRecorder.stop();
        }
        if (this.stream) {
            this.stream.getTracks().forEach(track => track.stop());
            this.stream = null;
        }
    }
}

window.VoiceManager = new AudioManager();
