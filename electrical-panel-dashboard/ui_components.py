"""
ui_components.py — Reusable Streamlit and Plotly widget builders.

Every function in this module renders exactly one visual element (or returns
a Plotly Figure) and has no electrical-engineering logic of its own.  Keeping
rendering separate from calculation logic means each component can be updated,
themed, or swapped independently.
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import config


# ---------------------------------------------------------------------------
# Color helper
# ---------------------------------------------------------------------------

def status_color(severity: str) -> str:
    """
    Map a severity string to a CSS hex color.

    Args:
        severity: "OK", "WARNING", "FAULT", or anything else.

    Returns:
        Hex color string.
    """
    return {
        "OK":      "#2ecc71",   # green
        "WARNING": "#f39c12",   # amber
        "FAULT":   "#e74c3c",   # red
    }.get(severity, "#95a5a6")  # grey for unknown


# ---------------------------------------------------------------------------
# Metric card
# ---------------------------------------------------------------------------

def metric_card(
    label: str,
    value: str,
    unit: str,
    status: str = "OK",
    delta: str | None = None,
) -> None:
    """
    Render a styled metric card with a colored left-border status indicator.

    Args:
        label:  Short descriptor shown in small caps above the value.
        value:  Formatted numeric value string (e.g. "149.7").
        unit:   Unit label shown smaller to the right of value (e.g. "kW").
        status: "OK", "WARNING", or "FAULT" — controls border color.
        delta:  Optional secondary line (e.g. "+2.3 % from nominal").
    """
    color = status_color(status)
    delta_html = (
        f'<p style="margin:4px 0 0; font-size:12px; color:#8892a4;">{delta}</p>'
        if delta else ""
    )
    st.markdown(
        f"""
        <div style="
            border-left: 4px solid {color};
            background: #1e2433;
            border-radius: 6px;
            padding: 12px 16px;
            margin: 4px 0;
        ">
            <p style="margin:0; font-size:11px; color:#8892a4;
                      text-transform:uppercase; letter-spacing:1px;">{label}</p>
            <p style="margin:4px 0 0; font-size:26px; font-weight:700; color:#e8eaf0;">
                {value}&nbsp;<span style="font-size:14px; color:#8892a4;">{unit}</span>
            </p>
            {delta_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Phase gauge
# ---------------------------------------------------------------------------

def phase_gauge(
    phase_label: str,
    V: float,
    I: float,
    pf: float,
    status: str = "OK",
    V_nominal: float = config.V_LINE_TO_NEUTRAL,
) -> go.Figure:
    """
    Return a Plotly gauge Indicator for a single phase voltage.

    The gauge arc has three colored zones:
      Red    [220, 235.45] — fault region (<85 % of 277 V nominal)
      Amber  [235.45, 249.3] — warning region (<90 % of 277 V)
      Green  [249.3, 320] — normal operating region

    Args:
        phase_label: e.g. "Phase A"
        V:           Measured voltage in volts.
        I:           Measured current in amps (shown in title).
        pf:          Measured power factor (shown in title).
        status:      "OK", "WARNING", or "FAULT" (needle color).
        V_nominal:   Nominal voltage (default 277 V).

    Returns:
        plotly.graph_objects.Figure (caller must call st.plotly_chart).
    """
    fault_v = V_nominal * 0.85
    warn_v  = V_nominal * 0.90

    needle_color = status_color(status)

    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=V,
        delta={
            "reference": V_nominal,
            "valueformat": ".1f",
            "increasing": {"color": "#2ecc71"},
            "decreasing": {"color": "#e74c3c"},
        },
        number={"suffix": " V", "font": {"size": 22, "color": "#e8eaf0"}},
        title={
            "text": (
                f"<b>{phase_label}</b><br>"
                f"<span style='font-size:12px;color:#8892a4'>"
                f"I = {I:.1f} A &nbsp;|&nbsp; PF = {pf:.3f}</span>"
            ),
            "font": {"size": 15, "color": "#e8eaf0"},
        },
        gauge={
            "axis": {
                "range": [220, 320],
                "tickwidth": 1,
                "tickcolor": "#8892a4",
                "tickfont": {"color": "#8892a4", "size": 10},
            },
            "bar": {"color": needle_color, "thickness": 0.25},
            "bgcolor": "rgba(0,0,0,0)",
            "borderwidth": 0,
            "steps": [
                {"range": [220, fault_v], "color": "rgba(231,76,60,0.25)"},
                {"range": [fault_v, warn_v], "color": "rgba(243,156,18,0.25)"},
                {"range": [warn_v, 320], "color": "rgba(46,204,113,0.15)"},
            ],
            "threshold": {
                "line": {"color": "#e74c3c", "width": 2},
                "thickness": 0.75,
                "value": fault_v,
            },
        },
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin={"t": 60, "b": 20, "l": 20, "r": 20},
        height=220,
    )
    return fig


