#!/usr/bin/env python3
"""
filter_search.py — Exhaustive filter search for high win-rate subsets
=====================================================================
Runs the sweep+CISD detection engine on all models, then searches every
combination of time / day / direction / session / sweep-size filters to
find the highest win-rate pockets.

Out-of-sample check: years are split 60/40 (IS / OOS by calendar year).
A combination is only flagged as "robust" if OOS WR ≥ target_wr - 0.10.

Usage:
    python3 filter_search.py                          # all 3 models, WR ≥ 80%
    python3 filter_search.py --target-wr 0.90 --min-n 15
    python3 filter_search.py --models 4H_15M 1H_5M --top 20
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from model_stats import (
    connect, load_1m, resample, df_to_arrays, df_1m_to_arrays,
    detect_model, MODELS, DB_PATH, RR, CISD_FAST_BARS,
)

DOW_NAMES = {1: 'Mon', 2: 'Tue', 3: 'Wed', 4: 'Thu', 5: 'Fri'}

# ── Data collection ────────────────────────────────────────────────────────────
def collect_raw_trades(model_keys, table='nq_1m'):
    con = connect(DB_PATH)
    df_1m_full, df_1m_rth = load_1m(con, table)

    needed_sweep = {MODELS[mk]['sweep_tf_min'] for mk in model_keys}
    needed_cisd  = {MODELS[mk]['cisd_tf_min']  for mk in model_keys}

    sweep_dfs = {
        tf: resample(df_1m_full if tf >= 1440 else df_1m_rth, tf,
                     '1D' if tf >= 1440 else f'{tf}min')
        for tf in sorted(needed_sweep)
    }
    cisd_dfs = {
        tf: resample(df_1m_rth, tf, f'{tf}min')
        for tf in sorted(needed_cisd)
    }

    sweep_arrs   = {tf: df_to_arrays(df) for tf, df in sweep_dfs.items()}
    cisd_arrs    = {tf: df_to_arrays(df) for tf, df in cisd_dfs.items()}
    m1_full_arrs = df_1m_to_arrays(df_1m_full)
    m1_rth_arrs  = df_1m_to_arrays(df_1m_rth)

    raw = {}
    for mk in model_keys:
        cfg    = MODELS[mk]
        s_arrs = sweep_arrs[cfg['sweep_tf_min']]
        c_arrs = cisd_arrs[cfg['cisd_tf_min']]
        m1     = m1_full_arrs if cfg['sweep_tf_min'] >= 1440 else m1_rth_arrs
        raw[mk] = detect_model(m1, s_arrs, c_arrs, mk, cfg)

    return raw


# ── Per-subset stats ───────────────────────────────────────────────────────────
def stats(g, rr=RR):
    n    = len(g)
    wins = int(g['win'].sum())
    wr   = wins / n
    ev   = round(wr * rr - (1 - wr), 3)
    pf   = round((wins * rr) / max(n - wins, 1), 3)
    return n, wins, round(wr, 4), ev, pf


def oos_stats(df, split_yr, rr=RR):
    """Stats for the OOS window (years >= split_yr)."""
    oos = df[df['yr'] >= split_yr]
    if len(oos) < 5:
        return None, 0
    n, wins, wr, ev, pf = stats(oos, rr)
    return wr, n


# ── Main search ────────────────────────────────────────────────────────────────
def search(df_raw, model_key, target_wr, min_n, rr=RR):
    """
    Exhaustively test every single-dimension and multi-dimension filter combo.
    Returns list of result dicts sorted by (WR desc, EV desc, N desc).
    """
    df = df_raw[df_raw['rejected_by'] == ''].copy()
    wl = df[df['outcome'].isin(['WIN', 'LOSS'])].copy()
    wl['win'] = (wl['outcome'] == 'WIN').astype(int)
    if len(wl) == 0:
        return []

    # IS / OOS split: first 60% of years = IS, remainder = OOS
    years     = sorted(wl['yr'].unique())
    split_yr  = years[max(1, int(len(years) * 0.6))] if len(years) >= 3 else None

    results = []

    def record(label, subset, filters):
        if len(subset) < min_n:
            return
        n, wins, wr, ev, pf = stats(subset, rr)
        if wr < target_wr:
            return
        oos_wr, oos_n = oos_stats(subset, split_yr, rr) if split_yr else (None, 0)
        # flag robust: OOS WR within 10pp of target (didn't fall apart)
        robust = (oos_wr is not None) and (oos_wr >= target_wr - 0.10)
        results.append({
            'model':  model_key,
            'label':  label,
            'n':      n,
            'wins':   wins,
            'wr':     wr,
            'ev':     ev,
            'pf':     pf,
            'oos_wr': oos_wr,
            'oos_n':  oos_n,
            'robust': robust,
            **filters,
        })

    # ── 1-D ───────────────────────────────────────────────────────────────────
    for direction, g in wl.groupby('direction'):
        record(f'{direction}', g, {'direction': direction})

    for hr, g in wl.groupby('hr'):
        record(f'{hr:02d}:00', g, {'hr': int(hr)})

    for dow, g in wl.groupby('dow'):
        record(DOW_NAMES.get(dow, '?'), g, {'dow': int(dow)})

    for sess, g in wl.groupby('session'):
        record(f'Session={sess}', g, {'session': sess})

    # ── 2-D ───────────────────────────────────────────────────────────────────
    for (hr, direction), g in wl.groupby(['hr', 'direction']):
        record(f'{hr:02d}:00 {direction}', g, {'hr': int(hr), 'direction': direction})

    for (dow, direction), g in wl.groupby(['dow', 'direction']):
        dn = DOW_NAMES.get(dow, '?')
        record(f'{dn} {direction}', g, {'dow': int(dow), 'direction': direction})

    for (hr, dow), g in wl.groupby(['hr', 'dow']):
        dn = DOW_NAMES.get(dow, '?')
        record(f'{hr:02d}:00 {dn}', g, {'hr': int(hr), 'dow': int(dow)})

    for (sess, direction), g in wl.groupby(['session', 'direction']):
        record(f'Session={sess} {direction}', g, {'session': sess, 'direction': direction})

    # sweep_pct bands
    for lo, hi in [(0.10, 0.30), (0.30, 0.60), (0.60, 1.00), (1.00, 1.50)]:
        sb = wl[(wl['sweep_pct'] >= lo) & (wl['sweep_pct'] < hi)]
        label_s = f'sweep [{lo:.0%},{hi:.0%})'
        record(label_s, sb, {'sweep_lo': lo, 'sweep_hi': hi})
        for direction, g in sb.groupby('direction'):
            record(f'{label_s} {direction}', g,
                   {'sweep_lo': lo, 'sweep_hi': hi, 'direction': direction})

    # ── 3-D ───────────────────────────────────────────────────────────────────
    for (hr, dow, direction), g in wl.groupby(['hr', 'dow', 'direction']):
        dn = DOW_NAMES.get(dow, '?')
        record(f'{hr:02d}:00 {dn} {direction}', g,
               {'hr': int(hr), 'dow': int(dow), 'direction': direction})

    for (sess, dow, direction), g in wl.groupby(['session', 'dow', 'direction']):
        dn = DOW_NAMES.get(dow, '?')
        record(f'Session={sess} {dn} {direction}', g,
               {'session': sess, 'dow': int(dow), 'direction': direction})

    for (hr, direction), g in wl.groupby(['hr', 'direction']):
        for lo, hi in [(0.10, 0.30), (0.30, 0.60), (0.60, 1.00), (1.00, 1.50)]:
            sb = g[(g['sweep_pct'] >= lo) & (g['sweep_pct'] < hi)]
            record(f'{hr:02d}:00 {direction} sweep[{lo:.0%},{hi:.0%})', sb,
                   {'hr': int(hr), 'direction': direction, 'sweep_lo': lo, 'sweep_hi': hi})

    results.sort(key=lambda x: (-x['wr'], -x['ev'], -x['n']))
    return results


# ── Formatting ─────────────────────────────────────────────────────────────────
def print_table(results, target_wr, top):
    W1, W2 = 10, 40
    hdr = (f"  {'Model':<{W1}}  {'Filter':<{W2}}  {'WR':>7}  {'EV':>7}  "
           f"{'N':>5}  {'OOS WR':>8}  {'OOS N':>6}  {'OK?':>4}")
    sep = '  ' + '─'*W1 + '  ' + '─'*W2 + '  ' + '─'*7 + '  ' + '─'*7 + \
          '  ' + '─'*5 + '  ' + '─'*8 + '  ' + '─'*6 + '  ' + '─'*4
    print(hdr)
    print(sep)
    shown = 0
    for r in results:
        if shown >= top:
            break
        oos_s   = f"{r['oos_wr']:.1%}" if r['oos_wr'] is not None else '   —   '
        oos_n_s = str(r['oos_n']) if r['oos_n'] else '  —  '
        ok_s    = '✓' if r['robust'] else ('?' if r['oos_wr'] is None else '✗')
        print(f"  {r['model']:<{W1}}  {r['label']:<{W2}}  {r['wr']:>6.1%}  "
              f"{r['ev']:>+7.3f}R  {r['n']:>5}  {oos_s:>8}  {oos_n_s:>6}  {ok_s:>4}")
        shown += 1


# ── Entry point ────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--models',     nargs='+', default=['4H_15M', '1H_5M', '1H_3M'],
                        choices=list(MODELS.keys()))
    parser.add_argument('--target-wr',  type=float, default=0.80,   dest='target_wr')
    parser.add_argument('--min-n',      type=int,   default=15,      dest='min_n')
    parser.add_argument('--top',        type=int,   default=40)
    parser.add_argument('--table',      default='nq_1m')
    args = parser.parse_args()

    print(f"\n{'═'*75}")
    print(f"  FILTER SEARCH  ·  target WR ≥ {args.target_wr:.0%}  ·  N ≥ {args.min_n}")
    print(f"  Models: {', '.join(args.models)}  ·  Table: {args.table}")
    print(f"{'═'*75}")
    print("  OOS = out-of-sample (last 40% of years).  ✓ = OOS WR ≥ (target − 10pp)")
    print(f"{'─'*75}")

    raw_trades = collect_raw_trades(args.models, table=args.table)

    all_results = []
    for mk, df_raw in raw_trades.items():
        df_clean = df_raw[df_raw['rejected_by'] == '']
        wl_n = int((df_clean['outcome'].isin(['WIN', 'LOSS'])).sum())
        print(f"\n  {mk}: {wl_n:,} resolved trades")
        results = search(df_raw, mk, args.target_wr, args.min_n)
        print(f"         → {len(results):,} combos ≥ {args.target_wr:.0%} WR, N ≥ {args.min_n}")
        robust = sum(1 for r in results if r['robust'])
        print(f"         → {robust} OOS-robust (WR ≥ {args.target_wr - 0.10:.0%} out-of-sample)")
        all_results.extend(results)

    all_results.sort(key=lambda x: (-x['wr'], -x['ev'], -x['n']))

    print(f"\n{'═'*75}")
    print(f"  TOP {min(args.top, len(all_results))} RESULTS  (all models combined)")
    print(f"{'═'*75}")
    print_table(all_results, args.target_wr, args.top)

    # Robust-only summary
    robust_results = [r for r in all_results if r['robust']]
    if robust_results:
        print(f"\n{'═'*75}")
        print(f"  OOS-ROBUST ONLY  ({len(robust_results)} combos)")
        print(f"{'═'*75}")
        print_table(robust_results, args.target_wr, min(args.top, len(robust_results)))
    else:
        print(f"\n  ⚠  No OOS-robust combos found at WR ≥ {args.target_wr:.0%}.")
        print(f"     Try --target-wr {args.target_wr - 0.05:.2f}")

    print(f"\n{'═'*75}")
    print("  NOTE: The more dimensions filtered, the smaller the N.")
    print("  A combo with N < 30 should be treated as exploratory, not tradeable.")
    print(f"{'═'*75}\n")


if __name__ == '__main__':
    main()
