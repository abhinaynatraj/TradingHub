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
