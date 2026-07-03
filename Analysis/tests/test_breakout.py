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


def test_followthrough_bearish_takeout_in_q3():
    """Bearish breakout: H1.close < H0.low. H2 prints lower low at minute 32 (Q3)."""
    # H0 low=95, H1 low=85/close=88 (< 95), H2 low=80 at minute 32
    h0 = helpers.make_hour('2024-01-02 09:00', ohlc=(100, 105, 95, 100),
                           high_at_minute=20, low_at_minute=40)
    h1 = helpers.make_hour('2024-01-02 10:00', ohlc=(100, 105, 85, 88),
                           high_at_minute=10, low_at_minute=50)
    h2 = helpers.make_hour('2024-01-02 11:00', ohlc=(88, 92, 80, 85),
                           high_at_minute=5, low_at_minute=32)
    minutes = helpers.concat_hours(h0, h1, h2)
    enriched = bars._enrich_minutes(minutes)
    hourly, _ = bars.build_all_from_minutes(enriched)
    events = bs.attach_followthrough(bs.classify(hourly), enriched)
    h1_row = events.iloc[1]
    assert h1_row['breakout'] == 'bearish'
    assert h1_row['followthrough'] == True
    assert h1_row['takeout_quarter_of_h2'] == 3


def test_followthrough_no_takeout_returns_pd_na():
    """When followthrough=False, takeout_quarter_of_h2 should be pd.NA (not python None)."""
    h0 = helpers.make_hour('2024-01-02 09:00', ohlc=(100, 105, 95, 100),
                           high_at_minute=20, low_at_minute=40)
    h1 = helpers.make_hour('2024-01-02 10:00', ohlc=(100, 115, 95, 110),
                           high_at_minute=30, low_at_minute=40)
    # H2 doesn't break above H1.high (115)
    h2 = helpers.make_hour('2024-01-02 11:00', ohlc=(110, 113, 105, 112),
                           high_at_minute=5, low_at_minute=20)
    minutes = helpers.concat_hours(h0, h1, h2)
    enriched = bars._enrich_minutes(minutes)
    hourly, _ = bars.build_all_from_minutes(enriched)
    events = bs.attach_followthrough(bs.classify(hourly), enriched)
    h1_row = events.iloc[1]
    assert h1_row['breakout'] == 'bullish'
    assert h1_row['followthrough'] == False
    assert pd.isna(h1_row['takeout_quarter_of_h2'])


def test_breakout_metric_returns_rates():
    """Build a tiny events df and run the metric function directly."""
    events = pd.DataFrame({
        'breakout': ['bullish', 'bullish', 'bearish', 'neither', 'no_prev'],
        'followthrough': [True, False, True, None, None],
        'immediate_reversal': [False, True, False, None, None],
        'h1_open_vs_prev_mid': ['above', 'below', 'above', None, None],
    })
    rec = bs.breakout_metric(events)
    assert rec['n_total'] == 5
    assert rec['n_classifiable'] == 4  # excludes the one no_prev row
    assert rec['n_bullish'] == 2
    assert rec['n_bearish'] == 1
    # Rates use n_classifiable as denominator
    assert rec['bullish_breakout_rate'] == 0.5  # 2/4
    assert rec['bearish_breakout_rate'] == 0.25  # 1/4
    assert rec['bullish_followthrough_rate'] == 0.5
    assert rec['bearish_followthrough_rate'] == 1.0
    assert rec['bullish_immediate_reversal_rate'] == 0.5


def test_h2_excursion_bullish_basic():
    """Bullish breakout, H2 open=110, intra-H2 low=108, high=115.
    Expected: MAE = (110-108)/110 * 100 = 1.818...%
              MFE = (115-110)/110 * 100 = 4.545...%
    """
    h0 = helpers.make_hour('2024-01-02 09:00', ohlc=(100, 105, 95, 100),
                           high_at_minute=20, low_at_minute=40)
    h1 = helpers.make_hour('2024-01-02 10:00', ohlc=(100, 115, 95, 110),
                           high_at_minute=30, low_at_minute=40)
    # H2: open=110, low=108 at min 5, high=115 at min 20, close=112
    h2 = helpers.make_hour('2024-01-02 11:00', ohlc=(110, 115, 108, 112),
                           high_at_minute=20, low_at_minute=5)
    minutes = helpers.concat_hours(h0, h1, h2)
    enriched = bars._enrich_minutes(minutes)
    hourly, _ = bars.build_all_from_minutes(enriched)
    events = bs.attach_followthrough(bs.classify(hourly), enriched)
    h1_row = events.iloc[1]
    assert h1_row['breakout'] == 'bullish'
    assert h1_row['h2_mae_pct'] == pytest.approx((110 - 108) / 110 * 100, rel=1e-6)
    assert h1_row['h2_mfe_pct'] == pytest.approx((115 - 110) / 110 * 100, rel=1e-6)


