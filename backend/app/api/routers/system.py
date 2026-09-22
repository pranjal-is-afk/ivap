"""System status endpoints — every number here is measured, not hardcoded."""
from __future__ import annotations

import os
import platform
import time

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import db_health
from app.services import vision

router = APIRouter(prefix="/system", tags=["system"])

_STARTED_AT = time.time()


@router.get("/status")
def status(user=Depends(get_current_user)):
    from app.main import worker

    db_ok = db_health.check()
    cam_stats = worker.status()
    return {
        "app": {"name": settings.app_name, "version": settings.version, "uptime_s": int(time.time() - _STARTED_AT)},
        "python": platform.python_version(),
        "platform": platform.platform(),
        "db": {"status": db_health.status, "ok": db_ok},
        "gpu": {
            # IBVAP_CPU_ONLY=1 (cloud) forces the CPU path; report it honestly
            "cuda_available": vision.cuda_available() and os.environ.get("IBVAP_CPU_ONLY", "").strip() != "1",
            "device": "cpu" if os.environ.get("IBVAP_CPU_ONLY", "").strip() == "1" else vision.device_name(),
        },
        "cameras": cam_stats,
        "auth_note": "JWT + RBAC active (admin/operator/viewer)",
    }


@router.get("/pipeline")
def pipeline(user=Depends(get_current_user)):
    """Measured per-camera pipeline performance (real FPS / latency)."""
    from app.main import worker

    stats = worker.status()
    return {
        camera_id: {
            "alive": s["alive"],
            "fps": s["fps"],
            "latency_ms": s["latency_ms"],
            "status": s["meta"].get("status"),
            "error": s["meta"].get("error"),
            "recoveries": s["meta"].get("recoveries", 0),
        }
        for camera_id, s in stats.items()
    }
