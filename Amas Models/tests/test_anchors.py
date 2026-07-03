"""Tests for engine.anchors — H1 anchor builder + window slicer.

Per the design spec, Category A (TZ correctness) and Category C (lookahead):
- anchor_ts must be tz-aware in America/New_York and floored in NY tz (DST safe).
- slice_h1_window uses a half-open interval [anchor_ts, anchor_ts + 1h).
- extreme_minute_high/low are causal — the minute-of-hour (0-59) at which the
  H1 high/low was struck.
- Empty windows are silently skipped.
"""
from __future__ import annotations

import pandas as pd
import pytest

from engine import anchors


def _make_bars(ts_list, ohlcv_list):
    """Build a tz-aware [ns, NY] bars DataFrame from a list of timestamps and OHLCV tuples."""
    df = pd.DataFrame({
        "ts": ts_list,
        "open": [r[0] for r in ohlcv_list],
        "high": [r[1] for r in ohlcv_list],
        "low": [r[2] for r in ohlcv_list],
        "close": [r[3] for r in ohlcv_list],
        "volume": [r[4] for r in ohlcv_list],
    })
    df["ts"] = df["ts"].astype("datetime64[ns, America/New_York]")
    df["volume"] = df["volume"].astype("int64")
    return df


def test_build_h1_anchors_basic_shape(synthetic_bars_1m):
    """5 days RTH only → expect 7 hours per day (09, 10, 11, 12, 13, 14, 15) = 35 anchors.

    The 09 hour is partial (09:30-10:00, 30 bars) and the 15 hour is full (60 bars).
    The synthetic fixture stops at 16:00 exclusive, so 15:00-16:00 is the last full hour.
    """
    bars = synthetic_bars_1m()
    out = anchors.build_h1_anchors(bars)

    expected_cols = [
        "anchor_ts", "close_ts", "open", "high", "low", "close",
        "volume", "n_bars", "extreme_minute_high", "extreme_minute_low",
    ]
    assert list(out.columns) == expected_cols, f"columns: {list(out.columns)}"

    # 5 days * 7 hours per day (09, 10, 11, 12, 13, 14, 15) = 35
    assert len(out) == 35, f"expected 35 anchors, got {len(out)}"

    assert out["anchor_ts"].dt.tz is not None, "anchor_ts must be tz-aware"
    assert str(out["anchor_ts"].dt.tz) == "America/New_York"
    assert out["anchor_ts"].dtype.unit == "ns"
    assert str(out["close_ts"].dt.tz) == "America/New_York"
    assert out["close_ts"].dtype.unit == "ns"

    assert out["volume"].dtype == "int64"
    assert out["n_bars"].dtype == "int64"
    # extreme minutes should be plain ints in 0..59
    assert out["extreme_minute_high"].between(0, 59).all()
    assert out["extreme_minute_low"].between(0, 59).all()


def test_anchor_ts_is_floored_in_ny_tz(synthetic_bars_1m):
    bars = synthetic_bars_1m()
    out = anchors.build_h1_anchors(bars)
    # Every anchor_ts must have minute=0, second=0
    assert (out["anchor_ts"].dt.minute == 0).all()
    assert (out["anchor_ts"].dt.second == 0).all()
    # close_ts = anchor_ts + 1h
    assert ((out["close_ts"] - out["anchor_ts"]) == pd.Timedelta("1h")).all()


def test_anchor_ohlc_correctness():
    """Hand-verified: 4 bars in a single 09:00 hour. Verify OHLC, volume, n_bars, extremes."""
    base = pd.Timestamp("2024-01-02 09:30", tz="America/New_York")
    ts_list = [base, base + pd.Timedelta(minutes=1), base + pd.Timedelta(minutes=2), base + pd.Timedelta(minutes=3)]
    # (open, high, low, close, volume)
    rows = [
        (100.0, 101.0,  99.5, 100.5, 10),
        (100.5, 102.0,  99.0, 101.0, 20),  # high here = 102.0 at :31
        (101.0, 101.5,  98.0, 100.0, 30),  # low here = 98.0 at :32
        (100.0, 100.5,  99.0,  99.5, 40),
    ]
    bars = _make_bars(ts_list, rows)
    out = anchors.build_h1_anchors(bars)
    assert len(out) == 1
    row = out.iloc[0]
    assert row["anchor_ts"] == pd.Timestamp("2024-01-02 09:00", tz="America/New_York")
    assert row["close_ts"] == pd.Timestamp("2024-01-02 10:00", tz="America/New_York")
    assert row["open"] == 100.0  # first bar's open
    assert row["high"] == 102.0  # max of all highs
    assert row["low"] == 98.0    # min of all lows
    assert row["close"] == 99.5  # last bar's close
    assert row["volume"] == 100
    assert row["n_bars"] == 4
    assert row["extreme_minute_high"] == 31
    assert row["extreme_minute_low"] == 32


