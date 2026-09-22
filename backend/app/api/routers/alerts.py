"""Alert search, acknowledge/dismiss workflow, and audit-chain verification."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session as OrmSession, joinedload

from app.api.deps import get_current_user, require_role
from app.db.models import Alert, AlertStatus, Camera, Event, Role, User
from app.db.session import get_db
from app.services.audit import append_entry, verify_chain

router = APIRouter(prefix="/alerts", tags=["alerts"])


def _alert_payload(a: Alert) -> dict:
    ev = a.event
    cam = ev.camera
    det = ev.details or {}
    snap = ev.frame_snapshot
    clip = det.get("clip")
    return {
        "id": a.id,
        "severity": a.severity,
        "status": a.status.value,
        "created_at": a.created_at.isoformat(),
        "acknowledged_by": a.ack_user.username if a.ack_user else None,
        "acknowledged_at": a.acknowledged_at.isoformat() if a.acknowledged_at else None,
        "event": {
            "id": ev.id,
            "kind": ev.kind.value,
            "occurred_at": ev.occurred_at.isoformat(),
            "details": det,
            "camera_id": ev.camera_id,
            "camera_name": cam.name if cam else "unknown",
            "location": cam.location if cam else "",
            "zone_id": ev.zone_id,
            "snapshot_url": f"/api/evidence/{snap}" if snap else None,
            "clip_url": f"/api/evidence/{clip}" if clip else None,
        },
    }


@router.get("")
def list_alerts(
    camera_id: str | None = None,
    severity: str | None = None,
    alert_status: str | None = None,
    kind: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    q: str | None = None,
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    query = (
        db.query(Alert)
        .options(joinedload(Alert.event).joinedload(Event.camera))
        .join(Event)
        .order_by(Alert.created_at.desc())
    )
    if camera_id:
        query = query.filter(Event.camera_id == camera_id)
    if severity:
        query = query.filter(Alert.severity == severity)
    if alert_status:
        query = query.filter(Alert.status == AlertStatus(alert_status))
    if kind:
        query = query.filter(Event.kind == kind)
    if since:
        query = query.filter(Alert.created_at >= since)
    if until:
        query = query.filter(Alert.created_at <= until)
    if q:
        like = f"%{q.lower()}%"
        query = query.filter(
            func.lower(Event.details["zone_name"].astext).like(like)
            | func.lower(Event.details["label"].astext).like(like)
            | func.lower(Camera.name).like(like)
        )
    total = query.count()
    rows = query.offset(offset).limit(limit).all()
    return {"total": total, "items": [_alert_payload(a) for a in rows]}


@router.post("/{alert_id}/acknowledge")
def acknowledge(alert_id: str, user: User = Depends(require_role(Role.operator)), db: OrmSession = Depends(get_db)):
    a = db.get(Alert, alert_id)
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "alert not found")
    if a.status == AlertStatus.new:
        a.status = AlertStatus.acknowledged
        a.acknowledged_by = user.id  # FK to users.id; username resolved for display
        a.acknowledged_at = datetime.now(timezone.utc)
        try:
            append_entry(db, actor=user.username, action="alert_acknowledged", alert_id=a.id)
        except Exception:
            pass
        db.commit()
    return {"ok": True, "status": a.status.value}


@router.post("/{alert_id}/dismiss")
def dismiss(alert_id: str, user: User = Depends(require_role(Role.operator)), db: OrmSession = Depends(get_db)):
    a = db.get(Alert, alert_id)
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "alert not found")
    a.status = AlertStatus.dismissed
    try:
        append_entry(db, actor=user.username, action="alert_dismissed", alert_id=a.id)
    except Exception:
        pass
    db.commit()
    return {"ok": True, "status": a.status.value}


@router.get("/audit/verify")
def audit_verify(user: User = Depends(get_current_user), db: OrmSession = Depends(get_db)):
    """Honest tamper-evidence check over the hash-chained ledger."""
    return verify_chain(db)
