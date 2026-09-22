"""Unit tests for the Intrusion Probability Index (IPI) engine."""
from app.pipeline.alerts import compute_ipi, should_alert


def test_ipi_restricted_night_person():
    ipi = compute_ipi(
        event_kind="zone_intrusion",
        label="person",
        zone_type="restricted",
        dwell_s=5.0,
        is_night_time=True,
    )
    # 45 (restricted) + 10 (dwell) + 20 (night) + 15 (person) = 90
    assert ipi.score >= 80
    assert ipi.level == "CRITICAL"
    assert ipi.factors["zone_hazard"] == 45
    assert ipi.factors["time_of_day"] == 20
    assert ipi.factors["target_class"] == 15
    assert "CRITICAL" in ipi.rationale


def test_ipi_dwell_scaling():
    short = compute_ipi(
        event_kind="loitering",
        label="person",
        zone_type="loiter",
        dwell_s=2.0,
        is_night_time=False,
    )
    long = compute_ipi(
        event_kind="loitering",
        label="person",
        zone_type="loiter",
        dwell_s=20.0,
        is_night_time=False,
    )
    assert long.score > short.score
    assert long.factors["dwell_risk"] > short.factors["dwell_risk"]
    assert long.factors["dwell_risk"] <= 30


def test_ipi_score_bounds():
    for dwell in [0, 5, 50, 500]:
        for night in [True, False]:
            for ztype in ["restricted", "loiter", "entry", None]:
                for label in ["person", "car", "unknown"]:
                    ipi = compute_ipi("zone_intrusion", label, ztype, float(dwell), night)
                    assert 0 <= ipi.score <= 100
                    assert ipi.level in {"LOW", "ELEVATED", "HIGH", "CRITICAL"}


def test_should_alert_attaches_ipi():
    decision = should_alert(
        event_kind="zone_intrusion",
        label="person",
        zone_type="restricted",
        is_night_time=False,
        dwell_s=0.0,
    )
    assert decision.make_alert is True
    assert decision.ipi is not None
    assert decision.ipi.score >= 60
    assert "zone_hazard" in decision.ipi.factors
