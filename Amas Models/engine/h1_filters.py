"""Per-setup filter computations for the H1 Continuation model.

Each function computes a single `passes_<key>: bool` flag for a Continuation
setup. The model detector (Task 3.1d) calls these to attach `passes_*` columns
to every trade row; the dashboard then enumerates filter combos at viewing
time.

All functions are PURE: no I/O, no global state, no mutation of inputs.

Per the design spec, Category C (lookahead): the H1 filters operate on the
just-closed H1 row (or the prior H1 row, for `passes_target_after_42`) and
on H4/daily history *strictly before* the H1's `anchor_ts`. None of the
filters peek into bars that haven't formed yet.

Filter index (10 total, per `model_specs.md` "Cross-cutting concepts →
Confluences"):
    1.  passes_macro_010
    2.  passes_top3_macros
    3.  passes_avoid_lunch
    4.  passes_target_after_42
    5.  passes_no_opposite_struct_h1
    6.  passes_no_htf_rejection
    7.  passes_aggressive_body
    8.  passes_distribution_candle
    9.  passes_within_5m_structure
    10. passes_smt
"""
from __future__ import annotations

from typing import Literal, Optional

import pandas as pd


Direction = Literal["long", "short"]


# --------------------------------------------------------------------------- #
# Time-of-day filters (1, 2, 3)
# --------------------------------------------------------------------------- #


def passes_macro_010(entry_ts: pd.Timestamp) -> bool:
    """True iff `entry_ts` falls within the H1-internal macro window `:50–:10`.

    The window straddles the hour close: the last 10 minutes of the prior hour
    (`:50–:59`) and the first 10 minutes of the new hour (`:00–:10` inclusive).
    """
    minute = entry_ts.minute
    return minute >= 50 or minute <= 10


def passes_top3_macros(entry_ts: pd.Timestamp) -> bool:
    """True iff `entry_ts` falls in one of the top-3 NY macro windows.

    Windows (per M1 PDF 1:01:41 ranking):
        - 08:50–09:10
        - 09:50–10:10
        - 10:50–11:10
    """
    minute = entry_ts.minute
    hour = entry_ts.hour
    if minute >= 50 and hour in (8, 9, 10):
        return True
    if minute <= 10 and hour in (9, 10, 11):
        return True
    return False


def passes_avoid_lunch(entry_ts: pd.Timestamp) -> bool:
    """True iff `entry_ts` is OUTSIDE the explicitly-avoided lunch macro `11:50–12:10`.

    Returns False inside the lunch window, True everywhere else (including
    other macros and outside-macro times).
    """
    minute = entry_ts.minute
    hour = entry_ts.hour
    if minute >= 50 and hour == 11:
        return False
    if minute <= 10 and hour == 12:
        return False
    return True


# --------------------------------------------------------------------------- #
# H1-feature filters (4, 5, 7, 8)
# --------------------------------------------------------------------------- #


def passes_target_after_42(prior_h1: pd.Series, direction: Direction) -> bool:
    """:42 timing rule on the PRIOR H1 (the candle whose extreme is the draw).

    Per the spec: the high (long) or low (short) being targeted must have
    formed at minute >= 42 of its source candle.

    Args:
        prior_h1: the H1 row before the just-closed one (the one whose extreme
            is the trade's draw target). Must have `extreme_minute_high` and
            `extreme_minute_low` columns populated by `build_h1_anchors`.
        direction: trade direction. "long" checks `extreme_minute_high`;
            "short" checks `extreme_minute_low`.
    """
    if direction == "long":
        return int(prior_h1["extreme_minute_high"]) >= 42
    elif direction == "short":
        return int(prior_h1["extreme_minute_low"]) >= 42
    else:
        raise ValueError(f"direction must be 'long' or 'short', got {direction!r}")


def passes_no_opposite_struct_h1(h1: pd.Series, threshold: float = 0.5) -> bool:
    """True iff the just-closed H1 has NO large opposite-direction wick.

    For a bullish H1 (close > open), the opposite-side wick is the LOWER wick
    (= `min(open, close) - low`). For a bearish H1, the opposite wick is the
    UPPER wick (= `high - max(open, close)`). The body is `abs(close - open)`.

    Returns True iff `opposite_wick / max(body, 1e-9) <= threshold`.

    Default threshold = 0.5: opposite wick must be no more than 50% of body.
    For an exact-doji body, the ratio explodes → returns False (correctly
    flagging dojis as having opposite structure relative to their body).

    Note: this is an HEURISTIC for "opposite structure" per Open Question #5
    in `model_specs.md`. A more sophisticated definition (clean opposite-OB on
    the H1) is deferred.
    """
    open_ = float(h1["open"])
    close = float(h1["close"])
    high = float(h1["high"])
    low = float(h1["low"])

    body = abs(close - open_)
    if close >= open_:
        # bullish (or neutral) → opposite wick is the lower wick
        opposite_wick = min(open_, close) - low
    else:
        # bearish → opposite wick is the upper wick
        opposite_wick = high - max(open_, close)

    # Guard against doji (body ≈ 0): use a tiny floor so the ratio is finite.
    ratio = opposite_wick / max(body, 1e-9)
    return ratio <= threshold


