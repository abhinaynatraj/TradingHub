"""Pure classification functions for hour and triad structures.

CRITICAL: every function here must have a Pine analogue with byte-identical
output. These produce the canonical Python reference; parity is enforced in
Phase 9.

Conventions:
- All comparisons are STRICT (`<` and `>`). Equality breaks the line/apex
  pattern and downgrades to doji. Tested in test_classifier.py.
- Returns "pending" when the structure isn't fully formed yet (e.g. only
  C1+C2 of a triad). The state-vector builder uses this to decide what to
  encode.
"""
from __future__ import annotations

from typing import Literal

from engine.aggregations import HourAgg, TriadAgg

HourClass = Literal["line-up", "line-down", "doji", "pending"]
TriadClass = Literal["line-up", "line-down", "apex-up", "apex-down", "doji", "pending"]


def classify_hour(hour: HourAgg) -> HourClass:
    """Classify a 1h hour by its 4 quarters' high/low stacking pattern.

    Returns "pending" if any of Q1..Q4 is missing.
    """
    qs = [hour.q1, hour.q2, hour.q3, hour.q4]
    if any(q is None for q in qs):
        return "pending"
    h = [q.high for q in qs]
    l = [q.low for q in qs]
    if h[0] < h[1] < h[2] < h[3] and l[0] < l[1] < l[2] < l[3]:
        return "line-up"
    if h[0] > h[1] > h[2] > h[3] and l[0] > l[1] > l[2] > l[3]:
        return "line-down"
    return "doji"


def classify_triad(triad: TriadAgg) -> TriadClass:
    """Classify a 3h triad by its three 1h candles' high/low pattern.

    Returns "pending" if any of C1..C3 is missing.
    """
    hs = [triad.c1, triad.c2, triad.c3]
    if any(h is None for h in hs):
        return "pending"
    h_high = [h.high for h in hs]
    h_low = [h.low for h in hs]
    if any(v is None for v in h_high + h_low):
        return "pending"
    if h_high[0] < h_high[1] < h_high[2] and h_low[0] < h_low[1] < h_low[2]:
        return "line-up"
    if h_high[0] > h_high[1] > h_high[2] and h_low[0] > h_low[1] > h_low[2]:
        return "line-down"
    if h_high[0] < h_high[1] > h_high[2]:
        return "apex-up"
    if h_low[0] > h_low[1] < h_low[2]:
        return "apex-down"
    return "doji"


from dataclasses import dataclass


@dataclass(frozen=True, order=True)
class SweepEvent:
    """A strict break of a prior quarter's extreme by a later quarter, within an hour."""
    by_q: int           # 2..4
    target_q: int       # 1..(by_q-1)
    side: str           # "high" or "low"


def detect_sweeps_in_hour(hour: HourAgg) -> list[SweepEvent]:
    """Return all sweep events in the hour, sorted by (by_q, target_q, side).

    Sweep = later quarter's high strictly > earlier quarter's high (or low <).
    Equality does NOT trigger a sweep.
    """
    qs = [hour.q1, hour.q2, hour.q3, hour.q4]
    sweeps: list[SweepEvent] = []
    for by_idx in range(1, 4):       # Q2, Q3, Q4 → indices 1, 2, 3 in zero-based
        by_q = qs[by_idx]
        if by_q is None:
            continue
        for target_idx in range(0, by_idx):
            target_q = qs[target_idx]
            if target_q is None:
                continue
            if by_q.high > target_q.high:
                sweeps.append(SweepEvent(by_q=by_q.quarter_idx, target_q=target_q.quarter_idx, side="high"))
            if by_q.low < target_q.low:
                sweeps.append(SweepEvent(by_q=by_q.quarter_idx, target_q=target_q.quarter_idx, side="low"))
    sweeps.sort()
    return sweeps
