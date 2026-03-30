"""
Liveness Detection & Anti-Spoofing
====================================
Detect whether the face in the camera is a real, live person
vs. a photo, screen replay, or mask.
"""

import logging
from typing import Optional

import cv2
import numpy as np

try:
    import face_recognition
    FACE_RECOGNITION_AVAILABLE = True
except ImportError:
    FACE_RECOGNITION_AVAILABLE = False

logger = logging.getLogger(__name__)

# Eye Aspect Ratio threshold for blink detection
EAR_THRESHOLD = 0.25
EAR_CONSECUTIVE_FRAMES = 2

# Motion detection thresholds
MOTION_MIN_DISPLACEMENT = 5.0   # Minimum face center displacement (pixels)
MOTION_MAX_DISPLACEMENT = 200.0  # Maximum (too much = different person)


def eye_aspect_ratio(eye_points: list[tuple]) -> float:
    """
    Calculate the Eye Aspect Ratio (EAR) for blink detection.
    
    EAR = (|p2-p6| + |p3-p5|) / (2 * |p1-p4|)
    
    When the eye is open, EAR is relatively constant (~0.3).
    When the eye is closed, EAR drops below the threshold (~0.2).
    
    Args:
        eye_points: List of 6 (x, y) tuples defining the eye contour.
    
    Returns:
        EAR value (float).
    """
    if len(eye_points) < 6:
        return 0.3  # Default open-eye value

    # Convert to numpy for vector math
    p = np.array(eye_points, dtype=np.float64)

    # Vertical distances
    v1 = np.linalg.norm(p[1] - p[5])
    v2 = np.linalg.norm(p[2] - p[4])

    # Horizontal distance
    h = np.linalg.norm(p[0] - p[3])

    if h == 0:
        return 0.3

    return (v1 + v2) / (2.0 * h)


def detect_blink(frames: list[np.ndarray]) -> dict:
    """
    Detect blink across multiple frames by tracking EAR.
    A blink is detected when EAR drops below threshold and recovers.
    
    Args:
        frames: List of RGB image arrays (3+ frames).
    
    Returns:
        Dictionary with blink_detected (bool) and ear_values.
    """
    if not FACE_RECOGNITION_AVAILABLE:
        return {"blink_detected": False, "error": "face_recognition not available"}

    ear_values = []
    below_threshold_count = 0
    blink_detected = False

    for frame in frames:
        landmarks_list = face_recognition.face_landmarks(frame)
        if not landmarks_list:
            ear_values.append(None)
            continue

        landmarks = landmarks_list[0]
        left_eye = landmarks.get("left_eye", [])
        right_eye = landmarks.get("right_eye", [])

        if not left_eye or not right_eye:
            ear_values.append(None)
            continue

        left_ear = eye_aspect_ratio(left_eye)
        right_ear = eye_aspect_ratio(right_eye)
        avg_ear = (left_ear + right_ear) / 2.0
        ear_values.append(round(avg_ear, 4))

        if avg_ear < EAR_THRESHOLD:
            below_threshold_count += 1
        else:
            if below_threshold_count >= EAR_CONSECUTIVE_FRAMES:
                blink_detected = True
            below_threshold_count = 0

    # Check final state
    if below_threshold_count >= EAR_CONSECUTIVE_FRAMES:
        blink_detected = True

    return {
        "blink_detected": blink_detected,
        "ear_values": ear_values,
        "frames_analyzed": len(frames),
    }


def detect_motion(frames: list[np.ndarray]) -> dict:
    """
    Detect face motion between frames.
    A live person naturally shifts position; a photo is static.
    
    Args:
        frames: List of RGB image arrays (2+ frames).
    
    Returns:
        Dictionary with motion_detected, displacements, and average_displacement.
    """
    if len(frames) < 2:
        return {"motion_detected": False, "error": "Need at least 2 frames"}

    face_centers = []

    for frame in frames:
        if FACE_RECOGNITION_AVAILABLE:
            locations = face_recognition.face_locations(frame, model="hog")
        else:
            # OpenCV fallback
            gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
            cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            )
            faces = cascade.detectMultiScale(gray, 1.1, 5, minSize=(80, 80))
            locations = [(y, x + w, y + h, x) for (x, y, w, h) in faces]

        if locations:
            top, right, bottom, left = locations[0]
            center_x = (left + right) / 2.0
            center_y = (top + bottom) / 2.0
            face_centers.append((center_x, center_y))
        else:
            face_centers.append(None)

    # Calculate displacements between consecutive frames
    displacements = []
    for i in range(1, len(face_centers)):
        if face_centers[i] is not None and face_centers[i - 1] is not None:
            dx = face_centers[i][0] - face_centers[i - 1][0]
            dy = face_centers[i][1] - face_centers[i - 1][1]
            disp = np.sqrt(dx ** 2 + dy ** 2)
            displacements.append(round(float(disp), 2))

    if not displacements:
        return {
            "motion_detected": False,
            "error": "Could not track face across frames",
            "displacements": [],
        }

    avg_displacement = sum(displacements) / len(displacements)
    max_displacement = max(displacements)

    motion_detected = (
        avg_displacement >= MOTION_MIN_DISPLACEMENT
        and max_displacement <= MOTION_MAX_DISPLACEMENT
    )

    return {
        "motion_detected": motion_detected,
        "displacements": displacements,
        "average_displacement": round(avg_displacement, 2),
        "max_displacement": round(max_displacement, 2),
    }


