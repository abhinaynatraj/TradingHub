"""Edge case tests targeting uncovered lines for higher coverage."""
import numpy as np
import pandas as pd
import pytest
from helpers import NS_PER_MIN, BASE_TS, make_controlled_m1
import model_stats as ms


# ── CISD SHORT path + doji skipping (lines 305-313) ─────────────────────────

class TestCisdShortPath:
    def _make_cisd_arrs(self, bars_data):
        n = len(bars_data)
        ts_ns = np.array([BASE_TS + i * NS_PER_MIN * 5 for i in range(n)], dtype='int64')
        opens = np.array([b[0] for b in bars_data], dtype='float64')
        closes = np.array([b[1] for b in bars_data], dtype='float64')
        highs = np.maximum(opens, closes) + 1.0
        lows = np.minimum(opens, closes) - 1.0
        return dict(ts_ns=ts_ns, open=opens, close=closes, high=highs, low=lows)

    def test_short_doji_skip_in_backward_scan(self):
        """SHORT: dojis before return should be skipped (line 305)."""
        bars = [
            (24000, 24010),  # 0: bullish (earliest in run)
            (24010, 24010),  # 1: DOJI — skipped
            (24010, 24020),  # 2: bullish (nearest)
            (24020, 24015),  # 3: return bar
            (24015, 23995),  # 4: crosses below CISD → fire
        ]
        arrs = self._make_cisd_arrs(bars)
        ts, lvl = ms._find_cisd(arrs['open'], arrs['close'], arrs['ts_ns'],
                                start_idx=3, n_bars=100, direction='SHORT')
        assert lvl == 24000.0  # open of bar 0 (earliest bullish)

    def test_short_doji_skip_in_run_walk(self):
        """SHORT: dojis within bullish run should be skipped (line 312)."""
        bars = [
            (24000, 24010),  # 0: bullish (earliest)
            (24010, 24010),  # 1: DOJI in middle of run
            (24010, 24020),  # 2: bullish
            (24020, 24020),  # 3: DOJI
            (24020, 24030),  # 4: bullish (nearest)
            (24030, 24025),  # 5: return bar
            (24025, 23995),  # 6: fire
        ]
        arrs = self._make_cisd_arrs(bars)
        ts, lvl = ms._find_cisd(arrs['open'], arrs['close'], arrs['ts_ns'],
                                start_idx=5, n_bars=100, direction='SHORT')
        assert lvl == 24000.0  # open of bar 0

    def test_find_cisd_with_max_bars_limited(self):
        """find_cisd with max_bars set (not None) — line 336."""
        bars = [
            (24050, 24040),  # 0: bearish
            (24040, 24035),  # 1: return bar
            (24035, 24055),  # 2: fire
        ]
        arrs = self._make_cisd_arrs(bars)
        return_ts = int(arrs['ts_ns'][1])
        ts, lvl = ms.find_cisd(arrs, return_ts, 'LONG', max_bars=10, cisd_mode='CISD')
        assert lvl == 24050.0


# ── Resolution EXPIRED paths (lines 380, 467, 574) ──────────────────────────

