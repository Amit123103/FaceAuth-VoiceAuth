"""
TOTP Two-Factor Authentication
===============================
Time-based One-Time Password (TOTP) implementation
using pyotp for Google Authenticator compatibility.
"""

import secrets
import string
import pyotp
from typing import Optional

from backend.config import get_settings

settings = get_settings()

# Recovery code configuration
RECOVERY_CODE_LENGTH = 8
RECOVERY_CODE_COUNT = 10


def generate_totp_secret() -> str:
    """
    Generate a new TOTP secret for a user.
    
    Returns:
        Base32-encoded secret string.
    """
    return pyotp.random_base32()


def get_totp_uri(secret: str, username: str) -> str:
    """
    Generate a provisioning URI for QR code generation.
    Compatible with Google Authenticator, Authy, etc.
    
    Args:
        secret: The TOTP secret.
        username: The user's display name.
    
    Returns:
        otpauth:// URI string.
    """
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(
        name=username,
        issuer_name=settings.app_name,
    )


def verify_totp(secret: str, code: str) -> bool:
    """
    Verify a TOTP code against the secret.
    Allows a 30-second window tolerance.
    
    Args:
        secret: The user's TOTP secret.
        code: The 6-digit code to verify.
    
    Returns:
        True if the code is valid.
    """
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)  # ±30 seconds


def generate_recovery_codes() -> list[str]:
    """
    Generate a set of one-time recovery codes.
    Each code is a random alphanumeric string.
    
    Returns:
        List of recovery code strings.
    """
    alphabet = string.ascii_uppercase + string.digits
    codes = []
    for _ in range(RECOVERY_CODE_COUNT):
        code = "".join(secrets.choice(alphabet) for _ in range(RECOVERY_CODE_LENGTH))
        # Format as XXXX-XXXX for readability
        formatted = f"{code[:4]}-{code[4:]}"
        codes.append(formatted)
    return codes


def generate_qr_code_data(uri: str) -> str:
    """
    Generate a QR code as a base64-encoded PNG image.
    
    Args:
        uri: The otpauth:// URI.
    
    Returns:
        Base64-encoded PNG string (for embedding in HTML/JSON).
    """
    import qrcode
    import io
    import base64

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(uri)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    return base64.b64encode(buffer.getvalue()).decode("utf-8")
