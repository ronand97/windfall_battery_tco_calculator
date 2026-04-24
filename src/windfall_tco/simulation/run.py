"""Fold `step()` over a `ConsumptionSeries` to produce a `SimResult`.

Pure: no I/O. SoC is continuous across day boundaries. Baseline cost per day is
the sum of `load_kwh * price` over all slots (no battery action); per-day savings
are `baseline - total_cost`. See spec §7.3.
"""

from __future__ import annotations

from windfall_tco.data_models import (
    BatterySpec,
    BatteryState,
    ConsumptionSeries,
    DaySimResult,
    DispatchPolicy,
    SimResult,
    Tariff,
)
from windfall_tco.simulation.step import step


def run(
    series: ConsumptionSeries,
    tariff: Tariff,
    spec: BatterySpec,
    policy: DispatchPolicy,
) -> SimResult:
    """Simulate battery dispatch over every slot of every day in `series`."""
    simulated_days = len(series.days)

    # Edge case: empty series — emit a zeroed, well-formed SimResult.
    if simulated_days == 0:
        return SimResult(
            days=[],
            total_savings_pence=0.0,
            total_baseline_cost_pence=0.0,
            total_with_battery_cost_pence=0.0,
            simulated_days=0,
            annualized_savings_pence=0.0,
        )

    state = BatteryState(
        energy_stored_kwh=spec.initial_soc_fraction * spec.usable_capacity_kwh
    )

    day_results: list[DaySimResult] = []
    total_savings_pence = 0.0
    total_baseline_cost_pence = 0.0
    total_with_battery_cost_pence = 0.0
    # Aggregate the user's actual current-tariff cost from billing data on the
    # series. `None` means "unavailable for at least one slot" — if ANY reading
    # lacks cost data we treat the whole total as unavailable, since a partial
    # sum would be misleading when compared against the full-period modeled costs.
    actual_cost_pence: float | None = 0.0

    for day in series.days:
        step_results = []
        day_cost_pence = 0.0
        day_baseline_pence = 0.0
        for reading in day.readings:
            price = tariff.rate_at(reading.start)
            state, sr = step(
                prior_state=state,
                load_kwh=reading.kwh,
                price_pence_per_kwh=price,
                spec=spec,
                policy=policy,
                timestamp_start=reading.start,
            )
            step_results.append(sr)
            day_cost_pence += sr.cost_pence
            day_baseline_pence += reading.kwh * price
            if actual_cost_pence is not None:
                if reading.current_cost_pence is None:
                    actual_cost_pence = None
                else:
                    actual_cost_pence += reading.current_cost_pence

        day_savings_pence = day_baseline_pence - day_cost_pence
        day_results.append(
            DaySimResult(
                date=day.date,
                steps=step_results,
                total_cost_pence=day_cost_pence,
                baseline_cost_pence=day_baseline_pence,
                savings_pence=day_savings_pence,
            )
        )
        total_savings_pence += day_savings_pence
        total_baseline_cost_pence += day_baseline_pence
        total_with_battery_cost_pence += day_cost_pence

    annualized_savings_pence = total_savings_pence * 365 / simulated_days

    return SimResult(
        days=day_results,
        total_savings_pence=total_savings_pence,
        total_baseline_cost_pence=total_baseline_cost_pence,
        total_with_battery_cost_pence=total_with_battery_cost_pence,
        simulated_days=simulated_days,
        annualized_savings_pence=annualized_savings_pence,
        total_actual_current_cost_pence=actual_cost_pence,
    )
