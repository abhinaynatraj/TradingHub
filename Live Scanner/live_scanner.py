#!/usr/bin/env python3
"""
Fractal Sweep — Live Scanner
=============================
Connects to IB Gateway / TWS, streams real-time 1m bars for NQ and ES,
detects Sweep + CISD setups across all 4 model variants, and fires alerts
via macOS native notifications and Discord webhooks.

Requirements:
    pip install ib_insync pandas numpy requests

IB Gateway / TWS ports:
    TWS paper:        7497    TWS live:         7496
    IB Gateway paper: 4002    IB Gateway live:  4001

Setup:
    1. Start IB Gateway or TWS and enable API connections
       (File → Global Config → API → Settings → Enable ActiveX and Socket Clients)
    2. Set DISCORD_WEBHOOK below or export DISCORD_WEBHOOK=https://...
    3. python3 "Live Scanner/live_scanner.py"
"""

import asyncio
import logging
import os
import subprocess
import threading
import time
from collections import deque
from datetime import datetime, timedelta, timezone

# Python 3.10+ no longer auto-creates an event loop — ib_insync needs one present at import time
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

import json
import numpy as np
import pandas as pd
import requests
from ib_insync import IB, ContFuture, util
from pathlib import Path

# ── USER CONFIG ───────────────────────────────────────────────────────────────
IB_HOST        = '127.0.0.1'
IB_PORT        = 4002          # IB Gateway paper; live = 4001, TWS paper = 7497, TWS live = 7496
IB_CLIENT_ID   = 10            # any int; must not conflict with other IB connections
DISCORD_WEBHOOK = os.environ.get('DISCORD_WEBHOOK', 'https://discord.com/api/webhooks/1487896746758770843/cg8Q6aLRc5s9TD3li9tuwEm1bj9uFCuI1k7kPLgZbS_YyCzosWrYaDqtRCxu20Kuh5iY')
INSTRUMENTS    = ['NQ', 'ES']  # instruments to scan
ACTIVE_MODELS  = ['4H_15M', '1H_5M', '1H_3M', '30M_3M']
TIMEZONE       = 'America/New_York'
MAC_NOTIFY     = True
HISTORY_DAYS   = 2             # days of 1m bars to seed on startup (covers anchor lookback)
# ─────────────────────────────────────────────────────────────────────────────

# ── DETECTION CONSTANTS (mirror model_stats.py) ───────────────────────────────
SWEEP_MIN_PCT  = 0.10   # sweep must be ≥ 10% of prior candle range
SWEEP_MAX_PCT  = 1.50   # sweep must be ≤ 150% of prior candle range
CISD_FAST_BARS = 8      # CISD must fire within this many CISD-TF bars
MIN_RISK_PTS   = 3.0    # minimum stop distance in points
RTH_START      = 7      # ET hour
RTH_END        = 16     # ET hour (exclusive)

MODELS: dict[str, dict] = {
    '4H_15M': dict(label='4H Sweep · 15M CISD', sweep_tf=240, cisd_tf=15, q1_min=60,  min_range=30),
    '1H_5M':  dict(label='1H Sweep · 5M CISD',  sweep_tf=60,  cisd_tf=5,  q1_min=15,  min_range=12),
    '1H_3M':  dict(label='1H Sweep · 3M CISD',  sweep_tf=60,  cisd_tf=3,  q1_min=15,  min_range=12),
    '30M_3M': dict(label='30M Sweep · 3M CISD', sweep_tf=30,  cisd_tf=3,  q1_min=8,   min_range=8),
}

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)-7s  %(message)s',
    datefmt='%H:%M:%S',
)
log = logging.getLogger('sweep_scanner')

# ── LOAD HISTORICAL MAE/MFE AVERAGES FROM model_stats.json ───────────────────
# Keyed by (model_key, session, direction) → {avg_mae, avg_mfe}
_STATS_JSON = Path(__file__).parent.parent / 'Fractal Sweep' / 'model_stats.json'
_SESSION_STATS: dict = {}

