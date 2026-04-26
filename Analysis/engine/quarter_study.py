"""In-depth quarter-of-the-hour study.

Builds a per-hour feature row with quarter OHLCs, location of extremes,
direction signs, range/body stats, and runs the A-F sub-studies.
"""
from __future__ import annotations
import pandas as pd
import numpy as np
import warnings
import slicers


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


# ---------------------------------------------------------------------------
# Sub-studies A-F
# ---------------------------------------------------------------------------

def study_a_metric(df: pd.DataFrame) -> dict:
    """High/low location distribution."""
    n = len(df)
    rec = {}
    for q in (1, 2, 3, 4):
        rec[f'q_of_high_q{q}_pct'] = float((df['q_of_high'] == q).mean()) if n else float('nan')
        rec[f'q_of_low_q{q}_pct'] = float((df['q_of_low'] == q).mean()) if n else float('nan')
    return rec


def study_b_metric(df: pd.DataFrame) -> dict:
    """Sequencing: H-first vs L-first."""
    n = len(df)
    return {
        'extreme_first_H_pct': float((df['extreme_first'] == 'H').mean()) if n else float('nan'),
        'extreme_first_L_pct': float((df['extreme_first'] == 'L').mean()) if n else float('nan'),
        'extreme_first_T_pct': float((df['extreme_first'] == 'T').mean()) if n else float('nan'),
    }


def study_c_metric(df: pd.DataFrame) -> dict:
    """Per-quarter directional bias and range."""
    rec = {}
    for q in (1, 2, 3, 4):
        n = len(df)
        rec[f'q{q}_up_pct'] = float((df[f'q{q}_dir'] == 1).mean()) if n else float('nan')
        rec[f'q{q}_down_pct'] = float((df[f'q{q}_dir'] == -1).mean()) if n else float('nan')
        rec[f'q{q}_flat_pct'] = float((df[f'q{q}_dir'] == 0).mean()) if n else float('nan')
        rec[f'q{q}_avg_range'] = float(df[f'q{q}_range'].mean()) if n else float('nan')
        rec[f'q{q}_median_range'] = float(df[f'q{q}_range'].median()) if n else float('nan')
        rec[f'q{q}_avg_body'] = float(df[f'q{q}_body'].mean()) if n else float('nan')
        avg_range = df[f'q{q}_range'].mean()
        avg_body = df[f'q{q}_body'].mean()
        rec[f'q{q}_body_to_range_ratio'] = float(avg_body / avg_range) if avg_range else float('nan')
    return rec


def _conditional_dir_pct(df: pd.DataFrame, given_col: str, given_val: int,
                         then_col: str, then_val: int) -> float:
    sub = df[df[given_col] == given_val]
    if not len(sub):
        return float('nan')
    return float((sub[then_col] == then_val).mean())


def study_d_metric(df: pd.DataFrame) -> dict:
    """Conditional shift detection."""
    rec = {
        'p_hour_up_given_q1_up': _conditional_dir_pct(df, 'q1_dir', 1, 'hour_dir', 1),
        'p_hour_down_given_q1_down': _conditional_dir_pct(df, 'q1_dir', -1, 'hour_dir', -1),
        'p_q2_up_given_q1_up': _conditional_dir_pct(df, 'q1_dir', 1, 'q2_dir', 1),
        'p_q3_up_given_q1_up': _conditional_dir_pct(df, 'q1_dir', 1, 'q3_dir', 1),
        'p_q4_up_given_q1_up': _conditional_dir_pct(df, 'q1_dir', 1, 'q4_dir', 1),
        'p_q4_down_given_q1_up': _conditional_dir_pct(df, 'q1_dir', 1, 'q4_dir', -1),
        'p_q4_up_given_q1_down': _conditional_dir_pct(df, 'q1_dir', -1, 'q4_dir', 1),
    }
    # Reversal: q4_dir opposite of q1_dir given q1_dir != 0
    nz = df[df['q1_dir'] != 0]
    if len(nz):
        rec['p_q4_reversal_given_q1_dir'] = float(((nz['q4_dir'] != 0) & (nz['q4_dir'] != nz['q1_dir'])).mean())
    else:
        rec['p_q4_reversal_given_q1_dir'] = float('nan')
    return rec


