# Electrical Panel Monitoring Dashboard

> **All sensor readings are SIMULATED by a probabilistic noise model. This project does not interface with real electrical hardware.**

---

## 1. Project Overview

This project is a SCADA-style electrical panel monitoring dashboard built with **Streamlit**, **Plotly**, and **Python**. It simulates a 277/480 V 3-phase commercial electrical panel with eight configurable branch circuits, displays real-time power metrics, classifies faults by severity, and persists alarm events to a CSV log. The codebase is structured around pure-function EE math, object-oriented design patterns, and a full pytest suite with HTML coverage reporting — demonstrating how classical electrical engineering fundamentals can be implemented and validated as clean, testable software.

**Key features:**

- 277/480 V 3-phase bus monitoring with power triangle visualization (S, P, Q, PF)
- 8 configurable branch circuits with independent per-circuit fault detection
- Auto-refreshing SCADA-style dashboard via `st.rerun` loop (configurable interval)
- Real-time fault classification with **WARNING** and **FAULT** severity levels
- Persistent fault event log (CSV, row-capped) that survives browser reloads
- Adjustable voltage, current, and power factor thresholds via sidebar sliders
- 74 unit tests with pytest-cov HTML coverage report

---

## 2. Prerequisites

- **Python 3.10 or higher** — f-strings, `|` union type hints, and `dataclasses` are used throughout
- **pip** — for installing dependencies from `requirements.txt`
- *(Optional)* **virtualenv** or the built-in `venv` module — recommended to isolate project dependencies

---

## 3. Installation

```bash
git clone <repo-url>
cd electrical-panel-dashboard

python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

---

## 4. Running the Dashboard

```bash
streamlit run app.py
```

The dashboard opens at **http://localhost:8501** by default. It auto-refreshes every **3 seconds** (configurable via the **Refresh Interval** slider in the sidebar). Each refresh calls the simulator, runs fault detection across all circuits, appends any new fault events to the CSV log, and re-renders all charts.

Use the sidebar to:
- Pause / resume auto-refresh
- Adjust voltage, current, and power factor thresholds
- Change the trend-chart history window
- Clear the fault log

---

## 5. Running Tests

```bash
# Run all tests with verbose output
pytest tests/ -v

# Run with coverage report (HTML at htmlcov/index.html)
pytest tests/ --cov=. --cov-report=html
```

Open `htmlcov/index.html` in a browser to view the line-by-line coverage report.

---

## 6. Formula Reference

| Symbol | Formula | Units | Module | Engineering Note |
|--------|---------|-------|--------|-----------------|
| S | S = V × I | VA | calculations.py | Apparent power — product of RMS voltage and current; what the utility source must supply |
| P | P = V × I × PF | W | calculations.py | Real power — the work-doing component; only P produces heat, torque, or light |
| Q | Q = √(S² − P²) | VAR | calculations.py | Reactive power — energy stored and released by inductors and capacitors per cycle |
| PF | PF = cos(θ) | dimensionless | calculations.py | Power factor — ratio of real to apparent power; θ is the V–I phase angle |
| E | E = P × Δt / 3 600 000 | kWh | calculations.py | Energy — time integral of power; Δt in seconds |
| Load% | (I_actual / I_rated) × 100 | % | calculations.py | How close a circuit is to its rated current capacity |
| dev% | (V − V_nom) / V_nom × 100 | % | calculations.py | Signed voltage deviation; negative = under-voltage |
| P₃φ | P = √3 × V_L × I_L × PF | W | calculations.py | 3-phase power; √3 ≈ 1.732 arises from the 120° phase displacement between phases |

---

## 7. Fault Threshold Defaults

| Parameter | Warning | Fault | Nominal |
|-----------|---------|-------|---------|
| Voltage (L-N) | < 249.3 V (−10 %) | < 235.45 V (−15 %) | 277 V |
| Phase Current | > 220 A (110 % of rated 200 A) | > 250 A (125 %) | 160 A (80 % load) |
| Power Factor | < 0.85 | < 0.75 | 0.88 |

All thresholds are adjustable in real-time via sidebar sliders.

---

## 8. Project Structure

```
Panel-Watch-Electrical-Panel-Monitoring-Dashboard/   ← repo root
├── README.md                           # This file
├── .github/
│   └── workflows/
│       └── ci.yml                      # GitHub Actions CI/CD pipeline
└── electrical-panel-dashboard/
    ├── app.py                          # Streamlit entry point — wires all modules, auto-rerun loop
    ├── config.py                       # All constants, thresholds, 8 circuit definitions
    ├── simulator.py                    # Probabilistic sensor data generator (SIMULATED)
    ├── calculations.py                 # Pure EE math functions (no Streamlit dependency)
    ├── fault_detector.py               # Stateless fault classification; FaultEvent dataclass
    ├── logger.py                       # CSV fault log persistence with row cap
    ├── ui_components.py                # Reusable Streamlit/Plotly widget builders
    ├── Dockerfile                      # Container image for the Streamlit app
    ├── data/
    │   └── fault_log.csv               # Auto-created; persists across browser reloads
    ├── tests/
    │   ├── __init__.py
    │   ├── test_calculations.py        # 45 unit tests for EE formulas
    │   └── test_fault_detector.py      # 29 unit tests for fault classification
    ├── .coveragerc                     # pytest-cov config — HTML report at htmlcov/
    └── requirements.txt                # Pinned dependencies
