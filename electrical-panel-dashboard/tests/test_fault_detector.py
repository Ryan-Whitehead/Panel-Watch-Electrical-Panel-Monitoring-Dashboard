"""
tests/test_fault_detector.py

Unit tests for fault_detector.py.
Tests cover: nominal (no fault), warning boundary, fault boundary,
between-threshold, batch detection, and mixed-format readings.
"""

from datetime import datetime

import config
from fault_detector import (
    FaultEvent,
    check_current,
    check_power_factor,
    check_voltage,
    detect_faults,
    detect_faults_batch,
)

TEST_TIMESTAMP = datetime(2024, 1, 15, 10, 30, 0)
THRESHOLDS = config.THRESHOLDS   # shorthand

# Convenience limits
V_NOM  = config.V_LINE_TO_NEUTRAL          # 277 V
I_RATED = config.PHASE_RATED_CURRENT_A     # 200 A
WARN_V  = V_NOM  * (1 + THRESHOLDS["voltage"]["warn_pct"])    # 249.3 V
FAULT_V = V_NOM  * (1 + THRESHOLDS["voltage"]["fault_pct"])   # 235.45 V
WARN_I  = I_RATED * THRESHOLDS["current"]["warn_pct"]          # 220 A
FAULT_I = I_RATED * THRESHOLDS["current"]["fault_pct"]         # 250 A
WARN_PF  = THRESHOLDS["power_factor"]["warn"]                   # 0.85
FAULT_PF = THRESHOLDS["power_factor"]["fault"]                  # 0.75


# ---------------------------------------------------------------------------
# check_voltage
# ---------------------------------------------------------------------------

class TestCheckVoltage:
    def test_nominal_no_fault(self):
        assert check_voltage("Phase-A", V_NOM, V_NOM, THRESHOLDS, TEST_TIMESTAMP) is None

    def test_just_above_warn_threshold(self):
        # 91 % of nominal is above the 90 % warning limit → no fault
        V = V_NOM * 0.91
        assert check_voltage("Phase-A", V, V_NOM, THRESHOLDS, TEST_TIMESTAMP) is None

    def test_at_warn_threshold(self):
        # Strictly below the warning limit → WARNING
        V = WARN_V - 0.1
        event = check_voltage("Phase-A", V, V_NOM, THRESHOLDS, TEST_TIMESTAMP)
        assert event is not None
        assert event.severity == "WARNING"

    def test_below_warn_above_fault(self):
        # Between warning and fault limits → WARNING (not FAULT)
        V = (WARN_V + FAULT_V) / 2.0
        event = check_voltage("Phase-A", V, V_NOM, THRESHOLDS, TEST_TIMESTAMP)
        assert event is not None
        assert event.severity == "WARNING"

    def test_at_fault_threshold(self):
        V = FAULT_V - 0.1
        event = check_voltage("Phase-A", V, V_NOM, THRESHOLDS, TEST_TIMESTAMP)
        assert event is not None
        assert event.severity == "FAULT"

    def test_severely_under(self):
        event = check_voltage("Phase-A", 220.0, V_NOM, THRESHOLDS, TEST_TIMESTAMP)
        assert event is not None
        assert event.severity == "FAULT"

    def test_return_type(self):
        V = FAULT_V - 1.0
        event = check_voltage("Phase-A", V, V_NOM, THRESHOLDS, TEST_TIMESTAMP)
        assert isinstance(event, FaultEvent)

    def test_severity_field(self):
        V = FAULT_V - 1.0
        event = check_voltage("Phase-A", V, V_NOM, THRESHOLDS, TEST_TIMESTAMP)
        assert event.severity == "FAULT"

    def test_circuit_field(self):
        V = FAULT_V - 1.0
        event = check_voltage("Phase-A", V, V_NOM, THRESHOLDS, TEST_TIMESTAMP)
        assert event.circuit == "Phase-A"

    def test_parameter_field(self):
        V = FAULT_V - 1.0
        event = check_voltage("Phase-A", V, V_NOM, THRESHOLDS, TEST_TIMESTAMP)
        assert event.parameter == "voltage"


# ---------------------------------------------------------------------------
# check_current
# ---------------------------------------------------------------------------

class TestCheckCurrent:
    def test_nominal_no_fault(self):
        assert check_current("Phase-A", 160.0, I_RATED, THRESHOLDS, TEST_TIMESTAMP) is None

    def test_at_warn_threshold(self):
        I = WARN_I + 0.1
        event = check_current("Phase-A", I, I_RATED, THRESHOLDS, TEST_TIMESTAMP)
        assert event is not None
        assert event.severity == "WARNING"

    def test_above_warn_below_fault(self):
        I = (WARN_I + FAULT_I) / 2.0
        event = check_current("Phase-A", I, I_RATED, THRESHOLDS, TEST_TIMESTAMP)
        assert event is not None
        assert event.severity == "WARNING"

    def test_at_fault_threshold(self):
        I = FAULT_I + 0.1
        event = check_current("Phase-A", I, I_RATED, THRESHOLDS, TEST_TIMESTAMP)
        assert event is not None
        assert event.severity == "FAULT"

    def test_well_above(self):
        event = check_current("Phase-A", 300.0, I_RATED, THRESHOLDS, TEST_TIMESTAMP)
        assert event is not None
        assert event.severity == "FAULT"

    def test_zero_current(self):
        assert check_current("Phase-A", 0.0, I_RATED, THRESHOLDS, TEST_TIMESTAMP) is None


# ---------------------------------------------------------------------------
# check_power_factor
# ---------------------------------------------------------------------------

