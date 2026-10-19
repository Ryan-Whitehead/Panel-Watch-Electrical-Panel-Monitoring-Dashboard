"""
fault_detector.py — Stateless fault classification for electrical panel readings.

Engineering rationale
---------------------
In real industrial protection systems, measurement algorithms (IED firmware)
are kept strictly separate from HMI / SCADA display software.  This separation
allows the protection logic to be independently tested, audited, and replaced
without touching the display layer.  This module mirrors that pattern:

  * All detection functions are pure (stateless, no side effects).
  * Threshold values are passed as arguments so the Streamlit sidebar can
    override defaults without modifying this file.
  * FaultEvent is a typed dataclass — easy to serialize, easy to test.

Severity levels
---------------
  WARNING : Value has crossed the first (soft) threshold.  Operator attention
            recommended; load-shedding or investigation may be warranted.
  FAULT   : Value has crossed the second (hard) threshold.  Protective relay
            would trip in a real system.  Immediate action required.
"""

from dataclasses import dataclass
from datetime import datetime

import config

# ---------------------------------------------------------------------------
# FaultEvent dataclass
# ---------------------------------------------------------------------------

@dataclass
class FaultEvent:
    """Structured record of a single fault or warning condition."""
    timestamp: datetime
    circuit:   str      # e.g. "Phase-A", "Motor-1"
    parameter: str      # "voltage", "current", or "power_factor"
    value:     float    # actual measured value
    unit:      str      # "V", "A", or "PF"
    threshold: float    # the threshold value that was crossed
    severity:  str      # "WARNING" or "FAULT"
    message:   str      # human-readable description

    def to_dict(self) -> dict:
        """Return all fields as a plain dict (timestamp as ISO string)."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "circuit":   self.circuit,
            "parameter": self.parameter,
            "value":     self.value,
            "unit":      self.unit,
            "threshold": self.threshold,
            "severity":  self.severity,
            "message":   self.message,
        }


# ---------------------------------------------------------------------------
# Individual parameter checks
# ---------------------------------------------------------------------------

def check_voltage(
    circuit: str,
    V_actual: float,
    V_nominal: float,
    thresholds: dict,
    timestamp: datetime,
) -> FaultEvent | None:
    """
    Check a voltage reading against under-voltage thresholds.

    Args:
        circuit:    Name of the circuit or phase (e.g. "Phase-A", "HVAC").
        V_actual:   Measured RMS voltage in volts (V).
        V_nominal:  Nominal voltage in volts (V).
        thresholds: Dict with key "voltage" containing "warn_pct" and "fault_pct"
                    as fractional multipliers (e.g. -0.10 for −10 %).
        timestamp:  Timestamp for the FaultEvent.

    Returns:
        FaultEvent if a threshold is crossed, else None.
        FAULT is returned when V_actual < fault_limit (takes priority over WARNING).
    """
    warn_limit  = V_nominal * (1.0 + thresholds["voltage"]["warn_pct"])
    fault_limit = V_nominal * (1.0 + thresholds["voltage"]["fault_pct"])

    if V_actual < fault_limit:
        return FaultEvent(
            timestamp=timestamp,
            circuit=circuit,
            parameter="voltage",
            value=round(V_actual, 2),
            unit="V",
            threshold=round(fault_limit, 2),
            severity="FAULT",
            message=(
                f"Under-voltage on {circuit}: {V_actual:.1f} V "
                f"(nominal {V_nominal:.0f} V, fault threshold {fault_limit:.1f} V)"
            ),
        )
    if V_actual < warn_limit:
        return FaultEvent(
            timestamp=timestamp,
            circuit=circuit,
            parameter="voltage",
            value=round(V_actual, 2),
            unit="V",
            threshold=round(warn_limit, 2),
            severity="WARNING",
            message=(
                f"Under-voltage on {circuit}: {V_actual:.1f} V "
                f"(nominal {V_nominal:.0f} V, warning threshold {warn_limit:.1f} V)"
            ),
        )
    return None


def check_current(
    circuit: str,
    I_actual: float,
    I_rated: float,
    thresholds: dict,
    timestamp: datetime,
) -> FaultEvent | None:
    """
    Check a current reading against over-current thresholds.

    Args:
        circuit:    Name of the circuit or phase.
        I_actual:   Measured RMS current in amps (A).
        I_rated:    Rated (nameplate) current in amps (A).
        thresholds: Dict with key "current" containing "warn_pct" and "fault_pct"
                    as multipliers of I_rated (e.g. 1.10 = 110 %).
        timestamp:  Timestamp for the FaultEvent.

    Returns:
        FaultEvent if a threshold is crossed, else None.
    """
    warn_limit  = I_rated * thresholds["current"]["warn_pct"]
    fault_limit = I_rated * thresholds["current"]["fault_pct"]

    if I_actual > fault_limit:
        return FaultEvent(
            timestamp=timestamp,
            circuit=circuit,
            parameter="current",
            value=round(I_actual, 2),
            unit="A",
            threshold=round(fault_limit, 2),
            severity="FAULT",
            message=(
                f"Over-current on {circuit}: {I_actual:.1f} A "
                f"(rated {I_rated:.0f} A, fault threshold {fault_limit:.1f} A)"
            ),
        )
    if I_actual > warn_limit:
        return FaultEvent(
            timestamp=timestamp,
            circuit=circuit,
            parameter="current",
            value=round(I_actual, 2),
            unit="A",
            threshold=round(warn_limit, 2),
            severity="WARNING",
            message=(
                f"Over-current on {circuit}: {I_actual:.1f} A "
                f"(rated {I_rated:.0f} A, warning threshold {warn_limit:.1f} A)"
            ),
        )
    return None


def check_power_factor(
    circuit: str,
    pf_actual: float,
    thresholds: dict,
    timestamp: datetime,
) -> FaultEvent | None:
    """
    Check a power-factor reading against low-PF thresholds.

    Args:
        circuit:    Name of the circuit or phase.
        pf_actual:  Measured displacement power factor (dimensionless [0, 1]).
        thresholds: Dict with key "power_factor" containing "warn" and "fault"
                    as absolute PF values.
        timestamp:  Timestamp for the FaultEvent.

    Returns:
        FaultEvent if a threshold is crossed, else None.
    """
    warn_limit  = thresholds["power_factor"]["warn"]
    fault_limit = thresholds["power_factor"]["fault"]

    if pf_actual < fault_limit:
        return FaultEvent(
            timestamp=timestamp,
            circuit=circuit,
            parameter="power_factor",
            value=round(pf_actual, 4),
            unit="PF",
            threshold=fault_limit,
            severity="FAULT",
            message=(
                f"Low power factor on {circuit}: {pf_actual:.3f} "
                f"(fault threshold {fault_limit:.3f})"
            ),
        )
    if pf_actual < warn_limit:
        return FaultEvent(
            timestamp=timestamp,
            circuit=circuit,
            parameter="power_factor",
            value=round(pf_actual, 4),
            unit="PF",
            threshold=warn_limit,
            severity="WARNING",
            message=(
                f"Low power factor on {circuit}: {pf_actual:.3f} "
                f"(warning threshold {warn_limit:.3f})"
            ),
        )
    return None


# ---------------------------------------------------------------------------
# Single-reading aggregator
# ---------------------------------------------------------------------------

def _check_all(
    circuit: str,
    V: float,
    I: float,
    pf: float,
    V_nominal: float,
    I_rated: float,
    thresholds: dict,
    timestamp: datetime,
) -> list[FaultEvent]:
    """Run all three checks and return the list of non-None results."""
    results = []
    for event in (
        check_voltage(circuit, V, V_nominal, thresholds, timestamp),
        check_current(circuit, I, I_rated, thresholds, timestamp),
        check_power_factor(circuit, pf, thresholds, timestamp),
    ):
        if event is not None:
            results.append(event)
    return results


def detect_faults(
    reading: dict,
    V_nominal: float,
    I_rated: float,
    thresholds: dict,
) -> list[FaultEvent]:
    """
    Detect faults in a single reading dict.

    Handles two dict formats:
      - Phase reading: keys phase_A_V, phase_A_I, phase_A_PF, etc.
                       → runs all 3 checks for each of phases A, B, C.
      - Circuit reading: keys circuit_name, voltage_V, current_A, power_factor
                         → runs all 3 checks once.

    Args:
        reading:    Dict produced by simulator.generate_phase_readings() or
                    one element of simulator.generate_circuit_readings().
        V_nominal:  Nominal voltage in volts.
        I_rated:    Rated current in amps.
        thresholds: Threshold dict (see check_* functions for structure).

    Returns:
        Flat list of FaultEvents (may be empty).
    """
    ts = reading.get("timestamp", datetime.now())
    events: list[FaultEvent] = []

    if "circuit_name" in reading:
        # --- circuit reading ---
        events.extend(
            _check_all(
                circuit=reading["circuit_name"],
                V=reading["voltage_V"],
                I=reading["current_A"],
                pf=reading["power_factor"],
                V_nominal=V_nominal,
                I_rated=I_rated,
                thresholds=thresholds,
                timestamp=ts,
            )
        )
    else:
        # --- phase bus reading ---
        for phase, suffix in (("Phase-A", "A"), ("Phase-B", "B"), ("Phase-C", "C")):
            events.extend(
                _check_all(
                    circuit=phase,
                    V=reading[f"phase_{suffix}_V"],
                    I=reading[f"phase_{suffix}_I"],
                    pf=reading[f"phase_{suffix}_PF"],
                    V_nominal=V_nominal,
                    I_rated=I_rated,
                    thresholds=thresholds,
                    timestamp=ts,
                )
            )
    return events


# ---------------------------------------------------------------------------
# Batch aggregator
# ---------------------------------------------------------------------------

def detect_faults_batch(
    readings: list[dict],
    thresholds: dict,
    circuits_config: list[dict],
) -> list[FaultEvent]:
    """
    Detect faults across a mixed list of phase and circuit readings.

    For circuit readings the rated current and nominal voltage are looked up
    from circuits_config by matching circuit_name.  For phase readings,
    config.PHASE_RATED_CURRENT_A and config.V_LINE_TO_NEUTRAL are used.

    Args:
        readings:        List of reading dicts (phase or circuit format).
        thresholds:      Threshold dict.
        circuits_config: List of circuit dicts from config.CIRCUITS.

    Returns:
        Flat list of all FaultEvents across all readings.
    """
    circuit_map: dict[str, dict] = {c["name"]: c for c in circuits_config}
    events: list[FaultEvent] = []

    for reading in readings:
        if "circuit_name" in reading:
            cname = reading["circuit_name"]
            cdef  = circuit_map.get(cname, {})
            I_rated  = cdef.get("rated_current_A", config.PHASE_RATED_CURRENT_A)
            V_nominal = config.V_LINE_TO_NEUTRAL
        else:
            I_rated   = config.PHASE_RATED_CURRENT_A
            V_nominal = config.V_LINE_TO_NEUTRAL

        events.extend(detect_faults(reading, V_nominal, I_rated, thresholds))

    return events
