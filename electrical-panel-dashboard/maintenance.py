"""
maintenance.py — Maintenance decision-support for the building-wide monitor.

Converts detected fault events into structured maintenance items and manages
the workflow state (acknowledge, add note, mark reviewed, resolve).

Key design decisions
--------------------
* Electrical condition and workflow status are tracked separately.
  A fault acknowledged by a technician is still electrically active until
  the simulated measurement returns to normal.
* Priority is rule-based and transparent:
    HIGH   — any panel with an active FAULT condition
    MEDIUM — any panel with an active WARNING condition (no FAULT)
    LOW    — items where the electrical condition has resolved but a
             maintenance record should be retained for follow-up
* Items are keyed by (panel_id, fault_category) so multiple distinct fault
  types on the same panel produce independent maintenance items.
* This module is pure Python (no Streamlit) so it is fully unit-testable.

Classes
-------
MaintenanceItem
    Structured record of one maintenance condition.

MaintenanceQueue
    Collection manager with add / acknowledge / note / resolve / filter / sort.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

# ---------------------------------------------------------------------------
# Priority constants (rule documentation)
# ---------------------------------------------------------------------------

PRIORITY_HIGH = "HIGH"      # Active FAULT condition
PRIORITY_MEDIUM = "MEDIUM"  # Active WARNING condition
PRIORITY_LOW = "LOW"        # Resolved condition kept for maintenance record

PRIORITY_ORDER = {PRIORITY_HIGH: 0, PRIORITY_MEDIUM: 1, PRIORITY_LOW: 2}

# Workflow status values
WORKFLOW_OPEN = "OPEN"
WORKFLOW_ACKNOWLEDGED = "ACKNOWLEDGED"
WORKFLOW_REVIEWED = "REVIEWED"

# Electrical condition values
CONDITION_FAULT = "FAULT"
CONDITION_WARNING = "WARNING"
CONDITION_NORMAL = "NORMAL"


# ---------------------------------------------------------------------------
# MaintenanceItem dataclass
# ---------------------------------------------------------------------------

@dataclass
class MaintenanceItem:
    """
    One maintenance condition derived from electrical fault detection.

    Attributes
    ----------
    item_id : str
        Unique identifier: "{panel_id}::{parameter}" e.g. "P-07::current".
    panel_id : str
        Panel where the condition was detected.
    floor : int
        Floor of the panel.
    location : str
        Descriptive panel location.
    fault_category : str
        "voltage", "current", or "power_factor".
    electrical_condition : str
        Current electrical state: "FAULT", "WARNING", or "NORMAL".
    severity : str
        Severity of the most recent active event: "FAULT" or "WARNING".
    measured_value : float
        Measurement value that triggered the condition (most recent).
    unit : str
        Unit of the measured value: "V", "A", or "PF".
    threshold : float
        The threshold that was crossed.
    first_detected : datetime
        Timestamp when this condition was first observed.
    latest_detected : datetime
        Timestamp of the most recent detection.
    priority : str
        Rule-based priority: "HIGH", "MEDIUM", or "LOW".
    workflow_status : str
        Technician workflow state: "OPEN", "ACKNOWLEDGED", or "REVIEWED".
    acknowledged_at : Optional[datetime]
        When a technician acknowledged the alert (None if not yet acknowledged).
    notes : list[str]
        Technician notes attached to this item.
    resolved_at : Optional[datetime]
        When the electrical condition returned to normal (None if still active).
    injected : bool
        True if this item was created from a manually injected fault (Fault
        Simulation Control Center) rather than a background simulation event.
    """

    item_id: str
    panel_id: str
    floor: int
    location: str
    fault_category: str
    electrical_condition: str
    severity: str
    measured_value: float
    unit: str
    threshold: float
    first_detected: datetime
    latest_detected: datetime
    priority: str
    workflow_status: str = WORKFLOW_OPEN
    acknowledged_at: Optional[datetime] = field(default=None)
    notes: list = field(default_factory=list)
    resolved_at: Optional[datetime] = field(default=None)
    injected: bool = False

    @property
    def is_active(self) -> bool:
        """True when the electrical condition is still FAULT or WARNING."""
        return self.electrical_condition in (CONDITION_FAULT, CONDITION_WARNING)

    @property
    def age_seconds(self) -> float:
        """Seconds since first detection."""
        return (datetime.now() - self.first_detected).total_seconds()

    def to_dict(self) -> dict:
        """Serialise to a plain dict for CSV / DataFrame export."""
        return {
            "item_id":              self.item_id,
            "panel_id":             self.panel_id,
            "floor":                self.floor,
            "location":             self.location,
            "fault_category":       self.fault_category,
            "electrical_condition": self.electrical_condition,
            "severity":             self.severity,
            "measured_value":       self.measured_value,
            "unit":                 self.unit,
            "threshold":            self.threshold,
            "first_detected":       self.first_detected.isoformat(),
            "latest_detected":      self.latest_detected.isoformat(),
            "priority":             self.priority,
            "workflow_status":      self.workflow_status,
            "acknowledged_at":      self.acknowledged_at.isoformat() if self.acknowledged_at else "",
            "notes":                " | ".join(self.notes),
            "resolved_at":          self.resolved_at.isoformat() if self.resolved_at else "",
            "injected":             self.injected,
        }


# ---------------------------------------------------------------------------
# Priority rules (pure function — easy to test)
# ---------------------------------------------------------------------------

def compute_priority(electrical_condition: str) -> str:
    """
    Derive inspection priority from the current electrical condition.

    Rules (documented openly — not a certified safety assessment):
        FAULT   → HIGH   (immediate attention recommended)
        WARNING → MEDIUM (schedule inspection)
        NORMAL  → LOW    (resolved; retain for maintenance record)

    Parameters
    ----------
    electrical_condition : str
        "FAULT", "WARNING", or "NORMAL".

    Returns
    -------
    str
        "HIGH", "MEDIUM", or "LOW".
    """
    if electrical_condition == CONDITION_FAULT:
        return PRIORITY_HIGH
    if electrical_condition == CONDITION_WARNING:
        return PRIORITY_MEDIUM
    return PRIORITY_LOW


# ---------------------------------------------------------------------------
# MaintenanceQueue
# ---------------------------------------------------------------------------

class MaintenanceQueue:
    """
    Collection manager for MaintenanceItem objects.

    Items are keyed by item_id = "{panel_id}::{fault_category}" so the same
    panel can have independent items for voltage, current, and power factor.

    Workflow rules
    --------------
    * Acknowledging an alert does NOT clear the electrical fault.
      The electrical_condition field reflects the actual simulated measurement.
    * A fault resolves only when update_from_fault_events() is called and
      the relevant condition is no longer in the fault event list.
    * Resolved items remain in the queue with priority=LOW for follow-up.
    """

    def __init__(self) -> None:
        self._items: dict = {}   # {item_id: MaintenanceItem}

    # ------------------------------------------------------------------
    # Mutation methods
    # ------------------------------------------------------------------

    def update_from_fault_events(
        self,
        fault_events: list,
        panel_registry: dict,
        now: Optional[datetime] = None,
    ) -> None:
        """
        Update the queue from a list of FaultEvents (one simulation tick).

        For each unique (panel_id, fault_category) in fault_events:
        - Create a new MaintenanceItem if one does not already exist.
        - Update latest_detected, measured_value, and priority if it does.

        For existing items whose (panel_id, fault_category) is NOT in
        fault_events, set electrical_condition to NORMAL and mark resolved.

        Parameters
        ----------
        fault_events : list[FaultEvent]
            Output of BuildingSimulator.step().
        panel_registry : dict[str, PanelState]
            Used to look up floor and location for new items.
        now : Optional[datetime]
            Timestamp to use; defaults to datetime.now().
        """
        if now is None:
            now = datetime.now()

        # Build a set of (panel_id, fault_category) currently active.
        active_keys: set = set()
        for fe in fault_events:
            # circuit format: "P-07/Phase-A" → extract panel_id
            panel_id = fe.circuit.split("/")[0] if "/" in fe.circuit else fe.circuit
            category = fe.parameter   # "voltage", "current", or "power_factor"
            key = f"{panel_id}::{category}"
            active_keys.add(key)

            if key not in self._items:
                # New item.
                ps = panel_registry.get(panel_id)
                floor = ps.definition.floor if ps else 0
                location = ps.definition.location if ps else panel_id
                injected = getattr(fe, "injected", False) if hasattr(fe, "injected") else False

                item = MaintenanceItem(
                    item_id=key,
                    panel_id=panel_id,
                    floor=floor,
                    location=location,
                    fault_category=category,
                    electrical_condition=fe.severity,
                    severity=fe.severity,
                    measured_value=fe.value,
                    unit=fe.unit,
                    threshold=fe.threshold,
                    first_detected=now,
                    latest_detected=now,
                    priority=compute_priority(fe.severity),
                    injected=injected,
                )
                self._items[key] = item
            else:
                # Update existing item.
                item = self._items[key]
                item.latest_detected = now
                item.measured_value = fe.value
                item.threshold = fe.threshold
                item.electrical_condition = fe.severity
                item.severity = fe.severity
                item.priority = compute_priority(fe.severity)
                # Re-open if previously resolved.
                if item.resolved_at is not None:
                    item.resolved_at = None
                    item.workflow_status = WORKFLOW_OPEN

        # Resolve items no longer in the active fault list.
        for key, item in self._items.items():
            if key not in active_keys and item.is_active:
                item.electrical_condition = CONDITION_NORMAL
                item.priority = PRIORITY_LOW
                item.resolved_at = now

    def acknowledge(self, item_id: str, now: Optional[datetime] = None) -> None:
        """
        Acknowledge an alert.

        Acknowledging records the time and changes workflow_status to
        ACKNOWLEDGED.  It does NOT clear the electrical fault.

        Raises
        ------
        KeyError
            If item_id is not in the queue.
        """
        if item_id not in self._items:
            raise KeyError(f"Maintenance item '{item_id}' not found.")
        if now is None:
            now = datetime.now()
        item = self._items[item_id]
        item.workflow_status = WORKFLOW_ACKNOWLEDGED
        item.acknowledged_at = now

    def add_note(self, item_id: str, note: str) -> None:
        """
        Append a technician note to a maintenance item.

        Raises
        ------
        KeyError
            If item_id is not in the queue.
        ValueError
            If note is empty.
        """
        if item_id not in self._items:
            raise KeyError(f"Maintenance item '{item_id}' not found.")
        if not note or not note.strip():
            raise ValueError("Note cannot be empty.")
        self._items[item_id].notes.append(note.strip())

    def mark_reviewed(self, item_id: str) -> None:
        """
        Mark an item as reviewed by the technician.

        Raises
        ------
        KeyError
            If item_id is not in the queue.
        """
        if item_id not in self._items:
            raise KeyError(f"Maintenance item '{item_id}' not found.")
        self._items[item_id].workflow_status = WORKFLOW_REVIEWED

    def clear_resolved(self) -> int:
        """
        Remove all fully resolved and reviewed items from the queue.

        Returns
        -------
        int
            Number of items removed.
        """
        to_remove = [
            k for k, v in self._items.items()
            if not v.is_active and v.workflow_status == WORKFLOW_REVIEWED
        ]
        for k in to_remove:
            del self._items[k]
        return len(to_remove)

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------

    def active_items(self) -> list:
        """Return items where electrical_condition is FAULT or WARNING."""
        return [v for v in self._items.values() if v.is_active]

    def all_items(self) -> list:
        """Return all items (active and resolved)."""
        return list(self._items.values())

    def filter_items(
        self,
        floor: Optional[int] = None,
        panel_id: Optional[str] = None,
        severity: Optional[str] = None,
        fault_category: Optional[str] = None,
        include_resolved: bool = True,
    ) -> list:
        """
        Return a filtered list of maintenance items.

        All filters are optional; only the specified filters are applied.
        """
        items = self.all_items() if include_resolved else self.active_items()
        if floor is not None:
            items = [i for i in items if i.floor == floor]
        if panel_id is not None:
            items = [i for i in items if i.panel_id == panel_id]
        if severity is not None:
            items = [i for i in items if i.severity == severity]
        if fault_category is not None:
            items = [i for i in items if i.fault_category == fault_category]
        return items

    def sorted_by_priority(self, include_resolved: bool = True) -> list:
        """
        Return items sorted by priority (HIGH → MEDIUM → LOW) then by
        first_detected (oldest first within each priority level).
        """
        items = self.all_items() if include_resolved else self.active_items()
        return sorted(
            items,
            key=lambda i: (PRIORITY_ORDER.get(i.priority, 99), i.first_detected),
        )

    def counts(self) -> dict:
        """Return {HIGH, MEDIUM, LOW, total} counts across all items."""
        all_i = self.all_items()
        return {
            "HIGH":   sum(1 for i in all_i if i.priority == PRIORITY_HIGH),
            "MEDIUM": sum(1 for i in all_i if i.priority == PRIORITY_MEDIUM),
            "LOW":    sum(1 for i in all_i if i.priority == PRIORITY_LOW),
            "total":  len(all_i),
        }

    def get_item(self, item_id: str) -> MaintenanceItem:
        """
        Retrieve a specific item by ID.

        Raises
        ------
        KeyError
            If item_id is not in the queue.
        """
        if item_id not in self._items:
            raise KeyError(f"Maintenance item '{item_id}' not found.")
        return self._items[item_id]
