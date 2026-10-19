"""
demo_mode.py — Deterministic demonstration mode for PanelWatch.

Purpose
-------
Provides a repeatable, background-noise-free presentation environment for the
Guided Maintenance Demonstration.  When Demo Mode is active the
BuildingSimulator suppresses its 4 % probabilistic background fault injection
so that only manually injected faults appear during the demonstration.

This module is pure Python (no Streamlit dependency) so it can be fully
unit-tested without a running Streamlit server.

Classes
-------
DemoState
    Lightweight dataclass that holds the demo's step counter and the
    demo_mode_active flag.  It is stored in Streamlit session state and
    serialises trivially to plain Python types.

Functions
---------
reset_demo_state() -> DemoState
    Return a fresh DemoState with step 0 and demo_mode_active=False.

advance_step(state) -> DemoState
    Return a new DemoState with step incremented by 1 (clamped at MAX_STEP).

DEMO_STEPS
    Ordered list of (label, instruction) pairs describing each step.
    Used by the UI to show the current step and what the technician should do.

Engineering note
----------------
Separating demo state from the production simulation prevents demo resets from
affecting the persistent fault_log.csv.  The BuildingSimulator and
MaintenanceQueue objects are re-initialised on "Reset Demo Environment" but
the CSV log is intentionally left untouched so production-style records are
not erased without explicit user action.
"""

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Step definitions
# ---------------------------------------------------------------------------

MAX_STEP: int = 5   # Steps 0–5 (6 total)

# DEMO_STEPS contains static template text.  The demo panel ID is resolved
# dynamically at render time via build_demo_steps(panel_id).
DEMO_STEPS_TEMPLATE: list = [
    {
        "step": 0,
        "label": "Step 1 — Normal Operation",
        "instruction_template": (
            "All panels are operating normally. "
            "Building Overview shows all NORMAL panels. "
            "Maintenance Queue has no active faults. "
            "Click **▶ Next** to inject an overcurrent fault into **{panel_id}**."
        ),
        "action": "clear_injections",
    },
    {
        "step": 1,
        "label": "Step 2 — Inject Overcurrent",
        "instruction_template": (
            "Overcurrent fault injected into **{panel_id}** ({panel_label}). "
            "Switch to 🏢 **Building Overview** and watch **{panel_id}** turn FAULT (red). "
            "The simulated current will exceed 125 % of rated on all three phases."
        ),
        "action": "inject_overcurrent",
    },
    {
        "step": 2,
        "label": "Step 3 — Fault Classification",
        "instruction_template": (
            "🛠️ Open the **Maintenance Queue** tab. "
            "A HIGH-priority item for **{panel_id}::current** should have appeared automatically. "
            "It shows the measured current, rated current, fault threshold, and severity."
        ),
        "action": "observe",
    },
    {
        "step": 3,
        "label": "Step 4 — Acknowledge Fault",
        "instruction_template": (
            "In the **Maintenance Queue** tab, select **{panel_id}::current** from the dropdown "
            "and click **✅ Acknowledge**. "
            "Add a note such as *'Checked breaker — scheduling load review'*. "
            "Acknowledging does NOT clear the electrical fault condition."
        ),
        "action": "observe",
    },
    {
        "step": 4,
        "label": "Step 5 — Restore Normal Operation",
        "instruction_template": (
            "The fault injection on **{panel_id}** has been cleared. "
            "**{panel_id}** will return to NORMAL on the next simulation tick. "
            "The maintenance item priority drops to LOW (resolved) but the "
            "acknowledgement and notes are preserved."
        ),
        "action": "clear_injection",
    },
    {
        "step": 5,
        "label": "Step 6 — Review Maintenance History",
        "instruction_template": (
            "Demonstration complete ✅  "
            "The maintenance record for **{panel_id}::current** is now LOW priority (resolved). "
            "The technician note and acknowledgement timestamp are retained. "
            "Use the **Export Maintenance Report** button in the Maintenance Queue tab "
            "to download a full CSV report."
        ),
        "action": "done",
    },
]


