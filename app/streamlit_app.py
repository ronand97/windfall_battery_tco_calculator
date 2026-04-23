"""Streamlit UI for the Windfall battery TCO calculator.

Thin imperative shell over the pure functional core in `windfall_tco`.
See §10 of `docs/superpowers/specs/2026-04-22-home-battery-tco-design.md`.
"""

from __future__ import annotations

from datetime import date, datetime, time

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from windfall_tco.data_loading.manual_profile import load_manual_profile
from windfall_tco.data_loading.octopus_csv import load_octopus_csv
from windfall_tco.data_models import (
    BatterySpec,
    DaySimResult,
    DispatchPolicy,
    LoadResult,
    SimResult,
    Tariff,
    TariffBand,
)
from windfall_tco.economics import savings_summary, simple_payback_years
from windfall_tco.simulation.run import run
from windfall_tco.tariffs import CUSTOM_DEFAULT, OCTOPUS_COSY, OCTOPUS_GO

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PRESET_LABELS = ["Octopus Cosy", "Octopus Go", "Custom"]
_PRESET_BY_LABEL: dict[str, Tariff] = {
    "Octopus Cosy": OCTOPUS_COSY,
    "Octopus Go": OCTOPUS_GO,
    "Custom": CUSTOM_DEFAULT,
}
_ANCHOR_DATE = date(2000, 1, 1)  # Arbitrary anchor so Plotly treats x-axis as continuous.
_MANUAL_DEFAULT_WATTS: list[float] = [
    150, 120, 100, 100, 100, 120,   # 00-06
    180, 250, 280, 220, 200, 220,   # 06-12
    240, 220, 210, 230, 380, 450,   # 12-18
    420, 380, 320, 260, 200, 170,   # 18-24
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _time_to_hour_float(t: time) -> float:
    return t.hour + t.minute / 60.0


def _time_to_anchor_dt(t: time) -> datetime:
    return datetime.combine(_ANCHOR_DATE, t)


def _parse_hhmm(s: str) -> time:
    s = s.strip()
    if s in ("24:00", "24", "2400"):
        return time(0, 0)
    parts = s.split(":")
    if len(parts) != 2:
        raise ValueError(f"Expected HH:MM, got {s!r}")
    hh, mm = int(parts[0]), int(parts[1])
    if hh == 24 and mm == 0:
        return time(0, 0)
    return time(hh, mm)


def _tariff_to_df(tariff: Tariff) -> pd.DataFrame:
    rows = []
    for i, b in enumerate(tariff.bands):
        is_last = i == len(tariff.bands) - 1
        end_str = "24:00" if is_last and b.end == time(0, 0) else b.end.strftime("%H:%M")
        rows.append(
            {
                "start": b.start.strftime("%H:%M"),
                "end": end_str,
                "rate_pence_per_kwh": float(b.rate_pence_per_kwh),
            }
        )
    return pd.DataFrame(rows, columns=["start", "end", "rate_pence_per_kwh"])


def _df_to_tariff(df: pd.DataFrame, name: str) -> Tariff:
    bands: list[TariffBand] = []
    for _, row in df.iterrows():
        start_raw = row.get("start")
        end_raw = row.get("end")
        rate_raw = row.get("rate_pence_per_kwh")
        if pd.isna(start_raw) or pd.isna(end_raw) or pd.isna(rate_raw):
            continue
        start_str = str(start_raw).strip()
        end_str = str(end_raw).strip()
        if not start_str or not end_str:
            continue
        bands.append(
            TariffBand(
                start=_parse_hhmm(start_str),
                end=_parse_hhmm(end_str),
                rate_pence_per_kwh=float(rate_raw),
            )
        )
    return Tariff(name=name, bands=bands)


def _band_rate_bounds(tariff: Tariff) -> tuple[float, float]:
    rates = [b.rate_pence_per_kwh for b in tariff.bands]
    return min(rates), max(rates)


def _rate_color(rate: float, low: float, high: float) -> str:
    """Classify a band rate into low/mid/high and return an RGBA fill colour."""
    if high <= low:
        return "rgba(120, 180, 255, 0.10)"
    span = high - low
    lo_thresh = low + span / 3.0
    hi_thresh = low + 2.0 * span / 3.0
    if rate <= lo_thresh:
        return "rgba(46, 204, 113, 0.12)"   # low — green
    if rate >= hi_thresh:
        return "rgba(231, 76, 60, 0.14)"    # high — red
    return "rgba(241, 196, 15, 0.10)"       # mid — amber


def _add_tariff_bands(fig: go.Figure, tariff: Tariff, *, secondary: bool = False) -> None:
    """Shade each tariff band as a background vrect, coloured by rate level."""
    low, high = _band_rate_bounds(tariff)
    for i, band in enumerate(tariff.bands):
        is_last = i == len(tariff.bands) - 1
        x0 = _time_to_anchor_dt(band.start)
        end_t = band.end
        if is_last and end_t == time(0, 0):
            x1 = datetime.combine(_ANCHOR_DATE, time(23, 59, 59))
        else:
            x1 = _time_to_anchor_dt(end_t)
        fig.add_vrect(
            x0=x0,
            x1=x1,
            fillcolor=_rate_color(band.rate_pence_per_kwh, low, high),
            line_width=0,
            layer="below",
            annotation_text=f"{band.rate_pence_per_kwh:.1f}p",
            annotation_position="top left",
            annotation_font_size=10,
            annotation_opacity=0.6,
        )


def _manual_watts_from_df(df: pd.DataFrame) -> list[float]:
    vals = df["avg_watts"].fillna(0.0).tolist()
    if len(vals) != 24:
        raise ValueError(f"Manual profile editor expected 24 rows, got {len(vals)}")
    return [max(0.0, float(v)) for v in vals]


def _default_manual_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "hour": [f"{h:02d}:00" for h in range(24)],
            "avg_watts": _MANUAL_DEFAULT_WATTS,
        }
    )


