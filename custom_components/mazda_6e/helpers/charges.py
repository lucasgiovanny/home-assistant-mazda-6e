"""Charging-session detection from the cable, charge status, state of charge and current."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

MAX_CHARGES = 100
# Longer poll gaps (HA restart, API outage) are not counted as charging time.
MAX_POLL_GAP = timedelta(minutes=5)


def build_charge(session: dict[str, Any], capacity_kwh: float) -> dict[str, Any] | None:
    """Summarise one plug-in session, or None when the car never charged."""
    soc_start = session.get("soc_start")
    soc_end = session.get("soc_end")
    soc_added = round(soc_end - soc_start, 1) if soc_start is not None and soc_end is not None else None
    charging_min = round(session["charging_seconds"] / 60)
    if charging_min == 0 and not soc_added:
        return None

    started = datetime.fromisoformat(session["start"])
    ended = datetime.fromisoformat(session["end"])
    return {
        "start": session["start"],
        "end": session["end"],
        "duration_min": round(max((ended - started).total_seconds() / 60, 0)),
        "charging_min": charging_min,
        "soc_start": soc_start,
        "soc_end": soc_end,
        "soc_added": soc_added,
        "energy_kwh": round(soc_added / 100 * capacity_kwh, 2) if soc_added is not None else None,
        "type": "DC" if session["dc"] else "AC",
        "peak_current_a": session["peak_current_a"],
    }


class ChargeTracker:
    """Follows the cable from plug-in to unplug and hands back each finished session."""

    def __init__(self, state: dict[str, Any] | None = None) -> None:
        self.session: dict[str, Any] | None = (state or {}).get("session")

    def as_dict(self) -> dict[str, Any]:
        return {"session": self.session}

    def update(
        self,
        connected: bool | None,
        dc: bool,
        charging: bool,
        soc: float | None,
        current: float | None,
        now: datetime,
        capacity_kwh: float,
    ) -> dict[str, Any] | None:
        """Feed one poll; returns a finished session once the cable is unplugged."""
        if connected is None:
            return None

        session = self.session
        if not connected:
            if session is None:
                return None
            self.session = None
            return build_charge(session, capacity_kwh)

        stamp = now.isoformat()
        if session is None:
            session = self.session = {
                "start": stamp,
                "end": stamp,
                "soc_start": soc,
                "soc_end": soc,
                "charging_seconds": 0,
                "charging": False,
                "dc": False,
                "peak_current_a": 0,
            }

        gap = now - datetime.fromisoformat(session["end"])
        if session["charging"] and timedelta(0) < gap <= MAX_POLL_GAP:
            session["charging_seconds"] += round(gap.total_seconds())
        session["end"] = stamp
        session["charging"] = charging
        session["dc"] = session["dc"] or dc
        if soc is not None:
            if session["soc_start"] is None:
                session["soc_start"] = soc
            session["soc_end"] = soc
        if charging and current is not None:
            session["peak_current_a"] = max(session["peak_current_a"], round(abs(current)))
        return None
