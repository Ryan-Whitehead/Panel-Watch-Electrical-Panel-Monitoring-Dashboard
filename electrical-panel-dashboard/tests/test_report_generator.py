"""
tests/test_report_generator.py

Unit tests for report_generator.py.

Coverage
--------
generate_maintenance_csv()
  - Returns a non-empty string
  - Disclaimer lines are present in the output
  - Report title is present
  - Building summary block is present
  - Column headers are present (all 18 human-readable labels)
  - Empty queue → valid CSV with header + 0 data rows
  - Single HIGH item → all fields present in the data row
  - Priority sort order: HIGH before MEDIUM before LOW
  - Active fault electrical_condition preserved correctly
  - Resolved fault electrical_condition preserved correctly
  - Acknowledgement status (workflow_status) present and correct
  - Technician notes joined with ' | '
  - Empty notes render as empty string (not 'None')
  - generated_at timestamp appears in the output
  - building_summary counts appear in the header block
  - measured_value formatted with 3 decimal places
  - threshold formatted with 3 decimal places
  - injected fault marked YES / NO correctly
  - resolved_at present and empty when not resolved
"""

import csv
from datetime import datetime

from maintenance import (
    CONDITION_FAULT,
    CONDITION_NORMAL,
    CONDITION_WARNING,
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_MEDIUM,
    MaintenanceItem,
    MaintenanceQueue,
)
from report_generator import (
    COLUMN_HEADERS,
    DATA_COLUMNS,
    DISCLAIMER_LINES,
    generate_maintenance_csv,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

TS = datetime(2024, 6, 1, 9, 0, 0)
TS2 = datetime(2024, 6, 1, 9, 5, 0)

BUILDING_SUMMARY = {
    "total": 20,
    "normal": 18,
    "warning": 1,
    "fault": 1,
}


def _make_item(
    item_id: str = "P-07::current",
    panel_id: str = "P-07",
    floor: int = 5,
    location: str = "Laboratory Suite A",
    fault_category: str = "current",
    electrical_condition: str = CONDITION_FAULT,
    severity: str = "FAULT",
    measured_value: float = 337.5,
    unit: str = "A",
    threshold: float = 312.5,
    priority: str = PRIORITY_HIGH,
    notes: list | None = None,
    acknowledged_at: datetime | None = None,
    resolved_at: datetime | None = None,
    injected: bool = False,
) -> MaintenanceItem:
    item = MaintenanceItem(
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
    if notes:
        item.notes = notes
    item.acknowledged_at = acknowledged_at
    item.resolved_at = resolved_at
    item.injected = injected
    return item


def _queue_with(*items) -> MaintenanceQueue:
    q = MaintenanceQueue()
    for item in items:
        q._items[item.item_id] = item
    return q


def _parse_data_rows(csv_text: str) -> list:
    """
    Parse the data section (non-comment, non-blank rows) from the report CSV.
    Returns a list of dicts keyed by the first (header) data row.
    """
    lines = [ln for ln in csv_text.splitlines() if ln and not ln.startswith("#")]
    reader = csv.DictReader(lines)
    return list(reader)


# ---------------------------------------------------------------------------
# Basic output validity
# ---------------------------------------------------------------------------

class TestBasicOutput:
    def test_returns_string(self):
        q = MaintenanceQueue()
        result = generate_maintenance_csv(q, BUILDING_SUMMARY, TS)
        assert isinstance(result, str)

    def test_non_empty(self):
        q = MaintenanceQueue()
        result = generate_maintenance_csv(q, BUILDING_SUMMARY, TS)
        assert len(result) > 0

    def test_disclaimer_present(self):
        q = MaintenanceQueue()
        result = generate_maintenance_csv(q, BUILDING_SUMMARY, TS)
        for line in DISCLAIMER_LINES:
            assert line in result, f"Disclaimer line missing: {line!r}"

    def test_report_title_present(self):
        q = MaintenanceQueue()
        result = generate_maintenance_csv(q, BUILDING_SUMMARY, TS)
        assert "PanelWatch Maintenance Report" in result

    def test_generated_at_timestamp_present(self):
        ts = datetime(2024, 6, 15, 14, 30, 0)
        q = MaintenanceQueue()
        result = generate_maintenance_csv(q, BUILDING_SUMMARY, ts)
        assert "2024-06-15 14:30:00" in result

    def test_building_name_present(self):
        q = MaintenanceQueue()
        result = generate_maintenance_csv(q, BUILDING_SUMMARY, TS)
        assert "PanelWatch Simulated Commercial Building" in result


# ---------------------------------------------------------------------------
# Building summary block
# ---------------------------------------------------------------------------

class TestBuildingSummaryBlock:
    def test_total_panels_in_header(self):
        q = MaintenanceQueue()
        result = generate_maintenance_csv(q, BUILDING_SUMMARY, TS)
        assert "20" in result

    def test_normal_count_in_header(self):
        q = MaintenanceQueue()
        result = generate_maintenance_csv(q, BUILDING_SUMMARY, TS)
        assert "18" in result

    def test_fault_count_in_header(self):
        q = MaintenanceQueue()
        result = generate_maintenance_csv(q, BUILDING_SUMMARY, TS)
        assert "1" in result


# ---------------------------------------------------------------------------
# Column headers
# ---------------------------------------------------------------------------

class TestColumnHeaders:
    def test_all_human_readable_headers_present(self):
        q = MaintenanceQueue()
        result = generate_maintenance_csv(q, BUILDING_SUMMARY, TS)
        for header in COLUMN_HEADERS.values():
            assert header in result, f"Column header missing: {header!r}"

    def test_data_columns_count(self):
        assert len(DATA_COLUMNS) == 18


# ---------------------------------------------------------------------------
# Empty queue
# ---------------------------------------------------------------------------

class TestEmptyQueue:
    def test_zero_data_rows(self):
        q = MaintenanceQueue()
        result = generate_maintenance_csv(q, BUILDING_SUMMARY, TS)
        rows = _parse_data_rows(result)
        assert len(rows) == 0

    def test_header_still_present_when_empty(self):
        q = MaintenanceQueue()
        result = generate_maintenance_csv(q, BUILDING_SUMMARY, TS)
        assert "Item ID" in result

    def test_disclaimer_still_present_when_empty(self):
        q = MaintenanceQueue()
        result = generate_maintenance_csv(q, BUILDING_SUMMARY, TS)
        assert "DISCLAIMER" in result


# ---------------------------------------------------------------------------
# Single item — field presence and correctness
# ---------------------------------------------------------------------------

class TestSingleItem:
    def _get_row(self) -> dict:
        item = _make_item(
            measured_value=337.5,
            threshold=312.5,
            notes=["Checked breaker"],
            acknowledged_at=TS2,
        )
        q = _queue_with(item)
        result = generate_maintenance_csv(q, BUILDING_SUMMARY, TS)
        rows = _parse_data_rows(result)
        assert len(rows) == 1
        return rows[0]

    def test_item_id_present(self):
        row = self._get_row()
        assert row["Item ID"] == "P-07::current"

    def test_panel_id_present(self):
        row = self._get_row()
        assert row["Panel ID"] == "P-07"

    def test_floor_present(self):
        row = self._get_row()
        assert row["Floor"] == "5"

    def test_location_present(self):
        row = self._get_row()
        assert row["Location"] == "Laboratory Suite A"

    def test_fault_category_present(self):
        row = self._get_row()
        assert row["Fault Category"] == "current"

    def test_electrical_condition_active(self):
        row = self._get_row()
        assert row["Electrical Condition"] == CONDITION_FAULT

    def test_severity_present(self):
        row = self._get_row()
        assert row["Severity"] == "FAULT"

    def test_measured_value_three_decimal_places(self):
        row = self._get_row()
        assert row["Measured Value"] == "337.500"

    def test_unit_present(self):
        row = self._get_row()
        assert row["Unit"] == "A"

    def test_threshold_three_decimal_places(self):
        row = self._get_row()
        assert row["Threshold"] == "312.500"

    def test_priority_present(self):
        row = self._get_row()
        assert row["Maintenance Priority"] == PRIORITY_HIGH

    def test_workflow_status_open(self):
        item = _make_item()
        q = _queue_with(item)
        result = generate_maintenance_csv(q, BUILDING_SUMMARY, TS)
        rows = _parse_data_rows(result)
        assert rows[0]["Workflow Status"] == "OPEN"

    def test_acknowledged_at_isoformat(self):
        row = self._get_row()
        assert row["Acknowledged At"] == TS2.isoformat()

    def test_acknowledged_at_empty_when_none(self):
        item = _make_item(acknowledged_at=None)
        q = _queue_with(item)
        result = generate_maintenance_csv(q, BUILDING_SUMMARY, TS)
        rows = _parse_data_rows(result)
        assert rows[0]["Acknowledged At"] == ""

    def test_technician_notes_joined(self):
        item = _make_item(notes=["First note", "Second note"])
        q = _queue_with(item)
        result = generate_maintenance_csv(q, BUILDING_SUMMARY, TS)
        rows = _parse_data_rows(result)
        assert rows[0]["Technician Notes"] == "First note | Second note"

    def test_empty_notes_is_empty_string(self):
        # notes=["Checked breaker"] in _get_row — override for this specific check
        item = _make_item(notes=[])
        q = _queue_with(item)
        result = generate_maintenance_csv(q, BUILDING_SUMMARY, TS)
        rows = _parse_data_rows(result)
        assert rows[0]["Technician Notes"] == ""

    def test_resolved_at_empty_when_not_resolved(self):
        row = self._get_row()
        assert row["Resolved At"] == ""

    def test_resolved_at_isoformat_when_resolved(self):
        item = _make_item(electrical_condition=CONDITION_NORMAL, resolved_at=TS2)
        q = _queue_with(item)
        result = generate_maintenance_csv(q, BUILDING_SUMMARY, TS)
        rows = _parse_data_rows(result)
        assert rows[0]["Resolved At"] == TS2.isoformat()

    def test_injected_no(self):
        item = _make_item(injected=False)
        q = _queue_with(item)
        result = generate_maintenance_csv(q, BUILDING_SUMMARY, TS)
        rows = _parse_data_rows(result)
        assert rows[0]["Injected Fault (Demo)"] == "NO"

    def test_injected_yes(self):
        item = _make_item(injected=True)
        q = _queue_with(item)
        result = generate_maintenance_csv(q, BUILDING_SUMMARY, TS)
        rows = _parse_data_rows(result)
        assert rows[0]["Injected Fault (Demo)"] == "YES"


# ---------------------------------------------------------------------------
# Priority sort order
# ---------------------------------------------------------------------------

class TestPrioritySortOrder:
    def test_high_before_low(self):
        high_item = _make_item(
            item_id="P-01::voltage", fault_category="voltage",
            priority=PRIORITY_HIGH,
        )
        low_item = _make_item(
            item_id="P-02::power_factor", fault_category="power_factor",
            electrical_condition=CONDITION_NORMAL,
            priority=PRIORITY_LOW,
        )
        # Insert in reversed order to verify sort
        q = _queue_with(low_item, high_item)
        result = generate_maintenance_csv(q, BUILDING_SUMMARY, TS)
        rows = _parse_data_rows(result)
        priorities = [r["Maintenance Priority"] for r in rows]
        assert priorities.index(PRIORITY_HIGH) < priorities.index(PRIORITY_LOW)

    def test_high_before_medium_before_low(self):
        high = _make_item(item_id="P-01::voltage", fault_category="voltage",
                          priority=PRIORITY_HIGH)
        medium = _make_item(item_id="P-02::current", fault_category="current",
                            electrical_condition=CONDITION_WARNING,
                            severity="WARNING", priority=PRIORITY_MEDIUM)
        low = _make_item(item_id="P-03::power_factor", fault_category="power_factor",
                         electrical_condition=CONDITION_NORMAL, priority=PRIORITY_LOW)
        q = _queue_with(low, medium, high)
        result = generate_maintenance_csv(q, BUILDING_SUMMARY, TS)
        rows = _parse_data_rows(result)
        priorities = [r["Maintenance Priority"] for r in rows]
        assert priorities[0] == PRIORITY_HIGH
        assert priorities[1] == PRIORITY_MEDIUM
        assert priorities[2] == PRIORITY_LOW

    def test_three_items_total_rows(self):
        high = _make_item(item_id="P-01::voltage", fault_category="voltage",
                          priority=PRIORITY_HIGH)
        medium = _make_item(item_id="P-02::current", fault_category="current",
                            electrical_condition=CONDITION_WARNING,
                            severity="WARNING", priority=PRIORITY_MEDIUM)
        low = _make_item(item_id="P-03::power_factor", fault_category="power_factor",
                         electrical_condition=CONDITION_NORMAL, priority=PRIORITY_LOW)
        q = _queue_with(high, medium, low)
        result = generate_maintenance_csv(q, BUILDING_SUMMARY, TS)
        rows = _parse_data_rows(result)
        assert len(rows) == 3


# ---------------------------------------------------------------------------
# Active vs resolved distinction
# ---------------------------------------------------------------------------

class TestActiveVsResolved:
    def test_active_fault_condition_is_fault(self):
        item = _make_item(electrical_condition=CONDITION_FAULT)
        q = _queue_with(item)
        result = generate_maintenance_csv(q, BUILDING_SUMMARY, TS)
        rows = _parse_data_rows(result)
        assert rows[0]["Electrical Condition"] == CONDITION_FAULT

    def test_resolved_condition_is_normal(self):
        item = _make_item(
            electrical_condition=CONDITION_NORMAL,
            priority=PRIORITY_LOW,
            resolved_at=TS2,
        )
        q = _queue_with(item)
        result = generate_maintenance_csv(q, BUILDING_SUMMARY, TS)
        rows = _parse_data_rows(result)
        assert rows[0]["Electrical Condition"] == CONDITION_NORMAL