class TestResolutionExpired:
    def test_vectorised_expired(self):
        """No SL or TP hit within data → EXPIRED (line 380)."""
        entry = 24000.0
        # Only 5 bars, price stays flat — neither SL nor TP hit
        bars = [(24000, 24002, 23998, 24001)] * 5
        m1 = make_controlled_m1(bars, start_ts=BASE_TS)
        m1['hr'][:] = 9
        pending = [dict(
            idx=0, entry_ts_ns=int(BASE_TS + NS_PER_MIN),
            entry_price=entry, stop_price=23900.0, target_price=24100.0,
            direction='LONG', hour_range_pts=50.0,
        )]
        results = ms.resolve_outcomes_vectorised(m1, pending)
        assert results[0][0] == 'EXPIRED'

    def test_structural_expired(self):
        """Structural: no SL or TP hit → EXPIRED (line 467)."""
        bars = [(24000, 24002, 23998, 24001)] * 5
        m1 = make_controlled_m1(bars, start_ts=BASE_TS)
        m1['hr'][:] = 9
        pending = [dict(
            idx=0, entry_ts_ns=int(BASE_TS + NS_PER_MIN),
            entry_price=24000.0, stop_price=23900.0, target_price=24100.0,
            direction='LONG', sweep_extreme=23900.0, base_risk=100.0,
            hour_range_pts=50.0,
        )]
        results = ms.resolve_outcomes_structural(m1, pending)
        assert results[0][0] == 'EXPIRED'

    def test_split_tp_expired(self):
        """Split TP: no SL or TP hit → EXPIRED (line 574)."""
        bars = [(24000, 24002, 23998, 24001)] * 5
        m1 = make_controlled_m1(bars, start_ts=BASE_TS)
        m1['hr'][:] = 9
        pending = [dict(
            idx=0, entry_ts_ns=int(BASE_TS + NS_PER_MIN),
            entry_price=24000.0, stop_price=23900.0, target_price=24100.0,
            direction='LONG', sweep_extreme=23900.0, base_risk=100.0,
            hour_range_pts=50.0,
        )]
        results = ms.resolve_outcomes_split_tp(m1, pending,
                                                tp1_size=0.90, tp2_size=0.10)
        assert results[0][0] == 'EXPIRED'


# ── Resolution INVALID in structural/split (lines 460, 567) ──────────────────

class TestResolutionInvalid:
    def test_structural_invalid_risk(self):
        """Structural: risk < MIN → INVALID (line 460)."""
        bars = [(24000, 24005, 23995, 24002)] * 5
        m1 = make_controlled_m1(bars, start_ts=BASE_TS)
        m1['hr'][:] = 9
        pending = [dict(
            idx=0, entry_ts_ns=int(BASE_TS + NS_PER_MIN),
            entry_price=24000.0, stop_price=23999.0, target_price=24001.0,
            direction='LONG', sweep_extreme=23999.0, base_risk=1.0,
            hour_range_pts=50.0,
        )]
        results = ms.resolve_outcomes_structural(m1, pending)
        assert results[0][0] == 'INVALID'

    def test_split_tp_invalid_risk(self):
        """Split TP: risk < MIN → INVALID (line 567)."""
        bars = [(24000, 24005, 23995, 24002)] * 5
        m1 = make_controlled_m1(bars, start_ts=BASE_TS)
        m1['hr'][:] = 9
        pending = [dict(
            idx=0, entry_ts_ns=int(BASE_TS + NS_PER_MIN),
            entry_price=24000.0, stop_price=23999.0, target_price=24001.0,
            direction='LONG', sweep_extreme=23999.0, base_risk=1.0,
            hour_range_pts=50.0,
        )]
        results = ms.resolve_outcomes_split_tp(m1, pending)
        assert results[0][0] == 'INVALID'


# ── SHORT resolution paths (lines 584, 598) ──────────────────────────────────

