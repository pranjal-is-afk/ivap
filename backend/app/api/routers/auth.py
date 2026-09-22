"""Authentication: JWT login, current user, admin user management."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as OrmSession

from app.api.deps import get_current_user, require_role
from app.core.security import create_access_token, hash_password, verify_password
from app.db.models import Role, User, UserSecret
from app.db.session import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    username: str
    display_name: str


class UserOut(BaseModel):
    id: str
    username: str
    display_name: str
    role: str
    is_active: bool

    class Config:
        from_attributes = True


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: OrmSession = Depends(get_db)):
    user = db.query(User).filter_by(username=body.username).one_or_none()
    # Constant-ish behavior regardless of user existence
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    secret = db.get(UserSecret, user.id)
    if secret is None or not verify_password(body.password, secret.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    token = create_access_token(subject=user.id, role=user.role.value)
    return TokenResponse(
        access_token=token, role=user.role.value, username=user.username, display_name=user.display_name
    )


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.get("/users", response_model=list[UserOut])
def list_users(user: User = Depends(require_role(Role.admin)), db: OrmSession = Depends(get_db)):
    return db.query(User).all()


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(default="", max_length=128)
    role: Role


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(body: CreateUserRequest, user: User = Depends(require_role(Role.admin)), db: OrmSession = Depends(get_db)):
    if db.query(User).filter_by(username=body.username).one_or_none() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "username exists")
    u = User(username=body.username, display_name=body.display_name, role=body.role)
    db.add(u)
    db.flush()
    db.add(UserSecret(user_id=u.id, password_hash=hash_password(body.password)))
    db.commit()
    db.refresh(u)
    return u