def _load_session_stats() -> None:
    """
    Parse model_stats.json and build a lookup of avg MAE/MFE %
    by (model_key, session, direction) using the default profile sl_026_tp_018.
    Falls back gracefully if the file is missing or malformed.
    """
    global _SESSION_STATS
    try:
        data = json.loads(_STATS_JSON.read_text())
        for full_key, model_data in data.items():
            # full_key e.g. '1H_5M_PREV_CISD'
            model_key = full_key.replace('_PREV_CISD', '')
            profile = (model_data.get('profiles') or {}).get('sl_026_tp_018') or {}
            for row in profile.get('by_session') or []:
                k = (model_key, row.get('session', ''), row.get('direction', ''))
                _SESSION_STATS[k] = {
                    'avg_mae': row.get('avg_mae'),
                    'avg_mfe': row.get('avg_mfe'),
                }
        log.info('Loaded session MAE/MFE stats for %d breakdowns', len(_SESSION_STATS))
    except Exception as exc:
        log.warning('Could not load model_stats.json for MAE/MFE context: %s', exc)

_load_session_stats()


# ── NOTIFICATIONS ─────────────────────────────────────────────────────────────

def _notify_macos(title: str, body: str) -> None:
    if not MAC_NOTIFY:
        return
    try:
        script = (
            f'display notification "{body}" '
            f'with title "{title}" '
            f'sound name "Blow"'
        )
        subprocess.run(['osascript', '-e', script], check=True, capture_output=True)
    except Exception as exc:
        log.warning('macOS notify failed: %s', exc)


def _notify_discord(setup: dict) -> None:
    if not DISCORD_WEBHOOK:
        return
    direction  = setup['direction']
    is_long    = direction == 'LONG'
    color      = 0x10B981 if is_long else 0xF87171
    arrow      = '▲' if is_long else '▼'
    side_emoji = '🟢' if is_long else '🔴'
    entry      = setup['entry_price']
    base_risk  = setup['base_risk']
    sweep_pct  = setup['sweep_pct'] * 100

    # Structural levels
    struct_stop = setup['stop_price']
    tp1         = setup['tp1_price']
    struct_sl_pct = abs(entry - struct_stop) / entry * 100
    tp1_pct       = abs(tp1  - entry)        / entry * 100

    # Fixed % levels (sl_026_tp_018)
    fixed_sl   = setup['fixed_sl']
    fixed_tp   = setup['fixed_tp']
    fixed_sl_pct = abs(entry - fixed_sl) / entry * 100
    fixed_tp_pct = abs(fixed_tp - entry) / entry * 100
    fixed_rr     = round(fixed_tp_pct / fixed_sl_pct, 2) if fixed_sl_pct else 0

    # Historical MAE/MFE averages for this model + session + direction
    hist    = _SESSION_STATS.get((setup['model_key'], setup['session'], direction), {})
    avg_mae = hist.get('avg_mae')
    avg_mfe = hist.get('avg_mfe')
    mae_str = f'**{avg_mae:.4f}%**' if avg_mae is not None else '—'
    mfe_str = f'**{avg_mfe:.4f}%**' if avg_mfe is not None else '—'

    embed = {
        'title': f'{side_emoji}  {setup["symbol"]}  {direction} {arrow}',
        'description': (
            f'### {setup["model_label"]}\n'
            f'`{setup["session"]}`  ·  {setup["ts_et"]}'
        ),
        'color': color,
        'fields': [
            # Row 1 — Structural profile (SL = sweep extreme, TP1 = 1R, runner w/ BE)
            {'name': '📍 Entry',              'value': f'```{entry:.2f}```',                                       'inline': True},
            {'name': '🛑 Struct Stop',        'value': f'```{struct_stop:.2f}```\n−{struct_sl_pct:.3f}%',         'inline': True},
            {'name': '🎯 TP1 (1R) + Runner',  'value': f'```{tp1:.2f}```\n+{tp1_pct:.3f}%',                      'inline': True},
            # Row 2 — Fixed % profile (sl_026_tp_018)
            {'name': '⚠️ Base Risk',          'value': f'**{base_risk:.1f} pts**',                                'inline': True},
            {'name': '🛑 Fixed SL (0.26%)',   'value': f'`{fixed_sl:.2f}`  −{fixed_sl_pct:.3f}%',                'inline': True},
            {'name': '🎯 Fixed TP (0.18%)',   'value': f'`{fixed_tp:.2f}`  +{fixed_tp_pct:.3f}%  ({fixed_rr}R)', 'inline': True},
            # Row 3 — Context
            {'name': '📊 Sweep',              'value': f'**{sweep_pct:.1f}%** of range',                          'inline': True},
            {'name': '📉 Avg MAE',            'value': mae_str,                                                    'inline': True},
            {'name': '📈 Avg MFE',            'value': mfe_str,                                                    'inline': True},
        ],
        'footer': {'text': 'Struct: SL=sweep extreme, TP1=1R 50% exit + runner w/ BE  ·  Fixed: sl_026_tp_018'},
        'timestamp': datetime.now(timezone.utc).isoformat(),
    }
    try:
        r = requests.post(
            DISCORD_WEBHOOK,
            json={'embeds': [embed]},
            timeout=10,
        )
        r.raise_for_status()
    except Exception as exc:
        log.warning('Discord notify failed: %s', exc)


