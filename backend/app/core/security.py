"""Security utilities: password hashing, JWT creation/verification."""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from typing import Any

import jwt

from app.core.config import settings
from app.core.env_flags import is_auth_disabled
from app.db.models import Role

# ---- PBKDF2-HMAC-SHA256 password hashing (no native deps, constant-time verify)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    iterations = 200_000
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_hex, hash_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iters))
        return hmac.compare_digest(dk.hex(), hash_hex)
    except (ValueError, TypeError):
        return False


# ---- JWT


def create_access_token(subject: str, role: str, extra: dict[str, Any] | None = None) -> str:
    now = time.time()
    payload = {
        "sub": subject,
        "role": role,
        "iat": int(now),
        "exp": int(now + settings.jwt_expire_hours * 3600),
        "iss": "ibvap",
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    """Raises jwt.PyJWTError subclasses on any problem."""
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm], issuer="ibvap")
    if is_auth_disabled():
        return payload  # still verify shape, but no expiry enforcement
    return payload


# ---- role helpers


class RolePermissionError(PermissionError):
    pass


def role_at_least(actual: str, minimum: str) -> bool:
    order = {Role.viewer: 0, Role.operator: 1, Role.admin: 2}
    return order.get(Role(actual), -1) >= order[Role(minimum)]


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)
