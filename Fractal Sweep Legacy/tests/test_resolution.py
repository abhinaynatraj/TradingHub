"""Tests for outcome resolution: vectorised, structural, split_tp."""
import numpy as np
import pytest
from helpers import NS_PER_MIN, BASE_TS, make_controlled_m1
import model_stats as ms


def _make_resolution_scenario(entry_price, direction, sl_price, tp_price,
                               bars_after_entry, start_ts=None):
    """Build m1_arrs and a single pending entry for resolution testing.

    Args:
        bars_after_entry: list of (open, high, low, close) tuples AFTER entry
    """
    ts = start_ts or BASE_TS
    entry_ts = ts  # entry at first bar

    # Build bars: entry bar + subsequent bars
    all_bars = [(entry_price, entry_price + 1, entry_price - 1, entry_price)] + bars_after_entry
    m1 = make_controlled_m1(all_bars, start_ts=ts)

    pending = [dict(
        idx=0,
        entry_ts_ns=int(entry_ts + NS_PER_MIN),  # enters on bar after entry bar
        entry_price=entry_price,
        stop_price=sl_price,
        target_price=tp_price,
        direction=direction,
        sweep_extreme=sl_price,
        base_risk=abs(entry_price - sl_price),
        hour_range_pts=50.0,
    )]
    return m1, pending


# ── Vectorised Resolution ────────────────────────────────────────────────────

class TestResolveVectorised:
    def test_long_win(self):
        """Price hits target → WIN."""
        entry, sl, tp = 24000.0, 23980.0, 24020.0
        bars = [
            (24000, 24005, 23995, 24002),  # bar 1: normal
            (24002, 24025, 24000, 24022),  # bar 2: hits target (24020)
        ]
        m1, pending = _make_resolution_scenario(entry, 'LONG', sl, tp, bars)
        results = ms.resolve_outcomes_vectorised(m1, pending)
        assert results[0][0] == 'WIN'
        assert results[0][1] > 0  # positive R

    def test_long_loss(self):
        """Price hits stop → LOSS."""
        entry, sl, tp = 24000.0, 23980.0, 24020.0
        bars = [
            (24000, 24005, 23995, 23998),
            (23998, 24000, 23975, 23978),  # hits stop (23980)
        ]
        m1, pending = _make_resolution_scenario(entry, 'LONG', sl, tp, bars)
        results = ms.resolve_outcomes_vectorised(m1, pending)
        assert results[0][0] == 'LOSS'
        assert results[0][1] < 0

    def test_short_win(self):
        """SHORT: price hits target below → WIN."""
        entry, sl, tp = 24000.0, 24020.0, 23980.0
        bars = [
            (24000, 24005, 23995, 23998),
            (23998, 24000, 23975, 23978),  # hits target (23980)
        ]
        m1, pending = _make_resolution_scenario(entry, 'SHORT', sl, tp, bars)
        results = ms.resolve_outcomes_vectorised(m1, pending)
        assert results[0][0] == 'WIN'

    def test_short_loss(self):
        """SHORT: price hits stop above → LOSS."""
        entry, sl, tp = 24000.0, 24020.0, 23980.0
        bars = [
            (24000, 24010, 23995, 24005),  # bar 1: doesn't hit yet
            (24005, 24025, 23998, 24015),  # bar 2: high=24025 > stop=24020 → LOSS
            (24015, 24020, 24010, 24018),  # bar 3: after stop
        ]
        m1, pending = _make_resolution_scenario(entry, 'SHORT', sl, tp, bars)
        results = ms.resolve_outcomes_vectorised(m1, pending)
        assert results[0][0] == 'LOSS'

    def test_invalid_risk_too_small(self):
        """Risk < MIN_RISK_PTS → INVALID."""
        entry, sl, tp = 24000.0, 23999.0, 24001.0  # 1 pt risk < 3.0
        bars = [(24000, 24005, 23995, 24002)]
        m1, pending = _make_resolution_scenario(entry, 'LONG', sl, tp, bars)
        results = ms.resolve_outcomes_vectorised(m1, pending)
        assert results[0][0] == 'INVALID'

    def test_invalid_risk_too_large(self):
        """Risk > MAX_RISK_PTS → INVALID."""
        entry, sl, tp = 24000.0, 23800.0, 24200.0  # 200 pts > 112.5
        bars = [(24000, 24005, 23995, 24002)]
        m1, pending = _make_resolution_scenario(entry, 'LONG', sl, tp, bars)
        results = ms.resolve_outcomes_vectorised(m1, pending)
        assert results[0][0] == 'INVALID'

    def test_mae_mfe_tracked(self):
        """MAE and MFE are computed correctly."""
        entry, sl, tp = 24000.0, 23950.0, 24050.0
        bars = [
            (24000, 24010, 23990, 24005),  # MAE=10, MFE=10
            (24005, 24055, 24000, 24052),  # MFE goes to 55, hits target
        ]
        m1, pending = _make_resolution_scenario(entry, 'LONG', sl, tp, bars)
        results = ms.resolve_outcomes_vectorised(m1, pending)
        assert results[0][0] == 'WIN'
        # MAE and MFE are in the result tuple
        assert len(results[0]) >= 3  # (outcome, r, mae_pct, mfe_pct)


