"""Fold `step()` over a `ConsumptionSeries` to produce a `SimResult`.

Pure: no I/O. SoC is continuous across day boundaries. Baseline cost per day is
the sum of `load_kwh * price` over all slots (no battery action); per-day savings
are `baseline - total_cost`. See spec §7.3.

Internal structure:
    _initial_battery_state()    — SoC at t=0 from spec
    _simulate_slot()            — one half-hour: tariff lookup + step()
    _simulate_day()             — one day: fold _simulate_slot over 48 readings
    _merge_actual_cost()        — accumulate billing data, poison to None on gap
    run()                       — orchestrator over all days + final aggregation
"""

from __future__ import annotations

from windfall_tco.data_models import (
    BatterySpec,
    BatteryState,
    ConsumptionSeries,
    DailyConsumption,
    DaySimResult,
    DispatchPolicy,
    HalfHourReading,
    SimResult,
    StepResult,
    Tariff,
)
from windfall_tco.simulation.step import step


def _initial_battery_state(spec: BatterySpec) -> BatteryState:
    """Starting SoC = `initial_soc_fraction × usable_capacity`."""
    return BatteryState(
        energy_stored_kwh=spec.initial_soc_fraction * spec.usable_capacity_kwh,
    )


def _merge_actual_cost(running: float | None, slot_cost: float | None) -> float | None:
    """Add a slot's billed cost to the running total, propagating "unavailable".

    Once any slot lacks billing data the aggregate becomes `None` and stays
    that way — a partial sum across a multi-day series would mislead the
    "current vs modeled" comparison.
    """
    if running is None or slot_cost is None:
        return None
    return running + slot_cost


def _simulate_slot(
    state: BatteryState,
    reading: HalfHourReading,
    tariff: Tariff,
    spec: BatterySpec,
    policy: DispatchPolicy,
) -> tuple[BatteryState, StepResult, float]:
    """Run `step()` for one half-hour reading.

    Returns the new battery state, the step result, and the slot's *baseline*
    cost in pence (i.e. what this slot would have cost on the modeled tariff
    with no battery — `load × price`).
    """
    price_pence = tariff.rate_at(reading.start)
    new_state, result = step(
        prior_state=state,
        load_kwh=reading.kwh,
        price_pence_per_kwh=price_pence,
        spec=spec,
        policy=policy,
        timestamp_start=reading.start,
    )
    baseline_cost_pence = reading.kwh * price_pence
    return new_state, result, baseline_cost_pence


def _simulate_day(
    day: DailyConsumption,
    tariff: Tariff,
    spec: BatterySpec,
    policy: DispatchPolicy,
    state: BatteryState,
    actual_cost_pence: float | None,
) -> tuple[BatteryState, DaySimResult, float | None]:
    """Run all 48 slots in a day, threading SoC and the actual-cost aggregate."""
    step_results: list[StepResult] = []
    day_with_battery_pence = 0.0
    day_baseline_pence = 0.0
    day_actual_pence = actual_cost_pence

    for reading in day.readings:
        state, sr, slot_baseline_pence = _simulate_slot(
            state, reading, tariff, spec, policy
        )
        step_results.append(sr)
        day_with_battery_pence += sr.cost_pence
        day_baseline_pence += slot_baseline_pence
        day_actual_pence = _merge_actual_cost(day_actual_pence, reading.current_cost_pence)

    day_result = DaySimResult(
        date=day.date,
        steps=step_results,
        total_cost_pence=day_with_battery_pence,
        baseline_cost_pence=day_baseline_pence,
        savings_pence=day_baseline_pence - day_with_battery_pence,
    )
    return state, day_result, day_actual_pence


def _empty_sim_result() -> SimResult:
    """Zero-day series → well-formed result with all aggregates at zero."""
    return SimResult(
        days=[],
        total_savings_pence=0.0,
        total_baseline_cost_pence=0.0,
        total_with_battery_cost_pence=0.0,
        simulated_days=0,
        annualized_savings_pence=0.0,
    )


def run(
    series: ConsumptionSeries,
    tariff: Tariff,
    spec: BatterySpec,
    policy: DispatchPolicy,
) -> SimResult:
    """Simulate battery dispatch over every slot of every day in `series`."""
    simulated_days = len(series.days)
    if simulated_days == 0:
        return _empty_sim_result()

    state = _initial_battery_state(spec)
    day_results: list[DaySimResult] = []
    actual_cost_pence: float | None = 0.0

    for day in series.days:
        state, day_result, actual_cost_pence = _simulate_day(
            day, tariff, spec, policy, state, actual_cost_pence
        )
        day_results.append(day_result)

    total_baseline_pence = sum(d.baseline_cost_pence for d in day_results)
    total_with_battery_pence = sum(d.total_cost_pence for d in day_results)
    total_savings_pence = total_baseline_pence - total_with_battery_pence
    annualized_savings_pence = total_savings_pence * 365 / simulated_days

    return SimResult(
        days=day_results,
        total_savings_pence=total_savings_pence,
        total_baseline_cost_pence=total_baseline_pence,
        total_with_battery_cost_pence=total_with_battery_pence,
        simulated_days=simulated_days,
        annualized_savings_pence=annualized_savings_pence,
        total_actual_current_cost_pence=actual_cost_pence,
    )
