#!/usr/bin/env python3
"""
ny1_backtest.py — NY1 F.P.FVG Backtest
========================================
Backtests the First Presented Fair Value Gap model on 1-minute NQ futures.

Rules:
  - Scan 9:31–9:59 ET for the first 3-candle FVG (C1=oldest, C2=gap, C3=newest)
  - 9:30 FVG is excluded; first valid FVG only (1 shot 1 bullet)
  - Direction: C2 bullish → LONG, C2 bearish → SHORT
  - Entry: limit at FVG zone boundary on retrace (C3.low for LONG, C3.high for SHORT)
  - Stop: C1.low (LONG) or C1.high (SHORT)
  - TP1 (POTQ): +0.10% from entry (80% of position)
  - Runner: 20% exits at 16:00 close or stop

Usage:
    python3 ny1_backtest.py
    python3 ny1_backtest.py --table es_1m
    python3 ny1_backtest.py --no-json
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

# ── Constants ─────────────────────────────────────────────────────────────────
DB_PATH  = Path(__file__).parent.parent / 'CandleScience' / 'candle_science.duckdb'
OUT_JSON = Path(__file__).parent / 'ny1_results.json'

TP1_BPS       = 0.001   # 10 basis points = 0.10%
MIN_RISK_PTS  = 0.25    # guard against zero-risk setups
MIN_FVG_TICKS = 0       # minimum FVG gap size in ticks (0 = no filter)
TICK_SIZE     = 0.25    # NQ futures tick size in points
ACCOUNT_SIZE  = 4500    # account size for risk metrics ($)
RISK_PER_TRADE = 225    # risk per trade ($)
DOW_NAMES    = {1: 'Mon', 2: 'Tue', 3: 'Wed', 4: 'Thu', 5: 'Fri'}  # DuckDB: 0=Sun
MONTH_NAMES  = {1:'Jan',2:'Feb',3:'Mar',4:'Apr',5:'May',6:'Jun',
                7:'Jul',8:'Aug',9:'Sep',10:'Oct',11:'Nov',12:'Dec'}


# ── Database ──────────────────────────────────────────────────────────────────
def connect_db():
    if not DB_PATH.exists():
        sys.exit(f'[error] database not found: {DB_PATH}')
    return duckdb.connect(str(DB_PATH), read_only=True)


def load_bars(con, table: str) -> pd.DataFrame:
    """Load all RTH 1-min bars (9:00–16:00 ET) with date/time columns."""
    df = con.execute(f"""
        SELECT
            CAST(timezone('America/New_York', timestamp) AS DATE)  AS trade_date,
            timezone('America/New_York', timestamp)                AS ts_et,
            date_part('hour',   timezone('America/New_York', timestamp)) AS hr,
            date_part('minute', timezone('America/New_York', timestamp)) AS mn,
            date_part('dow',    timezone('America/New_York', timestamp)) AS dow,
            date_part('year',   timezone('America/New_York', timestamp)) AS yr,
            date_part('month',  timezone('America/New_York', timestamp)) AS mo,
            open, high, low, close
        FROM {table}
        WHERE date_part('hour', timezone('America/New_York', timestamp))
              BETWEEN 9 AND 16
          AND date_part('dow', timezone('America/New_York', timestamp))
              BETWEEN 1 AND 5
        ORDER BY timestamp
    """).df()

    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df['ts_et']      = pd.to_datetime(df['ts_et'], utc=True).dt.tz_convert('America/New_York')
    for col in ('hr', 'mn', 'dow', 'yr', 'mo'):
        df[col] = df[col].astype(int)

    # Exclude the 16:xx bars except exactly 16:00 (used only for runner exit)
    df = df[~((df['hr'] == 16) & (df['mn'] > 0))].reset_index(drop=True)
    return df


# ── Per-day array builder ──────────────────────────────────────────────────────
def build_day_arrays(day_df: pd.DataFrame) -> dict:
    """Convert a single day's DataFrame to numpy arrays for fast scanning."""
    return {
        'ts_et': day_df['ts_et'].values,
        'hr':    day_df['hr'].values.astype(np.int32),
        'mn':    day_df['mn'].values.astype(np.int32),
        'open':  day_df['open'].values,
        'high':  day_df['high'].values,
        'low':   day_df['low'].values,
        'close': day_df['close'].values,
        'tval':  (day_df['hr'].values * 60 + day_df['mn'].values).astype(np.int32),
        'n':     len(day_df),
    }


