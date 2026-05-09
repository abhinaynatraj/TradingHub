"""Attach DSP segment context to Fractal Sweep recent_trades."""

from __future__ import annotations
from decimal import Decimal
from pathlib import Path
from typing import Iterator
import ijson
import pandas as pd

from .distributions import bin_pct


def _to_float(v):
    """ijson returns Decimal for JSON numbers; coerce to float for math.
    Leave None / bool / str alone."""
    if isinstance(v, Decimal):
        return float(v)
    return v


def _coerce_trade(trade: dict) -> dict:
    return {k: _to_float(v) for k, v in trade.items()}


# Columns we keep from the FS trade rows (drop everything else to keep file small).
FS_KEEP_FIELDS = [
    "date", "direction", "hr", "mn", "session", "dow", "dow_name",
    "entry_price", "sweep_extreme", "target_price", "risk_pts",
    "r", "outcome", "mae_pct", "mfe_pct", "mae_pct_hr", "mfe_pct_hr",
    "hour_range_pts", "smt", "silver", "cisd_close",
    "passes_f3", "passes_f4", "classification",
]


def stream_recent_trades(fs_json_path: Path, model_key: str, profile: str = "simple_1r") -> Iterator[dict]:
    """Stream-parse one model+profile's `recent_trades` array."""
    item_path = f"{model_key}.profiles.{profile}.recent_trades.item"
    with open(fs_json_path, "rb") as f:
        yield from ijson.items(f, item_path)


def attach_dsp_context(trade: dict, dist_by_date: dict) -> dict | None:
    """Attach DSP fields. Returns None if no DSP distribution available for the date."""
    date = trade["date"]
    dist = dist_by_date.get(date)
    if dist is None:
        return None

    prior_low   = float(dist["prior_low"])
    prior_range = float(dist["prior_range"])
    if prior_range <= 0:
        return None

    entry_price = float(trade["entry_price"])
    entry_pct = (entry_price - prior_low) / prior_range * 100.0
    entry_seg = bin_pct(entry_pct)

    top_h_seg = dist["top_h_seg"]
    top_l_seg = dist["top_l_seg"]

    out = {k: trade.get(k) for k in FS_KEEP_FIELDS if k in trade}
    out.update({
        "dsp_entry_pct":     round(entry_pct, 2),
        "dsp_entry_seg":     entry_seg,                          # -1 if OOB
        "dsp_top_h_seg":     top_h_seg,
        "dsp_top_l_seg":     top_l_seg,
        # Predictive flags: where is entry vs top high/low segments?
        "dsp_at_or_above_top_h":  entry_seg >= 0 and entry_seg >= top_h_seg,
        "dsp_below_top_h":        entry_seg >= 0 and entry_seg <  top_h_seg,
        "dsp_at_or_below_top_l":  entry_seg >= 0 and entry_seg <= top_l_seg,
        "dsp_above_top_l":        entry_seg >= 0 and entry_seg >  top_l_seg,
        "dsp_in_inside_range":    entry_seg in (4, 5, 6, 7),     # 0-100% (inside PDH-PDL)
        "dsp_above_pdh":          entry_seg in (8, 9, 10, 11),   # >100%
        "dsp_below_pdl":          entry_seg in (0, 1, 2, 3),     # <0%
    })
    return out


def join_fs_trades(fs_json_path: Path, dist_df: pd.DataFrame, model_key: str) -> list[dict]:
    """Iterate FS trades for one model and attach DSP context. Drop trades
    whose date has no usable distribution (early in the dataset, OOB, etc.)."""
    dist_by_date = {row["d"]: row for _, row in dist_df.iterrows()}
    out = []
    n_total = 0
    n_dropped = 0
    from datetime import date as _date
    for raw_trade in stream_recent_trades(fs_json_path, model_key):
        n_total += 1
        trade = _coerce_trade(raw_trade)
        # Convert string date to datetime.date for dict lookup.
        try:
            trade["date"] = _date.fromisoformat(trade["date"])
        except (ValueError, TypeError):
            n_dropped += 1
            continue
        joined = attach_dsp_context(trade, dist_by_date)
        if joined is None:
            n_dropped += 1
            continue
        # Re-stringify the date for JSON output.
        joined["date"] = joined["date"].isoformat()
        out.append(joined)
    print(f"  {model_key}: {len(out):,} trades joined ({n_dropped:,} dropped of {n_total:,})")
    return out
