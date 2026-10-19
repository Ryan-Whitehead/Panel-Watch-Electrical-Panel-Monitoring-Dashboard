"""
app.py — Streamlit entry point for the Electrical Panel Monitoring Dashboard.

This file contains no business logic.  It orchestrates calls to:
    config          — constants and circuit definitions
    simulator       — generate_phase_readings, generate_circuit_readings, SimulatorHistory
    calculations    — EE formula functions
    fault_detector  — detect_faults_batch
    logger          — append_faults, load_recent, clear_log, fault_counts
    ui_components   — all Streamlit/Plotly widget builders
"""

import time
from datetime import datetime

import pandas as pd
import streamlit as st

import config
from calculations import (
    apparent_power,
    energy_kwh,
    load_percentage,
    reactive_power,
    real_power,
    three_phase_power,
    voltage_deviation_pct,
)
from fault_detector import detect_faults_batch
from logger import append_faults, clear_log, fault_counts, load_recent
from simulator import SimulatorHistory, generate_circuit_readings, generate_phase_readings
from ui_components import (
    circuit_bar_chart,
    fault_log_table,
    metric_card,
    phase_gauge,
    sidebar_controls,
    status_color,
    trend_chart,
)

# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Electrical Panel Monitor",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Global CSS — dark engineering theme
st.markdown(
    """
    <style>
        #MainMenu  { visibility: hidden; }
        footer     { visibility: hidden; }
        header     { visibility: hidden; }
        body, .stApp { background-color: #0d1117; }
        .stTabs [data-baseweb="tab"] {
            font-size: 15px;
            padding: 8px 20px;
            color: #8892a4;
        }
        .stTabs [aria-selected="true"] {
            border-bottom: 2px solid #3b82f6 !important;
            color: #e8eaf0 !important;
        }
        .block-container { padding-top: 1rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

settings = sidebar_controls()

if settings["clear_log"]:
    clear_log()
    st.sidebar.success("Fault log cleared.")

# ---------------------------------------------------------------------------
# Session state initialisation (first run only)
# ---------------------------------------------------------------------------

if "history" not in st.session_state:
    st.session_state.history = SimulatorHistory(maxlen=settings["history_window"])
if "energy_kwh" not in st.session_state:
    st.session_state.energy_kwh = 0.0
if "run_count" not in st.session_state:
    st.session_state.run_count = 0
if "latest_phase" not in st.session_state:
    st.session_state.latest_phase = None
if "latest_circuits" not in st.session_state:
    st.session_state.latest_circuits = []

# ---------------------------------------------------------------------------
# Page header
# ---------------------------------------------------------------------------

st.title("⚡ Electrical Panel Monitoring Dashboard")
st.caption(
    "📍 Main Distribution Panel — 277/480 V 3Φ | 60 Hz  "
    "| ⚠️ **SIMULATED DATA** — not from real sensors or hardware"
)

# ---------------------------------------------------------------------------
# Data generation
# ---------------------------------------------------------------------------

if not settings["pause_simulation"]:
    now = datetime.now()
    phase_reading    = generate_phase_readings(now)
    circuit_readings = generate_circuit_readings(now)
    st.session_state.latest_phase    = phase_reading
    st.session_state.latest_circuits = circuit_readings
else:
    st.warning("⏸ Simulation paused — displaying last recorded readings.")
    phase_reading    = st.session_state.latest_phase
    circuit_readings = st.session_state.latest_circuits

# Guard: nothing to show on first paused run
if phase_reading is None or not circuit_readings:
    st.info("Waiting for first reading…")
    time.sleep(1)
    st.rerun()

# ---------------------------------------------------------------------------
# Calculations
# ---------------------------------------------------------------------------

# Per-phase derived quantities
phases = [
    ("A", "phase_A_V", "phase_A_I", "phase_A_PF"),
    ("B", "phase_B_V", "phase_B_I", "phase_B_PF"),
    ("C", "phase_C_V", "phase_C_I", "phase_C_PF"),
]

phase_data: dict[str, dict] = {}
for label, vk, ik, pfk in phases:
    V   = phase_reading[vk]
    I   = phase_reading[ik]
    pf  = phase_reading[pfk]
    S   = apparent_power(V, I)
    P   = real_power(V, I, pf)
    Q   = reactive_power(P, S)
    dev = voltage_deviation_pct(V, config.V_LINE_TO_NEUTRAL)
    phase_data[label] = {"V": V, "I": I, "pf": pf, "S": S, "P": P, "Q": Q, "dev": dev}

# 3-phase bus totals
avg_I  = sum(phase_data[p]["I"]  for p in "ABC") / 3.0
avg_pf = sum(phase_data[p]["pf"] for p in "ABC") / 3.0
total_P_W  = three_phase_power(config.V_LINE_TO_LINE, avg_I, avg_pf)
total_S_VA = three_phase_power(config.V_LINE_TO_LINE, avg_I, 1.0)   # S = √3 V I

# Energy accumulation (only on live ticks)
if not settings["pause_simulation"]:
    st.session_state.energy_kwh += energy_kwh(total_P_W, settings["refresh_interval"])

# Per-circuit load %
for cr in circuit_readings:
    cr["load_pct"] = load_percentage(cr["current_A"], cr["rated_current_A"])

# ---------------------------------------------------------------------------
# Fault detection
# ---------------------------------------------------------------------------

all_readings = [phase_reading] + circuit_readings
new_faults   = detect_faults_batch(all_readings, settings["thresholds"], config.CIRCUITS)

if new_faults and not settings["pause_simulation"]:
    append_faults(new_faults)

# Helper: worst severity for a named circuit/phase in the current tick
def _worst_status(name: str) -> str:
    severities = [fe.severity for fe in new_faults if fe.circuit == name]
    if "FAULT"   in severities:
        return "FAULT"
    if "WARNING" in severities:
        return "WARNING"
    return "OK"

phase_status = {p: _worst_status(f"Phase-{p}") for p in "ABC"}
circuit_status = {cr["circuit_name"]: _worst_status(cr["circuit_name"]) for cr in circuit_readings}

# ---------------------------------------------------------------------------
# Tab layout
# ---------------------------------------------------------------------------

tab1, tab2, tab3 = st.tabs(["⚡ 3-Phase Bus", "🔌 Circuit Breakdown", "🚨 Fault Log"])

# ── Tab 1 — 3-Phase Bus ────────────────────────────────────────────────────
with tab1:

    # Row 1: phase gauges
    g1, g2, g3 = st.columns(3)
    for col, phase_label, key in [(g1, "Phase A", "A"), (g2, "Phase B", "B"), (g3, "Phase C", "C")]:
        pd_entry = phase_data[key]
        fig = phase_gauge(
            phase_label=phase_label,
            V=pd_entry["V"],
            I=pd_entry["I"],
            pf=pd_entry["pf"],
            status=phase_status[key],
        )
        col.plotly_chart(fig, use_container_width=True)

    # Row 2: summary metrics
    m1, m2, m3, m4 = st.columns(4)
    worst_bus = max(
        (phase_status[p] for p in "ABC"),
        key=lambda s: {"OK": 0, "WARNING": 1, "FAULT": 2}[s],
    )
    with m1:
        metric_card("Total Real Power", f"{total_P_W/1000:.1f}", "kW", status=worst_bus)
    with m2:
        metric_card("Total Apparent Power", f"{total_S_VA/1000:.1f}", "kVA", status=worst_bus)
    with m3:
        pf_status = "FAULT" if avg_pf < settings["thresholds"]["power_factor"]["fault"] \
                   else "WARNING" if avg_pf < settings["thresholds"]["power_factor"]["warn"] \
                   else "OK"
        metric_card("Avg Power Factor", f"{avg_pf:.3f}", "PF", status=pf_status)
    with m4:
        metric_card("Energy Consumed", f"{st.session_state.energy_kwh:.4f}", "kWh")

    st.divider()

    # Row 3: trend charts
    df_phase = st.session_state.history.phase_dataframe()
    if len(df_phase) >= 2:
        c_left, c_right = st.columns(2)
        with c_left:
            fig_v = trend_chart(
                df=df_phase,
                y_cols=["phase_A_V", "phase_B_V", "phase_C_V"],
                title="Voltage Trend — All Phases",
                y_label="Voltage (V)",
                colors=["#4e9af1", "#2ecc71", "#f39c12"],
                warning_value=config.V_LINE_TO_NEUTRAL * 0.90,
                fault_value=config.V_LINE_TO_NEUTRAL * 0.85,
            )
            st.plotly_chart(fig_v, use_container_width=True)
        with c_right:
            fig_i = trend_chart(
                df=df_phase,
                y_cols=["phase_A_I", "phase_B_I", "phase_C_I"],
                title="Current Trend — All Phases",
                y_label="Current (A)",
                colors=["#4e9af1", "#2ecc71", "#f39c12"],
                warning_value=config.PHASE_RATED_CURRENT_A * 1.10,
                fault_value=config.PHASE_RATED_CURRENT_A * 1.25,
            )
            st.plotly_chart(fig_i, use_container_width=True)

        # Row 4: PF trend
        fig_pf = trend_chart(
            df=df_phase,
            y_cols=["phase_A_PF", "phase_B_PF", "phase_C_PF"],
            title="Power Factor Trend — All Phases",
            y_label="Power Factor",
            colors=["#4e9af1", "#2ecc71", "#f39c12"],
            warning_value=settings["thresholds"]["power_factor"]["warn"],
            fault_value=settings["thresholds"]["power_factor"]["fault"],
        )
        st.plotly_chart(fig_pf, use_container_width=True)
    else:
        st.info("Collecting trend data… charts appear after 2 readings.")

# ── Tab 2 — Circuit Breakdown ──────────────────────────────────────────────
with tab2:

    circuit_summary = pd.DataFrame([
        {
            "circuit_name": cr["circuit_name"],
            "load_pct":     cr["load_pct"],
            "status":       circuit_status[cr["circuit_name"]],
        }
        for cr in circuit_readings
    ])

    # Bar chart
    st.plotly_chart(circuit_bar_chart(circuit_summary), use_container_width=True)

    st.divider()

    # Metric card grid (4 per row × 2 rows)
    st.subheader("Circuit Status")
    for row_start in range(0, len(circuit_readings), 4):
        cols = st.columns(4)
        for col, cr in zip(cols, circuit_readings[row_start:row_start + 4]):
            cname  = cr["circuit_name"]
            status = circuit_status[cname]
            with col:
                metric_card(
                    label=cname,
                    value=f"{cr['current_A']:.1f}",
                    unit="A",
                    status=status,
                    delta=f"{cr['load_pct']:.1f}% load",
                )

    st.divider()

    # Per-circuit trend
    st.subheader("Circuit Current Trend")
    circuit_names = [cr["circuit_name"] for cr in circuit_readings]
    selected = st.selectbox("Select circuit:", circuit_names)
    df_circ  = st.session_state.history.circuit_dataframe(selected)
    if len(df_circ) >= 2:
        # Look up rated current for this circuit
        rated_i = next(
            (c["rated_current_A"] for c in config.CIRCUITS if c["name"] == selected),
            30.0,
        )
        fig_circ = trend_chart(
            df=df_circ,
            y_cols=["current_A"],
            title=f"{selected} — Current Trend",
            y_label="Current (A)",
            colors=["#4e9af1"],
            warning_value=rated_i * 1.10,
            fault_value=rated_i * 1.25,
        )
        st.plotly_chart(fig_circ, use_container_width=True)
    else:
        st.info("Collecting circuit trend data…")

# ── Tab 3 — Fault Log ──────────────────────────────────────────────────────
with tab3:

    counts = fault_counts()
    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        metric_card("Total Events (all time)", str(counts["total"]), "events")
    with fc2:
        metric_card("FAULT Events", str(counts["FAULT"]), "", status="FAULT" if counts["FAULT"] else "OK")
    with fc3:
        metric_card("WARNING Events", str(counts["WARNING"]), "", status="WARNING" if counts["WARNING"] else "OK")

    st.divider()
    fault_log_table(load_recent(100))
    st.caption(f"Fault log persisted to: `{config.FAULT_LOG_PATH}`")

# ---------------------------------------------------------------------------
# Append to history + auto-rerun
# ---------------------------------------------------------------------------

if not settings["pause_simulation"]:
    st.session_state.history.append(phase_reading, circuit_readings)

st.session_state.run_count += 1

if not settings["pause_simulation"]:
    time.sleep(settings["refresh_interval"])
    st.rerun()