def find_idx(arrs: dict, hr: int, mn: int) -> int:
    """Return index of bar at hr:mn, or -1 if not found."""
    tval = hr * 60 + mn
    idx  = int(np.searchsorted(arrs['tval'], tval, side='left'))
    if idx < arrs['n'] and arrs['tval'][idx] == tval:
        return idx
    return -1


# ── FVG Detection ─────────────────────────────────────────────────────────────
def detect_fvg(arrs: dict) -> dict | None:
    """
    Scan 9:31–9:59 for the first valid FVG.
    C1 = bar before C2, C3 = bar after C2. C2 must be 9:31–9:59.

    Bullish FVG: C3.low > C1.high  →  gap = [C1.high, C3.low]
    Bearish FVG: C3.high < C1.low  →  gap = [C3.high, C1.low]
    Direction from C2 body: bullish C2 → LONG, bearish C2 → SHORT.
    """
    n = arrs['n']
    for c2_idx in range(1, n - 1):
        hr = int(arrs['hr'][c2_idx])
        mn = int(arrs['mn'][c2_idx])

        # C2 must be strictly 9:31–9:59
        if hr != 9 or mn < 31 or mn > 59:
            if hr > 9 or (hr == 9 and mn > 59):
                break   # past the window, stop scanning
            continue

        c1_idx = c2_idx - 1
        c3_idx = c2_idx + 1

        c1_h = arrs['high'][c1_idx];  c1_l = arrs['low'][c1_idx]
        c3_h = arrs['high'][c3_idx];  c3_l = arrs['low'][c3_idx]
        c2_o = arrs['open'][c2_idx];  c2_c = arrs['close'][c2_idx]

        # Bullish FVG: gap exists upward, C2 is bullish
        if c3_l > c1_h and c2_c > c2_o:
            if MIN_FVG_TICKS > 0 and (c3_l - c1_h) < MIN_FVG_TICKS * TICK_SIZE:
                continue
            c2_l = arrs['low'][c2_idx]
            return {
                'c1_idx': c1_idx, 'c2_idx': c2_idx, 'c3_idx': c3_idx,
                'fvg_top': float(c3_l),
                'fvg_bot': float(c1_h),
                'entry':   float(c3_l),             # limit buy at top of gap
                'stop':    float(min(c1_l, c2_l)),  # stop below lowest of C1/C2
                'direction': 'LONG',
            }

        # Bearish FVG: gap exists downward, C2 is bearish
        if c3_h < c1_l and c2_c < c2_o:
            if MIN_FVG_TICKS > 0 and (c1_l - c3_h) < MIN_FVG_TICKS * TICK_SIZE:
                continue
            c2_h = arrs['high'][c2_idx]
            return {
                'c1_idx': c1_idx, 'c2_idx': c2_idx, 'c3_idx': c3_idx,
                'fvg_top': float(c1_l),
                'fvg_bot': float(c3_h),
                'entry':   float(c3_h),             # limit sell at bottom of gap
                'stop':    float(max(c1_h, c2_h)),  # stop above highest of C1/C2
                'direction': 'SHORT',
            }

    return None


# ── Entry fill scanner ────────────────────────────────────────────────────────
def scan_fill(arrs: dict, c3_idx: int, fvg: dict, eod_idx: int) -> dict | None:
    """
    Scan from bar after C3 through EOD for limit fill.
    LONG fill: bar.low <= entry  (price retraces into the gap)
    SHORT fill: bar.high >= entry
    Fill price is always the limit price (fvg['entry']).
    """
    entry     = fvg['entry']
    direction = fvg['direction']

    for j in range(c3_idx + 1, eod_idx + 1):
        if direction == 'LONG':
            if arrs['low'][j] <= entry:
                return {
                    'fill_idx': j,
                    'fill_ts':  arrs['ts_et'][j],
                    'fill_hr':  int(arrs['hr'][j]),
                    'fill_mn':  int(arrs['mn'][j]),
                }
        else:  # SHORT
            if arrs['high'][j] >= entry:
                return {
                    'fill_idx': j,
                    'fill_ts':  arrs['ts_et'][j],
                    'fill_hr':  int(arrs['hr'][j]),
                    'fill_mn':  int(arrs['mn'][j]),
                }
    return None


