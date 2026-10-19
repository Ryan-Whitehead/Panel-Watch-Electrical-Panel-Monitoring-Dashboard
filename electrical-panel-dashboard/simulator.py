"""
simulator.py — Probabilistic simulated sensor data generator.

!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
ALL DATA PRODUCED BY THIS MODULE IS SIMULATED.
It does NOT come from real sensors, hardware, or electrical infrastructure.
The probabilistic noise model and fault-injection logic are for demonstration
and educational purposes only.
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

Design notes:
  - Gaussian noise is added around nominal values to produce realistic-looking
    waveform trends without requiring real measurements.
  - Faults are injected probabilistically so the dashboard occasionally shows
    alarm conditions without running flat-line data.
  - SimulatorHistory stores the last N readings in a deque ring buffer for
    trend charts; deque(maxlen=N) evicts oldest entries in O(1).
"""

import collections
import enum
from datetime import datetime

import numpy as np
import pandas as pd

import config

SIMULATED_DATA: bool = True  # Always True — data is never from real sensors.


# ---------------------------------------------------------------------------
# Fault scenario enum
# ---------------------------------------------------------------------------

class FaultScenario(enum.Enum):
    NORMAL = "normal"
    OVERCURRENT = "overcurrent"
    UNDERVOLTAGE = "undervoltage"
    LOW_POWER_FACTOR = "low_power_factor"


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _inject_phase_fault(
    scenario: FaultScenario,
    voltages: list[float],
    currents: list[float],
    pfs: list[float],
) -> tuple[list[float], list[float], list[float]]:
    """Apply a fault scenario to a random phase index and return modified lists."""
    idx = int(np.random.randint(0, 3))
    if scenario == FaultScenario.OVERCURRENT:
        currents[idx] = config.PHASE_RATED_CURRENT_A * 1.35 + float(
            np.random.normal(0, 1.0)
        )
    elif scenario == FaultScenario.UNDERVOLTAGE:
        voltages[idx] = config.V_LINE_TO_NEUTRAL * 0.82 + float(
            np.random.normal(0, 1.0)
        )
    elif scenario == FaultScenario.LOW_POWER_FACTOR:
        pfs[idx] = 0.68 + float(np.random.normal(0, 0.005))
    return voltages, currents, pfs


# ---------------------------------------------------------------------------
# Phase-bus reading generator
# ---------------------------------------------------------------------------

def generate_phase_readings(
    timestamp: datetime,
    fault_scenario: FaultScenario | None = None,
) -> dict:
    """
    Generate one set of 3-phase bus readings with Gaussian noise.

    Args:
        timestamp:      Timestamp to embed in the returned dict.
        fault_scenario: If provided, override random fault injection with this
                        specific scenario (used for deterministic testing).

    Returns:
        dict with keys:
            timestamp, simulated,
            phase_A_V, phase_B_V, phase_C_V   (line-to-neutral, V)
            phase_A_I, phase_B_I, phase_C_I   (line current, A)
            phase_A_PF, phase_B_PF, phase_C_PF (power factor)

    Notes:
        - Nominal operating point: 277 V L-N, 160 A (80 % of 200 A rated), PF 0.88.
        - Voltage clipped to [200, 320] V.
        - Current clipped to [0, 300] A.
        - PF clipped to [0.70, 1.0].
    """
    # --- nominal values ---
    V_nom = config.V_LINE_TO_NEUTRAL
    I_nom = config.PHASE_RATED_CURRENT_A * 0.80   # 160 A nominal load
    PF_nom = 0.88

    voltages = [
        float(np.random.normal(V_nom, config.NOISE_VOLTAGE_SIGMA)) for _ in range(3)
    ]
    currents = [
        float(np.random.normal(I_nom, config.NOISE_CURRENT_SIGMA)) for _ in range(3)
    ]
    pfs = [
        float(np.random.normal(PF_nom, config.NOISE_PF_SIGMA)) for _ in range(3)
    ]

    # --- fault injection ---
    if fault_scenario is None:
        draw = float(np.random.random())
        if draw < 0.015:
            scenario = FaultScenario.OVERCURRENT
        elif draw < 0.030:
            scenario = FaultScenario.UNDERVOLTAGE
        elif draw < 0.040:
            scenario = FaultScenario.LOW_POWER_FACTOR
        else:
            scenario = FaultScenario.NORMAL
    else:
        scenario = fault_scenario

    if scenario != FaultScenario.NORMAL:
        voltages, currents, pfs = _inject_phase_fault(scenario, voltages, currents, pfs)

    # --- clip to physical bounds ---
    voltages = [float(np.clip(v, 200.0, 320.0)) for v in voltages]
    currents = [float(np.clip(i, 0.0, 300.0)) for i in currents]
    pfs      = [float(np.clip(p, 0.70, 1.0)) for p in pfs]

    return {
        "timestamp":  timestamp,
        "simulated":  True,
        "phase_A_V":  voltages[0],
        "phase_B_V":  voltages[1],
        "phase_C_V":  voltages[2],
        "phase_A_I":  currents[0],
        "phase_B_I":  currents[1],
        "phase_C_I":  currents[2],
        "phase_A_PF": pfs[0],
        "phase_B_PF": pfs[1],
        "phase_C_PF": pfs[2],
    }


