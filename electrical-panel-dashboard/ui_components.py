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
    Render all dashboard controls and return the current user-selected settings.

    Controls are rendered in TWO places so they are always reachable:
      1. ``st.sidebar`` — visible on wide screens / desktop browsers.
      2. A ``st.expander`` on the main page — always accessible regardless of
         whether the Streamlit sidebar is collapsed or hidden by the browser.

    Both containers use unique widget keys (suffixed ``_sb`` / ``_ex``) so
    Streamlit does not raise a DuplicateWidgetID error.  The expander values
    take precedence: if they differ from the sidebar values, the expander wins.
    In practice, users will use one or the other, not both simultaneously.

    Floor configuration uses a *pending* pattern: the number input writes to
    ``st.session_state.pending_num_floors`` and the "Apply Configuration" button
    must be clicked before the floor change takes effect in ``app.py``.  This
    prevents an accidental nudge from silently resetting the building simulator
    and maintenance queue mid-demo.

    Returns:
        dict with keys:
            refresh_interval   (int, seconds)
            pause_simulation   (bool)
            history_window     (int, readings)
            num_floors         (int, currently **active** floor count)
            apply_floors       (bool, True only when Apply button was clicked
                                *and* pending differs from active)
            pending_num_floors (int, value shown in the number input)
            clear_log          (bool, True if button was clicked this run)
            thresholds         (dict matching config.THRESHOLDS structure)
                voltage:   {warn_pct, fault_pct}  — fractional multipliers
                current:   {warn_pct, fault_pct}  — multipliers of rated I
                power_factor: {warn, fault}         — absolute PF values
    """
    from building_config import DEFAULT_NUM_FLOORS, MAX_FLOORS, MIN_FLOORS

    _active = st.session_state.get("active_num_floors", DEFAULT_NUM_FLOORS)

    # ── Helper: render all widgets into any container ───────────────────────
    def _render(c, suffix: str) -> dict:
        """Render all controls into container *c*; suffix makes keys unique."""
        c.subheader("🏢 Building Configuration")
        pf = c.number_input(
            "Number of Floors",
            min_value=MIN_FLOORS,
            max_value=MAX_FLOORS,
            value=_active,
            step=1,
            key=f"pending_num_floors_{suffix}",
            help=(
                f"Configure floors ({MIN_FLOORS}–{MAX_FLOORS}). "
                "Panels are redistributed via round-robin. "
                "Click Apply to confirm — resets sim and maintenance queue."
            ),
        )
        fc = int(pf) != _active
        if fc:
            c.warning(
                f"⚠️ Pending: **{_active} → {int(pf)} floor(s)**\n\n"
                "Applying resets the Building Simulator and Maintenance Queue. "
                "Fault log is preserved.",
                icon=None,
            )
        af = c.button(
            "✅ Apply Configuration",
            key=f"btn_apply_floors_{suffix}",
            use_container_width=True,
            disabled=not fc,
        )

        c.divider()
        c.subheader("Simulation")
        ri = c.slider(
            "Refresh Interval (s)", min_value=1, max_value=10,
            value=config.REFRESH_INTERVAL_DEFAULT, step=1,
            key=f"refresh_{suffix}",
        )
        ps = c.checkbox("Pause Simulation", value=False, key=f"pause_{suffix}")
        hw = c.slider(
            "Trend History (readings)", min_value=10, max_value=120,
            value=config.HISTORY_WINDOW, step=5,
            key=f"history_{suffix}",
        )

        c.divider()
        c.subheader("Voltage Thresholds")
        vw = c.slider(
            "Warning (%)", min_value=-20, max_value=-5, value=-10, step=1,
            key=f"v_warn_{suffix}",
        )
        vf = c.slider(
            "Fault (%)", min_value=-25, max_value=-11, value=-15, step=1,
            key=f"v_fault_{suffix}",
        )

        c.divider()
        c.subheader("Current Thresholds (% of rated)")
        iw = c.slider(
            "Warning (%)", min_value=100, max_value=120, value=110, step=1,
            key=f"i_warn_{suffix}",
        )
        if_ = c.slider(
            "Fault (%)", min_value=115, max_value=150, value=125, step=1,
            key=f"i_fault_{suffix}",
        )

        c.divider()
        c.subheader("Power Factor Thresholds")
        pw = c.slider(
            "Warning", min_value=0.70, max_value=0.95, value=0.85, step=0.01,
            key=f"pf_warn_{suffix}",
        )
        pff = c.slider(
            "Fault", min_value=0.60, max_value=0.84, value=0.75, step=0.01,
            key=f"pf_fault_{suffix}",
        )

        c.divider()
        cl = c.button(
            "🗑️ Clear Fault Log", use_container_width=True, key=f"clear_log_{suffix}",
        )

        return {
            "pending_floors": int(pf),
            "floors_changed": fc,
            "apply_floors":   af and fc,
            "refresh":        ri,
            "pause":          ps,
            "history":        hw,
            "v_warn":         vw,
            "v_fault":        vf,
            "i_warn":         iw,
            "i_fault":        if_,
            "pf_warn":        pw,
            "pf_fault":       pff,
            "clear_log":      cl,
        }

    # ── Sidebar ─────────────────────────────────────────────────────────────
    st.sidebar.title("⚡ Panel Controls")
    st.sidebar.caption("⚠️ **SIMULATED DATA** — not from real sensors or hardware.")
    st.sidebar.divider()
    sb = _render(st.sidebar, "sb")

    # ── On-page expander (always visible) ───────────────────────────────────
    with st.expander("⚙️ Dashboard Controls", expanded=False):
        st.caption("⚠️ **SIMULATED DATA** — not from real sensors or hardware.")
        ex = _render(st, "ex")

    # ── Merge: expander takes precedence when its Apply button was clicked, ─
    # otherwise sidebar values are used (desktop users won't open the expander).
    # For boolean OR-style actions (apply, clear_log) either source can trigger.
    apply_floors  = sb["apply_floors"]  or ex["apply_floors"]
    clear_log     = sb["clear_log"]     or ex["clear_log"]
    pending       = ex["pending_floors"] if ex["apply_floors"] else sb["pending_floors"]

    # For sliders, expander wins only if it differs from default (user touched it).
    # Simplest safe merge: if expander's pause is True, honour it; same for refresh.
    pause    = sb["pause"]   or ex["pause"]
    refresh  = min(sb["refresh"],  ex["refresh"])   # use the lower (faster) if either changed
    history  = max(sb["history"],  ex["history"])   # use the larger window if either changed
    v_warn   = max(sb["v_warn"],   ex["v_warn"])    # less aggressive threshold wins
    v_fault  = max(sb["v_fault"],  ex["v_fault"])
    i_warn   = min(sb["i_warn"],   ex["i_warn"])
    i_fault  = min(sb["i_fault"],  ex["i_fault"])
    pf_warn  = max(sb["pf_warn"],  ex["pf_warn"])
    pf_fault = max(sb["pf_fault"], ex["pf_fault"])

    thresholds = {
        "voltage": {
            "warn_pct":  v_warn  / 100.0,
            "fault_pct": v_fault / 100.0,
        },
        "current": {
            "warn_pct":  i_warn  / 100.0,
            "fault_pct": i_fault / 100.0,
        },
        "power_factor": {
            "warn":  pf_warn,
            "fault": pf_fault,
        },
    }

    return {
        "refresh_interval":   refresh,
        "pause_simulation":   pause,
        "history_window":     history,
        "num_floors":         _active,
        "apply_floors":       apply_floors,
        "pending_num_floors": pending,
        "clear_log":          clear_log,
        "thresholds":         thresholds,
    }


# ===========================================================================
# Building-wide UI components
# Added for the building-wide monitoring upgrade.
# All functions below are pure renderers — no electrical logic.
# ===========================================================================

# ---------------------------------------------------------------------------
# Panel status card (building overview grid)
# ---------------------------------------------------------------------------

def panel_status_card(panel_id: str, location: str, floor: int,
                      status: str, p_kw: float, pf: float,
                      energy_kwh_val: float, injected: bool = False) -> None:
    """
    Render a compact status card for one panel in the building overview grid.

    Args:
        panel_id:       e.g. "P-07"
        location:       descriptive name
        floor:          floor number
        status:         "NORMAL", "WARNING", or "FAULT"
        p_kw:           total real power (kW)
        pf:             aggregate power factor
        energy_kwh_val: accumulated energy (kWh)
        injected:       True when an active manual fault injection is present
    """
    color = status_color(status)
    badge = (
        '<span style="font-size:10px;background:#5b2d8e;color:#e8eaf0;'
        'border-radius:3px;padding:1px 5px;margin-left:6px;">INJECTED</span>'
        if injected else ""
    )
    st.markdown(
        f"""
        <div style="border-left:4px solid {color};background:#1e2433;
                    border-radius:6px;padding:8px 12px;margin:3px 0;">
            <p style="margin:0;font-size:12px;font-weight:700;color:#e8eaf0;">
                {panel_id}{badge}
            </p>
            <p style="margin:1px 0;font-size:10px;color:#8892a4;">
                Floor {floor} · {location}
            </p>
            <p style="margin:2px 0;font-size:11px;color:{color};font-weight:600;">
                {status}
            </p>
            <p style="margin:1px 0;font-size:10px;color:#8892a4;">
                {p_kw:.1f} kW · PF {pf:.3f} · {energy_kwh_val:.3f} kWh
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Floor grid chart (Plotly scatter — floor vs. panel position)
# ---------------------------------------------------------------------------

