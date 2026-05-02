"""Time/structure primitives derived from a tz-aware NY-time pd.Timestamp.

These are the Python equivalents of the Pine `time_primitives` section. Every
function here must have a Pine analogue with byte-identical output.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from engine import constants as C


def quarter_of(ts: pd.Timestamp) -> int:
    """Return 1..4 for the quarter-of-hour."""
    return C.quarter_for_minute(ts.minute)


def block_id_of(ts: pd.Timestamp) -> Optional[str]:
    """Return the 3h triad block id, or None if ts is in the 15:00-18:00 excluded gap."""
    return C.block_for_hour(ts.hour)


def hour_index_in_triad(ts: pd.Timestamp) -> Optional[int]:
    """Return 1, 2, or 3 (C1, C2, C3 of the triad), or None if ts is in the excluded gap."""
    block = block_id_of(ts)
    if block is None:
        return None
    start_hour = int(block.split("-")[0])
    # block "21-00" wraps; hour 21 → C1, 22 → C2, 23 → C3.
    return ts.hour - start_hour + 1


def triad_anchor_ts(ts: pd.Timestamp) -> pd.Timestamp:
    """Return the timestamp of the first 1m bar (HH:00:00) of C1 of the triad containing ts.

    Raises ValueError if ts is in the excluded gap.
    """
    block = block_id_of(ts)
    if block is None:
        raise ValueError(f"ts {ts} is in the excluded 15:00-18:00 gap")
    start_hour = int(block.split("-")[0])
    return ts.normalize() + pd.Timedelta(hours=start_hour)


def hour_anchor_ts(ts: pd.Timestamp) -> pd.Timestamp:
    """Return HH:00:00 of the hour ts belongs to."""
    return ts.normalize() + pd.Timedelta(hours=ts.hour)


def quarter_anchor_ts(ts: pd.Timestamp) -> pd.Timestamp:
    """Return HH:MM:00 of the quarter ts belongs to (one of :00, :15, :30, :45)."""
    q = quarter_of(ts)
    minute = (q - 1) * 15
    return ts.normalize() + pd.Timedelta(hours=ts.hour, minutes=minute)
