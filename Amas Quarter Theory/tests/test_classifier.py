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
    # No monotonic stack, no clean swing: highs 100,101,102 (line-up) but lows 98,99,97 (not line-up/down)
    t = _triad_with(c1_h=100, c1_l=98, c2_h=101, c2_l=99, c3_h=102, c3_l=97)
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
