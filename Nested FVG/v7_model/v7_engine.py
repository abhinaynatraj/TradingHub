"""Nested FVG Pro v7-dynamic — fully optimised Python backtest engine.

Speed design
------------
simulate_trade_fast()
    Pure-numpy implementation of the 3-leg exit state machine.
    Uses np.argmax to find first-hit bars instead of a Python for-loop.
    ~50-200× faster than the equivalent bar-by-bar loop.

preprocess_signals()
    Runs detect + session/window gating + sess_end computation ONCE.
    The combo loop in sweep.py reuses the result for all 840+ combinations.
    Critical: _session_end_idx was previously called per-signal per-combo
    (840× redundant).  Now it's called once total.

run_combo_fast()
    Iterates the pre-processed signal list with the block-while-open gate
    and daily-loss-limit, applying risk params to simulate_trade_fast.
    No file I/O, no pandas, no numpy allocations beyond array slicing.

Dynamic % levels
----------------
    stop_price    = entry ± entry × stop_pct / 100
    partial_price = entry ± entry × partial_pct / 100
    target_price  = entry ± entry × target_pct / 100
    ext_price     = entry ± entry × ext_pct / 100

All levels computed at entry time → instrument/price-level agnostic.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Ensure the repo root (Nested FVG/) is on sys.path so `engine` resolves as a package.
_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from engine.constants import MIN_FVG_BP, PROXIMITY_BP, COOLDOWN_BARS  # noqa: E402
from engine.detect import find_fvgs                                     # noqa: E402
from engine.resampling import resample                                  # noqa: E402
import engine.build_stats as bs                                         # noqa: E402

# ── Default parameters (≈ Pine v7 defaults at NQ ~20 000) ────────────────────
DEFAULT_STOP_PCT    = 0.10    # 0.10% ≈ 20 pts at 20 000
DEFAULT_PARTIAL_PCT = 0.10
DEFAULT_TARGET_PCT  = 0.225  # 0.225% ≈ 45 pts
DEFAULT_EXT_PCT     = 0.30
DEFAULT_QTY         = 3
DEFAULT_QTY_PART    = 1
DEFAULT_QTY_TGT     = 1
DEFAULT_BE_AT_PART  = True
DEFAULT_DLL_USD     = 400.0
DEFAULT_PTDLL_USD   = 150.0
DEFAULT_USD_PER_PT  = 2.0    # MNQ $2/pt
DEFAULT_COOLDOWN    = COOLDOWN_BARS  # 30 bars


# ── Session / window helpers ──────────────────────────────────────────────────

def _in_session(ct_h: int) -> bool:
    """Pine session 1900-1600 Chicago = hours 19..23 + 0..15."""
    return ct_h >= 19 or ct_h <= 15


def _in_window(ct_h: int) -> bool:
    """v7 trading windows (CT, all four enabled by default)."""
    return (19 <= ct_h <= 20) or (ct_h == 1) or (6 <= ct_h <= 10) or (12 <= ct_h <= 13)


def _window_label(ct_h: int) -> str:
    if 19 <= ct_h <= 20: return '7-9PM'
    if ct_h == 1:        return '1-2AM'
    if 6 <= ct_h <= 10:  return '6-11AM'
    if 12 <= ct_h <= 13: return '12-2PM'
    return 'Other'


def _session_of(ct_h: int) -> str:
    if ct_h >= 19 or ct_h <= 1: return 'ASIA'
    if 2 <= ct_h <= 7:           return 'LONDON'
    if 8 <= ct_h <= 15:          return 'NY'
    return 'OTHER'


# ── Vectorised trade simulation ───────────────────────────────────────────────

def simulate_trade_fast(
        hi_sl: np.ndarray, lo_sl: np.ndarray, cl_sl: np.ndarray,
        direction: int,
        entry_price: float,
        stop_price: float, partial_price: float,
        target_price: float, ext_price: float,
        qty: int, qty_part: int, qty_tgt: int,
        be_at_partial: bool,
        per_trade_dll_usd: float,
        usd_per_pt: float,
) -> tuple:
    """Numpy-vectorised 3-leg exit state machine.  No Python bar loop.

    Args:
        hi_sl, lo_sl, cl_sl : 1m arrays already sliced to [entry_idx+1 : sess_end+1]
        direction            : +1 LONG  / -1 SHORT

    Returns:
        (pts, bucket, n_bars_held, partial_hit, target_hit, ext_hit, mae_pts, mfe_pts)
        pts is in points×contracts (multiply by usd_per_pt to get $).
    """
    nb = len(hi_sl)
    qty_run = qty - qty_part - qty_tgt

    if nb == 0:
        return 0.0, 'expired', 0, False, False, False, 0.0, 0.0

    # ── Flip SHORT to LONG perspective ────────────────────────────────────
    # In flipped space everything behaves as LONG; pts computed in flipped
    # space equal correct pts for the original direction.
    if direction == 1:
        hi, lo, cl = hi_sl, lo_sl, cl_sl
        ep = entry_price
        stp, pp, tp, xp = stop_price, partial_price, target_price, ext_price
        mae = max(0.0, ep - float(lo.min()))
        mfe = max(0.0, float(hi.max()) - ep)
    else:
        hi, lo, cl = -lo_sl, -hi_sl, -cl_sl
        ep = -entry_price
        stp = -stop_price; pp = -partial_price; tp = -target_price; xp = -ext_price
        mae = max(0.0, float(hi_sl.max()) - entry_price)
        mfe = max(0.0, entry_price - float(lo_sl.min()))

    INF = nb

    def _first(mask: np.ndarray) -> int:
        """Index of first True, or INF if none."""
        return int(np.argmax(mask)) if mask.any() else INF

    # ── Phase 1: stop vs partial (and per-trade emergency) ────────────────
    stop1 = _first(lo <= stp)
    part  = _first(hi >= pp)
    if per_trade_dll_usd > 0:
        emerg1 = _first((cl - ep) * qty * usd_per_pt < -per_trade_dll_usd)
    else:
        emerg1 = INF

    p1 = min(stop1, part, emerg1)

    if p1 == INF:
        # Nothing hit — session expires
        pts = qty * (cl[-1] - ep)
        return float(pts), 'expired', nb, False, False, False, mae, mfe

    if p1 == emerg1 and p1 <= part:
        pts = qty * (cl[p1] - ep)
        return float(pts), 'loss', p1 + 1, False, False, False, mae, mfe

    if p1 <= part and p1 == stop1:  # stop wins ties (Pine checks stop FIRST)
        pts = qty * (stp - ep)
        return float(pts), 'loss', p1 + 1, False, False, False, mae, mfe

    # ── Partial filled ────────────────────────────────────────────────────
    pts   = qty_part * (pp - ep)
    q_rem = qty - qty_part
    cur_stp = ep if be_at_partial else stp  # BE stop (in flipped space)

    if part + 1 >= nb:
        pts += q_rem * (cl[-1] - ep)
        return float(pts), 'partial', nb, True, False, False, mae, mfe

    hi2 = hi[part + 1:]; lo2 = lo[part + 1:]; cl2 = cl[part + 1:]
    nb2 = len(hi2)

    stop2  = _first(lo2 <= cur_stp)
    tgt    = _first(hi2 >= tp)
    emerg2 = _first((cl2 - ep) * q_rem * usd_per_pt < -per_trade_dll_usd) \
             if per_trade_dll_usd > 0 else nb2

    p2 = min(stop2, tgt, emerg2)

    if p2 == nb2:
        pts += q_rem * (cl2[-1] - ep)
        return float(pts), 'partial', nb, True, False, False, mae, mfe

    if p2 <= tgt and (p2 == stop2 or p2 == emerg2):
        # Stop or emergency hit after partial, before or on same bar as target
        pts += q_rem * (cl2[p2] - ep if p2 == emerg2 else cur_stp - ep)
        bucket = 'be_scratch' if cur_stp == ep else 'partial'
        return float(pts), bucket, part + 1 + p2 + 1, True, False, False, mae, mfe

    # ── Target filled ─────────────────────────────────────────────────────
    pts   += qty_tgt * (tp - ep)
    q_rem2 = q_rem - qty_tgt

    if q_rem2 == 0 or tgt + 1 >= nb2:
        if q_rem2 > 0:
            pts += q_rem2 * (cl2[-1] - ep)
        return float(pts), 'target_win', nb, True, True, False, mae, mfe

    hi3 = hi2[tgt + 1:]; lo3 = lo2[tgt + 1:]; cl3 = cl2[tgt + 1:]
    nb3 = len(hi3)

    ext3  = _first(hi3 >= xp)
    stop3 = _first(lo3 <= cur_stp)
    p3    = min(stop3, ext3)  # stop wins ties

    if p3 == nb3:
        pts += q_rem2 * (cl3[-1] - ep)
        return float(pts), 'target_win', nb, True, True, False, mae, mfe

    if p3 == ext3 and p3 != stop3:  # ext wins only if stop didn't also hit
        pts += q_rem2 * (xp - ep)
        return float(pts), 'target_win', part + 1 + tgt + 1 + ext3 + 1, True, True, True, mae, mfe

    # Runner stopped out (at BE) after target but before ext
    pts += q_rem2 * (cur_stp - ep)
    return float(pts), 'target_win', part + 1 + tgt + 1 + stop3 + 1, True, True, False, mae, mfe


# ── Signal detection + pre-processing ────────────────────────────────────────

def detect_signals(m1, m1_es=None,
                   min_fvg_bp=MIN_FVG_BP,
                   proximity_bp=PROXIMITY_BP):
    """Detect 1m-in-5m nested FVG signals.  No session/window gating here —
    that is applied in preprocess_signals() so the sweep can vary it cheaply.

    Returns a raw list of signal dicts (one per nested FVG candidate):
        {sig_ts, entry_idx, direction, smt,
         ltf_top, ltf_bot, htf_top, htf_bot,
         gap_ltf_pts, gap_htf_pts}
    """
    ltf = bs._with_close_ts(m1)
    htf = resample(m1, 5)

    print(f"  [detect] FVG scan: {len(m1['ts_ns']):,} 1m bars …")
    ltf_fvgs = find_fvgs(ltf, min_fvg_bp)
    htf_fvgs = find_fvgs(htf, min_fvg_bp)
    print(f"  [detect] {len(ltf_fvgs):,} 1m FVGs / {len(htf_fvgs):,} 5m FVGs")

    m1_ts = m1['ts_ns']
    bs._compute_mit_ts(htf_fvgs, m1['close'], ltf['ts_close_ns'])
    m1_hours = bs._ny_hours(m1_ts)
    hosts = bs._find_nested_hosts(ltf_fvgs, htf_fvgs, m1_ts, m1_hours, proximity_bp)

    raw = []
    for lf, host in zip(ltf_fvgs, hosts):
        if host is None:
            continue
        sig_ts    = lf['ts_ns']
        entry_idx = int(np.searchsorted(m1_ts, sig_ts, side='left'))
        if entry_idx >= len(m1_ts):
            continue
        if int(m1_ts[entry_idx]) - int(sig_ts) > 5 * 60 * 1_000_000_000:
            continue
        raw.append(dict(
            sig_ts=int(sig_ts),
            entry_idx=int(entry_idx),
            direction=int(lf['dir']),
            smt=bs._smt_at(m1_es, sig_ts, lf['dir']),
            ltf_top=float(lf['top']),  ltf_bot=float(lf['bot']),
            htf_top=float(host['top']), htf_bot=float(host['bot']),
            gap_ltf_pts=float(lf['gap_pts']),
            gap_htf_pts=float(host['gap_pts']),
        ))

    print(f"  [detect] {len(raw):,} raw nested signals (before session/window gates)")
    return raw


def preprocess_signals(raw_signals, m1, m1_hours, ct_hour, ct_date,
                       use_windows=True):
    """Gate raw signals once: session + window.
    Pre-compute sess_end for each surviving signal.

    Returns a list of augmented signal dicts ready for run_combo_fast().
    This is called ONCE before the parameter sweep.
    """
    m1_ts = m1['ts_ns']
    prepped = []
    last_dir = {1: -10**9, -1: -10**9}

    for sig in raw_signals:
        idx = sig['entry_idx']
        cth = int(ct_hour[idx])
        cday = str(ct_date[idx])

        if not _in_session(cth):
            continue
        if use_windows and not _in_window(cth):
            continue

        sess_end = bs._session_end_idx(m1_hours, idx, m1_ts)

        ets = pd.Timestamp(int(m1_ts[idx]), unit='ns', tz='UTC').tz_convert('America/New_York')
        prepped.append({
            **sig,
            'cth':      cth,
            'cday':     cday,
            'dow':      int(ets.dayofweek),
            'minute':   int(ets.minute),
            'yr':       int(ets.year),
            'date':     ets.strftime('%Y-%m-%d'),
            'session':  _session_of(cth),
            'window':   _window_label(cth),
            'sess_end': int(sess_end),
        })

    print(f"  [preprocess] {len(prepped):,} signals survive session+window+cooldown")
    return prepped


# ── Core combo simulation (fast, no I/O) ─────────────────────────────────────

def run_combo_fast(prepped, m1_arrays,
                   stop_pct, partial_pct, target_pct, ext_pct,
                   qty=DEFAULT_QTY,
                   qty_part=DEFAULT_QTY_PART,
                   qty_tgt=DEFAULT_QTY_TGT,
                   be_at_partial=DEFAULT_BE_AT_PART,
                   dll_usd=DEFAULT_DLL_USD,
                   per_trade_dll_usd=DEFAULT_PTDLL_USD,
                   usd_per_pt=DEFAULT_USD_PER_PT,
                   entry_mode='immediate',
                   cooldown=DEFAULT_COOLDOWN):
    """Simulate one (stop%, partial%, target%, ext%) configuration.

    Args:
        prepped      : output of preprocess_signals()
        m1_arrays    : (high, low, close) numpy arrays extracted from m1 dict
        entry_mode   : 'immediate', 'near_edge', 'middle', 'far_edge'

    Returns:
        list of trade-row dicts
    """
    high, low, close = m1_arrays
    rows        = []
    daily_usd   = {}    # cday → cumulative $ (DLL gate)
    blocked_until = -1  # block-while-open
    
    last_bull_idx = -10**9
    last_bear_idx = -10**9
    last_signal_idx = -10**9

    for sig in prepped:
        entry_idx = sig['entry_idx']
        direction = sig['direction']
        
        # Shared and Directional Cooldown (Pine Script Match)
        if entry_idx - last_signal_idx < cooldown:
            continue
        if direction == 1 and (entry_idx - last_bull_idx < cooldown):
            continue
        if direction == -1 and (entry_idx - last_bear_idx < cooldown):
            continue

        if entry_idx <= blocked_until:
            continue

        cday = sig['cday']
        if daily_usd.get(cday, 0.0) <= -abs(dll_usd):
            continue
            
        # Update trackers only if the trade was actually taken
        last_signal_idx = entry_idx
        if direction == 1:
            last_bull_idx = entry_idx
        else:
            last_bear_idx = entry_idx
        
        if entry_mode == 'immediate':
            entry_price = float(close[entry_idx])
        elif entry_mode == 'near_edge':
            entry_price = sig['ltf_top'] if direction == 1 else sig['ltf_bot']
        elif entry_mode == 'middle':
            entry_price = (sig['ltf_top'] + sig['ltf_bot']) / 2.0
        else: # far_edge
            entry_price = sig['ltf_bot'] if direction == 1 else sig['ltf_top']
            
        sess_end    = sig['sess_end']

        # Dynamic levels (% of entry price)
        stop_pts    = entry_price * stop_pct    / 100.0
        partial_pts = entry_price * partial_pct / 100.0
        target_pts  = entry_price * target_pct  / 100.0
        ext_pts     = entry_price * ext_pct     / 100.0

        if direction == 1:
            stop_price    = entry_price - stop_pts
            partial_price = entry_price + partial_pts
            target_price  = entry_price + target_pts
            ext_price     = entry_price + ext_pts
        else:
            stop_price    = entry_price + stop_pts
            partial_price = entry_price - partial_pts
            target_price  = entry_price - target_pts
            ext_price     = entry_price - ext_pts

        hi_sl = high [entry_idx + 1 : sess_end + 1]
        lo_sl = low  [entry_idx + 1 : sess_end + 1]
        cl_sl = close[entry_idx + 1 : sess_end + 1]

        pts, bucket, n_bars, part_hit, tgt_hit, ext_hit, mae, mfe = simulate_trade_fast(
            hi_sl, lo_sl, cl_sl, direction,
            entry_price, stop_price, partial_price, target_price, ext_price,
            qty, qty_part, qty_tgt,
            be_at_partial, per_trade_dll_usd, usd_per_pt,
        )

        usd = float(pts * usd_per_pt)
        blocked_until = entry_idx + n_bars
        daily_usd[cday] = daily_usd.get(cday, 0.0) + usd

        r_mult = float(pts / (stop_pts * qty)) if (stop_pts and qty) else 0.0

        rows.append({
            'date':          sig['date'],
            'ct_hour':       sig['cth'],
            'minute':        sig['minute'],
            'dow':           sig['dow'],
            'yr':            sig['yr'],
            'session':       sig['session'],
            'window':        sig['window'],
            'direction':     'LONG' if direction == 1 else 'SHORT',
            'ltf_top':       sig['ltf_top'],  'ltf_bot': sig['ltf_bot'],
            'htf_top':       sig['htf_top'],  'htf_bot': sig['htf_bot'],
            'gap_ltf_pts':   sig['gap_ltf_pts'],
            'gap_htf_pts':   sig['gap_htf_pts'],
            'smt':           bool(sig['smt']),
            'entry_price':   entry_price,
            'stop_price':    stop_price,
            'partial_price': partial_price,
            'target_price':  target_price,
            'ext_price':     ext_price,
            'stop_pts':      stop_pts,
            'target_pts':    target_pts,
            'stop_pct':      float(stop_pct),
            'partial_pct':   float(partial_pct),
            'target_pct':    float(target_pct),
            'ext_pct':       float(ext_pct),
            'bucket':        bucket,
            'partial_hit':   bool(part_hit),
            'target_hit':    bool(tgt_hit),
            'ext_hit':       bool(ext_hit),
            'pts':           float(pts),
            'usd':           usd,
            'r_multiple':    r_mult,
            'mae_pts':       float(mae),
            'mfe_pts':       float(mfe),
            'bars_held':     n_bars,
        })

    return rows


# ── Aggregation ───────────────────────────────────────────────────────────────

def agg(rows, stop_pct=None, partial_pct=None, target_pct=None, ext_pct=None, total_days=None):
    """Compute summary stats for a list of trade rows."""
    if not rows:
        return {}
    settled  = [r for r in rows if r['bucket'] != 'expired']
    wins     = [r for r in settled if r['bucket'] == 'target_win']
    losses   = [r for r in settled if r['bucket'] == 'loss']
    parts    = [r for r in settled if r['bucket'] in ('partial', 'be_scratch')]
    expired  = [r for r in rows    if r['bucket'] == 'expired']
    n = len(rows); ns = len(settled)

    max_cons_loss = 0
    curr_cons_loss = 0
    for r in rows:
        if r['bucket'] == 'loss':
            curr_cons_loss += 1
            if curr_cons_loss > max_cons_loss:
                max_cons_loss = curr_cons_loss
        elif r['bucket'] != 'expired':
            curr_cons_loss = 0
            
    avg_daily_setups = n / total_days if total_days else 0.0

    wr_honest = 100.0 * len(wins) / ns if ns else 0.0
    wr_v7     = 100.0 * (len(wins) + len(parts)) / ns if ns else 0.0
    ev_usd    = sum(r['usd'] for r in settled) / ns if ns else 0.0
    ev_r      = sum(r['r_multiple'] for r in settled) / ns if ns else 0.0
    pos_r     = sum(r['r_multiple'] for r in settled if r['r_multiple'] > 0)
    neg_r     = -sum(r['r_multiple'] for r in settled if r['r_multiple'] < 0)
    pf        = pos_r / neg_r if neg_r else 0.0
    total_usd = sum(r['usd'] for r in rows)

    cum = 0.0; peak = 0.0; max_dd = 0.0
    for r in rows:
        cum  += r['usd']
        peak  = max(peak, cum)
        max_dd = max(max_dd, peak - cum)

    out = dict(
        n=n, n_settled=ns,
        wins=len(wins), losses=len(losses),
        partials=len(parts), expired=len(expired),
        wr_honest=round(wr_honest, 2),
        wr_v7=round(wr_v7, 2),
        ev_r=round(ev_r, 4),
        ev_usd=round(ev_usd, 2),
        pos_r=pos_r,
        neg_r=neg_r,
        pf=round(pf, 3),
        total_usd=round(total_usd, 2),
        max_drawdown_usd=round(max_dd, 2),
        max_cons_loss=max_cons_loss,
        avg_daily_setups=round(avg_daily_setups, 2),
    )
    if stop_pct is not None:
        out.update(stop_pct=stop_pct, partial_pct=partial_pct,
                   target_pct=target_pct, ext_pct=ext_pct)
    return out

def agg_chunked(rows, stop_pct=None, partial_pct=None, target_pct=None, ext_pct=None, total_days=None):
    """Aggregate rows grouped by (session, direction, smt). Drawdown is omitted."""
    from collections import defaultdict
    groups = defaultdict(list)
    for r in rows:
        key = (r.get('session', 'OTHER'), r.get('direction', 'LONG'), r.get('smt', False))
        groups[key].append(r)
    
    out_list = []
    for (sess, d, smt), chunk in groups.items():
        st = agg(chunk, total_days=total_days)
        # remove drawdown and max_cons_loss as they aren't strictly aggregable
        st.pop('max_drawdown_usd', None)
        st.pop('max_cons_loss', None)
        
        # add grouping keys
        st['session'] = sess
        st['direction'] = d
        st['smt'] = smt
        if stop_pct is not None:
            st.update(stop_pct=stop_pct, partial_pct=partial_pct, target_pct=target_pct, ext_pct=ext_pct)
        out_list.append(st)
        
    return out_list