# ---------------------------------------------------------------------------
# Chart builders
# ---------------------------------------------------------------------------


def build_spaghetti_fig(sim_result: SimResult, tariff: Tariff) -> go.Figure:
    """Multi-day overview: all days' consumption + battery net dispatch on one 24h axis."""
    fig = go.Figure()
    _add_tariff_bands(fig, tariff)

    load_legend_shown = False
    net_legend_shown = False
    for day in sim_result.days:
        x = [_time_to_anchor_dt(s.timestamp_start) for s in day.steps]
        load_y = [s.load_kwh for s in day.steps]
        net_y = [s.battery_discharge_kwh - s.battery_charge_kwh for s in day.steps]
        fig.add_trace(
            go.Scatter(
                x=x,
                y=load_y,
                mode="lines",
                line={"width": 1, "color": "rgba(52, 152, 219, 0.35)"},
                name="Consumption",
                legendgroup="load",
                showlegend=not load_legend_shown,
                hovertemplate="%{x|%H:%M}<br>Load: %{y:.3f} kWh<extra></extra>",
            )
        )
        load_legend_shown = True
        fig.add_trace(
            go.Scatter(
                x=x,
                y=net_y,
                mode="lines",
                line={"width": 1, "color": "rgba(211, 84, 0, 0.35)"},
                name="Battery net (discharge - charge)",
                legendgroup="net",
                showlegend=not net_legend_shown,
                hovertemplate="%{x|%H:%M}<br>Net: %{y:.3f} kWh<extra></extra>",
            )
        )
        net_legend_shown = True

    fig.update_layout(
        title="Multi-day overview (all simulated days overlaid)",
        xaxis={
            "title": "Time of day",
            "tickformat": "%H:%M",
            "range": [
                _time_to_anchor_dt(time(0, 0)),
                datetime.combine(_ANCHOR_DATE, time(23, 59, 59)),
            ],
        },
        yaxis_title="kWh per half-hour",
        hovermode="x unified",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02},
        margin={"t": 60, "b": 40, "l": 60, "r": 20},
    )
    return fig


