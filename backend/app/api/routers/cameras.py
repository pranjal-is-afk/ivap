"""Camera CRUD. Changes restart the corresponding pipeline thread live."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as OrmSession

from app.api.deps import get_current_user, require_role
from app.core.config import REPO_ROOT
from app.db.models import Camera, Role, User, Zone
from app.db.session import get_db

router = APIRouter(prefix="/cameras", tags=["cameras"])


class CameraIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    location: str = Field(default="", max_length=256)
    source: str = Field(min_length=1, max_length=512)
    fps_target: float = Field(default=10.0, gt=0, le=30)
    notes: str = Field(default="", max_length=2000)
    enabled: bool = True


class CameraOut(CameraIn):
    id: str
    is_simulated: bool

    class Config:
        from_attributes = True


def _camera_payload(c: Camera) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "location": c.location,
        "source": c.source,
        "fps_target": c.fps_target,
        "notes": c.notes,
        "enabled": c.enabled,
        "is_simulated": c.source and not c.source.lower().startswith(("rtsp://", "rtmp://", "http://", "https://")),
    }


@router.get("")
def list_cameras(user: User = Depends(get_current_user), db: OrmSession = Depends(get_db)):
    return [_camera_payload(c) for c in db.query(Camera).order_by(Camera.created_at).all()]


@router.post("", status_code=201)
def create_camera(body: CameraIn, user: User = Depends(require_role(Role.admin)), db: OrmSession = Depends(get_db)):
    c = Camera(**body.model_dump())
    db.add(c)
    db.commit()
    db.refresh(c)
    from app.main import worker

    if c.enabled:
        worker.start_camera(_runtime_camera(db, c))
    return _camera_payload(c)


def _runtime_camera(db: OrmSession, c: Camera) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "source": c.source,
        "fps_target": c.fps_target,
        "zones": [
            {
                "id": z.id,
                "name": z.name,
                "zone_type": z.zone_type,
                "polygon": z.polygon,
                "min_dwell_seconds": z.min_dwell_seconds,
                "active": z.active,
            }
            for z in db.query(Zone).filter_by(camera_id=c.id).all()
        ],
    }


@router.patch("/{camera_id}")
def update_camera(camera_id: str, body: CameraIn, user: User = Depends(require_role(Role.admin)), db: OrmSession = Depends(get_db)):
    c = db.get(Camera, camera_id)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "camera not found")
    for k, v in body.model_dump().items():
        setattr(c, k, v)
    db.commit()
    from app.main import worker

    worker.stop_camera(c.id)
    if c.enabled:
        worker.start_camera(_runtime_camera(db, c))
    return _camera_payload(c)


@router.delete("/{camera_id}", status_code=204)
def delete_camera(camera_id: str, user: User = Depends(require_role(Role.admin)), db: OrmSession = Depends(get_db)):
    c = db.get(Camera, camera_id)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "camera not found")
    from app.main import worker

    worker.stop_camera(c.id)
    db.delete(c)
    db.commit()


@router.post("/upload")
def upload_video(
    file: UploadFile = File(...),
    user: User = Depends(require_role(Role.admin)),
):
    """Upload a surveillance video file for simulated/demo ingestion."""
    clean_name = os.path.basename(file.filename or "footage.mp4").replace(" ", "_")
    if not clean_name.lower().endswith((".mp4", ".avi", ".mov", ".mkv")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "File must be an MP4, AVI, MOV, or MKV video")

    videos_dir = REPO_ROOT / "assets" / "videos"
    videos_dir.mkdir(parents=True, exist_ok=True)
    dest_path = videos_dir / clean_name

    try:
        with open(dest_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as exc:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Upload write failed: {exc}")

    rel_path = f"assets/videos/{clean_name}"
    return {"filename": clean_name, "source": rel_path}

