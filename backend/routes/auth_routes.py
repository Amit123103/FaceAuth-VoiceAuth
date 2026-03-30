"""
Authentication Routes
======================
Registration, login (password + face), token refresh, logout, and 2FA verification.
"""

import logging
import random
import string
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status, Form, File, UploadFile, BackgroundTasks
import numpy as np
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.database import get_db
from backend.database.models import User, LoginHistory, ActiveSession, AuditLog
from backend.auth.password import hash_password, verify_password
from backend.auth.jwt_handler import (
    create_access_token, create_refresh_token,
    decode_token, blacklist_token,
)
from backend.auth.dependencies import get_current_user, get_client_ip, get_user_agent
from backend.auth.rate_limiter import (
    check_rate_limit, check_account_lockout,
    record_failed_login, reset_failed_logins,
)
from backend.security.encryption import encrypt_face_encoding, decrypt_face_encoding
from backend.security.totp import verify_totp
from backend.security.email_alert import send_security_alert
from backend.face.detector import process_registration_image, decode_base64_image, detect_faces, get_face_encoding
from backend.face.matcher import compare_faces
from backend.face.quality import assess_face_quality
from backend.face.liveness import perform_liveness_check
from backend.voice_biometrics.spoof_detector import detect_replay_attack
from backend.voice_biometrics.vad_processor import preprocess_audio
from backend.voice_biometrics.embedding_extractor import extract_voice_embedding, compute_voice_similarity
from backend.voice_biometrics.fusion_engine import evaluate_fusion
from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


# ── Request/Response Models ──────────────────────────────────

class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., max_length=255)
    password: str = Field(..., min_length=8, max_length=72)
    face_image: str = Field(..., description="Base64-encoded face image")

    @field_validator("username")
    @classmethod
    def validate_username(cls, v):
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("Username can only contain letters, numbers, hyphens, and underscores")
        return v.lower()

    @field_validator("password")
    @classmethod
    def validate_password(cls, v):
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in v):
            raise ValueError("Password must contain at least one special character")
        return v


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class FaceLoginRequest(BaseModel):
    face_image: str = Field(..., description="Base64-encoded face image")


class TokenRefreshRequest(BaseModel):
    refresh_token: str


class Verify2FARequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6)
    temp_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict


