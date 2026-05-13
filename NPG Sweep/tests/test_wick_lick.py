"""Tests for Wick Lick detection (bearish + bullish + double-sweep exclusion)."""
import numpy as np
import pytest
from helpers import make_htf_arrs, NS_PER_MIN, BASE_TS
import wick_lick as wl


class TestBearishWickLick:
    def test_basic_bearish_sweep_close_back_inside(self):
        """prev high = 100, current high = 105 (sweep), close = 99 (back inside) → bearish."""
        # Candles: (open, high, low, close)
        candles = [
            (95,  100, 90,  98),   # 0: prior candle, high=100
            (98,  105, 96,  99),   # 1: sweep candle: high>prev.high, close<prev.high
        ]
        arrs = make_htf_arrs(candles, tf_min=60)
        events = wl.detect_wick_licks(arrs)
        assert len(events) == 1
        e = events[0]
        assert e['direction'] == 'SHORT'
        assert e['sweep_extreme'] == 105.0      # the swept high (= sweep candle high)
        assert e['prev_extreme'] == 100.0       # the prior candle's high that was swept
        assert e['sweep_idx'] == 1              # index of the sweep candle in HTF arrays

    def test_no_sweep_no_event(self):
        """Current high < prev high → no Wick Lick."""
        candles = [
            (95,  100, 90,  98),
            (98,  99,  96,  97),
        ]
        events = wl.detect_wick_licks(make_htf_arrs(candles))
        assert events == []

    def test_swept_but_closed_above_prev_high_no_event(self):
        """Swept and closed beyond — full breakout, not a Wick Lick."""
        candles = [
            (95,  100, 90,  98),
            (98,  105, 96, 103),    # close > prev.high → no rejection
        ]
        events = wl.detect_wick_licks(make_htf_arrs(candles))
        assert events == []


class TestBullishWickLick:
    def test_basic_bullish_sweep_close_back_inside(self):
        # prev: high=110, low=100; sweep candle: high=109 (no high sweep), low=95<100, close=102>100 → bullish WL
        candles = [
            (105, 110, 100, 108),   # 0: prior, low=100
            (108, 109, 95,  102),   # 1: low<prev.low, close>prev.low, high<prev.high → bullish WL
        ]
        arrs = make_htf_arrs(candles)
        events = wl.detect_wick_licks(arrs)
        assert len(events) == 1
        e = events[0]
        assert e['direction'] == 'LONG'
        assert e['sweep_extreme'] == 95.0
        assert e['prev_extreme'] == 100.0
        assert e['sweep_idx'] == 1


class TestDoubleSweepExclusion:
    def test_swept_both_extremes_excluded(self):
        """Double-sweep candle: swept high AND low, closed inside prev range → excluded."""
        candles = [
            (95, 100, 90,  98),         # prev: range [90, 100]
            (98, 105, 85,  95),         # sweep both: h>100, l<90, c=95 in (90,100)
        ]
        events = wl.detect_wick_licks(make_htf_arrs(candles))
        assert events == []


class TestMultipleEvents:
    def test_two_setups_in_sequence(self):
        # Candle 1 bearish WL: high=105>100, close=99<100. prev_low stays 90.
        # Candle 2: high=104<105, low=97>90 — neither extreme swept → no event.
        # Candle 3 bullish WL: low=89<90 (prev low of candle 2=97... wait)
        # Use explicit prev extremes: c2 low=97; c3 sweeps low=89<97, close=101>97 → LONG.
        candles = [
            (95,  100, 90,  98),     # 0: baseline; high=100, low=90
            (98,  105, 97,  99),     # 1: bearish WL: h=105>100, c=99<100 (event 1 SHORT)
            (99,  104, 98, 100),     # 2: h=104<105, l=98>97 → no event
            (100, 103, 89, 101),     # 3: bullish WL: l=89<98 (prev low), c=101>98 (event 2 LONG)
        ]
        events = wl.detect_wick_licks(make_htf_arrs(candles))
        assert len(events) == 2
        assert events[0]['direction'] == 'SHORT'
        assert events[1]['direction'] == 'LONG'
