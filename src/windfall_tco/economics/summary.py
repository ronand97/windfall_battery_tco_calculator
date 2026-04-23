"""Pack a ``SimResult`` into a display-ready ``SavingsSummary``."""

from windfall_tco.data_models import SavingsSummary, SimResult


def savings_summary(result: SimResult) -> SavingsSummary:
    """Derive the headline summary fields (daily average + annualized baseline/with-battery)."""
    simulated_days = result.simulated_days
    if simulated_days == 0:
        daily_average_savings_pence = 0.0
        baseline_annualized_cost_pence = 0.0
        with_battery_annualized_cost_pence = 0.0
    else:
        daily_average_savings_pence = result.total_savings_pence / simulated_days
        baseline_annualized_cost_pence = (
            result.total_baseline_cost_pence * 365 / simulated_days
        )
        with_battery_annualized_cost_pence = (
            result.total_with_battery_cost_pence * 365 / simulated_days
        )

    return SavingsSummary(
        total_savings_pence=result.total_savings_pence,
        simulated_days=simulated_days,
        daily_average_savings_pence=daily_average_savings_pence,
        annualized_savings_pence=result.annualized_savings_pence,
        baseline_annualized_cost_pence=baseline_annualized_cost_pence,
        with_battery_annualized_cost_pence=with_battery_annualized_cost_pence,
    )
