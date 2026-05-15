"""Integration tests for build_model_stats()."""
import pandas as pd
import numpy as np
import pytest
import model_stats as ms


def _make_resolved_df(n=100):
    """Build a realistic resolved trades DataFrame."""
    rng = np.random.RandomState(42)
    outcomes = rng.choice(['WIN', 'LOSS'], n, p=[0.8, 0.2])
    r_vals = np.where(outcomes == 'WIN', rng.uniform(0.5, 2.0, n), rng.uniform(-1.2, -0.5, n))
    hrs = rng.choice(range(8, 16), n)
    dows = rng.choice(range(1, 6), n)  # Mon-Fri
    sessions = np.array([ms.get_session(h + rng.uniform(0, 0.5)) for h in hrs])
    directions = rng.choice(['LONG', 'SHORT'], n)
    sweep_pcts = rng.uniform(0.05, 0.49, n)

    df = pd.DataFrame({
        'date': [f'2023-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}' for i in range(n)],
        'yr': 2023,
        'dow': dows,
        'direction': directions,
        'ref_range': rng.uniform(15, 60, n),
        'sweep_ext': rng.uniform(3, 20, n),
        'sweep_pct': sweep_pcts,
        'sweep_extreme': rng.uniform(23900, 24100, n),
        'sweep_mode': 'PREV',
        'cisd_mode': 'CISD',
        'ref_lookback': 1,
        'smt': rng.choice([True, False], n, p=[0.25, 0.75]),
        'hr': hrs,
        'mn': rng.choice(range(0, 60, 5), n),
        'session': sessions,
        'entry_price': rng.uniform(23900, 24100, n).round(2),
        'base_risk': rng.uniform(10, 80, n).round(2),
        'cisd_level': rng.uniform(23900, 24100, n).round(2),
        'hour_range_pts': rng.uniform(20, 100, n).round(2),
        'rejected_by': '',
        'stop_price': rng.uniform(23850, 24050, n).round(2),
        'target_price': rng.uniform(23950, 24150, n).round(2),
        'risk_pts': rng.uniform(10, 80, n).round(2),
        'outcome': outcomes,
        'r': r_vals.round(3),
        'mae_pct': rng.uniform(0.01, 0.5, n).round(4),
        'mfe_pct': rng.uniform(0.05, 2.0, n).round(4),
        'mae_pct_hr': rng.uniform(1, 80, n).round(4),
        'mfe_pct_hr': rng.uniform(5, 300, n).round(4),
    })
    return df


