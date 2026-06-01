"""Pure FVG detection, mitigation, and nesting logic for the Nested FVG backtest.

No DB or I/O — operates on bar dicts (ts_ns/open/high/low/close numpy arrays)
and returns plain Python structures so it is fully unit-testable.
"""
import numpy as np


def find_fvgs(bars, min_bp):
    """Detect 3-candle FVGs (Pine geometry).

    Bullish (BISI): low[i] > high[i-2] -> gap [high[i-2], low[i]], formed at i.
    Bearish (SIBI): high[i] < low[i-2] -> gap [high[i], low[i-2]], formed at i.

    Args:
        bars: dict with ts_ns/open/high/low/close numpy arrays.
        min_bp: minimum gap size in basis points of the reference price.

    Returns:
        list of dicts: {idx, ts_ns, dir (1|-1), top, bot, gap_pts}. idx is the
        bar index at which the gap is confirmed (the 3rd candle).
    """
    high = bars['high']
    low = bars['low']
    ts = bars['ts_ns']
    out = []
    for i in range(2, len(high)):
        # Bullish
        if low[i] > high[i - 2]:
            bot = float(high[i - 2])
            top = float(low[i])
            gap = top - bot
            if gap >= bot * (min_bp / 10000.0):
                out.append(dict(idx=i, ts_ns=int(ts[i]), dir=1, top=top, bot=bot, gap_pts=gap))
        # Bearish
        elif high[i] < low[i - 2]:
            bot = float(high[i])
            top = float(low[i - 2])
            gap = top - bot
            if gap >= top * (min_bp / 10000.0):
                out.append(dict(idx=i, ts_ns=int(ts[i]), dir=-1, top=top, bot=bot, gap_pts=gap))
    return out


def is_mitigated(gap, close):
    """A gap is mitigated once a bar CLOSES through its far edge.

    Bull gap dies when close < bot. Bear gap dies when close > top.
    """
    if gap['dir'] == 1:
        return close < gap['bot']
    return close > gap['top']
