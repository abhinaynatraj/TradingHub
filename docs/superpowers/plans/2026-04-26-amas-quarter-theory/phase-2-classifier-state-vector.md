# Phase 2 — Classifier + State Vector

> **Sub-skill:** Use superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** Pure functions for hour/triad/sweep/midline/05-box classification, plus state-key builder. End state: full test coverage on classifier rules and state-key format. This phase produces the **canonical Python reference** that Pine must match (parity tests come in Phase 9).

**Prereq:** Phase 1 complete.

---

### Task 2.1: Aggregation dataclasses

**Files:**
- Create: `engine/aggregations.py`
- Create: `tests/test_aggregations.py`

- [ ] **Step 1: Write the failing test**

File: `tests/test_aggregations.py`

```python
"""Tests for engine.aggregations — running quarter/hour/triad state objects."""
from __future__ import annotations

import pandas as pd
import pytest

from engine.aggregations import QuarterAgg, HourAgg, TriadAgg


def _ts(s: str) -> pd.Timestamp:
    return pd.Timestamp(s, tz="America/New_York")


def test_quarter_agg_update_tracks_extremes_and_anchors():
    q = QuarterAgg(quarter_idx=2, anchor_ts=_ts("2024-01-02 09:15"))
    q.update(_ts("2024-01-02 09:15"), open_=100.0, high=101.0, low=99.5, close=100.5)
    q.update(_ts("2024-01-02 09:18"), open_=100.5, high=102.0, low=100.0, close=101.5)
    q.update(_ts("2024-01-02 09:24"), open_=101.5, high=101.7, low=98.5, close=99.0)

    assert q.high == 102.0
    assert q.low == 98.5
    assert q.high_anchor_ts == _ts("2024-01-02 09:18")
    assert q.low_anchor_ts == _ts("2024-01-02 09:24")
    assert q.open_ == 100.0
    assert q.close == 99.0
    assert q.bar_count == 3


def test_quarter_agg_mid_is_high_low_average():
    q = QuarterAgg(quarter_idx=1, anchor_ts=_ts("2024-01-02 09:00"))
    q.update(_ts("2024-01-02 09:00"), open_=100.0, high=110.0, low=90.0, close=105.0)
    assert q.mid == 100.0


def test_hour_agg_holds_four_quarters_and_05_box():
    h = HourAgg(anchor_ts=_ts("2024-01-02 09:00"))
    assert h.q1 is None and h.q2 is None and h.q3 is None and h.q4 is None
    assert h.box_05_high is None and h.box_05_low is None


def test_hour_agg_high_low_aggregate_quarters():
    h = HourAgg(anchor_ts=_ts("2024-01-02 09:00"))
    h.q1 = QuarterAgg(quarter_idx=1, anchor_ts=_ts("2024-01-02 09:00"))
    h.q1.high = 105.0; h.q1.low = 99.0
    h.q2 = QuarterAgg(quarter_idx=2, anchor_ts=_ts("2024-01-02 09:15"))
    h.q2.high = 107.0; h.q2.low = 100.0
    assert h.high == 107.0
    assert h.low == 99.0


def test_hour_agg_high_low_returns_none_when_no_quarters():
    h = HourAgg(anchor_ts=_ts("2024-01-02 09:00"))
    assert h.high is None
    assert h.low is None


def test_hour_agg_mid():
    h = HourAgg(anchor_ts=_ts("2024-01-02 09:00"))
    h.q1 = QuarterAgg(quarter_idx=1, anchor_ts=_ts("2024-01-02 09:00"))
    h.q1.high = 110.0; h.q1.low = 90.0
    assert h.mid == 100.0


def test_triad_agg_holds_three_hours():
    t = TriadAgg(block_id="09-12", anchor_ts=_ts("2024-01-02 09:00"))
    assert t.c1 is None and t.c2 is None and t.c3 is None


def test_triad_agg_high_low_mid_aggregate_hours():
    t = TriadAgg(block_id="09-12", anchor_ts=_ts("2024-01-02 09:00"))
    t.c1 = HourAgg(anchor_ts=_ts("2024-01-02 09:00"))
    t.c1.q1 = QuarterAgg(1, _ts("2024-01-02 09:00")); t.c1.q1.high = 105.0; t.c1.q1.low = 95.0
    t.c2 = HourAgg(anchor_ts=_ts("2024-01-02 10:00"))
    t.c2.q1 = QuarterAgg(1, _ts("2024-01-02 10:00")); t.c2.q1.high = 110.0; t.c2.q1.low = 102.0
    assert t.high == 110.0
    assert t.low == 95.0
    assert t.mid == 102.5
```

- [ ] **Step 2: Run the test to verify FAIL**

```bash
python3 -m pytest tests/test_aggregations.py -v
```
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `engine/aggregations.py`**

File: `engine/aggregations.py`

```python
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
```

- [ ] **Step 4: Run tests to verify PASS**

```bash
python3 -m pytest tests/test_aggregations.py -v
```
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add engine/aggregations.py tests/test_aggregations.py
git commit -m "feat(quarter-theory): add quarter/hour/triad aggregation dataclasses"
```

---

### Task 2.2: Hour & triad classifier (line-up / line-dn / doji / apex-up / apex-dn)

**Files:**
- Create: `engine/classifier.py`
- Create: `tests/test_classifier.py`

- [ ] **Step 1: Write the failing test**

File: `tests/test_classifier.py`

```python
"""Tests for engine.classifier — hour and triad classification.

Spec rules:
- line-up hour: Q1.h<Q2.h<Q3.h<Q4.h AND Q1.l<Q2.l<Q3.l<Q4.l (strict on both sides)
- line-down hour: monotonic mirror
- doji hour: anything else
- 3h line-up: C1.h<C2.h<C3.h AND C1.l<C2.l<C3.l (strict)
- 3h line-down: mirror
- 3h apex-up: C1.h<C2.h>C3.h (C2 makes swing high)
- 3h apex-down: C1.l>C2.l<C3.l (C2 makes swing low)
- 3h doji: anything else
- Equality on any comparison disqualifies line/apex.
"""
from __future__ import annotations

import pandas as pd

from engine.aggregations import QuarterAgg, HourAgg, TriadAgg
from engine.classifier import classify_hour, classify_triad


def _ts(s: str) -> pd.Timestamp:
    return pd.Timestamp(s, tz="America/New_York")


def _q(idx: int, h: float, l: float) -> QuarterAgg:
    q = QuarterAgg(quarter_idx=idx, anchor_ts=_ts(f"2024-01-02 09:{(idx-1)*15:02d}"))
    q.high = h; q.low = l
    return q


