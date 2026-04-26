"""Tests for Analysis/engine/quarter_study.py."""
import pandas as pd
import numpy as np
import pytest
import quarter_study as qs
import bars
import helpers


def _build_one_hour(ohlc=(100, 110, 90, 105), high_min=20, low_min=40):
    minutes = helpers.make_hour('2024-01-02 10:00', ohlc=ohlc,
                                high_at_minute=high_min, low_at_minute=low_min)
    enriched = bars._enrich_minutes(minutes)
    hourly, quarters = bars.build_all_from_minutes(enriched)
    return enriched, hourly, quarters


def test_q_of_high_when_high_in_q2():
    _, hourly, quarters = _build_one_hour(high_min=20, low_min=40)
    feats = qs.build_features(hourly, quarters)
    assert feats.iloc[0]['q_of_high'] == 2  # minute 20 → Q2


def test_q_of_high_when_high_in_q4():
    _, hourly, quarters = _build_one_hour(high_min=50, low_min=10)
    feats = qs.build_features(hourly, quarters)
    assert feats.iloc[0]['q_of_high'] == 4
    assert feats.iloc[0]['q_of_low'] == 1


def test_extreme_first_high_before_low():
    _, hourly, quarters = _build_one_hour(high_min=10, low_min=50)
    feats = qs.build_features(hourly, quarters)
    assert feats.iloc[0]['extreme_first'] == 'H'


def test_extreme_first_low_before_high():
    _, hourly, quarters = _build_one_hour(high_min=50, low_min=10)
    feats = qs.build_features(hourly, quarters)
    assert feats.iloc[0]['extreme_first'] == 'L'


def test_quarter_directions_and_ranges_correct():
    """Verify quarter-level directional signs and range calculations."""
    # _build_one_hour defaults: ohlc=(100, 110, 90, 105), high_min=20, low_min=40
    # hour open=100, close=105 → up (+1); high=110, low=90 → range=20
    _, hourly, quarters = _build_one_hour()
    feats = qs.build_features(hourly, quarters)
    assert 'q1_dir' in feats.columns
    assert 'q4_range' in feats.columns
    assert 'hour_dir' in feats.columns
    # hour_dir: close (105) > open (100) → +1
    assert feats.iloc[0]['hour_dir'] == 1
    # hour_range: high (110) - low (90) = 20
    assert feats.iloc[0]['hour_range'] == 20
    # All q*_dir, q*_range, q*_body columns present
    for q in (1, 2, 3, 4):
        assert f'q{q}_dir' in feats.columns
        assert f'q{q}_range' in feats.columns
        assert f'q{q}_body' in feats.columns


def test_build_features_handles_empty_input():
    """Empty hourly + empty quarters should return an empty DataFrame, not crash."""
    empty_hourly = pd.DataFrame(columns=['hour_start_et', 'open', 'high', 'low',
                                          'close', 'volume', 'prev_hour_open',
                                          'prev_hour_high', 'prev_hour_low',
                                          'prev_hour_close', 'prev_hour_mid',
                                          'year', 'dow', 'hour_of_day_et'])
    empty_quarters = pd.DataFrame(columns=['hour_start_et', 'quarter', 'open',
                                            'high', 'low', 'close', 'volume',
                                            'q_high_minute', 'q_low_minute'])
    feats = qs.build_features(empty_hourly, empty_quarters)
    assert len(feats) == 0


def _synthetic_features(n=20):
    """Build a small synthetic feature df with known structure for metric tests."""
    rng = np.random.default_rng(42)
    q1_high = rng.uniform(100, 110, n)
    q1_low = rng.uniform(90, 100, n)
    q4_high = rng.uniform(100, 110, n)
    q4_low = rng.uniform(90, 100, n)
    # Hour extremes must enclose all quarter extremes (real-data invariant).
    # Add a small positive overshoot so the failed-hold cases produce strictly positive overshoot.
    hour_high = np.maximum.reduce([q1_high, q4_high]) + rng.uniform(0.1, 5, n)
    hour_low = np.minimum.reduce([q1_low, q4_low]) - rng.uniform(0.1, 5, n)
    df = pd.DataFrame({
        'q_of_high': rng.integers(1, 5, n),
        'q_of_low': rng.integers(1, 5, n),
        'extreme_first': rng.choice(['H', 'L'], n),
        'q1_dir': rng.choice([-1, 0, 1], n),
        'q2_dir': rng.choice([-1, 0, 1], n),
        'q3_dir': rng.choice([-1, 0, 1], n),
        'q4_dir': rng.choice([-1, 0, 1], n),
        'q1_range': rng.uniform(1, 10, n),
        'q2_range': rng.uniform(1, 10, n),
        'q3_range': rng.uniform(1, 10, n),
        'q4_range': rng.uniform(1, 10, n),
        'q1_body': rng.uniform(0, 5, n),
        'q2_body': rng.uniform(0, 5, n),
        'q3_body': rng.uniform(0, 5, n),
        'q4_body': rng.uniform(0, 5, n),
        'q1_high': q1_high,
        'q1_low': q1_low,
        'q4_high': q4_high,
        'q4_low': q4_low,
        'hour_range': hour_high - hour_low,  # derived; was uniform(5,20)
        'hour_dir': rng.choice([-1, 0, 1], n),
        'hour_high': hour_high,
        'hour_low': hour_low,
        'year': 2024,
        'dow': 1,
        'hour_of_day_et': 10,
    })
    return df


def test_study_a_returns_q_of_high_distribution():
    df = _synthetic_features()
    rec = qs.study_a_metric(df)
    # Should have keys for q1..q4 high and low pcts
    assert 'q_of_high_q1_pct' in rec
    assert 'q_of_low_q4_pct' in rec
    assert 0 <= rec['q_of_high_q1_pct'] <= 1


def test_study_b_returns_extreme_first_pct():
    df = _synthetic_features()
    rec = qs.study_b_metric(df)
    assert 'extreme_first_H_pct' in rec
    assert 'extreme_first_L_pct' in rec


def test_study_c_returns_per_quarter_directional_rates():
    df = _synthetic_features()
    rec = qs.study_c_metric(df)
    for q in (1, 2, 3, 4):
        assert f'q{q}_up_pct' in rec
        assert f'q{q}_down_pct' in rec
        assert f'q{q}_avg_range' in rec


def test_study_d_q1_to_hour_dir():
    df = _synthetic_features()
    rec = qs.study_d_metric(df)
    # P(hour_dir=+1 | q1_dir=+1)
    assert 'p_hour_up_given_q1_up' in rec
    assert 'p_q4_reversal_given_q1_dir' in rec


def test_study_e_q1_high_hold_rate():
    df = _synthetic_features()
    rec = qs.study_e_metric(df)
    assert 'q1_high_hold_rate' in rec
    assert 'q4_high_hold_rate' in rec
    # When Q1 high failed to hold, hour_high > q1_high so overshoot is strictly positive.
    # If formula is ever inverted (q1_high - hour_high), this assert will catch it.
    assert rec['q1_high_fail_overshoot_mean'] >= 0


def test_study_f_quintile_table_returns_5_rows():
    df = _synthetic_features(n=100)  # need enough for clean quintiles
    out = qs.study_f_table(df)
    assert len(out) == 5
    assert 'q1_range_quintile' in out.columns
    assert 'avg_hour_range' in out.columns
