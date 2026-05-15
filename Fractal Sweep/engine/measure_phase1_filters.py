#!/usr/bin/env python3
"""
measure_phase1_filters.py — Pre-build impact study for Phase-1 filters.

Computes per-trade flags for the two Phase-1 candidates without modifying the
production engine:

  passes_p42      Amas "late-extreme" rule. Swept extreme of the prior HTF
                  candle was printed in the last 30% of that candle's window
                  (minute >= 42 for 1H, >= 21 for 30M).
  passes_pd_cisd  Fearing "CISD in PD" rule. CISD bar close sits in the
                  premium half (shorts) or discount half (longs) of the prior
                  HTF range.

Loads the existing trade rows from model_stats.json, re-queries the DB to
recover the prior HTF candle's OHLC + 1-min minute-of-extreme, computes the
two flags per row, and prints WR/EV summaries:
  - each filter standalone
  - each filter conditional on SMT
  - both filters combined, and combined with SMT
  - 5-filter combo (F3 + F4 + SMT + p42 + pd) compared vs current 3-filter best

Side effects: none. Writes nothing. Pure-read against DB + JSON.

Usage:
    cd "Fractal Sweep" && python3 engine/measure_phase1_filters.py
"""

from pathlib import Path
import json
import duckdb
import pandas as pd
import numpy as np
from datetime import timedelta

ROOT     = Path(__file__).parent.parent
DB_PATH  = ROOT / 'candle_science.duckdb'
JSON_PATH = ROOT / 'model_stats.json'

MODELS = {
    '1H_5M':  {'sweep_tf_min': 60, 'threshold_min': 42},
    '30M_3M': {'sweep_tf_min': 30, 'threshold_min': 21},
}


def load_trades(model_key):
    """Pull all simple_1r trades (full history) for a model from the JSON."""
    with open(JSON_PATH) as f:
        j = json.load(f)
    key = f'{model_key}_PREV_CISD'
    rows = j[key]['profiles']['simple_1r']['recent_trades']
    df = pd.DataFrame(rows)
    # Keep only resolved trades (WIN/LOSS/BE). SKIP rows have no CISD/outcome.
    df = df[df['outcome'].isin(['WIN', 'LOSS', 'BE'])].copy()
    return df


def load_1m_bars(con):
    """Load NQ 1m bars indexed by NY-local timestamp."""
    print('  Loading NQ 1m bars from DuckDB...')
    df = con.execute("""
        SELECT
            timezone('America/New_York', timestamp) AS ts,
            high, low, open, close
        FROM nq_1m
        ORDER BY ts
    """).df()
    # Strip tz info so we can do tz-naive datetime arithmetic with row dates.
    df['ts'] = pd.to_datetime(df['ts']).dt.tz_localize(None)
    df = df.set_index('ts')
    print(f'  Loaded {len(df):,} 1m bars')
    return df


