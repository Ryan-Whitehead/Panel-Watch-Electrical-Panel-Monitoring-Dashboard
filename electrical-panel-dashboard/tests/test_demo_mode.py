"""
tests/test_demo_mode.py

Unit tests for demo_mode.py.

Coverage
--------
DemoState
  - default values after construction
  - current_step_info returns correct DEMO_STEPS entry
  - is_complete is False before MAX_STEP, True at MAX_STEP
  - progress_label format

reset_demo_state()
  - returns step=0, demo_mode_active=False, empty notes
  - returns a new object (does not mutate caller)

advance_step()
  - increments step by 1
  - clamps at MAX_STEP (no overshoot)
  - preserves demo_mode_active
  - preserves notes
  - does not mutate the passed state

set_demo_mode()
  - sets demo_mode_active=True
  - sets demo_mode_active=False
  - preserves step and notes

Demo Mode / BuildingSimulator interaction
  - demo_mode=False → background injection probability unchanged
  - demo_mode=True  → background injection never fires (over many ticks)
  - manual injection still fires in demo_mode=True
  - P-07 overcurrent injection crosses fault threshold reliably
"""

from unittest.mock import patch

import config
from building_simulator import BuildingSimulator
from demo_mode import (
    DEMO_STEPS,
    MAX_STEP,
    DemoState,
    advance_step,
    reset_demo_state,
    set_demo_mode,
)

# ---------------------------------------------------------------------------
# DemoState defaults
# ---------------------------------------------------------------------------

class TestDemoStateDefaults:
    def test_default_step_is_zero(self):
        ds = DemoState()
        assert ds.step == 0

    def test_default_demo_mode_inactive(self):
        ds = DemoState()
        assert ds.demo_mode_active is False

    def test_default_notes_empty(self):
        ds = DemoState()
        assert ds.notes == {}

    def test_current_step_info_returns_dict(self):
        ds = DemoState()
        info = ds.current_step_info
        assert isinstance(info, dict)

    def test_current_step_info_step_zero(self):
        ds = DemoState(step=0)
        assert ds.current_step_info["step"] == 0

    def test_current_step_info_step_three(self):
        ds = DemoState(step=3)
        assert ds.current_step_info["step"] == 3

    def test_is_complete_false_at_step_zero(self):
        ds = DemoState(step=0)
        assert ds.is_complete is False

    def test_is_complete_false_at_step_four(self):
        ds = DemoState(step=4)
        assert ds.is_complete is False

    def test_is_complete_true_at_max_step(self):
        ds = DemoState(step=MAX_STEP)
        assert ds.is_complete is True

    def test_progress_label_step_zero(self):
        ds = DemoState(step=0)
        assert "1" in ds.progress_label
        assert "6" in ds.progress_label

    def test_progress_label_step_five(self):
        ds = DemoState(step=5)
        assert "6" in ds.progress_label


# ---------------------------------------------------------------------------
# DEMO_STEPS list structure
# ---------------------------------------------------------------------------

class TestDemoSteps:
    def test_demo_steps_count(self):
        assert len(DEMO_STEPS) == MAX_STEP + 1

    def test_all_steps_have_required_keys(self):
        required = {"step", "label", "instruction", "action"}
        for entry in DEMO_STEPS:
            assert required.issubset(set(entry.keys())), f"Missing keys in step {entry}"

    def test_step_indices_sequential(self):
        for i, entry in enumerate(DEMO_STEPS):
            assert entry["step"] == i

    def test_actions_are_known_values(self):
        known = {"clear_injections", "inject_overcurrent", "observe", "clear_injection", "done"}
        for entry in DEMO_STEPS:
            assert entry["action"] in known, f"Unknown action: {entry['action']}"


# ---------------------------------------------------------------------------
# reset_demo_state()
# ---------------------------------------------------------------------------

class TestResetDemoState:
    def test_returns_demo_state(self):
        result = reset_demo_state()
        assert isinstance(result, DemoState)

    def test_step_is_zero(self):
        result = reset_demo_state()
        assert result.step == 0

    def test_demo_mode_inactive(self):
        result = reset_demo_state()
        assert result.demo_mode_active is False

    def test_notes_empty(self):
        result = reset_demo_state()
        assert result.notes == {}

    def test_does_not_mutate_caller(self):
        original = DemoState(step=3, demo_mode_active=True, notes={"x": "y"})
        reset_demo_state()
        # original must be unchanged
        assert original.step == 3
        assert original.demo_mode_active is True


# ---------------------------------------------------------------------------
# advance_step()
# ---------------------------------------------------------------------------

class TestAdvanceStep:
    def test_increments_step(self):
        ds = DemoState(step=0)
        result = advance_step(ds)
        assert result.step == 1

    def test_increments_from_middle(self):
        ds = DemoState(step=3)
        result = advance_step(ds)
        assert result.step == 4

    def test_clamps_at_max_step(self):
        ds = DemoState(step=MAX_STEP)
        result = advance_step(ds)
        assert result.step == MAX_STEP

    def test_clamp_does_not_overshoot(self):
        ds = DemoState(step=MAX_STEP)
        result = advance_step(advance_step(ds))
        assert result.step == MAX_STEP

    def test_preserves_demo_mode_active(self):
        ds = DemoState(step=1, demo_mode_active=True)
        result = advance_step(ds)
        assert result.demo_mode_active is True

    def test_preserves_notes(self):
        ds = DemoState(step=1, notes={"P-07::current": "warm breaker"})
        result = advance_step(ds)
        assert result.notes == {"P-07::current": "warm breaker"}

    def test_does_not_mutate_original(self):
        ds = DemoState(step=2)
        advance_step(ds)
        assert ds.step == 2   # original unchanged


