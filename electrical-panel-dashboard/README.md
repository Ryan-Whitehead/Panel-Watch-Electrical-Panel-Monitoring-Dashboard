# PanelWatch — Building Electrical Monitoring Dashboard

> **All sensor readings are SIMULATED by a probabilistic noise model.**
> This project does not interface with real electrical hardware or control any physical equipment.

Built for the **IBM Bob Hackathon 2026** by Ryan Whitehead.

---

## 1. Project Overview

PanelWatch is a building-wide SCADA-style electrical monitoring dashboard built with **Streamlit**, **Plotly**, and **Python**. It simulates **20 independent 277/480 V 3-phase panels** distributed across 12 floors of a commercial building, enabling a maintenance technician (Richie) to monitor the entire building's electrical health from a single screen.

**Key features:**

- **Building Overview** — 20-panel status grid with floor filter, search, and status heat-map
- **3-Phase Bus** — live per-phase voltage, current, power factor, and power triangle for a selected panel
- **Circuit Breakdown** — 8 configurable branch circuits with load bars and trend charts
- **Fault Simulation** — deterministic fault injection (overcurrent, undervoltage, low PF) per panel; includes a Richie's Demo scenario that walks through a realistic multi-panel incident
- **Maintenance Queue** — rule-based priority queue (HIGH / MEDIUM / LOW) with acknowledge, notes, and resolve workflow
- **Analytics** — fault trend, fault-by-category, and fault-by-panel charts from the persistent log
- **Fault Log** — timestamped CSV log of every fault event, survives browser reloads
- Accurate energy accumulation using monotonic elapsed-time measurement
- Auto-refreshing SCADA-style dashboard via `st.rerun` loop (configurable interval)
- 207-test pytest suite covering calculations, fault detection, building model, and maintenance queue

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
+-- building_simulator.py        BuildingSimulator — 20-panel independent sim engine
+-- maintenance.py               MaintenanceItem, MaintenanceQueue, priority rules
+-- simulator.py                 Single-panel probabilistic generator (SIMULATED)
+-- calculations.py              Pure EE math functions (no Streamlit dependency)
+-- fault_detector.py            Stateless fault classification; FaultEvent dataclass
+-- logger.py                    CSV fault log persistence with row cap
+-- ui_components.py             Reusable Streamlit/Plotly widget builders
+-- data/
|   +-- .gitkeep
+-- tests/
|   +-- test_calculations.py     Unit tests for EE formulas (56 tests)
|   +-- test_energy_accumulation.py  Unit tests for energy accumulation (13 tests)
|   +-- test_fault_detector.py   Unit tests for fault classification (29 tests)
|   +-- test_building.py         Unit tests for building model (47 tests)
|   +-- test_maintenance.py      Unit tests for maintenance queue (62 tests)
+-- .coveragerc                  pytest-cov config
+-- ruff.toml                    Linter config (E/F/I rules, target py310)
+-- requirements.txt             Pinned dependencies
+-- README.md
```

---

## 10. Richie's Demo Walkthrough

This walkthrough shows a first-time reviewer (or interviewer) the full building-monitoring workflow in under 5 minutes.

1. **Open the app** — `streamlit run app.py` → **Building Overview** tab loads automatically.
2. **Observe the grid** — 20 panel cards show NORMAL (green). Note the floor filter and search box.
3. **Go to Fault Simulation tab** → expand **"Richie's Demo Scenario"** and click **"Run Richie's Demo"**.
   - P-07 gets an OVERCURRENT injection; P-09 gets an UNDERVOLTAGE injection.
   - Within one or two refresh ticks the Building Overview grid shows two FAULT cards.
4. **Back to Building Overview** — filter by status = FAULT; only the two affected panels appear.
5. **Click through to a FAULT panel's card** → the 3-Phase Bus tab shows the three phases all in the fault band.
6. **Maintenance Queue tab** — two HIGH-priority items appear automatically (one per fault type per panel).
   - Acknowledge P-07's overcurrent item; add a technician note (e.g. "Checked breaker, scheduling load review").
7. **Click "Clear Injections"** in Fault Simulation — panels return to NORMAL after the next tick.
8. **Back to Maintenance Queue** — items drop to LOW priority (resolved). Mark them as Reviewed, then Clear Resolved.
9. **Analytics tab** — fault trend chart shows the spike; fault-by-category bar confirms "current" and "voltage" event counts.
10. **Fault Log tab** — raw CSV rows show every event with timestamps.

---

## 11. Assumptions and Limitations

1. **Sinusoidal steady-state** — formulas assume pure 60 Hz sinusoids; no harmonic distortion modeled.
2. **Displacement PF only** — PF = cos(theta), not true power factor. VFDs and switching supplies produce harmonics that reduce true PF below displacement PF.
3. **Nonnegative reactive power** — Q magnitude only; lagging vs. leading sign not tracked (phase angles not available from the simulator).
4. **Single-point RMS snapshots** — each reading is one RMS sample, not a waveform capture.
5. **No transformer model** — transformer losses, tap changes, and magnetizing current are not modeled.
6. **Probabilistic fault injection** — faults occur randomly at ~4% probability. Real faults are deterministic physical events.
7. **Energy resets on app restart** — kWh is stored in session state and resets when the server restarts. The fault log persists.
8. **Single-user** — not designed for concurrent multi-user access.

---

## 12. Interview Prep Notes

**Why sum per phase instead of using the balanced formula?**
The balanced formula `P = sqrt(3) x V_LL x I_L x PF` assumes identical conditions on all three phases. The simulator adds independent Gaussian noise to each phase, creating small imbalances. Summing per-phase contributions (`P_total = P_A + P_B + P_C`) is always accurate regardless of load balance. Real power quality analyzers always use per-phase summation.

**Why `time.monotonic()` for energy?**
`time.time()` can jump backward (NTP correction, DST). `time.monotonic()` is guaranteed to be strictly non-decreasing, making it safe for elapsed-time measurement. A paused simulation resets the clock so paused time never appears in the energy meter.

**What is aggregate power factor?**
`PF_agg = P_total / S_total` is the ratio of total real power to total apparent power across all three phases combined. It represents the equivalent PF a utility meter would see at the service entrance. Individual phase PFs may differ; the aggregate is a weighted average by apparent power.
