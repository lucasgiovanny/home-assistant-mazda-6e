"""Trip detection tests."""

from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "custom_components" / "mazda_6e" / "helpers" / "trips.py"
SPEC = importlib.util.spec_from_file_location("trips_test", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

DRIVING, PARKED = MODULE.DRIVING, MODULE.PARKED
T0 = datetime(2026, 10, 15, 8, 0, tzinfo=timezone.utc)


def feed(tracker, polls):
    """Run (minutes, status, odometer, soc) polls and collect finished trips."""
    trips = []
    for minutes, status, odometer, soc in polls:
        trip = tracker.update(status, odometer, soc, T0 + timedelta(minutes=minutes), 68.8)
        if trip:
            trips.append(trip)
    return trips


def test_a_trip_ends_after_five_minutes_parked():
    trips = feed(MODULE.TripTracker(), [
        (0, PARKED, 1000.0, 80),
        (1, DRIVING, 1000.0, 80),
        (20, DRIVING, 1012.0, 76),
        (25, PARKED, 1023.0, 74),
        (29, PARKED, 1023.0, 74),
        (30, PARKED, 1023.0, 74),
    ])

    assert len(trips) == 1
    trip = trips[0]
    assert trip["distance_km"] == 23.0
    assert trip["duration_min"] == 24
    assert trip["soc_used"] == 6
    assert trip["energy_kwh"] == 4.13
    assert trip["consumption_kwh_100km"] == 18.0
    assert trip["avg_speed_kmh"] == 57.5
    assert trip["end"] == (T0 + timedelta(minutes=25)).isoformat()


def test_a_short_stop_belongs_to_the_same_trip():
    trips = feed(MODULE.TripTracker(), [
        (0, DRIVING, 500.0, 60),
        (10, PARKED, 508.0, 58),
        (13, DRIVING, 508.0, 58),
        (30, PARKED, 520.0, 55),
        (36, PARKED, 520.0, 55),
    ])

    assert [trip["distance_km"] for trip in trips] == [20.0]
    assert trips[0]["soc_used"] == 5


def test_flickers_and_missing_data_do_not_make_trips():
    tracker = MODULE.TripTracker()
    assert feed(tracker, [
        (0, DRIVING, 100.0, 50),
        (1, PARKED, 100.1, 50),
        (10, PARKED, 100.1, 50),
        (11, None, None, None),
        (12, PARKED, None, 50),
    ]) == []
    assert tracker.as_dict() == {"start": None, "stop": None}


def test_an_unfinished_trip_survives_a_restart():
    tracker = MODULE.TripTracker()
    feed(tracker, [(0, DRIVING, 200.0, 70), (5, PARKED, 205.0, 69)])

    restored = MODULE.TripTracker(tracker.as_dict())
    trips = feed(restored, [(11, PARKED, 205.0, 69)])

    assert [trip["distance_km"] for trip in trips] == [5.0]


def test_soc_is_optional():
    trip = MODULE.build_trip(
        {"time": T0.isoformat(), "odometer": 10.0, "soc": None},
        {"time": (T0 + timedelta(minutes=10)).isoformat(), "odometer": 15.0, "soc": 40},
        68.8,
    )
    assert trip["distance_km"] == 5.0
    assert trip["energy_kwh"] is None
    assert trip["consumption_kwh_100km"] is None


def test_month_totals_count_only_the_current_month():
    trips = [
        {"end": "2026-10-14T18:00:00+00:00", "distance_km": 30.0, "energy_kwh": 5.0},
        {"end": "2026-10-02T08:00:00+00:00", "distance_km": 20.0, "energy_kwh": None},
        {"end": "2026-09-30T23:30:00+00:00", "distance_km": 99.0, "energy_kwh": 9.0},
    ]
    totals = MODULE.month_totals(trips, datetime(2026, 10, 15, 12, tzinfo=timezone.utc))

    assert totals == {"trips": 2, "distance_km": 50.0, "energy_kwh": 5.0, "consumption_kwh_100km": 10.0}
    assert MODULE.month_totals([], T0)["consumption_kwh_100km"] is None
