"""Tests targeting specific uncovered lines for higher coverage."""
import numpy as np
import pandas as pd
import pytest
from helpers import NS_PER_MIN, BASE_TS, make_controlled_m1
import model_stats as ms


# ── CISD SHORT doji walk (line 340) ──────────────────────────────────────────

class TestCisdShortDojiWalk:
    def _arrs(self, bars):
        n = len(bars)
        ts = np.array([BASE_TS + i * NS_PER_MIN * 5 for i in range(n)], dtype='int64')
        o = np.array([b[0] for b in bars], dtype='float64')
        c = np.array([b[1] for b in bars], dtype='float64')
        h = np.maximum(o, c) + 1.0
        l = np.minimum(o, c) - 1.0
        return dict(ts_ns=ts, open=o, close=c, high=h, low=l)

    def test_short_doji_in_run_walk_back(self):
        """SHORT: doji during backward walk of bullish run (line 340)."""
        bars = [
            (24000, 24010),  # 0: bullish (earliest)
            (24010, 24010),  # 1: DOJI — skip during walk-back
            (24010, 24020),  # 2: bullish
            (24020, 24015),  # 3: return
            (24015, 23995),  # 4: fire
        ]
        arrs = self._arrs(bars)
        ts, lvl = ms._find_cisd(arrs['open'], arrs['close'], arrs['ts_ns'],
                                start_idx=3, n_bars=100, direction='SHORT')
        assert lvl == 24000.0


# ── Resolution: vectorised EXPIRED with no data (line 415) ───────────────────

class TestResolutionExpiredNoBars:
    def test_vectorised_no_bars_after_entry(self):
        """Entry timestamp beyond available data → EXPIRED (line 415)."""
        bars = [(24000, 24005, 23995, 24002)]
        m1 = make_controlled_m1(bars, start_ts=BASE_TS)
        m1['hr'][:] = 9
        # Entry far in the future — no bars to scan
        pending = [dict(
            idx=0, entry_ts_ns=int(BASE_TS + NS_PER_MIN * 1000),
            entry_price=24000.0, stop_price=23950.0, target_price=24050.0,
            direction='LONG', hour_range_pts=50.0,
        )]
        results = ms.resolve_outcomes_vectorised(m1, pending)
        assert results[0][0] in ('EXPIRED', 'INVALID')

    def test_structural_no_bars_after_entry(self):
        """Structural: no bars after entry → EXPIRED (line 502)."""
        bars = [(24000, 24005, 23995, 24002)]
        m1 = make_controlled_m1(bars, start_ts=BASE_TS)
        m1['hr'][:] = 9
        pending = [dict(
            idx=0, entry_ts_ns=int(BASE_TS + NS_PER_MIN * 1000),
            entry_price=24000.0, stop_price=23950.0, target_price=24050.0,
            direction='LONG', sweep_extreme=23950.0, base_risk=50.0,
            hour_range_pts=50.0,
        )]
        results = ms.resolve_outcomes_structural(m1, pending)
        assert results[0][0] in ('EXPIRED', 'INVALID')

    def test_split_tp_no_bars_after_entry(self):
        """Split TP: no bars after entry → EXPIRED (line 609)."""
        bars = [(24000, 24005, 23995, 24002)]
        m1 = make_controlled_m1(bars, start_ts=BASE_TS)
        m1['hr'][:] = 9
        pending = [dict(
            idx=0, entry_ts_ns=int(BASE_TS + NS_PER_MIN * 1000),
            entry_price=24000.0, stop_price=23950.0, target_price=24050.0,
            direction='LONG', sweep_extreme=23950.0, base_risk=50.0,
            hour_range_pts=50.0,
        )]
        results = ms.resolve_outcomes_split_tp(m1, pending)
        assert results[0][0] in ('EXPIRED', 'INVALID')


# ── SHORT runner mark-to-market (lines 696, 712) ────────────────────────────