def study_e_metric(df: pd.DataFrame) -> dict:
    """Early- and late-extreme persistence + overshoot when Q1 fails."""
    n = len(df)
    rec = {
        'q1_high_hold_rate': float((df['q_of_high'] == 1).mean()) if n else float('nan'),
        'q1_low_hold_rate': float((df['q_of_low'] == 1).mean()) if n else float('nan'),
        'q4_high_hold_rate': float((df['q_of_high'] == 4).mean()) if n else float('nan'),
        'q4_low_hold_rate': float((df['q_of_low'] == 4).mean()) if n else float('nan'),
    }
    failed = df[df['q_of_high'] != 1]
    if 'hour_high' in df.columns and len(failed):
        overshoot = failed['hour_high'] - failed['q1_high']
        rec['q1_high_fail_overshoot_mean'] = float(overshoot.mean())
        rec['q1_high_fail_overshoot_median'] = float(overshoot.median())
    else:
        rec['q1_high_fail_overshoot_mean'] = float('nan')
        rec['q1_high_fail_overshoot_median'] = float('nan')
    return rec


def study_f_table(df: pd.DataFrame) -> pd.DataFrame:
    """Q1-range quintile bucketing.

    Returns 5 rows (one per quintile) with avg hour range, remaining range,
    Q1-extreme hold rates, and direction distribution.
    """
    if len(df) < 5:
        return pd.DataFrame()
    df = df.copy()
    try:
        df['q1_range_quintile'] = pd.qcut(df['q1_range'], 5, labels=[1, 2, 3, 4, 5],
                                          duplicates='drop')
    except ValueError:
        warnings.warn(
            f"study_f_table: pd.qcut could not form 5 bins (got {len(df)} rows, "
            f"likely too many ties in q1_range). Returning empty DataFrame.",
            stacklevel=2,
        )
        return pd.DataFrame()
    rows = []
    for quintile, sub in df.groupby('q1_range_quintile', observed=True):
        rows.append({
            'q1_range_quintile': int(quintile),
            'count': len(sub),
            'avg_q1_range': float(sub['q1_range'].mean()),
            'avg_hour_range': float(sub['hour_range'].mean()),
            'avg_remaining_range': float((sub['hour_range'] - sub['q1_range']).mean()),
            'q1_high_hold_rate': float((sub['q_of_high'] == 1).mean()),
            'q1_low_hold_rate': float((sub['q_of_low'] == 1).mean()),
            'hour_up_pct': float((sub['hour_dir'] == 1).mean()),
            'hour_down_pct': float((sub['hour_dir'] == -1).mean()),
        })
    return pd.DataFrame(rows)


def build_summaries(features: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Run every (study, slice) combination and return a dict of dataframes.

    Keys are like 'study_a_aggregate', 'study_d_by_hour', 'study_f_aggregate', etc.
    Study F is a table-style study, so it only has aggregate / by_year / by_hour /
    by_dow variants, not the full grid (the grid would be too sparse for quintiles).
    """
    out = {}
    metric_studies = [
        ('study_a', study_a_metric),
        ('study_b', study_b_metric),
        ('study_c', study_c_metric),
        ('study_d', study_d_metric),
        ('study_e', study_e_metric),
    ]
    slice_fns = [
        ('aggregate', slicers.slice_aggregate),
        ('by_year', slicers.slice_by_year),
        ('by_hour', slicers.slice_by_hour),
        ('by_dow', slicers.slice_by_dow),
        ('grid', slicers.slice_by_hour_dow),
    ]
    for study_name, metric_fn in metric_studies:
        for slice_name, slice_fn in slice_fns:
            out[f'{study_name}_{slice_name}'] = slice_fn(features, metric_fn)
    # Study F: aggregate + by_year + by_hour + by_dow only
    out['study_f_aggregate'] = study_f_table(features)
    for slice_name, by_col in [('by_year', 'year'), ('by_hour', 'hour_of_day_et'),
                               ('by_dow', 'dow')]:
        rows = []
        for k, sub in features.groupby(by_col):
            t = study_f_table(sub)
            if len(t):
                t[by_col] = k
                rows.append(t)
        out[f'study_f_{slice_name}'] = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    return out
