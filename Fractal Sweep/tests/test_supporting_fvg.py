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
