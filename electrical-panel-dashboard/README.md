# PanelWatch — Electrical Panel Monitoring Dashboard

> **All sensor readings are SIMULATED by a probabilistic noise model.**
> This project does not interface with real electrical hardware or control any physical equipment.

Built for the **IBM Bob Hackathon 2026** by Ryan Whitehead.

---

## 1. Project Overview

PanelWatch is a SCADA-style electrical panel monitoring dashboard built with **Streamlit**, **Plotly**, and **Python**. It simulates a 277/480 V 3-phase commercial electrical panel with eight configurable branch circuits, displays real-time power metrics, classifies faults by severity, and persists alarm events to a CSV log.

**Key features:**

- 277/480 V 3-phase bus monitoring with per-phase summation power triangle (P, S, Q, PF)
- 8 configurable branch circuits (HVAC, Lighting, Motor-1/2/3, Compressor, Receptacles, Emergency)
- Accurate energy accumulation using monotonic elapsed-time measurement
- Auto-refreshing SCADA-style dashboard via `st.rerun` loop (configurable interval)
- Real-time fault classification with **WARNING** and **FAULT** severity levels
- Persistent fault event log (CSV, row-capped) that survives browser reloads
- Adjustable voltage, current, and power factor thresholds via sidebar sliders
- Full pytest suite with pytest-cov HTML coverage report

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
+-- app.py                      Streamlit entry point
+-- config.py                   Constants, thresholds, circuit definitions
+-- simulator.py                Probabilistic sensor data generator (SIMULATED)
+-- calculations.py             Pure EE math functions (no Streamlit dependency)
+-- fault_detector.py           Stateless fault classification; FaultEvent dataclass
+-- logger.py                   CSV fault log persistence with row cap
+-- ui_components.py            Reusable Streamlit/Plotly widget builders
+-- data/
|   +-- .gitkeep
+-- tests/
|   +-- test_calculations.py    Unit tests for EE formulas
|   +-- test_fault_detector.py  Unit tests for fault classification
+-- .coveragerc                 pytest-cov config
+-- requirements.txt            Pinned dependencies
+-- README.md
```

---

## 10. Assumptions and Limitations

1. **Sinusoidal steady-state** — formulas assume pure 60 Hz sinusoids; no harmonic distortion modeled.
2. **Displacement PF only** — PF = cos(theta), not true power factor. VFDs and switching supplies produce harmonics that reduce true PF below displacement PF.
3. **Nonnegative reactive power** — Q magnitude only; lagging vs. leading sign not tracked (phase angles not available from the simulator).
4. **Single-point RMS snapshots** — each reading is one RMS sample, not a waveform capture.
5. **No transformer model** — transformer losses, tap changes, and magnetizing current are not modeled.
6. **Probabilistic fault injection** — faults occur randomly at ~4% probability. Real faults are deterministic physical events.
7. **Energy resets on app restart** — kWh is stored in session state and resets when the server restarts. The fault log persists.
8. **Single-user** — not designed for concurrent multi-user access.

---

## 11. Interview Prep Notes

**Why sum per phase instead of using the balanced formula?**
The balanced formula `P = sqrt(3) x V_LL x I_L x PF` assumes identical conditions on all three phases. The simulator adds independent Gaussian noise to each phase, creating small imbalances. Summing per-phase contributions (`P_total = P_A + P_B + P_C`) is always accurate regardless of load balance. Real power quality analyzers always use per-phase summation.

**Why `time.monotonic()` for energy?**
`time.time()` can jump backward (NTP correction, DST). `time.monotonic()` is guaranteed to be strictly non-decreasing, making it safe for elapsed-time measurement. A paused simulation resets the clock so paused time never appears in the energy meter.

**What is aggregate power factor?**
`PF_agg = P_total / S_total` is the ratio of total real power to total apparent power across all three phases combined. It represents the equivalent PF a utility meter would see at the service entrance. Individual phase PFs may differ; the aggregate is a weighted average by apparent power.
