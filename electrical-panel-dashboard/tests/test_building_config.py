"""
tests/test_building_config.py

Unit tests for building_config.py.

Coverage
--------
distribute_panels()
  - 1-floor building: all panels on floor 1
  - 5-floor building: even distribution, 4 panels per floor
  - 10-floor building: 2 panels per floor
  - 12-floor building (default): matches config floor assignments
  - 20-floor building: 1 panel per floor
  - 50-floor building: 20 occupied floors, floors 21–50 empty
  - 3-floor building: uneven but every floor has at least 1 panel
  - All panel_ids preserved after redistribution
  - No new panels created
  - Panel count unchanged
  - Floor values always in [1, num_floors]
  - Location string updated to include floor number
  - ValueError when num_floors < 1
  - Empty panel list returns empty list
  - Calling twice does not double-append floor suffix

active_floors()
  - Returns sorted list of occupied floor numbers
  - Empty panel list returns empty list
  - Single panel returns [floor]
  - Deduplicates floors when multiple panels share a floor

panel_ids_for_demo()
  - Returns first panel's id
  - ValueError on empty list

DemoState.demo_panel_id
  - Default is "P-01"
  - advance_step preserves demo_panel_id
  - set_demo_mode preserves demo_panel_id
  - reset_demo_state returns default demo_panel_id

build_demo_steps()
  - Returns 6 steps
  - panel_id substituted in all instruction strings
  - Works with any panel_id string

Fault injection after reconfiguration
  - Inject fault into panel on floor 1 of a 1-floor building
  - Maintenance priority HIGH after overcurrent injection

Historical fault preservation
  - Reconfiguring (new BuildingSimulator) does not erase fault_log.csv
"""

import pytest