```

---

## 9. Assumptions and Limitations

1. **Sinusoidal steady-state**: All formulas assume pure sinusoidal voltage and current at 60 Hz. No harmonic distortion is modeled.
2. **Balanced load approximation**: The 3-phase power formula `P = √3 × V_L × I_L × PF` assumes a balanced (symmetrical) load. The simulator introduces slight imbalance via Gaussian noise.
3. **Single-point snapshot readings**: Each reading is an instantaneous RMS sample, not a waveform capture. Real power analyzers sample at 10–50 kHz.
4. **No transformer model**: The simulation does not model transformer losses, tap changes, or magnetizing current.
5. **Displacement PF only**: PF here is displacement power factor (DPF = cos θ), not true power factor (TPF). Variable-frequency drives (VFDs) and switching supplies produce harmonics that distort TPF significantly.
6. **Probabilistic fault injection**: Faults are injected randomly at 4 % probability per tick. In a real system, faults are deterministic physical events. The probability model is for demonstration only.
7. **Energy resets on app restart**: kWh accumulation is stored in Streamlit session state and resets when the server restarts. The fault log persists; energy does not.
8. **Single-user only**: The dashboard is not designed for multi-user concurrent access.

---

## 10. Interview Prep / Engineering Notes

### Why separate `calculations.py` from the rest?
Pure functions with no side effects are the easiest code to test. By keeping EE math in one file with no Streamlit or Pandas imports, any formula can be tested in isolation with a single function call. This mirrors how embedded protection relay firmware separates measurement algorithms from I/O drivers — a pattern called "separation of concerns."

### Why a `FaultEvent` dataclass?
Dataclasses provide typed, self-documenting data transfer objects. The `to_dict()` method makes CSV logging trivial. In industrial control systems, fault records are standardized structures — e.g., IEC 61968 Asset Management messages or DNP3 event objects. Using a dataclass instead of a plain dict prevents field-name typos and makes the code self-documenting.

### Why simulate faults probabilistically?
A purely deterministic simulator would produce a flat line with no noise, which looks fake and doesn't demonstrate the fault-detection logic. Gaussian noise around nominal values plus rare probabilistic fault injection produces waveform patterns that resemble real SCADA historian data. The 4 % fault injection rate generates enough alarms to demonstrate the fault log without overwhelming it.

### What is the √3 factor in three-phase power?
In a balanced 3-phase system, the three phase currents are 120° apart. When you sum their contributions to total power, the phasor geometry yields a √3 multiplier on the line-to-line voltage and line current product. Numerically: √3 ≈ 1.732. At 480 V, 200 A, PF = 0.90 this gives 1.732 × 480 × 200 × 0.90 ≈ **149.7 kW**.

### What is the difference between apparent, real, and reactive power?
The power triangle: **S** (hypotenuse, VA) = apparent power — what the utility bills you for generation capacity. **P** (horizontal leg, W) = real power — what actually does work (heat, torque, light). **Q** (vertical leg, VAR) = reactive power — energy sloshing back and forth between source and inductive/capacitive loads. **PF = P / S = cos(θ)**. A PF of 0.85 means 85 % of apparent power is doing useful work; the remaining 15 % circulates as reactive current, causing extra I²R losses in conductors.

### Why use `deque(maxlen=N)` for the history buffer?
`collections.deque` with a `maxlen` is an O(1) ring buffer — appending a new reading automatically evicts the oldest one without any explicit deletion logic. For a dashboard that refreshes every few seconds and keeps 60 readings, this is far more efficient than appending to a growing list and slicing. It also has a bounded memory footprint, which matters for long-running dashboard sessions.

### Why persist fault events to CSV?
Streamlit re-executes the entire script on every refresh. In-memory state stored in `st.session_state` survives reruns but not server restarts. A CSV log (like a simplified SCADA historian) survives restarts, can be opened in Excel, and demonstrates awareness of data persistence concerns found in real industrial systems.

### What would make this production-ready?
1. Replace the simulator with a real **Modbus/TCP** or **DNP3** driver (e.g., `pymodbus`)
2. Use a **time-series database** (InfluxDB, TimescaleDB) instead of CSV
3. Add **authentication** (Streamlit auth or a reverse proxy)
4. Package as a **Docker container** for deployment
5. Add **ROCOF** (rate-of-change of frequency) fault detection for grid frequency events
6. Model **harmonic distortion** to compute true power factor vs. displacement power factor
7. Add **email/SMS alerting** when FAULT severity events are logged
