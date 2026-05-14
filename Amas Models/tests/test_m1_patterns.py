"""Tests for engine.m1_patterns — M1 entry pattern detectors.

Per Task 3.1b, three pattern detectors operating on M1 bars:
- Order Block (OB)
- Breaker Block
- Inversion FVG

Correctness invariants tested here (per the task spec):
1. Causal: detectors only use bars[k] for k <= formed_ts.index
2. No duplicates: (formed_ts, entry_price) pairs unique within a kind+direction.
3. Half-open windows: empty / short slices return [].
4. No mutation: bars not modified in place.
5. Direction symmetry: a fixture mirrored around its mean produces a mirrored
   pattern set with the opposite direction.
"""
from __future__ import annotations

import pandas as pd
import pytest

from engine.m1_patterns import (
    M1Pattern,
    find_order_blocks,
    find_breakers,
    find_inversion_fvgs,
)


def _make_bars(rows, start_ts: str = "2024-01-02 10:00") -> pd.DataFrame:
    """rows is a list of (open, high, low, close) tuples, one per minute starting at start_ts."""
    if len(rows) == 0:
        df = pd.DataFrame({
            "ts": pd.Series(dtype="datetime64[ns, America/New_York]"),
            "open": pd.Series(dtype="float64"),
            "high": pd.Series(dtype="float64"),
            "low": pd.Series(dtype="float64"),
            "close": pd.Series(dtype="float64"),
            "volume": pd.Series(dtype="int64"),
        })
        return df
    base = pd.Timestamp(start_ts, tz="America/New_York")
    out = []
    for i, (o, h, l, c) in enumerate(rows):
        out.append({
            "ts": base + pd.Timedelta(minutes=i),
            "open": o, "high": h, "low": l, "close": c, "volume": 10,
        })
    df = pd.DataFrame(out)
    df["ts"] = df["ts"].astype("datetime64[ns, America/New_York]")
    df["volume"] = df["volume"].astype("int64")
    return df


def _mirror_bars(bars: pd.DataFrame) -> pd.DataFrame:
    """Flip OHLC vertically around the mean of (high.max() + low.min()) / 2.

    open <-> open (mirrored), high <-> low (swapped & mirrored), close mirrored.
    Returns a NEW DataFrame; original is untouched.
    """
    mid = (bars["high"].max() + bars["low"].min()) / 2.0
    out = bars.copy()
    new_open = 2 * mid - bars["open"]
    new_close = 2 * mid - bars["close"]
    new_high = 2 * mid - bars["low"]   # original low -> new high
    new_low = 2 * mid - bars["high"]   # original high -> new low
    out["open"] = new_open
    out["high"] = new_high
    out["low"] = new_low
    out["close"] = new_close
    return out


# --------------------------------------------------------------------------- #
# Order Block
# --------------------------------------------------------------------------- #


def test_order_block_long_basic():
    """bar 0: down-close. bar 1: up-close (doesn't yet break OB high). bar 2: makes the higher high."""
    bars = _make_bars([
        (101.0, 101.2, 100.0, 100.2),  # 0: down-close OB candidate (open=101.0, low=100.0, high=101.2)
        (100.2, 101.1, 100.1, 101.0),  # 1: up-close, high=101.1 (still <= OB_high=101.2), no violation
        (101.0, 102.0, 100.5, 101.9),  # 2: up-close, makes higher-high 102.0 > 101.2
    ])
    patterns = find_order_blocks(bars, "long")
    assert len(patterns) == 1, f"expected 1 long OB, got {len(patterns)}: {patterns}"
    p = patterns[0]
    assert p.kind == "OB"
    assert p.direction == "long"
    assert p.formed_ts == bars["ts"].iloc[2]
    assert p.entry_price == 101.0  # bar 0 open
    assert p.invalidation_price == 100.0  # bar 0 low


