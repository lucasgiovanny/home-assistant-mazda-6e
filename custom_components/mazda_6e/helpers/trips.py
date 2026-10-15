"""Trip detection from the driving/parked status, odometer and state of charge."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

DRIVING = 1
PARKED = 2

# A stop shorter than this (a red light, dropping someone off) belongs to the same trip.
STOP_MERGE = timedelta(minutes=5)
# Status flickers while parked report a few hundred metres at most.
MIN_TRIP_KM = 0.3
MAX_TRIPS = 100
DEFAULT_BATTERY_CAPACITY_KWH = 68.8


def _snapshot(when: datetime, odometer: float, soc: float | None) -> dict[str, Any]:
    return {"time": when.isoformat(), "odometer": odometer, "soc": soc}


def build_trip(start: dict[str, Any], end: dict[str, Any], capacity_kwh: float) -> dict[str, Any] | None:
    """Summarise one trip from its start and end snapshots, or None when too short."""
    distance = round(end["odometer"] - start["odometer"], 1)
    if distance < MIN_TRIP_KM:
        return None

    started = datetime.fromisoformat(start["time"])
    ended = datetime.fromisoformat(end["time"])
    minutes = max((ended - started).total_seconds() / 60, 0)

    soc_used = None
    energy = None
    consumption = None
    if start.get("soc") is not None and end.get("soc") is not None:
        soc_used = round(start["soc"] - end["soc"], 1)
        energy = round(soc_used / 100 * capacity_kwh, 2)
        consumption = round(energy / distance * 100, 1)

    return {
        "start": start["time"],
        "end": end["time"],
        "duration_min": round(minutes),
        "distance_km": distance,
        "soc_start": start.get("soc"),
        "soc_end": end.get("soc"),
        "soc_used": soc_used,
        "energy_kwh": energy,
        "consumption_kwh_100km": consumption,
        "avg_speed_kmh": round(distance / (minutes / 60), 1) if minutes else None,
        "odometer_start": start["odometer"],
        "odometer_end": end["odometer"],
    }


class TripTracker:
    """Follows driving and parked transitions and hands back each finished trip."""

    def __init__(self, state: dict[str, Any] | None = None) -> None:
        state = state or {}
        self.start: dict[str, Any] | None = state.get("start")
        self.stop: dict[str, Any] | None = state.get("stop")

    def as_dict(self) -> dict[str, Any]:
        return {"start": self.start, "stop": self.stop}

    def update(
        self,
        status: int | None,
        odometer: float | None,
        soc: float | None,
        now: datetime,
        capacity_kwh: float,
    ) -> dict[str, Any] | None:
        """Feed one poll; returns a finished trip when a stop has lasted long enough."""
        if odometer is None:
            return None

        if status == DRIVING:
            if self.start is None:
                self.start = _snapshot(now, odometer, soc)
            self.stop = None
            return None

        if status != PARKED or self.start is None:
            return None

        if self.stop is None:
            self.stop = _snapshot(now, odometer, soc)
            return None

        if now - datetime.fromisoformat(self.stop["time"]) < STOP_MERGE:
            return None

        trip = build_trip(self.start, self.stop, capacity_kwh)
        self.start = None
        self.stop = None
        return trip


def month_totals(trips: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
    """Distance, energy and trip count for the calendar month of `now`."""
    month = [
        trip for trip in trips
        if (ended := datetime.fromisoformat(trip["end"]).astimezone(now.tzinfo)).year == now.year
        and ended.month == now.month
    ]
    distance = round(sum(trip["distance_km"] for trip in month), 1)
    energy = round(sum(trip["energy_kwh"] or 0 for trip in month), 1)
    return {
        "trips": len(month),
        "distance_km": distance,
        "energy_kwh": energy,
        "consumption_kwh_100km": round(energy / distance * 100, 1) if distance else None,
    }
