#!/usr/bin/env python3
"""npg_stats.py - NPG Sweep Engine v1.0

Detects npg-spec Wick Lick + CISD setups across NQ (or ES) 1m data.
Profiles: series_multi (4 partial exits) and raw_measure (no SL/TP).
Filters: Silver, Bias (Bull/Bear), Body-vs-Wick CISD, SMT.
Pairings: 1H_5M, 4H_15M, D_1H.

Usage:
    python3 engine/npg_stats.py
    python3 engine/npg_stats.py --pairings 1H_5M
    python3 engine/npg_stats.py --table es_1m
"""
import argparse
import sys
import json
from pathlib import Path
import numpy as np

from resampling import resample
from wick_lick import detect_wick_licks
from cisd_npg import find_cisd_npg_in_window
from projections import compute_targets, resolve_series_multi, resolve_raw_measure
from filters import is_silver, candle_of_day, is_smt
from aggregation import (agg, reach_rates, by_hour, by_dow, by_session,
                          by_direction, filter_combinations)


DB_PATH = Path(__file__).parent.parent.parent / 'Fractal Sweep' / 'candle_science.duckdb'
OUT_PATH = Path(__file__).parent.parent / 'npg_stats.json'

PAIRINGS = {
    '1H_5M':  dict(sweep_tf_min=60,   cisd_tf_min=5),
    '4H_15M': dict(sweep_tf_min=240,  cisd_tf_min=15),
    'D_1H':   dict(sweep_tf_min=1440, cisd_tf_min=60),
}

PROFILES = ['series_multi', 'raw_measure']
MULTIPLIERS = [0.5, 1.0, 1.5, 2.0]
MIN_RISK_PTS = 3.0
MAX_RISK_PTS = 112.5
OUTCOME_MAX_BARS = 1440


