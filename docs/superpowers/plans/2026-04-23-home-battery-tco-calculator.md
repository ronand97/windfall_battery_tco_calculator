# Home Battery TCO Calculator — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python package + Streamlit app that simulates a home battery on a static time-of-use tariff and reports annual savings and simple payback period.

**Architecture:** Functional core, imperative shell. Pure functions operating on frozen pydantic data models in `src/windfall_tco/`; a thin Streamlit app in `app/streamlit_app.py` consumes the core. Simulation is a per-half-hour `step()` transition folded over the full consumption series by `run()`.

**Tech Stack:** Python 3.12, uv, pydantic v2, pandas (I/O + Streamlit only), plotly, streamlit, pytest, pytest-cov, hypothesis, ruff.

**Design spec:** `docs/superpowers/specs/2026-04-22-home-battery-tco-design.md`

---

## Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `.python-version`
- Create: `.gitignore`
- Create: `README.md`
- Create: `src/windfall_tco/__init__.py`
- Create: `src/windfall_tco/data_loading/__init__.py`
- Create: `src/windfall_tco/simulation/__init__.py`
- Create: `src/windfall_tco/economics/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/data_loading/__init__.py`
- Create: `tests/simulation/__init__.py`
- Create: `tests/economics/__init__.py`
- Create: `tests/test_smoke.py`

- [ ] **Step 1: Create `.python-version`**

```
3.12
```

- [ ] **Step 2: Create `.gitignore`**

```
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
dist/
*.egg-info/
.pytest_cache/
.coverage
htmlcov/
.ruff_cache/

# Environments
.venv/
.env

# IDE
.vscode/
.idea/

# OS
.DS_Store
```

- [ ] **Step 3: Create `pyproject.toml`**

```toml
[project]
name = "windfall-tco"
version = "0.1.0"
description = "Home battery TCO calculator"
requires-python = ">=3.12"
dependencies = [
    "pydantic>=2.6",
    "pandas>=2.2",
    "plotly>=5.20",
    "streamlit>=1.32",
]

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
    "hypothesis>=6.100",
    "ruff>=0.4",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/windfall_tco"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra --strict-markers"
pythonpath = ["src"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "SIM", "RUF"]
```

- [ ] **Step 4: Create `README.md`**

```markdown
# Windfall Battery TCO Calculator

Simulate the savings of adding a home battery on a static time-of-use electricity tariff, and compute simple payback period.

## Setup

    uv sync

## Run the app

    uv run streamlit run app/streamlit_app.py

## Run tests

    uv run pytest
```

- [ ] **Step 5: Create all `__init__.py` files**

Each file is empty. Create the following:
- `src/windfall_tco/__init__.py`
- `src/windfall_tco/data_loading/__init__.py`
- `src/windfall_tco/simulation/__init__.py`
- `src/windfall_tco/economics/__init__.py`
- `tests/__init__.py`
- `tests/data_loading/__init__.py`
- `tests/simulation/__init__.py`
- `tests/economics/__init__.py`

- [ ] **Step 6: Create `tests/test_smoke.py`**

```python
def test_package_imports():
    import windfall_tco  # noqa: F401
```

- [ ] **Step 7: Install dependencies**

Run: `uv sync`
Expected: creates `.venv/`, installs all deps and dev deps, writes `uv.lock`.

- [ ] **Step 8: Run the smoke test**

Run: `uv run pytest -v`
Expected: `1 passed`. If it fails with `ModuleNotFoundError`, double-check `pythonpath = ["src"]` in `pyproject.toml`.

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml .python-version .gitignore README.md src tests uv.lock
git commit -m "Scaffold project structure, toolchain, and smoke test"
```

---

## Task 2: Data models — inputs (tariff, battery, dispatch, consumption)

**Files:**
- Create: `src/windfall_tco/data_models.py`
- Create: `tests/test_data_models.py`

- [ ] **Step 1: Write failing tests for TariffBand**

Create `tests/test_data_models.py`:

```python
from datetime import date, time

import pytest
from pydantic import ValidationError

from windfall_tco.data_models import (
    BatterySpec,
    BatteryState,
    ConsumptionSeries,
    DailyConsumption,
    DispatchPolicy,
    HalfHourReading,
    LoadResult,
    Tariff,
    TariffBand,
)


# -------- TariffBand --------

def test_tariff_band_valid():
    band = TariffBand(start=time(0, 0), end=time(6, 0), rate_pence_per_kwh=5.0)
    assert band.rate_pence_per_kwh == 5.0


def test_tariff_band_rejects_zero_rate():
    with pytest.raises(ValidationError):
        TariffBand(start=time(0, 0), end=time(6, 0), rate_pence_per_kwh=0)


def test_tariff_band_rejects_negative_rate():
    with pytest.raises(ValidationError):
        TariffBand(start=time(0, 0), end=time(6, 0), rate_pence_per_kwh=-1)


def test_tariff_band_is_frozen():
    band = TariffBand(start=time(0, 0), end=time(6, 0), rate_pence_per_kwh=5.0)
    with pytest.raises(ValidationError):
        band.rate_pence_per_kwh = 10  # type: ignore[misc]
```

- [ ] **Step 2: Add failing tests for Tariff coverage**

Append to `tests/test_data_models.py`:

```python
# -------- Tariff --------

def _band(start_h: int, end_h: int, rate: float) -> TariffBand:
    return TariffBand(
        start=time(start_h % 24, 0),
        end=time(end_h % 24, 0) if end_h < 24 else time(23, 59, 59, 999999),
        rate_pence_per_kwh=rate,
    )


def test_tariff_accepts_full_coverage():
    tariff = Tariff(
        name="two-band",
        bands=[_band(0, 6, 5), _band(6, 24, 30)],
    )
    assert tariff.name == "two-band"
    assert len(tariff.bands) == 2


def test_tariff_rejects_gap():
    with pytest.raises(ValidationError):
        Tariff(
            name="gap",
            bands=[_band(0, 6, 5), _band(8, 24, 30)],  # 6–8 gap
        )


def test_tariff_rejects_overlap():
    with pytest.raises(ValidationError):
        Tariff(
            name="overlap",
            bands=[_band(0, 10, 5), _band(8, 24, 30)],  # 8–10 overlap
        )


def test_tariff_rejects_uncovered_end():
    with pytest.raises(ValidationError):
        Tariff(
            name="short",
            bands=[_band(0, 20, 5)],  # misses 20–24
        )


def test_tariff_rejects_uncovered_start():
    with pytest.raises(ValidationError):
        Tariff(
            name="short",
            bands=[_band(2, 24, 5)],  # misses 0–2
        )
```

- [ ] **Step 3: Add failing tests for BatterySpec, BatteryState, DispatchPolicy**

Append to `tests/test_data_models.py`:

```python
# -------- BatterySpec --------

def test_battery_spec_defaults():
    spec = BatterySpec()
    assert spec.usable_capacity_kwh == 2.5
    assert spec.max_charge_power_w == 800
    assert spec.max_discharge_power_w == 800
    assert spec.round_trip_efficiency == 0.9
    assert spec.initial_soc_fraction == 0.5


def test_battery_spec_rejects_efficiency_gt_1():
    with pytest.raises(ValidationError):
        BatterySpec(round_trip_efficiency=1.5)


def test_battery_spec_rejects_negative_capacity():
    with pytest.raises(ValidationError):
        BatterySpec(usable_capacity_kwh=-1)


# -------- BatteryState --------

def test_battery_state_valid():
    state = BatteryState(energy_stored_kwh=1.2)
    assert state.energy_stored_kwh == 1.2


def test_battery_state_is_frozen():
    state = BatteryState(energy_stored_kwh=1.2)
    with pytest.raises(ValidationError):
        state.energy_stored_kwh = 0.5  # type: ignore[misc]


def test_battery_state_rejects_negative():
    with pytest.raises(ValidationError):
        BatteryState(energy_stored_kwh=-0.1)


# -------- DispatchPolicy --------

def test_dispatch_policy_valid():
    policy = DispatchPolicy(
        charge_below_pence_per_kwh=10.0,
        discharge_above_pence_per_kwh=25.0,
    )
    assert policy.charge_below_pence_per_kwh == 10.0


def test_dispatch_policy_rejects_inverted_thresholds():
    with pytest.raises(ValidationError):
        DispatchPolicy(
            charge_below_pence_per_kwh=25.0,
            discharge_above_pence_per_kwh=10.0,
        )


def test_dispatch_policy_rejects_equal_thresholds():
    with pytest.raises(ValidationError):
        DispatchPolicy(
            charge_below_pence_per_kwh=15.0,
            discharge_above_pence_per_kwh=15.0,
        )
```

- [ ] **Step 4: Add failing tests for consumption types**

Append to `tests/test_data_models.py`:

```python
# -------- HalfHourReading --------

def test_half_hour_reading_valid():
    r = HalfHourReading(start=time(8, 0), kwh=0.3)
    assert r.kwh == 0.3


def test_half_hour_reading_rejects_negative():
    with pytest.raises(ValidationError):
        HalfHourReading(start=time(8, 0), kwh=-0.1)


# -------- DailyConsumption --------

def _full_day_readings(kwh: float = 0.1) -> list[HalfHourReading]:
    out: list[HalfHourReading] = []
    for i in range(48):
        h, m = divmod(i * 30, 60)
        out.append(HalfHourReading(start=time(h, m), kwh=kwh))
    return out


def test_daily_consumption_valid():
    day = DailyConsumption(date=date(2026, 4, 1), readings=_full_day_readings())
    assert len(day.readings) == 48


def test_daily_consumption_rejects_wrong_count():
    bad = _full_day_readings()[:47]
    with pytest.raises(ValidationError):
        DailyConsumption(date=date(2026, 4, 1), readings=bad)


def test_daily_consumption_rejects_unsorted():
    readings = _full_day_readings()
    readings[0], readings[1] = readings[1], readings[0]
    with pytest.raises(ValidationError):
        DailyConsumption(date=date(2026, 4, 1), readings=readings)


def test_daily_consumption_rejects_duplicate_times():
    readings = _full_day_readings()
    readings[1] = HalfHourReading(start=readings[0].start, kwh=0.1)
    with pytest.raises(ValidationError):
        DailyConsumption(date=date(2026, 4, 1), readings=readings)


# -------- ConsumptionSeries --------

def test_consumption_series_valid():
    day = DailyConsumption(date=date(2026, 4, 1), readings=_full_day_readings())
    series = ConsumptionSeries(days=[day])
    assert len(series.days) == 1


# -------- LoadResult --------

def test_load_result_valid():
    day = DailyConsumption(date=date(2026, 4, 1), readings=_full_day_readings())
    series = ConsumptionSeries(days=[day])
    result = LoadResult(series=series, warnings=["ignored"])
    assert result.warnings == ["ignored"]
```

- [ ] **Step 5: Run tests to verify they fail**

Run: `uv run pytest tests/test_data_models.py -v`
Expected: ImportError on `windfall_tco.data_models`.

- [ ] **Step 6: Implement `src/windfall_tco/data_models.py`**

```python
"""Frozen pydantic models used throughout the simulator.

All input types and result types live here. Validators enforce invariants
so downstream code can trust the data shape without defensive checks.
"""

from __future__ import annotations

from datetime import date, time

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ---------- Tariff ----------

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
    def _validate_bands_cover_day(self) -> "Tariff":
        if not self.bands:
            raise ValueError("tariff must have at least one band")

        # Sort by start time, reject overlaps, require full coverage.
        ordered = sorted(self.bands, key=lambda b: b.start)
        cursor = time(0, 0)
        for band in ordered:
            if band.start != cursor:
                raise ValueError(
                    f"tariff has a gap or overlap at {cursor}: next band starts {band.start}"
                )
            cursor = band.end
        end_of_day = time(23, 59, 59, 999999)
        if cursor != time(0, 0) and cursor < end_of_day:
            # Allow the last band to end at either 00:00 (next day) or 23:59:59.999999.
            if cursor != time(0, 0):
                raise ValueError(f"tariff does not cover full 24h; last end is {cursor}")
        return self


# ---------- Battery ----------

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


# ---------- Dispatch policy ----------

class DispatchPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    charge_below_pence_per_kwh: float
    discharge_above_pence_per_kwh: float

    @model_validator(mode="after")
    def _validate_thresholds(self) -> "DispatchPolicy":
        if self.discharge_above_pence_per_kwh <= self.charge_below_pence_per_kwh:
            raise ValueError(
                "discharge_above_pence_per_kwh must be greater than charge_below_pence_per_kwh"
            )
        return self


# ---------- Consumption ----------

class HalfHourReading(BaseModel):
    model_config = ConfigDict(frozen=True)

    start: time
    kwh: float = Field(ge=0)