def fire_alerts(setup: dict) -> None:
    direction = setup['direction']
    arrow     = '▲' if direction == 'LONG' else '▼'
    title     = f'🔔  {setup["symbol"]}  {direction} {arrow}'
    body      = (
        f'{setup["model_label"]}  ·  '
        f'Entry {setup["entry_price"]:.2f}  '
        f'SL {setup["stop_price"]:.2f}  '
        f'TP1 {setup["tp1_price"]:.2f}  '
        f'Risk {setup["base_risk"]:.1f} pts'
    )
    log.info(
        'ALERT  %s  %s %s  |  entry=%.2f  struct_stop=%.2f  tp1=%.2f  [%s]',
        setup['symbol'], direction, arrow,
        setup['entry_price'], setup['stop_price'], setup['tp1_price'],
        setup['model_label'],
    )
    _notify_macos(title, body)
    _notify_discord(setup)


# ── HELPERS ───────────────────────────────────────────────────────────────────

def get_session(hour: int, minute: int) -> str:
    hf = hour + minute / 60.0
    if 8.5  <= hf < 11.5: return 'NY1'
    if 11.5 <= hf < 16.0: return 'NY2'
    if 7.0  <= hf <  8.5: return 'PRE'
    return 'OVERNIGHT'


def resample(df: pd.DataFrame, tf_min: int) -> pd.DataFrame:
    """Resample an ET-indexed 1m DataFrame to tf_min OHLCV bars."""
    floored = df.index.floor(f'{tf_min}min')
    return df.groupby(floored).agg(
        open=('open', 'first'),
        high=('high', 'max'),
        low=('low', 'min'),
        close=('close', 'last'),
    )


# ── CISD DETECTION (logic mirrors model_stats.py verbatim) ───────────────────

def _find_cisd_arrays(
    opens: np.ndarray,
    closes: np.ndarray,
    start_idx: int,
    n_bars: int,
    direction: str,
) -> tuple[int | None, float | None]:
    """
    Returns (firing_bar_idx, cisd_level) or (None, None).

    Step 1 — backward from start_idx: find the consecutive opposing delivery
    run (bearish run for LONG, bullish run for SHORT) and derive cisd_level
    from the open of the FIRST (earliest) candle in that run.

    Step 2 — forward from start_idx: find the first bar whose close crosses
    cisd_level in the trade direction.
    """
    end  = min(start_idx + n_bars * 2, len(closes))
    back = max(0, start_idx - n_bars * 4)

    if direction == 'LONG':
        j = start_idx - 1
        while j >= back and closes[j] == opens[j]:
            j -= 1
        if j < back or closes[j] >= opens[j]:
            return None, None
        run_start = j
        k = j - 1
        while k >= back:
            if   closes[k] < opens[k]: run_start = k; k -= 1
            elif closes[k] == opens[k]: k -= 1
            else: break
        cisd_level = float(opens[run_start])
        for i in range(start_idx, end):
            if closes[i] > cisd_level:
                return i, cisd_level

    else:  # SHORT
        j = start_idx - 1
        while j >= back and closes[j] == opens[j]:
            j -= 1
        if j < back or closes[j] <= opens[j]:
            return None, None
        run_start = j
        k = j - 1
        while k >= back:
            if   closes[k] > opens[k]: run_start = k; k -= 1
            elif closes[k] == opens[k]: k -= 1
            else: break
        cisd_level = float(opens[run_start])
        for i in range(start_idx, end):
            if closes[i] < cisd_level:
                return i, cisd_level

    return None, None


