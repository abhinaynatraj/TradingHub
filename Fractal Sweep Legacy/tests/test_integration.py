"""Integration tests using a small test DuckDB.

These tests exercise the full pipeline: load_1m → resample → detect_setups_base →
apply_profile_and_resolve → build_model_stats, including SMT cross-reference.
"""
import os
import json
import numpy as np
import pandas as pd
import pytest
import model_stats as ms

TEST_DB = os.path.join(os.path.dirname(__file__), 'test_candles.duckdb')

# Skip all tests if test DB doesn't exist
pytestmark = pytest.mark.skipif(
    not os.path.exists(TEST_DB),
    reason="test_candles.duckdb not found"
)


@pytest.fixture(scope='module')
def db_con():
    """Connect to the test database."""
    con = ms.connect(TEST_DB)
    yield con
    con.close()


@pytest.fixture(scope='module')
def nq_data(db_con):
    """Load NQ 1m data."""
    return ms.load_1m(db_con, 'nq_1m')


@pytest.fixture(scope='module')
def es_data(db_con):
    """Load ES 1m data."""
    return ms.load_1m(db_con, 'es_1m')


# ── load_1m tests ────────────────────────────────────────────────────────────

class TestLoadData:
    def test_load_nq(self, nq_data):
        """load_1m returns (full, rth) DataFrames."""
        full, rth = nq_data
        assert len(full) > 0
        assert len(rth) > 0
        assert len(rth) <= len(full)

    def test_load_es(self, es_data):
        full, rth = es_data
        assert len(full) > 0

    def test_columns_present(self, nq_data):
        """1m DataFrames have expected columns."""
        full, rth = nq_data
        for col in ['open', 'high', 'low', 'close', 'hr', 'mn', 'dow', 'yr', 'trade_date']:
            assert col in full.columns

    def test_rth_filter(self, nq_data):
        """RTH data is filtered to 07:00-16:00."""
        _, rth = nq_data
        assert rth['hr'].min() >= 7
        assert rth['hr'].max() <= 16

    def test_high_gte_low(self, nq_data):
        """Data integrity: high >= low."""
        full, _ = nq_data
        assert (full['high'] >= full['low']).all()


# ── Resample tests ───────────────────────────────────────────────────────────

class TestResampleIntegration:
    def test_resample_60min(self, nq_data):
        _, rth = nq_data
        result = ms.resample(rth, 60, '60min')
        assert len(result) > 0
        assert 'high_tf' in result.columns

    def test_resample_30min(self, nq_data):
        _, rth = nq_data
        result = ms.resample(rth, 30, '30min')
        assert len(result) > 0

    def test_resample_5min(self, nq_data):
        _, rth = nq_data
        result = ms.resample(rth, 5, '5min')
        assert len(result) > 0

    def test_resample_15min(self, nq_data):
        _, rth = nq_data
        result = ms.resample(rth, 15, '15min')
        assert len(result) > 0

    def test_df_to_arrays_from_real_data(self, nq_data):
        _, rth = nq_data
        resampled = ms.resample(rth, 60, '60min')
        arrs = ms.df_to_arrays(resampled)
        assert arrs['ts_ns'].dtype == np.int64
        assert len(arrs['open']) == len(resampled)

    def test_df_1m_to_arrays_from_real_data(self, nq_data):
        _, rth = nq_data
        arrs = ms.df_1m_to_arrays(rth)
        assert 'mn' in arrs
        assert len(arrs['ts_ns']) == len(rth)


# ── Full pipeline: detect + resolve ─────────────────────────────────────────