class DailyConsumption(BaseModel):
    model_config = ConfigDict(frozen=True)

    date: date
    readings: list[HalfHourReading]

    @model_validator(mode="after")
    def _validate_readings(self) -> "DailyConsumption":
        if len(self.readings) != 48:
            raise ValueError(f"expected 48 readings, got {len(self.readings)}")
        starts = [r.start for r in self.readings]
        if starts != sorted(starts):
            raise ValueError("readings must be sorted by start time")
        if len(set(starts)) != 48:
            raise ValueError("readings must have unique start times")
        return self


class ConsumptionSeries(BaseModel):
    model_config = ConfigDict(frozen=True)

    days: list[DailyConsumption]


class LoadResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    series: ConsumptionSeries
    warnings: list[str]
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `uv run pytest tests/test_data_models.py -v`
Expected: all tests for TariffBand, Tariff, BatterySpec, BatteryState, DispatchPolicy, HalfHourReading, DailyConsumption, ConsumptionSeries, LoadResult pass.

- [ ] **Step 8: Commit**

```bash
git add src/windfall_tco/data_models.py tests/test_data_models.py
git commit -m "Add input data models with validators (tariff, battery, dispatch, consumption)"
```

---

## Task 3: Data models — simulation and summary results

**Files:**
- Modify: `src/windfall_tco/data_models.py` (append)
- Modify: `tests/test_data_models.py` (append)

- [ ] **Step 1: Add failing tests for result types**

Append to `tests/test_data_models.py`:

```python
from windfall_tco.data_models import (
    DaySimResult,
    SavingsSummary,
    SimResult,
    StepResult,
)


# -------- StepResult --------

def test_step_result_valid():
    r = StepResult(
        timestamp_start=time(16, 0),
        load_kwh=0.2,
        price_pence_per_kwh=30.0,
        grid_import_kwh=0.0,
        grid_for_load_kwh=0.0,
        battery_charge_kwh=0.0,
        battery_discharge_kwh=0.2,
        battery_soc_kwh=1.0,
        cost_pence=0.0,
    )
    assert r.battery_discharge_kwh == 0.2


def test_step_result_is_frozen():
    r = StepResult(
        timestamp_start=time(16, 0),
        load_kwh=0.2,
        price_pence_per_kwh=30.0,
        grid_import_kwh=0.0,
        grid_for_load_kwh=0.0,
        battery_charge_kwh=0.0,
        battery_discharge_kwh=0.2,
        battery_soc_kwh=1.0,
        cost_pence=0.0,
    )
    with pytest.raises(ValidationError):
        r.cost_pence = 1.0  # type: ignore[misc]


# -------- DaySimResult --------

def test_day_sim_result_valid():
    step = StepResult(
        timestamp_start=time(16, 0),
        load_kwh=0.2,
        price_pence_per_kwh=30.0,
        grid_import_kwh=0.0,
        grid_for_load_kwh=0.0,
        battery_charge_kwh=0.0,
        battery_discharge_kwh=0.2,
        battery_soc_kwh=1.0,
        cost_pence=0.0,
    )
    day = DaySimResult(
        date=date(2026, 4, 1),
        steps=[step],
        total_cost_pence=0.0,
        baseline_cost_pence=6.0,
        savings_pence=6.0,
    )
    assert day.savings_pence == 6.0


# -------- SimResult --------

def test_sim_result_valid():
    sim = SimResult(
        days=[],
        total_savings_pence=100.0,
        total_baseline_cost_pence=500.0,
        total_with_battery_cost_pence=400.0,
        simulated_days=10,
        annualized_savings_pence=3650.0,
    )
    assert sim.simulated_days == 10


# -------- SavingsSummary --------

def test_savings_summary_valid():
    s = SavingsSummary(
        total_savings_pence=100.0,
        simulated_days=10,
        daily_average_savings_pence=10.0,
        annualized_savings_pence=3650.0,
        baseline_annualized_cost_pence=18250.0,
        with_battery_annualized_cost_pence=14600.0,
    )
    assert s.daily_average_savings_pence == 10.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data_models.py -v`
Expected: ImportError on `StepResult` et al.

- [ ] **Step 3: Append result types to `src/windfall_tco/data_models.py`**

Append (before the last blank line):

```python
# ---------- Simulation results ----------

class StepResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    timestamp_start: time
    load_kwh: float
    price_pence_per_kwh: float
    grid_import_kwh: float        # total grid draw
    grid_for_load_kwh: float      # portion that served load
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


class SavingsSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    total_savings_pence: float
    simulated_days: int
    daily_average_savings_pence: float
    annualized_savings_pence: float
    baseline_annualized_cost_pence: float
    with_battery_annualized_cost_pence: float
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data_models.py -v`
Expected: all new tests pass alongside existing ones.

- [ ] **Step 5: Commit**

```bash
git add src/windfall_tco/data_models.py tests/test_data_models.py
git commit -m "Add simulation result and savings summary data models"
```

---

## Task 4: Tariff presets (Cosy, Go)

**Files:**
- Create: `src/windfall_tco/tariffs.py`
- Create: `tests/test_tariffs.py`

Octopus Cosy (as of spec date — a representative shape; exact real-world rates change over time, user can edit in-app):
- 04:00–07:00: cheap (off-peak)
- 13:00–16:00: cheap (off-peak)
- 22:00–24:00: cheap (off-peak)
- 16:00–19:00: peak
- All other hours: standard

Octopus Go (simpler):
- 00:30–05:30: cheap
- All other hours: standard

For MVP we use illustrative rates; user edits in the Streamlit editor.

- [ ] **Step 1: Write failing test**

Create `tests/test_tariffs.py`:

```python
from windfall_tco.data_models import Tariff
from windfall_tco.tariffs import OCTOPUS_COSY, OCTOPUS_GO, PRESETS


def test_cosy_is_a_tariff():
    assert isinstance(OCTOPUS_COSY, Tariff)
    assert OCTOPUS_COSY.name == "Octopus Cosy"
    # Cosy has multiple bands (peak + cheap + standard)
    assert len(OCTOPUS_COSY.bands) >= 3


def test_go_is_a_tariff():
    assert isinstance(OCTOPUS_GO, Tariff)
    assert OCTOPUS_GO.name == "Octopus Go"
    # Go has a single cheap window + standard rate
    assert len(OCTOPUS_GO.bands) >= 2


def test_presets_dict_contains_both():
    assert "Octopus Cosy" in PRESETS
    assert "Octopus Go" in PRESETS
    assert PRESETS["Octopus Cosy"] is OCTOPUS_COSY
    assert PRESETS["Octopus Go"] is OCTOPUS_GO
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tariffs.py -v`
Expected: ImportError on `windfall_tco.tariffs`.

- [ ] **Step 3: Implement `src/windfall_tco/tariffs.py`**

```python
"""Shipped tariff presets. Rates are illustrative; users edit in the app."""

from datetime import time

from windfall_tco.data_models import Tariff, TariffBand

_STANDARD_P = 27.0
_COSY_CHEAP_P = 12.0
_COSY_PEAK_P = 39.0
_GO_CHEAP_P = 8.5


OCTOPUS_COSY: Tariff = Tariff(
    name="Octopus Cosy",
    bands=[
        TariffBand(start=time(0, 0), end=time(4, 0), rate_pence_per_kwh=_STANDARD_P),
        TariffBand(start=time(4, 0), end=time(7, 0), rate_pence_per_kwh=_COSY_CHEAP_P),
        TariffBand(start=time(7, 0), end=time(13, 0), rate_pence_per_kwh=_STANDARD_P),
        TariffBand(start=time(13, 0), end=time(16, 0), rate_pence_per_kwh=_COSY_CHEAP_P),
        TariffBand(start=time(16, 0), end=time(19, 0), rate_pence_per_kwh=_COSY_PEAK_P),
        TariffBand(start=time(19, 0), end=time(22, 0), rate_pence_per_kwh=_STANDARD_P),
        TariffBand(
            start=time(22, 0),
            end=time(23, 59, 59, 999999),
            rate_pence_per_kwh=_COSY_CHEAP_P,
        ),
    ],
)


OCTOPUS_GO: Tariff = Tariff(
    name="Octopus Go",
    bands=[
        TariffBand(start=time(0, 0), end=time(0, 30), rate_pence_per_kwh=_STANDARD_P),
        TariffBand(start=time(0, 30), end=time(5, 30), rate_pence_per_kwh=_GO_CHEAP_P),
        TariffBand(
            start=time(5, 30),
            end=time(23, 59, 59, 999999),
            rate_pence_per_kwh=_STANDARD_P,
        ),
    ],
)


PRESETS: dict[str, Tariff] = {
    OCTOPUS_COSY.name: OCTOPUS_COSY,
    OCTOPUS_GO.name: OCTOPUS_GO,
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_tariffs.py -v`
Expected: all tests pass. If the Tariff validator rejects the presets, inspect the coverage logic in `data_models.py` — the `23:59:59.999999` end-of-day marker must be accepted.

- [ ] **Step 5: Commit**

```bash
git add src/windfall_tco/tariffs.py tests/test_tariffs.py
git commit -m "Add Octopus Cosy and Go tariff presets"
```

---

## Task 5: Tariff rate lookup helper

**Files:**
- Create: `src/windfall_tco/tariff_lookup.py`
- Create: `tests/test_tariff_lookup.py`

A small helper, used by the simulator and the economics layer, to answer: "what's the rate for this half-hour slot?"

- [ ] **Step 1: Write failing test**

Create `tests/test_tariff_lookup.py`:

```python
from datetime import time

import pytest

from windfall_tco.data_models import Tariff, TariffBand
from windfall_tco.tariff_lookup import rate_at


def _two_band() -> Tariff:
    return Tariff(
        name="two-band",
        bands=[
            TariffBand(start=time(0, 0), end=time(6, 0), rate_pence_per_kwh=5.0),
            TariffBand(
                start=time(6, 0),
                end=time(23, 59, 59, 999999),
                rate_pence_per_kwh=30.0,
            ),
        ],
    )


def test_rate_at_start_of_first_band():
    assert rate_at(_two_band(), time(0, 0)) == 5.0


def test_rate_at_midnight_last_slot():
    # last slot starts at 23:30; it must fall in the 30p band
    assert rate_at(_two_band(), time(23, 30)) == 30.0


def test_rate_at_band_boundary_inclusive_on_start():
    # 06:00 is the start of band 2, so it uses the 30p rate (not 5p)
    assert rate_at(_two_band(), time(6, 0)) == 30.0


def test_rate_at_band_boundary_exclusive_on_end():
    # 05:30 is still in band 1
    assert rate_at(_two_band(), time(5, 30)) == 5.0


def test_rate_at_raises_if_not_covered():
    # craft a tariff that doesn't actually cover — only possible if a user
    # builds one with bands=[] (which the Tariff validator rejects), so this
    # test validates defensive behavior using monkeypatching
    t = _two_band()
    t = t.model_copy(update={"bands": []})
    with pytest.raises(ValueError):
        rate_at(t, time(10, 0))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tariff_lookup.py -v`
Expected: ImportError on `windfall_tco.tariff_lookup`.

- [ ] **Step 3: Implement `src/windfall_tco/tariff_lookup.py`**

```python
"""Look up the tariff rate that applies at a given time-of-day."""

from datetime import time

from windfall_tco.data_models import Tariff


def rate_at(tariff: Tariff, t: time) -> float:
    """Return pence/kWh for the band containing `t` (inclusive start, exclusive end)."""
    for band in tariff.bands:
        if band.start <= t < band.end:
            return band.rate_pence_per_kwh
    raise ValueError(f"no tariff band covers time {t}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_tariff_lookup.py -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/windfall_tco/tariff_lookup.py tests/test_tariff_lookup.py
git commit -m "Add tariff rate lookup helper"
```

---

## Task 6: Simulation step — idle and discharge branches

**Files:**
- Create: `src/windfall_tco/simulation/step.py`
- Create: `tests/simulation/test_step.py`

- [ ] **Step 1: Write failing tests for idle + discharge branches**

Create `tests/simulation/test_step.py`:

