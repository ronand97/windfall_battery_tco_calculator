"""Unit + hypothesis property tests for `simulation.step()`."""

from __future__ import annotations

from datetime import time

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from windfall_tco.data_models import (
    BatterySpec,
    BatteryState,
    DispatchPolicy,
)
from windfall_tco.simulation.step import step

T0 = time(12, 0)


def _spec(
    *,
    capacity_kwh: float = 2.5,
    max_charge_w: float = 800.0,
    max_discharge_w: float = 800.0,
    efficiency: float = 0.9,
    initial_soc_fraction: float = 0.5,
) -> BatterySpec:
    return BatterySpec(
        usable_capacity_kwh=capacity_kwh,
        max_charge_power_w=max_charge_w,
        max_discharge_power_w=max_discharge_w,
        round_trip_efficiency=efficiency,
        initial_soc_fraction=initial_soc_fraction,
    )


def _policy(*, charge_below: float = 10.0, discharge_above: float = 20.0) -> DispatchPolicy:
    return DispatchPolicy(
        charge_below_pence_per_kwh=charge_below,
        discharge_above_pence_per_kwh=discharge_above,
    )


# ----------------------------- Discharge branch -----------------------------


def test_discharge_with_energy_discharges_up_to_min_of_power_load_soc() -> None:
    # max_discharge_kwh = 800 W * 0.5h / 1000 = 0.4 kWh.
    # load 1.0 kWh, SoC 2.0 kWh → discharges 0.4 kWh (power-limited).
    spec = _spec()
    policy = _policy()
    state = BatteryState(energy_stored_kwh=2.0)
    new_state, sr = step(
        prior_state=state,
        load_kwh=1.0,
        price_pence_per_kwh=30.0,
        spec=spec,
        policy=policy,
        timestamp_start=T0,
    )
    assert sr.battery_discharge_kwh == pytest.approx(0.4)
    assert sr.battery_charge_kwh == 0.0
    assert sr.grid_import_kwh == pytest.approx(0.6)
    assert sr.grid_for_load_kwh == pytest.approx(0.6)
    assert new_state.energy_stored_kwh == pytest.approx(1.6)
    assert sr.cost_pence == pytest.approx(0.6 * 30.0)


def test_discharge_capped_by_soc_when_battery_almost_empty() -> None:
    spec = _spec()
    policy = _policy()
    state = BatteryState(energy_stored_kwh=0.1)
    new_state, sr = step(
        prior_state=state,
        load_kwh=1.0,
        price_pence_per_kwh=30.0,
        spec=spec,
        policy=policy,
        timestamp_start=T0,
    )
    assert sr.battery_discharge_kwh == pytest.approx(0.1)
    assert sr.grid_import_kwh == pytest.approx(0.9)
    assert new_state.energy_stored_kwh == pytest.approx(0.0)


def test_discharge_with_empty_battery_emits_nothing() -> None:
    spec = _spec()
    policy = _policy()
    state = BatteryState(energy_stored_kwh=0.0)
    new_state, sr = step(
        prior_state=state,
        load_kwh=1.0,
        price_pence_per_kwh=30.0,
        spec=spec,
        policy=policy,
        timestamp_start=T0,
    )
    assert sr.battery_discharge_kwh == 0.0
    assert sr.battery_charge_kwh == 0.0
    assert sr.grid_import_kwh == pytest.approx(1.0)
    assert new_state.energy_stored_kwh == 0.0
    assert sr.cost_pence == pytest.approx(30.0)


def test_discharge_capped_by_load_when_load_is_smaller_than_max_discharge() -> None:
    # Load 0.05 kWh < max_discharge 0.4 kWh, plenty of SoC.
    spec = _spec()
    policy = _policy()
    state = BatteryState(energy_stored_kwh=2.0)
    new_state, sr = step(
        prior_state=state,
        load_kwh=0.05,
        price_pence_per_kwh=30.0,
        spec=spec,
        policy=policy,
        timestamp_start=T0,
    )
    assert sr.battery_discharge_kwh == pytest.approx(0.05)
    assert sr.grid_import_kwh == pytest.approx(0.0)
    assert sr.grid_for_load_kwh == pytest.approx(0.0)
    assert new_state.energy_stored_kwh == pytest.approx(1.95)
    assert sr.cost_pence == pytest.approx(0.0)


def test_discharge_at_exact_threshold_price_triggers_discharge() -> None:
    spec = _spec()
    policy = _policy(discharge_above=20.0)
    state = BatteryState(energy_stored_kwh=1.0)
    _, sr = step(
        prior_state=state,
        load_kwh=0.5,
        price_pence_per_kwh=20.0,  # == discharge_above → discharge branch (>= ).
        spec=spec,
        policy=policy,
        timestamp_start=T0,
    )
    assert sr.battery_discharge_kwh > 0.0


# ----------------------------- Charge branch -----------------------------