# ── Registration ─────────────────────────────────────────────

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    request: Request,
    body: RegisterRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Register a new user with credentials and face data.
    
    Steps:
    1. Validate inputs
    2. Check username/email uniqueness
    3. Process face image (detect, encode, quality check)
    4. Encrypt face encoding
    5. Create user record
    """
    # Check existing users
    existing = await db.execute(
        select(User).where(
            (User.username == body.username.lower()) |
            (User.email == body.email.lower())
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email already registered",
        )

    # Process face image
    face_result = process_registration_image(body.face_image)
    if not face_result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Face registration failed: {face_result['error']}",
        )

    # Quality check
    face_location = face_result["face_location"]
    image = decode_base64_image(body.face_image)
    quality = assess_face_quality(
        image,
        (face_location["top"], face_location["right"],
         face_location["bottom"], face_location["left"]),
    )

    if not quality["passed"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Face image quality too low",
                "score": quality["overall_score"],
                "min_required": quality["min_required"],
                "recommendations": quality["recommendations"],
            },
        )

    # Encrypt face encoding (Handle fallback mode)
    encoding = face_result.get("encoding")
    if encoding is None:
        # If no encoding (OpenCV mode), use a dummy for now so registration works
        # In production, you'd require dlib or use a different encoder
        import numpy as np
        encoding = np.zeros(128)
    
    encrypted_data, nonce, salt = encrypt_face_encoding(encoding)

    # Generate verification code
    verification_code = "".join(random.choices(string.digits, k=6))

    try:
        # Create user
        user = User(
            username=body.username.lower(),
            email=body.email.lower(),
            password_hash=hash_password(body.password),
            face_encoding_encrypted=encrypted_data,
            face_encoding_iv=nonce,
            encryption_salt=salt,
            face_registered=True,
            face_image_base64=body.face_image, # Store the raw reference image
            is_verified=True,  # Auto-verify for dev
            verification_code=verification_code,
            verification_expires=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        db.add(user)
        await db.flush()
    except Exception as e:
        logger.error(f"Database error during registration: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal registration error: {str(e)}"
        )

    # Audit log
    db.add(AuditLog(
        user_id=user.id,
        action="user.registered",
        details=f"User registered with face data (quality: {quality['overall_score']}%)",
        ip_address=get_client_ip(request),
    ))

    logger.info(f"New user registered: {user.username} (verification: {verification_code})")

    # Security Alert: Welcome Email
    background_tasks = BackgroundTasks()
    background_tasks.add_task(
        send_security_alert,
        username=user.username,
        email=user.email,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        method="registration",
        success=True,
        alert_type="registration"
    )

    return {
        "message": "Registration successful",
        "user_id": user.id,
        "username": user.username,
        "face_quality_score": quality["overall_score"],
        "verification_required": not user.is_verified,
    }


# ── Password Login ───────────────────────────────────────────

@router.post("/login")
async def login(
    request: Request,
    body: LoginRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate with username and password."""
    # Find user
    result = await db.execute(
        select(User).where(User.username == body.username.lower())
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # Check account lockout
    lock_msg = await check_account_lockout(user)
    if lock_msg:
        background_tasks.add_task(
            send_security_alert,
            username=user.username,
            email=user.email,
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
            method="password",
            success=False,
            failure_reason="Account Temporarily Locked"
        )
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=lock_msg,
        )

    # Verify password
    if not verify_password(body.password, user.password_hash):
        await record_failed_login(user, db)

        # Log failed attempt
        db.add(LoginHistory(
            user_id=user.id,
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
            login_method="password",
            success=False,
            failure_reason="Invalid password",
        ))

        remaining = settings.max_login_attempts - (user.failed_login_count + 1)
        
        # Security Alert: Failed Password Attempt
        background_tasks.add_task(
            send_security_alert,
            username=user.username,
            email=user.email,
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
            method="password",
            success=False,
            failure_reason="Incorrect Password"
        )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid credentials. {max(0, remaining)} attempts remaining.",
        )

    # Check if 2FA is enabled
    if user.is_2fa_enabled:
        # Issue a temporary token for 2FA verification
        temp_token = create_access_token(
            user.id, user.username, user.is_admin,
            extra_claims={"type": "2fa_pending", "requires_2fa": True},
        )
        return {
            "requires_2fa": True,
            "temp_token": temp_token,
            "message": "2FA verification required",
        }

    # Successful login
    return await _create_session(user, "password", request, db, background_tasks, alert_type="secure_password")


# ── Face Login ───────────────────────────────────────────────

