# ⚡ PanelWatch — Building Electrical Panel Monitoring Dashboard

> **Portfolio Project** — built by an Electrical Engineering Technology junior as a
> demonstration of real-time electrical monitoring, fault detection, and maintenance
> workflow concepts.
>
> ⚠️ **All data is entirely simulated. This dashboard does not connect to, monitor,
> or control any real electrical equipment or sensors.**

---

## Overview

PanelWatch is a professional-grade multi-panel electrical monitoring dashboard built
with **Python 3.10+**, **Streamlit**, **Pandas**, and **Plotly**. It simulates a
20-panel, configurable-floor commercial building operating on a 277/480 V 3-phase
60 Hz system and demonstrates:

- Realistic per-panel voltage, current, power factor, and energy readings
- Real-time fault detection (overcurrent, undervoltage, low power factor)
- A prioritised maintenance queue with acknowledgement, notes, and CSV export
- An interactive fault injection and guided 6-step demo scenario
- Building-wide analytics from a persistent fault event log
- Configurable warning/fault thresholds across all three electrical parameters

---

## Architecture

```
electrical-panel-dashboard/
├── app.py                  Streamlit entry point — 7-tab orchestration only
├── calculations.py         Pure EE math (real power, reactive power, energy, etc.)
├── simulator.py            Single-panel probabilistic reading generator
├── building_simulator.py   20-panel BuildingSimulator with per-panel state
├── fault_detector.py       Stateless fault classification from readings
├── logger.py               CSV fault log — append, load, clear, count
├── maintenance.py          MaintenanceItem, MaintenanceQueue, compute_priority
├── building.py             PanelDefinition, PanelState, registry helpers
├── building_config.py      distribute_panels(), active_floors(), floor bounds
├── config.py               All constants — BUILDING_PANELS, thresholds, paths
├── demo_mode.py            DemoState, build_demo_steps(), guided demo helpers
├── report_generator.py     generate_maintenance_csv() — 18-column CSV report
├── ui_components.py        Reusable Streamlit/Plotly widget builders
├── requirements.txt
├── Dockerfile
├── ruff.toml               Linting config (E/F/I, target py310, ignore E741)
└── tests/
    ├── test_calculations.py        56 tests — EE formulas + edge cases
    ├── test_fault_detector.py      29 tests — fault classification
    ├── test_energy_accumulation.py 13 tests — energy tick accumulation
    ├── test_building.py            47 tests — PanelDefinition, PanelState, registry
    ├── test_maintenance.py         62 tests — MaintenanceQueue full lifecycle
    ├── test_demo_mode.py           38 tests — DemoState, build_demo_steps
    ├── test_report_generator.py    38 tests — CSV report generation
    └── test_building_config.py     50 tests — distribute_panels, active_floors
```

**Total: 333 tests — all passing.**

### Key design principle

All electrical calculation and fault-detection logic lives in pure Python modules
with no Streamlit imports. This means every formula can be unit-tested in isolation
without spinning up a browser, and the same logic could be reused in a CLI tool,
REST API, or a different UI framework without modification.

---

## Dashboard Tabs

| # | Tab | Purpose |
|---|-----|---------|
| 0 | 🏢 Building Overview | 20-panel status grid, floor map, search/filter, per-panel trends |
| 1 | ⚡ 3-Phase Bus | Phase gauges, voltage/current/PF trend charts, energy accumulation |
| 2 | 🔌 Circuit Breakdown | 8-circuit load bar chart, per-circuit current trends |
| 3 | 🔧 Fault Simulation | Demo Mode toggle, guided 6-step demo, manual fault injection |
| 4 | 🛠️ Maintenance Queue | Priority queue, acknowledge, notes, resolve, CSV export |
| 5 | 📊 Analytics | Fault events by category, by panel, cumulative trend over time |
| 6 | 🚨 Fault Log | Raw timestamped fault event table with severity highlighting |

---

## Setup Instructions

### Prerequisites

| Tool | Version |
|------|---------|
| Python | 3.10 or newer |
| pip | latest |

### 1 — Clone the repository

```bash
git clone https://github.com/Ryan-Whitehead/Panel-Watch-Electrical-Panel-Monitoring-Dashboard.git
cd Panel-Watch-Electrical-Panel-Monitoring-Dashboard
```

### 2 — Create and activate a virtual environment

```bash
# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate

# Windows (PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3 — Install dependencies

```bash
pip install -r electrical-panel-dashboard/requirements.txt
```

### 4 — Run the dashboard

```bash
cd electrical-panel-dashboard
streamlit run app.py
```

The dashboard opens at `http://localhost:8501` by default.

### 5 — Run the test suite

```bash
cd electrical-panel-dashboard
python -m pytest tests/ -v
```

Expected output: **333 passed** with no warnings.

### 6 — Lint

```bash
cd electrical-panel-dashboard
python -m ruff check .
```

Expected output: no errors.

### Docker (optional)

```bash
docker build -t panelwatch ./electrical-panel-dashboard
docker run -p 8501:8501 panelwatch
```

---

## Electrical Engineering Concepts

### Formulas used

| Quantity | Formula | Module |
|----------|---------|--------|
| Apparent power | S = V × I (VA) | `calculations.py` |
| Real power | P = V × I × PF (W) | `calculations.py` |
| Reactive power | Q = √(S² − P²) (VAR) | `calculations.py` |
| Energy (tick) | ΔE = P × Δt / 3 600 000 (kWh) | `calculations.py` |
| Load percentage | load% = (I_measured / I_rated) × 100 | `calculations.py` |
| Voltage deviation | dev% = (V − V_nom) / V_nom × 100 | `calculations.py` |
| Aggregate PF | PF_agg = P_total / S_total | `calculations.py` |

