"""Diagnostics redaction tests."""

import asyncio
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace


ROOT = Path(__file__).parents[1] / "custom_components" / "mazda_6e"


def load_diagnostics_module(monkeypatch):
    """Load diagnostics with the integration constants but without the package."""
    package = ModuleType("diagnostics_test")
    package.__path__ = [str(ROOT)]
    monkeypatch.setitem(sys.modules, "diagnostics_test", package)
    for name in ("const", "diagnostics"):
        spec = importlib.util.spec_from_file_location(f"diagnostics_test.{name}", ROOT / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, spec.name, module)
        spec.loader.exec_module(module)
    return module


def test_config_entry_diagnostics_redact_control_credentials(monkeypatch):
    """Control passcode and signing keys never appear in diagnostics."""
    module = load_diagnostics_module(monkeypatch)
    entry = SimpleNamespace(
        entry_id="entry",
        data={
            "token": "secret-token",
            "refresh": "secret-refresh",
            "deviceid": "secret-device",
            "control_private_key": "secret-private-key",
            "control_pin": "123456",
            "region": "europe",
        },
    )
    hass = SimpleNamespace(data={"mazda_6e": {"entry": SimpleNamespace(data={})}})

    info = asyncio.run(module.async_get_config_entry_diagnostics(hass, entry))["info"]

    assert info["region"] == "europe"
    for key in ("token", "refresh", "deviceid", "control_private_key", "control_pin"):
        assert info[key] == "**REDACTED**"
