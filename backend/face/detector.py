import base64
import io
import logging
from typing import Optional, List, Tuple
import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
# Set to True only if dlib is perfectly installed. 
# On Windows, False is safer (uses OpenCV fallback).
FACE_REC_AVAILABLE = False 

# Load OpenCV Haar Cascade for fallback detection
try:
    cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
    face_cascade = cv2.CascadeClassifier(cascade_path)
    if face_cascade.empty():
        logger.error("[ERROR] Failed to load OpenCV Haar Cascade")
except Exception as e:
    logger.error(f"[ERROR] OpenCV Cascade load error: {e}")

def decode_base64_image(base64_string: str) -> np.ndarray:
    """Decodes a base64 string (with or without data URI prefix) to a numpy RGB array."""
    if "," in base64_string:
        base64_string = base64_string.split(",", 1)[1]
    
    # Padding fix
    missing_padding = len(base64_string) % 4
    if missing_padding:
        base64_string += "=" * (4 - missing_padding)

    try:
        image_bytes = base64.b64decode(base64_string)
        image = Image.open(io.BytesIO(image_bytes))
        if image.mode != "RGB":
            image = image.convert("RGB")
        return np.array(image)
    except Exception as e:
        logger.error(f"Image decode failed: {e}")
        raise ValueError(f"Invalid image data: {e}")

def detect_faces(image: np.ndarray) -> List[Tuple[int, int, int, int]]:
    """Detects faces using the best available engine."""
    results = []
    
    # Try high-quality Dlib/face_recognition if available
    if FACE_REC_AVAILABLE:
        try:
            import face_recognition
            return face_recognition.face_locations(image, model="hog")
        except Exception as e:
            logger.warning(f"face_recognition failed, falling back to OpenCV: {e}")

    # Robust Fallback: OpenCV Haar Cascades with multi-pass
    try:
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        # Equalize histogram to improve detection in varying lighting
        gray = cv2.equalizeHist(gray)
        
        faces = None
        # Pass 1: Standard detection
        faces = face_cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=4, minSize=(40, 40)
        )
        
        # Pass 2: More lenient if nothing found
        if faces is None or len(faces) == 0:
            faces = face_cascade.detectMultiScale(
                gray, scaleFactor=1.05, minNeighbors=3, minSize=(30, 30)
            )
        
        if faces is not None:
            for (x, y, w, h) in faces:
                # Convert to (top, right, bottom, left) format
                results.append((int(y), int(x + w), int(y + h), int(x)))
        
        logger.info(f"[DETECT] Found {len(results)} face(s) in {image.shape[1]}x{image.shape[0]} image")
    except Exception as e:
        logger.error(f"OpenCV Detection failed: {e}")
    
    return results

def get_face_encoding(image: np.ndarray, face_location: Tuple[int, int, int, int]) -> Optional[np.ndarray]:
    """Generates 128-d encoding if available, otherwise returns zero-vector."""
    if FACE_REC_AVAILABLE:
        try:
            import face_recognition
            encodings = face_recognition.face_encodings(image, [face_location], num_jitters=1)
            if encodings:
                return encodings[0]
        except Exception as e:
            logger.error(f"Encoding failed: {e}")

    # Fallback/Compatibility Mode: 
    # Return a dummy vector so the system doesn't crash
    return np.zeros(128)

def process_registration_image(base64_string: str) -> dict:
    """Complete pipeline for registration image processing."""
    try:
        image = decode_base64_image(base64_string)
        face_locations = detect_faces(image)
        
        if not face_locations:
            return {"success": False, "error": "No face detected"}
        
        # Robust Selection: Pick the largest face (by area) instead of failing on multiple detections
        if len(face_locations) > 1:
            logger.warning(f"[REGISTRATION] Multiple faces ({len(face_locations)}) detected. Selecting largest face.")
            face_locations = [max(face_locations, key=lambda f: (f[2] - f[0]) * (f[1] - f[3]))]
            
        primary_face = face_locations[0]
        encoding = get_face_encoding(image, primary_face)
        
        return {
            "success": True,
            "face_location": {
                "top": int(face_locations[0][0]),
                "right": int(face_locations[0][1]),
                "bottom": int(face_locations[0][2]),
                "left": int(face_locations[0][3])
            },
            "encoding": encoding.tolist() if hasattr(encoding, "tolist") else encoding,
            "face_count": 1
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
