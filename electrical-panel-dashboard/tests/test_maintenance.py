"""
tests/test_maintenance.py

Unit tests for maintenance.py.

Coverage
--------
compute_priority (pure rule function)
  - FAULT → HIGH
  - WARNING → MEDIUM
  - NORMAL → LOW
  - unknown value falls back to LOW

MaintenanceItem
  - is_active: True for FAULT and WARNING, False for NORMAL
  - age_seconds is non-negative
  - to_dict returns all expected keys with correct types
  - acknowledged_at serialised correctly (None → empty string)

MaintenanceQueue.update_from_fault_events
  - creates new item from a FaultEvent
  - updates existing item on repeated fault
  - resolves item when no longer in fault list
  - re-opens resolved item when fault re-appears
  - correctly parses panel_id from "P-07/Phase-A" circuit format
  - circuit without "/" treated as panel_id directly

MaintenanceQueue.acknowledge
  - sets workflow_status to ACKNOWLEDGED
  - stamps acknowledged_at timestamp
  - raises KeyError for unknown item_id
  - does NOT clear the electrical condition

MaintenanceQueue.add_note
  - appends note text
  - multiple notes accumulate
  - raises KeyError for unknown item_id
  - raises ValueError for empty note
  - raises ValueError for whitespace-only note

MaintenanceQueue.mark_reviewed
  - sets workflow_status to REVIEWED
  - raises KeyError for unknown item_id

MaintenanceQueue.clear_resolved
  - removes REVIEWED + resolved items
  - does NOT remove ACKNOWLEDGED + resolved items
  - does NOT remove active items with REVIEWED status
  - returns count of removed items

MaintenanceQueue query methods
  - active_items returns only FAULT/WARNING
  - all_items returns active + resolved
  - filter_items: floor, panel_id, severity, fault_category, include_resolved
  - sorted_by_priority: HIGH before MEDIUM before LOW, then oldest first
  - counts: correct HIGH/MEDIUM/LOW/total tallies
  - get_item: correct item returned, KeyError for unknown
"""

from datetime import datetime

import pytest

