"""Runtime-validated configuration helpers.

Local-dev conveniences live in .env; anything a judge might flip (auth disable,
suppression of SIMULATED-FEED badges) must be explicitly validated here so it is
impossible to accidentally ship a demo that lies about what it is.
"""
from __future__ import annotations

import os


def is_auth_disabled() -> bool:
    """Auth can only be disabled by explicitly setting BOTH flags.

    IBVAP_ALLOW_AUTH_DISABLE=1 and IBVAP_I_UNDERSTAND_NO_AUTH=1.
    This is a deliberate footgun guard: it should never be on by accident.
    """
    return (
        os.environ.get("IBVAP_ALLOW_AUTH_DISABLE") == "1"
        and os.environ.get("IBVAP_I_UNDERSTAND_NO_AUTH") == "1"
    )


def is_local_video_source(source: str) -> bool:
    """A source is 'simulated' (labelled as such in the UI) unless it is a
    network camera scheme (rtsp/rtmp/http(s))."""
    s = source.strip().lower()
    return not (s.startswith("rtsp://") or s.startswith("rtmp://") or s.startswith("http://") or s.startswith("https://"))
