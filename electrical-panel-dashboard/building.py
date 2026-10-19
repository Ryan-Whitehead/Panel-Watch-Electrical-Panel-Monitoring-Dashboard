"""
building.py — Building-wide panel model.

Defines the data structures that represent a single electrical panel in the
building.  All classes are pure Python (no Streamlit / Pandas dependencies)
so they can be unit-tested and imported by any module.

Classes
-------
PanelDefinition
    Immutable description of a panel: where it is and what it is rated for.
    Built from config.BUILDING_PANELS entries.

PanelReading
    One snapshot of three-phase measurements for a panel.

PanelState
    Live mutable state for one panel: latest reading, history ring-buffer,
    accumulated energy, fault status, and the monotonic clock for the
    energy meter.

Registry helpers
----------------
build_registry(panels_config)
    Construct an ordered dict of {panel_id: PanelState} from config.

get_panel(registry, panel_id)
    Safe lookup with KeyError on unknown ID.

panels_by_floor(registry)
    Return {floor: [PanelState, ...]} grouped dict.
"""

import collections
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import config

# ---------------------------------------------------------------------------
# PanelDefinition — static description of a panel (immutable after creation)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PanelDefinition:
    """
    Immutable description of one electrical panel in the building.

    Attributes
    ----------
    panel_id : str
        Unique identifier, e.g. "P-07".
    floor : int
        Floor number where the panel is installed.
    location : str
        Human-readable location description.
    v_line_to_line : float
        Nominal line-to-line voltage (V).
    v_line_to_neutral : float
        Nominal line-to-neutral voltage (V).
    phase_rated_current_a : float
        Rated current per phase (A).
    nominal_load_pct : float
        Baseline operating load as a fraction of rated current [0, 1].
    nominal_pf : float
        Baseline operating power factor [0, 1].
    """

    panel_id: str
    floor: int
    location: str
    v_line_to_line: float
    v_line_to_neutral: float
    phase_rated_current_a: float
    nominal_load_pct: float
    nominal_pf: float

    @classmethod
    def from_config_dict(cls, d: dict) -> "PanelDefinition":
        """Construct from a config.BUILDING_PANELS entry dict."""
        return cls(
            panel_id=d["panel_id"],
            floor=d["floor"],
            location=d["location"],
            v_line_to_line=d["v_line_to_line"],
            v_line_to_neutral=d["v_line_to_neutral"],
            phase_rated_current_a=d["phase_rated_current_a"],
            nominal_load_pct=d["nominal_load_pct"],
            nominal_pf=d["nominal_pf"],
        )

    @property
    def nominal_current_a(self) -> float:
        """Nominal operating current = rated × nominal load fraction."""
        return self.phase_rated_current_a * self.nominal_load_pct

    @property
    def label(self) -> str:
        """Short display label: 'P-07 · Floor 5'."""
        return f"{self.panel_id} · Floor {self.floor}"

    @property
    def full_label(self) -> str:
        """Full display label: 'P-07 — Laboratory Suite A (Floor 5)'."""
        return f"{self.panel_id} — {self.location} (Floor {self.floor})"


# ---------------------------------------------------------------------------
# PanelReading — one measurement snapshot
# ---------------------------------------------------------------------------

@dataclass
class PanelReading:
    """
    One three-phase measurement snapshot for a panel.

    All simulated values.  The `injected` flag marks readings produced by
    deliberate fault injection (Fault Simulation Control Center) rather than
    the background probabilistic simulator.

    Electrical quantities follow the per-phase summation convention:
        P_total = P_A + P_B + P_C
        S_total = S_A + S_B + S_C
        PF_agg  = P_total / S_total
    """

    timestamp: datetime
    panel_id: str

    # Per-phase voltages (V, line-to-neutral)
    phase_a_v: float
    phase_b_v: float
    phase_c_v: float

    # Per-phase currents (A)
    phase_a_i: float
    phase_b_i: float
    phase_c_i: float

    # Per-phase power factors
    phase_a_pf: float
    phase_b_pf: float
    phase_c_pf: float

    # Derived aggregates (populated by building_simulator after generation)
    p_total_w: float = 0.0
    s_total_va: float = 0.0
    q_total_var: float = 0.0
    pf_agg: float = 0.0

    # Fault metadata
    overall_status: str = "NORMAL"   # "NORMAL", "WARNING", or "FAULT"
    injected: bool = False           # True = from Fault Simulation Control Center

    def to_phase_dict(self) -> dict:
        """
        Return a dict in the format expected by fault_detector.detect_faults()
        for a phase-bus reading.
        """
        return {
            "timestamp": self.timestamp,
            "simulated": True,
            "phase_A_V": self.phase_a_v,
            "phase_B_V": self.phase_b_v,
            "phase_C_V": self.phase_c_v,
            "phase_A_I": self.phase_a_i,
            "phase_B_I": self.phase_b_i,
            "phase_C_I": self.phase_c_i,
            "phase_A_PF": self.phase_a_pf,
            "phase_B_PF": self.phase_b_pf,
            "phase_C_PF": self.phase_c_pf,
        }


# ---------------------------------------------------------------------------
# PanelState — live mutable state for one panel
# ---------------------------------------------------------------------------

