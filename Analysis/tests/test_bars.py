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


def test_hourly_ohlc_matches_synthetic():
    minutes = helpers.make_hour('2024-01-02 10:00', ohlc=(100, 110, 90, 105),
                                high_at_minute=20, low_at_minute=40)
    minutes = bars._enrich_minutes(minutes)
    hourly = bars.build_hourly(minutes)
    assert len(hourly) == 1
    row = hourly.iloc[0]
    assert row['open'] == 100
    assert row['high'] == 110
    assert row['low'] == 90
    assert row['close'] == 105
    assert row['volume'] == 600
    assert row['hour_start_et'] == pd.Timestamp('2024-01-02 10:00', tz='America/New_York')


def test_hourly_drops_incomplete_hour():
    """An hour with only 59 minutes should be dropped."""
    minutes = helpers.make_hour('2024-01-02 10:00')
    minutes = minutes.iloc[:59].copy()  # remove last minute
    minutes = bars._enrich_minutes(minutes)
    hourly = bars.build_hourly(minutes)
    assert len(hourly) == 0


def test_hourly_drops_17_et_settlement_hour():
    """The 17:00 ET hour is always excluded even if data is present."""
    h17 = helpers.make_hour('2024-01-02 17:00')
    h18 = helpers.make_hour('2024-01-02 18:00')
    minutes = helpers.concat_hours(h17, h18)
    minutes = bars._enrich_minutes(minutes)
    hourly = bars.build_hourly(minutes)
    assert len(hourly) == 1
    assert hourly['hour_of_day_et'].iloc[0] == 18
