"""Manual 24-row watts-per-hour profile parser (§8.2).

Convert a list of 24 hourly average-watts values into a single-day
`ConsumptionSeries`. Each hourly value yields two identical half-hour kWh
readings (kwh = watts / 1000 * 0.5).
"""

from __future__ import annotations

from datetime import date as date_cls
from datetime import time

from windfall_tco.data_models import (
    ConsumptionSeries,
    DailyConsumption,
    HalfHourReading,
    LoadResult,
)

_HOURS_PER_DAY = 24


def load_manual_profile(
    watts_per_hour: list[float],
    day: date_cls | None = None,
) -> LoadResult:
    """Convert 24 hourly average-watts values into a single-day `ConsumptionSeries`.

    Args:
        watts_per_hour: 24 non-negative floats, one per hour starting at 00:00.
        day: Optional calendar date label for the resulting day. Defaults to
            `date.today()`. The date is a label only; downstream simulation
            annualizes by ×365 regardless.

    Raises:
        ValueError: If `watts_per_hour` does not contain exactly 24 entries, or
            if any entry is negative.
    """
    if len(watts_per_hour) != _HOURS_PER_DAY:
        raise ValueError(
            f"Manual profile: expected exactly {_HOURS_PER_DAY} hourly watts values, "
            f"got {len(watts_per_hour)}"
        )

    for idx, w in enumerate(watts_per_hour):
        if w < 0:
            raise ValueError(
                f"Manual profile: negative watts at hour {idx} ({w!r}); "
                "values must be >= 0"
            )

    readings: list[HalfHourReading] = []
    for hour, watts in enumerate(watts_per_hour):
        kwh = watts / 1000.0 * 0.5
        readings.append(HalfHourReading(start=time(hour=hour, minute=0), kwh=kwh))
        readings.append(HalfHourReading(start=time(hour=hour, minute=30), kwh=kwh))

    label_date = day if day is not None else date_cls.today()
    daily = DailyConsumption(date=label_date, readings=readings)
    series = ConsumptionSeries(days=[daily])
    return LoadResult(series=series, warnings=[])