# ---------------------------------------------------------------------------
# Circuit reading generator
# ---------------------------------------------------------------------------

def generate_circuit_readings(
    timestamp: datetime,
    fault_scenario: FaultScenario | None = None,
) -> list[dict]:
    """
    Generate one reading per branch circuit defined in config.CIRCUITS.

    Args:
        timestamp:      Timestamp to embed in each returned dict.
        fault_scenario: If provided, apply this scenario to ALL circuits
                        (used for deterministic testing).  When None, a
                        single random circuit may have a fault injected at
                        config.FAULT_INJECT_PROBABILITY probability.

    Returns:
        List of dicts (one per circuit) with keys:
            timestamp, simulated, circuit_name, voltage_V, current_A,
            power_factor, rated_current_A, rated_pf, color.
    """
    readings: list[dict] = []

    # Decide whether to inject a fault into one circuit this tick.
    fault_circuit_idx: int | None = None
    injected_scenario: FaultScenario = FaultScenario.NORMAL

    if fault_scenario is None:
        if float(np.random.random()) < config.FAULT_INJECT_PROBABILITY:
            fault_circuit_idx = int(np.random.randint(0, len(config.CIRCUITS)))
            injected_scenario = FaultScenario(
                np.random.choice(
                    [FaultScenario.OVERCURRENT.value,
                     FaultScenario.UNDERVOLTAGE.value,
                     FaultScenario.LOW_POWER_FACTOR.value]
                )
            )
    else:
        injected_scenario = fault_scenario

    for idx, circuit in enumerate(config.CIRCUITS):
        rated_I  = circuit["rated_current_A"]
        rated_pf = circuit["rated_pf"]

        voltage = float(
            np.clip(
                np.random.normal(config.V_LINE_TO_NEUTRAL, config.NOISE_VOLTAGE_SIGMA),
                200.0, 320.0,
            )
        )
        current = float(
            np.clip(
                np.random.normal(rated_I * 0.70, rated_I * 0.05),
                0.0, rated_I * 1.5,
            )
        )
        pf = float(
            np.clip(
                np.random.normal(rated_pf, 0.015),
                0.70, 1.0,
            )
        )

        # Apply fault if this circuit is selected (or all, for explicit scenario).
        apply = (fault_scenario is not None) or (idx == fault_circuit_idx)
        if apply and injected_scenario == FaultScenario.OVERCURRENT:
            current = float(np.clip(rated_I * 1.30, 0.0, rated_I * 1.5))
        elif apply and injected_scenario == FaultScenario.UNDERVOLTAGE:
            voltage = float(np.clip(config.V_LINE_TO_NEUTRAL * 0.83, 200.0, 320.0))
        elif apply and injected_scenario == FaultScenario.LOW_POWER_FACTOR:
            pf = float(np.clip(0.70 + np.random.normal(0, 0.005), 0.70, 1.0))

        readings.append({
            "timestamp":       timestamp,
            "simulated":       True,
            "circuit_name":    circuit["name"],
            "voltage_V":       voltage,
            "current_A":       current,
            "power_factor":    pf,
            "rated_current_A": rated_I,
            "rated_pf":        rated_pf,
            "color":           circuit["color"],
        })

    return readings


