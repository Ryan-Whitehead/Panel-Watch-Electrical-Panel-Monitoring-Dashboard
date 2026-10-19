"""
config.py — Project-wide constants for the Electrical Panel Monitoring Dashboard.

All threshold values, circuit definitions, simulation parameters, and path
settings live here so no magic numbers appear elsewhere in the codebase.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Electrical system parameters — 277/480 V 3-phase (North American industrial)
# ---------------------------------------------------------------------------
V_LINE_TO_LINE: float = 480.0      # Volts — line-to-line (phase-to-phase)
V_LINE_TO_NEUTRAL: float = 277.0   # Volts — line-to-neutral (branch circuit)
FREQUENCY_HZ: float = 60.0         # Hz — nominal system frequency
PHASE_RATED_CURRENT_A: float = 200.0  # Amps — rated current per phase on the main bus

# ---------------------------------------------------------------------------
# Branch circuit definitions
# Each dict: name, rated_current_A, rated_pf, color (Plotly hex)
# ---------------------------------------------------------------------------
CIRCUITS: list[dict] = [
    {"name": "HVAC",        "rated_current_A": 40.0, "rated_pf": 0.85, "color": "#4e9af1"},
    {"name": "Lighting",    "rated_current_A": 20.0, "rated_pf": 0.96, "color": "#f1c40f"},
    {"name": "Motor-1",     "rated_current_A": 30.0, "rated_pf": 0.83, "color": "#2ecc71"},
    {"name": "Motor-2",     "rated_current_A": 30.0, "rated_pf": 0.83, "color": "#1abc9c"},
    {"name": "Motor-3",     "rated_current_A": 30.0, "rated_pf": 0.82, "color": "#27ae60"},
    {"name": "Compressor",  "rated_current_A": 35.0, "rated_pf": 0.82, "color": "#e67e22"},
    {"name": "Receptacles", "rated_current_A": 25.0, "rated_pf": 0.95, "color": "#9b59b6"},
    {"name": "Emergency",   "rated_current_A": 15.0, "rated_pf": 0.97, "color": "#e74c3c"},
]

# ---------------------------------------------------------------------------
# Fault / warning thresholds
# voltage: percentage deviation from nominal (negative = under-voltage)
# current: percentage of rated current
# power_factor: absolute value
# ---------------------------------------------------------------------------
THRESHOLDS: dict = {
    "voltage": {
        "warn_pct":  -0.10,   # -10%  → warn limit = V_nom * 0.90
        "fault_pct": -0.15,   # -15%  → fault limit = V_nom * 0.85
    },
    "current": {
        "warn_pct":   1.10,   # 110% of rated
        "fault_pct":  1.25,   # 125% of rated
    },
    "power_factor": {
        "warn":  0.85,
        "fault": 0.75,
    },
}

# ---------------------------------------------------------------------------
# Simulation parameters
# ---------------------------------------------------------------------------
NOISE_VOLTAGE_SIGMA: float = 2.5    # Volts — Gaussian σ for voltage noise
NOISE_CURRENT_SIGMA: float = 0.5    # Amps  — Gaussian σ for current noise on bus phases
NOISE_PF_SIGMA: float = 0.01        # PF units — Gaussian σ for power-factor noise

FAULT_INJECT_PROBABILITY: float = 0.04   # 4% chance of injecting a fault each reading
HISTORY_WINDOW: int = 60                 # Number of readings to keep in trend-chart buffer

# ---------------------------------------------------------------------------
# Building-wide panel registry
# 20 panels distributed across 12 floors of a commercial building.
# Each entry is data-only; no logic lives here.
#
# Keys:
#   panel_id         — unique identifier, e.g. "P-01"
#   floor            — integer floor number (1–12)
#   location         — descriptive name shown in the UI
#   v_line_to_line   — nominal line-to-line voltage (V)
#   v_line_to_neutral — nominal line-to-neutral voltage (V)
#   phase_rated_current_a — rated current per phase (A)
#   nominal_load_pct — baseline operating load as fraction of rated (0–1)
#   nominal_pf       — baseline operating power factor
# ---------------------------------------------------------------------------
# fmt: off
BUILDING_PANELS: list[dict] = [
    # Floor 1 — Lobby & Building Services
    {"panel_id": "P-01", "floor": 1,  "location": "Main Service Entrance",
     "v_line_to_line": 480.0, "v_line_to_neutral": 277.0,
     "phase_rated_current_a": 400.0, "nominal_load_pct": 0.65, "nominal_pf": 0.88},
    {"panel_id": "P-02", "floor": 1,  "location": "Lobby & Common Areas",
     "v_line_to_line": 480.0, "v_line_to_neutral": 277.0,
     "phase_rated_current_a": 200.0, "nominal_load_pct": 0.50, "nominal_pf": 0.92},
    # Floor 2 — Mechanical & Electrical Rooms
    {"panel_id": "P-03", "floor": 2,  "location": "Central Mechanical Room",
     "v_line_to_line": 480.0, "v_line_to_neutral": 277.0,
     "phase_rated_current_a": 300.0, "nominal_load_pct": 0.75, "nominal_pf": 0.85},
    {"panel_id": "P-04", "floor": 2,  "location": "Electrical Equipment Room",
     "v_line_to_line": 480.0, "v_line_to_neutral": 277.0,
     "phase_rated_current_a": 250.0, "nominal_load_pct": 0.70, "nominal_pf": 0.87},
    # Floor 3 — Office Space
    {"panel_id": "P-05", "floor": 3,  "location": "East Wing Office",
     "v_line_to_line": 480.0, "v_line_to_neutral": 277.0,
     "phase_rated_current_a": 200.0, "nominal_load_pct": 0.55, "nominal_pf": 0.91},
    # Floor 4 — Office Space
    {"panel_id": "P-06", "floor": 4,  "location": "West Wing Office",
     "v_line_to_line": 480.0, "v_line_to_neutral": 277.0,
     "phase_rated_current_a": 200.0, "nominal_load_pct": 0.58, "nominal_pf": 0.90},
    # Floor 5 — Mixed Office / Lab
    {"panel_id": "P-07", "floor": 5,  "location": "Laboratory Suite A",
     "v_line_to_line": 480.0, "v_line_to_neutral": 277.0,
     "phase_rated_current_a": 250.0, "nominal_load_pct": 0.72, "nominal_pf": 0.86},
    {"panel_id": "P-08", "floor": 5,  "location": "Laboratory Suite B",
     "v_line_to_line": 480.0, "v_line_to_neutral": 277.0,
     "phase_rated_current_a": 250.0, "nominal_load_pct": 0.68, "nominal_pf": 0.87},
    # Floor 6 — Data Centre
    {"panel_id": "P-09", "floor": 6,  "location": "Data Centre \u2014 Row A",
     "v_line_to_line": 480.0, "v_line_to_neutral": 277.0,
     "phase_rated_current_a": 300.0, "nominal_load_pct": 0.80, "nominal_pf": 0.95},
    {"panel_id": "P-10", "floor": 6,  "location": "Data Centre \u2014 Row B",
     "v_line_to_line": 480.0, "v_line_to_neutral": 277.0,
     "phase_rated_current_a": 300.0, "nominal_load_pct": 0.78, "nominal_pf": 0.95},
    # Floor 7 — Conference & Training
    {"panel_id": "P-11", "floor": 7,  "location": "Conference Centre",
     "v_line_to_line": 480.0, "v_line_to_neutral": 277.0,
     "phase_rated_current_a": 200.0, "nominal_load_pct": 0.45, "nominal_pf": 0.92},
    # Floor 8 — Office Space
    {"panel_id": "P-12", "floor": 8,  "location": "North Wing Office",
     "v_line_to_line": 480.0, "v_line_to_neutral": 277.0,
     "phase_rated_current_a": 200.0, "nominal_load_pct": 0.55, "nominal_pf": 0.91},
    {"panel_id": "P-13", "floor": 8,  "location": "South Wing Office",
     "v_line_to_line": 480.0, "v_line_to_neutral": 277.0,
     "phase_rated_current_a": 200.0, "nominal_load_pct": 0.53, "nominal_pf": 0.90},
    # Floor 9 — HVAC Plant
    {"panel_id": "P-14", "floor": 9,  "location": "HVAC Plant Room",
     "v_line_to_line": 480.0, "v_line_to_neutral": 277.0,
     "phase_rated_current_a": 350.0, "nominal_load_pct": 0.82, "nominal_pf": 0.84},
    # Floor 10 — Executive / High-End Office
    {"panel_id": "P-15", "floor": 10, "location": "Executive Suite",
     "v_line_to_line": 480.0, "v_line_to_neutral": 277.0,
     "phase_rated_current_a": 200.0, "nominal_load_pct": 0.48, "nominal_pf": 0.93},
    {"panel_id": "P-16", "floor": 10, "location": "Boardroom & AV Systems",
     "v_line_to_line": 480.0, "v_line_to_neutral": 277.0,
     "phase_rated_current_a": 150.0, "nominal_load_pct": 0.42, "nominal_pf": 0.92},
    # Floor 11 — Telecom & IT
    {"panel_id": "P-17", "floor": 11, "location": "Telecom Closet \u2014 North",
     "v_line_to_line": 480.0, "v_line_to_neutral": 277.0,
     "phase_rated_current_a": 200.0, "nominal_load_pct": 0.65, "nominal_pf": 0.94},
    {"panel_id": "P-18", "floor": 11, "location": "Telecom Closet \u2014 South",
     "v_line_to_line": 480.0, "v_line_to_neutral": 277.0,
     "phase_rated_current_a": 200.0, "nominal_load_pct": 0.62, "nominal_pf": 0.94},
    # Floor 12 — Rooftop Plant & Emergency Systems
    {"panel_id": "P-19", "floor": 12, "location": "Rooftop Mechanical Plant",
     "v_line_to_line": 480.0, "v_line_to_neutral": 277.0,
     "phase_rated_current_a": 300.0, "nominal_load_pct": 0.70, "nominal_pf": 0.83},
    {"panel_id": "P-20", "floor": 12, "location": "Emergency & Fire Systems",
     "v_line_to_line": 480.0, "v_line_to_neutral": 277.0,
     "phase_rated_current_a": 150.0, "nominal_load_pct": 0.35, "nominal_pf": 0.97},
]
# fmt: on

# ---------------------------------------------------------------------------
# Dashboard / UI parameters
# ---------------------------------------------------------------------------
REFRESH_INTERVAL_DEFAULT: int = 3   # seconds between auto-reruns
PLOTLY_THEME: str = "plotly_dark"

# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
FAULT_LOG_PATH: Path = Path("data/fault_log.csv")
MAINTENANCE_LOG_PATH: Path = Path("data/maintenance_log.csv")
MAX_LOG_ROWS: int = 500
