"""
building_simulator.py — Per-panel simulation engine for the building-wide monitor.

Each of the 20 building panels has strictly independent simulation state:
its own Gaussian noise stream, its own energy accumulator, and its own
monotonic clock.  A fault injected into one panel has no effect on any other.

Classes
-------
BuildingSimulator
    Holds the {panel_id: PanelState} registry and advances all panels
    forward by one tick on each call to step().

Design notes
------------
* Reuses existing calculations.py functions (sum_phase_power,
  accumulate_energy_tick) and fault_detector.detect_faults() — no new
  electrical formulas.
* Reuses simulator.FaultScenario for the fault injection API so the
  Fault Simulation Control Center can pass the same enum values.
* ALL data produced is SIMULATED.  The module-level constant
  SIMULATED_DATA = True makes this unambiguous.
"""

import time
from dataclasses import replace
from datetime import datetime
from typing import Optional

import numpy as np

import config
from building import PanelDefinition, PanelReading, build_registry
from calculations import accumulate_energy_tick, sum_phase_power
from fault_detector import detect_faults
from simulator import FaultScenario

SIMULATED_DATA: bool = True  # Always True — data never comes from real sensors.


# ---------------------------------------------------------------------------
# Noise / injection helpers
# ---------------------------------------------------------------------------

def _gaussian(mean: float, sigma: float, low: float, high: float) -> float:
    """Draw one clipped Gaussian sample."""
    return float(np.clip(np.random.normal(mean, sigma), low, high))


def _make_phase_reading(
    defn: PanelDefinition,
    timestamp: datetime,
    fault_scenario: Optional[FaultScenario],
    injected: bool,
) -> PanelReading:
    """
    Generate one three-phase measurement snapshot for a panel.

    Noise model
    -----------
    Each panel's nominal operating point is defined in config.BUILDING_PANELS
    (nominal_load_pct × phase_rated_current_a, nominal_pf).  Gaussian noise
    matching config.NOISE_* sigmas is added, then values are clipped to
    physically plausible ranges.

    Fault injection
    ---------------
    When fault_scenario is not None the named phase is pushed deterministically
    outside the detection threshold so the fault is reliably triggered.
    The injected flag is set on the returned PanelReading to distinguish
    manual injections from background probabilistic faults.
    """
    v_nom = defn.v_line_to_neutral
    i_nom = defn.nominal_current_a
    pf_nom = defn.nominal_pf

    voltages = [_gaussian(v_nom, config.NOISE_VOLTAGE_SIGMA, 200.0, 320.0) for _ in range(3)]
    currents = [_gaussian(i_nom, config.NOISE_CURRENT_SIGMA, 0.0, defn.phase_rated_current_a * 1.5) for _ in range(3)]
    pfs = [_gaussian(pf_nom, config.NOISE_PF_SIGMA, 0.70, 1.0) for _ in range(3)]

    # --- deterministic fault injection ---
    if fault_scenario == FaultScenario.OVERCURRENT:
        # Set all three phases to 135% of rated — reliably crosses the 125% FAULT threshold.
        for k in range(3):
            currents[k] = float(np.clip(defn.phase_rated_current_a * 1.35, 0.0, defn.phase_rated_current_a * 1.5))
    elif fault_scenario == FaultScenario.UNDERVOLTAGE:
        # Set all three phases to 82% of nominal — reliably below the 85% FAULT threshold.
        for k in range(3):
            voltages[k] = float(np.clip(v_nom * 0.82, 200.0, 320.0))
    elif fault_scenario == FaultScenario.LOW_POWER_FACTOR:
        # Set all three phases to 0.68 — below the 0.75 FAULT threshold.
        # NOTE: the clip range [0.70, 1.0] raises 0.68 → 0.70, which still
        # crosses the fault threshold (< 0.75) so detection is reliable.
        for k in range(3):
            pfs[k] = float(np.clip(0.68, 0.70, 1.0))

    # Aggregate power quantities via per-phase summation.
    bus = sum_phase_power([
        (voltages[0], currents[0], pfs[0]),
        (voltages[1], currents[1], pfs[1]),
        (voltages[2], currents[2], pfs[2]),
    ])

    return PanelReading(
        timestamp=timestamp,
        panel_id=defn.panel_id,
        phase_a_v=voltages[0],
        phase_b_v=voltages[1],
        phase_c_v=voltages[2],
        phase_a_i=currents[0],
        phase_b_i=currents[1],
        phase_c_i=currents[2],
        phase_a_pf=pfs[0],
        phase_b_pf=pfs[1],
        phase_c_pf=pfs[2],
        p_total_w=bus["P_total"],
        s_total_va=bus["S_total"],
        q_total_var=bus["Q_total"],
        pf_agg=bus["PF_agg"],
        injected=injected,
    )