def _hour_with(highs: list[float], lows: list[float], anchor: str = "2024-01-02 09:00") -> HourAgg:
    h = HourAgg(anchor_ts=_ts(anchor))
    h.q1 = _q(1, highs[0], lows[0])
    h.q2 = _q(2, highs[1], lows[1])
    h.q3 = _q(3, highs[2], lows[2])
    h.q4 = _q(4, highs[3], lows[3])
    return h


# ── HOUR CLASSIFICATION ──────────────────────────────────────────────────────

def test_classify_hour_line_up_strict():
    h = _hour_with([100, 101, 102, 103], [99, 99.5, 100, 100.5])
    assert classify_hour(h) == "line-up"


def test_classify_hour_line_down_strict():
    h = _hour_with([103, 102, 101, 100], [100.5, 100, 99.5, 99])
    assert classify_hour(h) == "line-down"


def test_classify_hour_doji_when_highs_dont_stack():
    h = _hour_with([100, 102, 101, 103], [99, 99.5, 100, 100.5])  # Q3 high < Q2 high
    assert classify_hour(h) == "doji"


def test_classify_hour_doji_when_lows_dont_stack():
    h = _hour_with([100, 101, 102, 103], [99, 99.5, 99.4, 100.5])  # Q3 low < Q2 low
    assert classify_hour(h) == "doji"


def test_classify_hour_equality_is_doji_not_line():
    # Q1.high == Q2.high → strict comparison fails → doji
    h = _hour_with([100, 100, 102, 103], [99, 99.5, 100, 100.5])
    assert classify_hour(h) == "doji"


def test_classify_hour_returns_pending_if_quarters_missing():
    h = HourAgg(anchor_ts=_ts("2024-01-02 09:00"))
    h.q1 = _q(1, 100, 99); h.q2 = _q(2, 101, 99.5)
    # Q3, Q4 not yet formed
    assert classify_hour(h) == "pending"


# ── TRIAD CLASSIFICATION ─────────────────────────────────────────────────────

def _triad_with(c1_h: float, c1_l: float, c2_h: float, c2_l: float, c3_h: float, c3_l: float) -> TriadAgg:
    """Build a 3-hour triad with the given hourly highs/lows. Each hour has its quarters
    set so HourAgg.high/low resolve cleanly."""
    t = TriadAgg(block_id="09-12", anchor_ts=_ts("2024-01-02 09:00"))
    for idx, (anchor, hi, lo) in enumerate([
        ("2024-01-02 09:00", c1_h, c1_l),
        ("2024-01-02 10:00", c2_h, c2_l),
        ("2024-01-02 11:00", c3_h, c3_l),
    ], start=1):
        h = HourAgg(anchor_ts=_ts(anchor))
        h.q1 = _q(1, hi, lo)
        setattr(t, f"c{idx}", h)
    return t


def test_classify_triad_line_up_strict():
    t = _triad_with(c1_h=100, c1_l=98, c2_h=102, c2_l=99, c3_h=104, c3_l=100)
    assert classify_triad(t) == "line-up"


def test_classify_triad_line_down_strict():
    t = _triad_with(c1_h=104, c1_l=100, c2_h=102, c2_l=99, c3_h=100, c3_l=98)
    assert classify_triad(t) == "line-down"


def test_classify_triad_apex_up_swing_high_at_c2():
    # C1.h < C2.h > C3.h. Lows do NOT need to form a clean apex pattern for apex-up.
    t = _triad_with(c1_h=100, c1_l=98, c2_h=105, c2_l=99, c3_h=103, c3_l=100)
    assert classify_triad(t) == "apex-up"


def test_classify_triad_apex_down_swing_low_at_c2():
    # C1.l > C2.l < C3.l.
    t = _triad_with(c1_h=104, c1_l=100, c2_h=103, c2_l=95, c3_h=102, c3_l=98)
    assert classify_triad(t) == "apex-down"


def test_classify_triad_doji_when_no_clean_pattern():
    # No monotonic stack, no clean swing
    t = _triad_with(c1_h=100, c1_l=98, c2_h=102, c2_l=97, c3_h=101, c3_l=99)
    assert classify_triad(t) == "doji"


def test_classify_triad_equality_is_doji_not_line():
    t = _triad_with(c1_h=100, c1_l=98, c2_h=100, c2_l=99, c3_h=104, c3_l=100)
    assert classify_triad(t) == "doji"


def test_classify_triad_pending_when_hours_missing():
    t = TriadAgg(block_id="09-12", anchor_ts=_ts("2024-01-02 09:00"))
    h = HourAgg(anchor_ts=_ts("2024-01-02 09:00"))
    h.q1 = _q(1, 100, 99)
    t.c1 = h
    # C2, C3 not yet
    assert classify_triad(t) == "pending"
```

- [ ] **Step 2: Run the test to verify FAIL**

```bash
python3 -m pytest tests/test_classifier.py -v
```
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `engine/classifier.py`**

File: `engine/classifier.py`

```python
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
```

- [ ] **Step 4: Run tests to verify PASS**

```bash
python3 -m pytest tests/test_classifier.py -v
```
Expected: 13 passed.

- [ ] **Step 5: Commit**

```bash
git add engine/classifier.py tests/test_classifier.py
git commit -m "feat(quarter-theory): add hour/triad classifier with strict comparisons"
```

---

### Task 2.3: Sweep detection within an hour

**Files:**
- Modify: `engine/classifier.py` (add `detect_sweeps_in_hour`)
- Create: `tests/test_sweeps.py`

- [ ] **Step 1: Write the failing test**

File: `tests/test_sweeps.py`

```python
"""Tests for sweep detection. A sweep is a STRICT break (>) of a prior
quarter's extreme by a later quarter, within the same hour."""
from __future__ import annotations

import pandas as pd

from engine.aggregations import QuarterAgg, HourAgg
from engine.classifier import detect_sweeps_in_hour, SweepEvent


def _ts(s: str) -> pd.Timestamp:
    return pd.Timestamp(s, tz="America/New_York")


def _q(idx: int, h: float, l: float, anchor: str | None = None) -> QuarterAgg:
    if anchor is None:
        anchor = f"2024-01-02 09:{(idx-1)*15:02d}"
    q = QuarterAgg(quarter_idx=idx, anchor_ts=_ts(anchor))
    q.high = h; q.low = l
    q.high_anchor_ts = _ts(anchor)
    q.low_anchor_ts = _ts(anchor)
    return q


