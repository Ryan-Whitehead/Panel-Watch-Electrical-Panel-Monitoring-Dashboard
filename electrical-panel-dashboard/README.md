# PanelWatch — Technical Reference

> **All sensor readings are SIMULATED by a probabilistic noise model.**
> This project does not interface with real electrical hardware or control any physical equipment.

Built for the **IBM Bob Hackathon 2026** by Ryan Whitehead.

---

## 1. Project Overview

PanelWatch is a building-wide SCADA-style electrical monitoring dashboard built with **Streamlit**, **Plotly**, and **Python**. It simulates **20 independent 277/480 V 3-phase panels** distributed across a **configurable number of floors** (default 12, range 1–50), enabling building maintenance personnel to monitor the entire electrical health of a simulated building from a single screen.

**Key features:**

- **Building Overview** — 20-panel status grid with floor filter, search, and status heat-map
- **Configurable Floor Count** — sidebar slider changes the number of floors (1–50); panels are redistributed automatically using a round-robin algorithm
- **3-Phase Bus** — live per-phase voltage, current, power factor, and power triangle
- **Circuit Breakdown** — 8 configurable branch circuits with load bars and trend charts
- **Fault Simulation** — Demo Mode toggle (suppresses random background faults); 6-step Guided Maintenance Demonstration; manual per-panel injection (overcurrent, undervoltage, low PF)
- **Maintenance Queue** — rule-based priority queue (HIGH / MEDIUM / LOW) with acknowledge, notes, resolve, and CSV report export
- **Analytics** — fault trend, fault-by-category, and fault-by-panel charts from the persistent log
- **Fault Log** — timestamped CSV log of every fault event, survives browser reloads
- Accurate energy accumulation using `time.monotonic()` elapsed-time measurement
- Auto-refreshing SCADA-style dashboard via `st.rerun` loop (configurable interval)
- **333-test pytest suite** covering calculations, fault detection, building model, maintenance queue, demo mode, report generation, and floor configuration

---

## 2. Prerequisites

- **Python 3.10 or higher**
- **pip**
- *(Optional)* `venv` for dependency isolation

---

## 3. Installation

```bash
git clone https://github.com/Ryan-Whitehead/Panel-Watch-Electrical-Panel-Monitoring-Dashboard.git
cd Panel-Watch-Electrical-Panel-Monitoring-Dashboard/electrical-panel-dashboard

python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

> **Note:** The runnable application is inside the `electrical-panel-dashboard/` subdirectory.
> All commands below assume you are inside that directory.

---

## 4. Running the Dashboard

```bash
streamlit run app.py
```

Opens at **http://localhost:8501** by default.
Auto-refreshes every 3 seconds (configurable via the sidebar Refresh Interval slider).

**Sidebar controls:**
- Pause / resume the simulation
- Adjust voltage, current, and power factor fault thresholds
- Change the trend-chart history window
- Clear the fault log

---

## 5. Running Tests

```bash
# Verbose test output
pytest tests/ -v