def floor_grid_chart(panel_summaries: list) -> "go.Figure":
    """
    Return a Plotly scatter chart showing panel status by floor.

    Each panel is a circle marker; color encodes status (green/amber/red).
    X axis = position within floor; Y axis = floor number.

    Args:
        panel_summaries: list of dicts with keys panel_id, floor, location,
                         status, p_total_kw, pf_agg, injected.

    Returns:
        plotly.graph_objects.Figure
    """
    # Group by floor to assign x-positions within each floor.
    from collections import defaultdict
    floor_counts: "defaultdict[int, int]" = defaultdict(int)
    xs, ys, colors_list, texts, sizes = [], [], [], [], []

    for row in panel_summaries:
        fl = row["floor"]
        floor_counts[fl] += 1
        x = floor_counts[fl]
        xs.append(x)
        ys.append(fl)
        colors_list.append(status_color(row["status"]))
        badge = " ⚡" if row.get("injected") else ""
        texts.append(
            f"<b>{row['panel_id']}{badge}</b><br>"
            f"{row['location']}<br>"
            f"Floor {fl}<br>"
            f"Status: {row['status']}<br>"
            f"P: {row['p_total_kw']:.1f} kW | PF: {row['pf_agg']:.3f}"
        )
        sizes.append(22 if row["status"] == "FAULT" else 16)

    fig = go.Figure(go.Scatter(
        x=xs,
        y=ys,
        mode="markers+text",
        marker=dict(color=colors_list, size=sizes, line=dict(width=1, color="#2a3040")),
        text=[r["panel_id"] for r in panel_summaries],
        textposition="top center",
        textfont=dict(color="#e8eaf0", size=9),
        hovertext=texts,
        hoverinfo="text",
    ))
    fig.update_layout(
        title=dict(text="Building Panel Status by Floor", font=dict(size=14, color="#e8eaf0"), x=0.01),
        xaxis=dict(title="Panel (left to right per floor)", showgrid=False,
                   tickfont=dict(color="#8892a4", size=9), zeroline=False),
        yaxis=dict(title="Floor", tickmode="linear", tick0=1, dtick=1,
                   tickfont=dict(color="#8892a4", size=10), gridcolor="#2a3040"),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(13,17,23,0.6)",
        margin=dict(t=40, b=40, l=60, r=20),
        height=420,
        template=config.PLOTLY_THEME,
        showlegend=False,
    )
    return fig


