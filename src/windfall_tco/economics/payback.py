"""Simple payback helper."""


def simple_payback_years(
    battery_cost_pounds: float,
    annualized_savings_pence: float,
) -> float | None:
    """Years to recoup ``battery_cost_pounds`` given ``annualized_savings_pence``; ``None`` if no savings."""
    if annualized_savings_pence <= 0:
        return None
    return battery_cost_pounds / (annualized_savings_pence / 100)
