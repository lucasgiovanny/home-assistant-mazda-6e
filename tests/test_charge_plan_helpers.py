"""Charge plan helper tests."""

from datetime import datetime, time, timedelta, timezone
import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "custom_components" / "mazda_6e" / "helpers" / "charge_plan.py"
SPEC = importlib.util.spec_from_file_location("charge_plan_test", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_plan_times_use_hhmm():
    assert MODULE.parse_plan_time("0400") == time(4, 0)
    assert MODULE.parse_plan_time("04:00") is None
    assert MODULE.parse_plan_time(None) is None
    assert MODULE.format_plan_time(time(11, 5)) == "1105"


def test_plan_time_zone_labels():
    assert MODULE.plan_time_zone(datetime(2026, 7, 1, tzinfo=timezone(timedelta(hours=1)))) == "GMT+01:00"
    assert MODULE.plan_time_zone(datetime(2026, 1, 1, tzinfo=timezone.utc)) == "GMT+00:00"
    assert MODULE.plan_time_zone(datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=-3, minutes=-30)))) == "GMT-03:30"


def test_describe_observed_plan():
    data = {"status": {"charge": {"chargePlanList": [
        {"planId": 2107063764810641410, "planType": 1, "isValid": 1, "startTime": "0400", "startSwitch": 1},
    ]}}}

    assert MODULE.charge_plans({"status": {"charge": {}}}) is None
    assert [MODULE.describe_plan(plan) for plan in MODULE.charge_plans(data)] == [
        {"plan_id": "2107063764810641410", "enabled": True, "start_time": "04:00", "end_time": None},
    ]
