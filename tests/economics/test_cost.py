"""Tests for ``economics.cost``."""

from datetime import date, time

import pytest

from windfall_tco.data_models import DailyConsumption, HalfHourReading, Tariff, TariffBand
from windfall_tco.economics.cost import baseline_daily_cost, cost_of_slots


def _canonical_starts() -> list[time]:
    return [time(hour=(i * 30) // 60, minute=(i * 30) % 60) for i in range(48)]


def _flat_readings(kwh: float) -> list[HalfHourReading]:
    return [HalfHourReading(start=t, kwh=kwh) for t in _canonical_starts()]


FLAT_TARIFF = Tariff(
    name="Flat",
    bands=[TariffBand(start=time(0, 0), end=time(0, 0), rate_pence_per_kwh=20.0)],
)

TWO_BAND_TARIFF = Tariff(
    name="TwoBand",
    bands=[
        TariffBand(start=time(0, 0), end=time(6, 0), rate_pence_per_kwh=5.0),
        TariffBand(start=time(6, 0), end=time(0, 0), rate_pence_per_kwh=30.0),
    ],
)


def test_cost_of_slots_flat_tariff():
    readings = _flat_readings(0.1)
    assert cost_of_slots(readings, FLAT_TARIFF) == pytest.approx(96.0, rel=1e-9)


def test_cost_of_slots_two_band_tariff():
    readings = _flat_readings(0.1)
    # 12 cheap slots (00:00-06:00) * 0.1 * 5 = 6.0
    # 36 peak slots (06:00-24:00) * 0.1 * 30 = 108.0
    # total = 114.0
    assert cost_of_slots(readings, TWO_BAND_TARIFF) == pytest.approx(114.0, rel=1e-9)


def test_cost_of_slots_empty():
    assert cost_of_slots([], FLAT_TARIFF) == 0.0


def test_boundary_06_00_is_peak():
    """Half-open intervals: 06:00 falls into the peak band, not the cheap one."""
    reading = HalfHourReading(start=time(6, 0), kwh=1.0)
    # If it landed in the cheap band, we'd see 5.0. It must be 30.0.
    assert cost_of_slots([reading], TWO_BAND_TARIFF) == pytest.approx(30.0, rel=1e-9)


def test_boundary_05_30_is_cheap():
    """The last slot before the boundary stays in the cheap band."""
    reading = HalfHourReading(start=time(5, 30), kwh=1.0)
    assert cost_of_slots([reading], TWO_BAND_TARIFF) == pytest.approx(5.0, rel=1e-9)


def test_baseline_daily_cost_matches_cost_of_slots():
    readings = _flat_readings(0.1)
    day = DailyConsumption(date=date(2026, 4, 23), readings=readings)
    assert baseline_daily_cost(day, TWO_BAND_TARIFF) == pytest.approx(
        cost_of_slots(readings, TWO_BAND_TARIFF), rel=1e-9
    )
    assert baseline_daily_cost(day, TWO_BAND_TARIFF) == pytest.approx(114.0, rel=1e-9)