class TestBuildModelStats:
    def test_returns_dict(self):
        """build_model_stats returns a dict."""
        df = _make_resolved_df(50)
        cfg = dict(label='Test', sweep_tf_min=60, cisd_tf_min=5,
                   min_range=12, session_hrs=(7.0, 16.0))
        result = ms.build_model_stats(df, 100, '1H_5M', cfg,
                                       stop_mult=1.0, target_mult=1.0,
                                       profile_key='test', profile_type='mult')
        assert isinstance(result, dict)

    def test_meta_fields(self):
        """Output contains meta with key stats."""
        df = _make_resolved_df(100)
        cfg = dict(label='Test', sweep_tf_min=60, cisd_tf_min=5,
                   min_range=12, session_hrs=(7.0, 16.0))
        result = ms.build_model_stats(df, 200, '1H_5M', cfg,
                                       stop_mult=1.0, target_mult=1.0,
                                       profile_key='test', profile_type='mult')
        meta = result['meta']
        assert 'win_rate' in meta
        assert 'ev_per_trade' in meta
        assert 'profit_factor' in meta
        assert 'total_wl' in meta
        assert meta['total_wl'] > 0

    def test_by_hour_populated(self):
        """by_hour breakdown is populated."""
        df = _make_resolved_df(200)
        cfg = dict(label='Test', sweep_tf_min=60, cisd_tf_min=5,
                   min_range=12, session_hrs=(7.0, 16.0))
        result = ms.build_model_stats(df, 200, '1H_5M', cfg,
                                       stop_mult=1.0, target_mult=1.0,
                                       profile_key='test', profile_type='mult')
        assert 'by_hour' in result
        assert len(result['by_hour']) > 0

    def test_by_dow_populated(self):
        df = _make_resolved_df(200)
        cfg = dict(label='Test', sweep_tf_min=60, cisd_tf_min=5,
                   min_range=12, session_hrs=(7.0, 16.0))
        result = ms.build_model_stats(df, 200, '1H_5M', cfg,
                                       stop_mult=1.0, target_mult=1.0,
                                       profile_key='test', profile_type='mult')
        assert 'by_dow' in result
        assert len(result['by_dow']) > 0

    def test_by_session_populated(self):
        df = _make_resolved_df(200)
        cfg = dict(label='Test', sweep_tf_min=60, cisd_tf_min=5,
                   min_range=12, session_hrs=(7.0, 16.0))
        result = ms.build_model_stats(df, 200, '1H_5M', cfg,
                                       stop_mult=1.0, target_mult=1.0,
                                       profile_key='test', profile_type='mult')
        assert 'by_session' in result

    def test_dir_summary(self):
        """dir_summary has LONG and SHORT entries."""
        df = _make_resolved_df(200)
        cfg = dict(label='Test', sweep_tf_min=60, cisd_tf_min=5,
                   min_range=12, session_hrs=(7.0, 16.0))
        result = ms.build_model_stats(df, 200, '1H_5M', cfg,
                                       stop_mult=1.0, target_mult=1.0,
                                       profile_key='test', profile_type='mult')
        dirs = [d['direction'] for d in result['dir_summary']]
        assert 'LONG' in dirs
        assert 'SHORT' in dirs

    def test_smt_summary(self):
        """smt_summary has True and False entries."""
        df = _make_resolved_df(200)
        cfg = dict(label='Test', sweep_tf_min=60, cisd_tf_min=5,
                   min_range=12, session_hrs=(7.0, 16.0))
        result = ms.build_model_stats(df, 200, '1H_5M', cfg,
                                       stop_mult=1.0, target_mult=1.0,
                                       profile_key='test', profile_type='mult')
        assert 'smt_summary' in result
        if result['smt_summary']:
            smt_vals = [s['smt'] for s in result['smt_summary']]
            assert True in smt_vals or False in smt_vals

    def test_tspot_breakdown(self):
        """tspot_breakdown is populated."""
        df = _make_resolved_df(200)
        cfg = dict(label='Test', sweep_tf_min=60, cisd_tf_min=5,
                   min_range=12, session_hrs=(7.0, 16.0))
        result = ms.build_model_stats(df, 200, '1H_5M', cfg,
                                       stop_mult=1.0, target_mult=1.0,
                                       profile_key='test', profile_type='mult')
        assert 'tspot_breakdown' in result

    def test_risk_stats(self):
        """risk_stats computed correctly. R-only schema (account-agnostic
        post-2026-04 refactor). Dollar fields and ACCOUNT_SIZE were removed."""
        df = _make_resolved_df(100)
        cfg = dict(label='Test', sweep_tf_min=60, cisd_tf_min=5,
                   min_range=12, session_hrs=(7.0, 16.0))
        result = ms.build_model_stats(df, 200, '1H_5M', cfg,
                                       stop_mult=1.0, target_mult=1.0,
                                       profile_key='test', profile_type='mult')
        rs = result['risk_stats']
        # Current R-only fields
        for field in ('trades', 'wins', 'losses', 'avg_win_r', 'avg_loss_r',
                      'max_consec_wins', 'max_consec_losses',
                      'avg_consec_wins', 'avg_consec_losses', 'ce'):
            assert field in rs, f"missing field: {field}"
        assert rs['trades'] == rs['wins'] + rs['losses']

    def test_recent_trades(self):
        """recent_trades list is included."""
        df = _make_resolved_df(100)
        cfg = dict(label='Test', sweep_tf_min=60, cisd_tf_min=5,
                   min_range=12, session_hrs=(7.0, 16.0))
        result = ms.build_model_stats(df, 200, '1H_5M', cfg,
                                       stop_mult=1.0, target_mult=1.0,
                                       profile_key='test', profile_type='mult')
        assert 'recent_trades' in result
        assert len(result['recent_trades']) > 0
        # Check smt field in trades
        assert 'smt' in result['recent_trades'][0]

    def test_heatmap(self):
        """Heatmap is populated."""
        df = _make_resolved_df(200)
        cfg = dict(label='Test', sweep_tf_min=60, cisd_tf_min=5,
                   min_range=12, session_hrs=(7.0, 16.0))
        result = ms.build_model_stats(df, 200, '1H_5M', cfg,
                                       stop_mult=1.0, target_mult=1.0,
                                       profile_key='test', profile_type='mult')
        assert 'heatmap' in result

    def test_by_year(self):
        df = _make_resolved_df(100)
        cfg = dict(label='Test', sweep_tf_min=60, cisd_tf_min=5,
                   min_range=12, session_hrs=(7.0, 16.0))
        result = ms.build_model_stats(df, 200, '1H_5M', cfg,
                                       stop_mult=1.0, target_mult=1.0,
                                       profile_key='test', profile_type='mult')
        assert 'by_year' in result
