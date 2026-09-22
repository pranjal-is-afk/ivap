"""Serve evidence artifacts (snapshots/clips) with path-traversal protection.

Accepts the JWT either as an Authorization header or a ?token= query param,
because <img>/<video> tags cannot set headers.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

router = APIRouter(prefix="/evidence", tags=["evidence"])


def _user_from_request(request: Request, token: str | None):
    from app.core.env_flags import is_auth_disabled
    from app.core.security import decode_token
    from app.db.models import User
    from app.db.session import SessionLocal

    if token:
        payload = decode_token(token)
    elif request.headers.get("authorization", "").lower().startswith("bearer "):
        payload = decode_token(request.headers["authorization"].split(" ", 1)[1])
    elif is_auth_disabled():
        return None  # dev mode
    else:
        raise HTTPException(status_code=401, detail="token required")
    db = SessionLocal()
    try:
        user = db.get(User, payload.get("sub"))
        if user is None or not user.is_active:
            raise HTTPException(status_code=401, detail="invalid user")
        return user
    finally:
        db.close()


@router.get("/{rel_path:path}")
def get_evidence(rel_path: str, token: str | None = None, user=Depends(_user_from_request)):
    from app.main import app as fastapi_app

    from app.services.evidence import EvidenceStore

    store: EvidenceStore = fastapi_app.state.evidence_store
    path = store.resolve(rel_path)
    if path is None:
        raise HTTPException(status_code=404, detail="evidence not found")
    return FileResponse(path, media_type=store.media_type(path))
