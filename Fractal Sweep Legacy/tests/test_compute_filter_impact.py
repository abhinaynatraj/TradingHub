"""Tests for compute_filter_impact()."""
import pandas as pd
import numpy as np
import pytest
import model_stats as ms


def _make_filtered_df():
    """Build a DataFrame with various rejection codes."""
    rows = [
        # Valid trades
        *[dict(outcome='WIN', r=1.0, rejected_by='', win=1) for _ in range(50)],
        *[dict(outcome='LOSS', r=-1.0, rejected_by='', win=0) for _ in range(20)],
        # Rejected trades
        *[dict(outcome='SKIP', r=0.0, rejected_by='F1_SMALL_RANGE', win=0) for _ in range(10)],
        *[dict(outcome='SKIP', r=0.0, rejected_by='F3_SWEEP_TOO_LARGE', win=0) for _ in range(8)],
        *[dict(outcome='SKIP', r=0.0, rejected_by='F4_NO_CLOSE_BACK', win=0) for _ in range(5)],
        *[dict(outcome='SKIP', r=0.0, rejected_by='NO_CISD', win=0) for _ in range(15)],
        *[dict(outcome='INVALID', r=0.0, rejected_by='INVALID_RISK', win=0) for _ in range(3)],
        *[dict(outcome='INVALID', r=0.0, rejected_by='RISK_TOO_LARGE', win=0) for _ in range(4)],
    ]
    return pd.DataFrame(rows)


class TestComputeFilterImpact:
    def test_returns_list(self):
        df = _make_filtered_df()
        result = ms.compute_filter_impact(df)
        assert isinstance(result, list)

    def test_baseline_first(self):
        """First entry is baseline (unfiltered)."""
        df = _make_filtered_df()
        result = ms.compute_filter_impact(df)
        assert result[0]['label'] == 'Baseline (unfiltered)'
        assert result[0]['n'] > 0

    def test_filters_in_order(self):
        """Filters appear in expected order."""
        df = _make_filtered_df()
        result = ms.compute_filter_impact(df)
        filter_codes = [r.get('filter_code') for r in result[1:] if 'filter_code' in r]
        expected_order = ['F1_SMALL_RANGE', 'F3_SWEEP_TOO_LARGE', 'F4_NO_CLOSE_BACK',
                          'NO_CISD', 'INVALID_RISK', 'RISK_TOO_LARGE']
        for code in filter_codes:
            assert code in expected_order

    def test_removed_counts(self):
        """Each filter step reports how many trades were removed."""
        df = _make_filtered_df()
        result = ms.compute_filter_impact(df)
        for r in result[1:]:
            assert 'removed' in r
            assert r['removed'] > 0

    def test_n_decreases(self):
        """Trade count decreases as filters are applied."""
        df = _make_filtered_df()
        result = ms.compute_filter_impact(df)
        prev_n = result[0]['n']
        for r in result[1:]:
            assert r['n'] <= prev_n
            prev_n = r['n']

    def test_empty_df(self):
        """Empty DataFrame → baseline with 0 trades."""
        df = pd.DataFrame({'outcome': [], 'r': [], 'rejected_by': [], 'win': []})
        result = ms.compute_filter_impact(df)
        assert result[0]['n'] == 0

    def test_no_rejected(self):
        """All valid trades → only baseline returned."""
        df = pd.DataFrame({
            'outcome': ['WIN'] * 10,
            'r': [1.0] * 10,
            'rejected_by': [''] * 10,
            'win': [1] * 10,
        })
        result = ms.compute_filter_impact(df)
        # Only baseline, no filter steps (nothing to remove)
        assert len(result) == 1
        assert result[0]['n'] == 10