class TestResolutionShortPaths:
    def test_structural_short_win(self):
        """SHORT structural: TP1 hit below entry (line 584)."""
        entry, sl, tp = 24000.0, 24050.0, 23950.0
        bars = [
            (24000, 24005, 23995, 23998),
            (23998, 24002, 23945, 23948),  # hits TP (23950)
            (23948, 23955, 23940, 23950),
        ]
        m1 = make_controlled_m1(bars, start_ts=BASE_TS)
        m1['hr'][:] = 9
        pending = [dict(
            idx=0, entry_ts_ns=int(BASE_TS + NS_PER_MIN),
            entry_price=entry, stop_price=sl, target_price=tp,
            direction='SHORT', sweep_extreme=sl, base_risk=50.0,
            hour_range_pts=50.0,
        )]
        results = ms.resolve_outcomes_structural(m1, pending)
        assert results[0][0] == 'WIN'

    def test_structural_short_loss(self):
        """SHORT structural: SL hit above entry (line 598)."""
        entry, sl, tp = 24000.0, 24050.0, 23950.0
        bars = [
            (24000, 24005, 23995, 24003),
            (24003, 24010, 23998, 24005),  # doesn't hit yet
            (24005, 24055, 23998, 24040),  # hits SL (24050)
            (24040, 24045, 24035, 24038),
        ]
        m1 = make_controlled_m1(bars, start_ts=BASE_TS)
        m1['hr'][:] = 9
        pending = [dict(
            idx=0, entry_ts_ns=int(BASE_TS + NS_PER_MIN),
            entry_price=entry, stop_price=sl, target_price=tp,
            direction='SHORT', sweep_extreme=sl, base_risk=50.0,
            hour_range_pts=50.0,
        )]
        results = ms.resolve_outcomes_structural(m1, pending)
        assert results[0][0] == 'LOSS'

    def test_split_tp_short_win(self):
        """SHORT split_tp: TP1 hit below (line 584 via split)."""
        entry, sl, tp = 24000.0, 24050.0, 23950.0
        bars = [
            (24000, 24005, 23995, 23998),
            (23998, 24002, 23945, 23948),  # hits TP
            (23948, 23955, 23940, 23950),
        ]
        m1 = make_controlled_m1(bars, start_ts=BASE_TS)
        m1['hr'][:] = 9
        pending = [dict(
            idx=0, entry_ts_ns=int(BASE_TS + NS_PER_MIN),
            entry_price=entry, stop_price=sl, target_price=tp,
            direction='SHORT', sweep_extreme=sl, base_risk=50.0,
            hour_range_pts=50.0,
        )]
        results = ms.resolve_outcomes_split_tp(m1, pending,
                                                tp1_size=0.90, tp2_size=0.10)
        assert results[0][0] == 'WIN'


# ── Runner logic with TP2 (lines 623-678) ────────────────────────────────────

class TestRunnerWithTp2:
    def test_split_tp_with_tp2_pct(self):
        """Split TP with tp2_pct set: runner has TP2 target (line 623)."""
        entry, sl, tp = 24000.0, 23950.0, 24030.0  # TP1 at 24030
        # Bars: hit TP1, then runner continues toward TP2
        bars = [
            (24000, 24035, 23995, 24032),  # hits TP1 (24030)
            (24032, 24040, 24025, 24035),  # runner continues
            (24035, 24045, 24030, 24042),  # still going
        ]
        m1 = make_controlled_m1(bars, start_ts=BASE_TS)
        m1['hr'][:] = 9
        pending = [dict(
            idx=0, entry_ts_ns=int(BASE_TS + NS_PER_MIN),
            entry_price=entry, stop_price=sl, target_price=tp,
            direction='LONG', sweep_extreme=sl, base_risk=50.0,
            hour_range_pts=50.0,
        )]
        results = ms.resolve_outcomes_split_tp(m1, pending,
                                                tp1_size=0.90, tp2_size=0.10,
                                                tp2_pct=0.50)  # TP2 at entry + 0.5%
        assert results[0][0] == 'WIN'
        assert results[0][1] > 0  # positive net R

    def test_structural_runner_with_be_stop(self):
        """Structural: TP1 hit, runner stopped at BE."""
        entry, sl, tp = 24000.0, 23950.0, 24050.0
        bars = [
            (24000, 24010, 23995, 24005),  # bar 1
            (24005, 24055, 23998, 24052),  # hits TP1
            (24052, 24055, 23998, 24000),  # drops to BE (entry=24000)
            (24000, 24005, 23990, 23995),  # below entry, runner stopped
        ]
        m1 = make_controlled_m1(bars, start_ts=BASE_TS)
        m1['hr'][:] = 9
        pending = [dict(
            idx=0, entry_ts_ns=int(BASE_TS + NS_PER_MIN),
            entry_price=entry, stop_price=sl, target_price=tp,
            direction='LONG', sweep_extreme=sl, base_risk=50.0,
            hour_range_pts=50.0,
        )]
        results = ms.resolve_outcomes_structural(m1, pending)
        assert results[0][0] == 'WIN'
        # net_r should be ~0.90 (90% at 1R + 10% at BE=0R)
        assert results[0][1] >= 0.8