def build_demo_steps(panel_id: str, panel_label: str = "") -> list:
    """
    Build the DEMO_STEPS list with the given panel_id and label substituted.

    Parameters
    ----------
    panel_id : str
        Panel identifier used as the demonstration target (e.g. "P-01").
    panel_label : str
        Short descriptive label shown in step 2 (e.g. "Floor 1 — Main Service Entrance").
        Defaults to panel_id if not provided.

    Returns
    -------
    list[dict]
        Six-element list of step dicts with 'instruction' key populated.
    """
    if not panel_label:
        panel_label = panel_id
    steps = []
    for template in DEMO_STEPS_TEMPLATE:
        step = dict(template)
        step["instruction"] = template["instruction_template"].format(
            panel_id=panel_id,
            panel_label=panel_label,
        )
        steps.append(step)
    return steps


# Keep DEMO_STEPS as a convenience alias using the default panel (P-01).
# app.py always calls build_demo_steps() with the current demo panel.
DEMO_STEPS: list = build_demo_steps("P-01")


# ---------------------------------------------------------------------------
# DemoState dataclass
# ---------------------------------------------------------------------------

@dataclass
class DemoState:
    """
    Lightweight state object for the guided maintenance demonstration.

    Attributes
    ----------
    step : int
        Current step index (0 = first step, 5 = final step).
    demo_mode_active : bool
        When True the BuildingSimulator suppresses background probabilistic
        fault injection so only manually injected faults appear.
    demo_panel_id : str
        The panel targeted by the current demonstration run.
        Set when the demo environment is initialised or reset.
    """

    step: int = 0
    demo_mode_active: bool = False
    notes: dict = field(default_factory=dict)
    demo_panel_id: str = "P-01"

    @property
    def current_step_info(self) -> dict:
        """Return the current step dict with instruction rendered for demo_panel_id."""
        steps = build_demo_steps(self.demo_panel_id)
        return steps[self.step]

    @property
    def is_complete(self) -> bool:
        """True when the scenario has reached the final step."""
        return self.step >= MAX_STEP

    @property
    def progress_label(self) -> str:
        """Short string suitable for a UI progress indicator."""
        return f"Step {self.step + 1} / {MAX_STEP + 1}"


# ---------------------------------------------------------------------------
# Pure helper functions (easy to unit-test)
# ---------------------------------------------------------------------------

def reset_demo_state() -> DemoState:
    """
    Return a completely fresh DemoState.

    Does NOT touch:
    - fault_log.csv
    - The single-panel SimulatorHistory
    - Single-panel energy accumulators

    The caller (app.py) is responsible for re-creating the BuildingSimulator
    and MaintenanceQueue objects if a full environment reset is requested.

    Returns
    -------
    DemoState
        step=0, demo_mode_active=False, notes={}
    """
    return DemoState(step=0, demo_mode_active=False, notes={})


def advance_step(state: DemoState) -> DemoState:
    """
    Return a new DemoState with step incremented by 1 (clamped at MAX_STEP).

    Parameters
    ----------
    state : DemoState
        Current demo state.

    Returns
    -------
    DemoState
        New state with step = min(state.step + 1, MAX_STEP).
        demo_mode_active and notes are preserved.
    """
    new_step = min(state.step + 1, MAX_STEP)
    return DemoState(
        step=new_step,
        demo_mode_active=state.demo_mode_active,
        notes=dict(state.notes),
        demo_panel_id=state.demo_panel_id,
    )


def set_demo_mode(state: DemoState, active: bool) -> DemoState:
    """
    Return a new DemoState with demo_mode_active set to *active*.

    Parameters
    ----------
    state : DemoState
        Current demo state.
    active : bool
        New value for demo_mode_active.

    Returns
    -------
    DemoState
        New state with demo_mode_active=active, step, notes, and
        demo_panel_id preserved.
    """
    return DemoState(
        step=state.step,
        demo_mode_active=active,
        notes=dict(state.notes),
        demo_panel_id=state.demo_panel_id,
    )
