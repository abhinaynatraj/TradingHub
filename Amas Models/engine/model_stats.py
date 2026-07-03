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
from engine.constants import OUTCOME_MAX_BARS, RISK_PER_TRADE_USD  # noqa: E402
from engine.filters import enumerate_combos, apply_combo  # noqa: E402
from engine.models import MODELS  # noqa: E402
from engine.outcomes import Setup, resolve_outcome, compute_draw_hit  # noqa: E402
from engine.stats import agg, get_session  # noqa: E402


ENGINE_VERSION = "0.1.0"


def _build_hour_range_lookup(bars: pd.DataFrame) -> dict:
    """Precompute (date, hour) → hour-high-minus-hour-low for the full 1m bar set.

    Used to normalize per-trade MAE/MFE into a fraction of the entry hour's
    actual range — gives a regime-independent excursion metric. Mirrors
    Fractal Sweep's pattern in engine/model_stats.py:1177-1193.

    Keys are `(date, hour_int)` with date = python datetime.date (NY local),
    hour = 0..23 NY local. Returns a plain dict; lookup is O(1).
    """
    if len(bars) == 0:
        return {}
    # bars["ts"] is tz-aware datetime64[ns, America/New_York] per db.load_bars()
    ts = bars["ts"]
    grp_keys = list(zip(ts.dt.date, ts.dt.hour))
    hi = bars["high"].values
    lo = bars["low"].values
    # Walk once, tracking running max/min per (date, hour) key.
    out: dict = {}
    for i, k in enumerate(grp_keys):
        h = hi[i]
        l = lo[i]
        cur = out.get(k)
        if cur is None:
            out[k] = (h, l)
        else:
            cur_hi, cur_lo = cur
            if h > cur_hi:
                cur_hi = h
            if l < cur_lo:
                cur_lo = l
            out[k] = (cur_hi, cur_lo)
    # Final pass: collapse to range. Zero ranges (single-bar hours) get None
    # so downstream `mae_pct_hr = mae_pts / range * 100` doesn't divide-by-zero.
    return {k: (v[0] - v[1]) if (v[0] - v[1]) > 0 else None for k, v in out.items()}


def _attach_hour_normalized_excursion(row: dict, hr_range_lookup: dict) -> None:
    """Add mae_pct_hr / mfe_pct_hr to a trade row using its entry_ts.

    entry_ts is the string form of a pd.Timestamp (set in run() at the
    trade-row build site). Parse it back to extract (date, hour). If the
    lookup misses or the range is None, set both pct fields to None so the
    aggregator can skip them gracefully.
    """
    try:
        ts = pd.Timestamp(row["entry_ts"])
        key = (ts.date(), ts.hour)
        rng = hr_range_lookup.get(key)
    except Exception:
        rng = None
    if rng is None or rng == 0:
        row["mae_pct_hr"] = None
        row["mfe_pct_hr"] = None
    else:
        row["mae_pct_hr"] = row["mae_pts"] / rng * 100.0
        row["mfe_pct_hr"] = row["mfe_pts"] / rng * 100.0


def _equity_metrics(trades: list[dict], risk_per_trade_usd: float) -> dict:
    """Walk trades in chronological order and compute equity-curve metrics.

    Returns {min_equity_usd, max_dd_usd, max_dd_pct, equity_curve_final_usd}.
    EXPIRED trades count as zero R (no PnL impact). The walk assumes 1× risk
    per trade — a $400 loss for r=-1, $400 win for r=+1, etc.

    `equity_curve_final_usd` is the running total at the end of the walk.
    Drawdown is peak-to-trough on the running curve, in dollars and pct.
    """
    if not trades:
        return {"min_equity_usd": 0.0, "max_dd_usd": 0.0, "max_dd_pct": 0.0,
                "equity_curve_final_usd": 0.0}
    # Sort by entry_ts so the equity walk is chronological. The orchestrator
    # already iterates in detection order which is temporal, but be defensive
    # in case a future model registry yields non-temporal output.
    rows = sorted(trades, key=lambda r: r.get("entry_ts") or "")
    equity = 0.0
    peak = 0.0
    min_eq = 0.0
    max_dd = 0.0
    max_dd_pct = 0.0
    for r in rows:
        pnl = (r["r"] or 0.0) * risk_per_trade_usd
        equity += pnl
        if equity > peak:
            peak = equity
        if equity < min_eq:
            min_eq = equity
        dd = peak - equity
        if dd > max_dd:
            max_dd = dd
            # peak is the high-water mark; pct vs peak (account-relative) is
            # the conventional drawdown definition. Guard zero peak.
            max_dd_pct = (dd / peak * 100.0) if peak > 0 else 0.0
    return {
        "min_equity_usd": min_eq,
        "max_dd_usd": max_dd,
        "max_dd_pct": max_dd_pct,
        "equity_curve_final_usd": equity,
    }


