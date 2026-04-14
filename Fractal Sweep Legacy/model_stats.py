#!/usr/bin/env python3
"""
model_stats.py  —  Multi-Timeframe Sweep + CISD Statistical Engine v6.0
========================================================================
Runs each of the four model pairs across TWO sweep modes × ONE CISD mode,
producing up to 8 output keys.

SWEEP MODE
  PREV     — sweep reference = immediately prior sweep-TF candle

CISD MODE
  CISD — Change in State of Delivery (body-only):
         • Wicks ignored — only opens and closes matter
         • Dojis (close == open) are neutral (skip, don't break run)
         • Step 1 — BACKWARD from the return bar: find the consecutive
           opposing delivery run that formed the high/low before the sweep.
             SHORT: find consecutive up-close run before return bar
             LONG:  find consecutive down-close run before return bar
         • cisd_level = open of the FIRST (earliest) candle in that run
             SHORT: lowest open in the ascending bullish run
             LONG:  highest open in the descending bearish run
         • Step 2 — FORWARD from the return bar: fire on close through level
             LONG:  close > cisd_level
             SHORT: close < cisd_level

Performance:
  • resolve_outcomes_vectorised: fully numpy, no iterrows — ~20-40× faster
  • detect_model: all inner loops use pre-built numpy arrays + searchsorted,
    no pandas .loc[] slicing in the hot path
  • find_unswept_level: uses passed-in numpy arrays, no list comprehensions
  • find_cisd: integer index arithmetic, no df.loc[] per call
  • All TF arrays built once, reused across all 8 model/mode combos

Usage:
    python3 model_stats.py                              # all 4 models
    python3 model_stats.py --models 1H_5M 1H_3M
    python3 model_stats.py --cisd-fast-bars 12
    python3 model_stats.py --table es_1m
"""

import argparse
import sys
import duckdb
import pandas as pd
import numpy as np
import json
from pathlib import Path
import scipy.stats as _scipy_stats

# ── PATHS ─────────────────────────────────────────────────────────────────────
DB_PATH   = Path(__file__).parent / 'candle_science.duckdb'
OUT_PATH  = Path(__file__).parent / 'model_stats.json'
TABLE     = 'nq_1m'
PHASE1_XL = Path(__file__).parent.parent / 'archive' / 'Fractal Sweep' / 'fractal_phase1_results.xlsx'

# ── DATE → CLASSIFICATION MAP ────────────────────────────────────────────────
# Uses the daily_classifier engine to classify dates directly from DuckDB.
# Falls back to the Excel file if the classifier or DB is unavailable.
def _load_date_classification():
    """Build {date_str: cls_key} by running the daily classifier on DB data."""
    # Try live classification from DuckDB first
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent / 'NY1 FPFVG'))
        from daily_classifier import classify_day
        import duckdb

        con = duckdb.connect(str(DB_PATH), read_only=True)
        df = con.execute("""
            SELECT
                timezone('America/New_York', timestamp) AS datetime,
                open::DOUBLE AS open, high::DOUBLE AS high,
                low::DOUBLE  AS low,  close::DOUBLE AS close
            FROM nq_1m
            ORDER BY timestamp
        """).df()
        con.close()

        df['datetime'] = pd.to_datetime(df['datetime'])
        df['date'] = df['datetime'].dt.date

        mapping = {}
        for day, grp in df.groupby('date'):
            grp = grp.reset_index(drop=True)
            day_class, _ = classify_day(grp)
            mapping[str(day)] = day_class

        print(f'  Classified {len(mapping)} dates from DuckDB (live)')
        return mapping
    except Exception as e:
        print(f'  [info] Live classification unavailable ({e}), trying Excel fallback...')

    # Fallback: load from Excel
    try:
        import openpyxl
        wb = openpyxl.load_workbook(PHASE1_XL, read_only=True, data_only=True)
        mapping = {}
        for cls_key, sheet_name in [('DWP','DWP Data'),('DNP','DNP Data'),
                                     ('R1','R1 Data'),('R2','R2 Data'),
                                     ('Unclassified','Unclassified Data')]:
            if sheet_name not in wb.sheetnames:
                continue
            ws = wb[sheet_name]
            rows = list(ws.iter_rows(values_only=True))
            hdr = rows[2]
            ci  = {h: i for i, h in enumerate(hdr) if h}
            date_col = ci.get('Date')
            if date_col is None:
                continue
            for row in rows[3:]:
                if not row[0]:
                    continue
                try:
                    d = str(row[date_col])[:10]
                    if d and d not in mapping:
                        mapping[d] = cls_key
                except Exception:
                    continue
        return mapping
    except Exception as e:
        print(f'  [warn] Could not load classification map: {e}')
        return {}

DATE_CLASSIFICATION = _load_date_classification()
print(f'  Loaded {len(DATE_CLASSIFICATION)} date→classification mappings')

# ── GLOBAL CONSTANTS ──────────────────────────────────────────────────────────
ACCOUNT_SIZE     = 4500   # $ account size for risk metrics
RISK_PER_TRADE   = 225    # $ risk per trade
POINT_VALUE      = 2.0    # $ per point for MNQ (Micro NQ); NQ = 20.0
MIN_RISK_PTS     = 3.0
MAX_RISK_PTS     = RISK_PER_TRADE / POINT_VALUE  # 112.5 pts for MNQ @ $225 risk
OUTCOME_MAX_BARS = 360
SWEEP_MAX_PCT    = 0.50
CISD_FAST_BARS   = None  # None = no limit; CISD can form any time before session end
UNSWEPT_LOOKBACK = 10

# ── RISK PROFILES ─────────────────────────────────────────────────────────────
# Each tuple: (stop_val, target_val, display_key, profile_type)
#
# profile_type='mult'  → stop/target distances = val × base_risk
#                         base_risk = |entry_price − sweep_extreme|
#
# profile_type='pct'   → stop/target distances = entry_price × val / 100
#                         (fixed % of entry price, independent of sweep size)
RR_PROFILES = [
    # --- Structural Dynamic: SL = sweep extreme (1×base_risk), TP1 = 1R, 90% exit; runner (10%) with BE stop ---
    (1.0, 1.0, 'structural_dynamic', 'structural'),
    # --- Split-exit: TP1 @ structural PTQ level (90% off), 10% runner free with BE stop ---
    # target_val is a placeholder; overridden per-model with structural ptq_level at runtime
    (1.0, 0.0, 'split_80_20', 'split_tp'),
    # --- Simple 1R: SL = sweep extreme, TP = 1R, 100% exit (all-in/all-out) ---
    (1.0, 1.0, 'simple_1r', 'mult'),
]
DEFAULT_PROFILE = 'structural_dynamic'

DOW_NAMES = {0:'Sun', 1:'Mon', 2:'Tue', 3:'Wed', 4:'Thu', 5:'Fri', 6:'Sat'}
HR_LABELS = {h: f"{h:02d}:00" for h in range(0, 24)}

# ── MODEL DEFINITIONS ─────────────────────────────────────────────────────────
MODELS = {
    '4H_15M': dict(
        label        = '4H Sweep · 15M CISD',
        sweep_tf_min = 4 * 60,
        cisd_tf_min  = 15,
        q1_min       = 60,
        min_range    = 30,
        session_hrs  = (7.0, 16.0),
    ),
    '1H_5M': dict(
        label        = '1H Sweep · 5M CISD',
        sweep_tf_min = 60,
        cisd_tf_min  = 5,
        q1_min       = 15,
        min_range    = 12,
        session_hrs  = (7.0, 16.0),
    ),
    '1H_3M': dict(
        label        = '1H Sweep · 3M CISD',
        sweep_tf_min = 60,
        cisd_tf_min  = 3,
        q1_min       = 15,
        min_range    = 12,
        session_hrs  = (7.0, 16.0),
    ),
    '30M_3M': dict(
        label        = '30M Sweep · 3M CISD',
        sweep_tf_min = 30,
        cisd_tf_min  = 3,
        q1_min       = 8,
        min_range    = 8,
        session_hrs  = (7.0, 16.0),
    ),
}
SWEEP_MODES = ['PREV']
CISD_MODES  = ['CISD']


# ── DB ────────────────────────────────────────────────────────────────────────
def connect(db_path):
    return duckdb.connect(str(db_path), read_only=True)


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
    print(f"   {len(raw):,} total bars  |  {len(raw_rth):,} RTH (07:00–16:00)")
    return raw, raw_rth


# ── RESAMPLE ──────────────────────────────────────────────────────────────────
def resample(df_1m, tf_min, label):
    print(f"   Building {label} bars ...")
    df2 = df_1m.copy()
    df2['ts_tf'] = df2.index.floor(f"{tf_min}min")
    agg = df2.groupby('ts_tf').agg(
        trade_date=('trade_date','first'), yr=('yr','first'), mo=('mo','first'),
        dow=('dow','first'), hr=('hr','first'),
        open_tf=('open','first'), high_tf=('high','max'),
        low_tf=('low','min'),    close_tf=('close','last'),
    ).sort_index()
    print(f"      {len(agg):,} {label} bars")
    return agg


# ── NUMPY ARRAY BUILDERS ──────────────────────────────────────────────────────
def df_to_arrays(df):
    """
    Convert a time-indexed resampled OHLC dataframe to numpy arrays.
    ts_ns is int64 nanoseconds — used with np.searchsorted for fast lookups.
    Called ONCE per timeframe; results reused across all model/mode combos.
    """
    return dict(
        ts_ns      = df.index.view('int64').copy(),
        open       = df['open_tf'].values.astype('float64'),
        high       = df['high_tf'].values.astype('float64'),
        low        = df['low_tf'].values.astype('float64'),
        close      = df['close_tf'].values.astype('float64'),
        trade_date = df['trade_date'].values.copy(),
        yr         = df['yr'].values.astype('int32'),
        dow        = df['dow'].values.astype('int32'),
        hr         = df['hr'].values.astype('int32'),
    )


