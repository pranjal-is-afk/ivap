"""Reset demo data: delete events/alerts/tracks/plates/faces + evidence files.

Keeps users, cameras and zones. Usage:
    .venv\\Scripts\\python.exe backend\\app\\db\\reset_demo_data.py
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core.config import settings  # noqa: E402
from app.db.models import Alert, Event, Face, Plate, Track  # noqa: E402
from app.db.session import SessionLocal, init_db  # noqa: E402


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        n_alerts = db.query(Alert).delete()
        n_events = db.query(Event).delete()
        n_tracks = db.query(Track).delete()
        n_plates = db.query(Plate).delete()
        n_faces = db.query(Face).delete()
        db.commit()
        print(f"deleted: {n_alerts} alerts, {n_events} events, {n_tracks} tracks, {n_plates} plates, {n_faces} faces")
    finally:
        db.close()

    ev = settings.evidence_path
    if ev.exists():
        shutil.rmtree(ev)
        ev.mkdir(parents=True, exist_ok=True)
        print(f"cleared evidence dir: {ev}")


if __name__ == "__main__":
    main()