def build_day_fig(
    day_sim_result: DaySimResult,
    tariff: Tariff,
    usable_capacity_kwh: float,
) -> go.Figure:
    """Single-day drill-down: load line + battery bars + grid import + SoC secondary axis."""
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    _add_tariff_bands(fig, tariff)

    x = [_time_to_anchor_dt(s.timestamp_start) for s in day_sim_result.steps]
    load_y = [s.load_kwh for s in day_sim_result.steps]
    charge_y = [s.battery_charge_kwh for s in day_sim_result.steps]
    # Discharge shown as negative bars (energy leaving the battery to serve load).
    discharge_y = [-s.battery_discharge_kwh for s in day_sim_result.steps]
    grid_y = [s.grid_import_kwh for s in day_sim_result.steps]
    denom = usable_capacity_kwh if usable_capacity_kwh > 0 else 1.0
    soc_pct = [100.0 * s.battery_soc_kwh / denom for s in day_sim_result.steps]

    fig.add_trace(
        go.Bar(
            x=x,
            y=charge_y,
            name="Battery charge",
            marker_color="rgba(39, 174, 96, 0.7)",
            hovertemplate="%{x|%H:%M}<br>Charge: %{y:.3f} kWh<extra></extra>",
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Bar(
            x=x,
            y=discharge_y,
            name="Battery discharge",
            marker_color="rgba(211, 84, 0, 0.7)",
            hovertemplate="%{x|%H:%M}<br>Discharge: %{customdata:.3f} kWh<extra></extra>",
            customdata=[s.battery_discharge_kwh for s in day_sim_result.steps],
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=x,
            y=load_y,
            mode="lines",
            line={"width": 3, "color": "#2c3e50"},
            name="Load",
            hovertemplate="%{x|%H:%M}<br>Load: %{y:.3f} kWh<extra></extra>",
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=x,
            y=grid_y,
            mode="lines",
            line={"width": 1.5, "color": "#8e44ad", "dash": "dot"},
            name="Grid import",
            hovertemplate="%{x|%H:%M}<br>Grid: %{y:.3f} kWh<extra></extra>",
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=x,
            y=soc_pct,
            mode="lines",
            line={"width": 2, "color": "#16a085"},
            name="SoC (%)",
            hovertemplate="%{x|%H:%M}<br>SoC: %{y:.1f}%<extra></extra>",
        ),
        secondary_y=True,
    )

    fig.update_layout(
        barmode="relative",
        title=f"Single-day drill-down — {day_sim_result.date.isoformat()}",
        xaxis={
            "title": "Time of day",
            "tickformat": "%H:%M",
            "range": [
                _time_to_anchor_dt(time(0, 0)),
                datetime.combine(_ANCHOR_DATE, time(23, 59, 59)),
            ],
        },
        hovermode="x unified",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02},
        margin={"t": 60, "b": 40, "l": 60, "r": 60},
    )
    fig.update_yaxes(title_text="kWh per half-hour", secondary_y=False)
    fig.update_yaxes(title_text="SoC (%)", secondary_y=True, range=[0, 110])
    return fig


# ---------------------------------------------------------------------------
# Session state init
# ---------------------------------------------------------------------------


def _init_state() -> None:
    ss = st.session_state
    if "source_choice" not in ss:
        ss["source_choice"] = "Manual profile"
    if "manual_df" not in ss:
        ss["manual_df"] = _default_manual_df()
    if "manual_load_result" not in ss:
        ss["manual_load_result"] = load_manual_profile(_MANUAL_DEFAULT_WATTS)
    if "uploaded_load_result" not in ss:
        ss["uploaded_load_result"] = None
    if "uploaded_filename" not in ss:
        ss["uploaded_filename"] = None
    if "preset_label" not in ss:
        ss["preset_label"] = "Octopus Cosy"
    if "tariff_df" not in ss:
        ss["tariff_df"] = _tariff_to_df(OCTOPUS_COSY)
    if "current_tariff" not in ss:
        ss["current_tariff"] = OCTOPUS_COSY
    if "sim_result" not in ss:
        ss["sim_result"] = None
    if "selected_day_index" not in ss:
        ss["selected_day_index"] = 0


# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------


