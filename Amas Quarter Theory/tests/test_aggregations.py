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
