"""Orchestrator: load 1m bars from the shared DuckDB, detect nested FVGs per TF
pair, simulate trades, and write one parquet per pairing + a slim manifest.json.

Run:
    python3 engine/build_stats.py                 # all pairings, NQ + ES, SMT on
    python3 engine/build_stats.py --pairings 1m_5m
    python3 engine/build_stats.py --no-smt
"""
import argparse
import datetime
import json

import numpy as np
import pandas as pd

# Imports work both as a script (cwd=engine/, `python3 build_stats.py`) and as a
# package module (`from engine.build_stats import ...`) for tests.
try:
    from constants import (DB_PATH, DATA_DIR, PAIRINGS, STOP_PTS, PARTIAL_PTS,
                           TARGET_PTS, EXT_PTS, MIN_FVG_BP, PROXIMITY_BP, COOLDOWN_BARS,
                           POINT_VALUE_USD, SESSION_HOURS, SESSION_END_HOUR, OUTCOMES)
    from resampling import resample
    from detect import find_fvgs, is_mitigated, is_nested
    from simulate import simulate_trade, pnl_to_usd
    from parquet_writer import write_trades_parquet
except ModuleNotFoundError:
    from engine.constants import (DB_PATH, DATA_DIR, PAIRINGS, STOP_PTS, PARTIAL_PTS,
                                  TARGET_PTS, EXT_PTS, MIN_FVG_BP, PROXIMITY_BP, COOLDOWN_BARS,
                                  POINT_VALUE_USD, SESSION_HOURS, SESSION_END_HOUR, OUTCOMES)
    from engine.resampling import resample
    from engine.detect import find_fvgs, is_mitigated, is_nested
    from engine.simulate import simulate_trade, pnl_to_usd
    from engine.parquet_writer import write_trades_parquet


def load_1m(table):
    import duckdb
    print(f"[load] {table} from {DB_PATH}")
    con = duckdb.connect(str(DB_PATH), read_only=True)
    df = con.execute(f"""
        SELECT CAST(EXTRACT(EPOCH FROM timestamp) * 1e9 AS BIGINT) AS ts_ns,
               open, high, low, close
        FROM {table} ORDER BY timestamp
    """).fetchdf()
    con.close()
    print(f"  {len(df):,} bars")
    return dict(
        ts_ns=df['ts_ns'].to_numpy(dtype='int64'),
        open=df['open'].to_numpy(dtype='float64'),
        high=df['high'].to_numpy(dtype='float64'),
        low=df['low'].to_numpy(dtype='float64'),
        close=df['close'].to_numpy(dtype='float64'),
    )


def _ny(ts_ns):
    return pd.Timestamp(int(ts_ns), tz='UTC').tz_convert('America/New_York')


def _session_of(hour):
    if hour >= 18 or hour < 2:
        return 'ASIA'
    if 2 <= hour <= 7:
        return 'LONDON'
    if 8 <= hour <= 15:
        return 'NY'
    return 'OTHER'


_SESSION_MAX_NS = np.int64(22 * 60 * 60 * 1_000_000_000)  # 22h: 18:00 -> 16:00 next day


def _session_end_idx(m1_hours, entry_idx, m1_ts=None):
    """First 1m bar index at/after entry whose NY hour is in [16,18) (force-close).

    Gap-safe: only considers bars within 22 wall-clock hours of entry (one Globex
    session is 18:00->16:00 = 22h). This prevents latching onto a LATER day's 16:00
    when the entry day's close is missing from the data, or jumping a multi-day gap.
    Returns the last in-window bar if no 16:00 bar exists within the horizon.
    """
    n = len(m1_hours)
    if m1_ts is not None:
        horizon = m1_ts[entry_idx] + _SESSION_MAX_NS
        # last index whose ts is within the 22h horizon
        hi = int(np.searchsorted(m1_ts, horizon, side='right'))
        hi = min(hi, n)
    else:
        hi = n
    seg = m1_hours[entry_idx:hi]
    rel = np.nonzero((seg >= 16) & (seg < 18))[0]
    if len(rel):
        return entry_idx + int(rel[0])
    # no in-window close found: expire at the last bar within the horizon
    if hi - 1 > entry_idx:
        return hi - 1
    return n - 1