def _hour(qs: list[QuarterAgg]) -> HourAgg:
    h = HourAgg(anchor_ts=_ts("2024-01-02 09:00"))
    for q in qs:
        setattr(h, f"q{q.quarter_idx}", q)
    return h


def test_no_sweeps_when_only_q1():
    h = _hour([_q(1, 100, 99)])
    assert detect_sweeps_in_hour(h) == []


def test_q2_sweeps_q1_high():
    h = _hour([_q(1, 100, 99), _q(2, 101, 99.5)])
    sweeps = detect_sweeps_in_hour(h)
    assert SweepEvent(by_q=2, target_q=1, side="high") in sweeps


def test_q2_sweeps_q1_low():
    h = _hour([_q(1, 100, 99), _q(2, 100, 98.5)])
    sweeps = detect_sweeps_in_hour(h)
    assert SweepEvent(by_q=2, target_q=1, side="low") in sweeps


def test_q2_sweeps_both_high_and_low_of_q1():
    h = _hour([_q(1, 100, 99), _q(2, 101, 98)])
    sweeps = detect_sweeps_in_hour(h)
    assert SweepEvent(by_q=2, target_q=1, side="high") in sweeps
    assert SweepEvent(by_q=2, target_q=1, side="low") in sweeps


def test_equality_is_not_a_sweep():
    # Q2 high == Q1 high → not a sweep
    h = _hour([_q(1, 100, 99), _q(2, 100, 98)])
    sweeps = detect_sweeps_in_hour(h)
    high_sweeps = [s for s in sweeps if s.side == "high"]
    assert high_sweeps == []  # equality doesn't trigger


def test_q3_sweeps_q1_and_q2_separately():
    # Q3 high (105) > Q1 high (100) AND > Q2 high (101) — two sweeps
    h = _hour([_q(1, 100, 99), _q(2, 101, 99.5), _q(3, 105, 99.7)])
    sweeps = detect_sweeps_in_hour(h)
    assert SweepEvent(by_q=3, target_q=1, side="high") in sweeps
    assert SweepEvent(by_q=3, target_q=2, side="high") in sweeps


def test_sweeps_sorted_by_by_q_then_target_q_then_side():
    h = _hour([_q(1, 100, 99), _q(2, 101, 98), _q(3, 102, 97)])
    sweeps = detect_sweeps_in_hour(h)
    # Must be sorted: smaller by_q first, smaller target_q, then side ('high' < 'low')
    keys = [(s.by_q, s.target_q, s.side) for s in sweeps]
    assert keys == sorted(keys)
```

- [ ] **Step 2: Run the test to verify FAIL**

```bash
python3 -m pytest tests/test_sweeps.py -v
```
Expected: FAIL — `ImportError: cannot import name 'detect_sweeps_in_hour'`.

- [ ] **Step 3: Add `detect_sweeps_in_hour` and `SweepEvent` to `engine/classifier.py`**

Append to `engine/classifier.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify PASS**

```bash
python3 -m pytest tests/test_sweeps.py tests/test_classifier.py -v
```
Expected: 7 + 13 = 20 passed.

- [ ] **Step 5: Commit**

```bash
git add engine/classifier.py tests/test_sweeps.py
git commit -m "feat(quarter-theory): add sweep detection (strict break, sorted output)"
```

---

### Task 2.4: 05-box and band derivation

**Files:**
- Create: `engine/box_05.py`
- Create: `tests/test_box_05.py`

- [ ] **Step 1: Write the failing test**

File: `tests/test_box_05.py`

```python
"""Tests for 05-box construction and band level derivation.

The 05-box is the price range across the first 5 minute bars of an hour
(:00, :01, :02, :03, :04 inclusive). Bands at ±0.05% and ±0.10% from box
edges (high*1.0005, etc.).
"""
from __future__ import annotations

import pandas as pd

from engine.box_05 import build_box_05, band_levels, BandLevels


def _bar(ts: str, h: float, l: float, o: float = 0.0, c: float = 0.0) -> dict:
    return {
        "ts": pd.Timestamp(ts, tz="America/New_York"),
        "open": o or l, "high": h, "low": l, "close": c or h,
    }


def test_build_box_05_uses_5_minute_bars_inclusive():
    bars = [
        _bar("2024-01-02 09:00", h=101.0, l=100.0),
        _bar("2024-01-02 09:01", h=101.5, l= 99.5),
        _bar("2024-01-02 09:02", h=100.8, l= 99.8),
        _bar("2024-01-02 09:03", h=102.0, l=100.2),
        _bar("2024-01-02 09:04", h=101.7, l= 99.0),
    ]
    box = build_box_05(bars, hour_anchor_ts=pd.Timestamp("2024-01-02 09:00", tz="America/New_York"))
    assert box.high == 102.0
    assert box.low == 99.0
    assert box.locked is True


def test_build_box_05_partial_when_fewer_than_5_bars():
    bars = [
        _bar("2024-01-02 09:00", h=101.0, l=100.0),
        _bar("2024-01-02 09:01", h=101.5, l= 99.5),
        _bar("2024-01-02 09:02", h=100.8, l= 99.8),
    ]
    box = build_box_05(bars, hour_anchor_ts=pd.Timestamp("2024-01-02 09:00", tz="America/New_York"))
    assert box.high == 101.5
    assert box.low == 99.5
    assert box.locked is False  # only 3 of 5 bars in


def test_build_box_05_filters_to_correct_hour_minutes():
    # If extra bars from minutes 5-7 are passed, they're ignored.
    bars = [
        _bar("2024-01-02 09:00", h=101.0, l=100.0),
        _bar("2024-01-02 09:04", h=101.7, l= 99.0),
        _bar("2024-01-02 09:05", h=110.0, l= 90.0),  # outside the 0..4 window
    ]
    box = build_box_05(bars, hour_anchor_ts=pd.Timestamp("2024-01-02 09:00", tz="America/New_York"))
    assert box.high == 101.7  # 110.0 from the :05 bar must NOT contribute
    assert box.low == 99.0


def test_band_levels_05_and_10_percent():
    # box_high=100, box_low=100 (degenerate but easy to verify arithmetic)
    bands = band_levels(box_high=100.0, box_low=100.0)
    assert bands.upper_05 == 100.0 * 1.0005
    assert bands.upper_10 == 100.0 * 1.0010
    assert bands.lower_05 == 100.0 * 0.9995
    assert bands.lower_10 == 100.0 * 0.9990


def test_band_levels_distinct_high_low():
    bands = band_levels(box_high=21000.0, box_low=20990.0)
    assert bands.upper_05 == 21000.0 * 1.0005
    assert bands.upper_10 == 21000.0 * 1.0010
    assert bands.lower_05 == 20990.0 * 0.9995
    assert bands.lower_10 == 20990.0 * 0.9990
```

