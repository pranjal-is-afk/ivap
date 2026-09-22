"""Per-camera pipeline thread: capture → detect → track → zones → ANPR → persist.

Each enabled camera gets its own daemon thread. All shared DB work goes
through short-lived sessions; WebSocket pushes marshal to the API event loop.
"""
from __future__ import annotations

import logging
import os
import queue as pyqueue
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import cv2
import numpy as np

from app.core import env_flags
from app.db.models import Alert, AlertStatus, Camera, Event, EventKind, Face, Plate, Track
from app.db.session import SessionLocal
from app.pipeline import anpr
from app.pipeline.alerts import is_night
from app.pipeline.ingest import create_stream_source
from app.pipeline.zones import ZoneEngine
from app.services import vision

log = logging.getLogger("ibvap.engine")

PERSON_IDS = {0}
VEHICLE_LABELS = {"car", "truck", "bus", "motorcycle"}

# Cloud hosts have no GPU. Set IBVAP_CPU_ONLY=1 to force the CPU path so the
# System page and FPS numbers honestly reflect the device actually used.
_CPU_ONLY = os.environ.get("IBVAP_CPU_ONLY", "").strip() == "1"

ANPR_COOLDOWN_S = 8.0
FACE_INTERVAL_S = 2.0


def apply_low_light_enhancement(frame: np.ndarray) -> np.ndarray:
    """Luminance-adaptive CLAHE enhancement for low-light/night border surveillance.
    
    Prevents detection collapse in low illumination scenes without corrupting daylight frames.
    """
    try:
        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        cl = clahe.apply(l)
        enhanced = cv2.merge((cl, a, b))
        return cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)
    except Exception:
        return frame