def _smt_at(m1_es, ts_ns, direction):
    """Crude NQ-ES divergence flag: ES did NOT confirm the same gap direction.
    Returns False if ES data unavailable."""
    if m1_es is None:
        return False
    idx = int(np.searchsorted(m1_es['ts_ns'], ts_ns, side='right')) - 1
    if idx < 2:
        return False
    es_up = m1_es['close'][idx] > m1_es['close'][idx - 2]
    return (direction == 1 and not es_up) or (direction == -1 and es_up)


def _ny_hours(ts_ns):
    """Vectorized NY hour-of-day for an array of ns timestamps (one pass)."""
    idx = pd.DatetimeIndex(pd.to_datetime(ts_ns, utc=True)).tz_convert('America/New_York')
    return idx.hour.to_numpy()


def _compute_mit_ts(htf_fvgs, htf_close, htf_ts):
    """Vectorized mitigation: each HTF gap's first close-through ts after formation.

    Replaces the per-gap Python forward-scan (O(gaps * bars)) — still per-gap but
    each lookup is a numpy nonzero over the post-formation slice. Sets g['mit_ts'].
    """
    n = len(htf_close)
    for g in htf_fvgs:
        i0 = g['idx'] + 1
        g['mit_ts'] = None
        if i0 >= n:
            continue
        if g['dir'] == 1:
            hits = np.nonzero(htf_close[i0:] < g['bot'])[0]
        else:
            hits = np.nonzero(htf_close[i0:] > g['top'])[0]
        if len(hits):
            g['mit_ts'] = int(htf_ts[i0 + hits[0]])


def _find_nested_hosts(ltf_fvgs, htf_fvgs, proximity_bp=PROXIMITY_BP):
    """Sweep-line nesting: for each LTF FVG, the first live, same-direction,
    containing HTF gap (in HTF formation order). O(LTF * live-set) instead of
    O(LTF * HTF). Verified identical to the brute-force reference (see test).

    Both lists are already time-sorted by formation (find_fvgs scans bars in order).
    Returns a list parallel to ltf_fvgs: the host gap dict, or None.
    """
    by_dir = {1: [g for g in htf_fvgs if g['dir'] == 1],
              -1: [g for g in htf_fvgs if g['dir'] == -1]}
    ptr = {1: 0, -1: 0}
    live = {1: [], -1: []}
    hosts = []
    for lf in ltf_fvgs:
        sig = lf['ts_ns']
        d = lf['dir']
        gaps = by_dir[d]
        # admit HTF gaps CONFIRMED strictly before this signal confirms.
        # Both ts_ns are now bar-CLOSE (confirmation) times; strict `<` forbids an
        # HTF host that confirms on the same bar/instant as the LTF signal.
        while ptr[d] < len(gaps) and gaps[ptr[d]]['ts_ns'] < sig:
            live[d].append(gaps[ptr[d]])
            ptr[d] += 1
        # drop gaps mitigated at/before this signal (preserve formation order)
        live[d] = [g for g in live[d] if g['mit_ts'] is None or g['mit_ts'] > sig]
        host = None
        for hg in live[d]:
            if is_nested(lf, hg, proximity_bp):
                host = hg
                break
        hosts.append(host)
    return hosts


def _with_close_ts(m1):
    """Give a native 1m dict a `ts_close_ns` = each bar's close instant (the next
    bar's start), so find_fvgs stamps 1m FVGs at confirmation-close, consistent
    with resampled series. The last bar's close is estimated as +1 minute."""
    ts = m1['ts_ns']
    NS_MIN = np.int64(60_000_000_000)
    close = np.empty_like(ts)
    close[:-1] = ts[1:]
    close[-1] = ts[-1] + NS_MIN
    out = dict(m1)
    out['ts_close_ns'] = close
    return out


