"""H1 anchor builder for the Amas Models engine.

Resamples 1-minute bars into 1-hour candles in `America/New_York` tz, with
duration-based windowing (NOT row-count-based) and proper DST handling.

Per the design spec, Category A (TZ correctness) and Category C (lookahead):
- Floor in NY tz (the analysis tz), never in UTC then convert.
- Windows are half-open: [anchor_ts, anchor_ts + 1h).
- DST jumps are handled natively by `dt.floor('1h')` on a tz-aware NY series:
  spring-forward (02:00 vanishes) yields no 02:00 anchor; fall-back (01:00
  repeats) yields two distinct 01:00 anchors at different UTC instants.
- Empty windows are silently skipped; we never emit a NaN-OHLC row.
- `extreme_minute_high/low` are recorded for the FIRST occurrence on ties
  (idxmax/idxmin default behaviour), needed for downstream :42/:50 rules.

This module is a pure function — no DB I/O, no hidden state.
"""
from __future__ import annotations

import pandas as pd


def build_h1_anchors(bars: pd.DataFrame) -> pd.DataFrame:
    """Build H1 candles from 1-minute bars.

    Args:
        bars: 1m bars DataFrame as returned by `engine.db.load_bars`. Must have
            columns `ts, open, high, low, close, volume` with `ts` tz-aware in
            America/New_York and [ns] resolution.

    Returns:
        DataFrame with one row per H1 window that has at least one 1m bar.
        Columns:
            anchor_ts: tz-aware [ns, America/New_York] start of the H1 window.
            close_ts: anchor_ts + 1h (also tz-aware, [ns, NY]).
            open: open of the first 1m bar in the window.
            high: max of all 1m bar highs in the window.
            low: min of all 1m bar lows in the window.
            close: close of the last 1m bar in the window.
            volume: sum of 1m bar volumes (int64).
            n_bars: count of 1m bars in the window (int64; useful QC).
            extreme_minute_high: minute-of-hour (0-59) at which the H1 high
                was struck. First occurrence on ties.
            extreme_minute_low: minute-of-hour (0-59) at which the H1 low
                was struck. First occurrence on ties.

    Empty windows (no bars present in [anchor_ts, anchor_ts + 1h)) are not
    emitted — they are silently skipped, never rendered as NaN-OHLC rows.
    """
    out_cols = [
        "anchor_ts", "close_ts", "open", "high", "low", "close",
        "volume", "n_bars", "extreme_minute_high", "extreme_minute_low",
    ]

    if len(bars) == 0:
        empty = pd.DataFrame({c: pd.Series(dtype="float64") for c in out_cols})
        # restore tz/int dtypes on the empty frame
        empty["anchor_ts"] = pd.Series(dtype="datetime64[ns, America/New_York]")
        empty["close_ts"] = pd.Series(dtype="datetime64[ns, America/New_York]")
        empty["volume"] = pd.Series(dtype="int64")
        empty["n_bars"] = pd.Series(dtype="int64")
        empty["extreme_minute_high"] = pd.Series(dtype="int64")
        empty["extreme_minute_low"] = pd.Series(dtype="int64")
        return empty[out_cols]

    # Floor by UTC instant, then express the result in NY tz. NY is always at
    # a whole-hour offset from UTC (-05:00 or -04:00), so UTC hour boundaries
    # coincide exactly with NY hour boundaries — flooring in UTC produces the
    # same wall-clock anchor as flooring in NY, with NO DST ambiguity at the
    # floor step. Concretely:
    #   * Spring-forward (e.g., 2024-03-10): the missing 02:00 hour cannot
    #     appear because the bars never carry that wall-clock value; bars at
    #     01:30 EST and 03:30 EDT floor to 06:00 UTC and 07:00 UTC, expressing
    #     as 01:00 EST and 03:00 EDT respectively. No spurious 02:00 anchor.
    #   * Fall-back (e.g., 2023-11-05): the two distinct 01:00 wall-clock
    #     hours floor to 05:00 UTC and 06:00 UTC respectively, expressing as
    #     two distinct 01:00 NY anchors at different UTC offsets.
    # `dt.floor('1h')` on a UTC-tz series is unambiguous and handles both DST
    # cases without needing `ambiguous=` overrides.
    floored = bars["ts"].dt.tz_convert("UTC").dt.floor("1h").dt.tz_convert("America/New_York")

    # Group by the floored anchor. Use sort=False to preserve encountered order;
    # since `bars` is monotonic increasing per the load contract, this gives us
    # anchor groups in chronological order.
    rows = []
    for anchor_ts, group in bars.groupby(floored, sort=True):
        if len(group) == 0:
            continue  # defensive — groupby never yields empty groups
        idx_high = group["high"].idxmax()
        idx_low = group["low"].idxmin()
        rows.append({
            "anchor_ts": anchor_ts,
            "close_ts": anchor_ts + pd.Timedelta("1h"),
            "open": float(group["open"].iloc[0]),
            "high": float(group["high"].max()),
            "low": float(group["low"].min()),
            "close": float(group["close"].iloc[-1]),
            "volume": int(group["volume"].sum()),
            "n_bars": int(len(group)),
            "extreme_minute_high": int(group.loc[idx_high, "ts"].minute),
            "extreme_minute_low": int(group.loc[idx_low, "ts"].minute),
        })

    out = pd.DataFrame(rows, columns=out_cols)
    # Lock dtypes — anchor_ts/close_ts come back as object if the rows list was
    # empty, but since we early-returned above, here we always have rows.
    out["anchor_ts"] = out["anchor_ts"].astype("datetime64[ns, America/New_York]")
    out["close_ts"] = out["close_ts"].astype("datetime64[ns, America/New_York]")
    out["volume"] = out["volume"].astype("int64")
    out["n_bars"] = out["n_bars"].astype("int64")
    out["extreme_minute_high"] = out["extreme_minute_high"].astype("int64")
    out["extreme_minute_low"] = out["extreme_minute_low"].astype("int64")
    return out


def slice_h1_window(bars: pd.DataFrame, anchor_ts: pd.Timestamp) -> pd.DataFrame:
    """Return the 1m bars belonging to the H1 window starting at `anchor_ts`.

    Uses a half-open interval [anchor_ts, anchor_ts + 1h). A bar at exactly
    `anchor_ts + 1h` belongs to the NEXT H1 window, not this one.

    Args:
        bars: 1m bars DataFrame (same shape as `engine.db.load_bars` output).
        anchor_ts: tz-aware Timestamp at the start of an H1 window. Must be in
            a tz comparable to `bars['ts']` (America/New_York).

    Returns:
        DataFrame with the same columns as `bars`, containing the bars in the
        window. May be empty.
    """
    end_ts = anchor_ts + pd.Timedelta("1h")
    mask = (bars["ts"] >= anchor_ts) & (bars["ts"] < end_ts)
    return bars[mask]
