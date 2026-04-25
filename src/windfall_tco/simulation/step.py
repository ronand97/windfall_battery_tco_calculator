"""Atomic half-hour dispatch transition — pure function.

Implements the three-branch (DISCHARGE / CHARGE / IDLE) algorithm from spec §7.2.
The branch is selected purely by price vs. the dispatch policy thresholds.
`DispatchPolicy` guarantees `discharge_above > charge_below`, so the branches are
mutually exclusive.

Internal structure:
    decide_action()   — picks the branch from price + policy (the "decision")
    _flows_for_*()    — compute energy flows for each branch (the "execution")
    step()            — orchestrator that wires them together
"""

from __future__ import annotations

from datetime import time
from typing import Literal, NamedTuple

from windfall_tco.data_models import (
    BatterySpec,
    BatteryState,
    DispatchPolicy,
    StepResult,
)

# Half an hour in hours — slot duration.
_SLOT_HOURS = 0.5

# A purely-internal value type for the four energy quantities a branch produces.
# Lighter than a pydantic model and immutable like the rest of the domain.
class _Flows(NamedTuple):
    battery_charge_kwh: float
    battery_discharge_kwh: float
    grid_import_kwh: float
    new_soc_kwh: float

DispatchAction = Literal["discharge", "charge", "idle"]


def decide_action(
    price_pence_per_kwh: float,
    policy: DispatchPolicy,
) -> DispatchAction:
    """Pick which dispatch branch applies for this slot's price.

    The decision is *only* a function of the spot price and the policy's two
    thresholds — no battery state, no load. This is what makes the policy a
    "stateless price-threshold rule" (spec §3.4).
    """
    if price_pence_per_kwh >= policy.discharge_above_pence_per_kwh:
        return "discharge"
    if price_pence_per_kwh <= policy.charge_below_pence_per_kwh:
        return "charge"
    return "idle"


def _flows_for_discharge(
    soc_kwh: float,
    load_kwh: float,
    max_discharge_kwh: float,
) -> _Flows:
    """Battery serves the load up to its power and energy limits; rest from grid."""
    battery_discharge_kwh = min(max_discharge_kwh, load_kwh, soc_kwh)
    return _Flows(
        battery_charge_kwh=0.0,
        battery_discharge_kwh=battery_discharge_kwh,
        grid_import_kwh=load_kwh - battery_discharge_kwh,
        new_soc_kwh=soc_kwh - battery_discharge_kwh,
    )


def _flows_for_charge(
    soc_kwh: float,
    load_kwh: float,
    capacity_kwh: float,
    max_charge_kwh: float,
    efficiency: float,
) -> _Flows:
    """Battery charges from grid; round-trip efficiency loss is paid on the grid side."""
    headroom_kwh = capacity_kwh - soc_kwh
    # The float guard handles tiny negatives near full SoC.
    effective_stored = max(0.0, min(max_charge_kwh * efficiency, headroom_kwh))
    grid_kwh_for_charge = effective_stored / efficiency if effective_stored > 0 else 0.0
    return _Flows(
        battery_charge_kwh=effective_stored,
        battery_discharge_kwh=0.0,
        grid_import_kwh=load_kwh + grid_kwh_for_charge,
        new_soc_kwh=soc_kwh + effective_stored,
    )


def _flows_for_idle(soc_kwh: float, load_kwh: float) -> _Flows:
    """Battery does nothing; load met entirely from grid."""
    return _Flows(
        battery_charge_kwh=0.0,
        battery_discharge_kwh=0.0,
        grid_import_kwh=load_kwh,
        new_soc_kwh=soc_kwh,
    )


def _flows_for_action(
    action: DispatchAction,
    soc_kwh: float,
    load_kwh: float,
    spec: BatterySpec,
) -> _Flows:
    """Dispatch on the chosen action and return the resulting energy flows."""
    max_discharge_kwh = spec.max_discharge_power_w / 1000.0 * _SLOT_HOURS
    max_charge_kwh = spec.max_charge_power_w / 1000.0 * _SLOT_HOURS
    if action == "discharge":
        return _flows_for_discharge(soc_kwh, load_kwh, max_discharge_kwh)
    if action == "charge":
        return _flows_for_charge(
            soc_kwh,
            load_kwh,
            spec.usable_capacity_kwh,
            max_charge_kwh,
            spec.round_trip_efficiency,
        )
    return _flows_for_idle(soc_kwh, load_kwh)


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
    action = decide_action(price_pence_per_kwh, policy)
    flows = _flows_for_action(
        action,
        soc_kwh=prior_state.energy_stored_kwh,
        load_kwh=load_kwh,
        spec=spec,
    )

    new_state = BatteryState(energy_stored_kwh=flows.new_soc_kwh)
    result = StepResult(
        timestamp_start=timestamp_start,
        load_kwh=load_kwh,
        price_pence_per_kwh=price_pence_per_kwh,
        grid_import_kwh=flows.grid_import_kwh,
        # Per spec §7.2: load minus what the battery covered, identical across
        # all three branches (battery_discharge_kwh is 0 outside the discharge
        # branch, so this collapses to load_kwh there).
        grid_for_load_kwh=load_kwh - flows.battery_discharge_kwh,
        battery_charge_kwh=flows.battery_charge_kwh,
        battery_discharge_kwh=flows.battery_discharge_kwh,
        battery_soc_kwh=flows.new_soc_kwh,
        cost_pence=flows.grid_import_kwh * price_pence_per_kwh,
    )
    return new_state, result
