"""Tests for engine.models.h1_continuation — H1 Continuation detector.

Per Task 3.1d, this module composes engine/anchors.py, engine/m1_patterns.py,
and engine/h1_filters.py into `detect_setups`. The composition must:

- Emit one Setup per (anchor_ts, direction) at most (dedup invariant, Cat B).
- Causal: any setup must reproduce when bars are truncated at entry_ts (Cat C).
- Risk-gate: setups with risk_pts > MAX_RISK_PTS are EXCLUDED, not flagged (Cat F).
- Attach all 10 passes_<key>: bool flags as real booleans (no None, no missing).
- Construct valid Setup objects (let Setup.__post_init__ raise on malformed).
"""
from __future__ import annotations

import dataclasses

import pandas as pd
import pytest

from engine.constants import MAX_RISK_PTS
from engine.models import MODELS
from engine.models.h1_continuation import detect_setups, _H1ContinuationSetup
from engine.outcomes import Setup


# --------------------------------------------------------------------------- #
# Fixture builders
# --------------------------------------------------------------------------- #

EXPECTED_FLAGS = [
    "passes_macro_010",
    "passes_top3_macros",
    "passes_avoid_lunch",
    "passes_target_after_42",
    "passes_no_opposite_struct_h1",
    "passes_no_htf_rejection",
    "passes_aggressive_body",
    "passes_distribution_candle",
    "passes_within_5m_structure",
    "passes_smt",
]


def _empty_bars() -> pd.DataFrame:
    df = pd.DataFrame({
        "ts": pd.Series(dtype="datetime64[ns, America/New_York]"),
        "open": pd.Series(dtype="float64"),
        "high": pd.Series(dtype="float64"),
        "low": pd.Series(dtype="float64"),
        "close": pd.Series(dtype="float64"),
        "volume": pd.Series(dtype="int64"),
    })
    return df


def _build_bars(rows: list[dict]) -> pd.DataFrame:
    """rows: list of dicts with ts, open, high, low, close, volume."""
    df = pd.DataFrame(rows)
    df["ts"] = df["ts"].astype("datetime64[ns, America/New_York]")
    df["volume"] = df["volume"].astype("int64")
    return df


def _h1_bars(anchor_ts_str: str, *, open_: float, high: float, low: float, close: float,
             em_high_minute: int = 50, em_low_minute: int = 5) -> list[dict]:
    """Build 60 minutes of M1 bars matching a specific H1 candle's OHLC + extreme minutes.

    The minute-of-hour values em_high_minute/em_low_minute determine WHICH minute
    bar carries the extreme price.
    """
    base = pd.Timestamp(anchor_ts_str, tz="America/New_York")
    out = []
    # Body interpolation: linear from open at minute 0 to close at minute 59.
    for i in range(60):
        # Default OHLC near-flat around an interpolated mid
        frac = i / 59.0
        mid = open_ + (close - open_) * frac
        h = mid + 0.05
        l = mid - 0.05
        o = mid
        c = mid + 0.01
        if i == 0:
            o = open_  # ensure first bar opens at H1 open
            c = open_ + 0.01
            h = open_ + 0.05
            l = open_ - 0.05
        if i == 59:
            c = close  # ensure last bar closes at H1 close
            o = close - 0.01
            h = close + 0.05
            l = close - 0.05
        if i == em_high_minute:
            h = high
        if i == em_low_minute:
            l = low
        out.append({
            "ts": base + pd.Timedelta(minutes=i),
            "open": o, "high": h, "low": l, "close": c, "volume": 10,
        })
    return out


