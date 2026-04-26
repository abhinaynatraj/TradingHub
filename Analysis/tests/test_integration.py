"""End-to-end smoke test against the real DuckDB.

Skipped automatically if the DB file is missing (CI environments without it).
Runs against a small recent slice so it stays fast.
"""
import json
from pathlib import Path
import pytest
import bars
import run_all


pytestmark = pytest.mark.skipif(
    not bars.db_path().exists(),
    reason=f"shared DuckDB not found at {bars.db_path()}"
)


def test_run_all_against_recent_slice(tmp_path, monkeypatch):
    """Run the engine against a 1-month slice; assert outputs land + are sane."""
    # Redirect run_all.HERE so its output goes to tmp_path/engine,
    # which means HERE.parent / 'data' = tmp_path / 'data'.
    fake_engine = tmp_path / 'engine'
    fake_engine.mkdir()
    monkeypatch.setattr(run_all, 'HERE', fake_engine)

    run_all.main(start='2025-09-01', end='2025-10-01')

    data_root = tmp_path / 'data'
    assert (data_root / 'manifest.json').exists()
    manifest = json.loads((data_root / 'manifest.json').read_text())
    assert manifest['total_hours'] > 0
    assert manifest['schema_version'] == 1
    assert manifest['n_bullish_breakouts'] > 0
    assert manifest['n_bearish_breakouts'] > 0

    # Critical files
    assert (data_root / 'breakout' / 'breakouts.parquet').exists()
    assert (data_root / 'breakout' / 'summary_aggregate.parquet').exists()
    assert (data_root / 'quarters' / 'quarter_features.parquet').exists()
    assert (data_root / 'quarters' / 'study_a_aggregate.parquet').exists()

    # No NaNs in critical prev-hour columns (after the first row)
    import pandas as pd
    breakouts = pd.read_parquet(data_root / 'breakout' / 'breakouts.parquet')
    # After the first row, prev_hour_high should be non-null
    non_first = breakouts.iloc[1:]
    assert non_first['prev_hour_high'].notna().all()
    assert non_first['prev_hour_low'].notna().all()
    assert non_first['prev_hour_mid'].notna().all()


def test_breakout_summary_aggregate_has_expected_columns(tmp_path, monkeypatch):
    """The breakout summary_aggregate.parquet has the expected metric columns."""
    fake_engine = tmp_path / 'engine'
    fake_engine.mkdir()
    monkeypatch.setattr(run_all, 'HERE', fake_engine)
    run_all.main(start='2025-09-01', end='2025-10-01')

    import pandas as pd
    s = pd.read_parquet(tmp_path / 'data' / 'breakout' / 'summary_aggregate.parquet')
    assert len(s) == 1
    expected_cols = {'count', 'n_total', 'n_classifiable', 'n_bullish', 'n_bearish',
                     'bullish_breakout_rate', 'bearish_breakout_rate',
                     'bullish_followthrough_rate', 'bearish_followthrough_rate'}
    assert expected_cols.issubset(s.columns)


def test_study_e_overshoot_metrics_are_populated(tmp_path, monkeypatch):
    """Regression test: study_e_metric overshoot was silently NaN due to a
    column-name mismatch (looked for 'hour_high', engine produced 'high').
    This test reads the production parquet and asserts the metric is populated.
    """
    fake_engine = tmp_path / 'engine'
    fake_engine.mkdir()
    monkeypatch.setattr(run_all, 'HERE', fake_engine)
    run_all.main(start='2025-09-01', end='2025-10-01')

    import pandas as pd
    s = pd.read_parquet(tmp_path / 'data' / 'quarters' / 'study_e_aggregate.parquet')
    # Both metrics should be populated (not NaN)
    assert s['q1_high_fail_overshoot_mean'].notna().all(), (
        "q1_high_fail_overshoot_mean is NaN — likely the column-name mismatch "
        "between build_features (which produces 'high') and study_e_metric "
        "(which reads 'hour_high') has reappeared.")
    assert s['q1_high_fail_overshoot_median'].notna().all()
    # And positive (overshoot must be > 0 by definition)
    assert (s['q1_high_fail_overshoot_mean'] > 0).all()
    assert (s['q1_high_fail_overshoot_median'] > 0).all()
