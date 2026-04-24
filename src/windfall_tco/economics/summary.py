"""Pack a ``SimResult`` into a display-ready ``SavingsSummary``."""

from windfall_tco.data_models import SavingsSummary, SimResult


def savings_summary(result: SimResult) -> SavingsSummary:
    """Derive the headline summary fields.

    Always populates: daily average savings + annualized baseline/with-battery.
    Additionally, when the underlying ``SimResult`` carries
    ``total_actual_current_cost_pence`` (i.e. the CSV had cost data), populates
    the three-way comparison fields:
      * annualized current-tariff cost (user's actual billed cost scaled to a year)
      * tariff-switch savings: current − baseline (positive = switch saves money)
      * total-vs-current savings: current − with-battery (positive = full switch
        plus battery saves money vs. doing nothing)
    """
    simulated_days = result.simulated_days
    if simulated_days == 0:
        daily_average_savings_pence = 0.0
        baseline_annualized_cost_pence = 0.0
        with_battery_annualized_cost_pence = 0.0
        actual_current_annualized_cost_pence: float | None = None
        tariff_switch_annualized_savings_pence: float | None = None
        total_vs_current_annualized_savings_pence: float | None = None
    else:
        scale = 365 / simulated_days
        daily_average_savings_pence = result.total_savings_pence / simulated_days
        baseline_annualized_cost_pence = result.total_baseline_cost_pence * scale
        with_battery_annualized_cost_pence = result.total_with_battery_cost_pence * scale

        if result.total_actual_current_cost_pence is None:
            actual_current_annualized_cost_pence = None
            tariff_switch_annualized_savings_pence = None
            total_vs_current_annualized_savings_pence = None
        else:
            actual_current_annualized_cost_pence = (
                result.total_actual_current_cost_pence * scale
            )
            tariff_switch_annualized_savings_pence = (
                actual_current_annualized_cost_pence - baseline_annualized_cost_pence
            )
            total_vs_current_annualized_savings_pence = (
                actual_current_annualized_cost_pence - with_battery_annualized_cost_pence
            )

    return SavingsSummary(
        total_savings_pence=result.total_savings_pence,
        simulated_days=simulated_days,
        daily_average_savings_pence=daily_average_savings_pence,
        annualized_savings_pence=result.annualized_savings_pence,
        baseline_annualized_cost_pence=baseline_annualized_cost_pence,
        with_battery_annualized_cost_pence=with_battery_annualized_cost_pence,
        actual_current_annualized_cost_pence=actual_current_annualized_cost_pence,
        tariff_switch_annualized_savings_pence=tariff_switch_annualized_savings_pence,
        total_vs_current_annualized_savings_pence=(
            total_vs_current_annualized_savings_pence
        ),
    )
