"""
Face Matching Engine
====================
Compare face encodings using Euclidean distance
with configurable threshold and confidence scoring.
"""

import numpy as np
from typing import Optional

from backend.config import get_settings

settings = get_settings()


def compare_faces(
    known_encoding: np.ndarray,
    unknown_encoding: np.ndarray,
    threshold: Optional[float] = None,
) -> dict:
    """
    Compare two face encodings and determine if they match.
    
    Uses Euclidean distance (L2 norm) between 128-dimensional vectors.
    A distance of 0.0 = identical, typically:
      - < 0.4 = same person (high confidence)
      - 0.4 - 0.6 = likely same person
      - > 0.6 = different people
    
    Args:
        known_encoding: The stored reference encoding (128-d).
        unknown_encoding: The new encoding to compare (128-d).
        threshold: Match threshold (default from settings).
    
    Returns:
        Dictionary with:
            - match: bool — whether faces match
            - distance: float — Euclidean distance
            - confidence: float — confidence percentage (0-100)
            - threshold_used: float
    """
    if threshold is None:
        threshold = settings.face_match_threshold

    # Calculate Euclidean distance
    distance = float(np.linalg.norm(known_encoding - unknown_encoding))

    # Determine match - ensure standard Python bool casting
    is_match = bool(distance <= threshold)
 
    # Calculate confidence score
    if distance <= threshold:
        confidence = float(max(0.0, (1.0 - (distance / threshold)) * 100.0))
    else:
        confidence = 0.0
 
    return {
        "match": is_match,
        "distance": float(round(distance, 4)),
        "confidence": float(round(confidence, 2)),
        "threshold_used": float(threshold),
    }


def find_best_match(
    known_encodings: list[tuple[str, np.ndarray]],
    unknown_encoding: np.ndarray,
    threshold: Optional[float] = None,
) -> Optional[dict]:
    """
    Find the best matching face from a list of known encodings.
    
    Args:
        known_encodings: List of (user_id, encoding) tuples.
        unknown_encoding: The encoding to match against.
        threshold: Match threshold.
    
    Returns:
        Best match result with user_id, or None if no match found.
    """
    if threshold is None:
        threshold = settings.face_match_threshold

    best_match = None
    best_distance = float("inf")

    for user_id, known_encoding in known_encodings:
        result = compare_faces(known_encoding, unknown_encoding, threshold)

        if result["match"] and result["distance"] < best_distance:
            best_distance = result["distance"]
            best_match = {
                "user_id": user_id,
                **result,
            }

    return best_match


def batch_compare(
    known_encodings: list[np.ndarray],
    unknown_encoding: np.ndarray,
) -> np.ndarray:
    """
    Efficiently compare one encoding against many using vectorized operations.
    
    Args:
        known_encodings: List of known face encodings.
        unknown_encoding: The encoding to compare.
    
    Returns:
        Array of Euclidean distances.
    """
    if not known_encodings:
        return np.array([])

    known_array = np.array(known_encodings)
    return np.linalg.norm(known_array - unknown_encoding, axis=1)
