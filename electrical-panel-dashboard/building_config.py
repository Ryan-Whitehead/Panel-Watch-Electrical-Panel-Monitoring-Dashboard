"""
building_config.py — Runtime building floor configuration for PanelWatch.

Purpose
-------
Provides a pure-Python layer between the static panel definitions in
config.BUILDING_PANELS and the live BuildingSimulator.  This allows users to
configure the number of floors through the dashboard without modifying any
static constants.

The floor count is a presentation / routing concern, not an electrical one.
Panel electrical parameters (rated current, nominal PF, voltage) are
unchanged by floor reassignment — only the floor number and location label
are updated.

Key design decisions
--------------------
* config.BUILDING_PANELS is never mutated.  distribute_panels() always returns
  a fresh list of copies.
* Panel identifiers (P-01 … P-20) are always preserved so fault log entries
  and maintenance records remain consistent across floor reconfigurations.
* Historical fault events in fault_log.csv retain the floor information
  recorded at the time of the event.  Only the live simulation is updated.
* The distribution algorithm is round-robin (deterministic, reproducible).

Functions
---------
distribute_panels(panels, num_floors) -> list[dict]
    Return a copy of panels with floor assignments remapped to [1..num_floors].

active_floors(panels) -> list[int]
    Return sorted list of occupied floor numbers.

panel_ids_for_demo(panels) -> str
    Return the panel_id of the first panel in the (remapped) list, used as the
    default target for the guided maintenance demonstration.
"""

# ---------------------------------------------------------------------------
# Floor configuration constants
# ---------------------------------------------------------------------------

DEFAULT_NUM_FLOORS: int = 12   # Default matches config.BUILDING_PANELS
MIN_FLOORS: int = 1
MAX_FLOORS: int = 50


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def distribute_panels(panels: list, num_floors: int) -> list:
    """
    Return a copy of *panels* with floor assignments remapped to [1..num_floors].

    Algorithm: round-robin
    ----------------------
    Panel i (0-indexed) is assigned to floor (i % num_floors) + 1.

    Properties guaranteed by this algorithm:
    - Every panel is assigned exactly one floor in [1, num_floors].
    - All panel_ids remain unique.
    - No new panels are created.
    - Panels are distributed as evenly as possible (differ by at most 1).
    - The mapping is deterministic and reproducible for any input.

    Examples
    --------
    20 panels, 5 floors  → 4 panels per floor (floors 1–5 each get 4)
    20 panels, 10 floors → 2 panels per floor
    20 panels, 20 floors → 1 panel per floor
    20 panels, 25 floors → panels on floors 1–20, floors 21–25 empty
    20 panels, 3 floors  → floors 1/2/3 get 7/7/6 panels respectively

    Parameters
    ----------
    panels : list[dict]
        Panel definition dicts (from config.BUILDING_PANELS or a subset).
        Each dict must contain at minimum a "panel_id" key.
    num_floors : int
        Target number of floors.  Must be >= MIN_FLOORS.

    Returns
    -------
    list[dict]
        New list of dicts.  Each dict is a shallow copy of the original with
        the "floor" key replaced by the remapped floor number and the
        "location" key updated to reflect the new floor.

    Raises
    ------
    ValueError
        If num_floors < MIN_FLOORS or panels is empty.
    """
    if num_floors < MIN_FLOORS:
        raise ValueError(
            f"num_floors must be >= {MIN_FLOORS}, got {num_floors}"
        )
    if not panels:
        return []

    result = []
    for idx, panel in enumerate(panels):
        new_floor = (idx % num_floors) + 1
        updated = dict(panel)
        updated["floor"] = new_floor
        # Update location label to include new floor number so the UI
        # always shows the current assignment rather than the config default.
        # We strip any existing " (Floor N)" suffix before re-appending.
        base_location = _strip_floor_suffix(panel.get("location", ""))
        updated["location"] = f"{base_location} (Floor {new_floor})"
        result.append(updated)
    return result


def active_floors(panels: list) -> list:
    """
    Return a sorted list of floor numbers that have at least one panel.

    Parameters
    ----------
    panels : list[dict]
        Remapped panel definitions (output of distribute_panels).

    Returns
    -------
    list[int]
        Sorted ascending.  Empty list if panels is empty.
    """
    return sorted({p["floor"] for p in panels})


def panel_ids_for_demo(panels: list) -> str:
    """
    Return the panel_id of the first panel in *panels*.

    This is used by the guided maintenance demonstration to select a default
    target panel without hard-coding "P-07" or assuming any specific floor.

    Parameters
    ----------
    panels : list[dict]
        Remapped panel definitions.  Must be non-empty.

    Returns
    -------
    str
        panel_id of panels[0].

    Raises
    ------
    ValueError
        If panels is empty.
    """
    if not panels:
        raise ValueError("panels must be non-empty to select a demo panel")
    return panels[0]["panel_id"]


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _strip_floor_suffix(location: str) -> str:
    """
    Remove a trailing ' (Floor N)' suffix from a location string.

    Used to avoid double-appending floor numbers when redistribute_panels is
    called more than once on the same panel list.

    >>> _strip_floor_suffix("East Wing Office (Floor 3)")
    'East Wing Office'
    >>> _strip_floor_suffix("Main Service Entrance")
    'Main Service Entrance'
    """
    import re
    return re.sub(r"\s*\(Floor \d+\)\s*$", "", location).strip()