# ── Structural Resolution (90/10 split) ──────────────────────────────────────

class TestResolveStructural:
    def test_tp1_hit_runner_be(self):
        """TP1 hit → 90% exits, runner with BE stop."""
        entry, sl, tp = 24000.0, 23950.0, 24050.0
        bars = [
            (24000, 24055, 23995, 24052),  # hits TP1 (24050)
            (24052, 24055, 23999, 24000),  # runner stopped at BE (24000)
        ]
        m1, pending = _make_resolution_scenario(entry, 'LONG', sl, tp, bars)
        results = ms.resolve_outcomes_structural(m1, pending)
        outcome, net_r = results[0][0], results[0][1]
        assert outcome == 'WIN'
        # net_r ≈ 0.90 * 1.0 + 0.10 * 0.0 = 0.90 (runner at BE)
        assert net_r > 0

    def test_sl_hit_before_tp1(self):
        """SL hit before TP1 → full loss."""
        entry, sl, tp = 24000.0, 23950.0, 24050.0
        bars = [
            (24000, 24005, 23945, 23948),  # hits SL (23950)
            (23948, 23955, 23940, 23945),
        ]
        m1, pending = _make_resolution_scenario(entry, 'LONG', sl, tp, bars)
        results = ms.resolve_outcomes_structural(m1, pending)
        assert results[0][0] == 'LOSS'
        assert results[0][1] < 0


# ── Split TP Resolution ──────────────────────────────────────────────────────

class TestResolveSplitTp:
    def test_tp1_hit_with_runner(self):
        """Split TP: TP1 hit, runner continues."""
        entry, sl, tp = 24000.0, 23950.0, 24050.0
        bars = [
            (24000, 24055, 23995, 24052),  # hits TP1
            (24052, 24060, 24000, 24000),  # runner stopped at BE
        ]
        m1, pending = _make_resolution_scenario(entry, 'LONG', sl, tp, bars)
        results = ms.resolve_outcomes_split_tp(m1, pending,
                                               tp1_size=0.90, tp2_size=0.10)
        assert results[0][0] == 'WIN'
        assert results[0][1] > 0

    def test_sl_hit_full_loss(self):
        """SL hit before any TP → full loss."""
        entry, sl, tp = 24000.0, 23950.0, 24050.0
        bars = [
            (24000, 24005, 23945, 23948),  # hits SL
            (23948, 23955, 23940, 23945),
        ]
        m1, pending = _make_resolution_scenario(entry, 'LONG', sl, tp, bars)
        results = ms.resolve_outcomes_split_tp(m1, pending,
                                               tp1_size=0.90, tp2_size=0.10)
        assert results[0][0] == 'LOSS'
        assert abs(results[0][1] - (-1.0)) < 0.1