def test_order_block_long_invalidated_by_lower_low():
    """Candidate OB low is violated BEFORE structure breaks up — not an OB.

    Bar 1 has low=99.0 which is < OB low=100.0, AND bar 1's high=100.3 doesn't
    break OB high. So invalidation triggers first; bar 2's higher high doesn't
    save the pattern.
    """
    bars = _make_bars([
        (101.0, 101.2, 100.0, 100.2),  # 0: down-close OB candidate, low=100.0, high=101.2
        ( 99.5, 100.3,  99.0, 100.1),  # 1: up-close (NOT an OB itself); low=99.0 violates OB low
        (100.1, 100.5,  99.5, 100.4),  # 2: up-close; never makes higher-high above 101.2
    ])
    patterns = find_order_blocks(bars, "long")
    assert patterns == [], f"expected no long OB, got {patterns}"


def test_order_block_short_mirror():
    """Mirror of the basic long OB: up-close bar gets broken to the downside."""
    bars = _make_bars([
        (100.0, 101.0, 99.8, 100.8),   # 0: up-close OB candidate (open=100, high=101, low=99.8)
        (100.8, 100.9,  99.9, 100.0),  # 1: down-close, low=99.9 (still >= OB_low=99.8), no break
        (100.0, 100.1,  99.0,  99.1),  # 2: down-close, lower-low 99.0 < OB_low 99.8 → break
    ])
    patterns = find_order_blocks(bars, "short")
    assert len(patterns) == 1, f"expected 1 short OB, got {len(patterns)}"
    p = patterns[0]
    assert p.kind == "OB"
    assert p.direction == "short"
    assert p.formed_ts == bars["ts"].iloc[2]
    assert p.entry_price == 100.0  # bar 0 open
    assert p.invalidation_price == 101.0  # bar 0 high


# --------------------------------------------------------------------------- #
# Breaker
# --------------------------------------------------------------------------- #


def test_breaker_long_basic():
    """A short OB forms (up-close bar broken down), then is violated upward, then retests."""
    bars = _make_bars([
        # SHORT OB at index 0: up-close bar; indices 1-2 take a lower low.
        (100.0, 101.0, 99.8, 100.8),    # 0: up-close, OB_high=101.0, OB_low=99.8, OB_open=100.0
        (100.8, 100.9, 99.5, 99.6),     # 1: down-close, doesn't violate OB high
        ( 99.6,  99.7, 99.0, 99.1),     # 2: down-close, lower-low → short OB FORMED at i=2
        # Now the OB needs to be VIOLATED upward (close > OB_high = 101.0).
        ( 99.1, 102.0, 99.0, 101.5),    # 3: closes above 101.0 (OB broken upward)
        # Now retest from above (low <= OB_open = 100.0).
        (101.5, 101.6, 99.9, 100.5),    # 4: low 99.9 <= 100.0 → retest, BREAKER FORMED long at i=4
    ])
    patterns = find_breakers(bars, "long")
    assert len(patterns) == 1, f"expected 1 long breaker, got {len(patterns)}: {patterns}"
    p = patterns[0]
    assert p.kind == "BREAKER"
    assert p.direction == "long"
    assert p.formed_ts == bars["ts"].iloc[4]
    assert p.entry_price == 100.0   # OB open
    assert p.invalidation_price == 99.8  # OB low


def test_breaker_short_mirror():
    """Mirror: a long OB forms, gets violated downward, then retests from below."""
    bars = _make_bars([
        # LONG OB at index 0: down-close bar; indices 1-2 take a higher high.
        (101.0, 101.2, 100.0, 100.2),  # 0: down-close, OB_low=100.0, OB_high=101.2, OB_open=101.0
        (100.2, 101.5, 100.1, 101.4),  # 1: up-close
        (101.4, 102.0, 101.3, 101.9),  # 2: up-close, higher-high → long OB formed at i=2
        # Now OB violated downward (close < OB_low = 100.0).
        (101.9, 102.0,  99.0,  99.5),  # 3: closes below 100.0 → OB broken downward
        # Now retest from below (high >= OB_open = 101.0).
        ( 99.5, 101.1, 99.4, 100.5),   # 4: high 101.1 >= 101.0 → BREAKER FORMED short at i=4
    ])
    patterns = find_breakers(bars, "short")
    assert len(patterns) == 1, f"expected 1 short breaker, got {len(patterns)}"
    p = patterns[0]
    assert p.kind == "BREAKER"
    assert p.direction == "short"
    assert p.formed_ts == bars["ts"].iloc[4]
    assert p.entry_price == 101.0  # OB open
    assert p.invalidation_price == 101.2  # OB high


