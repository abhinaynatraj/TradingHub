"""Running aggregation state objects: quarter → hour → triad.

Each level holds raw OHL extremes and tracks the anchor timestamp of the
candle that printed the extreme. These are the facts the classifier and
state-vector consume.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd


@dataclass
class QuarterAgg:
    quarter_idx: int                            # 1..4
    anchor_ts: pd.Timestamp                     # quarter open timestamp
    open_: Optional[float] = None
    close: Optional[float] = None
    high: float = float("-inf")
    low: float = float("inf")
    high_anchor_ts: Optional[pd.Timestamp] = None
    low_anchor_ts: Optional[pd.Timestamp] = None
    bar_count: int = 0

    def update(
        self,
        ts: pd.Timestamp,
        open_: float,
        high: float,
        low: float,
        close: float,
    ) -> None:
        if self.bar_count == 0:
            self.open_ = open_
        self.close = close
        if high > self.high:
            self.high = high
            self.high_anchor_ts = ts
        if low < self.low:
            self.low = low
            self.low_anchor_ts = ts
        self.bar_count += 1

    @property
    def mid(self) -> float:
        return (self.high + self.low) / 2.0


@dataclass
class HourAgg:
    anchor_ts: pd.Timestamp                     # HH:00 of the hour
    q1: Optional[QuarterAgg] = None
    q2: Optional[QuarterAgg] = None
    q3: Optional[QuarterAgg] = None
    q4: Optional[QuarterAgg] = None
    box_05_high: Optional[float] = None
    box_05_low: Optional[float] = None
    box_05_locked: bool = False                 # True after the :04 bar closes

    def quarters(self) -> list[QuarterAgg]:
        return [q for q in (self.q1, self.q2, self.q3, self.q4) if q is not None]

    @property
    def high(self) -> Optional[float]:
        qs = self.quarters()
        return max(q.high for q in qs) if qs else None

    @property
    def low(self) -> Optional[float]:
        qs = self.quarters()
        return min(q.low for q in qs) if qs else None

    @property
    def mid(self) -> Optional[float]:
        if self.high is None or self.low is None:
            return None
        return (self.high + self.low) / 2.0


@dataclass
class TriadAgg:
    block_id: str
    anchor_ts: pd.Timestamp                     # C1 anchor (HH:00 of block start)
    c1: Optional[HourAgg] = None
    c2: Optional[HourAgg] = None
    c3: Optional[HourAgg] = None

    def hours(self) -> list[HourAgg]:
        return [h for h in (self.c1, self.c2, self.c3) if h is not None]

    @property
    def high(self) -> Optional[float]:
        hs = [h for h in self.hours() if h.high is not None]
        return max(h.high for h in hs) if hs else None

    @property
    def low(self) -> Optional[float]:
        hs = [h for h in self.hours() if h.low is not None]
        return min(h.low for h in hs) if hs else None

    @property
    def mid(self) -> Optional[float]:
        if self.high is None or self.low is None:
            return None
        return (self.high + self.low) / 2.0
