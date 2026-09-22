"""ANPR: number-plate localization + OCR + Indian plate format validation.

Pipeline per vehicle detection:
  1. crop vehicle bbox (padded)
  2. Haar-cascade plate candidate localization (fallback: whole crop)
  3. EasyOCR on the candidate
  4. regex validation against Indian HSRP-ish formats
"""
from __future__ import annotations

import logging
import re

import cv2
import numpy as np

from app.services import vision

log = logging.getLogger("ibvap.anpr")

# Indian commercial/private plate regex (permissive, HSRP-inspired):
# 2 letters, 1-2 digit state code, 1-2 letter district series, 1-4 digit number.
INDIAN_PLATE_RE = re.compile(r"^[A-Z]{2}[0-9]{1,2}[A-Z]{0,3}[0-9]{1,4}$")

# Regex used to clean OCR noise: keep alphanumerics only.
_CLEAN_RE = re.compile(r"[^A-Z0-9]")

# Common OCR confusions on plate fonts
_OCR_FIXES = {"O": "0", "I": "1", "S": "5", "B": "8", "Z": "2", "D": "0"}


def clean_plate_text(raw: str) -> str:
    """Uppercase, strip non-alphanumerics, fix common OCR confusions."""
    t = _CLEAN_RE.sub("", (raw or "").upper())
    return t


def is_valid_indian_plate(text: str) -> bool:
    """Strict shape validation: 2 letters + 1-2 digits + optional letters + digits.

    Uses a slightly relaxed shape (total 6-10 chars, >= 2 letters, >= 3 digits)
    since Indian plates vary; tuned to reject OCR garbage.
    """
    if not (6 <= len(text) <= 10):
        return False
    letters = sum(c.isalpha() for c in text)
    digits = sum(c.isdigit() for c in text)
    if letters < 2 or digits < 3:
        return False
    return bool(INDIAN_PLATE_RE.match(text))


def locate_plate_crop(vehicle_img: np.ndarray) -> np.ndarray:
    """Return a crop likely containing the plate. Uses Haar cascade if it
    finds a hit; otherwise returns the bottom-center band of the vehicle."""
    h, w = vehicle_img.shape[:2]
    if h <= 0 or w <= 0:
        return vehicle_img
    try:
        cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_russian_plate_number.xml")
        gray = cv2.cvtColor(vehicle_img, cv2.COLOR_BGR2GRAY)
        plates = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(30, 10))
        if len(plates) > 0:
            x, y, pw, ph = plates[0]
            pad = 4
            x0, y0 = max(0, x - pad), max(0, y - pad)
            x1, y1 = min(w, x + pw + pad), min(h, y + ph + pad)
            return vehicle_img[y0:y1, x0:x1]
    except Exception:
        log.exception("plate cascade failed; falling back to band crop")
    # Fallback: bottom-center horizontal band where plates usually are
    y0, y1 = int(h * 0.55), int(h * 0.95)
    x0, x1 = int(w * 0.15), int(w * 0.85)
    return vehicle_img[y0:y1, x0:x1]


def preprocess_for_ocr(img: np.ndarray) -> np.ndarray:
    """Grayscale, resize up, CLAHE contrast boost — helps EasyOCR a lot."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return clahe.apply(gray)


def _candidate_fixes(text: str) -> list:
    """Generate plausible corrections of common OCR confusions.
    Indian plates interleave letters and digits, so a blind global replace is
    wrong; we instead try the raw text plus a few targeted variants and let
    the validator decide."""
    cands = [text]
    # variant: map letter-lookalikes to digits everywhere (helps digit-heavy reads)
    digit_fix = "".join(_OCR_FIXES.get(c, c) for c in text)
    if digit_fix not in cands:
        cands.append(digit_fix)
    # variant: first 2 chars forced letters (state code) if they look like digits
    if len(text) >= 3 and text[:2].isdigit():
        rev = {"0": "O", "1": "I", "5": "S", "8": "B", "2": "Z"}
        head = "".join(rev.get(c, c) for c in text[:2]) + text[2:]
        if head not in cands:
            cands.append(head)
    return cands


def read_plate(vehicle_img: np.ndarray) -> dict | None:
    """Run the full ANPR path on a vehicle crop. Returns
    {text, ocr_raw, confidence, is_valid} or None on any failure."""
    if vehicle_img is None or vehicle_img.size == 0:
        return None
    try:
        plate_img = locate_plate_crop(vehicle_img)
        pre = preprocess_for_ocr(plate_img)
        reader = vision.get_ocr()
        results = reader.readtext(pre, allowlist="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", detail=1)
        if not results:
            return None
        # join top-2 boxes for two-line plates, else take best
        results = sorted(results, key=lambda r: -r[2])
        raw = "".join(r[1] for r in results[:2])
        conf = float(min(results[0][2], 1.0))
        base = clean_plate_text(raw)
        if not base:
            return None
        # try corrections; first valid candidate wins, else keep raw read
        chosen = base
        valid = is_valid_indian_plate(base)
        if not valid:
            for cand in _candidate_fixes(base)[1:]:
                if is_valid_indian_plate(cand):
                    chosen, valid = cand, True
                    break
        return {
            "text": chosen,
            "ocr_raw": raw,
            "confidence": round(conf, 3),
            "is_valid": valid,
        }
    except Exception:
        log.exception("ANPR read failed")
        return None