def find_cisd(
    cisd_df: pd.DataFrame,
    return_ts: pd.Timestamp,
    direction: str,
) -> tuple[bool, float | None, float | None, pd.Timestamp | None]:
    """
    Search cisd_df for CISD firing at/after return_ts.

    Returns (fired, cisd_level, entry_price, entry_ts).
      entry_price = open of the NEXT cisd-TF bar after the firing bar.
      Returns (False, None, None, None) if CISD does not fire.
    """
    if cisd_df is None or len(cisd_df) < 2:
        return False, None, None, None

    opens  = cisd_df['open'].to_numpy(dtype='float64')
    closes = cisd_df['close'].to_numpy(dtype='float64')
    idx_arr = cisd_df.index

    start = int(idx_arr.searchsorted(return_ts, side='left'))
    if start >= len(idx_arr):
        return False, None, None, None

    fire_idx, cisd_level = _find_cisd_arrays(opens, closes, start, CISD_FAST_BARS, direction)
    if fire_idx is None:
        return False, None, None, None

    entry_idx = fire_idx + 1
    if entry_idx >= len(idx_arr):
        # CISD fired on the last available bar — entry bar not yet open.
        # Return the firing bar's close as an estimated entry.
        return True, cisd_level, float(closes[fire_idx]), idx_arr[fire_idx]

    return True, cisd_level, float(opens[entry_idx]), idx_arr[entry_idx]


# ── SETUP DETECTION ───────────────────────────────────────────────────────────

