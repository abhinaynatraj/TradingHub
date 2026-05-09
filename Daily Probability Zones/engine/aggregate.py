"""Aggregations: WR/EV stratified by DSP segment context."""

from __future__ import annotations
import math
import numpy as np


def wilson_ci(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson 95% CI for a binomial proportion. Returns (lo, hi)."""
    if n == 0:
        return (0.0, 0.0)
    p = wins / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def agg(rows: list[dict]) -> dict:
    """Standard FS-style aggregation block."""
    if not rows:
        return {"n": 0, "wins": 0, "wr": 0.0, "ev": 0.0, "pf": 0.0,
                "wr_lo": 0.0, "wr_hi": 0.0, "avg_r": 0.0,
                "avg_mae_hr": 0.0, "avg_mfe_hr": 0.0}
    rs = np.array([r["r"] for r in rows if r.get("r") is not None and r.get("outcome") in ("WIN", "LOSS")])
    if len(rs) == 0:
        return {"n": len(rows), "wins": 0, "wr": 0.0, "ev": 0.0, "pf": 0.0,
                "wr_lo": 0.0, "wr_hi": 0.0, "avg_r": 0.0,
                "avg_mae_hr": 0.0, "avg_mfe_hr": 0.0}
    wins = int(np.sum(rs > 0))
    n = len(rs)
    losses_sum = -float(np.sum(rs[rs < 0]))
    wins_sum = float(np.sum(rs[rs > 0]))
    pf = (wins_sum / losses_sum) if losses_sum > 0 else float("inf")
    wr = wins / n
    ev = float(np.mean(rs))
    lo, hi = wilson_ci(wins, n)

    mae_hr = [r.get("mae_pct_hr") for r in rows if r.get("mae_pct_hr") is not None]
    mfe_hr = [r.get("mfe_pct_hr") for r in rows if r.get("mfe_pct_hr") is not None]

    return {
        "n":          n,
        "wins":       wins,
        "wr":         round(wr, 4),
        "ev":         round(ev, 4),
        "pf":         (round(pf, 3) if pf != float("inf") else None),
        "wr_lo":      round(lo, 4),
        "wr_hi":      round(hi, 4),
        "avg_r":      round(float(np.mean(rs)), 4),
        "avg_mae_hr": (round(float(np.mean(mae_hr)), 2) if mae_hr else 0.0),
        "avg_mfe_hr": (round(float(np.mean(mfe_hr)), 2) if mfe_hr else 0.0),
    }


def by_entry_segment(trades: list[dict]) -> dict:
    """Stratify by which segment the entry price landed in (0-11)."""
    by_seg = {}
    for t in trades:
        seg = t.get("dsp_entry_seg", -1)
        if seg < 0:
            continue
        by_seg.setdefault(seg, []).append(t)
    return {str(k): agg(v) for k, v in sorted(by_seg.items())}


def by_dsp_zone(trades: list[dict]) -> dict:
    """Stratify by inside-range / above-PDH / below-PDL zones."""
    bins = {"below_pdl": [], "inside": [], "above_pdh": [], "oob": []}
    for t in trades:
        if t.get("dsp_below_pdl"):
            bins["below_pdl"].append(t)
        elif t.get("dsp_in_inside_range"):
            bins["inside"].append(t)
        elif t.get("dsp_above_pdh"):
            bins["above_pdh"].append(t)
        else:
            bins["oob"].append(t)
    return {k: agg(v) for k, v in bins.items()}


def by_top_segment_proximity(trades: list[dict]) -> dict:
    """Stratify by entry position vs predicted top-high segment."""
    bins = {
        "long_below_top_h":  [],   # LONG below predicted high zone — room to run
        "long_at_or_above":  [],   # LONG already at/past top-h — fading the day's tail
        "short_above_top_l": [],   # SHORT above predicted low zone — room to run
        "short_at_or_below": [],   # SHORT at/past top-l — late
    }
    for t in trades:
        d = t.get("direction")
        if d == "LONG":
            if t.get("dsp_below_top_h"):
                bins["long_below_top_h"].append(t)
            elif t.get("dsp_at_or_above_top_h"):
                bins["long_at_or_above"].append(t)
        elif d == "SHORT":
            if t.get("dsp_above_top_l"):
                bins["short_above_top_l"].append(t)
            elif t.get("dsp_at_or_below_top_l"):
                bins["short_at_or_below"].append(t)
    return {k: agg(v) for k, v in bins.items()}


def by_smt_and_dsp(trades: list[dict]) -> dict:
    """Cross-tab: SMT × DSP zone (the most interesting question — does DSP
    add lift on top of the strongest existing FS filter?)."""
    out = {}
    for smt_label, smt_val in [("with_smt", True), ("without_smt", False)]:
        sub = [t for t in trades if t.get("smt") == smt_val]
        out[smt_label] = {
            "all":        agg(sub),
            "below_pdl":  agg([t for t in sub if t.get("dsp_below_pdl")]),
            "inside":     agg([t for t in sub if t.get("dsp_in_inside_range")]),
            "above_pdh":  agg([t for t in sub if t.get("dsp_above_pdh")]),
        }
    return out


def baseline_summary(trades: list[dict]) -> dict:
    """Overall baseline (no DSP filter applied)."""
    return agg(trades)