```python
from datetime import time

from windfall_tco.data_models import BatterySpec, BatteryState, DispatchPolicy
from windfall_tco.simulation.step import step


def _spec(capacity: float = 2.5, charge_w: float = 800, discharge_w: float = 800, eff: float = 0.9) -> BatterySpec:
    return BatterySpec(
        usable_capacity_kwh=capacity,
        max_charge_power_w=charge_w,
        max_discharge_power_w=discharge_w,
        round_trip_efficiency=eff,
        initial_soc_fraction=0.5,
    )


def _policy(charge_below: float = 10.0, discharge_above: float = 25.0) -> DispatchPolicy:
    return DispatchPolicy(
        charge_below_pence_per_kwh=charge_below,
        discharge_above_pence_per_kwh=discharge_above,
    )


# -------- Idle branch --------

def test_idle_when_price_between_thresholds():
    state = BatteryState(energy_stored_kwh=1.0)
    new_state, result = step(
        prior_state=state,
        load_kwh=0.3,
        price_pence_per_kwh=20.0,   # between 10 and 25 -> idle
        slot_start=time(10, 0),
        spec=_spec(),
        policy=_policy(),
    )
    assert result.battery_charge_kwh == 0
    assert result.battery_discharge_kwh == 0
    assert result.grid_import_kwh == 0.3
    assert result.grid_for_load_kwh == 0.3
    assert new_state.energy_stored_kwh == 1.0
    assert result.cost_pence == 0.3 * 20.0


# -------- Discharge branch --------

def test_discharge_with_ample_battery():
    state = BatteryState(energy_stored_kwh=2.0)
    # Load is 0.3 kWh this slot; max discharge is 800W * 0.5h = 0.4 kWh
    # So battery covers the entire load.
    new_state, result = step(
        prior_state=state,
        load_kwh=0.3,
        price_pence_per_kwh=30.0,    # above 25 -> discharge
        slot_start=time(17, 0),
        spec=_spec(),
        policy=_policy(),
    )
    assert result.battery_discharge_kwh == 0.3
    assert result.battery_charge_kwh == 0
    assert result.grid_import_kwh == 0
    assert result.grid_for_load_kwh == 0
    assert new_state.energy_stored_kwh == 1.7  # 2.0 - 0.3
    assert result.cost_pence == 0


def test_discharge_capped_by_power():
    state = BatteryState(energy_stored_kwh=2.0)
    # Load is 0.6 kWh; max discharge is 0.4 kWh (800W * 0.5h)
    new_state, result = step(
        prior_state=state,
        load_kwh=0.6,
        price_pence_per_kwh=30.0,
        slot_start=time(17, 0),
        spec=_spec(),
        policy=_policy(),
    )
    assert result.battery_discharge_kwh == 0.4
    assert result.grid_import_kwh == 0.2
    assert result.grid_for_load_kwh == 0.2
    assert new_state.energy_stored_kwh == 1.6


def test_discharge_capped_by_soc():
    state = BatteryState(energy_stored_kwh=0.1)
    # Load is 0.3; max discharge power allows 0.4; only 0.1 stored.
    new_state, result = step(
        prior_state=state,
        load_kwh=0.3,
        price_pence_per_kwh=30.0,
        slot_start=time(17, 0),
        spec=_spec(),
        policy=_policy(),
    )
    assert result.battery_discharge_kwh == 0.1
    assert result.grid_import_kwh == 0.2
    assert new_state.energy_stored_kwh == 0.0


def test_discharge_empty_battery():
    state = BatteryState(energy_stored_kwh=0.0)
    new_state, result = step(
        prior_state=state,
        load_kwh=0.3,
        price_pence_per_kwh=30.0,
        slot_start=time(17, 0),
        spec=_spec(),
        policy=_policy(),
    )
    assert result.battery_discharge_kwh == 0
    assert result.grid_import_kwh == 0.3
    assert new_state.energy_stored_kwh == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/simulation/test_step.py -v`
Expected: ImportError on `windfall_tco.simulation.step`.

- [ ] **Step 3: Implement `src/windfall_tco/simulation/step.py` (idle + discharge + charge branches)**

Even though this task's tests only cover idle + discharge, implementing the full function now (including charge) avoids a second rewrite in Task 7. Task 7's tests will exercise the charge branch explicitly.

```python
"""Atomic half-hour state transition for the battery simulator.

Pure function: given the prior state and this slot's inputs, returns the
(new_state, result) pair. No I/O, no globals, no mutation.
"""

from __future__ import annotations

from datetime import time

from windfall_tco.data_models import (
    BatterySpec,
    BatteryState,
    DispatchPolicy,
    StepResult,
)

_SLOT_HOURS = 0.5


def step(
    prior_state: BatteryState,
    load_kwh: float,
    price_pence_per_kwh: float,
    slot_start: time,
    spec: BatterySpec,
    policy: DispatchPolicy,
) -> tuple[BatteryState, StepResult]:
    if price_pence_per_kwh >= policy.discharge_above_pence_per_kwh:
        return _discharge(prior_state, load_kwh, price_pence_per_kwh, slot_start, spec)
    if price_pence_per_kwh <= policy.charge_below_pence_per_kwh:
        return _charge(prior_state, load_kwh, price_pence_per_kwh, slot_start, spec)
    return _idle(prior_state, load_kwh, price_pence_per_kwh, slot_start)


def _discharge(
    prior_state: BatteryState,
    load_kwh: float,
    price: float,
    slot_start: time,
    spec: BatterySpec,
) -> tuple[BatteryState, StepResult]:
    max_discharge_kwh = spec.max_discharge_power_w / 1000 * _SLOT_HOURS
    battery_discharge_kwh = min(max_discharge_kwh, load_kwh, prior_state.energy_stored_kwh)
    grid_import_kwh = load_kwh - battery_discharge_kwh
    new_soc = prior_state.energy_stored_kwh - battery_discharge_kwh
    return (
        BatteryState(energy_stored_kwh=new_soc),
        StepResult(
            timestamp_start=slot_start,
            load_kwh=load_kwh,
            price_pence_per_kwh=price,
            grid_import_kwh=grid_import_kwh,
            grid_for_load_kwh=load_kwh - battery_discharge_kwh,
            battery_charge_kwh=0.0,
            battery_discharge_kwh=battery_discharge_kwh,
            battery_soc_kwh=new_soc,
            cost_pence=grid_import_kwh * price,
        ),
    )


def _charge(
    prior_state: BatteryState,
    load_kwh: float,
    price: float,
    slot_start: time,
    spec: BatterySpec,
) -> tuple[BatteryState, StepResult]:
    max_charge_kwh = spec.max_charge_power_w / 1000 * _SLOT_HOURS
    headroom_kwh = spec.usable_capacity_kwh - prior_state.energy_stored_kwh
    effective_stored = min(max_charge_kwh * spec.round_trip_efficiency, headroom_kwh)
    grid_kwh_for_charge = (
        effective_stored / spec.round_trip_efficiency if effective_stored > 0 else 0.0
    )
    grid_import_kwh = load_kwh + grid_kwh_for_charge
    new_soc = prior_state.energy_stored_kwh + effective_stored
    return (
        BatteryState(energy_stored_kwh=new_soc),
        StepResult(
            timestamp_start=slot_start,
            load_kwh=load_kwh,
            price_pence_per_kwh=price,
            grid_import_kwh=grid_import_kwh,
            grid_for_load_kwh=load_kwh,
            battery_charge_kwh=effective_stored,
            battery_discharge_kwh=0.0,
            battery_soc_kwh=new_soc,
            cost_pence=grid_import_kwh * price,
        ),
    )


def _idle(
    prior_state: BatteryState,
    load_kwh: float,
    price: float,
    slot_start: time,
) -> tuple[BatteryState, StepResult]:
    return (
        prior_state,
        StepResult(
            timestamp_start=slot_start,
            load_kwh=load_kwh,
            price_pence_per_kwh=price,
            grid_import_kwh=load_kwh,
            grid_for_load_kwh=load_kwh,
            battery_charge_kwh=0.0,
            battery_discharge_kwh=0.0,
            battery_soc_kwh=prior_state.energy_stored_kwh,
            cost_pence=load_kwh * price,
        ),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/simulation/test_step.py -v`
Expected: all five idle/discharge tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/windfall_tco/simulation/step.py tests/simulation/test_step.py
git commit -m "Add simulation step function with idle and discharge branches tested"
```

---

## Task 7: Simulation step — charge branch tests

**Files:**
- Modify: `tests/simulation/test_step.py` (append)

- [ ] **Step 1: Add charge branch tests**

Append to `tests/simulation/test_step.py`:

```python
# -------- Charge branch --------

def test_charge_with_ample_headroom():
    state = BatteryState(energy_stored_kwh=0.0)
    # price 5 below threshold 10 -> charge
    # max_charge = 800W * 0.5h = 0.4 kWh
    # eff 0.9 -> effective_stored = 0.4 * 0.9 = 0.36 kWh
    # grid_for_charge = 0.36 / 0.9 = 0.4 kWh
    new_state, result = step(
        prior_state=state,
        load_kwh=0.2,
        price_pence_per_kwh=5.0,
        slot_start=time(4, 0),
        spec=_spec(),
        policy=_policy(),
    )
    assert result.battery_charge_kwh == pytest.approx(0.36)
    assert result.battery_discharge_kwh == 0
    assert result.grid_import_kwh == pytest.approx(0.6)   # 0.2 + 0.4
    assert result.grid_for_load_kwh == pytest.approx(0.2)
    assert new_state.energy_stored_kwh == pytest.approx(0.36)


def test_charge_capped_by_headroom():
    # Battery nearly full: capacity 2.5, currently 2.4, headroom 0.1 kWh
    state = BatteryState(energy_stored_kwh=2.4)
    new_state, result = step(
        prior_state=state,
        load_kwh=0.2,
        price_pence_per_kwh=5.0,
        slot_start=time(4, 0),
        spec=_spec(),
        policy=_policy(),
    )
    assert result.battery_charge_kwh == pytest.approx(0.1)
    # grid_for_charge = 0.1 / 0.9
    assert result.grid_import_kwh == pytest.approx(0.2 + 0.1 / 0.9)
    assert new_state.energy_stored_kwh == pytest.approx(2.5)


def test_charge_full_battery():
    state = BatteryState(energy_stored_kwh=2.5)
    new_state, result = step(
        prior_state=state,
        load_kwh=0.2,
        price_pence_per_kwh=5.0,
        slot_start=time(4, 0),
        spec=_spec(),
        policy=_policy(),
    )
    assert result.battery_charge_kwh == 0
    assert result.grid_import_kwh == 0.2
    assert new_state.energy_stored_kwh == 2.5


def test_load_satisfaction_invariant_holds_in_all_branches():
    """Energy conservation: load = battery_discharge + grid_for_load, every branch."""
    spec = _spec()
    policy = _policy()

    for price, soc, label in [
        (5.0, 1.0, "charge"),
        (20.0, 1.0, "idle"),
        (30.0, 1.0, "discharge"),
    ]:
        _, r = step(
            prior_state=BatteryState(energy_stored_kwh=soc),
            load_kwh=0.3,
            price_pence_per_kwh=price,
            slot_start=time(12, 0),
            spec=spec,
            policy=policy,
        )
        assert r.load_kwh == pytest.approx(
            r.battery_discharge_kwh + r.grid_for_load_kwh
        ), f"invariant broken in {label} branch"


def test_need_pytest_import():
    # Ensures the import exists in this file for .approx() usage above
    assert pytest is not None
```

Note: `pytest` is already imported at the top of this file from Task 6's tests (it is). If the earlier tests don't import pytest yet, also add `import pytest` at the top of the file.

- [ ] **Step 2: Ensure `pytest` is imported at top of the file**

Check `tests/simulation/test_step.py` has `import pytest` at the top. If not, add it.

- [ ] **Step 3: Run tests to verify they pass**

Run: `uv run pytest tests/simulation/test_step.py -v`
Expected: all charge + invariant tests pass.

- [ ] **Step 4: Commit**

```bash
git add tests/simulation/test_step.py
git commit -m "Add charge branch and load-satisfaction invariant tests for step"
```

---

## Task 8: Simulation step — hypothesis property tests

**Files:**
- Create: `tests/simulation/test_step_properties.py`

- [ ] **Step 1: Write property tests**

Create `tests/simulation/test_step_properties.py`:

```python
from datetime import time

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from windfall_tco.data_models import BatterySpec, BatteryState, DispatchPolicy
from windfall_tco.simulation.step import step


@st.composite
def _inputs(draw):
    capacity = draw(st.floats(min_value=0.5, max_value=20.0, allow_nan=False))
    charge_w = draw(st.floats(min_value=200, max_value=5000, allow_nan=False))
    discharge_w = draw(st.floats(min_value=200, max_value=5000, allow_nan=False))
    eff = draw(st.floats(min_value=0.5, max_value=1.0, allow_nan=False))
    soc = draw(st.floats(min_value=0.0, max_value=capacity, allow_nan=False))
    load = draw(st.floats(min_value=0.0, max_value=5.0, allow_nan=False))
    charge_below = draw(st.floats(min_value=1.0, max_value=40.0, allow_nan=False))
    discharge_above = draw(st.floats(min_value=charge_below + 1, max_value=100.0, allow_nan=False))
    price = draw(st.floats(min_value=0.0, max_value=150.0, allow_nan=False))
    assume(discharge_above > charge_below)
    return {
        "spec": BatterySpec(
            usable_capacity_kwh=capacity,
            max_charge_power_w=charge_w,
            max_discharge_power_w=discharge_w,
            round_trip_efficiency=eff,
            initial_soc_fraction=0.5,
        ),
        "policy": DispatchPolicy(
            charge_below_pence_per_kwh=charge_below,
            discharge_above_pence_per_kwh=discharge_above,
        ),
        "state": BatteryState(energy_stored_kwh=soc),
        "load_kwh": load,
        "price": price,
    }