def passes_aggressive_body(h1: pd.Series, threshold: float = 0.6) -> bool:
    """True iff the H1 body is at least `threshold` of the candle's total range.

    body = abs(close - open); range = high - low.
    Returns: body / max(range, 1e-9) >= threshold.

    Default 0.6 per `model_specs.md` (Open Question #4 initial heuristic).
    """
    open_ = float(h1["open"])
    close = float(h1["close"])
    high = float(h1["high"])
    low = float(h1["low"])
    body = abs(close - open_)
    rng = high - low
    return (body / max(rng, 1e-9)) >= threshold


def passes_distribution_candle(h1: pd.Series, direction: Direction) -> bool:
    """True iff the just-closed H1 is a DISTRIBUTION candle (not a pullback) for `direction`.

    Distinguishes the OHLC shape per the M3 transcript glossary:

    - **Bullish distribution (direction="long"):** opens, makes the LOW early,
      distributes upward, closes near the HIGH. The high is "unprotected"
      because there's not enough remaining time in the candle to defend it.
      Predicate: `extreme_minute_low < 42 AND extreme_minute_high >= 42`.

    - **Bearish distribution (direction="short"):** opens, makes the HIGH early,
      distributes downward, closes near the LOW. Mirror.
      Predicate: `extreme_minute_high < 42 AND extreme_minute_low >= 42`.

    The pullback variants (where the trade-direction extreme is formed early)
    return False — pullback candles are NOT tradeable per the mentor.

    Note: this is about the *just-closed* H1 (the source/trigger candle).
    `passes_target_after_42` is the analogous flag for the PRIOR H1 (the draw).
    Both must pass for an A+ Continuation setup.
    """
    em_high = int(h1["extreme_minute_high"])
    em_low = int(h1["extreme_minute_low"])
    if direction == "long":
        return em_low < 42 and em_high >= 42
    elif direction == "short":
        return em_high < 42 and em_low >= 42
    else:
        raise ValueError(f"direction must be 'long' or 'short', got {direction!r}")


# --------------------------------------------------------------------------- #
# HTF rejection (6)
# --------------------------------------------------------------------------- #


def passes_no_htf_rejection(
    h1: pd.Series,
    h4_bars: Optional[pd.DataFrame],
    daily_bars: Optional[pd.DataFrame],
    direction: Direction,
) -> bool:
    """True iff the H1's wick has NOT already swept a recent H4 or daily extreme.

    For direction "long" (Continuation bullish — H1 close above prior H1 high):
        the trade-direction wick is the UPPER wick. We don't want it to have
        already swept an H4 or daily HIGH. Returns True iff
            h1.high < max(recent H4 highs)  AND  h1.high < max(recent daily highs).

    For direction "short": mirrored on lows. Returns True iff
            h1.low > min(recent H4 lows)  AND  h1.low > min(recent daily lows).

    "Recent" = the most recent 24 H4 bars and 5 daily bars before
    `h1.anchor_ts` (the H4-window-equivalent of "the last day" and the
    daily-window-equivalent of "the last week").

    If EITHER `h4_bars` or `daily_bars` is None or empty, the entire check
    is skipped and the filter returns True — per the task spec, the absence
    of HTF context means we cannot refute the setup, so we let it pass. (The
    detector composition layer is responsible for choosing whether to load
    HTF data; absence here is a deliberate "skip" signal, not an error.)

    Args:
        h1: the just-closed H1 row.
        h4_bars: H4 anchors DataFrame (same schema as H1 anchors), or None.
        daily_bars: daily anchors DataFrame (same schema), or None.
        direction: trade direction.
    """
    # Spec: return True if EITHER is None or empty (skip the whole check).
    if h4_bars is None or len(h4_bars) == 0:
        return True
    if daily_bars is None or len(daily_bars) == 0:
        return True

    h1_anchor = h1["anchor_ts"]
    h1_high = float(h1["high"])
    h1_low = float(h1["low"])

    def _recent_extreme(df: pd.DataFrame, n: int, side: Literal["high", "low"]) -> Optional[float]:
        """Return max(high) or min(low) of the most recent `n` bars strictly
        before `h1_anchor`. None if no usable bars in the prior window."""
        prior = df[df["anchor_ts"] < h1_anchor]
        if len(prior) == 0:
            return None
        recent = prior.tail(n)
        if side == "high":
            return float(recent["high"].max())
        else:
            return float(recent["low"].min())

    if direction == "long":
        h4_max = _recent_extreme(h4_bars, 24, "high")
        d_max = _recent_extreme(daily_bars, 5, "high")
        # If neither HTF frame has prior bars before h1_anchor, treat as skip.
        h4_ok = (h4_max is None) or (h1_high < h4_max)
        d_ok = (d_max is None) or (h1_high < d_max)
        return h4_ok and d_ok
    elif direction == "short":
        h4_min = _recent_extreme(h4_bars, 24, "low")
        d_min = _recent_extreme(daily_bars, 5, "low")
        h4_ok = (h4_min is None) or (h1_low > h4_min)
        d_ok = (d_min is None) or (h1_low > d_min)
        return h4_ok and d_ok
    else:
        raise ValueError(f"direction must be 'long' or 'short', got {direction!r}")


