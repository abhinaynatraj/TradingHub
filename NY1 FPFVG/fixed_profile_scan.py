#!/usr/bin/env python3
"""
fixed_profile_scan.py — Brute-force fixed % SL/TP profile scanner
===================================================================
Tests all 10,000 combinations of SL and TP (0.01%–1.00% in 0.01% steps)
across every filled NY1 F.P.FVG trade and finds the top 7 fixed % profiles
that never blow the account (min_equity > 0).

Uses numpy vectorisation: for each trade, a (100 × 100) R-matrix is computed
in one pass, then accumulated across all trades.

Usage:
    python3 fixed_profile_scan.py
    python3 fixed_profile_scan.py --table es_1m
"""

import argparse
import json
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

# ── Constants (must match ny1_backtest.py) ─────────────────────────────────────
DB_PATH        = Path(__file__).parent.parent / 'Fractal Sweep' / 'candle_science.duckdb'
OUT_JSON       = Path(__file__).parent / 'fixed_scan_results.json'

ACCOUNT_SIZE   = 4_500
RISK_PER_TRADE = 225
MIN_RISK_PTS   = 0.25
MIN_FVG_TICKS  = 0
TICK_SIZE      = 0.25

# Grid: 0.01 % → 1.00 % in 0.01 % steps (100 values each axis, 10 000 combos)
N   = 100
PCT = np.round(np.arange(1, N + 1) * 0.01, 2)  # [0.01, 0.02, …, 1.00] in %

# Minimum realistic SL — exclude ultra-tight stops that can't work in practice
MIN_SL_PCT = 0.03   # 0.03% minimum SL (≈3 bps; realistic for NQ at 9:30)


# ── DB helpers (identical to ny1_backtest.py) ──────────────────────────────────
def connect_db():
    if not DB_PATH.exists():
        sys.exit(f'[error] database not found: {DB_PATH}')
    return duckdb.connect(str(DB_PATH), read_only=True)


def load_bars(con, table: str) -> pd.DataFrame:
    df = con.execute(f"""
        SELECT
            CAST(timezone('America/New_York', timestamp) AS DATE)  AS trade_date,
            date_part('hour',   timezone('America/New_York', timestamp)) AS hr,
            date_part('minute', timezone('America/New_York', timestamp)) AS mn,
            date_part('dow',    timezone('America/New_York', timestamp)) AS dow,
            open, high, low, close
        FROM {table}
        WHERE date_part('hour', timezone('America/New_York', timestamp)) BETWEEN 9 AND 16
          AND date_part('dow',  timezone('America/New_York', timestamp)) BETWEEN 1 AND 5
        ORDER BY timestamp
    """).df()
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    for col in ('hr', 'mn', 'dow'):
        df[col] = df[col].astype(int)
    # Keep only 9:00–16:00 (drop 16:01+ if any)
    df = df[~((df['hr'] == 16) & (df['mn'] > 0))].reset_index(drop=True)
    return df


def build_day(day_df: pd.DataFrame) -> dict:
    tval = (day_df['hr'].values * 60 + day_df['mn'].values).astype(np.int32)
    return {
        'hr':   day_df['hr'].values.astype(np.int32),
        'mn':   day_df['mn'].values.astype(np.int32),
        'high': day_df['high'].values,
        'low':  day_df['low'].values,
        'open': day_df['open'].values,
        'close':day_df['close'].values,
        'tval': tval,
        'n':    len(day_df),
    }


def find_idx(arrs, hr, mn):
    tval = hr * 60 + mn
    idx  = int(np.searchsorted(arrs['tval'], tval, side='left'))
    return idx if idx < arrs['n'] and arrs['tval'][idx] == tval else -1


# ── FVG detection (identical to ny1_backtest.py) ───────────────────────────────
def detect_fvg(arrs) -> dict | None:
    n = arrs['n']
    for c2 in range(1, n - 1):
        hr, mn = int(arrs['hr'][c2]), int(arrs['mn'][c2])
        if hr != 9 or mn < 31:
            continue
        if hr > 9 or mn > 59:
            break
        c1, c3 = c2 - 1, c2 + 1
        c1h, c1l = arrs['high'][c1], arrs['low'][c1]
        c3h, c3l = arrs['high'][c3], arrs['low'][c3]
        c2o, c2c = arrs['open'][c2], arrs['close'][c2]
        # Bullish
        if c3l > c1h and c2c > c2o:
            return {'c3_idx': c3, 'entry': float(c3l),
                    'stop': float(min(c1l, arrs['low'][c2])), 'direction': 'LONG'}
        # Bearish
        if c3h < c1l and c2c < c2o:
            return {'c3_idx': c3, 'entry': float(c3h),
                    'stop': float(max(c1h, arrs['high'][c2])), 'direction': 'SHORT'}
    return None