def df_1m_to_arrays(df):
    """Convert 1m dataframe to numpy arrays for vectorised outcome resolution."""
    return dict(
        ts_ns      = df.index.view('int64').copy(),
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


# ── SESSION LABEL ─────────────────────────────────────────────────────────────
def get_session(hr_float):
    if 8.5  <= hr_float < 11.5: return 'NY1'
    if 11.5 <= hr_float < 16.0: return 'NY2'
    if 7.0  <= hr_float < 8.5:  return 'PRE'
    if 0    <= hr_float < 7.0:  return 'OVERNIGHT'
    return 'OTHER'


# ── HOUR OPEN HELPER ─────────────────────────────────────────────────────────
_HOUR_NS = 60 * 60 * 10**9

def compute_hour_open_legacy(m1_ts_ns, m1_opens, entry_ts_ns):
    """
    Return the open of the first 1m bar inside the clock hour containing
    entry_ts_ns. Used by the CISD Hour-Open Alignment criterion: compares
    the CISD candle close to the hour's open to confirm setup direction.
    """
    hour_start_ns = (int(entry_ts_ns) // _HOUR_NS) * _HOUR_NS
    hour_end_ns = hour_start_ns + _HOUR_NS
    idx = int(np.searchsorted(m1_ts_ns, hour_start_ns, side='left'))
    if idx >= len(m1_ts_ns):
        return None
    if int(m1_ts_ns[idx]) >= hour_end_ns:
        return None
    return float(m1_opens[idx])



# ── CISD DETECTION ────────────────────────────────────────────────────────────
def _find_cisd(c_opens, c_closes, c_ts_ns, start_idx, n_bars, direction):
    """
    CISD — Change in State of Delivery (body-only).

    Step 1 — BACKWARD scan from start_idx (the return bar):
      Find the consecutive opposing delivery run that formed the high/low
      BEFORE the return to range — i.e. the candles that made the sweep.
        SHORT: look for consecutive up-close candles (bullish delivery run)
        LONG:  look for consecutive down-close candles (bearish delivery run)
      Scan back up to n_bars before start_idx.

    cisd_level = open of the FIRST (earliest in time) candle in that run:
        SHORT: first = lowest open of the ascending bullish run
        LONG:  first = highest open of the descending bearish run

    Step 2 — FORWARD scan from start_idx:
      Fire on the first bar whose close crosses cisd_level:
        LONG:  close > cisd_level
        SHORT: close < cisd_level

    Dojis (close == open) are neutral — skipped, do not break the run.
    """
    end  = min(start_idx + n_bars, len(c_closes))
    back = max(0, start_idx - n_bars * 4)      # backward scan: look much further back for run start

    if direction == 'LONG':
        # ── Step 1: backward — find consecutive bearish run before start_idx ──
        j = start_idx - 1
        while j >= back and c_closes[j] == c_opens[j]:
            j -= 1                             # skip dojis
        if j < back or c_closes[j] >= c_opens[j]:
            return None, None                  # no bearish candle found
        run_start = j
        k = j - 1
        while k >= back:
            if   c_closes[k] < c_opens[k]:  run_start = k; k -= 1
            elif c_closes[k] == c_opens[k]:  k -= 1        # doji neutral
            else: break
        cisd_level = float(c_opens[run_start])  # open of FIRST (highest) bearish candle

        # ── Step 2: forward — first bar that closes above cisd_level ──────────
        for i in range(start_idx, end):
            if c_closes[i] > cisd_level:
                return c_ts_ns[i], cisd_level

    else:  # SHORT
        # ── Step 1: backward — find consecutive bullish run before start_idx ──
        j = start_idx - 1
        while j >= back and c_closes[j] == c_opens[j]:
            j -= 1
        if j < back or c_closes[j] <= c_opens[j]:
            return None, None                  # no bullish candle found
        run_start = j
        k = j - 1
        while k >= back:
            if   c_closes[k] > c_opens[k]:  run_start = k; k -= 1
            elif c_closes[k] == c_opens[k]:  k -= 1
            else: break
        cisd_level = float(c_opens[run_start])  # open of FIRST (lowest) bullish candle

        # ── Step 2: forward — first bar that closes below cisd_level ──────────
        for i in range(start_idx, end):
            if c_closes[i] < cisd_level:
                return c_ts_ns[i], cisd_level

    return None, None


def find_cisd(c_arrs, return_ts_ns, direction, max_bars, cisd_mode):
    """
    Uses searchsorted to find the integer index — no df.loc[].
    Returns (fired_ts_ns, cisd_level) or (None, None).
    max_bars=None means no limit — scan to end of available data (session end).
    """
    start_idx = int(np.searchsorted(c_arrs['ts_ns'], return_ts_ns, side='left'))
    if start_idx >= len(c_arrs['ts_ns']):
        return None, None
    if max_bars is None:
        # Cap at 16:00 ET same day to prevent cross-session CISD
        # Use hr array: session ends when hour >= 16 on the same trade_date
        start_date = c_arrs['trade_date'][start_idx]
        day_end = start_idx
        while day_end < len(c_arrs['ts_ns']):
            if c_arrs['trade_date'][day_end] != start_date:
                break
            if c_arrs['hr'][day_end] >= 16:
                day_end += 1  # include 16:00 bar itself
                break
            day_end += 1
        n_forward = day_end - start_idx
    else:
        n_forward = min(max_bars * 2, 40)
    return _find_cisd(
        c_arrs['open'], c_arrs['close'], c_arrs['ts_ns'],
        start_idx, n_forward, direction
    )


# ── VECTORISED OUTCOME RESOLUTION ────────────────────────────────────────────
def resolve_outcomes_vectorised(m1_arrs, pending):
    """
    Resolve WIN / LOSS / EXPIRED / INVALID for all entries in one pass.
    No Python loops over bars — uses numpy cumulative min/max + argmax.

    pending: list of dicts with keys:
        idx, entry_ts_ns, entry_price, stop_price, target_price, direction
    Returns list of (outcome, r) in the same order as pending.
    """
    ts_ns  = m1_arrs['ts_ns']
    highs  = m1_arrs['high']
    lows   = m1_arrs['low']
    closes = m1_arrs['close']
    N      = len(ts_ns)

    results = []
    for e in pending:
        entry_ts_ns  = e['entry_ts_ns']
        entry_price  = e['entry_price']
        stop_price   = e['stop_price']
        target_price = e['target_price']
        direction    = e['direction']

        risk = abs(entry_price - stop_price)
        if risk < MIN_RISK_PTS or risk > MAX_RISK_PTS:
            results.append(('INVALID', 0.0, 0.0, 0.0))
            continue

        # Target from the manipulation-range projection (2× manip range from sweep extreme)
        target = target_price

        # Start the scan one bar after the entry bar opens
        start = int(np.searchsorted(ts_ns, entry_ts_ns, side='right'))
        end   = min(start + OUTCOME_MAX_BARS, N)

        if start >= N:
            results.append(('EXPIRED', 0.0, 0.0, 0.0))
            continue

        h = highs[start:end]
        l = lows[start:end]

        if direction == 'LONG':
            t_hit = h >= target
            s_hit = l <= stop_price
        else:
            t_hit = l <= target
            s_hit = h >= stop_price

        t_any = t_hit.any()
        s_any = s_hit.any()

        actual_rr = round(abs(target - entry_price) / risk, 2) if risk > 0 else 0.0

        # Determine trade end index for MAE/MFE window
        if not t_any and not s_any:
            last_r = (closes[end - 1] - entry_price) / risk \
                     if direction == 'LONG' \
                     else (entry_price - closes[end - 1]) / risk
            outcome, r_val = 'EXPIRED', round(float(last_r), 2)
            trade_end = end - start
        elif not s_any:
            outcome, r_val = 'WIN', actual_rr
            trade_end = int(np.argmax(t_hit)) + 1
        elif not t_any:
            outcome, r_val = 'LOSS', -1.0
            trade_end = int(np.argmax(s_hit)) + 1
        else:
            t_idx = int(np.argmax(t_hit))
            s_idx = int(np.argmax(s_hit))
            outcome, r_val = ('WIN', actual_rr) if t_idx <= s_idx else ('LOSS', -1.0)
            trade_end = (t_idx if t_idx <= s_idx else s_idx) + 1

        # MAE/MFE as % of entry price over the trade window
        h_w = h[:trade_end]
        l_w = l[:trade_end]
        if direction == 'LONG':
            mae_pct = round(float(max(0.0, entry_price - l_w.min()) / entry_price * 100), 4)
            mfe_pct = round(float(max(0.0, h_w.max() - entry_price) / entry_price * 100), 4)
        else:
            mae_pct = round(float(max(0.0, h_w.max() - entry_price) / entry_price * 100), 4)
            mfe_pct = round(float(max(0.0, entry_price - l_w.min()) / entry_price * 100), 4)

        results.append((outcome, r_val, mae_pct, mfe_pct))

    return results


# ── STRUCTURAL-DYNAMIC OUTCOME RESOLUTION ─────────────────────────────────────
def resolve_outcomes_structural(m1_arrs, pending):
    """
    Structural Dynamic profile:
      - Phase 1: scan for SL (stop_price) or TP1 (target_price = entry ± 1R)
      - If SL first → LOSS, r = -1.0
      - If TP1 first → 90% exits at +1R; runner (10%) holds with BE (entry) stop
      - Phase 2 (runner): scan for BE stop or EOD; runner_exit_r in R units
      - net_r = 0.90 × 1.0 + 0.10 × runner_exit_r

    Returns list of (outcome, net_r, mae_pct, mfe_pct, tp1_hit, runner_exit_r)
    """
    ts_ns  = m1_arrs['ts_ns']
    highs  = m1_arrs['high']
    lows   = m1_arrs['low']
    closes = m1_arrs['close']
    N      = len(ts_ns)

    results = []
    for e in pending:
        entry_ts_ns  = e['entry_ts_ns']
        entry_price  = e['entry_price']
        stop_price   = e['stop_price']
        target_price = e['target_price']   # TP1 = entry ± 1R
        direction    = e['direction']

        risk = abs(entry_price - stop_price)
        if risk < MIN_RISK_PTS or risk > MAX_RISK_PTS:
            results.append(('INVALID', 0.0, 0.0, 0.0, False, 0.0))
            continue

        start = int(np.searchsorted(ts_ns, entry_ts_ns, side='right'))
        end   = min(start + OUTCOME_MAX_BARS, N)

        if start >= N:
            results.append(('EXPIRED', 0.0, 0.0, 0.0, False, 0.0))
            continue

        h = highs[start:end]
        l = lows[start:end]

        if direction == 'LONG':
            tp1_hit_arr = h >= target_price
            sl_hit_arr  = l <= stop_price
        else:
            tp1_hit_arr = l <= target_price
            sl_hit_arr  = h >= stop_price

        tp1_any = tp1_hit_arr.any()
        sl_any  = sl_hit_arr.any()

        tp1_idx = int(np.argmax(tp1_hit_arr)) if tp1_any else len(h)
        sl_idx  = int(np.argmax(sl_hit_arr))  if sl_any  else len(h)

        # ── Outcome determination ─────────────────────────────────────────────
        if not tp1_any and not sl_any:
            # Expired — neither TP1 nor SL hit
            trade_end = len(h)
            last_r = ((closes[end - 1] - entry_price) / risk
                      if direction == 'LONG'
                      else (entry_price - closes[end - 1]) / risk)
            # MAE/MFE over actual trade window
            h_w, l_w = h[:trade_end], l[:trade_end]
            if direction == 'LONG':
                mae_pct = round(float(max(0.0, entry_price - l_w.min()) / entry_price * 100), 4)
                mfe_pct = round(float(max(0.0, h_w.max() - entry_price) / entry_price * 100), 4)
            else:
                mae_pct = round(float(max(0.0, h_w.max() - entry_price) / entry_price * 100), 4)
                mfe_pct = round(float(max(0.0, entry_price - l_w.min()) / entry_price * 100), 4)
            results.append(('EXPIRED', round(float(last_r), 2), mae_pct, mfe_pct, False, 0.0))
            continue

        if sl_any and (not tp1_any or sl_idx < tp1_idx):
            # SL hit before TP1 → full LOSS
            trade_end = sl_idx + 1
            h_w, l_w = h[:trade_end], l[:trade_end]
            if direction == 'LONG':
                mae_pct = round(float(max(0.0, entry_price - l_w.min()) / entry_price * 100), 4)
                mfe_pct = round(float(max(0.0, h_w.max() - entry_price) / entry_price * 100), 4)
            else:
                mae_pct = round(float(max(0.0, h_w.max() - entry_price) / entry_price * 100), 4)
                mfe_pct = round(float(max(0.0, entry_price - l_w.min()) / entry_price * 100), 4)
            results.append(('LOSS', -1.0, mae_pct, mfe_pct, False, 0.0))
            continue

        # ── TP1 hit first — run the runner with BE stop ───────────────────────
        runner_start = tp1_idx + 1
        runner_end   = len(h)
        runner_exit_r = 0.0  # default: runner reaches BE

        if runner_start < runner_end:
            rh = h[runner_start:runner_end]
            rl = l[runner_start:runner_end]
            if direction == 'LONG':
                be_hit = rl <= entry_price
            else:
                be_hit = rh >= entry_price

            if not be_hit.any():
                # Runner survived to EOD — mark to market at last close
                last_close = closes[start + runner_end - 1]
                if direction == 'LONG':
                    runner_exit_r = (last_close - entry_price) / risk
                else:
                    runner_exit_r = (entry_price - last_close) / risk
                runner_exit_r = max(0.0, round(float(runner_exit_r), 3))
            else:
                # Runner stopped at BE — trade ends at BE hit
                runner_end = runner_start + int(np.argmax(be_hit)) + 1

        # MAE/MFE over actual trade window (entry to final exit)
        trade_end = runner_end
        h_w, l_w = h[:trade_end], l[:trade_end]
        if direction == 'LONG':
            mae_pct = round(float(max(0.0, entry_price - l_w.min()) / entry_price * 100), 4)
            mfe_pct = round(float(max(0.0, h_w.max() - entry_price) / entry_price * 100), 4)
        else:
            mae_pct = round(float(max(0.0, h_w.max() - entry_price) / entry_price * 100), 4)
            mfe_pct = round(float(max(0.0, entry_price - l_w.min()) / entry_price * 100), 4)

        net_r = round(0.90 * 1.0 + 0.10 * runner_exit_r, 3)
        results.append(('WIN', net_r, mae_pct, mfe_pct, True, runner_exit_r))

    return results


# ── SPLIT-TP OUTCOME RESOLUTION ───────────────────────────────────────────────
def resolve_outcomes_split_tp(m1_arrs, pending,
                               tp1_size: float = 0.90, tp2_size: float = 0.10,
                               tp2_pct: float = None):
    """
    Split-exit profile:
      - TP1 at target_price (= entry ± entry × ptq_level/100, already set in pending)
        → exits tp1_size (90%) of position; tp1_r = TP1_dist / base_risk (variable per trade)
      - Runner (tp2_size = 10%) holds with BE stop toward TP2
        If tp2_pct is set: TP2 = entry ± entry × tp2_pct/100 (p50 MFE level)
        If tp2_pct is None: runner runs free to EOD (legacy behavior)
      - SL (stop_price) hit before TP1 → full LOSS, r = -1.0
      - net_r = tp1_size × tp1_r + tp2_size × runner_exit_r
    """
    ts_ns  = m1_arrs['ts_ns']
    highs  = m1_arrs['high']
    lows   = m1_arrs['low']
    closes = m1_arrs['close']
    N      = len(ts_ns)

    results = []
    for e in pending:
        entry_ts_ns  = e['entry_ts_ns']
        entry_price  = e['entry_price']
        stop_price   = e['stop_price']
        target_price = e['target_price']   # TP1 = entry ± 1R
        direction    = e['direction']

        base_risk = abs(entry_price - stop_price)
        if base_risk < MIN_RISK_PTS or base_risk > MAX_RISK_PTS:
            results.append(('INVALID', 0.0, 0.0, 0.0, False, 0.0))
            continue

        start = int(np.searchsorted(ts_ns, entry_ts_ns, side='right'))
        end   = min(start + OUTCOME_MAX_BARS, N)

        if start >= N:
            results.append(('EXPIRED', 0.0, 0.0, 0.0, False, 0.0))
            continue

        h = highs[start:end]
        l = lows[start:end]

        if direction == 'LONG':
            tp1_hit_arr = h >= target_price
            sl_hit_arr  = l <= stop_price
        else:
            tp1_hit_arr = l <= target_price
            sl_hit_arr  = h >= stop_price

        tp1_any = tp1_hit_arr.any()
        sl_any  = sl_hit_arr.any()

        tp1_idx = int(np.argmax(tp1_hit_arr)) if tp1_any else len(h)
        sl_idx  = int(np.argmax(sl_hit_arr))  if sl_any  else len(h)

        # ── Outcome determination ─────────────────────────────────────────────
        if not tp1_any and not sl_any:
            trade_end = len(h)
            last_r = ((closes[end - 1] - entry_price) / base_risk
                      if direction == 'LONG'
                      else (entry_price - closes[end - 1]) / base_risk)
            h_w, l_w = h[:trade_end], l[:trade_end]
            if direction == 'LONG':
                mae_pct = round(float(max(0.0, entry_price - l_w.min()) / entry_price * 100), 4)
                mfe_pct = round(float(max(0.0, h_w.max() - entry_price) / entry_price * 100), 4)
            else:
                mae_pct = round(float(max(0.0, h_w.max() - entry_price) / entry_price * 100), 4)
                mfe_pct = round(float(max(0.0, entry_price - l_w.min()) / entry_price * 100), 4)
            results.append(('EXPIRED', round(float(last_r), 2), mae_pct, mfe_pct, False, 0.0))
            continue

        if sl_any and (not tp1_any or sl_idx < tp1_idx):
            trade_end = sl_idx + 1
            h_w, l_w = h[:trade_end], l[:trade_end]
            if direction == 'LONG':
                mae_pct = round(float(max(0.0, entry_price - l_w.min()) / entry_price * 100), 4)
                mfe_pct = round(float(max(0.0, h_w.max() - entry_price) / entry_price * 100), 4)
            else:
                mae_pct = round(float(max(0.0, h_w.max() - entry_price) / entry_price * 100), 4)
                mfe_pct = round(float(max(0.0, entry_price - l_w.min()) / entry_price * 100), 4)
            results.append(('LOSS', -1.0, mae_pct, mfe_pct, False, 0.0))
            continue

        # ── TP1 hit first — 90% off; 10% runner toward TP2 with BE stop ────────
        tp1_dist = abs(target_price - entry_price)
        tp1_r    = tp1_dist / base_risk   # R-multiple locked in at TP1 (variable per trade)

        runner_start  = tp1_idx + 1
        runner_end    = len(h)
        runner_exit_r = 0.0  # default: runner stopped at BE

        # Compute TP2 price if tp2_pct is set
        if tp2_pct is not None:
            tp2_dist = entry_price * tp2_pct / 100.0
            if direction == 'LONG':
                tp2_price = entry_price + tp2_dist
            else:
                tp2_price = entry_price - tp2_dist
        else:
            tp2_price = None

        if runner_start < runner_end:
            rh = h[runner_start:runner_end]
            rl = l[runner_start:runner_end]

            # Check TP2 hit (if set)
            if tp2_price is not None:
                if direction == 'LONG':
                    tp2_hit_arr = rh >= tp2_price
                    be_hit_arr  = rl <= entry_price
                else:
                    tp2_hit_arr = rl <= tp2_price
                    be_hit_arr  = rh >= entry_price

                tp2_any = tp2_hit_arr.any()
                be_any  = be_hit_arr.any()
                tp2_idx = int(np.argmax(tp2_hit_arr)) if tp2_any else len(rh)
                be_idx  = int(np.argmax(be_hit_arr))  if be_any  else len(rh)

                if tp2_any and (not be_any or tp2_idx <= be_idx):
                    # TP2 hit before BE → runner exits at TP2
                    runner_exit_r = round(float(tp2_dist / base_risk), 3)
                    runner_end = runner_start + tp2_idx + 1
                elif be_any:
                    # BE hit before TP2 → runner exits at breakeven
                    runner_exit_r = 0.0
                    runner_end = runner_start + be_idx + 1
                else:
                    # Neither hit → mark to market at EOD
                    last_close = closes[start + runner_end - 1]
                    if direction == 'LONG':
                        runner_exit_r = (last_close - entry_price) / base_risk
                    else:
                        runner_exit_r = (entry_price - last_close) / base_risk
                    runner_exit_r = max(0.0, round(float(runner_exit_r), 3))
            else:
                # Legacy: runner free to EOD with BE stop
                if direction == 'LONG':
                    be_hit_arr = rl <= entry_price
                else:
                    be_hit_arr = rh >= entry_price

                be_any = be_hit_arr.any()

                if not be_any:
                    last_close = closes[start + runner_end - 1]
                    if direction == 'LONG':
                        runner_exit_r = (last_close - entry_price) / base_risk
                    else:
                        runner_exit_r = (entry_price - last_close) / base_risk
                    runner_exit_r = max(0.0, round(float(runner_exit_r), 3))
                else:
                    # BE stop hit
                    runner_end = runner_start + int(np.argmax(be_hit_arr)) + 1

        # MAE/MFE over actual trade window (entry to final exit)
        trade_end = runner_end
        h_w, l_w = h[:trade_end], l[:trade_end]
        if direction == 'LONG':
            mae_pct = round(float(max(0.0, entry_price - l_w.min()) / entry_price * 100), 4)
            mfe_pct = round(float(max(0.0, h_w.max() - entry_price) / entry_price * 100), 4)
        else:
            mae_pct = round(float(max(0.0, h_w.max() - entry_price) / entry_price * 100), 4)
            mfe_pct = round(float(max(0.0, entry_price - l_w.min()) / entry_price * 100), 4)

        net_r = round(tp1_size * tp1_r + tp2_size * runner_exit_r, 3)
        results.append(('WIN', net_r, mae_pct, mfe_pct, True, runner_exit_r))

    return results


# ── FULL DISTRIBUTION STATS HELPER ────────────────────────────────────────────
def _dist_stats(vals_series, n_bins=30):
    """Return full percentile stats + histogram for a pandas Series."""
    vals = vals_series.dropna()
    vals = vals[vals > 0]
    if len(vals) == 0:
        return {}
    counts, edges = np.histogram(vals, bins=n_bins)
    hist = [{'lo': round(float(edges[i]), 4),
             'hi': round(float(edges[i+1]), 4),
             'n':  int(counts[i])} for i in range(len(counts))]
    # mode = midpoint of most-populated bucket
    mode_bucket = max(hist, key=lambda x: x['n'])
    mode_val = round((mode_bucket['lo'] + mode_bucket['hi']) / 2, 4)
    return dict(
        count = int(len(vals)),
        min   = round(float(vals.min()), 4),
        p10   = round(float(vals.quantile(.10)), 4),
        p25   = round(float(vals.quantile(.25)), 4),
        p50   = round(float(vals.quantile(.50)), 4),
        p75   = round(float(vals.quantile(.75)), 4),
        p90   = round(float(vals.quantile(.90)), 4),
        p95   = round(float(vals.quantile(.95)), 4),
        p99   = round(float(vals.quantile(.99)), 4),
        max   = round(float(vals.max()), 4),
        mean  = round(float(vals.mean()), 4),
        std   = round(float(vals.std(ddof=1)), 4) if len(vals) > 1 else 0.0,
        mode  = mode_val,
        hist  = hist,
    )


def _lognorm_fit(vals_np):
    """Return log-normal fit params for a positive numpy array."""
    lv = np.log(vals_np[vals_np > 0])
    if len(lv) < 5:
        return {}
    mu    = float(lv.mean())
    sigma = float(lv.std(ddof=1))
    n     = len(vals_np)
    probs = (np.arange(1, n + 1) - 0.5) / n
    theoretical = np.exp(mu + sigma * _scipy_stats.norm.ppf(probs))
    empirical   = np.sort(vals_np)
    r = float(np.corrcoef(empirical, theoretical)[0, 1]) if len(empirical) > 1 else 0.0
    return dict(
        mu             = round(mu, 4),
        sigma          = round(sigma, 4),
        implied_median = round(float(np.exp(mu)), 4),
        implied_mean   = round(float(np.exp(mu + sigma**2 / 2)), 4),
        implied_mode   = round(float(np.exp(mu - sigma**2)), 4),
        goodness       = round(r, 4),
    )


def _clusters(vals, n):
    """Return 3-tier cluster stats at p33 / p75 breakpoints."""
    p33 = float(vals.quantile(0.33))
    p75 = float(vals.quantile(0.75))
    tiers = [
        (0,   p33,          'Tight',    '0 → p33'),
        (p33, p75,          'Moderate', 'p33 → p75'),
        (p75, float('inf'), 'Wide',     'p75 → max'),
    ]
    out = []
    for lo, hi, label, rng in tiers:
        if hi < float('inf'):
            mask = (vals >= lo) & (vals < hi)
        else:
            mask = vals >= lo
        cv = vals[mask]
        out.append(dict(
            label        = label,
            range        = rng,
            n            = int(len(cv)),
            pct_of_trades= round(len(cv) / max(n, 1) * 100, 1),
            mean         = round(float(cv.mean()), 4)   if len(cv) else 0,
            median       = round(float(cv.median()), 4) if len(cv) else 0,
            max          = round(float(cv.max()), 4)    if len(cv) else 0,
        ))
    return out


_DOW_ORDER  = [1, 2, 3, 4, 5]          # DuckDB dow: 1=Mon … 5=Fri
_DOW_LABELS = ['Mon','Tue','Wed','Thu','Fri']

def _build_excursion_heatmap(wl, col, n_bins=20):
    """Pre-bin MAE or MFE by day-of-week.
    Returns {grid (5×n_bins), val_max, labels, n} — compact for JSON."""
    vals = wl[[col, 'dow']].dropna()
    vals = vals[vals[col] >= 0]
    if len(vals) < 5:
        return {'grid': [], 'val_max': 0.5, 'labels': _DOW_LABELS, 'n': 0}
    val_max = float(vals[col].quantile(0.95)) or 0.5
    grid = [[0] * n_bins for _ in range(5)]
    for row in vals.itertuples():
        dow_idx = _DOW_ORDER.index(int(row.dow)) if int(row.dow) in _DOW_ORDER else None
        if dow_idx is None:
            continue
        xi = min(int(getattr(row, col) / val_max * n_bins), n_bins - 1)
        grid[dow_idx][xi] += 1
    return {'grid': grid, 'val_max': round(val_max, 4), 'labels': _DOW_LABELS, 'n': len(vals)}


def _full_mae_stats(wl, ce=None, n_bins=50):
    """Rich MAE distribution: log-normal fit, clusters, full percentiles, SL sweep."""
    vals = wl['mae_pct'].dropna()
    vals = vals[vals > 0]
    n = len(vals)
    if n < 20:
        return None

    p99_val  = float(vals.quantile(0.99))
    clipped  = vals[vals <= p99_val]
    counts_h, edges_h = np.histogram(clipped, bins=n_bins)
    mode_idx = int(np.argmax(counts_h))
    mode_v   = round((float(edges_h[mode_idx]) + float(edges_h[mode_idx + 1])) / 2, 4)

    pct_levels = [5,10,15,20,25,30,35,40,50,60,65,70,75,80,85,90,95,99]
    percentiles = {f'p{p}': round(float(vals.quantile(p / 100)), 4) for p in pct_levels}

    # SL sweep: for each MAE threshold, compute touch%, P(false stop), P(genuine)
    raw_thresholds = [float(vals.quantile(p / 100)) for p in [5,10,15,20,25,30,35,40,50,60,70,80,90,95]]
    thresholds = sorted({round(t, 4) for t in raw_thresholds})
    sl_sweep = []
    best_opt = None; _opt_fallback = None
    for thr in thresholds:
        touched = wl[wl['mae_pct'] >= thr]
        if len(touched) == 0:
            continue
        nt = len(touched)
        n_win  = int((touched['outcome'] == 'WIN').sum())
        n_loss = int((touched['outcome'] == 'LOSS').sum())
        p_rec = round(n_win  / nt, 4)
        p_ko  = round(n_loss / nt, 4)
        exc   = round(nt / n * 100, 1)
        sl_sweep.append(dict(threshold=thr, exceed_pct=exc, p_recovered=p_rec, p_ko=p_ko))
        # opt_sl: first threshold (highest reach) where p_ko >= 0.70
        # = tightest stop where 70%+ of trades dipping this deep are genuine losses
        if best_opt is None and p_ko >= 0.70:
            best_opt = thr
        if _opt_fallback is None and p_ko >= 0.50:
            _opt_fallback = thr

    if best_opt is None:
        best_opt = _opt_fallback

    return dict(
        n          = n,
        mean       = round(float(vals.mean()), 4),
        median     = round(float(vals.median()), 4),
        std        = round(float(vals.std(ddof=1)), 4),
        mode       = mode_v,
        skewness   = round(float(_scipy_stats.skew(vals)), 3),
        kurtosis   = round(float(_scipy_stats.kurtosis(vals)), 3),
        percentiles= percentiles,
        lognorm    = _lognorm_fit(vals.values),
        clusters   = _clusters(vals, n),
        histogram  = dict(
            edges  = [round(float(e), 4) for e in edges_h],
            counts = [int(c) for c in counts_h],
        ),
        sl_sweep   = sl_sweep,
        opt_sl     = best_opt,
        ce         = ce,
    )


def _full_mfe_stats(wl, n_bins=50):
    """Rich MFE distribution: log-normal fit, clusters, full percentiles, BE triggers, PTQ."""
    vals = wl['mfe_pct'].dropna()
    vals = vals[vals > 0]
    n = len(vals)
    if n < 20:
        return None

    p99_val  = float(vals.quantile(0.99))
    clipped  = vals[vals <= p99_val]
    counts_h, edges_h = np.histogram(clipped, bins=n_bins)
    mode_idx = int(np.argmax(counts_h))
    mode_v   = round((float(edges_h[mode_idx]) + float(edges_h[mode_idx + 1])) / 2, 4)

    pct_levels = [5,10,15,20,25,30,35,40,50,60,65,70,75,80,85,90,95,99]
    percentiles = {f'p{p}': round(float(vals.quantile(p / 100)), 4) for p in pct_levels}

    # Clusters for MFE use Small / Moderate / Large labels
    p33 = float(vals.quantile(0.33))
    p75 = float(vals.quantile(0.75))
    mfe_tiers = [
        (0,   p33,          'Small',    '0 → p33'),
        (p33, p75,          'Moderate', 'p33 → p75'),
        (p75, float('inf'), 'Large',    'p75 → max'),
    ]
    clusters = []
    for lo, hi, label, rng in mfe_tiers:
        mask = (vals >= lo) & (vals < hi) if hi < float('inf') else (vals >= lo)
        cv = vals[mask]
        clusters.append(dict(
            label=label, range=rng, n=int(len(cv)),
            pct_of_trades=round(len(cv) / max(n, 1) * 100, 1),
            mean=round(float(cv.mean()), 4) if len(cv) else 0,
            median=round(float(cv.median()), 4) if len(cv) else 0,
            max=round(float(cv.max()), 4) if len(cv) else 0,
        ))

    # BE trigger analysis
    net_r_col = 'net_r' if 'net_r' in wl.columns else None
    ev_base   = round(float(wl[net_r_col].mean()), 4) if net_r_col else None
    avg_loss  = float(wl.loc[wl[net_r_col] < 0, net_r_col].mean()) if net_r_col and (wl[net_r_col] < 0).any() else -1.0

    raw_trigs = [float(vals.quantile(p / 100)) for p in [5,10,15,20,25,30,35,40,50,60,70,80,90]]
    triggers  = sorted({round(t, 4) for t in raw_trigs})
    be_triggers = []
    ptq_level = None; ptq_reach_rate = None
    _ptq_fallback = None; _ptq_fallback_rr = None
    for thr in triggers:
        reached = wl[wl['mfe_pct'] >= thr]
        if len(reached) == 0:
            continue
        nr = len(reached)
        reach_rate = round(nr / n * 100, 1)
        if net_r_col:
            n_pos = int((reached[net_r_col] > 0).sum())
            n_neg = int((reached[net_r_col] <= 0).sum())
        else:
            n_pos = int((reached['outcome'] == 'WIN').sum())
            n_neg = int((reached['outcome'] == 'LOSS').sum())
        p_pos = round(n_pos / nr, 4)
        n_rescued = n_neg
        ev_delta  = round(n_rescued / n * abs(avg_loss), 4)
        new_ev    = round((ev_base or 0) + ev_delta, 4)
        be_triggers.append(dict(
            trigger_pct = thr,
            reach_rate  = reach_rate,
            p_pos_given = p_pos,
            n_rescued   = n_rescued,
            ev_delta    = ev_delta,
            new_ev      = new_ev,
        ))
        # PTQ: first trigger (highest reach) where p_pos >= 0.70; fallback to 0.50
        if ptq_level is None and p_pos >= 0.70:
            ptq_level = thr; ptq_reach_rate = reach_rate
        if _ptq_fallback is None and p_pos >= 0.50:
            _ptq_fallback = thr; _ptq_fallback_rr = reach_rate

    if ptq_level is None and _ptq_fallback is not None:
        ptq_level = _ptq_fallback; ptq_reach_rate = _ptq_fallback_rr

    return dict(
        n           = n,
        mean        = round(float(vals.mean()), 4),
        median      = round(float(vals.median()), 4),
        std         = round(float(vals.std(ddof=1)), 4),
        mode        = mode_v,
        skewness    = round(float(_scipy_stats.skew(vals)), 3),
        kurtosis    = round(float(_scipy_stats.kurtosis(vals)), 3),
        percentiles = percentiles,
        lognorm     = _lognorm_fit(vals.values),
        clusters    = clusters,
        histogram   = dict(
            edges  = [round(float(e), 4) for e in edges_h],
            counts = [int(c) for c in counts_h],
        ),
        be_triggers    = be_triggers,
        ptq_level      = ptq_level,
        ptq_reach_rate = ptq_reach_rate,
    )


# ── SETUP DETECTOR  (profile-agnostic — no stop/target computed here) ─────────
def detect_setups_base(m1_arrs, s_arrs, c_arrs, model_key, model_cfg,
                       cisd_fast_bars=CISD_FAST_BARS, es_s_arrs=None,
                       es_m1_arrs=None):
    """
    Detect all sweep+CISD setups.  Returns (base_rows, base_pending).

    base_rows    — list of dicts with all metadata *except* stop/target/outcome.
                   Includes `base_risk` = |entry_price − sweep_extreme| which
                   apply_profile_and_resolve uses to scale stop / target.
    base_pending — list of {idx, entry_ts_ns, entry_price, sweep_extreme,
                            base_risk, direction} for every valid entry.
    """
    q1_min    = model_cfg['q1_min']
    min_range = model_cfg['min_range']
    sess_hrs  = model_cfg['session_hrs']
    label     = f"{model_key}_PREV_CISD"

    NS_PER_MIN = np.int64(60_000_000_000)
    q1_ns      = np.int64(q1_min) * NS_PER_MIN
    gap_limit  = np.int64(model_cfg['sweep_tf_min']) * NS_PER_MIN * 3

    s_ts    = s_arrs['ts_ns']
    s_open  = s_arrs['open']
    s_high  = s_arrs['high']
    s_low   = s_arrs['low']
    s_close = s_arrs['close']
    s_n     = len(s_ts)

    # ES data for SMT divergence
    has_smt = es_s_arrs is not None and es_m1_arrs is not None
    if has_smt:
        es_ts     = es_s_arrs['ts_ns']
        es_high   = es_s_arrs['high']
        es_low    = es_s_arrs['low']
        es_m1_ts  = es_m1_arrs['ts_ns']
        es_m1_h   = es_m1_arrs['high']
        es_m1_l   = es_m1_arrs['low']

    m1_ts   = m1_arrs['ts_ns']
    m1_open = m1_arrs['open']
    m1_high = m1_arrs['high']
    m1_low  = m1_arrs['low']
    m1_close= m1_arrs['close']
    m1_hr   = m1_arrs['hr']
    m1_mn   = m1_arrs['mn']
    m1_dow  = m1_arrs['dow']
    m1_date = m1_arrs['trade_date']

    # ── Precompute hourly range lookup: (date, hr) → high-low pts ──────────
    # Groups all 1m bars by (trade_date, hr) and computes max(high)-min(low)
    _hr_range = {}
    _prev_date_hr = (None, None)
    _hr_hi = _hr_lo = 0.0
    for _k in range(len(m1_ts)):
        _dh = (m1_date[_k], m1_hr[_k])
        if _dh != _prev_date_hr:
            if _prev_date_hr[0] is not None:
                _hr_range[_prev_date_hr] = _hr_hi - _hr_lo
            _prev_date_hr = _dh
            _hr_hi = m1_high[_k]
            _hr_lo = m1_low[_k]
        else:
            if m1_high[_k] > _hr_hi: _hr_hi = m1_high[_k]
            if m1_low[_k]  < _hr_lo: _hr_lo = m1_low[_k]
    if _prev_date_hr[0] is not None:
        _hr_range[_prev_date_hr] = _hr_hi - _hr_lo

    print(f"   [{label}] Scanning {s_n:,} sweep bars ... ({len(_hr_range):,} hourly ranges precomputed)")

    base_rows    = []
    base_pending = []

    for i in range(1, s_n):
        curr_ts_ns = s_ts[i]

        if curr_ts_ns - s_ts[i - 1] > gap_limit:
            continue
        refs = {
            'SHORT': (s_high[i - 1], s_high[i - 1] - s_low[i - 1], 1),
            'LONG':  (s_low[i - 1],  s_high[i - 1] - s_low[i - 1], 1),
        }

        q1_start_ns = curr_ts_ns
        q1_end_ns   = curr_ts_ns + q1_ns - NS_PER_MIN
        q1_s = int(np.searchsorted(m1_ts, q1_start_ns, side='left'))
        q1_e = int(np.searchsorted(m1_ts, q1_end_ns,   side='right'))
        if q1_e - q1_s < 3:
            continue

        q1_h  = m1_high[q1_s:q1_e]
        q1_l  = m1_low[q1_s:q1_e]
        q1_c  = m1_close[q1_s:q1_e]
        q1_hr = m1_hr[q1_s:q1_e]
        q1_mn = m1_mn[q1_s:q1_e]
        q1_ts = m1_ts[q1_s:q1_e]

        if sess_hrs:
            hrf = q1_hr + q1_mn / 60.0
            if not np.any((hrf >= sess_hrs[0]) & (hrf < sess_hrs[1])):
                continue

        # ── SMT: find corresponding ES prior candle high/low ────────────────
        # ES and NQ use the same session times, so their HTF candle timestamps
        # should align. Find the ES candle matching the current NQ period start,
        # then use its [i-1] high/low as the ES reference level.
        es_ref_high = None
        es_ref_low  = None
        if has_smt:
            es_idx = int(np.searchsorted(es_ts, curr_ts_ns, side='left'))
            # Verify timestamp match (same period start)
            if es_idx < len(es_ts) and abs(es_ts[es_idx] - curr_ts_ns) < NS_PER_MIN and es_idx > 0:
                es_ref_high = float(es_high[es_idx - 1])
                es_ref_low  = float(es_low[es_idx - 1])

        for direction in ('SHORT', 'LONG'):
            ref_level, ref_range, ref_lookback = refs[direction]

            if direction == 'SHORT':
                swept_mask = q1_h > ref_level
            else:
                swept_mask = q1_l < ref_level

            if not swept_mask.any():
                continue

            pos = int(swept_mask.argmax())

            if direction == 'SHORT':
                sweep_extreme = float(q1_h[swept_mask].max())
            else:
                sweep_extreme = float(q1_l[swept_mask].min())

            sweep_ext = abs(sweep_extreme - ref_level)

            # SMT divergence: did ES also sweep its corresponding level?
            # Check ES 1m bars in the same Q1 window as NQ.
            # Divergence = ES did NOT sweep → stronger signal for NQ trade direction
            smt_divergence = False
            if has_smt and es_ref_high is not None and es_ref_low is not None:
                # Get ES 1m bars for the same Q1 window
                es_q1_s = int(np.searchsorted(es_m1_ts, q1_start_ns, side='left'))
                es_q1_e = int(np.searchsorted(es_m1_ts, q1_end_ns,   side='right'))
                if es_q1_e > es_q1_s:
                    if direction == 'SHORT':
                        # NQ swept above prior high. Did ES also sweep above its prior high?
                        es_also_swept = float(es_m1_h[es_q1_s:es_q1_e].max()) > es_ref_high
                        smt_divergence = not es_also_swept  # Divergence if ES did NOT sweep
                    else:
                        # NQ swept below prior low. Did ES also sweep below its prior low?
                        es_also_swept = float(es_m1_l[es_q1_s:es_q1_e].min()) < es_ref_low
                        smt_divergence = not es_also_swept  # Divergence if ES did NOT sweep

            rejected_by = ''
            if ref_range < min_range:
                rejected_by = 'F1_SMALL_RANGE'
            elif ref_range > 0 and (sweep_ext / ref_range) > SWEEP_MAX_PCT:
                rejected_by = 'F3_SWEEP_TOO_LARGE'

            post_s = pos + 1
            if post_s >= len(q1_ts):
                continue

            if direction == 'SHORT':
                ret_mask = q1_l[post_s:] <= ref_level
            else:
                ret_mask = q1_h[post_s:] >= ref_level

            if not ret_mask.any():
                continue

            ret_rel   = int(ret_mask.argmax())
            ret_idx   = post_s + ret_rel
            ret_close = float(q1_c[ret_idx])
            ret_ts_ns = int(q1_ts[ret_idx])

            if not rejected_by:
                if direction == 'SHORT' and ret_close > ref_level:
                    rejected_by = 'F4_NO_CLOSE_BACK'
                elif direction == 'LONG' and ret_close < ref_level:
                    rejected_by = 'F4_NO_CLOSE_BACK'

            cisd_ts_ns, cisd_level = find_cisd(
                c_arrs, ret_ts_ns, direction, cisd_fast_bars, 'CISD'
            )

            # ── Prior candle filters (optional, evaluated per-trade) ──────────
            #
            # prior_counter_close: the prior sweep-TF candle (s_arrs[i-1], e.g.
            #   10am when 11am sweeps 10am's low) closed in the OPPOSITE
            #   direction to the trade setup. LONG trades (sweep of low) want a
            #   bearish prior close (close < open). SHORT trades (sweep of
            #   high) want a bullish prior close (close > open).
            #
            # prior_engulfing: the prior sweep-TF candle engulfs the candle
            #   before it (s_arrs[i-2]), using extremes (wick-inclusive): the
            #   prior candle's range strictly contains the one before it, i.e.
            #   prior.high >= prev_prev.high AND prior.low <= prev_prev.low.
            _prior_o = float(s_open[i - 1])
            _prior_c = float(s_close[i - 1])
            if direction == 'LONG':
                prior_counter_close = bool(_prior_c < _prior_o)
            else:
                prior_counter_close = bool(_prior_c > _prior_o)
            if i >= 2:
                _prior_h = float(s_high[i - 1])
                _prior_l = float(s_low[i - 1])
                _prev_h  = float(s_high[i - 2])
                _prev_l  = float(s_low[i - 2])
                prior_engulfing = bool(_prior_h >= _prev_h and _prior_l <= _prev_l)
            else:
                prior_engulfing = None  # no prev-prev candle available

            base_row = dict(
                date          = str(s_arrs['trade_date'][i]),
                yr            = int(s_arrs['yr'][i]),
                dow           = int(s_arrs['dow'][i]),
                direction     = direction,
                ref_range     = round(float(ref_range), 2),
                sweep_ext     = round(float(sweep_ext), 2),
                sweep_pct     = round(sweep_ext / ref_range, 3) if ref_range > 0 else 0,
                sweep_extreme = round(float(sweep_extreme), 2),
                sweep_mode    = 'PREV',
                prior_counter_close = prior_counter_close,
                prior_engulfing     = prior_engulfing,
                cisd_mode     = 'CISD',
                ref_lookback  = ref_lookback,
                smt           = smt_divergence,
            )

            if cisd_ts_ns is None:
                base_row.update(
                    hr=int(s_arrs['hr'][i]), session='OTHER',
                    entry_price=None, base_risk=None, cisd_level=None,
                    stop_price=None, target_price=None, risk_pts=None,
                    outcome='SKIP', rejected_by=rejected_by or 'NO_CISD',
                    r=0.0, mae_pct=None, mfe_pct=None,
                    mae_pct_hr=None, mfe_pct_hr=None, hour_range_pts=None,
                )
                base_rows.append(base_row)
                continue

            # ── Entry bar: next CISD-TF candle open after CISD fires ──────────
            cisd_c_idx = int(np.searchsorted(c_arrs['ts_ns'], cisd_ts_ns, side='left'))
            next_c_idx = cisd_c_idx + 1
            if next_c_idx >= len(c_arrs['ts_ns']):
                continue

            entry_ts_ns = int(c_arrs['ts_ns'][next_c_idx])
            entry_price = float(c_arrs['open'][next_c_idx])

            entry_start = int(np.searchsorted(m1_ts, entry_ts_ns, side='left'))
            if entry_start >= len(m1_ts):
                continue

            # base_risk = |entry − sweep_extreme| = 1 full R-unit
            base_risk = abs(entry_price - sweep_extreme)

            # Entry must be on the correct side of the sweep extreme
            if direction == 'LONG'  and entry_price <= sweep_extreme:
                continue
            if direction == 'SHORT' and entry_price >= sweep_extreme:
                continue

            hr_val = int(m1_hr[entry_start])
            mn_val = int(m1_mn[entry_start])
            _entry_date = m1_date[entry_start]
            _hr_rng = _hr_range.get((_entry_date, hr_val), 0.0)

            # CISD Hour-Open Alignment confirmation criterion:
            #   LONG: CISD candle close must be ABOVE the current hour's open
            #   SHORT: CISD candle close must be BELOW the current hour's open
            # "Current hour" = the clock hour containing the CISD candle.
            # Neutral (exact tie) and missing hour_open both resolve to False.
            _cisd_close = float(c_arrs['close'][cisd_c_idx])
            _cisd_hour_open = compute_hour_open_legacy(m1_ts, m1_open, cisd_ts_ns)
            if _cisd_hour_open is None:
                _cisd_aligned = None
            elif direction == 'LONG':
                _cisd_aligned = bool(_cisd_close > _cisd_hour_open)
            else:
                _cisd_aligned = bool(_cisd_close < _cisd_hour_open)

            base_row.update(
                date         = str(_entry_date),
                dow          = int(m1_dow[entry_start]),
                hr           = hr_val,
                mn           = mn_val,
                session      = get_session(hr_val + mn_val / 60.0),
                entry_price  = round(entry_price, 2),
                base_risk    = round(base_risk, 2),
                cisd_level   = round(cisd_level, 2) if cisd_level is not None else None,
                hour_range_pts = round(_hr_rng, 2),
                cisd_close      = round(_cisd_close, 2),
                cisd_hour_open  = round(_cisd_hour_open, 2) if _cisd_hour_open is not None else None,
                cisd_aligned    = _cisd_aligned,
                rejected_by  = rejected_by,
                # profile-dependent fields — filled by apply_profile_and_resolve
                stop_price   = None,
                target_price = None,
                risk_pts     = None,
                outcome      = '',
                r            = 0.0,
                mae_pct      = None,
                mfe_pct      = None,
                mae_pct_hr   = None,
                mfe_pct_hr   = None,
            )
            base_rows.append(base_row)
            base_pending.append(dict(
                idx              = len(base_rows) - 1,
                entry_ts_ns      = entry_ts_ns,
                entry_price      = entry_price,
                sweep_extreme    = float(sweep_extreme),
                base_risk        = base_risk,
                direction        = direction,
                hour_range_pts   = _hr_rng,
            ))

    print(f"      {len(base_pending):,} entries detected across all filters")
    return base_rows, base_pending


# ── PROFILE OUTCOME RESOLVER ──────────────────────────────────────────────────
def apply_profile_and_resolve(base_rows, base_pending, m1_arrs,
                               stop_val, target_val, profile_type='mult',
                               tp2_pct=None, sl_mae_pct=None):
    """
    Compute stop / target for each detected setup and resolve outcomes.

    profile_type='mult'  (sweep-relative):
        risk_pts   = stop_val  × base_risk   (base_risk = |entry − sweep_extreme|)
        LONG:  stop = entry − stop_val×base_risk,  target = entry + target_val×base_risk
        SHORT: stop = entry + stop_val×base_risk,  target = entry − target_val×base_risk

    profile_type='pct'  (fixed % of entry price):
        risk_pts   = entry_price × stop_val  / 100
        LONG:  stop = entry × (1 − stop_val/100),   target = entry × (1 + target_val/100)
        SHORT: stop = entry × (1 + stop_val/100),   target = entry × (1 − target_val/100)
    """
    rows = [dict(r) for r in base_rows]   # shallow copy per profile

    profile_pending = []
    for bp in base_pending:
        idx           = bp['idx']
        entry_price   = bp['entry_price']
        base_risk     = bp['base_risk']
        direction     = bp['direction']

        if profile_type == 'pct':
            stop_dist    = entry_price * stop_val   / 100.0
            target_dist  = entry_price * target_val / 100.0
        elif profile_type == 'split_tp':
            structural_stop = stop_val * base_risk       # 1× base_risk (sweep extreme)
            if sl_mae_pct is not None:
                mae_stop = entry_price * sl_mae_pct / 100.0
                stop_dist = min(structural_stop, mae_stop)
            else:
                stop_dist = structural_stop
            target_dist  = entry_price * target_val / 100.0  # TP1 = fixed % of entry
        else:  # 'mult' / 'structural'
            stop_dist    = stop_val   * base_risk
            target_dist  = target_val * base_risk

        risk_pts = stop_dist

        if direction == 'LONG':
            stop_price   = entry_price - stop_dist
            target_price = entry_price + target_dist
        else:
            stop_price   = entry_price + stop_dist
            target_price = entry_price - target_dist

        rows[idx]['stop_price']   = round(stop_price,   2)
        rows[idx]['target_price'] = round(target_price, 2)
        rows[idx]['risk_pts']     = round(risk_pts,     2)

        if risk_pts < MIN_RISK_PTS:
            rows[idx]['outcome']     = 'INVALID'
            rows[idx]['rejected_by'] = rows[idx]['rejected_by'] or 'INVALID_RISK'
            continue
        if risk_pts > MAX_RISK_PTS:
            rows[idx]['outcome']     = 'INVALID'
            rows[idx]['rejected_by'] = rows[idx]['rejected_by'] or 'RISK_TOO_LARGE'
            continue

        profile_pending.append(dict(
            idx              = idx,
            entry_ts_ns      = bp['entry_ts_ns'],
            entry_price      = entry_price,
            stop_price       = stop_price,
            target_price     = target_price,
            direction        = direction,
            hour_range_pts   = bp.get('hour_range_pts', 0.0),
        ))

    if profile_type in ('structural', 'split_tp'):
        # Initialise split-exit columns so DataFrame always has them
        for r in rows:
            r.setdefault('tp1_hit', False)
            r.setdefault('runner_exit_r', 0.0)
        if profile_type == 'structural':
            outcomes = resolve_outcomes_structural(m1_arrs, profile_pending)
        else:
            outcomes = resolve_outcomes_split_tp(m1_arrs, profile_pending,
                                                tp2_pct=tp2_pct)
        for po, (outcome, r_val, mae_pct, mfe_pct, tp1_hit, runner_exit_r) in zip(profile_pending, outcomes):
            idx = po['idx']
            rows[idx]['outcome']       = outcome
            rows[idx]['r']             = r_val
            rows[idx]['mae_pct']       = mae_pct
            rows[idx]['mfe_pct']       = mfe_pct
            rows[idx]['tp1_hit']       = tp1_hit
            rows[idx]['runner_exit_r'] = runner_exit_r
            hr_rng = po.get('hour_range_pts', 0.0)
            if hr_rng > 0 and mae_pct is not None:
                mae_pts = mae_pct / 100.0 * po['entry_price']
                mfe_pts = mfe_pct / 100.0 * po['entry_price']
                rows[idx]['mae_pct_hr'] = round(mae_pts / hr_rng * 100, 4)
                rows[idx]['mfe_pct_hr'] = round(mfe_pts / hr_rng * 100, 4)
            if outcome == 'INVALID':
                rows[idx]['rejected_by'] = rows[idx]['rejected_by'] or 'INVALID_RISK'
    else:
        outcomes = resolve_outcomes_vectorised(m1_arrs, profile_pending)
        for po, (outcome, r_val, mae_pct, mfe_pct) in zip(profile_pending, outcomes):
            idx = po['idx']
            rows[idx]['outcome']  = outcome
            rows[idx]['r']        = r_val
            rows[idx]['mae_pct']  = mae_pct
            rows[idx]['mfe_pct']  = mfe_pct
            hr_rng = po.get('hour_range_pts', 0.0)
            if hr_rng > 0 and mae_pct is not None:
                mae_pts = mae_pct / 100.0 * po['entry_price']
                mfe_pts = mfe_pct / 100.0 * po['entry_price']
                rows[idx]['mae_pct_hr'] = round(mae_pts / hr_rng * 100, 4)
                rows[idx]['mfe_pct_hr'] = round(mfe_pts / hr_rng * 100, 4)
            if outcome == 'INVALID':
                rows[idx]['rejected_by'] = rows[idx]['rejected_by'] or 'INVALID_RISK'

    df = pd.DataFrame(rows) if rows else pd.DataFrame()
    if not df.empty:
        passed = int((df['rejected_by'] == '').sum())
        wl_n   = int(df['outcome'].isin(['WIN','LOSS']).sum())
        print(f"        [{stop_val}:{target_val} {profile_type}]  {passed:,} filtered setups  "
              f"→  {wl_n:,} resolved (WIN/LOSS)")
    return df


# ── STATISTICS ────────────────────────────────────────────────────────────────
def agg(g):
    """Aggregate a group of trades into summary stats."""
    n = len(g)
    if n == 0:
        return dict(n=0, wins=0, wr=0, ev=0, pf=0, avg_risk_pts=0, avg_rr=0,
                    avg_mae=None, avg_mfe=None, avg_mae_hr=None, avg_mfe_hr=None)
    wins    = int(g['win'].sum())
    wr      = round(wins / n, 4)
    ev      = round(float(g['r'].sum()) / n, 3)
    win_r   = float(g.loc[g['win'] == 1, 'r'].sum())
    loss_r  = float(abs(g.loc[g['win'] == 0, 'r'].sum()))
    pf      = round(win_r / max(loss_r, 0.001), 3)
    avg_rr  = round(win_r / max(wins, 1), 2)
    ar      = round(float(g['risk_pts'].mean()), 1) \
              if 'risk_pts' in g.columns and g['risk_pts'].notna().any() else 0
    _mae = g['mae_pct'].dropna() if 'mae_pct' in g.columns else None
    _mfe = g['mfe_pct'].dropna() if 'mfe_pct' in g.columns else None
    avg_mae = round(float(_mae.mean()), 4) if _mae is not None and len(_mae) > 0 else None
    avg_mfe = round(float(_mfe.mean()), 4) if _mfe is not None and len(_mfe) > 0 else None
    _mae_hr = g['mae_pct_hr'].dropna() if 'mae_pct_hr' in g.columns else None
    _mfe_hr = g['mfe_pct_hr'].dropna() if 'mfe_pct_hr' in g.columns else None
    avg_mae_hr = round(float(_mae_hr.mean()), 4) if _mae_hr is not None and len(_mae_hr) > 0 else None
    avg_mfe_hr = round(float(_mfe_hr.mean()), 4) if _mfe_hr is not None and len(_mfe_hr) > 0 else None
    return dict(n=n, wins=wins, wr=wr, ev=ev, pf=pf, avg_risk_pts=ar, avg_rr=avg_rr,
                avg_mae=avg_mae, avg_mfe=avg_mfe, avg_mae_hr=avg_mae_hr, avg_mfe_hr=avg_mfe_hr)


def build_model_stats(df_raw, trading_days, model_key, model_cfg,
                      stop_mult=1.0, target_mult=2.0, profile_key='1:2',
                      profile_type='mult'):
    df   = df_raw[df_raw['rejected_by'] == ''].copy()
    wl   = df[df['outcome'].isin(['WIN','LOSS'])].copy()
    wl['win'] = (wl['outcome'] == 'WIN').astype(int)

    # ── T-Spot variant classification ─────────────────────────────────────────
    # Classify each trade into one of 6 T-Spot types based on sweep_pct:
    #   ProTrend  (<0.30) — small sweep through midpoint region
    #   Normal    (0.30–0.80) — standard sweep of prior candle extreme
    #   Expansive (>0.80) — large / deep sweep
    # Combined with direction → 6 variants matching the T-Spot indicator study.
    def _classify_tspot(row):
        sp = row['sweep_pct']
        suffix = 'BULL' if row['direction'] == 'LONG' else 'BEAR'
        if sp < 0.30:   return f'ProTrend_{suffix}'
        if sp < 0.80:   return f'Normal_{suffix}'
        return f'Expansive_{suffix}'

    wl['tspot_type'] = wl.apply(_classify_tspot, axis=1)

    by_hour = []
    for (hr, direction), g in wl.groupby(['hr', 'direction']):
        s = agg(g)
        if s['n'] >= 5:
            s.update(hr=int(hr), direction=direction,
                     hr_label=HR_LABELS.get(int(hr), f"{int(hr):02d}:00"))
            by_hour.append(s)

    by_session = []
    for (sess, direction), g in wl.groupby(['session', 'direction']):
        s = agg(g); s.update(session=sess, direction=direction)
        by_session.append(s)

    by_dow = []
    for (dow, direction), g in wl.groupby(['dow', 'direction']):
        s = agg(g)
        if s['n'] >= 5:
            s.update(dow=int(dow), dow_name=DOW_NAMES.get(int(dow), '?'),
                     direction=direction)
            by_dow.append(s)

    heatmap = []
    for (hr, dow), g in wl.groupby(['hr', 'dow']):
        s = agg(g)
        if s['n'] >= 3:
            s.update(hr=int(hr), dow=int(dow), dow_name=DOW_NAMES.get(int(dow), '?'))
            heatmap.append(s)

    combos = []
    for (hr, dow, direction), g in wl.groupby(['hr', 'dow', 'direction']):
        s = agg(g)
        if s['n'] >= 6:
            dn = DOW_NAMES.get(int(dow), '?')
            s.update(hr=int(hr), dow=int(dow), dow_name=dn, direction=direction,
                     label=f"{dn} {int(hr):02d}:00 {direction}")
            combos.append(s)
    combos.sort(key=lambda x: x['ev'], reverse=True)

    by_year = []
    for yr, g in wl.groupby('yr'):
        s = agg(g); s.update(yr=int(yr))
        by_year.append(s)

    target_r = target_mult / stop_mult if stop_mult > 0 else 2.0
    h  = target_r / 2
    r_buckets = [
        ('Loss',                  lambda r: r <  0),
        (f'0–{h:.2g}R',           lambda r: (0 <= r) & (r <  h)),
        (f'{h:.2g}–{target_r:.2g}R', lambda r: (h <= r) & (r <  target_r * 1.05)),
        (f'{target_r:.2g}R ✓',    lambda r: (target_r * 0.95 <= r) & (r <= target_r * 1.15)),
        (f'>{target_r:.2g}R',     lambda r: r > target_r * 1.05),
    ]
    df_r   = df[df['outcome'] != 'INVALID'].copy()
    r_hist = [{'bucket': lbl, 'n': int(fn(df_r['r']).sum())} for lbl, fn in r_buckets]

    dir_summary = []
    for direction, g in wl.groupby('direction'):
        s = agg(g); s.update(direction=direction)
        dir_summary.append(s)

    # SMT divergence breakdown
    smt_summary = []
    if 'smt' in wl.columns:
        for smt_val, g in wl.groupby('smt'):
            s = agg(g); s.update(smt=bool(smt_val))
            smt_summary.append(s)

    mae = wl['mae_pct'].dropna()
    mfe = wl['mfe_pct'].dropna()
    wins_wl2 = wl[wl['win'] == 1]
    loss_wl2 = wl[wl['win'] == 0]
    # Compact legacy fields (kept for meta tile compatibility)
    mae_dist_legacy = dict(
        median = round(float(mae.median()), 4) if len(mae) else 0,
        p80    = round(float(mae.quantile(.80)), 4) if len(mae) else 0,
        p90    = round(float(mae.quantile(.90)), 4) if len(mae) else 0,
        mean   = round(float(mae.mean()), 4) if len(mae) else 0,
        **{f'ext_{k}': v for k, v in _dist_stats(mae).items()},
    )
    mfe_dist_legacy = dict(
        median = round(float(mfe.median()), 4) if len(mfe) else 0,
        p80    = round(float(mfe.quantile(.80)), 4) if len(mfe) else 0,
        p90    = round(float(mfe.quantile(.90)), 4) if len(mfe) else 0,
        mean   = round(float(mfe.mean()), 4) if len(mfe) else 0,
        **{f'ext_{k}': v for k, v in _dist_stats(mfe).items()},
    )
    # Win-only and loss-only MAE/MFE
    mae_wins_dist = _dist_stats(wins_wl2['mae_pct'].dropna())
    mfe_wins_dist = _dist_stats(wins_wl2['mfe_pct'].dropna())
    mae_loss_dist = _dist_stats(loss_wl2['mae_pct'].dropna())
    mfe_loss_dist = _dist_stats(loss_wl2['mfe_pct'].dropna())

    rp = wl['risk_pts'].dropna()
    risk_dist = dict(
        mean   = round(float(rp.mean()),1)          if len(rp) else 0,
        median = round(float(rp.median()),1)        if len(rp) else 0,
        p25    = round(float(rp.quantile(.25)),1)   if len(rp) else 0,
        p75    = round(float(rp.quantile(.75)),1)   if len(rp) else 0,
        p90    = round(float(rp.quantile(.90)),1)   if len(rp) else 0,
        max    = round(float(rp.max()),1)            if len(rp) else 0,
    )

    overall  = agg(wl)
    ny_setup = df[df['session'].isin(['NY1', 'NY2'])]
    spd      = round(len(ny_setup) / max(trading_days, 1), 2)

    filter_impact = compute_filter_impact(df_raw)
    filter_variants = compute_filter_variants(df_raw)

    # ── T-Spot breakdown: stats per variant × DOW × Hour ─────────────────────
    TSPOT_KEYS = ['Normal_BULL','Normal_BEAR','Expansive_BULL',
                  'Expansive_BEAR','ProTrend_BULL','ProTrend_BEAR']
    tspot_breakdown = {}
    for tk in TSPOT_KEYS:
        grp = wl[wl['tspot_type'] == tk]
        if len(grp) == 0:
            tspot_breakdown[tk] = dict(
                overall=dict(n=0, wins=0, wr=0, ev=0, pf=0, avg_risk_pts=0),
                heatmap=[], by_hour=[], by_dow=[], top_combos=[])
            continue

        hm = []
        for (hr, dow), g in grp.groupby(['hr', 'dow']):
            s = agg(g)
            if s['n'] >= 2:
                s.update(hr=int(hr), dow=int(dow), dow_name=DOW_NAMES.get(int(dow), '?'))
                hm.append(s)

        bh = []
        for hr, g in grp.groupby('hr'):
            s = agg(g)
            if s['n'] >= 3:
                s.update(hr=int(hr), hr_label=HR_LABELS.get(int(hr), f'{int(hr):02d}:00'))
                bh.append(s)

        bd = []
        for dow, g in grp.groupby('dow'):
            s = agg(g)
            if s['n'] >= 3:
                s.update(dow=int(dow), dow_name=DOW_NAMES.get(int(dow), '?'))
                bd.append(s)

        tc = []
        for (hr, dow, direction), g in grp.groupby(['hr', 'dow', 'direction']):
            s = agg(g)
            if s['n'] >= 4:
                dn = DOW_NAMES.get(int(dow), '?')
                s.update(hr=int(hr), dow=int(dow), dow_name=dn, direction=direction,
                         label=f"{dn} {int(hr):02d}:00 {direction}")
                tc.append(s)
        tc.sort(key=lambda x: x['ev'], reverse=True)

        tspot_breakdown[tk] = dict(
            overall=agg(grp), heatmap=hm, by_hour=bh, by_dow=bd, top_combos=tc[:10])

    # All resolved trades (capped at 500 for JSON size; sub-TF slices are uncapped)
    recent_cols = ['date','direction','hr','mn','session','dow','entry_price',
                   'sweep_extreme','target_price','risk_pts','r','outcome',
                   'mae_pct','mfe_pct','mae_pct_hr','mfe_pct_hr','hour_range_pts','smt',
                   'cisd_close','cisd_hour_open','cisd_aligned',
                   'prior_counter_close','prior_engulfing']
    recent_rows = (wl[recent_cols]
                   .sort_values('date', ascending=False)
                   .copy())
    recent_rows['dow_name'] = recent_rows['dow'].map(lambda d: DOW_NAMES.get(int(d), '?'))
    recent_rows['classification'] = recent_rows['date'].astype(str).str[:10].map(
        lambda d: DATE_CLASSIFICATION.get(d, 'Unclassified'))
    recent_trades = recent_rows.to_dict('records')
    for t in recent_trades:
        t['date'] = str(t['date'])[:10]
        t['dow']  = int(t['dow'])
        t['hr']   = int(t['hr'])
        t['mn']   = int(t['mn'])
        for k in ('entry_price','sweep_extreme','target_price','risk_pts','r'):
            if t[k] is not None:
                t[k] = round(float(t[k]), 2)
        for k in ('mae_pct','mfe_pct','mae_pct_hr','mfe_pct_hr','hour_range_pts'):
            if k in t and t[k] is not None:
                t[k] = round(float(t[k]), 4)

    # ── Risk stats for hero tiles ─────────────────────────────────────────────
    wl_sorted   = wl.sort_values('date')
    outcomes_seq = wl_sorted['win'].tolist()
    def _max_consec(seq, val):
        mx = cur = 0
        for v in seq:
            cur = cur + 1 if v == val else 0
            mx  = max(mx, cur)
        return mx
    rs_max_cw = _max_consec(outcomes_seq, 1)
    rs_max_cl = _max_consec(outcomes_seq, 0)

    rr_actual   = round(target_mult / stop_mult, 4) if stop_mult > 0 else 2.0
    wins_df     = wl_sorted[wl_sorted['win'] == 1]
    losses_df   = wl_sorted[wl_sorted['win'] == 0]
    avg_win_r   = round(float(wins_df['r'].mean()), 4)   if len(wins_df)   else rr_actual
    avg_loss_r  = round(float(losses_df['r'].mean()), 4) if len(losses_df) else -1.0
    avg_win_usd  = round(avg_win_r  * RISK_PER_TRADE, 2)
    avg_loss_usd = round(avg_loss_r * RISK_PER_TRADE, 2)

    # sl_pct = avg (risk_pts / entry_price * 100); tp_pct = sl_pct * rr_actual
    entry_col = wl_sorted['entry_price'].replace(0, np.nan).dropna()
    rp_col    = wl_sorted.loc[entry_col.index, 'risk_pts']
    if len(entry_col):
        sl_pct_val = round(float((rp_col / entry_col * 100).mean()), 4)
        tp_pct_val = round(sl_pct_val * rr_actual, 4)
    else:
        sl_pct_val = None
        tp_pct_val = None

    eq = float(ACCOUNT_SIZE)
    peak_eq = eq
    min_eq = eq
    max_dd_abs = 0.0
    max_dd_usd = 0.0
    # Daily P&L for Sharpe: accumulate by date
    daily_pnl: dict = {}
    for _, row in wl_sorted.iterrows():
        r_val = row['r']
        if r_val is not None and not np.isnan(r_val):
            trade_pnl = float(r_val) * RISK_PER_TRADE
            eq += trade_pnl
            if eq < min_eq:
                min_eq = eq
            if eq > peak_eq:
                peak_eq = eq
            dd = (peak_eq - eq) / peak_eq if peak_eq > 0 else 0.0
            if dd > max_dd_abs:
                max_dd_abs = dd
                max_dd_usd = peak_eq - eq
            # date bucket for Sharpe
            try:
                trade_date = str(row['date'])[:10]
                if trade_date:
                    daily_pnl[trade_date] = daily_pnl.get(trade_date, 0.0) + trade_pnl
            except Exception:
                pass
    min_eq = round(min_eq, 2)
    max_dd_pct = round(max_dd_abs * 100, 2)
    total_pnl_usd = round(eq - ACCOUNT_SIZE, 2)
    blown  = min_eq <= 0.0

    # Annualised Sharpe (daily returns, 252 trading days)
    if len(daily_pnl) > 1:
        dpnl_arr = np.array(list(daily_pnl.values()))
        sharpe_val = round(float(dpnl_arr.mean() / dpnl_arr.std(ddof=1) * np.sqrt(252)), 2) \
                     if dpnl_arr.std(ddof=1) > 0 else None
    else:
        sharpe_val = None

    risk_stats = {
        'account_size':     ACCOUNT_SIZE,
        'risk_per_trade':   RISK_PER_TRADE,
        'trades':           overall['n'],
        'wins':             overall['wins'],
        'losses':           overall['n'] - overall['wins'],
        'be_count':         0,
        'avg_win_usd':      avg_win_usd,
        'avg_loss_usd':     avg_loss_usd,
        'blown':            blown,
        'min_equity_usd':   min_eq,
        'max_consec_wins':  rs_max_cw,
        'max_consec_losses': rs_max_cl,
        'sl_pct':           sl_pct_val,
        'tp_pct':           tp_pct_val,
        'max_dd_pct':       max_dd_pct,
        'max_dd_usd':       round(max_dd_usd, 2),
        'total_pnl_usd':    total_pnl_usd,
        'sharpe':           sharpe_val,
    }

    # CE — Combined Edge: EV_R × PF
    # EV_R = EV_dollar / risk_per_trade; CE = EV_R × PF
    _pf = overall['pf']
    _n_wins = risk_stats['wins']
    _n_losses = risk_stats['losses']
    _n_total = risk_stats['trades']
    _ev_dollar = (avg_win_usd * _n_wins + avg_loss_usd * _n_losses) / _n_total if _n_total > 0 else 0
    _ev_r = _ev_dollar / RISK_PER_TRADE if RISK_PER_TRADE > 0 else 0
    ce = round(_ev_r * _pf, 6) if _pf and _n_total > 0 else None
    risk_stats['ce'] = ce

    # Rich MAE / MFE distribution studies — split by outcome for deeper analysis
    # All trades (combined)
    rich_mae = _full_mae_stats(wl, ce=ce)
    rich_mfe = _full_mfe_stats(wl)
    # Winners only — MAE shows optimal stop (how far winners dip before winning)
    #              — MFE shows where winners peak (optimal TP / PTQ)
    wins_only = wl[wl['win'] == 1].copy()
    rich_mae_wins = _full_mae_stats(wins_only, ce=ce) if len(wins_only) > 10 else None
    rich_mfe_wins = _full_mfe_stats(wins_only) if len(wins_only) > 10 else None
    # Losers only — MAE shows stop confirmation (all hit SL, validates stop)
    #             — MFE shows rescue opportunity (how far losers went in your favor before reversing)
    losses_only = wl[wl['win'] == 0].copy()
    rich_mae_losses = _full_mae_stats(losses_only, ce=ce) if len(losses_only) > 10 else None
    rich_mfe_losses = _full_mfe_stats(losses_only) if len(losses_only) > 10 else None

    # Bell curve of actual MAE distribution
    mae_vals = wl_sorted['mae_pct'].dropna()
    mae_vals = mae_vals[mae_vals > 0]
    if len(mae_vals) > 1 and mae_vals.std() > 0:
        mae_mu = float(mae_vals.mean())
        mae_sd = float(mae_vals.std(ddof=1))
        mae_np = mae_vals.values
        risk_stats['mae_bell'] = {
            'mean':      round(mae_mu, 4),
            'std':       round(mae_sd, 4),
            'plus_0_5s': round(mae_mu + 0.5 * mae_sd, 4),
            'plus_1s':   round(mae_mu + mae_sd, 4),
            'plus_1_5s': round(mae_mu + 1.5 * mae_sd, 4),
            'plus_2s':   round(mae_mu + 2.0 * mae_sd, 4),
            'cov_mean':  round(float(np.mean(mae_np <= mae_mu)) * 100, 1),
            'cov_0_5s':  round(float(np.mean(mae_np <= mae_mu + 0.5*mae_sd)) * 100, 1),
            'cov_1s':    round(float(np.mean(mae_np <= mae_mu + mae_sd)) * 100, 1),
            'cov_1_5s':  round(float(np.mean(mae_np <= mae_mu + 1.5*mae_sd)) * 100, 1),
            'cov_2s':    round(float(np.mean(mae_np <= mae_mu + 2.0*mae_sd)) * 100, 1),
        }
    else:
        risk_stats['mae_bell'] = None

    full_key = f"{model_key}_PREV_CISD"
    # Breakeven WR:
    #   structural:  wr × 0.9R = (1-wr) × 1R  →  wr = 1/1.9 ≈ 0.5263
    #     (min win = 0.90×1R + 0.10×0R = 0.9R when runner exits at BE)
    #   split_tp:    wr × 0.9R = (1-wr) × 1R  →  wr = 1/1.9 ≈ 0.5263
    if profile_type == 'structural':
        be_wr = round(1.0 / 1.9, 4)
    elif profile_type == 'split_tp':
        be_wr = round(1.0 / 1.9, 4)
    else:
        be_wr = round(stop_mult / (stop_mult + target_mult), 4)

    # ── Structural-dynamic / split-tp extra stats ──────────────────────────────
    structural_stats = None
    if profile_type in ('structural', 'split_tp') and 'tp1_hit' in wl.columns:
        tp1_rate   = round(float(wl['tp1_hit'].mean()), 4)
        tp1_trades = wl[wl['tp1_hit'] == True]
        runner_col = tp1_trades['runner_exit_r'].dropna()
        runner_ran = runner_col[runner_col > 0]
        structural_stats = {
            'tp1_hit_rate':        tp1_rate,
            'runner_ran_further_rate': round(float(len(runner_ran) / max(len(runner_col), 1)), 4),
            'runner_stats':        _dist_stats(runner_col),
            'runner_ran_stats':    _dist_stats(runner_ran),
        }

    return {
        'meta': {
            'model_key':          model_key,
            'full_key':           full_key,
            'profile_key':        profile_key,
            'profile_type':       profile_type,
            'model_label':        model_cfg['label'],
            'sweep_mode':         'PREV',
            'cisd_mode':          'CISD',
            'cisd_mode_label':    'Body CISD — close through open of last opposing run',
            'instrument':         TABLE.split('_')[0].upper(),
            'date_range':         f"{str(df['date'].min())[:10]} – {str(df['date'].max())[:10]}"
                                  if len(df) else '—',
            'trading_days':       trading_days,
            'total_raw':          len(df_raw),
            'total_wl':           overall['n'],
            'total_expired':      int((df['outcome'] == 'EXPIRED').sum()),
            'win_rate':           overall['wr'],
            'ev_per_trade':       overall['ev'],
            'profit_factor':      overall['pf'],
            'avg_risk_pts':       overall['avg_risk_pts'],
            'setups_per_day_ny':  spd,
            'risk_breakeven_wr':  be_wr,
            'rr_target':          rr_actual,
            'stop_mult':          stop_mult,
            'target_mult':        target_mult,
            'tp1_pct':            round(target_mult, 4) if profile_type == 'split_tp' else None,
            **{f'risk_{k}': v for k, v in risk_dist.items()},
            **{f'mae_{k}':  v for k, v in mae_dist_legacy.items()},
            **{f'mfe_{k}':  v for k, v in mfe_dist_legacy.items()},
        },
        'by_hour':       by_hour,
        'by_session':    by_session,
        'by_dow':        by_dow,
        'heatmap':       heatmap,
        'top_combos':    combos[:15],
        'worst_combos':  sorted(combos, key=lambda x: x['ev'])[:5],
        'by_year':       by_year,
        'r_hist':        r_hist,
        'dir_summary':   dir_summary,
        'smt_summary':   smt_summary,
        'risk_dist':     risk_dist,
        'filter_impact': filter_impact,
        'filter_variants': filter_variants,
        'lookback_dist':    [],
        'mae_dist':         mae_dist_legacy,
        'mfe_dist':         mfe_dist_legacy,
        'rich_mae':         rich_mae,
        'rich_mfe':         rich_mfe,
        'rich_mae_wins':    rich_mae_wins,
        'rich_mfe_wins':    rich_mfe_wins,
        'rich_mae_losses':  rich_mae_losses,
        'rich_mfe_losses':  rich_mfe_losses,
        'mae_wins_dist':    mae_wins_dist,
        'mfe_wins_dist':    mfe_wins_dist,
        'mae_loss_dist':    mae_loss_dist,
        'mfe_loss_dist':    mfe_loss_dist,
        'tspot_breakdown':  tspot_breakdown,
        'mae_heatmap':      _build_excursion_heatmap(wl, 'mae_pct'),
        'mfe_heatmap':      _build_excursion_heatmap(wl, 'mfe_pct'),
        'recent_trades':    recent_trades,
        'risk_stats':       risk_stats,
        'structural_stats': structural_stats,
        'by_classification': _compute_by_classification(wl_sorted),
        'by_tf':            _compute_by_tf(wl, wl_sorted, stop_mult, target_mult,
                                           sl_pct_val, tp_pct_val, agg,
                                           HR_LABELS, DOW_NAMES),
    }


def _compute_by_classification(wl_sorted: 'pd.DataFrame') -> dict:
    """Compute WR / PF / PnL / Sharpe / MaxDD per day classification."""
    if not DATE_CLASSIFICATION or wl_sorted is None or len(wl_sorted) == 0:
        return {}
    cls_order = ['DWP', 'DNP', 'R1', 'R2', 'Unclassified']
    result = {}
    for cls in cls_order:
        dates = {d for d, c in DATE_CLASSIFICATION.items() if c == cls}
        sub = wl_sorted[wl_sorted['date'].astype(str).str[:10].isin(dates)].copy()
        n = len(sub)
        if n == 0:
            result[cls] = None
            continue
        wins   = int((sub['win'] == 1).sum())
        losses = n - wins
        wr     = round(wins / n * 100, 2)
        gross_win  = float(sub.loc[sub['win'] == 1, 'r'].sum()) * RISK_PER_TRADE
        gross_loss = abs(float(sub.loc[sub['win'] == 0, 'r'].sum())) * RISK_PER_TRADE
        pf     = round(gross_win / gross_loss, 3) if gross_loss > 0 else 0.0
        # Equity curve
        eq = float(ACCOUNT_SIZE)
        peak_eq = eq
        max_dd = 0.0
        daily_pnl: dict = {}
        for _, row in sub.iterrows():
            r_val = row['r']
            if r_val is None or np.isnan(float(r_val)):
                continue
            trade_pnl = float(r_val) * RISK_PER_TRADE
            eq += trade_pnl
            if eq > peak_eq:
                peak_eq = eq
            dd = (peak_eq - eq) / peak_eq if peak_eq > 0 else 0.0
            if dd > max_dd:
                max_dd = dd
            try:
                td = str(row['date'])[:10]
                daily_pnl[td] = daily_pnl.get(td, 0.0) + trade_pnl
            except Exception:
                pass
        total_pnl = round(eq - ACCOUNT_SIZE, 0)
        max_dd_pct = round(max_dd * 100, 2)
        blown = eq <= 0
        if len(daily_pnl) > 1:
            dpnl = np.array(list(daily_pnl.values()))
            sharpe = round(float(dpnl.mean() / dpnl.std(ddof=1) * np.sqrt(252)), 2) \
                     if dpnl.std(ddof=1) > 0 else None
        else:
            sharpe = None
        result[cls] = {
            'trades':    n,
            'wins':      wins,
            'losses':    losses,
            'wr':        wr,
            'pf':        pf,
            'pnl':       total_pnl,
            'sharpe':    sharpe,
            'max_dd':    max_dd_pct,
            'blown':     blown,
        }
    return result


def _build_slice_stats(wl_sub, stop_mult, target_mult, agg_fn, hr_labels,
                       dow_names, date_classification=None):
    """Build compact stats for a sub-timeframe slice. Used by _compute_by_tf and
    per-TF split profile resolution."""
    if len(wl_sub) == 0:
        return None
    wl_sub = wl_sub.copy()
    if 'win' not in wl_sub.columns:
        wl_sub['win'] = (wl_sub['outcome'] == 'WIN').astype(int)
    n     = len(wl_sub)
    wins  = int((wl_sub['win'] == 1).sum())
    wr    = round(wins / n, 4)
    ev    = round(float(wl_sub['r'].sum()) / n, 3)
    win_r = float(wl_sub.loc[wl_sub['win'] == 1, 'r'].sum())
    los_r = float(abs(wl_sub.loc[wl_sub['win'] == 0, 'r'].sum()))
    pf    = round(win_r / max(los_r, 0.001), 3)
    date_range = f"{str(wl_sub['date'].min())[:10]} – {str(wl_sub['date'].max())[:10]}"
    sl_pct_val = None; tp_pct_val = None

    # Equity / risk stats
    ws_sorted = wl_sub.sort_values('date')
    eq = float(ACCOUNT_SIZE); peak_eq = eq; max_dd = 0.0; max_dd_usd = 0.0; min_eq = eq
    daily_pnl: dict = {}
    def _mc(seq, val):
        mx = cur = 0
        for v in seq:
            cur = cur + 1 if v == val else 0; mx = max(mx, cur)
        return mx
    for _, row in ws_sorted.iterrows():
        r_val = row['r']
        if r_val is None or np.isnan(float(r_val)): continue
        tp = float(r_val) * RISK_PER_TRADE
        eq += tp
        if eq < min_eq: min_eq = eq
        if eq > peak_eq: peak_eq = eq
        dd = (peak_eq - eq) / peak_eq if peak_eq > 0 else 0.0
        if dd > max_dd:
            max_dd = dd
            max_dd_usd = peak_eq - eq
        try:
            td = str(row['date'])[:10]
            daily_pnl[td] = daily_pnl.get(td, 0.0) + tp
        except Exception:
            pass
    outcomes_seq = ws_sorted['win'].tolist()
    mcw = _mc(outcomes_seq, 1); mcl = _mc(outcomes_seq, 0)
    total_pnl = round(eq - ACCOUNT_SIZE, 2)
    max_dd_pct = round(max_dd * 100, 2)
    blown = eq <= 0.0
    if len(daily_pnl) > 1:
        dpnl = np.array(list(daily_pnl.values()))
        sharpe = round(float(dpnl.mean() / dpnl.std(ddof=1) * np.sqrt(252)), 2) \
                 if dpnl.std(ddof=1) > 0 else None
    else:
        sharpe = None
    ce = round(ev * pf, 6) if pf and n > 0 else None
    # by_hour
    bh = []
    for (hr, direction), g in wl_sub.groupby(['hr', 'direction']):
        s = agg_fn(g)
        if s['n'] >= 3:
            s.update(hr=int(hr), hr_label=hr_labels.get(int(hr), f'{int(hr):02d}:00'))
            bh.append(s)
    # by_session
    def get_sess(hr):
        h = float(hr)
        if 8.5 <= h < 11.5: return 'NY1'
        if 11.5 <= h < 16.0: return 'NY2'
        return 'Other'
    wl_sub2 = wl_sub.copy()
    wl_sub2['session2'] = wl_sub2['hr'].apply(get_sess)
    bs = []
    for (sess, direction), g in wl_sub2.groupby(['session2', 'direction']):
        if sess == 'Other': continue
        s = agg_fn(g); s.update(session=sess, direction=direction); bs.append(s)
    # by_dow
    bd = []
    for (dow, direction), g in wl_sub.groupby(['dow', 'direction']):
        s = agg_fn(g)
        if s['n'] >= 3:
            s.update(dow=int(dow), dow_name=dow_names.get(int(dow), '?'))
            bd.append(s)
    # dir_summary
    ds = []
    for direction, g in wl_sub.groupby('direction'):
        s = agg_fn(g); s['direction'] = direction; ds.append(s)
    # by_year
    wl_sub['year'] = wl_sub['date'].astype(str).str[:4].astype(int)
    by_yr = []
    for yr, g in wl_sub.groupby('year'):
        s = agg_fn(g); s['yr'] = int(yr); by_yr.append(s)
    # r_hist
    rr_actual = round(target_mult / stop_mult, 4) if stop_mult > 0 else 2.0
    r_hist = [
        {'bucket': f'-1R (loss)', 'n': n - wins, 'fill': 'loss'},
        {'bucket': f'{rr_actual}R (target)', 'n': wins, 'fill': 'win'},
    ]
    # recent trades
    recent_cols = ['date','direction','hr','mn','session','dow','entry_price',
                   'sweep_extreme','target_price','risk_pts','r','outcome',
                   'mae_pct','mfe_pct','mae_pct_hr','mfe_pct_hr','hour_range_pts','smt',
                   'cisd_close','cisd_hour_open','cisd_aligned',
                   'prior_counter_close','prior_engulfing']
    available = [c for c in recent_cols if c in wl_sub.columns]
    rt = wl_sub[available].sort_values('date', ascending=False).copy()
    rt['dow_name'] = rt['dow'].map(lambda d: dow_names.get(int(d), '?'))
    _dc = date_classification or DATE_CLASSIFICATION
    rt['classification'] = rt['date'].astype(str).str[:10].map(
        lambda d: _dc.get(d, 'Unclassified'))
    recent_trades = rt.to_dict('records')
    for t in recent_trades:
        t['date'] = str(t['date'])[:10]
        for k in ['dow','hr','mn']:
            if k in t: t[k] = int(t[k])
        for k in ['entry_price','sweep_extreme','target_price','risk_pts','r']:
            if k in t and t[k] is not None:
                t[k] = round(float(t[k]), 2)
        for k in ['mae_pct','mfe_pct','mae_pct_hr','mfe_pct_hr','hour_range_pts']:
            if k in t and t[k] is not None:
                t[k] = round(float(t[k]), 4)

    return {
        'meta': {
            'total_wl': n, 'win_rate': wr, 'ev_per_trade': ev,
            'profit_factor': pf, 'date_range': date_range,
            'rr_target': rr_actual,
        },
        'risk_stats': {
            'account_size': ACCOUNT_SIZE, 'risk_per_trade': RISK_PER_TRADE,
            'trades': n, 'wins': wins, 'losses': n - wins, 'be_count': 0,
            'blown': blown, 'min_equity_usd': round(min_eq, 2),
            'max_dd_usd': round(max_dd_usd, 2),
            'max_consec_wins': mcw, 'max_consec_losses': mcl,
            'sl_pct': sl_pct_val, 'tp_pct': tp_pct_val,
            'max_dd_pct': max_dd_pct, 'total_pnl_usd': total_pnl,
            'sharpe': sharpe, 'ce': ce,
        },
        'by_hour':         bh,
        'by_session':      bs,
        'by_dow':          bd,
        'dir_summary':     ds,
        'by_year':         by_yr,
        'r_hist':          r_hist,
        'by_classification': _compute_by_classification(ws_sorted),
        'mae_heatmap':       _build_excursion_heatmap(wl_sub, 'mae_pct'),
        'mfe_heatmap':       _build_excursion_heatmap(wl_sub, 'mfe_pct'),
        'recent_trades':   recent_trades,
    }


def _compute_by_tf(wl_full, wl_sorted_full, stop_mult, target_mult,
                   sl_pct_val, tp_pct_val, agg_fn, hr_labels, dow_names) -> dict:
    """Compute compact hero+chart stats for each sub-timeframe slice."""
    from datetime import date, timedelta
    import pandas as pd

    if wl_full is None or len(wl_full) == 0:
        return {}

    # Determine reference date from data (latest trade date)
    max_date_str = str(wl_sorted_full['date'].max())[:10]
    try:
        ref = date.fromisoformat(max_date_str)
    except Exception:
        return {}

    TF_CUTOFFS = {
        '2y': ref - timedelta(days=730),
        '1y': ref - timedelta(days=365),
        '6m': ref - timedelta(days=182),
        '3m': ref - timedelta(days=91),
        '1m': ref - timedelta(days=30),
    }

    result = {}
    dates_str = wl_full['date'].astype(str).str[:10]
    tf_keys = list(TF_CUTOFFS.items())
    for idx, (tf_key, cutoff) in enumerate(tf_keys, 1):
        print(f"        by_tf [{idx}/{len(tf_keys)}] {tf_key} ...", flush=True)
        mask = dates_str >= cutoff.isoformat()
        sub  = wl_full[mask]
        result[tf_key] = _build_slice_stats(
            sub, stop_mult, target_mult, agg_fn, hr_labels, dow_names)
        print(f"           {len(sub):,} trades  ✓", flush=True)

    return result


def compute_filter_impact(df_all):
    FILTER_ORDER  = ['F1_SMALL_RANGE','F3_SWEEP_TOO_LARGE',
                     'F4_NO_CLOSE_BACK','NO_CISD','INVALID_RISK','RISK_TOO_LARGE']
    FILTER_LABELS_MAP = {
        'F1_SMALL_RANGE':    'F1: Prior Range Floor',
        'F3_SWEEP_TOO_LARGE':'F3: Sweep Max Cap',
        'F4_NO_CLOSE_BACK':  'F4: Close-Back Required',
        'NO_CISD':           'No CISD Formed',
        'INVALID_RISK':      'Invalid Risk (< min)',
        'RISK_TOO_LARGE':    'Risk Too Large (> $225 MNQ)',
    }
    def ev_of(df):
        wl = df[df['outcome'].isin(['WIN','LOSS'])].copy()
        if len(wl) == 0: return 0, 0, 0, 0
        wl['win'] = (wl['outcome'] == 'WIN').astype(int)
        wins  = int(wl['win'].sum())
        wr    = wins / len(wl)
        ev    = float(wl['r'].sum()) / len(wl)
        win_r = float(wl.loc[wl['win'] == 1, 'r'].sum())
        pf    = win_r / max(float(abs(wl.loc[wl['win'] == 0, 'r'].sum())), 0.001)
        return round(wr,4), round(ev,3), round(pf,3), len(wl)

    base = df_all[~df_all['outcome'].isin(['SKIP','INVALID'])].copy()
    wr0, ev0, pf0, n0 = ev_of(base)
    results = [dict(label='Baseline (unfiltered)', n=n0, wr=wr0, ev=ev0,
                    pf=pf0, removed=0)]
    remaining = base.copy()
    for fcode in FILTER_ORDER:
        removed = remaining[remaining['rejected_by'] == fcode]
        if len(removed) == 0: continue
        remaining = remaining[remaining['rejected_by'] != fcode]
        wr, ev_v, pf, n = ev_of(remaining)
        results.append(dict(label=FILTER_LABELS_MAP.get(fcode, fcode),
                            filter_code=fcode, n=n, wr=wr, ev=ev_v, pf=pf,
                            removed=len(removed)))
    return results


def compute_filter_variants(df_all):
    """Analyze each filter's individual contribution to model performance.

    Returns dict with:
      - individual_removal: what happens when you remove just ONE filter (keep all others)
      - individual_only: what happens when you apply ONLY this filter (remove everything else)
      - cumulative_additive: adding filters one at a time in optimal order
      - best_combo: the filter combination that maximizes EV
    """
    FILTERS = ['F1_SMALL_RANGE', 'F3_SWEEP_TOO_LARGE', 'F4_NO_CLOSE_BACK',
               'SMT', 'HOUR_ALIGNED', 'PRIOR_COUNTER_CLOSE', 'PRIOR_ENGULFING']
    FILTER_LABELS = {
        'F1_SMALL_RANGE':    'F1: Prior Range Floor',
        'F3_SWEEP_TOO_LARGE':'F3: Sweep Max Cap',
        'F4_NO_CLOSE_BACK':  'F4: Close-Back Required',
        'SMT':               'SMT Divergence',
        'HOUR_ALIGNED':      'Hour-Open Aligned',
        'PRIOR_COUNTER_CLOSE':'Prior Counter-Close',
        'PRIOR_ENGULFING':   'Prior Engulfing',
    }
    # Positive filters (off-by-default, additive): these don't use rejected_by
    # codes — they gate on per-trade boolean columns.
    POSITIVE_FILTERS = {'SMT', 'HOUR_ALIGNED', 'PRIOR_COUNTER_CLOSE', 'PRIOR_ENGULFING'}

    def stats_of(df):
        wl = df[df['outcome'].isin(['WIN', 'LOSS'])].copy()
        if len(wl) == 0:
            return dict(n=0, wr=0, ev=0, pf=0, spd=0,
                        avg_risk=0, max_dd_pct=0, sharpe=None)
        wl['win'] = (wl['outcome'] == 'WIN').astype(int)
        n = len(wl)
        wins = int(wl['win'].sum())
        wr = round(wins / n, 4)
        win_r = float(wl.loc[wl['win'] == 1, 'r'].sum())
        loss_r = float(abs(wl.loc[wl['win'] == 0, 'r'].sum()))
        ev = round(float(wl['r'].sum()) / n, 3)
        pf = round(win_r / max(loss_r, 0.001), 3)
        avg_risk = round(float(wl['risk_pts'].mean()), 1) if 'risk_pts' in wl.columns and wl['risk_pts'].notna().any() else 0
        # Equity curve for max DD
        eq = float(ACCOUNT_SIZE); peak = eq; max_dd = 0.0
        for r_val in wl['r'].values:
            eq += float(r_val) * RISK_PER_TRADE
            if eq > peak: peak = eq
            dd = (peak - eq) / peak if peak > 0 else 0
            if dd > max_dd: max_dd = dd
        # Sharpe
        daily_pnl = {}
        for _, row in wl.iterrows():
            d = str(row['date'])[:10]
            daily_pnl[d] = daily_pnl.get(d, 0) + float(row['r']) * RISK_PER_TRADE
        dp = list(daily_pnl.values())
        sharpe = None
        if len(dp) > 1:
            mu = sum(dp) / len(dp)
            sd = (sum((v - mu)**2 for v in dp) / (len(dp) - 1)) ** 0.5
            if sd > 0:
                sharpe = round(mu / sd * (252 ** 0.5), 2)
        # SPD
        dates = wl['date'].astype(str).str[:10].nunique()
        spd = round(n / max(dates, 1), 2) if dates else 0

        return dict(n=n, wr=wr, ev=ev, pf=pf, spd=spd,
                    avg_risk=avg_risk, max_dd_pct=round(max_dd * 100, 2),
                    sharpe=sharpe)

    # Base: all valid trades (no rejected_by filters — SKIP/INVALID already excluded)
    all_valid = df_all[~df_all['outcome'].isin(['SKIP', 'INVALID'])].copy()
    has_smt = 'smt' in all_valid.columns
    has_hour_aligned = 'cisd_aligned' in all_valid.columns
    has_prior_counter = 'prior_counter_close' in all_valid.columns
    has_prior_engulfing = 'prior_engulfing' in all_valid.columns

    # Helper: apply a set of filters to all_valid
    def apply_filters(active_set):
        """Return trades that pass all filters in active_set."""
        mask = pd.Series(True, index=all_valid.index)
        for f in active_set:
            if f == 'SMT':
                if has_smt:
                    mask &= all_valid['smt'] == True
            elif f == 'HOUR_ALIGNED':
                if has_hour_aligned:
                    mask &= all_valid['cisd_aligned'] == True
            elif f == 'PRIOR_COUNTER_CLOSE':
                if has_prior_counter:
                    mask &= all_valid['prior_counter_close'] == True
            elif f == 'PRIOR_ENGULFING':
                if has_prior_engulfing:
                    mask &= all_valid['prior_engulfing'] == True
            else:
                # Standard rejection filter: remove trades rejected by this code
                mask &= all_valid['rejected_by'] != f
        return all_valid[mask]

    # Standard filters = rejection-based filters (on by default).
    # Positive filters (SMT, HOUR_ALIGNED, PRIOR_COUNTER_CLOSE, PRIOR_ENGULFING)
    # are off by default and appear in individual_removal as "Add X".
    STD_FILTERS = [f for f in FILTERS if f not in POSITIVE_FILTERS]

    # Current production baseline (F1 + F3 + F4, no SMT)
    fully_filtered = apply_filters(STD_FILTERS)
    baseline = stats_of(fully_filtered)
    baseline['label'] = 'All Filters (current)'
    baseline['filters'] = list(STD_FILTERS)

    # Unfiltered
    unfiltered = stats_of(all_valid)
    unfiltered['label'] = 'No Filters (raw)'
    unfiltered['filters'] = []

    # ── Individual removal: remove ONE filter from current, keep all others ──
    individual_removal = []
    for f in FILTERS:
        if f in POSITIVE_FILTERS:
            # "Add X" — apply all standard filters PLUS this positive filter
            kept = apply_filters(STD_FILTERS + [f])
            s = stats_of(kept)
            s['label'] = f'Add {FILTER_LABELS.get(f, f)}'
            s['removed_filter'] = f
            s['ev_delta'] = round(s['ev'] - baseline['ev'], 3)
            s['wr_delta'] = round((s['wr'] - baseline['wr']) * 100, 2)
            s['n_added'] = s['n'] - baseline['n']  # negative = fewer trades
        else:
            # Remove this filter from the standard set
            remaining = [ff for ff in STD_FILTERS if ff != f]
            kept = apply_filters(remaining)
            s = stats_of(kept)
            s['label'] = f'Without {FILTER_LABELS.get(f, f)}'
            s['removed_filter'] = f
            s['ev_delta'] = round(s['ev'] - baseline['ev'], 3)
            s['wr_delta'] = round((s['wr'] - baseline['wr']) * 100, 2)
            s['n_added'] = s['n'] - baseline['n']
        individual_removal.append(s)

    # ── All combinations (2^4 = 16 with SMT) ─────────────────────────────────
    from itertools import combinations
    combos = []
    for r in range(len(FILTERS) + 1):
        for combo in combinations(FILTERS, r):
            kept = apply_filters(list(combo))
            s = stats_of(kept)
            s['filters'] = list(combo)
            s['label'] = ' + '.join(FILTER_LABELS.get(f, f) for f in combo) if combo else 'No Filters'
            s['n_filters'] = len(combo)
            combos.append(s)

    # Sort by EV descending
    combos.sort(key=lambda x: x['ev'], reverse=True)
    best = combos[0] if combos else None

    return dict(
        baseline=baseline,
        unfiltered=unfiltered,
        individual_removal=individual_removal,
        all_combinations=combos,
        best_combination=best,
    )


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    global TABLE, CISD_FAST_BARS
    parser = argparse.ArgumentParser()
    parser.add_argument('--db',             default=str(DB_PATH))
    parser.add_argument('--table',          default=TABLE)
    parser.add_argument('--output',         default=str(OUT_PATH))
    parser.add_argument('--models',         nargs='+', default=list(MODELS.keys()),
                                            choices=list(MODELS.keys()))
    parser.add_argument('--cisd-fast-bars', type=int,  default=None,
                                            dest='cisd_fast_bars',
                                            help='Max CISD bars (default: no limit)')
    args = parser.parse_args()
    TABLE          = args.table
    CISD_FAST_BARS = args.cisd_fast_bars

    print("\n" + "═"*65)
    print(f"  SWEEP MODEL ENGINE v6.0  ·  {TABLE.upper()}")
    print(f"  Profiles: {', '.join(pk for _, __, pk, ___ in RR_PROFILES)}")
    print(f"  Models: {', '.join(args.models)}")
    print(f"  Sweep mode: PREV  ·  CISD bars: {'unlimited' if CISD_FAST_BARS is None else CISD_FAST_BARS}")
    print("═"*65)

    con = connect(args.db)
    df_1m_full, df_1m_rth = load_1m(con, args.table)
    trading_days = df_1m_rth['trade_date'].nunique()

    # ── Load ES data for SMT divergence (NQ sweep vs ES sweep) ──────────────
    smt_table = 'es_1m' if args.table == 'nq_1m' else 'nq_1m'
    print(f"\n[1b] Loading {smt_table} for SMT divergence ...")
    try:
        es_1m_full, es_1m_rth = load_1m(con, smt_table)
        has_smt = True
    except Exception as e:
        print(f"   ⚠  SMT data not available ({e}), skipping SMT divergence")
        has_smt = False

    print("\n[2] Pre-building timeframes ...")
    needed_sweep_tfs = {MODELS[mk]['sweep_tf_min'] for mk in args.models}
    needed_cisd_tfs  = {MODELS[mk]['cisd_tf_min']  for mk in args.models}
    sweep_dfs = {
        tf: resample(df_1m_full if tf >= 1440 else df_1m_rth, tf,
                     "1D" if tf >= 1440 else f"{tf}min")
        for tf in sorted(needed_sweep_tfs)
    }
    cisd_dfs = {
        tf: resample(df_1m_rth, tf, f"{tf}min")
        for tf in sorted(needed_cisd_tfs)
    }
    # ES sweep-TF candles for SMT comparison (same timeframes as NQ)
    es_sweep_dfs = {}
    if has_smt:
        for tf in sorted(needed_sweep_tfs):
            es_sweep_dfs[tf] = resample(es_1m_full if tf >= 1440 else es_1m_rth, tf,
                                        f"ES_{'1D' if tf >= 1440 else f'{tf}min'}")

    print("\n[3] Converting to numpy arrays (built once, reused across all runs) ...")
    sweep_arrs   = {tf: df_to_arrays(df)    for tf, df in sweep_dfs.items()}
    cisd_arrs    = {tf: df_to_arrays(df)    for tf, df in cisd_dfs.items()}
    es_sweep_arrs  = {tf: df_to_arrays(df)   for tf, df in es_sweep_dfs.items()} if has_smt else {}
    es_m1_full_arrs = df_1m_to_arrays(es_1m_full) if has_smt else None
    es_m1_rth_arrs  = df_1m_to_arrays(es_1m_rth)  if has_smt else None
    m1_full_arrs = df_1m_to_arrays(df_1m_full)
    m1_rth_arrs  = df_1m_to_arrays(df_1m_rth)
    print("   Done.")

    all_stats    = {}
    summary_rows = []

    for mk in args.models:
        cfg    = MODELS[mk]
        s_arrs = sweep_arrs[cfg['sweep_tf_min']]
        c_arrs = cisd_arrs[cfg['cisd_tf_min']]
        m1     = m1_full_arrs if cfg['sweep_tf_min'] >= 1440 else m1_rth_arrs

        full_key = f"{mk}_PREV_CISD"
        print(f"\n{'─'*65}")
        print(f"  {full_key}  —  {cfg['label']}")
        print(f"{'─'*65}")

        es_s  = es_sweep_arrs.get(cfg['sweep_tf_min']) if has_smt else None
        es_m1 = (es_m1_full_arrs if cfg['sweep_tf_min'] >= 1440 else es_m1_rth_arrs) if has_smt else None
        base_rows, base_pending = detect_setups_base(
            m1, s_arrs, c_arrs, mk, cfg, cisd_fast_bars=CISD_FAST_BARS,
            es_s_arrs=es_s, es_m1_arrs=es_m1)
        if not base_rows:
            print(f"   ⚠  No setups found")
            continue

        print(f"      Resolving outcomes across {len(RR_PROFILES)} profiles ...")
        model_profiles = {}
        structural_df = None   # resolved trades from structural_dynamic (for per-TF PTQ)
        structural_ptq = None  # all-time PTQ from structural_dynamic
        structural_p50_mfe = None  # all-time p50 MFE
        for p_idx, (stop_val, target_val, pk, ptype) in enumerate(RR_PROFILES, 1):
            # ── split_80_20: per-TF resolution with period-specific PTQ/p50 ──
            if pk == 'split_80_20':
                if structural_df is None or structural_ptq is None:
                    print(f"      [{p_idx}/{len(RR_PROFILES)}] profile {pk} — skipped (no structural PTQ)", flush=True)
                    continue

                # Compute TF cutoff dates from structural trades
                from datetime import date as _date, timedelta as _td
                _max_date_str = str(structural_df[structural_df['rejected_by'] == '']['date'].max())[:10]
                try:
                    _ref = _date.fromisoformat(_max_date_str)
                except Exception:
                    _ref = _date.today()
                _tf_cutoffs = {
                    'all': None,
                    '2y': (_ref - _td(days=730)).isoformat(),
                    '1y': (_ref - _td(days=365)).isoformat(),
                    '6m': (_ref - _td(days=182)).isoformat(),
                    '3m': (_ref - _td(days=91)).isoformat(),
                    '1m': (_ref - _td(days=30)).isoformat(),
                }

                # Extract per-TF PTQ/p50 from structural trades (winners' MFE)
                _struct_wl = structural_df[(structural_df['rejected_by'] == '') &
                                           structural_df['outcome'].isin(['WIN','LOSS'])].copy()
                _struct_dates = _struct_wl['date'].astype(str).str[:10]

                _tf_targets = {}
                for _tfk, _cutoff in _tf_cutoffs.items():
                    if _cutoff is not None:
                        _sub = _struct_wl[_struct_dates >= _cutoff]
                    else:
                        _sub = _struct_wl
                    _wins = _sub[_sub['outcome'] == 'WIN']
                    if len(_wins) < 20:
                        _wins = _sub  # fallback to all trades if too few winners
                    _mfe_s = _full_mfe_stats(_wins) if len(_wins) >= 20 else None
                    _mae_s = _full_mae_stats(_wins) if len(_wins) >= 20 else None
                    if _mfe_s:
                        _ptq = _mfe_s.get('ptq_level')
                        _p50 = (_mfe_s.get('percentiles') or {}).get('p50')
                    else:
                        _ptq = None; _p50 = None
                    # MAE p90 of winners = 90% of winners stay within this dip
                    _mae_p90 = (_mae_s.get('percentiles') or {}).get('p90') if _mae_s else None
                    _tf_targets[_tfk] = {'ptq': _ptq, 'p50': _p50, 'mae_p90': _mae_p90}

                print(f"      [{p_idx}/{len(RR_PROFILES)}] profile {pk} — per-TF targets:", flush=True)
                for _tfk, _tgt in _tf_targets.items():
                    _ptq_v = f"{_tgt['ptq']:.4f}%" if _tgt['ptq'] else 'None'
                    _p50_v = f"{_tgt['p50']:.4f}%" if _tgt['p50'] else 'None'
                    _mae_v = f"{_tgt['mae_p90']:.4f}%" if _tgt['mae_p90'] else 'None'
                    print(f"         {_tfk:>3s}: PTQ={_ptq_v}  p50={_p50_v}  MAE_p90={_mae_v}", flush=True)

                # Use all-time targets for the main (all-time) resolution
                _all_ptq = _tf_targets['all']['ptq'] or structural_ptq
                _all_p50 = _tf_targets['all']['p50'] or structural_p50_mfe
                _all_mae = _tf_targets['all']['mae_p90']
                if _all_ptq is None:
                    print(f"         skipped (no all-time PTQ)", flush=True)
                    continue

                # Resolve all-time first
                target_val = _all_ptq
                _tp2_label = f", TP2={_all_p50:.4f}% p50 MFE" if _all_p50 else ""
                _sl_label = f", SL=min(struct,{_all_mae:.4f}% MAE_p90)" if _all_mae else ""
                print(f"         all-time: TP1={target_val:.4f}% PTQ{_tp2_label}{_sl_label} ...", flush=True)
                df_p = apply_profile_and_resolve(
                    base_rows, base_pending, m1, stop_val, target_val, ptype,
                    tp2_pct=_all_p50, sl_mae_pct=_all_mae)
                if df_p.empty:
                    continue
                print(f"         building all-time stats + TF slices ...", flush=True)
                stats = build_model_stats(
                    df_p, trading_days, mk, cfg, stop_val, target_val, pk, ptype)
                # Attach all-time TP2 and SL cap to meta
                stats['meta']['tp2_pct'] = _all_p50
                stats['meta']['sl_mae_p90_pct'] = _all_mae

                # Build set of main trade keys for consistency filtering
                _main_wl = df_p[(df_p['rejected_by'] == '') &
                                df_p['outcome'].isin(['WIN','LOSS'])]
                _main_keys = set(zip(
                    _main_wl['date'].astype(str).str[:10],
                    _main_wl['entry_price'].round(2)))

                # Re-resolve each sub-TF with period-specific targets and replace by_tf
                for _tfk, _cutoff in _tf_cutoffs.items():
                    if _tfk == 'all':
                        continue
                    _tgt = _tf_targets[_tfk]
                    _tf_ptq = _tgt['ptq']
                    _tf_p50 = _tgt['p50']
                    if _tf_ptq is None:
                        continue  # keep the sliced stats from all-time resolution

                    _tf_mae = _tgt['mae_p90']
                    _tp2_v = f", TP2={_tf_p50:.4f}%" if _tf_p50 else ""
                    _sl_v = f", SL=min(struct,{_tf_mae:.4f}%)" if _tf_mae else ""
                    print(f"         {_tfk}: TP1={_tf_ptq:.4f}% PTQ{_tp2_v}{_sl_v} ...", flush=True)
                    _tf_df = apply_profile_and_resolve(
                        base_rows, base_pending, m1, stop_val, _tf_ptq, ptype,
                        tp2_pct=_tf_p50, sl_mae_pct=_tf_mae)
                    if _tf_df.empty:
                        continue
                    # Filter to only trades in this TF period that also exist in main trades
                    _tf_wl = _tf_df[(_tf_df['date'].astype(str).str[:10] >= _cutoff) &
                                    (_tf_df['rejected_by'] == '') &
                                    _tf_df['outcome'].isin(['WIN','LOSS'])]
                    _tf_trade_keys = set(zip(
                        _tf_wl['date'].astype(str).str[:10],
                        _tf_wl['entry_price'].round(2)))
                    _extra = _tf_trade_keys - _main_keys
                    if _extra:
                        _mask = pd.Series(
                            list(zip(_tf_wl['date'].astype(str).str[:10],
                                     _tf_wl['entry_price'].round(2))),
                            index=_tf_wl.index
                        ).isin(_extra)
                        _tf_wl = _tf_wl[~_mask]
                    if len(_tf_wl) < 3:
                        continue
                    _slice = _build_slice_stats(
                        _tf_wl, stop_val, target_val, agg, HR_LABELS, DOW_NAMES,
                        DATE_CLASSIFICATION)
                    if _slice:
                        _slice['meta']['tp1_pct'] = _tf_ptq
                        _slice['meta']['tp2_pct'] = _tf_p50
                        _slice['meta']['sl_mae_p90_pct'] = _tf_mae
                        stats['by_tf'][_tfk] = _slice
                        print(f"           {len(_tf_wl):,} trades  ✓", flush=True)

                # Store per-TF target metadata
                stats['split_tf_targets'] = {
                    k: {'tp1_ptq_pct': v['ptq'], 'tp2_p50_pct': v['p50'],
                        'sl_mae_p90_pct': v['mae_p90']}
                    for k, v in _tf_targets.items()
                }
                model_profiles[pk] = stats
                print(f"         profile {pk} done ✓", flush=True)
                continue

            print(f"      [{p_idx}/{len(RR_PROFILES)}] profile {pk} ...", flush=True)
            df_p = apply_profile_and_resolve(
                base_rows, base_pending, m1, stop_val, target_val, ptype)
            if df_p.empty:
                continue
            print(f"         building stats + TF slices ...", flush=True)
            stats = build_model_stats(
                df_p, trading_days, mk, cfg, stop_val, target_val, pk, ptype)
            model_profiles[pk] = stats
            # Capture structural_dynamic's PTQ/p50 and resolved trades for split profile
            if pk == 'structural_dynamic':
                structural_df = df_p
                _mfe_wins = stats.get('rich_mfe_wins') or stats.get('rich_mfe') or {}
                structural_ptq = _mfe_wins.get('ptq_level')
                _mfe_pcts = _mfe_wins.get('percentiles', {})
                structural_p50_mfe = _mfe_pcts.get('p50')
            print(f"         profile {pk} done ✓", flush=True)

        if not model_profiles:
            continue

        all_stats[full_key] = {'profiles': model_profiles}

        # Summary uses the default profile (1:2)
        def_stats = model_profiles.get(DEFAULT_PROFILE, next(iter(model_profiles.values())))
        m_  = def_stats['meta']
        fi  = def_stats['filter_impact']
        summary_rows.append((
            full_key,
            fi[0].get('ev', 0) if fi else 0,
            fi[0].get('pf', 0) if fi else 0,
            m_['win_rate'], m_['ev_per_trade'], m_['profit_factor'],
            m_['total_wl'], m_['setups_per_day_ny'],
        ))

    # ── Write JSON ─────────────────────────────────────────────────────────────
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, 'w') as f:
        json.dump(all_stats, f, indent=2, default=str)

    # ── Summary table ──────────────────────────────────────────────────────────
    print(f"\n{'═'*78}")
    print(f"  SUMMARY  (profile = {DEFAULT_PROFILE}  ·  Base = unfiltered, Refined = all filters)")
    print(f"{'═'*78}")
    print(f"  {'Key':<24}  {'Base EV':>8}  {'Base PF':>7}  "
          f"{'→ WR':>7}  {'EV':>8}  {'PF':>7}  {'N':>6}  {'SPD':>5}")
    print(f"  {'─'*24}  {'─'*8}  {'─'*7}  {'─'*7}  {'─'*8}  {'─'*7}  {'─'*6}  {'─'*5}")

    prev_group = None
    for row in summary_rows:
        fk, bev, bpf, wr, ev, pf, n, spd = row
        group = '_'.join(fk.split('_')[:-1])
        if prev_group and group != prev_group:
            print()
        prev_group = group

        print(f"  {fk:<24}  {bev:>+8.3f}R  {bpf:>7.3f}  {wr:>6.1%}  "
              f"{ev:>+8.3f}R  {pf:>7.3f}  {n:>6,}  {spd:>5.2f}")

    print(f"{'═'*78}")
    print(f"\n  ✓  Written → {out}")
    print(f"     Open http://localhost:8000/model_dashboard.html\n")


if __name__ == '__main__':
    main()
