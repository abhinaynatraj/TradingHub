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
        bars: dict with ts_ns/open/high/low/close numpy arrays. If the bars are a
            RESAMPLED (higher-timeframe) series, also pass a `ts_close_ns` array
            (the timestamp at which each bar CLOSES, i.e. when the bar becomes
            known). The FVG is then stamped with `ts_close_ns[i]` — the moment the
            gap is actually confirmed — NOT the bar's start. This prevents
            look-ahead bias: a 5m FVG must not be "known" until the 5m bar closes.
            For a native 1m series (no `ts_close_ns`), `ts_ns[i]` is used as-is.
        min_bp: minimum gap size in basis points of the reference price.

    Returns:
        list of dicts: {idx, ts_ns, dir (1|-1), top, bot, gap_pts}. idx is the
        bar index at which the gap is confirmed (the 3rd candle). ts_ns is the
        CONFIRMATION timestamp (bar close for resampled series).
    """
    high = bars['high']
    low = bars['low']
    # Confirmation timestamp: bar-close for resampled series, else the bar ts.
    ts = bars.get('ts_close_ns', bars['ts_ns'])
    out = []
    for i in range(2, len(high)):
        # NOTE: bp threshold reference differs by direction (near edge), matching the Pine source.
        # Bullish
        if low[i] > high[i - 2]:
            bot = float(high[i - 2])
            top = float(low[i])
            gap = top - bot
            if gap >= bot * (min_bp / 10000.0):
                out.append(dict(idx=i, ts_ns=int(ts[i]), dir=1, top=top, bot=bot, gap_pts=gap))
        # Bearish (elif: a single bar cannot satisfy both gap conditions)
        elif high[i] < low[i - 2]:
            bot = float(high[i])
            top = float(low[i - 2])
            gap = top - bot
            if gap >= top * (min_bp / 10000.0):
                out.append(dict(idx=i, ts_ns=int(ts[i]), dir=-1, top=top, bot=bot, gap_pts=gap))
    return out


def is_mitigated(gap, close):
    """A gap is mitigated once a bar CLOSES through its far edge.

    Bull gap dies when close < bot (strictly; touching the edge is not mitigation). Bear gap dies when close > top.
    """
    if gap['dir'] == 1:
        return bool(close < gap['bot'])
    return bool(close > gap['top'])


def is_nested(ltf, htf, proximity_bp):
    """True if the LTF gap fits within the HTF gap (same direction) +/- proximity.

    prox is computed off the HTF bottom (a stable reference near the zone).
    """
    if ltf['dir'] != htf['dir']:
        return False
    prox = htf['bot'] * (proximity_bp / 10000.0)
    return bool(ltf['bot'] >= (htf['bot'] - prox) and ltf['top'] <= (htf['top'] + prox))
