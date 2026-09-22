"""Alert policy engine tests — severity, dedup, label filtering, night boost."""
from app.pipeline.alerts import DEDUP_WINDOW_SECONDS, compute_severity, is_night, should_alert


def test_night_window_boundaries():
    assert is_night(23)
    assert is_night(3)
    assert is_night(20)
    assert not is_night(6)
    assert not is_night(12)
    assert not is_night(19)


def test_person_intrusion_is_high():
    assert compute_severity("zone_intrusion", "person", is_night_time=False, zone_type="restricted") == "high"


def test_person_intrusion_at_night_is_critical():
    assert compute_severity("zone_intrusion", "person", is_night_time=True, zone_type="restricted") == "critical"


def test_vehicle_intrusion_is_high():
    assert compute_severity("zone_intrusion", "car", is_night_time=False) == "high"


def test_loitering_defaults_to_medium():
    assert compute_severity("loitering", "person", is_night_time=False) == "medium"


def test_animal_does_not_page_operator():
    d = should_alert("zone_intrusion", "dog", zone_type="restricted")
    assert d.make_alert is False
    assert "not alert-worthy" in d.reason


def test_dedup_within_cooldown():
    first = should_alert("zone_intrusion", "person", last_same_key_ts=None, now_ts=100.0)
    assert first.make_alert
    dup = should_alert("zone_intrusion", "person", last_same_key_ts=100.0, now_ts=100.0 + DEDUP_WINDOW_SECONDS - 1)
    assert dup.make_alert is False
    after = should_alert("zone_intrusion", "person", last_same_key_ts=100.0, now_ts=100.0 + DEDUP_WINDOW_SECONDS + 1)
    assert after.make_alert


def test_unknown_kind_never_alerts():
    assert should_alert("meteor_strike", "person").make_alert is False
