"""Zone geometry + transition logic — the geofence heart. Must be correct."""
import pytest
from shapely.geometry import Polygon

from app.pipeline.zones import (
    ZoneEngine,
    ZoneGeometryError,
    to_pixel_polygon,
    validate_polygon,
)


def test_polygon_needs_three_points():
    with pytest.raises(ZoneGeometryError):
        validate_polygon([{"x": 0.1, "y": 0.1}, {"x": 0.5, "y": 0.5}], 1920, 1080)


def test_polygon_rejects_out_of_range():
    with pytest.raises(ZoneGeometryError):
        validate_polygon(
            [{"x": 1.5, "y": 0.1}, {"x": 0.5, "y": 0.5}, {"x": 0.2, "y": 0.9}], 1920, 1080
        )


def test_polygon_rejects_nan():
    with pytest.raises(ZoneGeometryError):
        validate_polygon(
            [{"x": float("nan"), "y": 0.1}, {"x": 0.5, "y": 0.5}, {"x": 0.2, "y": 0.9}],
            1920,
            1080,
        )


def test_polygon_rejects_bad_frame():
    with pytest.raises(ZoneGeometryError):
        validate_polygon([{"x": 0.1, "y": 0.1}, {"x": 0.5, "y": 0.5}, {"x": 0.2, "y": 0.9}], 0, 1080)


def test_normalized_to_pixel_conversion():
    poly = to_pixel_polygon(
        [{"x": 0.0, "y": 0.0}, {"x": 0.5, "y": 0.0}, {"x": 0.5, "y": 0.5}, {"x": 0.0, "y": 0.5}],
        1920,
        1080,
    )
    assert poly.equals(Polygon([(0, 0), (960, 0), (960, 540), (0, 540)]))


def _engine_with_square_zone(x0=0.25, y0=0.25, x1=0.75, y1=0.75, zone_type="restricted"):
    eng = ZoneEngine()
    eng.set_zones(
        [
            {
                "id": "z1",
                "name": "Test Zone",
                "zone_type": zone_type,
                "polygon": [
                    {"x": x0, "y": y0},
                    {"x": x1, "y": y0},
                    {"x": x1, "y": y1},
                    {"x": x0, "y": y1},
                ],
                "min_dwell_seconds": 0,
                "active": True,
            }
        ]
    )
    return eng


def test_enter_event_fires_once_on_crossing():
    eng = _engine_with_square_zone()
    # track starts outside (center at 100,100 of 1000x1000 → normalized 0.1,0.1)
    ev1 = eng.evaluate(1000, 1000, [{"track_id": 7, "bbox": (80, 80, 120, 120), "label": "person"}], now_ts=0.0)
    assert ev1 == []
    # track moves inside (center 500,500)
    ev2 = eng.evaluate(1000, 1000, [{"track_id": 7, "bbox": (480, 480, 520, 520), "label": "person"}], now_ts=1.0)
    assert len(ev2) == 1
    assert ev2[0]["type"] == "enter"
    assert ev2[0]["zone_id"] == "z1"
    assert ev2[0]["track_id"] == 7
    # still inside: no duplicate enter
    ev3 = eng.evaluate(1000, 1000, [{"track_id": 7, "bbox": (480, 480, 520, 520), "label": "person"}], now_ts=2.0)
    assert ev3 == []


def test_exit_then_reenter_fires_again():
    eng = _engine_with_square_zone()
    inside = {"track_id": 3, "bbox": (480, 480, 520, 520), "label": "person"}
    outside = {"track_id": 3, "bbox": (0, 0, 40, 40), "label": "person"}
    # first appearance inside counts as an enter
    ev = eng.evaluate(1000, 1000, [inside], 0.0)
    assert len(ev) == 1 and ev[0]["type"] == "enter"
    ev = eng.evaluate(1000, 1000, [outside], 1.0)  # exit (no event by design)
    assert ev == []
    ev = eng.evaluate(1000, 1000, [inside], 2.0)  # re-enter
    assert len(ev) == 1 and ev[0]["type"] == "enter"


def test_inactive_zone_never_fires():
    eng = ZoneEngine()
    eng.set_zones(
        [
            {
                "id": "z1",
                "name": "Off",
                "zone_type": "restricted",
                "polygon": [{"x": 0, "y": 0}, {"x": 1, "y": 0}, {"x": 1, "y": 1}, {"x": 0, "y": 1}],
                "min_dwell_seconds": 0,
                "active": False,
            }
        ]
    )
    ev = eng.evaluate(1000, 1000, [{"track_id": 1, "bbox": (400, 400, 600, 600), "label": "person"}], 0.0)
    assert ev == []


def test_degenerate_zone_polygon_is_ignored_not_fatal():
    eng = ZoneEngine()
    eng.set_zones(
        [{"id": "bad", "name": "Bad", "zone_type": "restricted", "polygon": [{"x": 0.1, "y": 0.1}], "min_dwell_seconds": 0, "active": True}]
    )
    # must not raise
    ev = eng.evaluate(1000, 1000, [{"track_id": 1, "bbox": (400, 400, 600, 600), "label": "person"}], 0.0)
    assert ev == []


def test_dwell_fires_once_after_threshold():
    eng = _engine_with_square_zone(zone_type="loiter")
    eng.zones["z1"].min_dwell_seconds = 10
    inside = {"track_id": 9, "bbox": (480, 480, 520, 520), "label": "person"}
    ev = eng.evaluate(1000, 1000, [inside], 0.0)  # enter
    assert len(ev) == 1 and ev[0]["type"] == "enter"
    ev = eng.evaluate(1000, 1000, [inside], 5.0)  # not yet
    assert ev == []
    ev = eng.evaluate(1000, 1000, [inside], 11.0)  # dwell!
    assert len(ev) == 1 and ev[0]["type"] == "dwell" and ev[0]["dwell_s"] >= 10.0
    ev = eng.evaluate(1000, 1000, [inside], 20.0)  # only once
    assert ev == []


def test_center_point_rule_not_bbox_overlap():
    # zone is a small square at center; bbox corner touches it but center is outside
    eng = _engine_with_square_zone(x0=0.45, y0=0.45, x1=0.55, y1=0.55)
    ev = eng.evaluate(1000, 1000, [{"track_id": 1, "bbox": (540, 540, 700, 700), "label": "person"}], 0.0)
    assert ev == []  # center (620,620) is outside the 450-550 square
