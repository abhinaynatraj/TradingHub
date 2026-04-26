"""Tests for find_supporting_fvg — supporting FVG confluence detection."""
import numpy as np
import pytest

import model_stats as ms


def _arrs(bars):
    """Build a minimal arrs dict with just the OHLC fields find_supporting_fvg uses."""
    n = len(bars)
    return dict(
        open  = np.array([b[0] for b in bars], dtype='float64'),
        high  = np.array([b[1] for b in bars], dtype='float64'),
        low   = np.array([b[2] for b in bars], dtype='float64'),
        close = np.array([b[3] for b in bars], dtype='float64'),
    )


def test_bullish_strict_fvg_between_sl_and_entry():
    # 5 bars total. FVG forms at index 2 (3-bar pattern using bars 0,1,2).
    # bar 0 high = 100, bar 2 low = 105 → bullish FVG band (100, 105].
    # No subsequent bar dips below 100 → unfilled.
    bars = [
        # (open, high, low, close)
        (95, 100, 92, 99),   # 0 — defines lower edge (high=100)
        (99, 103, 98, 102),  # 1 — middle bar (irrelevant to gap)
        (102, 108, 105, 107),# 2 — defines upper edge (low=105) → FVG forms here
        (107, 110, 106, 109),# 3 — stays above 100, doesn't fill
        (109, 112, 108, 111),# 4 — entry bar (will not be inspected past entry_idx)
    ]
    arrs = _arrs(bars)
    # Long trade: sweep_extreme=98 (below the gap), entry_price=109 (above the gap).
    # Body of gap (100, 105] is fully between 98 and 109 → strict True, loose True.
    strict, loose = ms.find_supporting_fvg(
        arrs, window_start_idx=0, entry_idx=4,
        sweep_extreme=98.0, entry_price=109.0, direction='LONG',
    )
    assert strict is True
    assert loose is True


def test_bullish_loose_only_fvg_extends_below_sl():
    # Bullish FVG forms with bottom BELOW sweep_extreme=98 → loose True, strict False.
    # Bars 0 and 1 highs both kept at 97 (below SL=98) so neither i=2 nor i=3
    # candidate gap can satisfy strict.
    bars = [
        (95,  97, 92, 96),    # 0 — high=97 < SL=98
        (96,  97, 94, 96),    # 1 — high=97 < SL=98
        (96, 105,101,104),    # 2 — low=101 > high[0]=97 → bullish FVG (97, 101]
        (104,108,102,107),    # 3 — also forms FVG (97,102] with high[1]=97; both have bottom=97<98
        (107,110,106,109),    # 4 — entry; not scanned
    ]
    arrs = _arrs(bars)
    strict, loose = ms.find_supporting_fvg(
        arrs, window_start_idx=0, entry_idx=4,
        sweep_extreme=98.0, entry_price=109.0, direction='LONG',
    )
    assert strict is False  # all candidate gap bottoms (97) < sweep_extreme (98)
    assert loose is True    # gap tops (101, 102) <= entry (109)


def test_bullish_fvg_above_entry_both_false():
    # Gap forms ABOVE entry — not supporting. Both False.
    bars = [
        (95, 100, 92, 99),
        (99, 103, 98, 102),
        (102, 108, 105, 107),  # FVG (100, 105]
        (107, 110, 106, 109),
        (109, 112, 108, 111),  # entry
    ]
    arrs = _arrs(bars)
    # Entry below the gap → top (105) > entry (104) → loose False.
    strict, loose = ms.find_supporting_fvg(
        arrs, window_start_idx=0, entry_idx=4,
        sweep_extreme=98.0, entry_price=104.0, direction='LONG',
    )
    assert strict is False
    assert loose is False


def test_bullish_fvg_filled_before_entry_both_false():
    # FVG forms at bar 2, but bar 3 wicks into bottom of gap (low <= 100).
    # Should be treated as filled → both False.
    bars = [
        (95, 100, 92, 99),
        (99, 103, 98, 102),
        (102, 108, 105, 107),  # FVG (100, 105]
        (107, 110, 99, 109),   # low=99 <= 100 → fills the gap
        (109, 112, 108, 111),  # entry
    ]
    arrs = _arrs(bars)
    strict, loose = ms.find_supporting_fvg(
        arrs, window_start_idx=0, entry_idx=4,
        sweep_extreme=98.0, entry_price=111.0, direction='LONG',
    )
    assert strict is False
    assert loose is False


def test_bearish_fvg_does_not_count_for_long():
    # All bars contain a bearish 3-bar gap but no bullish gap. Long trade.
    bars = [
        (110, 112, 108, 109),  # 0 — low=108
        (109, 110, 106, 107),  # 1
        (107, 105, 102, 104),  # 2 — high=105 < low[0]=108 → bearish FVG (105, 108)
        (104, 105, 100, 102),
        (102, 104,  98, 100),  # entry below — but trade is LONG so wrong-side
    ]
    arrs = _arrs(bars)
    strict, loose = ms.find_supporting_fvg(
        arrs, window_start_idx=0, entry_idx=4,
        sweep_extreme=95.0, entry_price=102.0, direction='LONG',
    )
    assert strict is False
    assert loose is False


