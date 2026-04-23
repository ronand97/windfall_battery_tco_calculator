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
