"""
logger.py — Persistent CSV fault event log.

Schema (CSV columns):
    timestamp  — ISO-format datetime string
    circuit    — circuit or phase name (e.g. "Phase-A", "Motor-1")
    parameter  — "voltage", "current", or "power_factor"
    value      — measured value at time of fault
    unit       — "V", "A", or "PF"
    threshold  — threshold value that was crossed
    severity   — "WARNING" or "FAULT"
    message    — human-readable description

Design notes:
    - The CSV is appended on each write so it survives browser reloads.
    - A row cap (config.MAX_LOG_ROWS) prevents unbounded file growth during
      long demo sessions.  Trimming reads and rewrites the file only when the
      cap is exceeded, keeping normal-path I/O to a single append operation.
    - All file operations are wrapped in try/except so a log I/O error never
      crashes the dashboard.
"""

import pandas as pd

import config
from fault_detector import FaultEvent

CSV_COLUMNS: list[str] = [
    "timestamp", "circuit", "parameter", "value",
    "unit", "threshold", "severity", "message",
]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ensure_data_dir() -> None:
    """Create the directory that contains the CSV log if it doesn't exist."""
    config.FAULT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def _trim_log() -> None:
    """
    If the CSV exceeds config.MAX_LOG_ROWS, keep only the most recent rows.

    Reads and rewrites the file only when the row count exceeds the cap, so
    normal-path appends never trigger a full read-write cycle.
    """
    try:
        if not config.FAULT_LOG_PATH.exists():
            return
        df = pd.read_csv(config.FAULT_LOG_PATH)
        if len(df) > config.MAX_LOG_ROWS:
            df.tail(config.MAX_LOG_ROWS).to_csv(
                config.FAULT_LOG_PATH, index=False
            )
    except Exception:
        pass  # Never crash the dashboard due to a trim failure.


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def append_faults(fault_events: list[FaultEvent]) -> None:
    """
    Append a list of FaultEvents to the persistent CSV log.

    Creates the file (with header) on first call; appends without header on
    subsequent calls.  No-ops silently if fault_events is empty.

    Args:
        fault_events: List of FaultEvent instances to persist.
    """
    if not fault_events:
        return
    try:
        _ensure_data_dir()
        rows = [fe.to_dict() for fe in fault_events]
        df   = pd.DataFrame(rows, columns=CSV_COLUMNS)
        file_exists = config.FAULT_LOG_PATH.exists()
        df.to_csv(
            config.FAULT_LOG_PATH,
            mode="a",
            header=not file_exists,
            index=False,
        )
        _trim_log()
    except Exception:
        pass  # Never crash the dashboard due to a log write failure.


def load_recent(n: int = 50) -> pd.DataFrame:
    """
    Load the most recent n fault events from the CSV, newest first.

    Args:
        n: Maximum number of rows to return.

    Returns:
        DataFrame with columns matching CSV_COLUMNS, newest rows first.
        Returns an empty DataFrame (correct columns) if the file is missing
        or malformed.
    """
    try:
        if not config.FAULT_LOG_PATH.exists():
            return pd.DataFrame(columns=CSV_COLUMNS)
        df = pd.read_csv(config.FAULT_LOG_PATH, parse_dates=["timestamp"])
        if df.empty:
            return pd.DataFrame(columns=CSV_COLUMNS)
        return df.tail(n).iloc[::-1].reset_index(drop=True)
    except Exception:
        return pd.DataFrame(columns=CSV_COLUMNS)


def clear_log() -> None:
    """
    Delete the CSV fault log.

    Idempotent — does nothing if the file does not exist.
    """
    try:
        config.FAULT_LOG_PATH.unlink(missing_ok=True)
    except Exception:
        pass


def fault_counts(severity_filter: str | None = None) -> dict:
    """
    Return fault event counts grouped by severity.

    Args:
        severity_filter: If provided (e.g. "FAULT"), return the count for
                         that severity only in the dict.  If None, return all.

    Returns:
        Dict like {"WARNING": 42, "FAULT": 7, "total": 49}.
        Returns zero-counts if the file does not exist.
    """
    empty = {"WARNING": 0, "FAULT": 0, "total": 0}
    try:
        if not config.FAULT_LOG_PATH.exists():
            return empty
        df = pd.read_csv(config.FAULT_LOG_PATH, usecols=["severity"])
        if df.empty:
            return empty
        counts = df["severity"].value_counts().to_dict()
        result = {
            "WARNING": int(counts.get("WARNING", 0)),
            "FAULT":   int(counts.get("FAULT", 0)),
            "total":   len(df),
        }
        if severity_filter:
            return {severity_filter: result.get(severity_filter, 0)}
        return result
    except Exception:
        return empty
