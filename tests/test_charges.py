"""Charging-session detection tests."""

from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "custom_components" / "mazda_6e" / "helpers" / "charges.py"
SPEC = importlib.util.spec_from_file_location("charges_test", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

T0 = datetime(2026, 10, 16, 13, 0, tzinfo=timezone.utc)


def feed(tracker, polls):
    """Run (minutes, connected, dc, charging, soc, current) polls and collect finished sessions."""
    sessions = []
    for minutes, connected, dc, charging, soc, current in polls:
        session = tracker.update(connected, dc, charging, soc, current, T0 + timedelta(minutes=minutes), 68.8)
        if session:
            sessions.append(session)
    return sessions


def test_a_dc_session_runs_from_plug_in_to_unplug():
    sessions = feed(MODULE.ChargeTracker(), [
        (0, False, False, False, 33, 0),
        (1, True, True, False, 33, 0),
        (2, True, True, True, 34, -148),
        (3, True, True, True, 35, -218),
        (25, True, True, True, 81, -216),
        (26, True, True, False, 82, 0),
        (27, False, False, False, 82, 0),
    ])

    assert len(sessions) == 1
    session = sessions[0]
    assert session["start"] == (T0 + timedelta(minutes=1)).isoformat()
    assert session["end"] == (T0 + timedelta(minutes=26)).isoformat()
    assert session["duration_min"] == 25
    assert session["soc_added"] == 49
    assert session["energy_kwh"] == 33.71
    assert session["type"] == "DC"
    assert session["peak_current_a"] == 218


def test_solar_pauses_stay_in_one_session_and_count_only_charging_time():
    sessions = feed(MODULE.ChargeTracker(), [
        (0, True, False, True, 50, 16),
        (30, True, False, True, 52, 16),
        (31, True, False, False, 52, 0),
        (120, True, False, False, 52, 0),
        (121, True, False, True, 52, 16),
        (122, True, False, True, 53, 16),
        (123, False, False, False, 53, 0),
    ])

    assert len(sessions) == 1
    assert sessions[0]["type"] == "AC"
    assert sessions[0]["soc_added"] == 3
    # Poll gaps over 5 min (0 to 30) are not counted.
    assert sessions[0]["charging_min"] == 2


def test_plugging_in_without_charging_is_not_logged():
    tracker = MODULE.ChargeTracker()
    assert feed(tracker, [
        (0, True, False, False, 80, 0),
        (5, True, False, False, 80, 0),
        (6, False, False, False, 80, 0),
    ]) == []
    assert tracker.as_dict() == {"session": None}


def test_missing_data_neither_starts_nor_ends_a_session():
    tracker = MODULE.ChargeTracker()
    assert feed(tracker, [(0, None, False, False, None, None)]) == []
    assert tracker.session is None

    feed(tracker, [(1, True, False, True, 40, 16), (2, None, False, False, None, None)])
    assert tracker.session is not None


def test_an_unfinished_session_survives_a_restart_without_counting_the_gap():
    tracker = MODULE.ChargeTracker()
    feed(tracker, [(0, True, False, True, 40, 16), (1, True, False, True, 41, 16)])

    restored = MODULE.ChargeTracker(tracker.as_dict())
    sessions = feed(restored, [(30, True, False, True, 45, 16), (31, False, False, False, 45, 0)])

    assert len(sessions) == 1
    assert sessions[0]["soc_start"] == 40
    assert sessions[0]["soc_end"] == 45
    assert sessions[0]["charging_min"] == 1
