"""Sanity check for the helpers themselves."""
import helpers


def test_make_hour_aggregates_correctly():
    df = helpers.make_hour('2024-01-02 10:00', ohlc=(100, 110, 90, 105),
                           high_at_minute=20, low_at_minute=40)
    assert len(df) == 60
    assert df['open'].iloc[0] == 100
    assert df['close'].iloc[59] == 105
    assert df['high'].max() == 110
    assert df['low'].min() == 90
    # Volume: 10 * 60
    assert df['volume'].sum() == 600


def test_make_minutes_default_pattern():
    df = helpers.make_minutes('2024-01-02 10:00', 5)
    assert len(df) == 5
    assert df['open'].iloc[0] == 100.0
    assert df['open'].iloc[4] == 104.0