def test_extreme_minute_high_low():
    """Craft a fixture where the H1 high is at minute :42 and low is at minute :17."""
    base = pd.Timestamp("2024-01-02 10:00", tz="America/New_York")
    ts_list = [base + pd.Timedelta(minutes=i) for i in range(60)]
    rows = []
    for i in range(60):
        # baseline price 100; bump high to 200 at minute :42; drop low to 50 at minute :17
        h = 100.5
        l = 99.5
        if i == 42:
            h = 200.0
        if i == 17:
            l = 50.0
        rows.append((100.0, h, l, 100.0, 1))
    bars = _make_bars(ts_list, rows)
    out = anchors.build_h1_anchors(bars)
    assert len(out) == 1
    assert out.iloc[0]["extreme_minute_high"] == 42
    assert out.iloc[0]["extreme_minute_low"] == 17


def test_extreme_minute_uses_first_occurrence_on_ties():
    """If two bars share the same high, idxmax-style selection picks the FIRST."""
    base = pd.Timestamp("2024-01-02 10:00", tz="America/New_York")
    ts_list = [base + pd.Timedelta(minutes=i) for i in range(5)]
    rows = [
        (100.0, 105.0, 99.5, 100.0, 1),  # high tie (first occurrence) at :00
        (100.0, 105.0, 99.5, 100.0, 1),  # high tie (later) at :01 — should NOT win
        (100.0, 100.5, 90.0, 100.0, 1),  # low tie (first occurrence) at :02
        (100.0, 100.5, 90.0, 100.0, 1),  # low tie (later) at :03 — should NOT win
        (100.0, 100.5, 99.5, 100.0, 1),
    ]
    bars = _make_bars(ts_list, rows)
    out = anchors.build_h1_anchors(bars)
    assert out.iloc[0]["extreme_minute_high"] == 0
    assert out.iloc[0]["extreme_minute_low"] == 2


def test_slice_h1_window_returns_correct_bars(synthetic_bars_1m):
    bars = synthetic_bars_1m()
    anchor_ts = pd.Timestamp("2024-01-08 10:00", tz="America/New_York")
    sliced = anchors.slice_h1_window(bars, anchor_ts)
    # Full hour 10:00-11:00 → 60 bars
    assert len(sliced) == 60
    assert sliced["ts"].min() == anchor_ts
    assert sliced["ts"].max() == anchor_ts + pd.Timedelta(minutes=59)
    assert (sliced["ts"] >= anchor_ts).all()
    assert (sliced["ts"] < anchor_ts + pd.Timedelta("1h")).all()


def test_slice_h1_window_excludes_close_ts():
    """A bar at exactly anchor_ts + 1h belongs to the NEXT H1 (half-open)."""
    base = pd.Timestamp("2024-01-02 10:00", tz="America/New_York")
    ts_list = [base, base + pd.Timedelta(minutes=30), base + pd.Timedelta(minutes=60)]
    rows = [(100.0, 100.5, 99.5, 100.0, 1)] * 3
    bars = _make_bars(ts_list, rows)
    sliced = anchors.slice_h1_window(bars, base)
    assert len(sliced) == 2
    assert (sliced["ts"] < base + pd.Timedelta("1h")).all()


