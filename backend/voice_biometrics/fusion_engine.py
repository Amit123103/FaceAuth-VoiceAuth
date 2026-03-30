"""
Multi-Modal Fusion Authentication Engine
========================================
Implements Decision and Score-Level fusion logic scaling across 
Confidence, Replay Spoofing, and Phrase checks.
"""
from typing import Dict, Any

class AuthenticationResult:
    def __init__(self, allowed: bool, reason: str, confidence: float):
        self.allowed = allowed
        self.reason = reason
        self.confidence = float(confidence)

def evaluate_fusion(
    face_score: float = 0.0, 
    voice_score: float = 0.0,
    liveness_score: float = 1.0,
    phrase_matched: bool = True,
    strict_mode: bool = False
) -> AuthenticationResult:
    """
    Weighted Fusion Algorithm:
    - Face verification holds 60% weight (assuming highly robust image).
    - Voice provides 40% weight.
    - Liveness spoof detector dynamically degrades the total scalar.
    """
    # Ensure inputs are floats (defensive against route dictionary passing)
    face_score = float(face_score)
    voice_score = float(voice_score)

    # Base requirements
    if strict_mode and (not face_score or not voice_score):
        return AuthenticationResult(False, "Dual-modality required in strict mode.", 0.0)

    # Calculate aggregate
    # Normalize face score assuming threshold was 0.6 (where 1.0 is exact match)
    # Cosine Similarity voice score (where 0.8 is standard threshold)
    
    adjusted_face = min(max((face_score - 0.5) * 2, 0.0), 1.0) # Scale 0.5-1.0 -> 0-1
    adjusted_voice = min(max((voice_score - 0.7) * 3, 0.0), 1.0) # Scale 0.7-1.0 -> 0-1
    
    # Weighting
    final_score = (adjusted_face * 0.6) + (adjusted_voice * 0.4)
    
    # Penalty Multiplications 
    final_score = final_score * liveness_score
    
    if not phrase_matched:
        final_score *= 0.5 # Serious penalty if they said the wrong password

    if final_score > 0.75:
        return AuthenticationResult(True, "Access Granted - High Confidence", final_score)
    elif final_score > 0.50:
        return AuthenticationResult(False, "Step-up Authentication Required.", final_score)
    else:
        return AuthenticationResult(False, "Access Denied - Biometric threshold failed.", final_score)
