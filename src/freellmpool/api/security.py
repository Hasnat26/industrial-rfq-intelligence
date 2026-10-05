"""Password hashing and session-token primitives for the procurement SaaS API.

Stdlib-only by design: PBKDF2-HMAC-SHA256 with a per-password salt for
credentials, and opaque random bearer tokens stored only as SHA-256 digests.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

PBKDF2_ITERATIONS = 390_000
SALT_BYTES = 16
TOKEN_BYTES = 32
_ALGORITHM = "pbkdf2_sha256"


def hash_password(password: str) -> str:
    """Return a salted PBKDF2 hash. Plaintext passwords are never persisted."""
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    salt_b64 = base64.urlsafe_b64encode(salt).decode("ascii")
    digest_b64 = base64.urlsafe_b64encode(digest).decode("ascii")
    return f"{_ALGORITHM}${PBKDF2_ITERATIONS}${salt_b64}${digest_b64}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time verification of a password against a stored hash."""
    parts = stored.split("$")
    if len(parts) != 4:
        return False
    algorithm, iterations_raw, salt_b64, digest_b64 = parts
    if algorithm != _ALGORITHM:
        return False
    try:
        iterations = int(iterations_raw)
        salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_b64.encode("ascii"))
    except ValueError:
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(candidate, expected)


def new_session_token() -> str:
    """Issue a cryptographically random bearer token."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_session_token(token: str) -> str:
    """Reduce a bearer token to the digest persisted in auth_sessions."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