def run_pairing(m1, sweep_tf_min, cisd_tf_min, profile='series_multi',
                body_confirm=True, multipliers=None,
                m1_es=None):
    """Run one pairing x one profile and return trades + summary.

    Args:
        m1: dict of NQ 1m arrays (ts_ns, open, high, low, close)
        m1_es: optional dict of ES 1m arrays for SMT computation

    Returns:
        dict(trades=[...], summary={...})
    """
    multipliers = multipliers or MULTIPLIERS
    sweep_tf = resample(m1, sweep_tf_min)
    cisd_tf = resample(m1, cisd_tf_min)
    sweep_es = resample(m1_es, sweep_tf_min) if m1_es is not None else None

    events = detect_wick_licks(sweep_tf)
    trades = []
    seen_anchors = set()

    for ev in events:
        anchor_idx = ev['sweep_idx']
        if anchor_idx in seen_anchors:
            continue
        seen_anchors.add(anchor_idx)

        # Find anchor close ts (= start of next HTF candle)
        if anchor_idx + 1 >= len(sweep_tf['ts_ns']):
            # Use the resampler's bucket close if available
            if 'ts_close_ns' in sweep_tf:
                anchor_close_ts = int(sweep_tf['ts_close_ns'][anchor_idx])
            else:
                continue
        else:
            anchor_close_ts = int(sweep_tf['ts_ns'][anchor_idx + 1])

        # Locate c2_idx in the CISD-TF: bar that contains the swept extreme price
        # We search within the sweep HTF candle's window in the CISD TF
        sweep_open_ts = int(sweep_tf['ts_ns'][anchor_idx])
        cisd_window_mask = (cisd_tf['ts_ns'] >= sweep_open_ts) & (cisd_tf['ts_ns'] < anchor_close_ts)
        idxs = np.where(cisd_window_mask)[0]
        if len(idxs) == 0:
            continue

        # c2_idx = first CISD-TF bar whose high (SHORT) or low (LONG) equals the sweep extreme
        c2_idx = None
        for i in idxs:
            if ev['direction'] == 'SHORT' and cisd_tf['high'][i] >= ev['sweep_extreme'] - 1e-9:
                c2_idx = int(i)
                break
            if ev['direction'] == 'LONG' and cisd_tf['low'][i] <= ev['sweep_extreme'] + 1e-9:
                c2_idx = int(i)
                break
        if c2_idx is None:
            continue

        cisd = find_cisd_npg_in_window(
            o=cisd_tf['open'], c=cisd_tf['close'],
            h=cisd_tf['high'], l=cisd_tf['low'], ts=cisd_tf['ts_ns'],
            c2_idx=c2_idx, direction=ev['direction'],
            anchor_close_ts=anchor_close_ts,
            body_confirm=body_confirm,
        )
        if cisd is None:
            continue

        # Entry = open of bar after CISD fire on CISD-TF
        entry_idx_cisd_tf = cisd['fire_idx'] + 1
        if entry_idx_cisd_tf >= len(cisd_tf['ts_ns']):
            continue
        entry_price = float(cisd_tf['open'][entry_idx_cisd_tf])
        sl_price = float(ev['sweep_extreme'])
        risk_pts = abs(entry_price - sl_price)
        if risk_pts < MIN_RISK_PTS or risk_pts > MAX_RISK_PTS:
            continue

        # Targets from CISD series range, anchored to the structural break level
        # Per Pine source line 707: bearish → series_low, bullish → series_high
        break_price = cisd['series_low'] if ev['direction'] == 'SHORT' else cisd['series_high']
        targets = compute_targets(ev['direction'], break_price, cisd['series_range'], multipliers)

        # Outcome resolution on 1m bars starting from entry
        entry_ts = int(cisd_tf['ts_ns'][entry_idx_cisd_tf])
        m1_entry_idx = int(np.searchsorted(m1['ts_ns'], entry_ts))
        if m1_entry_idx >= len(m1['ts_ns']):
            continue

        if profile == 'series_multi':
            outcome = resolve_series_multi(
                o=m1['open'], h=m1['high'], l=m1['low'], c=m1['close'],
                ts=m1['ts_ns'], entry_idx=m1_entry_idx,
                entry_price=entry_price, sl_price=sl_price,
                direction=ev['direction'], targets=targets,
                max_bars=OUTCOME_MAX_BARS,
            )
        else:
            outcome = resolve_raw_measure(
                o=m1['open'], h=m1['high'], l=m1['low'], c=m1['close'],
                ts=m1['ts_ns'], entry_idx=m1_entry_idx,
                entry_price=entry_price,
                direction=ev['direction'], targets=targets,
                max_bars=OUTCOME_MAX_BARS,
            )

        # Compute filter flags
        # Silver needs hour, prev/prev-prev highs/lows from sweep_tf
        if anchor_idx >= 2:
            prev_high = float(sweep_tf['high'][anchor_idx - 1])
            prev_low = float(sweep_tf['low'][anchor_idx - 1])
            prev_prev_high = float(sweep_tf['high'][anchor_idx - 2])
            prev_prev_low = float(sweep_tf['low'][anchor_idx - 2])
            hour_et = _hour_of_day_et(sweep_tf['ts_ns'][anchor_idx])
            silver_flag = is_silver(
                ev['direction'], hour_et, float(sweep_tf['close'][anchor_idx]),
                prev_low, prev_prev_low, prev_high, prev_prev_high,
            )
        else:
            silver_flag = False

        smt_flag = False
        if sweep_es is not None and anchor_idx > 0 and anchor_idx < len(sweep_es['ts_ns']):
            es_window_high = float(sweep_es['high'][anchor_idx])
            es_window_low = float(sweep_es['low'][anchor_idx])
            es_prev_high = float(sweep_es['high'][anchor_idx - 1])
            es_prev_low = float(sweep_es['low'][anchor_idx - 1])
            smt_flag = is_smt(ev['direction'], es_window_high, es_window_low,
                              es_prev_high, es_prev_low)

        trades.append(dict(
            direction=ev['direction'],
            sweep_extreme=ev['sweep_extreme'],
            entry_price=entry_price,
            sl_price=sl_price,
            hits=outcome['hits'],
            sl_hit=outcome.get('sl_hit', False),
            composite_r=outcome['composite_r'],
            mae_pts=outcome['mae_pts'],
            mfe_pts=outcome['mfe_pts'],
            silver=silver_flag,
            smt=smt_flag,
            hour=_hour_of_day_et(int(cisd_tf['ts_ns'][entry_idx_cisd_tf])),
            dow=_day_of_week_et(int(cisd_tf['ts_ns'][entry_idx_cisd_tf])),
            series_range=cisd['series_range'],
            entry_ts_ns=int(cisd_tf['ts_ns'][entry_idx_cisd_tf]),
        ))

    summary = dict(
        n_trades=len(trades),
        agg=agg(trades),
        reach_rates=reach_rates(trades),
        by_hour=by_hour(trades),
        by_dow=by_dow(trades),
        by_session=by_session(trades),
        by_direction=by_direction(trades),
        filter_combinations=filter_combinations(trades, ['silver', 'smt']),
    )
    return dict(trades=trades, summary=summary)