class CameraWorker(threading.Thread):
    """Runs the full analytics loop for one camera source."""

    def __init__(self, camera: dict, worker_ref: "IngestWorker") -> None:
        super().__init__(daemon=True, name=f"cam-{camera['name']}")
        self.camera = camera
        self.worker = worker_ref
        self.stop_event = threading.Event()

        self.zone_engine = ZoneEngine()
        self.zone_engine.set_zones(camera.get("zones", []))

        # real, measured metrics
        self.fps = 0.0
        self.latency_ms = 0.0
        self._fps_hist: deque = deque(maxlen=60)

        self.capture = None
        self._frame_w = 0
        self._frame_h = 0
        self._recovered_count = 0
        # rolling JPEG buffer for pre-event evidence clips (~last 15s)
        self._recent: deque = deque(maxlen=180)
        self.latest_meta: dict = {"status": "starting"}

    # ------------- capture

    def _open_capture(self) -> bool:
        src = self.camera["source"]
        try:
            if isinstance(src, int) or (isinstance(src, str) and src.isdigit()):
                self.capture = cv2.VideoCapture(int(src))
            else:
                self.capture = cv2.VideoCapture(str(src))
            if not self.capture.isOpened():
                log.error("cannot open source %s", src)
                return False
            ok, frame = self.capture.read()
            if not ok or frame is None:
                log.error("source %s opened but cannot decode frames", src)
                self.capture.release()
                return False
            self._frame_h, self._frame_w = frame.shape[:2]
            return True
        except Exception:
            log.exception("exception opening source %s", src)
            return False

    def _handle_stall(self) -> bool:
        """Recover from a dead source. Files loop back to frame 0; network
        sources get released + reopened after a backoff."""
        src = str(self.camera["source"])
        log.warning("source %s stalled; recovering", src)
        try:
            if self.capture is not None:
                self.capture.release()
        except Exception:
            pass
        if env_flags.is_local_video_source(src):
            try:
                self.capture = cv2.VideoCapture(src)
                if self.capture.isOpened():
                    self._recovered_count += 1
                    return True
            except Exception:
                log.exception("file reopen failed")
            return False
        time.sleep(2.0)
        ok = self._open_capture()
        if ok:
            self._recovered_count += 1
        return ok

    # ------------- inference

    def _detect_and_track(self, frame):
        try:
            det = vision.get_detector()
            results = det.track(
                frame,
                persist=True,
                verbose=False,
                conf=0.35,
                iou=0.5,
                tracker="bytetrack.yaml",
                device=0 if (vision.cuda_available() and not _CPU_ONLY) else "cpu",
            )
            return results[0] if results else None
        except Exception as exc:
            log.exception("detect failed: %s", exc)
            vision.release_gpu_memory()
            return None

    def _tracks_from_result(self, result) -> list:
        out = []
        if result is None or result.boxes is None or result.boxes.id is None:
            return out
        names = result.names
        for box in result.boxes:
            try:
                tid = int(box.id.item())
                cls = int(box.cls.item())
                conf = float(box.conf.item())
                x1, y1, x2, y2 = (float(v) for v in box.xyxy[0].tolist())
                label = names.get(cls, "object") if isinstance(names, dict) else str(names[cls])
                out.append({"track_id": tid, "label": label, "conf": conf, "bbox": (x1, y1, x2, y2)})
            except Exception:
                log.exception("bad detection row; skipping")
        return out

    # ------------- main loop

    def run(self) -> None:
        if not self._open_capture():
            self.latest_meta = {"status": "error", "error": f"cannot open source: {self.camera['source']}"}
            return

        try:
            while not self.stop_event.is_set():
                t_loop = time.time()

                ok, frame = self.capture.read() if self.capture else (False, None)
                if not ok or frame is None:
                    if self._handle_stall():
                        continue
                    self.latest_meta = {"status": "error", "error": "capture lost and reopen failed"}
                    time.sleep(1.0)
                    continue

                frame_ts = time.time()
                inf_frame = frame
                if self.camera.get("night_mode") or np.mean(frame) < 55.0:
                    inf_frame = apply_low_light_enhancement(frame)
                result = self._detect_and_track(inf_frame)
                tracks = self._tracks_from_result(result)

                now_ts = time.time()
                # zone transitions (with bbox attached for evidence crops)
                for ev in self.zone_engine.evaluate(self._frame_w, self._frame_h, tracks, now_ts):
                    bbox = next((t["bbox"] for t in tracks if t["track_id"] == ev["track_id"]), None)
                    if bbox:
                        ev["bbox"] = bbox
                    self.worker.handle_zone_event(self, ev, frame)

                # ANPR on vehicle tracks (throttled per track, OCR serialized)
                for v in tracks:
                    if v["label"] in VEHICLE_LABELS:
                        self.worker.maybe_anpr(self, v, frame)

                # faces (detection only, throttled)
                self.worker.maybe_faces(self, frame, tracks)

                # metrics: real measured end-to-end FPS + per-frame latency
                self.latency_ms = (time.time() - frame_ts) * 1000.0

                # raw-frame MJPEG for the live grid (frontend draws overlays)
                try:
                    ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 72])
                    if ok:
                        self._recent.append(buf.tobytes())
                        self.worker.broadcast_mjpeg(self.camera["id"], buf.tobytes())
                except Exception:
                    log.exception("mjpeg encode failed")

                self.latest_meta = {
                    "status": "live",
                    "fps": round(self.fps, 1),
                    "latency_ms": round(self.latency_ms, 1),
                    "recoveries": self._recovered_count,
                    "tracks": [
                        {
                            "track_id": t["track_id"],
                            "label": t["label"],
                            "conf": round(t["conf"], 2),
                            "bbox": [round(v, 1) for v in t["bbox"]],
                        }
                        for t in tracks
                    ],
                    "frame_w": self._frame_w,
                    "frame_h": self._frame_h,
                    "ts": now_ts,
                }
                self.worker.push_tracks_update(self.camera["id"], self.latest_meta)

                target_dt = 1.0 / max(1.0, float(self.camera.get("fps_target", 10.0)))
                elapsed = time.time() - t_loop
                if elapsed < target_dt:
                    time.sleep(target_dt - elapsed)
                # full loop time (incl. throttle) = honest delivered FPS
                dt = time.time() - t_loop
                if dt > 0:
                    self._fps_hist.append(1.0 / dt)
                    self.fps = sum(self._fps_hist) / len(self._fps_hist)
        finally:
            try:
                if self.capture is not None:
                    self.capture.release()
            except Exception:
                pass
            vision.release_gpu_memory()
            self.latest_meta = {"status": "stopped"}


