"""Hourly breakout follow-through study.

For each hour H1 with a valid prev hour H0:
- bullish breakout: H1.close > H0.high  (strict)
- bearish breakout: H1.close < H0.low   (strict)
- neither: everything else (including inside bars)

Then for each breakout, look at H2 to detect:
- bullish follow-through: H2 prints high > H1.high at any minute
- bearish follow-through: H2 prints low < H1.low at any minute
- immediate-reversal: H2 takes out the *opposite* extreme of H1
"""
from __future__ import annotations
import pandas as pd
import numpy as np

import slicers


def classify(hourly: pd.DataFrame) -> pd.DataFrame:
    """Add a `breakout` column to the hourly dataframe.

    Values: 'bullish', 'bearish', 'neither', or 'no_prev' (first row, no H0).
    """
    df = hourly.copy()
    breakout = pd.Series('neither', index=df.index, dtype='object')
    no_prev_mask = df['prev_hour_high'].isna()
    bull = df['close'] > df['prev_hour_high']
    bear = df['close'] < df['prev_hour_low']
    breakout.loc[bull] = 'bullish'
    breakout.loc[bear] = 'bearish'
    breakout.loc[no_prev_mask] = 'no_prev'
    df['breakout'] = breakout
    # h1_open vs prev_mid (above/below/equal)
    df['h1_open_vs_prev_mid'] = np.where(
        df['open'] > df['prev_hour_mid'], 'above',
        np.where(df['open'] < df['prev_hour_mid'], 'below', 'equal')
    )
    # Use pd.NA so downstream code can check with pd.isna(); plain None
    # would be silently coerced to float NaN due to the string-typed column.
    df.loc[no_prev_mask, 'h1_open_vs_prev_mid'] = pd.NA
    return df


def _quarter_for_minute(minute_of_hour: int) -> int:
    """Q1=:00-14, Q2=:15-29, Q3=:30-44, Q4=:45-59."""
    return minute_of_hour // 15 + 1


def attach_followthrough(classified: pd.DataFrame, minutes: pd.DataFrame) -> pd.DataFrame:
    """For each breakout row in `classified`, look at the next hour's 1-min bars
    and determine:
    - followthrough: True if H2 trades strictly beyond H1's extreme in the
      breakout direction
    - takeout_quarter_of_h2: 1..4 indicating which quarter of H2 first crossed
      (NaN if no takeout)
    - immediate_reversal: True if H2 strictly takes out H1's *opposite* extreme
      (only meaningful for breakout rows)

    Non-breakout rows ('neither', 'no_prev') get NaN for all three.
    """
    df = classified.copy().sort_values('hour_start_et').reset_index(drop=True)

    # Pre-bucket minutes by hour for fast lookup
    m = minutes.copy()
    m['hour_start_et'] = m['ny_ts'].dt.floor('h')
    m['minute_of_hour'] = m['ny_ts'].dt.minute
    grouped = dict(list(m.groupby('hour_start_et')))

    next_hour = df['hour_start_et'].shift(-1)

    followthrough = []
    takeout_q = []
    reversal = []

    for i, row in df.iterrows():
        b = row['breakout']
        if b not in ('bullish', 'bearish'):
            followthrough.append(np.nan)
            takeout_q.append(np.nan)
            reversal.append(np.nan)
            continue
        h2_start = next_hour.iloc[i]
        if pd.isna(h2_start) or h2_start not in grouped:
            followthrough.append(np.nan)
            takeout_q.append(np.nan)
            reversal.append(np.nan)
            continue
        h2 = grouped[h2_start].sort_values('minute_of_hour')
        h1_high = row['high']
        h1_low = row['low']
        if b == 'bullish':
            crossed = h2[h2['high'] > h1_high]
            if len(crossed) > 0:
                first_min = int(crossed['minute_of_hour'].iloc[0])
                followthrough.append(True)
                takeout_q.append(_quarter_for_minute(first_min))
            else:
                followthrough.append(False)
                takeout_q.append(np.nan)
            reversal.append(bool((h2['low'] < h1_low).any()))
        else:  # bearish
            crossed = h2[h2['low'] < h1_low]
            if len(crossed) > 0:
                first_min = int(crossed['minute_of_hour'].iloc[0])
                followthrough.append(True)
                takeout_q.append(_quarter_for_minute(first_min))
            else:
                followthrough.append(False)
                takeout_q.append(np.nan)
            reversal.append(bool((h2['high'] > h1_high).any()))

    # Use nullable boolean / Int dtypes so NaN is represented as pd.NA
    # and parquet round-trips with proper typing for the dashboard.
    df['followthrough'] = pd.array(followthrough, dtype='boolean')
    df['takeout_quarter_of_h2'] = pd.array(takeout_q, dtype='Int64')
    df['immediate_reversal'] = pd.array(reversal, dtype='boolean')
    return df


def breakout_metric(events: pd.DataFrame) -> dict:
    """Aggregation function fed into a slicer.

    Rates use n_classifiable (excludes 'no_prev' rows, which can't be classified)
    as the denominator so the metric isn't deflated by data-edge gaps.
    """
    n_total = len(events)
    bull = events[events['breakout'] == 'bullish']
    bear = events[events['breakout'] == 'bearish']
    n_bull, n_bear = len(bull), len(bear)
    n_classifiable = n_total - int((events['breakout'] == 'no_prev').sum())

    def _rate(sub: pd.DataFrame, col: str) -> float:
        s = sub[col].dropna()
        return float(s.mean()) if len(s) else float('nan')

    return {
        'n_total': n_total,
        'n_classifiable': n_classifiable,
        'n_bullish': n_bull,
        'n_bearish': n_bear,
        'bullish_breakout_rate': n_bull / n_classifiable if n_classifiable else float('nan'),
        'bearish_breakout_rate': n_bear / n_classifiable if n_classifiable else float('nan'),
        'bullish_followthrough_rate': _rate(bull, 'followthrough'),
        'bearish_followthrough_rate': _rate(bear, 'followthrough'),
        'bullish_immediate_reversal_rate': _rate(bull, 'immediate_reversal'),
        'bearish_immediate_reversal_rate': _rate(bear, 'immediate_reversal'),
    }


def build_summaries(events: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Return {summary_name: dataframe} dict for all 5 slicing dimensions."""
    return {
        'aggregate': slicers.slice_aggregate(events, breakout_metric),
        'by_year': slicers.slice_by_year(events, breakout_metric),
        'by_hour': slicers.slice_by_hour(events, breakout_metric),
        'by_dow': slicers.slice_by_dow(events, breakout_metric),
        'grid': slicers.slice_by_hour_dow(events, breakout_metric),
    }
