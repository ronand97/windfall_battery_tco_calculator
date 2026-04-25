# Windfall Battery TCO Calculator

A personal Python tool with a Streamlit UI that answers:

> *Will adding a home battery save me money on my electricity bill, and how long until it pays for itself?*

It models a battery doing pure grid arbitrage (charge when electricity is cheap, discharge when expensive) on a UK static time-of-use tariff (e.g. Octopus Cosy or Go) and reports:

- **Annual savings** vs. the modelled tariff with no battery.
- **Tariff-switch savings** — how much you'd save (or lose) by switching tariff alone, before adding a battery.
- **Total savings vs. your *current* tariff** — using the actual billed costs from your Octopus CSV, so you see whether the full switch + battery beats staying put.
- **Simple payback period** in years against a battery cost you enter.

Both raw period totals (over the days you uploaded) and annualised figures (×365/N) are shown.

## How it works

Functional core, imperative shell. Pure functions on frozen pydantic data models do all the work; the Streamlit app is a thin UI layer.

```
┌──────────────────────┐    ┌────────────────────────┐    ┌──────────────────┐
│ Consumption data     │    │ Static ToU tariff      │    │ Battery + policy │
│  • Octopus CSV       │    │  • Cosy / Go / Custom  │    │  • capacity, kW  │
│  • Manual 24h        │    │  • bands, p/kWh        │    │  • thresholds    │
└──────────┬───────────┘    └───────────┬────────────┘    └─────────┬────────┘
           │                            │                           │
           └────────────┬───────────────┴───────────────┬───────────┘
                        ▼                               ▼
           ┌────────────────────────────┐     ┌──────────────────────┐
           │ simulation.run()           │     │ economics.summary()  │
           │  folds step() over every   │────▶│  derives £ figures + │
           │  half-hour slot of every   │     │  payback + 3-way     │
           │  day (48 slots/day)        │     │  comparison fields   │
           └────────────────────────────┘     └──────────┬───────────┘
                                                         ▼
                                            ┌────────────────────────┐
                                            │ Streamlit charts +     │
                                            │ summary cards          │
                                            └────────────────────────┘
```

### Dispatch model

Each half-hour slot, the battery is in one of three states based on the spot price vs. the dispatch policy thresholds:

| Branch       | Trigger                                     | Behaviour                                                    |
| ------------ | ------------------------------------------- | ------------------------------------------------------------ |
| **Discharge** | `price ≥ discharge_above`                  | Battery serves load up to its discharge power and current SoC; rest from grid. |
| **Charge**   | `price ≤ charge_below`                      | Battery charges from grid up to its charge power and headroom; round-trip efficiency loss is paid on the grid side. |
| **Idle**     | otherwise                                   | Battery does nothing; load met from grid.                    |

Battery only matches load — no export to grid. SoC is continuous across day boundaries.

## Quick start

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
# install dependencies
uv sync

# run the app
uv run streamlit run app/streamlit_app.py
```

The app opens in your browser. Upload an Octopus CSV (Account → Energy → "Export"), pick a tariff preset, set a battery capacity / cost, and click **Run simulation**.

## Inputs

### Octopus CSV upload

Standard half-hourly consumption export from the Octopus dashboard. The parser reads two columns and ignores the rest:

| Column                         | Used for                                      |
| ------------------------------ | --------------------------------------------- |
| `Consumption (kwh)`            | Per-slot energy use (the modelled load).     |
| `Estimated Cost Inc. Tax (p)`  | Your *current-tariff* cost per slot — drives the "vs current" comparison. Optional; column may be missing on older exports. |
| `Start`                        | ISO 8601 timestamp; converted to local UK wall-clock for grouping. |

Days that don't cover a clean 48-slot half-hour grid are skipped with a warning (DST transition days have 46 or 50 slots; partial-data days are usually meter outages).

### Manual profile

A 24-row table of average watts per hour. Each value is split into two equal half-hour slots. No billing data, so the "vs current" comparison is hidden — only the modelled-tariff savings are shown.

### Tariff

Pick **Octopus Cosy**, **Octopus Go**, or **Custom**, then edit the bands inline (start, end, p/kWh). Bands must cover 00:00–24:00 contiguously with no gaps or overlaps; the validator surfaces any errors below the table.

### Battery and dispatch

Sliders in the sidebar:

| Parameter             | Default | Range            |
| --------------------- | ------- | ---------------- |
| Usable capacity       | 2.5 kWh | 1–20 kWh         |
| Max charge power      | 800 W   | 200–5000 W       |
| Max discharge power   | 800 W   | 200–5000 W       |
| Round-trip efficiency | 90%     | 70–100%          |
| Initial SoC           | 50%     | 0–100%           |

Dispatch thresholds default to the cheapest and most-expensive bands of the chosen tariff and can be overridden.

## Outputs

A persistent headline row (simulated days, simple payback, annual saving vs current) sits above two tabs:

- **Annualised (365 days)** — modelled costs scaled to a full year.
- **Simulated period (N days)** — raw totals for exactly the days you uploaded.

Each tab shows three cost cards (current actual, modelled tariff no-battery, modelled tariff with battery — coloured deltas relative to current) and three savings cards (tariff switch alone, battery on the new tariff, total).

Two charts:

- **Multi-day overview (spaghetti)** — every day's consumption + battery net dispatch overlaid on a 24h x-axis, with tariff bands shaded in the background.
- **Single-day drill-down** — load line, charge/discharge bars, grid import, and SoC % on a secondary y-axis for whichever day you select.

## Project structure

```
src/windfall_tco/
  data_models.py             # frozen pydantic models for everything
  tariffs.py                 # Cosy / Go presets
  data_loading/
    octopus_csv.py           # CSV parser, day filtering, cost-column ingest
    manual_profile.py        # 24-watt → 48-slot kWh
  simulation/
    step.py                  # one-slot dispatch transition
    run.py                   # fold step() over the series
  economics/
    cost.py                  # baseline cost helper
    payback.py               # simple_payback_years
    summary.py               # SavingsSummary including 3-way comparison

app/streamlit_app.py         # the UI
tests/                       # pytest, mirrors src/ layout
```

## Development

```bash
# tests (pytest + hypothesis property tests)
uv run pytest

# tests with coverage
uv run pytest --cov

# lint
uv run ruff check src tests app
```
