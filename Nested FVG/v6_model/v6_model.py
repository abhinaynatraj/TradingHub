"""Faithful backtest port of Kelli's 'Nested FVG Pro' v6 indicator.

THE indicator IS the model. This is a line-for-line port of the Pine's actual
control flow at its DEFAULT settings — not a re-derivation. It reuses only the FVG
geometry primitive (find_fvgs == the Pine's gap math); everything else (session,
windows, gating, multi-contract scale-out, BE-at-partial, block-while-open, loss
limits, outcome accounting) mirrors the Pine.

v6 defaults replicated:
  - Entry: Immediate  -> enter at the signal bar's CLOSE (confirmed 1m bar).
  - Stop 20, Partial 20, Target 45, Extended 60 (points).
  - 3 contracts: 1 at partial, 1 at target, 1 runner to extended.
  - Break-even at partial: once the partial fills, stop on the remaining 2 -> entry.
  - Block new trades while one is open (one position at a time); 30-bar cooldown.
  - Session 1900-1600 Chicago; purge gaps/state at session open.
  - Trading windows (CT): 7-9 PM, 1-2 AM, 6-11 AM, 12-2 PM.
  - Daily loss limit $400; per-trade max loss $150 (emergency exit on bar close).
  - MNQ $2/pt. NQ price data.

Time handling: bars are converted to America/Chicago via pandas (full DST). The DB is
stored America/Toronto (Eastern); CT is the Pine's reference, so we evaluate the
session + windows in CT exactly as the indicator does.

Outputs both win-rate definitions on identical trades:
  - WR_v6  (partials + BE-scratches counted as "wins", as the Pine's tables do)
  - WR_honest (full target reached only)
plus the real $ expectancy per trade.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ENGINE = Path(__file__).parent.parent / 'engine'
sys.path.insert(0, str(ENGINE))

from constants import MIN_FVG_BP, PROXIMITY_BP, COOLDOWN_BARS
from resampling import resample
from detect import find_fvgs, is_nested
import build_stats as bs

# ── v6 default inputs ────────────────────────────────────────────────────────
STOP_PTS    = 20.0
PARTIAL_PTS = 20.0
TARGET_PTS  = 45.0
EXT_PTS     = 60.0
POS_QTY     = 3
QTY_PART    = 1
QTY_TGT     = 1
QTY_RUN     = POS_QTY - QTY_PART - QTY_TGT      # 1 runner
BE_AT_PARTIAL = True
USD_PER_PT  = 2.0                               # MNQ
DLL_USD     = 400.0                             # daily loss limit
PER_TRADE_DLL_USD = 150.0                       # per-trade emergency exit
COOLDOWN    = COOLDOWN_BARS                      # 30


def _ct_parts(ts_ns_array):
    """Vectorized America/Chicago hour + calendar date string for every bar."""
    idx = pd.DatetimeIndex(pd.to_datetime(ts_ns_array, utc=True)).tz_convert('America/Chicago')
    return idx.hour.to_numpy(), idx.strftime('%Y-%m-%d').to_numpy(), idx


def _in_window(ct_h):
    # matches v6: in_7pm 19-20, in_1am 1, in_6am 6-10, in_12pm 12-13
    return (19 <= ct_h <= 20) or (ct_h == 1) or (6 <= ct_h <= 10) or (12 <= ct_h <= 13)


def _in_session(ct_h):
    # Pine session "1900-1600" Chicago = 19:00 .. 15:59 CT (wraps midnight).
    # In-session hours: 19,20,21,22,23,0..15.
    return ct_h >= 19 or ct_h <= 15


def simulate_trade(m1, entry_idx, direction, sess_end_idx):
    """3-contract scale-out with BE-at-partial and a per-trade $ emergency stop.
    Returns realized points (summed over contracts), $ , outcome bucket, exit_idx."""
    high = m1['high']; low = m1['low']; close = m1['close']
    e = float(close[entry_idx])     # Immediate entry = signal bar close
    if direction == 1:
        stop = e - STOP_PTS; part = e + PARTIAL_PTS; tgt = e + TARGET_PTS; ext = e + EXT_PTS
    else:
        stop = e + STOP_PTS; part = e - PARTIAL_PTS; tgt = e - TARGET_PTS; ext = e - EXT_PTS

    cur_stop = stop
    partial_hit = False
    target_hit = False
    q_open = POS_QTY
    pts = 0.0
    bucket = None
    exit_idx = entry_idx
    per_trade_pts = PER_TRADE_DLL_USD / USD_PER_PT   # 75 pts of adverse * contracts

    # outcomes resolve starting the bar AFTER entry (entry filled at this bar's close)
    for i in range(entry_idx + 1, min(sess_end_idx, len(high) - 1) + 1):
        exit_idx = i
        hi = high[i]; lo = low[i]; c = close[i]

        # per-trade emergency exit (checked on bar close, like the Pine)
        unreal = ((c - e) if direction == 1 else (e - c)) * q_open
        if unreal * USD_PER_PT < -PER_TRADE_DLL_USD:
            pts += q_open * ((c - e) if direction == 1 else (e - c))
            bucket = 'loss'
            q_open = 0; break

        if direction == 1:
            if lo <= cur_stop:
                pts += q_open * (cur_stop - e)
                bucket = ('loss' if not partial_hit else ('be_scratch' if cur_stop == e else 'partial'))
                q_open = 0; break
            if not partial_hit and hi >= part:
                pts += QTY_PART * (part - e); partial_hit = True; q_open -= QTY_PART
                if BE_AT_PARTIAL: cur_stop = e
            if partial_hit and not target_hit and hi >= tgt:
                pts += QTY_TGT * (tgt - e); target_hit = True; q_open -= QTY_TGT
            if target_hit and hi >= ext:
                pts += QTY_RUN * (ext - e); q_open -= QTY_RUN; bucket = 'target_win'; break
        else:
            if hi >= cur_stop:
                pts += q_open * (e - cur_stop)
                bucket = ('loss' if not partial_hit else ('be_scratch' if cur_stop == e else 'partial'))
                q_open = 0; break
            if not partial_hit and lo <= part:
                pts += QTY_PART * (e - part); partial_hit = True; q_open -= QTY_PART
                if BE_AT_PARTIAL: cur_stop = e
            if partial_hit and not target_hit and lo <= tgt:
                pts += QTY_TGT * (e - tgt); target_hit = True; q_open -= QTY_TGT
            if target_hit and lo <= ext:
                pts += QTY_RUN * (e - ext); q_open -= QTY_RUN; bucket = 'target_win'; break

    if bucket is None:
        # session ended with legs still open: Pine purges at session open -> close flat
        cpx = float(close[min(sess_end_idx, len(close) - 1)])
        pts += q_open * ((cpx - e) if direction == 1 else (e - cpx))
        bucket = 'target_win' if target_hit else ('partial' if partial_hit else 'expired')
    return dict(pts=pts, usd=pts * USD_PER_PT, bucket=bucket, exit_idx=exit_idx,
                partial_hit=partial_hit, target_hit=target_hit)


def run():
    m1 = bs.load_1m('nq_1m')
    ts = m1['ts_ns']
    ct_hour, ct_date, _ = _ct_parts(ts)
    m1['_ny_hours'] = bs._ny_hours(ts)   # for the session-end (16:00) helper

    # detection (the Pine's geometry): 1m gaps nested in 5m gaps
    ltf = bs._with_close_ts(m1)
    htf = resample(m1, 5)
    ltf_fvgs = find_fvgs(ltf, MIN_FVG_BP)
    htf_fvgs = find_fvgs(htf, MIN_FVG_BP)
    bs._compute_mit_ts(htf_fvgs, htf['close'], htf['ts_close_ns'])
    hosts = bs._find_nested_hosts(ltf_fvgs, htf_fvgs)

    rows = []
    buckets = dict(target_win=0, partial=0, be_scratch=0, loss=0, expired=0)
    tot_pts = 0.0
    daily_pts = {}                 # ct_date -> running pts (for DLL gate)
    last_dir = {1: -10**9, -1: -10**9}
    blocked_until = -1             # block-while-open: index of current trade's exit

    for lf, host in zip(ltf_fvgs, hosts):
        if host is None:
            continue
        sig_ts = lf['ts_ns']
        entry_idx = int(np.searchsorted(ts, sig_ts, side='left'))
        if entry_idx >= len(ts):
            continue
        # gap guard (stale signal across a data gap)
        if int(ts[entry_idx]) - int(sig_ts) > 5 * 60 * 1_000_000_000:
            continue
        # block-while-open
        if entry_idx <= blocked_until:
            continue
        cth = int(ct_hour[entry_idx]); cday = ct_date[entry_idx]
        # gates: session + trading window
        if not _in_session(cth) or not _in_window(cth):
            continue
        # daily loss limit (no new signals once daily losses reach the limit)
        if daily_pts.get(cday, 0.0) * USD_PER_PT <= -DLL_USD:
            continue
        # cooldown per direction
        if entry_idx - last_dir[lf['dir']] < COOLDOWN:
            continue
        last_dir[lf['dir']] = entry_idx

        sess_end = bs._session_end_idx(m1['_ny_hours'], entry_idx, ts)
        r = simulate_trade(m1, entry_idx, lf['dir'], sess_end)
        blocked_until = r['exit_idx']                     # block until this trade closes
        buckets[r['bucket']] += 1
        tot_pts += r['pts']
        daily_pts[cday] = daily_pts.get(cday, 0.0) + r['pts']
        rows.append(dict(date=cday, ct_hour=cth, direction='LONG' if lf['dir'] == 1 else 'SHORT',
                         bucket=r['bucket'], pts=r['pts'], usd=r['usd']))

    return rows, buckets, tot_pts


def report(rows, buckets, tot_pts):
    n = len(rows)
    settled = buckets['target_win'] + buckets['partial'] + buckets['be_scratch'] + buckets['loss']
    inflated_wins = buckets['target_win'] + buckets['partial'] + buckets['be_scratch']
    wr_v6 = 100.0 * inflated_wins / settled if settled else 0.0
    wr_honest = 100.0 * buckets['target_win'] / settled if settled else 0.0
    ev_usd = (tot_pts * USD_PER_PT) / n if n else 0.0

    print("=" * 64)
    print("NESTED FVG PRO v6 — faithful port @ default settings (NQ, MNQ $2/pt)")
    print("=" * 64)
    print(f"trades: {n:,}")
    print(f"buckets: target_win={buckets['target_win']:,}  partial={buckets['partial']:,}  "
          f"be_scratch={buckets['be_scratch']:,}  loss={buckets['loss']:,}  expired={buckets['expired']:,}")
    print(f"total: {tot_pts:,.1f} pts*contracts   ${tot_pts*USD_PER_PT:,.0f}")
    print()
    print(f"WR (v6 tables — partials + BE count as wins): {wr_v6:5.1f}%")
    print(f"WR (honest — full target reached only):       {wr_honest:5.1f}%")
    print(f"REAL expectancy per trade: ${ev_usd:+.2f}")
    print()
    # per-CT-window breakdown
    df = pd.DataFrame(rows)
    if len(df):
        def win_lbl(h):
            if 19 <= h <= 20: return '7-9PM CT'
            if h == 1: return '1-2AM CT'
            if 6 <= h <= 10: return '6-11AM CT'
            if 12 <= h <= 13: return '12-2PM CT'
            return 'other'
        df['window'] = df['ct_hour'].map(win_lbl)
        g = df.groupby('window').agg(n=('usd', 'size'), total_usd=('usd', 'sum'),
                                     ev_usd=('usd', 'mean')).round(2)
        print("Per trading-window:")
        print(g.to_string())
    return dict(n=n, buckets=buckets, wr_v6=round(wr_v6, 1), wr_honest=round(wr_honest, 1),
                ev_usd=round(ev_usd, 2), total_usd=round(tot_pts * USD_PER_PT, 0))


if __name__ == '__main__':
    rows, buckets, tot_pts = run()
    report(rows, buckets, tot_pts)
