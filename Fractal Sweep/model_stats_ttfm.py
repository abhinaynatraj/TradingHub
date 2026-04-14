#!/usr/bin/env python3
"""
model_stats.py  —  TTFM (TTrades Fractal Model) Backtesting Engine v1.0
=========================================================================
Detects T-Spot → Touch → Pivot Sweep Confirmation setups across four
HTF/chartTF pairs and measures MAE/MFE for each trade.

No WIN/LOSS resolution — trades carry MAE/MFE only.
No risk profiles, no filters, no SMT, no Q1/CISD.

Usage:
    python3 model_stats.py                          # all 4 models
    python3 model_stats.py --models 15M_1M 1H_5M
    python3 model_stats.py --table es_1m
"""

import argparse
import math
import json
import time
import duckdb
import pandas as pd
import numpy as np
from pathlib import Path

# ── PATHS ─────────────────────────────────────────────────────────────────────
DB_PATH  = Path(__file__).parent / 'candle_science.duckdb'
OUT_PATH = Path(__file__).parent / 'model_stats_ttfm.json'

# ── MODEL DEFINITIONS ─────────────────────────────────────────────────────────
MODELS = {
    '15M_1M':  dict(htf_min=15,  chart_tf_min=1),
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
    raw_rth = raw[
        (raw['hr'] >= 7) & ((raw['hr'] < 16) | ((raw['hr'] == 16) & (raw['mn'] == 0)))
    ].copy()
    print(f"   {len(raw):,} total bars  |  {len(raw_rth):,} RTH (07:00-16:00)")
    return raw, raw_rth


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
    """Convert DatetimeIndex to int64 nanoseconds regardless of unit (us/ns)."""
    return idx.astype('datetime64[ns]').view('int64').copy()


def df_to_arrays(df):
    """Convert a time-indexed resampled OHLC dataframe to numpy arrays."""
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
    """Convert 1m dataframe to numpy arrays."""
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


# ── LOG MIDPOINT (TTFM Pine port) ────────────────────────────────────────────
def log_midpoint(h, l, o, c):
    """TTFM log-space midpoint."""
    log_h, log_l, log_o, log_c = math.log(h), math.log(l), math.log(o), math.log(c)
    body = abs(log_c - log_o)
    upper_wick = log_h - max(log_o, log_c)
    lower_wick = min(log_o, log_c) - log_l
    if max(upper_wick, lower_wick) > body:
        if upper_wick > lower_wick:
            log_mid = log_h - upper_wick / 2
        else:
            log_mid = log_l + lower_wick / 2
    else:
        log_mid = (log_h + log_l) / 2
    return math.exp(log_mid)


# ── OUTSIDE BAR CHECK ────────────────────────────────────────────────────────
def is_outside_bar(lc_h, lc_l, lc_c, pc_h, pc_l):
    return (lc_h > pc_h and lc_l < pc_l and lc_c > pc_l and lc_c < pc_h)


# ── T-SPOT DETECTION (6 types) ───────────────────────────────────────────────
def detect_tspot(lc, pc, ppc):
    """
    lc/pc/ppc are dicts with keys: o, h, l, c
    Returns (tspot_type, direction, sweep_mid, close_level, c2_level) or None.
    Types: normal, expansive, protrend. Directions: LONG, SHORT.
    """
    if is_outside_bar(lc['h'], lc['l'], lc['c'], pc['h'], pc['l']):
        return None

    mid_prev = log_midpoint(pc['h'], pc['l'], pc['o'], pc['c'])

    # Type 1: Normal Bearish - lc sweeps pc high, closes below it
    if lc['h'] > pc['h'] and lc['c'] < pc['h']:
        sweep_mid = log_midpoint(lc['h'], lc['l'], lc['o'], lc['c'])
        if lc['c'] < sweep_mid:
            return ('normal', 'SHORT', sweep_mid, lc['c'], lc['h'])

    # Type 2: Normal Bullish - lc sweeps pc low, closes above it
    if lc['l'] < pc['l'] and lc['c'] > pc['l']:
        sweep_mid = log_midpoint(lc['h'], lc['l'], lc['o'], lc['c'])
        if lc['c'] > sweep_mid:
            return ('normal', 'LONG', sweep_mid, lc['c'], lc['l'])

    # Type 3: Expansive Bearish - pc swept ppc high, lc confirms down
    if (pc['h'] > ppc['h'] and lc['c'] < max(pc['o'], pc['c'])
        and (pc['c'] >= log_midpoint(pc['h'], pc['l'], pc['o'], pc['c'])
             or pc['c'] >= ppc['h']
             or (pc['h'] > ppc['h'] and pc['l'] < ppc['l'] and pc['c'] > ppc['l'] and pc['c'] < ppc['h']))):
        sweep_mid = log_midpoint(lc['h'], lc['l'], lc['o'], lc['c'])
        if lc['c'] < sweep_mid:
            return ('expansive', 'SHORT', sweep_mid, lc['c'], pc['h'])

    # Type 4: Expansive Bullish - pc swept ppc low, lc confirms up
    if (pc['l'] < ppc['l'] and lc['c'] > min(pc['o'], pc['c'])
        and (pc['c'] <= log_midpoint(pc['h'], pc['l'], pc['o'], pc['c'])
             or pc['c'] <= ppc['l']
             or (pc['h'] > ppc['h'] and pc['l'] < ppc['l'] and pc['c'] > ppc['l'] and pc['c'] < ppc['h']))):
        sweep_mid = log_midpoint(lc['h'], lc['l'], lc['o'], lc['c'])
        if lc['c'] > sweep_mid:
            return ('expansive', 'LONG', sweep_mid, lc['c'], pc['l'])

    # Type 5: Pro-trend Bullish - lc dips below prev midpoint, closes above prev high
    if lc['l'] < mid_prev and lc['l'] > pc['o'] and lc['c'] > pc['h']:
        sweep_mid = log_midpoint(lc['h'], lc['l'], lc['o'], lc['c'])
        if lc['c'] > sweep_mid:
            return ('protrend', 'LONG', sweep_mid, lc['c'], None)

    # Type 6: Pro-trend Bearish - lc rises above prev midpoint, closes below prev low
    if lc['h'] > mid_prev and lc['h'] < pc['o'] and lc['c'] < pc['l']:
        sweep_mid = log_midpoint(lc['h'], lc['l'], lc['o'], lc['c'])
        if lc['c'] < sweep_mid:
            return ('protrend', 'SHORT', sweep_mid, lc['c'], None)

    return None


# ── PIVOT DETECTION (2-bar left, 2-bar right, body-based) ─────────────────────
def detect_pivot_high(opens, closes, idx):
    if idx < 2 or idx + 2 >= len(opens):
        return None
    body = max(opens[idx], closes[idx])
    for offset in [-2, -1, 1, 2]:
        if max(opens[idx + offset], closes[idx + offset]) >= body:
            return None
    return float(body)


def detect_pivot_low(opens, closes, idx):
    if idx < 2 or idx + 2 >= len(opens):
        return None
    body = min(opens[idx], closes[idx])
    for offset in [-2, -1, 1, 2]:
        if min(opens[idx + offset], closes[idx + offset]) <= body:
            return None
    return float(body)


# ── TOUCH DETECTION ───────────────────────────────────────────────────────────
def check_touch(bar_high, bar_low, bar_open, bar_close, touch_level, direction):
    if direction == 'LONG':
        return (bar_low < touch_level or bar_open < touch_level) and bar_close > touch_level
    else:
        return (bar_high > touch_level or bar_open > touch_level) and bar_close < touch_level


# ── CONFIRMATION DETECTION ────────────────────────────────────────────────────
def check_confirmation(bar_open, bar_close, pivot_level, pivot_bar_idx, touch_bar_idx, touch_level, direction):
    if pivot_bar_idx >= touch_bar_idx:
        return False
    if direction == 'LONG':
        return bar_open < pivot_level and bar_close > pivot_level and pivot_level > touch_level
    else:
        return bar_open > pivot_level and bar_close < pivot_level and pivot_level < touch_level


# ── HOUR OPEN HELPER ─────────────────────────────────────────────────────────
_HOUR_NS = 60 * 60 * 10**9

def compute_hour_open_ttfm(m1_arrs, entry_ts_ns):
    """
    Return the open of the first 1m bar inside the clock hour containing
    entry_ts_ns. Floor-hour boundary on naive-ET ts_ns. Returns None if
    the entire hour has no 1m bars.
    """
    hour_start_ns = (int(entry_ts_ns) // _HOUR_NS) * _HOUR_NS
    hour_end_ns = hour_start_ns + _HOUR_NS
    ts = m1_arrs['ts_ns']
    idx = int(np.searchsorted(ts, hour_start_ns, side='left'))
    if idx >= len(ts):
        return None
    if int(ts[idx]) >= hour_end_ns:
        return None
    return float(m1_arrs['open'][idx])


# ── MFE MEASUREMENT ──────────────────────────────────────────────────────────
def measure_mfe(m1_arrs, entry_ts_ns, stop_price, cutoff_ns, pivot_level, direction):
    start = int(np.searchsorted(m1_arrs['ts_ns'], entry_ts_ns, side='left'))
    end = min(int(np.searchsorted(m1_arrs['ts_ns'], cutoff_ns, side='right')), len(m1_arrs['ts_ns']))
    if start >= end:
        return None
    if direction == 'LONG':
        max_fav = pivot_level
        for k in range(start, end):
            if m1_arrs['low'][k] <= stop_price:
                break
            if m1_arrs['high'][k] > max_fav:
                max_fav = m1_arrs['high'][k]
        return (max_fav - pivot_level) / pivot_level * 100
    else:
        min_fav = pivot_level
        for k in range(start, end):
            if m1_arrs['high'][k] >= stop_price:
                break
            if m1_arrs['low'][k] < min_fav:
                min_fav = m1_arrs['low'][k]
        return (pivot_level - min_fav) / pivot_level * 100


# ── MAIN SCAN LOOP ───────────────────────────────────────────────────────────
def scan_ttfm_model(htf_arrs, chart_arrs, m1_arrs, model_key, cfg):
    htf_n = len(htf_arrs['ts_ns'])
    htf_period_ns = cfg['htf_min'] * 60 * 10**9
    trades = []
    tspot_count = 0
    pct_step = max(1, htf_n // 10)

    for i in range(3, htf_n):
        if (i - 3) % pct_step == 0:
            pct = (i - 3) / max(htf_n - 3, 1) * 100
            print(f'    [{model_key}] {pct:.0f}%  ({i:,}/{htf_n:,} HTF bars, {len(trades)} trades, {tspot_count} tspots)', flush=True)
        if htf_arrs['ts_ns'][i] - htf_arrs['ts_ns'][i-1] > 3 * htf_period_ns:
            continue

        # Build candle dicts
        lc  = {'o': float(htf_arrs['open'][i-1]), 'h': float(htf_arrs['high'][i-1]),
               'l': float(htf_arrs['low'][i-1]),  'c': float(htf_arrs['close'][i-1])}
        pc  = {'o': float(htf_arrs['open'][i-2]), 'h': float(htf_arrs['high'][i-2]),
               'l': float(htf_arrs['low'][i-2]),  'c': float(htf_arrs['close'][i-2])}
        ppc = {'o': float(htf_arrs['open'][i-3]), 'h': float(htf_arrs['high'][i-3]),
               'l': float(htf_arrs['low'][i-3]),  'c': float(htf_arrs['close'][i-3])}

        tspot = detect_tspot(lc, pc, ppc)
        if tspot is None:
            continue

        tspot_type, direction, sweep_mid, close_level, c2_level = tspot
        tspot_count += 1
        touch_level = close_level

        htf_start_ns = int(htf_arrs['ts_ns'][i])
        htf_end_ns = htf_start_ns + htf_period_ns

        ct_start = int(np.searchsorted(chart_arrs['ts_ns'], htf_start_ns, side='left'))
        ct_end = int(np.searchsorted(chart_arrs['ts_ns'], htf_end_ns, side='right'))
        if ct_start >= ct_end:
            continue

        last_pivot_high, last_pivot_high_bar = None, -1
        last_pivot_low, last_pivot_low_bar = None, -1
        touched = False
        touch_bar_idx = -1

        for j in range(ct_start, ct_end):
            # Update pivots continuously
            if j >= 2:
                ph = detect_pivot_high(chart_arrs['open'], chart_arrs['close'], j - 2)
                if ph is not None:
                    last_pivot_high, last_pivot_high_bar = ph, j - 2
                pl = detect_pivot_low(chart_arrs['open'], chart_arrs['close'], j - 2)
                if pl is not None:
                    last_pivot_low, last_pivot_low_bar = pl, j - 2

            if not touched:
                if check_touch(float(chart_arrs['high'][j]), float(chart_arrs['low'][j]),
                               float(chart_arrs['open'][j]), float(chart_arrs['close'][j]),
                               touch_level, direction):
                    touched = True
                    touch_bar_idx = j
                continue

            # Check confirmation
            pivot_level = last_pivot_high if direction == 'LONG' else last_pivot_low
            pivot_bar = last_pivot_high_bar if direction == 'LONG' else last_pivot_low_bar
            if pivot_level is None:
                continue

            if check_confirmation(float(chart_arrs['open'][j]), float(chart_arrs['close'][j]),
                                  pivot_level, pivot_bar, touch_bar_idx, touch_level, direction):
                entry_price = float(chart_arrs['close'][j])
                entry_ts_ns = int(chart_arrs['ts_ns'][j])

                # Hour open: first 1m bar inside the clock hour containing the entry.
                # Used by the Hour-Open Bias filter (entry > hour_open = bullish setup).
                hour_open = compute_hour_open_ttfm(m1_arrs, entry_ts_ns)

                if direction == 'LONG':
                    stop_price = float(np.min(chart_arrs['low'][pivot_bar:j+1]))
                    mae_pct = (pivot_level - stop_price) / pivot_level * 100
                else:
                    stop_price = float(np.max(chart_arrs['high'][pivot_bar:j+1]))
                    mae_pct = (stop_price - pivot_level) / pivot_level * 100

                mfe_cutoff_ns = htf_end_ns + htf_period_ns
                mfe_pct = measure_mfe(m1_arrs, entry_ts_ns, stop_price, mfe_cutoff_ns, pivot_level, direction)

                # Get session label
                hr = int(chart_arrs['hr'][j])
                mn = int(chart_arrs['mn'][j]) if 'mn' in chart_arrs else 0
                t_dec = hr + mn / 60.0
                if 7.0 <= t_dec < 8.5:
                    session = 'PRE'
                elif 8.5 <= t_dec < 11.5:
                    session = 'NY1'
                elif 11.5 <= t_dec < 16.0:
                    session = 'NY2'
                else:
                    session = 'OVERNIGHT'

                # Attribute the trade to the HTF block where the entry actually fires (i),
                # not the T-Spot candle's block (i-1). Matters for overnight 4H blocks that
                # span midnight — otherwise by_dow and by_year break on those trades.
                trade = {
                    'date': str(htf_arrs['trade_date'][i]),
                    'yr': int(htf_arrs['yr'][i]),
                    'dow': int(htf_arrs['dow'][i]),
                    'dow_name': DOW_NAMES.get(int(htf_arrs['dow'][i]), '?'),
                    'hr': hr,
                    'mn': mn,
                    'entry_time': f'{hr:02d}:{mn:02d}',
                    'session': session,
                    'direction': direction,
                    'tspot_type': tspot_type,
                    'entry_price': round(entry_price, 2),
                    'pivot_level': round(pivot_level, 2),
                    'stop_price': round(stop_price, 2),
                    'sweep_mid': round(sweep_mid, 2),
                    'close_level': round(close_level, 2),
                    'c2_level': round(c2_level, 2) if c2_level else None,
                    'mae_pct': round(mae_pct, 4),
                    'mfe_pct': round(mfe_pct, 4) if mfe_pct is not None else None,
                    'risk_pts': round(abs(entry_price - stop_price), 2),
                    'hour_open': round(hour_open, 2) if hour_open is not None else None,
                }
                trades.append(trade)
                break  # one trade per T-Spot

    return trades


# ── AGGREGATION (MAE/MFE only, no WIN/LOSS) ──────────────────────────────────
def agg(g):
    n = len(g)
    if n == 0:
        return dict(n=0, avg_mae=None, avg_mfe=None, med_mae=None, med_mfe=None,
                    p90_mae=None, p90_mfe=None)
    mae = g['mae_pct'].dropna()
    mfe = g['mfe_pct'].dropna()
    return dict(
        n=n,
        avg_mae=round(float(mae.mean()), 4) if len(mae) else None,
        avg_mfe=round(float(mfe.mean()), 4) if len(mfe) else None,
        med_mae=round(float(mae.median()), 4) if len(mae) else None,
        med_mfe=round(float(mfe.median()), 4) if len(mfe) else None,
        p90_mae=round(float(mae.quantile(0.90)), 4) if len(mae) >= 5 else None,
        p90_mfe=round(float(mfe.quantile(0.90)), 4) if len(mfe) >= 5 else None,
    )


def build_model_stats(df, model_key):
    if df.empty:
        return {'meta': {'model_key': model_key, 'total_trades': 0}, 'recent_trades': []}

    n = len(df)
    mae_all = df['mae_pct'].dropna()
    mfe_all = df['mfe_pct'].dropna()
    dates = sorted(df['date'].unique())

    meta = {
        'model_key': model_key,
        'instrument': 'NQ',
        'date_range': f'{dates[0]} to {dates[-1]}' if dates else '',
        'total_trades': n,
        'trading_days': len(dates),
        'setups_per_day': round(n / max(len(dates), 1), 2),
        'avg_mae': round(float(mae_all.mean()), 4) if len(mae_all) else None,
        'avg_mfe': round(float(mfe_all.mean()), 4) if len(mfe_all) else None,
        'med_mae': round(float(mae_all.median()), 4) if len(mae_all) else None,
        'med_mfe': round(float(mfe_all.median()), 4) if len(mfe_all) else None,
    }

    # by_hour
    by_hour = []
    for (hr, d), g in df.groupby(['hr', 'direction']):
        if len(g) >= 3:
            row = agg(g)
            row.update(hr=int(hr), hr_label=f'{int(hr):02d}:00', direction=d)
            by_hour.append(row)

    # by_dow
    by_dow = []
    for (dow, d), g in df.groupby(['dow', 'direction']):
        if len(g) >= 3:
            row = agg(g)
            row.update(dow=int(dow), dow_name=DOW_NAMES.get(int(dow), '?'), direction=d)
            by_dow.append(row)

    # by_session
    by_session = []
    if 'session' in df.columns:
        for (sess, d), g in df.groupby(['session', 'direction']):
            row = agg(g)
            row.update(session=sess, direction=d)
            by_session.append(row)

    # by_tspot_type
    by_tspot_type = []
    for (tt, d), g in df.groupby(['tspot_type', 'direction']):
        row = agg(g)
        row.update(tspot_type=tt, direction=d)
        by_tspot_type.append(row)

    # by_year
    by_year = []
    for yr, g in df.groupby('yr'):
        row = agg(g)
        row.update(yr=int(yr))
        by_year.append(row)

    # dir_summary
    dir_summary = []
    for d, g in df.groupby('direction'):
        row = agg(g)
        row.update(direction=d)
        dir_summary.append(row)

    # MAE/MFE distributions
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

    recent_trades = df.to_dict('records')

    return {
        'meta': meta,
        'by_hour': by_hour,
        'by_dow': by_dow,
        'by_session': by_session,
        'by_tspot_type': by_tspot_type,
        'by_year': by_year,
        'dir_summary': dir_summary,
        'mae_dist': dist_stats(mae_all),
        'mfe_dist': dist_stats(mfe_all),
        'recent_trades': recent_trades,
    }


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--models', nargs='*', default=list(MODELS.keys()))
    parser.add_argument('--table', default='nq_1m')
    args = parser.parse_args()

    t0 = time.time()
    con = duckdb.connect(str(DB_PATH), read_only=True)
    raw, _ = load_1m(con, args.table)
    con.close()
    print(f'Loaded {len(raw):,} bars from {args.table}')

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
        trades = scan_ttfm_model(htf_arrs, chart_arrs, m1_arrs, model_key, cfg)
        print(f'    {len(trades)} trades found', flush=True)

        df = pd.DataFrame(trades) if trades else pd.DataFrame()
        stats = build_model_stats(df, model_key)
        results[model_key] = stats

    out_path = Path(__file__).parent / 'model_stats_ttfm.json'
    with open(out_path, 'w') as f:
        json.dump(results, f, default=str)
    print(f'\nWritten -> {out_path}')
    print(f'Total time: {time.time() - t0:.1f}s')


if __name__ == '__main__':
    main()
