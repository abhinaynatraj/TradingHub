#!/usr/bin/env python3
"""
model_stats_fixed_constant.py — Fixed Constant (Locked Anchor) Model
=====================================================================
Doctrine-compliant H3-style architecture from the Wolf Tank doctrine.

For each new HTF block, the engine locks the anchor at the close of the
FIRST chart-TF bar inside that block. From that lock close, MAE/MFE are
measured to the end of the HTF block. One rep per HTF block. No filters,
no direction labels, no win/loss resolution — just up/down excursions.

Passes all four fixed constant qualification tests:
  1. Same time every rep (locked HTF block boundary)
  2. Consistent structure (same anchor TF every rep)
  3. Zero conditional judgment (no setup criteria)
  4. Decision anchor only (direction comes from external sources)

Usage:
    python3 model_stats_fixed_constant.py
    python3 model_stats_fixed_constant.py --models 1H_5M
    python3 model_stats_fixed_constant.py --table es_1m
"""

import argparse
import json
import time
import duckdb
import pandas as pd
import numpy as np
from pathlib import Path

# ── PATHS ─────────────────────────────────────────────────────────────────────
DB_PATH  = Path(__file__).parent / 'candle_science.duckdb'
OUT_PATH = Path(__file__).parent / 'model_stats_fixed_constant.json'

# ── MODEL DEFINITIONS ─────────────────────────────────────────────────────────
# NOTE: 15M_1M intentionally NOT included — measurement window too short.
MODELS = {
    '30M_3M':  dict(htf_min=30,  chart_tf_min=3),
    '1H_5M':   dict(htf_min=60,  chart_tf_min=5),
    '4H_15M':  dict(htf_min=240, chart_tf_min=15),
}

DOW_NAMES = {0: 'Sun', 1: 'Mon', 2: 'Tue', 3: 'Wed', 4: 'Thu', 5: 'Fri', 6: 'Sat'}


# ── LOAD 1m BARS ──────────────────────────────────────────────────────────────
def load_1m(con, table):
    print(f"[1] Loading {table} ...")
    raw = con.execute(f"""
        SELECT
            CAST(timezone('America/New_York', timestamp) AS DATE)  AS trade_date,
            CAST(timezone('America/New_York', timestamp) AS TIME)  AS bar_time,
            open::DOUBLE AS open, high::DOUBLE AS high,
            low::DOUBLE  AS low,  close::DOUBLE AS close,
            date_part('year',   timezone('America/New_York', timestamp)) AS yr,
            date_part('month',  timezone('America/New_York', timestamp)) AS mo,
            date_part('dow',    timezone('America/New_York', timestamp)) AS dow,
            date_part('hour',   timezone('America/New_York', timestamp)) AS hr,
            date_part('minute', timezone('America/New_York', timestamp)) AS mn
        FROM {table}
        ORDER BY timestamp
    """).df()
    raw['ts'] = pd.to_datetime(
        raw['trade_date'].astype(str) + ' ' + raw['bar_time'].astype(str)
    )
    raw = raw.sort_values('ts').reset_index(drop=True).set_index('ts')
    print(f"   {len(raw):,} total bars")
    return raw


# ── RESAMPLE ──────────────────────────────────────────────────────────────────
def resample(df_1m, tf_min, label):
    print(f"   Building {label} bars ...")
    df2 = df_1m.copy()
    df2['ts_tf'] = df2.index.floor(f"{tf_min}min")
    agg_df = df2.groupby('ts_tf').agg(
        trade_date=('trade_date', 'first'), yr=('yr', 'first'), mo=('mo', 'first'),
        dow=('dow', 'first'), hr=('hr', 'first'), mn=('mn', 'first'),
        open_tf=('open', 'first'), high_tf=('high', 'max'),
        low_tf=('low', 'min'),    close_tf=('close', 'last'),
    ).sort_index()
    print(f"      {len(agg_df):,} {label} bars")
    return agg_df


# ── NUMPY ARRAY BUILDERS ──────────────────────────────────────────────────────
def _index_to_ns(idx):
    """Convert a pandas DatetimeIndex to int64 nanoseconds regardless of unit (us/ns)."""
    return idx.astype('datetime64[ns]').view('int64').copy()


def df_to_arrays(df):
    return dict(
        ts_ns      = _index_to_ns(df.index),
        open       = df['open_tf'].values.astype('float64'),
        high       = df['high_tf'].values.astype('float64'),
        low        = df['low_tf'].values.astype('float64'),
        close      = df['close_tf'].values.astype('float64'),
        trade_date = df['trade_date'].values.copy(),
        yr         = df['yr'].values.astype('int32'),
        dow        = df['dow'].values.astype('int32'),
        hr         = df['hr'].values.astype('int32'),
        mn         = df['mn'].values.astype('int32'),
    )


