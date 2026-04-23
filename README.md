# Windfall Battery TCO Calculator

A personal Python tool with a Streamlit UI that answers:

> *If I install a 2.5 kWh / 800 W home battery on a static time-of-use electricity tariff, how much would I save over a year, and how long is the payback period?*

Pure grid arbitrage, UK/Octopus context, static time-of-use tariffs (Cosy, Go, or custom).

## Setup

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

This creates `.venv/` and installs all runtime + dev dependencies.

## Run tests

```bash
uv run pytest
```

With coverage:

```bash
uv run pytest --cov
```

## Lint

```bash
uv run ruff check src tests
```

## Run the app

```bash
uv run streamlit run app/streamlit_app.py
```

See `docs/superpowers/specs/2026-04-22-home-battery-tco-design.md` for the full design spec.
