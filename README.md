# FaceAuth — Enterprise Face Recognition Authentication System

![FaceAuth Banner](https://images.unsplash.com/photo-1550751827-4bd374c3f58b?auto=format&fit=crop&q=80&w=1200)

FaceAuth is a production-ready, high-security authentication platform combining traditional password security with advanced biometric face recognition. Built with FastAPI, dlib, and OpenCV.

## 🚀 Key Features

- **🔐 Hybrid Authentication**: Seamlessly switch between password and face login.
- **📷 Advanced Biometrics**: 128-d face encoding with Euclidean distance matching.
- **🛡️ Liveness Detection**: Multi-frame anti-spoofing (blink, motion, and texture analysis).
- **🔒 Military-Grade Encryption**: Biometric data is AES-256-GCM encrypted using per-user PBKDF2 keys.
- **📱 Responsive UI**: Premium dark-mode glassmorphic interface with real-time camera feedback.
- **🛠️ Admin Panel**: Full user management, audit logs, and automated database backups.
- **☁️ Online/Offline**: Local SQLite storage with JSON export/backup capabilities.

## 🛠️ Technology Stack

| Layer | Technology |
|---|---|
| **Backend** | FastAPI (Python 3.9+) |
| **Face Recognition** | dlib, OpenCV, face_recognition |
| **Database** | SQLite (SQLAlchemy Async) |
| **Security** | JWT, bcrypt, AES-256-GCM, pyotp (2FA) |
| **Frontend** | Vanilla HTML5, CSS3 (Modern UI), JavaScript |
| **Camera** | WebRTC (getUserMedia) |

## 🏁 Getting Started

### Prerequisites

- **Python 3.9+**
- **C++ Build Tools** (Required for `dlib` compilation)
  - Windows: [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)
  - Linux: `build-essential cmake libopenblas-dev liblapack-dev`
- **CMake**

### ❌ Troubleshooting dlib on Windows

If you see `ERROR: Failed building wheel for dlib`, it's because `dlib` requires C++ compilation.

**Option A: The Easy Way (Pre-compiled Wheel)**
1. Check your Python version: `python --version` (e.g., 3.11).
2. Download a matching `.whl` file for your version from a trusted source like [dlib-bin](https://github.com/vladimirmariakov/dlib-bin).
3. Install it directly: `pip install dlib-xxx.whl`.

**Option B: The Official Way (Build Tools)**
1. **Install CMake**: `pip install cmake` and ensure it's in your PATH.
2. **Install Visual Studio Build Tools**: 
   - Download from [official site](https://visualstudio.microsoft.com/visual-cpp-build-tools/).
   - Select **"Desktop development with C++"** in the installer.
   - Ensure **MSVC v14x** and **Windows SDK** are checked.
3. Restart your terminal and try `pip install -r backend/requirements.txt` again.

### Installation & Running (Windows)

1. **Setup Environment**:
   ```powershell
   python -m venv venv
   .\venv\Scripts\activate
   ```

2. **Install Core Dependencies**:
   ```powershell
   pip install fastapi uvicorn[standard] python-multipart sqlalchemy aiosqlite python-jose[cryptography] passlib[bcrypt] bcrypt cryptography pyotp qrcode[pil] apscheduler python-dotenv pydantic-settings pytest pytest-asyncio httpx python-dateutil numpy opencv-python-headless Pillow
   ```

3. **Install Face Recognition (dlib)**:
   - Download the [cp311 wheel](https://github.com/z-mahmud22/Dlib_Windows_Python3.x/raw/main/dlib-19.24.1-cp311-cp311-win_amd64.whl) to this folder.
   - Run: `pip install dlib-19.24.1-cp311-cp311-win_amd64.whl`
   - Finally: `pip install face-recognition`

4. **Initialize Config**:
   - Copy `.env.example` to `.env`
   - Open `.env` and verify `DATABASE_URL` starts with `sqlite+aiosqlite://`

5. **Run the Server**:

   ```powershell
   python -m backend.main
   ```

   The application will be available at `http://localhost:8000`.

## 🧪 Testing

Run the test suite using `pytest`:
```bash
pytest backend/tests
```

## 🚢 Deployment Guide

FaceAuth is designed for distributed deployment with a split architecture.

### 🌐 Frontend (Vercel)
Vercel is recommended for the vanilla JS/HTML frontend due to its edge-network performance.

1. **Root Directory**: Set to `frontend`.
2. **Build Command**: `(skip)` (it's static).
3. **Environment Variables**:
   - `BACKEND_URL`: `https://your-backend.render.com` (Ensure this is updated in `frontend/js/utils.js`).

### ⚙️ Backend (Render)
Render provides a robust environment for FastAPI and Python dependencies.

1. **Blueprint / Direct Config**:
   - **Build Command**: `pip install -r backend/requirements.txt`
   - **Start Command**: `gunicorn -w 4 -k uvicorn.workers.UvicornWorker backend.main:app`
2. **Persistence (SQLite)**:
   - Since Render's disk is ephemeral, you must attach a **Persistent Disk** to the `/data` directory (where `faceauth.db` lives).
   - Alternatively, update `DATABASE_URL` to point to a managed **Postgres** instance on Render.
3. **Environment Variables**:
   - `SECRET_KEY`: Long random string.
   - `ALGORITHM`: `HS256`
   - `DATABASE_URL`: `sqlite+aiosqlite:///data/faceauth.db` (if using disk).


## 🔒 Security Architecture

FaceAuth implements multiple layers of security to protect biometric privacy:
1. **Never Storing Images**: Raw camera frames are processed in-memory and discarded. Only 128-d mathematical encodings are stored.
2. **Double-Blind Encryption**: Encodings are encrypted before landing in the database. The secret key is derived from a user-specific salt and the system's master key.
3. **Session Hardening**: JWTs are stored in-memory on the client to prevent XSS-based token theft. CSRF and CSP headers are enforced via backend middleware.

## 📄 License

This project is licensed under the MIT License.
