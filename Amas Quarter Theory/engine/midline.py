"""Midline source resolution and reaction detection.

The active midline of the current hour (or current 3h block) is:
- the PRIOR candle's mid, if the current candle is strictly inside prior range
  (current.low > prior.low AND current.high < prior.high)
- otherwise the CURRENT candle's mid.

Equality on either side counts as broken-out (uses current).

Reaction detection:
- SUPPORT: wick below mid, close above mid
- REJECT: wick above mid, close below mid
"""
from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

MidlineSource = Literal["prior", "current"]


def resolve_midline_source(
    current_high: float,
    current_low: float,
    prior_high: Optional[float],
    prior_low: Optional[float],
) -> tuple[float, MidlineSource]:
    """Return (mid_price, source). If no prior, falls back to current."""
    if prior_high is None or prior_low is None:
        return ((current_high + current_low) / 2.0, "current")

    strictly_inside = (current_low > prior_low) and (current_high < prior_high)
    if strictly_inside:
        return ((prior_high + prior_low) / 2.0, "prior")
    return ((current_high + current_low) / 2.0, "current")


class MidlineReaction(str, Enum):
    SUPPORT = "support"     # wick below mid, close above
    REJECT = "reject"       # wick above mid, close below


def detect_midline_reaction(
    mid: float,
    bar_open: float,
    bar_high: float,
    bar_low: float,
    bar_close: float,
) -> Optional[MidlineReaction]:
    """Detect a wick-and-close reaction against the midline. None if no reaction."""
    if bar_low < mid and bar_close > mid:
        return MidlineReaction.SUPPORT
    if bar_high > mid and bar_close < mid:
        return MidlineReaction.REJECT
    return None
