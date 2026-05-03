"""npg-specification CISD: opposing-candle series broken by opposing close.

Mirrors the Pine source `detectCISDAndProjections` (sweep_cisd_mtf_fvg.pine
lines 658–723):

For a bearish setup (direction='SHORT'):
  - Walk BACKWARD from c2_idx collecting bullish candles (close > open)
  - Stop on the first bearish candle (close <= open) — no doji handling
  - Cap at max_series bars
  - Track series_high / series_low across the run (body if body_confirm else wick)
  - Walk FORWARD from c2_idx + 1: fire when close < series_low (bears break the bull series)

For LONG: mirror — walk back collecting bearish, fire on close > series_high.

Returns None if no series + break is found within max_forward bars.
"""
import numpy as np


def find_cisd_npg(o, c, h, l, ts, c2_idx, direction, body_confirm=True,
                  max_series=20, max_forward=100):
    """Detect npg-spec CISD given the swept candle index on the LTF.

    Args:
        o, c, h, l, ts: numpy arrays of LTF bar OHLC + timestamps
        c2_idx: index of the LTF bar holding the swept HTF extreme
        direction: 'SHORT' (bearish setup) or 'LONG' (bullish setup)
        body_confirm: True → use max/min(open, close); False → use high/low
        max_series: cap on backward series length (npg default 20)
        max_forward: cap on forward bars to wait for the break

    Returns:
        dict(fire_idx, fire_ts_ns, series_high, series_low, series_range,
             series_extreme_broken, series_count) or None
    """
    n = len(o)

    # Backward scan from c2_idx, collecting opposing-direction candles
    series_indices = [c2_idx]
    for k in range(1, max_series):
        i = c2_idx - k
        if i < 0:
            break
        is_bullish = c[i] > o[i]
        if direction == 'SHORT':
            # Series collects bullish; stop on bearish (or doji)
            if is_bullish:
                series_indices.append(i)
            else:
                break
        else:  # LONG
            if not is_bullish and c[i] != o[i]:
                series_indices.append(i)
            else:
                break

    # Compute series extremes
    if body_confirm:
        bodies_high = np.maximum(o[series_indices], c[series_indices])
        bodies_low = np.minimum(o[series_indices], c[series_indices])
        series_high = float(bodies_high.max())
        series_low = float(bodies_low.min())
    else:
        series_high = float(h[series_indices].max())
        series_low = float(l[series_indices].min())

    # Forward scan: first close that breaks the opposing extreme
    # SHORT (bearish setup): bullish series collected; fires DOWN through series_low
    # LONG  (bullish setup): bearish series collected; fires UP through series_high
    extreme = series_low if direction == 'SHORT' else series_high
    for j in range(c2_idx + 1, min(n, c2_idx + 1 + max_forward)):
        if direction == 'SHORT' and c[j] < series_low:
            return dict(
                fire_idx=j,
                fire_ts_ns=int(ts[j]),
                series_high=series_high,
                series_low=series_low,
                series_range=series_high - series_low,
                series_extreme_broken=extreme,
                series_count=len(series_indices),
            )
        if direction == 'LONG' and c[j] > series_high:
            return dict(
                fire_idx=j,
                fire_ts_ns=int(ts[j]),
                series_high=series_high,
                series_low=series_low,
                series_range=series_high - series_low,
                series_extreme_broken=extreme,
                series_count=len(series_indices),
            )
    return None


def find_cisd_npg_in_window(o, c, h, l, ts, c2_idx, direction,
                            anchor_close_ts, body_confirm=True, max_series=20):
    """Same as find_cisd_npg but rejects fires past anchor_close_ts.

    The anchor window is the HTF candle bucket that contains the sweep candle.
    Fires must occur strictly before the next HTF candle opens (i.e., fire_ts < anchor_close_ts).
    """
    # Compute max_forward as the number of LTF bars left in the window
    n = len(o)
    j = c2_idx + 1
    max_forward = 0
    while j < n and ts[j] < anchor_close_ts:
        max_forward += 1
        j += 1

    if max_forward == 0:
        return None

    return find_cisd_npg(o, c, h, l, ts, c2_idx, direction,
                         body_confirm=body_confirm,
                         max_series=max_series,
                         max_forward=max_forward)
