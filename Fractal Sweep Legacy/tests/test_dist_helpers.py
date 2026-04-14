"""Tests for distribution helper functions: _dist_stats, _lognorm_fit, _clusters."""
import pandas as pd
import numpy as np
import pytest
import model_stats as ms


class TestDistStats:
    def test_basic_output(self):
        """Returns dict with expected keys."""
        vals = pd.Series(np.random.RandomState(42).uniform(0.05, 0.5, 100))
        result = ms._dist_stats(vals)
        assert 'count' in result
        assert 'mean' in result
        assert 'p50' in result  # _dist_stats uses p50, not 'median'
        assert 'p90' in result
        assert 'hist' in result
        assert 'mode' in result

    def test_empty_series(self):
        """Empty series → empty dict."""
        result = ms._dist_stats(pd.Series(dtype='float64'))
        assert result == {}

    def test_all_zeros(self):
        """All zeros → empty (filtered by > 0)."""
        result = ms._dist_stats(pd.Series([0.0, 0.0, 0.0]))
        assert result == {}

    def test_single_value(self):
        """Single positive value → valid output."""
        result = ms._dist_stats(pd.Series([0.5]))
        assert result['count'] == 1
        assert result['mean'] == 0.5

    def test_percentile_ordering(self):
        """Percentiles are in ascending order."""
        vals = pd.Series(np.random.RandomState(42).uniform(0.05, 2.0, 200))
        result = ms._dist_stats(vals)
        assert result['p10'] <= result['p25']
        assert result['p25'] <= result['p50']
        assert result['p50'] <= result['p75']
        assert result['p75'] <= result['p90']
        assert result['p90'] <= result['p95']

    def test_histogram_bins(self):
        """Histogram has correct number of bins."""
        vals = pd.Series(np.random.RandomState(42).uniform(0.05, 0.5, 100))
        result = ms._dist_stats(vals, n_bins=20)
        assert len(result['hist']) == 20


class TestLognormFit:
    def test_basic_fit(self):
        """Returns dict with mu, sigma, goodness."""
        vals = np.random.RandomState(42).lognormal(0.5, 0.3, 100)
        result = ms._lognorm_fit(vals)
        assert 'mu' in result
        assert 'sigma' in result
        assert 'goodness' in result
        assert 'implied_median' in result

    def test_too_few_values(self):
        """Fewer than 5 values → empty dict."""
        result = ms._lognorm_fit(np.array([0.5, 0.6, 0.7]))
        assert result == {}

    def test_goodness_reasonable(self):
        """Goodness of fit for actual lognormal data should be high."""
        vals = np.random.RandomState(42).lognormal(0.5, 0.3, 500)
        result = ms._lognorm_fit(vals)
        assert result['goodness'] > 0.9  # should fit well


class TestClusters:
    def test_returns_3_clusters(self):
        """Always returns 3 clusters."""
        vals = pd.Series(np.random.RandomState(42).uniform(0.05, 1.0, 100))
        result = ms._clusters(vals, len(vals))
        assert len(result) == 3

    def test_cluster_labels(self):
        """Clusters have expected labels."""
        vals = pd.Series(np.random.RandomState(42).uniform(0.05, 1.0, 100))
        result = ms._clusters(vals, len(vals))
        labels = [c['label'] for c in result]
        assert 'Tight' in labels
        assert 'Moderate' in labels
        assert 'Wide' in labels

    def test_cluster_sum(self):
        """Total n across clusters ≈ input count."""
        vals = pd.Series(np.random.RandomState(42).uniform(0.05, 1.0, 100))
        result = ms._clusters(vals, len(vals))
        total = sum(c['n'] for c in result)
        assert total == len(vals)
