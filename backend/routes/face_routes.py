"""
Face Routes
============
Face capture, quality checking, liveness verification,
and face data update endpoints.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.database import get_db
from backend.database.models import User, AuditLog
from backend.auth.dependencies import get_current_user, get_client_ip
from backend.face.detector import (
    decode_base64_image, detect_faces, get_face_encoding,
    process_registration_image,
)
from backend.face.quality import assess_face_quality
from backend.face.liveness import perform_liveness_check
from backend.face.matcher import compare_faces
from backend.security.encryption import encrypt_face_encoding, decrypt_face_encoding

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/face", tags=["Face Recognition"])


# ── Request Models ───────────────────────────────────────────

class FaceCaptureRequest(BaseModel):
    face_image: str = Field(..., description="Base64-encoded face image")


class LivenessCheckRequest(BaseModel):
    frames: list[str] = Field(
        ...,
        min_length=3,
        description="List of base64-encoded frames for liveness check",
    )


class FaceVerifyRequest(BaseModel):
    face_image: str = Field(..., description="Base64-encoded face image")


# ── Face Capture ─────────────────────────────────────────────

@router.post("/capture")
async def capture_face(
    request: Request,
    body: FaceCaptureRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Capture and process a face image.
    Detects face, generates encoding, and checks quality.
    """
    try:
        result = process_registration_image(body.face_image)

        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result["error"],
            )

        # Quality check
        image = decode_base64_image(body.face_image)
        loc = result["face_location"]
        quality = assess_face_quality(
            image,
            (loc["top"], loc["right"], loc["bottom"], loc["left"]),
        )

        return {
            "success": True,
            "face_detected": True,
            "face_count": result["face_count"],
            "face_location": result["face_location"],
            "quality": quality,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Face capture failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Face processing error: {type(e).__name__}")


# ── Quality Check ────────────────────────────────────────────

@router.post("/quality-check")
async def quality_check(body: FaceCaptureRequest):
    """Check face quality without storing anything."""
    try:
        try:
            image = decode_base64_image(body.face_image)
        except ValueError as e:
            return {
                "face_detected": False,
                "quality": None,
                "message": f"Invalid image data: {str(e)}",
            }

        face_locations = detect_faces(image)

        if not face_locations:
            return {
                "face_detected": False,
                "quality": None,
                "message": "No face detected",
            }

        quality = assess_face_quality(image, face_locations[0])

        return {
            "face_detected": True,
            "face_count": len(face_locations),
            "quality": quality,
        }
    except Exception as e:
        import traceback
        logger.error(f"FATAL quality check error: {str(e)}\n{traceback.format_exc()}")
        return {
            "face_detected": False,
            "quality": None,
            "message": f"Server processing error. Please ensure good lighting.",
            "error_type": type(e).__name__
        }


# ── Liveness Check ───────────────────────────────────────────

@router.post("/liveness-check")
async def liveness_check(body: LivenessCheckRequest):
    """
    Perform liveness detection using multiple frames.
    Checks for blink detection, motion, and texture analysis.
    """
    try:
        frames = [decode_base64_image(f) for f in body.frames]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Failed to decode frame: {e}")

    result = perform_liveness_check(frames)

    return {
        "is_live": result["is_live"],
        "overall_score": result["overall_score"],
        "checks_passed": result["checks_passed"],
        "total_checks": result["total_checks"],
        "details": result.get("details", {}),
    }


# ── Face Update ──────────────────────────────────────────────

@router.put("/update")
async def update_face(
    request: Request,
    body: FaceCaptureRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Re-capture and update the user's face data."""
    result = process_registration_image(body.face_image)

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])

    # Quality check
    image = decode_base64_image(body.face_image)
    loc = result["face_location"]
    quality = assess_face_quality(
        image,
        (loc["top"], loc["right"], loc["bottom"], loc["left"]),
    )

    if not quality["passed"]:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Face quality too low for update",
                "score": quality["overall_score"],
                "recommendations": quality["recommendations"],
            },
        )

    # Encrypt and store new face encoding
    encoding = result["encoding"]
    encrypted_data, nonce, salt = encrypt_face_encoding(encoding)

    current_user.face_encoding_encrypted = encrypted_data
    current_user.face_encoding_iv = nonce
    current_user.encryption_salt = salt
    current_user.face_registered = True
    current_user.updated_at = datetime.now(timezone.utc)

    db.add(AuditLog(
        user_id=current_user.id,
        action="face.updated",
        details=f"Face data re-captured (quality: {quality['overall_score']}%)",
        ip_address=get_client_ip(request),
    ))

    return {
        "message": "Face data updated successfully",
        "quality_score": quality["overall_score"],
    }


# ── Face Verify ──────────────────────────────────────────────

@router.post("/verify")
async def verify_face(
    body: FaceVerifyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Verify a face against the current user's stored face data.
    Returns match result with confidence score.
    """
    if not current_user.face_registered:
        raise HTTPException(status_code=400, detail="No face data registered")

    try:
        image = decode_base64_image(body.face_image)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    face_locations = detect_faces(image)
    if not face_locations:
        raise HTTPException(status_code=400, detail="No face detected")

    # Generate encoding
    input_encoding = get_face_encoding(image, face_locations[0])
    if input_encoding is None:
        raise HTTPException(status_code=400, detail="Failed to encode face")

    # Decrypt stored encoding
    try:
        stored_encoding = decrypt_face_encoding(
            current_user.face_encoding_encrypted,
            current_user.face_encoding_iv,
            current_user.encryption_salt,
        )
    except Exception as e:
        logger.error(f"Failed to decrypt face data: {e}")
        raise HTTPException(status_code=500, detail="Failed to access stored face data")

    # Compare
    try:
        match_result = compare_faces(stored_encoding, input_encoding)
    except Exception as e:
        logger.error(f"Face comparison failed: {e}")
        raise HTTPException(status_code=500, detail="Comparison engine error")

    return {
        "verified": match_result["match"],
        "confidence": match_result["confidence"],
        "distance": match_result["distance"],
        "threshold": match_result["threshold_used"],
    }
