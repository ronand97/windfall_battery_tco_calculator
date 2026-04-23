"""Atomic half-hour dispatch transition — pure function.

Implements the three-branch (DISCHARGE / CHARGE / IDLE) algorithm from spec §7.2.
The branch is selected purely by price vs. the dispatch policy thresholds.
`DispatchPolicy` guarantees `discharge_above > charge_below`, so the branches are
mutually exclusive.
"""

from __future__ import annotations

from datetime import time

from windfall_tco.data_models import (
    BatterySpec,
    BatteryState,
    DispatchPolicy,
    StepResult,
)

# Half an hour in hours — slot duration.
_SLOT_HOURS = 0.5


def step(
    prior_state: BatteryState,
    load_kwh: float,
    price_pence_per_kwh: float,
    spec: BatterySpec,
    policy: DispatchPolicy,
    *,
    timestamp_start: time,
) -> tuple[BatteryState, StepResult]:
    """Advance the battery state by one half-hour slot.

    Pure: returns a fresh `BatteryState` and a `StepResult` describing the slot.
    See spec §7.1 and §7.2 for the algorithm.
    """
    soc = prior_state.energy_stored_kwh
    efficiency = spec.round_trip_efficiency

    max_discharge_kwh = spec.max_discharge_power_w / 1000.0 * _SLOT_HOURS
    max_charge_kwh = spec.max_charge_power_w / 1000.0 * _SLOT_HOURS

    if price_pence_per_kwh >= policy.discharge_above_pence_per_kwh:
        # DISCHARGE branch.
        battery_discharge_kwh = min(max_discharge_kwh, load_kwh, soc)
        battery_charge_kwh = 0.0
        grid_import_kwh = load_kwh - battery_discharge_kwh
        new_soc = soc - battery_discharge_kwh
    elif price_pence_per_kwh <= policy.charge_below_pence_per_kwh:
        # CHARGE branch.
        headroom_kwh = spec.usable_capacity_kwh - soc
        effective_stored = min(max_charge_kwh * efficiency, headroom_kwh)
        # Guard against tiny negative values from float noise near full SoC.
        if effective_stored < 0.0:
            effective_stored = 0.0
        grid_kwh_for_charge = effective_stored / efficiency
        battery_charge_kwh = effective_stored
        battery_discharge_kwh = 0.0
        grid_import_kwh = load_kwh + grid_kwh_for_charge
        new_soc = soc + effective_stored
    else:
        # IDLE branch.
        battery_charge_kwh = 0.0
        battery_discharge_kwh = 0.0
        grid_import_kwh = load_kwh
        new_soc = soc

    grid_for_load_kwh = load_kwh - battery_discharge_kwh
    cost_pence = grid_import_kwh * price_pence_per_kwh

    new_state = BatteryState(energy_stored_kwh=new_soc)
    result = StepResult(
        timestamp_start=timestamp_start,
        load_kwh=load_kwh,
        price_pence_per_kwh=price_pence_per_kwh,
        grid_import_kwh=grid_import_kwh,
        grid_for_load_kwh=grid_for_load_kwh,
        battery_charge_kwh=battery_charge_kwh,
        battery_discharge_kwh=battery_discharge_kwh,
        battery_soc_kwh=new_soc,
        cost_pence=cost_pence,
    )
    return new_state, result
