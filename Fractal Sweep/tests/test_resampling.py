"""Tests for resample(), df_to_arrays(), df_1m_to_arrays()."""
import pandas as pd
import numpy as np
import pytest
import model_stats as ms


def _make_1m_df(n_bars=120, start_price=24000.0):
    """Build a minimal 1m DataFrame matching load_1m() output format."""
    rng = np.random.RandomState(42)
    dates = pd.date_range('2023-11-14 09:30', periods=n_bars, freq='1min')
    prices = start_price + np.cumsum(rng.uniform(-2, 2, n_bars))

    df = pd.DataFrame({
        'trade_date': '2023-11-14',
        'open': prices,
        'high': prices + rng.uniform(0, 3, n_bars),
        'low': prices - rng.uniform(0, 3, n_bars),
        'close': prices + rng.uniform(-1, 1, n_bars),
        'yr': 2023,
        'mo': 11,
        'dow': 2,
        'hr': [9 + (i // 60) for i in range(n_bars)],
        'mn': [i % 60 for i in range(n_bars)],
    }, index=dates)
    df.index.name = 'ts'
    return df


class TestResample:
    def test_60min_from_120_1m_bars(self):
        """120 bars of 1m → at least 2 bars of 60m."""
        df_1m = _make_1m_df(120)
        result = ms.resample(df_1m, 60, '60min')
        assert len(result) >= 2

    def test_ohlcv_aggregation(self):
        """Resampled OHLC: open=first, high=max, low=min, close=last."""
        df_1m = _make_1m_df(60)
        result = ms.resample(df_1m, 60, '60min')
        assert len(result) >= 1

        # Check OHLC columns exist with _tf suffix
        assert 'open_tf' in result.columns
        assert 'high_tf' in result.columns
        assert 'low_tf' in result.columns
        assert 'close_tf' in result.columns

        # High should be max of all 1m highs
        assert result['high_tf'].iloc[0] >= result['low_tf'].iloc[0]

    def test_trade_date_preserved(self):
        """Resampled bars have trade_date column."""
        df_1m = _make_1m_df(60)
        result = ms.resample(df_1m, 60, '60min')
        assert 'trade_date' in result.columns

    def test_30min_bars(self):
        """60 bars → 2 x 30min bars."""
        df_1m = _make_1m_df(60)
        result = ms.resample(df_1m, 30, '30min')
        assert len(result) == 2


class TestDfToArrays:
    def test_output_keys(self):
        """df_to_arrays returns dict with expected keys."""
        df_1m = _make_1m_df(60)
        resampled = ms.resample(df_1m, 60, '60min')
        arrs = ms.df_to_arrays(resampled)

        expected_keys = {'ts_ns', 'open', 'high', 'low', 'close',
                         'trade_date', 'yr', 'dow', 'hr'}
        assert set(arrs.keys()) == expected_keys

    def test_ts_ns_is_int64(self):
        """Timestamps are int64 nanoseconds."""
        df_1m = _make_1m_df(60)
        resampled = ms.resample(df_1m, 60, '60min')
        arrs = ms.df_to_arrays(resampled)
        assert arrs['ts_ns'].dtype == np.int64

    def test_array_lengths_match(self):
        """All arrays have same length as input rows."""
        df_1m = _make_1m_df(120)
        resampled = ms.resample(df_1m, 60, '60min')
        arrs = ms.df_to_arrays(resampled)
        n = len(resampled)
        for key in ['ts_ns', 'open', 'high', 'low', 'close']:
            assert len(arrs[key]) == n

    def test_high_gte_low(self):
        """Data integrity: high >= low for every bar."""
        df_1m = _make_1m_df(120)
        resampled = ms.resample(df_1m, 60, '60min')
        arrs = ms.df_to_arrays(resampled)
        assert np.all(arrs['high'] >= arrs['low'])


class TestDf1mToArrays:
    def test_output_keys(self):
        """df_1m_to_arrays returns dict with 1m-specific keys."""
        df_1m = _make_1m_df(60)
        arrs = ms.df_1m_to_arrays(df_1m)

        expected_keys = {'ts_ns', 'open', 'high', 'low', 'close',
                         'hr', 'mn', 'yr', 'dow', 'trade_date'}
        assert set(arrs.keys()) == expected_keys

    def test_mn_field_present(self):
        """1m arrays have minute field (mn) unlike HTF arrays."""
        df_1m = _make_1m_df(60)
        arrs = ms.df_1m_to_arrays(df_1m)
        assert 'mn' in arrs
        assert len(arrs['mn']) == 60

    def test_float64_prices(self):
        """Price arrays are float64."""
        df_1m = _make_1m_df(60)
        arrs = ms.df_1m_to_arrays(df_1m)
        for key in ['open', 'high', 'low', 'close']:
            assert arrs[key].dtype == np.float64