@dataclass
class PanelState:
    """
    Mutable runtime state for a single electrical panel.

    Each panel maintains its own:
    - Latest measurement snapshot (PanelReading)
    - History ring-buffer for trend charts (deque of PanelReading)
    - Accumulated energy (kWh)
    - Monotonic clock for the energy meter (None until first tick)
    - Current fault status string

    This design ensures panels have strictly independent state: a fault or
    measurement on one panel cannot affect another.

    Attributes
    ----------
    definition : PanelDefinition
        Immutable description of this panel.
    latest_reading : Optional[PanelReading]
        Most recent measurement; None before the first simulation tick.
    history : collections.deque[PanelReading]
        Ring buffer of recent readings for trend charts.
    energy_kwh : float
        Accumulated energy since the session started.
    last_tick_time : Optional[float]
        time.monotonic() at the last live tick; None after pause/startup.
    status : str
        Current operating status: "NORMAL", "WARNING", or "FAULT".
    injected_scenario : Optional[str]
        Name of the manually injected fault scenario, or None for normal
        probabilistic simulation.
    """

    definition: PanelDefinition
    latest_reading: Optional[PanelReading] = field(default=None)
    history: "collections.deque[PanelReading]" = field(
        default_factory=lambda: collections.deque(maxlen=config.HISTORY_WINDOW)
    )
    energy_kwh: float = 0.0
    last_tick_time: Optional[float] = field(default=None)
    status: str = "NORMAL"
    injected_scenario: Optional[str] = field(default=None)

    def append_reading(self, reading: PanelReading) -> None:
        """Append a new reading to history and update latest."""
        self.latest_reading = reading
        self.history.append(reading)
        self.status = reading.overall_status

    def history_as_lists(self) -> dict:
        """
        Return history as plain lists suitable for Plotly charting without
        requiring a Pandas import in this module.

        Returns a dict with keys:
            timestamps, phase_a_v, phase_b_v, phase_c_v,
            phase_a_i, phase_b_i, phase_c_i,
            phase_a_pf, phase_b_pf, phase_c_pf,
            p_total_kw
        """
        readings = list(self.history)
        return {
            "timestamps":  [r.timestamp for r in readings],
            "phase_a_v":   [r.phase_a_v for r in readings],
            "phase_b_v":   [r.phase_b_v for r in readings],
            "phase_c_v":   [r.phase_c_v for r in readings],
            "phase_a_i":   [r.phase_a_i for r in readings],
            "phase_b_i":   [r.phase_b_i for r in readings],
            "phase_c_i":   [r.phase_c_i for r in readings],
            "phase_a_pf":  [r.phase_a_pf for r in readings],
            "phase_b_pf":  [r.phase_b_pf for r in readings],
            "phase_c_pf":  [r.phase_c_pf for r in readings],
            "p_total_kw":  [r.p_total_w / 1000.0 for r in readings],
        }

    def inject_fault(self, scenario: str) -> None:
        """
        Set a deterministic fault scenario on this panel.

        The scenario name must match one of the FaultScenario enum values in
        simulator.py: 'overcurrent', 'undervoltage', 'low_power_factor'.
        Pass None to clear the injection and return to normal simulation.
        """
        self.injected_scenario = scenario

    def clear_fault_injection(self) -> None:
        """Clear any manually injected fault and return to normal simulation."""
        self.injected_scenario = None


# ---------------------------------------------------------------------------
# Registry helpers
# ---------------------------------------------------------------------------

def build_registry(panels_config: list) -> dict:
    """
    Construct an ordered dict of {panel_id: PanelState} from config.

    Args:
        panels_config: List of panel definition dicts (config.BUILDING_PANELS).

    Returns:
        Ordered dict keyed by panel_id, preserving insertion order.
    """
    registry: dict = {}
    for entry in panels_config:
        defn = PanelDefinition.from_config_dict(entry)
        registry[defn.panel_id] = PanelState(definition=defn)
    return registry


def get_panel(registry: dict, panel_id: str) -> PanelState:
    """
    Safe panel lookup.

    Raises
    ------
    KeyError
        If panel_id is not in the registry.
    """
    if panel_id not in registry:
        raise KeyError(f"Panel '{panel_id}' not found in registry. "
                       f"Known IDs: {list(registry.keys())}")
    return registry[panel_id]


def panels_by_floor(registry: dict) -> dict:
    """
    Group panels by floor number.

    Returns
    -------
    dict
        {floor_number: [PanelState, ...]} with floors in ascending order.
    """
    result: dict = {}
    for panel_state in registry.values():
        fl = panel_state.definition.floor
        result.setdefault(fl, []).append(panel_state)
    return dict(sorted(result.items()))


def building_summary(registry: dict) -> dict:
    """
    Return a high-level summary dict for the building overview header.

    Returns
    -------
    dict with keys:
        total, normal, warning, fault
    """
    total = len(registry)
    normal = sum(1 for ps in registry.values() if ps.status == "NORMAL")
    warning = sum(1 for ps in registry.values() if ps.status == "WARNING")
    fault = sum(1 for ps in registry.values() if ps.status == "FAULT")
    return {"total": total, "normal": normal, "warning": warning, "fault": fault}