# ---------------------------------------------------------------------------
# Maintenance priority table
# ---------------------------------------------------------------------------

def maintenance_table(items: list) -> None:
    """
    Render a styled maintenance priority table.

    HIGH rows: red background; MEDIUM rows: amber; LOW rows: muted.

    Args:
        items: list of MaintenanceItem objects (or dicts via .to_dict()).
    """
    if not items:
        st.info("No maintenance items in queue.")
        return

    import pandas as pd

    rows = [i.to_dict() if hasattr(i, "to_dict") else i for i in items]
    df = pd.DataFrame(rows)

    display_cols = [
        "panel_id", "floor", "fault_category", "severity",
        "measured_value", "unit", "priority", "workflow_status",
        "first_detected", "latest_detected", "notes",
    ]
    df = df[[c for c in display_cols if c in df.columns]]

    def _row_style(row: "pd.Series") -> list:
        p = row.get("priority", "")
        if p == "HIGH":
            return ["background-color:#3d1a1a;color:#ff6b6b"] * len(row)
        if p == "MEDIUM":
            return ["background-color:#3d2e0a;color:#ffa500"] * len(row)
        return ["background-color:#1e2433;color:#8892a4"] * len(row)

    styled = df.style.apply(_row_style, axis=1)
    st.dataframe(styled, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Building summary metric row
# ---------------------------------------------------------------------------

def building_summary_metrics(summary: dict) -> None:
    """
    Render a four-column metric row for the building overview header.

    Args:
        summary: dict with keys total, normal, warning, fault.
    """
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        metric_card("Monitored Panels", str(summary["total"]), "panels")
    with c2:
        metric_card("Normal", str(summary["normal"]), "panels", status="OK")
    with c3:
        status = "WARNING" if summary["warning"] > 0 else "OK"
        metric_card("Warning", str(summary["warning"]), "panels", status=status)
    with c4:
        status = "FAULT" if summary["fault"] > 0 else "OK"
        metric_card("Fault", str(summary["fault"]), "panels", status=status)


# ---------------------------------------------------------------------------
# Analytics charts
# ---------------------------------------------------------------------------

def analytics_faults_by_category(fault_df: "pd.DataFrame") -> "go.Figure":
    """
    Bar chart of fault event counts grouped by parameter (category).

    Args:
        fault_df: DataFrame loaded from logger.load_recent() or full log.

    Returns:
        go.Figure
    """
    if fault_df.empty:
        return go.Figure()
    counts = fault_df["parameter"].value_counts().reset_index()
    counts.columns = ["category", "count"]
    fig = go.Figure(go.Bar(
        x=counts["category"],
        y=counts["count"],
        marker_color=["#4e9af1", "#f39c12", "#2ecc71"][:len(counts)],
        text=counts["count"],
        textposition="outside",
        textfont=dict(color="#e8eaf0"),
    ))
    fig.update_layout(
        title=dict(text="Fault Events by Category (SIMULATED DATA)", font=dict(size=13, color="#e8eaf0"), x=0.01),
        xaxis=dict(tickfont=dict(color="#e8eaf0")),
        yaxis=dict(title="Count", tickfont=dict(color="#8892a4"), gridcolor="#2a3040"),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(13,17,23,0.6)",
        height=280,
        margin=dict(t=40, b=30, l=50, r=20),
        template=config.PLOTLY_THEME,
    )
    return fig


def analytics_faults_by_panel(fault_df: "pd.DataFrame") -> "go.Figure":
    """
    Horizontal bar chart of fault event counts grouped by panel (circuit prefix).

    Args:
        fault_df: DataFrame from logger.load_recent().

    Returns:
        go.Figure
    """
    if fault_df.empty:
        return go.Figure()
    # Extract panel_id from circuit field (format: "P-07/Phase-A" or legacy "Phase-A")
    fault_df = fault_df.copy()
    fault_df["panel"] = fault_df["circuit"].str.split("/").str[0]
    counts = fault_df["panel"].value_counts().reset_index()
    counts.columns = ["panel", "count"]
    counts = counts.sort_values("count", ascending=True)

    fig = go.Figure(go.Bar(
        x=counts["count"],
        y=counts["panel"],
        orientation="h",
        marker_color="#e74c3c",
        text=counts["count"],
        textposition="outside",
        textfont=dict(color="#e8eaf0"),
    ))
    fig.update_layout(
        title=dict(text="Fault Events by Panel (SIMULATED DATA)", font=dict(size=13, color="#e8eaf0"), x=0.01),
        xaxis=dict(title="Count", tickfont=dict(color="#8892a4"), gridcolor="#2a3040"),
        yaxis=dict(tickfont=dict(color="#e8eaf0")),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(13,17,23,0.6)",
        height=max(200, 30 * len(counts) + 60),
        margin=dict(t=40, b=30, l=80, r=50),
        template=config.PLOTLY_THEME,
    )
    return fig


def analytics_fault_trend(fault_df: "pd.DataFrame") -> "go.Figure":
    """
    Time-series line chart of cumulative fault events.

    Args:
        fault_df: DataFrame from logger.load_recent() with timestamp column.

    Returns:
        go.Figure
    """
    if fault_df.empty or "timestamp" not in fault_df.columns:
        return go.Figure()

    import pandas as pd

    df = fault_df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp")
    df["cumulative"] = range(1, len(df) + 1)

    fig = go.Figure(go.Scatter(
        x=df["timestamp"],
        y=df["cumulative"],
        mode="lines",
        line=dict(color="#4e9af1", width=2),
        fill="tozeroy",
        fillcolor="rgba(78,154,241,0.1)",
    ))
    fig.update_layout(
        title=dict(
            text="Cumulative Fault Events Over Time (SIMULATED DATA)",
            font=dict(size=13, color="#e8eaf0"),
            x=0.01,
        ),
        xaxis=dict(tickfont=dict(color="#8892a4", size=9), showgrid=False),
        yaxis=dict(title="Cumulative Events", tickfont=dict(color="#8892a4"), gridcolor="#2a3040"),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(13,17,23,0.6)",
        height=260,
        margin=dict(t=40, b=30, l=60, r=20),
        template=config.PLOTLY_THEME,
    )
    return fig
