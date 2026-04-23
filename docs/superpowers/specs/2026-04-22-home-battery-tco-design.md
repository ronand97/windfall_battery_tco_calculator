# Windfall Battery TCO Calculator — Design Spec

**Status:** Complete draft. Pending user review before implementation plan.

**Created:** 2026-04-22
**Last updated:** 2026-04-23

---

## 1. Purpose

A personal Python tool with a Streamlit UI that answers:

> *If I install a 2.5 kWh / 800 W home battery on a static time-of-use electricity tariff, how much would I save over a year, and how long is the payback period?*

## 2. Scope

- **In scope:** savings modeling + simple payback period; pure grid arbitrage; UK/Octopus context; static time-of-use tariffs; single-user local Streamlit app.
- **Out of scope:** full TCO (no capacity fade, replacement cycles, NPV, or discount rate); solar generation (now or later); dynamic half-hourly tariffs like Octopus Agile (but data models must be extensible to support them without rework); export tariffs; multi-user/auth.

## 3. Inputs

### 3.1 Consumption data — two entrypoints, one output shape

1. **Octopus CSV upload** — half-hourly consumption export from the Octopus account dashboard. Produces a multi-day `ConsumptionSeries`.
2. **Manual entry** — a 24-row editable table of average watts per hour. Auto-split into 48 half-hour kWh values (`kwh = watts / 1000 × 0.5`). Produces a 1-day `ConsumptionSeries`; simulation scales savings to annual by ×365.

Both entrypoints produce the same pydantic `ConsumptionSeries` type — downstream code does not know which was used.

### 3.2 Tariff

Static time-of-use with N contiguous bands covering 00:00–24:00. No overlaps, no gaps. Rate in pence per kWh. Presets shipped: Octopus Cosy, Octopus Go. Custom tariffs editable in-app.

### 3.3 Battery specification

| Parameter | Default | UI range |
|---|---|---|
| Usable capacity | 2.5 kWh | 1–20 kWh |
| Max discharge power | 800 W | 200–5000 W |
| Max charge power | 800 W | 200–5000 W |
| Round-trip efficiency (charge-side) | 90% | 70–100% |
| Initial SoC | 50% of usable capacity | 0–100% |

### 3.4 Dispatch policy

Price-threshold rules:
- **Charge** from grid when `price ≤ charge_below_pence_per_kwh`
- **Discharge** to home load when `price ≥ discharge_above_pence_per_kwh`
- **Idle** otherwise
- Constraint: `discharge_above > charge_below` (enforced by model validator)
- Defaults auto-derived from tariff: `charge_below` = cheapest band rate, `discharge_above` = most expensive band rate. User can override via sliders.

Battery **matches load** during discharge (up to 800 W). No export to grid.

### 3.5 Payback

Single user-entered number: battery system cost in £. Simple payback = `cost / annualized_savings`.

## 4. Outputs

1. **Headline summary cards** — annual savings (£), daily average savings (£), payback period (years).
2. **Multi-day overview chart** (spaghetti plot) — all days' consumption overlaid on a 24h x-axis, battery net dispatch overlaid, tariff bands shaded as background.
3. **Single-day drill-down chart** — day selector; full energy profile + simulated battery dispatch for the selected day.

## 5. Architecture

**Approach: functional core, imperative shell.** All business logic in pure functions operating on immutable pydantic data models. Streamlit is a thin UI layer over the core.

### 5.1 Repo layout

```
windfall_battery_tco_calculator/
├── pyproject.toml
├── README.md
├── .python-version           # 3.12
├── .gitignore
├── src/
│   └── windfall_tco/
│       ├── __init__.py
│       ├── data_models.py          # all pydantic models in one file
│       ├── tariffs.py              # shipped tariff presets (Cosy, Go)
│       ├── data_loading/
│       │   ├── __init__.py
│       │   ├── octopus_csv.py
│       │   └── manual_profile.py
│       ├── simulation/
│       │   ├── __init__.py
│       │   ├── step.py
│       │   └── run.py
│       └── economics/
│           ├── __init__.py
│           ├── cost.py
│           └── payback.py
├── app/
│   └── streamlit_app.py
└── tests/
    ├── test_data_models.py
    ├── data_loading/
    │   └── fixtures/               # sample Octopus CSVs
    ├── simulation/
    │   ├── test_step.py
    │   └── test_run.py             # golden-value scenarios
    └── economics/
```

### 5.2 Tooling

