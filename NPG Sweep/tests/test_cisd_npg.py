"""Tests for npg CISD: opposing-candle-series with body or wick extremes,
broken by an opposing close. Max series length = 20 bars."""
import numpy as np
import pytest
from helpers import make_oc_arrs, BASE_TS, NS_PER_MIN
import cisd_npg as cn


class TestBackwardSeriesScan:
    def test_three_bullish_run_before_bearish_setup(self):
        """For a bearish setup, walk back from c2_bar collecting bullish candles
        until a bearish (same-direction) candle ends the run."""
        # Bars: [bearish, bullish, bullish, bullish (= the c2 sweep candle, treated
        # as part of opposing series since the sweep itself is the highest leg)]
        # In npg source: series starts AT c2_bar and walks backward, so c2_bar
        # is included. Series ends when a bullish candle (for bearish setup)
        # is followed by a bearish one going backward.
        #
        # We model: c2_bar = 3 (the sweep candle, bullish close).
        # Walking backward: bar 3 bullish, bar 2 bullish, bar 1 bullish,
        # bar 0 bearish → series = bars [1,2,3], series_low = min body low.
        bars = [
            (100, 99),   # 0: bearish — STOPS the backward walk
            (99, 102),   # 1: bullish (earliest in series)
            (102, 104),  # 2: bullish
            (104, 107),  # 3: bullish (c2_bar, the sweep candle for bearish setup)
            (107, 105),  # 4: forward bar — close > series_low?
        ]
        arrs = make_oc_arrs(bars, tf_min=5)
        result = cn.find_cisd_npg(
            o=arrs['open'], c=arrs['close'], h=arrs['high'], l=arrs['low'],
            ts=arrs['ts_ns'], c2_idx=3, direction='SHORT', body_confirm=True,
            max_series=20, max_forward=100,
        )
        # Series bodies: min(o,c) → bars 1,2,3 → 99, 102, 104 → series_low = 99
        # Bar 4 close = 105, NOT < 99 → no fire on bar 4
        # Need a bar with close < 99
        assert result is None  # no break yet

    def test_break_below_series_low_fires(self):
        bars = [
            (100, 99),    # 0: bearish — stops backward walk
            (99, 102),    # 1: bullish
            (102, 104),   # 2: bullish
            (104, 107),   # 3: bullish (c2_bar)
            (107, 100),   # 4: bearish, close 100 > 99
            (100, 95),    # 5: bearish, close 95 < 99 → FIRE
        ]
        arrs = make_oc_arrs(bars, tf_min=5)
        result = cn.find_cisd_npg(
            o=arrs['open'], c=arrs['close'], h=arrs['high'], l=arrs['low'],
            ts=arrs['ts_ns'], c2_idx=3, direction='SHORT', body_confirm=True,
            max_series=20, max_forward=100,
        )
        assert result is not None
        assert result['fire_idx'] == 5
        assert result['series_high'] == 107.0      # max of (max(o,c)) over bars 1,2,3
        assert result['series_low'] == 99.0        # min of (min(o,c)) over bars 1,2,3
        assert result['series_range'] == 8.0
        assert result['fire_ts_ns'] == arrs['ts_ns'][5]
        assert result['series_extreme_broken'] == 99.0  # series_low (what was crossed)

    def test_max_series_cap_at_20(self):
        # 25 consecutive bullish bars; series should cap at 20 going backward
        bars = [(100 + i, 100 + i + 1) for i in range(25)]   # all bullish
        # Add a forward break bar at the end that closes BELOW series_low
        # Series: indices 5..24, min(o,c) = 100+5 = 105 → series_low = 105.
        bars.append((125, 100))   # close 100 < 105 → fire
        arrs = make_oc_arrs(bars, tf_min=5)
        result = cn.find_cisd_npg(
            o=arrs['open'], c=arrs['close'], h=arrs['high'], l=arrs['low'],
            ts=arrs['ts_ns'], c2_idx=24, direction='SHORT', body_confirm=True,
            max_series=20, max_forward=100,
        )
        assert result is not None
        # Series bars: indices 5..24 (20 bars). bars[i] = (100+i, 100+i+1).
        # max(o,c) = 100+i+1, min(o,c) = 100+i.
        # series_high = 100+24+1 = 125, series_low = 100+5 = 105
        assert result['series_high'] == 125.0
        assert result['series_low'] == 105.0
        assert result['fire_idx'] == 25