# ---------------------------------------------------------------------------
# Trend chart
# ---------------------------------------------------------------------------

def trend_chart(
    df: pd.DataFrame,
    y_cols: list[str],
    title: str,
    y_label: str,
    colors: list[str],
    warning_value: float | None = None,
    fault_value: float | None = None,
) -> go.Figure:
    """
    Return a Plotly multi-trace line chart for trend monitoring.

    Args:
        df:            DataFrame indexed by datetime; y_cols must be columns.
        y_cols:        List of column names to plot (one trace each).
        title:         Chart title.
        y_label:       Y-axis label string.
        colors:        List of hex colors, one per y_col.
        warning_value: If provided, draw a dashed amber horizontal threshold line.
        fault_value:   If provided, draw a dashed red horizontal threshold line.

    Returns:
        plotly.graph_objects.Figure.
    """
    fig = go.Figure()
    for col, color in zip(y_cols, colors):
        if col in df.columns:
            fig.add_trace(go.Scatter(
                x=df.index,
                y=df[col],
                name=col.replace("_", " "),
                line={"color": color, "width": 1.5},
                mode="lines",
            ))

    if warning_value is not None:
        fig.add_hline(
            y=warning_value,
            line={"color": "#f39c12", "dash": "dash", "width": 1},
            annotation_text="WARNING",
            annotation_font_color="#f39c12",
            annotation_font_size=10,
        )
    if fault_value is not None:
        fig.add_hline(
            y=fault_value,
            line={"color": "#e74c3c", "dash": "dash", "width": 1},
            annotation_text="FAULT",
            annotation_font_color="#e74c3c",
            annotation_font_size=10,
        )

    fig.update_layout(
        title={"text": title, "font": {"size": 14, "color": "#e8eaf0"}, "x": 0.01},
        xaxis={"showgrid": False, "tickfont": {"color": "#8892a4", "size": 10}},
        yaxis={
            "title": y_label,
            "titlefont": {"color": "#8892a4", "size": 11},
            "tickfont": {"color": "#8892a4", "size": 10},
            "gridcolor": "#2a3040",
        },
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(13,17,23,0.6)",
        legend={
            "orientation": "h",
            "y": -0.2,
            "font": {"color": "#8892a4", "size": 10},
        },
        margin={"t": 40, "b": 40, "l": 50, "r": 20},
        height=260,
        template=config.PLOTLY_THEME,
    )
    return fig


# ---------------------------------------------------------------------------
# Circuit load bar chart
# ---------------------------------------------------------------------------

def circuit_bar_chart(circuit_df: pd.DataFrame) -> go.Figure:
    """
    Return a horizontal bar chart of load percentage per circuit.

    Args:
        circuit_df: DataFrame with columns: circuit_name, load_pct, status.

    Returns:
        plotly.graph_objects.Figure.
    """
    colors = [status_color(s) for s in circuit_df["status"]]

    fig = go.Figure(go.Bar(
        x=circuit_df["load_pct"],
        y=circuit_df["circuit_name"],
        orientation="h",
        marker_color=colors,
        text=[f"{v:.1f}%" for v in circuit_df["load_pct"]],
        textposition="outside",
        textfont={"color": "#e8eaf0", "size": 11},
        cliponaxis=False,
    ))

    # Rated capacity reference line
    fig.add_vline(
        x=100,
        line={"color": "#ffffff", "dash": "dash", "width": 1},
        annotation_text="Rated",
        annotation_font_color="#ffffff",
        annotation_font_size=10,
    )
    # Warning threshold reference line
    fig.add_vline(
        x=110,
        line={"color": "#f39c12", "dash": "dash", "width": 1},
        annotation_text="Warning",
        annotation_font_color="#f39c12",
        annotation_font_size=10,
    )

    fig.update_layout(
        title={"text": "Circuit Load Percentage", "font": {"size": 14, "color": "#e8eaf0"}, "x": 0.01},
        xaxis={
            "title": "Load (%)",
            "range": [0, max(150, circuit_df["load_pct"].max() * 1.2) if not circuit_df.empty else 150],
            "tickfont": {"color": "#8892a4", "size": 10},
            "titlefont": {"color": "#8892a4"},
            "gridcolor": "#2a3040",
        },
        yaxis={"tickfont": {"color": "#e8eaf0", "size": 11}},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(13,17,23,0.6)",
        margin={"t": 40, "b": 40, "l": 110, "r": 60},
        height=320,
        template=config.PLOTLY_THEME,
    )
    return fig


