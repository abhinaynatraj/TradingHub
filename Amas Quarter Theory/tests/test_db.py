"""Tests for engine.db — DB load, tz conversion, data-quality assertions."""
from __future__ import annotations

import pandas as pd
import pytest

from engine import db


def test_db_path_points_to_fractal_sweep():
    p = db.db_path()
    assert p.name == "candle_science.duckdb"
    assert p.parent.name == "Fractal Sweep"


def test_assert_load_invariants_passes_clean_frame():
    df = pd.DataFrame({
        "ts": pd.to_datetime(["2024-01-02 09:30", "2024-01-02 09:31", "2024-01-02 09:32"])
                .tz_localize("America/New_York"),
        "open":   [100.0, 101.0, 102.0],
        "high":   [101.5, 102.5, 103.5],
        "low":    [ 99.5, 100.5, 101.5],
        "close":  [101.0, 102.0, 103.0],
        "volume": [10, 20, 30],
    })
    df["ts"] = df["ts"].astype("datetime64[ns, America/New_York]")
    df["volume"] = df["volume"].astype("int64")
    db.assert_load_invariants(df)  # should not raise


def test_assert_load_invariants_rejects_naive_ts():
    df = pd.DataFrame({
        "ts": pd.to_datetime(["2024-01-02 09:30"]),  # tz-naive
        "open": [100.0], "high": [101.0], "low": [99.0], "close": [100.5],
        "volume": pd.Series([10], dtype="int64"),
    })
    with pytest.raises(AssertionError, match="tz-aware"):
        db.assert_load_invariants(df)


def test_assert_load_invariants_rejects_duplicate_ts():
    df = pd.DataFrame({
        "ts": pd.to_datetime(["2024-01-02 09:30", "2024-01-02 09:30"])
                .tz_localize("America/New_York"),
        "open": [100.0, 100.0], "high": [101.0, 101.0],
        "low": [99.0, 99.0], "close": [100.5, 100.5],
        "volume": pd.Series([10, 10], dtype="int64"),
    })
    df["ts"] = df["ts"].astype("datetime64[ns, America/New_York]")
    with pytest.raises(AssertionError, match="unique"):
        db.assert_load_invariants(df)


def test_assert_load_invariants_rejects_ohlc_violation():
    df = pd.DataFrame({
        "ts": pd.to_datetime(["2024-01-02 09:30"]).tz_localize("America/New_York"),
        "open": [100.0], "high": [99.0],  # high < open — invalid
        "low": [98.0], "close": [99.5],
        "volume": pd.Series([10], dtype="int64"),
    })
    df["ts"] = df["ts"].astype("datetime64[ns, America/New_York]")
    with pytest.raises(AssertionError, match="OHLC"):
        db.assert_load_invariants(df)