# ── Outcome resolution ────────────────────────────────────────────────────────
def resolve_outcome(arrs: dict, fill_idx: int, fvg: dict,
                    tp1: float, eod_idx: int) -> dict:
    """
    Scan from bar after fill for TP1 or stop.
    TP1 wins on same-bar conflict. After TP1, scan runner until stop or EOD.
    """
    entry     = fvg['entry']
    stop      = fvg['stop']
    direction = fvg['direction']
    risk_pts  = abs(entry - stop)

    outcome_main = 'OPEN'
    tp1_idx      = None
    stop_idx     = None

    # ── Step 1: scan for TP1 or stop ──────────────────────────────────────────
    for j in range(fill_idx + 1, eod_idx + 1):
        h = arrs['high'][j]
        l = arrs['low'][j]

        if direction == 'LONG':
            hit_tp1  = h >= tp1
            hit_stop = l <= stop
        else:
            hit_tp1  = l <= tp1
            hit_stop = h >= stop

        if hit_tp1 and hit_stop:
            # same bar — TP1 wins
            outcome_main = 'WIN'
            tp1_idx = j
            break
        if hit_tp1:
            outcome_main = 'WIN'
            tp1_idx = j
            break
        if hit_stop:
            outcome_main = 'LOSS'
            stop_idx = j
            break

    # ── Step 2: runner resolution (only if TP1 was hit) ───────────────────────
    runner_exit_price  = None
    runner_outcome     = None
    mfe2_pct           = 0.0
    mfe3_pct           = 0.0

    if outcome_main == 'WIN':
        runner_exit_idx   = eod_idx
        runner_exit_price = float(arrs['close'][eod_idx])
        runner_outcome    = 'WIN'

        for j in range(tp1_idx + 1, eod_idx + 1):
            if direction == 'LONG'  and arrs['low'][j]  <= stop:
                runner_exit_idx   = j
                runner_exit_price = stop
                runner_outcome    = 'LOSS'
                break
            if direction == 'SHORT' and arrs['high'][j] >= stop:
                runner_exit_idx   = j
                runner_exit_price = stop
                runner_outcome    = 'LOSS'
                break

        # MFE2: max favorable from fill to runner exit (stop or EOD)
        mfe2_pts = 0.0
        for j in range(fill_idx, runner_exit_idx + 1):
            fav = (float(arrs['high'][j]) - entry) if direction == 'LONG' \
                  else (entry - float(arrs['low'][j]))
            if fav > mfe2_pts:
                mfe2_pts = fav
        mfe2_pct = round(mfe2_pts / entry * 100, 4) if entry > 0 else 0.0

        # MFE3: EOD close vs entry (%), only if:
        # 1. Runner was NOT stopped out (exits at EOD, not the stop)
        # 2. MFE3 > MFE2 (EOD close beats the runner's peak)
        if runner_outcome == 'WIN':
            eod_close = float(arrs['close'][eod_idx])
            mfe3_raw  = (eod_close - entry) / entry * 100 if direction == 'LONG' \
                        else (entry - eod_close) / entry * 100
            mfe3_pct  = round(mfe3_raw, 4) if mfe3_raw > mfe2_pct else 0.0
        else:
            mfe3_pct  = 0.0

    # ── Step 3: R calculation ─────────────────────────────────────────────────
    if risk_pts <= 0:
        combined_r = None
    elif outcome_main == 'WIN':
        tp1_move   = abs(tp1 - entry)
        tp1_r      = tp1_move / risk_pts
        main_r     = 0.8 * tp1_r

        if direction == 'LONG':
            run_move = runner_exit_price - entry
        else:
            run_move = entry - runner_exit_price
        runner_r  = run_move / risk_pts
        combined_r = round(main_r + 0.2 * runner_r, 4)
    elif outcome_main == 'LOSS':
        combined_r = -1.0
    else:
        combined_r = None

    return {
        'outcome_main':       outcome_main,
        'runner_exit_price':  runner_exit_price,
        'runner_outcome':     runner_outcome,
        'combined_r':         combined_r,
        'mfe2_pct':           mfe2_pct,
        'mfe3_pct':           mfe3_pct,
    }


