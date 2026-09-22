"""Model and pipeline lazy initialization (GPU-safe, load-once)."""
from __future__ import annotations

import logging
import os
import threading

import cv2
import numpy as np
import torch
from ultralytics import YOLO

from app.core.config import REPO_ROOT

log = logging.getLogger("ibvap.vision")

_MODELS_DIR = REPO_ROOT / "assets" / "models"
_MODELS_DIR.mkdir(parents=True, exist_ok=True)

_lock = threading.Lock()
_detector: YOLO | None = None
_ocr = None
_face_cascade = None
_device_checked = False


def cuda_available() -> bool:
    try:
        return torch.cuda.is_available()
    except Exception:
        return False


def device_name() -> str:
    try:
        if cuda_available():
            return torch.cuda.get_device_name(0)
        return "cpu"
    except Exception:
        return "unknown"


def get_detector() -> YOLO:
    """YOLOv11n COCO-pretrained detector, loaded once, moved to GPU if present."""
    global _detector
    with _lock:
        if _detector is None:
            try:
                use_cpu = os.environ.get("IBVAP_CPU_ONLY", "").strip() == "1"
                model = YOLO("yolo11n.pt")
                if cuda_available() and not use_cpu:
                    model.to("cuda")
                _detector = model
                log.info("YOLO loaded on %s", device_name() if not use_cpu else "cpu (IBVAP_CPU_ONLY=1)")
            except Exception:
                log.exception("failed to load YOLO detector")
                raise
    return _detector


def get_ocr():
    """EasyOCR English reader, loaded once on demand.

    Defaults to CPU: ANPR is throttled (one read per track per 8 s), so CPU is
    easily fast enough and keeps ~1 GB of VRAM headroom on 6 GB cards —
    reliability over bragging rights. Set IBVAP_OCR_DEVICE=gpu to override.
    """
    global _ocr
    with _lock:
        if _ocr is None:
            try:
                import easyocr

                import os

                use_gpu = os.environ.get("IBVAP_OCR_DEVICE", "cpu").lower() == "gpu" and cuda_available()
                log.info("loading EasyOCR on %s (this takes ~10-30s first time)...", "gpu" if use_gpu else "cpu")
                _ocr = easyocr.Reader(
                    ["en"], gpu=use_gpu, verbose=False, model_storage_directory=str(_MODELS_DIR / "easyocr")
                )
                log.info("EasyOCR ready on %s", "gpu" if use_gpu else "cpu")
            except Exception:
                log.exception("failed to load EasyOCR")
                raise
    return _ocr


def get_face_cascade():
    """Haar cascade face detector (CPU, cheap, honest: detection only)."""
    global _face_cascade
    with _lock:
        if _face_cascade is None:
            cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            _face_cascade = cv2.CascadeClassifier(cascade_path)
            if _face_cascade.empty():
                log.error("failed to load Haar cascade")
                raise RuntimeError("Haar cascade load failed")
    return _face_cascade


def release_gpu_memory() -> None:
    try:
        if cuda_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


def warmup() -> dict:
    """Run one dummy inference per model to pay JIT/kernel costs up front."""
    results = {"yolo": False, "ocr": False, "face": False}
    try:
        det = get_detector()
        dummy = np.zeros((480, 640, 3), dtype=np.uint8)
        det.predict(dummy, verbose=False, device=0 if cuda_available() else "cpu")
        results["yolo"] = True
    except Exception:
        log.exception("yolo warmup failed")
    try:
        get_face_cascade()
        results["face"] = True
    except Exception:
        log.exception("face cascade warmup failed")
    try:
        get_ocr()
        results["ocr"] = True
    except Exception:
        log.exception("ocr warmup failed")
    release_gpu_memory()
    return results
