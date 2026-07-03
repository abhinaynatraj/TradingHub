"""Tests for the Sprint 2 additions: per-row hourly excursion normalization,
equity-curve metrics, and (hour / dow / session / year) breakdown grouping.

These cover the new helper functions in engine/model_stats.py and the new
fields in engine/stats.py:agg() — without needing the full DuckDB to be
loaded, so they run in milliseconds.
"""
from __future__ import annotations

import pandas as pd
import pytest

from engine.constants import RISK_PER_TRADE_USD
from engine.model_stats import (
    _attach_hour_normalized_excursion,
    _build_breakdowns,
    _build_hour_range_lookup,
    _equity_metrics,
)
from engine.stats import agg, get_session


# ── _build_hour_range_lookup ────────────────────────────────────────────────

def _make_bars(rows: list[tuple]) -> pd.DataFrame:
    """Build a minimal bars DataFrame from (ts_str, high, low) tuples."""
    df = pd.DataFrame(rows, columns=["ts", "high", "low"])
    df["ts"] = pd.to_datetime(df["ts"]).dt.tz_localize("America/New_York")
    df["open"] = df["high"]
    df["close"] = df["low"]
    df["volume"] = 100
    return df


def test_hour_range_lookup_simple():
    bars = _make_bars([
        ("2024-01-08 09:30:00", 105.0, 100.0),
        ("2024-01-08 09:31:00", 107.0, 102.0),  # extends high
        ("2024-01-08 09:59:00", 106.0,  99.0),  # extends low
        ("2024-01-08 10:00:00", 110.0, 108.0),  # new hour
    ])
    lookup = _build_hour_range_lookup(bars)
    import datetime as dt
    assert lookup[(dt.date(2024, 1, 8), 9)] == pytest.approx(107.0 - 99.0)
    assert lookup[(dt.date(2024, 1, 8), 10)] == pytest.approx(110.0 - 108.0)


def test_hour_range_lookup_zero_range_becomes_none():
    """If an hour has only one bar with high == low, the lookup yields None
    (would otherwise divide-by-zero in mae_pct_hr/mfe_pct_hr)."""
    bars = _make_bars([
        ("2024-01-08 09:30:00", 100.0, 100.0),  # zero range
    ])
    lookup = _build_hour_range_lookup(bars)
    import datetime as dt
    assert lookup[(dt.date(2024, 1, 8), 9)] is None


def test_hour_range_lookup_empty_bars():
    bars = pd.DataFrame({"ts": [], "high": [], "low": [], "open": [], "close": [], "volume": []})
    assert _build_hour_range_lookup(bars) == {}


# ── _attach_hour_normalized_excursion ───────────────────────────────────────

def test_attach_excursion_with_known_range():
    import datetime as dt
    lookup = {(dt.date(2024, 1, 8), 9): 8.0}  # 8 point hour range
    row = {
        "entry_ts": "2024-01-08 09:35:00-05:00",
        "mae_pts": 2.0,
        "mfe_pts": 4.0,
    }
    _attach_hour_normalized_excursion(row, lookup)
    assert row["mae_pct_hr"] == pytest.approx(25.0)   # 2/8 * 100
    assert row["mfe_pct_hr"] == pytest.approx(50.0)   # 4/8 * 100


def test_attach_excursion_missing_lookup_yields_none():
    row = {"entry_ts": "2024-01-08 09:35:00-05:00", "mae_pts": 2.0, "mfe_pts": 4.0}
    _attach_hour_normalized_excursion(row, {})
    assert row["mae_pct_hr"] is None
    assert row["mfe_pct_hr"] is None


def test_attach_excursion_zero_range_yields_none():
    import datetime as dt
    lookup = {(dt.date(2024, 1, 8), 9): None}
    row = {"entry_ts": "2024-01-08 09:35:00-05:00", "mae_pts": 2.0, "mfe_pts": 4.0}
    _attach_hour_normalized_excursion(row, lookup)
    assert row["mae_pct_hr"] is None
    assert row["mfe_pct_hr"] is None


def test_attach_excursion_unparseable_ts_yields_none():
    row = {"entry_ts": "not a real timestamp", "mae_pts": 2.0, "mfe_pts": 4.0}
    _attach_hour_normalized_excursion(row, {})
    assert row["mae_pct_hr"] is None
    assert row["mfe_pct_hr"] is None


# ── _equity_metrics ─────────────────────────────────────────────────────────

def test_equity_metrics_simple_wins_then_losses():
    """+1, +1, -1, -1, -1: peak = $800 after 2 wins, trough at -$400 final,
    so max dd = $1200, max_dd_pct = 150%."""
    trades = [
        {"entry_ts": "2024-01-08 09:30", "r":  1.0, "outcome": "TP"},
        {"entry_ts": "2024-01-08 10:00", "r":  1.0, "outcome": "TP"},
        {"entry_ts": "2024-01-08 11:00", "r": -1.0, "outcome": "SL"},
        {"entry_ts": "2024-01-08 12:00", "r": -1.0, "outcome": "SL"},
        {"entry_ts": "2024-01-08 13:00", "r": -1.0, "outcome": "SL"},
    ]
    m = _equity_metrics(trades, RISK_PER_TRADE_USD)
    R = RISK_PER_TRADE_USD
    assert m["equity_curve_final_usd"] == pytest.approx(-1.0 * R)   # +2 -3 = -1R
    assert m["min_equity_usd"] == pytest.approx(-1.0 * R)
    assert m["max_dd_usd"] == pytest.approx(3.0 * R)               # 2R → -1R = 3R
    assert m["max_dd_pct"] == pytest.approx(150.0)                 # 3R / 2R peak


