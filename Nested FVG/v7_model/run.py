import sys
import time
import json
import argparse
from datetime import datetime, UTC
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import engine.build_stats as bs  # noqa: E402
from engine.constants import DATA_DIR
from v7_model.v7_engine import (
    detect_signals, preprocess_signals, run_combo_fast, agg,
    DEFAULT_STOP_PCT, DEFAULT_PARTIAL_PCT, DEFAULT_TARGET_PCT, DEFAULT_EXT_PCT,
    DEFAULT_QTY, DEFAULT_QTY_PART, DEFAULT_QTY_TGT,
    DEFAULT_BE_AT_PART, DEFAULT_DLL_USD, DEFAULT_PTDLL_USD,
    DEFAULT_USD_PER_PT, DEFAULT_COOLDOWN,
)


def _ct_parts(ts_ns_array):
    idx = pd.DatetimeIndex(pd.to_datetime(ts_ns_array, utc=True)).tz_convert('America/Chicago')
    return idx.hour.to_numpy(), idx.strftime('%Y-%m-%d').to_numpy(), idx


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--stop', type=float, default=DEFAULT_STOP_PCT)
    p.add_argument('--partial', type=float, default=DEFAULT_PARTIAL_PCT)
    p.add_argument('--target', type=float, default=DEFAULT_TARGET_PCT)
    p.add_argument('--ext', type=float, default=DEFAULT_EXT_PCT)
    p.add_argument('--no-smt', action='store_true')
    args = p.parse_args()

    DATA_DIR.mkdir(exist_ok=True)
    t0 = time.time()
    
    print("Loading 1m data...")
    m1 = bs.load_1m('nq_1m')
    m1_es = None if args.no_smt else bs.load_1m('es_1m')
    m1_arrays = (m1['high'], m1['low'], m1['close'])
    
    print("Detecting signals...")
    raw_signals = detect_signals(m1, m1_es)
    
    print("Preprocessing signals...")
    m1_ts = m1['ts_ns']
    ct_hour, ct_date, _ = _ct_parts(m1_ts)
    m1_hours_ny = bs._ny_hours(m1_ts)
    
    prepped = preprocess_signals(
        raw_signals, m1, m1_hours_ny, ct_hour, ct_date,
        use_windows=True, cooldown=DEFAULT_COOLDOWN
    )
    
    print(f"Running simulation with:")
    print(f"  Stop:    {args.stop}%")
    print(f"  Partial: {args.partial}%")
    print(f"  Target:  {args.target}%")
    print(f"  Ext:     {args.ext}%")
    
    rows = run_combo_fast(
        prepped, m1_arrays,
        args.stop, args.partial, args.target, args.ext,
        qty=DEFAULT_QTY,
        qty_part=DEFAULT_QTY_PART,
        qty_tgt=DEFAULT_QTY_TGT,
        be_at_partial=DEFAULT_BE_AT_PART,
        dll_usd=DEFAULT_DLL_USD,
        per_trade_dll_usd=DEFAULT_PTDLL_USD,
        usd_per_pt=DEFAULT_USD_PER_PT
    )
    
    df = pd.DataFrame(rows)
    out_file = DATA_DIR / 'v7_trades.parquet'
    df.to_parquet(out_file)
    print(f"Wrote {len(df)} rows to {out_file}")
    
    summary = agg(rows, stop_pct=args.stop, partial_pct=args.partial, 
                  target_pct=args.target, ext_pct=args.ext)
                  
    config = dict(
        stop_pct=args.stop, partial_pct=args.partial,
        target_pct=args.target, ext_pct=args.ext,
        qty=DEFAULT_QTY, qty_part=DEFAULT_QTY_PART, qty_tgt=DEFAULT_QTY_TGT,
        dll_usd=DEFAULT_DLL_USD, ptdll_usd=DEFAULT_PTDLL_USD,
        usd_per_pt=DEFAULT_USD_PER_PT
    )
    
    manifest = dict(
        run_timestamp_utc=datetime.now(UTC).isoformat(),
        config=config,
        summary=summary
    )
    
    with open(DATA_DIR / 'v7_manifest.json', 'w') as f:
        json.dump(manifest, f, indent=2)
        
    print(f"Run complete in {time.time() - t0:.1f}s")
    for k, v in summary.items():
        print(f"  {k}: {v}")


if __name__ == '__main__':
    main()