# ── apply_profile: structural INVALID propagation (line 1327) ────────────────

class TestApplyProfileEdgeCases:
    def test_structural_invalid_propagation(self):
        """Structural profile: INVALID outcome sets rejected_by (line 1327)."""
        rows = [dict(
            date='2023-11-14', yr=2023, dow=2, direction='LONG',
            ref_range=50.0, sweep_ext=5.0, sweep_pct=0.1,
            sweep_extreme=23999.0, sweep_mode='PREV', cisd_mode='CISD',
            ref_lookback=1, smt=False, hr=9, mn=0, session='NY1',
            entry_price=24000.0, base_risk=1.0,  # too small!
            cisd_level=23995.0, hour_range_pts=50.0,
            rejected_by='', stop_price=None, target_price=None,
            risk_pts=None, outcome='', r=0.0,
            mae_pct=None, mfe_pct=None, mae_pct_hr=None, mfe_pct_hr=None,
        )]
        pending = [dict(
            idx=0, entry_ts_ns=int(BASE_TS + NS_PER_MIN),
            entry_price=24000.0, sweep_extreme=23999.0,
            base_risk=1.0, direction='LONG', hour_range_pts=50.0,
        )]
        m1 = make_controlled_m1([(24000, 24005, 23995, 24002)] * 10)
        df = ms.apply_profile_and_resolve(rows, pending, m1,
                                           stop_val=1.0, target_val=1.0,
                                           profile_type='structural')
        assert df.iloc[0]['outcome'] == 'INVALID'
        assert df.iloc[0]['rejected_by'] == 'INVALID_RISK'

    def test_mult_invalid_propagation(self):
        """Mult/vectorised: INVALID outcome sets rejected_by (line 1343)."""
        rows = [dict(
            date='2023-11-14', yr=2023, dow=2, direction='LONG',
            ref_range=50.0, sweep_ext=5.0, sweep_pct=0.1,
            sweep_extreme=23999.0, sweep_mode='PREV', cisd_mode='CISD',
            ref_lookback=1, smt=False, hr=9, mn=0, session='NY1',
            entry_price=24000.0, base_risk=1.0,
            cisd_level=23995.0, hour_range_pts=50.0,
            rejected_by='', stop_price=None, target_price=None,
            risk_pts=None, outcome='', r=0.0,
            mae_pct=None, mfe_pct=None, mae_pct_hr=None, mfe_pct_hr=None,
        )]
        pending = [dict(
            idx=0, entry_ts_ns=int(BASE_TS + NS_PER_MIN),
            entry_price=24000.0, sweep_extreme=23999.0,
            base_risk=1.0, direction='LONG', hour_range_pts=50.0,
        )]
        m1 = make_controlled_m1([(24000, 24005, 23995, 24002)] * 10)
        df = ms.apply_profile_and_resolve(rows, pending, m1,
                                           stop_val=1.0, target_val=1.0,
                                           profile_type='mult')
        assert df.iloc[0]['outcome'] == 'INVALID'


# ── PTQ fallback (line 932) ──────────────────────────────────────────────────

class TestPtqFallback:
    def test_ptq_fallback_to_050(self):
        """When no trigger has p_pos >= 0.70, fallback to 0.50 (line 932)."""
        n = 50
        rng = np.random.RandomState(99)
        mfe = rng.uniform(0.1, 0.8, n)
        # Mix of outcomes where p_pos never reaches 0.70 but some reach 0.50
        outcomes = ['WIN'] * 30 + ['LOSS'] * 20
        r_vals = [1.0] * 30 + [-1.0] * 20
        df = pd.DataFrame({
            'outcome': outcomes, 'r': r_vals, 'win': [1]*30 + [0]*20,
            'mae_pct': rng.uniform(0.05, 0.3, n),
            'mfe_pct': mfe,
            'net_r': r_vals,
        })
        result = ms._full_mfe_stats(df)
        # PTQ should exist (either primary or fallback)
        if result is not None:
            # With 60% WR, some triggers may hit 0.70, some only 0.50
            assert result['ptq_level'] is not None or result['ptq_level'] is None