def test_h2_excursion_bearish_basic():
    """Bearish breakout, H2 open=90, intra-H2 high=92, low=87.
    Expected (short): MAE = (92-90)/90 * 100 = 2.222...%
                      MFE = (90-87)/90 * 100 = 3.333...%
    """
    h0 = helpers.make_hour('2024-01-02 09:00', ohlc=(100, 105, 95, 100),
                           high_at_minute=20, low_at_minute=40)
    h1 = helpers.make_hour('2024-01-02 10:00', ohlc=(100, 105, 85, 90),
                           high_at_minute=10, low_at_minute=40)
    # H2: open=90, high=92 at min 5, low=87 at min 30, close=88
    h2 = helpers.make_hour('2024-01-02 11:00', ohlc=(90, 92, 87, 88),
                           high_at_minute=5, low_at_minute=30)
    minutes = helpers.concat_hours(h0, h1, h2)
    enriched = bars._enrich_minutes(minutes)
    hourly, _ = bars.build_all_from_minutes(enriched)
    events = bs.attach_followthrough(bs.classify(hourly), enriched)
    h1_row = events.iloc[1]
    assert h1_row['breakout'] == 'bearish'
    assert h1_row['h2_mae_pct'] == pytest.approx((92 - 90) / 90 * 100, rel=1e-6)
    assert h1_row['h2_mfe_pct'] == pytest.approx((90 - 87) / 90 * 100, rel=1e-6)


def test_h2_excursion_na_for_non_breakouts():
    """Inside bar (breakout='neither') → h2_mae_pct + h2_mfe_pct both NaN.
    Also covers the first row which is 'no_prev'.
    """
    h0 = helpers.make_hour('2024-01-02 09:00', ohlc=(100, 110, 90, 100),
                           high_at_minute=20, low_at_minute=40)
    # H1 inside H0 range entirely
    h1 = helpers.make_hour('2024-01-02 10:00', ohlc=(100, 105, 95, 102),
                           high_at_minute=30, low_at_minute=40)
    h2 = helpers.make_hour('2024-01-02 11:00', ohlc=(102, 108, 98, 104),
                           high_at_minute=10, low_at_minute=40)
    minutes = helpers.concat_hours(h0, h1, h2)
    enriched = bars._enrich_minutes(minutes)
    hourly, _ = bars.build_all_from_minutes(enriched)
    events = bs.attach_followthrough(bs.classify(hourly), enriched)
    # H0 row is 'no_prev' (first row); H1 is 'neither' (inside bar)
    assert events.iloc[0]['breakout'] == 'no_prev'
    assert pd.isna(events.iloc[0]['h2_mae_pct'])
    assert pd.isna(events.iloc[0]['h2_mfe_pct'])
    assert events.iloc[1]['breakout'] == 'neither'
    assert pd.isna(events.iloc[1]['h2_mae_pct'])
    assert pd.isna(events.iloc[1]['h2_mfe_pct'])


def test_h2_excursion_no_minutes_returns_na():
    """If a breakout's next hour has no minute bars (data gap), both
    excursion columns are NaN — matches followthrough behavior."""
    h0 = helpers.make_hour('2024-01-02 09:00', ohlc=(100, 105, 95, 100),
                           high_at_minute=20, low_at_minute=40)
    # Bullish breakout, but no H2 minutes (we only feed h0 + h1)
    h1 = helpers.make_hour('2024-01-02 10:00', ohlc=(100, 115, 95, 110),
                           high_at_minute=30, low_at_minute=40)
    minutes = helpers.concat_hours(h0, h1)
    enriched = bars._enrich_minutes(minutes)
    hourly, _ = bars.build_all_from_minutes(enriched)
    events = bs.attach_followthrough(bs.classify(hourly), enriched)
    h1_row = events.iloc[1]
    assert h1_row['breakout'] == 'bullish'
    # H2 has no minutes → NaN for everything including new columns
    assert pd.isna(h1_row['h2_mae_pct'])
    assert pd.isna(h1_row['h2_mfe_pct'])


def test_h2_excursion_clamped_to_zero_on_one_sided_trending():
    """Strong bullish continuation: H2's lowest 1-min low is ABOVE H2 open
    (price never dropped after entry). MAE must clamp to 0, not go negative.

    make_hour() enforces l<=o so we build H2 with make_minutes() directly,
    giving every bar a low strictly above the H2 first-bar open (110.0).
    """
    from datetime import timedelta
    from zoneinfo import ZoneInfo
    NY = ZoneInfo('America/New_York')

    h0 = helpers.make_hour('2024-01-02 09:00', ohlc=(100, 105, 95, 100),
                           high_at_minute=20, low_at_minute=40)
    # H1 bullish breakout: close=110 > H0 high=105
    h1 = helpers.make_hour('2024-01-02 10:00', ohlc=(100, 115, 95, 110),
                           high_at_minute=30, low_at_minute=40)
    # H2 trends straight up: first bar opens at 110, but every bar's low is
    # 110.05+, i.e., H2 aggregate low > H2 open. Without the clamp, mae_pts < 0.
    h2_base = pd.Timestamp('2024-01-02 11:00', tz=NY)
    h2_rows = []
    for i in range(60):
        o_i = 110.0 + i * 0.1          # opens drift upward from 110.0
        h2_rows.append({
            'timestamp': h2_base + timedelta(minutes=i),
            'open':  o_i,
            'high':  o_i + 0.2,
            'low':   o_i + 0.05,        # low is ABOVE 110.0 for every bar
            'close': o_i + 0.1,
            'volume': 10,
        })
    h2 = pd.DataFrame(h2_rows)
    minutes = helpers.concat_hours(h0, h1, h2)
    enriched = bars._enrich_minutes(minutes)
    hourly, _ = bars.build_all_from_minutes(enriched)
    events = bs.attach_followthrough(bs.classify(hourly), enriched)
    h1_row = events.iloc[1]
    assert h1_row['breakout'] == 'bullish'
    # H2 low (110.05) > H2 open (110.0) → raw mae_pts < 0; must be clamped to 0.
    assert h1_row['h2_mae_pct'] == 0.0
    # MFE should be > 0 (price rose well above entry).
    assert h1_row['h2_mfe_pct'] > 0