def analyze_texture(image: np.ndarray) -> dict:
    """
    Analyze image texture to detect screen/print artifacts.
    
    Real faces have natural texture variation, while screens
    show moiré patterns and prints show paper texture.
    
    Uses Laplacian variance as a focus/texture metric.
    
    Args:
        image: RGB numpy array.
    
    Returns:
        Dictionary with texture_score, is_real_texture, and metrics.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)

    # Laplacian variance (focus/sharpness metric)
    laplacian = cv2.Laplacian(gray, cv2.CV_64F)
    laplacian_var = float(laplacian.var())

    # Local Binary Pattern (LBP) based texture analysis
    # High frequency content ratio
    f_transform = np.fft.fft2(gray.astype(np.float64))
    f_shift = np.fft.fftshift(f_transform)
    magnitude = np.abs(f_shift)

    rows, cols = gray.shape
    crow, ccol = rows // 2, cols // 2
    mask_size = min(rows, cols) // 8

    # High frequency energy ratio
    total_energy = np.sum(magnitude ** 2)
    center_mask = magnitude[
        crow - mask_size:crow + mask_size,
        ccol - mask_size:ccol + mask_size
    ]
    low_freq_energy = np.sum(center_mask ** 2)
    high_freq_ratio = 1.0 - (low_freq_energy / total_energy) if total_energy > 0 else 0

    # Texture score: combine metrics
    # Real faces: moderate laplacian (30-500), moderate HF ratio (0.3-0.8)
    # Screens: high laplacian, unusual HF patterns
    # Prints: low laplacian, low HF
    texture_score = 0.0

    if 20 < laplacian_var < 800:
        texture_score += 40
    elif laplacian_var >= 800:
        texture_score += 15  # Possible screen
    else:
        texture_score += 10  # Too blurry or print

    if 0.2 < high_freq_ratio < 0.85:
        texture_score += 40
    else:
        texture_score += 10

    # Color variance check (screens often have limited color range)
    color_std = np.std(image.astype(np.float64))
    if color_std > 30:
        texture_score += 20
    else:
        texture_score += 5

    is_real = texture_score >= 70

    return {
        "is_real_texture": is_real,
        "texture_score": round(texture_score, 2),
        "laplacian_variance": round(laplacian_var, 2),
        "high_freq_ratio": round(float(high_freq_ratio), 4),
        "color_std": round(float(color_std), 2),
    }


def perform_liveness_check(frames: list[np.ndarray]) -> dict:
    """
    Comprehensive liveness check combining all detection methods.
    
    Args:
        frames: List of RGB image frames (minimum 3).
    
    Returns:
        Combined liveness result with individual check details.
    """
    if len(frames) < 3:
        return {
            "is_live": False,
            "error": "Minimum 3 frames required for liveness check",
            "overall_score": 0,
        }

    # Run all checks
    blink_result = detect_blink(frames)
    motion_result = detect_motion(frames)
    texture_result = analyze_texture(frames[len(frames) // 2])  # Use middle frame

    # Scoring
    score = 0
    checks_passed = 0
    total_checks = 3

    if blink_result.get("blink_detected"):
        score += 35
        checks_passed += 1

    if motion_result.get("motion_detected"):
        score += 35
        checks_passed += 1

    if texture_result.get("is_real_texture"):
        score += 30
        checks_passed += 1

    # Need at least 2 of 3 checks to pass
    is_live = checks_passed >= 2

    return {
        "is_live": is_live,
        "overall_score": score,
        "checks_passed": checks_passed,
        "total_checks": total_checks,
        "details": {
            "blink_detection": blink_result,
            "motion_detection": motion_result,
            "texture_analysis": texture_result,
        },
    }
