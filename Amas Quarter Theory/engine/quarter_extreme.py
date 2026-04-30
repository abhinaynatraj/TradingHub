"""Per-hour: identify which quarter holds the hour's high and low,
and classify each as in-stat (Q1/Q4) or out-of-stat (Q2/Q3).

Tie-breaking: when multiple quarters reach the same extreme, the EARLIEST
quarter wins (smallest quarter_idx). This matches "first-touch" convention
for chart annotation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from engine.aggregations import HourAgg

IN_STAT_QUARTERS = (1, 4)


@dataclass(frozen=True)
class QuarterExtreme:
    quarter_idx: int
    side: Literal["high", "low"]
    in_stat: bool


def classify_quarter_extremes(hour: HourAgg) -> list[QuarterExtreme]:
    """Return the in/out-of-stat extremes (one for high, one for low)."""
    qs = [hour.q1, hour.q2, hour.q3, hour.q4]
    if any(q is None for q in qs):
        return []

    # Find earliest-quarter holders of the global high and low.
    hi_q = min(qs, key=lambda q: (-q.high, q.quarter_idx)).quarter_idx
    lo_q = min(qs, key=lambda q: (q.low, q.quarter_idx)).quarter_idx
    # Sorting tuples with tie-breakers: for high we want max value but earliest
    # quarter on ties → sort by (-high, quarter_idx) ascending picks earliest.
    return [
        QuarterExtreme(quarter_idx=hi_q, side="high", in_stat=hi_q in IN_STAT_QUARTERS),
        QuarterExtreme(quarter_idx=lo_q, side="low",  in_stat=lo_q in IN_STAT_QUARTERS),
    ]
