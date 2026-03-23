#!/usr/bin/env python3
"""
ttfm_backtest.py — TTrades Fractal Model° Historical Backtest
==============================================================
Implements TTFM° sweep → T-Spot zone → zone-touch entry rules
directly from the Pine Script indicator logic. No dependency on
model_stats.py.

T-Spot entry mechanic:
  - Zone is C3.close ↔ sweep_mid (log-weighted midpoint of C3)
  - Entry: limit order AT sweep_mid when price touches it
  - Stop:  C3.high (BEAR) or C3.low (BULL)
  - Target: 2R  (configurable via --rr)

HTF default: 60-minute candles (suitable for 5-minute chart).

Usage:
    python3 ttfm_backtest.py
    python3 ttfm_backtest.py --table es_1m
    python3 ttfm_backtest.py --htf 240 --rr 1.5
    python3 ttfm_backtest.py --min-risk 3 --max-hold 120
"""

import argparse
import json
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

# ── Paths & constants ─────────────────────────────────────────────────────────
DB_PATH    = Path(__file__).parent.parent / 'Fractal Sweep' / 'candle_science.duckdb'
OUT_JSON   = Path(__file__).parent / 'ttfm_results.json'

DEFAULT_HTF      = 60      # minutes  (1-hour HTF)
DEFAULT_RR       = 2.0     # risk-reward ratio
DEFAULT_MIN_RISK = 5.0     # minimum risk in points (filters tiny setups)
DEFAULT_MAX_HOLD = 240     # max 1m bars to hold before recording OPEN

RTH_START = 7              # 07:00 ET — zone-touch scan window start
RTH_END   = 16             # 16:00 ET — zone-touch scan window end

DOW_NAMES = {0: 'Mon', 1: 'Tue', 2: 'Wed', 3: 'Thu', 4: 'Fri'}

VARIANTS = [
    'Normal_BEAR', 'Normal_BULL',
    'Expansive_BEAR', 'Expansive_BULL',
    'ProTrend_BEAR', 'ProTrend_BULL',
]


# ── Database ──────────────────────────────────────────────────────────────────
def connect():
    if not DB_PATH.exists():
        sys.exit(f'[error] database not found: {DB_PATH}')
    return duckdb.connect(str(DB_PATH), read_only=True)


