"""Plan service helper tests."""

from datetime import datetime, time, timedelta, timezone
import importlib


def test_next_departure_rolls_over_to_tomorrow():
    services = importlib.import_module("custom_components.mazda_6e.services")
    now = datetime(2026, 10, 5, 12, 0, tzinfo=timezone(timedelta(hours=1)))

    assert services.next_departure(now, time(13, 30)) == now.replace(hour=13, minute=30)
    assert services.next_departure(now, time(7, 30)) == datetime(2026, 10, 6, 7, 30, tzinfo=now.tzinfo)
    assert services.next_departure(now, time(12, 0)) == datetime(2026, 10, 6, 12, 0, tzinfo=now.tzinfo)
