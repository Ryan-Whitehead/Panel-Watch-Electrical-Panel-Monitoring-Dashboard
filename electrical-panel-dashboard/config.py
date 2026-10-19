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
# Dashboard / UI parameters
# ---------------------------------------------------------------------------
REFRESH_INTERVAL_DEFAULT: int = 3   # seconds between auto-reruns
PLOTLY_THEME: str = "plotly_dark"

# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
FAULT_LOG_PATH: Path = Path("data/fault_log.csv")
MAX_LOG_ROWS: int = 500
