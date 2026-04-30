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
