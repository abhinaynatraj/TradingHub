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
    detect_signals, preprocess_signals, run_combo_fast, agg_chunked,
    DEFAULT_QTY, DEFAULT_BE_AT_PART, DEFAULT_DLL_USD, DEFAULT_PTDLL_USD,
    DEFAULT_USD_PER_PT, DEFAULT_COOLDOWN,
)

# ── Stage 1 default sweep grid ───────────────────────────────────────────────
# Sweeping Stop% from 0.05% to 0.30%
STOP_PCTS = [0.05, 0.075, 0.10, 0.125, 0.15, 0.175, 0.20, 0.225, 0.25, 0.275, 0.30]
# Strict 1.5R target multiplier
R_MULTIPLIER = 1.5

# Two entry models to compare
ENTRY_MODELS = ['immediate', 'far_edge']


def _ct_parts(ts_ns_array):
    idx = pd.DatetimeIndex(pd.to_datetime(ts_ns_array, utc=True)).tz_convert('America/Chicago')
    return idx.hour.to_numpy(), idx.strftime('%Y-%m-%d').to_numpy(), idx


def worker_task(combo):
    sp, prepped, m1_arrays, settings, total_days, entry_mode = combo
    tp = round(sp * R_MULTIPLIER, 3)
    
    # All-in, all-out at target (we map it to partial to avoid 3-leg logic issues when pp==tp)
    rows = run_combo_fast(
        prepped, m1_arrays,
        sp, partial_pct=tp, target_pct=tp, ext_pct=tp,
        qty=settings['qty'],
        qty_part=settings['qty'],  # All contracts exit at partial
        qty_tgt=0,  
        be_at_partial=False,
        dll_usd=settings['dll_usd'],
        per_trade_dll_usd=settings['ptdll_usd'],
        usd_per_pt=settings['usd_per_pt'],
        cooldown=DEFAULT_COOLDOWN,
        entry_mode=entry_mode,
    )
    
    for r in rows:
        if r['bucket'] == 'partial':
            r['bucket'] = 'target_win'
        r['entry_model'] = entry_mode
            
    # Return both the raw trades and the chunked aggregations
    chunks = agg_chunked(rows, stop_pct=sp, target_pct=tp, total_days=total_days)
    for c in chunks:
        c['entry_model'] = entry_mode
    return chunks, rows


def run_sweep(stop_range, no_smt=False):
    DATA_DIR.mkdir(exist_ok=True)
    t0 = time.time()
    
    print("Loading 1m data for Stage 1...")
    m1 = bs.load_1m('nq_1m')
    m1_es = None if no_smt else bs.load_1m('es_1m')
    m1_arrays = (m1['high'], m1['low'], m1['close'])
    
    print("Detecting signals...")
    raw_signals = detect_signals(m1, m1_es)
    
    print("Preprocessing signals...")
    m1_ts = m1['ts_ns']
    ct_hour, ct_date, _ = _ct_parts(m1_ts)
    m1_hours_ny = bs._ny_hours(m1_ts)
    
    total_days = len(np.unique(ct_date))
    print(f"Total dataset trading days: {total_days}")
    
    prepped = preprocess_signals(
        raw_signals, m1, m1_hours_ny, ct_hour, ct_date,
        use_windows=True
    )
    
    settings = dict(
        qty=DEFAULT_QTY,
        be_at_part=False,
        dll_usd=9999999,  # Disable DLL for Stage 1 edge proof
        ptdll_usd=0, # Disable per-trade DLL for Stage 1 edge proof
        usd_per_pt=DEFAULT_USD_PER_PT
    )
    
    combos = []
    for entry_mode in ENTRY_MODELS:
        for sp in stop_range:
            combos.append((sp, prepped, m1_arrays, settings, total_days, entry_mode))
            
    print(f"Sweeping {len(combos)} combinations for Stage 1 ({len(ENTRY_MODELS)} entry models × {len(stop_range)} stops)...")
    
    all_chunks = []
    all_trades = []
    with ProcessPoolExecutor() as executor:
        futures = {executor.submit(worker_task, c): c for c in combos}
        
        for i, future in enumerate(as_completed(futures), 1):
            try:
                chunks, trades = future.result()
                all_chunks.extend(chunks)
                all_trades.extend(trades)
                if i % 10 == 0:
                    print(f"  {i}/{len(combos)} done...")
            except Exception as e:
                print(f"Error in combo: {e}")
                
    df_chunks = pd.DataFrame(all_chunks)
    out_file_chunks = DATA_DIR / 'v7_stage1_sweep.parquet'
    df_chunks.to_parquet(out_file_chunks)
    print(f"Wrote {len(df_chunks)} chunk rows to {out_file_chunks}")
    
    df_trades = pd.DataFrame(all_trades)
    out_file_trades = DATA_DIR / 'v7_stage1_trades.parquet'
    df_trades.to_parquet(out_file_trades)
    print(f"Wrote {len(df_trades)} trade rows to {out_file_trades}")
    
    manifest = dict(
        run_timestamp_utc=datetime.now(UTC).isoformat(),
        n_combos=len(combos),
        stop_range=stop_range,
        entry_models=ENTRY_MODELS,
        r_multiplier=R_MULTIPLIER,
        settings=settings
    )
    with open(DATA_DIR / 'v7_stage1_manifest.json', 'w') as f:
        json.dump(manifest, f, indent=2)
        
    print(f"Stage 1 Sweep complete in {time.time() - t0:.1f}s")


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--stop', type=float, nargs='+', default=STOP_PCTS)
    p.add_argument('--no-smt', action='store_true')
    args = p.parse_args()

    run_sweep(args.stop, args.no_smt)
