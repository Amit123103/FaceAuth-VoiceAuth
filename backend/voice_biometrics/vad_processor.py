"""
Voice Activity Detection & Preprocessing Module
===============================================
Normalizes volume, removes trailing silence, and trims noise.
"""
import io
import logging
import numpy as np

logger = logging.getLogger(__name__)

try:
    import librosa
    import soundfile as sf
    LIBROSA_AVAILABLE = True
except ImportError:
    logger.warning("Librosa unavailable. VAD will skip advanced reduction.")
    LIBROSA_AVAILABLE = False


def preprocess_audio(wav_bytes: bytes) -> bytes:
    """
    Apply Voice Activity Detection (trimming silence) and normalize amplitude.
    Returns processed WAV bytes formatted for ECAPA-TDNN extraction (16kHz).
    """
    if not LIBROSA_AVAILABLE:
        return wav_bytes  # Passthrough
        
    try:
        # Load audio from memory using soundfile
        audio, sr = sf.read(io.BytesIO(wav_bytes))
        
        # If stereo, convert to mono
        if len(audio.shape) > 1:
            audio = audio.mean(axis=1)
            
        # Resample to 16kHz via librosa
        if sr != 16000:
            audio = librosa.resample(audio, orig_sr=sr, target_sr=16000)
            
        # Trim leading and trailing silence (top_db=30 is a standard threshold)
        audio_trimmed, _ = librosa.effects.trim(audio, top_db=30)
        
        # Normalize volume envelope
        audio_normalized = librosa.util.normalize(audio_trimmed)
        
        # Write back to memory buffer as 16-bit WAV
        out_buf = io.BytesIO()
        sf.write(out_buf, audio_normalized, 16000, format='WAV', subtype='PCM_16')
        
        return out_buf.getvalue()
        
    except Exception as e:
        logger.error(f"Failed to preprocess audio: {e}")
        # Return original audio stream if processing fails
        return wav_bytes
