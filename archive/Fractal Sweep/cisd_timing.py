#!/usr/bin/env python3
"""
cisd_timing.py — Does CISD timing within Q1 vs after Q1 affect win rate?
=========================================================================
For each valid trade, classifies whether CISD fired inside Q1 or after Q1,
then compares win rates / EV between the two groups.

Usage:
    python3 cisd_timing.py
    python3 cisd_timing.py --models 1H_5M 1H_3M
    python3 cisd_timing.py --table es_1m
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from model_stats import (
    connect, load_1m, resample, df_to_arrays, df_1m_to_arrays,
    find_cisd, MODELS, DB_PATH, RR,
    SWEEP_MIN_PCT, SWEEP_MAX_PCT, MIN_RISK_PTS, CISD_FAST_BARS,
    resolve_outcomes_vectorised,
)

NS_PER_MIN = np.int64(60_000_000_000)


def detect_with_timing(m1_arrs, s_arrs, c_arrs, model_key, model_cfg):
    """Like detect_model but captures cisd_ts_ns and q1_end_ns per trade."""
    q1_min    = model_cfg['q1_min']
    min_range = model_cfg['min_range']
    sess_hrs  = model_cfg['session_hrs']

    q1_ns     = np.int64(q1_min) * NS_PER_MIN
    gap_limit = np.int64(model_cfg['sweep_tf_min']) * NS_PER_MIN * 3

    s_ts   = s_arrs['ts_ns'];  s_high = s_arrs['high'];  s_low = s_arrs['low']
    s_n    = len(s_ts)

    m1_ts    = m1_arrs['ts_ns'];  m1_high  = m1_arrs['high']
    m1_low   = m1_arrs['low'];    m1_close = m1_arrs['close']
    m1_open  = m1_arrs['open'];   m1_hr    = m1_arrs['hr']
    m1_mn    = m1_arrs['mn']

    rows_pre = []
    pending  = []

    for i in range(1, s_n):
        curr_ts_ns  = s_ts[i]
        q1_start_ns = curr_ts_ns
        q1_end_ns   = curr_ts_ns + q1_ns - NS_PER_MIN   # last valid Q1 bar ts

        if curr_ts_ns - s_ts[i - 1] > gap_limit:
            continue

        refs = {
            'SHORT': (s_high[i - 1], s_high[i - 1] - s_low[i - 1]),
            'LONG':  (s_low[i - 1],  s_high[i - 1] - s_low[i - 1]),
        }

        q1_s = int(np.searchsorted(m1_ts, q1_start_ns, side='left'))
        q1_e = int(np.searchsorted(m1_ts, q1_end_ns,   side='right'))
        if q1_e - q1_s < 3:
            continue

        q1_h  = m1_high[q1_s:q1_e];  q1_l  = m1_low[q1_s:q1_e]
        q1_c  = m1_close[q1_s:q1_e]; q1_ts = m1_ts[q1_s:q1_e]
        q1_hr = m1_hr[q1_s:q1_e];    q1_mn = m1_mn[q1_s:q1_e]

        if sess_hrs:
            hrf = q1_hr + q1_mn / 60.0
            if not np.any((hrf >= sess_hrs[0]) & (hrf < sess_hrs[1])):
                continue

        for direction in ('SHORT', 'LONG'):
            ref_level, ref_range = refs[direction]

            swept_mask = q1_h > ref_level if direction == 'SHORT' else q1_l < ref_level
            if not swept_mask.any():
                continue

            pos = int(swept_mask.argmax())
            sweep_extreme = float(q1_h[swept_mask].max()) if direction == 'SHORT' \
                else float(q1_l[swept_mask].min())
            sweep_ext = abs(sweep_extreme - ref_level)

            if ref_range < min_range:
                continue
            if ref_range > 0 and not (SWEEP_MIN_PCT <= sweep_ext / ref_range <= SWEEP_MAX_PCT):
                continue

            post_s = pos + 1
            if post_s >= len(q1_ts):
                continue

            ret_mask = (q1_l[post_s:] <= ref_level) if direction == 'SHORT' \
                else (q1_h[post_s:] >= ref_level)
            if not ret_mask.any():
                continue

            ret_rel   = int(ret_mask.argmax())
            ret_idx   = post_s + ret_rel
            ret_close = float(q1_c[ret_idx])
            ret_ts_ns = int(q1_ts[ret_idx])

            if direction == 'SHORT' and ret_close > ref_level:
                continue
            if direction == 'LONG'  and ret_close < ref_level:
                continue

            cisd_ts_ns, cisd_level = find_cisd(
                c_arrs, ret_ts_ns, direction, CISD_FAST_BARS, 'CISD'
            )
            if cisd_ts_ns is None:
                continue

            # ── Key classification ─────────────────────────────────────────────
            cisd_in_q1 = cisd_ts_ns <= q1_end_ns

            entry_start = int(np.searchsorted(m1_ts, cisd_ts_ns, side='right'))
            if entry_start >= len(m1_ts):
                continue

            entry_ts_ns = int(m1_ts[entry_start])
            entry_price = float(m1_open[entry_start])
            stop_price  = sweep_extreme

            if direction == 'SHORT' and entry_price >= stop_price: continue
            if direction == 'LONG'  and entry_price <= stop_price: continue

            if direction == 'LONG':
                ref_high     = ref_level + ref_range
                manip_range  = max(ref_high - sweep_extreme, MIN_RISK_PTS)
                target_price = sweep_extreme + 2.0 * manip_range
            else:
                ref_low      = ref_level - ref_range
                manip_range  = max(sweep_extreme - ref_low, MIN_RISK_PTS)
                target_price = sweep_extreme - 2.0 * manip_range

            if direction == 'LONG'  and target_price <= entry_price: continue
            if direction == 'SHORT' and target_price >= entry_price: continue

            rows_pre.append(dict(
                direction  = direction,
                cisd_zone  = 'IN_Q1' if cisd_in_q1 else 'AFTER_Q1',
                outcome    = '',
            ))
            pending.append(dict(
                idx          = len(rows_pre) - 1,
                entry_ts_ns  = entry_ts_ns,
                entry_price  = entry_price,
                stop_price   = stop_price,
                target_price = target_price,
                direction    = direction,
            ))

    if not pending:
        return pd.DataFrame()

    resolved = resolve_outcomes_vectorised(m1_arrs, pending)
    for p, res in zip(pending, resolved):
        rows_pre[p['idx']]['outcome'] = res[0]  # (outcome, r_val, mae_pct, mfe_pct)

    return pd.DataFrame(rows_pre)


def stats(g):
    wl = g[g['outcome'].isin(['WIN', 'LOSS'])]
    if len(wl) == 0:
        return None
    n    = len(wl)
    wins = int((wl['outcome'] == 'WIN').sum())
    wr   = wins / n
    ev   = round(wr * RR - (1 - wr), 3)
    pf   = round((wins * RR) / max(n - wins, 1), 3)
    return dict(n=n, wins=wins, wr=wr, ev=ev, pf=pf)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--models', nargs='+',
                        default=list(MODELS.keys()),
                        choices=list(MODELS.keys()))
    parser.add_argument('--table', default='nq_1m')
    args = parser.parse_args()

    con = connect(DB_PATH)
    df_1m_full, df_1m_rth = load_1m(con, args.table)

    needed_sweep = {MODELS[mk]['sweep_tf_min'] for mk in args.models}
    needed_cisd  = {MODELS[mk]['cisd_tf_min']  for mk in args.models}

    sweep_arrs = {
        tf: df_to_arrays(resample(df_1m_full if tf >= 1440 else df_1m_rth, tf,
                                  '1D' if tf >= 1440 else f'{tf}min'))
        for tf in sorted(needed_sweep)
    }
    cisd_arrs = {
        tf: df_to_arrays(resample(df_1m_rth, tf, f'{tf}min'))
        for tf in sorted(needed_cisd)
    }
    m1_full = df_1m_to_arrays(df_1m_full)
    m1_rth  = df_1m_to_arrays(df_1m_rth)

    W = 12
    hdr = (f"  {'Model':<10}  {'Direction':<8}  {'Zone':<10}  "
           f"{'N':>5}  {'WR':>7}  {'EV':>7}  {'PF':>6}")
    sep = '  ' + '─'*10 + '  ' + '─'*8 + '  ' + '─'*10 + '  ' + \
          '─'*5 + '  ' + '─'*7 + '  ' + '─'*7 + '  ' + '─'*6

    print(f"\n{'═'*70}")
    print(f"  CISD TIMING: In Q1 vs After Q1")
    print(f"{'═'*70}")

    for mk in args.models:
        cfg   = MODELS[mk]
        s_arr = sweep_arrs[cfg['sweep_tf_min']]
        c_arr = cisd_arrs[cfg['cisd_tf_min']]
        m1    = m1_full if cfg['sweep_tf_min'] >= 1440 else m1_rth

        print(f"\n  Running {mk} (Q1 = {cfg['q1_min']}min, CISD TF = {cfg['cisd_tf_min']}min) ...")
        df = detect_with_timing(m1, s_arr, c_arr, mk, cfg)

        if df.empty:
            print(f"  {mk}: no trades")
            continue

        print(f"\n{hdr}")
        print(sep)

        for direction in ('LONG', 'SHORT'):
            sub = df[df['direction'] == direction]
            for zone in ('IN_Q1', 'AFTER_Q1'):
                g = sub[sub['cisd_zone'] == zone]
                s = stats(g)
                if s is None:
                    continue
                print(f"  {mk:<10}  {direction:<8}  {zone:<10}  "
                      f"{s['n']:>5}  {s['wr']:>6.1%}  {s['ev']:>+7.3f}  {s['pf']:>6.2f}")

        # Combined (both directions)
        print(sep)
        for zone in ('IN_Q1', 'AFTER_Q1'):
            g = df[df['cisd_zone'] == zone]
            s = stats(g)
            if s is None:
                continue
            print(f"  {mk:<10}  {'COMBINED':<8}  {zone:<10}  "
                  f"{s['n']:>5}  {s['wr']:>6.1%}  {s['ev']:>+7.3f}  {s['pf']:>6.2f}")

    print(f"\n{'═'*70}")
    print(f"  Q1 duration per model: 4H_15M=60min · 1H_5M=15min · 1H_3M=15min")
    print(f"  IN_Q1  = CISD fires before Q1 window ends")
    print(f"  AFTER_Q1 = CISD fires after Q1 window, later in the same hour")
    print(f"{'═'*70}\n")


if __name__ == '__main__':
    main()
