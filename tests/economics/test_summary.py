"""Tests for ``economics.summary.savings_summary``."""

import pytest

from windfall_tco.data_models import SimResult
from windfall_tco.economics.summary import savings_summary


def test_savings_summary_populated():
    result = SimResult(
        days=[],
        total_savings_pence=1000.0,
        total_baseline_cost_pence=5000.0,
        total_with_battery_cost_pence=4000.0,
        simulated_days=10,
        annualized_savings_pence=1000.0 * 365 / 10,
    )

    summary = savings_summary(result)

    assert summary.total_savings_pence == pytest.approx(1000.0, rel=1e-9)
    assert summary.simulated_days == 10
    assert summary.daily_average_savings_pence == pytest.approx(100.0, rel=1e-9)
    assert summary.annualized_savings_pence == pytest.approx(36500.0, rel=1e-9)
    assert summary.baseline_annualized_cost_pence == pytest.approx(
        5000.0 * 365 / 10, rel=1e-9
    )
    assert summary.with_battery_annualized_cost_pence == pytest.approx(
        4000.0 * 365 / 10, rel=1e-9
    )


def test_savings_summary_empty_simresult():
    """Zero simulated days must not divide by zero; all derived fields go to zero."""
    result = SimResult(
        days=[],
        total_savings_pence=0.0,
        total_baseline_cost_pence=0.0,
        total_with_battery_cost_pence=0.0,
        simulated_days=0,
        annualized_savings_pence=0.0,
    )

    summary = savings_summary(result)

    assert summary.total_savings_pence == 0.0
    assert summary.simulated_days == 0
    assert summary.daily_average_savings_pence == 0.0
    assert summary.annualized_savings_pence == 0.0
    assert summary.baseline_annualized_cost_pence == 0.0
    assert summary.with_battery_annualized_cost_pence == 0.0


def test_savings_summary_without_actual_cost_leaves_comparison_fields_none():
    """No actual cost on SimResult → three-way comparison fields stay None."""
    result = SimResult(
        days=[],
        total_savings_pence=1000.0,
        total_baseline_cost_pence=5000.0,
        total_with_battery_cost_pence=4000.0,
        simulated_days=10,
        annualized_savings_pence=1000.0 * 365 / 10,
        total_actual_current_cost_pence=None,
    )
    summary = savings_summary(result)
    assert summary.actual_current_annualized_cost_pence is None
    assert summary.tariff_switch_annualized_savings_pence is None
    assert summary.total_vs_current_annualized_savings_pence is None


def test_savings_summary_with_actual_cost_computes_comparison():
    """Cheaper-current-tariff case: tariff switch loses money, but battery recovers it."""
    # 10 simulated days. Current tariff cost 4500p; Cosy no-battery 5000p; Cosy+battery 4000p.
    # Annualization scale = 365/10 = 36.5x
    result = SimResult(
        days=[],
        total_savings_pence=1000.0,
        total_baseline_cost_pence=5000.0,
        total_with_battery_cost_pence=4000.0,
        simulated_days=10,
        annualized_savings_pence=1000.0 * 365 / 10,
        total_actual_current_cost_pence=4500.0,
    )
    summary = savings_summary(result)

    # Current actual annualized: 4500 * 36.5 = 164250
    assert summary.actual_current_annualized_cost_pence == pytest.approx(
        4500.0 * 365 / 10, rel=1e-9
    )
    # Tariff switch alone: current − baseline = 4500 - 5000 = -500 per 10 days → annualized -500*36.5
    # (Negative: switching to Cosy without a battery would cost more than current tariff.)
    assert summary.tariff_switch_annualized_savings_pence == pytest.approx(
        (4500.0 - 5000.0) * 365 / 10, rel=1e-9
    )
    # Total vs current: current − with_battery = 4500 - 4000 = 500 per 10 days → annualized 500*36.5
    # (Positive: full switch + battery is cheaper than staying put.)
    assert summary.total_vs_current_annualized_savings_pence == pytest.approx(
        (4500.0 - 4000.0) * 365 / 10, rel=1e-9
    )
