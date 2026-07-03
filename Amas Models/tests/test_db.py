"""Tests for engine.db — DB load, TZ correctness, data-quality assertions.

Per the design spec, Category A (TZ correctness) and Category E (Data quality):
every load must be tz-aware, [ns] resolution, monotonic, no duplicates, OHLC sane,
schema validated.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from engine import db


def test_db_path_resolves_to_fractal_sweep():
    p = db.db_path()
    assert p.name == "candle_science.duckdb"
    assert p.parent.name == "Fractal Sweep"


def test_db_path_exists():
    assert db.db_path().exists(), "Shared DB not found — Fractal Sweep must be present"


def test_load_bars_returns_tz_aware_ns_resolution():
    df = db.load_bars("nq_1m", start="2024-01-02", end="2024-01-03")
    assert df["ts"].dt.tz is not None, "ts must be tz-aware"
    assert df["ts"].dtype.unit == "ns", "ts must be [ns] resolution"
    assert str(df["ts"].dt.tz) == "America/New_York", "ts must be in NY tz"


def test_load_bars_schema():
    df = db.load_bars("nq_1m", start="2024-01-02", end="2024-01-03")
    assert list(df.columns) == ["ts", "open", "high", "low", "close", "volume"]
    assert df["open"].dtype == "float64"
    assert df["volume"].dtype == "int64"


def test_load_bars_monotonic_and_unique():
    df = db.load_bars("nq_1m", start="2024-01-02", end="2024-01-03")
    assert df["ts"].is_monotonic_increasing
    assert df["ts"].is_unique


def test_load_bars_ohlc_sanity():
    df = db.load_bars("nq_1m", start="2024-01-02", end="2024-01-03")
    assert (df["low"] <= df[["open", "close", "high"]].min(axis=1)).all()
    assert (df["high"] >= df[["open", "close", "low"]].max(axis=1)).all()


def test_tz_sentinel_known_minute():
    """Sanity test: the 09:30 ET open of a known weekday must exist with the right wall-clock timestamp.

    Uses 2024-01-02 (first trading day of 2024, Tue, no half-day).
    """
    df = db.load_bars("nq_1m", start="2024-01-02", end="2024-01-03")
    target = pd.Timestamp("2024-01-02 09:30:00", tz="America/New_York")
    matches = df[df["ts"] == target]
    assert len(matches) == 1, f"Expected exactly one bar at 2024-01-02 09:30 ET; got {len(matches)}"


def test_assert_load_invariants_rejects_naive_timestamps():
    df = pd.DataFrame({
        "ts": pd.to_datetime(["2024-01-02 09:30", "2024-01-02 09:31"]),
        "open": [100.0, 100.1], "high": [100.5, 100.6], "low": [99.5, 99.6],
        "close": [100.2, 100.3], "volume": [10, 10],
    })
    with pytest.raises(AssertionError, match="tz-aware"):
        db.assert_load_invariants(df)


def test_assert_load_invariants_rejects_us_resolution():
    df = pd.DataFrame({
        "ts": pd.to_datetime(["2024-01-02 09:30", "2024-01-02 09:31"], utc=True).astype("datetime64[us, UTC]"),
        "open": [100.0, 100.1], "high": [100.5, 100.6], "low": [99.5, 99.6],
        "close": [100.2, 100.3], "volume": [10, 10],
    })
    with pytest.raises(AssertionError, match=r"\[ns\]"):
        db.assert_load_invariants(df)


def test_assert_load_invariants_rejects_duplicate_timestamps():
    ts = pd.Timestamp("2024-01-02 09:30", tz="America/New_York")
    df = pd.DataFrame({
        "ts": [ts, ts],
        "open": [100.0, 100.1], "high": [100.5, 100.6], "low": [99.5, 99.6],
        "close": [100.2, 100.3], "volume": [10, 10],
    })
    df["ts"] = df["ts"].astype("datetime64[ns, America/New_York]")
    with pytest.raises(AssertionError, match="unique"):
        db.assert_load_invariants(df)


def test_assert_load_invariants_rejects_non_monotonic():
    df = pd.DataFrame({
        "ts": [
            pd.Timestamp("2024-01-02 09:31", tz="America/New_York"),
            pd.Timestamp("2024-01-02 09:30", tz="America/New_York"),
        ],
        "open": [100.0, 100.1], "high": [100.5, 100.6], "low": [99.5, 99.6],
        "close": [100.2, 100.3], "volume": [10, 10],
    })
    df["ts"] = df["ts"].astype("datetime64[ns, America/New_York]")
    with pytest.raises(AssertionError, match="monotonic"):
        db.assert_load_invariants(df)


def test_assert_load_invariants_rejects_invalid_ohlc():
    df = pd.DataFrame({
        "ts": [pd.Timestamp("2024-01-02 09:30", tz="America/New_York")],
        "open": [100.0], "high": [99.0], "low": [101.0],  # high < low
        "close": [100.5], "volume": [10],
    })
    df["ts"] = df["ts"].astype("datetime64[ns, America/New_York]")
    with pytest.raises(AssertionError, match="OHLC"):
        db.assert_load_invariants(df)


def test_check_gaps_flags_intra_session_gap():
    """A gap with 10 missing minutes during RTH is reported.

    `gap_minutes` is wall-clock minutes between consecutive retained bars
    (i.e., `next.ts - prev.ts` in minutes), so 10 missing minutes between bars
    at :09 and :20 reports as 11.0 minutes wall-clock.
    """
    rows = []
    base = pd.Timestamp("2024-01-02 09:30", tz="America/New_York")
    for i in range(10):
        rows.append({"ts": base + pd.Timedelta(minutes=i), "open": 100.0, "high": 100.1, "low": 99.9, "close": 100.0, "volume": 10})
    # gap: skip minutes 10..19, resume at minute 20 → 10 missing minutes,
    # 11 minutes wall-clock between bar at :09 and bar at :20.
    for i in range(20, 30):
        rows.append({"ts": base + pd.Timedelta(minutes=i), "open": 100.0, "high": 100.1, "low": 99.9, "close": 100.0, "volume": 10})
    df = pd.DataFrame(rows)
    df["ts"] = df["ts"].astype("datetime64[ns, America/New_York]")
    df["volume"] = df["volume"].astype("int64")
    gaps = db.check_gaps(df)
    assert len(gaps) == 1
    assert gaps[0]["gap_minutes"] == 11.0
