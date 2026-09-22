"""Zone (virtual fence) CRUD. Polygon is normalized [0..1] and validated."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as OrmSession

from app.api.deps import get_current_user, require_role
from app.db.models import Camera, Role, User, Zone
from app.db.session import get_db
from app.pipeline.zones import ZoneGeometryError, validate_polygon

router = APIRouter(prefix="/zones", tags=["zones"])


class Point(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class ZoneIn(BaseModel):
    camera_id: str
    name: str = Field(min_length=1, max_length=128)
    zone_type: str = Field(default="restricted", pattern="^(restricted|loiter|entry)$")
    polygon: list[Point] = Field(min_length=3, max_length=24)
    min_dwell_seconds: int = Field(default=0, ge=0, le=3600)
    active: bool = True


class ZoneOut(ZoneIn):
    id: str

    class Config:
        from_attributes = True


@router.get("")
def list_zones(camera_id: str | None = None, user: User = Depends(get_current_user), db: OrmSession = Depends(get_db)):
    q = db.query(Zone)
    if camera_id:
        q = q.filter_by(camera_id=camera_id)
    return q.all()


@router.post("", status_code=201)
def create_zone(body: ZoneIn, user: User = Depends(require_role(Role.operator)), db: OrmSession = Depends(get_db)):
    cam = db.get(Camera, body.camera_id)
    if cam is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "camera not found")
    try:
        validate_polygon([p.model_dump() for p in body.polygon], 1920, 1080)
    except ZoneGeometryError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    z = Zone(**body.model_dump())
    db.add(z)
    db.commit()
    _reload_camera(db, body.camera_id)
    return z


@router.patch("/{zone_id}")
def update_zone(zone_id: str, body: ZoneIn, user: User = Depends(require_role(Role.operator)), db: OrmSession = Depends(get_db)):
    z = db.get(Zone, zone_id)
    if z is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "zone not found")
    try:
        validate_polygon([p.model_dump() for p in body.polygon], 1920, 1080)
    except ZoneGeometryError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    for k, v in body.model_dump().items():
        setattr(z, k, v)
    db.commit()
    _reload_camera(db, z.camera_id)
    return z


@router.delete("/{zone_id}", status_code=204)
def delete_zone(zone_id: str, user: User = Depends(require_role(Role.operator)), db: OrmSession = Depends(get_db)):
    z = db.get(Zone, zone_id)
    if z is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "zone not found")
    cid = z.camera_id
    db.delete(z)
    db.commit()
    _reload_camera(db, cid)


def _reload_camera(db: OrmSession, camera_id: str) -> None:
    """Live reload: restart the pipeline thread so zone changes apply instantly."""
    from app.main import worker

    c = db.get(Camera, camera_id)
    if c is None or not c.enabled:
        return
    worker.stop_camera(c.id)
    worker.start_camera(
        {
            "id": c.id,
            "name": c.name,
            "source": c.source,
            "fps_target": c.fps_target,
            "zones": [
                {
                    "id": zz.id,
                    "name": zz.name,
                    "zone_type": zz.zone_type,
                    "polygon": zz.polygon,
                    "min_dwell_seconds": zz.min_dwell_seconds,
                    "active": zz.active,
                }
                for zz in db.query(Zone).filter_by(camera_id=c.id).all()
            ],
        }
    )
