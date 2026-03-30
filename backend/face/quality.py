"""
Face Quality Validation
========================
Assess image and face quality for registration.
Ensures captured faces meet minimum standards for reliable recognition.
"""

import cv2
import numpy as np
from typing import Optional

from backend.config import get_settings

settings = get_settings()


def check_face_size(
    face_location: tuple,
    image_shape: tuple,
    min_size: Optional[int] = None,
) -> dict:
    """
    Verify the detected face meets minimum size requirements.
    
    Args:
        face_location: (top, right, bottom, left) tuple.
        image_shape: (height, width, channels) of the image.
        min_size: Minimum face dimension in pixels.
    
    Returns:
        Quality check result.
    """
    if min_size is None:
        min_size = settings.face_min_size

    top, right, bottom, left = face_location
    face_width = right - left
    face_height = bottom - top

    passed = face_width >= min_size and face_height >= min_size

    # Score based on face size relative to image
    image_height, image_width = image_shape[:2]
    coverage = (face_width * face_height) / (image_width * image_height)

    # Ideal coverage: 15-60% of the frame
    if 0.15 <= coverage <= 0.60:
        size_score = 100
    elif 0.08 <= coverage < 0.15:
        size_score = 70
    elif 0.60 < coverage <= 0.80:
        size_score = 80
    else:
        size_score = 40

    return {
        "check": "face_size",
        "passed": bool(passed),
        "score": int(size_score),
        "face_width": int(face_width),
        "face_height": int(face_height),
        "min_required": int(min_size),
        "coverage_percent": float(round(coverage * 100, 1)),
    }


def check_face_centering(
    face_location: tuple,
    image_shape: tuple,
) -> dict:
    """
    Check if the face is approximately centered in the frame.
    
    Args:
        face_location: (top, right, bottom, left) tuple.
        image_shape: (height, width, channels).
    
    Returns:
        Centering quality result.
    """
    top, right, bottom, left = face_location
    image_height, image_width = image_shape[:2]

    face_center_x = (left + right) / 2.0
    face_center_y = (top + bottom) / 2.0

    image_center_x = image_width / 2.0
    image_center_y = image_height / 2.0

    # Normalized offset (0 = perfectly centered, 1 = at edge)
    offset_x = abs(face_center_x - image_center_x) / image_center_x
    offset_y = abs(face_center_y - image_center_y) / image_center_y

    max_offset = max(offset_x, offset_y)

    # Score: 100 if centered, decreasing as face moves to edge
    if max_offset <= 0.15:
        score = 100
    elif max_offset <= 0.30:
        score = 85
    elif max_offset <= 0.50:
        score = 65
    else:
        score = 35

    passed = max_offset <= 0.40

    return {
        "check": "centering",
        "passed": bool(passed),
        "score": int(score),
        "offset_x": float(round(offset_x, 3)),
        "offset_y": float(round(offset_y, 3)),
    }


def check_brightness(image: np.ndarray) -> dict:
    """
    Check image brightness and exposure.
    
    Args:
        image: RGB numpy array.
    
    Returns:
        Brightness quality result.
    """
    try:
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        mean_brightness = float(np.mean(gray))
        std_brightness = float(np.std(gray))
    except Exception as e:
        return {
            "check": "brightness",
            "passed": False,
            "score": 0,
            "error": "Image format error"
        }

    # Ideal brightness: 80-180 (0-255 range)
    if 80 <= mean_brightness <= 180:
        brightness_score = 100
    elif 50 <= mean_brightness < 80 or 180 < mean_brightness <= 210:
        brightness_score = 70
    else:
        brightness_score = 30

    # Good contrast: std > 40
    if std_brightness > 50:
        contrast_score = 100
    elif std_brightness > 30:
        contrast_score = 70
    else:
        contrast_score = 30

    score = int(brightness_score * 0.5 + contrast_score * 0.5)
    passed = score >= 60

    return {
        "check": "brightness",
        "passed": bool(passed),
        "score": int(score),
        "mean_brightness": float(round(mean_brightness, 1)),
        "std_brightness": float(round(std_brightness, 1)),
        "assessment": str(
            "too_dark" if mean_brightness < 80
            else "too_bright" if mean_brightness > 180
            else "good"
        ),
    }


def check_sharpness(image: np.ndarray) -> dict:
    """
    Check image sharpness/focus using Laplacian variance.
    
    Args:
        image: RGB numpy array.
    
    Returns:
        Sharpness quality result.
    """
    try:
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        variance = float(laplacian.var())
    except Exception:
        return {
            "check": "sharpness",
            "passed": False,
            "score": 0,
            "laplacian_variance": 0,
            "assessment": "error"
        }

    # Good sharpness: variance > 50
    if variance > 100:
        score = 100
    elif variance > 50:
        score = 80
    elif variance > 20:
        score = 55
    else:
        score = 20

    passed = variance > 30

    return {
        "check": "sharpness",
        "passed": bool(passed),
        "score": int(score),
        "laplacian_variance": float(round(variance, 2)),
        "assessment": str(
            "blurry" if variance < 30
            else "acceptable" if variance < 80
            else "sharp"
        ),
    }


def assess_face_quality(
    image: np.ndarray,
    face_location: tuple,
    min_quality_score: Optional[int] = None,
) -> dict:
    """
    Comprehensive face quality assessment.
    Combines all quality checks into an overall score.
    
    Args:
        image: RGB numpy array.
        face_location: (top, right, bottom, left).
        min_quality_score: Minimum overall score to pass.
    
    Returns:
        Complete quality assessment with individual check results.
    """
    if min_quality_score is None:
        min_quality_score = settings.face_quality_min_score

    # Run all checks
    size_result = check_face_size(face_location, image.shape)
    center_result = check_face_centering(face_location, image.shape)
    brightness_result = check_brightness(image)
    sharpness_result = check_sharpness(image)

    # Weighted overall score
    weights = {
        "face_size": 0.30,
        "centering": 0.20,
        "brightness": 0.25,
        "sharpness": 0.25,
    }

    overall_score = int(
        size_result["score"] * weights["face_size"]
        + center_result["score"] * weights["centering"]
        + brightness_result["score"] * weights["brightness"]
        + sharpness_result["score"] * weights["sharpness"]
    )

    all_passed = all([
        size_result["passed"],
        center_result["passed"],
        brightness_result["passed"],
        sharpness_result["passed"],
    ])

    meets_threshold = overall_score >= min_quality_score

    return {
        "overall_score": int(overall_score),
        "min_required": int(min_quality_score),
        "passed": bool(all_passed and meets_threshold),
        "checks": {
            "face_size": size_result,
            "centering": center_result,
            "brightness": brightness_result,
            "sharpness": sharpness_result,
        },
        "recommendations": list(_get_recommendations(
            size_result, center_result, brightness_result, sharpness_result
        )),
    }


def _get_recommendations(size, center, brightness, sharpness) -> list[str]:
    """Generate user-friendly improvement recommendations."""
    recs = []

    if not size["passed"]:
        recs.append("Move closer to the camera — your face should fill more of the frame.")
    
    if not center["passed"]:
        recs.append("Center your face in the camera frame.")
    
    if brightness.get("assessment") == "too_dark":
        recs.append("Increase lighting — the image is too dark.")
    elif brightness.get("assessment") == "too_bright":
        recs.append("Reduce lighting — the image is overexposed.")
    
    if not sharpness["passed"]:
        recs.append("Hold still — the image is blurry. Ensure good lighting.")
    
    if not recs:
        recs.append("Image quality is good!")

    return recs