- [ ] **Step 2: Run the test to verify FAIL**

```bash
python3 -m pytest tests/test_box_05.py -v
```
Expected: FAIL.

- [ ] **Step 3: Implement `engine/box_05.py`**

File: `engine/box_05.py`

```python
"""05-box construction and band level derivation.

The 05-box = price range from the first 5 minute bars of an hour (minutes
:00, :01, :02, :03, :04 inclusive). Bands at ±0.05% and ±0.10% from box
edges. Pine and Python must produce identical numeric outputs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd

from engine import constants as C


@dataclass(frozen=True)
class Box05:
    high: float
    low: float
    locked: bool                # True iff all 5 bars (:00..:04) have arrived


@dataclass(frozen=True)
class BandLevels:
    upper_05: float             # box_high * 1.0005
    upper_10: float             # box_high * 1.0010
    lower_05: float             # box_low  * 0.9995
    lower_10: float             # box_low  * 0.9990


def build_box_05(bars: Iterable[dict], hour_anchor_ts: pd.Timestamp) -> Box05:
    """Build a Box05 from any iterable of bar dicts (must include 'ts','high','low').

    Filters bars to those at minutes 0-4 of the hour matching hour_anchor_ts.
    `locked` is True iff all 5 minutes are represented.
    """
    minutes_seen: set[int] = set()
    box_high = float("-inf")
    box_low = float("inf")
    for bar in bars:
        ts: pd.Timestamp = bar["ts"]
        if ts.normalize() != hour_anchor_ts.normalize() or ts.hour != hour_anchor_ts.hour:
            continue
        if ts.minute not in C.BOX_05_MINUTES:
            continue
        minutes_seen.add(ts.minute)
        if bar["high"] > box_high:
            box_high = bar["high"]
        if bar["low"] < box_low:
            box_low = bar["low"]
    locked = minutes_seen == set(C.BOX_05_MINUTES)
    return Box05(high=box_high, low=box_low, locked=locked)


def band_levels(box_high: float, box_low: float) -> BandLevels:
    """Compute the four band levels from a 05-box's high/low."""
    o05, o10 = C.BAND_OFFSETS  # (0.0005, 0.0010)
    return BandLevels(
        upper_05=box_high * (1.0 + o05),
        upper_10=box_high * (1.0 + o10),
        lower_05=box_low  * (1.0 - o05),
        lower_10=box_low  * (1.0 - o10),
    )
```

- [ ] **Step 4: Run tests to verify PASS**

```bash
python3 -m pytest tests/test_box_05.py -v
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add engine/box_05.py tests/test_box_05.py
git commit -m "feat(quarter-theory): add 05-box construction and band level derivation"
```

---

### Task 2.5: Band rejection detection

**Files:**
- Modify: `engine/box_05.py` (add `detect_band_rejection`)
- Modify: `tests/test_box_05.py`

- [ ] **Step 1: Append failing tests to `tests/test_box_05.py`**

```python
from engine.box_05 import detect_band_rejection, BandRejection


def test_band_rejection_upper_05_wick_above_close_below():
    bands = band_levels(box_high=100.0, box_low=99.0)  # upper_05 = 100.05
    bar = {"open": 100.02, "high": 100.06, "low": 100.00, "close": 100.04}
    r = detect_band_rejection(bar, bands)
    assert r == BandRejection(side="upper", level="05")


def test_band_rejection_upper_10_wick_above_close_below():
    bands = band_levels(box_high=100.0, box_low=99.0)  # upper_10 = 100.10
    bar = {"open": 100.06, "high": 100.12, "low": 100.04, "close": 100.08}
    r = detect_band_rejection(bar, bands)
    # NOTE: this bar wicks above upper_10 AND closes back below upper_10. It also
    # wicks above upper_05 and closes above upper_05 (no rejection of 05). The
    # "10 rejection" is the more meaningful event (heavier band).
    assert r == BandRejection(side="upper", level="10")


def test_band_rejection_lower_05_wick_below_close_above():
    bands = band_levels(box_high=100.0, box_low=99.0)  # lower_05 = 98.9505
    bar = {"open": 98.97, "high": 99.00, "low": 98.94, "close": 98.98}
    r = detect_band_rejection(bar, bands)
    assert r == BandRejection(side="lower", level="05")


def test_no_rejection_when_close_outside_band():
    # Wicks above upper_05 AND closes above upper_05 → no rejection
    bands = band_levels(box_high=100.0, box_low=99.0)  # upper_05 = 100.05
    bar = {"open": 100.02, "high": 100.08, "low": 100.00, "close": 100.07}
    r = detect_band_rejection(bar, bands)
    assert r is None


def test_no_rejection_when_wick_doesnt_reach_band():
    bands = band_levels(box_high=100.0, box_low=99.0)
    bar = {"open": 100.00, "high": 100.04, "low": 99.96, "close": 100.02}
    r = detect_band_rejection(bar, bands)
    assert r is None


def test_band_rejection_prefers_10_over_05_when_both_apply():
    # Bar wicks above upper_10 and closes below upper_05 — both bands rejected,
    # but the 10 band is the more prominent event.
    bands = band_levels(box_high=100.0, box_low=99.0)
    bar = {"open": 100.02, "high": 100.12, "low": 100.00, "close": 100.04}
    r = detect_band_rejection(bar, bands)
    assert r == BandRejection(side="upper", level="10")
```

- [ ] **Step 2: Run the test to verify FAIL**

```bash
python3 -m pytest tests/test_box_05.py -v
```
Expected: FAIL — `cannot import name 'detect_band_rejection'`.

- [ ] **Step 3: Append `detect_band_rejection` to `engine/box_05.py`**

```python
from typing import Optional, Literal


@dataclass(frozen=True)
class BandRejection:
    side: Literal["upper", "lower"]
    level: Literal["05", "10"]


def detect_band_rejection(bar: dict, bands: BandLevels) -> Optional[BandRejection]:
    """Detect whether the given bar rejects a band.

    Upper rejection: bar.high > band AND bar.close < band (wick above, close below).
    Lower rejection: bar.low < band AND bar.close > band (wick below, close above).

    When both 05 and 10 bands of the same side reject, the 10 takes precedence
    (heavier band is the more meaningful event).
    """
    high = bar["high"]
    low = bar["low"]
    close = bar["close"]

    if high > bands.upper_10 and close < bands.upper_10:
        return BandRejection(side="upper", level="10")
    if high > bands.upper_05 and close < bands.upper_05:
        return BandRejection(side="upper", level="05")
    if low < bands.lower_10 and close > bands.lower_10:
        return BandRejection(side="lower", level="10")
    if low < bands.lower_05 and close > bands.lower_05:
        return BandRejection(side="lower", level="05")
    return None
```