def check_model(
    m1_df: pd.DataFrame,
    model_key: str,
    cfg: dict,
    symbol: str,
    fired: set,
) -> list[dict]:
    """
    Scan the most recent anchor period of the given model for a Sweep + CISD setup.
    Returns a list of new setup dicts (normally 0 or 1 per call).
    """
    sweep_tf = cfg['sweep_tf']
    cisd_tf  = cfg['cisd_tf']
    q1_min   = cfg['q1_min']
    min_range = cfg['min_range']

    now_et = m1_df.index[-1]

    # RTH guard
    if now_et.hour < RTH_START or now_et.hour >= RTH_END:
        return []

    anchor_df = resample(m1_df, sweep_tf)
    cisd_df   = resample(m1_df, cisd_tf)

    # Current anchor period boundary
    curr_start = now_et.floor(f'{sweep_tf}min')

    # Prior = last fully closed anchor bar
    completed = anchor_df[anchor_df.index < curr_start]
    if len(completed) < 1:
        return []

    prior     = completed.iloc[-1]
    prior_hi  = float(prior['high'])
    prior_lo  = float(prior['low'])
    ref_range = prior_hi - prior_lo

    if ref_range < min_range:
        return []

    # Q1 bars of the current anchor period
    q1_end = curr_start + pd.Timedelta(minutes=q1_min)
    q1     = m1_df[(m1_df.index >= curr_start) & (m1_df.index < q1_end)]
    if len(q1) < 3:
        return []

    new_setups = []

    for direction in ('LONG', 'SHORT'):
        ref_level = prior_lo if direction == 'LONG' else prior_hi

        # ── Phase 1: sweep ────────────────────────────────────────────────────
        if direction == 'LONG':
            swept = q1['low'] < ref_level
        else:
            swept = q1['high'] > ref_level

        if not swept.any():
            continue

        sweep_ts = swept.idxmax()

        if direction == 'LONG':
            sweep_extreme = float(q1.loc[swept, 'low'].min())
        else:
            sweep_extreme = float(q1.loc[swept, 'high'].max())

        sweep_ext = abs(sweep_extreme - ref_level)

        if ref_range > 0 and sweep_ext / ref_range < SWEEP_MIN_PCT:
            continue
        if ref_range > 0 and sweep_ext / ref_range > SWEEP_MAX_PCT:
            continue

        # ── Phase 2: return to range ──────────────────────────────────────────
        post = q1[q1.index > sweep_ts]
        if post.empty:
            continue

        if direction == 'LONG':
            ret_mask = post['high'] >= ref_level
        else:
            ret_mask = post['low'] <= ref_level

        if not ret_mask.any():
            continue

        ret_ts  = ret_mask.idxmax()
        ret_bar = q1.loc[ret_ts]

        # F4: close must be back inside range
        if direction == 'LONG' and float(ret_bar['close']) < ref_level:
            continue
        if direction == 'SHORT' and float(ret_bar['close']) > ref_level:
            continue

        # ── Phase 3: CISD ─────────────────────────────────────────────────────
        cisd_fired, cisd_level, entry_price, entry_ts = find_cisd(
            cisd_df, ret_ts, direction
        )
        if not cisd_fired or entry_price is None:
            continue

        # ── Dedup: one alert per (symbol, model, direction, anchor period) ────
        dedup = (symbol, model_key, direction, str(curr_start))
        if dedup in fired:
            continue

        # ── Risk / targets ────────────────────────────────────────────────────
        base_risk = abs(entry_price - sweep_extreme)
        if base_risk < MIN_RISK_PTS:
            continue

        # Structural profile: SL = sweep extreme, TP1 = entry ± 1R (50% exit),
        # runner holds with breakeven stop
        struct_stop = sweep_extreme
        struct_tp1  = (entry_price + base_risk
                       if direction == 'LONG'
                       else entry_price - base_risk)

        # Fixed % profiles (top 2 from backtester, default sl_026_tp_018)
        def _fixed(sl_pct, tp_pct):
            if direction == 'LONG':
                return (round(entry_price * (1 - sl_pct / 100), 2),
                        round(entry_price * (1 + tp_pct / 100), 2))
            else:
                return (round(entry_price * (1 + sl_pct / 100), 2),
                        round(entry_price * (1 - tp_pct / 100), 2))

        fixed_sl, fixed_tp = _fixed(0.26, 0.18)   # sl_026_tp_018 (default / best ranked)

        ts_label = (entry_ts.strftime('%Y-%m-%d %H:%M ET')
                    if hasattr(entry_ts, 'strftime') else str(entry_ts))

        setup = dict(
            symbol       = symbol,
            model_key    = model_key,
            model_label  = cfg['label'],
            direction    = direction,
            entry_price  = round(float(entry_price), 2),
            # Structural
            stop_price   = round(float(struct_stop), 2),
            tp1_price    = round(float(struct_tp1), 2),
            base_risk    = round(float(base_risk), 1),
            # Fixed % (sl_026_tp_018)
            fixed_sl     = fixed_sl,
            fixed_tp     = fixed_tp,
            sweep_pct    = round(sweep_ext / ref_range, 3) if ref_range > 0 else 0.0,
            cisd_level   = round(float(cisd_level), 2) if cisd_level else None,
            session      = get_session(now_et.hour, now_et.minute),
            ts_et        = ts_label,
            anchor_start = str(curr_start),
        )

        fired.add(dedup)
        new_setups.append(setup)
        log.info(
            'Setup found:  %s  %s  %s  entry=%.2f  struct_stop=%.2f  tp1=%.2f  fixed_sl=%.2f  fixed_tp=%.2f',
            symbol, direction, cfg['label'],
            setup['entry_price'], setup['stop_price'], setup['tp1_price'],
            setup['fixed_sl'], setup['fixed_tp'],
        )

    return new_setups


# ── MAIN SCANNER ──────────────────────────────────────────────────────────────