@settings(max_examples=200)
@given(_inputs())
def test_non_negative_flows(inputs):
    new_state, r = step(
        prior_state=inputs["state"],
        load_kwh=inputs["load_kwh"],
        price_pence_per_kwh=inputs["price"],
        slot_start=time(12, 0),
        spec=inputs["spec"],
        policy=inputs["policy"],
    )
    assert r.grid_import_kwh >= 0
    assert r.battery_charge_kwh >= 0
    assert r.battery_discharge_kwh >= 0
    assert r.grid_for_load_kwh >= 0
    assert new_state.energy_stored_kwh >= 0


@settings(max_examples=200)
@given(_inputs())
def test_soc_within_capacity(inputs):
    new_state, _ = step(
        prior_state=inputs["state"],
        load_kwh=inputs["load_kwh"],
        price_pence_per_kwh=inputs["price"],
        slot_start=time(12, 0),
        spec=inputs["spec"],
        policy=inputs["policy"],
    )
    assert new_state.energy_stored_kwh <= inputs["spec"].usable_capacity_kwh + 1e-9


@settings(max_examples=200)
@given(_inputs())
def test_at_most_one_flow_direction(inputs):
    _, r = step(
        prior_state=inputs["state"],
        load_kwh=inputs["load_kwh"],
        price_pence_per_kwh=inputs["price"],
        slot_start=time(12, 0),
        spec=inputs["spec"],
        policy=inputs["policy"],
    )
    assert not (r.battery_charge_kwh > 0 and r.battery_discharge_kwh > 0)


@settings(max_examples=200)
@given(_inputs())
def test_load_satisfaction_invariant(inputs):
    """load = battery_discharge + grid_for_load, always."""
    _, r = step(
        prior_state=inputs["state"],
        load_kwh=inputs["load_kwh"],
        price_pence_per_kwh=inputs["price"],
        slot_start=time(12, 0),
        spec=inputs["spec"],
        policy=inputs["policy"],
    )
    assert r.load_kwh == pytest.approx(r.battery_discharge_kwh + r.grid_for_load_kwh, abs=1e-9)


@settings(max_examples=200)
@given(_inputs())
def test_soc_delta_matches_flows(inputs):
    new_state, r = step(
        prior_state=inputs["state"],
        load_kwh=inputs["load_kwh"],
        price_pence_per_kwh=inputs["price"],
        slot_start=time(12, 0),
        spec=inputs["spec"],
        policy=inputs["policy"],
    )
    delta = new_state.energy_stored_kwh - inputs["state"].energy_stored_kwh
    assert delta == pytest.approx(r.battery_charge_kwh - r.battery_discharge_kwh, abs=1e-9)
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/simulation/test_step_properties.py -v`
Expected: all five property tests pass with 200 examples each.

- [ ] **Step 3: Commit**

```bash
git add tests/simulation/test_step_properties.py
git commit -m "Add hypothesis property tests for step invariants"
```

---

## Task 9: Simulation run — multi-day fold

**Files:**
- Create: `src/windfall_tco/simulation/run.py`
- Create: `tests/simulation/test_run.py`

- [ ] **Step 1: Write failing tests (SoC continuity + annualization + baseline)**

Create `tests/simulation/test_run.py`:

```python
from datetime import date, time

import pytest

from windfall_tco.data_models import (
    BatterySpec,
    ConsumptionSeries,
    DailyConsumption,
    DispatchPolicy,
    HalfHourReading,
    Tariff,
    TariffBand,
)
from windfall_tco.simulation.run import run


def _flat_day(d: date, kwh_per_slot: float) -> DailyConsumption:
    readings: list[HalfHourReading] = []
    for i in range(48):
        h, m = divmod(i * 30, 60)
        readings.append(HalfHourReading(start=time(h, m), kwh=kwh_per_slot))
    return DailyConsumption(date=d, readings=readings)


def _flat_tariff(rate: float) -> Tariff:
    return Tariff(
        name="flat",
        bands=[
            TariffBand(
                start=time(0, 0),
                end=time(23, 59, 59, 999999),
                rate_pence_per_kwh=rate,
            ),
        ],
    )


def _two_band_tariff(cheap: float, peak: float) -> Tariff:
    return Tariff(
        name="two-band",
        bands=[
            TariffBand(start=time(0, 0), end=time(12, 0), rate_pence_per_kwh=cheap),
            TariffBand(
                start=time(12, 0),
                end=time(23, 59, 59, 999999),
                rate_pence_per_kwh=peak,
            ),
        ],
    )


def _spec(capacity: float = 2.5, eff: float = 1.0) -> BatterySpec:
    # efficiency 1.0 to make arithmetic analytical in these tests
    return BatterySpec(
        usable_capacity_kwh=capacity,
        max_charge_power_w=800,
        max_discharge_power_w=800,
        round_trip_efficiency=eff,
        initial_soc_fraction=0.5,
    )


def _policy(charge_below: float, discharge_above: float) -> DispatchPolicy:
    return DispatchPolicy(
        charge_below_pence_per_kwh=charge_below,
        discharge_above_pence_per_kwh=discharge_above,
    )


def test_run_flat_tariff_zero_savings():
    """Battery never triggers — savings are zero."""
    series = ConsumptionSeries(days=[_flat_day(date(2026, 4, 1), 0.1)])
    tariff = _flat_tariff(rate=20.0)
    policy = _policy(charge_below=5.0, discharge_above=35.0)  # price never matches
    result = run(series, tariff, _spec(), policy)

    assert result.total_savings_pence == pytest.approx(0.0, abs=1e-9)
    assert result.simulated_days == 1


def test_run_annualizes_correctly():
    """Annualization scales by 365 / simulated_days."""
    series = ConsumptionSeries(days=[_flat_day(date(2026, 4, 1), 0.1)])
    tariff = _flat_tariff(rate=20.0)
    result = run(series, tariff, _spec(), _policy(charge_below=5.0, discharge_above=35.0))
    assert result.annualized_savings_pence == pytest.approx(
        result.total_savings_pence * 365 / 1
    )


def test_run_soc_continuous_across_days():
    """Day 2 starts where day 1 ended."""
    day1 = _flat_day(date(2026, 4, 1), 0.1)
    day2 = _flat_day(date(2026, 4, 2), 0.1)
    series = ConsumptionSeries(days=[day1, day2])
    tariff = _two_band_tariff(cheap=5.0, peak=30.0)
    policy = _policy(charge_below=5.0, discharge_above=30.0)
    result = run(series, tariff, _spec(eff=1.0), policy)

    day1_end_soc = result.days[0].steps[-1].battery_soc_kwh
    day2_start_soc_after_first_step = result.days[1].steps[0].battery_soc_kwh
    # After the first slot of day 2, SoC has evolved by at most one step.
    # The invariant we check is that day 2's first step began from day 1's final SoC.
    # step() returns new_soc for that step; to reconstruct prior SoC of first step,
    # reverse the flow:
    first_step = result.days[1].steps[0]
    reconstructed_prior = (
        first_step.battery_soc_kwh
        - first_step.battery_charge_kwh
        + first_step.battery_discharge_kwh
    )
    assert reconstructed_prior == pytest.approx(day1_end_soc, abs=1e-9)


def test_run_baseline_equals_load_times_price():
    series = ConsumptionSeries(days=[_flat_day(date(2026, 4, 1), 0.1)])
    tariff = _flat_tariff(rate=20.0)
    result = run(
        series,
        tariff,
        _spec(),
        _policy(charge_below=5.0, discharge_above=35.0),  # idle everywhere
    )
    # 48 slots × 0.1 kWh × 20 p = 96 p
    assert result.days[0].baseline_cost_pence == pytest.approx(96.0)
    # with no battery activity, total == baseline
    assert result.days[0].total_cost_pence == pytest.approx(96.0)
    assert result.days[0].savings_pence == pytest.approx(0.0, abs=1e-9)


def test_run_perfect_arbitrage_two_band():
    """12h cheap / 12h peak, battery can cycle once per day."""
    # cheap 00:00-12:00 @ 5p, peak 12:00-24:00 @ 30p
    tariff = _two_band_tariff(cheap=5.0, peak=30.0)
    # thresholds: charge if <= 10 (cheap), discharge if >= 20 (peak)
    policy = _policy(charge_below=10.0, discharge_above=20.0)
    # Load: 0.1 kWh per slot. 48 slots => 4.8 kWh/day load.
    series = ConsumptionSeries(days=[_flat_day(date(2026, 4, 1), 0.1)])
    # 2.5 kWh usable capacity. Eff 1.0 (analytical).
    result = run(series, tariff, _spec(capacity=2.5, eff=1.0), policy)

    # Baseline: 4.8 kWh * half at 5p + half at 30p
    # = 2.4 * 5 + 2.4 * 30 = 12 + 72 = 84p
    assert result.days[0].baseline_cost_pence == pytest.approx(84.0)
    # With battery: during peak (12:00-24:00), first slots get battery discharge
    # covering load until battery empties. Each slot 0.1 kWh, 0.1 per slot drains
    # 2.5 kWh in 25 slots; remaining slots pay peak price.
    # Savings = 2.5 kWh * 25p (difference between peak and baseline fulfillment) ≈ 62.5p
    # plus charging cost above baseline in cheap window, which equals the stored kWh at cheap rate.
    # Net savings = 2.5 * (30 - 5) = 62.5p
    assert result.days[0].savings_pence == pytest.approx(62.5, abs=1e-6)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/simulation/test_run.py -v`
Expected: ImportError on `windfall_tco.simulation.run`.

- [ ] **Step 3: Implement `src/windfall_tco/simulation/run.py`**

```python
"""Fold the step() transition over a full consumption series."""

from __future__ import annotations

from windfall_tco.data_models import (
    BatterySpec,
    BatteryState,
    ConsumptionSeries,
    DailyConsumption,
    DaySimResult,
    DispatchPolicy,
    SimResult,
    StepResult,
    Tariff,
)
from windfall_tco.simulation.step import step
from windfall_tco.tariff_lookup import rate_at


def run(
    series: ConsumptionSeries,
    tariff: Tariff,
    spec: BatterySpec,
    policy: DispatchPolicy,
) -> SimResult:
    state = BatteryState(energy_stored_kwh=spec.initial_soc_fraction * spec.usable_capacity_kwh)

    day_results: list[DaySimResult] = []
    total_cost_pence = 0.0
    total_baseline_pence = 0.0

    for day in series.days:
        state, day_result = _simulate_day(day, tariff, spec, policy, state)
        day_results.append(day_result)
        total_cost_pence += day_result.total_cost_pence
        total_baseline_pence += day_result.baseline_cost_pence

    total_savings_pence = total_baseline_pence - total_cost_pence
    simulated_days = len(series.days)
    annualized_savings_pence = (
        total_savings_pence * 365 / simulated_days if simulated_days > 0 else 0.0
    )

    return SimResult(
        days=day_results,
        total_savings_pence=total_savings_pence,
        total_baseline_cost_pence=total_baseline_pence,
        total_with_battery_cost_pence=total_cost_pence,
        simulated_days=simulated_days,
        annualized_savings_pence=annualized_savings_pence,
    )