# --------------------------------------------------------------------------- #
# Inversion FVG
# --------------------------------------------------------------------------- #


def test_inversion_fvg_long_basic():
    """Bearish 3-bar FVG (bar 0.low > bar 2.high), then violation upward, then retest."""
    bars = _make_bars([
        # Bearish FVG: bars 0,1,2; bar0.low > bar2.high
        (105.0, 105.5, 104.0, 104.2),  # 0: low=104.0
        (104.2, 104.3, 102.5, 102.8),  # 1: middle bar
        (102.8, 103.0, 101.5, 101.8),  # 2: high=103.0; gap = [103.0, 104.0]
        # Now violate the FVG upward: close > bar0.low (104.0).
        (101.8, 105.0, 101.7, 104.5),  # 3: close 104.5 > 104.0 → inversion confirmed
        # Now retest from above: low <= bar2.high (103.0).
        (104.5, 104.6, 102.9, 103.5),  # 4: low 102.9 <= 103.0 → INV_FVG long FORMED at i=4
    ])
    patterns = find_inversion_fvgs(bars, "long")
    assert len(patterns) == 1, f"expected 1 long INV_FVG, got {len(patterns)}: {patterns}"
    p = patterns[0]
    assert p.kind == "INV_FVG"
    assert p.direction == "long"
    assert p.formed_ts == bars["ts"].iloc[4]
    assert p.entry_price == 104.0   # bars[0].low (upper edge of original bearish FVG)
    assert p.invalidation_price == 103.0  # bars[2].high (lower edge of original FVG)


def test_inversion_fvg_short_mirror():
    """Bullish 3-bar FVG (bar 0.high < bar 2.low), then violation downward, then retest."""
    bars = _make_bars([
        # Bullish FVG: bar0.high < bar2.low
        (101.0, 101.5, 100.5, 101.2),  # 0: high=101.5
        (101.2, 102.5, 101.1, 102.4),  # 1: middle bar
        (102.4, 103.5, 102.6, 103.4),  # 2: low=102.6; gap = [101.5, 102.6]
        # Violate downward: close < bar0.high (101.5).
        (103.4, 103.5, 100.5, 101.0),  # 3: close 101.0 < 101.5 → inversion confirmed
        # Retest from below: high >= bar2.low (102.6).
        (101.0, 102.7, 100.8, 102.0),  # 4: high 102.7 >= 102.6 → INV_FVG short FORMED at i=4
    ])
    patterns = find_inversion_fvgs(bars, "short")
    assert len(patterns) == 1, f"expected 1 short INV_FVG, got {len(patterns)}: {patterns}"
    p = patterns[0]
    assert p.kind == "INV_FVG"
    assert p.direction == "short"
    assert p.formed_ts == bars["ts"].iloc[4]
    assert p.entry_price == 101.5  # bars[0].high
    assert p.invalidation_price == 102.6  # bars[2].low


# --------------------------------------------------------------------------- #
# Edge cases
# --------------------------------------------------------------------------- #


def test_no_pattern_in_chop():
    """Flat OHLC (every bar identical) → no pattern of any kind, either direction."""
    bars = _make_bars([(100.0, 100.0, 100.0, 100.0)] * 20)
    for d in ("long", "short"):
        assert find_order_blocks(bars, d) == []
        assert find_breakers(bars, d) == []
        assert find_inversion_fvgs(bars, d) == []


def test_empty_bars_returns_empty():
    bars = _make_bars([])
    for d in ("long", "short"):
        assert find_order_blocks(bars, d) == []
        assert find_breakers(bars, d) == []
        assert find_inversion_fvgs(bars, d) == []


