"""Evidence storage: snapshots + pre-event clips under the evidence root.

Path-traversal hardened: everything is resolved and checked to stay inside
the evidence directory before serving.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

from app.core.config import settings

log = logging.getLogger("ibvap.evidence")


class EvidenceStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _day_dir(self) -> Path:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        d = self.root / day
        d.mkdir(parents=True, exist_ok=True)
        return d

    def save_snapshot(self, jpeg_bytes: bytes) -> str | None:
        """Save a JPEG; returns the evidence-relative path (URL-safe)."""
        try:
            rel = f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}/{uuid.uuid4().hex}.jpg"
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(jpeg_bytes)
            return rel
        except Exception:
            log.exception("snapshot save failed")
            return None

    def save_clip(self, jpeg_frames: list, fps: float = 8.0) -> str | None:
        """Encode buffered JPEG frames into an .mp4 (pre-event clip).

        Returns evidence-relative path, or None if encoding is unavailable.
        Falls back to .avi if the mp4v codec is missing on this OS.
        """
        if not jpeg_frames:
            return None
        try:
            frame = cv2.imdecode(np.frombuffer(jpeg_frames[0], np.uint8), cv2.IMREAD_COLOR)
            if frame is None:
                return None
            h, w = frame.shape[:2]
            rel_mp4 = f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}/{uuid.uuid4().hex}.mp4"
            path = self.root / rel_mp4
            path.parent.mkdir(parents=True, exist_ok=True)
            writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
            if not writer.isOpened():  # codec fallback
                path = path.with_suffix(".avi")
                writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), fps, (w, h))
                rel_mp4 = str(path.relative_to(self.root)).replace("\\", "/")
            if not writer.isOpened():
                log.warning("no usable video codec for evidence clip")
                return None
            for jb in jpeg_frames:
                img = cv2.imdecode(np.frombuffer(jb, np.uint8), cv2.IMREAD_COLOR)
                if img is not None:
                    writer.write(img)
            writer.release()
            return rel_mp4
        except Exception:
            log.exception("clip save failed")
            return None

    def resolve(self, rel: str) -> Path | None:
        """Safely resolve a stored relative path; None if outside root."""
        try:
            p = (self.root / rel).resolve()
            if not str(p).startswith(str(self.root.resolve())):
                return None
            if not p.is_file():
                return None
            return p
        except Exception:
            return None

    def media_type(self, path: Path) -> str:
        return {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".mp4": "video/mp4",
            ".avi": "video/x-msvideo",
        }.get(path.suffix.lower(), "application/octet-stream")