def test_equity_metrics_expired_treated_as_zero_pnl():
    trades = [
        {"entry_ts": "2024-01-08 09:30", "r":  1.0, "outcome": "TP"},
        {"entry_ts": "2024-01-08 10:00", "r":  None, "outcome": "EXPIRED"},
        {"entry_ts": "2024-01-08 11:00", "r": -1.0, "outcome": "SL"},
    ]
    m = _equity_metrics(trades, RISK_PER_TRADE_USD)
    assert m["equity_curve_final_usd"] == pytest.approx(0.0)
    assert m["max_dd_usd"] == pytest.approx(RISK_PER_TRADE_USD)  # peak $400 → $0


def test_equity_metrics_empty():
    m = _equity_metrics([], RISK_PER_TRADE_USD)
    assert m == {"min_equity_usd": 0.0, "max_dd_usd": 0.0,
                 "max_dd_pct": 0.0, "equity_curve_final_usd": 0.0}


def test_equity_metrics_sorts_chronologically():
    """Even if trades arrive out of order, the walk should sort by entry_ts."""
    trades = [
        {"entry_ts": "2024-01-08 11:00", "r": -1.0, "outcome": "SL"},
        {"entry_ts": "2024-01-08 09:30", "r":  1.0, "outcome": "TP"},   # earliest
        {"entry_ts": "2024-01-08 10:00", "r":  1.0, "outcome": "TP"},
    ]
    m = _equity_metrics(trades, RISK_PER_TRADE_USD)
    R = RISK_PER_TRADE_USD
    # Chronological: +1, +1, -1 → peak 2R, final 1R → max dd 1R = 50%
    assert m["equity_curve_final_usd"] == pytest.approx(1.0 * R)
    assert m["max_dd_usd"] == pytest.approx(1.0 * R)
    assert m["max_dd_pct"] == pytest.approx(50.0)


# ── _build_breakdowns ───────────────────────────────────────────────────────

def test_build_breakdowns_groups_correctly():
    trades = [
        # Mon 09:30 (NY1)
        {"entry_ts": "2024-01-08 09:30:00-05:00", "r": 1.0, "outcome": "TP"},
        # Mon 13:00 (NY2)
        {"entry_ts": "2024-01-08 13:00:00-05:00", "r": -1.0, "outcome": "SL"},
        # Tue 09:30 (NY1)
        {"entry_ts": "2024-01-09 09:30:00-05:00", "r": 1.0, "outcome": "TP"},
    ]
    out = _build_breakdowns(trades)
    # Hours: two at hour=9, one at hour=13
    assert sorted(out["by_hour"].keys()) == [9, 13]
    assert out["by_hour"][9]["n"] == 2
    assert out["by_hour"][13]["n"] == 1
    # DOW: Mon=0 has two, Tue=1 has one
    assert sorted(out["by_dow"].keys()) == [0, 1]
    assert out["by_dow"][0]["n"] == 2
    assert out["by_dow"][1]["n"] == 1
    # Session: NY1 has two, NY2 has one
    assert "NY1" in out["by_session"]
    assert "NY2" in out["by_session"]
    assert out["by_session"]["NY1"]["n"] == 2
    assert out["by_session"]["NY2"]["n"] == 1
    # Year: all 2024
    assert list(out["by_year"].keys()) == [2024]
    assert out["by_year"][2024]["n"] == 3


def test_build_breakdowns_empty_trades_yields_empty_dicts():
    out = _build_breakdowns([])
    assert out == {"by_hour": {}, "by_dow": {}, "by_session": {}, "by_year": {}}


# ── get_session classifier ──────────────────────────────────────────────────

@pytest.mark.parametrize("hr,expected", [
    (0, "OVERNIGHT"),
    (6.99, "OVERNIGHT"),
    (7, "PRE"),
    (8.49, "PRE"),
    (8.5, "NY1"),
    (11.49, "NY1"),
    (11.5, "NY2"),
    (15.99, "NY2"),
    (16, "AFTER"),
    (23, "AFTER"),
])
def test_get_session_classifier_boundaries(hr, expected):
    assert get_session(hr) == expected


# ── agg() with new fields ───────────────────────────────────────────────────

def test_agg_emits_avg_mae_hr_when_field_present():
    trades = [
        {"r":  1.0, "outcome": "TP", "mae_pct_hr": 20.0, "mfe_pct_hr": 80.0},
        {"r": -1.0, "outcome": "SL", "mae_pct_hr": 40.0, "mfe_pct_hr": 30.0},
    ]
    summary = agg(trades)
    assert summary["avg_mae_hr"] == pytest.approx(30.0)
    assert summary["avg_mfe_hr"] == pytest.approx(55.0)


def test_agg_skips_none_excursions_in_average():
    trades = [
        {"r":  1.0, "outcome": "TP", "mae_pct_hr": 20.0, "mfe_pct_hr": None},
        {"r": -1.0, "outcome": "SL", "mae_pct_hr": None, "mfe_pct_hr": 30.0},
    ]
    summary = agg(trades)
    assert summary["avg_mae_hr"] == pytest.approx(20.0)
    assert summary["avg_mfe_hr"] == pytest.approx(30.0)


def test_agg_no_excursion_field_emits_no_avg():
    trades = [{"r": 1.0, "outcome": "TP"}]
    summary = agg(trades)
    assert "avg_mae_hr" not in summary
    assert "avg_mfe_hr" not in summary
