import sys
import time
import json
import argparse
from datetime import datetime, UTC
from pathlib import Path
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np
import pandas as pd

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import engine.build_stats as bs  # noqa: E402
from engine.constants import DATA_DIR
from v7_model.v7_engine import (
    detect_signals, preprocess_signals, run_combo_fast, agg,
    DEFAULT_QTY, DEFAULT_QTY_PART, DEFAULT_QTY_TGT,
    DEFAULT_BE_AT_PART, DEFAULT_DLL_USD, DEFAULT_PTDLL_USD,
    DEFAULT_USD_PER_PT, DEFAULT_COOLDOWN,
)

# ── Default sweep grid ────────────────────────────────────────────────────────
STOP_PCTS    = [0.05, 0.075, 0.10, 0.125, 0.15]
TARGET_PCTS  = [0.15, 0.20, 0.25, 0.30]

# Fixed ratios relative to target/stop
PARTIAL_FRAC = 0.50  # partial is 50% of the way to target
EXT_FRAC     = 1.50  # runner goes 50% further than target


def _ct_parts(ts_ns_array):
    idx = pd.DatetimeIndex(pd.to_datetime(ts_ns_array, utc=True)).tz_convert('America/Chicago')
    return idx.hour.to_numpy(), idx.strftime('%Y-%m-%d').to_numpy(), idx


def worker_task(combo):
    # This runs in a worker process
    # unpack combo
    sp, pp, tp, xp, prepped, m1_arrays, settings = combo
    rows = run_combo_fast(
        prepped, m1_arrays,
        sp, pp, tp, xp,
        qty=settings['qty'],
        qty_part=settings['qty_part'],
        qty_tgt=settings['qty_tgt'],
        be_at_partial=settings['be_at_part'],
        dll_usd=settings['dll_usd'],
        per_trade_dll_usd=settings['ptdll_usd'],
        usd_per_pt=settings['usd_per_pt']
    )
    from v7_model.v7_engine import agg_chunked
    return agg_chunked(rows, stop_pct=sp, partial_pct=pp, target_pct=tp, ext_pct=xp)


def run_sweep(stop_range, target_range, no_smt=False):
    DATA_DIR.mkdir(exist_ok=True)
    t0 = time.time()
    
    print("Loading 1m data...")
    m1 = bs.load_1m('nq_1m')
    m1_es = None if no_smt else bs.load_1m('es_1m')
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
    
    # Generate combos
    combos = []
    settings = dict(
        qty=DEFAULT_QTY, qty_part=DEFAULT_QTY_PART, qty_tgt=DEFAULT_QTY_TGT,
        be_at_part=DEFAULT_BE_AT_PART, dll_usd=DEFAULT_DLL_USD,
        ptdll_usd=DEFAULT_PTDLL_USD, usd_per_pt=DEFAULT_USD_PER_PT
    )
    
    for sp in stop_range:
        for tp in target_range:
            pp = round(tp * PARTIAL_FRAC, 3)
            xp = round(tp * EXT_FRAC, 3)
            combos.append((sp, pp, tp, xp, prepped, m1_arrays, settings))
            
    print(f"Sweeping {len(combos)} combinations...")
    
    results = []
    with ProcessPoolExecutor() as executor:
        futures = {executor.submit(worker_task, c): c for c in combos}
        
        for i, future in enumerate(as_completed(futures), 1):
            try:
                res = future.result()
                results.extend(res)
                if i % 50 == 0:
                    print(f"  {i}/{len(combos)} done...")
            except Exception as e:
                print(f"Error in combo: {e}")
                
    df = pd.DataFrame(results)
    
    # Calculate Sharpe
    # we don't have daily returns here, so we approximate or leave empty. 
    # For now, just adding a dummy column to match the dashboard expectation
    df['sharpe_daily'] = np.nan
    
    out_file = DATA_DIR / 'v7_sweep.parquet'
    df.to_parquet(out_file)
    print(f"Wrote {len(df)} rows to {out_file}")
    
    manifest = dict(
        run_timestamp_utc=datetime.now(UTC).isoformat(),
        n_combos=len(combos),
        stop_range=stop_range,
        target_range=target_range,
        settings=settings
    )
    with open(DATA_DIR / 'v7_sweep_manifest.json', 'w') as f:
        json.dump(manifest, f, indent=2)
        
    print(f"Sweep complete in {time.time() - t0:.1f}s")


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--stop', type=float, nargs='+', default=STOP_PCTS)
    p.add_argument('--target', type=float, nargs='+', default=TARGET_PCTS)
    p.add_argument('--no-smt', action='store_true')
    args = p.parse_args()

    run_sweep(args.stop, args.target, args.no_smt)
