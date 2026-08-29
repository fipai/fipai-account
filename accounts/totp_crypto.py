"""Authenticated, versioned encryption for TOTP seeds.

Keys are supplied by Django settings from the deployment secret manager. Stored
values carry only a format version and key id so keys can be rotated without
placing key material in the database.
"""
from __future__ import annotations

import re

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


PREFIX = "enc:v1:"
KEY_ID_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,128}")


class TOTPSecretEncryptionError(ValueError):
    """Raised when a TOTP seed cannot be safely encrypted or decrypted."""


def is_encrypted_totp_secret(value: str) -> bool:
    return isinstance(value, str) and value.startswith(PREFIX)


def get_totp_secret_key_id(ciphertext: str) -> str:
    """Return a validated key id without exposing any ciphertext material."""
    if not isinstance(ciphertext, str) or not ciphertext:
        raise TOTPSecretEncryptionError("TOTP secret is unavailable.")
    if not is_encrypted_totp_secret(ciphertext):
        raise TOTPSecretEncryptionError("Unencrypted TOTP secrets are not accepted.")
    try:
        key_id, token = ciphertext[len(PREFIX):].split(":", 1)
    except ValueError as exc:
        raise TOTPSecretEncryptionError("TOTP secret ciphertext is malformed.") from exc
    if not KEY_ID_PATTERN.fullmatch(key_id) or not token:
        raise TOTPSecretEncryptionError("TOTP secret ciphertext is malformed.")
    return key_id


def encrypt_totp_secret(secret: str) -> str:
    """Encrypt a non-empty plaintext seed with the active key."""
    if not isinstance(secret, str) or not secret:
        raise TOTPSecretEncryptionError("TOTP secret must be a non-empty string.")

    key_id = settings.TOTP_ENCRYPTION_KEY_ID
    key = settings.TOTP_ENCRYPTION_KEYRING.get(key_id)
    if not key:
        raise TOTPSecretEncryptionError("The active TOTP encryption key is unavailable.")

    token = Fernet(key.encode("ascii")).encrypt(secret.encode("utf-8")).decode("ascii")
    return f"{PREFIX}{key_id}:{token}"


def decrypt_totp_secret(ciphertext: str) -> str:
    """Decrypt a versioned seed and fail closed for plaintext or unknown keys."""
    key_id = get_totp_secret_key_id(ciphertext)
    token = ciphertext[len(PREFIX) + len(key_id) + 1:]

    key = settings.TOTP_ENCRYPTION_KEYRING.get(key_id)
    if not key:
        raise TOTPSecretEncryptionError("The TOTP decryption key is unavailable.")

    try:
        plaintext = Fernet(key.encode("ascii")).decrypt(token.encode("ascii"))
        return plaintext.decode("utf-8")
    except (InvalidToken, UnicodeDecodeError, ValueError) as exc:
        raise TOTPSecretEncryptionError("TOTP secret decryption failed.") from exc