def df_1m_to_arrays(df):
    return dict(
        ts_ns      = _index_to_ns(df.index),
        open       = df['open'].values.astype('float64'),
        high       = df['high'].values.astype('float64'),
        low        = df['low'].values.astype('float64'),
        close      = df['close'].values.astype('float64'),
        hr         = df['hr'].values.astype('int32'),
        mn         = df['mn'].values.astype('int32'),
        yr         = df['yr'].values.astype('int32'),
        dow        = df['dow'].values.astype('int32'),
        trade_date = df['trade_date'].values.copy(),
    )


# ── SESSION CLASSIFICATION ───────────────────────────────────────────────────
def get_session(hr, mn):
    t_dec = hr + mn / 60.0
    if 7.0 <= t_dec < 8.5:
        return 'PRE'
    elif 8.5 <= t_dec < 11.5:
        return 'NY1'
    elif 11.5 <= t_dec < 16.0:
        return 'NY2'
    else:
        return 'OVERNIGHT'


# ── MAIN SCAN: One Rep Per HTF Block ─────────────────────────────────────────
def scan_fixed_constant_model(htf_arrs, chart_arrs, m1_arrs, model_key, cfg):
    """
    For each HTF block:
      1. Lock at first chart-TF bar's close
      2. Track up/down excursions on 1m bars to end of HTF block
      3. Emit one rep per HTF block
    """
    htf_n = len(htf_arrs['ts_ns'])
    htf_period_ns = cfg['htf_min'] * 60 * 10**9
    chart_tf_min = cfg['chart_tf_min']
    chart_tf_ns = chart_tf_min * 60 * 10**9
    reps = []
    skipped_gap = 0
    skipped_short = 0
    skipped_no_chart = 0
    pct_step = max(1, htf_n // 10)

    for i in range(1, htf_n):
        if (i - 1) % pct_step == 0:
            pct = (i - 1) / max(htf_n - 1, 1) * 100
            print(f'    [{model_key}] {pct:.0f}%  ({i:,}/{htf_n:,} HTF bars, {len(reps)} reps)', flush=True)

        # Skip weekend / holiday gaps (>3x htf_period since prior HTF bar)
        if htf_arrs['ts_ns'][i] - htf_arrs['ts_ns'][i-1] > 3 * htf_period_ns:
            skipped_gap += 1
            continue

        htf_start_ns = int(htf_arrs['ts_ns'][i])
        htf_end_ns = htf_start_ns + htf_period_ns

        # Find FIRST chart-TF bar that starts at the HTF block start
        ct_start = int(np.searchsorted(chart_arrs['ts_ns'], htf_start_ns, side='left'))
        if ct_start >= len(chart_arrs['ts_ns']):
            skipped_no_chart += 1
            continue
        if int(chart_arrs['ts_ns'][ct_start]) != htf_start_ns:
            # No chart-TF bar starts exactly at this HTF block start (data gap)
            skipped_no_chart += 1
            continue

        # Lock at the close of the first chart-TF bar
        lock_ts_ns = int(chart_arrs['ts_ns'][ct_start])
        lock_ts_end_ns = lock_ts_ns + chart_tf_ns  # close happens at end of chart-TF bar
        htf_close = float(chart_arrs['close'][ct_start])
        htf_high = float(chart_arrs['high'][ct_start])
        htf_low = float(chart_arrs['low'][ct_start])
        htf_mid = (htf_high + htf_low) / 2.0

        # Measurement window: from end of lock chart-TF bar to end of HTF block
        m1_start = int(np.searchsorted(m1_arrs['ts_ns'], lock_ts_end_ns, side='left'))
        m1_end = int(np.searchsorted(m1_arrs['ts_ns'], htf_end_ns, side='left'))

        if m1_end - m1_start < 5:
            skipped_short += 1
            continue

        # Track extremes and time-to-extreme
        highest_high = htf_close
        lowest_low = htf_close
        idx_max_up = m1_start
        idx_max_down = m1_start
        for k in range(m1_start, m1_end):
            h = float(m1_arrs['high'][k])
            l = float(m1_arrs['low'][k])
            if h > highest_high:
                highest_high = h
                idx_max_up = k
            if l < lowest_low:
                lowest_low = l
                idx_max_down = k

        excursion_up_pct = (highest_high - htf_close) / htf_close * 100.0
        excursion_down_pct = (htf_close - lowest_low) / htf_close * 100.0

        # Time to extremes (minutes from end of lock bar)
        time_to_max_up_min = int((m1_arrs['ts_ns'][idx_max_up] - lock_ts_end_ns) // (60 * 10**9))
        time_to_max_down_min = int((m1_arrs['ts_ns'][idx_max_down] - lock_ts_end_ns) // (60 * 10**9))

        # Lock time stamp string and components from chart-TF bar
        hr = int(chart_arrs['hr'][ct_start])
        mn = int(chart_arrs['mn'][ct_start])
        session = get_session(hr, mn)

        lock_ts_pd = pd.Timestamp(lock_ts_ns)
        htf_start_pd = pd.Timestamp(htf_start_ns)
        block_end_pd = pd.Timestamp(htf_end_ns - 60 * 10**9)  # last minute of block

        rep = {
            'date': str(htf_arrs['trade_date'][i]),
            'dow': int(htf_arrs['dow'][i]),
            'dow_name': DOW_NAMES.get(int(htf_arrs['dow'][i]), '?'),
            'yr': int(htf_arrs['yr'][i]),
            'hr': hr,
            'mn': mn,
            'htf_block_start': htf_start_pd.strftime('%Y-%m-%d %H:%M:%S'),
            'lock_time': lock_ts_pd.strftime('%Y-%m-%d %H:%M:%S'),
            'lock_close': round(htf_close, 2),
            'htf_high': round(htf_high, 2),
            'htf_low': round(htf_low, 2),
            'htf_mid': round(htf_mid, 2),
            'block_end': block_end_pd.strftime('%Y-%m-%d %H:%M:%S'),
            'excursion_up_pct': round(excursion_up_pct, 4),
            'excursion_down_pct': round(excursion_down_pct, 4),
            'time_to_max_up_min': time_to_max_up_min,
            'time_to_max_down_min': time_to_max_down_min,
            'session': session,
        }
        reps.append(rep)

    print(f'    [{model_key}] done. reps={len(reps)} skipped_gap={skipped_gap} skipped_short={skipped_short} skipped_no_chart={skipped_no_chart}', flush=True)
    return reps


# ── AGGREGATION ──────────────────────────────────────────────────────────────
def agg(g):
    n = len(g)
    if n == 0:
        return dict(n=0)
    up = g['excursion_up_pct'].dropna()
    down = g['excursion_down_pct'].dropna()
    return dict(
        n=n,
        up_mean=round(float(up.mean()), 4),
        up_med=round(float(up.median()), 4),
        up_p25=round(float(up.quantile(0.25)), 4),
        up_p50=round(float(up.quantile(0.50)), 4),
        up_p75=round(float(up.quantile(0.75)), 4),
        up_p90=round(float(up.quantile(0.90)), 4),
        up_p95=round(float(up.quantile(0.95)), 4),
        up_p99=round(float(up.quantile(0.99)), 4),
        down_mean=round(float(down.mean()), 4),
        down_med=round(float(down.median()), 4),
        down_p25=round(float(down.quantile(0.25)), 4),
        down_p50=round(float(down.quantile(0.50)), 4),
        down_p75=round(float(down.quantile(0.75)), 4),
        down_p90=round(float(down.quantile(0.90)), 4),
        down_p95=round(float(down.quantile(0.95)), 4),
        down_p99=round(float(down.quantile(0.99)), 4),
    )


def dist_stats(arr):
    if len(arr) < 2:
        return {}
    return {
        'mean': round(float(arr.mean()), 4),
        'median': round(float(arr.median()), 4),
        'std': round(float(arr.std()), 4),
        'p10': round(float(arr.quantile(0.10)), 4),
        'p25': round(float(arr.quantile(0.25)), 4),
        'p50': round(float(arr.quantile(0.50)), 4),
        'p75': round(float(arr.quantile(0.75)), 4),
        'p90': round(float(arr.quantile(0.90)), 4),
        'p95': round(float(arr.quantile(0.95)), 4),
        'p99': round(float(arr.quantile(0.99)), 4),
        'min': round(float(arr.min()), 4),
        'max': round(float(arr.max()), 4),
    }


def build_model_stats(df, model_key, cfg, instrument):
    if df.empty:
        return {'meta': {'model_key': model_key, 'total_reps': 0}, 'recent_reps': []}

    n = len(df)
    up_all = df['excursion_up_pct'].dropna()
    down_all = df['excursion_down_pct'].dropna()
    dates = sorted(df['date'].unique())

    htf_min = cfg['htf_min']
    chart_tf_min = cfg['chart_tf_min']

    meta = {
        'model_key': model_key,
        'instrument': instrument,
        'date_range': f'{dates[0]} to {dates[-1]}' if dates else '',
        'total_reps': n,
        'trading_days': len(dates),
        'reps_per_day': round(n / max(len(dates), 1), 2),
        'lock_minute': chart_tf_min,
        'block_duration_min': htf_min,
        'measurement_window_min': htf_min - chart_tf_min,
        'htf_min': htf_min,
        'chart_tf_min': chart_tf_min,
        # Aggregated stats
        'up_mean': round(float(up_all.mean()), 4) if len(up_all) else None,
        'up_p50': round(float(up_all.quantile(0.50)), 4) if len(up_all) else None,
        'up_p90': round(float(up_all.quantile(0.90)), 4) if len(up_all) else None,
        'up_p99': round(float(up_all.quantile(0.99)), 4) if len(up_all) else None,
        'down_mean': round(float(down_all.mean()), 4) if len(down_all) else None,
        'down_p50': round(float(down_all.quantile(0.50)), 4) if len(down_all) else None,
        'down_p90': round(float(down_all.quantile(0.90)), 4) if len(down_all) else None,
        'down_p99': round(float(down_all.quantile(0.99)), 4) if len(down_all) else None,
    }

    # by_hour
    by_hour = []
    for hr, g in df.groupby('hr'):
        if len(g) >= 3:
            row = agg(g)
            row.update(hr=int(hr), hr_label=f'{int(hr):02d}:00')
            by_hour.append(row)
    by_hour.sort(key=lambda r: r['hr'])

    # by_dow
    by_dow = []
    for dow, g in df.groupby('dow'):
        if len(g) >= 3:
            row = agg(g)
            row.update(dow=int(dow), dow_name=DOW_NAMES.get(int(dow), '?'))
            by_dow.append(row)
    by_dow.sort(key=lambda r: r['dow'])

    # by_session
    by_session = []
    for sess, g in df.groupby('session'):
        row = agg(g)
        row.update(session=sess)
        by_session.append(row)

    # by_year
    by_year = []
    for yr, g in df.groupby('yr'):
        row = agg(g)
        row.update(yr=int(yr))
        by_year.append(row)
    by_year.sort(key=lambda r: r['yr'])

    return {
        'meta': meta,
        'by_hour': by_hour,
        'by_dow': by_dow,
        'by_session': by_session,
        'by_year': by_year,
        'up_dist': dist_stats(up_all),
        'down_dist': dist_stats(down_all),
        'recent_reps': df.to_dict('records'),
    }


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--models', nargs='*', default=list(MODELS.keys()))
    parser.add_argument('--table', default='nq_1m')
    args = parser.parse_args()

    t0 = time.time()
    con = duckdb.connect(str(DB_PATH), read_only=True)
    raw = load_1m(con, args.table)
    con.close()
    print(f'Loaded {len(raw):,} bars from {args.table}')

    instrument = 'NQ' if args.table == 'nq_1m' else 'ES' if args.table == 'es_1m' else args.table.upper()

    # Build all needed timeframes
    tfs_needed = set()
    for mk in args.models:
        cfg = MODELS[mk]
        tfs_needed.add(cfg['htf_min'])
        tfs_needed.add(cfg['chart_tf_min'])

    resampled = {}
    for tf in sorted(tfs_needed):
        if tf == 1:
            resampled[1] = raw
        else:
            resampled[tf] = resample(raw, tf, f'{tf}min')
        print(f'  {tf}min: {len(resampled[tf]):,} bars')

    arrs = {}
    for tf, df in resampled.items():
        if tf == 1:
            arrs[tf] = df_1m_to_arrays(df)
        else:
            arrs[tf] = df_to_arrays(df)

    m1_arrs = df_1m_to_arrays(raw)

    results = {}
    for model_key in args.models:
        cfg = MODELS[model_key]
        htf_arrs = arrs[cfg['htf_min']]
        chart_arrs = arrs[cfg['chart_tf_min']]

        print(f'\n  Scanning {model_key} ...', flush=True)
        reps = scan_fixed_constant_model(htf_arrs, chart_arrs, m1_arrs, model_key, cfg)
        print(f'    {len(reps)} reps emitted', flush=True)

        df = pd.DataFrame(reps) if reps else pd.DataFrame()
        stats = build_model_stats(df, model_key, cfg, instrument)
        results[model_key] = stats

    with open(OUT_PATH, 'w') as f:
        json.dump(results, f, default=str)
    print(f'\nWritten -> {OUT_PATH}')
    print(f'Total time: {time.time() - t0:.1f}s')

    # Summary
    print('\n── SUMMARY ─────────────────────────────────────────')
    for mk in args.models:
        m = results[mk].get('meta', {})
        print(f"  {mk:8s}  reps={m.get('total_reps', 0):>7,}  up_p99={m.get('up_p99', 0):.4f}%  down_p99={m.get('down_p99', 0):.4f}%")


if __name__ == '__main__':
    main()
