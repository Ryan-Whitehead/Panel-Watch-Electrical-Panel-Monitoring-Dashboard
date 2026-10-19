"""
tests/test_building.py

Unit tests for building.py.

Coverage
--------
PanelDefinition
  - from_config_dict constructs correct values
  - nominal_current_a property formula
  - label / full_label property format
  - immutability (frozen dataclass)

PanelState
  - initial defaults
  - append_reading updates latest, history, status
  - history ring-buffer maxlen is respected
  - history_as_lists output shape and keys
  - inject_fault / clear_fault_injection round-trip
  - is_active property on reading (indirectly via status)

build_registry
  - produces correct number of entries from BUILDING_PANELS
  - panel_ids match config
  - all values are PanelState instances

get_panel
  - returns correct PanelState for valid ID
  - raises KeyError for unknown ID

panels_by_floor
  - groups correctly
  - all floors present
  - sorted ascending

building_summary
  - counts match constructed registry states
  - edge case: all FAULT, all NORMAL, mixed
"""

from datetime import datetime

import pytest

import config
from building import (
    PanelDefinition,
    PanelReading,
    PanelState,
    build_registry,
    building_summary,
    get_panel,
    panels_by_floor,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

SAMPLE_ENTRY: dict = {
    "panel_id": "P-07",
    "floor": 5,
    "location": "Laboratory Suite A",
    "v_line_to_line": 480.0,
    "v_line_to_neutral": 277.0,
    "phase_rated_current_a": 250.0,
    "nominal_load_pct": 0.72,
    "nominal_pf": 0.86,
}

TS = datetime(2024, 6, 1, 12, 0, 0)


def _make_reading(panel_id: str = "P-07", status: str = "NORMAL") -> PanelReading:
    """Return a minimal PanelReading suitable for append_reading tests."""
    r = PanelReading(
        timestamp=TS,
        panel_id=panel_id,
        phase_a_v=277.0, phase_b_v=277.0, phase_c_v=277.0,
        phase_a_i=100.0, phase_b_i=100.0, phase_c_i=100.0,
        phase_a_pf=0.90, phase_b_pf=0.90, phase_c_pf=0.90,
        p_total_w=74790.0, s_total_va=83100.0, q_total_var=32370.0, pf_agg=0.90,
    )
    r.overall_status = status
    return r


# ---------------------------------------------------------------------------
# PanelDefinition
# ---------------------------------------------------------------------------

class TestPanelDefinition:
    def test_from_config_dict_panel_id(self):
        defn = PanelDefinition.from_config_dict(SAMPLE_ENTRY)
        assert defn.panel_id == "P-07"

    def test_from_config_dict_floor(self):
        defn = PanelDefinition.from_config_dict(SAMPLE_ENTRY)
        assert defn.floor == 5

    def test_from_config_dict_location(self):
        defn = PanelDefinition.from_config_dict(SAMPLE_ENTRY)
        assert defn.location == "Laboratory Suite A"

    def test_from_config_dict_voltages(self):
        defn = PanelDefinition.from_config_dict(SAMPLE_ENTRY)
        assert defn.v_line_to_line == 480.0
        assert defn.v_line_to_neutral == 277.0

    def test_from_config_dict_rated_current(self):
        defn = PanelDefinition.from_config_dict(SAMPLE_ENTRY)
        assert defn.phase_rated_current_a == 250.0

    def test_from_config_dict_nominal_load_pct(self):
        defn = PanelDefinition.from_config_dict(SAMPLE_ENTRY)
        assert defn.nominal_load_pct == pytest.approx(0.72)

    def test_from_config_dict_nominal_pf(self):
        defn = PanelDefinition.from_config_dict(SAMPLE_ENTRY)
        assert defn.nominal_pf == pytest.approx(0.86)

    def test_nominal_current_a_formula(self):
        """nominal_current_a = phase_rated_current_a × nominal_load_pct"""
        defn = PanelDefinition.from_config_dict(SAMPLE_ENTRY)
        expected = 250.0 * 0.72   # 180.0 A
        assert defn.nominal_current_a == pytest.approx(expected)

    def test_nominal_current_a_zero_load(self):
        entry = {**SAMPLE_ENTRY, "nominal_load_pct": 0.0}
        defn = PanelDefinition.from_config_dict(entry)
        assert defn.nominal_current_a == pytest.approx(0.0)

    def test_nominal_current_a_full_load(self):
        entry = {**SAMPLE_ENTRY, "nominal_load_pct": 1.0}
        defn = PanelDefinition.from_config_dict(entry)
        assert defn.nominal_current_a == pytest.approx(250.0)

    def test_label_format(self):
        defn = PanelDefinition.from_config_dict(SAMPLE_ENTRY)
        assert defn.label == "P-07 · Floor 5"

    def test_full_label_format(self):
        defn = PanelDefinition.from_config_dict(SAMPLE_ENTRY)
        assert defn.full_label == "P-07 — Laboratory Suite A (Floor 5)"

    def test_frozen_immutable(self):
        """PanelDefinition is a frozen dataclass — mutation must raise."""
        defn = PanelDefinition.from_config_dict(SAMPLE_ENTRY)
        with pytest.raises((AttributeError, TypeError)):
            defn.panel_id = "CHANGED"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# PanelState
# ---------------------------------------------------------------------------

class TestPanelState:
    def _make_state(self) -> PanelState:
        defn = PanelDefinition.from_config_dict(SAMPLE_ENTRY)
        return PanelState(definition=defn)

    def test_initial_latest_reading_is_none(self):
        ps = self._make_state()
        assert ps.latest_reading is None

    def test_initial_energy_kwh_zero(self):
        ps = self._make_state()
        assert ps.energy_kwh == 0.0

    def test_initial_status_normal(self):
        ps = self._make_state()
        assert ps.status == "NORMAL"

    def test_initial_injected_scenario_none(self):
        ps = self._make_state()
        assert ps.injected_scenario is None

    def test_append_reading_updates_latest(self):
        ps = self._make_state()
        r = _make_reading()
        ps.append_reading(r)
        assert ps.latest_reading is r

    def test_append_reading_updates_status(self):
        ps = self._make_state()
        r = _make_reading(status="FAULT")
        ps.append_reading(r)
        assert ps.status == "FAULT"

    def test_append_reading_history_grows(self):
        ps = self._make_state()
        for _ in range(5):
            ps.append_reading(_make_reading())
        assert len(ps.history) == 5

    def test_append_reading_history_ring_buffer(self):
        """History must not exceed HISTORY_WINDOW readings."""
        ps = self._make_state()
        limit = config.HISTORY_WINDOW
        for _ in range(limit + 10):
            ps.append_reading(_make_reading())
        assert len(ps.history) == limit

    def test_history_as_lists_keys(self):
        ps = self._make_state()
        ps.append_reading(_make_reading())
        result = ps.history_as_lists()
        expected_keys = {
            "timestamps", "phase_a_v", "phase_b_v", "phase_c_v",
            "phase_a_i", "phase_b_i", "phase_c_i",
            "phase_a_pf", "phase_b_pf", "phase_c_pf",
            "p_total_kw",
        }
        assert set(result.keys()) == expected_keys

    def test_history_as_lists_length_matches(self):
        ps = self._make_state()
        for _ in range(10):
            ps.append_reading(_make_reading())
        result = ps.history_as_lists()
        assert all(len(v) == 10 for v in result.values())

    def test_history_as_lists_p_total_kw_conversion(self):
        """p_total_kw must be p_total_w / 1000."""
        ps = self._make_state()
        r = _make_reading()
        r.p_total_w = 50_000.0
        ps.append_reading(r)
        result = ps.history_as_lists()
        assert result["p_total_kw"][0] == pytest.approx(50.0)

    def test_history_as_lists_empty(self):
        ps = self._make_state()
        result = ps.history_as_lists()
        assert all(len(v) == 0 for v in result.values())

    def test_inject_fault_sets_scenario(self):
        ps = self._make_state()
        ps.inject_fault("overcurrent")
        assert ps.injected_scenario == "overcurrent"

    def test_clear_fault_injection_clears(self):
        ps = self._make_state()
        ps.inject_fault("undervoltage")
        ps.clear_fault_injection()
        assert ps.injected_scenario is None

    def test_inject_and_clear_round_trip(self):
        ps = self._make_state()
        ps.inject_fault("low_power_factor")
        assert ps.injected_scenario == "low_power_factor"
        ps.clear_fault_injection()
        assert ps.injected_scenario is None


# ---------------------------------------------------------------------------
# build_registry
# ---------------------------------------------------------------------------

class TestBuildRegistry:
    def test_count_matches_config(self):
        reg = build_registry(config.BUILDING_PANELS)
        assert len(reg) == len(config.BUILDING_PANELS)

    def test_all_values_are_panel_state(self):
        reg = build_registry(config.BUILDING_PANELS)
        assert all(isinstance(v, PanelState) for v in reg.values())

    def test_panel_ids_match_config(self):
        reg = build_registry(config.BUILDING_PANELS)
        expected_ids = [e["panel_id"] for e in config.BUILDING_PANELS]
        assert list(reg.keys()) == expected_ids

    def test_empty_config_returns_empty_dict(self):
        reg = build_registry([])
        assert reg == {}

    def test_single_entry(self):
        reg = build_registry([SAMPLE_ENTRY])
        assert "P-07" in reg
        assert reg["P-07"].definition.floor == 5


# ---------------------------------------------------------------------------
# get_panel
# ---------------------------------------------------------------------------

class TestGetPanel:
    def test_returns_correct_panel(self):
        reg = build_registry(config.BUILDING_PANELS)
        ps = get_panel(reg, "P-07")
        assert ps.definition.panel_id == "P-07"

    def test_unknown_id_raises_key_error(self):
        reg = build_registry(config.BUILDING_PANELS)
        with pytest.raises(KeyError):
            get_panel(reg, "P-99")

    def test_empty_registry_raises_key_error(self):
        with pytest.raises(KeyError):
            get_panel({}, "P-01")


# ---------------------------------------------------------------------------
# panels_by_floor
# ---------------------------------------------------------------------------

class TestPanelsByFloor:
    def test_all_floors_present(self):
        reg = build_registry(config.BUILDING_PANELS)
        by_floor = panels_by_floor(reg)
        expected_floors = sorted({e["floor"] for e in config.BUILDING_PANELS})
        assert list(by_floor.keys()) == expected_floors

    def test_total_panels_preserved(self):
        reg = build_registry(config.BUILDING_PANELS)
        by_floor = panels_by_floor(reg)
        total = sum(len(v) for v in by_floor.values())
        assert total == len(config.BUILDING_PANELS)

    def test_floors_are_sorted_ascending(self):
        reg = build_registry(config.BUILDING_PANELS)
        by_floor = panels_by_floor(reg)
        keys = list(by_floor.keys())
        assert keys == sorted(keys)

    def test_correct_panels_on_floor_1(self):
        """Floor 1 should have P-01 and P-02 per config."""
        reg = build_registry(config.BUILDING_PANELS)
        by_floor = panels_by_floor(reg)
        ids_floor1 = [ps.definition.panel_id for ps in by_floor[1]]
        assert set(ids_floor1) == {"P-01", "P-02"}

    def test_single_panel_floor(self):
        """Floor 3 has only P-05 per config."""
        reg = build_registry(config.BUILDING_PANELS)
        by_floor = panels_by_floor(reg)
        assert len(by_floor[3]) == 1
        assert by_floor[3][0].definition.panel_id == "P-05"

    def test_empty_registry(self):
        assert panels_by_floor({}) == {}


# ---------------------------------------------------------------------------
# building_summary
# ---------------------------------------------------------------------------

class TestBuildingSummary:
    def _reg_with_statuses(self, statuses: list) -> dict:
        """Build a registry fragment with panels having the given statuses."""
        entries = config.BUILDING_PANELS[: len(statuses)]
        reg = build_registry(entries)
        for ps, status in zip(reg.values(), statuses):
            ps.status = status
        return reg

    def test_all_normal(self):
        reg = self._reg_with_statuses(["NORMAL"] * 5)
        s = building_summary(reg)
        assert s["total"] == 5
        assert s["normal"] == 5
        assert s["warning"] == 0
        assert s["fault"] == 0

    def test_all_fault(self):
        reg = self._reg_with_statuses(["FAULT"] * 3)
        s = building_summary(reg)
        assert s["fault"] == 3
        assert s["normal"] == 0

    def test_mixed_counts(self):
        statuses = ["NORMAL", "NORMAL", "WARNING", "FAULT", "WARNING"]
        reg = self._reg_with_statuses(statuses)
        s = building_summary(reg)
        assert s["total"] == 5
        assert s["normal"] == 2
        assert s["warning"] == 2
        assert s["fault"] == 1

    def test_counts_sum_to_total(self):
        statuses = ["NORMAL", "WARNING", "FAULT", "NORMAL", "FAULT"]
        reg = self._reg_with_statuses(statuses)
        s = building_summary(reg)
        assert s["normal"] + s["warning"] + s["fault"] == s["total"]

    def test_empty_registry(self):
        s = building_summary({})
        assert s == {"total": 0, "normal": 0, "warning": 0, "fault": 0}