# ── Stats helpers ─────────────────────────────────────────────────────────────
def _agg(trades: list[dict]) -> dict:
    wl   = [t for t in trades if t['outcome_main'] in ('WIN', 'LOSS')]
    if not wl:
        return {'n': 0, 'wins': 0, 'tp1_wr': None,
                'avg_mae_pct': None, 'avg_mfe1_pct': None, 'avg_mfe2_pct': None, 'avg_r': None}
    n    = len(wl)
    wins = sum(1 for t in wl if t['outcome_main'] == 'WIN')
    wr   = wins / n

    mae_vals  = [t['mae_pct']  for t in wl if t.get('mae_pct')  is not None]
    mfe1_vals = [t.get('mfe1_pct', 0.0) for t in wl]
    mfe2_vals = [t.get('mfe2_pct', 0.0) for t in wl]
    avg_mae   = round(float(np.mean(mae_vals)),  4) if mae_vals  else None
    avg_mfe1  = round(float(np.mean(mfe1_vals)), 4) if mfe1_vals else None
    avg_mfe2  = round(float(np.mean(mfe2_vals)), 4) if mfe2_vals else None

    rs    = [t['combined_r'] for t in wl if t['combined_r'] is not None]
    avg_r = round(float(np.mean(rs)), 4) if rs else None

    return {'n': n, 'wins': wins, 'tp1_wr': round(wr, 4),
            'avg_mae_pct': avg_mae, 'avg_mfe1_pct': avg_mfe1,
            'avg_mfe2_pct': avg_mfe2, 'avg_r': avg_r}


