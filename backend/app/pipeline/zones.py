"""Polygon zone logic — the geofence heart of IBVAP.

Zone polygons are stored in normalized [0..1] coordinates; this module owns
all conversion to pixel space and geometric tests. Kept pure (no cv2/db) so it
is trivially unit-testable.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from shapely.geometry import Point, Polygon


class ZoneGeometryError(ValueError):
    """Raised for degenerate polygons (<3 points, NaN coords, out of range)."""


def validate_polygon(norm_points, frame_w: int, frame_h: int) -> None:
    """Validate a normalized polygon against a concrete frame size."""
    if frame_w <= 0 or frame_h <= 0:
        raise ZoneGeometryError("frame dimensions must be positive")
    if len(norm_points) < 3:
        raise ZoneGeometryError("polygon needs >= 3 points")
    for p in norm_points:
        x, y = p.get("x"), p.get("y")
        if x is None or y is None:
            raise ZoneGeometryError("point missing x/y")
        if not (math.isfinite(x) and math.isfinite(y)):
            raise ZoneGeometryError("point coordinates must be finite")
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            raise ZoneGeometryError(f"point ({x},{y}) outside [0,1] range")


def to_pixel_polygon(norm_points, frame_w: int, frame_h: int) -> Polygon:
    validate_polygon(norm_points, frame_w, frame_h)
    return Polygon([(float(p["x"]) * frame_w, float(p["y"]) * frame_h) for p in norm_points])


@dataclass
class ZoneRuntime:
    """Per-camera zone state used by the live pipeline."""

    zone_id: str
    name: str
    zone_type: str
    polygon_norm: list
    min_dwell_seconds: int
    active: bool
    track_entered_at: dict = field(default_factory=dict, repr=False)
    track_inside: dict = field(default_factory=dict, repr=False)
    track_dwell_reported: dict = field(default_factory=dict, repr=False)


def center_of_box(x1, y1, x2, y2):
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


def point_in_polygon(px: float, py: float, poly: Polygon) -> bool:
    return poly.covers(Point(px, py))


class ZoneEngine:
    """Stateful per-camera zone evaluator.

    Feed it frame dims + zones + tracked detections each frame; it returns
    newly-entered / dwell-exceeded transitions. Designed for pytest coverage.
    """

    def __init__(self) -> None:
        self.zones: dict[str, ZoneRuntime] = {}

    def set_zones(self, zones: list) -> None:
        """zones: list of dicts with keys id,name,zone_type,polygon,
        min_dwell_seconds,active."""
        self.zones = {}
        for z in zones:
            self.zones[z["id"]] = ZoneRuntime(
                zone_id=z["id"],
                name=z["name"],
                zone_type=z.get("zone_type", "restricted"),
                polygon_norm=z["polygon"],
                min_dwell_seconds=int(z.get("min_dwell_seconds") or 0),
                active=bool(z.get("active", True)),
            )

    def evaluate(self, frame_w: int, frame_h: int, tracks: list, now_ts: float) -> list:
        """tracks: [{track_id:int, bbox:(x1,y1,x2,y2), label:str}]
        Returns transition events:
          {type: 'enter'|'dwell', zone_id, zone_name, zone_type, track_id, label, dwell_s}
        """
        events: list = []
        for zone in self.zones.values():
            if not zone.active:
                continue
            try:
                poly = to_pixel_polygon(zone.polygon_norm, frame_w, frame_h)
            except ZoneGeometryError:
                continue  # bad zone config must never crash the pipeline

            for t in tracks:
                cx, cy = center_of_box(*t["bbox"])
                inside = point_in_polygon(cx, cy, poly)
                tid = t["track_id"]
                was_inside = zone.track_inside.get(tid, False)

                if inside and not was_inside:
                    zone.track_inside[tid] = True
                    zone.track_entered_at[tid] = now_ts
                    zone.track_dwell_reported[tid] = False
                    events.append(
                        {
                            "type": "enter",
                            "zone_id": zone.zone_id,
                            "zone_name": zone.name,
                            "zone_type": zone.zone_type,
                            "track_id": tid,
                            "label": t.get("label", "object"),
                            "dwell_s": 0.0,
                        }
                    )
                elif inside and was_inside:
                    entered_at = zone.track_entered_at.get(tid)
                    if (
                        zone.zone_type == "loiter"
                        and zone.min_dwell_seconds > 0
                        and entered_at is not None
                        and not zone.track_dwell_reported.get(tid, False)
                        and (now_ts - entered_at) >= zone.min_dwell_seconds
                    ):
                        zone.track_dwell_reported[tid] = True
                        events.append(
                            {
                                "type": "dwell",
                                "zone_id": zone.zone_id,
                                "zone_name": zone.name,
                                "zone_type": zone.zone_type,
                                "track_id": tid,
                                "label": t.get("label", "object"),
                                "dwell_s": round(now_ts - entered_at, 1),
                            }
                        )
                elif not inside and was_inside:
                    zone.track_inside[tid] = False
                    zone.track_entered_at.pop(tid, None)
        return events