class TestWickConfirmation:
    def test_body_confirm_false_uses_wick(self):
        # When body_confirm=False, series extremes use high/low not max/min(o,c)
        # Series bars 1,2: body lows = 99 (bar 1), 102 (bar 2). Wick lows (from
        # make_oc_arrs: low = min(o,c) - 1) = 98 (bar 1), 101 (bar 2).
        # So body series_low = 99, wick series_low = 98.
        # Forward bar that fires on body (close < 99) but not wick (close >= 98):
        # Use close = 98.5.
        bars = [
            (100, 99),     # 0: bearish (stops walk)
            (99, 102),     # 1: bullish, body low=99, wick low=98
            (102, 107),    # 2: bullish, body low=102, wick low=101 (c2_bar)
            (107, 98.5),   # 3: forward bar — close 98.5 < 99 (body) but not < 98 (wick)
        ]
        arrs = make_oc_arrs(bars, tf_min=5)

        # body_confirm=True → series_low=99, fires (98.5 < 99)
        r_body = cn.find_cisd_npg(
            o=arrs['open'], c=arrs['close'], h=arrs['high'], l=arrs['low'],
            ts=arrs['ts_ns'], c2_idx=2, direction='SHORT', body_confirm=True,
            max_series=20, max_forward=100,
        )
        assert r_body is not None
        assert r_body['fire_idx'] == 3

        # body_confirm=False (use wick lows) → series_low=98, no fire (98.5 not < 98)
        r_wick = cn.find_cisd_npg(
            o=arrs['open'], c=arrs['close'], h=arrs['high'], l=arrs['low'],
            ts=arrs['ts_ns'], c2_idx=2, direction='SHORT', body_confirm=False,
            max_series=20, max_forward=100,
        )
        assert r_wick is None


class TestNoSeries:
    def test_c2_bar_followed_by_same_direction_breaks_immediately(self):
        # If the bar BEFORE c2_bar is same-direction (bearish for SHORT setup),
        # series consists of just c2_bar
        bars = [
            (100, 99),     # 0: bearish (same direction as setup → ends walk)
            (99, 105),     # 1: bullish (c2_bar)
            (105, 95),     # 2: bearish, close 95 < 99 → FIRE
        ]
        arrs = make_oc_arrs(bars, tf_min=5)
        result = cn.find_cisd_npg(
            o=arrs['open'], c=arrs['close'], h=arrs['high'], l=arrs['low'],
            ts=arrs['ts_ns'], c2_idx=1, direction='SHORT', body_confirm=True,
            max_series=20, max_forward=100,
        )
        assert result is not None
        assert result['series_high'] == 105.0   # just c2_bar's body high
        assert result['series_low'] == 99.0     # just c2_bar's body low


class TestAnchorWindow:
    def test_cisd_outside_anchor_window_rejected(self):
        """If the CISD fire bar's timestamp is past anchor_close_ts, reject."""
        bars = [
            (100, 99),    # 0: bearish (stops walk)
            (99, 105),    # 1: bullish (c2_bar)
            (105, 95),    # 2: bearish, close 95 < 99 → would fire
        ]
        arrs = make_oc_arrs(bars, tf_min=5)
        # Set anchor_close_ts BEFORE bar 2's timestamp → reject
        anchor_close_ts = int(arrs['ts_ns'][1])  # equals bar 1's ts
        result = cn.find_cisd_npg_in_window(
            o=arrs['open'], c=arrs['close'], h=arrs['high'], l=arrs['low'],
            ts=arrs['ts_ns'], c2_idx=1, direction='SHORT', body_confirm=True,
            max_series=20, anchor_close_ts=anchor_close_ts,
        )
        assert result is None

    def test_cisd_within_anchor_window_accepted(self):
        bars = [
            (100, 99),
            (99, 105),
            (105, 95),
        ]
        arrs = make_oc_arrs(bars, tf_min=5)
        anchor_close_ts = int(arrs['ts_ns'][2]) + 60_000_000_000  # well after bar 2
        result = cn.find_cisd_npg_in_window(
            o=arrs['open'], c=arrs['close'], h=arrs['high'], l=arrs['low'],
            ts=arrs['ts_ns'], c2_idx=1, direction='SHORT', body_confirm=True,
            max_series=20, anchor_close_ts=anchor_close_ts,
        )
        assert result is not None
        assert result['fire_idx'] == 2
