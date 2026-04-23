"""Tests for the manual 24h profile parser (`src/windfall_tco/data_loading/manual_profile.py`)."""

from __future__ import annotations

from datetime import date, time

import pytest

from windfall_tco.data_loading.manual_profile import load_manual_profile


def test_flat_1kw_profile_gives_0_5_kwh_per_slot():
    watts = [1000.0] * 24
    result = load_manual_profile(watts)
    assert result.warnings == []
    assert len(result.series.days) == 1
    day = result.series.days[0]
    assert day.date == date.today()
    assert len(day.readings) == 48
    for r in day.readings:
        assert r.kwh == pytest.approx(0.5)


def test_each_hour_emits_two_matching_half_hour_slots():
    # Distinct per-hour values so we can check the split-into-twos behavior.
    watts = [100.0 * (h + 1) for h in range(24)]
    result = load_manual_profile(watts)
    day = result.series.days[0]
    for h in range(24):
        expected_kwh = watts[h] / 1000.0 * 0.5
        r_on = day.readings[2 * h]
        r_half = day.readings[2 * h + 1]
        assert r_on.start == time(hour=h, minute=0)
        assert r_half.start == time(hour=h, minute=30)
        assert r_on.kwh == pytest.approx(expected_kwh)
        assert r_half.kwh == pytest.approx(expected_kwh)


def test_custom_day_label_used():
    watts = [500.0] * 24
    result = load_manual_profile(watts, day=date(2020, 1, 1))
    assert result.series.days[0].date == date(2020, 1, 1)


@pytest.mark.parametrize("n", [0, 23, 25, 48])
def test_wrong_length_raises_value_error(n: int):
    with pytest.raises(ValueError, match="24 hourly watts values"):
        load_manual_profile([100.0] * n)


def test_negative_value_raises_value_error():
    watts = [100.0] * 24
    watts[5] = -1.0
    with pytest.raises(ValueError, match="negative watts"):
        load_manual_profile(watts)


def test_zero_values_allowed():
    result = load_manual_profile([0.0] * 24)
    for r in result.series.days[0].readings:
        assert r.kwh == pytest.approx(0.0)