def build_stats(trades, meta_extra: dict) -> dict:
    overall = _agg(trades)

    by_dow = {}
    for d in range(1, 6):
        dn = DOW_NAMES[d]
        by_dow[dn] = _agg([t for t in trades if t['dow'] == d])

    by_hour = {}
    for h in range(9, 16):
        by_hour[str(h)] = _agg([t for t in trades if t['fill_hr'] == h])

    by_year = {}
    for yr in sorted({t['yr'] for t in trades}):
        by_year[str(yr)] = _agg([t for t in trades if t['yr'] == yr])

    by_month = {}
    for mo in range(1, 13):
        mn = MONTH_NAMES[mo]
        by_month[mn] = _agg([t for t in trades if t['mo'] == mo])

    by_direction = {
        'LONG':  _agg([t for t in trades if t['direction'] == 'LONG']),
        'SHORT': _agg([t for t in trades if t['direction'] == 'SHORT']),
    }

    wl_resolved = [t for t in trades if t.get('outcome_main') in ('WIN', 'LOSS')]
    recent_trades = sorted(wl_resolved, key=lambda t: t['date'], reverse=True)[:40]

    # ── By quarter ────────────────────────────────────────────────────────────
    def get_q(mo): return (mo - 1) // 3 + 1
    by_quarter = {f'Q{q}': _agg([t for t in trades if get_q(t['mo']) == q])
                  for q in range(1, 5)}

    # ── Risk stats ────────────────────────────────────────────────────────────
    outcomes_seq = [t['outcome_main'] for t in wl_resolved]
    def max_consec(seq, val):
        mx = cur = 0
        for v in seq:
            cur = cur + 1 if v == val else 0
            mx  = max(mx, cur)
        return mx
    max_cw = max_consec(outcomes_seq, 'WIN')
    max_cl = max_consec(outcomes_seq, 'LOSS')

    rs = [t['combined_r'] for t in wl_resolved if t['combined_r'] is not None]
    if len(rs) > 1:
        mean_r = float(np.mean(rs))
        std_r  = float(np.std(rs, ddof=1))
        years  = len({t['yr'] for t in wl_resolved}) or 1
        tpy    = len(rs) / years
        sharpe = round(mean_r / std_r * float(np.sqrt(tpy)), 3) if std_r > 0 else None
    else:
        sharpe = None

    mae_all  = [t['mae_pct']  for t in wl_resolved if t.get('mae_pct')  is not None]
    mfe2_all = [t.get('mfe2_pct', 0.0) for t in wl_resolved]
    mae_median  = round(float(np.median(mae_all)),  4) if mae_all  else None
    mfe_median  = round(float(np.median(mfe2_all)), 4) if mfe2_all else None

    win_rs  = [t['combined_r'] for t in wl_resolved
               if t['outcome_main'] == 'WIN' and t['combined_r'] is not None]
    avg_win_r = float(np.mean(win_rs)) if win_rs else 0.0
    p_wr   = overall['tp1_wr'] or 0.0
    edge   = p_wr * avg_win_r - (1 - p_wr) * 1.0
    N_units = ACCOUNT_SIZE / RISK_PER_TRADE
    if edge <= 0:
        ror = 1.0
    else:
        a   = (1 - edge) / (1 + edge)
        ror = round(min(1.0, a ** N_units), 4)

    risk_stats = {
        'ror':              ror,
        'max_consec_wins':  max_cw,
        'max_consec_losses': max_cl,
        'sharpe':           sharpe,
        'mae_median':       mae_median,
        'mfe_median':       mfe_median,
        'account_size':     ACCOUNT_SIZE,
        'risk_per_trade':   RISK_PER_TRADE,
    }

    return {
        'meta': {**meta_extra, **overall,
                 'generated_at': datetime.now().isoformat()},
        'overall':       overall,
        'by_dow':        by_dow,
        'by_hour':       by_hour,
        'by_year':       by_year,
        'by_month':      by_month,
        'by_quarter':    by_quarter,
        'by_direction':  by_direction,
        'risk_stats':    risk_stats,
        'recent_trades': recent_trades,
        'trades':        sorted(trades, key=lambda t: t['date']),
    }


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description='NY1 F.P.FVG backtest')
    parser.add_argument('--table',   default='nq_1m')
    parser.add_argument('--no-json', action='store_true', dest='no_json')
    args = parser.parse_args()

    bar = '═' * 68
    print(f'\n{bar}')
    print(f'  NY1 F.P.FVG Backtest  ·  {args.table}  ·  TP1=10bps  ·  Runner 20%')
    print(bar)

    print('\n  Loading bars...', end=' ', flush=True)
    con = connect_db()
    df  = load_bars(con, args.table)
    trading_days = df['trade_date'].nunique()
    print(f'{len(df):,} bars  ·  {trading_days:,} trading days')

    trades      = []
    n_setups    = 0
    n_filled    = 0
    n_no_fill   = 0
    n_no_setup  = 0

    print('  Running...', end=' ', flush=True)
    for date, day_df in df.groupby('trade_date'):
        arrs = build_day_arrays(day_df)

        # Need at least 9:30–10:01 bars
        if arrs['n'] < 5:
            continue

        # Find EOD index (16:00 bar for runner exit)
        eod_idx = find_idx(arrs, 16, 0)
        if eod_idx == -1:
            eod_idx = arrs['n'] - 1   # fallback to last bar

        # Detect first FVG
        fvg = detect_fvg(arrs)
        if fvg is None:
            n_no_setup += 1
            continue
        n_setups += 1

        # Risk check
        risk_pts = abs(fvg['entry'] - fvg['stop'])
        if risk_pts < MIN_RISK_PTS:
            n_no_setup += 1
            continue

        # MAE and MFE1 as percentage of entry price
        mae_pct  = round(risk_pts / fvg['entry'] * 100, 4)
        mfe1_pct = round(TP1_BPS * 100, 4)  # always 0.10%

        # TP1 level
        if fvg['direction'] == 'LONG':
            tp1 = fvg['entry'] * (1 + TP1_BPS)
        else:
            tp1 = fvg['entry'] * (1 - TP1_BPS)

        # Sanity: TP1 must be on the correct side of entry
        if fvg['direction'] == 'LONG'  and tp1 <= fvg['entry']: continue
        if fvg['direction'] == 'SHORT' and tp1 >= fvg['entry']: continue

        # Find fill
        fill = scan_fill(arrs, fvg['c3_idx'], fvg, eod_idx)
        if fill is None:
            n_no_fill += 1
            continue
        n_filled += 1

        # Resolve outcome
        outcome = resolve_outcome(arrs, fill['fill_idx'], fvg, tp1, eod_idx)

        # C2 timestamp for reference
        c2_ts = arrs['ts_et'][fvg['c2_idx']]
        c1_ts = arrs['ts_et'][fvg['c1_idx']]
        c3_ts = arrs['ts_et'][fvg['c3_idx']]
        dow   = int(day_df['dow'].iloc[0])
        yr    = int(day_df['yr'].iloc[0])
        mo    = int(day_df['mo'].iloc[0])

        fill_time = f"{fill['fill_hr']:02d}:{fill['fill_mn']:02d}"
        trades.append({
            'date':       str(date.date()) if hasattr(date, 'date') else str(date)[:10],
            'time':       fill_time,
            'dow':        dow,
            'dow_name':   DOW_NAMES.get(dow, '?'),
            'yr':         yr,
            'mo':         mo,
            'direction':  fvg['direction'],
            'c1_ts':      str(c1_ts)[:16],
            'c2_ts':      str(c2_ts)[:16],
            'c3_ts':      str(c3_ts)[:16],
            'fvg_top':    round(fvg['fvg_top'], 4),
            'fvg_bot':    round(fvg['fvg_bot'], 4),
            'entry':      round(fvg['entry'], 4),
            'stop':       round(fvg['stop'],  4),
            'tp1':        round(tp1, 4),
            'risk_pts':   round(risk_pts, 2),
            'mae_pct':    mae_pct,
            'mfe1_pct':   mfe1_pct if outcome['outcome_main'] == 'WIN' else 0.0,
            'fill_hr':    fill['fill_hr'],
            'fill_mn':    fill['fill_mn'],
            **outcome,
        })

    print(f'done\n')

    # ── Print summary ──────────────────────────────────────────────────────────
    wl   = [t for t in trades if t['outcome_main'] in ('WIN', 'LOSS')]
    wins = sum(1 for t in wl if t['outcome_main'] == 'WIN')
    wr   = wins / len(wl) if wl else 0
    mae_vals = [t['mae_pct'] for t in wl if t.get('mae_pct') is not None]
    avg_mae  = float(np.mean(mae_vals)) if mae_vals else 0

    print(f'{bar}')
    print(f'  SUMMARY')
    print(bar)
    print(f'  Trading days      : {trading_days:,}')
    print(f'  Days w/ setup     : {n_setups:,}  ({n_setups/trading_days:.1%})')
    print(f'  No fill (no retrace): {n_no_fill:,}')
    print(f'  Filled trades     : {n_filled:,}')
    print(f'  Resolved (W+L)    : {len(wl):,}')
    print(f'  Wins (TP1 hit)    : {wins:,}')
    print(f'  TP1 Win Rate      : {wr:.1%}')
    print(f'  Avg MAE           : {avg_mae:.4f}%')
    print()

    print(f'  BY DIRECTION')
    for d in ('LONG', 'SHORT'):
        sub  = [t for t in wl if t['direction'] == d]
        w    = sum(1 for t in sub if t['outcome_main'] == 'WIN')
        wr_d = w / len(sub) if sub else 0
        print(f'    {d:<6}  N={len(sub):>4}  WR={wr_d:.1%}')
    print()

    print(f'  BY DAY OF WEEK')
    for d in range(1, 6):
        sub  = [t for t in wl if t['dow'] == d]
        w    = sum(1 for t in sub if t['outcome_main'] == 'WIN')
        wr_d = w / len(sub) if sub else 0
        print(f'    {DOW_NAMES[d]}  N={len(sub):>4}  WR={wr_d:.1%}')
    print()

    print(f'  BY FILL HOUR')
    for h in range(9, 16):
        sub  = [t for t in wl if t['fill_hr'] == h]
        if not sub: continue
        w    = sum(1 for t in sub if t['outcome_main'] == 'WIN')
        wr_h = w / len(sub)
        print(f'    {h:02d}:xx  N={len(sub):>4}  WR={wr_h:.1%}')
    print()

    # ── Recent 40 trades table ─────────────────────────────────────────────────
    recent_40 = sorted(wl, key=lambda t: t['date'], reverse=True)[:40]
    hdr = f"  {'DATE':<12} {'TIME':<6} {'DIR':<6} {'MAE(%)':>8} {'MFE1(%)':>9} {'MFE2(%)':>9} {'MFE3(%)':>9} {'TP1':>5}"
    print(f'  RECENT 40 TRADES')
    print(f'  {"-"*74}')
    print(hdr)
    print(f'  {"-"*74}')
    for t in recent_40:
        tp1_str  = 'W' if t['outcome_main'] == 'WIN' else 'L'
        print(f"  {t['date']:<12} {t.get('time','?'):<6} {t['direction']:<6} "
              f"{t.get('mae_pct', 0):>8.4f} "
              f"{t.get('mfe1_pct', 0.0):>9.4f} "
              f"{t.get('mfe2_pct', 0.0):>9.4f} "
              f"{t.get('mfe3_pct', 0.0):>9.4f} "
              f"{tp1_str:>5}")
    print()

    print(f'{bar}\n')

    if not args.no_json:
        meta_extra = {
            'instrument':    args.table.split('_')[0].upper(),
            'model':         'NY1 F.P.FVG',
            'tp1_bps':       int(TP1_BPS * 10000),
            'table':         args.table,
            'trading_days':  trading_days,
            'total_setups':  n_setups,
            'total_filled':  n_filled,
            'total_no_fill': n_no_fill,
            'date_range':    f"{trades[0]['date']} – {trades[-1]['date']}" if trades else '',
        }
        out = build_stats(trades, meta_extra)
        with open(OUT_JSON, 'w') as f:
            json.dump(out, f, indent=2, default=str)
        print(f'  Saved → {OUT_JSON}')


if __name__ == '__main__':
    main()