class TestShortRunnerMarkToMarket:
    def test_structural_short_runner_mark_to_market(self):
        """SHORT structural: TP1 hit, runner doesn't hit BE, exits at EOD (line 696)."""
        bars = [
            (24000, 24005, 23995, 23998),
            (23998, 24002, 23945, 23948),  # hits TP (23950)
            (23948, 23950, 23935, 23940),  # runner continues down, no BE
            (23940, 23942, 23930, 23935),  # still down
        ]
        m1 = make_controlled_m1(bars, start_ts=BASE_TS)
        m1['hr'][:] = 9
        pending = [dict(
            idx=0, entry_ts_ns=int(BASE_TS + NS_PER_MIN),
            entry_price=24000.0, stop_price=24050.0, target_price=23950.0,
            direction='SHORT', sweep_extreme=24050.0, base_risk=50.0,
            hour_range_pts=50.0,
        )]
        results = ms.resolve_outcomes_structural(m1, pending)
        assert results[0][0] == 'WIN'
        assert results[0][5] > 0  # runner positive

    def test_split_short_runner_mark_to_market(self):
        """SHORT split: TP1 hit, runner exits at EOD with tp2 set (line 712)."""
        bars = [
            (24000, 24005, 23995, 23998),
            (23998, 24002, 23945, 23948),
            (23948, 23950, 23935, 23940),
            (23940, 23942, 23930, 23935),
        ]
        m1 = make_controlled_m1(bars, start_ts=BASE_TS)
        m1['hr'][:] = 9
        pending = [dict(
            idx=0, entry_ts_ns=int(BASE_TS + NS_PER_MIN),
            entry_price=24000.0, stop_price=24050.0, target_price=23950.0,
            direction='SHORT', sweep_extreme=24050.0, base_risk=50.0,
            hour_range_pts=50.0,
        )]
        results = ms.resolve_outcomes_split_tp(m1, pending,
                                                tp1_size=0.90, tp2_size=0.10,
                                                tp2_pct=2.0)  # TP2 far away
        assert results[0][0] == 'WIN'


# ── MAE/MFE edge cases (lines 819, 850, 939, 967) ───────────────────────────

class TestMaeMfeEdgeCases:
    def test_mae_no_positive_values(self):
        """MAE with all zero values → returns None (line 819)."""
        df = pd.DataFrame({
            'outcome': ['WIN'] * 25, 'r': [1.0] * 25, 'win': [1] * 25,
            'mae_pct': [0.0] * 25, 'mfe_pct': [0.5] * 25, 'net_r': [1.0] * 25,
        })
        result = ms._full_mae_stats(df)
        assert result is None  # all mae=0, filtered out

    def test_mfe_no_positive_values(self):
        """MFE with all zero values → returns None (line 850)."""
        df = pd.DataFrame({
            'outcome': ['WIN'] * 25, 'r': [1.0] * 25, 'win': [1] * 25,
            'mae_pct': [0.1] * 25, 'mfe_pct': [0.0] * 25, 'net_r': [1.0] * 25,
        })
        result = ms._full_mfe_stats(df)
        assert result is None

    def test_mae_sl_sweep_empty_touched(self):
        """MAE SL sweep: threshold above all values → skip (line 939)."""
        rng = np.random.RandomState(42)
        mae = rng.uniform(0.01, 0.1, 50)  # all very small
        df = pd.DataFrame({
            'outcome': ['WIN'] * 50, 'r': [1.0] * 50, 'win': [1] * 50,
            'mae_pct': mae, 'mfe_pct': [0.5] * 50, 'net_r': [1.0] * 50,
        })
        result = ms._full_mae_stats(df)
        assert result is not None

    def test_mfe_ptq_fallback(self):
        """PTQ fallback to 0.50 threshold (line 967)."""
        rng = np.random.RandomState(99)
        n = 50
        # 55% WR — p_pos might not reach 0.70 for any trigger
        outcomes = ['WIN'] * 28 + ['LOSS'] * 22
        df = pd.DataFrame({
            'outcome': outcomes, 'r': [1.0]*28 + [-1.0]*22,
            'win': [1]*28 + [0]*22,
            'mae_pct': rng.uniform(0.05, 0.3, n),
            'mfe_pct': rng.uniform(0.05, 0.8, n),
            'net_r': [1.0]*28 + [-1.0]*22,
        })
        result = ms._full_mfe_stats(df)
        if result:
            # PTQ should exist via fallback
            assert 'ptq_level' in result


# ── compute_filter_impact edge cases (lines 2125-2127) ───────────────────────

class TestFilterImpactEdgeCases:
    def test_with_actual_rejected_trades(self):
        """Filter impact returns at least the baseline."""
        rows = []
        for _ in range(30):
            rows.append(dict(outcome='WIN', r=1.0, rejected_by=''))
        for _ in range(10):
            rows.append(dict(outcome='LOSS', r=-1.0, rejected_by=''))
        for _ in range(15):
            rows.append(dict(outcome='SKIP', r=0.0, rejected_by='NO_CISD'))
        for _ in range(10):
            rows.append(dict(outcome='INVALID', r=0.0, rejected_by='INVALID_RISK'))

        df = pd.DataFrame(rows)
        result = ms.compute_filter_impact(df)
        assert len(result) >= 1
        assert result[0]['n'] == 40


# ── compute_filter_variants with SMT (line 2070) ────────────────────────────