def build_pairing(key, ltf_min, htf_min, m1, m1_es):
    """Detect nested FVGs for one TF pair and simulate. Returns (rows, n_suppressed)."""
    ltf = _with_close_ts(m1) if ltf_min == 1 else resample(m1, ltf_min)
    htf = resample(m1, htf_min)

    ltf_fvgs = find_fvgs(ltf, MIN_FVG_BP)
    htf_fvgs = find_fvgs(htf, MIN_FVG_BP)

    htf_close = htf['close']
    # Mitigation must be timestamped at the mitigating bar's CLOSE (when it becomes
    # known), not its start — same look-ahead concern as FVG confirmation.
    htf_close_ts = htf['ts_close_ns']
    _compute_mit_ts(htf_fvgs, htf_close, htf_close_ts)

    # Precompute NY hour for every 1m bar once (used for session gating + expiry).
    m1_ts = m1['ts_ns']
    m1_hours = _ny_hours(m1_ts)

    # Nesting hosts for all LTF FVGs via the sweep (parallel to ltf_fvgs).
    hosts = _find_nested_hosts(ltf_fvgs, htf_fvgs)

    rows = []
    n_suppressed = 0
    last_bar_for_dir = {1: -10**9, -1: -10**9}

    for lf, host in zip(ltf_fvgs, hosts):
        if host is None:
            continue
        # sig_ts is the FVG's CONFIRMATION-CLOSE time. The entry bar is the first
        # 1m bar at/after that close — its open is the first tradeable price once
        # the gap is known. (No +1: searchsorted already lands on the post-close bar.)
        sig_ts = lf['ts_ns']
        entry_idx = int(np.searchsorted(m1_ts, sig_ts, side='left'))
        if entry_idx >= len(m1_ts):
            continue
        # Gap guard: if the first post-close 1m bar is far from the FVG's confirmation
        # time (a data gap straddles it — weekend/holiday/dropout), the signal is
        # stale and not tradeable. Require the entry bar within the HTF bucket width.
        if int(m1_ts[entry_idx]) - int(sig_ts) > htf_min * 60 * 1_000_000_000:
            continue
        # Skip if the entry bar is out of session (e.g. at/after the 16:00 ET close)
        # — a trade entering at the expiry boundary has no session time to resolve.
        # Done BEFORE cooldown so out-of-session signals don't consume a cooldown slot.
        if int(m1_hours[entry_idx]) not in SESSION_HOURS:
            continue
        if entry_idx - last_bar_for_dir[lf['dir']] < COOLDOWN_BARS:
            n_suppressed += 1
            continue
        last_bar_for_dir[lf['dir']] = entry_idx
        entry_price = float(m1['open'][entry_idx])
        direction = lf['dir']

        sess_end = _session_end_idx(m1_hours, entry_idx, m1_ts)
        sim = simulate_trade(m1, entry_idx, entry_price, direction, sess_end,
                             STOP_PTS, PARTIAL_PTS, TARGET_PTS, EXT_PTS)

        ets = _ny(m1_ts[entry_idx])
        if direction == 1:
            stop_price = entry_price - STOP_PTS
            partial_price = entry_price + PARTIAL_PTS
            target_price = entry_price + TARGET_PTS
        else:
            stop_price = entry_price + STOP_PTS
            partial_price = entry_price - PARTIAL_PTS
            target_price = entry_price - TARGET_PTS

        rows.append(dict(
            instrument='NQ',
            direction='LONG' if direction == 1 else 'SHORT',
            entry_ts_ns=int(m1_ts[entry_idx]),
            date=ets.strftime('%Y-%m-%d'),
            yr=ets.year, dow=(ets.weekday() + 1) % 7,
            hour=ets.hour, minute=ets.minute,
            session=_session_of(ets.hour),
            entry_price=entry_price, stop_price=stop_price,
            partial_price=partial_price, target_price=target_price,
            htf_top=host['top'], htf_bot=host['bot'],
            ltf_top=lf['top'], ltf_bot=lf['bot'],
            gap_ltf_pts=lf['gap_pts'], gap_htf_pts=host['gap_pts'],
            outcome=sim['outcome'], partial_hit=sim['partial_hit'],
            reached_ext=sim['reached_ext'],
            pnl_pts=sim['pnl_pts'], r=sim['r'],
            pnl_usd=pnl_to_usd(sim['pnl_pts'], POINT_VALUE_USD),
            mae_pts=sim['mae_pts'], mfe_pts=sim['mfe_pts'],
            bars_held=sim['bars_held'],
            smt=_smt_at(m1_es, sig_ts, direction),
        ))
    return rows, n_suppressed


