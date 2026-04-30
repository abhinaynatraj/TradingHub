"""Tests for Analysis/engine/slicers.py."""
import pandas as pd
import pytest
import slicers


def _sample_df():
    return pd.DataFrame({
        'year': [2024, 2024, 2025, 2025, 2025],
        'dow': [0, 1, 0, 1, 2],
        'hour_of_day_et': [10, 10, 11, 11, 12],
        'value': [1, 2, 3, 4, 5],
    })


def _mean_metric(sub: pd.DataFrame) -> dict:
    return {'avg': sub['value'].mean()}


def test_slice_aggregate_returns_one_row():
    out = slicers.slice_aggregate(_sample_df(), _mean_metric)
    assert len(out) == 1
    assert out['avg'].iloc[0] == 3.0
    assert out['count'].iloc[0] == 5


def test_slice_by_year_returns_one_row_per_year():
    out = slicers.slice_by_year(_sample_df(), _mean_metric)
    assert len(out) == 2
    assert set(out['year']) == {2024, 2025}
    row_2024 = out[out['year'] == 2024].iloc[0]
    assert row_2024['count'] == 2
    assert row_2024['avg'] == 1.5


def test_slice_by_hour_returns_one_row_per_hour():
    out = slicers.slice_by_hour(_sample_df(), _mean_metric)
    assert set(out['hour_of_day_et']) == {10, 11, 12}


def test_slice_by_dow_returns_one_row_per_dow():
    out = slicers.slice_by_dow(_sample_df(), _mean_metric)
    assert set(out['dow']) == {0, 1, 2}


def test_slice_by_hour_dow_grid():
    out = slicers.slice_by_hour_dow(_sample_df(), _mean_metric)
    # 5 unique (hour, dow) combos in the sample
    assert len(out) == 5
    assert {'hour_of_day_et', 'dow', 'count', 'avg'}.issubset(out.columns)


def test_count_column_always_present():
    out = slicers.slice_by_year(_sample_df(), _mean_metric)
    assert 'count' in out.columns


def test_metric_fn_returning_reserved_count_raises():
    def bad_metric(sub):
        return {'count': 99}  # collides with auto-attached count

    with pytest.raises(ValueError, match='count'):
        slicers.slice_aggregate(_sample_df(), bad_metric)
    with pytest.raises(ValueError, match='count'):
        slicers.slice_by_year(_sample_df(), bad_metric)


def test_metric_fn_returning_slice_key_raises():
    def bad_metric(sub):
        return {'year': 9999}  # collides with the groupby key column

    with pytest.raises(ValueError, match='year'):
        slicers.slice_by_year(_sample_df(), bad_metric)