def _build_breakdowns(trades: list[dict]) -> dict:
    """Build by_hour / by_dow / by_session / by_year breakdown dicts.

    Each value is the agg() result over the trade subset that matches the key.
    Hours and DOW use Python conventions: hour 0..23, weekday 0=Mon..6=Sun.
    Trades on Sat/Sun appear if the data covers them (overnight futures); the
    consumer can filter as needed.
    """
    by_hour: dict = {}
    by_dow: dict = {}
    by_session: dict = {}
    by_year: dict = {}
    if not trades:
        return {"by_hour": by_hour, "by_dow": by_dow,
                "by_session": by_session, "by_year": by_year}
    # Bucket trades by each key. Parsing the entry_ts string once per row is
    # the same cost the breakdown loops would pay individually.
    buckets_hour: dict = {}
    buckets_dow: dict = {}
    buckets_session: dict = {}
    buckets_year: dict = {}
    for row in trades:
        try:
            ts = pd.Timestamp(row["entry_ts"])
        except Exception:
            continue
        h = int(ts.hour)
        d = int(ts.weekday())   # 0=Mon
        y = int(ts.year)
        s = get_session(h)
        buckets_hour.setdefault(h, []).append(row)
        buckets_dow.setdefault(d, []).append(row)
        buckets_session.setdefault(s, []).append(row)
        buckets_year.setdefault(y, []).append(row)
    for h, rows in buckets_hour.items():
        by_hour[h] = agg(rows)
    for d, rows in buckets_dow.items():
        by_dow[d] = agg(rows)
    for s, rows in buckets_session.items():
        by_session[s] = agg(rows)
    for y, rows in buckets_year.items():
        by_year[y] = agg(rows)
    return {"by_hour": by_hour, "by_dow": by_dow,
            "by_session": by_session, "by_year": by_year}


def run(table: str = "nq_1m", model_keys: Optional[list[str]] = None) -> dict:
    """Load bars, run all (or the requested) models, return the JSON-shaped result."""
    bars = db.load_bars(table)

    # Precompute hourly H/L ranges once per run — shared across every model.
    hr_range_lookup = _build_hour_range_lookup(bars)

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
            # Carry forward optional model-attached metadata: anchor, draw, entry_pattern.
            # `anchor_ts` already added above via getattr fallback.
            if hasattr(setup, "draw_price"):
                row["draw_price"] = setup.draw_price
            if hasattr(setup, "entry_pattern"):
                row["entry_pattern"] = setup.entry_pattern
            # Draw-hit measurement: did price reach the prior-H1 extreme before SL?
            # This is the mentor's actual edge claim; the 1R take-profit is risk
            # management. Computed independently of the outcome resolver — the trade
            # may have booked at 1R but eventually reached the draw, or vice versa.
            if hasattr(setup, "draw_price"):
                hit, hit_ts = compute_draw_hit(bars, setup, setup.draw_price, max_bars=OUTCOME_MAX_BARS)
                row["draw_hit"] = hit
                row["draw_hit_ts"] = str(hit_ts) if hit_ts is not None else None
            # Carry forward any passes_<filter> flags the detector attached.
            for attr in dir(setup):
                if attr.startswith("passes_"):
                    row[attr] = getattr(setup, attr)
            # Hourly-range-normalized MAE/MFE (Fractal Sweep parity).
            # Adds row["mae_pct_hr"] and row["mfe_pct_hr"], both float or None.
            _attach_hour_normalized_excursion(row, hr_range_lookup)
            trades.append(row)

        summary = agg(trades)
        # Equity-curve metrics — min equity, max dollar drawdown, pct dd.
        # Computed at orchestrator level since outcomes.py resolves trades
        # in isolation and never sees the chronological list.
        equity = _equity_metrics(trades, RISK_PER_TRADE_USD)
        summary.update(equity)
        # Per-segment breakdowns. Each is {bucket_key: agg() dict}.
        breakdowns = _build_breakdowns(trades)

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
            "by_hour": breakdowns["by_hour"],
            "by_dow": breakdowns["by_dow"],
            "by_session": breakdowns["by_session"],
            "by_year": breakdowns["by_year"],
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
