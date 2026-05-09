"""Per-date DSP segment distributions, walk-forward (no lookahead).

For each eligible NY trading day `d`, compute the 12-bin distribution of
where day-highs and day-lows landed in the strictly-prior 250-day window,
expressed as percent of the prior day's range (PDL=0%, PDH=100%).
"""

from __future__ import annotations
from pathlib import Path
import duckdb
import numpy as np
import pandas as pd

LOOKBACK = 250
N_SEGS = 12
# 13 edges → 12 bins of 25% each, spanning [-100, 200].
EDGES = np.arange(-100.0, 200.0 + 1e-9, 25.0)


def load_daily_hl(db_path: Path, table: str = "nq_1m") -> pd.DataFrame:
    """Daily H/L in NY tz, zero-range days dropped (matches Pine indicator)."""
    sql = f"""
    SELECT
        DATE_TRUNC('day', timezone('America/New_York', timestamp)) AS d,
        MAX(high) AS h,
        MIN(low)  AS l
    FROM {table}
    GROUP BY 1
    ORDER BY 1
    """
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        df = con.execute(sql).df()
    finally:
        con.close()
    df["d"] = pd.to_datetime(df["d"]).dt.date
    df["range"] = df["h"] - df["l"]
    df = df[df["range"] > 0].reset_index(drop=True)
    return df


def bin_pct_vec(pcts: np.ndarray) -> np.ndarray:
    """Vectorized binning. -1 == out of bounds (below -100 or above 200)."""
    out = np.full(pcts.shape, -1, dtype=np.int64)
    valid = (pcts >= -100.0) & (pcts <= 200.0) & np.isfinite(pcts)
    idx = np.floor((pcts[valid] + 100.0) / 25.0).astype(np.int64)
    idx = np.clip(idx, 0, N_SEGS - 1)
    out[valid] = idx
    return out


def bin_pct(pct: float) -> int:
    """Scalar binning. -1 == OOB."""
    if not np.isfinite(pct) or pct < -100.0 or pct > 200.0:
        return -1
    idx = int(np.floor((pct + 100.0) / 25.0))
    return max(0, min(N_SEGS - 1, idx))


def compute_per_date_distributions(daily: pd.DataFrame) -> pd.DataFrame:
    """For each row beyond LOOKBACK, return the per-date distribution.

    Output columns:
        d, prior_high, prior_low, prior_range,
        h_seg (today's actual high seg, post-hoc — not used for prediction),
        l_seg,
        top_h_seg, top_l_seg,
        h_dist (12-bin counts), l_dist (12-bin counts),
        n_window (eligible days in the prior 250-day window)
    """
    # Each row's "prior" anchor is row[i-1].
    prior_low_arr   = daily["l"].shift(1).values
    prior_high_arr  = daily["h"].shift(1).values
    prior_range_arr = daily["range"].shift(1).values
    day_high_arr    = daily["h"].values
    day_low_arr     = daily["l"].values

    with np.errstate(invalid="ignore"):
        h_pct = (day_high_arr - prior_low_arr) / prior_range_arr * 100.0
        l_pct = (day_low_arr  - prior_low_arr) / prior_range_arr * 100.0

    h_seg = bin_pct_vec(h_pct)
    l_seg = bin_pct_vec(l_pct)

    n = len(daily)
    rows = []
    for i in range(LOOKBACK + 1, n):
        # Walk back through prior LOOKBACK rows, take only in-bin observations.
        wstart = i - LOOKBACK
        wh = h_seg[wstart:i]
        wl = l_seg[wstart:i]
        valid = (wh >= 0) & (wl >= 0)
        wh_v = wh[valid]
        wl_v = wl[valid]
        if len(wh_v) < 5:
            continue
        h_counts = np.bincount(wh_v, minlength=N_SEGS)
        l_counts = np.bincount(wl_v, minlength=N_SEGS)
        rows.append({
            "d": daily["d"].iloc[i],
            "prior_high":  prior_high_arr[i],
            "prior_low":   prior_low_arr[i],
            "prior_range": prior_range_arr[i],
            "h_seg":       int(h_seg[i]) if h_seg[i] >= 0 else None,
            "l_seg":       int(l_seg[i]) if l_seg[i] >= 0 else None,
            "top_h_seg":   int(h_counts.argmax()),
            "top_l_seg":   int(l_counts.argmax()),
            "h_dist":      h_counts.tolist(),
            "l_dist":      l_counts.tolist(),
            "n_window":    int(len(wh_v)),
        })
    return pd.DataFrame(rows)
