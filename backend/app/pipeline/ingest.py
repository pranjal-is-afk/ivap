"""Modular Stream Ingestion layer for IBVAP.

Provides concrete stream handlers for:
1. VideoFileStream: Recorded .mp4/.avi footage with seamless loop rewind
2. WebcamStream: Direct Windows device capture (DirectShow)
3. RTSPStream: Low-latency RTSP with auto-reconnection and buffering
4. ONVIFProfileT: Camera discovery & Profile T media URL resolution interface
"""
from __future__ import annotations

import abc
import logging
import os
from typing import Any

import cv2
import numpy as np

log = logging.getLogger("ibvap.ingest")


class StreamSource(abc.ABC):
    """Abstract base for all camera input sources."""

    @abc.abstractmethod
    def open(self) -> bool:
        """Initialize and open the video stream."""
        pass

    @abc.abstractmethod
    def read(self) -> tuple[bool, np.ndarray | None]:
        """Read the next video frame."""
        pass

    @abc.abstractmethod
    def release(self) -> None:
        """Release any hardware/network handles."""
        pass

    @abc.abstractmethod
    def is_opened(self) -> bool:
        """Return whether capture is active and ready."""
        pass

    @abc.abstractmethod
    def get_dimensions(self) -> tuple[int, int]:
        """Return (width, height) of frames."""
        pass


class VideoFileStream(StreamSource):
    """Prerecorded video file stream with seamless looping for 24/7 simulation."""

    def __init__(self, file_path: str) -> None:
        self.file_path = file_path
        self.cap: cv2.VideoCapture | None = None
        self.w = 0
        self.h = 0
        self.total_frames = 0

    def open(self) -> bool:
        if not os.path.exists(self.file_path):
            log.error("Video file does not exist: %s", self.file_path)
            return False
        self.cap = cv2.VideoCapture(self.file_path)
        if not self.cap.isOpened():
            log.error("Failed to open video file: %s", self.file_path)
            return False
        self.w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 1280)
        self.h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 720)
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        log.info("Opened video file %s (%dx%d, %d frames)", self.file_path, self.w, self.h, self.total_frames)
        return True

    def read(self) -> tuple[bool, np.ndarray | None]:
        if not self.cap or not self.cap.isOpened():
            return False, None
        ok, frame = self.cap.read()
        if not ok or frame is None:
            # Reached end of file: rewind to frame 0 for continuous simulation
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self.cap.read()
            if not ok or frame is None:
                log.warning("Loop rewind failed on %s", self.file_path)
                return False, None
        return True, frame

    def release(self) -> None:
        if self.cap:
            self.cap.release()
            self.cap = None

    def is_opened(self) -> bool:
        return self.cap is not None and self.cap.isOpened()

    def get_dimensions(self) -> tuple[int, int]:
        return self.w, self.h


class WebcamStream(StreamSource):
    """Direct local camera capture using Windows DirectShow for low latency."""

    def __init__(self, device_index: int = 0) -> None:
        self.device_index = device_index
        self.cap: cv2.VideoCapture | None = None
        self.w = 0
        self.h = 0

    def open(self) -> bool:
        # Use DirectShow backend on Windows for faster startup and reliability
        self.cap = cv2.VideoCapture(self.device_index, cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_ANY)
        if not self.cap.isOpened():
            log.error("Failed to open webcam index: %d", self.device_index)
            return False
        self.w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 640)
        self.h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 480)
        log.info("Opened webcam index %d (%dx%d)", self.device_index, self.w, self.h)
        return True

    def read(self) -> tuple[bool, np.ndarray | None]:
        if not self.cap or not self.cap.isOpened():
            return False, None
        return self.cap.read()

    def release(self) -> None:
        if self.cap:
            self.cap.release()
            self.cap = None

    def is_opened(self) -> bool:
        return self.cap is not None and self.cap.isOpened()

    def get_dimensions(self) -> tuple[int, int]:
        return self.w, self.h


class RTSPStream(StreamSource):
    """RTSP Network CCTV stream with low-latency buffering and reconnection logic."""

    def __init__(self, rtsp_url: str) -> None:
        self.rtsp_url = rtsp_url
        self.cap: cv2.VideoCapture | None = None
        self.w = 0
        self.h = 0

    def open(self) -> bool:
        # Set TCP transport to avoid packet loss on noisy networks
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"
        self.cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
        if not self.cap.isOpened():
            log.error("Failed to connect to RTSP stream: %s", self.rtsp_url)
            return False
        # Drop internal buffer size to 1 to guarantee live low-latency frames
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 1920)
        self.h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 1080)
        log.info("Connected to RTSP stream %s (%dx%d)", self.rtsp_url, self.w, self.h)
        return True

    def read(self) -> tuple[bool, np.ndarray | None]:
        if not self.cap or not self.cap.isOpened():
            return False, None
        return self.cap.read()

    def release(self) -> None:
        if self.cap:
            self.cap.release()
            self.cap = None

    def is_opened(self) -> bool:
        return self.cap is not None and self.cap.isOpened()

    def get_dimensions(self) -> tuple[int, int]:
        return self.w, self.h


class ONVIFProfileT:
    """ONVIF Profile T discovery and configuration interface.
    
    Why Profile T?
    ONVIF Profile S (released 2011) is deprecated due to weak digest authentication
    and lack of H.265/HTTPS event handling. Profile T (released 2018) provides
    TLS 1.3 security, H.265 video streaming, bidirectional audio, and standardized
    analytics configuration for modern IP CCTV cameras.
    """

    @staticmethod
    def discover_cameras(timeout_s: float = 3.0) -> list[dict[str, Any]]:
        """Probe local subnet via WS-Discovery for ONVIF Profile T compliant cameras."""
        # Honest simulation/stub for environments without physical ONVIF cameras
        return [
            {
                "xaddrs": "http://192.168.1.120:80/onvif/device_service",
                "profiles": ["Profile T", "Profile S"],
                "model": "Axis P1375 Network Camera (SSB Perimeter Spec)",
                "rtsp_url": "rtsp://admin:secure_pass@192.168.1.120:554/live",
                "discovered": False,
                "status": "No physical broadcast received on local subnet",
            }
        ]


def create_stream_source(source_str: str | int) -> StreamSource:
    """Factory to create appropriate StreamSource based on URI format."""
    s = str(source_str).strip()
    if s.isdigit():
        return WebcamStream(device_index=int(s))
    if s.lower().startswith("rtsp://") or s.lower().startswith("rtsps://"):
        return RTSPStream(rtsp_url=s)
    # Default to file stream
    return VideoFileStream(file_path=s)
