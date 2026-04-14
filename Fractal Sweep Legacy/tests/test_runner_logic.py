"""Tests for runner continuation logic in structural and split_tp resolution."""
import numpy as np
import pytest
from helpers import NS_PER_MIN, BASE_TS, make_controlled_m1
import model_stats as ms


def _run_structural(entry, sl, tp, direction, bars):
    """Helper to run structural resolution with given bars."""
    m1 = make_controlled_m1(bars, start_ts=BASE_TS)
    m1['hr'][:] = 9
    pending = [dict(
        idx=0, entry_ts_ns=int(BASE_TS + NS_PER_MIN),
        entry_price=entry, stop_price=sl, target_price=tp,
        direction=direction, sweep_extreme=sl,
        base_risk=abs(entry - sl), hour_range_pts=50.0,
    )]
    return ms.resolve_outcomes_structural(m1, pending)


def _run_split(entry, sl, tp, direction, bars, tp2_pct=None):
    """Helper to run split_tp resolution."""
    m1 = make_controlled_m1(bars, start_ts=BASE_TS)
    m1['hr'][:] = 9
    pending = [dict(
        idx=0, entry_ts_ns=int(BASE_TS + NS_PER_MIN),
        entry_price=entry, stop_price=sl, target_price=tp,
        direction=direction, sweep_extreme=sl,
        base_risk=abs(entry - sl), hour_range_pts=50.0,
    )]
    return ms.resolve_outcomes_split_tp(m1, pending,
                                         tp1_size=0.90, tp2_size=0.10,
                                         tp2_pct=tp2_pct)


class TestStructuralRunnerLong:
    def test_tp1_hit_runner_be_stop(self):
        """LONG: TP1 hit, runner drops to BE (entry) → runner_exit_r = 0."""
        bars = [
            (24000, 24010, 23995, 24005),   # entry bar
            (24005, 24055, 24000, 24052),   # hits TP1 (24050)
            (24052, 24055, 23999, 24000),   # runner drops to BE
            (24000, 24005, 23990, 23995),   # below entry
        ]
        results = _run_structural(24000, 23950, 24050, 'LONG', bars)
        assert results[0][0] == 'WIN'
        assert results[0][4] == True  # tp1_hit
        assert results[0][5] == 0.0   # runner at BE

    def test_tp1_hit_runner_continues_up(self):
        """LONG: TP1 hit, runner doesn't hit BE, exits at EOD."""
        bars = [
            (24000, 24010, 23995, 24005),
            (24005, 24055, 24000, 24052),   # hits TP1
            (24052, 24060, 24045, 24058),   # runner goes up
            (24058, 24065, 24050, 24062),   # still up
        ]
        results = _run_structural(24000, 23950, 24050, 'LONG', bars)
        assert results[0][0] == 'WIN'
        assert results[0][4] == True   # tp1_hit
        assert results[0][5] > 0       # runner positive (EOD above entry)


class TestStructuralRunnerShort:
    def test_short_tp1_hit_runner_be(self):
        """SHORT: TP1 hit below, runner rises to BE."""
        bars = [
            (24000, 24005, 23995, 23998),
            (23998, 24002, 23945, 23948),   # hits TP1 (23950)
            (23948, 24005, 23945, 24000),   # runner rises to BE (24000)
            (24000, 24010, 23995, 24005),
        ]
        results = _run_structural(24000, 24050, 23950, 'SHORT', bars)
        assert results[0][0] == 'WIN'
        assert results[0][4] == True
        assert results[0][5] == 0.0  # BE

    def test_short_tp1_hit_runner_continues_down(self):
        """SHORT: TP1 hit, runner keeps dropping."""
        bars = [
            (24000, 24005, 23995, 23998),
            (23998, 24002, 23945, 23948),   # hits TP1
            (23948, 23950, 23935, 23938),   # runner continues down
            (23938, 23940, 23925, 23930),
        ]
        results = _run_structural(24000, 24050, 23950, 'SHORT', bars)
        assert results[0][0] == 'WIN'
        assert results[0][4] == True
        assert results[0][5] > 0  # runner positive


