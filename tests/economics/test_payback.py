"""Tests for ``economics.payback``."""

import math

import pytest

from windfall_tco.economics.payback import simple_payback_years


def test_normal_case():
    # £1000 system, 50000p/year = £500/year -> 2 years.
    assert simple_payback_years(1000.0, 50000.0) == pytest.approx(2.0, rel=1e-9)


def test_zero_savings_returns_none():
    assert simple_payback_years(1000.0, 0.0) is None


def test_negative_savings_returns_none():
    assert simple_payback_years(1000.0, -1.0) is None


def test_tiny_savings_is_huge_but_finite():
    result = simple_payback_years(1000.0, 0.001)
    assert result is not None
    assert math.isfinite(result)
    # £1000 / (0.001p/100 per year) = £1000 / £0.00001/year = 1e8 years.
    assert result > 1e6