def _bullish_continuation_fixture():
    """Two H1 candles: prior closes lower, current closes ABOVE prior.high.

    Then 10 minutes of post-close M1 bars forming a long OB on a PULLBACK below
    prior.high (the draw): the breakout retraces back through prior.high=105.0
    forming an M1 OB whose entry is below 105.0 (so entry_price < draw geometry
    is satisfied).
    """
    # Prior H1: 09:00-10:00. open=100, high=105, low=99, close=104.
    # extreme high at minute 50 (>=42, so passes T42).
    prior = _h1_bars("2024-01-02 09:00", open_=100.0, high=105.0, low=99.0, close=104.0,
                      em_high_minute=50, em_low_minute=5)
    # Current H1: 10:00-11:00. open=104, close=107 (> prior.high=105 → bullish continuation).
    current = _h1_bars("2024-01-02 10:00", open_=104.0, high=107.5, low=103.0, close=107.0,
                        em_high_minute=55, em_low_minute=10)
    # Post-close window: 11:00-11:10. Price pulls back BELOW prior.high=105, forms an
    # M1 OB whose entry is at 104.5 (below draw), then resumes up.
    # bar 0: down-close (OB candidate). open=104.8, close=104.3, high=104.9, low=104.0.
    #   entry=104.8, invalidation=104.0, risk=0.8.
    # bar 1: up-close, no OB violation, no high break (high <= 104.9, low >= 104.0).
    # bar 2: higher high (high=105.0 > 104.9) → OB confirmed.
    base11 = pd.Timestamp("2024-01-02 11:00", tz="America/New_York")
    post = [
        {"ts": base11 + pd.Timedelta(minutes=0),
         "open": 104.8, "high": 104.9, "low": 104.0, "close": 104.3, "volume": 10},  # OB candidate (down-close)
        {"ts": base11 + pd.Timedelta(minutes=1),
         "open": 104.3, "high": 104.85, "low": 104.1, "close": 104.7, "volume": 10},  # no break
        {"ts": base11 + pd.Timedelta(minutes=2),
         "open": 104.7, "high": 105.0, "low": 104.5, "close": 104.9, "volume": 10},  # break (105.0 > 104.9)
    ]
    for i in range(3, 10):
        post.append({
            "ts": base11 + pd.Timedelta(minutes=i),
            "open": 104.9, "high": 105.1, "low": 104.8, "close": 105.0, "volume": 10,
        })
    # Add follow-on bars so outcome resolver can run. After M1 OB, price runs up;
    # entry=104.8, sl=104.0, risk=0.8, tp = 104.8 + 0.8 = 105.6.
    follow = []
    for i in range(10, 600):
        follow.append({
            "ts": base11 + pd.Timedelta(minutes=i),
            "open": 105.0, "high": 106.0, "low": 104.9, "close": 105.5, "volume": 10,
        })
    rows = prior + current + post + follow
    return _build_bars(rows)


def _bearish_continuation_fixture():
    """Mirror of bullish. Prior closes higher, current closes BELOW prior.low.

    Post-close window: price PULLS BACK UP through prior.low (the draw=105.0),
    forms a short M1 OB whose entry is above 105.0. Then drops back down.
    """
    prior = _h1_bars("2024-01-02 09:00", open_=110.0, high=111.0, low=105.0, close=106.0,
                      em_high_minute=5, em_low_minute=50)
    current = _h1_bars("2024-01-02 10:00", open_=106.0, high=106.5, low=102.0, close=103.0,
                        em_high_minute=10, em_low_minute=55)
    base11 = pd.Timestamp("2024-01-02 11:00", tz="America/New_York")
    # Short OB: bar 0 up-close (entry > draw=105). bar 2 makes lower-low.
    # bar 0: open=105.2, close=105.7, high=106.0, low=105.1. entry=105.2, invalid=106.0, risk=0.8.
    # bar 1: down-close, no high break (high <= 106.0), no low violation (low >= 105.1).
    # bar 2: lower-low (low < 105.1).
    post = [
        {"ts": base11 + pd.Timedelta(minutes=0),
         "open": 105.2, "high": 106.0, "low": 105.1, "close": 105.7, "volume": 10},  # up-close OB
        {"ts": base11 + pd.Timedelta(minutes=1),
         "open": 105.7, "high": 105.9, "low": 105.15, "close": 105.3, "volume": 10},  # no break
        {"ts": base11 + pd.Timedelta(minutes=2),
         "open": 105.3, "high": 105.5, "low": 105.0, "close": 105.1, "volume": 10},  # lower-low (105.0 < 105.1)
    ]
    for i in range(3, 10):
        post.append({
            "ts": base11 + pd.Timedelta(minutes=i),
            "open": 105.1, "high": 105.15, "low": 104.8, "close": 104.9, "volume": 10,
        })
    follow = []
    for i in range(10, 600):
        follow.append({
            "ts": base11 + pd.Timedelta(minutes=i),
            "open": 104.9, "high": 105.0, "low": 103.5, "close": 104.0, "volume": 10,
        })
    rows = prior + current + post + follow
    return _build_bars(rows)