import config
from building import build_registry
from fault_detector import FaultEvent
from maintenance import (
    CONDITION_FAULT,
    CONDITION_NORMAL,
    CONDITION_WARNING,
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_MEDIUM,
    WORKFLOW_ACKNOWLEDGED,
    WORKFLOW_OPEN,
    WORKFLOW_REVIEWED,
    MaintenanceItem,
    MaintenanceQueue,
    compute_priority,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

TS = datetime(2024, 6, 1, 9, 0, 0)
TS2 = datetime(2024, 6, 1, 9, 0, 5)


def _make_fault_event(
    circuit: str = "P-07/Phase-A",
    parameter: str = "voltage",
    value: float = 220.0,
    unit: str = "V",
    threshold: float = 235.45,
    severity: str = "FAULT",
    message: str = "Test fault",
) -> FaultEvent:
    return FaultEvent(
        timestamp=TS,
        circuit=circuit,
        parameter=parameter,
        value=value,
        unit=unit,
        threshold=threshold,
        severity=severity,
        message=message,
    )


def _make_item(
    item_id: str = "P-07::voltage",
    panel_id: str = "P-07",
    floor: int = 5,
    location: str = "Laboratory Suite A",
    fault_category: str = "voltage",
    electrical_condition: str = CONDITION_FAULT,
    severity: str = "FAULT",
    measured_value: float = 220.0,
    unit: str = "V",
    threshold: float = 235.45,
    priority: str = PRIORITY_HIGH,
) -> MaintenanceItem:
    return MaintenanceItem(
        item_id=item_id,
        panel_id=panel_id,
        floor=floor,
        location=location,
        fault_category=fault_category,
        electrical_condition=electrical_condition,
        severity=severity,
        measured_value=measured_value,
        unit=unit,
        threshold=threshold,
        first_detected=TS,
        latest_detected=TS,
        priority=priority,
    )


def _queue_with_item(**kwargs) -> MaintenanceQueue:
    """Return a MaintenanceQueue pre-populated with one item."""
    q = MaintenanceQueue()
    item = _make_item(**kwargs)
    q._items[item.item_id] = item
    return q


# ---------------------------------------------------------------------------
# compute_priority
# ---------------------------------------------------------------------------

class TestComputePriority:
    def test_fault_returns_high(self):
        assert compute_priority(CONDITION_FAULT) == PRIORITY_HIGH

    def test_warning_returns_medium(self):
        assert compute_priority(CONDITION_WARNING) == PRIORITY_MEDIUM

    def test_normal_returns_low(self):
        assert compute_priority(CONDITION_NORMAL) == PRIORITY_LOW

    def test_unknown_returns_low(self):
        """Any value that is not FAULT or WARNING falls through to LOW."""
        assert compute_priority("UNKNOWN") == PRIORITY_LOW

    def test_empty_string_returns_low(self):
        assert compute_priority("") == PRIORITY_LOW


# ---------------------------------------------------------------------------
# MaintenanceItem
# ---------------------------------------------------------------------------

class TestMaintenanceItem:
    def test_is_active_fault(self):
        item = _make_item(electrical_condition=CONDITION_FAULT)
        assert item.is_active is True

    def test_is_active_warning(self):
        item = _make_item(electrical_condition=CONDITION_WARNING)
        assert item.is_active is True

    def test_is_active_normal(self):
        item = _make_item(electrical_condition=CONDITION_NORMAL)
        assert item.is_active is False

    def test_age_seconds_non_negative(self):
        item = _make_item()
        assert item.age_seconds >= 0.0

    def test_to_dict_all_keys_present(self):
        item = _make_item()
        d = item.to_dict()
        expected_keys = {
            "item_id", "panel_id", "floor", "location", "fault_category",
            "electrical_condition", "severity", "measured_value", "unit",
            "threshold", "first_detected", "latest_detected", "priority",
            "workflow_status", "acknowledged_at", "notes", "resolved_at",
            "injected",
        }
        assert set(d.keys()) == expected_keys

    def test_to_dict_acknowledged_at_none_is_empty_string(self):
        item = _make_item()
        assert item.acknowledged_at is None
        assert item.to_dict()["acknowledged_at"] == ""

    def test_to_dict_acknowledged_at_isoformat(self):
        item = _make_item()
        item.acknowledged_at = TS
        assert item.to_dict()["acknowledged_at"] == TS.isoformat()

    def test_to_dict_resolved_at_none_is_empty_string(self):
        item = _make_item()
        assert item.to_dict()["resolved_at"] == ""

    def test_to_dict_notes_joined_with_pipe(self):
        item = _make_item()
        item.notes = ["First note", "Second note"]
        assert item.to_dict()["notes"] == "First note | Second note"

    def test_to_dict_empty_notes(self):
        item = _make_item()
        assert item.to_dict()["notes"] == ""


# ---------------------------------------------------------------------------
# MaintenanceQueue.update_from_fault_events
# ---------------------------------------------------------------------------

class TestUpdateFromFaultEvents:
    def _registry(self):
        return build_registry(config.BUILDING_PANELS)

    def test_creates_new_item_from_fault_event(self):
        q = MaintenanceQueue()
        fe = _make_fault_event()
        q.update_from_fault_events([fe], self._registry(), now=TS)
        assert "P-07::voltage" in q._items

    def test_new_item_priority_high_for_fault(self):
        q = MaintenanceQueue()
        fe = _make_fault_event(severity="FAULT")
        q.update_from_fault_events([fe], self._registry(), now=TS)
        assert q._items["P-07::voltage"].priority == PRIORITY_HIGH

    def test_new_item_priority_medium_for_warning(self):
        q = MaintenanceQueue()
        fe = _make_fault_event(severity="WARNING")
        q.update_from_fault_events([fe], self._registry(), now=TS)
        assert q._items["P-07::voltage"].priority == PRIORITY_MEDIUM

    def test_updates_existing_item_latest_detected(self):
        q = MaintenanceQueue()
        fe = _make_fault_event()
        q.update_from_fault_events([fe], self._registry(), now=TS)
        q.update_from_fault_events([fe], self._registry(), now=TS2)
        assert q._items["P-07::voltage"].latest_detected == TS2

    def test_does_not_change_first_detected_on_update(self):
        q = MaintenanceQueue()
        fe = _make_fault_event()
        q.update_from_fault_events([fe], self._registry(), now=TS)
        q.update_from_fault_events([fe], self._registry(), now=TS2)
        assert q._items["P-07::voltage"].first_detected == TS

    def test_resolves_item_when_fault_clears(self):
        q = MaintenanceQueue()
        fe = _make_fault_event()
        q.update_from_fault_events([fe], self._registry(), now=TS)
        # Next tick: no faults
        q.update_from_fault_events([], self._registry(), now=TS2)
        item = q._items["P-07::voltage"]
        assert item.electrical_condition == CONDITION_NORMAL
        assert item.resolved_at == TS2

    def test_reopens_resolved_item_when_fault_returns(self):
        q = MaintenanceQueue()
        reg = self._registry()
        fe = _make_fault_event()
        q.update_from_fault_events([fe], reg, now=TS)
        q.update_from_fault_events([], reg, now=TS2)
        # Fault reappears
        ts3 = datetime(2024, 6, 1, 9, 0, 10)
        q.update_from_fault_events([fe], reg, now=ts3)
        item = q._items["P-07::voltage"]
        assert item.electrical_condition == CONDITION_FAULT
        assert item.resolved_at is None
        assert item.workflow_status == WORKFLOW_OPEN

    def test_parses_panel_id_from_slash_circuit(self):
        """circuit='P-09/Phase-C' → panel_id='P-09'"""
        q = MaintenanceQueue()
        fe = _make_fault_event(circuit="P-09/Phase-C")
        q.update_from_fault_events([fe], self._registry(), now=TS)
        assert "P-09::voltage" in q._items
        assert q._items["P-09::voltage"].panel_id == "P-09"

    def test_plain_circuit_no_slash_used_as_panel_id(self):
        """circuit='P-09' (no slash) → panel_id='P-09'"""
        q = MaintenanceQueue()
        fe = _make_fault_event(circuit="P-09")
        q.update_from_fault_events([fe], self._registry(), now=TS)
        assert "P-09::voltage" in q._items

    def test_lookup_floor_and_location_from_registry(self):
        q = MaintenanceQueue()
        fe = _make_fault_event(circuit="P-07/Phase-A")
        q.update_from_fault_events([fe], self._registry(), now=TS)
        item = q._items["P-07::voltage"]
        assert item.floor == 5
        assert item.location == "Laboratory Suite A"

    def test_multiple_panels_one_tick(self):
        q = MaintenanceQueue()
        fe1 = _make_fault_event(circuit="P-01/Phase-A", parameter="voltage")
        fe2 = _make_fault_event(circuit="P-02/Phase-B", parameter="current",
                                unit="A", value=260.0, threshold=250.0)
        q.update_from_fault_events([fe1, fe2], self._registry(), now=TS)
        assert "P-01::voltage" in q._items
        assert "P-02::current" in q._items

    def test_empty_fault_list_does_not_create_items(self):
        q = MaintenanceQueue()
        q.update_from_fault_events([], self._registry(), now=TS)
        assert len(q._items) == 0


# ---------------------------------------------------------------------------
# MaintenanceQueue.acknowledge
# ---------------------------------------------------------------------------

class TestAcknowledge:
    def test_sets_workflow_acknowledged(self):
        q = _queue_with_item()
        q.acknowledge("P-07::voltage", now=TS)
        assert q._items["P-07::voltage"].workflow_status == WORKFLOW_ACKNOWLEDGED

    def test_stamps_acknowledged_at(self):
        q = _queue_with_item()
        q.acknowledge("P-07::voltage", now=TS)
        assert q._items["P-07::voltage"].acknowledged_at == TS

    def test_does_not_clear_electrical_condition(self):
        q = _queue_with_item(electrical_condition=CONDITION_FAULT)
        q.acknowledge("P-07::voltage", now=TS)
        assert q._items["P-07::voltage"].electrical_condition == CONDITION_FAULT

    def test_unknown_item_raises_key_error(self):
        q = MaintenanceQueue()
        with pytest.raises(KeyError):
            q.acknowledge("NONEXISTENT::voltage")


# ---------------------------------------------------------------------------
# MaintenanceQueue.add_note
# ---------------------------------------------------------------------------

class TestAddNote:
    def test_appends_note(self):
        q = _queue_with_item()
        q.add_note("P-07::voltage", "Checked phase voltage — breaker is warm")
        assert q._items["P-07::voltage"].notes == ["Checked phase voltage — breaker is warm"]

    def test_multiple_notes_accumulate(self):
        q = _queue_with_item()
        q.add_note("P-07::voltage", "First note")
        q.add_note("P-07::voltage", "Second note")
        assert len(q._items["P-07::voltage"].notes) == 2

    def test_strips_whitespace(self):
        q = _queue_with_item()
        q.add_note("P-07::voltage", "  trimmed  ")
        assert q._items["P-07::voltage"].notes == ["trimmed"]

    def test_unknown_item_raises_key_error(self):
        q = MaintenanceQueue()
        with pytest.raises(KeyError):
            q.add_note("NONEXISTENT::current", "note")

    def test_empty_string_raises_value_error(self):
        q = _queue_with_item()
        with pytest.raises(ValueError):
            q.add_note("P-07::voltage", "")

    def test_whitespace_only_raises_value_error(self):
        q = _queue_with_item()
        with pytest.raises(ValueError):
            q.add_note("P-07::voltage", "   ")


# ---------------------------------------------------------------------------
# MaintenanceQueue.mark_reviewed
# ---------------------------------------------------------------------------

class TestMarkReviewed:
    def test_sets_workflow_reviewed(self):
        q = _queue_with_item()
        q.mark_reviewed("P-07::voltage")
        assert q._items["P-07::voltage"].workflow_status == WORKFLOW_REVIEWED

    def test_unknown_item_raises_key_error(self):
        q = MaintenanceQueue()
        with pytest.raises(KeyError):
            q.mark_reviewed("NONEXISTENT::voltage")


# ---------------------------------------------------------------------------
# MaintenanceQueue.clear_resolved
# ---------------------------------------------------------------------------

class TestClearResolved:
    def test_removes_reviewed_and_resolved_item(self):
        q = _queue_with_item(electrical_condition=CONDITION_NORMAL)
        q._items["P-07::voltage"].resolved_at = TS
        q._items["P-07::voltage"].workflow_status = WORKFLOW_REVIEWED
        removed = q.clear_resolved()
        assert removed == 1
        assert "P-07::voltage" not in q._items

    def test_does_not_remove_acknowledged_and_resolved(self):
        """ACKNOWLEDGED + NORMAL (resolved) should NOT be removed — only REVIEWED."""
        q = _queue_with_item(electrical_condition=CONDITION_NORMAL)
        q._items["P-07::voltage"].resolved_at = TS
        q._items["P-07::voltage"].workflow_status = WORKFLOW_ACKNOWLEDGED
        removed = q.clear_resolved()
        assert removed == 0
        assert "P-07::voltage" in q._items

    def test_does_not_remove_active_reviewed_item(self):
        """Active FAULT even if REVIEWED should not be removed."""
        q = _queue_with_item(electrical_condition=CONDITION_FAULT)
        q._items["P-07::voltage"].workflow_status = WORKFLOW_REVIEWED
        removed = q.clear_resolved()
        assert removed == 0

    def test_returns_count_of_removed(self):
        q = MaintenanceQueue()
        for suffix, cond in [("voltage", CONDITION_NORMAL), ("current", CONDITION_NORMAL)]:
            item = _make_item(
                item_id=f"P-07::{suffix}",
                fault_category=suffix,
                electrical_condition=cond,
            )
            item.resolved_at = TS
            item.workflow_status = WORKFLOW_REVIEWED
            q._items[item.item_id] = item
        assert q.clear_resolved() == 2


# ---------------------------------------------------------------------------
# MaintenanceQueue query methods
# ---------------------------------------------------------------------------

class TestQueryMethods:
    def _populated_queue(self) -> MaintenanceQueue:
        """Queue with 4 items: 1 HIGH active, 1 MEDIUM active, 1 HIGH resolved, 1 LOW resolved."""
        q = MaintenanceQueue()

        fault_active = _make_item(
            item_id="P-01::voltage", panel_id="P-01", floor=1,
            fault_category="voltage",
            electrical_condition=CONDITION_FAULT, priority=PRIORITY_HIGH,
        )
        warn_active = _make_item(
            item_id="P-07::current", panel_id="P-07", floor=5,
            fault_category="current", electrical_condition=CONDITION_WARNING,
            priority=PRIORITY_MEDIUM, severity="WARNING",
        )
        fault_resolved = _make_item(
            item_id="P-09::power_factor", panel_id="P-09", floor=6,
            fault_category="power_factor", electrical_condition=CONDITION_NORMAL,
            priority=PRIORITY_LOW,
        )
        fault_resolved.resolved_at = TS

        low_pf_resolved = _make_item(
            item_id="P-02::power_factor", panel_id="P-02", floor=1,
            fault_category="power_factor", electrical_condition=CONDITION_NORMAL,
            priority=PRIORITY_LOW,
        )
        low_pf_resolved.resolved_at = TS

        q._items = {
            "P-01::voltage": fault_active,
            "P-07::current": warn_active,
            "P-09::power_factor": fault_resolved,
            "P-02::power_factor": low_pf_resolved,
        }
        return q

    # active_items
    def test_active_items_excludes_resolved(self):
        q = self._populated_queue()
        active = q.active_items()
        ids = [i.item_id for i in active]
        assert "P-01::voltage" in ids
        assert "P-07::current" in ids
        assert "P-09::power_factor" not in ids

    def test_active_items_count(self):
        q = self._populated_queue()
        assert len(q.active_items()) == 2

    # all_items
    def test_all_items_count(self):
        q = self._populated_queue()
        assert len(q.all_items()) == 4

    # filter_items — floor
    def test_filter_by_floor(self):
        q = self._populated_queue()
        result = q.filter_items(floor=5)
        assert all(i.floor == 5 for i in result)

    def test_filter_by_floor_no_match(self):
        q = self._populated_queue()
        assert q.filter_items(floor=99) == []

    # filter_items — panel_id
    def test_filter_by_panel_id(self):
        q = self._populated_queue()
        result = q.filter_items(panel_id="P-07")
        assert len(result) == 1
        assert result[0].panel_id == "P-07"

    # filter_items — severity
    def test_filter_by_severity_fault(self):
        q = self._populated_queue()
        result = q.filter_items(severity="FAULT")
        assert all(i.severity == "FAULT" for i in result)

    # filter_items — fault_category
    def test_filter_by_fault_category(self):
        q = self._populated_queue()
        result = q.filter_items(fault_category="power_factor")
        assert all(i.fault_category == "power_factor" for i in result)

    # filter_items — include_resolved=False
    def test_filter_exclude_resolved(self):
        q = self._populated_queue()
        result = q.filter_items(include_resolved=False)
        assert all(i.is_active for i in result)

    # sorted_by_priority
    def test_sorted_by_priority_order(self):
        q = self._populated_queue()
        items = q.sorted_by_priority()
        priorities = [i.priority for i in items]
        # HIGH items must come before MEDIUM; MEDIUM before LOW
        first_medium = next((k for k, p in enumerate(priorities) if p == PRIORITY_MEDIUM), len(priorities))
        last_high = max((k for k, p in enumerate(priorities) if p == PRIORITY_HIGH), default=-1)
        assert last_high < first_medium

    def test_sorted_by_priority_no_duplicate_removal(self):
        q = self._populated_queue()
        assert len(q.sorted_by_priority()) == 4

    def test_sorted_by_priority_exclude_resolved(self):
        q = self._populated_queue()
        items = q.sorted_by_priority(include_resolved=False)
        assert all(i.is_active for i in items)

    # counts
    def test_counts_high(self):
        q = self._populated_queue()
        c = q.counts()
        assert c["HIGH"] == 1

    def test_counts_medium(self):
        q = self._populated_queue()
        c = q.counts()
        assert c["MEDIUM"] == 1

    def test_counts_low(self):
        q = self._populated_queue()
        c = q.counts()
        assert c["LOW"] == 2

    def test_counts_total(self):
        q = self._populated_queue()
        c = q.counts()
        assert c["total"] == 4

    def test_counts_empty_queue(self):
        q = MaintenanceQueue()
        c = q.counts()
        assert c == {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "total": 0}

    # get_item
    def test_get_item_returns_correct_item(self):
        q = self._populated_queue()
        item = q.get_item("P-07::current")
        assert item.panel_id == "P-07"
        assert item.fault_category == "current"

    def test_get_item_unknown_raises_key_error(self):
        q = MaintenanceQueue()
        with pytest.raises(KeyError):
            q.get_item("NONEXISTENT::voltage")