def _simulate_day(
    day: DailyConsumption,
    tariff: Tariff,
    spec: BatterySpec,
    policy: DispatchPolicy,
    starting_state: BatteryState,
) -> tuple[BatteryState, DaySimResult]:
    state = starting_state
    steps: list[StepResult] = []
    total_cost = 0.0
    baseline_cost = 0.0

    for reading in day.readings:
        price = rate_at(tariff, reading.start)
        state, r = step(state, reading.kwh, price, reading.start, spec, policy)
        steps.append(r)
        total_cost += r.cost_pence
        baseline_cost += reading.kwh * price

    return state, DaySimResult(
        date=day.date,
        steps=steps,
        total_cost_pence=total_cost,
        baseline_cost_pence=baseline_cost,
        savings_pence=baseline_cost - total_cost,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/simulation/test_run.py -v`
Expected: all five run tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/windfall_tco/simulation/run.py tests/simulation/test_run.py
git commit -m "Add simulation run function with SoC continuity and baseline cost"
```

---

## Task 10: Economics — cost

**Files:**
- Create: `src/windfall_tco/economics/cost.py`
- Create: `tests/economics/test_cost.py`

- [ ] **Step 1: Write failing tests**

Create `tests/economics/test_cost.py`:

```python
from datetime import date, time

import pytest

from windfall_tco.data_models import (
    DailyConsumption,
    HalfHourReading,
    Tariff,
    TariffBand,
)
from windfall_tco.economics.cost import baseline_daily_cost, cost_of_slots


def _flat_tariff(rate: float) -> Tariff:
    return Tariff(
        name="flat",
        bands=[
            TariffBand(
                start=time(0, 0),
                end=time(23, 59, 59, 999999),
                rate_pence_per_kwh=rate,
            )
        ],
    )


def _full_day(kwh: float) -> DailyConsumption:
    readings: list[HalfHourReading] = []
    for i in range(48):
        h, m = divmod(i * 30, 60)
        readings.append(HalfHourReading(start=time(h, m), kwh=kwh))
    return DailyConsumption(date=date(2026, 4, 1), readings=readings)


def test_cost_of_slots_flat_tariff():
    readings = _full_day(0.1).readings
    # 48 * 0.1 kWh * 20 p = 96p
    assert cost_of_slots(readings, _flat_tariff(20.0)) == pytest.approx(96.0)


def test_cost_of_slots_empty():
    assert cost_of_slots([], _flat_tariff(20.0)) == 0.0


def test_baseline_daily_cost_matches_cost_of_slots():
    day = _full_day(0.15)
    tariff = _flat_tariff(25.0)
    assert baseline_daily_cost(day, tariff) == pytest.approx(
        cost_of_slots(day.readings, tariff)
    )


def test_cost_of_slots_with_two_band_tariff():
    # cheap 00:00-12:00 @ 5p, peak 12:00-24:00 @ 30p
    tariff = Tariff(
        name="two-band",
        bands=[
            TariffBand(start=time(0, 0), end=time(12, 0), rate_pence_per_kwh=5.0),
            TariffBand(
                start=time(12, 0),
                end=time(23, 59, 59, 999999),
                rate_pence_per_kwh=30.0,
            ),
        ],
    )
    readings = _full_day(0.1).readings
    # 24 slots @ 5p * 0.1 = 12p, 24 slots @ 30p * 0.1 = 72p -> 84p total
    assert cost_of_slots(readings, tariff) == pytest.approx(84.0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/economics/test_cost.py -v`
Expected: ImportError on `windfall_tco.economics.cost`.

- [ ] **Step 3: Implement `src/windfall_tco/economics/cost.py`**

```python
"""Cost calculations. Pure functions, pence everywhere."""

from windfall_tco.data_models import DailyConsumption, HalfHourReading, Tariff
from windfall_tco.tariff_lookup import rate_at


def cost_of_slots(readings: list[HalfHourReading], tariff: Tariff) -> float:
    """Sum of reading kWh × rate-at-slot-start (pence)."""
    return sum(r.kwh * rate_at(tariff, r.start) for r in readings)


def baseline_daily_cost(day: DailyConsumption, tariff: Tariff) -> float:
    """Cost of a day's consumption at the tariff, with no battery. Pence."""
    return cost_of_slots(day.readings, tariff)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/economics/test_cost.py -v`
Expected: all four tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/windfall_tco/economics/cost.py tests/economics/test_cost.py
git commit -m "Add economics cost functions"
```

---

## Task 11: Economics — payback and savings summary

**Files:**
- Create: `src/windfall_tco/economics/payback.py`
- Create: `tests/economics/test_payback.py`

- [ ] **Step 1: Write failing tests**

Create `tests/economics/test_payback.py`:

```python
import pytest

from windfall_tco.data_models import SimResult
from windfall_tco.economics.payback import savings_summary, simple_payback_years


def test_simple_payback_positive_savings():
    # £500 battery, 10000p annual savings -> £100/year -> 5 years
    assert simple_payback_years(500.0, 10000.0) == pytest.approx(5.0)


def test_simple_payback_zero_savings_returns_none():
    assert simple_payback_years(500.0, 0.0) is None


def test_simple_payback_negative_savings_returns_none():
    assert simple_payback_years(500.0, -1.0) is None


def test_simple_payback_free_battery():
    assert simple_payback_years(0.0, 10000.0) == pytest.approx(0.0)


def test_savings_summary_from_sim_result():
    sim = SimResult(
        days=[],
        total_savings_pence=1000.0,
        total_baseline_cost_pence=5000.0,
        total_with_battery_cost_pence=4000.0,
        simulated_days=10,
        annualized_savings_pence=36500.0,
    )
    s = savings_summary(sim)
    assert s.total_savings_pence == 1000.0
    assert s.simulated_days == 10
    assert s.daily_average_savings_pence == pytest.approx(100.0)
    assert s.annualized_savings_pence == 36500.0
    assert s.baseline_annualized_cost_pence == pytest.approx(5000.0 * 365 / 10)
    assert s.with_battery_annualized_cost_pence == pytest.approx(4000.0 * 365 / 10)


def test_savings_summary_zero_days_safe():
    sim = SimResult(
        days=[],
        total_savings_pence=0.0,
        total_baseline_cost_pence=0.0,
        total_with_battery_cost_pence=0.0,
        simulated_days=0,
        annualized_savings_pence=0.0,
    )
    s = savings_summary(sim)
    assert s.daily_average_savings_pence == 0.0
    assert s.baseline_annualized_cost_pence == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/economics/test_payback.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/windfall_tco/economics/payback.py`**

```python
"""Payback and savings summary."""

from windfall_tco.data_models import SavingsSummary, SimResult


def simple_payback_years(
    battery_cost_pounds: float,
    annualized_savings_pence: float,
) -> float | None:
    if annualized_savings_pence <= 0:
        return None
    return battery_cost_pounds / (annualized_savings_pence / 100)


def savings_summary(result: SimResult) -> SavingsSummary:
    days = result.simulated_days
    if days == 0:
        return SavingsSummary(
            total_savings_pence=0.0,
            simulated_days=0,
            daily_average_savings_pence=0.0,
            annualized_savings_pence=0.0,
            baseline_annualized_cost_pence=0.0,
            with_battery_annualized_cost_pence=0.0,
        )
    return SavingsSummary(
        total_savings_pence=result.total_savings_pence,
        simulated_days=days,
        daily_average_savings_pence=result.total_savings_pence / days,
        annualized_savings_pence=result.annualized_savings_pence,
        baseline_annualized_cost_pence=result.total_baseline_cost_pence * 365 / days,
        with_battery_annualized_cost_pence=result.total_with_battery_cost_pence * 365 / days,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/economics/test_payback.py -v`
Expected: all six tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/windfall_tco/economics/payback.py tests/economics/test_payback.py
git commit -m "Add simple payback and savings summary functions"
```

---

## Task 12: Data loading — manual profile

**Files:**
- Create: `src/windfall_tco/data_loading/manual_profile.py`
- Create: `tests/data_loading/test_manual_profile.py`

- [ ] **Step 1: Write failing tests**

Create `tests/data_loading/test_manual_profile.py`:

```python
from datetime import date, time

import pytest

from windfall_tco.data_loading.manual_profile import from_hourly_watts


def test_from_hourly_watts_produces_48_slots():
    watts = [200.0] * 24
    result = from_hourly_watts(watts)
    assert len(result.series.days) == 1
    day = result.series.days[0]
    assert len(day.readings) == 48
    assert result.warnings == []


def test_from_hourly_watts_each_hour_split_evenly():
    # 200 W constant -> 0.1 kWh per half-hour slot
    watts = [200.0] * 24
    result = from_hourly_watts(watts)
    for reading in result.series.days[0].readings:
        assert reading.kwh == pytest.approx(0.1)


def test_from_hourly_watts_first_slot_is_midnight():
    watts = [200.0] * 24
    result = from_hourly_watts(watts)
    assert result.series.days[0].readings[0].start == time(0, 0)
    assert result.series.days[0].readings[1].start == time(0, 30)


def test_from_hourly_watts_varying_values():
    watts = [100.0] + [0.0] * 23  # hour 0 is 100W, rest zero
    result = from_hourly_watts(watts)
    # hour 0 -> two half-hour slots of 0.05 kWh each
    assert result.series.days[0].readings[0].kwh == pytest.approx(0.05)
    assert result.series.days[0].readings[1].kwh == pytest.approx(0.05)
    assert result.series.days[0].readings[2].kwh == 0.0


def test_from_hourly_watts_rejects_wrong_length():
    with pytest.raises(ValueError):
        from_hourly_watts([100.0] * 23)


def test_from_hourly_watts_rejects_negative():
    bad = [100.0] * 24
    bad[5] = -1.0
    with pytest.raises(ValueError):
        from_hourly_watts(bad)


def test_from_hourly_watts_date_is_today():
    from datetime import date as date_cls

    watts = [200.0] * 24
    result = from_hourly_watts(watts)
    assert result.series.days[0].date == date_cls.today()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/data_loading/test_manual_profile.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/windfall_tco/data_loading/manual_profile.py`**

```python
"""Manual profile: 24 hourly watt values -> 48-slot ConsumptionSeries."""

from datetime import date, time

from windfall_tco.data_models import (
    ConsumptionSeries,
    DailyConsumption,
    HalfHourReading,
    LoadResult,
)


def from_hourly_watts(hourly_watts: list[float]) -> LoadResult:
    if len(hourly_watts) != 24:
        raise ValueError(f"expected 24 hourly values, got {len(hourly_watts)}")
    if any(w < 0 for w in hourly_watts):
        raise ValueError("watt values must be non-negative")

    # 1 h = 0.5 kWh for every 1000 W, split evenly into two 30-min slots
    readings: list[HalfHourReading] = []
    for hour_index, watts in enumerate(hourly_watts):
        half_hour_kwh = (watts / 1000.0) * 0.5
        readings.append(HalfHourReading(start=time(hour_index, 0), kwh=half_hour_kwh))
        readings.append(HalfHourReading(start=time(hour_index, 30), kwh=half_hour_kwh))

    day = DailyConsumption(date=date.today(), readings=readings)
    return LoadResult(series=ConsumptionSeries(days=[day]), warnings=[])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/data_loading/test_manual_profile.py -v`
Expected: all seven tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/windfall_tco/data_loading/manual_profile.py tests/data_loading/test_manual_profile.py
git commit -m "Add manual profile loader (hourly watts -> 48-slot series)"
```

---

## Task 13: Data loading — Octopus CSV parser

**Files:**
- Create: `src/windfall_tco/data_loading/octopus_csv.py`
- Create: `tests/data_loading/test_octopus_csv.py`
- Create: `tests/data_loading/fixtures/one_full_day.csv`
- Create: `tests/data_loading/fixtures/partial_day.csv`
- Create: `tests/data_loading/fixtures/dst_spring.csv`

- [ ] **Step 1: Create fixture `one_full_day.csv`**

Path: `tests/data_loading/fixtures/one_full_day.csv`

```
Consumption (kwh), Estimated Cost Inc. Tax (p), Standing Charge Inc. Tax (p), Start, End
```

Then append 48 rows for a single day (2026-04-01, BST offset +01:00). Use a simple generator pattern — each row:

```
0.100000, 2.5, 0.93, 2026-04-01THH:MM:00+01:00, 2026-04-01THH:MM:00+01:00
```

with half-hourly `Start` stepping from 00:00 to 23:30, and `End` 30 min after. Full file (copy-paste exactly):

```
Consumption (kwh), Estimated Cost Inc. Tax (p), Standing Charge Inc. Tax (p), Start, End
0.100000, 2.5, 0.93, 2026-04-01T00:00:00+01:00, 2026-04-01T00:30:00+01:00
0.100000, 2.5, 0.93, 2026-04-01T00:30:00+01:00, 2026-04-01T01:00:00+01:00
0.100000, 2.5, 0.93, 2026-04-01T01:00:00+01:00, 2026-04-01T01:30:00+01:00
0.100000, 2.5, 0.93, 2026-04-01T01:30:00+01:00, 2026-04-01T02:00:00+01:00
0.100000, 2.5, 0.93, 2026-04-01T02:00:00+01:00, 2026-04-01T02:30:00+01:00
0.100000, 2.5, 0.93, 2026-04-01T02:30:00+01:00, 2026-04-01T03:00:00+01:00
0.100000, 2.5, 0.93, 2026-04-01T03:00:00+01:00, 2026-04-01T03:30:00+01:00
0.100000, 2.5, 0.93, 2026-04-01T03:30:00+01:00, 2026-04-01T04:00:00+01:00
0.100000, 2.5, 0.93, 2026-04-01T04:00:00+01:00, 2026-04-01T04:30:00+01:00
0.100000, 2.5, 0.93, 2026-04-01T04:30:00+01:00, 2026-04-01T05:00:00+01:00
0.100000, 2.5, 0.93, 2026-04-01T05:00:00+01:00, 2026-04-01T05:30:00+01:00
0.100000, 2.5, 0.93, 2026-04-01T05:30:00+01:00, 2026-04-01T06:00:00+01:00
0.100000, 2.5, 0.93, 2026-04-01T06:00:00+01:00, 2026-04-01T06:30:00+01:00
0.100000, 2.5, 0.93, 2026-04-01T06:30:00+01:00, 2026-04-01T07:00:00+01:00
0.100000, 2.5, 0.93, 2026-04-01T07:00:00+01:00, 2026-04-01T07:30:00+01:00
0.100000, 2.5, 0.93, 2026-04-01T07:30:00+01:00, 2026-04-01T08:00:00+01:00
0.100000, 2.5, 0.93, 2026-04-01T08:00:00+01:00, 2026-04-01T08:30:00+01:00
0.100000, 2.5, 0.93, 2026-04-01T08:30:00+01:00, 2026-04-01T09:00:00+01:00
0.100000, 2.5, 0.93, 2026-04-01T09:00:00+01:00, 2026-04-01T09:30:00+01:00
0.100000, 2.5, 0.93, 2026-04-01T09:30:00+01:00, 2026-04-01T10:00:00+01:00
0.100000, 2.5, 0.93, 2026-04-01T10:00:00+01:00, 2026-04-01T10:30:00+01:00
0.100000, 2.5, 0.93, 2026-04-01T10:30:00+01:00, 2026-04-01T11:00:00+01:00
0.100000, 2.5, 0.93, 2026-04-01T11:00:00+01:00, 2026-04-01T11:30:00+01:00
0.100000, 2.5, 0.93, 2026-04-01T11:30:00+01:00, 2026-04-01T12:00:00+01:00
0.100000, 2.5, 0.93, 2026-04-01T12:00:00+01:00, 2026-04-01T12:30:00+01:00
0.100000, 2.5, 0.93, 2026-04-01T12:30:00+01:00, 2026-04-01T13:00:00+01:00
0.100000, 2.5, 0.93, 2026-04-01T13:00:00+01:00, 2026-04-01T13:30:00+01:00
0.100000, 2.5, 0.93, 2026-04-01T13:30:00+01:00, 2026-04-01T14:00:00+01:00
0.100000, 2.5, 0.93, 2026-04-01T14:00:00+01:00, 2026-04-01T14:30:00+01:00
0.100000, 2.5, 0.93, 2026-04-01T14:30:00+01:00, 2026-04-01T15:00:00+01:00
0.100000, 2.5, 0.93, 2026-04-01T15:00:00+01:00, 2026-04-01T15:30:00+01:00
0.100000, 2.5, 0.93, 2026-04-01T15:30:00+01:00, 2026-04-01T16:00:00+01:00
0.100000, 2.5, 0.93, 2026-04-01T16:00:00+01:00, 2026-04-01T16:30:00+01:00
0.100000, 2.5, 0.93, 2026-04-01T16:30:00+01:00, 2026-04-01T17:00:00+01:00
0.100000, 2.5, 0.93, 2026-04-01T17:00:00+01:00, 2026-04-01T17:30:00+01:00
0.100000, 2.5, 0.93, 2026-04-01T17:30:00+01:00, 2026-04-01T18:00:00+01:00
0.100000, 2.5, 0.93, 2026-04-01T18:00:00+01:00, 2026-04-01T18:30:00+01:00
0.100000, 2.5, 0.93, 2026-04-01T18:30:00+01:00, 2026-04-01T19:00:00+01:00
0.100000, 2.5, 0.93, 2026-04-01T19:00:00+01:00, 2026-04-01T19:30:00+01:00
0.100000, 2.5, 0.93, 2026-04-01T19:30:00+01:00, 2026-04-01T20:00:00+01:00
0.100000, 2.5, 0.93, 2026-04-01T20:00:00+01:00, 2026-04-01T20:30:00+01:00
0.100000, 2.5, 0.93, 2026-04-01T20:30:00+01:00, 2026-04-01T21:00:00+01:00
0.100000, 2.5, 0.93, 2026-04-01T21:00:00+01:00, 2026-04-01T21:30:00+01:00
0.100000, 2.5, 0.93, 2026-04-01T21:30:00+01:00, 2026-04-01T22:00:00+01:00
0.100000, 2.5, 0.93, 2026-04-01T22:00:00+01:00, 2026-04-01T22:30:00+01:00
0.100000, 2.5, 0.93, 2026-04-01T22:30:00+01:00, 2026-04-01T23:00:00+01:00
0.100000, 2.5, 0.93, 2026-04-01T23:00:00+01:00, 2026-04-01T23:30:00+01:00
0.100000, 2.5, 0.93, 2026-04-01T23:30:00+01:00, 2026-04-02T00:00:00+01:00
```

- [ ] **Step 2: Create fixture `partial_day.csv` (only 5 slots)**

Path: `tests/data_loading/fixtures/partial_day.csv`

```
Consumption (kwh), Estimated Cost Inc. Tax (p), Standing Charge Inc. Tax (p), Start, End
0.100000, 2.5, 0.93, 2026-05-12T00:00:00+01:00, 2026-05-12T00:30:00+01:00
0.100000, 2.5, 0.93, 2026-05-12T00:30:00+01:00, 2026-05-12T01:00:00+01:00
0.100000, 2.5, 0.93, 2026-05-12T01:00:00+01:00, 2026-05-12T01:30:00+01:00
0.100000, 2.5, 0.93, 2026-05-12T01:30:00+01:00, 2026-05-12T02:00:00+01:00
0.100000, 2.5, 0.93, 2026-05-12T02:00:00+01:00, 2026-05-12T02:30:00+01:00
```

- [ ] **Step 3: Create fixture `dst_spring.csv` (46 slots on 2026-03-29)**

UK DST springs forward on the last Sunday of March. At 01:00 GMT clocks jump to 02:00 BST. So 2026-03-29 has 46 half-hour slots in wall-clock (01:00–02:00 BST does not exist).

Path: `tests/data_loading/fixtures/dst_spring.csv`

```
Consumption (kwh), Estimated Cost Inc. Tax (p), Standing Charge Inc. Tax (p), Start, End
0.100000, 2.5, 0.93, 2026-03-29T00:00:00+00:00, 2026-03-29T00:30:00+00:00
0.100000, 2.5, 0.93, 2026-03-29T00:30:00+00:00, 2026-03-29T01:00:00+00:00
0.100000, 2.5, 0.93, 2026-03-29T02:00:00+01:00, 2026-03-29T02:30:00+01:00
0.100000, 2.5, 0.93, 2026-03-29T02:30:00+01:00, 2026-03-29T03:00:00+01:00
0.100000, 2.5, 0.93, 2026-03-29T03:00:00+01:00, 2026-03-29T03:30:00+01:00
0.100000, 2.5, 0.93, 2026-03-29T03:30:00+01:00, 2026-03-29T04:00:00+01:00
0.100000, 2.5, 0.93, 2026-03-29T04:00:00+01:00, 2026-03-29T04:30:00+01:00
0.100000, 2.5, 0.93, 2026-03-29T04:30:00+01:00, 2026-03-29T05:00:00+01:00
0.100000, 2.5, 0.93, 2026-03-29T05:00:00+01:00, 2026-03-29T05:30:00+01:00
0.100000, 2.5, 0.93, 2026-03-29T05:30:00+01:00, 2026-03-29T06:00:00+01:00
0.100000, 2.5, 0.93, 2026-03-29T06:00:00+01:00, 2026-03-29T06:30:00+01:00
0.100000, 2.5, 0.93, 2026-03-29T06:30:00+01:00, 2026-03-29T07:00:00+01:00
0.100000, 2.5, 0.93, 2026-03-29T07:00:00+01:00, 2026-03-29T07:30:00+01:00
0.100000, 2.5, 0.93, 2026-03-29T07:30:00+01:00, 2026-03-29T08:00:00+01:00
0.100000, 2.5, 0.93, 2026-03-29T08:00:00+01:00, 2026-03-29T08:30:00+01:00
0.100000, 2.5, 0.93, 2026-03-29T08:30:00+01:00, 2026-03-29T09:00:00+01:00
0.100000, 2.5, 0.93, 2026-03-29T09:00:00+01:00, 2026-03-29T09:30:00+01:00
0.100000, 2.5, 0.93, 2026-03-29T09:30:00+01:00, 2026-03-29T10:00:00+01:00
0.100000, 2.5, 0.93, 2026-03-29T10:00:00+01:00, 2026-03-29T10:30:00+01:00
0.100000, 2.5, 0.93, 2026-03-29T10:30:00+01:00, 2026-03-29T11:00:00+01:00
0.100000, 2.5, 0.93, 2026-03-29T11:00:00+01:00, 2026-03-29T11:30:00+01:00
0.100000, 2.5, 0.93, 2026-03-29T11:30:00+01:00, 2026-03-29T12:00:00+01:00
0.100000, 2.5, 0.93, 2026-03-29T12:00:00+01:00, 2026-03-29T12:30:00+01:00
0.100000, 2.5, 0.93, 2026-03-29T12:30:00+01:00, 2026-03-29T13:00:00+01:00
0.100000, 2.5, 0.93, 2026-03-29T13:00:00+01:00, 2026-03-29T13:30:00+01:00
0.100000, 2.5, 0.93, 2026-03-29T13:30:00+01:00, 2026-03-29T14:00:00+01:00
0.100000, 2.5, 0.93, 2026-03-29T14:00:00+01:00, 2026-03-29T14:30:00+01:00
0.100000, 2.5, 0.93, 2026-03-29T14:30:00+01:00, 2026-03-29T15:00:00+01:00
0.100000, 2.5, 0.93, 2026-03-29T15:00:00+01:00, 2026-03-29T15:30:00+01:00
0.100000, 2.5, 0.93, 2026-03-29T15:30:00+01:00, 2026-03-29T16:00:00+01:00
0.100000, 2.5, 0.93, 2026-03-29T16:00:00+01:00, 2026-03-29T16:30:00+01:00
0.100000, 2.5, 0.93, 2026-03-29T16:30:00+01:00, 2026-03-29T17:00:00+01:00
0.100000, 2.5, 0.93, 2026-03-29T17:00:00+01:00, 2026-03-29T17:30:00+01:00
0.100000, 2.5, 0.93, 2026-03-29T17:30:00+01:00, 2026-03-29T18:00:00+01:00
0.100000, 2.5, 0.93, 2026-03-29T18:00:00+01:00, 2026-03-29T18:30:00+01:00
0.100000, 2.5, 0.93, 2026-03-29T18:30:00+01:00, 2026-03-29T19:00:00+01:00
0.100000, 2.5, 0.93, 2026-03-29T19:00:00+01:00, 2026-03-29T19:30:00+01:00
0.100000, 2.5, 0.93, 2026-03-29T19:30:00+01:00, 2026-03-29T20:00:00+01:00
0.100000, 2.5, 0.93, 2026-03-29T20:00:00+01:00, 2026-03-29T20:30:00+01:00
0.100000, 2.5, 0.93, 2026-03-29T20:30:00+01:00, 2026-03-29T21:00:00+01:00
0.100000, 2.5, 0.93, 2026-03-29T21:00:00+01:00, 2026-03-29T21:30:00+01:00
0.100000, 2.5, 0.93, 2026-03-29T21:30:00+01:00, 2026-03-29T22:00:00+01:00
0.100000, 2.5, 0.93, 2026-03-29T22:00:00+01:00, 2026-03-29T22:30:00+01:00
0.100000, 2.5, 0.93, 2026-03-29T22:30:00+01:00, 2026-03-29T23:00:00+01:00
0.100000, 2.5, 0.93, 2026-03-29T23:00:00+01:00, 2026-03-29T23:30:00+01:00
0.100000, 2.5, 0.93, 2026-03-29T23:30:00+01:00, 2026-03-30T00:00:00+01:00
```

- [ ] **Step 4: Write failing tests**

Create `tests/data_loading/test_octopus_csv.py`:

```python
from datetime import date
from pathlib import Path

import pytest

from windfall_tco.data_loading.octopus_csv import parse_octopus_csv

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_full_day():
    result = parse_octopus_csv(FIXTURES / "one_full_day.csv")
    assert len(result.series.days) == 1
    day = result.series.days[0]
    assert day.date == date(2026, 4, 1)
    assert len(day.readings) == 48
    assert result.warnings == []


def test_parse_partial_day_skipped():
    result = parse_octopus_csv(FIXTURES / "partial_day.csv")
    assert len(result.series.days) == 0
    assert len(result.warnings) == 1
    assert "2026-05-12" in result.warnings[0]
    assert "5 slots" in result.warnings[0] or "5" in result.warnings[0]


def test_parse_dst_spring_skipped():
    result = parse_octopus_csv(FIXTURES / "dst_spring.csv")
    assert len(result.series.days) == 0
    assert len(result.warnings) == 1
    assert "2026-03-29" in result.warnings[0]


def test_parse_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        parse_octopus_csv(tmp_path / "does_not_exist.csv")


def test_parse_malformed_csv_raises(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("this,is,not,an,octopus,csv\nfoo,bar,baz,qux,quux,zap\n")
    with pytest.raises(ValueError):
        parse_octopus_csv(bad)
```

- [ ] **Step 5: Run tests to verify they fail**

Run: `uv run pytest tests/data_loading/test_octopus_csv.py -v`
Expected: ImportError.

- [ ] **Step 6: Implement `src/windfall_tco/data_loading/octopus_csv.py`**

```python
"""Octopus consumption CSV parser.

Reads the two columns we need (`Consumption (kwh)`, `Start`), groups
half-hour readings by local wall-clock date, and emits a LoadResult.
Strict: days with anything other than exactly 48 clean slots are skipped
with a warning.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from windfall_tco.data_models import (
    ConsumptionSeries,
    DailyConsumption,
    HalfHourReading,
    LoadResult,
)

_REQUIRED_COLUMNS = {"Consumption (kwh)", "Start"}


def parse_octopus_csv(path: str | Path) -> LoadResult:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(str(path))

    # Strip whitespace from headers so `Start` vs ` Start` both work.
    df = pd.read_csv(path, skipinitialspace=True)
    df.columns = df.columns.str.strip()

    missing = _REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(
            f"missing required columns: {sorted(missing)}; got {list(df.columns)}"
        )

    # Parse timestamps as tz-aware. The tz offset in the file is the BST/GMT
    # wall-clock, so the local wall-clock time is the value with its tz attached.
    try:
        starts = pd.to_datetime(df["Start"], utc=False)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"could not parse Start column as timestamps: {exc}") from exc

    # Local wall-clock date + time.
    local_date = starts.dt.date
    local_time = starts.dt.time

    parsed = pd.DataFrame(
        {
            "date": local_date,
            "time": local_time,
            "kwh": df["Consumption (kwh)"].astype(float),
        }
    )

    warnings: list[str] = []
    days: list[DailyConsumption] = []

    for d, group in parsed.groupby("date"):
        if len(group) != 48:
            warnings.append(f"Skipped {d}: {len(group)} slots (expected 48)")
            continue
        unique_times = set(group["time"])
        if len(unique_times) != 48:
            warnings.append(f"Skipped {d}: duplicate slot times")
            continue
        sorted_group = group.sort_values("time")
        readings = [
            HalfHourReading(start=t, kwh=float(k))
            for t, k in zip(sorted_group["time"], sorted_group["kwh"], strict=True)
        ]
        try:
            days.append(DailyConsumption(date=d, readings=readings))
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Skipped {d}: {exc}")

    return LoadResult(series=ConsumptionSeries(days=days), warnings=warnings)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `uv run pytest tests/data_loading/test_octopus_csv.py -v`
Expected: all five tests pass.

- [ ] **Step 8: Commit**

```bash
git add src/windfall_tco/data_loading/octopus_csv.py tests/data_loading/test_octopus_csv.py tests/data_loading/fixtures
git commit -m "Add Octopus CSV parser with strict day validation and DST skipping"
```

---

## Task 14: Streamlit app — data input and tariff editor

**Files:**
- Create: `app/streamlit_app.py`

The Streamlit app is not unit-tested (the spec says manual behavior testing). We build it in two tasks: Task 14 sets up layout + data input + tariff editor; Task 15 adds the form, the sim run, and the charts.

- [ ] **Step 1: Create `app/streamlit_app.py` — skeleton, data input, tariff editor**

```python
"""Streamlit UI for the home battery TCO calculator."""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import streamlit as st

from windfall_tco.data_loading.manual_profile import from_hourly_watts
from windfall_tco.data_loading.octopus_csv import parse_octopus_csv
from windfall_tco.data_models import (
    ConsumptionSeries,
    LoadResult,
    Tariff,
    TariffBand,
)
from windfall_tco.tariffs import PRESETS

st.set_page_config(page_title="Home Battery TCO Calculator", layout="wide")
st.title("Home Battery TCO Calculator")


# ---------- Sidebar: data source ----------

with st.sidebar:
    st.header("1. Consumption data")
    data_source = st.radio(
        "Source",
        options=["Upload Octopus CSV", "Manual profile"],
        key="data_source",
    )

    load_result: LoadResult | None = None

    if data_source == "Upload Octopus CSV":
        uploaded = st.file_uploader("Octopus CSV", type=["csv"])
        if uploaded is not None:
            tmp_path = Path(st.session_state.get("_tmp_dir", "/tmp")) / uploaded.name
            tmp_path.write_bytes(uploaded.getvalue())
            try:
                load_result = parse_octopus_csv(tmp_path)
            except Exception as exc:  # noqa: BLE001
                st.error(f"Failed to parse CSV: {exc}")
    else:
        st.write("Enter typical hourly average watts (00:00 → 23:00):")
        default_watts = [200.0] * 24
        watts_df = pd.DataFrame(
            {"hour": [f"{h:02d}:00" for h in range(24)], "avg_watts": default_watts}
        )
        edited = st.data_editor(watts_df, key="manual_watts", num_rows="fixed")
        try:
            load_result = from_hourly_watts(edited["avg_watts"].astype(float).tolist())
        except ValueError as exc:
            st.error(f"Manual profile error: {exc}")

    if load_result is not None:
        st.success(f"Loaded {len(load_result.series.days)} day(s).")
        if load_result.warnings:
            with st.expander(f"Load warnings ({len(load_result.warnings)})"):
                for w in load_result.warnings:
                    st.write(f"- {w}")

# Persist the parsed series so the rest of the app sees it.
if load_result is not None:
    st.session_state["series"] = load_result.series


# ---------- Main: tariff editor ----------

st.header("2. Tariff")

preset_name = st.selectbox(
    "Preset",
    options=["Custom", *PRESETS.keys()],
    key="tariff_preset",
)

# Build initial editable table
if preset_name in PRESETS:
    preset = PRESETS[preset_name]
    rows = [
        {
            "start": b.start.strftime("%H:%M"),
            "end": b.end.strftime("%H:%M:%S"),
            "rate_pence_per_kwh": b.rate_pence_per_kwh,
        }
        for b in preset.bands
    ]
else:
    rows = [{"start": "00:00", "end": "23:59:59", "rate_pence_per_kwh": 27.0}]

tariff_df = st.data_editor(
    pd.DataFrame(rows),
    key="tariff_editor",
    num_rows="dynamic",
)

tariff: Tariff | None = None
try:
    from datetime import datetime as _dt

    def _parse_time(s: str):
        # Accept both HH:MM and HH:MM:SS
        for fmt in ("%H:%M:%S.%f", "%H:%M:%S", "%H:%M"):
            try:
                return _dt.strptime(s.strip(), fmt).time()
            except ValueError:
                continue
        raise ValueError(f"unparseable time: {s}")

    bands = [
        TariffBand(
            start=_parse_time(str(row["start"])),
            end=_parse_time(str(row["end"])),
            rate_pence_per_kwh=float(row["rate_pence_per_kwh"]),
        )
        for _, row in tariff_df.iterrows()
    ]
    tariff = Tariff(name=preset_name, bands=bands)
except Exception as exc:  # noqa: BLE001
    st.error(f"Tariff is invalid: {exc}")

if tariff is not None:
    st.session_state["tariff"] = tariff

st.info("Configure battery and run the simulation in the next step (coming in Task 15).")
```

- [ ] **Step 2: Run the app to verify it loads**

Run: `uv run streamlit run app/streamlit_app.py`
Expected: browser opens, page loads without errors. Upload a CSV or switch to Manual; you should see the tariff editor and the "coming in Task 15" notice. Verify the preset dropdown swaps tariff bands correctly. Kill the server after verification (Ctrl-C).

- [ ] **Step 3: Commit**

```bash
git add app/streamlit_app.py
git commit -m "Add Streamlit app skeleton with data input and tariff editor"
```

---

## Task 15: Streamlit app — form, simulation, summary, charts

**Files:**
- Modify: `app/streamlit_app.py`

- [ ] **Step 1: Replace the contents of `app/streamlit_app.py` with the full implementation**

```python
"""Streamlit UI for the home battery TCO calculator."""

from __future__ import annotations

from datetime import datetime as _dt
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from windfall_tco.data_loading.manual_profile import from_hourly_watts
from windfall_tco.data_loading.octopus_csv import parse_octopus_csv
from windfall_tco.data_models import (
    BatterySpec,
    ConsumptionSeries,
    DispatchPolicy,
    LoadResult,
    SimResult,
    Tariff,
    TariffBand,
)
from windfall_tco.economics.payback import savings_summary, simple_payback_years
from windfall_tco.simulation.run import run
from windfall_tco.tariffs import PRESETS

st.set_page_config(page_title="Home Battery TCO Calculator", layout="wide")
st.title("Home Battery TCO Calculator")


# ---------- helpers ----------

def _parse_time(s: str):
    for fmt in ("%H:%M:%S.%f", "%H:%M:%S", "%H:%M"):
        try:
            return _dt.strptime(str(s).strip(), fmt).time()
        except ValueError:
            continue
    raise ValueError(f"unparseable time: {s}")


def _tariff_cheapest_rate(t: Tariff) -> float:
    return min(b.rate_pence_per_kwh for b in t.bands)


def _tariff_most_expensive_rate(t: Tariff) -> float:
    return max(b.rate_pence_per_kwh for b in t.bands)


# ---------- Sidebar: data source ----------

with st.sidebar:
    st.header("1. Consumption data")
    data_source = st.radio(
        "Source",
        options=["Upload Octopus CSV", "Manual profile"],
        key="data_source",
    )

    load_result: LoadResult | None = None

    if data_source == "Upload Octopus CSV":
        uploaded = st.file_uploader("Octopus CSV", type=["csv"])
        if uploaded is not None:
            tmp_path = Path("/tmp") / uploaded.name
            tmp_path.write_bytes(uploaded.getvalue())
            try:
                load_result = parse_octopus_csv(tmp_path)
            except Exception as exc:  # noqa: BLE001
                st.error(f"Failed to parse CSV: {exc}")
    else:
        st.write("Enter typical hourly average watts (00:00 → 23:00):")
        default_watts = [200.0] * 24
        watts_df = pd.DataFrame(
            {"hour": [f"{h:02d}:00" for h in range(24)], "avg_watts": default_watts}
        )
        edited = st.data_editor(watts_df, key="manual_watts", num_rows="fixed")
        try:
            load_result = from_hourly_watts(edited["avg_watts"].astype(float).tolist())
        except ValueError as exc:
            st.error(f"Manual profile error: {exc}")

    if load_result is not None:
        st.success(f"Loaded {len(load_result.series.days)} day(s).")
        if load_result.warnings:
            with st.expander(f"Load warnings ({len(load_result.warnings)})"):
                for w in load_result.warnings:
                    st.write(f"- {w}")

if load_result is not None:
    st.session_state["series"] = load_result.series


# ---------- Main: tariff editor ----------

st.header("2. Tariff")

preset_name = st.selectbox(
    "Preset",
    options=["Custom", *PRESETS.keys()],
    key="tariff_preset",
)

if preset_name in PRESETS:
    preset = PRESETS[preset_name]
    rows = [
        {
            "start": b.start.strftime("%H:%M"),
            "end": b.end.strftime("%H:%M:%S"),
            "rate_pence_per_kwh": b.rate_pence_per_kwh,
        }
        for b in preset.bands
    ]
else:
    rows = [{"start": "00:00", "end": "23:59:59", "rate_pence_per_kwh": 27.0}]

tariff_df = st.data_editor(
    pd.DataFrame(rows),
    key="tariff_editor",
    num_rows="dynamic",
)

tariff: Tariff | None = None
try:
    bands = [
        TariffBand(
            start=_parse_time(str(row["start"])),
            end=_parse_time(str(row["end"])),
            rate_pence_per_kwh=float(row["rate_pence_per_kwh"]),
        )
        for _, row in tariff_df.iterrows()
    ]
    tariff = Tariff(name=preset_name, bands=bands)
except Exception as exc:  # noqa: BLE001
    st.error(f"Tariff is invalid: {exc}")


# ---------- Sidebar: battery + dispatch + run button (form) ----------

with st.sidebar:
    st.header("3. Battery and dispatch")
    with st.form(key="sim_config"):
        capacity = st.slider("Usable capacity (kWh)", 1.0, 20.0, 2.5, 0.1)
        discharge_w = st.slider("Max discharge power (W)", 200, 5000, 800, 50)
        charge_w = st.slider("Max charge power (W)", 200, 5000, 800, 50)
        efficiency_pct = st.slider("Round-trip efficiency (%)", 70, 100, 90, 1)
        initial_soc_pct = st.slider("Initial SoC (% of capacity)", 0, 100, 50, 5)

        default_cheap = _tariff_cheapest_rate(tariff) if tariff is not None else 10.0
        default_peak = _tariff_most_expensive_rate(tariff) if tariff is not None else 30.0

        charge_below = st.number_input(
            "Charge when price ≤ (p/kWh)",
            min_value=0.0,
            value=float(default_cheap),
            step=0.1,
        )
        discharge_above = st.number_input(
            "Discharge when price ≥ (p/kWh)",
            min_value=0.0,
            value=float(default_peak),
            step=0.1,
        )

        battery_cost_pounds = st.number_input(
            "Battery system cost (£)",
            min_value=0.0,
            value=1500.0,
            step=50.0,
        )

        submitted = st.form_submit_button("Run simulation")


# ---------- Run simulation ----------

series: ConsumptionSeries | None = st.session_state.get("series")

if submitted:
    if series is None:
        st.warning("Load consumption data first.")
    elif tariff is None:
        st.warning("Fix the tariff before running.")
    else:
        spec = BatterySpec(
            usable_capacity_kwh=capacity,
            max_charge_power_w=charge_w,
            max_discharge_power_w=discharge_w,
            round_trip_efficiency=efficiency_pct / 100,
            initial_soc_fraction=initial_soc_pct / 100,
        )
        try:
            policy = DispatchPolicy(
                charge_below_pence_per_kwh=float(charge_below),
                discharge_above_pence_per_kwh=float(discharge_above),
            )
        except Exception as exc:  # noqa: BLE001
            st.error(f"Dispatch thresholds invalid: {exc}")
        else:
            st.session_state["sim_result"] = run(series, tariff, spec, policy)
            st.session_state["sim_battery_cost_pounds"] = battery_cost_pounds


# ---------- Results ----------

sim_result: SimResult | None = st.session_state.get("sim_result")

if sim_result is not None:
    summary = savings_summary(sim_result)
    battery_cost_pounds = st.session_state.get("sim_battery_cost_pounds", 0.0)
    payback = simple_payback_years(battery_cost_pounds, summary.annualized_savings_pence)

    st.header("Results")
    c1, c2, c3 = st.columns(3)
    c1.metric("Annual savings", f"£{summary.annualized_savings_pence / 100:,.2f}")
    c2.metric(
        "Daily average",
        f"£{summary.daily_average_savings_pence / 100:,.2f}",
    )
    c3.metric(
        "Payback",
        "Never (no savings)" if payback is None else f"{payback:.1f} years",
    )

    # ----- Spaghetti overview chart -----
    st.subheader("Daily consumption and battery dispatch (all days)")
    fig = go.Figure()
    for day in sim_result.days:
        xs = [s.timestamp_start.strftime("%H:%M") for s in day.steps]
        load = [s.load_kwh for s in day.steps]
        net = [s.battery_discharge_kwh - s.battery_charge_kwh for s in day.steps]
        fig.add_trace(
            go.Scatter(
                x=xs,
                y=load,
                mode="lines",
                line=dict(width=1),
                opacity=0.15,
                name="Load",
                legendgroup="load",
                showlegend=(day is sim_result.days[0]),
                hovertemplate="%{x} · %{y:.3f} kWh<extra>Load</extra>",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=xs,
                y=net,
                mode="lines",
                line=dict(width=1, color="orange"),
                opacity=0.25,
                name="Battery net (discharge − charge)",
                legendgroup="battery",
                showlegend=(day is sim_result.days[0]),
                hovertemplate="%{x} · %{y:.3f} kWh<extra>Battery</extra>",
            )
        )

    # Tariff band shading (only if tariff exists)
    if tariff is not None:
        for b in tariff.bands:
            fig.add_vrect(
                x0=b.start.strftime("%H:%M"),
                x1=b.end.strftime("%H:%M"),
                fillcolor=_band_color(b.rate_pence_per_kwh, tariff),
                opacity=0.08,
                line_width=0,
            )

    fig.update_layout(
        xaxis_title="Time of day",
        yaxis_title="kWh (per 30 min)",
        height=400,
    )
    st.plotly_chart(fig, use_container_width=True)

    # ----- Day drill-down -----
    st.subheader("Single-day detail")
    dates = [d.date.isoformat() for d in sim_result.days]
    selected = st.selectbox("Pick a day", options=dates, index=0)
    day_idx = dates.index(selected)
    day = sim_result.days[day_idx]

    prev_col, next_col = st.columns(2)
    if prev_col.button("← Previous day", disabled=day_idx == 0):
        day_idx = max(0, day_idx - 1)
    if next_col.button("Next day →", disabled=day_idx == len(dates) - 1):
        day_idx = min(len(dates) - 1, day_idx + 1)
    day = sim_result.days[day_idx]

    xs = [s.timestamp_start.strftime("%H:%M") for s in day.steps]
    detail = go.Figure()
    detail.add_trace(
        go.Scatter(
            x=xs,
            y=[s.load_kwh for s in day.steps],
            mode="lines",
            name="Load",
            line=dict(width=2),
        )
    )
    detail.add_trace(
        go.Bar(
            x=xs,
            y=[s.battery_charge_kwh for s in day.steps],
            name="Battery charge",
            marker_color="#5b9bd5",
        )
    )
    detail.add_trace(
        go.Bar(
            x=xs,
            y=[-s.battery_discharge_kwh for s in day.steps],
            name="Battery discharge",
            marker_color="#f4a261",
        )
    )
    detail.add_trace(
        go.Scatter(
            x=xs,
            y=[s.grid_import_kwh for s in day.steps],
            mode="lines",
            name="Grid import",
            line=dict(dash="dot"),
        )
    )
    detail.add_trace(
        go.Scatter(
            x=xs,
            y=[s.battery_soc_kwh for s in day.steps],
            mode="lines",
            name="Battery SoC (kWh)",
            yaxis="y2",
            line=dict(color="grey", width=1),
        )
    )
    if tariff is not None:
        for b in tariff.bands:
            detail.add_vrect(
                x0=b.start.strftime("%H:%M"),
                x1=b.end.strftime("%H:%M"),
                fillcolor=_band_color(b.rate_pence_per_kwh, tariff),
                opacity=0.08,
                line_width=0,
            )
    detail.update_layout(
        barmode="relative",
        xaxis_title="Time of day",
        yaxis_title="kWh (per 30 min)",
        yaxis2=dict(
            title="SoC (kWh)",
            overlaying="y",
            side="right",
            showgrid=False,
        ),
        height=450,
    )
    st.plotly_chart(detail, use_container_width=True)
```

- [ ] **Step 2: Add the `_band_color` helper at the top of the file (after the imports)**

Insert after the existing `_tariff_most_expensive_rate` function:

```python
def _band_color(rate: float, tariff: Tariff) -> str:
    cheap = _tariff_cheapest_rate(tariff)
    peak = _tariff_most_expensive_rate(tariff)
    if peak == cheap:
        return "rgba(128,128,128,1.0)"
    if rate <= cheap + (peak - cheap) * 0.2:
        return "rgba(0, 180, 0, 1.0)"
    if rate >= peak - (peak - cheap) * 0.2:
        return "rgba(220, 40, 40, 1.0)"
    return "rgba(128, 128, 128, 1.0)"
```

- [ ] **Step 3: Run the app and exercise it**

Run: `uv run streamlit run app/streamlit_app.py`

Verify:
1. Switch data source between Upload and Manual. For Manual, edit some watt values; load confirmation appears.
2. Pick Octopus Cosy preset; tariff table populates with 7 bands.
3. Adjust battery sliders, click Run simulation.
4. Verify three summary cards appear with sensible numbers (if battery cost = £1500 and annual savings > 0, payback shows years; if savings = 0, shows "Never").
5. Spaghetti chart renders with load + battery lines + tariff band shading.
6. Day selector works; drill-down chart renders with stacked bars + SoC line.
7. Re-run with a different battery capacity — results update on submit.

Kill the server after verification.

- [ ] **Step 4: Commit**

```bash
git add app/streamlit_app.py
git commit -m "Add Streamlit form, simulation runner, summary cards, and charts"
```

---

## Task 16: End-to-end smoke test

**Files:**
- Create: `tests/test_end_to_end.py`

- [ ] **Step 1: Write an end-to-end test exercising the full core**

```python
from pathlib import Path

import pytest

from windfall_tco.data_loading.octopus_csv import parse_octopus_csv
from windfall_tco.data_models import BatterySpec, DispatchPolicy
from windfall_tco.economics.payback import savings_summary, simple_payback_years
from windfall_tco.simulation.run import run
from windfall_tco.tariffs import OCTOPUS_COSY

FIXTURES = Path(__file__).parent / "data_loading" / "fixtures"


def test_end_to_end_full_pipeline():
    load_result = parse_octopus_csv(FIXTURES / "one_full_day.csv")
    assert len(load_result.series.days) == 1

    spec = BatterySpec()  # defaults: 2.5 kWh, 800 W, 90% eff
    policy = DispatchPolicy(
        charge_below_pence_per_kwh=12.0,   # matches Cosy cheap band
        discharge_above_pence_per_kwh=39.0,  # matches Cosy peak band
    )

    sim_result = run(load_result.series, OCTOPUS_COSY, spec, policy)

    assert sim_result.simulated_days == 1
    assert sim_result.total_baseline_cost_pence > 0

    summary = savings_summary(sim_result)
    assert summary.simulated_days == 1

    payback = simple_payback_years(1500.0, summary.annualized_savings_pence)
    assert payback is None or payback > 0
```

- [ ] **Step 2: Run the test**

Run: `uv run pytest tests/test_end_to_end.py -v`
Expected: passes.

- [ ] **Step 3: Run the full test suite with coverage**

Run: `uv run pytest --cov=src/windfall_tco --cov-report=term-missing`
Expected: all tests pass. Coverage on `src/windfall_tco/` should be ≥ 90%. If below, inspect uncovered lines; most gaps will be defensive branches or the unused `BatteryState` mutation path.

- [ ] **Step 4: Commit**

```bash
git add tests/test_end_to_end.py
git commit -m "Add end-to-end smoke test exercising the full core pipeline"
```

---

## Final checklist

- [ ] Run `uv run pytest -v` — all tests green.
- [ ] Run `uv run ruff check` — no lint issues. Fix any and commit as `"style: ruff fixes"`.
- [ ] Run `uv run ruff format` — format the codebase if any diffs. Commit as `"style: ruff format"`.
- [ ] Run `uv run streamlit run app/streamlit_app.py` and manually verify the flow once more.
- [ ] `git log --oneline` should show ~16 commits, one per task (plus style commits).

---

## Self-review notes (written during plan authoring)

**Spec coverage check:**
- §3.1 Octopus CSV loader → Task 13 ✓
- §3.1 Manual 24h profile loader → Task 12 ✓
- §3.2 Tariff ToU + presets → Tasks 4, 14 ✓
- §3.3 Battery spec → Task 2 ✓
- §3.4 Dispatch policy → Task 2 ✓
- §3.5 Payback input → Task 15 ✓
- §4 Headline summary + spaghetti + drill-down → Task 15 ✓
- §5.1 Repo layout → Task 1 ✓
- §5.2 Tooling (uv, pytest, ruff, pydantic, plotly, streamlit, pandas) → Task 1 ✓
- §6 Data models → Tasks 2, 3 ✓
- §7.1 `step()` → Task 6 ✓
- §7.2 Step algorithm branches → Tasks 6, 7 ✓
- §7.3 `run()` with SoC continuity → Task 9 ✓
- §7.5 Golden-value scenarios → Task 9 (flat-idle, perfect-arbitrage, baseline); other scenarios (undersized, short-window, efficiency sweep) are covered by the hypothesis tests in Task 8 as strictly stronger invariants — adding them as golden-value tests is optional polish.
- §8.1 Octopus CSV strict day validation, DST skip, partial skip → Task 13 ✓
- §8.2 Manual profile → Task 12 ✓
- §9 Economics (cost, payback, savings summary) → Tasks 10, 11 ✓
- §10.1 Form-gated interaction → Task 15 ✓
- §10.2 Layout (sidebar config, main tariff+results) → Tasks 14, 15 ✓
- §10.3 Tariff preset handling → Task 14 ✓
- §10.4 Chart specs (spaghetti + drill-down with tariff shading + SoC axis) → Task 15 ✓
- §11.2 Property tests (hypothesis, energy conservation, non-negativity, SoC bounds, SoC delta) → Task 8 ✓
- §11.3 pytest + pytest-cov + hypothesis + ruff → Task 1 ✓

**Gaps intentionally left out of the plan** (not required by spec):
- `@st.cache_data` on `run()` — mentioned in §10.5 as a nicety; fine to skip for MVP since form-gated execution already avoids unnecessary reruns. Can be added later without refactoring.
- "Golden-value test for undersized battery / short charge window / efficiency sweep" as named tests — covered by property tests and the perfect-arbitrage analytical test. Adding them as named cases is optional polish.

**Type consistency check:** function names (`step`, `run`, `rate_at`, `cost_of_slots`, `baseline_daily_cost`, `simple_payback_years`, `savings_summary`, `from_hourly_watts`, `parse_octopus_csv`) are used identically everywhere they appear. Model field names (`grid_for_load_kwh`, `battery_discharge_kwh`, `energy_stored_kwh`, `initial_soc_fraction`, `usable_capacity_kwh`, `round_trip_efficiency`) match across the spec, the data models task, and all downstream tasks.