class IngestWorker:
    """Owns camera threads; persistence hooks; MJPEG fanout."""

    def __init__(self, evidence_store) -> None:
        self.workers: dict[str, CameraWorker] = {}
        self.evidence_store = evidence_store
        self._lock = threading.Lock()
        self._mjpeg_queues: dict[str, list] = {}
        self._mjpeg_lock = threading.Lock()
        self._anpr_last: dict = {}
        self._alert_last: dict = {}
        self._face_last: dict = {}
        self._ocr_lock = threading.Lock()
        self._ocr_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ibvap-anpr")
        self._track_uuid: dict = {}  # (camera_id, bytetrack_key) -> tracks.id
        self._ws_manager = None

    def set_ws_manager(self, ws_manager) -> None:
        self._ws_manager = ws_manager

    # ------------- lifecycle

    def has_camera(self, camera_id: str) -> bool:
        with self._lock:
            w = self.workers.get(camera_id)
            return w is not None and w.is_alive()

    def start_camera(self, camera: dict) -> None:
        with self._lock:
            cid = camera["id"]
            existing = self.workers.get(cid)
            if existing is not None and existing.is_alive():
                return
            w = CameraWorker(camera, self)
            self.workers[cid] = w
            w.start()

    def stop_camera(self, camera_id: str) -> None:
        with self._lock:
            w = self.workers.pop(camera_id, None)
        if w:
            w.stop_event.set()
            w.join(timeout=8)
            if w.is_alive():
                log.warning("camera worker %s did not stop cleanly", camera_id)
            vision.release_gpu_memory()

    def stop_all(self) -> None:
        for cid in list(self.workers.keys()):
            self.stop_camera(cid)

    def status(self) -> dict:
        with self._lock:
            return {
                cid: {
                    "alive": w.is_alive(),
                    "fps": round(w.fps, 1),
                    "latency_ms": round(w.latency_ms, 1),
                    "meta": w.latest_meta,
                }
                for cid, w in self.workers.items()
            }

    # ------------- track upsert (tracks table)

    def _upsert_tracks(self, camera_id: str, tracks_meta: list) -> None:
        try:
            db = SessionLocal()
            try:
                for t in tracks_meta:
                    key = (camera_id, t["track_id"])
                    uid = self._track_uuid.get(key)
                    now = time.time()
                    if uid is None:
                        row = db.query(Track).filter_by(camera_id=camera_id, track_key=t["track_id"]).first()
                        if row is None:
                            row = Track(camera_id=camera_id, track_key=t["track_id"], label=t["label"])
                            db.add(row)
                            db.flush()
                        uid = row.id
                        self._track_uuid[key] = uid
                    db.query(Track).filter_by(id=uid).update(
                        {
                            "last_seen": datetime.fromtimestamp(now, tz=timezone.utc),
                            "label": t["label"],
                            "frames_seen": Track.frames_seen + 1,
                        }
                    )
                db.commit()
            finally:
                db.close()
        except Exception:
            log.exception("track upsert failed")

    def push_tracks_update(self, camera_id: str, meta: dict) -> None:
        if meta.get("status") == "live" and meta.get("tracks"):
            self._upsert_tracks(camera_id, meta["tracks"])
        if self._ws_manager:
            self._ws_manager.broadcast_threadsafe({"type": "tracks", "camera_id": camera_id, **meta})

    # ------------- zone events → events + alerts

    def handle_zone_event(self, cam_worker: "CameraWorker", ev: dict, frame) -> None:
        from app.pipeline.alerts import should_alert
        from app.services.audit import append_entry

        camera = cam_worker.camera
        now = time.time()
        try:
            db = SessionLocal()
            try:
                dedup_key = (camera["id"], ev["zone_id"], ev["track_id"])
                last = self._alert_last.get(dedup_key)
                event_kind = "zone_intrusion" if ev["type"] == "enter" else "loitering"
                dwell_s = float(ev.get("dwell_s", 0.0))
                decision = should_alert(
                    event_kind=event_kind,
                    label=ev["label"],
                    zone_type=ev["zone_type"],
                    is_night_time=is_night(time.localtime().tm_hour),
                    last_same_key_ts=last,
                    now_ts=now,
                    dwell_s=dwell_s,
                )
                if decision.make_alert:
                    self._alert_last[dedup_key] = now

                # evidence: snapshot + pre-event clip (only when alerting)
                snap_rel = None
                clip_rel = None
                if decision.make_alert:
                    try:
                        h, w = frame.shape[:2]
                        x1, y1, x2, y2 = (int(v) for v in ev.get("bbox", (0, 0, w, h)))
                        pad = 40
                        crop = frame[max(0, y1 - pad) : min(h, y2 + pad), max(0, x1 - pad) : min(w, x2 + pad)]
                        if crop.size == 0:
                            crop = frame
                        ok, buf = cv2.imencode(".jpg", crop, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
                        if ok:
                            snap_rel = self.evidence_store.save_snapshot(buf.tobytes())
                    except Exception:
                        log.exception("evidence snapshot failed")
                    try:
                        clip_rel = self.evidence_store.save_clip(
                            list(cam_worker._recent)[-90:], fps=cam_worker.camera.get("fps_target", 8.0)
                        )
                    except Exception:
                        log.exception("evidence clip failed")

                ipi_dict = None
                if decision.ipi:
                    ipi_dict = {
                        "score": decision.ipi.score,
                        "level": decision.ipi.level,
                        "factors": decision.ipi.factors,
                        "rationale": decision.ipi.rationale,
                    }

                ev_row = Event(
                    camera_id=camera["id"],
                    zone_id=ev["zone_id"],
                    track_id=self._track_uuid.get((camera["id"], ev["track_id"])),
                    kind=EventKind.zone_intrusion if ev["type"] == "enter" else EventKind.loitering,
                    details={
                        "zone_name": ev["zone_name"],
                        "zone_type": ev["zone_type"],
                        "track_key": ev["track_id"],
                        "label": ev["label"],
                        "dwell_s": dwell_s,
                        "bbox": list(ev.get("bbox", ())),
                        "ipi": ipi_dict,
                    },
                    frame_snapshot=snap_rel,
                )
                ev_row.details["clip"] = clip_rel
                db.add(ev_row)
                db.flush()

                if decision.make_alert:
                    a = Alert(event_id=ev_row.id, severity=decision.severity, status=AlertStatus.new)
                    db.add(a)
                    db.flush()
                    try:
                        append_entry(db, actor="system", action="alert_created", alert_id=a.id,
                                     payload={"severity": decision.severity, "camera_id": camera["id"], "ipi": ipi_dict})
                    except Exception:
                        log.exception("audit append failed (continuing)")
                    db.commit()
                    if self._ws_manager:
                        self._ws_manager.broadcast_threadsafe(
                            {
                                "type": "alert",
                                "alert_id": a.id,
                                "event_id": ev_row.id,
                                "camera_id": camera["id"],
                                "camera_name": camera["name"],
                                "zone_name": ev["zone_name"],
                                "zone_type": ev["zone_type"],
                                "kind": ev_row.kind.value,
                                "severity": decision.severity,
                                "label": ev["label"],
                                "ipi": ipi_dict,
                                "snapshot_url": f"/api/evidence/{snap_rel}" if snap_rel else None,
                                "clip_url": f"/api/evidence/{clip_rel}" if clip_rel else None,
                                "details": ev_row.details,
                                "ts": ev_row.occurred_at.isoformat(),
                            }
                        )
                else:
                    db.commit()
            finally:
                db.close()
        except Exception:
            log.exception("zone event handling failed")

    # ------------- ANPR

    def maybe_anpr(self, cam_worker: "CameraWorker", vehicle: dict, frame) -> None:
        key = (cam_worker.camera["id"], vehicle["track_id"])
        now = time.time()
        if now - self._anpr_last.get(key, 0.0) < ANPR_COOLDOWN_S:
            return
        self._anpr_last[key] = now

        h, w = frame.shape[:2]
        x1, y1, x2, y2 = (int(v) for v in vehicle["bbox"])
        crop = frame[max(0, y1) : min(h, y2), max(0, x1) : min(w, x2)].copy()
        if crop.size == 0:
            return

        # Offload to background thread pool so camera worker thread latency remains low (<40ms)
        self._ocr_pool.submit(self._async_anpr, cam_worker.camera, vehicle, crop, now)

    def _async_anpr(self, camera: dict, vehicle: dict, crop: np.ndarray, now: float) -> None:
        try:
            with self._ocr_lock:
                result = anpr.read_plate(crop)
            if result is None:
                return

            snap_rel = None
            if result["is_valid"]:
                try:
                    ok, buf = cv2.imencode(".jpg", crop, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
                    if ok:
                        snap_rel = self.evidence_store.save_snapshot(buf.tobytes())
                except Exception:
                    log.exception("plate snapshot failed")

            try:
                db = SessionLocal()
                try:
                    p = Plate(
                        camera_id=camera["id"],
                        track_id=self._track_uuid.get((camera["id"], vehicle["track_id"])),
                        text=result["text"],
                        ocr_raw=result["ocr_raw"],
                        confidence=result["confidence"],
                        is_valid_format=result["is_valid"],
                        snapshot=snap_rel,
                    )
                    db.add(p)
                    ev_row = Event(
                        camera_id=camera["id"],
                        kind=EventKind.plate_read,
                        track_id=p.track_id,
                        details={
                            "text": result["text"],
                            "confidence": result["confidence"],
                            "is_valid": result["is_valid"],
                            "label": vehicle["label"],
                        },
                        frame_snapshot=snap_rel,
                    )
                    db.add(ev_row)
                    db.commit()
                finally:
                    db.close()
            except Exception:
                log.exception("plate persist failed")

            if self._ws_manager:
                self._ws_manager.broadcast_threadsafe(
                    {
                        "type": "plate",
                        "camera_id": camera["id"],
                        "camera_name": camera["name"],
                        "track_key": vehicle["track_id"],
                        **result,
                        "snapshot_url": f"/api/evidence/{snap_rel}" if snap_rel else None,
                        "ts": now,
                    }
                )
        except Exception:
            log.exception("async anpr worker failed")

    # ------------- faces (detection only, honest confidence from Haar levels)

    def maybe_faces(self, cam_worker: "CameraWorker", frame, tracks: list) -> None:
        if not any(t["label"] == "person" for t in tracks):
            return
        cid = cam_worker.camera["id"]
        now = time.time()
        if now - self._face_last.get(cid, 0.0) < FACE_INTERVAL_S:
            return
        self._face_last[cid] = now

        try:
            scale = 640.0 / max(frame.shape[1], 1)
            small = cv2.resize(frame, (int(frame.shape[1] * scale), int(frame.shape[0] * scale)))
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            cascade = vision.get_face_cascade()
            rects, levels, weights = cascade.detectMultiScale3(
                gray, scaleFactor=1.15, minNeighbors=5, minSize=(28, 28), outputRejectLevels=True
            )
            if len(rects) == 0:
                return
            db = SessionLocal()
            try:
                for (fx, fy, fw, fh), wgt in list(zip(rects, weights))[:2]:
                    fx0, fy0, fw0, fh0 = int(fx / scale), int(fy / scale), int(fw / scale), int(fh / scale)
                    face_crop = frame[fy0 : fy0 + fh0, fx0 : fx0 + fw0]
                    if face_crop.size == 0:
                        continue
                    ok, buf = cv2.imencode(".jpg", face_crop, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                    if not ok:
                        continue
                    snap_rel = self.evidence_store.save_snapshot(buf.tobytes())
                    db.add(
                        Face(
                            camera_id=cid,
                            confidence=round(float(wgt), 3),
                            snapshot=snap_rel,
                        )
                    )
                db.commit()
            finally:
                db.close()
        except Exception:
            log.exception("face handling failed")

    # ------------- MJPEG fanout

    def broadcast_mjpeg(self, camera_id: str, jpeg: bytes) -> None:
        with self._mjpeg_lock:
            queues = list(self._mjpeg_queues.get(camera_id, []))
        for q in queues:
            try:
                q.put_nowait(jpeg)
            except pyqueue.Full:
                pass  # slow consumer; drop frame

    def register_mjpeg(self, camera_id: str, maxsize: int = 2):
        q = pyqueue.Queue(maxsize=maxsize)
        with self._mjpeg_lock:
            self._mjpeg_queues.setdefault(camera_id, []).append(q)
        return q

    def unregister_mjpeg(self, camera_id: str, q) -> None:
        with self._mjpeg_lock:
            qs = self._mjpeg_queues.get(camera_id, [])
            if q in qs:
                qs.remove(q)
