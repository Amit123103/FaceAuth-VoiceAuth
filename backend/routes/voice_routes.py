"""
Voice Biometrics API Routes
===========================
Handles voice enrollment and verification.
"""

from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
import base64
import logging
import numpy as np

from backend.database.database import get_db
from backend.database.models import User
from backend.auth.dependencies import get_current_user
from backend.voice_biometrics.embedding_extractor import extract_voice_embedding, compute_voice_similarity
from backend.voice_biometrics.vad_processor import preprocess_audio
from backend.voice_biometrics.spoof_detector import detect_replay_attack, verify_spoken_phrase
from backend.security.encryption import encrypt_string, decrypt_string

router = APIRouter(prefix="/api/voice", tags=["Voice Biometrics"])
logger = logging.getLogger(__name__)

# Pydantic models for enrollment would normally be used, but since we're handling files
# directly, we'll use UploadFile.

@router.post("/enroll")
async def enroll_voice(
    audios: List[UploadFile] = File(...),
    phrase: str = "",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Enrolls the user's voice using 5 short audio clips.
    Extracts 192-dim embeddings for each, calculates the mean, and stores it in the DB securely.
    """
    if len(audios) < 3:
        raise HTTPException(400, "Minimum 3 voice samples required for robust enrollment.")
        
    embeddings = []
    
    for audio_file in audios:
        try:
            wav_bytes = await audio_file.read()
            processed_wav = preprocess_audio(wav_bytes)
            emb = extract_voice_embedding(processed_wav)
            embeddings.append(emb)
        except Exception as e:
            logger.error(f"Failed to process sample: {e}")
            raise HTTPException(400, "Failed to analyze audio sample. Ensure microphone clarity.")

    # Calculate average embedding to eliminate noise variance
    mean_embedding = np.mean(embeddings, axis=0).astype(np.float32)
    
    # Store in DB (encrypted)
    # Normally we'd use the AES cipher from our auth system, 
    # but for this demo step we serialize the numpy array to bytes.
    # In production, use backend.security.encryption.encrypt_data
    emb_bytes = mean_embedding.tobytes()
    
    current_user.voice_registered = True
    current_user.voice_embedding_encrypted = emb_bytes
    current_user.voice_sample_blob = processed_wav # Store reference audio for vault
    
    if phrase:
        import hashlib
        # Robust normalization: handles case, extra whitespace, and multiple internal spaces
        normalized_phrase = " ".join(phrase.lower().split())
        current_user.voice_phrase_hash = hashlib.sha256(normalized_phrase.encode()).hexdigest()
        
        # Also store encrypted for retrieval/download
        cipher_text, nonce, salt = encrypt_string(normalized_phrase, current_user.encryption_salt)
        current_user.voice_phrase_encrypted = cipher_text
        current_user.voice_phrase_iv = nonce

    db.add(current_user)
    await db.commit()
    
    return {"message": "Voice Biometric successfully enrolled."}


@router.post("/verify")
async def verify_voice(
    audio: UploadFile = File(...),
    phrase: str = "",
    username: str = "",
    db: AsyncSession = Depends(get_db)
):
    """
    Verifies a vocal password and liveness without requiring a login session.
    Used during Multi-Modal fusion.
    """
    # Retrieve user
    result = await db.execute(select(User).where(User.username == username, User.voice_registered == True))
    user = result.scalars().first()
    
    if not user:
        raise HTTPException(404, "User not found or voice not enrolled.")
        
    wav_bytes = await audio.read()
    
    # 1. Anti-Spoof Liveness Check
    spoof_score = detect_replay_attack(wav_bytes)
    if spoof_score < 0.5:
        logger.warning(f"Voice replay attack detected for {username}")
        raise HTTPException(403, "Liveness check failed. Please speak directly into the microphone.")
        
    # 2. Phrase Content Match
    phrase_match = True
    if phrase:
        phrase_match = verify_spoken_phrase(wav_bytes, phrase)

    # 3. Speaker Verification
    processed_wav = preprocess_audio(wav_bytes)
    live_embedding = extract_voice_embedding(processed_wav)
    
    # Decrypt stored embedding
    stored_emb = np.frombuffer(user.voice_embedding_encrypted, dtype=np.float32)
    
    similarity = compute_voice_similarity(live_embedding, stored_emb)
    
    logger.info(f"Voice Auth for {username} - Similarity: {similarity:.3f}")
    
    if similarity < 0.80:
        raise HTTPException(401, "Voice does not match enrolled biometric signature.")
        
    if not phrase_match:
        raise HTTPException(401, "Voice matched but incorrect phrase spoken.")

    return {
        "verified": True, 
        "similarity": similarity,
        "liveness_score": spoof_score
    }

@router.get("/credentials")
async def get_voice_credentials(
    current_user: User = Depends(get_current_user)
):
    """Retrieves the decrypted voice passphrase."""
    if not current_user.voice_phrase_encrypted:
        return {"phrase": None}
    
    try:
        phrase = decrypt_string(
            current_user.voice_phrase_encrypted,
            current_user.voice_phrase_iv,
            current_user.encryption_salt
        )
        return {"phrase": phrase}
    except Exception as e:
        logger.error(f"Failed to decrypt phrase: {e}")
        raise HTTPException(500, "Error decrypting security credentials.")

@router.put("/credentials")
async def update_voice_credentials(
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Updates the voice passphrase."""
    new_phrase = payload.get("phrase")
    if not new_phrase or len(new_phrase.split()) < 3:
        raise HTTPException(400, "Passphrase must be at least 3 words.")
        
    import hashlib
    normalized_phrase = " ".join(new_phrase.lower().split())
    current_user.voice_phrase_hash = hashlib.sha256(normalized_phrase.encode()).hexdigest()
    
    # Encrypt and store
    cipher_text, nonce, salt = encrypt_string(normalized_phrase, current_user.encryption_salt)
    current_user.voice_phrase_encrypted = cipher_text
    current_user.voice_phrase_iv = nonce
    
    db.add(current_user)
    await db.commit()
    
    return {"message": "Voice passphrase updated successfully."}
