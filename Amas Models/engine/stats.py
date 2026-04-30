"""Aggregation, Wilson CIs, and statistical helpers for the Amas Models engine.

Per the design spec, Category G (Statistical hygiene):
- EV is MEAN R, not median (computed over resolved trades only)
- PF is gross profit / gross loss in R (not dollars)
- Wilson 95% CI on WR for every breakdown cell
- Expired trades excluded from WR/EV but counted in N
- Sample size visible everywhere (returned in result dict)
"""
from __future__ import annotations

import math
from typing import Optional


def agg(rows: list[dict]) -> dict:
    """Aggregate a list of trade rows into summary metrics.

    Each row must have at least: r (float | None), outcome (str).
    Rows with outcome == 'EXPIRED' are counted in n but excluded from
    n_resolved, wr, ev, pf.

    Returns dict with: n, n_resolved, n_expired, wins, wr, wr_ci_low,
    wr_ci_high, ev, pf, avg_risk_pts (if present), avg_rr (if present),
    avg_mae, avg_mfe.
    """
    n = len(rows)
    n_expired = sum(1 for r in rows if r.get("outcome") == "EXPIRED")
    resolved = [r for r in rows if r.get("outcome") != "EXPIRED" and r.get("r") is not None]
    n_resolved = len(resolved)

    if n_resolved == 0:
        return {
            "n": n, "n_resolved": 0, "n_expired": n_expired,
            "wins": 0, "wr": None, "wr_ci_low": None, "wr_ci_high": None,
            "ev": None, "pf": None,
        }

    wins = sum(1 for r in resolved if r["r"] > 0)
    wr = wins / n_resolved
    ev = sum(r["r"] for r in resolved) / n_resolved

    gross_profit = sum(r["r"] for r in resolved if r["r"] > 0)
    gross_loss = sum(r["r"] for r in resolved if r["r"] < 0)
    if gross_loss == 0:
        pf = math.inf if gross_profit > 0 else None
    else:
        pf = gross_profit / abs(gross_loss)

    ci_low, ci_high = wilson_ci(wins=wins, n=n_resolved)

    result = {
        "n": n,
        "n_resolved": n_resolved,
        "n_expired": n_expired,
        "wins": wins,
        "wr": wr,
        "wr_ci_low": ci_low,
        "wr_ci_high": ci_high,
        "ev": ev,
        "pf": pf,
    }

    # Optional fields if present on rows
    if rows and "mae_pts" in rows[0]:
        mae_vals = [r.get("mae_pts", 0.0) for r in rows]
        result["avg_mae_pts"] = sum(mae_vals) / len(mae_vals)
    if rows and "mfe_pts" in rows[0]:
        mfe_vals = [r.get("mfe_pts", 0.0) for r in rows]
        result["avg_mfe_pts"] = sum(mfe_vals) / len(mfe_vals)
    if rows and "risk_pts" in rows[0]:
        risk_vals = [r["risk_pts"] for r in rows]
        result["avg_risk_pts"] = sum(risk_vals) / len(risk_vals)

    return result


def wilson_ci(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson 95% confidence interval for a proportion.

    More stable than normal approx for small N or extreme proportions.
    Returns (low, high). For n=0, returns (0.0, 1.0) — the maximally uninformative
    interval.
    """
    if n == 0:
        return (0.0, 1.0)
    p = wins / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    spread = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, center - spread), min(1.0, center + spread))