- [ ] **Step 4: Run tests to verify PASS**

```bash
python3 -m pytest tests/test_box_05.py -v
```
Expected: 11 passed.

- [ ] **Step 5: Commit**

```bash
git add engine/box_05.py tests/test_box_05.py
git commit -m "feat(quarter-theory): add band rejection detection (10 takes precedence over 05)"
```

---

### Task 2.6: Midline source resolution

**Files:**
- Create: `engine/midline.py`
- Create: `tests/test_midline.py`

- [ ] **Step 1: Write the failing test**

File: `tests/test_midline.py`

```python
"""Tests for midline source resolution.

Rule: if the current candle's range is STRICTLY inside the prior candle's range
(low > prior_low AND high < prior_high), use prior_mid. Else use current_mid.
Equality on either side counts as broken-out (uses current).
"""
from __future__ import annotations

from engine.midline import resolve_midline_source


def test_strictly_inside_uses_prior_mid():
    # current 100..101 inside prior 99..102 → use prior_mid
    mid, source = resolve_midline_source(
        current_high=101.0, current_low=100.0,
        prior_high=102.0,  prior_low=99.0,
    )
    assert source == "prior"
    assert mid == (102.0 + 99.0) / 2.0


def test_high_equality_uses_current_mid():
    mid, source = resolve_midline_source(
        current_high=102.0, current_low=100.0,
        prior_high=102.0,  prior_low=99.0,
    )
    # current_high == prior_high → broken-out
    assert source == "current"
    assert mid == (102.0 + 100.0) / 2.0


def test_low_equality_uses_current_mid():
    mid, source = resolve_midline_source(
        current_high=101.5, current_low=99.0,
        prior_high=102.0,  prior_low=99.0,
    )
    assert source == "current"


def test_breakout_above_uses_current_mid():
    mid, source = resolve_midline_source(
        current_high=103.0, current_low=100.0,
        prior_high=102.0,  prior_low=99.0,
    )
    assert source == "current"


def test_breakout_below_uses_current_mid():
    mid, source = resolve_midline_source(
        current_high=101.0, current_low=98.5,
        prior_high=102.0,  prior_low=99.0,
    )
    assert source == "current"


def test_no_prior_uses_current_mid():
    mid, source = resolve_midline_source(
        current_high=101.0, current_low=100.0,
        prior_high=None, prior_low=None,
    )
    assert source == "current"
    assert mid == 100.5
```

- [ ] **Step 2: Run the test to verify FAIL**

```bash
python3 -m pytest tests/test_midline.py -v
```
Expected: FAIL.

- [ ] **Step 3: Implement `engine/midline.py`**

File: `engine/midline.py`

```python
"""Midline source resolution.

The active midline of the current hour (or current 3h block) is:
- the PRIOR candle's mid, if the current candle is strictly inside prior range
  (current.low > prior.low AND current.high < prior.high)
- otherwise the CURRENT candle's mid.

Equality on either side counts as broken-out (uses current).
"""
from __future__ import annotations

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
```

- [ ] **Step 4: Run tests to verify PASS**

```bash
python3 -m pytest tests/test_midline.py -v
```
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add engine/midline.py tests/test_midline.py
git commit -m "feat(quarter-theory): add midline source resolution (strict inside-bar test)"
```

---

### Task 2.7: Midline reaction detection

**Files:**
- Modify: `engine/midline.py` (add `detect_midline_reaction`)
- Modify: `tests/test_midline.py`

- [ ] **Step 1: Append failing tests**

```python
from engine.midline import detect_midline_reaction, MidlineReaction


def test_support_reaction_wick_below_close_above():
    # Mid at 100. Bar dips below mid then closes above → support
    r = detect_midline_reaction(mid=100.0, bar_open=100.5, bar_high=100.8, bar_low=99.7, bar_close=100.3)
    assert r == MidlineReaction.SUPPORT


def test_reject_reaction_wick_above_close_below():
    r = detect_midline_reaction(mid=100.0, bar_open=99.7, bar_high=100.4, bar_low=99.5, bar_close=99.9)
    assert r == MidlineReaction.REJECT


def test_no_reaction_when_bar_doesnt_cross_mid():
    r = detect_midline_reaction(mid=100.0, bar_open=100.2, bar_high=100.5, bar_low=100.1, bar_close=100.3)
    assert r is None


def test_no_reaction_when_close_on_wrong_side():
    # Wicks below mid AND closes below → no support reaction (bar accepted the break)
    r = detect_midline_reaction(mid=100.0, bar_open=100.1, bar_high=100.2, bar_low=99.5, bar_close=99.7)
    assert r is None
```

- [ ] **Step 2: Run to verify FAIL**

```bash
python3 -m pytest tests/test_midline.py -v
```
Expected: FAIL — `cannot import name 'detect_midline_reaction'`.

- [ ] **Step 3: Append `detect_midline_reaction` to `engine/midline.py`**

```python
from enum import Enum


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
```

- [ ] **Step 4: Run tests to verify PASS**

```bash
python3 -m pytest tests/test_midline.py -v
```
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add engine/midline.py tests/test_midline.py
git commit -m "feat(quarter-theory): add midline reaction detection (support/reject)"
```

---

### Task 2.8: Quarter extreme classification (in-stat vs out-of-stat)

**Files:**
- Create: `engine/quarter_extreme.py`
- Create: `tests/test_quarter_extreme.py`

- [ ] **Step 1: Write the failing test**

File: `tests/test_quarter_extreme.py`