def _hour_of_day_et(ts_ns):
    """Hour 0..23 in America/New_York. Uses pandas for tz conversion."""
    import pandas as pd
    t = pd.Timestamp(int(ts_ns), tz='UTC').tz_convert('America/New_York')
    return int(t.hour)


def _day_of_week_et(ts_ns):
    """0=Mon..6=Sun in America/New_York."""
    import pandas as pd
    t = pd.Timestamp(int(ts_ns), tz='UTC').tz_convert('America/New_York')
    return int(t.dayofweek)


def load_1m(table='nq_1m'):
    """Load 1m bars from the shared DB into numpy arrays."""
    import duckdb
    print(f"[1] Loading {table} from {DB_PATH}")
    con = duckdb.connect(str(DB_PATH), read_only=True)
    df = con.execute(f"""
        SELECT
            CAST(EXTRACT(EPOCH FROM timestamp) * 1e9 AS BIGINT) AS ts_ns,
            open, high, low, close
        FROM {table}
        ORDER BY timestamp
    """).fetchdf()
    con.close()
    print(f"  {len(df):,} bars loaded")
    return dict(
        ts_ns=df['ts_ns'].to_numpy(dtype='int64'),
        open=df['open'].to_numpy(dtype='float64'),
        high=df['high'].to_numpy(dtype='float64'),
        low=df['low'].to_numpy(dtype='float64'),
        close=df['close'].to_numpy(dtype='float64'),
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--pairings', nargs='+', default=list(PAIRINGS.keys()))
    p.add_argument('--profiles', nargs='+', default=PROFILES)
    p.add_argument('--table', default='nq_1m')
    p.add_argument('--no-smt', action='store_true', help='Skip ES load + SMT computation')
    args = p.parse_args()

    m1 = load_1m(args.table)
    m1_es = None if (args.no_smt or args.table == 'es_1m') else load_1m('es_1m')

    # Output paths
    parquet_dir = OUT_PATH.parent / 'data'
    parquet_dir.mkdir(exist_ok=True)
    summary_out = {}
    manifest = dict(
        schema_version=1,
        run_timestamp_utc=__import__('datetime').datetime.utcnow().isoformat() + 'Z',
        pairings=list(args.pairings),
        profiles=list(args.profiles),
        files={},
    )

    # Lazy import to keep pyarrow optional at module-load time
    from parquet_writer import write_trades_parquet

    for pairing in args.pairings:
        cfg = PAIRINGS[pairing]
        for profile in args.profiles:
            key = f"{pairing}/{profile}"
            print(f"[2] Running {key}")
            result = run_pairing(
                m1,
                sweep_tf_min=cfg['sweep_tf_min'],
                cisd_tf_min=cfg['cisd_tf_min'],
                profile=profile,
                body_confirm=True,
                multipliers=MULTIPLIERS,
                m1_es=m1_es,
            )
            trades = result['trades']

            # Write parquet (one file per pairing/profile)
            slug = key.replace('/', '_')
            pq_path = parquet_dir / f"trades_{slug}.parquet"
            write_trades_parquet(trades, str(pq_path))
            manifest['files'][key] = f"data/trades_{slug}.parquet"
            print(f"  → {pq_path.name} ({len(trades):,} trades)")

            # Slim summary for hub card / sanity reads (NO _trades)
            summary = result['summary']
            summary['n_trades'] = len(trades)
            summary.pop('_trades', None)
            summary_out[key] = summary

    print(f"[3] Writing {OUT_PATH}")
    with open(OUT_PATH, 'w') as f:
        json.dump(dict(summary=summary_out, manifest=manifest), f, default=_json_default)
    print(f"  Written: {OUT_PATH}")
    return summary_out


def _json_default(obj):
    """Handle numpy / int64 in JSON serialization."""
    import numpy as np
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    raise TypeError(f"Not JSON serializable: {type(obj)}")


if __name__ == '__main__':
    main()
