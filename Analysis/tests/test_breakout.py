"""Tests for Analysis/engine/breakout_study.py."""
import pandas as pd
import pytest
import breakout_study as bs
import bars
import helpers


def _build_pair(h1_ohlc, h2_ohlc, h1_high_min=20, h1_low_min=40,
                h2_high_min=20, h2_low_min=40):
    h0 = helpers.make_hour('2024-01-02 09:00', ohlc=(100, 105, 95, 100),
                           high_at_minute=20, low_at_minute=40)
    h1 = helpers.make_hour('2024-01-02 10:00', ohlc=h1_ohlc,
                           high_at_minute=h1_high_min, low_at_minute=h1_low_min)
    h2 = helpers.make_hour('2024-01-02 11:00', ohlc=h2_ohlc,
                           high_at_minute=h2_high_min, low_at_minute=h2_low_min)
    minutes = helpers.concat_hours(h0, h1, h2)
    enriched = bars._enrich_minutes(minutes)
    hourly, quarters = bars.build_all_from_minutes(enriched)
    return enriched, hourly, quarters


def test_classify_bullish_breakout():
    """H1.close > H0.high → bullish."""
    # H0 high = 105; H1 close = 110 > 105
    _, hourly, _ = _build_pair((100, 115, 95, 110), (110, 120, 100, 115))
    result = bs.classify(hourly)
    h1 = result.iloc[1]
    assert h1['breakout'] == 'bullish'


def test_classify_bearish_breakout():
    """H1.close < H0.low → bearish."""
    # H0 low = 95; H1 close = 90 < 95
    _, hourly, _ = _build_pair((100, 105, 85, 90), (90, 95, 80, 85))
    result = bs.classify(hourly)
    assert result.iloc[1]['breakout'] == 'bearish'


def test_classify_strict_inequality_equal_is_neither():
    """H1.close == H0.high → neither (strict)."""
    # H0 high = 105; H1 close = 105 exactly
    _, hourly, _ = _build_pair((100, 110, 95, 105), (105, 115, 100, 110))
    result = bs.classify(hourly)
    assert result.iloc[1]['breakout'] == 'neither'


def test_classify_inside_bar_is_neither():
    """H1.high < H0.high AND H1.low > H0.low → inside bar → neither."""
    # H0: 95-105; H1: 97-103 (inside)
    _, hourly, _ = _build_pair((100, 103, 97, 100), (100, 110, 95, 105))
    result = bs.classify(hourly)
    assert result.iloc[1]['breakout'] == 'neither'


def test_classify_first_row_excluded():
    """First row has null prev_hour and is excluded from classification."""
    h0 = helpers.make_hour('2024-01-02 10:00')
    enriched = bars._enrich_minutes(h0)
    hourly, _ = bars.build_all_from_minutes(enriched)
    result = bs.classify(hourly)
    # First (only) row has null prev_hour_high → not classified
    assert result.iloc[0]['breakout'] == 'no_prev'
    # Also verify h1_open_vs_prev_mid is null for no_prev rows
    assert pd.isna(result.iloc[0]['h1_open_vs_prev_mid'])


def test_followthrough_bullish_takeout_in_q1_of_h2():
    """H1 close > H0 high (bullish). H2 prints higher high at minute 7 (Q1)."""
    # H0 high=105, H1 high=115/close=110, H2 high=120 at minute 7
    h0 = helpers.make_hour('2024-01-02 09:00', ohlc=(100, 105, 95, 100),
                           high_at_minute=20, low_at_minute=40)
    h1 = helpers.make_hour('2024-01-02 10:00', ohlc=(100, 115, 95, 110),
                           high_at_minute=30, low_at_minute=40)
    h2 = helpers.make_hour('2024-01-02 11:00', ohlc=(110, 120, 105, 115),
                           high_at_minute=7, low_at_minute=40)
    minutes = helpers.concat_hours(h0, h1, h2)
    enriched = bars._enrich_minutes(minutes)
    hourly, _ = bars.build_all_from_minutes(enriched)
    classified = bs.classify(hourly)
    events = bs.attach_followthrough(classified, enriched)
    # H1 (row 1) is bullish breakout; followthrough should be True; q = 1
    h1_row = events.iloc[1]
    assert h1_row['breakout'] == 'bullish'
    assert h1_row['followthrough'] == True
    assert h1_row['takeout_quarter_of_h2'] == 1


def test_followthrough_bullish_takeout_in_q2():
    """Higher high in H2 first occurs at minute 16 → Q2."""
    h0 = helpers.make_hour('2024-01-02 09:00', ohlc=(100, 105, 95, 100),
                           high_at_minute=20, low_at_minute=40)
    h1 = helpers.make_hour('2024-01-02 10:00', ohlc=(100, 115, 95, 110),
                           high_at_minute=30, low_at_minute=40)
    h2 = helpers.make_hour('2024-01-02 11:00', ohlc=(110, 120, 105, 115),
                           high_at_minute=16, low_at_minute=40)
    minutes = helpers.concat_hours(h0, h1, h2)
    enriched = bars._enrich_minutes(minutes)
    hourly, _ = bars.build_all_from_minutes(enriched)
    events = bs.attach_followthrough(bs.classify(hourly), enriched)
    assert events.iloc[1]['takeout_quarter_of_h2'] == 2


def test_followthrough_strict_no_takeout_when_equal():
    """H2.high == H1.high (no strict break) → not a takeout."""
    h0 = helpers.make_hour('2024-01-02 09:00', ohlc=(100, 105, 95, 100),
                           high_at_minute=20, low_at_minute=40)
    h1 = helpers.make_hour('2024-01-02 10:00', ohlc=(100, 115, 95, 110),
                           high_at_minute=30, low_at_minute=40)
    # H2 high equals H1 high (115) — exactly, no strict break
    h2 = helpers.make_hour('2024-01-02 11:00', ohlc=(110, 115, 105, 112),
                           high_at_minute=10, low_at_minute=40)
    minutes = helpers.concat_hours(h0, h1, h2)
    enriched = bars._enrich_minutes(minutes)
    hourly, _ = bars.build_all_from_minutes(enriched)
    events = bs.attach_followthrough(bs.classify(hourly), enriched)
    assert events.iloc[1]['followthrough'] == False
    assert pd.isna(events.iloc[1]['takeout_quarter_of_h2'])


def test_immediate_reversal_bullish_breakout_takes_out_h1_low():
    """Bullish H1 breakout, but H2 takes out H1's low → immediate_reversal=True."""
    h0 = helpers.make_hour('2024-01-02 09:00', ohlc=(100, 105, 95, 100),
                           high_at_minute=20, low_at_minute=40)
    # H1 bullish breakout: H1 close 110 > H0 high 105
    h1 = helpers.make_hour('2024-01-02 10:00', ohlc=(100, 115, 95, 110),
                           high_at_minute=30, low_at_minute=40)
    # H2 prints below H1.low (95) at some minute — H2 low = 90
    h2 = helpers.make_hour('2024-01-02 11:00', ohlc=(110, 112, 90, 100),
                           high_at_minute=5, low_at_minute=20)
    minutes = helpers.concat_hours(h0, h1, h2)
    enriched = bars._enrich_minutes(minutes)
    hourly, _ = bars.build_all_from_minutes(enriched)
    events = bs.attach_followthrough(bs.classify(hourly), enriched)
    h1_row = events.iloc[1]
    assert h1_row['breakout'] == 'bullish'
    assert h1_row['immediate_reversal'] == True