# ---------------------------------------------------------------------------
# History ring buffer
# ---------------------------------------------------------------------------

class SimulatorHistory:
    """
    Ring buffer that stores the last N phase and circuit readings for trend charts.

    Uses collections.deque(maxlen=N) for O(1) append-and-evict behavior.
    The maxlen is set from config.HISTORY_WINDOW by default but can be
    overridden (e.g., from the sidebar history-window slider).
    """

    def __init__(self, maxlen: int = config.HISTORY_WINDOW) -> None:
        self._phase_buf: collections.deque[dict] = collections.deque(maxlen=maxlen)
        # Each circuit tick produces len(CIRCUITS) dicts; buffer holds all of them flat.
        self._circuit_buf: collections.deque[dict] = collections.deque(
            maxlen=maxlen * len(config.CIRCUITS)
        )
        self.maxlen = maxlen

    def append(self, phase_reading: dict, circuit_readings: list[dict]) -> None:
        """Append one tick of phase and circuit readings to the ring buffers."""
        self._phase_buf.append(phase_reading)
        self._circuit_buf.extend(circuit_readings)

    def phase_dataframe(self) -> pd.DataFrame:
        """
        Return a DataFrame of all stored phase readings, indexed by timestamp.

        Columns: phase_A_V, phase_B_V, phase_C_V,
                 phase_A_I, phase_B_I, phase_C_I,
                 phase_A_PF, phase_B_PF, phase_C_PF
        """
        if not self._phase_buf:
            cols = [
                "phase_A_V", "phase_B_V", "phase_C_V",
                "phase_A_I", "phase_B_I", "phase_C_I",
                "phase_A_PF", "phase_B_PF", "phase_C_PF",
            ]
            return pd.DataFrame(columns=cols)
        df = pd.DataFrame(list(self._phase_buf))
        df = df.set_index("timestamp")
        drop_cols = [c for c in df.columns if c in ("simulated",)]
        df = df.drop(columns=drop_cols, errors="ignore")
        return df

    def circuit_dataframe(self, circuit_name: str) -> pd.DataFrame:
        """
        Return a DataFrame for a single named circuit, indexed by timestamp.

        Columns: voltage_V, current_A, power_factor, load_pct (derived).
        """
        rows = [r for r in self._circuit_buf if r["circuit_name"] == circuit_name]
        if not rows:
            return pd.DataFrame(columns=["voltage_V", "current_A", "power_factor", "load_pct"])
        df = pd.DataFrame(rows).set_index("timestamp")
        df["load_pct"] = df["current_A"] / df["rated_current_A"] * 100.0
        keep = ["voltage_V", "current_A", "power_factor", "load_pct"]
        return df[[c for c in keep if c in df.columns]]

    def all_circuits_dataframe(self) -> pd.DataFrame:
        """
        Return all circuit readings as a flat DataFrame indexed by timestamp.

        Includes circuit_name and derived load_pct columns.
        """
        if not self._circuit_buf:
            return pd.DataFrame(columns=["circuit_name", "voltage_V", "current_A",
                                          "power_factor", "load_pct"])
        df = pd.DataFrame(list(self._circuit_buf)).set_index("timestamp")
        df["load_pct"] = df["current_A"] / df["rated_current_A"] * 100.0
        return df