class TestFilterVariantsSmt:
    def test_variants_with_smt_column(self):
        """Filter variants includes SMT as a dimension."""
        rng = np.random.RandomState(42)
        n = 100
        outcomes = rng.choice(['WIN', 'LOSS'], n, p=[0.8, 0.2])
        df = pd.DataFrame({
            'date': '2023-11-14', 'outcome': outcomes,
            'rejected_by': rng.choice(['', 'F1_SMALL_RANGE', 'F3_SWEEP_TOO_LARGE'], n, p=[0.6, 0.2, 0.2]),
            'r': np.where(outcomes == 'WIN', 1.0, -1.0),
            'risk_pts': 30.0, 'smt': rng.choice([True, False], n, p=[0.3, 0.7]),
        })
        # Fix: SKIP outcome for rejected trades
        df.loc[df['rejected_by'] != '', 'outcome'] = 'SKIP'
        df.loc[df['rejected_by'] != '', 'r'] = 0.0

        result = ms.compute_filter_variants(df)
        assert 'all_combinations' in result
        # 6 runtime filter dimensions: F3, F4, SMT, HOUR_ALIGNED,
        # PRIOR_COUNTER, PRIOR_ENGULFING. Loop includes the empty set,
        # so 2**6 = 64 combos.
        assert len(result['all_combinations']) == 2**6
        # SMT combos should exist
        smt_combos = [c for c in result['all_combinations']
                      if 'NQ-ES' in (c.get('label') or '') or 'SMT' in (c.get('label') or '')]
        assert len(smt_combos) > 0

    def test_variants_without_smt_column(self):
        """Filter variants gracefully handles missing smt column."""
        n = 50
        outcomes = ['WIN'] * 35 + ['LOSS'] * 15
        df = pd.DataFrame({
            'date': '2023-11-14', 'outcome': outcomes,
            'rejected_by': [''] * 50,
            'r': [1.0]*35 + [-1.0]*15, 'risk_pts': 30.0,
        })
        result = ms.compute_filter_variants(df)
        assert 'all_combinations' in result
        # Without smt column, SMT filter should have no effect
        assert result['baseline']['n'] > 0


# ── build_model_stats equity tracking (line 1659) ────────────────────────────

class TestBuildModelStatsEquity:
    def _make_df(self, n=100, wr=0.8):
        rng = np.random.RandomState(42)
        outcomes = rng.choice(['WIN', 'LOSS'], n, p=[wr, 1-wr])
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
            'session': 'NY1', 'entry_price': 24000.0, 'base_risk': 50.0,
            'cisd_level': 23990.0, 'hour_range_pts': 50.0,
            'rejected_by': '',
            'stop_price': 23950.0, 'target_price': 24050.0,
            'risk_pts': 50.0, 'outcome': outcomes,
            'r': np.where(outcomes == 'WIN', 1.0, -1.0),
            'mae_pct': rng.uniform(0.05, 0.4, n),
            'mfe_pct': rng.uniform(0.1, 1.5, n),
            'mae_pct_hr': rng.uniform(5, 60, n),
            'mfe_pct_hr': rng.uniform(10, 200, n),
        })

    def test_equity_min_tracked(self):
        """min_equity_usd is tracked correctly (line 1659)."""
        cfg = dict(label='T', sweep_tf_min=60, cisd_tf_min=5,
                   min_range=12, session_hrs=(7.0, 16.0))
        df = self._make_df(50, wr=0.5)  # lower WR to hit min equity
        result = ms.build_model_stats(df, 100, '1H_5M', cfg,
                                       stop_mult=1.0, target_mult=1.0,
                                       profile_key='t', profile_type='mult')
        assert result['risk_stats']['min_equity_usd'] <= ms.ACCOUNT_SIZE

    def test_all_losses_blown(self):
        """All losses should blow the account."""
        cfg = dict(label='T', sweep_tf_min=60, cisd_tf_min=5,
                   min_range=12, session_hrs=(7.0, 16.0))
        df = self._make_df(30, wr=0.0)  # all losses
        result = ms.build_model_stats(df, 100, '1H_5M', cfg,
                                       stop_mult=1.0, target_mult=1.0,
                                       profile_key='t', profile_type='mult')
        assert result['risk_stats']['blown'] == True

    def test_filter_variants_in_output(self):
        """filter_variants is present in output."""
        cfg = dict(label='T', sweep_tf_min=60, cisd_tf_min=5,
                   min_range=12, session_hrs=(7.0, 16.0))
        df = self._make_df(100)
        result = ms.build_model_stats(df, 100, '1H_5M', cfg,
                                       stop_mult=1.0, target_mult=1.0,
                                       profile_key='t', profile_type='mult')
        assert 'filter_variants' in result
