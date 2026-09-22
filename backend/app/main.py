"""HTTP + WebSocket API for IBVAP."""
from __future__ import annotations

import asyncio
import logging
import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import (
    alerts,
    analytics,
    auth,
    cameras,
    evidence,
    live,
    system,
    zones,
)
from app.core.config import REPO_ROOT, settings
from app.db.seed import seed
from app.db.session import db_health, init_db
from app.pipeline.engine import IngestWorker
from app.services import vision
from app.services.evidence import EvidenceStore
from app.services.ws_manager import ws_manager

log = logging.getLogger("ibvap.main")

# Global singletons for the pipeline + evidence store
worker = IngestWorker(evidence_store=EvidenceStore(settings.evidence_path))
worker.set_ws_manager(ws_manager)


def _camera_job_from_row(c) -> dict:
    """DB row -> the camera job dict the pipeline threads consume."""
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
            for z in c.zones
        ],
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- startup
    init_db()
    seed()
    ws_manager.set_loop(asyncio.get_running_loop())
    app.state.worker = worker
    app.state.evidence_store = worker.evidence_store

    # auto-start enabled cameras (real pipeline threads)
    from app.db.models import Camera
    from app.db.session import SessionLocal

    # warm models in the background so the first vehicle/person doesn't pay
    # the load cost (EasyOCR cold start is ~20s otherwise)
    threading.Thread(target=vision.warmup, daemon=True, name="model-warmup").start()

    # auto-start every enabled camera (real pipeline threads). In a cloud/
    # tunnel deployment (IBVAP_DEMO=1) a cold container comes up with live
    # simulated feeds already running; locally this restores your last session.
    with SessionLocal() as db:
        for c in db.query(Camera).filter_by(enabled=True).all():
            if not worker.has_camera(c.id):
                worker.start_camera(_camera_job_from_row(c))

    yield

    # --- shutdown
    worker.stop_all()
    log.info("shutdown complete; GPU memory released")


app = FastAPI(title=settings.app_name, version=settings.version, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (auth.router, cameras.router, zones.router, alerts.router, analytics.router, system.router, live.router, evidence.router):
    app.include_router(router, prefix="/api")


@app.get("/api/health")
def health():
    db_ok = db_health.check()
    return {
        "status": "ok" if db_ok else "degraded",
        "db": db_health.status,
        "version": settings.version,
    }


# ---------------------------------------------------------------------------
# Single-origin static serving of the built frontend (frontend/dist).
#
# In dev, Vite (:5173) proxies /api to this server. In any single-process
# deployment (cloud container, tunnel demo, kiosk) we serve the built app
# from the same origin, so auth, MJPEG and WebSockets all just work without
# CORS. Enabled only when the dist folder exists — never in dev.
# ---------------------------------------------------------------------------
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

_dist = REPO_ROOT / "frontend" / "dist"
if _dist.is_dir() and (_dist / "index.html").is_file():
    app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="static-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        # never shadow API or WS routes
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="not found")
        candidate = (_dist / full_path).resolve()
        # path-traversal guard: stay inside dist
        if str(candidate).startswith(str(_dist.resolve())) and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_dist / "index.html")  # SPA fallback (hash router)

    log.info("serving frontend from %s", _dist)
