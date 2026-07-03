"""Tests for engine.h1_filters — per-setup filter computations.

Each filter computes a single `passes_<key>: bool` flag for an H1 Continuation
setup. Per Task 3.1c, these are pure boolean computations independent of the
model detector itself; the detector composes them in 3.1d.

Coverage strategy: at least one True path AND one False path for each of the
10 filters. Edge cases (None inputs, empty DataFrames) are exercised where the
spec calls them out.
"""
from __future__ import annotations

import pandas as pd
import pytest

from engine.h1_filters import (
    passes_macro_010,
    passes_top3_macros,
    passes_avoid_lunch,
    passes_target_after_42,
    passes_no_opposite_struct_h1,
    passes_no_htf_rejection,
    passes_aggressive_body,
    passes_distribution_candle,
    passes_within_5m_structure,
    passes_smt,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _ts(s: str) -> pd.Timestamp:
    """Parse an NY-tz timestamp from 'YYYY-MM-DD HH:MM' string."""
    return pd.Timestamp(s, tz="America/New_York")


def _h1_row(
    *,
    anchor_ts: str = "2024-01-02 09:00",
    open_: float = 100.0,
    high: float = 110.0,
    low: float = 95.0,
    close: float = 108.0,
    extreme_minute_high: int = 50,
    extreme_minute_low: int = 5,
    volume: int = 1000,
    n_bars: int = 60,
) -> pd.Series:
    """Build an H1 row with the same shape as engine.anchors.build_h1_anchors output."""
    a = _ts(anchor_ts)
    return pd.Series({
        "anchor_ts": a,
        "close_ts": a + pd.Timedelta("1h"),
        "open": float(open_),
        "high": float(high),
        "low": float(low),
        "close": float(close),
        "volume": int(volume),
        "n_bars": int(n_bars),
        "extreme_minute_high": int(extreme_minute_high),
        "extreme_minute_low": int(extreme_minute_low),
    })


def _h1_df(rows: list[pd.Series]) -> pd.DataFrame:
    """Stack a list of H1 rows into a DataFrame (matches anchors output schema)."""
    return pd.DataFrame([r.to_dict() for r in rows])


# --------------------------------------------------------------------------- #
# 1. passes_macro_010
# --------------------------------------------------------------------------- #


def test_passes_macro_010_inside_55():
    assert passes_macro_010(_ts("2024-01-02 09:55")) is True


def test_passes_macro_010_inside_05():
    assert passes_macro_010(_ts("2024-01-02 10:05")) is True


def test_passes_macro_010_inside_at_00():
    assert passes_macro_010(_ts("2024-01-02 10:00")) is True


def test_passes_macro_010_outside_30():
    assert passes_macro_010(_ts("2024-01-02 09:30")) is False


def test_passes_macro_010_boundary_50():
    assert passes_macro_010(_ts("2024-01-02 09:50")) is True


def test_passes_macro_010_boundary_10():
    assert passes_macro_010(_ts("2024-01-02 09:10")) is True


def test_passes_macro_010_outside_11():
    assert passes_macro_010(_ts("2024-01-02 09:11")) is False


# --------------------------------------------------------------------------- #
# 2. passes_top3_macros
# --------------------------------------------------------------------------- #


def test_passes_top3_macros_0950():
    assert passes_top3_macros(_ts("2024-01-02 09:55")) is True


def test_passes_top3_macros_1010():
    assert passes_top3_macros(_ts("2024-01-02 10:05")) is True


def test_passes_top3_macros_0850():
    assert passes_top3_macros(_ts("2024-01-02 08:55")) is True


def test_passes_top3_macros_1100():
    assert passes_top3_macros(_ts("2024-01-02 11:05")) is True


def test_passes_top3_macros_outside_top3_lunch():
    assert passes_top3_macros(_ts("2024-01-02 13:55")) is False


def test_passes_top3_macros_outside_top3_morning():
    # 08:30 — neither top-3 window
    assert passes_top3_macros(_ts("2024-01-02 08:30")) is False


def test_passes_top3_macros_outside_at_1130():
    # 11:30 falls outside any of the three windows
    assert passes_top3_macros(_ts("2024-01-02 11:30")) is False


# --------------------------------------------------------------------------- #
# 3. passes_avoid_lunch
# --------------------------------------------------------------------------- #


def test_passes_avoid_lunch_inside_lunch_1200():
    assert passes_avoid_lunch(_ts("2024-01-02 12:00")) is False


def test_passes_avoid_lunch_inside_lunch_1150():
    assert passes_avoid_lunch(_ts("2024-01-02 11:50")) is False


def test_passes_avoid_lunch_inside_lunch_1210():
    assert passes_avoid_lunch(_ts("2024-01-02 12:10")) is False


def test_passes_avoid_lunch_outside_lunch_morning():
    assert passes_avoid_lunch(_ts("2024-01-02 09:55")) is True


def test_passes_avoid_lunch_outside_lunch_afternoon():
    assert passes_avoid_lunch(_ts("2024-01-02 14:55")) is True


def test_passes_avoid_lunch_just_before_lunch():
    assert passes_avoid_lunch(_ts("2024-01-02 11:49")) is True


def test_passes_avoid_lunch_just_after_lunch():
    assert passes_avoid_lunch(_ts("2024-01-02 12:11")) is True


# --------------------------------------------------------------------------- #
# 4. passes_target_after_42
# --------------------------------------------------------------------------- #


def test_passes_target_after_42_high_long_pass():
    prior = _h1_row(extreme_minute_high=46, extreme_minute_low=5)
    assert passes_target_after_42(prior, "long") is True


def test_passes_target_after_42_high_long_fail_early():
    prior = _h1_row(extreme_minute_high=30, extreme_minute_low=5)
    assert passes_target_after_42(prior, "long") is False


def test_passes_target_after_42_low_short_pass():
    prior = _h1_row(extreme_minute_high=5, extreme_minute_low=51)
    assert passes_target_after_42(prior, "short") is True


def test_passes_target_after_42_low_short_fail():
    prior = _h1_row(extreme_minute_high=5, extreme_minute_low=15)
    assert passes_target_after_42(prior, "short") is False


def test_passes_target_after_42_boundary_42_long():
    prior = _h1_row(extreme_minute_high=42, extreme_minute_low=0)
    assert passes_target_after_42(prior, "long") is True


# --------------------------------------------------------------------------- #
# 5. passes_no_opposite_struct_h1
# --------------------------------------------------------------------------- #


def test_passes_no_opposite_struct_h1_bullish_pass():
    # Bullish: close > open. Body = 5, lower wick (= min(open,close) - low) = 1.
    # Ratio 1/5 = 0.2 <= 0.5 → PASS.
    h1 = _h1_row(open_=100.0, close=105.0, high=106.0, low=99.0)
    assert passes_no_opposite_struct_h1(h1) is True


def test_passes_no_opposite_struct_h1_bullish_fail_huge_lower_wick():
    # Bullish: body=5, lower wick=10. Ratio 10/5 = 2 > 0.5 → FAIL.
    h1 = _h1_row(open_=100.0, close=105.0, high=106.0, low=90.0)
    assert passes_no_opposite_struct_h1(h1) is False


def test_passes_no_opposite_struct_h1_bearish_pass():
    # Bearish: close < open. body=5, upper wick (= high - max(open,close)) = 1.
    h1 = _h1_row(open_=105.0, close=100.0, high=106.0, low=99.0)
    assert passes_no_opposite_struct_h1(h1) is True


def test_passes_no_opposite_struct_h1_bearish_fail():
    # Bearish: body=5, upper wick=10. ratio=2 → FAIL.
    h1 = _h1_row(open_=105.0, close=100.0, high=115.0, low=99.0)
    assert passes_no_opposite_struct_h1(h1) is False


def test_passes_no_opposite_struct_h1_custom_threshold_pass():
    # tighter threshold: 0.1. body=5, lower wick=0.4, ratio=0.08 → PASS.
    h1 = _h1_row(open_=100.0, close=105.0, high=106.0, low=99.6)
    assert passes_no_opposite_struct_h1(h1, threshold=0.1) is True


def test_passes_no_opposite_struct_h1_custom_threshold_fail():
    # tighter threshold: 0.1. body=5, lower wick=1, ratio=0.2 → FAIL.
    h1 = _h1_row(open_=100.0, close=105.0, high=106.0, low=99.0)
    assert passes_no_opposite_struct_h1(h1, threshold=0.1) is False


# --------------------------------------------------------------------------- #
# 6. passes_no_htf_rejection
# --------------------------------------------------------------------------- #


def test_passes_no_htf_rejection_long_pass():
    # h1.high < max recent H4 high AND < max recent daily high → PASS
    h1 = _h1_row(anchor_ts="2024-01-02 10:00", high=110.0)
    h4 = _h1_df([
        _h1_row(anchor_ts="2024-01-02 04:00", high=120.0),
        _h1_row(anchor_ts="2024-01-02 08:00", high=115.0),
    ])
    daily = _h1_df([
        _h1_row(anchor_ts="2024-01-01 00:00", high=125.0),
    ])
    assert passes_no_htf_rejection(h1, h4, daily, "long") is True


def test_passes_no_htf_rejection_long_fail_h4_swept():
    # h1.high > max recent H4 high → FAIL
    h1 = _h1_row(anchor_ts="2024-01-02 10:00", high=130.0)
    h4 = _h1_df([
        _h1_row(anchor_ts="2024-01-02 04:00", high=120.0),
    ])
    daily = _h1_df([
        _h1_row(anchor_ts="2024-01-01 00:00", high=125.0),
    ])
    assert passes_no_htf_rejection(h1, h4, daily, "long") is False


def test_passes_no_htf_rejection_long_fail_daily_swept():
    h1 = _h1_row(anchor_ts="2024-01-02 10:00", high=140.0)
    h4 = _h1_df([
        _h1_row(anchor_ts="2024-01-02 04:00", high=150.0),
    ])
    daily = _h1_df([
        _h1_row(anchor_ts="2024-01-01 00:00", high=130.0),
    ])
    assert passes_no_htf_rejection(h1, h4, daily, "long") is False


def test_passes_no_htf_rejection_short_pass():
    # h1.low > min recent H4 low AND > min recent daily low → PASS
    h1 = _h1_row(anchor_ts="2024-01-02 10:00", low=95.0)
    h4 = _h1_df([
        _h1_row(anchor_ts="2024-01-02 04:00", low=80.0),
    ])
    daily = _h1_df([
        _h1_row(anchor_ts="2024-01-01 00:00", low=85.0),
    ])
    assert passes_no_htf_rejection(h1, h4, daily, "short") is True


def test_passes_no_htf_rejection_short_fail():
    # h1.low < min recent H4 low → FAIL
    h1 = _h1_row(anchor_ts="2024-01-02 10:00", low=70.0)
    h4 = _h1_df([
        _h1_row(anchor_ts="2024-01-02 04:00", low=80.0),
    ])
    daily = _h1_df([
        _h1_row(anchor_ts="2024-01-01 00:00", low=85.0),
    ])
    assert passes_no_htf_rejection(h1, h4, daily, "short") is False


def test_passes_no_htf_rejection_handles_none_h4():
    h1 = _h1_row(anchor_ts="2024-01-02 10:00", high=999.0)
    daily = _h1_df([
        _h1_row(anchor_ts="2024-01-01 00:00", high=125.0),
    ])
    # None h4 → skip → True (per spec)
    assert passes_no_htf_rejection(h1, None, daily, "long") is True


def test_passes_no_htf_rejection_handles_none_daily():
    h1 = _h1_row(anchor_ts="2024-01-02 10:00", high=999.0)
    h4 = _h1_df([
        _h1_row(anchor_ts="2024-01-02 04:00", high=120.0),
    ])
    assert passes_no_htf_rejection(h1, h4, None, "long") is True


def test_passes_no_htf_rejection_handles_empty_h4():
    h1 = _h1_row(anchor_ts="2024-01-02 10:00", high=999.0)
    empty_h4 = _h1_df([])
    daily = _h1_df([
        _h1_row(anchor_ts="2024-01-01 00:00", high=125.0),
    ])
    assert passes_no_htf_rejection(h1, empty_h4, daily, "long") is True


def test_passes_no_htf_rejection_only_uses_prior_bars():
    # An H4 bar AFTER h1.anchor_ts should be ignored.
    h1 = _h1_row(anchor_ts="2024-01-02 10:00", high=110.0)
    h4 = _h1_df([
        _h1_row(anchor_ts="2024-01-02 04:00", high=120.0),
        _h1_row(anchor_ts="2024-01-02 12:00", high=200.0),  # FUTURE — must be excluded
    ])
    daily = _h1_df([
        _h1_row(anchor_ts="2024-01-01 00:00", high=125.0),
    ])
    assert passes_no_htf_rejection(h1, h4, daily, "long") is True


# --------------------------------------------------------------------------- #
# 7. passes_aggressive_body
# --------------------------------------------------------------------------- #


def test_passes_aggressive_body_pass_70pct():
    # body 7, range 10 → 0.7 ≥ 0.6 → PASS
    h1 = _h1_row(open_=100.0, close=107.0, high=108.5, low=98.5)
    assert passes_aggressive_body(h1) is True


def test_passes_aggressive_body_doji_fail():
    # body 0.1, range 10 → 0.01 < 0.6 → FAIL
    h1 = _h1_row(open_=100.0, close=100.1, high=105.0, low=95.0)
    assert passes_aggressive_body(h1) is False


def test_passes_aggressive_body_boundary_60():
    # body=6, range=10 → exactly 0.6 → PASS (>=)
    h1 = _h1_row(open_=100.0, close=106.0, high=108.0, low=98.0)
    assert passes_aggressive_body(h1) is True


def test_passes_aggressive_body_custom_threshold():
    # body 5, range 10 → 0.5 < 0.6 → FAIL default; PASS at 0.4
    h1 = _h1_row(open_=100.0, close=105.0, high=107.5, low=97.5)
    assert passes_aggressive_body(h1) is False
    assert passes_aggressive_body(h1, threshold=0.4) is True


# --------------------------------------------------------------------------- #
# 8. passes_distribution_candle
# --------------------------------------------------------------------------- #


def test_passes_distribution_candle_long_pass():
    # Bullish distribution: low formed early (<:42), high late (>=:42)
    h1 = _h1_row(extreme_minute_low=15, extreme_minute_high=55)
    assert passes_distribution_candle(h1, "long") is True


def test_passes_distribution_candle_long_fail_pullback():
    # Bullish pullback: high formed EARLY (<:42) → FAIL
    h1 = _h1_row(extreme_minute_low=2, extreme_minute_high=15)
    assert passes_distribution_candle(h1, "long") is False


def test_passes_distribution_candle_long_fail_low_late():
    # Bullish but the low is also late (>=:42) — not the OHLC-distribution shape
    h1 = _h1_row(extreme_minute_low=55, extreme_minute_high=58)
    assert passes_distribution_candle(h1, "long") is False


def test_passes_distribution_candle_short_pass():
    # Bearish distribution: high formed early, low late
    h1 = _h1_row(extreme_minute_high=15, extreme_minute_low=55)
    assert passes_distribution_candle(h1, "short") is True


def test_passes_distribution_candle_short_fail_pullback():
    # Bearish pullback: low formed early
    h1 = _h1_row(extreme_minute_high=58, extreme_minute_low=15)
    assert passes_distribution_candle(h1, "short") is False


def test_passes_distribution_candle_short_boundary():
    # Boundary: high at :41, low at :42 → PASS (high<42 AND low>=42)
    h1 = _h1_row(extreme_minute_high=41, extreme_minute_low=42)
    assert passes_distribution_candle(h1, "short") is True


# --------------------------------------------------------------------------- #
# 9. passes_within_5m_structure
# --------------------------------------------------------------------------- #


def test_passes_within_5m_structure_close():
    assert passes_within_5m_structure(100.0, 130.0) is True


def test_passes_within_5m_structure_far():
    assert passes_within_5m_structure(100.0, 200.0) is False


def test_passes_within_5m_structure_exact_threshold():
    # 40 == 40 → PASS (<=)
    assert passes_within_5m_structure(100.0, 140.0) is True


def test_passes_within_5m_structure_negative_direction():
    # short setup: entry above draw → still |delta|
    assert passes_within_5m_structure(150.0, 130.0) is True


def test_passes_within_5m_structure_custom_threshold():
    assert passes_within_5m_structure(100.0, 130.0, threshold=20.0) is False
    assert passes_within_5m_structure(100.0, 110.0, threshold=20.0) is True


# --------------------------------------------------------------------------- #
# 10. passes_smt
# --------------------------------------------------------------------------- #


def _es_window(*, highs: list[float], lows: list[float] | None = None) -> pd.DataFrame:
    """Build an ES 1m bars window (only high/low needed for SMT)."""
    if lows is None:
        lows = [h - 5.0 for h in highs]
    base = _ts("2024-01-02 10:00")
    rows = []
    for i, (h, l) in enumerate(zip(highs, lows)):
        rows.append({
            "ts": base + pd.Timedelta(minutes=i),
            "open": (h + l) / 2,
            "high": h,
            "low": l,
            "close": (h + l) / 2,
            "volume": 10,
        })
    df = pd.DataFrame(rows)
    df["ts"] = df["ts"].astype("datetime64[ns, America/New_York]")
    return df


def test_passes_smt_long_nq_swept_es_didnt():
    # NQ.high (110) > prior_nq_extreme (105). ES window max (98) <= prior_es_extreme (100). PASS.
    nq = _h1_row(high=110.0, low=90.0)
    es = _es_window(highs=[98.0, 97.5, 97.8])
    assert passes_smt(nq, prior_nq_extreme=105.0, es_h1_window=es,
                     prior_es_extreme=100.0, direction="long") is True


def test_passes_smt_long_both_swept_fail():
    # Both NQ and ES swept → FAIL (no divergence).
    nq = _h1_row(high=110.0, low=90.0)
    es = _es_window(highs=[101.0, 102.0, 99.0])  # max 102 > 100
    assert passes_smt(nq, prior_nq_extreme=105.0, es_h1_window=es,
                     prior_es_extreme=100.0, direction="long") is False


def test_passes_smt_long_nq_didnt_sweep_fail():
    # NQ failed to sweep its own prior high → SMT undefined / FAIL
    nq = _h1_row(high=104.0, low=90.0)  # 104 < 105 (prior_nq_extreme)
    es = _es_window(highs=[98.0, 97.0])
    assert passes_smt(nq, prior_nq_extreme=105.0, es_h1_window=es,
                     prior_es_extreme=100.0, direction="long") is False


def test_passes_smt_short_pass():
    # NQ low (80) < prior_nq_extreme (90). ES window min (102) >= prior_es_extreme (100). PASS.
    nq = _h1_row(high=120.0, low=80.0)
    es = _es_window(highs=[110.0, 108.0], lows=[105.0, 102.0])
    assert passes_smt(nq, prior_nq_extreme=90.0, es_h1_window=es,
                     prior_es_extreme=100.0, direction="short") is True


def test_passes_smt_short_both_swept_fail():
    nq = _h1_row(high=120.0, low=80.0)
    es = _es_window(highs=[110.0, 108.0], lows=[95.0, 94.0])  # min 94 < 100
    assert passes_smt(nq, prior_nq_extreme=90.0, es_h1_window=es,
                     prior_es_extreme=100.0, direction="short") is False


def test_passes_smt_handles_empty_es_window():
    nq = _h1_row(high=110.0, low=90.0)
    empty = _es_window(highs=[]) if False else pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume"])
    assert passes_smt(nq, prior_nq_extreme=105.0, es_h1_window=empty,
                     prior_es_extreme=100.0, direction="long") is False


def test_passes_smt_handles_none_prior_extremes():
    nq = _h1_row(high=110.0, low=90.0)
    es = _es_window(highs=[98.0, 97.0])
    assert passes_smt(nq, prior_nq_extreme=None, es_h1_window=es,
                     prior_es_extreme=100.0, direction="long") is False
    assert passes_smt(nq, prior_nq_extreme=105.0, es_h1_window=es,
                     prior_es_extreme=None, direction="long") is False
