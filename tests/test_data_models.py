"""Tests for pydantic data models in `windfall_tco.data_models`."""

from __future__ import annotations

from datetime import date, time

import pytest
from pydantic import ValidationError

from windfall_tco.data_models import (
    BatterySpec,
    DailyConsumption,
    DispatchPolicy,
    HalfHourReading,
    Tariff,
    TariffBand,
)

# ---------- helpers ----------

def _canonical_readings(kwh: float = 0.1) -> list[HalfHourReading]:
    """Return a valid 48-entry reading list covering 00:00, 00:30, ..., 23:30."""
    out: list[HalfHourReading] = []
    for i in range(48):
        total = i * 30
        out.append(
            HalfHourReading(
                start=time(hour=total // 60, minute=total % 60),
                kwh=kwh,
            )
        )
    return out


# ---------- Tariff ----------

class TestTariff:
    def test_accepts_single_full_day_band(self) -> None:
        t = Tariff(
            name="Flat",
            bands=[TariffBand(start=time(0, 0), end=time(0, 0), rate_pence_per_kwh=25.0)],
        )
        assert t.rate_at(time(0, 0)) == 25.0
        assert t.rate_at(time(12, 30)) == 25.0
        assert t.rate_at(time(23, 30)) == 25.0

    def test_accepts_multi_band_tariff(self) -> None:
        t = Tariff(
            name="Two Band",
            bands=[
                TariffBand(start=time(0, 0), end=time(7, 0), rate_pence_per_kwh=10.0),
                TariffBand(start=time(7, 0), end=time(0, 0), rate_pence_per_kwh=30.0),
            ],
        )
        assert t.rate_at(time(0, 0)) == 10.0
        assert t.rate_at(time(6, 59)) == 10.0
        assert t.rate_at(time(7, 0)) == 30.0  # start inclusive
        assert t.rate_at(time(23, 30)) == 30.0

    def test_accepts_bands_given_out_of_order(self) -> None:
        # Validator should sort before checking.
        t = Tariff(
            name="Shuffled",
            bands=[
                TariffBand(start=time(12, 0), end=time(0, 0), rate_pence_per_kwh=30.0),
                TariffBand(start=time(0, 0), end=time(12, 0), rate_pence_per_kwh=10.0),
            ],
        )
        # After validation, bands should be in canonical order.
        assert t.bands[0].start == time(0, 0)
        assert t.bands[-1].end == time(0, 0)

    def test_rejects_gap(self) -> None:
        with pytest.raises(ValidationError, match="gap"):
            Tariff(
                name="Gappy",
                bands=[
                    TariffBand(start=time(0, 0), end=time(6, 0), rate_pence_per_kwh=10.0),
                    TariffBand(start=time(7, 0), end=time(0, 0), rate_pence_per_kwh=30.0),
                ],
            )

    def test_rejects_overlap(self) -> None:
        with pytest.raises(ValidationError, match="overlap"):
            Tariff(
                name="Overlapping",
                bands=[
                    TariffBand(start=time(0, 0), end=time(8, 0), rate_pence_per_kwh=10.0),
                    TariffBand(start=time(7, 0), end=time(0, 0), rate_pence_per_kwh=30.0),
                ],
            )

    def test_rejects_missing_midnight_start(self) -> None:
        with pytest.raises(ValidationError, match="00:00"):
            Tariff(
                name="No Midnight Start",
                bands=[
                    TariffBand(start=time(1, 0), end=time(0, 0), rate_pence_per_kwh=25.0),
                ],
            )

    def test_rejects_non_midnight_end(self) -> None:
        with pytest.raises(ValidationError, match="24:00"):
            Tariff(
                name="No Midnight End",
                bands=[
                    TariffBand(start=time(0, 0), end=time(23, 30), rate_pence_per_kwh=25.0),
                ],
            )

    def test_rejects_empty_bands(self) -> None:
        with pytest.raises(ValidationError):
            Tariff(name="Empty", bands=[])

    def test_rate_at_band_boundaries(self) -> None:
        t = Tariff(
            name="Three Band",
            bands=[
                TariffBand(start=time(0, 0), end=time(8, 0), rate_pence_per_kwh=10.0),
                TariffBand(start=time(8, 0), end=time(18, 0), rate_pence_per_kwh=20.0),
                TariffBand(start=time(18, 0), end=time(0, 0), rate_pence_per_kwh=40.0),
            ],
        )
        # Start-inclusive.
        assert t.rate_at(time(0, 0)) == 10.0
        assert t.rate_at(time(8, 0)) == 20.0
        assert t.rate_at(time(18, 0)) == 40.0
        # End-exclusive: the instant before a boundary is still in the prior band.
        assert t.rate_at(time(7, 59)) == 10.0
        assert t.rate_at(time(17, 59)) == 20.0
        # Last slot start 23:30 is inside the final wrap-around band.
        assert t.rate_at(time(23, 30)) == 40.0


# ---------- DispatchPolicy ----------

class TestDispatchPolicy:
    def test_accepts_valid(self) -> None:
        p = DispatchPolicy(
            charge_below_pence_per_kwh=10.0,
            discharge_above_pence_per_kwh=30.0,
        )
        assert p.charge_below_pence_per_kwh == 10.0
        assert p.discharge_above_pence_per_kwh == 30.0

    def test_rejects_equal_thresholds(self) -> None:
        with pytest.raises(ValidationError, match="discharge_above"):
            DispatchPolicy(
                charge_below_pence_per_kwh=20.0,
                discharge_above_pence_per_kwh=20.0,
            )

    def test_rejects_discharge_below_charge(self) -> None:
        with pytest.raises(ValidationError, match="discharge_above"):
            DispatchPolicy(
                charge_below_pence_per_kwh=30.0,
                discharge_above_pence_per_kwh=10.0,
            )


# ---------- DailyConsumption ----------

class TestDailyConsumption:
    def test_accepts_valid_48_readings(self) -> None:
        day = DailyConsumption(date=date(2026, 4, 1), readings=_canonical_readings())
        assert len(day.readings) == 48
        assert day.readings[0].start == time(0, 0)
        assert day.readings[-1].start == time(23, 30)

    def test_rejects_fewer_than_48(self) -> None:
        readings = _canonical_readings()[:47]
        with pytest.raises(ValidationError, match="48"):
            DailyConsumption(date=date(2026, 4, 1), readings=readings)

    def test_rejects_more_than_48(self) -> None:
        readings = _canonical_readings()
        extra = HalfHourReading(start=time(23, 45), kwh=0.1)
        with pytest.raises(ValidationError, match="48"):
            DailyConsumption(date=date(2026, 4, 1), readings=[*readings, extra])

    def test_rejects_duplicate_times(self) -> None:
        readings = _canonical_readings()
        # Replace the last with a duplicate of the first.
        readings = [*readings[:-1], HalfHourReading(start=time(0, 0), kwh=0.1)]
        with pytest.raises(ValidationError):
            DailyConsumption(date=date(2026, 4, 1), readings=readings)

    def test_rejects_unsorted_input(self) -> None:
        readings = _canonical_readings()
        # Swap first two.
        readings = [readings[1], readings[0], *readings[2:]]
        with pytest.raises(ValidationError, match="sorted"):
            DailyConsumption(date=date(2026, 4, 1), readings=readings)

    def test_rejects_wrong_grid(self) -> None:
        # 48 readings but on wrong grid (hourly doubled up): 00:00, 00:00, 01:00, 01:00, ...
        readings: list[HalfHourReading] = []
        for h in range(24):
            readings.append(HalfHourReading(start=time(h, 0), kwh=0.1))
            readings.append(HalfHourReading(start=time(h, 0), kwh=0.1))
        with pytest.raises(ValidationError):
            DailyConsumption(date=date(2026, 4, 1), readings=readings)

    def test_rejects_negative_kwh(self) -> None:
        with pytest.raises(ValidationError):
            HalfHourReading(start=time(0, 0), kwh=-0.1)


# ---------- BatterySpec ----------

class TestBatterySpec:
    def test_defaults(self) -> None:
        spec = BatterySpec()
        assert spec.usable_capacity_kwh == 2.5
        assert spec.max_charge_power_w == 800
        assert spec.max_discharge_power_w == 800
        assert spec.round_trip_efficiency == 0.90
        assert spec.initial_soc_fraction == 0.5

    def test_rejects_zero_or_negative_capacity(self) -> None:
        with pytest.raises(ValidationError):
            BatterySpec(usable_capacity_kwh=0)
        with pytest.raises(ValidationError):
            BatterySpec(usable_capacity_kwh=-1)

    def test_rejects_zero_or_negative_power(self) -> None:
        with pytest.raises(ValidationError):
            BatterySpec(max_charge_power_w=0)
        with pytest.raises(ValidationError):
            BatterySpec(max_discharge_power_w=-100)

    def test_rejects_efficiency_above_one(self) -> None:
        with pytest.raises(ValidationError):
            BatterySpec(round_trip_efficiency=1.5)

    def test_rejects_efficiency_not_positive(self) -> None:
        with pytest.raises(ValidationError):
            BatterySpec(round_trip_efficiency=0)

    def test_rejects_soc_out_of_range(self) -> None:
        with pytest.raises(ValidationError):
            BatterySpec(initial_soc_fraction=-0.1)
        with pytest.raises(ValidationError):
            BatterySpec(initial_soc_fraction=1.5)

    def test_accepts_boundary_soc(self) -> None:
        assert BatterySpec(initial_soc_fraction=0).initial_soc_fraction == 0
        assert BatterySpec(initial_soc_fraction=1).initial_soc_fraction == 1