def test_short_bars_returns_empty():
    """Fewer than 3 bars: FVG (which needs at least 3) returns []. OB / Breaker need
    at least 2 bars to even consider a pattern; with 2 bars no pattern can form
    because a HH/LL strictly after the OB candle requires bar j > i+0 within slice."""
    bars = _make_bars([(100.0, 100.5, 99.5, 100.2), (100.2, 100.6, 99.4, 99.9)])
    for d in ("long", "short"):
        assert find_inversion_fvgs(bars, d) == []
    # 1-bar slice
    bars1 = _make_bars([(100.0, 100.5, 99.5, 100.2)])
    for d in ("long", "short"):
        assert find_order_blocks(bars1, d) == []
        assert find_breakers(bars1, d) == []
        assert find_inversion_fvgs(bars1, d) == []


def test_no_duplicates():
    """For each detector, no (formed_ts, entry_price) repeats within a single direction."""
    # Use a richer fixture that may produce overlapping patterns
    bars = _make_bars([
        (101.0, 101.2, 100.0, 100.2),  # OB candidate
        (100.2, 101.5, 100.1, 101.4),
        (101.4, 102.0, 101.3, 101.9),  # higher high
        (101.9, 103.0, 101.8, 102.9),  # higher highs continue
        (102.9, 104.0, 102.8, 103.9),
        (103.9, 105.0, 103.8, 104.9),
    ])
    for d in ("long", "short"):
        for finder in (find_order_blocks, find_breakers, find_inversion_fvgs):
            patterns = finder(bars, d)
            keys = [(p.formed_ts, p.entry_price) for p in patterns]
            assert len(keys) == len(set(keys)), f"duplicates in {finder.__name__}({d}): {keys}"


def test_no_lookahead_per_pattern():
    """Truncating bars at p.formed_ts (inclusive) must reproduce the same pattern.

    If a pattern depends on bars after its formed_ts to be detected, that's a lookahead bug.
    """
    bars = _make_bars([
        (101.0, 101.2, 100.0, 100.2),
        (100.2, 101.5, 100.1, 101.4),
        (101.4, 102.0, 101.3, 101.9),
        # extra bars after the OB pattern is formed — should not influence detection of it
        (101.9, 103.0, 101.8, 102.9),
        (102.9, 104.0, 102.8, 103.9),
    ])
    patterns = find_order_blocks(bars, "long")
    assert len(patterns) >= 1
    for p in patterns:
        truncated = bars[bars["ts"] <= p.formed_ts].reset_index(drop=True)
        truncated_patterns = find_order_blocks(truncated, "long")
        # The pattern must reappear in the truncated detection.
        keys = [(q.formed_ts, q.entry_price) for q in truncated_patterns]
        assert (p.formed_ts, p.entry_price) in keys, (
            f"OB pattern {p} disappears when bars truncated to its formed_ts"
        )


def test_no_lookahead_breakers():
    bars = _make_bars([
        (100.0, 101.0, 99.8, 100.8),
        (100.8, 100.9, 99.5, 99.6),
        ( 99.6,  99.7, 99.0, 99.1),
        ( 99.1, 102.0, 99.0, 101.5),
        (101.5, 101.6, 99.9, 100.5),
        (100.5, 102.0, 100.4, 101.5),
    ])
    patterns = find_breakers(bars, "long")
    assert len(patterns) >= 1
    for p in patterns:
        truncated = bars[bars["ts"] <= p.formed_ts].reset_index(drop=True)
        keys = [(q.formed_ts, q.entry_price) for q in find_breakers(truncated, "long")]
        assert (p.formed_ts, p.entry_price) in keys


def test_no_lookahead_inversion_fvgs():
    bars = _make_bars([
        (105.0, 105.5, 104.0, 104.2),
        (104.2, 104.3, 102.5, 102.8),
        (102.8, 103.0, 101.5, 101.8),
        (101.8, 105.0, 101.7, 104.5),
        (104.5, 104.6, 102.9, 103.5),
        (103.5, 104.0, 103.0, 103.8),
    ])
    patterns = find_inversion_fvgs(bars, "long")
    assert len(patterns) >= 1
    for p in patterns:
        truncated = bars[bars["ts"] <= p.formed_ts].reset_index(drop=True)
        keys = [(q.formed_ts, q.entry_price) for q in find_inversion_fvgs(truncated, "long")]
        assert (p.formed_ts, p.entry_price) in keys