# ---------------------------------------------------------------------------
# Fault log table
# ---------------------------------------------------------------------------

def fault_log_table(df: pd.DataFrame) -> None:
    """
    Render the fault log DataFrame with severity-based row coloring.

    FAULT rows are highlighted red; WARNING rows amber.

    Args:
        df: DataFrame from logger.load_recent(), columns matching CSV_COLUMNS.
    """
    if df.empty:
        st.info("No fault events recorded yet.")
        return

    display_cols = ["timestamp", "circuit", "parameter", "value", "unit", "severity", "message"]
    display_df = df[[c for c in display_cols if c in df.columns]]

    def _row_style(row: pd.Series) -> list[str]:
        if row.get("severity") == "FAULT":
            return ["background-color: #3d1a1a; color: #ff6b6b"] * len(row)
        if row.get("severity") == "WARNING":
            return ["background-color: #3d2e0a; color: #ffa500"] * len(row)
        return [""] * len(row)

    styled = display_df.style.apply(_row_style, axis=1)
    st.dataframe(styled, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Sidebar controls
# ---------------------------------------------------------------------------

def sidebar_controls() -> dict:
    """
    Render all sidebar controls and return the current user-selected settings.

    Returns:
        dict with keys:
            refresh_interval   (int, seconds)
            pause_simulation   (bool)
            history_window     (int, readings)
            clear_log          (bool, True if button was clicked this run)
            thresholds         (dict matching config.THRESHOLDS structure)
                voltage:   {warn_pct, fault_pct}  — fractional multipliers
                current:   {warn_pct, fault_pct}  — multipliers of rated I
                power_factor: {warn, fault}         — absolute PF values
    """
    st.sidebar.title("⚡ Panel Controls")
    st.sidebar.caption("⚠️ **SIMULATED DATA** — not from real sensors or hardware.")
    st.sidebar.divider()

    st.sidebar.subheader("Simulation")
    refresh_interval = st.sidebar.slider(
        "Refresh Interval (s)", min_value=1, max_value=10,
        value=config.REFRESH_INTERVAL_DEFAULT, step=1,
    )
    pause_simulation = st.sidebar.checkbox("Pause Simulation", value=False)
    history_window   = st.sidebar.slider(
        "Trend History (readings)", min_value=10, max_value=120,
        value=config.HISTORY_WINDOW, step=5,
    )

    st.sidebar.divider()
    st.sidebar.subheader("Voltage Thresholds")
    voltage_warn_pct  = st.sidebar.slider(
        "Warning Threshold (%)", min_value=-20, max_value=-5, value=-10, step=1,
    )
    voltage_fault_pct = st.sidebar.slider(
        "Fault Threshold (%)", min_value=-25, max_value=-11, value=-15, step=1,
    )

    st.sidebar.divider()
    st.sidebar.subheader("Current Thresholds (% of rated)")
    current_warn_pct  = st.sidebar.slider(
        "Warning (%)", min_value=100, max_value=120, value=110, step=1,
    )
    current_fault_pct = st.sidebar.slider(
        "Fault (%)", min_value=115, max_value=150, value=125, step=1,
    )

    st.sidebar.divider()
    st.sidebar.subheader("Power Factor Thresholds")
    pf_warn  = st.sidebar.slider(
        "Warning Threshold", min_value=0.70, max_value=0.95, value=0.85, step=0.01,
    )
    pf_fault = st.sidebar.slider(
        "Fault Threshold", min_value=0.60, max_value=0.84, value=0.75, step=0.01,
    )

    st.sidebar.divider()
    clear_log_clicked = st.sidebar.button("🗑️ Clear Fault Log", use_container_width=True)

    thresholds = {
        "voltage": {
            "warn_pct":  voltage_warn_pct  / 100.0,
            "fault_pct": voltage_fault_pct / 100.0,
        },
        "current": {
            "warn_pct":  current_warn_pct  / 100.0,
            "fault_pct": current_fault_pct / 100.0,
        },
        "power_factor": {
            "warn":  pf_warn,
            "fault": pf_fault,
        },
    }

    return {
        "refresh_interval": refresh_interval,
        "pause_simulation": pause_simulation,
        "history_window":   history_window,
        "clear_log":        clear_log_clicked,
        "thresholds":       thresholds,
    }