import config
from building_config import (
    DEFAULT_NUM_FLOORS,
    _strip_floor_suffix,
    active_floors,
    distribute_panels,
    panel_ids_for_demo,
)
from building_simulator import BuildingSimulator
from demo_mode import (
    DemoState,
    advance_step,
    build_demo_steps,
    reset_demo_state,
    set_demo_mode,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

PANELS = config.BUILDING_PANELS  # 20 panels


# ---------------------------------------------------------------------------
# distribute_panels — basic properties
# ---------------------------------------------------------------------------

class TestDistributePanels:
    def test_empty_panels_returns_empty(self):
        assert distribute_panels([], 5) == []

    def test_raises_if_num_floors_zero(self):
        with pytest.raises(ValueError):
            distribute_panels(PANELS, 0)

    def test_raises_if_num_floors_negative(self):
        with pytest.raises(ValueError):
            distribute_panels(PANELS, -1)

    def test_panel_count_unchanged(self):
        result = distribute_panels(PANELS, 7)
        assert len(result) == len(PANELS)

    def test_panel_ids_preserved(self):
        result = distribute_panels(PANELS, 5)
        original_ids = [p["panel_id"] for p in PANELS]
        result_ids   = [p["panel_id"] for p in result]
        assert result_ids == original_ids

    def test_all_floors_in_range(self):
        for n in [1, 3, 5, 10, 12, 20, 50]:
            result = distribute_panels(PANELS, n)
            floors = [p["floor"] for p in result]
            assert all(1 <= f <= n for f in floors), f"Out-of-range floor for n={n}"

    def test_does_not_mutate_original(self):
        original_floor = PANELS[0]["floor"]
        distribute_panels(PANELS, 3)
        assert PANELS[0]["floor"] == original_floor

    def test_location_contains_floor_number(self):
        result = distribute_panels(PANELS[:1], 1)
        assert "Floor 1" in result[0]["location"]

    def test_no_double_floor_suffix(self):
        """Calling distribute_panels twice must not append '(Floor N)' twice."""
        once  = distribute_panels(PANELS[:1], 1)
        twice = distribute_panels(once, 1)
        location = twice[0]["location"]
        assert location.count("(Floor") == 1


# ---------------------------------------------------------------------------
# distribute_panels — 1-floor building
# ---------------------------------------------------------------------------

class TestOneFloor:
    def test_all_panels_on_floor_1(self):
        result = distribute_panels(PANELS, 1)
        assert all(p["floor"] == 1 for p in result)

    def test_panel_count(self):
        result = distribute_panels(PANELS, 1)
        assert len(result) == 20


# ---------------------------------------------------------------------------
# distribute_panels — 5-floor building
# ---------------------------------------------------------------------------

class TestFiveFloors:
    def test_four_panels_per_floor(self):
        """20 panels / 5 floors = exactly 4 per floor."""
        result = distribute_panels(PANELS, 5)
        from collections import Counter
        counts = Counter(p["floor"] for p in result)
        assert all(v == 4 for v in counts.values())

    def test_all_five_floors_occupied(self):
        result = distribute_panels(PANELS, 5)
        floors = {p["floor"] for p in result}
        assert floors == {1, 2, 3, 4, 5}


# ---------------------------------------------------------------------------
# distribute_panels — 10-floor building
# ---------------------------------------------------------------------------

class TestTenFloors:
    def test_two_panels_per_floor(self):
        result = distribute_panels(PANELS, 10)
        from collections import Counter
        counts = Counter(p["floor"] for p in result)
        assert all(v == 2 for v in counts.values())


# ---------------------------------------------------------------------------
# distribute_panels — 12-floor building (default)
# ---------------------------------------------------------------------------

class TestTwelveFloors:
    def test_floor_count_12(self):
        result = distribute_panels(PANELS, DEFAULT_NUM_FLOORS)
        floors = {p["floor"] for p in result}
        assert max(floors) == 12

    def test_all_floors_1_to_12_occupied(self):
        result = distribute_panels(PANELS, DEFAULT_NUM_FLOORS)
        floors = {p["floor"] for p in result}
        # With 20 panels across 12 floors at least floors 1–8 each get 2,
        # and floors 9–12 each get 1 (round-robin: panels 0–11 → floors 1–12,
        # panels 12–19 → floors 1–8)
        assert floors == set(range(1, 13))


# ---------------------------------------------------------------------------
# distribute_panels — 20-floor building
# ---------------------------------------------------------------------------

class TestTwentyFloors:
    def test_one_panel_per_floor(self):
        result = distribute_panels(PANELS, 20)
        from collections import Counter
        counts = Counter(p["floor"] for p in result)
        assert all(v == 1 for v in counts.values())

    def test_exactly_20_floors_occupied(self):
        result = distribute_panels(PANELS, 20)
        floors = {p["floor"] for p in result}
        assert floors == set(range(1, 21))


# ---------------------------------------------------------------------------
# distribute_panels — 50-floor building
# ---------------------------------------------------------------------------

class TestFiftyFloors:
    def test_only_20_floors_occupied(self):
        """20 panels across 50 floors → only floors 1–20 have a panel."""
        result = distribute_panels(PANELS, 50)
        floors = {p["floor"] for p in result}
        assert floors == set(range(1, 21))

    def test_floors_21_to_50_empty(self):
        result = distribute_panels(PANELS, 50)
        floors = {p["floor"] for p in result}
        for f in range(21, 51):
            assert f not in floors

    def test_panel_count_unchanged(self):
        result = distribute_panels(PANELS, 50)
        assert len(result) == 20


# ---------------------------------------------------------------------------
# distribute_panels — 3-floor building (uneven)
# ---------------------------------------------------------------------------

class TestThreeFloors:
    def test_every_floor_has_at_least_one_panel(self):
        result = distribute_panels(PANELS, 3)
        floors = {p["floor"] for p in result}
        assert floors == {1, 2, 3}

    def test_floors_differ_by_at_most_one(self):
        from collections import Counter
        result = distribute_panels(PANELS, 3)
        counts = list(Counter(p["floor"] for p in result).values())
        assert max(counts) - min(counts) <= 1


# ---------------------------------------------------------------------------
# active_floors()
# ---------------------------------------------------------------------------

class TestActiveFloors:
    def test_empty_returns_empty(self):
        assert active_floors([]) == []

    def test_single_panel(self):
        assert active_floors([{"floor": 3}]) == [3]

    def test_sorted_ascending(self):
        panels = [{"floor": 5}, {"floor": 1}, {"floor": 3}]
        assert active_floors(panels) == [1, 3, 5]

    def test_deduplicates(self):
        panels = [{"floor": 2}, {"floor": 2}, {"floor": 4}]
        assert active_floors(panels) == [2, 4]

    def test_5_floor_distribution(self):
        result = distribute_panels(PANELS, 5)
        assert active_floors(result) == [1, 2, 3, 4, 5]

    def test_50_floor_distribution_active_floors(self):
        result = distribute_panels(PANELS, 50)
        assert active_floors(result) == list(range(1, 21))


# ---------------------------------------------------------------------------
# panel_ids_for_demo()
# ---------------------------------------------------------------------------

class TestPanelIdsForDemo:
    def test_returns_first_panel_id(self):
        result = distribute_panels(PANELS, 5)
        assert panel_ids_for_demo(result) == result[0]["panel_id"]

    def test_returns_first_panel_id_any_distribution(self):
        result = distribute_panels(PANELS, 1)
        assert panel_ids_for_demo(result) == PANELS[0]["panel_id"]

    def test_empty_raises_value_error(self):
        with pytest.raises(ValueError):
            panel_ids_for_demo([])


# ---------------------------------------------------------------------------
# _strip_floor_suffix (private helper)
# ---------------------------------------------------------------------------

class TestStripFloorSuffix:
    def test_strips_suffix(self):
        assert _strip_floor_suffix("East Wing Office (Floor 3)") == "East Wing Office"

    def test_no_suffix_unchanged(self):
        assert _strip_floor_suffix("Main Service Entrance") == "Main Service Entrance"

    def test_double_suffix_stripped_once(self):
        assert _strip_floor_suffix("Lab (Floor 1) (Floor 1)") == "Lab (Floor 1)"


# ---------------------------------------------------------------------------
# DemoState dynamic panel support
# ---------------------------------------------------------------------------

class TestDemoStateDynamicPanel:
    def test_default_demo_panel_id(self):
        ds = DemoState()
        assert ds.demo_panel_id == "P-01"

    def test_advance_step_preserves_demo_panel_id(self):
        ds = DemoState(demo_panel_id="P-05")
        result = advance_step(ds)
        assert result.demo_panel_id == "P-05"

    def test_set_demo_mode_preserves_demo_panel_id(self):
        ds = DemoState(demo_panel_id="P-10")
        result = set_demo_mode(ds, True)
        assert result.demo_panel_id == "P-10"

    def test_reset_demo_state_returns_default_panel(self):
        result = reset_demo_state()
        assert result.demo_panel_id == "P-01"


# ---------------------------------------------------------------------------
# build_demo_steps() — dynamic panel substitution
# ---------------------------------------------------------------------------

class TestBuildDemoSteps:
    def test_returns_six_steps(self):
        steps = build_demo_steps("P-03")
        assert len(steps) == 6

    def test_panel_id_in_step_0_instruction(self):
        steps = build_demo_steps("P-03")
        assert "P-03" in steps[0]["instruction"]

    def test_panel_id_in_all_relevant_instructions(self):
        steps = build_demo_steps("P-15")
        for step in steps:
            if step["action"] not in ("observe", "done"):
                assert "P-15" in step["instruction"]

    def test_works_with_any_panel_id(self):
        for pid in ["P-01", "P-10", "P-20"]:
            steps = build_demo_steps(pid)
            assert len(steps) == 6
            assert pid in steps[1]["instruction"]

    def test_panel_label_in_step_1(self):
        steps = build_demo_steps("P-07", "Floor 2 — Server Room")
        assert "Floor 2 — Server Room" in steps[1]["instruction"]


# ---------------------------------------------------------------------------
# Fault injection after floor reconfiguration
# ---------------------------------------------------------------------------

class TestFaultInjectionAfterReconfiguration:
    def test_inject_on_1_floor_building(self):
        """Overcurrent injection on a 1-floor building must produce FAULT events."""
        panels = distribute_panels(PANELS, 1)
        sim    = BuildingSimulator(panels)
        first_panel = panels[0]["panel_id"]
        sim.inject_fault(first_panel, "overcurrent")
        events = sim.step(paused=False, thresholds=config.THRESHOLDS, demo_mode=True)
        current_faults = [
            e for e in events
            if first_panel in e.circuit and e.parameter == "current" and e.severity == "FAULT"
        ]
        assert len(current_faults) > 0

    def test_inject_on_5_floor_building(self):
        """Overcurrent injection after 5-floor redistribution works correctly."""
        panels = distribute_panels(PANELS, 5)
        sim    = BuildingSimulator(panels)
        target = panels[0]["panel_id"]
        sim.inject_fault(target, "overcurrent")
        events = sim.step(paused=False, thresholds=config.THRESHOLDS, demo_mode=True)
        current_faults = [
            e for e in events
            if target in e.circuit and e.parameter == "current" and e.severity == "FAULT"
        ]
        assert len(current_faults) > 0

    def test_maintenance_priority_high_after_reconfiguration(self):
        """After floor change, overcurrent still produces HIGH-priority maintenance item."""
        from maintenance import MaintenanceQueue
        panels = distribute_panels(PANELS, 3)
        sim    = BuildingSimulator(panels)
        mq     = MaintenanceQueue()
        target = panels[0]["panel_id"]
        sim.inject_fault(target, "overcurrent")
        events = sim.step(paused=False, thresholds=config.THRESHOLDS, demo_mode=True)
        mq.update_from_fault_events(events, sim.registry)
        item_key = f"{target}::current"
        assert item_key in mq._items
        assert mq._items[item_key].priority == "HIGH"

    def test_no_panel_on_invalid_floor(self):
        """After redistribution to 5 floors, no panel should be on floor 6 or higher."""
        panels = distribute_panels(PANELS, 5)
        for p in panels:
            assert p["floor"] <= 5

    def test_demo_with_fewer_than_five_floors(self):
        """Guided demo panel id must be a valid panel in a 3-floor building."""
        panels  = distribute_panels(PANELS, 3)
        sim     = BuildingSimulator(panels)
        demo_id = panel_ids_for_demo(panels)
        assert demo_id in sim.registry

    def test_reconfiguration_preserves_fault_log(self, tmp_path, monkeypatch):
        """Creating a new BuildingSimulator does not touch the fault_log.csv."""
        import config as cfg
        log_path = tmp_path / "fault_log.csv"
        log_path.write_text("existing_data\n")
        monkeypatch.setattr(cfg, "FAULT_LOG_PATH", log_path)
        # Rebuild simulator — must NOT erase the CSV
        panels = distribute_panels(PANELS, 3)
        BuildingSimulator(panels)
        assert log_path.read_text() == "existing_data\n"
