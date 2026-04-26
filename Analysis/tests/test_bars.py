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


def test_prev_hour_columns_for_consecutive_hours():
    """Two adjacent hours: H2's prev_hour_* should equal H1's OHLC."""
    h1 = helpers.make_hour('2024-01-02 10:00', ohlc=(100, 110, 90, 105),
                           high_at_minute=20, low_at_minute=40)
    h2 = helpers.make_hour('2024-01-02 11:00', ohlc=(105, 115, 95, 110),
                           high_at_minute=10, low_at_minute=30)
    minutes = helpers.concat_hours(h1, h2)
    hourly = bars.build_hourly(bars._enrich_minutes(minutes))
    hourly = bars.attach_prev_hour(hourly)
    h2_row = hourly.iloc[1]
    assert h2_row['prev_hour_open'] == 100
    assert h2_row['prev_hour_high'] == 110
    assert h2_row['prev_hour_low'] == 90
    assert h2_row['prev_hour_close'] == 105
    assert h2_row['prev_hour_mid'] == 100.0  # (110 + 90) / 2


def test_prev_hour_skips_settlement_gap():
    """18:00 hour's prev_hour_* should equal previous day's 16:00 (skipping 17:00)."""
    h16 = helpers.make_hour('2024-01-02 16:00', ohlc=(200, 210, 190, 205),
                            high_at_minute=20, low_at_minute=40)
    h18 = helpers.make_hour('2024-01-02 18:00', ohlc=(205, 215, 195, 210),
                            high_at_minute=10, low_at_minute=30)
    minutes = helpers.concat_hours(h16, h18)
    hourly = bars.build_hourly(bars._enrich_minutes(minutes))
    hourly = bars.attach_prev_hour(hourly)
    h18_row = hourly[hourly['hour_of_day_et'] == 18].iloc[0]
    assert h18_row['prev_hour_high'] == 210
    assert h18_row['prev_hour_low'] == 190


def test_prev_hour_skips_weekend_gap():
    """Sun 18:00 hour's prev_hour_* should equal Fri 16:00's OHLC."""
    fri_16 = helpers.make_hour('2024-01-05 16:00', ohlc=(300, 310, 290, 305),
                               high_at_minute=20, low_at_minute=40)
    sun_18 = helpers.make_hour('2024-01-07 18:00', ohlc=(305, 315, 295, 310),
                               high_at_minute=10, low_at_minute=30)
    minutes = helpers.concat_hours(fri_16, sun_18)
    hourly = bars.build_hourly(bars._enrich_minutes(minutes))
    hourly = bars.attach_prev_hour(hourly)
    # Sunday in Python = dow 6
    sun_row = hourly[hourly['dow'] == 6].iloc[0]
    assert sun_row['prev_hour_high'] == 310
    assert sun_row['prev_hour_low'] == 290


def test_first_row_has_null_prev_hour():
    h1 = helpers.make_hour('2024-01-02 10:00')
    hourly = bars.build_hourly(bars._enrich_minutes(h1))
    hourly = bars.attach_prev_hour(hourly)
    assert pd.isna(hourly['prev_hour_high'].iloc[0])