def _agg(rows):
    settled = [r for r in rows if r['outcome'] != 'expired']
    wins = sum(1 for r in settled if r['outcome'] == 'win')
    losses = sum(1 for r in settled if r['outcome'] == 'loss')
    scratches = sum(1 for r in settled if r['outcome'] == 'scratch')
    expired = sum(1 for r in rows if r['outcome'] == 'expired')
    n_settled = len(settled)
    wr = (wins / n_settled * 100.0) if n_settled else 0.0
    ev_r = (sum(r['r'] for r in settled) / n_settled) if n_settled else 0.0
    pos = sum(r['r'] for r in settled if r['r'] > 0)
    neg = -sum(r['r'] for r in settled if r['r'] < 0)
    pf = (pos / neg) if neg else 0.0
    avg_usd = (sum(r['pnl_usd'] for r in settled) / n_settled) if n_settled else 0.0
    return dict(n=len(rows), wr=round(wr, 2), ev_r=round(ev_r, 4), pf=round(pf, 3),
                avg_pnl_usd=round(avg_usd, 2),
                wins=wins, losses=losses, scratches=scratches, expired=expired)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--pairings', nargs='+', default=list(PAIRINGS.keys()))
    p.add_argument('--no-smt', action='store_true')
    args = p.parse_args()

    DATA_DIR.mkdir(exist_ok=True)
    m1 = load_1m('nq_1m')
    m1_es = None if args.no_smt else load_1m('es_1m')

    manifest = dict(
        schema_version=1,
        run_timestamp_utc=datetime.datetime.now(datetime.UTC).isoformat(),
        date_range_start=_ny(m1['ts_ns'][0]).strftime('%Y-%m-%d'),
        date_range_end=_ny(m1['ts_ns'][-1]).strftime('%Y-%m-%d'),
        instrument_pricing='NQ price action, MNQ sized ($2/pt)',
        constants=dict(STOP_PTS=STOP_PTS, PARTIAL_PTS=PARTIAL_PTS, TARGET_PTS=TARGET_PTS,
                       EXT_PTS=EXT_PTS, MIN_FVG_BP=MIN_FVG_BP, PROXIMITY_BP=PROXIMITY_BP,
                       COOLDOWN_BARS=COOLDOWN_BARS, SESSION='18:00->16:00 ET',
                       POINT_VALUE_USD=POINT_VALUE_USD),
        pairings={},
    )

    for key in args.pairings:
        ltf_min, htf_min = PAIRINGS[key]
        print(f"[pairing] {key}  ltf={ltf_min}m htf={htf_min}m")
        rows, n_supp = build_pairing(key, ltf_min, htf_min, m1, m1_es)
        for r in rows:
            assert r['outcome'] in OUTCOMES, r['outcome']
            assert r['hour'] in SESSION_HOURS, f"out-of-session trade hour {r['hour']}"
        fname = f"trades_{key}.parquet"
        write_trades_parquet(rows, str(DATA_DIR / fname))
        if len(rows) < 20:
            print(f"  WARNING: only {len(rows)} trades for {key}")
        manifest['pairings'][key] = dict(
            file=fname, n_trades=len(rows), n_suppressed_cooldown=n_supp,
            agg=_agg(rows),
        )
        print(f"  {len(rows)} trades, {n_supp} suppressed")

    with open(DATA_DIR / 'manifest.json', 'w') as f:
        json.dump(manifest, f, indent=2)
    print(f"[done] wrote manifest + {len(args.pairings)} parquet(s) to {DATA_DIR}")


if __name__ == '__main__':
    main()
