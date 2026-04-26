"""Golden-value scenarios for `simulation.run()` (spec §7.5)."""

from __future__ import annotations

from datetime import date, time

import pytest

from windfall_tco.data_models import (
    BatterySpec,
    ConsumptionSeries,
    DailyConsumption,
    DispatchPolicy,
    HalfHourReading,
    Tariff,
    TariffBand,
)
from windfall_tco.simulation.run import run

# ----------------------------- Helpers -----------------------------

_SLOT_STARTS = [time(hour=i // 2, minute=(i % 2) * 30) for i in range(48)]


def _make_day(d: date, slot_kwh_list: list[float]) -> DailyConsumption:
    """Build a 48-slot `DailyConsumption` from a list of 48 kWh values."""
    assert len(slot_kwh_list) == 48
    readings = [
        HalfHourReading(start=start, kwh=kwh)
        for start, kwh in zip(_SLOT_STARTS, slot_kwh_list, strict=True)
    ]
    return DailyConsumption(date=d, readings=readings)


def _flat_day(d: date, kwh: float) -> DailyConsumption:
    """Build a day whose every slot holds the same kWh value."""
    return _make_day(d, [kwh] * 48)


def _flat_tariff(name: str, rate: float) -> Tariff:
    return Tariff(
        name=name,
        bands=[TariffBand(start=time(0, 0), end=time(0, 0), rate_pence_per_kwh=rate)],
    )


def _two_band_tariff(
    *,
    name: str = "TwoBand",
    cheap_start: time,
    cheap_end: time,
    cheap_rate: float,
    peak_rate: float,
) -> Tariff:
    """Two-band tariff: cheap window plus one peak band covering the rest of the day."""
    # Cover 00:00 → cheap_start @ peak, cheap window @ cheap, cheap_end → 24:00 @ peak.
    bands: list[TariffBand] = []
    if cheap_start != time(0, 0):
        bands.append(
            TariffBand(start=time(0, 0), end=cheap_start, rate_pence_per_kwh=peak_rate)
        )
    bands.append(
        TariffBand(start=cheap_start, end=cheap_end, rate_pence_per_kwh=cheap_rate)
    )
    if cheap_end != time(0, 0):
        bands.append(
            TariffBand(start=cheap_end, end=time(0, 0), rate_pence_per_kwh=peak_rate)
        )
    return Tariff(name=name, bands=bands)


# ----------------------------- Scenario 1: all-idle -----------------------------


def test_all_idle_flat_tariff_gives_zero_savings() -> None:
    """Flat tariff at 20p, mid-range price, battery never triggers → savings = 0."""
    tariff = _flat_tariff("Flat20p", 20.0)
    # charge_below = 5, discharge_above = 30 → 20 is mid-range, always IDLE.
    policy = DispatchPolicy(
        charge_below_pence_per_kwh=5.0, discharge_above_pence_per_kwh=30.0
    )
    spec = BatterySpec(
        usable_capacity_kwh=2.5,
        max_charge_power_w=800,
        max_discharge_power_w=800,
        round_trip_efficiency=0.9,
        initial_soc_fraction=0.5,
    )
    series = ConsumptionSeries(days=[_flat_day(date(2026, 4, 1), 0.1)])
    result = run(series, tariff, spec, policy)

    assert result.simulated_days == 1
    assert result.total_savings_pence == pytest.approx(0.0)
    # 48 slots * 0.1 kWh * 20p = 96p.
    assert result.total_baseline_cost_pence == pytest.approx(96.0)
    assert result.total_with_battery_cost_pence == pytest.approx(96.0)
    assert result.annualized_savings_pence == pytest.approx(0.0)
    # Every step must be idle.
    day_sim = result.days[0]
    assert all(s.battery_charge_kwh == 0.0 for s in day_sim.steps)
    assert all(s.battery_discharge_kwh == 0.0 for s in day_sim.steps)


# ----------------------------- Scenario 2: perfect arbitrage -----------------------------


def test_perfect_arbitrage_two_bands() -> None:
    """Cheap 00:00–06:00 @ 5p, peak 06:00–24:00 @ 30p.

    Battery: 5 kWh, 2000 W (so max_charge_kwh = 1.0, 12 cheap slots × 1.0 = 12 kWh
    slot-input; efficiency 1.0 → battery fills to 5 kWh well within window).
    Discharge during peak: load = 1.0 kWh/slot, max_discharge_kwh = 1.0 — battery
    discharges at full load until empty.

    Expected savings = discharged_energy × (peak − cheap). With eff=1.0 and full-
    charge amplitude = (5 - 2.5) kWh day-1 refill + full 5 kWh discharge during peak.
    The initial SoC (50% = 2.5 kWh) gets discharged for free (no previous charge
    cost), so the measured savings include its one-time bonus.
    """
    cheap_rate = 5.0
    peak_rate = 30.0
    tariff = _two_band_tariff(
        cheap_start=time(0, 0),
        cheap_end=time(6, 0),
        cheap_rate=cheap_rate,
        peak_rate=peak_rate,
    )
    policy = DispatchPolicy(
        charge_below_pence_per_kwh=cheap_rate,
        discharge_above_pence_per_kwh=peak_rate,
    )
    spec = BatterySpec(
        usable_capacity_kwh=5.0,
        max_charge_power_w=2000,
        max_discharge_power_w=2000,
        round_trip_efficiency=1.0,
        initial_soc_fraction=0.5,
    )
    # Load: 1.0 kWh per slot during peak window (06:00+), 0 during cheap window.
    # With capacity 5 kWh and peak load of 1 kWh/slot, battery discharges 5 slots' worth.
    slot_kwh = [0.0 if start < time(6, 0) else 1.0 for start in _SLOT_STARTS]
    series = ConsumptionSeries(days=[_make_day(date(2026, 4, 1), slot_kwh)])
    result = run(series, tariff, spec, policy)

    day_sim = result.days[0]
    # Total baseline = 36 peak slots * 1.0 kWh * 30p = 1080p.
    assert day_sim.baseline_cost_pence == pytest.approx(36 * 30.0)

    # Day starts with 2.5 kWh. During cheap window (12 slots, load=0, max 1 kWh each
    # slot) battery fills to 5 kWh by slot 3 (2.5 → 3.5 → 4.5 → 5.0 — 2.5 kWh charged).
    # Charging cost: 2.5 kWh * 5p = 12.5p.
    # During peak: discharges 5 kWh (full capacity) over 5 slots, then idles empty.
    # 31 peak slots at 1 kWh from grid at 30p = 930p; 5 slots from battery (0p from grid).
    # With-battery cost = 12.5p (charge) + 930p (uncovered peak) = 942.5p.
    # Savings = 1080 − 942.5 = 137.5p.
    expected_savings = 2.5 * (peak_rate - cheap_rate) + 2.5 * peak_rate  # newly-charged 2.5 kWh arb'd + free 2.5 kWh from initial SoC
    assert expected_savings == pytest.approx(137.5)
    assert day_sim.savings_pence == pytest.approx(expected_savings)
    assert result.total_savings_pence == pytest.approx(expected_savings)


# ----------------------------- Scenario 3: battery-empty-at-peak -----------------------------


def test_battery_empty_at_peak_partial_savings() -> None:
    """Tiny 0.5 kWh battery under heavy peak load → partial savings."""
    cheap_rate = 5.0
    peak_rate = 30.0
    tariff = _two_band_tariff(
        cheap_start=time(0, 0),
        cheap_end=time(6, 0),
        cheap_rate=cheap_rate,
        peak_rate=peak_rate,
    )
    policy = DispatchPolicy(
        charge_below_pence_per_kwh=cheap_rate,
        discharge_above_pence_per_kwh=peak_rate,
    )
    spec = BatterySpec(
        usable_capacity_kwh=0.5,
        max_charge_power_w=800,
        max_discharge_power_w=800,
        round_trip_efficiency=1.0,
        initial_soc_fraction=0.0,  # empty to isolate the effect.
    )
    # Load: 1.0 kWh each peak slot (36 slots), 0 during cheap.
    slot_kwh = [0.0 if start < time(6, 0) else 1.0 for start in _SLOT_STARTS]
    series = ConsumptionSeries(days=[_make_day(date(2026, 4, 1), slot_kwh)])
    result = run(series, tariff, spec, policy)

    # Battery can only shift 0.5 kWh per day (charge window plenty big enough,
    # capacity is the limit). Savings = 0.5 * (30 - 5) = 12.5p.
    # Upper bound (infinite battery) = 36 * (30 - 5) = 900p (unattainable here).
    assert result.total_savings_pence > 0
    assert result.total_savings_pence == pytest.approx(0.5 * (peak_rate - cheap_rate))
    infinite_battery_bound = 36 * (peak_rate - cheap_rate)
    assert result.total_savings_pence < infinite_battery_bound


# ----------------------------- Scenario 4: charge-window-too-short -----------------------------


def test_charge_window_too_short_cannot_keep_up() -> None:
    """1h cheap window, 8h peak — battery fully drains each day.

    Assertion: savings stay positive on every day and the battery drains down to
    empty at some point during the peak window each day, demonstrating the
    charge-window-too-short regime.
    """
    cheap_rate = 5.0
    peak_rate = 30.0
    # Cheap window 03:00-04:00 (2 slots); peak window 10:00-18:00 (16 slots); rest mid.
    bands = [
        TariffBand(start=time(0, 0), end=time(3, 0), rate_pence_per_kwh=15.0),
        TariffBand(start=time(3, 0), end=time(4, 0), rate_pence_per_kwh=cheap_rate),
        TariffBand(start=time(4, 0), end=time(10, 0), rate_pence_per_kwh=15.0),
        TariffBand(start=time(10, 0), end=time(18, 0), rate_pence_per_kwh=peak_rate),
        TariffBand(start=time(18, 0), end=time(0, 0), rate_pence_per_kwh=15.0),
    ]
    tariff = Tariff(name="Narrow", bands=bands)
    policy = DispatchPolicy(
        charge_below_pence_per_kwh=cheap_rate,
        discharge_above_pence_per_kwh=peak_rate,
    )
    spec = BatterySpec(
        usable_capacity_kwh=3.0,
        max_charge_power_w=800,
        max_discharge_power_w=800,
        round_trip_efficiency=1.0,
        initial_soc_fraction=0.5,  # start half full.
    )
    # Constant load everywhere.
    slot_kwh = [0.5] * 48
    series = ConsumptionSeries(
        days=[
            _make_day(date(2026, 4, 1), slot_kwh),
            _make_day(date(2026, 4, 2), slot_kwh),
            _make_day(date(2026, 4, 3), slot_kwh),
        ]
    )
    result = run(series, tariff, spec, policy)

    # Savings positive on every day.
    for day_sim in result.days:
        assert day_sim.savings_pence > 0

    # Battery gets drained each day: some step's post-step SoC must hit 0.
    for day_sim in result.days:
        assert any(s.battery_soc_kwh == 0.0 for s in day_sim.steps)

    # Cheap-window monotonicity: during 03:00–04:00 the battery only charges.
    for day_sim in result.days:
        cheap_steps = [s for s in day_sim.steps if time(3, 0) <= s.timestamp_start < time(4, 0)]
        assert len(cheap_steps) == 2
        socs = [s.battery_soc_kwh for s in cheap_steps]
        # Non-decreasing SoC across the cheap window.
        assert socs == sorted(socs)


# ----------------------------- Scenario 5: efficiency sweep -----------------------------


def test_efficiency_sweep_affects_savings_analytically() -> None:
    """Perfect-arbitrage scenario at efficiency 1.0 vs 0.5.

    At efficiency 1.0: 2.5 kWh of new charge → 2.5 * (30 − 5) = 62.5p + 2.5 kWh of
    initial SoC freebie = 2.5 * 30 = 75p; total 137.5p.
    At efficiency 0.5: 2.5 kWh of stored charge costs 5.0 kWh grid at 5p = 25p
    (vs. 12.5p at eff=1.0), so arb-savings on the charged portion = 2.5*30 − 25 = 50p.
    The 2.5 kWh initial-SoC freebie is unaffected by efficiency (no charging cost).
    Total at eff=0.5: 50 + 75 = 125p.
    """
    cheap_rate = 5.0
    peak_rate = 30.0
    tariff = _two_band_tariff(
        cheap_start=time(0, 0),
        cheap_end=time(6, 0),
        cheap_rate=cheap_rate,
        peak_rate=peak_rate,
    )
    policy = DispatchPolicy(
        charge_below_pence_per_kwh=cheap_rate,
        discharge_above_pence_per_kwh=peak_rate,
    )
    slot_kwh = [0.0 if start < time(6, 0) else 1.0 for start in _SLOT_STARTS]
    series = ConsumptionSeries(days=[_make_day(date(2026, 4, 1), slot_kwh)])

    def _run_at(eff: float) -> float:
        spec = BatterySpec(
            usable_capacity_kwh=5.0,
            max_charge_power_w=2000,
            max_discharge_power_w=2000,
            round_trip_efficiency=eff,
            initial_soc_fraction=0.5,
        )
        return run(series, tariff, spec, policy).total_savings_pence

    savings_10 = _run_at(1.0)
    savings_05 = _run_at(0.5)

    # Analytical expectations.
    expected_10 = 2.5 * (peak_rate - cheap_rate) + 2.5 * peak_rate
    new_charge_kwh = 2.5  # headroom available during cheap window.
    expected_05 = (
        new_charge_kwh * peak_rate - (new_charge_kwh / 0.5) * cheap_rate
    ) + 2.5 * peak_rate
    assert savings_10 == pytest.approx(expected_10)
    assert savings_05 == pytest.approx(expected_05)
    assert savings_10 > savings_05


# ----------------------------- Empty-series edge case -----------------------------


def test_empty_series_returns_zero_sim_result() -> None:
    tariff = _flat_tariff("Flat20p", 20.0)
    policy = DispatchPolicy(
        charge_below_pence_per_kwh=5.0, discharge_above_pence_per_kwh=30.0
    )
    spec = BatterySpec()
    series = ConsumptionSeries(days=[])
    result = run(series, tariff, spec, policy)
    assert result.simulated_days == 0
    assert result.total_savings_pence == 0.0
    assert result.total_baseline_cost_pence == 0.0
    assert result.total_with_battery_cost_pence == 0.0
    assert result.annualized_savings_pence == 0.0
    assert result.days == []


# ----------------------------- Annualization sanity -----------------------------


def test_annualized_savings_scales_by_365() -> None:
    """Manual-entry-style single day → annualized == daily * 365."""
    cheap_rate = 5.0
    peak_rate = 30.0
    tariff = _two_band_tariff(
        cheap_start=time(0, 0),
        cheap_end=time(6, 0),
        cheap_rate=cheap_rate,
        peak_rate=peak_rate,
    )
    policy = DispatchPolicy(
        charge_below_pence_per_kwh=cheap_rate,
        discharge_above_pence_per_kwh=peak_rate,
    )
    spec = BatterySpec(
        usable_capacity_kwh=0.5,
        max_charge_power_w=800,
        max_discharge_power_w=800,
        round_trip_efficiency=1.0,
        initial_soc_fraction=0.0,
    )
    slot_kwh = [0.0 if start < time(6, 0) else 1.0 for start in _SLOT_STARTS]
    series = ConsumptionSeries(days=[_make_day(date(2026, 4, 1), slot_kwh)])
    result = run(series, tariff, spec, policy)
    assert result.annualized_savings_pence == pytest.approx(result.total_savings_pence * 365)


# ----------------------------- Actual-cost aggregation -----------------------------


def test_run_aggregates_actual_current_cost_when_all_present():
    """When every reading has current_cost_pence, run() sums them into SimResult."""
    # Build a 48-slot day with kwh=0.1 and current_cost_pence=5.0 everywhere.
    readings = [
        HalfHourReading(start=start, kwh=0.1, current_cost_pence=5.0)
        for start in _SLOT_STARTS
    ]
    day = DailyConsumption(date=date(2026, 4, 1), readings=readings)
    series = ConsumptionSeries(days=[day])

    tariff = _flat_tariff("flat-20", 20.0)
    policy = DispatchPolicy(
        charge_below_pence_per_kwh=1.0, discharge_above_pence_per_kwh=100.0
    )
    spec = BatterySpec(usable_capacity_kwh=2.5, initial_soc_fraction=0.5)
    result = run(series, tariff, spec, policy)

    # 48 slots * 5p each = 240p
    assert result.total_actual_current_cost_pence == pytest.approx(240.0)


def test_run_returns_none_actual_cost_when_any_slot_missing():
    """A single missing current_cost_pence poisons the aggregate to None."""
    readings = [
        HalfHourReading(start=start, kwh=0.1, current_cost_pence=5.0)
        for start in _SLOT_STARTS
    ]
    # Drop cost data from slot 0.
    readings[0] = HalfHourReading(start=_SLOT_STARTS[0], kwh=0.1, current_cost_pence=None)
    day = DailyConsumption(date=date(2026, 4, 1), readings=readings)
    series = ConsumptionSeries(days=[day])

    tariff = _flat_tariff("flat-20", 20.0)
    policy = DispatchPolicy(
        charge_below_pence_per_kwh=1.0, discharge_above_pence_per_kwh=100.0
    )
    spec = BatterySpec(usable_capacity_kwh=2.5, initial_soc_fraction=0.5)
    result = run(series, tariff, spec, policy)

    assert result.total_actual_current_cost_pence is None
