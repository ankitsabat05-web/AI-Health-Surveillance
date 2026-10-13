from __future__ import annotations

import logging
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from pydantic import SecretStr

from app.config import settings

logger = logging.getLogger("health_surveillance.encryption")


class EncryptionError(Exception):
    """Raised when sensitive data cannot be encrypted or decrypted."""


@lru_cache(maxsize=1)
def _get_fernet() -> Fernet:
    """Load the encryption key from application settings."""
    key_setting = getattr(settings, "HEALTH_DATA_ENCRYPTION_KEY", None)

    if isinstance(key_setting, SecretStr):
        key = key_setting.get_secret_value()
    elif isinstance(key_setting, str):
        key = key_setting
    else:
        key = None

    if not key:
        raise EncryptionError("HEALTH_DATA_ENCRYPTION_KEY is not configured.")

    try:
        return Fernet(key.encode("utf-8"))
    except (ValueError, TypeError):
        raise EncryptionError(
            "HEALTH_DATA_ENCRYPTION_KEY is invalid. "
            "Generate a valid Fernet key and configure it securely."
        ) from None


def encrypt_text(plaintext: str) -> str:
    """Encrypt a string and return a URL-safe Base64 token."""
    if not isinstance(plaintext, str):
        raise TypeError("plaintext must be a string")

    try:
        encrypted = _get_fernet().encrypt(plaintext.encode("utf-8"))
        return encrypted.decode("utf-8")
    except EncryptionError:
        raise
    except Exception:
        logger.error("Sensitive-data encryption failed.")
        raise EncryptionError("Unable to encrypt sensitive data.") from None


def decrypt_text(ciphertext: str) -> str:
    """Decrypt a Fernet token and verify its authentication."""
    if not isinstance(ciphertext, str) or not ciphertext:
        raise EncryptionError("Invalid encrypted data.")

    try:
        decrypted = _get_fernet().decrypt(ciphertext.encode("utf-8"))
        return decrypted.decode("utf-8")
    except (InvalidToken, UnicodeDecodeError, ValueError, TypeError):
        logger.warning("Sensitive-data decryption failed.")
        raise EncryptionError(
            "Unable to decrypt data. The ciphertext or encryption key "
            "may be invalid."
        ) from None
    except EncryptionError:
        raise
    except Exception:
        logger.error("Sensitive-data decryption failed.")
        raise EncryptionError("Unable to decrypt sensitive data.") from None


def is_encrypted_token(value: str) -> bool:
    """Check whether a value resembles a Fernet token."""
    if not isinstance(value, str) or not value:
        return False

    try:
        _get_fernet().decrypt(value.encode("utf-8"))
        return True
    except (InvalidToken, ValueError, TypeError, EncryptionError):
        return False