def load_1m(con, table: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (df_full, df_rth) — 1m bars in America/New_York timezone."""
    df = con.execute(f"""
        SELECT
            timezone('America/New_York', timestamp) AS ts_et,
            open, high, low, close
        FROM {table}
        ORDER BY timestamp
    """).df()

    df['ts_et'] = pd.to_datetime(df['ts_et'], utc=True).dt.tz_convert('America/New_York')
    df['hr']    = df['ts_et'].dt.hour
    df['mn']    = df['ts_et'].dt.minute
    df['dow']   = df['ts_et'].dt.dayofweek   # 0 = Monday
    df['date']  = df['ts_et'].dt.date

    df_rth = df[
        (df['hr'] >= RTH_START) & (df['hr'] < RTH_END) & (df['dow'] <= 4)
    ].reset_index(drop=True)
    return df, df_rth


# ── HTF resampling ────────────────────────────────────────────────────────────
def resample_htf(df_rth: pd.DataFrame, htf_min: int) -> pd.DataFrame:
    """Resample RTH 1m bars to HTF OHLC."""
    htf = (
        df_rth.set_index('ts_et')
        .resample(f'{htf_min}min', label='left', closed='left')
        .agg(open=('open', 'first'), high=('high', 'max'),
             low=('low', 'min'),   close=('close', 'last'))
        .dropna()
        .reset_index()
        .rename(columns={'ts_et': 'ts'})
    )
    return htf


# ── Log midpoint (TTFM indicator formula) ─────────────────────────────────────
def log_mid(o: float, h: float, l: float, c: float) -> float:
    """
    Log-space weighted midpoint of a candle.
    Weights toward the dominant wick; falls back to geometric mean for body-dominant candles.
    Returns exp(mid) as a price level.
    """
    if h <= 0 or l <= 0 or h == l:
        return (h + l) / 2.0
    lh = np.log(h)
    ll = np.log(l)
    body_top    = np.log(max(o, c))
    body_bottom = np.log(min(o, c))
    upper_wick  = lh - body_top
    lower_wick  = body_bottom - ll
    body_size   = body_top - body_bottom

    if upper_wick >= lower_wick and upper_wick >= body_size:
        mid = lh - upper_wick / 2.0
    elif lower_wick > upper_wick and lower_wick >= body_size:
        mid = ll + lower_wick / 2.0
    else:
        mid = (lh + ll) / 2.0
    return float(np.exp(mid))


# ── CISD candle check ─────────────────────────────────────────────────────────
def is_cisd_candle(c1_h, c1_l, c1_c, c2_h, c2_l) -> bool:
    """
    Outside bar that closes back inside C2's range.
    Excluded from all T-Spot variants.
    """
    return (c1_h > c2_h and c1_l < c2_l
            and c2_l < c1_c < c2_h)


# ── T-Spot detection ──────────────────────────────────────────────────────────
def detect_tspots(df_htf: pd.DataFrame, htf_min: int) -> list[dict]:
    """
    Scan consecutive HTF candle triples (C1, C2, C3) for all 6 T-Spot variants.

    Returns a list of setup dicts, each containing:
      variant, direction, zone_ts (when zone activates = C3 close time),
      zone_bot, zone_top, entry (= sweep_mid), stop, ref_ts
    """
    records = df_htf.to_dict('records')
    setups  = []
    zone_open_td = pd.Timedelta(minutes=htf_min)

    for i in range(2, len(records)):
        c3 = records[i]       # last_closed (trigger candle)
        c2 = records[i - 1]   # prev_closed (the one being swept)
        c1 = records[i - 2]   # prev_prev_closed

        c3_o, c3_h, c3_l, c3_c = c3['open'], c3['high'], c3['low'],  c3['close']
        c2_o, c2_h, c2_l, c2_c = c2['open'], c2['high'], c2['low'],  c2['close']
        c1_h, c1_l              = c1['high'], c1['low']

        # Zone activates at the CLOSE of C3 = OPEN of the next HTF candle
        zone_ts = c3['ts'] + zone_open_td

        # Log midpoints
        sweep_mid   = log_mid(c3_o, c3_h, c3_l, c3_c)   # zone boundary
        mid_level   = log_mid(c2_o, c2_h, c2_l, c2_c)   # used by Pro-trend check

        # CISD candle exclusion
        cisd_excl = is_cisd_candle(c3_h, c3_l, c3_c, c2_h, c2_l)

        def add(variant, direction, stop):
            zone_top = max(c3_c, sweep_mid)
            zone_bot = min(c3_c, sweep_mid)
            setups.append({
                'variant':   variant,
                'direction': direction,
                'zone_ts':   zone_ts,
                'zone_top':  zone_top,
                'zone_bot':  zone_bot,
                'entry':     sweep_mid,   # limit order at sweep_mid
                'stop':      stop,
                'c3_ts':     c3['ts'],
            })

        # ── Normal Bearish ────────────────────────────────────────────
        if (not cisd_excl
                and c3_h > c2_h
                and c3_c < c2_h
                and c3_c < sweep_mid):
            add('Normal_BEAR', 'SHORT', c3_h)

        # ── Normal Bullish ────────────────────────────────────────────
        if (not cisd_excl
                and c3_l < c2_l
                and c3_c > c2_l
                and c3_c > sweep_mid):
            add('Normal_BULL', 'LONG', c3_l)

        # ── Expansive Bearish ─────────────────────────────────────────
        if (not cisd_excl
                and c2_h > c1_h
                and c3_c < max(c2_o, c2_c)
                and c3_c < sweep_mid):
            add('Expansive_BEAR', 'SHORT', c3_h)

        # ── Expansive Bullish ─────────────────────────────────────────
        if (not cisd_excl
                and c2_l < c1_l
                and c3_c > min(c2_o, c2_c)
                and c3_c > sweep_mid):
            add('Expansive_BULL', 'LONG', c3_l)

        # ── Pro-trend Bearish ─────────────────────────────────────────
        if (not cisd_excl
                and c3_h > mid_level
                and c3_h < c2_o
                and c3_c < c2_l
                and c3_c < sweep_mid):
            add('ProTrend_BEAR', 'SHORT', c3_h)

        # ── Pro-trend Bullish ─────────────────────────────────────────
        if (not cisd_excl
                and c3_l < mid_level
                and c3_l > c2_o
                and c3_c > c2_h
                and c3_c > sweep_mid):
            add('ProTrend_BULL', 'LONG', c3_l)

    return setups


# ── Trade simulation ──────────────────────────────────────────────────────────
def simulate(setups: list[dict], df_rth: pd.DataFrame,
             rr: float, min_risk: float, max_hold: int) -> pd.DataFrame:
    """
    For each setup, find the first RTH 1m bar after zone_ts where
    price reaches the entry level (sweep_mid). Simulate WIN / LOSS / OPEN.

    Entry rule:  limit order at sweep_mid
      BEAR touch: high >= sweep_mid (price rallied up to entry level)
      BULL touch: low  <= sweep_mid (price dipped down to entry level)

    Stop / target computed from entry and risk = abs(entry - stop).
    """
    # Pre-extract numpy arrays for fast inner loop.
    # pandas stores tz-aware timestamps as datetime64[us]; cast to int64 → microseconds.
    ts_np   = df_rth['ts_et'].values.astype('datetime64[us]').astype('int64')
    hi_np   = df_rth['high'].values
    lo_np   = df_rth['low'].values
    hr_np   = df_rth['hr'].values
    dow_np  = df_rth['dow'].values
    mn_np   = df_rth['mn'].values
    date_np = df_rth['date'].values
    n_bars  = len(ts_np)

    results = []

    for s in setups:
        entry_price = s['entry']
        stop_price  = s['stop']
        direction   = s['direction']

        risk = abs(entry_price - stop_price)
        if risk < min_risk:
            continue

        # Target at configured RR
        if direction == 'SHORT':
            target = entry_price - rr * risk
            if target >= entry_price:
                continue
        else:
            target = entry_price + rr * risk
            if target <= entry_price:
                continue

        # Timestamp as microseconds (pandas .value is nanoseconds → divide by 1000)
        zone_ts_ns = int(s['zone_ts'].value) // 1000

        # Find first 1m bar at or after zone activation
        scan_start = int(np.searchsorted(ts_np, zone_ts_ns, side='left'))  # zone_ts_ns = microseconds
        scan_end   = min(scan_start + max_hold, n_bars)

        # ── Step 1: find zone touch (limit fill) ──────────────────────
        fill_idx = -1
        for j in range(scan_start, scan_end):
            if direction == 'SHORT' and hi_np[j] >= entry_price:
                fill_idx = j
                break
            if direction == 'LONG'  and lo_np[j] <= entry_price:
                fill_idx = j
                break

        if fill_idx == -1:
            continue   # zone never touched; skip

        # Validate fill vs stop (price must not have already hit stop)
        if direction == 'SHORT' and hi_np[fill_idx] >= stop_price:
            continue
        if direction == 'LONG'  and lo_np[fill_idx] <= stop_price:
            continue

        entry_hr  = int(hr_np[fill_idx])
        entry_dow = int(dow_np[fill_idx])
        entry_mn  = int(mn_np[fill_idx])

        # ── Step 2: scan for stop or target ───────────────────────────
        outcome  = 'OPEN'
        for j in range(fill_idx + 1, scan_end):
            if direction == 'SHORT':
                if lo_np[j] <= target:
                    outcome = 'WIN';  break
                if hi_np[j] >= stop_price:
                    outcome = 'LOSS'; break
            else:
                if hi_np[j] >= target:
                    outcome = 'WIN';  break
                if lo_np[j] <= stop_price:
                    outcome = 'LOSS'; break

        results.append({
            'variant':   s['variant'],
            'direction': direction,
            'date':      str(date_np[fill_idx]),
            'hr':        entry_hr,
            'dow':       entry_dow,
            'mn':        entry_mn,
            'quarter':   entry_mn // 15 + 1,
            'risk_pts':  round(risk, 2),
            'entry':     round(entry_price, 2),
            'stop':      round(stop_price, 2),
            'target':    round(target, 2),
            'outcome':   outcome,
        })

    return pd.DataFrame(results)


# ── Statistics ────────────────────────────────────────────────────────────────
def stats_row(df: pd.DataFrame, rr: float) -> dict | None:
    """Compute win-rate, EV, profit factor from a subset of trades."""
    wl = df[df['outcome'].isin(['WIN', 'LOSS'])]
    if len(wl) < 1:
        return None
    n    = len(wl)
    wins = int((wl['outcome'] == 'WIN').sum())
    wr   = wins / n
    ev   = round(wr * rr - (1 - wr), 4)
    pf   = round((wins * rr) / max(n - wins, 1), 3)
    return {'n': n, 'wins': wins, 'wr': round(wr, 4), 'ev': ev, 'pf': pf}


def pct(x): return f'{x:.1%}'
def sgn(x): return f'{x:+.3f}'


# ── Printing helpers ──────────────────────────────────────────────────────────
def print_table(rows: list[dict], cols: list[tuple], title: str):
    """Print a formatted ASCII table."""
    print(f'\n  {title}')
    header = '  ' + '  '.join(f'{h:<{w}}' for h, w in cols)
    sep    = '  ' + '  '.join('─' * w for _, w in cols)
    print(header)
    print(sep)
    for r in rows:
        cells = []
        for h, w in cols:
            v = r.get(h, '')
            cells.append(f'{str(v):<{w}}')
        print('  ' + '  '.join(cells))


def print_heatmap(df: pd.DataFrame, rr: float):
    """Print WR% heatmap: rows = DOW, cols = Hour."""
    hours = sorted(df['hr'].unique())
    dows  = sorted(df['dow'].unique())

    # header
    hdr = f"  {'':5}" + ''.join(f' {h:02d}:00 ' for h in hours)
    print(hdr)
    print('  ' + '─' * (len(hdr) - 2))

    for d in dows:
        row_str = f"  {DOW_NAMES.get(d,'?'):<5}"
        for h in hours:
            sub = df[(df['dow'] == d) & (df['hr'] == h)]
            s   = stats_row(sub, rr)
            if s and s['n'] >= 5:
                wr_pct = int(round(s['wr'] * 100))
                row_str += f'  {wr_pct:>3}%  '
            else:
                row_str += '   —   '
        print(row_str)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description='TTFM° backtest')
    parser.add_argument('--table',    default='nq_1m',    help='DB table (nq_1m / es_1m)')
    parser.add_argument('--htf',      type=int, default=DEFAULT_HTF,      help='HTF in minutes')
    parser.add_argument('--rr',       type=float, default=DEFAULT_RR,     help='Risk:Reward ratio')
    parser.add_argument('--min-risk', type=float, default=DEFAULT_MIN_RISK, dest='min_risk',
                        help='Minimum risk in points to include trade')
    parser.add_argument('--max-hold', type=int, default=DEFAULT_MAX_HOLD, dest='max_hold',
                        help='Max 1m bars to hold before recording OPEN')
    parser.add_argument('--no-json',  action='store_true', dest='no_json',
                        help='Skip saving JSON output')
    args = parser.parse_args()

    bar = '═' * 72

    print(f'\n{bar}')
    print(f'  TTFM° Backtest  ·  {args.table}  ·  HTF={args.htf}min  ·  RR={args.rr}  ·  min_risk={args.min_risk}pts')
    print(bar)

    # ── Load data ──────────────────────────────────────────────────────────
    print('\n  Loading data...', end=' ', flush=True)
    con = connect()
    df_full, df_rth = load_1m(con, args.table)
    print(f'{len(df_rth):,} RTH bars  ({df_rth["ts_et"].min().date()} → {df_rth["ts_et"].max().date()})')

    # ── Resample HTF ──────────────────────────────────────────────────────
    print(f'  Resampling to {args.htf}min HTF...', end=' ', flush=True)
    df_htf = resample_htf(df_rth, args.htf)
    print(f'{len(df_htf):,} HTF candles')

    # ── Detect T-Spots ────────────────────────────────────────────────────
    print('  Detecting T-Spots...', end=' ', flush=True)
    setups = detect_tspots(df_htf, args.htf)
    by_variant = {}
    for v in VARIANTS:
        by_variant[v] = sum(1 for s in setups if s['variant'] == v)
    total_setups = sum(by_variant.values())
    print(f'{total_setups:,} total setups')
    for v, cnt in by_variant.items():
        print(f'    {v:<20} {cnt:>5,}')

    # ── Simulate entries ──────────────────────────────────────────────────
    print(f'\n  Simulating entries (min_risk={args.min_risk}pts, max_hold={args.max_hold}bars)...', end=' ', flush=True)
    df = simulate(setups, df_rth, rr=args.rr, min_risk=args.min_risk, max_hold=args.max_hold)
    if df.empty:
        print('\n  [!] No trades generated. Try lowering --min-risk.')
        return
    wl = df[df['outcome'].isin(['WIN', 'LOSS'])]
    print(f'{len(df):,} touched  ·  {len(wl):,} resolved  ·  {len(df) - len(wl):,} open/expired')

    # ══ OVERALL SUMMARY ════════════════════════════════════════════════════
    print(f'\n{bar}')
    print('  OVERALL SUMMARY')
    print(bar)
    ov = stats_row(df, args.rr)
    if ov:
        print(f'  Trades resolved : {ov["n"]:,}')
        print(f'  Wins            : {ov["wins"]:,}')
        print(f'  Win rate        : {pct(ov["wr"])}')
        print(f'  Expected value  : {sgn(ov["ev"])}R')
        print(f'  Profit factor   : {ov["pf"]:.2f}')
    avg_risk = wl['risk_pts'].mean() if not wl.empty else 0
    print(f'  Avg risk (pts)  : {avg_risk:.1f}')

    # ══ BY VARIANT ═════════════════════════════════════════════════════════
    print(f'\n{bar}')
    print('  BY VARIANT')
    print(bar)
    var_rows = []
    for v in VARIANTS:
        sub = df[df['variant'] == v]
        s   = stats_row(sub, args.rr)
        if s:
            var_rows.append({'Variant': v, 'N': s['n'], 'WR': pct(s['wr']),
                             'EV': sgn(s['ev']), 'PF': f"{s['pf']:.2f}"})
    print_table(var_rows,
                [('Variant',20),('N',7),('WR',8),('EV',9),('PF',7)],
                'Variant · N · WR · EV · PF')

    # ══ BY DIRECTION ═══════════════════════════════════════════════════════
    print(f'\n{bar}')
    print('  BY DIRECTION')
    print(bar)
    dir_rows = []
    for d in ('LONG', 'SHORT'):
        sub = df[df['direction'] == d]
        s   = stats_row(sub, args.rr)
        if s:
            dir_rows.append({'Direction': d, 'N': s['n'], 'WR': pct(s['wr']),
                             'EV': sgn(s['ev']), 'PF': f"{s['pf']:.2f}"})
    print_table(dir_rows,
                [('Direction',10),('N',7),('WR',8),('EV',9),('PF',7)],
                'Direction · N · WR · EV · PF')

    # ══ BY DAY OF WEEK ══════════════════════════════════════════════════════
    print(f'\n{bar}')
    print('  BY DAY OF WEEK')
    print(bar)
    dow_rows = []
    for d in range(5):
        sub = df[df['dow'] == d]
        s   = stats_row(sub, args.rr)
        if s:
            dow_rows.append({'Day': DOW_NAMES[d], 'N': s['n'], 'WR': pct(s['wr']),
                             'EV': sgn(s['ev']), 'PF': f"{s['pf']:.2f}"})
    print_table(dow_rows,
                [('Day',6),('N',7),('WR',8),('EV',9),('PF',7)],
                'Day · N · WR · EV · PF')

    # ══ BY HOUR ═════════════════════════════════════════════════════════════
    print(f'\n{bar}')
    print('  BY HOUR (ET)')
    print(bar)
    hr_rows = []
    for h in range(RTH_START, RTH_END):
        sub = df[df['hr'] == h]
        s   = stats_row(sub, args.rr)
        if s:
            hr_rows.append({'Hour': f'{h:02d}:00', 'N': s['n'], 'WR': pct(s['wr']),
                            'EV': sgn(s['ev']), 'PF': f"{s['pf']:.2f}"})
    print_table(hr_rows,
                [('Hour',7),('N',7),('WR',8),('EV',9),('PF',7)],
                'Hour · N · WR · EV · PF')

    # ══ DOW × HOUR HEATMAP ══════════════════════════════════════════════════
    print(f'\n{bar}')
    print('  WIN RATE HEATMAP  (DOW × Hour, min N=5, — = insufficient data)')
    print(bar)
    print_heatmap(wl, args.rr)

    # ══ TOP HOURS BY VARIANT ════════════════════════════════════════════════
    print(f'\n{bar}')
    print('  BEST HOURS PER VARIANT  (min N=10)')
    print(bar)
    best_rows = []
    for v in VARIANTS:
        sub_v = df[df['variant'] == v]
        for h in range(RTH_START, RTH_END):
            sub = sub_v[sub_v['hr'] == h]
            s   = stats_row(sub, args.rr)
            if s and s['n'] >= 10:
                best_rows.append({'Variant': v, 'Hour': f'{h:02d}:00',
                                  'N': s['n'], 'WR': pct(s['wr']),
                                  'EV': sgn(s['ev']), 'PF': f"{s['pf']:.2f}"})
    best_rows.sort(key=lambda x: -float(x['WR'].rstrip('%')))
    print_table(best_rows[:30],
                [('Variant',20),('Hour',7),('N',6),('WR',8),('EV',9),('PF',7)],
                'Variant · Hour · N · WR · EV · PF  (top 30, sorted by WR)')

    print(f'\n{bar}\n')

    # ══ SAVE JSON ════════════════════════════════════════════════════════════
    if not args.no_json:
        _save_json(df, wl, args, ov)
        print(f'  Saved → {OUT_JSON}')


def _save_json(df: pd.DataFrame, wl: pd.DataFrame, args, overall: dict):
    """Serialise results to JSON for the HTML dashboard."""
    rr = args.rr

    def _stats(sub):
        s = stats_row(sub, rr)
        return s if s else {'n': 0, 'wins': 0, 'wr': 0, 'ev': 0, 'pf': 0}

    # Per-variant
    by_variant = {v: _stats(df[df['variant'] == v]) for v in VARIANTS}

    # Per-DOW
    by_dow = {
        DOW_NAMES[d]: _stats(df[df['dow'] == d])
        for d in range(5)
        if not df[df['dow'] == d].empty
    }

    # Per-hour
    by_hour = {
        f'{h:02d}': _stats(df[df['hr'] == h])
        for h in range(RTH_START, RTH_END)
        if not df[df['hr'] == h].empty
    }

    # DOW × Hour grid (win rate matrix)
    hours = list(range(RTH_START, RTH_END))
    dows  = list(range(5))
    heatmap_wr   = {}
    heatmap_n    = {}
    heatmap_ev   = {}
    for d in dows:
        dn = DOW_NAMES[d]
        heatmap_wr[dn]  = {}
        heatmap_n[dn]   = {}
        heatmap_ev[dn]  = {}
        for h in hours:
            sub = df[(df['dow'] == d) & (df['hr'] == h)]
            s   = stats_row(sub, rr)
            hk  = f'{h:02d}'
            if s and s['n'] >= 5:
                heatmap_wr[dn][hk]  = round(s['wr'], 4)
                heatmap_n[dn][hk]   = s['n']
                heatmap_ev[dn][hk]  = s['ev']
            else:
                heatmap_wr[dn][hk]  = None
                heatmap_n[dn][hk]   = 0
                heatmap_ev[dn][hk]  = None

    # Per variant × hour
    variant_hour = {}
    for v in VARIANTS:
        variant_hour[v] = {}
        for h in hours:
            sub = df[(df['variant'] == v) & (df['hr'] == h)]
            s   = stats_row(sub, rr)
            variant_hour[v][f'{h:02d}'] = s if s else None

    # Per variant × DOW
    variant_dow = {}
    for v in VARIANTS:
        variant_dow[v] = {}
        for d in dows:
            sub = df[(df['variant'] == v) & (df['dow'] == d)]
            s   = stats_row(sub, rr)
            variant_dow[v][DOW_NAMES[d]] = s if s else None

    # Per quarter (Q1–Q4, 15-min windows within each hour)
    quarters = [1, 2, 3, 4]
    quarter_names = {1: 'Q1 (0–14m)', 2: 'Q2 (15–29m)', 3: 'Q3 (30–44m)', 4: 'Q4 (45–59m)'}
    by_quarter = {
        quarter_names[q]: _stats(df[df['quarter'] == q])
        for q in quarters
    }

    # Hour × Quarter grid (9 hours × 4 quarters)
    hour_quarter = {}
    for h in hours:
        hk = f'{h:02d}'
        hour_quarter[hk] = {}
        for q in quarters:
            sub = df[(df['hr'] == h) & (df['quarter'] == q)]
            s   = stats_row(sub, rr)
            hour_quarter[hk][str(q)] = s if (s and s['n'] >= 3) else None

    # Variant × Quarter
    variant_quarter = {}
    for v in VARIANTS:
        variant_quarter[v] = {}
        for q in quarters:
            sub = df[(df['variant'] == v) & (df['quarter'] == q)]
            s   = stats_row(sub, rr)
            variant_quarter[v][str(q)] = s if s else None

    # DOW × Quarter
    dow_quarter = {}
    for d in dows:
        dn = DOW_NAMES[d]
        dow_quarter[dn] = {}
        for q in quarters:
            sub = df[(df['dow'] == d) & (df['quarter'] == q)]
            s   = stats_row(sub, rr)
            dow_quarter[dn][str(q)] = s if s else None

    # Most recent 25 trades per variant
    recent_trades = {}
    for v in VARIANTS:
        sub = df[(df['variant'] == v) & (df['outcome'].isin(['WIN', 'LOSS']))]
        sub_sorted = sub.sort_values('date', ascending=False).head(25)
        rows = sub_sorted[['date','direction','hr','dow','mn','quarter','entry','stop','target','risk_pts','outcome']].to_dict('records')
        for t in rows:
            t['dow_name'] = DOW_NAMES.get(int(t['dow']), '?')
            t['date'] = str(t['date'])
        recent_trades[v] = rows

    out = {
        'meta': {
            'table':    args.table,
            'htf_min':  args.htf,
            'rr':       rr,
            'min_risk': args.min_risk,
            'total_resolved': int(len(df[df['outcome'].isin(['WIN','LOSS'])])),
            'total_trades':   int(len(df)),
        },
        'overall':      overall,
        'by_variant':   by_variant,
        'by_dow':       by_dow,
        'by_hour':      by_hour,
        'heatmap_wr':   heatmap_wr,
        'heatmap_n':    heatmap_n,
        'heatmap_ev':   heatmap_ev,
        'variant_hour':    variant_hour,
        'variant_dow':     variant_dow,
        'by_quarter':      by_quarter,
        'hour_quarter':    hour_quarter,
        'variant_quarter': variant_quarter,
        'dow_quarter':     dow_quarter,
        'hours':           [f'{h:02d}' for h in hours],
        'dows':            [DOW_NAMES[d] for d in dows],
        'variants':        VARIANTS,
        'quarters':        [str(q) for q in quarters],
        'quarter_names':   quarter_names,
        'recent_trades':   recent_trades,
    }

    with open(OUT_JSON, 'w') as f:
        json.dump(out, f, indent=2)


if __name__ == '__main__':
    main()
