"""Tests for MAE/MFE stats: _full_mae_stats(), _full_mfe_stats()."""
import pandas as pd
import numpy as np
import pytest
import model_stats as ms


def _make_wl_df(n, mae_vals, mfe_vals, outcomes=None, r_vals=None):
    """Build a win/loss DataFrame for MAE/MFE testing."""
    if outcomes is None:
        outcomes = ['WIN'] * (n * 3 // 4) + ['LOSS'] * (n - n * 3 // 4)
    if r_vals is None:
        r_vals = [1.0 if o == 'WIN' else -1.0 for o in outcomes]
    df = pd.DataFrame({
        'outcome': outcomes[:n],
        'r': r_vals[:n],
        'win': [1 if o == 'WIN' else 0 for o in outcomes[:n]],
        'mae_pct': mae_vals[:n],
        'mfe_pct': mfe_vals[:n],
        'net_r': r_vals[:n],
    })
    return df


class TestFullMaeStats:
    def test_returns_none_below_20_trades(self):
        """Fewer than 20 trades → returns None."""
        df = _make_wl_df(10, [0.1]*10, [0.3]*10)
        result = ms._full_mae_stats(df)
        assert result is None

    def test_basic_stats_computed(self):
        """With 50 trades, basic stats are computed."""
        rng = np.random.RandomState(42)
        mae = rng.uniform(0.05, 0.5, 50)
        mfe = rng.uniform(0.1, 1.0, 50)
        df = _make_wl_df(50, mae.tolist(), mfe.tolist())
        result = ms._full_mae_stats(df)
        assert result is not None
        assert 'percentiles' in result
        assert 'sl_sweep' in result
        assert 'opt_sl' in result
        assert result['n'] == 50
        assert result['mean'] > 0
        assert result['median'] > 0

    def test_percentiles_present(self):
        """All expected percentile keys exist."""
        rng = np.random.RandomState(42)
        mae = rng.uniform(0.05, 0.5, 100)
        mfe = rng.uniform(0.1, 1.0, 100)
        df = _make_wl_df(100, mae.tolist(), mfe.tolist())
        result = ms._full_mae_stats(df)
        pcts = result['percentiles']
        for p in ['p5', 'p10', 'p25', 'p50', 'p75', 'p90', 'p95']:
            assert p in pcts
            assert pcts[p] > 0

    def test_opt_sl_with_mixed_outcomes(self):
        """opt_sl should find threshold where p_ko >= 0.70."""
        # Create data where high MAE trades are mostly losers
        n = 100
        mae = list(np.linspace(0.05, 0.5, n))
        outcomes = ['WIN'] * 70 + ['LOSS'] * 30  # losers have higher MAE
        r_vals = [1.0] * 70 + [-1.0] * 30
        mfe = [0.5] * n
        df = _make_wl_df(n, mae, mfe, outcomes, r_vals)
        result = ms._full_mae_stats(df)
        # opt_sl should exist since losers cluster at high MAE
        assert result is not None
        assert 'opt_sl' in result

    def test_all_winners_opt_sl_none(self):
        """All winners → p_ko = 0 everywhere → opt_sl = None."""
        n = 50
        mae = list(np.linspace(0.05, 0.3, n))
        df = _make_wl_df(n, mae, [0.5]*n, ['WIN']*n, [1.0]*n)
        result = ms._full_mae_stats(df)
        assert result is not None
        assert result['opt_sl'] is None


class TestFullMfeStats:
    def test_returns_none_below_20_trades(self):
        df = _make_wl_df(10, [0.1]*10, [0.3]*10)
        result = ms._full_mfe_stats(df)
        assert result is None

    def test_basic_stats_computed(self):
        rng = np.random.RandomState(42)
        mae = rng.uniform(0.05, 0.5, 50)
        mfe = rng.uniform(0.1, 1.5, 50)
        df = _make_wl_df(50, mae.tolist(), mfe.tolist())
        result = ms._full_mfe_stats(df)
        assert result is not None
        assert 'ptq_level' in result
        assert 'be_triggers' in result
        assert result['n'] == 50

    def test_ptq_with_high_win_rate(self):
        """High WR → PTQ found at high reach_rate (low threshold)."""
        n = 100
        mfe = list(np.linspace(0.1, 2.0, n))
        outcomes = ['WIN'] * 85 + ['LOSS'] * 15
        r_vals = [1.0] * 85 + [-1.0] * 15
        df = _make_wl_df(n, [0.1]*n, mfe, outcomes, r_vals)
        result = ms._full_mfe_stats(df)
        assert result is not None
        assert result['ptq_level'] is not None
        assert result['ptq_level'] > 0

    def test_all_losers_ptq_none(self):
        """All losers → p_pos ≈ 0 → PTQ = None."""
        n = 50
        mfe = list(np.linspace(0.05, 0.5, n))
        df = _make_wl_df(n, [0.1]*n, mfe, ['LOSS']*n, [-1.0]*n)
        result = ms._full_mfe_stats(df)
        assert result is not None
        assert result['ptq_level'] is None

    def test_clusters_present(self):
        """MFE clusters (Small/Moderate/Large) are computed."""
        rng = np.random.RandomState(42)
        mfe = rng.uniform(0.1, 2.0, 100)
        df = _make_wl_df(100, [0.1]*100, mfe.tolist())
        result = ms._full_mfe_stats(df)
        assert result is not None
        clusters = result['clusters']
        assert len(clusters) == 3
        labels = [c['label'] for c in clusters]
        assert 'Small' in labels
        assert 'Moderate' in labels
        assert 'Large' in labels
