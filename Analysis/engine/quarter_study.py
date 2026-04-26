"""In-depth quarter-of-the-hour study.

Builds a per-hour feature row with quarter OHLCs, location of extremes,
direction signs, range/body stats, and runs the A-F sub-studies.
"""
from __future__ import annotations
import pandas as pd
import numpy as np


def build_features(hourly: pd.DataFrame, quarters: pd.DataFrame) -> pd.DataFrame:
    """One row per valid hour with quarter OHLC, location of extremes,
    directions, ranges, bodies."""
    # Pivot quarters: 4 rows per hour → 1 row per hour with q1_*, q2_*, ...
    pivot_cols = ['open', 'high', 'low', 'close', 'q_high_minute', 'q_low_minute']
    qp = quarters.pivot(index='hour_start_et', columns='quarter',
                        values=pivot_cols)
    qp.columns = [f'q{q}_{stat}' for stat, q in qp.columns]
    qp = qp.reset_index()

    df = hourly.merge(qp, on='hour_start_et', how='inner')

    if df.empty:
        # Empty input — return early before idxmax/apply would crash on missing columns.
        return df

    # Hour-level extreme location
    high_cols = ['q1_high', 'q2_high', 'q3_high', 'q4_high']
    low_cols = ['q1_low', 'q2_low', 'q3_low', 'q4_low']
    # idxmax across columns gives the col name containing the max — map to quarter int
    df['q_of_high'] = df[high_cols].idxmax(axis=1).str[1].astype(int)
    df['q_of_low'] = df[low_cols].idxmin(axis=1).str[1].astype(int)

    # extreme_first: compare absolute minute-of-hour for the high vs low
    # Note: q_high_minute is already minute-of-hour (0-59), so the value of
    # the relevant qN_q_high_minute column is the absolute minute.
    df['_high_abs_min'] = df.apply(
        lambda r: int(r[f'q{int(r["q_of_high"])}_q_high_minute']), axis=1)
    df['_low_abs_min'] = df.apply(
        lambda r: int(r[f'q{int(r["q_of_low"])}_q_low_minute']), axis=1)
    df['extreme_first'] = np.where(
        df['_high_abs_min'] < df['_low_abs_min'], 'H',
        np.where(df['_high_abs_min'] > df['_low_abs_min'], 'L', 'T'))

    # Per-quarter directions, ranges, bodies
    for q in (1, 2, 3, 4):
        df[f'q{q}_dir'] = np.sign(df[f'q{q}_close'] - df[f'q{q}_open']).astype(int)
        df[f'q{q}_range'] = df[f'q{q}_high'] - df[f'q{q}_low']
        df[f'q{q}_body'] = (df[f'q{q}_close'] - df[f'q{q}_open']).abs()

    # Hour-level
    df['hour_range'] = df['high'] - df['low']
    df['hour_dir'] = np.sign(df['close'] - df['open']).astype(int)

    # Drop helper cols
    df = df.drop(columns=['_high_abs_min', '_low_abs_min'])
    return df
