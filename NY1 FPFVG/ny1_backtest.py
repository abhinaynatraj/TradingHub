#!/usr/bin/env python3
"""
ny1_backtest.py — NY1 F.P.FVG Backtest
========================================
Backtests the First Presented Fair Value Gap model on 1-minute NQ futures.

Two model variants:
  cashflow          — 100% of position exits at TP1 (+0.10%). No runner.
  cashflow_extended — 80% exits at TP1; 20% runner with stop moved to entry
                      (breakeven) once TP1 is hit. Runner exits at BE stop or EOD.

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
DB_PATH  = Path(__file__).parent.parent / 'Fractal Sweep' / 'candle_science.duckdb'
OUT_JSON = Path(__file__).parent / 'ny1_results.json'

TP1_BPS       = 0.001   # 10 basis points = 0.10%
MIN_RISK_PTS  = 0.25    # guard against zero-risk setups
MIN_FVG_TICKS = 0       # minimum FVG gap size in ticks (0 = no filter)
TICK_SIZE     = 0.25    # NQ futures tick size in points
ACCOUNT_SIZE  = 4500    # account size for risk metrics ($)
RISK_PER_TRADE = 225    # risk per trade ($)
DOW_NAMES    = {1: 'Mon', 2: 'Tue', 3: 'Wed', 4: 'Thu', 5: 'Fri'}  # DuckDB: 0=Sun

# Fixed % stop/TP profiles — top 10 from brute-force scan (fixed_profile_scan.py)
# Each entry: (json_key, stop_pct, tp_pct, display_name)
PCT_PROFILES = [
    # Top 10 from master backtester (ranked by CE)
    ('pct_004_008', 0.0004, 0.0008, '#1  0.04% Stop / 0.08% TP  (2:1)'),
    ('pct_010_005', 0.0010, 0.0005, '#2  0.10% Stop / 0.05% TP  (0.5:1)'),
    ('pct_003_006', 0.0003, 0.0006, '#3  0.03% Stop / 0.06% TP  (2:1)'),
    ('pct_005_009', 0.0005, 0.0009, '#4  0.05% Stop / 0.09% TP  (1.8:1)'),
    ('pct_004_007', 0.0004, 0.0007, '#5  0.04% Stop / 0.07% TP  (1.75:1)'),
    ('pct_005_008', 0.0005, 0.0008, '#6  0.05% Stop / 0.08% TP  (1.6:1)'),
    ('pct_004_006', 0.0004, 0.0006, '#7  0.04% Stop / 0.06% TP  (1.5:1)'),
    ('pct_005_007', 0.0005, 0.0007, '#8  0.05% Stop / 0.07% TP  (1.4:1)'),
    ('pct_005_006', 0.0005, 0.0006, '#9  0.05% Stop / 0.06% TP  (1.2:1)'),
    ('pct_010_006', 0.0010, 0.0006, '#10 0.10% Stop / 0.06% TP  (0.6:1)'),
]
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
                    tp1: float, eod_idx: int, model: str = 'cashflow_extended') -> dict:
    """
    Scan from bar after fill for TP1 or stop.  TP1 wins on same-bar conflict.

    cashflow:
        100% exits at TP1.  No runner.  combined_r = tp1_move / risk_pts or -1.

    cashflow_extended:
        80% exits at TP1.  20% runner with stop moved to entry (breakeven).
        Runner exits at BE stop or EOD close.
    """
    entry     = fvg['entry']
    stop      = fvg['stop']
    direction = fvg['direction']
    risk_pts  = abs(entry - stop)

    outcome_main = 'OPEN'
    tp1_idx      = None

    # ── Step 1: scan for TP1 or stop (same for both models) ───────────────────
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
            outcome_main = 'WIN'; tp1_idx = j; break
        if hit_tp1:
            outcome_main = 'WIN'; tp1_idx = j; break
        if hit_stop:
            outcome_main = 'LOSS'; break

    # ── Step 2: model-specific resolution ─────────────────────────────────────
    mfe2_pct          = 0.0
    runner_exit_price = None
    runner_outcome    = None

    if risk_pts <= 0:
        combined_r = None
    elif outcome_main == 'LOSS':
        combined_r = -1.0
    elif outcome_main == 'WIN':
        tp1_move = abs(tp1 - entry)
        tp1_r    = tp1_move / risk_pts

        if model == 'cashflow':
            # 100% exits at TP1.  TP1 hit is treated as 1R (symmetric risk/reward).
            combined_r = 1.0

        else:  # cashflow_extended — runner with BE stop
            runner_stop       = entry          # stop moves to entry once TP1 hit
            runner_exit_idx   = eod_idx
            runner_exit_price = float(arrs['close'][eod_idx])
            runner_outcome    = 'WIN'

            for j in range(tp1_idx + 1, eod_idx + 1):
                if direction == 'LONG'  and arrs['low'][j]  <= runner_stop:
                    runner_exit_idx   = j
                    runner_exit_price = runner_stop
                    runner_outcome    = 'BE'
                    break
                if direction == 'SHORT' and arrs['high'][j] >= runner_stop:
                    runner_exit_idx   = j
                    runner_exit_price = runner_stop
                    runner_outcome    = 'BE'
                    break

            # MFE2: max favorable from fill to runner exit
            mfe2_pts = 0.0
            for j in range(fill_idx, runner_exit_idx + 1):
                fav = (float(arrs['high'][j]) - entry) if direction == 'LONG' \
                      else (entry - float(arrs['low'][j]))
                if fav > mfe2_pts:
                    mfe2_pts = fav
            mfe2_pct = round(mfe2_pts / entry * 100, 4) if entry > 0 else 0.0

            if direction == 'LONG':
                run_move = runner_exit_price - entry
            else:
                run_move = entry - runner_exit_price
            runner_r   = run_move / risk_pts
            # TP1 leg = 0.8R (treating TP1 hit as 1R); runner leg = 0.2 × runner_r
            combined_r = round(0.8 + 0.2 * runner_r, 4)

    else:
        combined_r = None

    return {
        'outcome_main':       outcome_main,
        'runner_exit_price':  runner_exit_price,
        'runner_outcome':     runner_outcome,
        'combined_r':         combined_r,
        'mfe2_pct':           mfe2_pct,
    }


def resolve_pct_profile(arrs: dict, fill_idx: int, fvg: dict,
                        stop_pct: float, tp_pct: float, eod_idx: int) -> dict:
    """
    Fixed-percentage stop/TP profile.  Stop and TP are both computed as a
    fixed percentage of the entry price, independent of FVG structure.

        stop  = entry ± entry * stop_pct
        tp    = entry ± entry * tp_pct
        R:R   = tp_pct / stop_pct  (fixed per profile)
    """
    entry     = fvg['entry']
    direction = fvg['direction']

    if direction == 'LONG':
        stop = entry * (1.0 - stop_pct)
        tp   = entry * (1.0 + tp_pct)
    else:
        stop = entry * (1.0 + stop_pct)
        tp   = entry * (1.0 - tp_pct)

    outcome = 'OPEN'
    for j in range(fill_idx + 1, eod_idx + 1):
        h = arrs['high'][j]
        l = arrs['low'][j]
        if direction == 'LONG':
            hit_tp   = h >= tp
            hit_stop = l <= stop
        else:
            hit_tp   = l <= tp
            hit_stop = h >= stop

        if hit_tp and hit_stop:
            outcome = 'WIN'; break   # TP wins on same-bar conflict
        if hit_tp:
            outcome = 'WIN'; break
        if hit_stop:
            outcome = 'LOSS'; break

    if outcome == 'WIN':
        combined_r = round(tp_pct / stop_pct, 4)
    elif outcome == 'LOSS':
        combined_r = -1.0
    else:
        combined_r = None

    return {
        'outcome_main': outcome,
        'combined_r':   combined_r,
        'pct_stop':     round(stop, 4),
        'pct_tp':       round(tp,   4),
    }


# ── Stats helpers ─────────────────────────────────────────────────────────────
def _agg(trades: list[dict]) -> dict:
    wl   = [t for t in trades if t['outcome_main'] in ('WIN', 'LOSS')]
    if not wl:
        return {'n': 0, 'wins': 0, 'tp1_wr': None,
                'avg_mae_pct': None, 'med_mae_pct': None,
                'avg_mfe1_pct': None, 'med_mfe1_pct': None, 'avg_mfe2_pct': None}
    n    = len(wl)
    wins = sum(1 for t in wl if t['outcome_main'] == 'WIN')
    wr   = wins / n

    mae_vals  = [t['mae_pct']  for t in wl if t.get('mae_pct')  is not None]
    mfe1_vals = [t.get('mfe1_pct', 0.0) for t in wl]
    mfe2_vals = [t.get('mfe2_pct', 0.0) for t in wl]
    avg_mae   = round(float(np.mean(mae_vals)),  4) if mae_vals  else None
    med_mae   = round(float(np.median(mae_vals)), 4) if mae_vals  else None
    avg_mfe1  = round(float(np.mean(mfe1_vals)), 4) if mfe1_vals else None
    med_mfe1  = round(float(np.median(mfe1_vals)), 4) if mfe1_vals else None
    avg_mfe2  = round(float(np.mean(mfe2_vals)), 4) if mfe2_vals else None

    return {'n': n, 'wins': wins, 'tp1_wr': round(wr, 4),
            'avg_mae_pct': avg_mae, 'med_mae_pct': med_mae,
            'avg_mfe1_pct': avg_mfe1, 'med_mfe1_pct': med_mfe1,
            'avg_mfe2_pct': avg_mfe2}


def build_stats(trades, meta_extra: dict, model: str = 'cashflow_extended') -> dict:
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
    if model == 'cashflow':
        mfe_all = [t.get('mfe1_pct', 0.0) for t in wl_resolved if t['outcome_main'] == 'WIN']
    else:
        mfe_all = [t.get('mfe2_pct', 0.0) for t in wl_resolved]
    mae_median  = round(float(np.median(mae_all)),  4) if mae_all  else None
    mfe_median  = round(float(np.median(mfe_all)),  4) if mfe_all  else None

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

    # Additional metrics for hero tiles
    losses_list  = [t for t in wl_resolved if t['outcome_main'] == 'LOSS']
    loss_rs      = [t['combined_r'] for t in losses_list if t['combined_r'] is not None]
    avg_loss_r   = round(float(np.mean(loss_rs)), 4) if loss_rs else -1.0
    avg_win_usd  = round(avg_win_r  * RISK_PER_TRADE, 2)
    avg_loss_usd = round(avg_loss_r * RISK_PER_TRADE, 2)

    eq = float(ACCOUNT_SIZE)
    min_eq = eq
    for t in sorted(wl_resolved, key=lambda x: x['date']):
        if t['combined_r'] is not None:
            eq += t['combined_r'] * RISK_PER_TRADE
            if eq < min_eq:
                min_eq = eq
    min_eq = round(min_eq, 2)
    blown  = min_eq <= 0.0

    if 'stop_pct' in meta_extra:
        sl_pct_val = meta_extra['stop_pct']
        tp_pct_val = meta_extra['tp_pct']
    else:
        sl_pct_val = overall.get('avg_mae_pct') or round(TP1_BPS * 100, 4)
        tp_pct_val = round(TP1_BPS * 100, 4)

    # CE — Combined Edge: avg(MFE / MAE) for WIN trades
    # Uses mfe2_pct (runner max favorable) for cashflow_extended, mfe1_pct otherwise
    mfe_key = 'mfe2_pct' if model == 'cashflow_extended' else 'mfe1_pct'
    ce_ratios = []
    for t in [t for t in wl_resolved if t['outcome_main'] == 'WIN']:
        mae = t.get('mae_pct') or 0.0
        mfe = t.get(mfe_key) or 0.0
        if mae > 0 and mfe > 0:
            ce_ratios.append(mfe / mae)
    ce = round(float(np.mean(ce_ratios)), 3) if ce_ratios else None

    # Bell curve of actual MAE distribution — SL candidates per sigma tier
    mae_raw = [t['mae_pct'] for t in wl_resolved
               if t.get('mae_pct') is not None and t['mae_pct'] > 0]
    if len(mae_raw) > 1 and len(set(mae_raw)) > 1:
        mae_mu = float(np.mean(mae_raw))
        mae_sd = float(np.std(mae_raw, ddof=1))
        # Actual empirical percentiles for coverage labels
        mae_np  = np.array(mae_raw)
        mae_bell = {
            'mean':         round(mae_mu, 4),
            'std':          round(mae_sd, 4),
            'plus_0_5s':    round(mae_mu + 0.5 * mae_sd, 4),   # ~69th pct
            'plus_1s':      round(mae_mu + mae_sd, 4),          # ~84th pct
            'plus_1_5s':    round(mae_mu + 1.5 * mae_sd, 4),   # ~93rd pct
            'plus_2s':      round(mae_mu + 2.0 * mae_sd, 4),   # ~97.5th pct
            # Empirical coverage at each candidate
            'cov_mean':     round(float(np.mean(mae_np <= mae_mu)) * 100, 1),
            'cov_0_5s':     round(float(np.mean(mae_np <= mae_mu + 0.5*mae_sd)) * 100, 1),
            'cov_1s':       round(float(np.mean(mae_np <= mae_mu + mae_sd)) * 100, 1),
            'cov_1_5s':     round(float(np.mean(mae_np <= mae_mu + 1.5*mae_sd)) * 100, 1),
            'cov_2s':       round(float(np.mean(mae_np <= mae_mu + 2.0*mae_sd)) * 100, 1),
        }
    else:
        mae_bell = None

    risk_stats = {
        'ror':              ror,
        'max_consec_wins':  max_cw,
        'max_consec_losses': max_cl,
        'sharpe':           sharpe,
        'mae_median':       mae_median,
        'mfe_median':       mfe_median,
        'account_size':     ACCOUNT_SIZE,
        'risk_per_trade':   RISK_PER_TRADE,
        'trades':           len(wl_resolved),
        'wins':             overall['wins'],
        'losses':           len(losses_list),
        'be_count':         0,
        'avg_win_usd':      avg_win_usd,
        'avg_loss_usd':     avg_loss_usd,
        'min_equity_usd':   min_eq,
        'blown':            blown,
        'sl_pct':           sl_pct_val,
        'tp_pct':           tp_pct_val,
        'ce':               ce,
        'mae_bell':         mae_bell,
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

    trades_by_model = {'cashflow': [], 'cashflow_extended': []}
    trades_by_pct   = {key: [] for key, *_ in PCT_PROFILES}
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

        # C2 timestamp for reference
        c2_ts = arrs['ts_et'][fvg['c2_idx']]
        c1_ts = arrs['ts_et'][fvg['c1_idx']]
        c3_ts = arrs['ts_et'][fvg['c3_idx']]
        dow   = int(day_df['dow'].iloc[0])
        yr    = int(day_df['yr'].iloc[0])
        mo    = int(day_df['mo'].iloc[0])

        fill_time = f"{fill['fill_hr']:02d}:{fill['fill_mn']:02d}"
        base = {
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
            'fill_hr':    fill['fill_hr'],
            'fill_mn':    fill['fill_mn'],
        }

        # Resolve outcome for each structural model
        for model_key in ('cashflow', 'cashflow_extended'):
            outcome = resolve_outcome(arrs, fill['fill_idx'], fvg, tp1, eod_idx, model=model_key)
            trades_by_model[model_key].append({
                **base,
                'mfe1_pct': mfe1_pct if outcome['outcome_main'] == 'WIN' else 0.0,
                **outcome,
            })

        # Resolve outcome for each fixed-% profile
        for pct_key, stop_pct, tp_pct, _ in PCT_PROFILES:
            pct_out = resolve_pct_profile(arrs, fill['fill_idx'], fvg,
                                          stop_pct, tp_pct, eod_idx)
            trades_by_pct[pct_key].append({
                **base,
                'mae_pct':  round(stop_pct * 100, 4),   # fixed stop distance
                'mfe1_pct': round(tp_pct * 100, 4) if pct_out['outcome_main'] == 'WIN' else 0.0,
                'mfe2_pct': 0.0,
                'runner_exit_price': None,
                'runner_outcome':    None,
                **pct_out,
            })

    print(f'done\n')

    # ── Print summary (use cashflow_extended as reference) ────────────────────
    trades   = trades_by_model['cashflow_extended']
    wl       = [t for t in trades if t['outcome_main'] in ('WIN', 'LOSS')]
    wins     = sum(1 for t in wl if t['outcome_main'] == 'WIN')
    wr       = wins / len(wl) if wl else 0
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
    hdr = f"  {'DATE':<12} {'TIME':<6} {'DIR':<6} {'MAE(%)':>8} {'MFE1(%)':>9} {'MFE2(%)':>9} {'TP1':>5}"
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
              f"{tp1_str:>5}")
    print()

    print(f'{bar}\n')

    if not args.no_json:
        ref = trades_by_model['cashflow_extended']
        meta_extra = {
            'instrument':    args.table.split('_')[0].upper(),
            'tp1_bps':       int(TP1_BPS * 10000),
            'table':         args.table,
            'trading_days':  trading_days,
            'total_setups':  n_setups,
            'total_filled':  n_filled,
            'total_no_fill': n_no_fill,
            'date_range':    f"{ref[0]['date']} – {ref[-1]['date']}" if ref else '',
        }
        out = {
            'cashflow': build_stats(
                trades_by_model['cashflow'],
                {**meta_extra, 'model_name': 'Cashflow'},
                model='cashflow',
            ),
            'cashflow_extended': build_stats(
                trades_by_model['cashflow_extended'],
                {**meta_extra, 'model_name': 'Cashflow + Extended'},
                model='cashflow_extended',
            ),
        }
        for pct_key, stop_pct, tp_pct, display_name in PCT_PROFILES:
            out[pct_key] = build_stats(
                trades_by_pct[pct_key],
                {**meta_extra,
                 'model_name': display_name,
                 'stop_pct':   round(stop_pct * 100, 4),
                 'tp_pct':     round(tp_pct  * 100, 4)},
                model='cashflow',   # single-exit, same mfe_median logic
            )
        with open(OUT_JSON, 'w') as f:
            json.dump(out, f, indent=2, default=str)
        print(f'  Saved → {OUT_JSON}')


if __name__ == '__main__':
    main()
