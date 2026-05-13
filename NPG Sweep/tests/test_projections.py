"""Tests for series_multi outcome resolution: 4 partial-exit projections + SL."""
import numpy as np
import pytest
from helpers import make_ltf_arrs, NS_PER_MIN, BASE_TS
import projections as p


class TestProjectionTargets:
    def test_compute_targets_bearish(self):
        """Bearish: targets = break_price − N × series_range."""
        targets = p.compute_targets(
            direction='SHORT', break_price=100.0, series_range=10.0,
            multipliers=[0.5, 1.0, 1.5, 2.0],
        )
        assert targets == [95.0, 90.0, 85.0, 80.0]

    def test_compute_targets_bullish(self):
        targets = p.compute_targets(
            direction='LONG', break_price=100.0, series_range=10.0,
            multipliers=[0.5, 1.0, 1.5, 2.0],
        )
        assert targets == [105.0, 110.0, 115.0, 120.0]


class TestResolveAllTargetsHit:
    def test_bearish_all_4_levels_reached(self):
        """SL above entry, price walks down hitting all 4 targets."""
        # entry_idx=0; entry=100, sl=110 (= sweep extreme), targets at 95/90/85/80
        # bars walk down through all targets without touching SL
        bars = [
            (100, 100, 100, 99),   # 0: entry bar, no target hit
            (99,  99,  94,  95),   # 1: hit 95 (low=94)
            (95,  95,  89,  90),   # 2: hit 90
            (90,  90,  84,  85),   # 3: hit 85
            (85,  85,  79,  80),   # 4: hit 80
        ]
        arrs = make_ltf_arrs(bars)
        outcome = p.resolve_series_multi(
            o=arrs['open'], h=arrs['high'], l=arrs['low'], c=arrs['close'],
            ts=arrs['ts_ns'], entry_idx=0, entry_price=100.0, sl_price=110.0,
            direction='SHORT', targets=[95.0, 90.0, 85.0, 80.0],
            max_bars=100,
        )
        assert outcome['hits'] == [True, True, True, True]
        assert outcome['sl_hit'] is False
        # Composite R: each leg = 25% × R_at_level. R_at_level = (entry-target)/risk_per_pt
        # risk_per_pt = entry - target / risk = (100-95)/10=0.5R, (100-90)/10=1.0R, (100-85)/10=1.5R, (100-80)/10=2.0R
        # composite_r = 0.25*(0.5+1.0+1.5+2.0) = 1.25
        assert outcome['composite_r'] == pytest.approx(1.25)

    def test_bullish_all_4_levels_reached(self):
        bars = [
            (100, 101, 100, 101),
            (101, 106, 100, 105),    # hit 105
            (105, 111, 105, 110),    # hit 110
            (110, 116, 110, 115),    # hit 115
            (115, 121, 115, 120),    # hit 120
        ]
        arrs = make_ltf_arrs(bars)
        outcome = p.resolve_series_multi(
            o=arrs['open'], h=arrs['high'], l=arrs['low'], c=arrs['close'],
            ts=arrs['ts_ns'], entry_idx=0, entry_price=100.0, sl_price=90.0,
            direction='LONG', targets=[105.0, 110.0, 115.0, 120.0],
            max_bars=100,
        )
        assert outcome['hits'] == [True, True, True, True]
        assert outcome['composite_r'] == pytest.approx(1.25)


class TestPartialFill:
    def test_bearish_first_two_targets_then_sl(self):
        """Hit 95 and 90, then price reverses to SL at 110."""
        bars = [
            (100, 100, 99, 99),
            (99,  99,  89, 90),   # hit 95 and 90 in same bar (low=89)
            (90, 110, 90, 109),   # SL hit (high>=110)
        ]
        arrs = make_ltf_arrs(bars)
        outcome = p.resolve_series_multi(
            o=arrs['open'], h=arrs['high'], l=arrs['low'], c=arrs['close'],
            ts=arrs['ts_ns'], entry_idx=0, entry_price=100.0, sl_price=110.0,
            direction='SHORT', targets=[95.0, 90.0, 85.0, 80.0],
            max_bars=100,
        )
        assert outcome['hits'] == [True, True, False, False]
        assert outcome['sl_hit'] is True
        # 25% × 0.5R + 25% × 1.0R + 50% × (-1.0R) = 0.125 + 0.25 - 0.5 = -0.125
        assert outcome['composite_r'] == pytest.approx(-0.125)

    def test_bearish_immediate_sl(self):
        bars = [
            (100, 110, 99, 109),    # SL hit immediately (high=110)
        ]
        arrs = make_ltf_arrs(bars)
        outcome = p.resolve_series_multi(
            o=arrs['open'], h=arrs['high'], l=arrs['low'], c=arrs['close'],
            ts=arrs['ts_ns'], entry_idx=0, entry_price=100.0, sl_price=110.0,
            direction='SHORT', targets=[95.0, 90.0, 85.0, 80.0],
            max_bars=100,
        )
        assert outcome['hits'] == [False, False, False, False]
        assert outcome['sl_hit'] is True
        assert outcome['composite_r'] == pytest.approx(-1.0)


class TestSameBarTie:
    def test_target_and_sl_same_bar_sl_wins(self):
        """When TP and SL are both touched in the same bar, SL wins (matches Fractal Sweep)."""
        # Bar has high=110 (SL) AND low=94 (target 95)
        bars = [
            (100, 110, 94, 100),
        ]
        arrs = make_ltf_arrs(bars)
        outcome = p.resolve_series_multi(
            o=arrs['open'], h=arrs['high'], l=arrs['low'], c=arrs['close'],
            ts=arrs['ts_ns'], entry_idx=0, entry_price=100.0, sl_price=110.0,
            direction='SHORT', targets=[95.0, 90.0, 85.0, 80.0],
            max_bars=100,
        )
        assert outcome['hits'] == [False, False, False, False]
        assert outcome['sl_hit'] is True


class TestRawMeasure:
    def test_records_mae_mfe_and_target_reach_flags(self):
        bars = [
            (100, 102, 99, 101),    # MFE=1 down (favorable=1 going up, adverse=2)
            (101, 105, 95, 96),     # mfe(SHORT) → 100-95=5, mae=5
            (96,  97,  88, 90),     # mfe → 12, mae unchanged
        ]
        arrs = make_ltf_arrs(bars)
        outcome = p.resolve_raw_measure(
            o=arrs['open'], h=arrs['high'], l=arrs['low'], c=arrs['close'],
            ts=arrs['ts_ns'], entry_idx=0, entry_price=100.0,
            direction='SHORT', targets=[95.0, 90.0, 85.0, 80.0],
            max_bars=100,
        )
        # MFE for SHORT = max(entry - bar_low) over all bars = 100 - 88 = 12
        # MAE for SHORT = max(bar_high - entry) = 105 - 100 = 5
        assert outcome['mfe_pts'] == 12.0
        assert outcome['mae_pts'] == 5.0
        # Target reach: 95 hit on bar 1, 90 hit on bar 2; 85, 80 not reached
        assert outcome['hits'] == [True, True, False, False]
