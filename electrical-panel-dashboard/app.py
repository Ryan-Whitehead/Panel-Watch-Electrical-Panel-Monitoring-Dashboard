"""
app.py — Streamlit entry point for PanelWatch.

Tabs
----
0  Building Overview     — 20-panel status grid, floor map, panel selector
1  ⚡ 3-Phase Bus         — existing single-panel 3-phase monitoring (unchanged)
2  🔌 Circuit Breakdown   — existing 8-circuit breakdown (unchanged)
3  🔧 Fault Simulation    — interactive fault injection + guided demo scenario
4  🛠  Maintenance Queue   — priority queue, acknowledge, notes, resolve
5  📊 Analytics           — fault trend charts from the persistent log
6  🚨 Fault Log           — existing raw fault event table (unchanged)

All orchestration only — no business logic in this file.

Auto-refresh strategy
---------------------
The dashboard uses ``@st.fragment(run_every=N)`` (Streamlit ≥ 1.37) instead of
``time.sleep() + st.rerun()``.  The fragment re-executes on a server-side timer
without blocking the websocket thread, so the browser never loses its connection
and the dark-flash between refreshes is eliminated.
"""

from datetime import datetime

import pandas as pd
import streamlit as st

import config
from building import building_summary
from building_config import (
    active_floors,
    distribute_panels,
    panel_ids_for_demo,
)
from building_simulator import BuildingSimulator
from calculations import (
    accumulate_energy_tick,
    apparent_power,
    load_percentage,
    reactive_power,
    real_power,
    sum_phase_power,
    voltage_deviation_pct,
)
from demo_mode import (
    DemoState,
    advance_step,
    build_demo_steps,
    reset_demo_state,
    set_demo_mode,
)
from fault_detector import detect_faults_batch
from logger import append_faults, clear_log, fault_counts, load_recent
from maintenance import MaintenanceQueue
from report_generator import generate_maintenance_csv
from simulator import SimulatorHistory, generate_circuit_readings, generate_phase_readings
from ui_components import (
    analytics_fault_trend,
    analytics_faults_by_category,
    analytics_faults_by_panel,
    building_summary_metrics,
    circuit_bar_chart,
    fault_log_table,
    floor_grid_chart,
    maintenance_table,
    metric_card,
    panel_status_card,
    phase_gauge,
    sidebar_controls,
    trend_chart,
)

# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="PanelWatch — Building Monitor",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
        #MainMenu  { visibility: hidden; }
        footer     { visibility: hidden; }
        header     { visibility: hidden; }
        body, .stApp { background-color: #0d1117; }
        .stTabs [data-baseweb="tab"] {
            font-size: 14px;
            padding: 6px 16px;
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
# Sidebar — rendered once per page load / user interaction (outside fragment)
# ---------------------------------------------------------------------------

settings = sidebar_controls()

if settings["clear_log"]:
    clear_log()
    st.sidebar.success("Fault log cleared.")

# ---------------------------------------------------------------------------
# Session state initialisation (first run only)
# ---------------------------------------------------------------------------

# ── Single-panel state (existing) ──────────────────────────────────────────
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
if "last_tick_time" not in st.session_state:
    st.session_state.last_tick_time = None

# ── Building-wide state (new) ───────────────────────────────────────────────
if "building_sim" not in st.session_state:
    st.session_state.building_sim = BuildingSimulator()
if "maint_queue" not in st.session_state:
    st.session_state.maint_queue = MaintenanceQueue()
if "selected_panel" not in st.session_state:
    st.session_state.selected_panel = "P-01"
if "demo_state" not in st.session_state:
    st.session_state.demo_state = DemoState()
if "active_num_floors" not in st.session_state:
    st.session_state.active_num_floors = settings["num_floors"]

# ---------------------------------------------------------------------------
# Floor configuration change detection (Apply-button gated)
# ---------------------------------------------------------------------------

if settings["apply_floors"]:
    _requested_floors = settings["pending_num_floors"]
    _new_panels = distribute_panels(config.BUILDING_PANELS, _requested_floors)
    st.session_state.building_sim  = BuildingSimulator(_new_panels)
    st.session_state.maint_queue   = MaintenanceQueue()
    _new_demo_pid = panel_ids_for_demo(_new_panels)
    st.session_state.demo_state    = DemoState(
        demo_mode_active=st.session_state.demo_state.demo_mode_active,
        demo_panel_id=_new_demo_pid,
    )
    if st.session_state.selected_panel not in st.session_state.building_sim.registry:
        st.session_state.selected_panel = _new_demo_pid
    st.session_state.active_num_floors = _requested_floors
    st.success(
        f"🏢 Building reconfigured to **{_requested_floors} floor(s)**. "
        "Simulation and maintenance queue have been reset. "
        "Persistent fault log is preserved."
    )

_num_floors = st.session_state.active_num_floors

# ---------------------------------------------------------------------------
# Page header
# ---------------------------------------------------------------------------

st.title("⚡ PanelWatch — Building Electrical Monitoring")
st.caption(
    f"📍 Simulated Building · {_num_floors} Floor(s) · "
    f"{len(config.BUILDING_PANELS)} Panels · 277/480 V 3Φ | 60 Hz  "
    "| ⚠️ **SIMULATED DATA** — not from real sensors or hardware"
)

# ---------------------------------------------------------------------------
# Dashboard fragment — ticks on a server-side timer without blocking the
# websocket.  This replaces time.sleep() + st.rerun() and eliminates the
# dark flash between refreshes.
# ---------------------------------------------------------------------------

@st.fragment(run_every=settings["refresh_interval"])
def _dashboard() -> None:  # noqa: C901
    import time

    # ── Single-panel data generation ───────────────────────────────────────
    if not settings["pause_simulation"]:
        _now = datetime.now()
        phase_reading    = generate_phase_readings(_now)
        circuit_readings = generate_circuit_readings(_now)
        st.session_state.latest_phase    = phase_reading
        st.session_state.latest_circuits = circuit_readings
    else:
        st.warning("⏸ Simulation paused — displaying last recorded readings.")
        phase_reading    = st.session_state.latest_phase
        circuit_readings = st.session_state.latest_circuits

    if phase_reading is None or not circuit_readings:
        st.info("Waiting for first reading…")
        return

    # ── Single-panel calculations ───────────────────────────────────────────
    _phases = [
        ("A", "phase_A_V", "phase_A_I", "phase_A_PF"),
        ("B", "phase_B_V", "phase_B_I", "phase_B_PF"),
        ("C", "phase_C_V", "phase_C_I", "phase_C_PF"),
    ]

    phase_data: dict = {}
    for _label, _vk, _ik, _pfk in _phases:
        _V   = phase_reading[_vk]
        _I   = phase_reading[_ik]
        _pf  = phase_reading[_pfk]
        _S   = apparent_power(_V, _I)
        _P   = real_power(_V, _I, _pf)
        _Q   = reactive_power(_P, _S)
        _dev = voltage_deviation_pct(_V, config.V_LINE_TO_NEUTRAL)
        phase_data[_label] = {"V": _V, "I": _I, "pf": _pf, "S": _S, "P": _P, "Q": _Q, "dev": _dev}

    bus_totals = sum_phase_power([
        (phase_data["A"]["V"], phase_data["A"]["I"], phase_data["A"]["pf"]),
        (phase_data["B"]["V"], phase_data["B"]["I"], phase_data["B"]["pf"]),
        (phase_data["C"]["V"], phase_data["C"]["I"], phase_data["C"]["pf"]),
    ])
    total_P_W   = bus_totals["P_total"]
    total_S_VA  = bus_totals["S_total"]
    agg_pf      = bus_totals["PF_agg"]

    st.session_state.energy_kwh, st.session_state.last_tick_time = (
        accumulate_energy_tick(
            energy_kwh_current=st.session_state.energy_kwh,
            total_P_W=total_P_W,
            paused=settings["pause_simulation"],
            last_tick_time=st.session_state.last_tick_time,
            current_tick_time=time.monotonic(),
        )
    )

    for _cr in circuit_readings:
        _cr["load_pct"] = load_percentage(_cr["current_A"], _cr["rated_current_A"])

    # ── Single-panel fault detection ────────────────────────────────────────
    _all_readings = [phase_reading] + circuit_readings
    _new_faults   = detect_faults_batch(_all_readings, settings["thresholds"], config.CIRCUITS)

    if _new_faults and not settings["pause_simulation"]:
        append_faults(_new_faults)

    def _worst_status(name: str) -> str:
        severities = [fe.severity for fe in _new_faults if fe.circuit == name]
        if "FAULT"   in severities:
            return "FAULT"
        if "WARNING" in severities:
            return "WARNING"
        return "OK"

    phase_status   = {p: _worst_status(f"Phase-{p}") for p in "ABC"}
    circuit_status = {cr["circuit_name"]: _worst_status(cr["circuit_name"]) for cr in circuit_readings}

    # ── Building-wide simulation step ───────────────────────────────────────
    if not settings["pause_simulation"]:
        _demo_mode_active = st.session_state.demo_state.demo_mode_active
        building_faults = st.session_state.building_sim.step(
            paused=False,
            thresholds=settings["thresholds"],
            demo_mode=_demo_mode_active,
        )
        if building_faults:
            append_faults(building_faults)
        st.session_state.maint_queue.update_from_fault_events(
            building_faults,
            st.session_state.building_sim.registry,
        )

    # ── Tab layout ──────────────────────────────────────────────────────────
    tab_overview, tab_bus, tab_circuits, tab_fault_sim, tab_maint, tab_analytics, tab_log = st.tabs([
        "🏢 Building Overview",
        "⚡ 3-Phase Bus",
        "🔌 Circuit Breakdown",
        "🔧 Fault Simulation",
        "🛠️ Maintenance Queue",
        "📊 Analytics",
        "🚨 Fault Log",
    ])

    # ── Tab 0 — Building Overview ───────────────────────────────────────────
    with tab_overview:
        bsim = st.session_state.building_sim
        summaries = bsim.panel_summaries()
        bsummary  = building_summary(bsim.registry)

        building_summary_metrics(bsummary)
        st.divider()

        st.plotly_chart(floor_grid_chart(summaries), use_container_width=True)
        st.divider()

        st.subheader("Panel List")
        search_term = st.text_input("Search panels (ID or location):", value="", key="panel_search")
        _floor_options = active_floors(
            [{"floor": ps.definition.floor} for ps in bsim.registry.values()]
        )
        floor_filter = st.selectbox(
            "Filter by floor:", ["All"] + [str(f) for f in _floor_options], key="floor_filter"
        )
        status_filter = st.selectbox(
            "Filter by status:", ["All", "NORMAL", "WARNING", "FAULT"], key="status_filter"
        )

        filtered = summaries
        if search_term:
            _lower = search_term.lower()
            filtered = [
                r for r in filtered
                if _lower in r["panel_id"].lower() or _lower in r["location"].lower()
            ]
        if floor_filter != "All":
            filtered = [r for r in filtered if r["floor"] == int(floor_filter)]
        if status_filter != "All":
            filtered = [r for r in filtered if r["status"] == status_filter]

        st.caption(f"Showing {len(filtered)} of {len(summaries)} panels")

        cols_per_row = 4
        for row_start in range(0, len(filtered), cols_per_row):
            row_cols = st.columns(cols_per_row)
            for col, row in zip(row_cols, filtered[row_start:row_start + cols_per_row]):
                with col:
                    panel_status_card(
                        panel_id=row["panel_id"],
                        location=row["location"],
                        floor=row["floor"],
                        status=row["status"],
                        p_kw=row["p_total_kw"],
                        pf=row["pf_agg"],
                        energy_kwh_val=row["energy_kwh"],
                        injected=row.get("injected", False),
                    )

        st.divider()

        st.subheader("Panel Detail")
        panel_ids = [r["panel_id"] for r in summaries]
        _sel_panel = st.session_state.selected_panel
        sel_idx = panel_ids.index(_sel_panel) if _sel_panel in panel_ids else 0
        selected_id = st.selectbox("Select panel to inspect:", panel_ids, index=sel_idx, key="panel_detail_select")
        st.session_state.selected_panel = selected_id

        sel_state = bsim.registry[selected_id]
        sel_defn  = sel_state.definition
        sel_r     = sel_state.latest_reading

        if sel_r is not None:
            dc1, dc2, dc3, dc4 = st.columns(4)
            with dc1:
                metric_card("Panel", sel_defn.full_label, "", status=sel_state.status)
            with dc2:
                metric_card("Real Power", f"{sel_r.p_total_w / 1000:.1f}", "kW", status=sel_state.status)
            with dc3:
                metric_card("Agg PF", f"{sel_r.pf_agg:.3f}", "PF", status=sel_state.status)
            with dc4:
                metric_card("Energy", f"{sel_state.energy_kwh:.4f}", "kWh")

            hist = sel_state.history_as_lists()
            if len(hist["timestamps"]) >= 2:
                hist_df = pd.DataFrame(hist).set_index("timestamps")
                col_v, col_i = st.columns(2)
                with col_v:
                    fig_pv = trend_chart(
                        df=hist_df,
                        y_cols=["phase_a_v", "phase_b_v", "phase_c_v"],
                        title=f"{selected_id} — Voltage Trend",
                        y_label="Voltage (V)",
                        colors=["#4e9af1", "#2ecc71", "#f39c12"],
                        warning_value=sel_defn.v_line_to_neutral * 0.90,
                        fault_value=sel_defn.v_line_to_neutral * 0.85,
                    )
                    st.plotly_chart(fig_pv, use_container_width=True)
                with col_i:
                    fig_pi = trend_chart(
                        df=hist_df,
                        y_cols=["phase_a_i", "phase_b_i", "phase_c_i"],
                        title=f"{selected_id} — Current Trend",
                        y_label="Current (A)",
                        colors=["#4e9af1", "#2ecc71", "#f39c12"],
                        warning_value=sel_defn.phase_rated_current_a * 1.10,
                        fault_value=sel_defn.phase_rated_current_a * 1.25,
                    )
                    st.plotly_chart(fig_pi, use_container_width=True)
            else:
                st.info("Collecting panel trend data…")
        else:
            st.info("Waiting for first reading from this panel…")

    # ── Tab 1 — 3-Phase Bus ─────────────────────────────────────────────────
    with tab_bus:
        g1, g2, g3 = st.columns(3)
        for _col, _phase_label, _key in [(g1, "Phase A", "A"), (g2, "Phase B", "B"), (g3, "Phase C", "C")]:
            _pd_entry = phase_data[_key]
            _fig = phase_gauge(
                phase_label=_phase_label,
                V=_pd_entry["V"],
                I=_pd_entry["I"],
                pf=_pd_entry["pf"],
                status=phase_status[_key],
            )
            _col.plotly_chart(_fig, use_container_width=True)

        _m1, _m2, _m3, _m4 = st.columns(4)
        _worst_bus = max(
            (phase_status[p] for p in "ABC"),
            key=lambda s: {"OK": 0, "WARNING": 1, "FAULT": 2}[s],
        )
        with _m1:
            metric_card("Total Real Power", f"{total_P_W / 1000:.1f}", "kW", status=_worst_bus)
        with _m2:
            metric_card("Total Apparent Power", f"{total_S_VA / 1000:.1f}", "kVA", status=_worst_bus)
        with _m3:
            _pf_status = (
                "FAULT" if agg_pf < settings["thresholds"]["power_factor"]["fault"]
                else "WARNING" if agg_pf < settings["thresholds"]["power_factor"]["warn"]
                else "OK"
            )
            metric_card("Aggregate PF", f"{agg_pf:.3f}", "PF", status=_pf_status)
        with _m4:
            metric_card("Energy Consumed", f"{st.session_state.energy_kwh:.4f}", "kWh")

        st.divider()

        _df_phase = st.session_state.history.phase_dataframe()
        if len(_df_phase) >= 2:
            _cl, _cr = st.columns(2)
            with _cl:
                _fig_v = trend_chart(
                    df=_df_phase,
                    y_cols=["phase_A_V", "phase_B_V", "phase_C_V"],
                    title="Voltage Trend — All Phases",
                    y_label="Voltage (V)",
                    colors=["#4e9af1", "#2ecc71", "#f39c12"],
                    warning_value=config.V_LINE_TO_NEUTRAL * 0.90,
                    fault_value=config.V_LINE_TO_NEUTRAL * 0.85,
                )
                st.plotly_chart(_fig_v, use_container_width=True)
            with _cr:
                _fig_i = trend_chart(
                    df=_df_phase,
                    y_cols=["phase_A_I", "phase_B_I", "phase_C_I"],
                    title="Current Trend — All Phases",
                    y_label="Current (A)",
                    colors=["#4e9af1", "#2ecc71", "#f39c12"],
                    warning_value=config.PHASE_RATED_CURRENT_A * 1.10,
                    fault_value=config.PHASE_RATED_CURRENT_A * 1.25,
                )
                st.plotly_chart(_fig_i, use_container_width=True)

            _fig_pf = trend_chart(
                df=_df_phase,
                y_cols=["phase_A_PF", "phase_B_PF", "phase_C_PF"],
                title="Power Factor Trend — All Phases",
                y_label="Power Factor",
                colors=["#4e9af1", "#2ecc71", "#f39c12"],
                warning_value=settings["thresholds"]["power_factor"]["warn"],
                fault_value=settings["thresholds"]["power_factor"]["fault"],
            )
            st.plotly_chart(_fig_pf, use_container_width=True)
        else:
            st.info("Collecting trend data… charts appear after 2 readings.")

    # ── Tab 2 — Circuit Breakdown ───────────────────────────────────────────
    with tab_circuits:
        _circuit_summary = pd.DataFrame([
            {
                "circuit_name": _cr["circuit_name"],
                "load_pct":     _cr["load_pct"],
                "status":       circuit_status[_cr["circuit_name"]],
            }
            for _cr in circuit_readings
        ])

        st.plotly_chart(circuit_bar_chart(_circuit_summary), use_container_width=True)
        st.divider()

        st.subheader("Circuit Status")
        for _row_start in range(0, len(circuit_readings), 4):
            _cols = st.columns(4)
            for _col, _cr in zip(_cols, circuit_readings[_row_start:_row_start + 4]):
                _cname  = _cr["circuit_name"]
                _status = circuit_status[_cname]
                with _col:
                    metric_card(
                        label=_cname,
                        value=f"{_cr['current_A']:.1f}",
                        unit="A",
                        status=_status,
                        delta=f"{_cr['load_pct']:.1f}% load",
                    )

        st.divider()

        st.subheader("Circuit Current Trend")
        _circuit_names = [_cr["circuit_name"] for _cr in circuit_readings]
        _selected_circuit = st.selectbox("Select circuit:", _circuit_names, key="circuit_trend_select")
        _df_circ = st.session_state.history.circuit_dataframe(_selected_circuit)
        if len(_df_circ) >= 2:
            _rated_i = next(
                (c["rated_current_A"] for c in config.CIRCUITS if c["name"] == _selected_circuit),
                30.0,
            )
            _fig_circ = trend_chart(
                df=_df_circ,
                y_cols=["current_A"],
                title=f"{_selected_circuit} — Current Trend",
                y_label="Current (A)",
                colors=["#4e9af1"],
                warning_value=_rated_i * 1.10,
                fault_value=_rated_i * 1.25,
            )
            st.plotly_chart(_fig_circ, use_container_width=True)
        else:
            st.info("Collecting circuit trend data…")

    # ── Tab 3 — Fault Simulation ────────────────────────────────────────────
    with tab_fault_sim:
        st.subheader("🔧 Fault Simulation Control Center")
        st.info(
            "⚠️ **SIMULATED DATA** — All fault injections affect only the software simulation. "
            "This dashboard does not connect to or control real electrical equipment."
        )

        bsim_ref = st.session_state.building_sim
        _ds = st.session_state.demo_state

        st.markdown("#### 🎬 Demo Mode")
        demo_col1, demo_col2 = st.columns([2, 1])
        with demo_col1:
            new_demo_active = st.toggle(
                "Enable Demo Mode (suppresses random background faults)",
                value=_ds.demo_mode_active,
                key="demo_mode_toggle",
                help=(
                    "When ON, the 4 % random background fault probability is suppressed "
                    "so only manually injected faults appear. Normal Gaussian measurement "
                    "noise continues. All data remains SIMULATED."
                ),
            )
        if new_demo_active != _ds.demo_mode_active:
            st.session_state.demo_state = set_demo_mode(_ds, new_demo_active)
            st.rerun()

        if st.session_state.demo_state.demo_mode_active:
            st.success(
                "🎬 **Demo Mode ACTIVE** — background random faults suppressed. "
                "Only manual injections will trigger fault conditions."
            )

        with demo_col2:
            if st.button(
                "🔄 Reset Demo Environment",
                key="btn_reset_demo_env",
                help=(
                    "Clears all fault injections, resets the Maintenance Queue, "
                    "and returns the demo to Step 1. "
                    "The persistent fault_log.csv is NOT erased."
                ),
            ):
                bsim_ref.clear_all_injections()
                st.session_state.maint_queue = MaintenanceQueue()
                st.session_state.demo_state = reset_demo_state()
                st.success(
                    "Demo environment reset. Fault injections cleared, Maintenance Queue "
                    "reset to empty. Persistent fault log preserved."
                )

        st.divider()

        st.markdown("#### 🧰 Guided Maintenance Demonstration")
        st.caption(
            "A repeatable 6-step walkthrough demonstrating the full monitoring and "
            "maintenance workflow. Enable Demo Mode above for a clean, distraction-free run."
        )

        _ds = st.session_state.demo_state
        _demo_pid = _ds.demo_panel_id
        if _demo_pid not in bsim_ref.registry:
            _demo_pid = next(iter(bsim_ref.registry))
            st.session_state.demo_state = DemoState(
                step=_ds.step,
                demo_mode_active=_ds.demo_mode_active,
                demo_panel_id=_demo_pid,
            )
            _ds = st.session_state.demo_state

        _demo_defn = bsim_ref.registry[_demo_pid].definition
        _demo_label = f"Floor {_demo_defn.floor} — {_demo_defn.location}"
        _step_info = build_demo_steps(_demo_pid, _demo_label)[_ds.step]

        st.progress((_ds.step) / 5, text=_ds.progress_label)
        st.info(f"**{_step_info['label']}**\n\n{_step_info['instruction']}")
        st.caption(f"Demo target panel: **{_demo_pid}** · {_demo_label}")

        demo_btns = st.columns(3)
        with demo_btns[0]:
            btn_label = "▶ Next Step" if not _ds.is_complete else "✅ Demo Complete"
            if st.button(btn_label, key="demo_next", disabled=_ds.is_complete):
                action = _step_info["action"]
                if action == "clear_injections":
                    bsim_ref.clear_all_injections()
                elif action == "inject_overcurrent":
                    bsim_ref.inject_fault(_demo_pid, "overcurrent")
                elif action == "clear_injection":
                    bsim_ref.clear_injection(_demo_pid)
                st.session_state.demo_state = advance_step(_ds)
                st.rerun()

        with demo_btns[1]:
            if st.button("⏮ Reset to Step 1", key="demo_reset"):
                bsim_ref.clear_all_injections()
                st.session_state.demo_state = DemoState(
                    demo_mode_active=_ds.demo_mode_active,
                    demo_panel_id=_demo_pid,
                )
                st.rerun()

        st.divider()

        with st.expander("⚙️ Manual Fault Injection (Advanced)", expanded=False):
            st.caption(
                "Inject any fault scenario into any panel independently of the guided demo."
            )
            inj_col1, inj_col2, inj_col3 = st.columns(3)
            with inj_col1:
                inj_panel = st.selectbox(
                    "Target panel:",
                    [p["panel_id"] for p in config.BUILDING_PANELS],
                    key="inj_panel",
                )
            with inj_col2:
                inj_scenario = st.selectbox(
                    "Fault scenario:",
                    ["overcurrent", "undervoltage", "low_power_factor"],
                    key="inj_scenario",
                )
            with inj_col3:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("💥 Inject Fault", use_container_width=True, key="btn_inject"):
                    bsim_ref.inject_fault(inj_panel, inj_scenario)
                    st.success(
                        f"Injected **{inj_scenario}** into **{inj_panel}**. "
                        "The fault will appear on the next simulation tick."
                    )

            if st.button("🔄 Clear All Injected Faults", key="btn_clear_inject"):
                bsim_ref.clear_all_injections()
                st.success("All injected faults cleared. Panels returning to normal simulation.")

            active_injections = [
                (pid, ps.injected_scenario)
                for pid, ps in bsim_ref.registry.items()
                if ps.injected_scenario is not None
            ]
            if active_injections:
                st.markdown("**Active injections:**")
                for pid, sc in active_injections:
                    st.markdown(f"- **{pid}** → `{sc}`")
            else:
                st.info("No active fault injections.")

    # ── Tab 4 — Maintenance Queue ───────────────────────────────────────────
    with tab_maint:
        st.subheader("🛠️ Maintenance Priority Queue")
        st.caption(
            "Prioritisation is rule-based (FAULT=HIGH, WARNING=MEDIUM, Resolved=LOW). "
            "Acknowledging an alert does NOT resolve the electrical fault. "
            "This is a decision-support tool — not a certified safety assessment."
        )

        mq = st.session_state.maint_queue

        mc = mq.counts()
        mcc1, mcc2, mcc3, mcc4 = st.columns(4)
        with mcc1:
            metric_card("Total Items", str(mc["total"]), "")
        with mcc2:
            metric_card("HIGH Priority", str(mc["HIGH"]), "", status="FAULT" if mc["HIGH"] else "OK")
        with mcc3:
            metric_card("MEDIUM Priority", str(mc["MEDIUM"]), "", status="WARNING" if mc["MEDIUM"] else "OK")
        with mcc4:
            metric_card("LOW (Resolved)", str(mc["LOW"]), "")

        st.divider()

        mf1, mf2, mf3, mf4 = st.columns(4)
        with mf1:
            _mq_floor_opts = active_floors(
                [{"floor": ps.definition.floor}
                 for ps in st.session_state.building_sim.registry.values()]
            )
            mf_floor = st.selectbox(
                "Floor:", ["All"] + [str(f) for f in _mq_floor_opts], key="mf_floor"
            )
        with mf2:
            mf_panel = st.selectbox(
                "Panel:", ["All"] + [p["panel_id"] for p in config.BUILDING_PANELS], key="mf_panel"
            )
        with mf3:
            mf_severity = st.selectbox("Severity:", ["All", "FAULT", "WARNING"], key="mf_severity")
        with mf4:
            mf_cat = st.selectbox("Category:", ["All", "voltage", "current", "power_factor"], key="mf_cat")

        show_resolved = st.checkbox("Include resolved (LOW priority) items", value=True, key="mf_resolved")

        filtered_items = mq.filter_items(
            floor=int(mf_floor) if mf_floor != "All" else None,
            panel_id=mf_panel if mf_panel != "All" else None,
            severity=mf_severity if mf_severity != "All" else None,
            fault_category=mf_cat if mf_cat != "All" else None,
            include_resolved=show_resolved,
        )
        sorted_items = sorted(
            filtered_items,
            key=lambda i: ({"HIGH": 0, "MEDIUM": 1, "LOW": 2}.get(i.priority, 9), i.first_detected),
        )

        maintenance_table(sorted_items)

        st.divider()

        st.markdown("##### ✏️ Acknowledge / Add Note / Review")
        st.caption(
            "Select an item from the dropdown, optionally add a note, "
            "then click an action button. "
            "Acknowledging records who saw the alert — it does not clear the electrical fault."
        )

        all_item_ids = [i.item_id for i in mq.all_items()]
        if all_item_ids:
            ack_item_id = st.selectbox("Select item:", all_item_ids, key="ack_select")
            ack_note = st.text_input("Add note (optional):", key="ack_note",
                                     placeholder="e.g. Checked breaker — scheduling load review")
            ac1, ac2, ac3 = st.columns(3)
            with ac1:
                if st.button("✅ Acknowledge", key="btn_ack", use_container_width=True):
                    try:
                        mq.acknowledge(ack_item_id)
                        if ack_note.strip():
                            mq.add_note(ack_item_id, ack_note.strip())
                        st.success(f"Acknowledged **{ack_item_id}**. Electrical condition unchanged.")
                    except KeyError as e:
                        st.error(str(e))
            with ac2:
                if st.button("📋 Mark Reviewed", key="btn_reviewed", use_container_width=True):
                    try:
                        mq.mark_reviewed(ack_item_id)
                        if ack_note.strip():
                            mq.add_note(ack_item_id, ack_note.strip())
                        st.success(f"Marked **{ack_item_id}** as reviewed.")
                    except KeyError as e:
                        st.error(str(e))
            with ac3:
                if st.button("🗑️ Clear Resolved+Reviewed", key="btn_clear_resolved",
                             use_container_width=True):
                    removed = mq.clear_resolved()
                    st.success(f"Removed {removed} resolved+reviewed items.")
        else:
            st.info("No maintenance items yet. Faults detected during simulation will appear here.")

        st.divider()

        st.markdown("##### 📥 Export Maintenance Report")
        st.caption(
            "Generates a structured CSV report of all maintenance items — active and resolved. "
            "Includes the full disclaimer, building summary, and all 15 tracked fields per item."
        )

        _bsummary_for_report = building_summary(st.session_state.building_sim.registry)
        _report_csv = generate_maintenance_csv(
            queue=mq,
            building_summary=_bsummary_for_report,
            generated_at=datetime.now(),
        )
        _report_filename = (
            f"panelwatch_maintenance_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
        st.download_button(
            label="⬇️ Download Maintenance Report (CSV)",
            data=_report_csv,
            file_name=_report_filename,
            mime="text/csv",
            use_container_width=True,
        )

    # ── Tab 5 — Analytics ───────────────────────────────────────────────────
    with tab_analytics:
        st.subheader("📊 Maintenance Analytics")
        st.caption("Based on persistent fault log. All data is SIMULATED.")

        _fault_df = load_recent(500)

        if _fault_df.empty:
            st.info("No fault events recorded yet. Analytics will populate as faults are detected.")
        else:
            _total_events = len(_fault_df)
            _fault_count  = (_fault_df["severity"] == "FAULT").sum() if "severity" in _fault_df.columns else 0
            _warn_count   = (_fault_df["severity"] == "WARNING").sum() if "severity" in _fault_df.columns else 0

            _a1, _a2, _a3 = st.columns(3)
            with _a1:
                metric_card("Total Events", str(_total_events), "")
            with _a2:
                metric_card("FAULT Events", str(_fault_count), "", status="FAULT" if _fault_count else "OK")
            with _a3:
                metric_card("WARNING Events", str(_warn_count), "", status="WARNING" if _warn_count else "OK")

            st.divider()

            _ac1, _ac2 = st.columns(2)
            with _ac1:
                st.plotly_chart(analytics_faults_by_category(_fault_df), use_container_width=True)
            with _ac2:
                st.plotly_chart(analytics_faults_by_panel(_fault_df), use_container_width=True)

            st.plotly_chart(analytics_fault_trend(_fault_df), use_container_width=True)

            st.divider()
            st.markdown("**Export fault log as CSV:**")
            _csv_data = _fault_df.to_csv(index=False)
            st.download_button(
                label="⬇️ Download fault_log.csv",
                data=_csv_data,
                file_name="panelwatch_fault_log.csv",
                mime="text/csv",
            )

    # ── Tab 6 — Fault Log ───────────────────────────────────────────────────
    with tab_log:
        _counts = fault_counts()
        _fc1, _fc2, _fc3 = st.columns(3)
        with _fc1:
            metric_card("Total Events (all time)", str(_counts["total"]), "events")
        with _fc2:
            metric_card("FAULT Events", str(_counts["FAULT"]), "", status="FAULT" if _counts["FAULT"] else "OK")
        with _fc3:
            metric_card("WARNING Events", str(_counts["WARNING"]), "", status="WARNING" if _counts["WARNING"] else "OK")

        st.divider()
        fault_log_table(load_recent(100))
        st.caption(f"Fault log persisted to: `{config.FAULT_LOG_PATH}`")

    # ── History append (inside fragment — runs every tick) ──────────────────
    if not settings["pause_simulation"]:
        st.session_state.history.append(phase_reading, circuit_readings)

    st.session_state.run_count += 1


# ---------------------------------------------------------------------------
# Invoke the fragment — Streamlit schedules it to re-execute every
# settings["refresh_interval"] seconds without a full page reload.
# ---------------------------------------------------------------------------

_dashboard()
