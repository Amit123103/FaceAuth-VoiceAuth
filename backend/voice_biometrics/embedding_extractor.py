"""
Voice Embedding Extractor Module
================================
Extracts deep identity embeddings from audio samples.
Utilizes SpeechBrain's ECAPA-TDNN model for Speaker Recognition.
"""

import io
import logging
import uuid
import os
import numpy as np

logger = logging.getLogger(__name__)

# Temporary directory for audio processing
TMP_DIR = os.path.join(os.path.dirname(__file__), "tmp")
os.makedirs(TMP_DIR, exist_ok=True)

# Try to load deep learning models
try:
    import torch
    import torchaudio
    from speechbrain.inference.speaker import EncoderClassifier
    
    # Load Pre-trained ECAPA-TDNN trained on VoxCeleb
    # This downloads the model to memory on first run (~80MB)
    classifier = EncoderClassifier.from_hparams(
        source="speechbrain/spkrec-ecapa-voxceleb", 
        savedir=os.path.join(TMP_DIR, "pretrained_models")
    )
    SPEECHBRAIN_AVAILABLE = True
    logger.info("SpeechBrain ECAPA-TDNN model loaded successfully.")
    
except (ImportError, OSError) as e:
    logger.warning(f"Could not load SpeechBrain/Torch. Using mock embeddings. Error: {e}")
    SPEECHBRAIN_AVAILABLE = False
    classifier = None

def extract_voice_embedding(wav_bytes: bytes) -> np.ndarray:
    """
    Takes raw WAV audio bytes and returns a 192-dimensional embedding vector.
    """
    if not SPEECHBRAIN_AVAILABLE:
        # Graceful fallback for environments missing heavy torch dependencies
        # In a real environment, this would raise an error or use an API
        logger.warning("[WARNING] Using random mock embedding. Install speechbrain.")
        # Ensure explicitly float32 to prevent expansion to 384 elements (float64)
        return np.random.rand(192).astype(np.float32)

    temp_path = os.path.join(TMP_DIR, f"temp_{uuid.uuid4().hex}.wav")
    try:
        # Write bytes to temp file because torchaudio requires file descriptor
        with open(temp_path, "wb") as f:
            f.write(wav_bytes)

        # Load audio using torchaudio (resamples to 16kHz internally if needed)
        signal, fs = torchaudio.load(temp_path)
        
        # ECAPA-TDNN requires 16000 Hz
        if fs != 16000:
            resampler = torchaudio.transforms.Resample(orig_freq=fs, new_freq=16000)
            signal = resampler(signal)
            
        # Extract embeddings
        # classifier.encode_batch returns shape [batch, 1, 192]
        embeddings = classifier.encode_batch(signal)
        
        # Convert to flat numpy array and FORCE float32
        embedding_vector = embeddings.squeeze().detach().cpu().numpy().astype(np.float32)
        return embedding_vector

    except Exception as e:
        logger.error(f"Failed to extract voice embedding: {e}")
        raise ValueError("Audio processing failed. Ensure valid WAV format.")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def compute_voice_similarity(emb1: np.ndarray, emb2: np.ndarray) -> float:
    """
    Compute Cosine Similarity between two embedding vectors.
    Returns score between -1.0 and 1.0 (1.0 means exact match).
    """
    # Ensure they are flattened and float32
    v1 = emb1.flatten().astype(np.float32)
    v2 = emb2.flatten().astype(np.float32)
    
    if v1.shape != v2.shape:
        logger.error(f"Shape Mismatch: {v1.shape} vs {v2.shape}")
        return 0.0

    # Cosine Similarity
    try:
        dot_product = np.dot(v1, v2)
        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return float(dot_product / (norm1 * norm2))
    except Exception as e:
        logger.error(f"Similarity computation error: {e}")
        return 0.0
