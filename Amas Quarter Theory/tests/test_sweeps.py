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
