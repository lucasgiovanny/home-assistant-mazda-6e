"""Windows cover feature tests."""

import importlib

from homeassistant.components.cover import CoverEntityFeature


def test_windows_cover_only_opens_and_closes():
    """The cloud command has no stop or position, so the cover must not advertise them."""
    cover = importlib.import_module("custom_components.mazda_6e.cover")

    features = object.__new__(cover.Mazda6eWindowsCover).supported_features

    assert features == CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE
    assert not features & CoverEntityFeature.STOP
