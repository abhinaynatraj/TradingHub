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


def _session_end_idx(m1_hours, entry_idx):
    """First 1m bar index at/after entry whose NY hour is in [16,18) (force-close).

    Uses a precomputed per-bar NY hour array. Returns the last index if no such
    bar exists before the data ends.
    """
    n = len(m1_hours)
    # vectorized: first index >= entry_idx where 16 <= hour < 18
    rel = np.nonzero((m1_hours[entry_idx:] >= 16) & (m1_hours[entry_idx:] < 18))[0]
    if len(rel):
        return entry_idx + int(rel[0])
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
        # admit HTF gaps formed at/before this signal
        while ptr[d] < len(gaps) and gaps[ptr[d]]['ts_ns'] <= sig:
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


def build_pairing(key, ltf_min, htf_min, m1, m1_es):
    """Detect nested FVGs for one TF pair and simulate. Returns (rows, n_suppressed)."""
    ltf = m1 if ltf_min == 1 else resample(m1, ltf_min)
    htf = resample(m1, htf_min)

    ltf_fvgs = find_fvgs(ltf, MIN_FVG_BP)
    htf_fvgs = find_fvgs(htf, MIN_FVG_BP)

    htf_close = htf['close']
    htf_ts = htf['ts_ns']
    _compute_mit_ts(htf_fvgs, htf_close, htf_ts)

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
        sig_ts = lf['ts_ns']
        sig_1m_idx = int(np.searchsorted(m1_ts, sig_ts, side='left'))
        # session gate using the precomputed hour at the signal bar
        if sig_1m_idx >= len(m1_hours) or int(m1_hours[sig_1m_idx]) not in SESSION_HOURS:
            continue
        if sig_1m_idx - last_bar_for_dir[lf['dir']] < COOLDOWN_BARS:
            n_suppressed += 1
            continue
        last_bar_for_dir[lf['dir']] = sig_1m_idx

        entry_idx = sig_1m_idx + 1
        if entry_idx >= len(m1_ts):
            continue
        # Entry is the NEXT bar's open. If that bar lands at/after the 16:00 ET
        # session close (out of SESSION_HOURS), skip — a trade entering at the
        # expiry boundary has no session time to resolve.
        if int(m1_hours[entry_idx]) not in SESSION_HOURS:
            continue
        entry_price = float(m1['open'][entry_idx])
        direction = lf['dir']

        sess_end = _session_end_idx(m1_hours, entry_idx)
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