# --------------------------------------------------------------------------- #
# 1. Empty bars
# --------------------------------------------------------------------------- #


def test_detect_setups_empty_bars():
    bars = _empty_bars()
    setups = detect_setups(bars)
    assert setups == []


# --------------------------------------------------------------------------- #
# 2. One bullish continuation
# --------------------------------------------------------------------------- #


def test_detect_setups_one_bullish_continuation():
    bars = _bullish_continuation_fixture()
    setups = detect_setups(bars)
    assert len(setups) == 1, f"expected 1 setup, got {len(setups)}: {setups}"
    s = setups[0]
    assert isinstance(s, Setup)
    assert s.direction == "long"
    assert s.draw_price == 105.0  # prior.high
    # Geometric sanity
    assert s.sl_price < s.entry_price < s.tp_price
    # All 10 flags present and bool
    for flag in EXPECTED_FLAGS:
        assert hasattr(s, flag), f"missing flag {flag}"
        v = getattr(s, flag)
        assert isinstance(v, bool), f"{flag} = {v!r} is not bool"
    # anchor_ts is the H1 anchor of the trigger candle (current.anchor_ts)
    assert s.anchor_ts == pd.Timestamp("2024-01-02 10:00", tz="America/New_York")
    assert s.entry_pattern in ("OB", "BREAKER", "INV_FVG")
    # Risk gate
    assert s.risk_pts <= MAX_RISK_PTS


# --------------------------------------------------------------------------- #
# 3. One bearish continuation
# --------------------------------------------------------------------------- #


def test_detect_setups_one_bearish_continuation():
    bars = _bearish_continuation_fixture()
    setups = detect_setups(bars)
    assert len(setups) == 1, f"expected 1 setup, got {len(setups)}: {setups}"
    s = setups[0]
    assert s.direction == "short"
    assert s.draw_price == 105.0  # prior.low
    assert s.sl_price > s.entry_price > s.tp_price
    for flag in EXPECTED_FLAGS:
        assert hasattr(s, flag) and isinstance(getattr(s, flag), bool)
    assert s.anchor_ts == pd.Timestamp("2024-01-02 10:00", tz="America/New_York")


# --------------------------------------------------------------------------- #
# 4. No pattern in post-close window
# --------------------------------------------------------------------------- #


def test_detect_setups_no_pattern_in_post_close_window():
    """Bullish continuation but post-close M1 window has only flat bars (no OB/Breaker/InvFVG)."""
    prior = _h1_bars("2024-01-02 09:00", open_=100.0, high=105.0, low=99.0, close=104.0,
                      em_high_minute=50, em_low_minute=5)
    current = _h1_bars("2024-01-02 10:00", open_=104.0, high=107.5, low=103.0, close=107.0,
                        em_high_minute=55, em_low_minute=10)
    base11 = pd.Timestamp("2024-01-02 11:00", tz="America/New_York")
    # 10 perfectly flat bars — no OB, no breaker, no FVG. Price stays above draw=105
    # so there's no PB-with-OB to fire on either.
    post = []
    for i in range(10):
        post.append({
            "ts": base11 + pd.Timedelta(minutes=i),
            "open": 106.5, "high": 106.55, "low": 106.45, "close": 106.5, "volume": 10,
        })
    follow = []
    for i in range(10, 100):
        follow.append({
            "ts": base11 + pd.Timedelta(minutes=i),
            "open": 106.5, "high": 106.55, "low": 106.45, "close": 106.5, "volume": 10,
        })
    bars = _build_bars(prior + current + post + follow)
    setups = detect_setups(bars)
    assert setups == [], f"expected 0 setups (no M1 pattern), got {len(setups)}"


# --------------------------------------------------------------------------- #
# 5. Risk gate excludes wide stops
# --------------------------------------------------------------------------- #


