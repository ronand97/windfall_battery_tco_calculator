"""Tests for the Octopus CSV parser (`src/windfall_tco/data_loading/octopus_csv.py`)."""

from __future__ import annotations

import re
from datetime import date, time
from pathlib import Path

import pytest

from windfall_tco.data_loading.octopus_csv import load_octopus_csv

FIXTURES = Path(__file__).parent / "fixtures"


def test_normal_day_loads_one_day_with_48_readings():
    result = load_octopus_csv(FIXTURES / "normal_day.csv")
    assert result.warnings == []
    assert len(result.series.days) == 1
    day = result.series.days[0]
    assert day.date == date(2026, 4, 1)
    assert len(day.readings) == 48
    # Canonical start-of-day reading.
    assert day.readings[0].start == time(0, 0)
    assert day.readings[0].kwh == pytest.approx(0.1)
    # Final reading at 23:30.
    assert day.readings[-1].start == time(23, 30)


def test_multi_day_two_clean_days_sorted():
    result = load_octopus_csv(FIXTURES / "multi_day.csv")
    assert result.warnings == []
    assert [d.date for d in result.series.days] == [date(2026, 4, 1), date(2026, 4, 2)]
    for d in result.series.days:
        assert len(d.readings) == 48


def test_dst_spring_skips_46_slot_day():
    result = load_octopus_csv(FIXTURES / "dst_spring.csv")
    assert [d.date for d in result.series.days] == [date(2026, 3, 30)]
    assert len(result.warnings) == 1
    assert re.fullmatch(
        r"Skipped 2026-03-29: DST transition \(46 slots\)", result.warnings[0]
    )


def test_dst_autumn_skips_50_slot_day():
    result = load_octopus_csv(FIXTURES / "dst_autumn.csv")
    assert [d.date for d in result.series.days] == [date(2026, 10, 26)]
    assert len(result.warnings) == 1
    assert re.fullmatch(
        r"Skipped 2026-10-25: DST transition \(50 slots\)", result.warnings[0]
    )


def test_partial_day_skipped_with_partial_warning():
    result = load_octopus_csv(FIXTURES / "partial.csv")
    assert [d.date for d in result.series.days] == [date(2026, 5, 13)]
    assert len(result.warnings) == 1
    assert "partial data" in result.warnings[0]
    assert "37 slots" in result.warnings[0]


def test_all_zero_day_loads_with_zero_kwh():
    result = load_octopus_csv(FIXTURES / "all_zero.csv")
    assert result.warnings == []
    assert len(result.series.days) == 1
    day = result.series.days[0]
    assert day.date == date(2026, 4, 2)
    for r in day.readings:
        assert r.kwh == pytest.approx(0.0)


def test_missing_consumption_column_raises_value_error(tmp_path: Path):
    # Create a CSV without the Consumption (kwh) column.
    bad = tmp_path / "bad.csv"
    bad.write_text(
        "Estimated Cost Inc. Tax (p), Standing Charge Inc. Tax (p), Start, End\n"
        "6.42, 0.93, 2026-04-01T00:00:00+01:00, 2026-04-01T00:30:00+01:00\n"
    )
    with pytest.raises(ValueError, match="missing"):
        load_octopus_csv(bad)


def test_accepts_string_path():
    result = load_octopus_csv(str(FIXTURES / "normal_day.csv"))
    assert len(result.series.days) == 1


def test_accepts_bytes_payload():
    data = (FIXTURES / "normal_day.csv").read_bytes()
    result = load_octopus_csv(data)
    assert len(result.series.days) == 1


def test_accepts_file_like_object():
    with (FIXTURES / "normal_day.csv").open("rb") as fh:
        result = load_octopus_csv(fh)
    assert len(result.series.days) == 1


def test_empty_file_raises_value_error(tmp_path: Path):
    empty = tmp_path / "empty.csv"
    empty.write_text("")
    with pytest.raises(ValueError):
        load_octopus_csv(empty)