class TestSplitTpRunnerWithTp2:
    def test_long_tp2_hit(self):
        """LONG split: TP1 hit, runner reaches TP2."""
        entry = 24000.0
        tp1 = 24030.0  # PTQ target
        sl = 23950.0
        # TP2 at 0.50% of entry = 24000 * 0.005 = 120 → TP2 at 24120
        bars = [
            (24000, 24010, 23995, 24005),
            (24005, 24035, 24000, 24032),   # hits TP1 (24030)
            (24032, 24060, 24025, 24055),   # runner continues
            (24055, 24125, 24050, 24120),   # hits TP2 (24120)
        ]
        results = _run_split(entry, sl, tp1, 'LONG', bars, tp2_pct=0.50)
        assert results[0][0] == 'WIN'
        assert results[0][4] == True   # tp1_hit
        assert results[0][5] > 0       # runner positive R

    def test_long_runner_be_before_tp2(self):
        """LONG split: TP1 hit, runner stopped at BE before TP2."""
        entry = 24000.0
        tp1 = 24030.0
        sl = 23950.0
        bars = [
            (24000, 24010, 23995, 24005),
            (24005, 24035, 24000, 24032),   # hits TP1
            (24032, 24035, 23998, 24000),   # drops to BE (24000)
            (24000, 24005, 23990, 23995),
        ]
        results = _run_split(entry, sl, tp1, 'LONG', bars, tp2_pct=0.50)
        assert results[0][0] == 'WIN'
        assert results[0][5] == 0.0  # BE stop

    def test_short_tp2_hit(self):
        """SHORT split: TP1 hit, runner reaches TP2 below."""
        entry = 24000.0
        tp1 = 23970.0
        sl = 24050.0
        # TP2 at 0.50% = 24000 * 0.005 = 120 → TP2 at 23880
        bars = [
            (24000, 24005, 23995, 23998),
            (23998, 24002, 23965, 23968),   # hits TP1 (23970)
            (23968, 23975, 23900, 23910),   # runner drops
            (23910, 23920, 23875, 23880),   # hits TP2 (23880)
        ]
        results = _run_split(entry, sl, tp1, 'SHORT', bars, tp2_pct=0.50)
        assert results[0][0] == 'WIN'
        assert results[0][4] == True
        assert results[0][5] > 0

    def test_neither_tp2_nor_be_hit(self):
        """Split: TP1 hit, neither TP2 nor BE → mark to market."""
        entry = 24000.0
        tp1 = 24030.0
        sl = 23950.0
        bars = [
            (24000, 24010, 23995, 24005),
            (24005, 24035, 24000, 24032),   # hits TP1
            (24032, 24040, 24025, 24035),   # stays between entry and TP2
            (24035, 24038, 24028, 24033),   # stays
        ]
        results = _run_split(entry, sl, tp1, 'LONG', bars, tp2_pct=2.0)  # TP2 very far
        assert results[0][0] == 'WIN'
        assert results[0][4] == True

    def test_legacy_no_tp2(self):
        """Split without tp2_pct: legacy runner with BE only (line 663-678)."""
        entry = 24000.0
        tp1 = 24030.0
        sl = 23950.0
        bars = [
            (24000, 24010, 23995, 24005),
            (24005, 24035, 24000, 24032),   # hits TP1
            (24032, 24040, 24025, 24035),   # runner, no BE hit
            (24035, 24038, 24028, 24033),
        ]
        results = _run_split(entry, sl, tp1, 'LONG', bars, tp2_pct=None)
        assert results[0][0] == 'WIN'
        assert results[0][4] == True
        # Without tp2_pct, runner exits at EOD mark-to-market
        assert results[0][5] >= 0  # should be positive (price above entry)
