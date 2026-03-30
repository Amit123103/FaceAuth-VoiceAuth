import base64
import numpy as np
from PIL import Image
import io
import sys
import os

# Add the current directory to sys.path so we can import backend
sys.path.append(os.getcwd())

def test_detection():
    print("🚀 Starting Face Detection Test...")
    
    # Create a blank 320x240 RGB image
    img = Image.new('RGB', (320, 240), color = (73, 109, 137))
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='JPEG')
    img_bytes = img_byte_arr.getvalue()
    
    print(f"✅ Created test image ({len(img_bytes)} bytes)")
    
    try:
        import face_recognition
        print("✅ face_recognition library loaded")
    except ImportError:
        print("❌ face_recognition NOT found")
        return

    # Convert to numpy array
    image_array = np.array(img)
    print(f"✅ Image converted to numpy array: {image_array.shape}")

    print("🔍 Attempting face detection (HOG mode)...")
    try:
        # This is where the 500 error likely happens (Segfault)
        locations = face_recognition.face_locations(image_array, model="hog")
        print(f"✅ Detection completed successfully. Found {len(locations)} faces.")
    except Exception as e:
        print(f"❌ Detection failed with error: {e}")

if __name__ == "__main__":
    test_detection()
