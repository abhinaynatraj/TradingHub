#!/usr/bin/env python3
"""
ny1_backtest.py — NY1 F.P.FVG Backtest  (open-run model)
==========================================================
Backtests the First Presented Fair Value Gap model on 1-minute NQ futures.

Model:
  • Entry  : limit at FVG edge (C3.low for LONG, C3.high for SHORT)
  • Stop   : structural — min(C1.low, C2.low) for LONG; max(C1.high, C2.high) for SHORT
  • Target : none — trade runs from fill to 16:00 ET (EOD)
  • Outcome: LOSS if stop hit before EOD, WIN if exits at EOD close
  • MFE    : max favourable excursion from fill to exit (analysed for TP research)

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
DB_PATH        = Path(__file__).parent.parent / 'Fractal Sweep' / 'candle_science.duckdb'
OUT_JSON       = Path(__file__).parent / 'ny1_results.json'

MIN_RISK_PTS   = 0.25    # guard against zero-risk setups
MIN_FVG_TICKS  = 0       # minimum FVG gap size in ticks (0 = no filter)
TICK_SIZE      = 0.25    # NQ futures tick size in points
ACCOUNT_SIZE   = 4_500   # account size for risk metrics ($)
RISK_PER_TRADE = 225     # risk per trade ($)

# ── Split-exit model ───────────────────────────────────────────────────────────
TP1_PCT      = 0.001     # 0.10% (10 bps) — Protect the Queen / TP1 level
TP1_SIZE     = 0.50      # 50% of position exits at TP1
RUNNER_SIZE  = 0.50      # 50% runner moves to BE, runs to EOD
DOW_NAMES      = {1: 'Mon', 2: 'Tue', 3: 'Wed', 4: 'Thu', 5: 'Fri'}  # DuckDB: 0=Sun
MONTH_NAMES    = {1:'Jan',2:'Feb',3:'Mar',4:'Apr',5:'May',6:'Jun',
                  7:'Jul',8:'Aug',9:'Sep',10:'Oct',11:'Nov',12:'Dec'}

TIMEFRAMES = [
    ('all', None),
    ('2y',  730),
    ('1y',  365),
    ('6m',  180),
    ('3m',   90),
    ('1m',   30),
]

# ── Top-10 fixed SL/TP profiles — ranked by NY1 weighted composite score ──────
# Scoring: Sharpe 25% + PF 20% + EV 15% + SQN 15% + MaxDD 10% + RoR 10% + CE 5%
# Source: fixed_profile_scan.py on NY1 data (SL ≥ 0.03%, not blown).
# Note: SL=0.10% FPFVG combos are blown on NY1 — classification filtering boosted
# their WR in FPFVG; NY1 runs without any classification.
# (rank, sl_pct, tp_pct)  —  sl/tp are percentages, e.g. 0.03 = 0.03%
# ── Top-10 fixed SL/TP profiles — verified clean in all timeframes ─────────────
# Ranked by NY1 weighted composite (Sharpe 25%+PF 20%+EV 15%+SQN 15%+MaxDD 10%+RoR 10%+CE 5%)
# All confirmed NOT blown in all, 2y, 1y, 6m, 3m, 1m windows.
# sl003_tp007 excluded despite scan rank: min_equity $599 all-time (87% DD, near-blown).
# (rank, sl_pct, tp_pct)
TOP10_FIXED_PROFILES = [
    (1,  0.03, 0.08),  # scan #1  score 0.9489 — 2.67R  MaxDD 23%
    (2,  0.03, 0.09),  # scan #5  score 0.9229 — 3.00R  MaxDD 35%
    (3,  0.03, 0.10),  # scan #7  score 0.8851 — 3.33R  MaxDD 35%
    (4,  0.03, 0.11),  # scan #8  score 0.8599 — 3.67R  MaxDD 36%
    (5,  0.03, 0.16),  # scan #10 score 0.8396 — 5.33R  MaxDD 31%
    (6,  0.03, 0.14),  # scan #11 score 0.8232 — 4.67R  MaxDD 41%
    (7,  0.03, 0.12),  # scan #12 score 0.8172 — 4.00R  MaxDD 42%
    (8,  0.03, 0.15),  # scan #13 score 0.8127 — 5.00R  MaxDD 34%
    (9,  0.03, 0.13),  # scan #14 score 0.8094 — 4.33R  MaxDD 37%
    (10, 0.03, 0.17),  # scan #15 score 0.8039 — 5.67R  MaxDD 33%
]

def profile_key(sl_pct: float, tp_pct: float) -> str:
    return f"sl{round(sl_pct * 100):03d}_tp{round(tp_pct * 100):03d}"


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
    df = df[~((df['hr'] == 16) & (df['mn'] > 0))].reset_index(drop=True)
    return df


# ── Timeframe filter ──────────────────────────────────────────────────────────
def filter_by_tf(trades: list, max_date: str, days: int | None) -> list:
    if days is None or not trades:
        return trades
    cutoff = (pd.Timestamp(max_date) - pd.Timedelta(days=days)).strftime('%Y-%m-%d')
    return [t for t in trades if t['date'] >= cutoff]


# ── Per-day array builder ─────────────────────────────────────────────────────
def build_day_arrays(day_df: pd.DataFrame) -> dict:
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
    tval = hr * 60 + mn
    idx  = int(np.searchsorted(arrs['tval'], tval, side='left'))
    if idx < arrs['n'] and arrs['tval'][idx] == tval:
        return idx
    return -1


# ── FVG Detection ─────────────────────────────────────────────────────────────
def detect_fvg(arrs: dict) -> dict | None:
    """
    Scan 9:31–9:59 for the first valid FVG.
    Bullish FVG: C3.low > C1.high, C2 bullish → LONG
    Bearish FVG: C3.high < C1.low, C2 bearish → SHORT
    """
    n = arrs['n']
    for c2_idx in range(1, n - 1):
        hr = int(arrs['hr'][c2_idx])
        mn = int(arrs['mn'][c2_idx])

        if hr != 9 or mn < 31 or mn > 59:
            if hr > 9 or (hr == 9 and mn > 59):
                break
            continue

        c1_idx = c2_idx - 1
        c3_idx = c2_idx + 1

        c1_h = arrs['high'][c1_idx];  c1_l = arrs['low'][c1_idx]
        c3_h = arrs['high'][c3_idx];  c3_l = arrs['low'][c3_idx]
        c2_o = arrs['open'][c2_idx];  c2_c = arrs['close'][c2_idx]

        if c3_l > c1_h and c2_c > c2_o:
            if MIN_FVG_TICKS > 0 and (c3_l - c1_h) < MIN_FVG_TICKS * TICK_SIZE:
                continue
            c2_l = arrs['low'][c2_idx]
            return {
                'c1_idx': c1_idx, 'c2_idx': c2_idx, 'c3_idx': c3_idx,
                'fvg_top': float(c3_l), 'fvg_bot': float(c1_h),
                'entry':   float(c3_l),
                'stop':    float(min(c1_l, c2_l)),
                'direction': 'LONG',
            }

        if c3_h < c1_l and c2_c < c2_o:
            if MIN_FVG_TICKS > 0 and (c1_l - c3_h) < MIN_FVG_TICKS * TICK_SIZE:
                continue
            c2_h = arrs['high'][c2_idx]
            return {
                'c1_idx': c1_idx, 'c2_idx': c2_idx, 'c3_idx': c3_idx,
                'fvg_top': float(c1_l), 'fvg_bot': float(c3_h),
                'entry':   float(c3_h),
                'stop':    float(max(c1_h, c2_h)),
                'direction': 'SHORT',
            }

    return None


# ── Entry fill scanner ────────────────────────────────────────────────────────
def scan_fill(arrs: dict, c3_idx: int, fvg: dict, eod_idx: int) -> dict | None:
    entry     = fvg['entry']
    direction = fvg['direction']
    for j in range(c3_idx + 1, eod_idx + 1):
        if direction == 'LONG':
            if arrs['low'][j] <= entry:
                return {'fill_idx': j, 'fill_ts': arrs['ts_et'][j],
                        'fill_hr': int(arrs['hr'][j]), 'fill_mn': int(arrs['mn'][j])}
        else:
            if arrs['high'][j] >= entry:
                return {'fill_idx': j, 'fill_ts': arrs['ts_et'][j],
                        'fill_hr': int(arrs['hr'][j]), 'fill_mn': int(arrs['mn'][j])}
    return None


# ── Split-exit resolver ────────────────────────────────────────────────────────
def resolve_open_run(arrs: dict, fill_idx: int, fvg: dict, eod_idx: int) -> dict:
    """
    Split-exit model:
      TP1  : 80% of position exits at TP1_PCT (0.10%) in trade's favour.
      Runner: remaining 20% runs to structural stop or EOD (16:00).

    Exit types:
      'TP1+EOD'  — TP1 hit, runner survived to EOD close
      'TP1+STOP' — TP1 hit, runner closed at breakeven (entry)
      'STOPPED'  — structural stop hit before TP1

    combined_r = TP1_SIZE * tp1_r + RUNNER_SIZE * runner_r
    MFE        = max favourable excursion from fill to last bar of the full trade.
    """
    entry     = fvg['entry']
    stop      = fvg['stop']
    direction = fvg['direction']
    risk_pts  = abs(entry - stop)

    # TP1 price level
    tp1_price = entry * (1 + TP1_PCT) if direction == 'LONG' \
                else entry * (1 - TP1_PCT)

    # ── Phase 1: scan for TP1 or stop ─────────────────────────────────────────
    tp1_idx  = None
    stop_idx = None

    for j in range(fill_idx + 1, eod_idx + 1):
        h = arrs['high'][j]
        l = arrs['low'][j]
        if direction == 'LONG':
            if l <= stop:
                stop_idx = j; break
            if h >= tp1_price:
                tp1_idx = j; break
        else:
            if h >= stop:
                stop_idx = j; break
            if l <= tp1_price:
                tp1_idx = j; break

    if stop_idx is not None:
        # Stopped before TP1
        exit_type   = 'STOPPED'
        tp1_exit    = None
        runner_exit = stop
        last_idx    = stop_idx
    elif tp1_idx is not None:
        # TP1 hit — runner stop moves to breakeven (entry)
        runner_type = 'EOD'
        runner_idx  = eod_idx
        for j in range(tp1_idx + 1, eod_idx + 1):
            h = arrs['high'][j]
            l = arrs['low'][j]
            if direction == 'LONG'  and l <= entry:
                runner_type = 'BE'; runner_idx = j; break
            if direction == 'SHORT' and h >= entry:
                runner_type = 'BE'; runner_idx = j; break
        exit_type   = 'TP1+EOD' if runner_type == 'EOD' else 'TP1+STOP'
        tp1_exit    = tp1_price
        runner_exit = entry if runner_type == 'BE' else float(arrs['close'][eod_idx])
        last_idx    = runner_idx
    else:
        # Neither TP1 nor stop hit — exits EOD without TP1
        exit_type   = 'STOPPED'   # treat as full stop (no partial exit)
        tp1_exit    = None
        runner_exit = float(arrs['close'][eod_idx])
        last_idx    = eod_idx

    # ── MFE: max favourable from fill bar through last bar of trade ────────────
    mfe_pts = 0.0
    for j in range(fill_idx, last_idx + 1):
        fav = (float(arrs['high'][j]) - entry) if direction == 'LONG' \
              else (entry - float(arrs['low'][j]))
        if fav > mfe_pts:
            mfe_pts = fav
    mfe_pct = round(mfe_pts / entry * 100, 4) if entry > 0 else 0.0

    # ── combined_r ─────────────────────────────────────────────────────────────
    if risk_pts > 0:
        if exit_type == 'STOPPED':
            runner_move = (runner_exit - entry) if direction == 'LONG' \
                          else (entry - runner_exit)
            combined_r = round(runner_move / risk_pts, 4)
        else:
            tp1_move    = (tp1_price  - entry) if direction == 'LONG' \
                          else (entry - tp1_price)
            runner_move = (runner_exit - entry) if direction == 'LONG' \
                          else (entry - runner_exit)
            combined_r  = round(TP1_SIZE * tp1_move / risk_pts
                                + RUNNER_SIZE * runner_move / risk_pts, 4)
    else:
        combined_r = None

    # Use runner_exit as the representative exit price for display
    display_exit = runner_exit if exit_type != 'STOPPED' else runner_exit

    return {
        'exit_type':   exit_type,
        'exit_price':  round(display_exit, 4),
        'tp1_price':   round(tp1_price, 4) if tp1_exit is not None else None,
        'mfe_pct':     mfe_pct,
        'combined_r':  combined_r,
    }


# ── Fixed SL/TP resolver ──────────────────────────────────────────────────────
def resolve_fixed_profile(arrs: dict, fill_idx: int, fvg: dict, eod_idx: int,
                           sl_pct: float, tp_pct: float) -> dict:
    """
    Fixed SL/TP profile resolver.
    sl_pct, tp_pct: in percent (e.g. 0.01 = 0.01%, 0.16 = 0.16%)
    Exit types: 'TP1+EOD' (TP hit), 'STOPPED' (SL hit or EOD without TP).
    mae_pct: actual adverse excursion (overrides structural stop distance in base).
    """
    entry     = fvg['entry']
    direction = fvg['direction']
    sl_pts    = entry * sl_pct / 100.0
    tp_pts    = entry * tp_pct / 100.0
    rr        = tp_pct / sl_pct

    if direction == 'LONG':
        sl_price = entry - sl_pts
        tp_price = entry + tp_pts
    else:
        sl_price = entry + sl_pts
        tp_price = entry - tp_pts

    exit_type  = None
    exit_price = None
    exit_idx   = eod_idx

    for j in range(fill_idx + 1, eod_idx + 1):
        h = arrs['high'][j]
        l = arrs['low'][j]
        if direction == 'LONG':
            if l <= sl_price:
                exit_type = 'STOPPED'; exit_price = sl_price; exit_idx = j; break
            if h >= tp_price:
                exit_type = 'TP1+EOD'; exit_price = tp_price; exit_idx = j; break
        else:
            if h >= sl_price:
                exit_type = 'STOPPED'; exit_price = sl_price; exit_idx = j; break
            if l <= tp_price:
                exit_type = 'TP1+EOD'; exit_price = tp_price; exit_idx = j; break

    if exit_type is None:
        # Reached EOD without TP or SL — treat as stopped
        exit_type  = 'STOPPED'
        exit_price = float(arrs['close'][eod_idx])
        exit_idx   = eod_idx

    # ── MAE: actual adverse excursion from fill to exit ───────────────────────
    mae_pts = 0.0
    for j in range(fill_idx, exit_idx + 1):
        adv = (entry - float(arrs['low'][j]))  if direction == 'LONG' \
              else (float(arrs['high'][j]) - entry)
        if adv > mae_pts:
            mae_pts = adv
    mae_pct_val = round(mae_pts / entry * 100, 4) if entry > 0 else 0.0

    # ── MFE: max favourable from fill to exit ────────────────────────────────
    mfe_pts = 0.0
    for j in range(fill_idx, exit_idx + 1):
        fav = (float(arrs['high'][j]) - entry) if direction == 'LONG' \
              else (entry - float(arrs['low'][j]))
        if fav > mfe_pts:
            mfe_pts = fav
    mfe_pct_val = round(mfe_pts / entry * 100, 4) if entry > 0 else 0.0

    # ── combined_r ─────────────────────────────────────────────────────────────
    if exit_type == 'TP1+EOD' and abs(float(exit_price) - tp_price) < 1e-4:
        combined_r = round(rr, 4)
    else:
        move = (float(exit_price) - entry) if direction == 'LONG' \
               else (entry - float(exit_price))
        combined_r = round(move / sl_pts, 4) if sl_pts > 0 else None

    return {
        'exit_type':  exit_type,
        'exit_price': round(float(exit_price), 4),
        'tp1_price':  round(tp_price, 4) if exit_type == 'TP1+EOD' else None,
        'mfe_pct':    mfe_pct_val,
        'mae_pct':    mae_pct_val,  # actual adverse excursion (overrides structural)
        'combined_r': combined_r,
    }


# ── Stats helpers ─────────────────────────────────────────────────────────────
_VALID_EXITS = ('TP1+EOD', 'TP1+STOP', 'STOPPED')
_DOW_ORDER   = [1, 2, 3, 4, 5]
_DOW_LABELS  = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']

def _build_excursion_heatmap(trades: list[dict], col: str, n_bins: int = 20) -> dict:
    """Bin mae_pct or mfe_pct by day-of-week into a pre-computed density grid."""
    valid = [t for t in trades if t.get(col) is not None and t[col] >= 0 and t.get('dow') in _DOW_ORDER]
    if len(valid) < 5:
        return {'grid': [], 'val_max': 0.5, 'labels': _DOW_LABELS, 'n': 0}
    vals = sorted(t[col] for t in valid)
    val_max = vals[min(int(len(vals) * 0.95), len(vals) - 1)] or 0.5
    grid = [[0] * n_bins for _ in range(5)]
    for t in valid:
        di = _DOW_ORDER.index(t['dow'])
        xi = min(int(t[col] / val_max * n_bins), n_bins - 1)
        grid[di][xi] += 1
    return {'grid': grid, 'val_max': round(val_max, 4), 'labels': _DOW_LABELS, 'n': len(valid)}

def _agg(trades: list[dict]) -> dict:
    wl = [t for t in trades if t.get('exit_type') in _VALID_EXITS]
    if not wl:
        return {'n': 0, 'tp1_count': 0, 'stopped_count': 0,
                'tp1_wr': None,
                'avg_mae_pct': None, 'med_mae_pct': None,
                'avg_mfe_pct': None, 'med_mfe_pct': None}
    n      = len(wl)
    tp1    = sum(1 for t in wl if t['exit_type'] in ('TP1+EOD', 'TP1+STOP'))
    tp1_wr = tp1 / n   # TP1 hit rate — used by charts as the bar height

    mae_vals = [t['mae_pct'] for t in wl if t.get('mae_pct') is not None]
    mfe_vals = [t.get('mfe_pct', 0.0) for t in wl]
    avg_mae  = round(float(np.mean(mae_vals)),   4) if mae_vals else None
    med_mae  = round(float(np.median(mae_vals)), 4) if mae_vals else None
    avg_mfe  = round(float(np.mean(mfe_vals)),   4) if mfe_vals else None
    med_mfe  = round(float(np.median(mfe_vals)), 4) if mfe_vals else None

    return {'n': n, 'tp1_count': tp1, 'stopped_count': n - tp1,
            'tp1_wr': round(tp1_wr, 4),
            'avg_mae_pct': avg_mae, 'med_mae_pct': med_mae,
            'avg_mfe_pct': avg_mfe, 'med_mfe_pct': med_mfe}


def build_stats(trades: list, meta_extra: dict,
                include_full_trades: bool = True) -> dict:
    overall = _agg(trades)

    by_dow = {DOW_NAMES[d]: _agg([t for t in trades if t['dow'] == d])
              for d in range(1, 6)}
    by_hour  = {str(h): _agg([t for t in trades if t['fill_hr'] == h])
                for h in range(9, 16)}
    by_year  = {str(yr): _agg([t for t in trades if t['yr'] == yr])
                for yr in sorted({t['yr'] for t in trades})}
    by_month = {MONTH_NAMES[mo]: _agg([t for t in trades if t['mo'] == mo])
                for mo in range(1, 13)}
    def get_q(mo): return (mo - 1) // 3 + 1
    by_quarter = {f'Q{q}': _agg([t for t in trades if get_q(t['mo']) == q])
                  for q in range(1, 5)}
    by_direction = {
        'LONG':  _agg([t for t in trades if t['direction'] == 'LONG']),
        'SHORT': _agg([t for t in trades if t['direction'] == 'SHORT']),
    }

    wl_resolved   = [t for t in trades if t.get('exit_type') in _VALID_EXITS]
    recent_trades = sorted(wl_resolved, key=lambda t: t['date'], reverse=True)[:40]

    # ── Streak stats ──────────────────────────────────────────────────────────
    # Win streak = consecutive TP1 hits; loss streak = consecutive full stops
    exit_seq = ['TP1' if t['exit_type'] in ('TP1+EOD','TP1+STOP') else 'STOPPED'
                for t in wl_resolved]
    def max_consec(seq, val):
        mx = cur = 0
        for v in seq:
            cur = cur + 1 if v == val else 0
            mx  = max(mx, cur)
        return mx
    max_cw = max_consec(exit_seq, 'TP1')
    max_cl = max_consec(exit_seq, 'STOPPED')

    # ── Sharpe ────────────────────────────────────────────────────────────────
    rs = [t['combined_r'] for t in wl_resolved if t['combined_r'] is not None]
    if len(rs) > 1:
        mean_r = float(np.mean(rs))
        std_r  = float(np.std(rs, ddof=1))
        years  = len({t['yr'] for t in wl_resolved}) or 1
        tpy    = len(rs) / years
        sharpe = round(mean_r / std_r * float(np.sqrt(tpy)), 3) if std_r > 0 else None
    else:
        sharpe = None

    # ── Equity curve / max DD ─────────────────────────────────────────────────
    eq     = float(ACCOUNT_SIZE)
    min_eq = eq
    for t in sorted(wl_resolved, key=lambda x: x['date']):
        if t['combined_r'] is not None:
            eq += t['combined_r'] * RISK_PER_TRADE
            if eq < min_eq:
                min_eq = eq
    min_eq = round(min_eq, 2)
    blown  = min_eq <= 0.0

    # ── Win / loss R summaries ────────────────────────────────────────────────
    stopped_list = [t for t in wl_resolved if t['exit_type'] == 'STOPPED']
    tp1_list     = [t for t in wl_resolved if t['exit_type'] in ('TP1+EOD','TP1+STOP')]
    tp1_rs  = [t['combined_r'] for t in tp1_list     if t['combined_r'] is not None]
    stop_rs = [t['combined_r'] for t in stopped_list if t['combined_r'] is not None]
    avg_tp1_r    = float(np.mean(tp1_rs))  if tp1_rs  else 0.0
    avg_stop_r   = round(float(np.mean(stop_rs)), 4) if stop_rs else -1.0
    avg_win_usd  = round(avg_tp1_r  * RISK_PER_TRADE, 2)
    avg_loss_usd = round(avg_stop_r * RISK_PER_TRADE, 2)

    p_wr = overall['tp1_wr'] or 0.0
    edge = p_wr * avg_tp1_r - (1 - p_wr) * abs(avg_stop_r)
    N_units = ACCOUNT_SIZE / RISK_PER_TRADE
    if edge <= 0:
        ror = 1.0
    else:
        a   = (1 - edge) / (1 + edge)
        ror = round(min(1.0, a ** N_units), 4)

    # ── CE — avg(MFE / MAE) for TP1+EOD trades ───────────────────────────────
    ce_ratios = []
    for t in [t for t in wl_resolved if t['exit_type'] == 'TP1+EOD']:
        mae = t.get('mae_pct') or 0.0
        mfe = t.get('mfe_pct') or 0.0
        if mae > 0 and mfe > 0:
            ce_ratios.append(mfe / mae)
    ce = round(float(np.mean(ce_ratios)), 3) if ce_ratios else None

    # ── MAE deep analysis (PhD-level, mirrors MFE study) ─────────────────────
    mae_raw = [t['mae_pct'] for t in wl_resolved
               if t.get('mae_pct') is not None and t['mae_pct'] > 0]
    mae_dist = None
    mae_bell = None   # kept for backward compat — populated below
    if len(mae_raw) > 10:
        mae_np = np.array(mae_raw)
        Nm = len(mae_np)

        # ── Basic moments ─────────────────────────────────────────────────────
        mae_mean = float(np.mean(mae_np))
        mae_med  = float(np.median(mae_np))
        mae_std  = float(np.std(mae_np, ddof=1))
        cen      = mae_np - mae_mean
        mae_skew = float(np.mean(cen**3) / (mae_std**3)) if mae_std > 0 else 0.0
        mae_kurt = float(np.mean(cen**4) / (mae_std**4)) - 3.0 if mae_std > 0 else 0.0

        # ── Mode via histogram peak ───────────────────────────────────────────
        hc, he = np.histogram(mae_np, bins=80)
        mi     = int(np.argmax(hc))
        mae_mode = round(float((he[mi] + he[mi + 1]) / 2), 4)

        # ── Full percentile table ─────────────────────────────────────────────
        pct_levels = [5, 10, 15, 20, 25, 30, 35, 40, 50, 60, 65, 70, 75, 80, 85, 90, 95, 99]
        mae_percentiles = {f'p{p}': round(float(np.percentile(mae_np, p)), 4)
                           for p in pct_levels}

        # ── Log-normal fit ────────────────────────────────────────────────────
        mae_pos = mae_np[mae_np > 1e-6]
        if len(mae_pos) > 10:
            lm      = np.log(mae_pos)
            lm_mu   = float(np.mean(lm))
            lm_sig  = float(np.std(lm, ddof=1))
            mae_lognorm = {
                'mu':             round(lm_mu,  4),
                'sigma':          round(lm_sig, 4),
                'implied_median': round(float(np.exp(lm_mu)), 4),
                'implied_mean':   round(float(np.exp(lm_mu + 0.5 * lm_sig**2)), 4),
                'implied_mode':   round(float(np.exp(lm_mu - lm_sig**2)), 4),
                'goodness':       round(float(np.corrcoef(
                    np.sort(lm),
                    np.linspace(-3, 3, len(lm))
                )[0, 1]), 4),
            }
        else:
            mae_lognorm = None

        # ── Natural clusters (3-tier) ─────────────────────────────────────────
        mc1_thresh = float(np.percentile(mae_np, 33))
        mc2_thresh = float(np.percentile(mae_np, 75))
        mc1 = mae_np[mae_np <  mc1_thresh]
        mc2 = mae_np[(mae_np >= mc1_thresh) & (mae_np < mc2_thresh)]
        mc3 = mae_np[mae_np >= mc2_thresh]
        mae_clusters = [
            {'label': 'Tight',    'range': f'0 – {mc1_thresh:.4f}%',
             'n': len(mc1), 'pct_of_trades': round(len(mc1)/Nm*100, 1),
             'mean':   round(float(np.mean(mc1)),   4) if len(mc1) else 0,
             'median': round(float(np.median(mc1)), 4) if len(mc1) else 0,
             'max':    round(float(np.max(mc1)),    4) if len(mc1) else 0},
            {'label': 'Moderate', 'range': f'{mc1_thresh:.4f}% – {mc2_thresh:.4f}%',
             'n': len(mc2), 'pct_of_trades': round(len(mc2)/Nm*100, 1),
             'mean':   round(float(np.mean(mc2)),   4) if len(mc2) else 0,
             'median': round(float(np.median(mc2)), 4) if len(mc2) else 0,
             'max':    round(float(np.max(mc2)),    4) if len(mc2) else 0},
            {'label': 'Wide',     'range': f'{mc2_thresh:.4f}%+',
             'n': len(mc3), 'pct_of_trades': round(len(mc3)/Nm*100, 1),
             'mean':   round(float(np.mean(mc3)),   4) if len(mc3) else 0,
             'median': round(float(np.median(mc3)), 4) if len(mc3) else 0,
             'max':    round(float(np.max(mc3)),    4) if len(mc3) else 0},
        ]

        # ── SL sweep — "how tight can you go?" ───────────────────────────────
        # For each MAE level X (% of trades exceeded it):
        #   exceeded_pct  : reach rate (% of trades with MAE >= threshold)
        #   threshold     : the MAE value at that percentile
        #   n_exceeded    : count of trades exceeding
        #   p_recovered   : fraction of exceeded trades that still hit TP1 (false stop rate)
        #   p_ko          : fraction that did NOT recover (genuine stops if SL set here)
        #   ev_cost       : EV lost per trade from false stops (R units)
        sl_sweep_pcts = [5, 10, 15, 20, 25, 30, 33, 40, 50, 60, 75, 90]
        sl_sweep = []
        for sp in sl_sweep_pcts:
            threshold = float(np.percentile(mae_np, 100 - sp))
            exceeded  = [t for t in wl_resolved if t.get('mae_pct', 0) >= threshold]
            if not exceeded:
                continue
            n_exc    = len(exceeded)
            n_rec    = sum(1 for t in exceeded
                          if t['exit_type'] in ('TP1+EOD', 'TP1+STOP'))
            p_rec    = round(n_rec / n_exc, 4)
            p_ko     = round(1.0 - p_rec, 4)
            # EV cost: false stops lose avg_tp1_r instead of gaining it
            ev_cost  = round(n_rec * avg_tp1_r / Nm, 4) if avg_tp1_r > 0 else 0.0
            sl_sweep.append({
                'exceed_pct':  sp,           # % of trades that touch this MAE
                'threshold':   round(threshold, 4),
                'n_exceeded':  n_exc,
                'p_recovered': p_rec,        # false stop rate (would have recovered)
                'p_ko':        p_ko,         # true stop rate (genuine losers)
                'ev_cost':     ev_cost,
            })

        # ── Optimal SL recommendation ─────────────────────────────────────────
        # Tightest level where majority of touched trades are genuine losers
        # (p_ko >= 0.50, i.e., most exceeded trades did NOT recover)
        opt_sl = None
        opt_sl_exceed = None
        for row in reversed(sl_sweep):
            if row['p_ko'] >= 0.50:
                opt_sl         = row['threshold']
                opt_sl_exceed  = row['exceed_pct']
                break
        if opt_sl is None and sl_sweep:
            best = max(sl_sweep, key=lambda r: r['p_ko'])
            opt_sl        = best['threshold']
            opt_sl_exceed = best['exceed_pct']

        # ── Histogram for canvas ──────────────────────────────────────────────
        p99m     = float(np.percentile(mae_np, 99))
        mae_edges = np.linspace(0, p99m, 61)
        mae_hv, _ = np.histogram(mae_np, bins=mae_edges)
        mae_hist  = {
            'edges':  [round(float(e), 5) for e in mae_edges],
            'counts': mae_hv.tolist(),
        }

        # ── Backward-compat mae_bell ──────────────────────────────────────────
        mae_bell = {
            'mean':      round(mae_mean, 4),
            'std':       round(mae_std,  4),
            'plus_0_5s': round(mae_mean + 0.5 * mae_std, 4),
            'plus_1s':   round(mae_mean + mae_std, 4),
            'plus_1_5s': round(mae_mean + 1.5 * mae_std, 4),
            'plus_2s':   round(mae_mean + 2.0 * mae_std, 4),
            'cov_mean':  round(float(np.mean(mae_np <= mae_mean)) * 100, 1),
            'cov_0_5s':  round(float(np.mean(mae_np <= mae_mean + 0.5*mae_std)) * 100, 1),
            'cov_1s':    round(float(np.mean(mae_np <= mae_mean + mae_std)) * 100, 1),
            'cov_1_5s':  round(float(np.mean(mae_np <= mae_mean + 1.5*mae_std)) * 100, 1),
            'cov_2s':    round(float(np.mean(mae_np <= mae_mean + 2.0*mae_std)) * 100, 1),
        }

        mae_dist = {
            'mean':      round(mae_mean, 4),
            'median':    round(mae_med,  4),
            'mode':      mae_mode,
            'std':       round(mae_std,  4),
            'skewness':  round(mae_skew, 3),
            'kurtosis':  round(mae_kurt, 3),
            'percentiles': mae_percentiles,
            'lognorm':   mae_lognorm,
            'clusters':  mae_clusters,
            'sl_sweep':  sl_sweep,
            'opt_sl':    round(opt_sl, 4) if opt_sl else None,
            'opt_sl_exceed': opt_sl_exceed,
            'histogram': mae_hist,
            'n':         Nm,
            'bell':      mae_bell,  # kept for legacy canvas
        }

    # ── MFE deep analysis (PhD-level) ────────────────────────────────────────
    mfe_raw = [t.get('mfe_pct', 0.0) for t in wl_resolved]
    mfe_dist = None
    if len(mfe_raw) > 10:
        mfe_np = np.array(mfe_raw)
        N = len(mfe_np)

        # ── Basic moments ─────────────────────────────────────────────────────
        mfe_mean = float(np.mean(mfe_np))
        mfe_med  = float(np.median(mfe_np))
        mfe_std  = float(np.std(mfe_np, ddof=1))
        centered = mfe_np - mfe_mean
        mfe_skew = float(np.mean(centered**3) / (mfe_std**3)) if mfe_std > 0 else 0.0
        mfe_kurt = float(np.mean(centered**4) / (mfe_std**4)) - 3.0 if mfe_std > 0 else 0.0

        # ── Mode via histogram peak ───────────────────────────────────────────
        hist_counts, hist_edges = np.histogram(mfe_np, bins=80)
        mode_idx  = int(np.argmax(hist_counts))
        mfe_mode  = round(float((hist_edges[mode_idx] + hist_edges[mode_idx + 1]) / 2), 4)

        # ── Full percentile table (every 5th + key levels) ───────────────────
        pct_levels = [5, 10, 15, 20, 25, 30, 35, 40, 50, 60, 65, 70, 75, 80, 85, 90, 95, 99]
        percentiles = {f'p{p}': round(float(np.percentile(mfe_np, p)), 4)
                       for p in pct_levels}

        # ── Log-normal fit (MFE is almost always right-skewed & positive) ────
        mfe_pos = mfe_np[mfe_np > 1e-6]
        if len(mfe_pos) > 10:
            log_mfe   = np.log(mfe_pos)
            log_mu    = float(np.mean(log_mfe))
            log_sigma = float(np.std(log_mfe, ddof=1))
            lognorm = {
                'mu':             round(log_mu,    4),
                'sigma':          round(log_sigma, 4),
                'implied_median': round(float(np.exp(log_mu)), 4),
                'implied_mean':   round(float(np.exp(log_mu + 0.5 * log_sigma**2)), 4),
                'implied_mode':   round(float(np.exp(log_mu - log_sigma**2)), 4),
                'goodness':       round(float(np.corrcoef(
                    np.sort(log_mfe),
                    np.linspace(-3, 3, len(log_mfe))
                )[0, 1]), 4),   # Pearson r with normal quantiles (higher = better fit)
            }
        else:
            lognorm = None

        # ── Natural clusters (3-tier: small / moderate / large runs) ─────────
        c1_thresh = float(np.percentile(mfe_np, 33))
        c2_thresh = float(np.percentile(mfe_np, 75))
        c1 = mfe_np[mfe_np <  c1_thresh]
        c2 = mfe_np[(mfe_np >= c1_thresh) & (mfe_np < c2_thresh)]
        c3 = mfe_np[mfe_np >= c2_thresh]
        clusters = [
            {'label': 'Small',    'range': f'0 – {c1_thresh:.4f}%',
             'n': len(c1), 'pct_of_trades': round(len(c1)/N*100, 1),
             'mean': round(float(np.mean(c1)),   4) if len(c1) else 0,
             'median': round(float(np.median(c1)), 4) if len(c1) else 0,
             'max':  round(float(np.max(c1)),   4) if len(c1) else 0},
            {'label': 'Moderate', 'range': f'{c1_thresh:.4f}% – {c2_thresh:.4f}%',
             'n': len(c2), 'pct_of_trades': round(len(c2)/N*100, 1),
             'mean': round(float(np.mean(c2)),   4) if len(c2) else 0,
             'median': round(float(np.median(c2)), 4) if len(c2) else 0,
             'max':  round(float(np.max(c2)),   4) if len(c2) else 0},
            {'label': 'Large',    'range': f'{c2_thresh:.4f}%+',
             'n': len(c3), 'pct_of_trades': round(len(c3)/N*100, 1),
             'mean': round(float(np.mean(c3)),   4) if len(c3) else 0,
             'median': round(float(np.median(c3)), 4) if len(c3) else 0,
             'max':  round(float(np.max(c3)),   4) if len(c3) else 0},
        ]

        # ── BE trigger analysis — "Protect the Queen" ─────────────────────────
        # For each trigger X%: if we move stop to entry once MFE >= X, then
        #   • trades with MFE >= X and combined_r < 0 exit at 0R instead
        # Key metrics per trigger:
        #   reach_rate   : % of all trades that hit this level
        #   p_pos_given  : P(combined_r > 0 | MFE >= X)  — "confidence" at this level
        #   n_rescued    : trades saved from negative exit
        #   ev_delta     : EV improvement per trade (R) from moving stop to BE at X
        #   cumulative_r_saved : total R saved across all trades
        trigger_pcts = [5, 10, 15, 20, 25, 30, 33, 40, 50, 60, 75, 90]
        be_triggers  = []
        base_ev      = float(np.mean([t['combined_r'] for t in wl_resolved
                                      if t['combined_r'] is not None]))
        for tp in trigger_pcts:
            trigger_val = float(np.percentile(mfe_np, 100 - tp))  # "reach rate = tp %"
            reached = [t for t in wl_resolved
                       if t.get('mfe_pct', 0) >= trigger_val and t['combined_r'] is not None]
            if not reached:
                continue
            n_reached   = len(reached)
            n_pos       = sum(1 for t in reached if t['combined_r'] > 0)
            p_pos       = round(n_pos / n_reached, 4)
            rescued     = [t for t in reached if t['combined_r'] < 0]
            n_rescued   = len(rescued)
            r_saved     = sum(abs(t['combined_r']) for t in rescued)
            ev_delta    = round(r_saved / N, 4)
            new_ev      = round(base_ev + ev_delta, 4)
            be_triggers.append({
                'reach_rate':    tp,              # % of trades that hit this level
                'trigger_pct':   round(trigger_val, 4),
                'n_reached':     n_reached,
                'p_pos_given':   p_pos,           # P(exit > entry | MFE >= trigger)
                'n_rescued':     n_rescued,        # saved from negative exit
                'ev_delta':      ev_delta,         # EV improvement per trade (R)
                'new_ev':        new_ev,
            })

        # ── Protect the Queen recommendation ─────────────────────────────────
        # Find the LOWEST trigger_pct where p_pos_given >= 0.50
        # i.e. most aggressive (earliest) BE move that still gives a coin-flip
        # be_triggers is ordered reach_rate ASC (high trigger → low trigger),
        # so we iterate in reverse to find the last entry >= 0.50
        ptq_level = None
        ptq_reach_rate = None
        for row in reversed(be_triggers):
            if row['p_pos_given'] >= 0.50:
                ptq_level      = row['trigger_pct']
                ptq_reach_rate = row['reach_rate']
                break
        # If no level reaches 50%, recommend the highest p_pos one
        if ptq_level is None and be_triggers:
            best = max(be_triggers, key=lambda r: r['p_pos_given'])
            ptq_level      = best['trigger_pct']
            ptq_reach_rate = best['reach_rate']

        # ── Histogram bins for canvas drawing ────────────────────────────────
        # 60 log-spaced bins from 0 to p99 for the histogram curve
        p99_val = float(np.percentile(mfe_np, 99))
        bin_edges = np.linspace(0, p99_val, 61)
        hist_vals, _ = np.histogram(mfe_np, bins=bin_edges)
        hist_data = {
            'edges': [round(float(e), 5) for e in bin_edges],
            'counts': hist_vals.tolist(),
        }

        mfe_dist = {
            # Moments
            'mean':     round(mfe_mean, 4),
            'median':   round(mfe_med,  4),
            'mode':     mfe_mode,
            'std':      round(mfe_std,  4),
            'skewness': round(mfe_skew, 3),
            'kurtosis': round(mfe_kurt, 3),
            # Percentiles
            'percentiles': percentiles,
            # Distribution fit
            'lognorm': lognorm,
            # Clusters
            'clusters': clusters,
            # BE / protect-the-queen
            'be_triggers':    be_triggers,
            'ptq_level':      round(ptq_level, 4) if ptq_level else None,
            'ptq_reach_rate': ptq_reach_rate,
            # Histogram for canvas
            'histogram': hist_data,
            'n': N,
        }

    risk_stats = {
        'ror':               ror,
        'max_consec_wins':   max_cw,
        'max_consec_losses': max_cl,
        'sharpe':            sharpe,
        'mae_median':        overall.get('med_mae_pct'),
        'mfe_median':        overall.get('med_mfe_pct'),
        'account_size':      ACCOUNT_SIZE,
        'risk_per_trade':    RISK_PER_TRADE,
        'trades':            len(wl_resolved),
        'tp1_count':         len(tp1_list),
        'stopped_count':     len(stopped_list),
        'avg_win_usd':       avg_win_usd,
        'avg_loss_usd':      avg_loss_usd,
        'min_equity_usd':    min_eq,
        'blown':             blown,
        'ce':                ce,
        'mae_bell':          mae_bell,
        'mae_dist':          mae_dist,
        'mfe_dist':          mfe_dist,
        'mae_heatmap':       _build_excursion_heatmap(trades, 'mae_pct'),
        'mfe_heatmap':       _build_excursion_heatmap(trades, 'mfe_pct'),
    }

    result = {
        'meta': {**meta_extra, **overall, 'generated_at': datetime.now().isoformat()},
        'overall':       overall,
        'by_dow':        by_dow,
        'by_hour':       by_hour,
        'by_year':       by_year,
        'by_month':      by_month,
        'by_quarter':    by_quarter,
        'by_direction':  by_direction,
        'risk_stats':    risk_stats,
        'recent_trades': recent_trades,
    }
    if include_full_trades:
        result['trades'] = sorted(trades, key=lambda t: t['date'])
    return result


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description='NY1 F.P.FVG backtest — split-exit (TP1=0.10% + runner)')
    parser.add_argument('--table',   default='nq_1m')
    parser.add_argument('--no-json', action='store_true', dest='no_json')
    args = parser.parse_args()

    bar = '═' * 68
    print(f'\n{bar}')
    print(f'  NY1 F.P.FVG Backtest  ·  {args.table}  ·  Split-Exit (TP1={TP1_PCT*100:.4f}% + Runner)')
    print(bar)

    print('\n  Loading bars...', end=' ', flush=True)
    con = connect_db()
    df  = load_bars(con, args.table)
    trading_days = df['trade_date'].nunique()
    print(f'{len(df):,} bars  ·  {trading_days:,} trading days')

    trades        = []
    fixed_trades  = {profile_key(sl, tp): [] for _, sl, tp in TOP10_FIXED_PROFILES}
    n_setups   = 0
    n_filled   = 0
    n_no_fill  = 0
    n_no_setup = 0

    print('  Running...', end=' ', flush=True)
    for date, day_df in df.groupby('trade_date'):
        arrs = build_day_arrays(day_df)
        if arrs['n'] < 5:
            continue

        eod_idx = find_idx(arrs, 16, 0)
        if eod_idx == -1:
            eod_idx = arrs['n'] - 1

        fvg = detect_fvg(arrs)
        if fvg is None:
            n_no_setup += 1
            continue
        n_setups += 1

        risk_pts = abs(fvg['entry'] - fvg['stop'])
        if risk_pts < MIN_RISK_PTS:
            n_no_setup += 1
            continue

        mae_pct = round(risk_pts / fvg['entry'] * 100, 4)

        fill = scan_fill(arrs, fvg['c3_idx'], fvg, eod_idx)
        if fill is None:
            n_no_fill += 1
            continue
        n_filled += 1

        c2_ts = arrs['ts_et'][fvg['c2_idx']]
        c1_ts = arrs['ts_et'][fvg['c1_idx']]
        c3_ts = arrs['ts_et'][fvg['c3_idx']]
        dow   = int(day_df['dow'].iloc[0])
        yr    = int(day_df['yr'].iloc[0])
        mo    = int(day_df['mo'].iloc[0])

        fill_time = f"{fill['fill_hr']:02d}:{fill['fill_mn']:02d}"
        base = {
            'date':      str(date.date()) if hasattr(date, 'date') else str(date)[:10],
            'time':      fill_time,
            'dow':       dow,
            'dow_name':  DOW_NAMES.get(dow, '?'),
            'yr':        yr,
            'mo':        mo,
            'direction': fvg['direction'],
            'c1_ts':     str(c1_ts)[:16],
            'c2_ts':     str(c2_ts)[:16],
            'c3_ts':     str(c3_ts)[:16],
            'fvg_top':   round(fvg['fvg_top'], 4),
            'fvg_bot':   round(fvg['fvg_bot'], 4),
            'entry':     round(fvg['entry'], 4),
            'stop':      round(fvg['stop'],  4),
            'risk_pts':  round(risk_pts, 2),
            'mae_pct':   mae_pct,
            'fill_hr':   fill['fill_hr'],
            'fill_mn':   fill['fill_mn'],
        }

        outcome = resolve_open_run(arrs, fill['fill_idx'], fvg, eod_idx)
        trades.append({**base, **outcome})

        for _, sl_pct, tp_pct in TOP10_FIXED_PROFILES:
            pk = profile_key(sl_pct, tp_pct)
            fixed_outcome = resolve_fixed_profile(arrs, fill['fill_idx'], fvg, eod_idx,
                                                   sl_pct, tp_pct)
            fixed_trades[pk].append({**base, **fixed_outcome})

    print(f'done\n')

    wl        = [t for t in trades if t.get('exit_type') in _VALID_EXITS]
    n_tp1     = sum(1 for t in wl if t['exit_type'] in ('TP1+EOD', 'TP1+STOP'))
    n_stopped = sum(1 for t in wl if t['exit_type'] == 'STOPPED')
    mfe_arr   = np.array([t.get('mfe_pct', 0.0) for t in wl]) if wl else np.array([])

    print(f'{bar}')
    print(f'  NY1 F.P.FVG · Split-Exit: TP1={TP1_PCT*100:.4f}% ({int(TP1_SIZE*100)}%) + Runner ({int(RUNNER_SIZE*100)}%)')
    print(bar)
    print(f'  Trading days         : {trading_days:,}')
    print(f'  Days w/ setup        : {n_setups:,}  ({n_setups/trading_days:.1%})')
    print(f'  No fill (no retrace) : {n_no_fill:,}')
    print(f'  Filled trades        : {n_filled:,}')
    print(f'  Resolved             : {len(wl):,}')
    print(f'  TP1 hit              : {n_tp1:,}  ({n_tp1/len(wl):.1%})')
    print(f'  Stopped (before TP1) : {n_stopped:,}  ({n_stopped/len(wl):.1%})')
    if len(mfe_arr):
        print(f'\n  MFE Distribution (all resolved trades)')
        print(f'    Mean   : {np.mean(mfe_arr):.4f}%')
        print(f'    Median : {np.median(mfe_arr):.4f}%')
        print(f'    StdDev : {np.std(mfe_arr, ddof=1):.4f}%')
        print(f'    p25    : {np.percentile(mfe_arr, 25):.4f}%')
        print(f'    p75    : {np.percentile(mfe_arr, 75):.4f}%')
        print(f'    p90    : {np.percentile(mfe_arr, 90):.4f}%')
        print(f'    p99    : {np.percentile(mfe_arr, 99):.4f}%')
    print()

    print(f'  BY DIRECTION')
    for d in ('LONG', 'SHORT'):
        sub    = [t for t in wl if t['direction'] == d]
        n_tp1d = sum(1 for t in sub if t['exit_type'] in ('TP1+EOD','TP1+STOP'))
        print(f'    {d:<6}  N={len(sub):>4}  TP1={n_tp1d/len(sub):.1%}  STOP={(len(sub)-n_tp1d)/len(sub):.1%}')
    print()

    print(f'  BY DAY OF WEEK')
    for d in range(1, 6):
        sub    = [t for t in wl if t['dow'] == d]
        n_tp1d = sum(1 for t in sub if t['exit_type'] in ('TP1+EOD','TP1+STOP'))
        print(f'    {DOW_NAMES[d]}  N={len(sub):>4}  TP1={n_tp1d/len(sub):.1%}')
    print()

    print(f'  BY FILL HOUR')
    for h in range(9, 16):
        sub    = [t for t in wl if t['fill_hr'] == h]
        if not sub: continue
        n_tp1h = sum(1 for t in sub if t['exit_type'] in ('TP1+EOD','TP1+STOP'))
        print(f'    {h:02d}:xx  N={len(sub):>4}  TP1={n_tp1h/len(sub):.1%}')
    print()

    print(f'{bar}\n')

    if not args.no_json:
        max_date = trades[-1]['date'] if trades else ''
        base_meta = {
            'instrument':    args.table.split('_')[0].upper(),
            'table':         args.table,
            'trading_days':  trading_days,
            'total_setups':  n_setups,
            'total_filled':  n_filled,
            'total_no_fill': n_no_fill,
        }

        out = {}
        for tf_key, tf_days in TIMEFRAMES:
            is_full = tf_days is None
            print(f'  Building timeframe: {tf_key}...', end=' ', flush=True)
            tf_trades = filter_by_tf(trades, max_date, tf_days)
            ref = tf_trades
            dr  = f"{ref[0]['date']} – {ref[-1]['date']}" if ref else ''
            meta_extra = {**base_meta, 'date_range': dr, 'timeframe': tf_key}

            profiles = {}
            profiles['open_run'] = build_stats(tf_trades, meta_extra,
                                               include_full_trades=is_full)
            for rank, sl_pct, tp_pct in TOP10_FIXED_PROFILES:
                pk = profile_key(sl_pct, tp_pct)
                tf_fixed = filter_by_tf(fixed_trades[pk], max_date, tf_days)
                profile_meta = {**meta_extra,
                                'profile': pk,
                                'profile_rank': rank,
                                'sl_pct': sl_pct,
                                'tp_pct': tp_pct,
                                'rr': round(tp_pct / sl_pct, 1)}
                profiles[pk] = build_stats(tf_fixed, profile_meta,
                                           include_full_trades=is_full)
            out[tf_key] = {'profiles': profiles}
            print(f'{len(tf_trades)} trades')

        with open(OUT_JSON, 'w') as f:
            json.dump(out, f, indent=2, default=str)
        print(f'\n  Saved → {OUT_JSON}')


if __name__ == '__main__':
    main()