def test_charge_with_headroom_pulls_extra_grid_and_stores_efficiency_adjusted() -> None:
    # efficiency 0.9, max_charge_kwh = 0.4, load 0.2, SoC 0 → effective stored
    # = min(0.4 * 0.9, 2.5) = 0.36 kWh; grid_for_charge = 0.36 / 0.9 = 0.4 kWh;
    # grid_import = 0.6 kWh.
    spec = _spec(efficiency=0.9)
    policy = _policy(charge_below=5.0)
    state = BatteryState(energy_stored_kwh=0.0)
    new_state, sr = step(
        prior_state=state,
        load_kwh=0.2,
        price_pence_per_kwh=5.0,
        spec=spec,
        policy=policy,
        timestamp_start=T0,
    )
    assert sr.battery_charge_kwh == pytest.approx(0.36)
    assert sr.battery_discharge_kwh == 0.0
    assert sr.grid_import_kwh == pytest.approx(0.6)
    assert sr.grid_for_load_kwh == pytest.approx(0.2)
    assert new_state.energy_stored_kwh == pytest.approx(0.36)
    assert sr.cost_pence == pytest.approx(0.6 * 5.0)


def test_charge_at_full_soc_does_nothing() -> None:
    spec = _spec()
    policy = _policy(charge_below=5.0)
    state = BatteryState(energy_stored_kwh=spec.usable_capacity_kwh)
    new_state, sr = step(
        prior_state=state,
        load_kwh=0.2,
        price_pence_per_kwh=5.0,
        spec=spec,
        policy=policy,
        timestamp_start=T0,
    )
    assert sr.battery_charge_kwh == 0.0
    assert sr.battery_discharge_kwh == 0.0
    assert sr.grid_import_kwh == pytest.approx(0.2)
    assert new_state.energy_stored_kwh == pytest.approx(spec.usable_capacity_kwh)


def test_charge_at_50_percent_efficiency_doubles_grid_pull() -> None:
    # efficiency 0.5: storing X kWh pulls 2X from the grid.
    # max_charge_kwh * eff = 0.4 * 0.5 = 0.2 kWh; room 2.5 → stored 0.2, grid for charge 0.4.
    spec = _spec(efficiency=0.5)
    policy = _policy(charge_below=5.0)
    state = BatteryState(energy_stored_kwh=0.0)
    _, sr = step(
        prior_state=state,
        load_kwh=0.0,
        price_pence_per_kwh=5.0,
        spec=spec,
        policy=policy,
        timestamp_start=T0,
    )
    assert sr.battery_charge_kwh == pytest.approx(0.2)
    assert sr.grid_import_kwh == pytest.approx(0.4)
    assert sr.grid_import_kwh == pytest.approx(2 * sr.battery_charge_kwh)


def test_charge_capped_by_headroom_when_near_full() -> None:
    # 2.5 kWh capacity, 2.4 kWh stored → 0.1 kWh headroom caps the charge below
    # the efficiency-adjusted power limit (0.4 * 0.9 = 0.36 kWh).
    spec = _spec(efficiency=0.9)
    policy = _policy(charge_below=5.0)
    state = BatteryState(energy_stored_kwh=2.4)
    new_state, sr = step(
        prior_state=state,
        load_kwh=0.0,
        price_pence_per_kwh=5.0,
        spec=spec,
        policy=policy,
        timestamp_start=T0,
    )
    assert sr.battery_charge_kwh == pytest.approx(0.1)
    assert sr.grid_import_kwh == pytest.approx(0.1 / 0.9)
    assert new_state.energy_stored_kwh == pytest.approx(2.5)


# ----------------------------- Idle branch -----------------------------


def test_idle_mid_range_price_no_battery_action() -> None:
    spec = _spec()
    policy = _policy(charge_below=10.0, discharge_above=20.0)
    state = BatteryState(energy_stored_kwh=1.0)
    new_state, sr = step(
        prior_state=state,
        load_kwh=0.5,
        price_pence_per_kwh=15.0,
        spec=spec,
        policy=policy,
        timestamp_start=T0,
    )
    assert sr.battery_charge_kwh == 0.0
    assert sr.battery_discharge_kwh == 0.0
    assert sr.grid_import_kwh == pytest.approx(0.5)
    assert sr.grid_for_load_kwh == pytest.approx(0.5)
    assert new_state.energy_stored_kwh == pytest.approx(1.0)
    assert sr.cost_pence == pytest.approx(0.5 * 15.0)


def test_step_result_carries_timestamp_and_inputs() -> None:
    spec = _spec()
    policy = _policy()
    state = BatteryState(energy_stored_kwh=1.0)
    _, sr = step(
        prior_state=state,
        load_kwh=0.3,
        price_pence_per_kwh=15.0,
        spec=spec,
        policy=policy,
        timestamp_start=time(9, 30),
    )
    assert sr.timestamp_start == time(9, 30)
    assert sr.load_kwh == pytest.approx(0.3)
    assert sr.price_pence_per_kwh == pytest.approx(15.0)
    assert sr.battery_soc_kwh == pytest.approx(1.0)


# ----------------------------- Property-based tests -----------------------------


