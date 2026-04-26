"""Cost-of-slots / baseline-daily-cost helpers.

Pure functions: multiply each half-hour reading's kWh by the tariff rate at its
start time and sum. Unit: pence.
"""

from windfall_tco.data_models import DailyConsumption, HalfHourReading, Tariff


def cost_of_slots(readings: list[HalfHourReading], tariff: Tariff) -> float:
    """Total pence for a list of readings given a tariff. Uses ``tariff.rate_at``."""
    return sum(r.kwh * tariff.rate_at(r.start) for r in readings)


def baseline_daily_cost(day: DailyConsumption, tariff: Tariff) -> float:
    """Pence; equivalent to ``cost_of_slots(day.readings, tariff)``."""
    return cost_of_slots(day.readings, tariff)