```python
"""Tests for quarter extreme classification.

For each completed hour, the hour has exactly one global high and one global low.
Each is labelled by the quarter that printed it:
- Q1 or Q4 → "in-stat"
- Q2 or Q3 → "out-of-stat"
"""
from __future__ import annotations

import pandas as pd

from engine.aggregations import QuarterAgg, HourAgg
from engine.quarter_extreme import classify_quarter_extremes, QuarterExtreme


def _ts(s: str) -> pd.Timestamp:
    return pd.Timestamp(s, tz="America/New_York")


def _q(idx: int, h: float, l: float) -> QuarterAgg:
    q = QuarterAgg(quarter_idx=idx, anchor_ts=_ts(f"2024-01-02 09:{(idx-1)*15:02d}"))
    q.high = h; q.low = l
    q.high_anchor_ts = q.anchor_ts
    q.low_anchor_ts = q.anchor_ts
    return q


def _hour(qs: list[QuarterAgg]) -> HourAgg:
    h = HourAgg(anchor_ts=_ts("2024-01-02 09:00"))
    for q in qs:
        setattr(h, f"q{q.quarter_idx}", q)
    return h


def test_q1_high_is_in_stat():
    # Q1 makes the highest high of the hour
    h = _hour([_q(1, 105, 99), _q(2, 103, 100), _q(3, 102, 99.5), _q(4, 101, 100)])
    extremes = classify_quarter_extremes(h)
    assert QuarterExtreme(quarter_idx=1, side="high", in_stat=True) in extremes


def test_q2_low_is_out_of_stat():
    h = _hour([_q(1, 102, 99.5), _q(2, 103, 98), _q(3, 104, 99), _q(4, 105, 99.7)])
    extremes = classify_quarter_extremes(h)
    assert QuarterExtreme(quarter_idx=2, side="low", in_stat=False) in extremes


def test_q4_in_stat_high_q3_out_of_stat_low():
    h = _hour([_q(1, 100, 99), _q(2, 101, 99.5), _q(3, 102, 98.0), _q(4, 105, 99.7)])
    extremes = classify_quarter_extremes(h)
    assert QuarterExtreme(quarter_idx=4, side="high", in_stat=True) in extremes
    assert QuarterExtreme(quarter_idx=3, side="low", in_stat=False) in extremes


def test_returns_empty_when_hour_incomplete():
    h = HourAgg(anchor_ts=_ts("2024-01-02 09:00"))
    h.q1 = _q(1, 100, 99)
    extremes = classify_quarter_extremes(h)
    assert extremes == []


def test_ties_broken_by_first_occurring_quarter():
    # Q2 and Q4 both reach 105.0 high. The earliest quarter is the anchor.
    h = _hour([_q(1, 100, 99), _q(2, 105, 99.5), _q(3, 104, 99.7), _q(4, 105, 99.8)])
    extremes = classify_quarter_extremes(h)
    high_extreme = [e for e in extremes if e.side == "high"][0]
    assert high_extreme.quarter_idx == 2
    assert high_extreme.in_stat is False  # Q2 is out-of-stat
```

- [ ] **Step 2: Run to verify FAIL**

```bash
python3 -m pytest tests/test_quarter_extreme.py -v
```
Expected: FAIL.

- [ ] **Step 3: Implement `engine/quarter_extreme.py`**

File: `engine/quarter_extreme.py`

```python
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
```

- [ ] **Step 4: Run tests to verify PASS**

```bash
python3 -m pytest tests/test_quarter_extreme.py -v
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add engine/quarter_extreme.py tests/test_quarter_extreme.py
git commit -m "feat(quarter-theory): add quarter-extreme classifier (in-stat / out-of-stat)"
```

---

### Task 2.9: State-vector schema and key builder

**Files:**
- Create: `engine/state_vector.py`
- Create: `tests/test_state_vector.py`
- Create: `docs/state_vector.md`

- [ ] **Step 1: Write the failing test**

File: `tests/test_state_vector.py`

```python
"""Tests for state-vector key construction.

The state-key string is the contract between Python and Pine. Byte-identical
output is mandatory; pinned by parity tests in Phase 9.

Schema fields (triad key):
  v1|sym|tf|block|c1cls|c2q|c2vh|c2vl|c2sw_c1h|c2sw_c1l|c2_inside|midhr|mid3h|box_react

Schema fields (hour key):
  v1|sym|tf|block|hour_idx|q|q1cls|q2cls|q3cls|q4cls|sweep_set|midhr|box_react
"""
from __future__ import annotations

from engine.state_vector import (
    TriadStateInputs, HourStateInputs,
    build_triad_key, build_hour_key,
    canonical_hash,
)


def test_triad_key_canonical_form():
    inputs = TriadStateInputs(
        sym="NQ", block="09-12", c1cls="line-up", c2q="Q3",
        c2vh="above", c2vl="above",
        c2sw_c1h=True, c2sw_c1l=False, c2_inside=False,
        midhr="support", mid3h="untouched", box_react="10up_rejected",
    )
    key = build_triad_key(inputs)
    expected = (
        "v1|sym=NQ|tf=triad|block=09-12|c1cls=line-up|c2q=Q3|"
        "c2vh=above|c2vl=above|c2sw_c1h=Y|c2sw_c1l=N|c2_inside=N|"
        "midhr=support|mid3h=untouched|box_react=10up_rejected"
    )
    assert key == expected


def test_hour_key_canonical_form():
    inputs = HourStateInputs(
        sym="NQ", block="09-12", hour_idx=2, q="Q3",
        q1cls="in-stat-high", q2cls="swept-q1-low",
        q3cls="inside", q4cls="inside",
        sweep_set=("Q2_swept_Q1_low",),
        midhr="support", box_react="05dn_rejected",
    )
    key = build_hour_key(inputs)
    expected = (
        "v1|sym=NQ|tf=hour|block=09-12|hour_idx=2|q=Q3|"
        "q1cls=in-stat-high|q2cls=swept-q1-low|q3cls=inside|q4cls=inside|"
        "sweep_set=Q2_swept_Q1_low|midhr=support|box_react=05dn_rejected"
    )
    assert key == expected


def test_hour_key_empty_sweep_set_renders_as_none():
    inputs = HourStateInputs(
        sym="NQ", block="09-12", hour_idx=1, q="Q1",
        q1cls="inside", q2cls="inside", q3cls="inside", q4cls="inside",
        sweep_set=(),
        midhr="untouched", box_react="none",
    )
    key = build_hour_key(inputs)
    assert "sweep_set=none" in key


def test_hour_key_multiple_sweeps_sorted_and_comma_joined():
    inputs = HourStateInputs(
        sym="NQ", block="09-12", hour_idx=2, q="Q4",
        q1cls="in-stat-high", q2cls="inside", q3cls="inside", q4cls="inside",
        sweep_set=("Q3_swept_Q1_low", "Q2_swept_Q1_high"),  # unsorted input
        midhr="support", box_react="none",
    )
    key = build_hour_key(inputs)
    # Sorted alphabetically, comma-joined
    assert "sweep_set=Q2_swept_Q1_high,Q3_swept_Q1_low" in key


def test_canonical_hash_is_deterministic():
    h1 = canonical_hash("v1|sym=NQ|tf=triad|block=09-12")
    h2 = canonical_hash("v1|sym=NQ|tf=triad|block=09-12")
    assert h1 == h2


def test_canonical_hash_different_for_different_strings():
    h1 = canonical_hash("v1|sym=NQ|tf=triad|block=09-12|c1cls=line-up")
    h2 = canonical_hash("v1|sym=NQ|tf=triad|block=09-12|c1cls=line-down")
    assert h1 != h2


def test_canonical_hash_is_short_base36():
    h = canonical_hash("v1|sym=NQ|tf=triad|block=09-12|c1cls=line-up|c2q=Q3")
    # Base36 of 64-bit int → 13 chars max
    assert len(h) <= 13
    assert all(c in "0123456789abcdefghijklmnopqrstuvwxyz" for c in h)


def test_triad_key_es_symbol():
    inputs = TriadStateInputs(
        sym="ES", block="06-09", c1cls="doji", c2q="closed",
        c2vh="inside", c2vl="inside",
        c2sw_c1h=False, c2sw_c1l=False, c2_inside=True,
        midhr="untouched", mid3h="reject", box_react="none",
    )
    key = build_triad_key(inputs)
    assert key.startswith("v1|sym=ES|tf=triad|")


def test_invalid_block_rejected():
    import pytest
    with pytest.raises(ValueError, match="block"):
        TriadStateInputs(
            sym="NQ", block="15-18",  # excluded gap — not a real block
            c1cls="line-up", c2q="Q3",
            c2vh="above", c2vl="above",
            c2sw_c1h=True, c2sw_c1l=False, c2_inside=False,
            midhr="support", mid3h="untouched", box_react="none",
        )


def test_invalid_c2q_rejected():
    import pytest
    with pytest.raises(ValueError, match="c2q"):
        TriadStateInputs(
            sym="NQ", block="09-12", c1cls="line-up", c2q="Q5",  # invalid
            c2vh="above", c2vl="above",
            c2sw_c1h=True, c2sw_c1l=False, c2_inside=False,
            midhr="support", mid3h="untouched", box_react="none",
        )
```