class TestCheckPowerFactor:
    def test_nominal_no_fault(self):
        assert check_power_factor("Phase-A", 0.90, THRESHOLDS, TEST_TIMESTAMP) is None

    def test_at_warn_threshold(self):
        pf = WARN_PF - 0.001
        event = check_power_factor("Phase-A", pf, THRESHOLDS, TEST_TIMESTAMP)
        assert event is not None
        assert event.severity == "WARNING"

    def test_between_thresholds(self):
        pf = (WARN_PF + FAULT_PF) / 2.0
        event = check_power_factor("Phase-A", pf, THRESHOLDS, TEST_TIMESTAMP)
        assert event is not None
        assert event.severity == "WARNING"

    def test_at_fault_threshold(self):
        pf = FAULT_PF - 0.001
        event = check_power_factor("Phase-A", pf, THRESHOLDS, TEST_TIMESTAMP)
        assert event is not None
        assert event.severity == "FAULT"

    def test_below_fault(self):
        event = check_power_factor("Phase-A", 0.65, THRESHOLDS, TEST_TIMESTAMP)
        assert event is not None
        assert event.severity == "FAULT"

    def test_unity_pf(self):
        assert check_power_factor("Phase-A", 1.0, THRESHOLDS, TEST_TIMESTAMP) is None


# ---------------------------------------------------------------------------
# detect_faults (single reading)
# ---------------------------------------------------------------------------

def _clean_phase_reading() -> dict:
    """Return a fully nominal phase reading."""
    return {
        "timestamp": TEST_TIMESTAMP,
        "simulated": True,
        "phase_A_V": V_NOM, "phase_B_V": V_NOM, "phase_C_V": V_NOM,
        "phase_A_I": 160.0, "phase_B_I": 160.0, "phase_C_I": 160.0,
        "phase_A_PF": 0.90, "phase_B_PF": 0.90, "phase_C_PF": 0.90,
    }


class TestDetectFaults:
    def test_clean_phase_reading(self):
        events = detect_faults(_clean_phase_reading(), V_NOM, I_RATED, THRESHOLDS)
        assert events == []

    def test_overcurrent_phase(self):
        reading = _clean_phase_reading()
        reading["phase_A_I"] = FAULT_I + 10.0   # well above fault limit
        events = detect_faults(reading, V_NOM, I_RATED, THRESHOLDS)
        fault_events = [e for e in events if e.severity == "FAULT" and e.circuit == "Phase-A"]
        assert len(fault_events) >= 1

    def test_undervoltage_circuit(self):
        reading = {
            "timestamp":       TEST_TIMESTAMP,
            "simulated":       True,
            "circuit_name":    "HVAC",
            "voltage_V":       230.0,        # well below warn threshold
            "current_A":       28.0,
            "power_factor":    0.87,
            "rated_current_A": 40.0,
        }
        events = detect_faults(reading, V_NOM, 40.0, THRESHOLDS)
        v_events = [e for e in events if e.parameter == "voltage"]
        assert len(v_events) >= 1

    def test_circuit_reading_format(self):
        reading = {
            "timestamp":       TEST_TIMESTAMP,
            "simulated":       True,
            "circuit_name":    "Motor-1",
            "voltage_V":       FAULT_V - 5.0,  # fault voltage
            "current_A":       25.0,
            "power_factor":    0.92,
            "rated_current_A": 30.0,
        }
        events = detect_faults(reading, V_NOM, 30.0, THRESHOLDS)
        assert all(e.circuit == "Motor-1" for e in events)


# ---------------------------------------------------------------------------
# detect_faults_batch
# ---------------------------------------------------------------------------

def _clean_circuit_readings() -> list[dict]:
    """Return 8 fully nominal circuit readings (all PF safely above 0.85)."""
    readings = []
    for circuit in config.CIRCUITS:
        readings.append({
            "timestamp":       TEST_TIMESTAMP,
            "simulated":       True,
            "circuit_name":    circuit["name"],
            "voltage_V":       V_NOM,
            "current_A":       circuit["rated_current_A"] * 0.70,
            "power_factor":    0.92,            # safely above 0.85 WARNING threshold
            "rated_current_A": circuit["rated_current_A"],
        })
    return readings


class TestDetectFaultsBatch:
    def test_empty_list(self):
        assert detect_faults_batch([], THRESHOLDS, config.CIRCUITS) == []

    def test_all_nominal(self):
        readings = _clean_circuit_readings()
        events = detect_faults_batch(readings, THRESHOLDS, config.CIRCUITS)
        assert events == []

    def test_mixed(self):
        readings = _clean_circuit_readings()
        # Inject overcurrent into Motor-2
        for r in readings:
            if r["circuit_name"] == "Motor-2":
                r["current_A"] = FAULT_I + 50.0
        events = detect_faults_batch(readings, THRESHOLDS, config.CIRCUITS)
        motor2_faults = [e for e in events if e.circuit == "Motor-2" and e.severity == "FAULT"]
        assert len(motor2_faults) >= 1

    def test_count(self):
        # 8 nominal readings → 0 faults
        readings = _clean_circuit_readings()
        events = detect_faults_batch(readings, THRESHOLDS, config.CIRCUITS)
        assert len(events) == 0

        # One circuit with severe overcurrent → at least 1 fault
        readings[0]["current_A"] = FAULT_I + 100.0
        events_with_fault = detect_faults_batch(readings, THRESHOLDS, config.CIRCUITS)
        assert len(events_with_fault) >= 1
