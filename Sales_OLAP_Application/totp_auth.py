"""
PharmaTrack DW: Pure-Python RFC 6238 TOTP & Authenticator Verification Module
Zero external dependencies: uses standard library (hmac, hashlib, time, struct, base64, secrets).
Compatible with Google Authenticator, Microsoft Authenticator, and RFC 6238 compliant apps.
"""

import hmac
import hashlib
import time
import struct
import base64
import secrets
import urllib.parse
from werkzeug.security import generate_password_hash, check_password_hash


def generate_secret() -> str:
    """
    Generates a secure, cryptographically random 20-byte (160-bit) base32 secret.
    Standard RFC 6238 recommends 160-bit secret keys.
    """
    raw_bytes = secrets.token_bytes(20)
    return base64.b32encode(raw_bytes).decode("utf-8").rstrip("=")


def format_secret_for_display(secret: str) -> str:
    """
    Formats the secret into readable groups of 4 characters (e.g. ABCD EFGH 1234 ...).
    Makes manual typing into Google / Microsoft Authenticator much easier and less error-prone.
    """
    clean = (secret or "").strip().replace(" ", "").upper()
    return " ".join(clean[i : i + 4] for i in range(0, len(clean), 4))


def _normalize_secret(secret: str) -> bytes:
    """Pads and decodes a base32 secret string into bytes."""
    clean = (secret or "").strip().replace(" ", "").upper()
    padding_len = (8 - len(clean) % 8) % 8
    padded = clean + ("=" * padding_len)
    return base64.b32decode(padded, casefold=True)


def get_totp(secret: str, offset: int = 0, interval: int = 30) -> str:
    """
    Generates a 6-digit TOTP code for the given secret and time offset.
    offset=0 is current time step; offset=-1 is previous 30s; offset=1 is next 30s.
    """
    try:
        key = _normalize_secret(secret)
    except Exception:
        return ""

    time_step = (int(time.time()) // interval) + offset
    msg = struct.pack(">Q", time_step)
    digest = hmac.new(key, msg, hashlib.sha1).digest()

    offset_index = digest[19] & 0x0F
    code_int = struct.unpack(">I", digest[offset_index : offset_index + 4])[0] & 0x7FFFFFFF
    return str(code_int % 1000000).zfill(6)


def verify_totp(secret: str, user_code: str, window: int = 1, interval: int = 30) -> bool:
    """
    Validates a 6-digit TOTP code submitted by the user.
    Allows a time drift of +/- window intervals (default window=1 allows +/- 30 seconds).
    Uses constant-time comparison to protect against timing attacks.
    """
    if not secret or not user_code:
        return False

    clean_code = str(user_code).strip().replace(" ", "")
    if not clean_code.isdigit() or len(clean_code) != 6:
        return False

    for off in range(-window, window + 1):
        expected = get_totp(secret, offset=off, interval=interval)
        if expected and hmac.compare_digest(expected, clean_code):
            return True

    return False


def get_provisioning_uri(username: str, secret: str, issuer: str = "PharmaTrack DW") -> str:
    """
    Constructs an otpauth:// URL that can be encoded as a QR code for authenticator apps.
    Format: otpauth://totp/{issuer}:{username}?secret={secret}&issuer={issuer}&algorithm=SHA1&digits=6&period=30
    """
    label = f"{issuer}:{username}"
    params = {
        "secret": (secret or "").strip().replace(" ", "").upper(),
        "issuer": issuer,
        "algorithm": "SHA1",
        "digits": "6",
        "period": "30",
    }
    encoded_label = urllib.parse.quote(label)
    encoded_query = urllib.parse.urlencode(params)
    return f"otpauth://totp/{encoded_label}?{encoded_query}"


def generate_recovery_codes(count: int = 8) -> list:
    """
    Generates single-use alphanumeric emergency recovery codes.
    Formatted as XXXX-XXXX (e.g. 84B2-9F1A) for readability.
    """
    codes = []
    for _ in range(count):
        raw = secrets.token_hex(4).upper()
        formatted = f"{raw[:4]}-{raw[4:]}"
        codes.append(formatted)
    return codes


def normalize_recovery_code(code: str) -> str:
    """Normalizes a recovery code by stripping spaces and hyphens and capitalizing."""
    return (code or "").strip().replace("-", "").replace(" ", "").upper()


def hash_recovery_code(code: str) -> str:
    """
    Securely hashes a recovery code using Werkzeug PBKDF2/scrypt.
    Plain-text recovery codes are never stored in the database.
    """
    normalized = normalize_recovery_code(code)
    return generate_password_hash(normalized)


def verify_recovery_code(user_code: str, stored_hash: str) -> bool:
    """Validates a user-supplied recovery code against a stored hash."""
    if not user_code or not stored_hash:
        return False
    normalized = normalize_recovery_code(user_code)
    return check_password_hash(stored_hash, normalized)

