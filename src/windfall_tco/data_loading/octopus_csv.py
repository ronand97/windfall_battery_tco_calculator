"""Octopus half-hourly consumption CSV parser.

Implements §8.1 of the design spec: read an Octopus consumption export, group
rows by local (UK wall-clock) date, and keep only days that cover the canonical
48-slot half-hour grid. Skipped days produce warning strings.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import IO

import pandas as pd

from windfall_tco.data_models import (
    ConsumptionSeries,
    DailyConsumption,
    HalfHourReading,
    LoadResult,
)

_CONSUMPTION_COL = "Consumption (kwh)"
_START_COL = "Start"
_LOCAL_TZ = "Europe/London"
_SLOTS_PER_DAY = 48


def _read_csv(source: Path | str | bytes | IO) -> pd.DataFrame:
    """Read a CSV from any of the supported source types.

    `pd.read_csv` accepts paths and file-like objects directly; raw `bytes` are
    wrapped in a `BytesIO` first.
    """
    if isinstance(source, bytes):
        source = BytesIO(source)
    try:
        df = pd.read_csv(source, skipinitialspace=True)
    except pd.errors.EmptyDataError as exc:
        raise ValueError("Octopus CSV is empty") from exc
    # Strip any remaining whitespace from column names (belt + braces alongside
    # skipinitialspace, which only strips leading whitespace from field values).
    df.columns = [str(c).strip() for c in df.columns]
    return df


def load_octopus_csv(source: Path | str | bytes | IO) -> LoadResult:
    """Parse an Octopus half-hourly consumption export.

    Accepts a filesystem path (str or Path), raw bytes, or a file-like object
    (e.g. the `UploadedFile` Streamlit hands back). Returns a `LoadResult`
    containing a `ConsumptionSeries` of every fully-covered local date plus a
    list of warning strings for skipped days (DST transitions, partial data).

    Raises `ValueError` on hard failures: missing required columns, unparsable
    timestamps, or an empty file.
    """
    df = _read_csv(source)

    # Column-presence check up front — produces the clearest diagnostic.
    missing = [c for c in (_CONSUMPTION_COL, _START_COL) if c not in df.columns]
    if missing:
        raise ValueError(
            f"Octopus CSV missing required columns: {missing} "
            f"(found columns: {list(df.columns)})"
        )

    if df.empty:
        raise ValueError("Octopus CSV has no rows")

    # Parse timestamps. Each row carries its own UTC offset, so we anchor to UTC
    # and convert to Europe/London wall-clock for date/time grouping.
    try:
        start_utc = pd.to_datetime(df[_START_COL], utc=True, format="ISO8601")
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Octopus CSV: unparsable Start timestamps: {exc}") from exc
    if start_utc.isna().any():
        bad_idx = start_utc.index[start_utc.isna()].tolist()
        raise ValueError(
            f"Octopus CSV: unparsable Start timestamps at rows {bad_idx[:5]}"
        )

    start_local = start_utc.dt.tz_convert(_LOCAL_TZ)

    # Build a working frame of local date / time / kwh, sorted for determinism.
    work = pd.DataFrame(
        {
            "date": start_local.dt.date,
            "time": start_local.dt.time,
            "kwh": pd.to_numeric(df[_CONSUMPTION_COL], errors="coerce"),
        }
    )
    if work["kwh"].isna().any():
        raise ValueError("Octopus CSV: non-numeric values in 'Consumption (kwh)' column")

    # Expected half-hour starts.
    from datetime import time as _time

    expected_starts = tuple(
        _time(hour=i // 2, minute=(i % 2) * 30) for i in range(_SLOTS_PER_DAY)
    )

    warnings: list[str] = []
    days: list[DailyConsumption] = []

    # Group by local date, process each in calendar order.
    for local_date, group in sorted(work.groupby("date"), key=lambda kv: kv[0]):
        n = len(group)
        if n != _SLOTS_PER_DAY:
            if n in (46, 50):
                warnings.append(f"Skipped {local_date}: DST transition ({n} slots)")
            else:
                warnings.append(f"Skipped {local_date}: partial data ({n} slots)")
            continue

        sorted_group = group.sort_values("time", kind="stable")
        times = tuple(sorted_group["time"].tolist())
        if times != expected_starts:
            # 48 rows but not the canonical grid (duplicates, gaps, off-grid offsets).
            warnings.append(f"Skipped {local_date}: partial data ({n} slots)")
            continue

        readings = [
            HalfHourReading(start=t, kwh=float(kwh))
            for t, kwh in zip(
                sorted_group["time"].tolist(), sorted_group["kwh"].tolist(), strict=True
            )
        ]
        days.append(DailyConsumption(date=local_date, readings=readings))

    series = ConsumptionSeries(days=days)
    return LoadResult(series=series, warnings=warnings)