### Fault conditions simulated

| Condition | Default warning | Default fault |
|-----------|----------------|---------------|
| Undervoltage | < 90 % of 277 V (249.3 V) | < 85 % of 277 V (235.5 V) |
| Overcurrent | > 110 % of rated current | > 125 % of rated current |
| Low power factor | PF < 0.85 | PF < 0.75 |

All thresholds are user-configurable via the sidebar sliders at runtime.

### System assumptions

- Nominal voltage: 277 V line-to-neutral, 480 V line-to-line
- System frequency: 60 Hz
- 20 panels, up to 50 floors (configurable 1–50)
- Energy accumulation uses wall-clock elapsed time between ticks
- Simulated readings use Gaussian noise around realistic nominal values;
  fault probabilities are 4 % per panel per tick for background noise
  (suppressed in Demo Mode)

---

## Configurable Floors

The sidebar **Number of Floors** input (1–50) redistributes all 20 panels across
the new floor count using a round-robin algorithm. **Changing the floor count
requires clicking "✅ Apply Configuration"** — an accidental nudge of the number
input alone will not trigger a reset. The warning banner in the sidebar describes
exactly what will change before you confirm.

When applied:
- The Building Simulator is rebuilt with the new panel distribution
- The in-memory Maintenance Queue is reset
- The persistent `fault_log.csv` is **preserved**

---

## Demo Mode

Enable **Demo Mode** on the Fault Simulation tab (Tab 3) to suppress the 4 %
background random fault probability. This produces a clean, distraction-free
environment for the 6-step guided maintenance demonstration:

1. Verify all panels normal
2. Inject overcurrent on demo panel
3. Observe fault propagation to maintenance queue
4. Acknowledge the maintenance item
5. Clear the fault injection
6. Confirm recovery

The demo panel is always the first panel assigned to floor 1 after any floor
reconfiguration.

---

## Maintenance Report Export

The Maintenance Queue tab exports an 18-column CSV report including:
- Disclaimer header (SIMULATED DATA)
- Building summary (total / normal / warning / fault panel counts)
- Per-item: panel ID, floor, fault category, severity, measured value, unit,
  priority, workflow status, first/latest detected timestamps, acknowledged-at,
  resolved-at, and notes

---

## Limitations

1. **No real hardware** — all readings are probabilistic simulations. Do not use
   this dashboard to make decisions about real electrical systems.
2. **Single-machine persistence** — the fault log (`fault_log.csv`) is a local CSV
   file; there is no database or multi-user support.
3. **Energy accuracy** — energy accumulation depends on wall-clock tick intervals.
   The auto-rerun interval (1–10 s) introduces rounding imprecision; values are
   illustrative only.
4. **Streamlit rerun model** — the entire script re-executes on every tick. This is
   appropriate for a portfolio demo but would not scale to hundreds of concurrent users.
5. **Power quality** — harmonics, transients, and asymmetric loading are not modelled.
6. **Fault injection persistence** — injected faults are stored in session state only;
   they do not survive a page refresh.

---

## Test Coverage Summary

| Test file | Tests | What is covered |
|-----------|-------|----------------|
| `test_calculations.py` | 56 | All EE formulas, edge cases (zero current, unity PF, negative deviation) |
| `test_fault_detector.py` | 29 | All three fault types, boundary values, batch detection |
| `test_energy_accumulation.py` | 13 | Tick accumulation, paused state, elapsed time handling |
| `test_building.py` | 47 | PanelDefinition construction, PanelState, registry helpers |
| `test_maintenance.py` | 62 | Full queue lifecycle — add, acknowledge, note, resolve, filter, export |
| `test_demo_mode.py` | 38 | DemoState, step advancement, reset, build_demo_steps output |
| `test_report_generator.py` | 38 | CSV structure, disclaimer rows, 18-column schema, edge cases |
| `test_building_config.py` | 50 | distribute_panels round-robin, active_floors, MIN/MAX bounds |
| **Total** | **333** | |

---

## Interview Defence Notes

**Why keep EE logic out of `app.py`?**
Streamlit reruns the entire script on every widget interaction. If formulas lived
in `app.py`, they'd be harder to unit-test (you'd need to mock the Streamlit
context) and harder to reuse elsewhere. Pure functions in separate modules are
testable, portable, and reviewable in isolation.

**Why a pending/Apply pattern for floor changes?**
Streamlit's `number_input` fires on every keypress. Without a confirmation gate,
incrementing the floor count from 12 to 13 would immediately destroy an in-progress
maintenance demo. The Apply button gives the operator a deliberate confirmation
step — standard practice in SCADA and HMI design.

**How does energy accumulation work without a real clock?**
`accumulate_energy_tick()` in `calculations.py` records `time.monotonic()` on each
tick and computes `Δt = current_tick − last_tick`. This turns the discrete
auto-rerun loop into a numeric integration: E += P × Δt / 3 600 000. The result is
in kWh and is as accurate as the OS scheduler allows.

**What makes the fault detection stateless?**
`detect_faults_batch()` in `fault_detector.py` takes a list of readings and a
thresholds dict and returns a list of `FaultEvent` objects — no global state, no
side effects. This means the same function works identically for the single-panel
bus and every panel in the building simulator without any modification.

---

## License

MIT — see `LICENSE` if present, otherwise treat as open for educational/portfolio use.
