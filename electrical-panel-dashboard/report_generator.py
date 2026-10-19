"""
report_generator.py — Maintenance report generation for PanelWatch.

Purpose
-------
Generates a structured CSV maintenance report from the live MaintenanceQueue.
The report is suitable for downloading from the Streamlit UI, sharing with
facilities management, or importing into a CMMS (Computerised Maintenance
Management System).

This module is pure Python (no Streamlit dependency) and is fully unit-testable.

Functions
---------
generate_maintenance_csv(queue, building_summary, generated_at) -> str
    Return a complete CSV string including a disclaimer header, building
    summary block, and one data row per maintenance item.

Engineering notes
-----------------
* Active faults (electrical_condition = FAULT or WARNING) are clearly
  distinguished from resolved faults (electrical_condition = NORMAL).
* Maintenance acknowledgement (workflow_status) is reported separately from
  the electrical fault condition — acknowledging an alert does not resolve it.
* All electrical values are reported with their units in the column headers.
* The disclaimer is prepended as comment lines (# prefix) so it survives
  import into tools that skip comment rows, while remaining visible in a
  text editor.

Disclaimer (required in every export)
--------------------------------------
All measurements and fault events are simulated for demonstration and
educational purposes.  PanelWatch is not a certified electrical protection
or safety system.
"""

import csv
import io
from datetime import datetime

from maintenance import MaintenanceQueue

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DISCLAIMER_LINES: list = [
    "DISCLAIMER: All measurements and fault events are simulated for demonstration",
    "and educational purposes. PanelWatch is not a certified electrical protection",
    "or safety system.",
]

BUILDING_NAME: str = "PanelWatch Simulated Commercial Building"
BUILDING_VOLTAGE: str = "277/480 V 3-Phase 60 Hz"

# Column order and headers for the data section
DATA_COLUMNS: list = [
    "item_id",
    "panel_id",
    "floor",
    "location",
    "fault_category",
    "electrical_condition",
    "severity",
    "measured_value",
    "unit",
    "threshold",
    "maintenance_priority",
    "workflow_status",
    "acknowledged_at",
    "technician_notes",
    "first_detected",
    "latest_detected",
    "resolved_at",
    "injected_fault",
]

# Human-readable column headers for the CSV header row
COLUMN_HEADERS: dict = {
    "item_id":               "Item ID",
    "panel_id":              "Panel ID",
    "floor":                 "Floor",
    "location":              "Location",
    "fault_category":        "Fault Category",
    "electrical_condition":  "Electrical Condition",
    "severity":              "Severity",
    "measured_value":        "Measured Value",
    "unit":                  "Unit",
    "threshold":             "Threshold",
    "maintenance_priority":  "Maintenance Priority",
    "workflow_status":       "Workflow Status",
    "acknowledged_at":       "Acknowledged At",
    "technician_notes":      "Technician Notes",
    "first_detected":        "First Detected",
    "latest_detected":       "Latest Detected",
    "resolved_at":           "Resolved At",
    "injected_fault":        "Injected Fault (Demo)",
}


# ---------------------------------------------------------------------------
# Main export function
# ---------------------------------------------------------------------------

def generate_maintenance_csv(
    queue: MaintenanceQueue,
    building_summary: dict,
    generated_at: datetime,
) -> str:
    """
    Generate a complete maintenance report as a CSV string.

    The output has three sections:
    1. Comment header — disclaimer, generation timestamp, building info,
       panel status summary.  Lines prefixed with '#' for easy parsing.
    2. Blank separator line.
    3. Data section — one header row followed by one row per maintenance item,
       sorted HIGH → MEDIUM → LOW then oldest-first within each priority.

    Parameters
    ----------
    queue : MaintenanceQueue
        The live maintenance queue from session state.
    building_summary : dict
        Dict with keys: total, normal, warning, fault.
        Used for the building status summary in the header block.
    generated_at : datetime
        Timestamp to embed in the report header.

    Returns
    -------
    str
        Complete UTF-8 CSV string ready for download.

    Notes
    -----
    * An empty queue produces a valid CSV with the header block and column
      headers but zero data rows.  This is handled gracefully.
    * Technician notes (a list) are joined with ' | ' for CSV compatibility.
    * All datetime values are ISO 8601 strings; empty strings where None.
    """
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")

    # ------------------------------------------------------------------
    # Section 1: Comment header block
    # ------------------------------------------------------------------
    for line in DISCLAIMER_LINES:
        writer.writerow([f"# {line}"])

    writer.writerow(["#"])
    writer.writerow(["# Report Title:       PanelWatch Maintenance Report"])
    writer.writerow([f"# Generated:          {generated_at.strftime('%Y-%m-%d %H:%M:%S')}"])
    writer.writerow([f"# Building:           {BUILDING_NAME}"])
    writer.writerow([f"# Electrical System:  {BUILDING_VOLTAGE}"])
    writer.writerow([f"# Total Panels:       {building_summary.get('total', 0)}"])
    writer.writerow(["#"])
    writer.writerow(["# Panel Status Summary:"])
    writer.writerow([f"#   NORMAL  : {building_summary.get('normal', 0)}"])
    writer.writerow([f"#   WARNING : {building_summary.get('warning', 0)}"])
    writer.writerow([f"#   FAULT   : {building_summary.get('fault', 0)}"])
    writer.writerow(["#"])

    counts = queue.counts()
    writer.writerow(["# Maintenance Queue Summary:"])
    writer.writerow([f"#   HIGH priority   (active FAULT)   : {counts['HIGH']}"])
    writer.writerow([f"#   MEDIUM priority (active WARNING) : {counts['MEDIUM']}"])
    writer.writerow([f"#   LOW priority    (resolved)       : {counts['LOW']}"])
    writer.writerow([f"#   Total items                      : {counts['total']}"])
    writer.writerow(["#"])

    # ------------------------------------------------------------------
    # Section 2: Blank separator
    # ------------------------------------------------------------------
    writer.writerow([])

    # ------------------------------------------------------------------
    # Section 3: Data rows
    # ------------------------------------------------------------------
    # Column header row (human-readable labels)
    writer.writerow([COLUMN_HEADERS[col] for col in DATA_COLUMNS])

    # Sort: HIGH → MEDIUM → LOW, then oldest first within each priority
    priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    items = sorted(
        queue.all_items(),
        key=lambda i: (priority_order.get(i.priority, 9), i.first_detected),
    )

    for item in items:
        writer.writerow([
            item.item_id,
            item.panel_id,
            item.floor,
            item.location,
            item.fault_category,
            item.electrical_condition,
            item.severity,
            f"{item.measured_value:.3f}",
            item.unit,
            f"{item.threshold:.3f}",
            item.priority,
            item.workflow_status,
            item.acknowledged_at.isoformat() if item.acknowledged_at else "",
            " | ".join(item.notes),
            item.first_detected.isoformat(),
            item.latest_detected.isoformat(),
            item.resolved_at.isoformat() if item.resolved_at else "",
            "YES" if item.injected else "NO",
        ])

    return output.getvalue()