| Concern | Choice |
|---|---|
| Python version | 3.12 |
| Env & deps | uv |
| Test | pytest + pytest-cov + hypothesis |
| Lint + format | ruff |
| Data model validation | pydantic (replaces strict mypy; mypy optional) |
| Charting | plotly |
| Numerics | pandas (OK inside `simulation/` for readability), numpy as needed |

## 6. Data Models

Single file: `src/windfall_tco/data_models.py`. `frozen=True` on pure value objects; `BatteryState` mutability revisited during implementation.

```python
from datetime import date, time
from pydantic import BaseModel, ConfigDict, Field

# -------- Tariff --------
class TariffBand(BaseModel):
    model_config = ConfigDict(frozen=True)
    start: time
    end: time
    rate_pence_per_kwh: float = Field(gt=0)

class Tariff(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    bands: list[TariffBand]   # validator: must cover 00:00–24:00 exactly, no overlaps

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
    # validator: discharge_above > charge_below

# -------- Consumption --------
class HalfHourReading(BaseModel):
    model_config = ConfigDict(frozen=True)
    start: time
    kwh: float = Field(ge=0)

class DailyConsumption(BaseModel):
    model_config = ConfigDict(frozen=True)
    date: date
    readings: list[HalfHourReading]   # validator: exactly 48, sorted, no gaps

class ConsumptionSeries(BaseModel):
    model_config = ConfigDict(frozen=True)
    days: list[DailyConsumption]      # 1 day for manual entry, N days for Octopus

# -------- Load result (from data_loading entrypoints) --------
class LoadResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    series: ConsumptionSeries
    warnings: list[str]               # e.g. "Skipped 2026-03-29: DST transition"

# -------- Simulation results --------
class StepResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    timestamp_start: time
    load_kwh: float
    price_pence_per_kwh: float
    grid_import_kwh: float            # total grid draw this slot
    grid_for_load_kwh: float          # portion of grid_import_kwh that went to load
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

# -------- Economics summary --------
class SavingsSummary(BaseModel):
    model_config = ConfigDict(frozen=True)
    total_savings_pence: float
    simulated_days: int
    daily_average_savings_pence: float
    annualized_savings_pence: float
    baseline_annualized_cost_pence: float
    with_battery_annualized_cost_pence: float
```

**Notes:**
- Time resolution hardcoded to half-hourly (48 slots/day). Matches Octopus exports.
- `ConsumptionSeries` is the shared output of both data-loading entrypoints.
- Standing charge intentionally omitted — doesn't affect savings (paid either way).
- `HalfHourReading.start` is `time` only; day is carried by enclosing `DailyConsumption.date`.
- `BatteryState` is frozen: `step()` produces a new instance each call (pure functional transition).

## 7. Simulation Logic

Pure functions in `src/windfall_tco/simulation/`.

### 7.1 `step()` — the atomic half-hour transition

```python
def step(
    prior_state: BatteryState,
    load_kwh: float,
    price_pence_per_kwh: float,
    spec: BatterySpec,
    policy: DispatchPolicy,
) -> tuple[BatteryState, StepResult]:
    ...
```

### 7.2 Step algorithm — precedence

Each slot enters exactly one of three branches, chosen by price:

```
if price >= policy.discharge_above:    # DISCHARGE
elif price <= policy.charge_below:     # CHARGE
else:                                  # IDLE
```

Mutually exclusive by `DispatchPolicy` validator (`discharge_above > charge_below`).

**Discharge branch:**
```
max_discharge_kwh      = max_discharge_power_w / 1000 * 0.5
battery_discharge_kwh  = min(max_discharge_kwh, load_kwh, energy_stored_kwh)
grid_import_kwh        = load_kwh - battery_discharge_kwh
battery_charge_kwh     = 0
new_soc                = energy_stored_kwh - battery_discharge_kwh
```

**Charge branch:**
```
max_charge_kwh         = max_charge_power_w / 1000 * 0.5
headroom_kwh           = usable_capacity_kwh - energy_stored_kwh
effective_stored       = min(max_charge_kwh * efficiency, headroom_kwh)
grid_kwh_for_charge    = effective_stored / efficiency
grid_import_kwh        = load_kwh + grid_kwh_for_charge
battery_charge_kwh     = effective_stored
battery_discharge_kwh  = 0
new_soc                = energy_stored_kwh + effective_stored
```

**Idle branch:**
```
grid_import_kwh        = load_kwh
battery_charge_kwh     = 0
battery_discharge_kwh  = 0
new_soc                = energy_stored_kwh
```