# ---------------------------------------------------------------------------
# set_demo_mode()
# ---------------------------------------------------------------------------

class TestSetDemoMode:
    def test_enables_demo_mode(self):
        ds = DemoState(demo_mode_active=False)
        result = set_demo_mode(ds, True)
        assert result.demo_mode_active is True

    def test_disables_demo_mode(self):
        ds = DemoState(demo_mode_active=True)
        result = set_demo_mode(ds, False)
        assert result.demo_mode_active is False

    def test_preserves_step(self):
        ds = DemoState(step=3)
        result = set_demo_mode(ds, True)
        assert result.step == 3

    def test_preserves_notes(self):
        ds = DemoState(notes={"k": "v"})
        result = set_demo_mode(ds, True)
        assert result.notes == {"k": "v"}

    def test_does_not_mutate_original(self):
        ds = DemoState(demo_mode_active=False)
        set_demo_mode(ds, True)
        assert ds.demo_mode_active is False


# ---------------------------------------------------------------------------
# BuildingSimulator demo_mode interaction
# ---------------------------------------------------------------------------

class TestBuildingSimulatorDemoMode:
    """
    Test that the demo_mode flag in BuildingSimulator.step() correctly suppresses
    background random fault injection while keeping manual injection working.

    Strategy: patch numpy.random.random to always return a value BELOW the
    FAULT_INJECT_PROBABILITY threshold (0.04).  In production mode this guarantees
    a background fault every tick; in demo_mode=True it should still be suppressed.
    """

    def _run_steps(self, n: int, demo_mode: bool) -> list:
        """Run n ticks and return all fault events."""
        sim = BuildingSimulator()
        all_events = []
        # Patch random so background injection would fire every tick if allowed.
        with patch("building_simulator.np.random.random", return_value=0.0):
            with patch(
                "building_simulator.np.random.choice",
                return_value="overcurrent",
            ):
                for _ in range(n):
                    events = sim.step(
                        paused=False,
                        thresholds=config.THRESHOLDS,
                        demo_mode=demo_mode,
                    )
                    all_events.extend(events)
        return all_events

    def test_demo_mode_false_background_fires(self):
        """With demo_mode=False and random forced to 0.0, faults should appear."""
        events = self._run_steps(5, demo_mode=False)
        assert len(events) > 0

    def test_demo_mode_true_background_suppressed(self):
        """
        With demo_mode=True the background probabilistic fault SCENARIO is
        suppressed.  Natural Gaussian noise may still produce events (e.g.
        panels whose nominal PF is near the warning boundary), but the
        deterministic overcurrent/undervoltage/low_pf injection that the
        background path would have chosen must not fire.

        Strategy: patch np.random.choice to return 'overcurrent' and
        np.random.random to 0.0 (always below threshold).  In production mode
        this forces an overcurrent scenario every tick for every panel; in
        demo_mode the elif branch is never reached so np.random.choice is
        never called.  We assert that no FAULT-severity current events appear
        (overcurrent is the only way to produce those without a manual injection).
        """
        sim = BuildingSimulator()
        fault_current_events = []
        with patch("building_simulator.np.random.random", return_value=0.0):
            with patch(
                "building_simulator.np.random.choice",
                return_value="overcurrent",
            ):
                for _ in range(5):
                    events = sim.step(
                        paused=False,
                        thresholds=config.THRESHOLDS,
                        demo_mode=True,
                    )
                    fault_current_events.extend(
                        e for e in events if e.parameter == "current" and e.severity == "FAULT"
                    )
        # No manual injections set → zero current FAULT events expected
        assert len(fault_current_events) == 0, (
            "Expected no FAULT-severity current events: background overcurrent "
            "injection should be suppressed in demo_mode=True"
        )

    def test_manual_injection_still_fires_in_demo_mode(self):
        """Manual injection must work regardless of demo_mode flag."""
        sim = BuildingSimulator()
        sim.inject_fault("P-07", "overcurrent")
        events = sim.step(
            paused=False,
            thresholds=config.THRESHOLDS,
            demo_mode=True,
        )
        panel_events = [e for e in events if "P-07" in e.circuit]
        assert len(panel_events) > 0

    def test_p07_overcurrent_crosses_fault_threshold(self):
        """
        P-07 overcurrent injection must produce at least one FAULT-severity
        current event — not just a WARNING.

        Engineering basis: the injection sets current to 135 % of rated, which
        exceeds the 125 % FAULT threshold defined in config.THRESHOLDS.
        """
        sim = BuildingSimulator()
        sim.inject_fault("P-07", "overcurrent")
        events = sim.step(
            paused=False,
            thresholds=config.THRESHOLDS,
            demo_mode=True,
        )
        current_faults = [
            e for e in events
            if "P-07" in e.circuit and e.parameter == "current" and e.severity == "FAULT"
        ]
        assert len(current_faults) > 0, (
            "Expected at least one FAULT-severity current event on P-07 after overcurrent injection"
        )

    def test_maintenance_priority_high_for_p07_overcurrent(self):
        """
        After a P-07 overcurrent FAULT, the maintenance queue must contain
        a HIGH-priority item for P-07::current.
        """
        from maintenance import MaintenanceQueue

        sim = BuildingSimulator()
        mq = MaintenanceQueue()
        sim.inject_fault("P-07", "overcurrent")
        events = sim.step(
            paused=False,
            thresholds=config.THRESHOLDS,
            demo_mode=True,
        )
        mq.update_from_fault_events(events, sim.registry)
        item = mq._items.get("P-07::current")
        assert item is not None, "Expected P-07::current in maintenance queue"
        assert item.priority == "HIGH"