def main() -> None:  # noqa: C901 — UI orchestration is linear but necessarily long.
    st.set_page_config(
        page_title="Windfall Battery TCO",
        page_icon=None,
        layout="wide",
    )
    _init_state()
    ss = st.session_state

    st.title("Windfall Battery TCO Calculator")
    st.caption(
        "Savings and simple payback for a home battery on a static time-of-use tariff."
    )

    # ---- Sidebar: data source + sim form ----
    with st.sidebar:
        st.header("Consumption data")
        ss["source_choice"] = st.radio(
            "Source",
            ["Upload Octopus CSV", "Manual profile"],
            index=0 if ss["source_choice"] == "Upload Octopus CSV" else 1,
        )

        if ss["source_choice"] == "Upload Octopus CSV":
            uploaded = st.file_uploader("Octopus consumption CSV", type="csv")
            if uploaded is not None:
                fingerprint = (uploaded.name, uploaded.size)
                if ss.get("uploaded_filename") != fingerprint:
                    try:
                        data = uploaded.getvalue()
                        ss["uploaded_load_result"] = load_octopus_csv(data)
                        ss["uploaded_filename"] = fingerprint
                        ss["selected_day_index"] = 0
                    except ValueError as exc:
                        st.error(f"Failed to parse CSV: {exc}")
                        ss["uploaded_load_result"] = None
                        ss["uploaded_filename"] = None
            lr: LoadResult | None = ss["uploaded_load_result"]
            if lr is not None:
                st.success(f"Parsed {len(lr.series.days)} day(s).")
                if lr.warnings:
                    with st.expander(f"Load warnings ({len(lr.warnings)})", expanded=False):
                        for w in lr.warnings:
                            st.write(f"- {w}")
        else:
            st.caption("Enter average watts per hour (24 rows).")
            edited = st.data_editor(
                ss["manual_df"],
                key="manual_editor",
                num_rows="fixed",
                hide_index=True,
                column_config={
                    "hour": st.column_config.TextColumn("Hour", disabled=True),
                    "avg_watts": st.column_config.NumberColumn(
                        "avg watts", min_value=0.0, step=10.0, format="%.0f"
                    ),
                },
                use_container_width=True,
            )
            ss["manual_df"] = edited
            try:
                watts = _manual_watts_from_df(edited)
                ss["manual_load_result"] = load_manual_profile(watts)
            except (ValueError, KeyError) as exc:
                st.error(f"Manual profile error: {exc}")

        st.divider()

        # Thresholds recompute each render from the current tariff because users
        # routinely edit bands mid-session and stale defaults would mislead.
        current_tariff: Tariff = ss["current_tariff"]
        cheapest, most_expensive = _band_rate_bounds(current_tariff)
        max_slider = max(most_expensive * 1.5, most_expensive + 1.0, 1.0)

        with st.form("sim"):
            st.subheader("Battery")
            capacity = st.slider(
                "Usable capacity (kWh)", 1.0, 20.0, 2.5, step=0.1,
            )
            charge_w = st.slider(
                "Max charge power (W)", 200, 5000, 800, step=50,
            )
            discharge_w = st.slider(
                "Max discharge power (W)", 200, 5000, 800, step=50,
            )
            efficiency = st.slider(
                "Round-trip efficiency", 0.70, 1.00, 0.90, step=0.01,
            )
            initial_soc = st.slider(
                "Initial SoC (fraction)", 0.0, 1.0, 0.5, step=0.05,
            )

            st.subheader("Dispatch thresholds")
            charge_below = st.slider(
                "Charge below (p/kWh)",
                min_value=0.0,
                max_value=float(max_slider),
                value=float(cheapest),
                step=0.5,
            )
            discharge_above = st.slider(
                "Discharge above (p/kWh)",
                min_value=0.0,
                max_value=float(max_slider),
                value=float(most_expensive),
                step=0.5,
            )

            st.subheader("Payback")
            battery_cost_gbp = st.number_input(
                "Battery system cost (£)", min_value=0.0, value=2000.0, step=50.0,
            )

            submitted = st.form_submit_button("Run simulation", type="primary")

    # ---- Main: tariff editor ----
    st.subheader("Tariff")
    col_preset, _ = st.columns([1, 3])
    with col_preset:
        new_preset = st.selectbox(
            "Tariff preset",
            PRESET_LABELS,
            index=PRESET_LABELS.index(ss["preset_label"]),
        )
    if new_preset != ss["preset_label"]:
        ss["preset_label"] = new_preset
        ss["tariff_df"] = _tariff_to_df(_PRESET_BY_LABEL[new_preset])

    tariff_df_edited = st.data_editor(
        ss["tariff_df"],
        key="tariff_editor",
        num_rows="dynamic",
        hide_index=True,
        column_config={
            "start": st.column_config.TextColumn("start (HH:MM)"),
            "end": st.column_config.TextColumn("end (HH:MM, use 24:00 for end-of-day)"),
            "rate_pence_per_kwh": st.column_config.NumberColumn(
                "rate (p/kWh)", min_value=0.0, step=0.5, format="%.2f"
            ),
        },
        use_container_width=True,
    )
    ss["tariff_df"] = tariff_df_edited

    tariff_error: str | None = None
    try:
        current_tariff = _df_to_tariff(tariff_df_edited, ss["preset_label"])
        ss["current_tariff"] = current_tariff
    except (ValueError, TypeError) as exc:
        tariff_error = str(exc)
        current_tariff = ss["current_tariff"]  # keep the last-good tariff in state

    if tariff_error:
        st.error(f"Tariff invalid: {tariff_error}")

    # ---- Resolve the current LoadResult ----
    active_load: LoadResult | None = (
        ss["uploaded_load_result"]
        if ss["source_choice"] == "Upload Octopus CSV"
        else ss["manual_load_result"]
    )

    # ---- Run sim on submit ----
    if submitted:
        if tariff_error is not None:
            st.warning("Fix the tariff table before running the simulation.")
        elif active_load is None or not active_load.series.days:
            st.warning("Upload a CSV or enter a manual profile first.")
        else:
            try:
                spec = BatterySpec(
                    usable_capacity_kwh=float(capacity),
                    max_charge_power_w=float(charge_w),
                    max_discharge_power_w=float(discharge_w),
                    round_trip_efficiency=float(efficiency),
                    initial_soc_fraction=float(initial_soc),
                )
                policy = DispatchPolicy(
                    charge_below_pence_per_kwh=float(charge_below),
                    discharge_above_pence_per_kwh=float(discharge_above),
                )
            except ValueError as exc:
                st.error(f"Invalid battery / policy inputs: {exc}")
            else:
                ss["sim_result"] = run(active_load.series, current_tariff, spec, policy)
                ss["sim_battery_cost_gbp"] = float(battery_cost_gbp)
                ss["sim_usable_capacity_kwh"] = float(capacity)
                ss["selected_day_index"] = 0

    # ---- Results ----
    result: SimResult | None = ss["sim_result"]
    if result is None or not result.days:
        st.info("Configure inputs in the sidebar, then click **Run simulation**.")
    else:
        summary = savings_summary(result)
        annual_savings_gbp = summary.annualized_savings_pence / 100.0
        daily_avg_gbp = summary.daily_average_savings_pence / 100.0
        payback = simple_payback_years(
            ss.get("sim_battery_cost_gbp", 2000.0),
            summary.annualized_savings_pence,
        )
        payback_str = "Never (no savings)" if payback is None else f"{payback:.1f} years"

        c1, c2, c3 = st.columns(3)
        c1.metric("Annual savings", f"£{annual_savings_gbp:,.2f}")
        c2.metric("Daily avg savings", f"£{daily_avg_gbp:,.2f}")
        c3.metric("Simple payback", payback_str)

        st.plotly_chart(
            build_spaghetti_fig(result, current_tariff),
            use_container_width=True,
        )

        # Day selector + prev/next.
        dates = [d.date for d in result.days]
        if ss["selected_day_index"] >= len(dates):
            ss["selected_day_index"] = 0

        sel_col, prev_col, next_col = st.columns([4, 1, 1])
        with sel_col:
            chosen = st.selectbox(
                "Day",
                options=list(range(len(dates))),
                index=ss["selected_day_index"],
                format_func=lambda i: dates[i].isoformat(),
            )
            if chosen != ss["selected_day_index"]:
                ss["selected_day_index"] = chosen
                st.rerun()
        with prev_col:
            if st.button(
                "← Prev",
                disabled=ss["selected_day_index"] <= 0,
                use_container_width=True,
            ):
                ss["selected_day_index"] = max(0, ss["selected_day_index"] - 1)
                st.rerun()
        with next_col:
            if st.button(
                "Next →",
                disabled=ss["selected_day_index"] >= len(dates) - 1,
                use_container_width=True,
            ):
                ss["selected_day_index"] = min(
                    len(dates) - 1, ss["selected_day_index"] + 1
                )
                st.rerun()

        day_result = result.days[ss["selected_day_index"]]
        st.plotly_chart(
            build_day_fig(
                day_result,
                current_tariff,
                usable_capacity_kwh=ss.get("sim_usable_capacity_kwh", 2.5),
            ),
            use_container_width=True,
        )

    # ---- Bottom: load warnings ----
    if active_load is not None and active_load.warnings:
        with st.expander(
            f"Load warnings ({len(active_load.warnings)})", expanded=False
        ):
            for w in active_load.warnings:
                st.write(f"- {w}")


main()
