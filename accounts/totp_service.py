"""
Two-Factor Authentication (2FA) Service
TOTP-based 2FA implementation using pyotp
"""
import pyotp
import secrets
import hashlib
from typing import Optional, Tuple, List
from django.conf import settings
from django.utils import timezone


# Backup code count
BACKUP_CODES_COUNT = 10


def generate_totp_secret() -> str:
    """Generate a new TOTP secret"""
    return pyotp.random_base32()


def generate_backup_codes(count: int = BACKUP_CODES_COUNT) -> List[str]:
    """Generate backup codes for 2FA"""
    codes = []
    for _ in range(count):
        # Generate 8-character alphanumeric code
        code = secrets.token_hex(4).upper()
        codes.append(code)
    return codes


def hash_backup_code(code: str) -> str:
    """Hash a backup code for secure storage"""
    return hashlib.sha256(code.encode()).hexdigest()


def verify_totp(secret: str, code: str) -> bool:
    """
    Verify a TOTP code against a secret
    Allows for 1 step tolerance (30 seconds before/after)
    """
    totp = pyotp.TOTP(secret)
    # Verify with tolerance of 1 step (30 seconds)
    return totp.verify(code, valid_window=1)


def verify_backup_code(hashed_codes: List[str], code: str) -> Tuple[bool, Optional[int]]:
    """
    Verify a backup code against hashed codes
    Returns (is_valid, code_index) tuple
    """
    code_upper = code.upper().strip()
    for i, hashed in enumerate(hashed_codes):
        if hashlib.sha256(code_upper.encode()).hexdigest() == hashed:
            return True, i
    return False, None


def get_totp_provisioning_uri(secret: str, username: str) -> str:
    """
    Get the TOTP provisioning URI for QR code generation
    Format: otpauth://totp/Issuer:Username?secret=Secret&issuer=Issuer
    """
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=username, issuer_name="FIPAI")


def remove_used_backup_code(hashed_codes: List[str], index: int) -> List[str]:
    """Remove a used backup code from the list"""
    new_codes = hashed_codes.copy()
    if 0 <= index < len(new_codes):
        new_codes.pop(index)
    return new_codes