class TestFullPipeline:
    @pytest.fixture(scope='class')
    def pipeline_data(self, nq_data, es_data):
        """Build all arrays needed for detection."""
        nq_full, nq_rth = nq_data
        es_full, es_rth = es_data

        # Build 1H sweep-TF and 5M CISD-TF
        sweep_df = ms.resample(nq_rth, 60, '60min')
        cisd_df = ms.resample(nq_rth, 5, '5min')
        es_sweep_df = ms.resample(es_rth, 60, 'ES_60min')

        s_arrs = ms.df_to_arrays(sweep_df)
        c_arrs = ms.df_to_arrays(cisd_df)
        m1_arrs = ms.df_1m_to_arrays(nq_rth)
        es_s_arrs = ms.df_to_arrays(es_sweep_df)
        es_m1_arrs = ms.df_1m_to_arrays(es_rth)

        return m1_arrs, s_arrs, c_arrs, es_s_arrs, es_m1_arrs

    def test_detect_setups(self, pipeline_data):
        """detect_setups_base runs without errors on real data."""
        m1, s, c, es_s, es_m1 = pipeline_data
        cfg = ms.MODELS['1H_5M']
        rows, pending = ms.detect_setups_base(
            m1, s, c, '1H_5M', cfg,
            cisd_fast_bars=None, es_s_arrs=es_s, es_m1_arrs=es_m1
        )
        assert isinstance(rows, list)
        assert isinstance(pending, list)
        # With synthetic data, we may or may not get setups
        print(f"  Found {len(rows)} rows, {len(pending)} pending entries")

    def test_detect_setups_without_smt(self, pipeline_data):
        """detect_setups_base works without ES data."""
        m1, s, c, _, _ = pipeline_data
        cfg = ms.MODELS['1H_5M']
        rows, pending = ms.detect_setups_base(
            m1, s, c, '1H_5M', cfg,
            cisd_fast_bars=None, es_s_arrs=None, es_m1_arrs=None
        )
        assert isinstance(rows, list)

    def test_smt_field_present(self, pipeline_data):
        """Detected setups have smt field."""
        m1, s, c, es_s, es_m1 = pipeline_data
        cfg = ms.MODELS['1H_5M']
        rows, pending = ms.detect_setups_base(
            m1, s, c, '1H_5M', cfg,
            cisd_fast_bars=None, es_s_arrs=es_s, es_m1_arrs=es_m1
        )
        if rows:
            assert 'smt' in rows[0]

    def test_apply_profile_structural(self, pipeline_data):
        """Full pipeline: detect → resolve with structural profile."""
        m1, s, c, es_s, es_m1 = pipeline_data
        cfg = ms.MODELS['1H_5M']
        rows, pending = ms.detect_setups_base(
            m1, s, c, '1H_5M', cfg,
            cisd_fast_bars=None, es_s_arrs=es_s, es_m1_arrs=es_m1
        )
        if not pending:
            pytest.skip("No setups detected in test data")

        df = ms.apply_profile_and_resolve(
            rows, pending, m1,
            stop_val=1.0, target_val=1.0,
            profile_type='structural'
        )
        assert not df.empty
        assert 'outcome' in df.columns
        assert 'r' in df.columns
        assert 'smt' in df.columns

    def test_apply_profile_split_tp(self, pipeline_data):
        """Full pipeline: detect → resolve with split_tp profile."""
        m1, s, c, es_s, es_m1 = pipeline_data
        cfg = ms.MODELS['1H_5M']
        rows, pending = ms.detect_setups_base(
            m1, s, c, '1H_5M', cfg,
            cisd_fast_bars=None, es_s_arrs=es_s, es_m1_arrs=es_m1
        )
        if not pending:
            pytest.skip("No setups detected in test data")

        df = ms.apply_profile_and_resolve(
            rows, pending, m1,
            stop_val=1.0, target_val=0.42,
            profile_type='split_tp',
            sl_mae_pct=0.30
        )
        assert not df.empty

    def test_build_model_stats_from_pipeline(self, pipeline_data):
        """Full pipeline: detect → resolve → build_model_stats."""
        m1, s, c, es_s, es_m1 = pipeline_data
        cfg = ms.MODELS['1H_5M']
        rows, pending = ms.detect_setups_base(
            m1, s, c, '1H_5M', cfg,
            cisd_fast_bars=None, es_s_arrs=es_s, es_m1_arrs=es_m1
        )
        if not pending:
            pytest.skip("No setups detected in test data")

        df = ms.apply_profile_and_resolve(
            rows, pending, m1,
            stop_val=1.0, target_val=1.0,
            profile_type='structural'
        )
        if df.empty:
            pytest.skip("No resolved trades")

        stats = ms.build_model_stats(
            df, 2, '1H_5M', cfg,
            stop_mult=1.0, target_mult=1.0,
            profile_key='structural_dynamic',
            profile_type='structural'
        )
        assert 'meta' in stats
        assert 'by_hour' in stats
        assert 'recent_trades' in stats
        assert 'smt_summary' in stats
        assert 'risk_stats' in stats

    def test_compute_filter_impact_from_pipeline(self, pipeline_data):
        """Full pipeline: detect → compute_filter_impact."""
        m1, s, c, es_s, es_m1 = pipeline_data
        cfg = ms.MODELS['1H_5M']
        rows, pending = ms.detect_setups_base(
            m1, s, c, '1H_5M', cfg,
            cisd_fast_bars=None, es_s_arrs=es_s, es_m1_arrs=es_m1
        )
        if not rows:
            pytest.skip("No rows detected")

        # Need to resolve first to populate outcomes
        df = ms.apply_profile_and_resolve(
            rows, pending, m1,
            stop_val=1.0, target_val=1.0,
            profile_type='structural'
        )
        if df.empty:
            pytest.skip("No resolved trades")

        impact = ms.compute_filter_impact(df)
        assert isinstance(impact, list)
        assert len(impact) >= 1  # at least baseline
        assert impact[0]['label'] == 'Baseline (unfiltered)'


