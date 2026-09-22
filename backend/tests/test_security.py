"""Password hashing + JWT + RBAC ordering tests."""
import time

import jwt
import pytest

from app.core.config import settings
from app.core.security import create_access_token, decode_token, hash_password, role_at_least, verify_password


def test_password_roundtrip():
    h = hash_password("s3cret-pass")
    assert h != "s3cret-pass"
    assert verify_password("s3cret-pass", h)
    assert not verify_password("wrong", h)


def test_hash_is_salted():
    assert hash_password("same") != hash_password("same")


def test_jwt_roundtrip():
    tok = create_access_token("user-123", "admin")
    payload = decode_token(tok)
    assert payload["sub"] == "user-123"
    assert payload["role"] == "admin"
    assert payload["iss"] == "ibvap"


def test_jwt_rejects_tampering():
    tok = create_access_token("user-123", "admin")
    with pytest.raises(jwt.PyJWTError):
        decode_token(tok + "x")
    with pytest.raises(jwt.PyJWTError):
        decode_token(tok[:-3] + "aaa")


def test_jwt_expiry_is_enforced():
    tok = create_access_token("u", "viewer", extra={})
    payload = jwt.decode(tok, options={"verify_exp": False}, algorithms=["HS256"], issuer="ibvap", key=settings.jwt_secret)
    assert payload["exp"] > time.time()


def test_role_ordering():
    assert role_at_least("admin", "operator")
    assert role_at_least("admin", "viewer")
    assert role_at_least("operator", "operator")
    assert role_at_least("operator", "viewer")
    assert not role_at_least("viewer", "operator")
    assert not role_at_least("viewer", "admin")
