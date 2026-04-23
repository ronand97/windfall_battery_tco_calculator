"""Economics helpers: baseline cost, savings summary, simple payback."""

from .cost import baseline_daily_cost, cost_of_slots
from .payback import simple_payback_years
from .summary import savings_summary

__all__ = [
    "baseline_daily_cost",
    "cost_of_slots",
    "savings_summary",
    "simple_payback_years",
]