@st.composite
def _scenario(draw):  # type: ignore[no-untyped-def]
    capacity = draw(st.floats(min_value=0.1, max_value=50.0))
    max_charge_w = draw(st.floats(min_value=100.0, max_value=10_000.0))
    max_discharge_w = draw(st.floats(min_value=100.0, max_value=10_000.0))
    efficiency = draw(st.floats(min_value=0.5, max_value=1.0))
    initial_soc_fraction = draw(st.floats(min_value=0.0, max_value=1.0))

    charge_below = draw(st.floats(min_value=0.1, max_value=50.0))
    delta = draw(st.floats(min_value=0.01, max_value=50.0))
    discharge_above = charge_below + delta

    soc = draw(st.floats(min_value=0.0, max_value=capacity))
    load_kwh = draw(st.floats(min_value=0.0, max_value=5.0))
    price = draw(st.floats(min_value=0.01, max_value=100.0))

    spec = BatterySpec(
        usable_capacity_kwh=capacity,
        max_charge_power_w=max_charge_w,
        max_discharge_power_w=max_discharge_w,
        round_trip_efficiency=efficiency,
        initial_soc_fraction=initial_soc_fraction,
    )
    policy = DispatchPolicy(
        charge_below_pence_per_kwh=charge_below,
        discharge_above_pence_per_kwh=discharge_above,
    )
    state = BatteryState(energy_stored_kwh=soc)
    return spec, policy, state, load_kwh, price


_TOL = 1e-9
# Looser tolerance for the charge-branch identity which multiplies through a
# potentially small efficiency and divides back.
_CHARGE_TOL = 1e-7


@given(_scenario())
@settings(max_examples=400, suppress_health_check=[HealthCheck.too_slow])
def test_property_non_negative_flows_and_valid_soc(scenario) -> None:  # type: ignore[no-untyped-def]
    spec, policy, state, load_kwh, price = scenario
    new_state, sr = step(
        prior_state=state,
        load_kwh=load_kwh,
        price_pence_per_kwh=price,
        spec=spec,
        policy=policy,
        timestamp_start=T0,
    )
    assert sr.grid_import_kwh >= -_TOL
    assert sr.battery_charge_kwh >= -_TOL
    assert sr.battery_discharge_kwh >= -_TOL
    assert new_state.energy_stored_kwh >= -_TOL
    assert new_state.energy_stored_kwh <= spec.usable_capacity_kwh + 1e-9


@given(_scenario())
@settings(max_examples=400, suppress_health_check=[HealthCheck.too_slow])
def test_property_not_both_charge_and_discharge(scenario) -> None:  # type: ignore[no-untyped-def]
    spec, policy, state, load_kwh, price = scenario
    _, sr = step(
        prior_state=state,
        load_kwh=load_kwh,
        price_pence_per_kwh=price,
        spec=spec,
        policy=policy,
        timestamp_start=T0,
    )
    assert not (sr.battery_charge_kwh > 0 and sr.battery_discharge_kwh > 0)


@given(_scenario())
@settings(max_examples=400, suppress_health_check=[HealthCheck.too_slow])
def test_property_load_satisfaction(scenario) -> None:  # type: ignore[no-untyped-def]
    spec, policy, state, load_kwh, price = scenario
    _, sr = step(
        prior_state=state,
        load_kwh=load_kwh,
        price_pence_per_kwh=price,
        spec=spec,
        policy=policy,
        timestamp_start=T0,
    )
    assert abs(load_kwh - (sr.battery_discharge_kwh + sr.grid_for_load_kwh)) < _TOL


@given(_scenario())
@settings(max_examples=400, suppress_health_check=[HealthCheck.too_slow])
def test_property_per_branch_conservation(scenario) -> None:  # type: ignore[no-untyped-def]
    spec, policy, state, load_kwh, price = scenario
    _, sr = step(
        prior_state=state,
        load_kwh=load_kwh,
        price_pence_per_kwh=price,
        spec=spec,
        policy=policy,
        timestamp_start=T0,
    )
    if price >= policy.discharge_above_pence_per_kwh:
        assert sr.battery_charge_kwh == 0.0
        assert abs(sr.grid_import_kwh - (load_kwh - sr.battery_discharge_kwh)) < _TOL
    elif price <= policy.charge_below_pence_per_kwh:
        assert sr.battery_discharge_kwh == 0.0
        expected = load_kwh + sr.battery_charge_kwh / spec.round_trip_efficiency
        assert abs(sr.grid_import_kwh - expected) < _CHARGE_TOL
    else:
        assert sr.battery_charge_kwh == 0.0
        assert sr.battery_discharge_kwh == 0.0
        assert abs(sr.grid_import_kwh - load_kwh) < _TOL


@given(_scenario())
@settings(max_examples=400, suppress_health_check=[HealthCheck.too_slow])
def test_property_soc_delta_matches_flow(scenario) -> None:  # type: ignore[no-untyped-def]
    spec, policy, state, load_kwh, price = scenario
    new_state, sr = step(
        prior_state=state,
        load_kwh=load_kwh,
        price_pence_per_kwh=price,
        spec=spec,
        policy=policy,
        timestamp_start=T0,
    )
    delta = new_state.energy_stored_kwh - state.energy_stored_kwh
    assert abs(delta - (sr.battery_charge_kwh - sr.battery_discharge_kwh)) < _TOL
