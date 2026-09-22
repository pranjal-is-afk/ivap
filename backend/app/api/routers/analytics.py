"""Analytics: real SQL aggregates only. No fabricated numbers anywhere."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session as OrmSession

from app.api.deps import get_current_user
from app.db.models import Alert, AlertStatus, Camera, Event, EventKind, Face, Plate, Track
from app.db.session import get_db

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/summary")
def summary(user=Depends(get_current_user), db: OrmSession = Depends(get_db)):
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(hours=24)

    return {
        "total_alerts": db.query(func.count(Alert.id)).scalar() or 0,
        "alerts_24h": db.query(func.count(Alert.id)).filter(Alert.created_at >= day_ago).scalar() or 0,
        "open_alerts": db.query(func.count(Alert.id)).filter(Alert.status == AlertStatus.new).scalar() or 0,
        "cameras": db.query(func.count(Camera.id)).scalar() or 0,
        "tracks": db.query(func.count(Track.id)).scalar() or 0,
        "events": db.query(func.count(Event.id)).scalar() or 0,
        "plates": db.query(func.count(Plate.id)).scalar() or 0,
        "valid_plates": db.query(func.count(Plate.id)).filter(Plate.is_valid_format.is_(True)).scalar() or 0,
        "faces": db.query(func.count(Face.id)).scalar() or 0,
    }


@router.get("/alerts_over_time")
def alerts_over_time(
    hours: int = Query(default=24, ge=1, le=720),
    bucket: str = Query(default="hour", pattern="^(hour|day)$"),
    user=Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    """Alert counts bucketed by hour or day (real GROUP BY date_trunc)."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    trunc = func.date_trunc(bucket, Alert.created_at)
    rows = (
        db.query(trunc.label("b"), func.count(Alert.id))
        .filter(Alert.created_at >= since)
        .group_by(trunc)
        .order_by(trunc)
        .all()
    )
    return [{"bucket": b.isoformat(), "count": c} for b, c in rows]


@router.get("/alerts_by_kind")
def alerts_by_kind(user=Depends(get_current_user), db: OrmSession = Depends(get_db)):
    rows = (
        db.query(Event.kind, func.count(Alert.id))
        .join(Event, Alert.event_id == Event.id)
        .group_by(Event.kind)
        .all()
    )
    return [{"kind": k.value if hasattr(k, "value") else str(k), "count": c} for k, c in rows]


@router.get("/alerts_by_camera")
def alerts_by_camera(user=Depends(get_current_user), db: OrmSession = Depends(get_db)):
    rows = (
        db.query(Camera.name, func.count(Alert.id))
        .join(Event, Alert.event_id == Event.id)
        .join(Camera, Event.camera_id == Camera.id)
        .group_by(Camera.name)
        .all()
    )
    return [{"camera": name, "count": c} for name, c in rows]


@router.get("/events_by_hour")
def events_by_hour(
    hours: int = Query(default=24, ge=1, le=720),
    user=Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    """Event volume by local hour — activity pattern (loitering/night analysis)."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = (
        db.query(func.extract("hour", Event.occurred_at).label("h"), func.count(Event.id))
        .filter(Event.occurred_at >= since)
        .group_by("h")
        .order_by("h")
        .all()
    )
    return [{"hour": int(h), "count": c} for h, c in rows]


@router.get("/plates/recent")
def recent_plates(
    limit: int = Query(default=50, le=200),
    valid_only: bool = False,
    user=Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    q = db.query(Plate).order_by(Plate.seen_at.desc())
    if valid_only:
        q = q.filter(Plate.is_valid_format.is_(True))
    return [
        {
            "id": p.id,
            "text": p.text,
            "confidence": p.confidence,
            "is_valid_format": p.is_valid_format,
            "seen_at": p.seen_at.isoformat(),
            "camera_id": p.camera_id,
            "snapshot": f"/api/evidence/{p.snapshot}" if p.snapshot else None,
        }
        for p in q.limit(limit).all()
    ]


@router.get("/fps")
def measured_fps(user=Depends(get_current_user)):
    """Live measured FPS/latency straight from the running pipeline threads."""
    from app.main import worker

    return worker.status()