def test_detect_setups_risk_gate_excludes_wide_stops():
    """M1 OB whose invalidation is > MAX_RISK_PTS away → setup excluded entirely."""
    prior = _h1_bars("2024-01-02 09:00", open_=100.0, high=105.0, low=70.0, close=104.0,
                      em_high_minute=50, em_low_minute=5)
    current = _h1_bars("2024-01-02 10:00", open_=104.0, high=107.5, low=80.0, close=107.0,
                        em_high_minute=55, em_low_minute=10)
    base11 = pd.Timestamp("2024-01-02 11:00", tz="America/New_York")
    # OB on a pullback below draw=105 with VERY wide invalidation (low=80, entry=104.8 →
    # risk=24.8 > MAX_RISK_PTS=20.0). And no other qualifying patterns in the window.
    post = [
        {"ts": base11 + pd.Timedelta(minutes=0),
         "open": 104.8, "high": 104.9, "low": 80.0, "close": 104.3, "volume": 10},  # huge low → wide stop
        {"ts": base11 + pd.Timedelta(minutes=1),
         "open": 104.3, "high": 104.85, "low": 104.1, "close": 104.7, "volume": 10},  # no break
        {"ts": base11 + pd.Timedelta(minutes=2),
         "open": 104.7, "high": 105.0, "low": 104.5, "close": 104.9, "volume": 10},  # break
    ]
    for i in range(3, 10):
        post.append({
            "ts": base11 + pd.Timedelta(minutes=i),
            "open": 104.9, "high": 105.1, "low": 104.8, "close": 105.0, "volume": 10,
        })
    follow = []
    for i in range(10, 100):
        follow.append({
            "ts": base11 + pd.Timedelta(minutes=i),
            "open": 105.0, "high": 106.0, "low": 104.9, "close": 105.5, "volume": 10,
        })
    bars = _build_bars(prior + current + post + follow)
    setups = detect_setups(bars)
    # The first OB in the window has risk > 20 → excluded. No other OB within 10 bars
    # → no setup at this anchor.
    assert setups == [], f"expected 0 setups (risk gate), got {len(setups)} with risks {[s.risk_pts for s in setups]}"


# --------------------------------------------------------------------------- #
# 6. Dedup: at most one setup per (anchor_ts, direction)
# --------------------------------------------------------------------------- #


def test_detect_setups_no_duplicates():
    """Multiple OBs in window (all entry < draw) — only the FIRST is taken."""
    prior = _h1_bars("2024-01-02 09:00", open_=100.0, high=105.0, low=99.0, close=104.0,
                      em_high_minute=50, em_low_minute=5)
    current = _h1_bars("2024-01-02 10:00", open_=104.0, high=107.5, low=103.0, close=107.0,
                        em_high_minute=55, em_low_minute=10)
    base11 = pd.Timestamp("2024-01-02 11:00", tz="America/New_York")
    # Two long OBs in succession, both with entry < draw=105.
    post = [
        # First OB at bar 0-2 (entry=104.8, invalid=104.0)
        {"ts": base11 + pd.Timedelta(minutes=0),
         "open": 104.8, "high": 104.9, "low": 104.0, "close": 104.3, "volume": 10},
        {"ts": base11 + pd.Timedelta(minutes=1),
         "open": 104.3, "high": 104.85, "low": 104.1, "close": 104.7, "volume": 10},
        {"ts": base11 + pd.Timedelta(minutes=2),
         "open": 104.7, "high": 105.0, "low": 104.5, "close": 104.9, "volume": 10},  # break
        # Second OB candidate at bar 3-5
        {"ts": base11 + pd.Timedelta(minutes=3),
         "open": 104.9, "high": 105.0, "low": 104.4, "close": 104.5, "volume": 10},  # down-close
        {"ts": base11 + pd.Timedelta(minutes=4),
         "open": 104.5, "high": 104.95, "low": 104.45, "close": 104.8, "volume": 10},  # no break
        {"ts": base11 + pd.Timedelta(minutes=5),
         "open": 104.8, "high": 105.05, "low": 104.7, "close": 105.0, "volume": 10},  # break
        # Filler bars
        {"ts": base11 + pd.Timedelta(minutes=6),
         "open": 105.0, "high": 105.1, "low": 104.9, "close": 105.05, "volume": 10},
        {"ts": base11 + pd.Timedelta(minutes=7),
         "open": 105.05, "high": 105.15, "low": 104.95, "close": 105.1, "volume": 10},
        {"ts": base11 + pd.Timedelta(minutes=8),
         "open": 105.1, "high": 105.2, "low": 105.0, "close": 105.15, "volume": 10},
        {"ts": base11 + pd.Timedelta(minutes=9),
         "open": 105.15, "high": 105.25, "low": 105.05, "close": 105.2, "volume": 10},
    ]
    follow = []
    for i in range(10, 400):
        follow.append({
            "ts": base11 + pd.Timedelta(minutes=i),
            "open": 105.2, "high": 106.0, "low": 105.0, "close": 105.7, "volume": 10,
        })
    bars = _build_bars(prior + current + post + follow)
    setups = detect_setups(bars)
    # Should be exactly 1 setup at this anchor (the first OB)
    keys = [(s.anchor_ts, s.direction) for s in setups]
    assert len(keys) == len(set(keys)), f"duplicates! keys = {keys}"
    assert len(setups) <= 1, f"expected <=1 setup (only first OB taken), got {len(setups)}"


