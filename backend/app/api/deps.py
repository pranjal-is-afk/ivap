"""FastAPI dependencies: current user extraction, RBAC enforcement."""
from __future__ import annotations

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session as OrmSession

from app.core.env_flags import is_auth_disabled
from app.core.security import role_at_least
from app.db.models import Role, User
from app.db.session import get_db

bearer_scheme = HTTPBearer(auto_error=True)


def _dev_user_for_role(role: Role) -> User:
    # Construct transient user object; never persisted.
    u = User()
    u.id = f"dev:{role.value}"
    u.username = f"dev-{role.value}"
    u.display_name = f"DEV {role.value.upper()} (auth disabled)"
    u.role = role
    u.is_active = True
    return u


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: OrmSession = Depends(get_db),
) -> User:
    """Resolve the JWT bearer to a real DB user. 401 on any failure."""
    if is_auth_disabled():
        # Explicitly flagged dev mode (requires two env flags); map token-less
        # requests to a viewer so RBAC still applies for dangerous actions.
        return _dev_user_for_role(Role.viewer)

    token = credentials.credentials
    try:
        payload = jwt.decode(
            token,
            _secret(),
            algorithms=["HS256"],
            issuer="ibvap",
        )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired") from exc
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    user = db.get(User, payload.get("sub"))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User inactive or unknown")
    return user


def _secret() -> str:
    from app.core.config import settings as s

    return s.jwt_secret


def require_role(minimum: Role):
    """Dependency factory: enforce minimum role for the endpoint."""

    def _enforce(user: User = Depends(get_current_user)) -> User:
        if not role_at_least(user.role.value, minimum.value):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires {minimum.value} role",
            )
        return user

    return _enforce
