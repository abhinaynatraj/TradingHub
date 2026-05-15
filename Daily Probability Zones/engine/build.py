"""Orchestrator: build model_stats.json for the DSP × Fractal Sweep study.

Run from the `Daily Probability Zones/` folder:
    python3 engine/build.py
"""

from __future__ import annotations
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Make sibling imports work whether run as script or module.
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from engine.distributions import load_daily_hl, compute_per_date_distributions, EDGES, LOOKBACK, N_SEGS
from engine.join import join_fs_trades
from engine.aggregate import (
    baseline_summary, by_entry_segment, by_dsp_zone,
    by_top_segment_proximity, by_smt_and_dsp,
)


REPO_ROOT = HERE.parent.parent
FS_JSON   = REPO_ROOT / "Fractal Sweep" / "model_stats.json"
DB_PATH   = REPO_ROOT / "Fractal Sweep" / "candle_science.duckdb"
OUT_PATH  = HERE.parent / "model_stats.json"

MODEL_KEYS = ["1H_5M_PREV_CISD", "30M_3M_PREV_CISD"]


def main() -> None:
    print(f"Reading daily H/L from {DB_PATH.name}...")
    daily = load_daily_hl(DB_PATH, table="nq_1m")
    print(f"  {len(daily):,} daily rows ({daily['d'].iloc[0]} → {daily['d'].iloc[-1]})")

    print(f"\nComputing per-date DSP distributions (lookback={LOOKBACK})...")
    dist_df = compute_per_date_distributions(daily)
    print(f"  {len(dist_df):,} dates have valid distributions")

    print(f"\nJoining DSP context to Fractal Sweep recent_trades...")
    print(f"  Source: {FS_JSON}")
    trades_by_model = {}
    for mk in MODEL_KEYS:
        trades_by_model[mk] = join_fs_trades(FS_JSON, dist_df, mk)

    print("\nBuilding aggregations...")
    out = {
        "meta": {
            "generated_at":  datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "lookback":      LOOKBACK,
            "n_segs":        N_SEGS,
            "edges":         EDGES.tolist(),
            "instrument":    "NQ (nq_1m)",
            "fs_source":     str(FS_JSON.relative_to(REPO_ROOT)),
            "n_dates":       len(dist_df),
            "date_range":    [str(dist_df["d"].iloc[0]), str(dist_df["d"].iloc[-1])],
            "segment_labels": [
                f"{int(EDGES[i])}-{int(EDGES[i+1])}%" for i in range(N_SEGS)
            ],
        },
        "models": {},
    }

    for mk, trades in trades_by_model.items():
        print(f"  {mk}:")
        out["models"][mk] = {
            "n_trades":              len(trades),
            "baseline":              baseline_summary(trades),
            "by_entry_segment":      by_entry_segment(trades),
            "by_dsp_zone":           by_dsp_zone(trades),
            "by_top_seg_proximity":  by_top_segment_proximity(trades),
            "by_smt_and_dsp":        by_smt_and_dsp(trades),
            "trades":                trades,
        }

    print(f"\nWriting {OUT_PATH}...")
    OUT_PATH.write_text(json.dumps(out, indent=None, separators=(",", ":")))
    size_mb = OUT_PATH.stat().st_size / 1_048_576
    print(f"  {size_mb:.1f} MB")
    print("\nDone.")


if __name__ == "__main__":
    main()
