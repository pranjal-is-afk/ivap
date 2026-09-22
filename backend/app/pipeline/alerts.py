"""Alert engine: decides which zone events become alerts and at what severity.

Kept pure and unit-testable. Policies are data-driven so they can be tuned
without code changes (PDR risk: per-zone sensitivity tuning instead of a
one-size-fits-all threshold).
"""
from __future__ import annotations

from dataclasses import dataclass

SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}

# Base severity by event type (tunable)
BASE_SEVERITY: dict[str, str] = {
    "zone_intrusion": "high",
    "loitering": "medium",
    "dwell": "medium",
    "plate_read": "low",
    "face_detected": "low",
    "night_movement": "medium",
}

# Labels considered security-relevant; others (e.g. animals) get downgraded.
HIGH_INTEREST_LABELS = {"person", "car", "truck", "bus", "motorcycle", "bicycle"}

# Deduplication: same (event kind, zone, track) inside this window is suppressed.
DEDUP_WINDOW_SECONDS = 30.0


@dataclass(frozen=True)
class IPIScore:
    score: int  # 0 to 100
    level: str  # "LOW" | "GUARD" | "ELEVATED" | "CRITICAL"
    factors: dict[str, int]  # decomposed contributing percentages/points
    rationale: str


@dataclass(frozen=True)
class AlertDecision:
    make_alert: bool
    severity: str
    reason: str
    ipi: IPIScore | None = None


def is_night(local_hour: int) -> bool:
    """Rough day/night split for night-movement boosting. 20:00–05:59 = night."""
    return local_hour >= 20 or local_hour < 6


def compute_ipi(
    event_kind: str,
    label: str,
    zone_type: str | None = None,
    dwell_s: float = 0.0,
    is_night_time: bool = False,
) -> IPIScore:
    """Compute Explainable Intrusion Probability Index (IPI) = f(zone_level, dwell_time, speed, time_of_day).
    
    Decomposed into clear, traceable integer weights totaling 0-100:
    - Zone Hazard (up to 45 pts)
    - Dwell Risk (up to 30 pts)
    - Time of Day (up to 20 pts)
    - Target Class Relevance (up to 15 pts)
    """
    zone_pts = 45 if zone_type == "restricted" else (25 if zone_type == "loiter" else 15)
    dwell_pts = min(30, int(dwell_s * 2.0)) if dwell_s > 0 else (10 if event_kind == "zone_intrusion" else 0)
    night_pts = 20 if is_night_time else 0
    target_pts = 15 if label == "person" else (10 if label in HIGH_INTEREST_LABELS else 5)

    raw_score = zone_pts + dwell_pts + night_pts + target_pts
    final_score = min(100, max(0, raw_score))

    if final_score >= 80:
        level = "CRITICAL"
    elif final_score >= 60:
        level = "HIGH"
    elif final_score >= 40:
        level = "ELEVATED"
    else:
        level = "LOW"

    factors = {
        "zone_hazard": zone_pts,
        "dwell_risk": dwell_pts,
        "time_of_day": night_pts,
        "target_class": target_pts,
    }
    rationale = (
        f"{level} threat (IPI {final_score}/100): zone={zone_type or 'general'} (+{zone_pts}), "
        f"dwell={dwell_s:.1f}s (+{dwell_pts}), night={is_night_time} (+{night_pts}), "
        f"class={label} (+{target_pts})"
    )
    return IPIScore(score=final_score, level=level, factors=factors, rationale=rationale)


def compute_severity(event_kind: str, label: str, is_night_time: bool, zone_type: str | None = None) -> str:
    base = BASE_SEVERITY.get(event_kind, "medium")
    # Night-time person movement is more security-relevant.
    if is_night_time and label == "person" and event_kind in {"zone_intrusion", "night_movement", "loitering"}:
        idx = min(SEVERITY_ORDER[base] + 1, SEVERITY_ORDER["critical"])
        base = [k for k, v in SEVERITY_ORDER.items() if v == idx][0]
    # A person physically inside a restricted zone is always at least high.
    if event_kind == "zone_intrusion" and label == "person" and zone_type == "restricted":
        if SEVERITY_ORDER[base] < SEVERITY_ORDER["high"]:
            base = "high"
    return base


def should_alert(
    event_kind: str,
    label: str,
    zone_type: str | None = None,
    is_night_time: bool = False,
    last_same_key_ts: float | None = None,
    now_ts: float = 0.0,
    cooldown_seconds: float = DEDUP_WINDOW_SECONDS,
    dwell_s: float = 0.0,
) -> AlertDecision:
    """Return whether this event should produce a user-facing alert, with explainable IPI."""
    ipi = compute_ipi(event_kind, label, zone_type, dwell_s, is_night_time)

    if event_kind not in BASE_SEVERITY:
        return AlertDecision(False, "low", f"unknown event kind {event_kind}", ipi=ipi)

    if label not in HIGH_INTEREST_LABELS and event_kind in {"zone_intrusion", "loitering", "dwell"}:
        # Animals/objects in a zone: log the event, don't page an operator.
        return AlertDecision(False, "low", f"label {label} not alert-worthy for {event_kind}", ipi=ipi)

    if zone_type == "entry" and event_kind == "zone_intrusion":
        # Entry zones record crossings for counting/trends; no operator paging.
        return AlertDecision(False, "low", "entry zone: crossing logged, no page", ipi=ipi)

    if last_same_key_ts is not None and (now_ts - last_same_key_ts) < cooldown_seconds:
        return AlertDecision(False, "low", "deduplicated within cooldown window", ipi=ipi)

    severity = compute_severity(event_kind, label, is_night_time, zone_type)
    # If IPI is critical, boost severity to at least high / critical
    if ipi.score >= 85 and SEVERITY_ORDER[severity] < SEVERITY_ORDER["high"]:
        severity = "high"

    return AlertDecision(True, severity, ipi.rationale, ipi=ipi)

