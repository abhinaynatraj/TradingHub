"""Filter predicates for npg-engine setups: Silver, Bias, Body-vs-Wick, SMT."""
import math


def candle_of_day(hour_et):
    """npg's bucket: floor(hour/4) + 1. Buckets 1..6 for hours 0..23."""
    return math.floor(hour_et / 4) + 1


def is_silver(direction, hour_et, last_close, prev_low, prev_prev_low,
              prev_high, prev_prev_high):
    """Silver gate: late-week timing AND aggressive close.

    Timing: candleOfDay==5 OR (candleOfDay==4 AND hour_et >= 13)
    Aggressive close (bearish): last_close < min(prev_low, prev_prev_low)
    Aggressive close (bullish): last_close > max(prev_high, prev_prev_high)
    """
    cod = candle_of_day(hour_et)
    timing_ok = (cod == 5) or (cod == 4 and hour_et >= 13)
    if not timing_ok:
        return False

    if direction == 'SHORT':
        return last_close < prev_low and last_close < prev_prev_low
    elif direction == 'LONG':
        return last_close > prev_high and last_close > prev_prev_high
    return False


def is_smt(direction, es_window_high, es_window_low, es_prev_high, es_prev_low):
    """SMT divergence: ES did NOT sweep its corresponding HTF extreme.

    For a bearish NQ Wick Lick (NQ swept prev high), SMT means ES's max during
    the same HTF window did NOT exceed ES's prev high.
    """
    if direction == 'SHORT':
        es_swept = es_window_high > es_prev_high
        return not es_swept
    elif direction == 'LONG':
        es_swept = es_window_low < es_prev_low
        return not es_swept
    return False