def test_direction_symmetry_order_blocks():
    """Mirroring a long-favorable fixture must yield the same number of short OBs."""
    bars = _make_bars([
        (101.0, 101.2, 100.0, 100.2),
        (100.2, 101.5, 100.1, 101.4),
        (101.4, 102.0, 101.3, 101.9),
        (101.9, 103.0, 101.8, 102.9),
    ])
    long_patterns = find_order_blocks(bars, "long")
    assert len(long_patterns) >= 1

    mirrored = _mirror_bars(bars)
    short_patterns = find_order_blocks(mirrored, "short")

    assert len(long_patterns) == len(short_patterns), (
        f"long={len(long_patterns)} vs short(mirrored)={len(short_patterns)}"
    )
    # The formed_ts values should also match (timestamps are unchanged by mirroring).
    long_ts = sorted(p.formed_ts for p in long_patterns)
    short_ts = sorted(p.formed_ts for p in short_patterns)
    assert long_ts == short_ts


def test_direction_symmetry_breakers():
    bars = _make_bars([
        (100.0, 101.0, 99.8, 100.8),
        (100.8, 100.9, 99.5, 99.6),
        ( 99.6,  99.7, 99.0, 99.1),
        ( 99.1, 102.0, 99.0, 101.5),
        (101.5, 101.6, 99.9, 100.5),
    ])
    long_patterns = find_breakers(bars, "long")
    assert len(long_patterns) >= 1

    mirrored = _mirror_bars(bars)
    short_patterns = find_breakers(mirrored, "short")
    assert len(long_patterns) == len(short_patterns)
    long_ts = sorted(p.formed_ts for p in long_patterns)
    short_ts = sorted(p.formed_ts for p in short_patterns)
    assert long_ts == short_ts


def test_direction_symmetry_inversion_fvgs():
    bars = _make_bars([
        (105.0, 105.5, 104.0, 104.2),
        (104.2, 104.3, 102.5, 102.8),
        (102.8, 103.0, 101.5, 101.8),
        (101.8, 105.0, 101.7, 104.5),
        (104.5, 104.6, 102.9, 103.5),
    ])
    long_patterns = find_inversion_fvgs(bars, "long")
    assert len(long_patterns) >= 1

    mirrored = _mirror_bars(bars)
    short_patterns = find_inversion_fvgs(mirrored, "short")
    assert len(long_patterns) == len(short_patterns)
    long_ts = sorted(p.formed_ts for p in long_patterns)
    short_ts = sorted(p.formed_ts for p in short_patterns)
    assert long_ts == short_ts


def test_no_mutation_of_input():
    bars = _make_bars([
        (101.0, 101.2, 100.0, 100.2),
        (100.2, 101.5, 100.1, 101.4),
        (101.4, 102.0, 101.3, 101.9),
    ])
    snapshot = bars.copy(deep=True)
    find_order_blocks(bars, "long")
    find_breakers(bars, "long")
    find_inversion_fvgs(bars, "long")
    pd.testing.assert_frame_equal(bars, snapshot)


def test_patterns_are_sorted_by_formed_ts():
    """Returned patterns must be sorted ascending by formed_ts."""
    bars = _make_bars([
        (101.0, 101.2, 100.0, 100.2),
        (100.2, 101.5, 100.1, 101.4),
        (101.4, 102.0, 101.3, 101.9),
        (101.9, 103.0, 101.8, 102.9),
        (102.9, 104.0, 102.8, 103.9),
    ])
    for finder in (find_order_blocks, find_breakers, find_inversion_fvgs):
        for d in ("long", "short"):
            patterns = finder(bars, d)
            ts = [p.formed_ts for p in patterns]
            assert ts == sorted(ts), f"{finder.__name__}({d}) not sorted by formed_ts: {ts}"