- [ ] **Step 2: Run to verify FAIL**

```bash
python3 -m pytest tests/test_state_vector.py -v
```
Expected: FAIL.

- [ ] **Step 3: Implement `engine/state_vector.py`**

File: `engine/state_vector.py`

```python
"""State-vector schema v1.

The state-key string format is the contract between this Python engine and
the Pine indicator. Both sides MUST produce byte-identical strings for the
same logical state, and MUST compute the same canonical_hash() of those
strings. Parity is tested in Phase 9.

Format:
  Triad key:
    v1|sym=<NQ|ES>|tf=triad|block=<HH-HH>|c1cls=<line-up|line-down|doji>|
    c2q=<Q1|Q2|Q3|Q4|closed>|c2vh=<above|inside|below|na>|c2vl=<...>|
    c2sw_c1h=<Y|N>|c2sw_c1l=<Y|N>|c2_inside=<Y|N>|
    midhr=<support|reject|untouched>|mid3h=<...>|
    box_react=<none|5up_rejected|5dn_rejected|10up_rejected|10dn_rejected|multi>

  Hour key:
    v1|sym=<NQ|ES>|tf=hour|block=<HH-HH>|hour_idx=<1|2|3>|q=<Q1..Q4|closed>|
    q1cls=<...>|q2cls=<...>|q3cls=<...>|q4cls=<...>|
    sweep_set=<comma-joined sorted | "none">|midhr=<...>|box_react=<...>
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal, Tuple

from engine import constants as C


SCHEMA_VERSION = C.SCHEMA_VERSION


# ── Allowed value sets ────────────────────────────────────────────────────────

_VALID_SYMS = ("NQ", "ES")
_VALID_C1CLS = ("line-up", "line-down", "doji")
_VALID_C2Q = ("Q1", "Q2", "Q3", "Q4", "closed")
_VALID_VS = ("above", "inside", "below", "na")
_VALID_MIDLINE = ("support", "reject", "untouched")
_VALID_BOX_REACT = ("none", "5up_rejected", "5dn_rejected", "10up_rejected", "10dn_rejected", "multi")
_VALID_QCLS = ("in-stat-high", "in-stat-low", "out-stat-high", "out-stat-low",
               "swept-q1-high", "swept-q1-low", "swept-q2-high", "swept-q2-low",
               "swept-q3-high", "swept-q3-low", "inside")
_VALID_HOUR_IDX = (1, 2, 3)


def _yn(b: bool) -> str:
    return "Y" if b else "N"


def _validate(field: str, val: object, allowed: tuple) -> None:
    if val not in allowed:
        raise ValueError(f"invalid {field}: {val!r} not in {allowed}")


# ── Triad inputs / key ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class TriadStateInputs:
    sym: Literal["NQ", "ES"]
    block: str
    c1cls: Literal["line-up", "line-down", "doji"]
    c2q: Literal["Q1", "Q2", "Q3", "Q4", "closed"]
    c2vh: Literal["above", "inside", "below", "na"]
    c2vl: Literal["above", "inside", "below", "na"]
    c2sw_c1h: bool
    c2sw_c1l: bool
    c2_inside: bool
    midhr: Literal["support", "reject", "untouched"]
    mid3h: Literal["support", "reject", "untouched"]
    box_react: str

    def __post_init__(self) -> None:
        _validate("sym", self.sym, _VALID_SYMS)
        _validate("block", self.block, C.BLOCK_IDS)
        _validate("c1cls", self.c1cls, _VALID_C1CLS)
        _validate("c2q", self.c2q, _VALID_C2Q)
        _validate("c2vh", self.c2vh, _VALID_VS)
        _validate("c2vl", self.c2vl, _VALID_VS)
        _validate("midhr", self.midhr, _VALID_MIDLINE)
        _validate("mid3h", self.mid3h, _VALID_MIDLINE)
        _validate("box_react", self.box_react, _VALID_BOX_REACT)


def build_triad_key(s: TriadStateInputs) -> str:
    return (
        f"{SCHEMA_VERSION}|sym={s.sym}|tf=triad|block={s.block}|c1cls={s.c1cls}|c2q={s.c2q}|"
        f"c2vh={s.c2vh}|c2vl={s.c2vl}|c2sw_c1h={_yn(s.c2sw_c1h)}|c2sw_c1l={_yn(s.c2sw_c1l)}|"
        f"c2_inside={_yn(s.c2_inside)}|midhr={s.midhr}|mid3h={s.mid3h}|box_react={s.box_react}"
    )


# ── Hour inputs / key ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class HourStateInputs:
    sym: Literal["NQ", "ES"]
    block: str
    hour_idx: Literal[1, 2, 3]
    q: Literal["Q1", "Q2", "Q3", "Q4", "closed"]
    q1cls: str
    q2cls: str
    q3cls: str
    q4cls: str
    sweep_set: Tuple[str, ...]
    midhr: Literal["support", "reject", "untouched"]
    box_react: str

    def __post_init__(self) -> None:
        _validate("sym", self.sym, _VALID_SYMS)
        _validate("block", self.block, C.BLOCK_IDS)
        _validate("hour_idx", self.hour_idx, _VALID_HOUR_IDX)
        _validate("q", self.q, _VALID_C2Q)
        for fn in ("q1cls", "q2cls", "q3cls", "q4cls"):
            _validate(fn, getattr(self, fn), _VALID_QCLS)
        _validate("midhr", self.midhr, _VALID_MIDLINE)
        _validate("box_react", self.box_react, _VALID_BOX_REACT)


def build_hour_key(s: HourStateInputs) -> str:
    sweep_str = ",".join(sorted(s.sweep_set)) if s.sweep_set else "none"
    return (
        f"{SCHEMA_VERSION}|sym={s.sym}|tf=hour|block={s.block}|hour_idx={s.hour_idx}|q={s.q}|"
        f"q1cls={s.q1cls}|q2cls={s.q2cls}|q3cls={s.q3cls}|q4cls={s.q4cls}|"
        f"sweep_set={sweep_str}|midhr={s.midhr}|box_react={s.box_react}"
    )


# ── Compact hash (Pine map keys) ─────────────────────────────────────────────

def canonical_hash(key: str) -> str:
    """Return a base36-encoded 64-bit hash of the canonical key string.

    Pine must compute the same hash. We use the low 64 bits of SHA-256 for
    portability — Pine 6 has built-in str.tonumber-style helpers that can
    replicate this with a simple polynomial-rolling hash. Phase 6 will
    implement the Pine-side equivalent and parity-test the values.

    Uses SHA-256 in Python; Pine emulates with manual byte-level arithmetic.
    """
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    n = int.from_bytes(digest[:8], "big", signed=False)
    return _to_base36(n)


def _to_base36(n: int) -> str:
    if n == 0:
        return "0"
    chars = "0123456789abcdefghijklmnopqrstuvwxyz"
    out = []
    while n > 0:
        out.append(chars[n % 36])
        n //= 36
    return "".join(reversed(out))
```

