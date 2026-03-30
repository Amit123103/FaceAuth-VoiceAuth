"""
AES-256 Encryption Module
==========================
Encrypt and decrypt face encodings and other sensitive data
using Fernet (AES-128-CBC under the hood) with PBKDF2 key derivation.

Note: Fernet uses AES-128 internally. For true AES-256, we use
the cryptography library's low-level primitives with AES-256-GCM.
"""

import os
import base64
import json
import hashlib
import numpy as np
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend

from backend.config import get_settings

settings = get_settings()

# AES-256 key size in bytes
AES_KEY_SIZE = 32  # 256 bits
NONCE_SIZE = 12    # 96 bits for GCM
SALT_SIZE = 32     # 256 bits
PBKDF2_ITERATIONS = 600_000  # OWASP 2023 recommendation


def derive_key(master_key: str, salt: bytes) -> bytes:
    """
    Derive an AES-256 key from the master key + per-user salt
    using PBKDF2-HMAC-SHA256.
    
    Args:
        master_key: The application's master encryption key.
        salt: Per-user random salt (32 bytes).
    
    Returns:
        32-byte derived key suitable for AES-256.
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=AES_KEY_SIZE,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
        backend=default_backend(),
    )
    return kdf.derive(master_key.encode("utf-8"))


def generate_salt() -> bytes:
    """Generate a cryptographically secure random salt."""
    return os.urandom(SALT_SIZE)


def encrypt_data(plaintext: bytes, key: bytes) -> tuple[bytes, bytes]:
    """
    Encrypt data using AES-256-GCM.
    
    Args:
        plaintext: The data to encrypt.
        key: 32-byte AES key.
    
    Returns:
        Tuple of (ciphertext_with_tag, nonce).
    """
    nonce = os.urandom(NONCE_SIZE)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    return ciphertext, nonce


def decrypt_data(ciphertext: bytes, key: bytes, nonce: bytes) -> bytes:
    """
    Decrypt data using AES-256-GCM.
    
    Args:
        ciphertext: The encrypted data (includes auth tag).
        key: 32-byte AES key.
        nonce: 12-byte nonce used during encryption.
    
    Returns:
        Decrypted plaintext bytes.
    
    Raises:
        cryptography.exceptions.InvalidTag: If decryption fails (wrong key or tampered data).
    """
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None)


# ── Face Encoding Helpers ────────────────────────────────────

def encrypt_face_encoding(
    encoding: np.ndarray,
    user_salt: Optional[bytes] = None,
) -> tuple[bytes, bytes, bytes]:
    """
    Encrypt a face encoding (128-d numpy array) for storage.
    
    Args:
        encoding: numpy array of shape (128,) from face_recognition.
        user_salt: Optional existing salt (generate new if None).
    
    Returns:
        Tuple of (encrypted_data, nonce, salt).
    """
    if user_salt is None:
        user_salt = generate_salt()

    # Ensure input is a numpy array (handles cases where a list was passed)
    encoding = np.asarray(encoding)
    
    # Serialize the numpy array to bytes
    encoding_bytes = encoding.astype(np.float64).tobytes()

    # Derive per-user key
    key = derive_key(settings.master_encryption_key, user_salt)

    # Encrypt
    ciphertext, nonce = encrypt_data(encoding_bytes, key)

    return ciphertext, nonce, user_salt


def decrypt_face_encoding(
    encrypted_data: bytes,
    nonce: bytes,
    user_salt: bytes,
) -> np.ndarray:
    """
    Decrypt a stored face encoding back to a numpy array.
    
    Args:
        encrypted_data: The encrypted face encoding.
        nonce: The nonce used during encryption.
        user_salt: The per-user salt for key derivation.
    
    Returns:
        numpy array of shape (128,).
    """
    # Derive the same key
    key = derive_key(settings.master_encryption_key, user_salt)

    # Decrypt
    plaintext = decrypt_data(encrypted_data, key, nonce)

    # Deserialize back to numpy array
    return np.frombuffer(plaintext, dtype=np.float64)


def encrypt_string(plaintext: str, salt: Optional[bytes] = None) -> tuple[bytes, bytes, bytes]:
    """
    Encrypt a string (e.g., TOTP secret) using AES-256-GCM.
    
    Returns:
        Tuple of (encrypted_data, nonce, salt).
    """
    if salt is None:
        salt = generate_salt()
    key = derive_key(settings.master_encryption_key, salt)
    ciphertext, nonce = encrypt_data(plaintext.encode("utf-8"), key)
    return ciphertext, nonce, salt


def decrypt_string(encrypted_data: bytes, nonce: bytes, salt: bytes) -> str:
    """
    Decrypt an encrypted string back to plaintext.
    """
    key = derive_key(settings.master_encryption_key, salt)
    plaintext = decrypt_data(encrypted_data, key, nonce)
    return plaintext.decode("utf-8")