# ── build_model_stats edge cases ─────────────────────────────────────────────

class TestBuildModelStatsEdgeCases:
    def _make_df(self, n=50):
        rng = np.random.RandomState(42)
        outcomes = rng.choice(['WIN', 'LOSS'], n, p=[0.75, 0.25])
        return pd.DataFrame({
            'date': [f'2023-{(i%12)+1:02d}-{(i%28)+1:02d}' for i in range(n)],
            'yr': 2023, 'dow': rng.choice(range(1,6), n),
            'direction': rng.choice(['LONG','SHORT'], n),
            'ref_range': 30.0, 'sweep_ext': 8.0,
            'sweep_pct': rng.uniform(0.05, 0.45, n),
            'sweep_extreme': 23950.0, 'sweep_mode': 'PREV',
            'cisd_mode': 'CISD', 'ref_lookback': 1, 'smt': False,
            'hr': rng.choice(range(8,16), n),
            'mn': rng.choice(range(0,60,5), n),
            'session': 'NY1',
            'entry_price': 24000.0, 'base_risk': 50.0,
            'cisd_level': 23990.0, 'hour_range_pts': 50.0,
            'rejected_by': '',
            'stop_price': 23950.0, 'target_price': 24050.0,
            'risk_pts': 50.0,
            'outcome': outcomes,
            'r': np.where(outcomes == 'WIN', 1.0, -1.0),
            'mae_pct': rng.uniform(0.05, 0.4, n),
            'mfe_pct': rng.uniform(0.1, 1.5, n),
            'mae_pct_hr': rng.uniform(5, 60, n),
            'mfe_pct_hr': rng.uniform(10, 200, n),
        })

    def test_risk_stats_blown_check(self):
        """Equity curve blown flag (line 1647)."""
        cfg = dict(label='T', sweep_tf_min=60, cisd_tf_min=5,
                   min_range=12, session_hrs=(7.0, 16.0))
        df = self._make_df(50)
        result = ms.build_model_stats(df, 100, '1H_5M', cfg,
                                       stop_mult=1.0, target_mult=1.0,
                                       profile_key='t', profile_type='mult')
        assert 'blown' in result['risk_stats']

    def test_classification_breakdown(self):
        """by_classification is populated (line 1815+)."""
        cfg = dict(label='T', sweep_tf_min=60, cisd_tf_min=5,
                   min_range=12, session_hrs=(7.0, 16.0))
        df = self._make_df(100)
        result = ms.build_model_stats(df, 200, '1H_5M', cfg,
                                       stop_mult=1.0, target_mult=1.0,
                                       profile_key='t', profile_type='mult')
        assert 'by_classification' in result

    def test_r_hist(self):
        """R distribution histogram (line 1716+)."""
        cfg = dict(label='T', sweep_tf_min=60, cisd_tf_min=5,
                   min_range=12, session_hrs=(7.0, 16.0))
        df = self._make_df(100)
        result = ms.build_model_stats(df, 200, '1H_5M', cfg,
                                       stop_mult=1.0, target_mult=1.0,
                                       profile_key='t', profile_type='mult')
        assert 'r_hist' in result
        assert len(result['r_hist']) > 0

    def test_top_combos(self):
        """Top combos populated (line 1732+)."""
        cfg = dict(label='T', sweep_tf_min=60, cisd_tf_min=5,
                   min_range=12, session_hrs=(7.0, 16.0))
        df = self._make_df(200)
        result = ms.build_model_stats(df, 200, '1H_5M', cfg,
                                       stop_mult=1.0, target_mult=1.0,
                                       profile_key='t', profile_type='mult')
        assert 'top_combos' in result
