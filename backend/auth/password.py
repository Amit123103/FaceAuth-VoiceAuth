"""
Password Hashing Utilities
===========================
bcrypt-based password hashing using passlib.
"""

import logging
from passlib.context import CryptContext
import bcrypt

# ── Bcrypt 4.0+ / Passlib Compatibility Patch ─────────────────
import bcrypt

# 1. Provide missing __about__ for Passlib version checking
if not hasattr(bcrypt, "__about__"):
    class BcryptAbout:
        def __init__(self):
            # Try to get version from metadata if available, otherwise fallback
            try:
                import importlib.metadata as metadata
                self.__version__ = metadata.version("bcrypt")
            except Exception:
                self.__version__ = getattr(bcrypt, "__version__", "4.0.0")
    bcrypt.__about__ = BcryptAbout()

# 2. Patch hashpw to handle the strict 72-byte limit in Bcrypt 4.0+
# Passlib tries to test truncation by passing long strings, which now raises ValueError.
_raw_hashpw = bcrypt.hashpw
def patched_hashpw(password, salt):
    if isinstance(password, str):
        password = password.encode("utf-8")
    # Truncate to 72 bytes as per bcrypt specification to avoid ValueError
    return _raw_hashpw(password[:72], salt)

bcrypt.hashpw = patched_hashpw
# ─────────────────────────────────────────────────────────────

logger = logging.getLogger(__name__)

# Configure bcrypt with sensible defaults
# Using "auto" deprecation to transparently upgrade hashes
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12,  # ~250ms on modern hardware
)


def hash_password(password: str) -> str:
    """
    Hash a plaintext password using bcrypt.
    
    Args:
        password: The plaintext password to hash.
        
    Returns:
        bcrypt hash string (60 characters).
    """
    # Manual truncation to 72 bytes to prevent bcrypt 4.0+ ValueError on Windows
    truncated_password = password.encode("utf-8")[:72].decode("utf-8", "ignore")
    return pwd_context.hash(truncated_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plaintext password against a bcrypt hash.
    Uses constant-time comparison to prevent timing attacks.
    
    Args:
        plain_password: The plaintext password to verify.
        hashed_password: The stored bcrypt hash.
        
    Returns:
        True if the password matches, False otherwise.
    """
    return pwd_context.verify(plain_password, hashed_password)


def needs_rehash(hashed_password: str) -> bool:
    """
    Check if a password hash needs to be re-hashed
    (e.g., because the rounds parameter was increased).
    """
    return pwd_context.needs_update(hashed_password)
