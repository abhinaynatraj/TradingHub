"""Tests for Analysis/engine/bars.py."""
import pandas as pd
import pytest
import bars
import helpers


def test_db_path_resolves_to_fractal_sweep_duckdb():
    p = bars.db_path()
    assert p.name == 'candle_science.duckdb'
    assert p.parent.name == 'Fractal Sweep'


def test_load_minutes_from_df_adds_ny_columns():
    raw = helpers.make_minutes('2024-01-02 10:00', 3)
    df = bars._enrich_minutes(raw)
    assert 'ny_ts' in df.columns
    assert str(df['ny_ts'].dt.tz) == 'America/New_York'
    # First bar at 10:00 ET → year/dow/hour
    assert df['year'].iloc[0] == 2024
    assert df['hour_of_day_et'].iloc[0] == 10
    # 2024-01-02 is Tuesday → Python dow = 1
    assert df['dow'].iloc[0] == 1