# --------------------------------------------------------------------------- #
# 5-minute structure (9)
# --------------------------------------------------------------------------- #


def passes_within_5m_structure(
    entry_price: float,
    draw_price: float,
    threshold: float = 40.0,
) -> bool:
    """True iff entry-to-draw distance is within the M5 structure threshold.

    Per Transcript 5 (~02:23, ~47:30): when the distance from entry to draw
    exceeds ~40 NQ points, the mentor calls it "5-minute structure" and avoids
    it because stop-loss placement becomes unreliable (the M1 OB/Breaker
    that's near entry is too small relative to the move's scale).

    Returns True iff `abs(entry_price - draw_price) <= threshold`.

    Default 40.0 is in NQ points; calling code is responsible for swapping
    when running ES.
    """
    return abs(float(entry_price) - float(draw_price)) <= threshold


# --------------------------------------------------------------------------- #
# SMT / NQ-ES divergence (10)
# --------------------------------------------------------------------------- #


def passes_smt(
    nq_h1: pd.Series,
    prior_nq_extreme: Optional[float],
    es_h1_window: pd.DataFrame,
    prior_es_extreme: Optional[float],
    direction: Direction,
) -> bool:
    """True iff there is NQ-ES divergence at the just-closed NQ H1's extreme.

    For direction "long" (NQ Continuation bullish): NQ swept its prior H1 high
    but ES did NOT sweep its corresponding prior H1 high during the same H1
    window. Returns True iff:
        nq_h1.high > prior_nq_extreme  AND  es_h1_window['high'].max() <= prior_es_extreme

    For direction "short": mirror on lows.
        nq_h1.low < prior_nq_extreme  AND  es_h1_window['low'].min() >= prior_es_extreme

    Returns False (cannot compute SMT confidently) when:
    - `es_h1_window` is empty
    - `prior_nq_extreme` or `prior_es_extreme` is None
    - NQ failed to sweep its own prior level (no SMT to speak of)

    Args:
        nq_h1: the just-closed NQ H1 row (needs `high` and `low`).
        prior_nq_extreme: NQ's prior H1 high (long) or low (short). None to skip.
        es_h1_window: ES 1m bars in the same H1 window as `nq_h1` (same dtypes
            as `engine.db.load_bars` output).
        prior_es_extreme: ES's prior H1 high/low corresponding to
            `prior_nq_extreme`. None to skip.
        direction: trade direction.
    """
    if prior_nq_extreme is None or prior_es_extreme is None:
        return False
    if es_h1_window is None or len(es_h1_window) == 0:
        return False

    if direction == "long":
        nq_swept = float(nq_h1["high"]) > float(prior_nq_extreme)
        if not nq_swept:
            return False
        es_max_high = float(es_h1_window["high"].max())
        es_did_not_sweep = es_max_high <= float(prior_es_extreme)
        return es_did_not_sweep
    elif direction == "short":
        nq_swept = float(nq_h1["low"]) < float(prior_nq_extreme)
        if not nq_swept:
            return False
        es_min_low = float(es_h1_window["low"].min())
        es_did_not_sweep = es_min_low >= float(prior_es_extreme)
        return es_did_not_sweep
    else:
        raise ValueError(f"direction must be 'long' or 'short', got {direction!r}")
