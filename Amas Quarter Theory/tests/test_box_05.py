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
