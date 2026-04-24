"""Pydantic data models for the windfall battery TCO calculator.

All models are frozen value objects. Time of day is represented as `datetime.time`.
Per the spec, tariff bands cover 00:00-24:00: the first band's `start` is `time(0, 0)`
and the last band's `end` is `time(0, 0)`, interpreted as "midnight of the next day"
(i.e. 24:00). Internal intervals are half-open `[start, end)`; the final band's
wrap-around end-of-day `time(0, 0)` is inclusive of the 23:30 slot.
"""

from __future__ import annotations

from datetime import date, time

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Canonical half-hour slot count per day.
_SLOTS_PER_DAY = 48


def _time_to_minutes(t: time, *, end: bool = False) -> int:
    """Map a `time` to minutes-from-midnight.

    `end=True` treats `time(0, 0)` as 24:00 (1440) rather than 0 — used for the
    wrap-around end-of-day convention on tariff band endpoints.
    """
    minutes = t.hour * 60 + t.minute
    if end and minutes == 0:
        return 24 * 60
    return minutes


def _canonical_half_hour_starts() -> list[time]:
    """Return the 48 canonical half-hour slot starts: 00:00, 00:30, ..., 23:30."""
    out: list[time] = []
    for i in range(_SLOTS_PER_DAY):
        total = i * 30
        out.append(time(hour=total // 60, minute=total % 60))
    return out


# -------- Tariff --------
class TariffBand(BaseModel):
    model_config = ConfigDict(frozen=True)
    start: time
    end: time
    rate_pence_per_kwh: float = Field(gt=0)


class Tariff(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    bands: list[TariffBand]

    @model_validator(mode="after")
    def _validate_bands(self) -> Tariff:
        if not self.bands:
            raise ValueError("Tariff must have at least one band")

        # Sort by start-of-day minutes (stable for the wrap-around convention).
        sorted_bands = sorted(self.bands, key=lambda b: _time_to_minutes(b.start))

        # First band must start at 00:00.
        if _time_to_minutes(sorted_bands[0].start) != 0:
            raise ValueError(
                f"Tariff {self.name!r}: bands must start at 00:00 "
                f"(got {sorted_bands[0].start.isoformat()})"
            )

        # Last band must end at 24:00 (represented as time(0, 0)).
        last_end_minutes = _time_to_minutes(sorted_bands[-1].end, end=True)
        if last_end_minutes != 24 * 60:
            raise ValueError(
                f"Tariff {self.name!r}: bands must end at 24:00 "
                f"(got {sorted_bands[-1].end.isoformat()})"
            )

        # Each band must be non-empty and contiguous with its successor.
        for i, band in enumerate(sorted_bands):
            is_last = i == len(sorted_bands) - 1
            start_min = _time_to_minutes(band.start)
            end_min = _time_to_minutes(band.end, end=is_last)
            if end_min <= start_min:
                raise ValueError(
                    f"Tariff {self.name!r}: band {band.start.isoformat()}"
                    f"-{band.end.isoformat()} has non-positive duration"
                )
            if not is_last:
                next_start_min = _time_to_minutes(sorted_bands[i + 1].start)
                if end_min < next_start_min:
                    raise ValueError(
                        f"Tariff {self.name!r}: gap between "
                        f"{band.end.isoformat()} and "
                        f"{sorted_bands[i + 1].start.isoformat()}"
                    )
                if end_min > next_start_min:
                    raise ValueError(
                        f"Tariff {self.name!r}: overlap between "
                        f"{band.end.isoformat()} and "
                        f"{sorted_bands[i + 1].start.isoformat()}"
                    )

        # Store the canonical sorted order.
        object.__setattr__(self, "bands", sorted_bands)
        return self

    def rate_at(self, t: time) -> float:
        """Return the pence/kWh rate for a given time-of-day.

        Uses half-open intervals `[start, end)`. The final band's wrap-around
        end at `time(0, 0)` is treated as 24:00, so `time(23, 30)` falls inside it.
        """
        minutes = _time_to_minutes(t)
        for i, band in enumerate(self.bands):
            is_last = i == len(self.bands) - 1
            start_min = _time_to_minutes(band.start)
            end_min = _time_to_minutes(band.end, end=is_last)
            if start_min <= minutes < end_min:
                return band.rate_pence_per_kwh
        # Unreachable given the validator guarantees full 00:00-24:00 coverage.
        raise ValueError(f"No band contains time {t.isoformat()}")


# -------- Battery --------
class BatterySpec(BaseModel):
    model_config = ConfigDict(frozen=True)
    usable_capacity_kwh: float = Field(gt=0, default=2.5)
    max_charge_power_w: float = Field(gt=0, default=800)
    max_discharge_power_w: float = Field(gt=0, default=800)
    round_trip_efficiency: float = Field(gt=0, le=1, default=0.90)
    initial_soc_fraction: float = Field(ge=0, le=1, default=0.5)


class BatteryState(BaseModel):
    model_config = ConfigDict(frozen=True)
    energy_stored_kwh: float = Field(ge=0)


# -------- Dispatch policy --------
class DispatchPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)
    charge_below_pence_per_kwh: float
    discharge_above_pence_per_kwh: float

    @model_validator(mode="after")
    def _validate_thresholds(self) -> DispatchPolicy:
        if self.discharge_above_pence_per_kwh <= self.charge_below_pence_per_kwh:
            raise ValueError(
                "DispatchPolicy: discharge_above_pence_per_kwh must be strictly "
                f"greater than charge_below_pence_per_kwh (got "
                f"discharge_above={self.discharge_above_pence_per_kwh}, "
                f"charge_below={self.charge_below_pence_per_kwh})"
            )
        return self


# -------- Consumption --------
class HalfHourReading(BaseModel):
    model_config = ConfigDict(frozen=True)
    start: time
    kwh: float = Field(ge=0)
    # Actual cost paid under the user's *current* tariff for this half-hour slot.
    # Populated by the Octopus CSV parser from the "Estimated Cost Inc. Tax (p)"
    # column; None for manually-entered profiles (where no billing data exists).
    current_cost_pence: float | None = Field(default=None, ge=0)


class DailyConsumption(BaseModel):
    model_config = ConfigDict(frozen=True)
    date: date
    readings: list[HalfHourReading]

    @model_validator(mode="after")
    def _validate_readings(self) -> DailyConsumption:
        if len(self.readings) != _SLOTS_PER_DAY:
            raise ValueError(
                f"DailyConsumption for {self.date}: expected exactly "
                f"{_SLOTS_PER_DAY} half-hour readings, got {len(self.readings)}"
            )

        starts = [r.start for r in self.readings]
        if starts != sorted(starts):
            raise ValueError(
                f"DailyConsumption for {self.date}: readings must be sorted by start time"
            )
        if len(set(starts)) != len(starts):
            raise ValueError(
                f"DailyConsumption for {self.date}: duplicate reading start times"
            )
        expected = _canonical_half_hour_starts()
        if starts != expected:
            raise ValueError(
                f"DailyConsumption for {self.date}: readings must cover the canonical "
                f"half-hour grid (00:00, 00:30, ..., 23:30) exactly, with no gaps"
            )
        return self


class ConsumptionSeries(BaseModel):
    model_config = ConfigDict(frozen=True)
    days: list[DailyConsumption]


# -------- Load result (from data_loading entrypoints) --------
class LoadResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    series: ConsumptionSeries
    warnings: list[str]


# -------- Simulation results --------
class StepResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    timestamp_start: time
    load_kwh: float
    price_pence_per_kwh: float
    grid_import_kwh: float
    grid_for_load_kwh: float
    battery_charge_kwh: float
    battery_discharge_kwh: float
    battery_soc_kwh: float
    cost_pence: float


class DaySimResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    date: date
    steps: list[StepResult]
    total_cost_pence: float
    baseline_cost_pence: float
    savings_pence: float


class SimResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    days: list[DaySimResult]
    total_savings_pence: float
    total_baseline_cost_pence: float
    total_with_battery_cost_pence: float
    simulated_days: int
    annualized_savings_pence: float
    # Total cost under the user's *current* tariff (from billing data, e.g. the
    # Octopus CSV cost column). None if any slot lacks this data (e.g. manual
    # profile). When present, enables the "current vs modeled vs with-battery"
    # three-way comparison in the UI.
    total_actual_current_cost_pence: float | None = None


# -------- Economics summary --------
class SavingsSummary(BaseModel):
    model_config = ConfigDict(frozen=True)
    total_savings_pence: float
    simulated_days: int
    daily_average_savings_pence: float
    annualized_savings_pence: float
    baseline_annualized_cost_pence: float
    with_battery_annualized_cost_pence: float
    # Actual-cost comparison fields. Non-None only when the underlying SimResult
    # carried current-tariff cost data (Octopus CSV upload path).
    actual_current_annualized_cost_pence: float | None = None
    tariff_switch_annualized_savings_pence: float | None = None
    total_vs_current_annualized_savings_pence: float | None = None