def test_dst_spring_forward():
    """2024-03-10: clocks jump from 02:00 EST to 03:00 EDT (the 02:00 hour does not exist).

    Feed bars from 01:00 to 04:59 EDT and assert anchor count is correct (no spurious
    02:00 anchor). On the spring-forward day the 01:00 hour is followed directly by
    the 03:00 hour, so we expect 3 anchors: 01:00 EST, 03:00 EDT, 04:00 EDT.
    """
    rows_ts = []
    rows_data = []
    # 60 bars at 01:00-01:59 EST (offset -05:00)
    for i in range(60):
        rows_ts.append(pd.Timestamp(f"2024-03-10 01:{i:02d}:00", tz="America/New_York"))
        rows_data.append((100.0, 100.5, 99.5, 100.0, 1))
    # 60 bars at 03:00-03:59 EDT (offset -04:00)
    for i in range(60):
        rows_ts.append(pd.Timestamp(f"2024-03-10 03:{i:02d}:00", tz="America/New_York"))
        rows_data.append((100.0, 100.5, 99.5, 100.0, 1))
    # 60 bars at 04:00-04:59 EDT
    for i in range(60):
        rows_ts.append(pd.Timestamp(f"2024-03-10 04:{i:02d}:00", tz="America/New_York"))
        rows_data.append((100.0, 100.5, 99.5, 100.0, 1))
    bars = _make_bars(rows_ts, rows_data)
    out = anchors.build_h1_anchors(bars)
    # Three distinct H1 anchors: 01, 03, 04. No 02 anchor (it does not exist).
    assert len(out) == 3, f"expected 3 anchors across DST jump, got {len(out)}"
    minutes_zero = (out["anchor_ts"].dt.minute == 0).all()
    assert minutes_zero
    # The hour-of-day values should be 1, 3, 4 (no 2)
    hours = sorted(out["anchor_ts"].dt.hour.tolist())
    assert hours == [1, 3, 4], f"expected [1, 3, 4], got {hours}"
    # n_bars should be 60 for each
    assert (out["n_bars"] == 60).all()


def test_dst_fall_back():
    """2023-11-05: clocks fall back from 02:00 EDT to 01:00 EST (01:00 hour repeats).

    The wall-clock '01:00' hour occurs twice — first as 01:00 EDT (-04:00) and again
    as 01:00 EST (-05:00). The underlying UTC instants are unique. We must produce
    TWO separate anchors at 01:00 (one per offset), not collapse them into one.
    """
    rows_ts = []
    rows_data = []
    # 60 bars at 00:00-00:59 EDT
    for i in range(60):
        rows_ts.append(pd.Timestamp(f"2023-11-05 00:{i:02d}:00", tz="America/New_York"))
        rows_data.append((100.0, 100.5, 99.5, 100.0, 1))
    # 60 bars at 01:00-01:59 EDT (first occurrence, before fall-back)
    for i in range(60):
        rows_ts.append(pd.Timestamp(f"2023-11-05 01:{i:02d}:00-04:00").tz_convert("America/New_York"))
        rows_data.append((100.0, 100.5, 99.5, 100.0, 1))
    # 60 bars at 01:00-01:59 EST (second occurrence, after fall-back)
    for i in range(60):
        rows_ts.append(pd.Timestamp(f"2023-11-05 01:{i:02d}:00-05:00").tz_convert("America/New_York"))
        rows_data.append((100.0, 100.5, 99.5, 100.0, 1))
    # 60 bars at 02:00-02:59 EST
    for i in range(60):
        rows_ts.append(pd.Timestamp(f"2023-11-05 02:{i:02d}:00-05:00").tz_convert("America/New_York"))
        rows_data.append((100.0, 100.5, 99.5, 100.0, 1))
    bars = _make_bars(rows_ts, rows_data)
    out = anchors.build_h1_anchors(bars)
    # 4 unique H1 windows (UTC-instant level): 00 EDT, 01 EDT, 01 EST, 02 EST.
    assert len(out) == 4, f"expected 4 anchors across fall-back, got {len(out)}"
    # Two anchors will both have wall-clock 01:00 but different UTC offsets — must
    # remain distinct (their tz-aware timestamps compare unequal at the UTC level).
    assert out["anchor_ts"].is_unique, "fall-back anchors must remain distinct (tz-aware)"
    assert (out["n_bars"] == 60).all()


