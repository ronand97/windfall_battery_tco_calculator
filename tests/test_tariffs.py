"""Smoke tests for the shipped tariff presets."""

from __future__ import annotations

from windfall_tco.data_models import Tariff
from windfall_tco.tariffs import CUSTOM_DEFAULT, OCTOPUS_COSY, OCTOPUS_GO, PRESETS


def test_octopus_cosy_is_valid_tariff() -> None:
    assert isinstance(OCTOPUS_COSY, Tariff)
    assert OCTOPUS_COSY.name == "Octopus Cosy"


def test_octopus_go_is_valid_tariff() -> None:
    assert isinstance(OCTOPUS_GO, Tariff)
    assert OCTOPUS_GO.name == "Octopus Go"


def test_custom_default_is_valid_tariff() -> None:
    assert isinstance(CUSTOM_DEFAULT, Tariff)
    assert CUSTOM_DEFAULT.name == "Custom"
    assert len(CUSTOM_DEFAULT.bands) == 1


def test_presets_contains_named_tariffs() -> None:
    assert isinstance(PRESETS, dict)
    assert "Octopus Cosy" in PRESETS
    assert "Octopus Go" in PRESETS
    assert PRESETS["Octopus Cosy"] is OCTOPUS_COSY
    assert PRESETS["Octopus Go"] is OCTOPUS_GO
