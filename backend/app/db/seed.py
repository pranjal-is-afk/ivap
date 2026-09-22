"""Idempotent database bootstrap: tables, default users, demo cameras + zones."""
from __future__ import annotations

import logging

from app.core.security import hash_password
from app.db.models import Camera, Role, User, UserSecret, Zone
from app.db.session import SessionLocal, init_db

log = logging.getLogger("ibvap.seed")

DEFAULT_USERS = [
    ("admin", "Admin", Role.admin, "ibvap-admin-2026"),
    ("operator", "Duty Operator", Role.operator, "ibvap-operator-2026"),
    ("viewer", "Command Viewer", Role.viewer, "ibvap-viewer-2026"),
]


def seed() -> None:
    init_db()
    db = SessionLocal()
    try:
        # ---- users
        for username, display, role, password in DEFAULT_USERS:
            if db.query(User).filter_by(username=username).one_or_none() is None:
                u = User(username=username, display_name=display, role=role)
                db.add(u)
                db.flush()
                db.add(UserSecret(user_id=u.id, password_hash=hash_password(password)))
                log.info("seeded user %s (%s)", username, role.value)

        # ---- demo cameras (local video files = SIMULATED feeds, labelled in UI)
        demo_cams = [
            {
                "name": "BOP-NORTH Gate",
                "location": "Border Out Post North — vehicle gate",
                "source": "assets/videos/street.mp4",
                "fps_target": 8.0,
                "notes": "Demo: recorded footage processed by the real pipeline",
            },
            {
                "name": "BOP-NORTH Perimeter",
                "location": "Border Out Post North — fence line",
                "source": "assets/videos/people.mp4",
                "fps_target": 8.0,
                "notes": "Demo: recorded footage processed by the real pipeline",
            },
        ]
        for cam_spec in demo_cams:
            if db.query(Camera).filter_by(name=cam_spec["name"]).one_or_none() is None:
                db.add(Camera(**cam_spec))
        db.flush()

        cam1 = db.query(Camera).filter_by(name="BOP-NORTH Gate").one()
        cam2 = db.query(Camera).filter_by(name="BOP-NORTH Perimeter").one()

        if db.query(Zone).filter_by(camera_id=cam1.id, name="Vehicle Inspection Bay").one_or_none() is None:
            db.add(
                Zone(
                    camera_id=cam1.id,
                    name="Vehicle Inspection Bay",
                    zone_type="restricted",
                    polygon=[
                        {"x": 0.08, "y": 0.52},
                        {"x": 0.50, "y": 0.46},
                        {"x": 0.55, "y": 0.92},
                        {"x": 0.04, "y": 0.94},
                    ],
                )
            )
        if db.query(Zone).filter_by(camera_id=cam2.id, name="Fence Hold Area").one_or_none() is None:
            db.add(
                Zone(
                    camera_id=cam2.id,
                    name="Fence Hold Area",
                    zone_type="loiter",
                    min_dwell_seconds=5,
                    polygon=[
                        {"x": 0.58, "y": 0.30},
                        {"x": 0.90, "y": 0.34},
                        {"x": 0.86, "y": 0.60},
                        {"x": 0.55, "y": 0.56},
                    ],
                )
            )
        db.commit()
        log.info("seed complete")
    finally:
        db.close()