def _classify_status(fault_events: list) -> str:
    """Return 'FAULT', 'WARNING', or 'NORMAL' from a list of FaultEvent."""
    severities = {fe.severity for fe in fault_events}
    if "FAULT" in severities:
        return "FAULT"
    if "WARNING" in severities:
        return "WARNING"
    return "NORMAL"


# ---------------------------------------------------------------------------
# BuildingSimulator
# ---------------------------------------------------------------------------

class BuildingSimulator:
    """
    Simulation engine for all 20 building panels.

    Each panel has independent state so faults, noise, and energy
    accumulation on one panel are completely isolated from all others.

    Usage
    -----
    sim = BuildingSimulator()
    faults_this_tick = sim.step(paused=False, thresholds=config.THRESHOLDS)
    state_p07 = sim.registry["P-07"]

    Attributes
    ----------
    registry : dict[str, PanelState]
        Live state keyed by panel_id.  Initialised from config.BUILDING_PANELS.
    """

    def __init__(self, panels: Optional[list] = None) -> None:
        """
        Parameters
        ----------
        panels : list[dict] | None
            Panel definition list to use.  When None (default), uses
            config.BUILDING_PANELS.  Pass a list from
            building_config.distribute_panels() to use a custom floor layout.
        """
        if panels is None:
            panels = config.BUILDING_PANELS
        self.registry: dict = build_registry(panels)

    # ------------------------------------------------------------------
    # Fault injection control
    # ------------------------------------------------------------------

    def inject_fault(self, panel_id: str, scenario: str) -> None:
        """
        Inject a deterministic fault scenario into a specific panel.

        Parameters
        ----------
        panel_id : str
            Target panel, e.g. "P-07".
        scenario : str
            One of: 'overcurrent', 'undervoltage', 'low_power_factor'.
            Pass None (as string "normal") to clear injection.

        Notes
        -----
        The injection affects only the named panel; all other panels continue
        normal probabilistic simulation.  The injected flag on each PanelReading
        produced while a fault is active is set to True so the UI can clearly
        label it as a manually injected event.
        """
        from building import get_panel
        panel = get_panel(self.registry, panel_id)
        if scenario == "normal":
            panel.clear_fault_injection()
        else:
            panel.inject_fault(scenario)

    def clear_injection(self, panel_id: str) -> None:
        """Clear any active fault injection on a panel."""
        from building import get_panel
        panel = get_panel(self.registry, panel_id)
        panel.clear_fault_injection()

    def clear_all_injections(self) -> None:
        """Clear fault injections on every panel."""
        for ps in self.registry.values():
            ps.clear_fault_injection()

    # ------------------------------------------------------------------
    # Simulation step
    # ------------------------------------------------------------------

    def step(
        self,
        paused: bool,
        thresholds: dict,
        demo_mode: bool = False,
    ) -> list:
        """
        Advance every panel by one simulation tick.

        For each panel:
        1. Generate a new three-phase reading (using the panel's individual
           noise model and any active fault injection).
        2. Run fault detection against the supplied thresholds.
        3. Accumulate energy using the monotonic clock.
        4. Append the reading to the panel's history ring-buffer.

        Parameters
        ----------
        paused : bool
            When True, readings are still generated (so the display stays
            live) but energy is not accumulated and the clock is reset.
            This matches the single-panel behaviour in app.py.
        thresholds : dict
            Threshold dict (config.THRESHOLDS or sidebar overrides).
        demo_mode : bool
            When True, suppresses the 4 % background probabilistic fault
            injection so only manually injected faults appear.  Normal
            Gaussian measurement noise is still applied so readings look
            realistic.  Default False (production behaviour unchanged).

        Returns
        -------
        list[FaultEvent]
            Flat list of all FaultEvents detected across all 20 panels
            this tick.  Empty list when all panels are normal.
        """
        now = datetime.now()
        current_time = time.monotonic()
        all_faults: list = []

        for panel_state in self.registry.values():
            defn = panel_state.definition

            # Resolve fault scenario for this panel.
            injected = False
            fault_scenario: Optional[FaultScenario] = None

            if panel_state.injected_scenario is not None:
                injected = True
                try:
                    fault_scenario = FaultScenario(panel_state.injected_scenario)
                except ValueError:
                    fault_scenario = None
            elif not demo_mode:
                # Background probabilistic fault injection (4% probability).
                # Suppressed when demo_mode=True to keep the demo deterministic.
                if float(np.random.random()) < config.FAULT_INJECT_PROBABILITY:
                    fault_scenario = FaultScenario(
                        np.random.choice([
                            FaultScenario.OVERCURRENT.value,
                            FaultScenario.UNDERVOLTAGE.value,
                            FaultScenario.LOW_POWER_FACTOR.value,
                        ])
                    )

            # Generate measurement.
            reading = _make_phase_reading(defn, now, fault_scenario, injected)

            # Run fault detection.
            fault_events = detect_faults(
                reading.to_phase_dict(),
                defn.v_line_to_neutral,
                defn.phase_rated_current_a,
                thresholds,
            )

            # Stamp each fault event with the panel_id as the circuit prefix.
            # detect_faults returns events with "Phase-A" / "Phase-B" / "Phase-C"
            # as circuit names; prefix them with the panel_id for the building log.
            prefixed_events = []
            for fe in fault_events:
                fe_prefixed = replace(
                    fe,
                    circuit=f"{defn.panel_id}/{fe.circuit}",
                    message=f"[{defn.panel_id}] {fe.message}",
                )
                prefixed_events.append(fe_prefixed)

            all_faults.extend(prefixed_events)

            # Update panel status.
            reading.overall_status = _classify_status(fault_events)
            reading.injected = injected

            # Accumulate energy.
            panel_state.energy_kwh, panel_state.last_tick_time = accumulate_energy_tick(
                energy_kwh_current=panel_state.energy_kwh,
                total_P_W=reading.p_total_w,
                paused=paused,
                last_tick_time=panel_state.last_tick_time,
                current_tick_time=current_time,
            )

            # Commit reading to history.
            panel_state.append_reading(reading)

        return all_faults

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    def panel_summaries(self) -> list:
        """
        Return a list of summary dicts, one per panel, for the building overview.

        Each dict has:
            panel_id, floor, location, status, p_total_kw, pf_agg,
            energy_kwh, injected, latest_timestamp
        """
        rows = []
        for ps in self.registry.values():
            r = ps.latest_reading
            rows.append({
                "panel_id":          ps.definition.panel_id,
                "floor":             ps.definition.floor,
                "location":          ps.definition.location,
                "status":            ps.status,
                "p_total_kw":        round(r.p_total_w / 1000.0, 2) if r else 0.0,
                "pf_agg":            round(r.pf_agg, 3) if r else 0.0,
                "energy_kwh":        round(ps.energy_kwh, 4),
                "injected":          r.injected if r else False,
                "latest_timestamp":  r.timestamp if r else None,
            })
        return rows