def test_bearish_strict_fvg_between_entry_and_sl_short():
    # SHORT trade: sweep_extreme is ABOVE entry (sweep of prior high).
    # Bearish FVG should sit with body fully inside [entry, sweep_extreme].
    bars = [
        (110, 112, 108, 109),  # 0 — low=108 → upper edge of bearish gap
        (109, 110, 106, 107),  # 1
        (107, 105, 102, 104),  # 2 — high=105 → lower edge. Bearish gap (105, 108)
        (104, 107, 102, 103),  # 3 — high=107 < 108 → does not fill
        (103, 105, 100, 102),  # 4 — entry
    ]
    arrs = _arrs(bars)
    # Short: sweep_extreme=110 (above), entry=102 (below). Gap (105, 108) is
    # fully inside [102, 110] → strict True, loose True.
    strict, loose = ms.find_supporting_fvg(
        arrs, window_start_idx=0, entry_idx=4,
        sweep_extreme=110.0, entry_price=102.0, direction='SHORT',
    )
    assert strict is True
    assert loose is True


def test_bearish_loose_only_short_extends_above_sl():
    # SHORT: bearish gap with top above sweep_extreme → strict False, loose True.
    bars = [
        (114, 116, 112, 113),  # 0 — low=112
        (113, 114, 110, 111),  # 1
        (111, 109, 106, 108),  # 2 — high=109 → bearish gap (109, 112)
        (108, 110, 106, 107),  # 3 — does not fill (max high in (i,entry)=110 < 112)
        (107, 109, 100, 102),  # 4 — entry
    ]
    arrs = _arrs(bars)
    # sweep_extreme=111 (below the top of gap=112) → strict False
    # gap bottom=109 >= entry=102 → loose True
    strict, loose = ms.find_supporting_fvg(
        arrs, window_start_idx=0, entry_idx=4,
        sweep_extreme=111.0, entry_price=102.0, direction='SHORT',
    )
    assert strict is False
    assert loose is True


def test_bearish_fvg_filled_before_entry_short():
    # SHORT bearish gap that gets filled (a later bar's high reaches the top).
    bars = [
        (114, 116, 112, 113),
        (113, 114, 110, 111),
        (111, 109, 106, 108),  # bearish gap (109, 112)
        (108, 113, 106, 110),  # high=113 >= 112 → fills the gap
        (110, 112, 100, 102),  # entry
    ]
    arrs = _arrs(bars)
    strict, loose = ms.find_supporting_fvg(
        arrs, window_start_idx=0, entry_idx=4,
        sweep_extreme=120.0, entry_price=102.0, direction='SHORT',
    )
    assert strict is False
    assert loose is False


def test_no_gap_in_window_both_false():
    # All consecutive bars overlap — no 3-bar gap exists.
    bars = [
        (100, 102,  99, 101),
        (101, 103, 100, 102),
        (102, 104, 101, 103),
        (103, 105, 102, 104),
        (104, 106, 103, 105),
    ]
    arrs = _arrs(bars)
    strict, loose = ms.find_supporting_fvg(
        arrs, window_start_idx=0, entry_idx=4,
        sweep_extreme=99.0, entry_price=105.0, direction='LONG',
    )
    assert strict is False
    assert loose is False


def test_window_too_small_returns_false():
    # entry_idx=2 means scan range [2, 2) — empty. Both False.
    bars = [
        (95, 100, 92, 99),
        (99, 103, 98, 102),
        (102, 108, 105, 107),
    ]
    arrs = _arrs(bars)
    strict, loose = ms.find_supporting_fvg(
        arrs, window_start_idx=0, entry_idx=2,
        sweep_extreme=98.0, entry_price=109.0, direction='LONG',
    )
    assert strict is False
    assert loose is False


def test_strict_implies_loose_invariant_random():
    # Property test: for any inputs the helper accepts, strict ⇒ loose.
    # Place sweep and entry INSIDE the bar range so that some candidate FVGs
    # satisfy loose but not strict — otherwise the strict band is so wide
    # that strict ≡ loose and the property is trivially true.
    rng = np.random.RandomState(7)
    long_loose_only_seen = False
    short_loose_only_seen = False
    for _ in range(200):
        n = 8
        opens  = rng.uniform(95, 110, n)
        closes = opens + rng.uniform(-2, 2, n)
        highs  = np.maximum(opens, closes) + rng.uniform(0, 2, n)
        lows   = np.minimum(opens, closes) - rng.uniform(0, 2, n)
        arrs = dict(open=opens, high=highs, low=lows, close=closes)

        # Random sweep / entry inside the range. For LONG, sweep < entry.
        a, b = sorted([float(rng.uniform(lows.min(), highs.max())),
                       float(rng.uniform(lows.min(), highs.max()))])
        long_sweep, long_entry = a, b
        s, l = ms.find_supporting_fvg(arrs, 0, n, long_sweep, long_entry, 'LONG')
        assert (not s) or l, "strict ⇒ loose violated for LONG"
        if l and not s:
            long_loose_only_seen = True

        # For SHORT, sweep > entry (sweep above price, entry below).
        short_sweep, short_entry = b, a
        s, l = ms.find_supporting_fvg(arrs, 0, n, short_sweep, short_entry, 'SHORT')
        assert (not s) or l, "strict ⇒ loose violated for SHORT"
        if l and not s:
            short_loose_only_seen = True

    # Coverage guards: if the construction never exercises the loose-but-not-
    # strict case, the property test is degenerate and should fail loudly.
    assert long_loose_only_seen,  "LONG: strict-false/loose-true case never exercised"
    assert short_loose_only_seen, "SHORT: strict-false/loose-true case never exercised"