def test_no_lookahead_in_anchors():
    """For each anchor, the bars used must satisfy ts < anchor_ts + 1h.

    Structurally enforced by slice_h1_window's half-open interval; this test asserts
    that running the anchor builder on a truncated DataFrame (containing only bars
    in [anchor_ts, anchor_ts + 1h)) produces the same anchor row as running on the
    full DataFrame.
    """
    base = pd.Timestamp("2024-01-02 10:00", tz="America/New_York")
    ts_list = [base + pd.Timedelta(minutes=i) for i in range(60)]
    # Add some bars in the NEXT hour with extreme prices that should NOT leak in
    next_hour = pd.Timestamp("2024-01-02 11:00", tz="America/New_York")
    ts_list.extend([next_hour + pd.Timedelta(minutes=i) for i in range(60)])
    rows = [(100.0, 100.5, 99.5, 100.0, 1)] * 60
    rows.extend([(100.0, 999.0, 1.0, 100.0, 1)] * 60)  # extreme prices in next hour
    bars = _make_bars(ts_list, rows)
    out = anchors.build_h1_anchors(bars)
    assert len(out) == 2
    first = out.iloc[0]
    assert first["anchor_ts"] == base
    # The first anchor's high/low must NOT include the extreme values from the next hour
    assert first["high"] == 100.5
    assert first["low"] == 99.5


def test_empty_window_is_skipped():
    """A 2-hour gap produces N-1 anchors (the gap window has 0 bars and is skipped)."""
    base = pd.Timestamp("2024-01-02 10:00", tz="America/New_York")
    ts_list = []
    rows = []
    # Hour 10:00-11:00: 60 bars
    for i in range(60):
        ts_list.append(base + pd.Timedelta(minutes=i))
        rows.append((100.0, 100.5, 99.5, 100.0, 1))
    # Hour 11:00-12:00: SKIPPED (no bars)
    # Hour 12:00-13:00: 60 bars
    for i in range(60):
        ts_list.append(base + pd.Timedelta(hours=2, minutes=i))
        rows.append((100.0, 100.5, 99.5, 100.0, 1))
    bars = _make_bars(ts_list, rows)
    out = anchors.build_h1_anchors(bars)
    # Only 2 anchors should appear (10:00 and 12:00); 11:00 is skipped (empty window)
    assert len(out) == 2
    hours = sorted(out["anchor_ts"].dt.hour.tolist())
    assert hours == [10, 12]


def test_n_bars_count():
    """A full hour reports n_bars=60; a gappy hour reports the actual count."""
    base = pd.Timestamp("2024-01-02 10:00", tz="America/New_York")
    ts_list = []
    rows = []
    # Hour 10:00-11:00: 60 bars (full)
    for i in range(60):
        ts_list.append(base + pd.Timedelta(minutes=i))
        rows.append((100.0, 100.5, 99.5, 100.0, 1))
    # Hour 11:00-12:00: only 17 bars (gappy)
    for i in [0, 1, 2, 5, 10, 11, 12, 20, 25, 30, 35, 40, 45, 50, 55, 56, 57]:
        ts_list.append(base + pd.Timedelta(hours=1, minutes=i))
        rows.append((100.0, 100.5, 99.5, 100.0, 1))
    bars = _make_bars(ts_list, rows)
    out = anchors.build_h1_anchors(bars)
    assert len(out) == 2
    out_sorted = out.sort_values("anchor_ts").reset_index(drop=True)
    assert out_sorted.iloc[0]["n_bars"] == 60
    assert out_sorted.iloc[1]["n_bars"] == 17


def test_slice_h1_window_returns_empty_for_no_bars():
    """slice_h1_window on an anchor with no bars returns an empty DataFrame with the right schema."""
    base = pd.Timestamp("2024-01-02 10:00", tz="America/New_York")
    ts_list = [base + pd.Timedelta(minutes=i) for i in range(60)]
    rows = [(100.0, 100.5, 99.5, 100.0, 1)] * 60
    bars = _make_bars(ts_list, rows)
    # Slice an empty hour
    empty_anchor = pd.Timestamp("2024-01-02 14:00", tz="America/New_York")
    sliced = anchors.slice_h1_window(bars, empty_anchor)
    assert len(sliced) == 0
    assert list(sliced.columns) == list(bars.columns)
