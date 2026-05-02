"""Wick Lick detection — npg-spec sweep + close-back-inside.

A bearish Wick Lick fires when:
  - last_closed.high > prev_closed.high  (sweep)
  - last_closed.close < prev_closed.high (closed back inside)
  - NOT also a full bullish double-sweep (last.l < prev.l AND last.c > prev.l)

A bullish Wick Lick is the mirror image.

Returns events with sweep_extreme (the swept candle's extreme), prev_extreme
(the prior candle's swept level), sweep_idx (HTF index), direction.
"""
import numpy as np


def detect_wick_licks(htf_arrs):
    """Detect all Wick Lick events in a sweep-TF candle series.

    Args:
        htf_arrs: dict with keys open/high/low/close/ts_ns (numpy arrays)

    Returns:
        list of dicts with keys: direction, sweep_extreme, prev_extreme,
        sweep_idx, sweep_ts_ns
    """
    o, h, l, c = htf_arrs['open'], htf_arrs['high'], htf_arrs['low'], htf_arrs['close']
    ts = htf_arrs['ts_ns']
    n = len(o)
    events = []

    for i in range(1, n):
        prev_h, prev_l = h[i-1], l[i-1]
        cur_h, cur_l, cur_c = h[i], l[i], c[i]

        # Double-sweep exclusion (matches npg source line 1106 / 1148):
        # not (high>prev.high AND low<prev.low AND close>prev.low AND close<prev.high)
        is_double_sweep = (cur_h > prev_h and cur_l < prev_l and
                           cur_c > prev_l and cur_c < prev_h)
        if is_double_sweep:
            continue

        # Bearish: swept prev high, closed back inside (below prev high)
        if cur_h > prev_h and cur_c < prev_h:
            events.append(dict(
                direction='SHORT',
                sweep_extreme=cur_h,
                prev_extreme=prev_h,
                sweep_idx=i,
                sweep_ts_ns=ts[i],
            ))
            continue

        # Bullish: swept prev low, closed back inside (above prev low)
        if cur_l < prev_l and cur_c > prev_l:
            events.append(dict(
                direction='LONG',
                sweep_extreme=cur_l,
                prev_extreme=prev_l,
                sweep_idx=i,
                sweep_ts_ns=ts[i],
            ))

    return events
