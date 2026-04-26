"""Orchestrator for the Amas Models engine.

Loads bars from DuckDB, iterates over registered models, runs each model's
detector, resolves outcomes, computes filter combos, and writes a single
model_stats.json.

Per the design spec, Category B (Trade deduplication) and H (Determinism):
- Post-detect dedup assertion per (anchor_ts, direction) — hard fail on duplicates
- Iteration order is registration order (dict-preserving)
- JSON output uses sorted keys for byte-stability across runs

CLI:
    python3 engine/model_stats.py                          # all models, NQ
    python3 engine/model_stats.py --models <key>           # subset
    python3 engine/model_stats.py --table es_1m            # ES instead of NQ
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Self-locate: when invoked as `python3 engine/model_stats.py`, Python only puts
# the script's directory (engine/) on sys.path, so `from engine import ...` fails.
# Inject the project root (parent of engine/) before any engine imports.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import pandas as pd  # noqa: E402

from engine import db  # noqa: E402
from engine.constants import OUTCOME_MAX_BARS  # noqa: E402
from engine.filters import enumerate_combos, apply_combo  # noqa: E402
from engine.models import MODELS  # noqa: E402
from engine.outcomes import Setup, resolve_outcome  # noqa: E402
from engine.stats import agg  # noqa: E402


ENGINE_VERSION = "0.1.0"


def run(table: str = "nq_1m", model_keys: Optional[list[str]] = None) -> dict:
    """Load bars, run all (or the requested) models, return the JSON-shaped result."""
    bars = db.load_bars(table)

    keys = model_keys if model_keys else list(MODELS.keys())
    for k in keys:
        if k not in MODELS:
            raise KeyError(f"Unknown model key: {k!r}. Registered: {list(MODELS.keys())}")

    out_models: dict[str, dict] = {}
    for key in keys:
        md = MODELS[key]
        setups: list[Setup] = list(md.detect(bars))

        # Dedup invariant B.2: hard fail on duplicate (anchor_ts, direction) pairs.
        seen: set[tuple] = set()
        dups: list[tuple] = []
        for s in setups:
            anchor_key = getattr(s, "anchor_ts", s.entry_ts)  # detectors may stamp anchor_ts; fallback entry_ts
            k2 = (anchor_key, s.direction)
            if k2 in seen:
                dups.append(k2)
            else:
                seen.add(k2)
        assert not dups, f"{key}/{table}: duplicate setups at {dups[:5]} (and {max(0, len(dups)-5)} more)"

        trades: list[dict] = []
        for setup in setups:
            outcome = resolve_outcome(bars, setup, max_bars=OUTCOME_MAX_BARS)
            row = {
                "anchor_ts": str(getattr(setup, "anchor_ts", setup.entry_ts)),
                "entry_ts": str(setup.entry_ts),
                "direction": setup.direction,
                "entry_price": setup.entry_price,
                "sl_price": setup.sl_price,
                "tp_price": setup.tp_price,
                "risk_pts": setup.risk_pts,
                "outcome": outcome.outcome,
                "r": outcome.r,
                "resolution_ts": str(outcome.resolution_ts) if outcome.resolution_ts else None,
                "mae_pts": outcome.mae_pts,
                "mfe_pts": outcome.mfe_pts,
                "bars_to_resolve": outcome.bars_to_resolve,
            }
            # Carry forward any passes_<filter> flags the detector attached.
            for attr in dir(setup):
                if attr.startswith("passes_"):
                    row[attr] = getattr(setup, attr)
            trades.append(row)

        summary = agg(trades)

        # 2^N filter combo grid
        filter_keys = [f.key for f in md.filters]
        combos = enumerate_combos(filter_keys)
        variants = []
        for combo in combos:
            subset = apply_combo(trades, combo)
            variants.append({
                "filters": sorted(list(combo)),
                "stats": agg(subset),
            })
        variants.sort(key=lambda v: (v["stats"].get("ev") or -999), reverse=True)

        out_models[key] = {
            "label": md.label,
            "filters": [{"key": f.key, "label": f.label, "default": f.default} for f in md.filters],
            "trades": trades,
            "summary": summary,
            "filter_variants": variants,
            "spec_html": "",  # filled by render_spec_html (Phase 3+)
        }

    return {
        "meta": {
            "engine_version": ENGINE_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "table": table,
            "data_range": f"{bars['ts'].min()} to {bars['ts'].max()}" if len(bars) else "",
            "spec_sha": _spec_sha(),
        },
        "models": out_models,
    }


def _spec_sha() -> str:
    """Hash of docs/model_specs.md, for reproducibility tracking."""
    spec = Path(__file__).resolve().parent.parent / "docs" / "model_specs.md"
    if not spec.exists():
        return ""
    return hashlib.sha256(spec.read_bytes()).hexdigest()


def write(result: dict, out_path: Optional[Path] = None) -> Path:
    """Serialize to model_stats.json with sorted keys (deterministic byte output)."""
    if out_path is None:
        out_path = Path(__file__).resolve().parent.parent / "model_stats.json"
    with out_path.open("w") as f:
        json.dump(result, f, sort_keys=True, default=str)
    return out_path


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Run the Amas Models engine.")
    p.add_argument("--table", default="nq_1m", choices=["nq_1m", "es_1m"])
    p.add_argument("--models", nargs="+", default=None, help="Subset of registered model keys.")
    args = p.parse_args(argv)

    result = run(table=args.table, model_keys=args.models)
    out = write(result)
    n_models = len(result["models"])
    n_trades = sum(len(m["trades"]) for m in result["models"].values())
    print(f"Wrote {out} ({n_models} model(s), {n_trades} trade(s)).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