class LiveScanner:
    def __init__(self):
        self.ib      = IB()
        # Rolling 1m bar buffer per symbol (enough bars for the 4H model + CISD lookback)
        maxlen       = HISTORY_DAYS * 24 * 60
        self.buffers : dict[str, deque] = {s: deque(maxlen=maxlen) for s in INSTRUMENTS}
        self.fired   : set              = set()   # dedup set, cleared each RTH open
        self._handles: dict             = {}      # symbol → BarDataList (keeps subscription alive)

    # ── IB connection ─────────────────────────────────────────────────────────

    def connect(self) -> None:
        log.info('Connecting to IB at %s:%d (clientId=%d) ...', IB_HOST, IB_PORT, IB_CLIENT_ID)
        self.ib.connect(IB_HOST, IB_PORT, clientId=IB_CLIENT_ID)
        log.info('Connected.  Client id: %d', IB_CLIENT_ID)

    # ── Subscriptions ─────────────────────────────────────────────────────────

    def subscribe(self, symbol: str) -> None:
        """Seed history AND subscribe to live 1m bars in a single IB request."""
        contract = ContFuture(symbol, 'CME')
        self.ib.qualifyContracts(contract)
        log.info('%s: qualified → %s', symbol, contract.localSymbol)

        bars = self.ib.reqHistoricalData(
            contract,
            endDateTime='',                          # empty = up to now
            durationStr=f'{HISTORY_DAYS} D',
            barSizeSetting='1 min',
            whatToShow='TRADES',
            useRTH=False,                            # include pre/post for anchor context
            keepUpToDate=True,                       # stream live bars after seed
        )

        # Seed buffer from historical batch
        for b in bars:
            self._push(symbol, b)
        log.info('%s: seeded %d historical bars', symbol, len(bars))

        # Wire live update handler
        bars.updateEvent += lambda b, has_new: self._on_bar(symbol, b, has_new)
        self._handles[symbol] = bars  # hold reference so GC doesn't destroy it
        log.info('%s: live subscription active', symbol)

    # ── Bar event ─────────────────────────────────────────────────────────────

    def _push(self, symbol: str, bar) -> None:
        self.buffers[symbol].append({
            'ts':    bar.date,
            'open':  float(bar.open),
            'high':  float(bar.high),
            'low':   float(bar.low),
            'close': float(bar.close),
        })

    def _on_bar(self, symbol: str, bars, has_new_bar: bool) -> None:
        if not has_new_bar or not bars:
            return
        self._push(symbol, bars[-1])
        self._scan(symbol)

    # ── Build ET-indexed DataFrame ────────────────────────────────────────────

    def _build_df(self, symbol: str) -> pd.DataFrame | None:
        rows = list(self.buffers[symbol])
        if len(rows) < 20:
            return None
        df = pd.DataFrame(rows)
        # IB returns tz-aware UTC datetimes; convert to ET
        df['ts'] = pd.to_datetime(df['ts'], utc=True).dt.tz_convert(TIMEZONE)
        df = df.set_index('ts').sort_index()
        # Keep only RTH bars (mirrors backtester's raw_rth filter)
        df = df[
            (df.index.hour >= RTH_START) &
            ((df.index.hour < RTH_END) |
             ((df.index.hour == RTH_END) & (df.index.minute == 0)))
        ]
        return df if len(df) >= 10 else None

    # ── Detection loop ────────────────────────────────────────────────────────

    def _scan(self, symbol: str) -> None:
        df = self._build_df(symbol)
        if df is None:
            return
        for model_key in ACTIVE_MODELS:
            setups = check_model(df, model_key, MODELS[model_key], symbol, self.fired)
            for setup in setups:
                fire_alerts(setup)

    # ── Daily reset ───────────────────────────────────────────────────────────

    def _daily_reset_loop(self) -> None:
        """Clear the dedup set each morning at RTH open so fresh setups can fire."""
        while True:
            now  = datetime.now()
            next_reset = now.replace(hour=RTH_START, minute=0, second=5, microsecond=0)
            if now >= next_reset:
                next_reset += timedelta(days=1)
            time.sleep((next_reset - now).total_seconds())
            self.fired.clear()
            log.info('Dedup set cleared for new trading day (%s)', next_reset.strftime('%Y-%m-%d'))

    # ── Entry point ───────────────────────────────────────────────────────────

    def run(self) -> None:
        self.connect()

        for sym in INSTRUMENTS:
            self.subscribe(sym)

        threading.Thread(target=self._daily_reset_loop, daemon=True, name='daily-reset').start()

        log.info(
            'Scanner running  —  instruments: %s  |  models: %s',
            ', '.join(INSTRUMENTS),
            ', '.join(ACTIVE_MODELS),
        )
        log.info('Press Ctrl+C to stop.')

        try:
            self.ib.run()   # blocks on the IB event loop
        except KeyboardInterrupt:
            log.info('Shutting down...')
        finally:
            self.ib.disconnect()
            log.info('Disconnected from IB.')


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    # Suppress ib_insync's own verbose logging; only show warnings and above
    util.logToConsole(logging.WARNING)
    scanner = LiveScanner()
    scanner.run()
