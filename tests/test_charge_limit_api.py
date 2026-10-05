"""Charge-limit API contract tests."""

import asyncio
import base64
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
from unittest.mock import AsyncMock

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


ROOT = Path(__file__).parents[1] / "custom_components" / "mazda_6e"


def load_module(monkeypatch, name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def api_context(monkeypatch):
    package = ModuleType("api_test")
    package.__path__ = [str(ROOT)]
    exceptions = ModuleType("homeassistant.exceptions")
    exceptions.ConfigEntryAuthFailed = type("ConfigEntryAuthFailed", (Exception,), {})
    monkeypatch.setitem(sys.modules, "api_test", package)
    monkeypatch.setitem(sys.modules, "homeassistant", ModuleType("homeassistant"))
    monkeypatch.setitem(sys.modules, "homeassistant.exceptions", exceptions)
    const = load_module(monkeypatch, "api_test.const", "const.py")
    crypto = load_module(monkeypatch, "api_test.credential_crypto", "credential_crypto.py")
    load_module(monkeypatch, "api_test.models", "models.py")
    api_module = load_module(monkeypatch, "api_test.api", "api.py")
    return api_module, const, crypto


def make_api(api_module, const, crypto):
    """Build an API with a real control key and its matching encrypted serial."""
    public_key, private_key = crypto.generate_control_key_pair()
    key = serialization.load_der_public_key(base64.b64decode(public_key))
    encrypted_serial = base64.encodebytes(key.encrypt(b"serial", padding.PKCS1v15())).decode()
    api = api_module.Mazda6EApi(
        None,
        "token",
        "refresh",
        "device",
        control_private_key=private_key,
        region=const.REGION_EUROPE,
    )
    return api, key, encrypted_serial


def test_set_charge_limit_uses_observed_contract(api_context):
    """Use serial type 2 and the captured charge_max request fields."""
    api, key, encrypted_serial = make_api(*api_context)
    api._request = AsyncMock(side_effect=[
        {"data": encrypted_serial},
        {"data": {"commandId": "command-id"}},
        {"data": {"resultCode": 0, "errorMsg": "success"}},
    ])

    result = asyncio.run(api.async_set_charge_limit(123, 85))

    assert result["resultCode"] == 0
    calls = api._request.await_args_list
    assert calls[0].args[0].endswith("/serial-no/get")
    assert calls[0].args[2] == {"type": "2"}
    assert calls[1].args[0].endswith("/charge/percentage")
    payload = calls[1].args[2]
    signature = payload.pop("sign")
    assert payload == {
        "chargePercentageMax": 85,
        "command": "charge_max",
        "rcToken": "",
        "seriralNo": "serial",
        "vehicleId": "123",
    }
    key.verify(
        base64.b64decode(signature),
        b"chargePercentageMax=85&seriralNo=serial&vehicleId=123",
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    assert calls[2].args[0].endswith("/control/control-result")
    assert calls[2].args[2] == {"commandId": "command-id", "vehicleId": "123"}


def test_set_charge_limit_accepts_code_1000_only_when_status_matches(api_context):
    """A non-responsive controller is acceptable only if the requested state is active."""
    api, _, encrypted_serial = make_api(*api_context)
    api._request = AsyncMock(side_effect=[
        {"data": encrypted_serial},
        {"data": {"commandId": "command-id"}},
    ])
    api._async_wait_for_control_result = AsyncMock(
        side_effect=RuntimeError("Control failed with result code 1000"),
    )
    api.async_get_vehicle_status = AsyncMock(
        return_value={"charge": {"maxSocPercent": 80}},
    )

    result = asyncio.run(api.async_set_charge_limit(123, 80))

    assert result["resultCode"] == 1000

    api._async_set_charge_limit_once = AsyncMock(side_effect=[
        RuntimeError("Control failed with result code 1000"),
        {"resultCode": 0, "errorMsg": "success"},
    ])
    api.async_get_vehicle_status = AsyncMock(
        return_value={"charge": {"maxSocPercent": 80}},
    )

    result = asyncio.run(api.async_set_charge_limit(123, 85))

    assert result["resultCode"] == 0
    assert api._async_set_charge_limit_once.await_count == 2


def test_get_battery_preheating_plan_uses_observed_contract(api_context):
    """Select the type-zero battery plan from the captured query endpoint."""
    api, _, _ = make_api(*api_context)
    expected = {"planId": 7, "planType": 0, "isValid": 1, "endData": "20260928060000"}
    api._request = AsyncMock(return_value={"data": [expected, {"planId": 8, "planType": 1}]})

    result = asyncio.run(api.async_get_battery_preheating_plan(123))

    assert result == expected
    call = api._request.await_args
    assert call.args[0].endswith("/heating-plans/query/list")
    assert call.args[2] == {"vehicleId": "123"}


@pytest.mark.parametrize(
    ("method", "args", "route", "serial_type", "expected_payload", "signed_data"),
    [
        (
            "async_update_battery_preheating",
            (123, 7, 0, "20260928060000"),
            "/heating-plans/update-plan",
            "5",
            {
                "endData": "20260928060000",
                "planId": "7",
                "planType": 0,
                "command": "COMMAND_HEATING_PLANS_UPDATE",
                "rcToken": "",
                "seriralNo": "serial",
                "vehicleId": "123",
            },
            b"endData=20260928060000&planId=7&planType=0&seriralNo=serial&vehicleId=123",
        ),
        (
            "async_disable_battery_preheating",
            (123, 7),
            "/heating-plans/plan-availability",
            "5",
            {
                "enabled": False,
                "planId": "7",
                "command": "COMMAND_HEATING_PLANS_AVAILABILITY",
                "rcToken": "",
                "seriralNo": "serial",
                "vehicleId": "123",
            },
            b"enabled=false&planId=7&seriralNo=serial&vehicleId=123",
        ),
        (
            "async_add_battery_preheating",
            (123, "20261006073000"),
            "/heating-plans/add-plan",
            "5",
            {
                "endData": "20261006073000",
                "planType": 0,
                "command": "COMMAND_HEATING_PLANS_ADD",
                "rcToken": "",
                "seriralNo": "serial",
                "vehicleId": "123",
            },
            b"endData=20261006073000&planType=0&seriralNo=serial&vehicleId=123",
        ),
        (
            "async_delete_battery_preheating",
            (123, 7),
            "/heating-plans/delete-plan",
            "5",
            {
                "planId": "7",
                "command": "COMMAND_HEATING_PLANS_DELETE",
                "rcToken": "",
                "seriralNo": "serial",
                "vehicleId": "123",
            },
            b"planId=7&seriralNo=serial&vehicleId=123",
        ),
    ],
)
def test_battery_preheating_commands_use_observed_contract(
    api_context, method, args, route, serial_type, expected_payload, signed_data,
):
    """Use serial type 5 and omit command and rcToken from both signatures."""
    api, key, encrypted_serial = make_api(*api_context)
    api._request = AsyncMock(side_effect=[
        {"data": encrypted_serial},
        {"data": {"commandId": "command-id"}},
        {"data": {"resultCode": 0, "errorMsg": "success"}},
    ])

    result = asyncio.run(getattr(api, method)(*args))

    assert result["resultCode"] == 0
    calls = api._request.await_args_list
    assert calls[0].args[2] == {"type": serial_type}
    assert calls[1].args[0].endswith(route)
    payload = calls[1].args[2]
    signature = payload.pop("sign")
    assert payload == expected_payload
    key.verify(
        base64.b64decode(signature),
        signed_data,
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    assert calls[2].args[2] == {"commandId": "command-id", "vehicleId": "123"}


@pytest.mark.parametrize(
    ("method", "args", "kwargs", "route", "expected_payload", "signed_data"),
    [
        (
            "async_add_charge_plan",
            (123, "1100", "1500"),
            {"end_enabled": True, "time_zone": "GMT+01:00"},
            "/charge/add-plan",
            {
                "command": "add_charge_plan",
                "endSwitch": 1,
                "endTime": "1500",
                "planType": 1,
                "startTime": "1100",
                "timeFormat": 1,
                "timeZone": "GMT+01:00",
            },
            b"endSwitch=1&endTime=1500&planType=1&seriralNo=serial&startTime=1100"
            b"&timeFormat=1&timeZone=GMT+01:00&vehicleId=123",
        ),
        (
            "async_modify_charge_plan",
            (123, {"planId": 42, "planType": 1, "timeFormat": 1}, "1100", "1500"),
            {"end_enabled": False, "time_zone": "GMT+00:00"},
            "/charge/modify-plan",
            {
                "command": "modify-plan",
                "endSwitch": 0,
                "endTime": "1500",
                "planId": "42",
                "planType": 1,
                "startTime": "1100",
                "timeFormat": 1,
                "timeZone": "GMT+00:00",
            },
            b"endSwitch=0&endTime=1500&planId=42&planType=1&seriralNo=serial"
            b"&startTime=1100&timeFormat=1&timeZone=GMT+00:00&vehicleId=123",
        ),
        (
            "async_delete_charge_plan",
            (123, 42),
            {},
            "/charge/delete-plan",
            {"command": "delete_charge_plan", "planId": "42"},
            b"planId=42&seriralNo=serial&vehicleId=123",
        ),
        (
            "async_set_charge_plan_enabled",
            (123, 42, False),
            {},
            "/charge/validity",
            {"command": "COMMAND_VALID_CHARGE_PLAN", "enabled": False, "planId": "42"},
            b"enabled=false&planId=42&seriralNo=serial&vehicleId=123",
        ),
    ],
)
def test_charge_plan_commands_use_charge_contract(
    api_context, method, args, kwargs, route, expected_payload, signed_data,
):
    """Charge plans use serial type 2 and omit command and rcToken from the signature."""
    api, key, encrypted_serial = make_api(*api_context)
    api._request = AsyncMock(side_effect=[
        {"data": encrypted_serial},
        {"data": {"commandId": "command-id"}},
        {"data": {"resultCode": 0, "errorMsg": "success"}},
    ])

    result = asyncio.run(getattr(api, method)(*args, **kwargs))

    assert result["resultCode"] == 0
    calls = api._request.await_args_list
    assert calls[0].args[2] == {"type": "2"}
    assert calls[1].args[0].endswith(route)
    payload = calls[1].args[2]
    signature = payload.pop("sign")
    assert payload == {
        **expected_payload,
        "rcToken": "",
        "seriralNo": "serial",
        "vehicleId": "123",
    }
    key.verify(base64.b64decode(signature), signed_data, padding.PKCS1v15(), hashes.SHA256())


def test_status_update_request_signs_without_command(api_context):
    """condition-inquiry uses serial type 1 and leaves command out of the signature."""
    api, key, encrypted_serial = make_api(*api_context)
    api._request = AsyncMock(side_effect=[
        {"data": encrypted_serial},
        {"data": {"commandId": "command-id"}},
        {"data": {"resultCode": 0, "errorMsg": "success"}},
    ])

    asyncio.run(api.async_request_status_update(123))

    calls = api._request.await_args_list
    assert calls[0].args[2] == {"type": "1"}
    assert calls[1].args[0].endswith("/control/condition-inquiry")
    payload = calls[1].args[2]
    signature = payload.pop("sign")
    assert payload == {"command": "COMMAND_GET_NEW_CONDITION", "seriralNo": "serial", "vehicleId": "123"}
    key.verify(base64.b64decode(signature), b"seriralNo=serial&vehicleId=123", padding.PKCS1v15(), hashes.SHA256())


def test_battery_preheating_plan_is_selected_from_heating_plans(api_context):
    api_module = api_context[0]
    assert api_module.battery_preheating_plan([{"planId": 8, "planType": 1}]) is None
    assert api_module.battery_preheating_plan([{"planId": 7, "planType": 0}]) == {"planId": 7, "planType": 0}