# ── 30M_3M model ────────────────────────────────────────────────────────────

class TestOtherModels:
    def test_30m_3m_detection(self, nq_data, es_data):
        """30M_3M model runs on real data."""
        _, nq_rth = nq_data
        _, es_rth = es_data

        sweep_df = ms.resample(nq_rth, 30, '30min')
        cisd_df = ms.resample(nq_rth, 3, '3min')
        es_sweep_df = ms.resample(es_rth, 30, 'ES_30min')

        s = ms.df_to_arrays(sweep_df)
        c = ms.df_to_arrays(cisd_df)
        m1 = ms.df_1m_to_arrays(nq_rth)
        es_s = ms.df_to_arrays(es_sweep_df)
        es_m1 = ms.df_1m_to_arrays(es_rth)

        cfg = ms.MODELS['30M_3M']
        rows, pending = ms.detect_setups_base(
            m1, s, c, '30M_3M', cfg,
            cisd_fast_bars=None, es_s_arrs=es_s, es_m1_arrs=es_m1
        )
        assert isinstance(rows, list)
        print(f"  30M_3M: {len(rows)} rows, {len(pending)} pending")


# ── JSON serialization ───────────────────────────────────────────────────────

class TestJsonOutput:
    def test_stats_json_serializable(self, nq_data, es_data):
        """build_model_stats output is JSON-serializable."""
        _, nq_rth = nq_data
        _, es_rth = es_data

        sweep_df = ms.resample(nq_rth, 60, '60min')
        cisd_df = ms.resample(nq_rth, 5, '5min')
        es_sweep_df = ms.resample(es_rth, 60, 'ES_60min')

        s = ms.df_to_arrays(sweep_df)
        c = ms.df_to_arrays(cisd_df)
        m1 = ms.df_1m_to_arrays(nq_rth)
        es_s = ms.df_to_arrays(es_sweep_df)
        es_m1 = ms.df_1m_to_arrays(es_rth)

        cfg = ms.MODELS['1H_5M']
        rows, pending = ms.detect_setups_base(
            m1, s, c, '1H_5M', cfg,
            cisd_fast_bars=None, es_s_arrs=es_s, es_m1_arrs=es_m1
        )
        if not pending:
            pytest.skip("No setups")

        df = ms.apply_profile_and_resolve(
            rows, pending, m1,
            stop_val=1.0, target_val=1.0,
            profile_type='structural'
        )
        if df.empty:
            pytest.skip("No trades")

        stats = ms.build_model_stats(
            df, 2, '1H_5M', cfg,
            stop_mult=1.0, target_mult=1.0,
            profile_key='test', profile_type='structural'
        )

        # Should be JSON-serializable
        json_str = json.dumps(stats, default=str)
        assert len(json_str) > 100
        parsed = json.loads(json_str)
        assert 'meta' in parsed