**Always:**
```
grid_for_load_kwh = load_kwh - battery_discharge_kwh
cost_pence        = grid_import_kwh * price_pence_per_kwh
```

Note: `grid_for_load_kwh` equals `grid_import_kwh` in the discharge and idle branches, and equals `load_kwh` in the charge branch (because the battery's charge draw is the only reason `grid_import > load` in that branch). The single formula above (`load − battery_discharge`) produces the right value in all three branches and makes the energy-conservation invariant trivially testable.

### 7.3 `run()` — fold over the full series

```python
def run(
    series: ConsumptionSeries,
    tariff: Tariff,
    spec: BatterySpec,
    policy: DispatchPolicy,
) -> SimResult:
    ...
```

- Folds `step()` over every half-hour slot of every day in the series.
- SoC is continuous across day boundaries (day 2 starts at day 1's final SoC).
- Initial SoC = `spec.initial_soc_fraction × spec.usable_capacity_kwh`.
- Baseline cost per day = `sum(load_kwh × price)` over all slots (no battery action).
- `savings_pence = baseline_cost_pence − total_cost_pence` per day; summed to `total_savings_pence`.
- `annualized_savings_pence = total_savings_pence × 365 / simulated_days`.

### 7.4 Modeling decisions

- Slot energy = power × 0.5 h. No sub-slot integration.
- Round-trip efficiency on charge side only. Pay more grid kWh for the same stored kWh.
- No cycle/fatigue modeling in MVP.
- Stateless dispatch — no look-ahead across slots.
- Edge case: battery empty during discharge window → `battery_discharge_kwh = 0`, all load to grid at peak price.
- Edge case: battery full during charge window → `battery_charge_kwh = 0`, no extra grid pull.

### 7.5 Golden-value test scenarios

- **All-idle**: flat one-band tariff. Battery never triggers. Savings = 0.
- **Perfect arbitrage**: two bands (e.g. 5p / 30p). Analytical expected savings.
- **Battery-empty-at-peak**: undersized battery. Partial savings; sim stays honest.
- **Charge-window-too-short**: peak longer than cheap window. Steady-state savings < day-1.
- **Efficiency sweep**: `round_trip_efficiency` 1.0 vs 0.5. Savings ratio matches analytical.

## 8. Data Loading

Two entrypoints under `src/windfall_tco/data_loading/`. Both return `LoadResult(series, warnings)`.

### 8.1 Octopus CSV parser — `octopus_csv.py`

**Expected CSV shape** (from a real Octopus consumption export):

```
Consumption (kwh), Estimated Cost Inc. Tax (p), Standing Charge Inc. Tax (p), Start, End
0.253000, 6.424612425, 0.93, 2026-04-01T00:00:00+01:00, 2026-04-01T00:30:00+01:00
...
```

**Parser behavior:**
- Read only `Consumption (kwh)` and `Start` columns. Ignore `Estimated Cost`, `Standing Charge`, `End`.
- Parse `Start` as tz-aware ISO 8601. Convert to local wall-clock (date, time) — the tariff is defined in wall-clock, so that's the authoritative representation for simulation.
- Group rows by local wall-clock date.
- **Strict day validation** — keep only days with exactly 48 slots, sorted by time, no duplicates. Skip others and emit warnings:
  - `"Skipped 2026-03-29: DST transition (46 slots)"`
  - `"Skipped 2026-10-25: DST transition (50 slots)"`
  - `"Skipped 2026-05-12: partial data (37 slots)"`
- Produce one `DailyConsumption` per retained date; assemble into `ConsumptionSeries`.
- Hard failures (missing columns, unparsable timestamps) raise `ValueError` with a clear message.

### 8.2 Manual profile parser — `manual_profile.py`

- Input: 24 average-watt values (one per hour, 00:00–23:00).
- Convert: each hourly watts value → two identical half-hour kWh values (`kwh = watts / 1000 × 0.5`).
- Produce a single `DailyConsumption` with `date = date.today()`. The date is a label only — the simulation annualizes by ×365 regardless of which calendar day it carries.
- Wrap in `ConsumptionSeries(days=[…])`.
- Returns `LoadResult(series, warnings=[])`.

### 8.3 Error surfacing

- `LoadResult.warnings` rendered in Streamlit as `st.expander("Load warnings (N)")` containing the list.
- Hard-failure exceptions caught at the Streamlit layer and displayed via `st.error`.

## 9. Economics

Pure functions in `src/windfall_tco/economics/`.

### 9.1 Unit convention

**Pence everywhere internally; convert to £ only at the display boundary.** Octopus CSV is already in pence; tariff is entered in pence/kWh; pence-as-float avoids rounding drift at the £0.01 scale.

### 9.2 Cost — `economics/cost.py`

```python
def cost_of_slots(
    readings: list[HalfHourReading],
    tariff: Tariff,
) -> float:  # total pence
    ...

def baseline_daily_cost(
    day: DailyConsumption,
    tariff: Tariff,
) -> float:  # pence
    ...
```

Same formula the simulator already uses internally; exposed for reuse (e.g., computing baselines without running the sim).

### 9.3 Payback — `economics/payback.py`

```python
def simple_payback_years(
    battery_cost_pounds: float,
    annualized_savings_pence: float,
) -> float | None:
    if annualized_savings_pence <= 0:
        return None
    return battery_cost_pounds / (annualized_savings_pence / 100)
```

- `None` signals "never pays back" — Streamlit renders as "Never (no savings)".
- No discounting, no tariff escalation, no inflation.

### 9.4 Savings summary

```python
def savings_summary(result: SimResult) -> SavingsSummary: ...
```

Packs derived fields (`daily_average_savings_pence`, annualized baseline, annualized with-battery) for the Streamlit headline cards.

### 9.5 Not included

- Battery degradation / TCO (deferred per scope decision — option B).
- Tariff escalation.
- Discounting / NPV.
- Cost-of-capital on upfront spend.

## 10. Streamlit Surface

`app/streamlit_app.py` — the only non-pure code path. Imports the core as a library.

### 10.1 Interaction pattern

- **Form-gated**: config inputs live inside an `st.form`; sim runs only when the user clicks "Run simulation". Rationale: year-long Octopus dumps + pandas overhead could make auto-rerun janky; explicit submit is cleaner.
- **CSV upload / manual entry lives outside the form** — `st.file_uploader` rerun semantics conflict with forms. Upload populates an in-memory `ConsumptionSeries` that the form-driven sim consumes.

### 10.2 Layout

- **Sidebar**:
  - Data source toggle: "Upload Octopus CSV" / "Manual profile".
  - If upload: `st.file_uploader`. Shows parsed day count + load warnings expander.
  - If manual: `st.data_editor` with 24 rows (hour, avg watts).
  - Inside `st.form`:
    - Battery spec sliders (capacity, charge power, discharge power, efficiency, initial SoC).
    - Dispatch thresholds (charge below, discharge above), defaulting from tariff.
    - Battery cost (£) input.
    - "Run simulation" submit button.
- **Main area**:
  - Tariff editor section (lives outside the form):
    - Preset dropdown: Cosy / Go / Custom.
    - `st.data_editor` showing bands. Edits allowed. Validator runs live; gaps/overlaps show as `st.error` below the table, disabling Run.
    - Editing the tariff (or picking a different preset) updates the default values shown in the sidebar's dispatch-threshold sliders. The user can then override those defaults inside the form before submitting.
  - Results (populated after Run):
    - Three headline cards: annual savings (£), daily avg (£), payback years.
    - Multi-day overview spaghetti chart (Plotly).
    - Day selector (`st.selectbox` of dates, defaulting to the first day, with "← prev / next →" buttons beside).
    - Single-day drill-down chart (Plotly).
    - Load warnings expander at the bottom.

### 10.3 Tariff preset handling

- Presets defined as `Tariff` constants in `src/windfall_tco/tariffs.py` (Cosy, Go).
- Selecting a preset copies its bands into the editable table.
- "Custom" starts with one full-day band at a default rate.

### 10.4 Chart specifications (Plotly)

**Multi-day overview (spaghetti):**
- x-axis: time-of-day, 00:00 → 23:59 (48 slots).
- Consumption: one thin semi-transparent line per day.
- Battery net dispatch (`discharge - charge`): one thin semi-transparent line per day, different color.
- Tariff bands: shaded background rectangles coloured by rate level.
- Legend: consumption / battery dispatch / band labels.

**Single-day drill-down:**
- Same x-axis, same tariff-band shading.
- Load: single bold line.
- Battery: stacked area/bars — charge above zero, discharge below zero.
- Grid import: secondary line.
- Secondary y-axis: battery SoC (%).

### 10.5 Session state

- Uploaded CSV parse result cached in `st.session_state` (re-parsing on every rerun is wasteful).
- `SimResult` cached via `@st.cache_data` keyed on all sim inputs.

## 11. Testing Strategy

### 11.1 Coverage

- Target 90% line coverage on `src/windfall_tco/` (especially `simulation/`).
- Streamlit app is not covered — behavior-tested manually.

### 11.2 Test types

- **Unit tests** per module (`tests/test_data_models.py`, `tests/simulation/test_step.py`, `tests/economics/test_cost.py`, etc.).
- **Golden-value tests** for `simulation/run.py` — scenarios listed in §7.5.
- **Property-based tests** (hypothesis) on `step()` for invariants:
  - `grid_import_kwh ≥ 0`
  - `battery_charge_kwh ≥ 0`, `battery_discharge_kwh ≥ 0`
  - `0 ≤ new_soc ≤ spec.usable_capacity_kwh`
  - At most one of `battery_charge_kwh > 0` / `battery_discharge_kwh > 0` is true per step.
  - **Energy conservation (load satisfaction):** `load_kwh == battery_discharge_kwh + grid_for_load_kwh` holds in every branch. This is the "x = y + z" invariant: home energy use = battery-supplied energy + grid-supplied energy-for-load.
  - Per-branch energy conservation:
    - Discharge branch: `grid_import_kwh == load_kwh - battery_discharge_kwh` and `battery_charge_kwh == 0`.
    - Charge branch: `grid_import_kwh == load_kwh + battery_charge_kwh / efficiency` and `battery_discharge_kwh == 0`.
    - Idle branch: `grid_import_kwh == load_kwh` and both battery flows are zero.
  - SoC delta matches flow: `new_soc - prior_soc == battery_charge_kwh - battery_discharge_kwh` (within float tolerance).
- **Parser tests** using a small committed fixture Octopus CSV in `tests/data_loading/fixtures/`. Include: a normal day, a DST-spring day, a DST-autumn day, a partial day, an all-zero day.

### 11.3 Test runner

- `pytest` with `pytest-cov` for coverage, `hypothesis` for property tests.
- `pyproject.toml` configures pytest to discover under `tests/` and treat `src/` as the package root.

## 12. Decisions Log (quick reference)

| Decision | Value | Notes |
|---|---|---|
| Scope | Savings + simple payback (option B) | No full TCO; no degradation |
| Solar | Not in scope | Pure grid arbitrage |
| Tariff shape | Static ToU, extensible to Agile | e.g. Octopus Cosy |
| Octopus CSV | Consumption data only | Cost / standing charge columns ignored |
| Dispatch strategy | Price-threshold rules | Extensible to Agile with zero logic change |
| Load matching | Match load up to 800 W, no export | |
| Sim horizon | Verbatim over uploaded period, ×365/N annualization | |
| Manual entry | 24-row watts-per-hour editor → 48 slots | Option B+ii |
| Capacity default | 2.5 kWh | |
| Charge/discharge power | 800 W / 800 W | Symmetric |
| Round-trip efficiency | 90%, charge-side | |
| Initial SoC | 50% | |
| DST handling | Strict — skip 46/50-slot days with warning | |
| Missing-slot days | Skip with warning | |
| Outputs | Headline summary + multi-day spaghetti + day drill-down | Plotly |
| Battery cost input | Single £ number | Simple payback |
| Architecture | Functional core, imperative shell (Approach 1) | |
| `data_models/` | Collapsed to single file | |
| Validation | Pydantic (not mypy-strict) | |
| Charts | Plotly | |
| Pandas | OK in `simulation/` for readability | |
| Streamlit pattern | Form-gated with submit button | |
| Tariff editor | Preset dropdown + editable table | Presets in `tariffs.py` |
| Day selector | `st.selectbox` + prev/next buttons | |
| Overview chart | Spaghetti (all days on 24h x-axis) | |
| Unit convention | Pence internal, £ display-only | |
| Payback "never" | Return `None`, render "Never (no savings)" | |
| Test coverage target | 90% on `src/windfall_tco/` | |
| Property tests | Hypothesis on `step()` invariants | |

## 13. Next Steps

1. **User review of this spec.** Flag anything that needs to change.
2. **Git init + commit** the spec (project directory is not yet a git repo).
3. **Invoke `writing-plans` skill** to produce the step-by-step implementation plan.
4. **Implement** — functional core first (`data_models`, `simulation`, `economics`), then `data_loading`, finally `streamlit_app`.