# With HTML coverage report (opens htmlcov/index.html)
pytest tests/ --cov=. --cov-report=html
```

---

## 6. Formula Reference

| Symbol | Formula | Units | Module | Notes |
|--------|---------|-------|--------|-------|
| S_k | S_k = V_k x I_k | VA | calculations.py | Per-phase apparent power |
| P_k | P_k = V_k x I_k x PF_k | W | calculations.py | Per-phase real power |
| Q_k | Q_k = sqrt(S_k^2 - P_k^2) | VAR | calculations.py | Per-phase reactive power (nonneg.) |
| P_total | P_A + P_B + P_C | W | calculations.py | Bus total real power (per-phase sum) |
| S_total | S_A + S_B + S_C | VA | calculations.py | Bus total apparent power |
| Q_total | Q_A + Q_B + Q_C | VAR | calculations.py | Bus total reactive power |
| PF_agg | P_total / S_total | - | calculations.py | Aggregate power factor |
| E | P x dt / 3,600,000 | kWh | calculations.py | Energy (dt = actual elapsed seconds) |
| Load% | (I_actual / I_rated) x 100 | % | calculations.py | Circuit load percentage |
| dev% | (V - V_nom) / V_nom x 100 | % | calculations.py | Signed voltage deviation |
| P_3ph | sqrt(3) x V_LL x I_L x PF | W | calculations.py | Balanced approx. (reference only) |

---

## 7. Electrical Engineering Design Decisions

### Per-phase summation vs. balanced approximation

The dashboard calculates bus totals by summing per-phase contributions:

```
P_total = (V_A x I_A x PF_A) + (V_B x I_B x PF_B) + (V_C x I_C x PF_C)
```

The simulator introduces Gaussian noise independently on each phase, producing slight imbalance. The balanced formula `P = sqrt(3) x V_LL x I_L x PF` is only exact when all three phases are identical. Per-phase summation is always correct and is the method used by real power analyzers and revenue meters. The balanced formula remains available in `calculations.py` for reference and comparison.

### Accurate energy accumulation

Energy is accumulated using the actual elapsed wall-clock time between simulation ticks:

```
delta_t = time.monotonic() - last_tick_time   (seconds)
E_kWh  += P_W x delta_t / 3,600,000
```

`time.monotonic()` is used because it never goes backwards and is unaffected by system-clock adjustments. The first tick after startup or after unpausing does not accumulate energy (elapsed time since the previous update is unknown). Pausing resets the clock so paused time is never counted.

### Aggregate power factor

The aggregate PF displayed on the dashboard is:

```
PF_agg = P_total / S_total
```

This is the equivalent single-number power factor for the combined three-phase load. It equals the per-phase PF only when all phases are balanced. Individual per-phase PFs are preserved in the phase gauges.

---

## 8. Fault Threshold Defaults

| Parameter | Warning | Fault | Nominal |
|-----------|---------|-------|---------|
| Voltage (L-N) | < 249.3 V (-10%) | < 235.45 V (-15%) | 277 V |
| Phase Current | > 220 A (110% of 200 A) | > 250 A (125%) | ~160 A |
| Power Factor | < 0.85 | < 0.75 | ~0.88 |

All thresholds are adjustable in real-time via sidebar sliders.

---

## 9. Project Structure

```
electrical-panel-dashboard/
+-- app.py                       Streamlit entry point (7 tabs, building-wide)
+-- config.py                    Constants, thresholds, BUILDING_PANELS registry
+-- building.py                  PanelDefinition, PanelState, registry helpers
+-- building_config.py           distribute_panels(), active_floors(), floor constants
+-- building_simulator.py        BuildingSimulator — accepts custom panel list
+-- maintenance.py               MaintenanceItem, MaintenanceQueue, priority rules
+-- demo_mode.py                 DemoState, build_demo_steps(), reset/advance helpers
+-- report_generator.py          generate_maintenance_csv() — structured CSV report
+-- simulator.py                 Single-panel probabilistic generator (SIMULATED)
+-- calculations.py              Pure EE math functions (no Streamlit dependency)
+-- fault_detector.py            Stateless fault classification; FaultEvent dataclass
+-- logger.py                    CSV fault log persistence with row cap
+-- ui_components.py             Reusable Streamlit/Plotly widget builders
+-- data/
|   +-- .gitkeep
+-- tests/
|   +-- test_calculations.py         EE formula unit tests (56 tests)
|   +-- test_energy_accumulation.py  Energy accumulation unit tests (13 tests)
|   +-- test_fault_detector.py       Fault classification unit tests (29 tests)
|   +-- test_building.py             Building model unit tests (47 tests)
|   +-- test_maintenance.py          Maintenance queue unit tests (62 tests)
|   +-- test_demo_mode.py            Demo mode unit tests (38 tests)
|   +-- test_report_generator.py     Report generation unit tests (38 tests)
|   +-- test_building_config.py      Floor configuration unit tests (50 tests)
+-- .coveragerc                  pytest-cov config
+-- ruff.toml                    Linter config (E/F/I rules, target py310)
+-- requirements.txt             Pinned dependencies
+-- README.md
```

---

## 10. Configurable Building Floors

### How It Works

The **Building Configuration** section in the sidebar contains a **Number of Floors** input (range 1–50, default 12).

When changed:
1. `building_config.distribute_panels()` remaps the 20 panels to the new floor count using a **round-robin algorithm**: panel *i* (0-indexed) → floor `(i % num_floors) + 1`.
2. A new `BuildingSimulator` is created with the remapped panel list.
3. The `MaintenanceQueue` is reset.
4. The Guided Maintenance Demonstration selects the first panel in the new registry as its target automatically.
5. Floor filters in Building Overview and Maintenance Queue are updated to show only occupied floors.
6. The persistent `fault_log.csv` is **not** erased — historical events retain the floor assignment recorded at the time of the event.

### Panel Distribution Examples

| Floors | Panels/floor | Notes |
|--------|-------------|-------|
| 1 | 20 | All panels on Floor 1 |
| 5 | 4 | Even distribution |
| 10 | 2 | Even distribution |
| 12 (default) | 1–2 | Floors 1–8 get 2, floors 9–12 get 1 |
| 20 | 1 | One panel per floor |
| 25 | 0–1 | Floors 1–20 have 1, floors 21–25 empty |
| 50 | 0–1 | Floors 1–20 have 1, floors 21–50 empty |

---

## 11. Demo Mode and Guided Maintenance Demonstration

### Demo Mode

The **Fault Simulation** tab has a **Demo Mode toggle** at the top. When enabled:
- The 4 % random background fault probability is **suppressed**.
- Only manually injected faults (or the guided scenario) trigger fault conditions.
- Normal Gaussian measurement noise continues so readings look realistic.
- The **Reset Demo Environment** button clears all injections, resets the Maintenance Queue, and returns to Step 1 — without erasing the persistent `fault_log.csv`.

### 6-Step Guided Maintenance Demonstration

The demonstration works with **any configured floor count** — the target panel is selected dynamically from the first panel in the current registry.

1. **Normal Operation** — Click ▶ Next Step. All injections are cleared. All panels are NORMAL.
2. **Inject Overcurrent** — Click ▶ Next Step. The demonstration panel receives an overcurrent injection. Switch to 🏢 Building Overview and watch it turn FAULT (red) within one refresh tick.
3. **Fault Classification** — Switch to 🛠️ Maintenance Queue. A HIGH-priority item for `{panel_id}::current` appears automatically showing measured current, rated current, and fault threshold.
4. **Acknowledge Fault** — Select the item in the Acknowledge dropdown. Add a note (e.g. *"Checked breaker — scheduling load review"*). Click ✅ Acknowledge. The electrical fault condition is NOT cleared.
5. **Restore Normal** — Click ▶ Next Step. The injection is cleared. The panel returns to NORMAL and the maintenance item drops to LOW priority (resolved).
6. **Review History** — The maintenance record retains the acknowledgement timestamp and technician note. Click **⬇️ Download Maintenance Report (CSV)** to export a full structured report.

---

## 12. Maintenance Report Export

The **Maintenance Queue** tab has an **Export Maintenance Report** section that generates a structured CSV report containing:

- Disclaimer (required by the project — not a certified safety system)
- Report title, generation timestamp, building name and voltage
- Panel status summary (total / NORMAL / WARNING / FAULT counts)
- Maintenance queue summary (HIGH / MEDIUM / LOW counts)
- One data row per item with 18 fields: item ID, panel ID, floor, location, fault category, electrical condition, severity, measured value, unit, threshold, maintenance priority, workflow status, acknowledged-at timestamp, technician notes, first detected, latest detected, resolved-at, and injected-fault flag

Active faults and resolved faults are distinguished by the **Electrical Condition** column (`FAULT`/`WARNING` = active, `NORMAL` = resolved). Acknowledging an alert is tracked separately in **Workflow Status** — it does not change the electrical condition.

---

## 13. Assumptions and Limitations

1. **Sinusoidal steady-state** — formulas assume pure 60 Hz sinusoids; no harmonic distortion modeled.
2. **Displacement PF only** — PF = cos(theta), not true power factor. VFDs and switching supplies produce harmonics that reduce true PF below displacement PF.
3. **Nonnegative reactive power** — Q magnitude only; lagging vs. leading sign not tracked (phase angles not available from the simulator).
4. **Single-point RMS snapshots** — each reading is one RMS sample, not a waveform capture.
5. **No transformer model** — transformer losses, tap changes, and magnetizing current are not modeled.
6. **Probabilistic fault injection** — faults occur randomly at ~4% probability. Real faults are deterministic physical events.
7. **Energy resets on app restart** — kWh is stored in session state and resets when the server restarts. The fault log persists.
8. **Single-user** — not designed for concurrent multi-user access.

---

## 14. Interview Prep Notes

**Why sum per phase instead of using the balanced formula?**
The balanced formula `P = sqrt(3) x V_LL x I_L x PF` assumes identical conditions on all three phases. The simulator adds independent Gaussian noise to each phase, creating small imbalances. Summing per-phase contributions (`P_total = P_A + P_B + P_C`) is always accurate regardless of load balance. Real power quality analyzers always use per-phase summation.

**Why `time.monotonic()` for energy?**
`time.time()` can jump backward (NTP correction, DST). `time.monotonic()` is guaranteed to be strictly non-decreasing, making it safe for elapsed-time measurement. A paused simulation resets the clock so paused time never appears in the energy meter.

**What is aggregate power factor?**
`PF_agg = P_total / S_total` is the ratio of total real power to total apparent power across all three phases combined. It represents the equivalent PF a utility meter would see at the service entrance. Individual phase PFs may differ; the aggregate is a weighted average by apparent power.