# --------------------------------------------------------------------------- #
# 7. With ES bars — passes_smt may be True
# --------------------------------------------------------------------------- #


def test_detect_setups_with_es_bars():
    """When ES is provided and ES did NOT sweep its prior high while NQ did → SMT True."""
    nq_bars = _bullish_continuation_fixture()

    # ES bars: prior H1 (09:00) high = 200.0. Current H1 (10:00) high = 199.5 (NO sweep).
    # NQ swept prior 105.0 (current high = 107.5 > 105.0). So SMT divergence.
    es_prior = _h1_bars("2024-01-02 09:00", open_=199.0, high=200.0, low=198.0, close=199.5,
                         em_high_minute=50, em_low_minute=5)
    es_current = _h1_bars("2024-01-02 10:00", open_=199.5, high=199.5, low=199.0, close=199.4,
                            em_high_minute=20, em_low_minute=5)
    # Padding bars for ES (short window)
    base11 = pd.Timestamp("2024-01-02 11:00", tz="America/New_York")
    es_follow = []
    for i in range(0, 100):
        es_follow.append({
            "ts": base11 + pd.Timedelta(minutes=i),
            "open": 199.4, "high": 199.5, "low": 199.3, "close": 199.4, "volume": 10,
        })
    es_bars = _build_bars(es_prior + es_current + es_follow)

    setups = detect_setups(nq_bars, es_bars=es_bars)
    assert len(setups) == 1
    # SMT should be True because ES did not sweep its prior 200.0
    assert setups[0].passes_smt is True


# --------------------------------------------------------------------------- #
# 8. Without ES bars — passes_smt always False
# --------------------------------------------------------------------------- #


def test_detect_setups_without_es_bars():
    bars = _bullish_continuation_fixture()
    setups = detect_setups(bars, es_bars=None)
    for s in setups:
        assert s.passes_smt is False


# --------------------------------------------------------------------------- #
# 9. Lookahead audit — truncate at entry_ts and re-run; setup reappears
# --------------------------------------------------------------------------- #


def test_detect_setups_lookahead_audit():
    bars = _bullish_continuation_fixture()
    setups = detect_setups(bars)
    assert len(setups) >= 1
    for s in setups:
        truncated = bars[bars["ts"] <= s.entry_ts].reset_index(drop=True)
        re_setups = detect_setups(truncated)
        match = [r for r in re_setups if r.anchor_ts == s.anchor_ts and r.direction == s.direction]
        assert len(match) == 1, (
            f"causality bug: setup at {s.anchor_ts}/{s.direction} did not reappear "
            f"after truncation at {s.entry_ts}; got {len(match)} matches"
        )
        # Same entry_price / sl_price / tp_price
        m = match[0]
        assert m.entry_ts == s.entry_ts
        assert m.entry_price == s.entry_price
        assert m.sl_price == s.sl_price
        assert m.tp_price == s.tp_price


# --------------------------------------------------------------------------- #
# 10. All filter flags present
# --------------------------------------------------------------------------- #


def test_detect_setups_all_filter_flags_present():
    """For each emitted setup, all 10 passes_* flags must be REAL booleans."""
    bars = _bullish_continuation_fixture()
    setups = detect_setups(bars)
    assert len(setups) >= 1
    for s in setups:
        for flag in EXPECTED_FLAGS:
            assert hasattr(s, flag), f"setup missing {flag}"
            v = getattr(s, flag)
            assert v is not None, f"{flag} is None"
            assert isinstance(v, bool), f"{flag} is not bool: {type(v).__name__}"