@router.post("/face-login")
async def face_login(
    request: Request,
    body: FaceLoginRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate using face recognition only."""
    # Decode and detect face
    try:
        image = decode_base64_image(body.face_image)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    face_locations = detect_faces(image)
    if not face_locations:
        raise HTTPException(status_code=400, detail="No face detected. Ensure good lighting and face the camera directly.")

    # Pick the largest face (by area) — handles false positives from Haar cascade
    if len(face_locations) > 1:
        face_locations = [max(face_locations, key=lambda f: (f[2] - f[0]) * (f[1] - f[3]))]

    # Generate encoding for the login attempt
    login_encoding = get_face_encoding(image, face_locations[0])
    if login_encoding is None:
        raise HTTPException(status_code=400, detail="Failed to process face")

    # Load all users with face data
    result = await db.execute(
        select(User).where(
            User.face_registered == True,
            User.is_active == True,
        )
    )
    users = result.scalars().all()

    if not users:
        raise HTTPException(status_code=401, detail="No registered faces found")

    # Compare against all registered faces
    from backend.security.encryption import decrypt_face_encoding
    
    best_match = None
    best_confidence = 0

    for user in users:
        if user.is_locked:
            continue

        try:
            stored_encoding = decrypt_face_encoding(
                user.face_encoding_encrypted,
                user.face_encoding_iv,
                user.encryption_salt,
            )

            result = compare_faces(stored_encoding, login_encoding)

            if result["match"] and result["confidence"] > best_confidence:
                best_confidence = result["confidence"]
                best_match = {
                    "user": user,
                    "result": result,
                }
        except Exception as e:
            logger.warning(f"Failed to decrypt face for user {user.id}: {e}")
            continue

    if best_match is None:
        # Log failed face login (no user context)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Face not recognized. Please try again or use password login.",
        )

    matched_user = best_match["user"]
    match_result = best_match["result"]

    # Check 2FA
    if matched_user.is_2fa_enabled:
        temp_token = create_access_token(
            matched_user.id, matched_user.username, matched_user.is_admin,
            extra_claims={"type": "2fa_pending", "requires_2fa": True},
        )
        return {
            "requires_2fa": True,
            "temp_token": temp_token,
            "confidence": float(match_result["confidence"]),
            "message": "Face recognized — 2FA verification required",
        }

    # Successful face login
    session = await _create_session(matched_user, "face", request, db, background_tasks, alert_type="biometric_face")
    session["face_match"] = {
        "confidence": float(match_result["confidence"]),
        "distance": float(match_result["distance"]),
    }
    return session


# ── 2FA Verification ─────────────────────────────────────────

@router.post("/verify-2fa")
async def verify_2fa(
    request: Request,
    body: Verify2FARequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Verify TOTP 2FA code after initial authentication."""
    payload = decode_token(body.temp_token)
    if not payload or not payload.get("requires_2fa"):
        raise HTTPException(status_code=401, detail="Invalid or expired 2FA token")

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_2fa_enabled:
        raise HTTPException(status_code=401, detail="2FA not configured")

    # Decrypt TOTP secret
    from backend.security.encryption import decrypt_string
    try:
        totp_secret = decrypt_string(
            user.totp_secret_encrypted,
            user.face_encoding_iv,  # Reuse nonce for TOTP
            user.encryption_salt,
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to verify 2FA")

    if not verify_totp(totp_secret, body.code):
        background_tasks.add_task(
            send_security_alert,
            username=user.username,
            email=user.email,
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
            method="2fa_totp",
            success=False,
            failure_reason="Invalid 2FA Code"
        )
        raise HTTPException(status_code=401, detail="Invalid 2FA code")

    return await _create_session(user, "2fa", request, db, background_tasks, alert_type="2fa_totp")


# ── Token Refresh ────────────────────────────────────────────

@router.post("/refresh")
async def refresh_token(
    request: Request,
    body: TokenRefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    """Refresh an access token using a refresh token."""
    payload = decode_token(body.refresh_token)

    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    user_id = payload.get("sub")

    # Verify session exists
    from backend.auth.password import pwd_context
    import hashlib
    token_hash = hashlib.sha256(body.refresh_token.encode()).hexdigest()

    result = await db.execute(
        select(ActiveSession).where(
            ActiveSession.user_id == user_id,
            ActiveSession.refresh_token_hash == token_hash,
        )
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=401, detail="Session not found or revoked")

    expires_at = session.expires_at if session.expires_at.tzinfo else session.expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Refresh token expired")

    # Fetch user
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User account not available")

    # Issue new access token
    access_token = create_access_token(user.id, user.username, user.is_admin)

    # Update session last_used
    session.last_used = datetime.now(timezone.utc)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": settings.jwt_access_token_expire_minutes * 60,
    }


# ── Logout ───────────────────────────────────────────────────

@router.post("/logout")
async def logout(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Invalidate the current session."""
    # Blacklist the access token
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1]
        await blacklist_token(token, db)

    # Audit
    db.add(AuditLog(
        user_id=current_user.id,
        action="user.logout",
        ip_address=get_client_ip(request),
    ))

    return {"message": "Successfully logged out"}


# ── Helper: Create Session ───────────────────────────────────

async def _create_session(
    user: User,
    login_method: str,
    request: Request,
    db: AsyncSession,
    background_tasks: BackgroundTasks,
    alert_type: str = "login"
) -> dict:
    """Create tokens, log the login, and store the session."""
    # Reset failed logins
    await reset_failed_logins(user, db)

    # Create tokens
    access_token = create_access_token(user.id, user.username, user.is_admin)
    refresh_token = create_refresh_token(user.id)

    # Enforce max sessions
    import hashlib
    result = await db.execute(
        select(func.count()).select_from(ActiveSession).where(
            ActiveSession.user_id == user.id
        )
    )
    session_count = result.scalar() or 0

    if session_count >= settings.max_active_sessions:
        # Remove oldest session
        oldest = await db.execute(
            select(ActiveSession)
            .where(ActiveSession.user_id == user.id)
            .order_by(ActiveSession.created_at.asc())
            .limit(1)
        )
        old_session = oldest.scalar_one_or_none()
        if old_session:
            await db.delete(old_session)

    # Store session
    token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
    db.add(ActiveSession(
        user_id=user.id,
        refresh_token_hash=token_hash,
        device_info=get_user_agent(request),
        ip_address=get_client_ip(request),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_token_expire_days),
    ))

    # Log successful login
    db.add(LoginHistory(
        user_id=user.id,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        login_method=login_method,
        success=True,
    ))

    # Audit
    db.add(AuditLog(
        user_id=user.id,
        action="user.login",
        details=f"Login via {login_method}",
        ip_address=get_client_ip(request),
    ))

    # Biometric transparency: Send security alert email in background
    background_tasks.add_task(
        send_security_alert,
        username=user.username,
        email=user.email,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        method=login_method,
        success=True,
        alert_type=alert_type
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.jwt_access_token_expire_minutes * 60,
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "is_admin": user.is_admin,
            "face_registered": user.face_registered,
            "is_2fa_enabled": user.is_2fa_enabled,
        },
    }

# ── Standalone Voice Login ────────────────────────────────────

@router.post("/voice-login")
async def voice_login(
    request: Request,
    background_tasks: BackgroundTasks,
    voice_audio: UploadFile = File(...),
    phrase: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    """
    Biometric Voice-Only Authentication
    Performs speaker verification (1:N) and phrase matching.
    """
    try:
        wav_bytes = await voice_audio.read()
    except Exception:
        raise HTTPException(status_code=400, detail="Could not buffer voice byte stream.")
        
    # 1. Anti-Spoof Liveness
    liveness_score = detect_replay_attack(wav_bytes)
    if liveness_score < 0.4:
         raise HTTPException(status_code=403, detail="Liveness check failed (Replay detected).")

    # 2. Extract Embedding
    processed_audio = preprocess_audio(wav_bytes)
    login_voice_embedding = extract_voice_embedding(processed_audio)
    
    # 3. Fetch Enrolled Voice Users
    result = await db.execute(select(User).where(User.voice_registered == True))
    users = result.scalars().all()
    
    if not users:
        raise HTTPException(status_code=404, detail="No enrolled voice identities found.")

    best_user = None
    best_score = 0.0
    
    # 4. Biometric 1:N Match
    for user in users:
        # A. Phrase Match
        if user.voice_phrase_hash:
            import hashlib
            normalized_input = " ".join(phrase.lower().split())
            if user.voice_phrase_hash != hashlib.sha256(normalized_input.encode()).hexdigest():
                continue # Skip if phrase doesn't match this identity

        # B. Voice similarity
        stored_voice = np.frombuffer(user.voice_embedding_encrypted, dtype=np.float32)
        similarity = float(compute_voice_similarity(login_voice_embedding, stored_voice))
        
        if similarity > 0.82 and similarity > best_score:
            best_score = similarity
            best_user = user

    if not best_user:
        raise HTTPException(status_code=401, detail="Voice signature or passphrase did not match.")
        
    logger.info(f"Voice-Only Access Granted to {best_user.username} w/ Similarity {best_score:.2f}")

    # Check 2FA
    if best_user.is_2fa_enabled:
        temp_token = create_access_token(
            best_user.id, best_user.username, best_user.is_admin,
            extra_claims={"type": "2fa_pending", "requires_2fa": True},
        )
        return {"requires_2fa": True, "temp_token": temp_token, "message": "2FA required"}

    return await _create_session(best_user, "voice_only", request, db, background_tasks, alert_type="biometric_voice")

# ── Multi-Modal Fusion Login ─────────────────────────────────

from fastapi import UploadFile, File, Form
import numpy as np
from backend.security.encryption import decrypt_face_encoding
from backend.voice_biometrics.embedding_extractor import extract_voice_embedding, compute_voice_similarity
from backend.voice_biometrics.vad_processor import preprocess_audio
from backend.voice_biometrics.spoof_detector import detect_replay_attack, verify_spoken_phrase
from backend.voice_biometrics.fusion_engine import evaluate_fusion

@router.post("/fusion-login")
async def fusion_login(
    request: Request,
    background_tasks: BackgroundTasks,
    face_image: str = Form(...),
    voice_audio: UploadFile = File(...),
    phrase: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    """
    Zero-Trust Multi-Modal Authentication
    Requires both a biometric Face encoding and a live Voice recording.
    Calculates independent confidence thresholds and delegates to FusionEngine.
    """
    
    # 1. Evaluate Face 
    try:
        image = decode_base64_image(face_image)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid face image format.")

    face_locations = detect_faces(image)
    if not face_locations:
        raise HTTPException(status_code=400, detail="No face detected in video stream.")
    
    # Prioritize largest face
    if len(face_locations) > 1:
        face_locations = [max(face_locations, key=lambda f: (f[2] - f[0]) * (f[1] - f[3]))]

    login_face_encoding = get_face_encoding(image, face_locations[0])
    if login_face_encoding is None:
        raise HTTPException(status_code=400, detail="Failed to process face encoding.")
    
    # Fetch enrolled users who have BOTH face and voice registered
    result = await db.execute(
        select(User).where(User.face_registered == True, User.voice_registered == True)
    )
    users = result.scalars().all()
    
    if not users:
        raise HTTPException(status_code=401, detail="No multi-modal identities found.")

    # 2. Evaluate Voice
    try:
        wav_bytes = await voice_audio.read()
    except Exception:
        raise HTTPException(status_code=400, detail="Could not buffer voice byte stream.")
        
    liveness_score = detect_replay_attack(wav_bytes)
    
    # 2.B Strict Phrase Match
    phrase_matched = False
    if phrase:
        processed_phrase = phrase.lower().strip()
        # Verify against stored hash or decrypt and compare
        import hashlib
        provided_hash = hashlib.sha256(processed_phrase.encode()).hexdigest()
        
        # Check against multiple users to find correct identity
        # (This happens inside the loop for each candidate user)
    
    processed_audio = preprocess_audio(wav_bytes)
    login_voice_embedding = extract_voice_embedding(processed_audio)
    
    # 3. Search and Score Fusion
    best_user = None
    best_fusion_score = 0.0
    highest_confidence = 0.0
    
    for user in users:
        # A. Face match
        stored_face = decrypt_face_encoding(user.face_encoding_encrypted, user.face_encoding_iv, user.encryption_salt)
        face_result = compare_faces(stored_face, login_face_encoding)
        face_confidence_score = float(face_result["confidence"]) / 100.0
        
        # B. Voice match
        stored_voice = np.frombuffer(user.voice_embedding_encrypted, dtype=np.float32)
        voice_confidence = compute_voice_similarity(login_voice_embedding, stored_voice)
        
        # C. Phrase match (User specific)
        user_phrase_matched = False
        # C. Phrase Match
        if user.voice_phrase_hash:
            import hashlib
            normalized_input = " ".join(phrase.lower().split())
            user_phrase_matched = (user.voice_phrase_hash == hashlib.sha256(normalized_input.encode()).hexdigest())
        else:
            user_phrase_matched = True # No phrase set for this user

        # D. Multi-modal Fusion
        auth_result = evaluate_fusion(
            face_score=face_confidence_score,
            voice_score=voice_confidence,
            liveness_score=liveness_score,
            phrase_matched=user_phrase_matched
        )
        
        if auth_result.allowed and auth_result.confidence > best_fusion_score:
            best_fusion_score = auth_result.confidence
            best_user = user
            highest_confidence = auth_result.confidence

    if not best_user:
        logger.warning(f"Fusion auth failed. Max confidence reached: {best_fusion_score:.2f}")
        raise HTTPException(status_code=401, detail="Multi-modal authentication failed. Signatures did not meet thresholds.")
        
    logger.info(f"Fusion Access Granted to {best_user.username} w/ Confidence {highest_confidence:.2f}")

    # Check 2FA
    if best_user.is_2fa_enabled:
        temp_token = create_access_token(
            best_user.id, best_user.username, best_user.is_admin,
            extra_claims={"type": "2fa_pending", "requires_2fa": True},
        )
        return {
            "requires_2fa": True, 
            "temp_token": temp_token, 
            "message": "2FA required",
            "confidence": float(highest_confidence)
        }

    # Success Response
    session = await _create_session(best_user, "face+voice_fusion", request, db, background_tasks, alert_type="biometric_dual")
    session["auth_meta"] = {
        "fusion_score": float(highest_confidence)
    }
    return session


@router.get("/biometric-data")
async def get_biometric_data(
    current_user: User = Depends(get_current_user)
):
    """Retrieves the stored biometric previews for the Identity Vault."""
    import base64
    
    voice_base64 = None
    if current_user.voice_sample_blob:
        voice_base64 = f"data:audio/wav;base64,{base64.b64encode(current_user.voice_sample_blob).decode()}"
        
    return {
        "has_face": current_user.face_registered,
        "face_image": current_user.face_image_base64,
        "has_voice": current_user.voice_registered,
        "voice_sample": voice_base64,
        "username": current_user.username
    }

