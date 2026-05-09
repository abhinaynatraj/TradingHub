"""Orchestrator for the breakout strategy backtest.

Loads breakouts.parquet + 1-min bars, runs all 3 stop variants, writes
trade-level and aggregate parquets + a manifest under
Analysis/data/strategy/.

Run from repo root or anywhere:
    python3 Analysis/strategy/run_strategy.py
    python3 Analysis/strategy/run_strategy.py --variants structural_1r
    python3 Analysis/strategy/run_strategy.py --start 2020-01-01
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd

HERE = Path(__file__).resolve().parent
ENGINE_DIR = HERE.parent / 'engine'
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ENGINE_DIR))

import bars                      # noqa: E402  Analysis/engine/bars.py
import engine as strategy_engine # noqa: E402  Analysis/strategy/engine.py
import aggregate as agg          # noqa: E402  Analysis/strategy/aggregate.py


VARIANTS = ['structural_1r', 'breakout_bar', 'time_bounded']

VARIANT_LABELS = {
    'structural_1r': 'Structural 1R',
    'breakout_bar':  'Breakout-bar stop',
    'time_bounded':  'Time-bounded (15m)',
}

VARIANT_DESCS = {
    'structural_1r': "Stop = prior hour's opposite extreme. Reject if > 30 pts. Target = 1R.",
    'breakout_bar':  "Stop = breakout bar's own opposite extreme. Reject if > 15 pts. Target = 1R.",
    'time_bounded':  "Stop = prior hour's opposite extreme. Exit at TP, SL, or 15-min time stop, whichever first.",
}


def _serialize_summary(summary: dict, out_dir: Path, variant: str) -> dict:
    """Write per-variant summaries; return JSON-friendly headline metrics."""
    # DataFrame outputs → parquet
    df_keys = ['by_year', 'by_hour', 'by_dow', 'by_direction', 'equity']
    written = {}
    for k in df_keys:
        df = summary.get(k)
        if isinstance(df, pd.DataFrame) and not df.empty:
            path = out_dir / f'{variant}_{k}.parquet'
            df.to_parquet(path, index=False)
            written[k] = path.name
    # Dict outputs → JSON-embedded in the manifest
    return {
        'aggregate': summary['aggregate'],
        'rejection': summary['rejection'],
        'exits':     summary['exits'],
        'files':     written,
    }


def main(start: str | None = None,
         end:   str | None = None,
         variants: list[str] | None = None) -> None:
    out_root = HERE.parent / 'data' / 'strategy'
    out_root.mkdir(parents=True, exist_ok=True)

    variants = variants or VARIANTS
    breakouts_path = HERE.parent / 'data' / 'breakout' / 'breakouts.parquet'
    if not breakouts_path.exists():
        print(f"[strategy] ERROR: {breakouts_path} not found. Run Analysis/engine/run_all.py first.")
        sys.exit(1)

    print(f"[strategy] reading breakouts: {breakouts_path}")
    events = pd.read_parquet(breakouts_path)
    n_total = len(events)
    n_breakouts = int(events['breakout'].isin(['bullish', 'bearish']).sum())
    print(f"[strategy]   {n_total:,} hour rows, {n_breakouts:,} breakout events")

    print(f"[strategy] loading 1-min bars (start={start}, end={end})...")
    minutes = bars.load_minutes(start=start, end=end)
    print(f"[strategy]   {len(minutes):,} 1-min rows")

    summaries: dict = {}
    for v in variants:
        trades = strategy_engine.simulate(events, minutes, v)
        if trades.empty:
            print(f"[strategy]   variant {v}: no trades produced.")
            continue
        # Persist trades
        trades_path = out_root / f'{v}_trades.parquet'
        trades.to_parquet(trades_path, index=False)
        # Aggregate
        s = agg.build_all_summaries(trades)
        summaries[v] = _serialize_summary(s, out_root, v)
        rej = s['rejection']
        ag = s['aggregate']
        print(f"[strategy]   variant {v}: taken {rej['n_taken']:,}/{rej['n_total_events']:,} "
              f"({rej['taken_rate']*100:.1f}%) · "
              f"WR {ag['wr']*100:.1f}% · EV {ag['avg_r']:+.3f}R · "
              f"PnL ${ag['total_pnl_usd']:,.0f} · max DD ${ag['max_dd_usd']:,.0f}")

    # Manifest
    manifest = {
        'schema_version': 1,
        'run_timestamp_utc': datetime.now(timezone.utc).isoformat(),
        'date_range_start': str(minutes['ny_ts'].min()) if len(minutes) else None,
        'date_range_end':   str(minutes['ny_ts'].max()) if len(minutes) else None,
        'instrument_pricing': 'NQ price action, MNQ sized ($2/pt, $225/trade target risk)',
        'constants': {
            'POINT_VALUE_USD': strategy_engine.POINT_VALUE_USD,
            'RISK_PER_TRADE_USD': strategy_engine.RISK_PER_TRADE_USD,
            'MIN_RISK_PTS': strategy_engine.MIN_RISK_PTS,
            'MAX_RISK_PTS_STRUCT': strategy_engine.MAX_RISK_PTS_STRUCT,
            'MAX_RISK_PTS_TIGHT': strategy_engine.MAX_RISK_PTS_TIGHT,
            'OUTCOME_MAX_BARS': strategy_engine.OUTCOME_MAX_BARS,
            'TIME_STOP_BARS': strategy_engine.TIME_STOP_BARS,
        },
        'variants': {
            v: {
                'label': VARIANT_LABELS[v],
                'description': VARIANT_DESCS[v],
                **summaries.get(v, {}),
            } for v in variants
        },
    }
    (out_root / 'manifest.json').write_text(json.dumps(manifest, indent=2, default=str))
    print(f"[strategy] wrote manifest: {out_root / 'manifest.json'}")
    print(f"[strategy] done.")


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--start', help='ISO date (NY local)')
    p.add_argument('--end',   help='ISO date (NY local), exclusive')
    p.add_argument('--variants', nargs='+', choices=VARIANTS, help='Subset of variants')
    args = p.parse_args()
    main(start=args.start, end=args.end, variants=args.variants)
