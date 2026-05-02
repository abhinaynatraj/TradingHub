"""Single source of truth for time/structure constants used across the engine and Pine.

Schema version is the contract between Python and Pine. Changing it requires a
full rebuild + re-paste + parity re-validation.
"""
from __future__ import annotations

from typing import Optional

# Contract version. Bump only when changing the state-vector schema.
SCHEMA_VERSION: str = "v1"

# NY-time 3h triad blocks. Format: "HH-HH" (start-end). Sorted by start hour.
# 15:00-18:00 is excluded per spec — no triad covers that range.
BLOCK_IDS: tuple[str, ...] = (
    "00-03", "03-06", "06-09", "09-12", "12-15", "18-21", "21-00",
)

# Map hour-of-day (0..23 in NY tz) → block id, or None if hour is in the excluded gap.
_BLOCK_BY_HOUR: dict[int, Optional[str]] = {
    **{h: "00-03" for h in (0, 1, 2)},
    **{h: "03-06" for h in (3, 4, 5)},
    **{h: "06-09" for h in (6, 7, 8)},
    **{h: "09-12" for h in (9, 10, 11)},
    **{h: "12-15" for h in (12, 13, 14)},
    **{h: None for h in (15, 16, 17)},
    **{h: "18-21" for h in (18, 19, 20)},
    **{h: "21-00" for h in (21, 22, 23)},
}


def block_for_hour(hour: int) -> Optional[str]:
    """Return the block-id for a given NY-time hour, or None if hour is in the excluded gap."""
    if hour < 0 or hour > 23:
        raise ValueError(f"hour must be in [0,23], got {hour}")
    return _BLOCK_BY_HOUR[hour]


def quarter_for_minute(minute: int) -> int:
    """Return 1..4 for the quarter-of-hour. Q1=:00..:14, Q2=:15..:29, Q3=:30..:44, Q4=:45..:59."""
    if minute < 0 or minute > 59:
        raise ValueError(f"minute must be in [0,59], got {minute}")
    return minute // 15 + 1


# Outcome resolver lookback (matches Amas Models / Fractal Sweep).
OUTCOME_MAX_BARS: int = 1440  # 1 trading day of 1m bars

# Supported instruments and their DuckDB table names.
SUPPORTED_SYMBOLS: tuple[str, ...] = ("NQ", "ES")
TABLE_FOR_SYMBOL: dict[str, str] = {"NQ": "nq_1m", "ES": "es_1m"}

# 05-box band percentage offsets, in absolute decimal form. Applied as
# `box_high * (1 + offset)` for upper bands and `box_low * (1 - offset)` for lower.
BAND_OFFSETS: tuple[float, ...] = (0.0005, 0.0010)  # 0.05%, 0.10%

# 05-box minute bars (inclusive).
BOX_05_MINUTES: tuple[int, ...] = (0, 1, 2, 3, 4)

# Hour-of-triad indices (C1, C2, C3 → 1, 2, 3).
HOUR_INDICES: tuple[int, ...] = (1, 2, 3)