# --------------------------------------------------------------------------- #
# 11. Dedup invariant on a fixture that COULD produce duplicates
# --------------------------------------------------------------------------- #


def test_detect_setups_dedup_invariant():
    """Construct a fixture where multiple patterns could fire; assert dedup holds."""
    # Use the same multi-OB fixture as no_duplicates above.
    prior = _h1_bars("2024-01-02 09:00", open_=100.0, high=105.0, low=99.0, close=104.0,
                      em_high_minute=50, em_low_minute=5)
    current = _h1_bars("2024-01-02 10:00", open_=104.0, high=107.5, low=103.0, close=107.0,
                        em_high_minute=55, em_low_minute=10)
    base11 = pd.Timestamp("2024-01-02 11:00", tz="America/New_York")
    # Many overlapping OB-like candles below draw=105.
    post = [
        {"ts": base11 + pd.Timedelta(minutes=0),
         "open": 104.8, "high": 104.9, "low": 104.0, "close": 104.3, "volume": 10},
        {"ts": base11 + pd.Timedelta(minutes=1),
         "open": 104.3, "high": 104.85, "low": 104.1, "close": 104.7, "volume": 10},
        {"ts": base11 + pd.Timedelta(minutes=2),
         "open": 104.7, "high": 105.0, "low": 104.5, "close": 104.9, "volume": 10},
        {"ts": base11 + pd.Timedelta(minutes=3),
         "open": 104.9, "high": 105.0, "low": 104.4, "close": 104.5, "volume": 10},
        {"ts": base11 + pd.Timedelta(minutes=4),
         "open": 104.5, "high": 104.95, "low": 104.45, "close": 104.8, "volume": 10},
        {"ts": base11 + pd.Timedelta(minutes=5),
         "open": 104.8, "high": 105.05, "low": 104.7, "close": 105.0, "volume": 10},
        {"ts": base11 + pd.Timedelta(minutes=6),
         "open": 105.0, "high": 105.1, "low": 104.9, "close": 105.05, "volume": 10},
        {"ts": base11 + pd.Timedelta(minutes=7),
         "open": 105.05, "high": 105.15, "low": 104.95, "close": 105.1, "volume": 10},
        {"ts": base11 + pd.Timedelta(minutes=8),
         "open": 105.1, "high": 105.2, "low": 105.0, "close": 105.15, "volume": 10},
        {"ts": base11 + pd.Timedelta(minutes=9),
         "open": 105.15, "high": 105.25, "low": 105.05, "close": 105.2, "volume": 10},
    ]
    follow = []
    for i in range(10, 200):
        follow.append({
            "ts": base11 + pd.Timedelta(minutes=i),
            "open": 105.2, "high": 106.0, "low": 105.0, "close": 105.7, "volume": 10,
        })
    bars = _build_bars(prior + current + post + follow)
    setups = detect_setups(bars)
    keys = [(s.anchor_ts, s.direction) for s in setups]
    assert len(keys) == len(set(keys)), f"dedup invariant violated! keys = {keys}"


# --------------------------------------------------------------------------- #
# 12. Models registry has h1_continuation
# --------------------------------------------------------------------------- #


def test_models_registry_has_h1_continuation():
    assert "h1_continuation" in MODELS
    md = MODELS["h1_continuation"]
    assert md.label == "H1 Continuation (Model 2 entry)"
    assert callable(md.detect)
    assert len(md.filters) == 10


# --------------------------------------------------------------------------- #
# 13. Filter keys match Setup field names (passes_<key> exists)
# --------------------------------------------------------------------------- #


def test_filter_keys_match_setup_field_names():
    md = MODELS["h1_continuation"]
    field_names = {f.name for f in dataclasses.fields(_H1ContinuationSetup)}
    for filt in md.filters:
        expected_field = f"passes_{filt.key}"
        assert expected_field in field_names, (
            f"Filter key {filt.key!r} does not map to a real field on _H1ContinuationSetup; "
            f"expected field name {expected_field!r}. Available: {sorted(field_names)}"
        )