def prior_htf_window(trade_date, hr, mn, sweep_tf_min):
    """Given an entry's date/hour/minute in NY time, derive the prior HTF
    candle's [start, end) window. The 'current' HTF anchor is the one the
    sweep happens in. The 'prior' anchor is the one immediately before."""
    entry_dt = pd.Timestamp(trade_date) + pd.Timedelta(hours=hr, minutes=mn)
    # Floor to the current HTF anchor start
    if sweep_tf_min == 60:
        curr_start = entry_dt.replace(minute=0, second=0, microsecond=0, nanosecond=0)
    else:  # 30
        curr_start = entry_dt.replace(minute=(entry_dt.minute // 30) * 30,
                                       second=0, microsecond=0, nanosecond=0)
    prior_start = curr_start - pd.Timedelta(minutes=sweep_tf_min)
    prior_end   = curr_start - pd.Timedelta(minutes=1)  # inclusive
    return prior_start, prior_end


def compute_flags_for_trades(df, m1, model_cfg):
    """Add passes_p42, prior_extreme_minute_offset, prior_high, prior_low,
    cisd_pd_pct, passes_pd_cisd to df. Mutates and returns df."""
    sweep_tf_min  = model_cfg['sweep_tf_min']
    threshold_min = model_cfg['threshold_min']

    p42_results = []
    pd_results  = []
    minute_offsets = []
    pd_pcts        = []

    skipped = 0
    for row in df.itertuples():
        prior_start, prior_end = prior_htf_window(
            row.date, row.hr, row.mn, sweep_tf_min
        )
        try:
            window = m1.loc[prior_start:prior_end]
        except KeyError:
            window = m1.iloc[0:0]
        if len(window) == 0:
            skipped += 1
            p42_results.append(False)
            pd_results.append(False)
            minute_offsets.append(np.nan)
            pd_pcts.append(np.nan)
            continue

        prior_high = float(window['high'].max())
        prior_low  = float(window['low'].min())
        prior_range = prior_high - prior_low

        # Locate the swept extreme. SHORT swept prior high; LONG swept prior low.
        if row.direction == 'SHORT':
            extreme_idx = window['high'].idxmax()
        else:
            extreme_idx = window['low'].idxmin()
        offset_min = int((extreme_idx - prior_start).total_seconds() // 60)
        minute_offsets.append(offset_min)
        p42_results.append(offset_min >= threshold_min)

        # CISD PD: location of cisd_close inside prior HTF range
        if prior_range > 0:
            r = (float(row.cisd_close) - prior_low) / prior_range
        else:
            r = 0.5
        pd_pcts.append(r)
        if row.direction == 'SHORT':
            pd_results.append(r >= 0.5)
        else:
            pd_results.append(r <= 0.5)

    df = df.copy()
    df['prior_extreme_minute_offset'] = minute_offsets
    df['prior_extreme_minute_pct']    = [m / sweep_tf_min if not np.isnan(m) else np.nan
                                          for m in minute_offsets]
    df['cisd_pd_pct'] = pd_pcts
    df['passes_p42']    = p42_results
    df['passes_pd_cisd'] = pd_results
    if skipped:
        print(f'  WARN: skipped {skipped} trades (no 1m bars in prior window)')
    return df


def stats(df_subset, label):
    n = len(df_subset)
    if n == 0:
        return {'label': label, 'n': 0, 'wr': float('nan'),
                'ev': float('nan'), 'pf': float('nan')}
    wins = int((df_subset['outcome'] == 'WIN').sum())
    wr   = 100.0 * wins / n
    ev   = float(df_subset['r'].mean())
    gross_win  = float(df_subset.loc[df_subset['r'] > 0, 'r'].sum())
    gross_loss = float(df_subset.loc[df_subset['r'] < 0, 'r'].sum())
    pf = (gross_win / -gross_loss) if gross_loss < 0 else float('inf')
    return {'label': label, 'n': n, 'wr': wr, 'ev': ev, 'pf': pf}


def print_row(s, base_wr=None, base_ev=None, indent='  '):
    delta_wr = (s['wr'] - base_wr) if base_wr is not None else None
    delta_ev = (s['ev'] - base_ev) if base_ev is not None else None
    dwr = f"  ΔWR={delta_wr:+.2f}%" if delta_wr is not None else ''
    dev = f"  ΔEV={delta_ev:+.3f}R" if delta_ev is not None else ''
    print(f"{indent}{s['label']:<48} N={s['n']:>5}  "
          f"WR={s['wr']:5.2f}%  EV={s['ev']:+.3f}R  PF={s['pf']:5.2f}{dwr}{dev}")


def report_model(model_key, df):
    print(f"\n{'='*92}\nMODEL: {model_key}\n{'='*92}")

    # 1) Baseline
    base = stats(df, 'baseline (all resolved trades)')
    print_row(base)

    # 2) Existing single filters (for sanity)
    print('\n  --- existing filters (sanity check) ---')
    f3   = stats(df[df['passes_f3']],   'F3 (shallow sweep)')
    f4   = stats(df[df['passes_f4']],   'F4 (closed back inside)')
    smt  = stats(df[df['smt']],         'SMT (NQ-ES divergence)')
    for s in (f3, f4, smt):
        print_row(s, base['wr'], base['ev'])

    # 3) New Phase-1 filters standalone
    print('\n  --- Phase-1 candidates standalone ---')
    p42  = stats(df[df['passes_p42']],     'P42 (Amas late-extreme :42)')
    pd_c = stats(df[df['passes_pd_cisd']], 'PD  (Fearing CISD-in-PD)')
    for s in (p42, pd_c):
        print_row(s, base['wr'], base['ev'])

    # 4) Conditional on SMT
    print('\n  --- conditional on SMT ---')
    smt_only = df[df['smt']]
    smt_base = stats(smt_only, 'SMT baseline')
    print_row(smt_base)
    smt_p42  = stats(smt_only[smt_only['passes_p42']],     '  SMT ∧ P42')
    smt_pd   = stats(smt_only[smt_only['passes_pd_cisd']], '  SMT ∧ PD')
    smt_both = stats(smt_only[smt_only['passes_p42'] & smt_only['passes_pd_cisd']],
                     '  SMT ∧ P42 ∧ PD')
    for s in (smt_p42, smt_pd, smt_both):
        print_row(s, smt_base['wr'], smt_base['ev'], indent='    ')

    # 5) Combined with existing F3+F4+SMT (the current best combo)
    print('\n  --- compared to current best combo (F3 ∧ F4 ∧ SMT) ---')
    mask_345 = df['passes_f3'] & df['passes_f4'] & df['smt']
    best345 = stats(df[mask_345], 'F3 ∧ F4 ∧ SMT (current best)')
    print_row(best345, base['wr'], base['ev'])
    mask_345_p42  = mask_345 & df['passes_p42']
    mask_345_pd   = mask_345 & df['passes_pd_cisd']
    mask_345_both = mask_345 & df['passes_p42'] & df['passes_pd_cisd']
    for label, mask in [
        ('  + P42',        mask_345_p42),
        ('  + PD',         mask_345_pd),
        ('  + P42 + PD',   mask_345_both),
    ]:
        s = stats(df[mask], label)
        print_row(s, best345['wr'], best345['ev'], indent='    ')

    # 6) Distribution diagnostics
    print('\n  --- distribution diagnostics ---')
    valid_minute = df['prior_extreme_minute_offset'].dropna()
    valid_pd     = df['cisd_pd_pct'].dropna()
    print(f"  prior_extreme_minute_offset: n={len(valid_minute):,}  "
          f"min={valid_minute.min():.0f}  median={valid_minute.median():.0f}  "
          f"max={valid_minute.max():.0f}  pct_pass_p42={100*df['passes_p42'].mean():.1f}%")
    print(f"  cisd_pd_pct:                 n={len(valid_pd):,}  "
          f"min={valid_pd.min():.2f}  median={valid_pd.median():.2f}  "
          f"max={valid_pd.max():.2f}  pct_pass_pd={100*df['passes_pd_cisd'].mean():.1f}%")

    # 7) Quick orthogonality check vs existing filters
    print('\n  --- orthogonality (correlation matrix) ---')
    flags = df[['passes_f3', 'passes_f4', 'smt', 'passes_p42', 'passes_pd_cisd']].astype(int)
    corr = flags.corr()
    for r in corr.index:
        cells = '  '.join(f"{corr.loc[r,c]:+.2f}" for c in corr.columns)
        print(f"    {r:<18} {cells}")


def main():
    print(f"Reading: {JSON_PATH}")
    print(f"DB:      {DB_PATH}")
    con = duckdb.connect(str(DB_PATH), read_only=True)
    m1 = load_1m_bars(con)

    for model_key, cfg in MODELS.items():
        print(f"\n--- Loading trades for {model_key} ---")
        df = load_trades(model_key)
        print(f"  {len(df):,} resolved trades loaded")
        df = compute_flags_for_trades(df, m1, cfg)
        report_model(model_key, df)

    print('\nDone. Read-only — no files written.')


if __name__ == '__main__':
    main()