- [ ] **Step 4: Run tests to verify PASS**

```bash
python3 -m pytest tests/test_state_vector.py -v
```
Expected: 9 passed.

- [ ] **Step 5: Write `docs/state_vector.md` (versioned schema reference)**

File: `docs/state_vector.md`

```markdown
# State Vector — Schema v1

This document is the single source of truth for the state-key string format.
The Python engine (`engine/state_vector.py`) and the Pine indicator
(`pine/quarter_theory.pine`) MUST produce byte-identical strings for the
same logical state, and the same `canonical_hash()` of those strings.

Schema bumps require:
1. Update `SCHEMA_VERSION` in `engine/constants.py` and Pine.
2. Re-run `engine/build.py`.
3. Re-paste `_generated_tables.pine`.
4. Re-run parity test (`tests/test_state_vector.py::test_pine_parity` after Phase 9).

## Triad key

\`\`\`
v1|sym=<sym>|tf=triad|block=<block>|c1cls=<c1cls>|c2q=<c2q>|
c2vh=<c2vh>|c2vl=<c2vl>|c2sw_c1h=<Y|N>|c2sw_c1l=<Y|N>|c2_inside=<Y|N>|
midhr=<midhr>|mid3h=<mid3h>|box_react=<box_react>
\`\`\`

| Field | Allowed values |
|---|---|
| sym | NQ \| ES |
| block | 00-03 \| 03-06 \| 06-09 \| 09-12 \| 12-15 \| 18-21 \| 21-00 |
| c1cls | line-up \| line-down \| doji |
| c2q | Q1 \| Q2 \| Q3 \| Q4 \| closed |
| c2vh, c2vl | above \| inside \| below \| na |
| c2sw_c1h, c2sw_c1l, c2_inside | Y \| N |
| midhr, mid3h | support \| reject \| untouched |
| box_react | none \| 5up_rejected \| 5dn_rejected \| 10up_rejected \| 10dn_rejected \| multi |

## Hour key

\`\`\`
v1|sym=<sym>|tf=hour|block=<block>|hour_idx=<hour_idx>|q=<q>|
q1cls=<...>|q2cls=<...>|q3cls=<...>|q4cls=<...>|
sweep_set=<sorted comma-joined | "none">|midhr=<...>|box_react=<...>
\`\`\`

| Field | Allowed values |
|---|---|
| hour_idx | 1 \| 2 \| 3 |
| q | Q1..Q4 \| closed |
| qNcls | in-stat-high \| in-stat-low \| out-stat-high \| out-stat-low \| swept-qX-high \| swept-qX-low \| inside |
| sweep_set | Comma-joined sorted strings like "Q2_swept_Q1_high,Q3_swept_Q2_low", or "none" |

## Canonical hash

\`canonical_hash(key)\` = base36 of the low 64 bits of SHA-256(key as utf-8).

The Pine side replicates this with byte-level arithmetic. Both sides agree
to ≤13 chars in `[0-9a-z]`.
```

- [ ] **Step 6: Commit**

```bash
git add engine/state_vector.py tests/test_state_vector.py docs/state_vector.md
git commit -m "feat(quarter-theory): add state-vector schema v1 with canonical_hash"
```

---

### Phase 2 smoke test

- [ ] **Run all tests:**

```bash
python3 -m pytest tests/ -q
```
Expected: ~70 tests passed (Phase 1's 21 + this phase's ~49).

- [ ] **Sanity check state-key generation:**

```bash
python3 -c "
import sys; sys.path.insert(0, '.')
from engine.state_vector import TriadStateInputs, build_triad_key, canonical_hash
inputs = TriadStateInputs(
    sym='NQ', block='09-12', c1cls='line-up', c2q='Q3',
    c2vh='above', c2vl='above',
    c2sw_c1h=True, c2sw_c1l=False, c2_inside=False,
    midhr='support', mid3h='untouched', box_react='10up_rejected',
)
key = build_triad_key(inputs)
print('Key:', key)
print('Hash:', canonical_hash(key))
"
```
Expected output: a fully-formatted key string and a base36 hash.

**End of Phase 2.** Move to [Phase 3 — Empirical aggregator](phase-3-empirical.md).