def scan_fill(arrs, c3, fvg, eod) -> int | None:
    entry, d = fvg['entry'], fvg['direction']
    for j in range(c3 + 1, eod + 1):
        if d == 'LONG'  and arrs['low'][j]  <= entry: return j
        if d == 'SHORT' and arrs['high'][j] >= entry: return j
    return None


# ── Vectorised R-matrix for one trade ─────────────────────────────────────────
def r_matrix(arrs, fill_idx: int, fvg: dict, eod_idx: int) -> np.ndarray:
    """
    Returns (N, N) float array.  Axis-0 = SL index, Axis-1 = TP index.
    Value = combined_r for that combo: positive (win), -1.0 (loss), NaN (open/expired).

    For each bar in the scan window, compute:
      adv[b] = max adverse excursion this bar  (% of entry)
      fav[b] = max favourable excursion this bar (% of entry)

    For combo (sl_i, tp_j):
      first bar where adv >= sl_pct → stop hit
      first bar where fav >= tp_pct → tp hit
      TP wins same-bar conflicts.
      r = tp_pct/sl_pct (win) | -1.0 (loss) | NaN (neither by EOD)
    """
    nb = eod_idx - fill_idx  # number of scan bars (fill+1 … eod inclusive)
    if nb <= 0:
        return np.full((N, N), np.nan)

    highs = arrs['high'][fill_idx + 1 : eod_idx + 1]
    lows  = arrs['low'] [fill_idx + 1 : eod_idx + 1]
    entry = fvg['entry']

    if fvg['direction'] == 'LONG':
        adv = np.maximum(0.0, (entry - lows)  / entry * 100)  # (nb,)
        fav = np.maximum(0.0, (highs - entry) / entry * 100)  # (nb,)
    else:
        adv = np.maximum(0.0, (highs - entry) / entry * 100)
        fav = np.maximum(0.0, (entry - lows)  / entry * 100)

    # (nb, N) — True where bar b breaches sl_i / tp_j threshold
    adv_m = adv[:, None] >= PCT[None, :]   # (nb, N)  sl axis
    fav_m = fav[:, None] >= PCT[None, :]   # (nb, N)  tp axis

    # First bar index that breaches each threshold; nb = "never"
    first_adv = np.where(adv_m.any(0), np.argmax(adv_m, 0), nb)   # (N,) sl
    first_fav = np.where(fav_m.any(0), np.argmax(fav_m, 0), nb)   # (N,) tp

    fa2 = first_adv[:, None]   # (N, 1)  sl axis
    ff2 = first_fav[None, :]   # (1, N)  tp axis

    win      = ff2 <= fa2                        # TP hits first (or tie → TP wins)
    resolved = np.minimum(fa2, ff2) < nb         # at least one side hit

    # R:R ratio matrix — same value regardless of % or decimal scale
    r_win = PCT[None, :] / PCT[:, None]          # (N, N)  tp_pct / sl_pct

    return np.where(~resolved, np.nan, np.where(win, r_win, -1.0))


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--table', default='nq_1m')
    parser.add_argument('--top',   type=int, default=50)
    args = parser.parse_args()

    print(f'\nFixed % SL/TP Scanner  ·  {args.table}')
    print(f'Grid: {N}×{N} = {N*N:,} combinations  |  SL/TP: 0.01%–1.00% in 0.01% steps\n')

    con = connect_db()
    df  = load_bars(con, args.table)
    print(f'Bars loaded  : {len(df):,}')
    print(f'Trading days : {df["trade_date"].nunique():,}\n')

    equity        = np.full((N, N), float(ACCOUNT_SIZE))
    min_equity    = np.full((N, N), float(ACCOUNT_SIZE))
    peak_equity   = np.full((N, N), float(ACCOUNT_SIZE))
    max_dd_pct_m  = np.zeros((N, N))   # running max consecutive DD%
    wins_m        = np.zeros((N, N), dtype=np.int64)
    total_m       = np.zeros((N, N), dtype=np.int64)
    years_seen    = set()

    n_filled = 0
    n_days   = df['trade_date'].nunique()
    tick     = max(1, n_days // 20)

    for i, (date, day_df) in enumerate(df.groupby('trade_date')):
        if i % tick == 0:
            print(f'  {i:>5}/{n_days}  filled so far: {n_filled:,}', end='\r', flush=True)

        arrs = build_day(day_df)
        if arrs['n'] < 5:
            continue

        eod = find_idx(arrs, 16, 0)
        if eod == -1:
            eod = arrs['n'] - 1

        fvg = detect_fvg(arrs)
        if fvg is None:
            continue
        if abs(fvg['entry'] - fvg['stop']) < MIN_RISK_PTS:
            continue

        fill = scan_fill(arrs, fvg['c3_idx'], fvg, eod)
        if fill is None:
            continue

        n_filled += 1
        years_seen.add(date.year)
        rm = r_matrix(arrs, fill, fvg, eod)

        delta        = np.where(np.isnan(rm), 0.0, rm * RISK_PER_TRADE)
        equity      += delta
        peak_equity  = np.maximum(peak_equity, equity)
        min_equity   = np.minimum(min_equity,  equity)
        # True running max consecutive drawdown (not global peak vs global trough)
        cur_dd       = np.where(peak_equity > 0,
                                (peak_equity - equity) / peak_equity * 100, 0.0)
        max_dd_pct_m = np.maximum(max_dd_pct_m, cur_dd)

        wins_m  += (rm > 0).astype(np.int64)
        total_m += np.isfinite(rm).astype(np.int64)

    print(f'\n  Done — {n_filled:,} filled trades scanned\n')

    blown     = min_equity <= 0.0
    surviving = int((~blown).sum())
    print(f'Combos not blown : {surviving:,} / {N*N:,}')

    if surviving == 0:
        print('\nNo surviving combinations found.')
        return

    # ── Compute all 7 metrics analytically (vectorized) ──────────────────────
    # Binary outcomes: win = +rr R, loss = -1R (unresolved = 0, excluded from stats)
    num_years = max(len(years_seen), 1)
    n_bankroll = ACCOUNT_SIZE / RISK_PER_TRADE    # = 20
    MIN_TRADES = 30                               # minimum trades for a valid combo

    W  = wins_m.astype(float)
    L  = (total_m - wins_m).astype(float)
    NT = total_m.astype(float)
    rr_m = PCT[None, :] / PCT[:, None]           # (N, N) R:R per combo

    sl_ok = (PCT >= MIN_SL_PCT)[:, None]   # (N,1) — True for realistic SL rows
    valid = (~blown) & (total_m >= MIN_TRADES) & sl_ok

    with np.errstate(divide='ignore', invalid='ignore'):
        wr_m   = np.where(NT > 0, W / NT, 0.0)
        # EV in R units
        ev_r_m = np.where(NT > 0, (W * rr_m - L) / NT, 0.0)
        # Analytical std for binary outcomes
        E_r2   = np.where(NT > 0, (W * rr_m**2 + L) / NT, 0.0)
        var_r  = np.maximum(E_r2 - ev_r_m**2, 0.0)
        std_r  = np.sqrt(var_r)
        # EV in dollars
        ev_dol = ev_r_m * RISK_PER_TRADE
        # PF (gross wins / gross losses)
        pf_m   = np.where(L > 0, W * rr_m / L, 999.0)
        # CE = EV_R × PF
        ce_m   = ev_r_m * pf_m
        # SQN = EV_R / std_r * sqrt(N)
        sqn_m  = np.where(std_r > 0, ev_r_m / std_r * np.sqrt(NT), 0.0)
        # Sharpe (annualised): sqrt(trades_per_year)
        tpy    = n_filled / num_years
        sharpe_m = np.where(std_r > 0, ev_r_m / std_r * np.sqrt(tpy), 0.0)
        # max_dd_pct_m is already computed correctly as running DD in the scan loop
        # RoR = ((1-CE)/(1+CE))^N_bankroll * 100
        ror_m  = np.where(
            ce_m <= 0, 100.0,
            np.minimum(100.0,
                np.where(ce_m < 1.0,
                    ((1 - ce_m) / (1 + ce_m))**n_bankroll * 100,
                    0.0))
        )

    # ── Weighted composite score ──────────────────────────────────────────────
    # Weights: Sharpe 25%, PF 20%, EV 15%, SQN 15%, MaxDD 10%, RoR 10%, CE 5%
    # All normalized to [0,1] over the valid population
    def norm_arr(arr, higher_is_better=True):
        vals = arr[valid]
        if vals.size == 0:
            return np.zeros_like(arr)
        lo, hi = float(vals.min()), float(vals.max())
        if hi == lo:
            return np.full_like(arr, 0.5)
        n = (arr - lo) / (hi - lo)
        return n if higher_is_better else 1.0 - n

    score_m = (
        0.25 * norm_arr(sharpe_m,   True)  +
        0.20 * norm_arr(pf_m,       True)  +
        0.15 * norm_arr(ev_dol,     True)  +
        0.15 * norm_arr(sqn_m,      True)  +
        0.10 * norm_arr(max_dd_pct_m, False) +
        0.10 * norm_arr(ror_m,      False) +
        0.05 * norm_arr(ce_m,       True)
    )

    composite = np.where(valid, score_m, -np.inf)
    order     = np.argsort(composite.flatten())[::-1]

    top_n = args.top
    top_results = []
    for idx in order:
        if composite.flat[idx] == -np.inf:
            break
        sl_i = idx // N
        tp_i = idx  % N
        top_results.append({
            'rank':          len(top_results) + 1,
            'sl_pct':        round(PCT[sl_i], 2),
            'tp_pct':        round(PCT[tp_i], 2),
            'rr':            round(PCT[tp_i] / PCT[sl_i], 2),
            'win_rate':      round(float(wr_m.flat[idx]), 4),
            'wins':          int(wins_m.flat[idx]),
            'losses':        int(total_m.flat[idx]) - int(wins_m.flat[idx]),
            'trades':        int(total_m.flat[idx]),
            'ev_r':          round(float(ev_r_m.flat[idx]), 6),
            'ev_dollar':     round(float(ev_dol.flat[idx]), 4),
            'pf':            round(float(pf_m.flat[idx]), 4),
            'ce':            round(float(ce_m.flat[idx]), 6),
            'sqn':           round(float(sqn_m.flat[idx]), 4),
            'sharpe':        round(float(sharpe_m.flat[idx]), 4),
            'max_dd_pct':    round(float(max_dd_pct_m.flat[idx]), 2),
            'ror_pct':       round(float(ror_m.flat[idx]), 4),
            'min_equity':    round(float(min_equity.flat[idx]), 2),
            'final_equity':  round(float(equity.flat[idx]), 2),
            'composite':     round(float(composite.flat[idx]), 6),
        })
        if len(top_results) == top_n:
            break

    # ── Print results ──────────────────────────────────────────────────────────
    bar = '─' * 104
    print(f'\n{bar}')
    print(f'  TOP {top_n} FIXED % PROFILES  (not blown · SL ≥ {MIN_SL_PCT}% · ranked by weighted composite score)')
    print(f'  Weights: Sharpe 25% · PF 20% · EV 15% · SQN 15% · MaxDD 10% · RoR 10% · CE 5%')
    print(bar)
    print(f'  {"#":<3} {"SL%":>5} {"TP%":>5} {"R:R":>5} {"WR":>7} '
          f'{"Sharpe":>8} {"PF":>6} {"SQN":>7} {"CE":>8} {"MaxDD%":>8} {"RoR%":>7} {"Score":>8}')
    print(f'  {"-"*101}')
    for r in top_results:
        print(f'  {r["rank"]:<3} {r["sl_pct"]:>4.2f}% {r["tp_pct"]:>4.2f}% '
              f'{r["rr"]:>5.2f} {r["win_rate"]:>6.1%} '
              f'{r["sharpe"]:>8.3f} {r["pf"]:>6.3f} {r["sqn"]:>7.3f} '
              f'{r["ce"]:>8.5f} {r["max_dd_pct"]:>7.1f}% {r["ror_pct"]:>6.2f}% '
              f'{r["composite"]:>8.4f}')
    print(bar)

    # ── Extract scores for the 10 FPFVG-validated SL/TP combos ──────────────
    # These are the unique SL/TP pairs tested across all direction classifications
    # in the FPFVG analysis — run on NY1 data without classification filtering.
    FPFVG_COMBOS = [
        (0.03, 0.06), (0.04, 0.06), (0.04, 0.07), (0.04, 0.08),
        (0.05, 0.06), (0.05, 0.07), (0.05, 0.08), (0.05, 0.09),
        (0.10, 0.05), (0.10, 0.06),
    ]

    def _combo_stats(sl_p, tp_p):
        # Find grid indices
        sl_i = int(round(sl_p / 0.01)) - 1
        tp_i = int(round(tp_p / 0.01)) - 1
        if sl_i < 0 or sl_i >= N or tp_i < 0 or tp_i >= N:
            return None
        idx = sl_i * N + tp_i
        return {
            'sl_pct':       round(sl_p, 2),
            'tp_pct':       round(tp_p, 2),
            'rr':           round(tp_p / sl_p, 4),
            'win_rate':     round(float(wr_m.flat[idx]),        4),
            'wins':         int(wins_m.flat[idx]),
            'losses':       int(total_m.flat[idx]) - int(wins_m.flat[idx]),
            'trades':       int(total_m.flat[idx]),
            'ev_r':         round(float(ev_r_m.flat[idx]),      6),
            'ev_dollar':    round(float(ev_dol.flat[idx]),      4),
            'pf':           round(float(pf_m.flat[idx]),        4),
            'ce':           round(float(ce_m.flat[idx]),        6),
            'sqn':          round(float(sqn_m.flat[idx]),       4),
            'sharpe':       round(float(sharpe_m.flat[idx]),    4),
            'max_dd_pct':   round(float(max_dd_pct_m.flat[idx]),2),
            'ror_pct':      round(float(ror_m.flat[idx]),       4),
            'min_equity':   round(float(min_equity.flat[idx]),  2),
            'final_equity': round(float(equity.flat[idx]),      2),
            'blown':        bool(blown.flat[idx]),
            'composite':    round(float(composite.flat[idx]) if composite.flat[idx] > -np.inf else 0.0, 6),
        }

    fpfvg_on_ny1 = []
    for sl_p, tp_p in FPFVG_COMBOS:
        s = _combo_stats(sl_p, tp_p)
        if s:
            fpfvg_on_ny1.append(s)

    fpfvg_on_ny1.sort(key=lambda x: x['composite'], reverse=True)
    for i, r in enumerate(fpfvg_on_ny1, 1):
        r['rank'] = i

    print(f'\n  FPFVG-VALIDATED COMBOS ON NY1 DATA (ranked by composite score)')
    print(f'  {"#":<3} {"SL%":>5} {"TP%":>5} {"R:R":>5} {"WR":>7} {"Sharpe":>8} {"PF":>6} {"SQN":>7} {"MaxDD%":>8} {"Blown":>6} {"Score":>8}')
    print(f'  {"-"*85}')
    for r in fpfvg_on_ny1:
        print(f'  {r["rank"]:<3} {r["sl_pct"]:>4.2f}% {r["tp_pct"]:>4.2f}% '
              f'{r["rr"]:>5.2f} {r["win_rate"]:>6.1%} {r["sharpe"]:>8.3f} '
              f'{r["pf"]:>6.3f} {r["sqn"]:>7.3f} {r["max_dd_pct"]:>7.1f}% '
              f'{"YES" if r["blown"] else "no":>6}  {r["composite"]:>8.4f}')

    out = {
        'table':             args.table,
        'grid':              f'{N}×{N} = {N*N} combinations',
        'sl_range':          '0.01%–1.00% in 0.01% steps',
        'tp_range':          '0.01%–1.00% in 0.01% steps',
        'account_size':      ACCOUNT_SIZE,
        'risk_per_trade':    RISK_PER_TRADE,
        'filled_trades':     n_filled,
        'combos_not_blown':  surviving,
        'scoring':           'Sharpe 25% + PF 20% + EV 15% + SQN 15% + MaxDD 10% + RoR 10% + CE 5%',
        'fpfvg_combos_on_ny1': fpfvg_on_ny1,
        f'top{top_n}':       top_results,
    }
    with open(OUT_JSON, 'w') as f:
        json.dump(out, f, indent=2)
    print(f'\n  Results saved → {OUT_JSON}\n')


if __name__ == '__main__':
    main()
