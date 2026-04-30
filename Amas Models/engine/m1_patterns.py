"""M1 entry pattern detectors for the Amas Models engine.

Three pattern detectors that scan a slice of M1 bars looking for the mentor's
three entry trigger patterns:

- **Order Block (OB):** a 1-bar opposite-color candle that gets immediately
  broken by structure (a higher-high after it for longs; lower-low for shorts).
  Entry on retest into the OB body. Stop is the OB's far edge.

- **Breaker Block:** a *failed* OB. The original (opposite-direction) OB gets
  violated, and the trade enters on the retest of that broken zone from the
  other side.

- **Inversion FVG (INV_FVG):** a 3-bar Fair Value Gap that's been violated
  through and re-tested from the opposite side. The gap's role flips.

These functions are CAUSAL and PURE: they return all patterns visible up to
each pattern's `formed_ts`, in chronological order, with no duplicates and no
mutation of the input. Downstream code (Tasks 3.1c/d) will pick which one fires
per setup.

Per the design spec, Category C (lookahead): the pattern is "formed" at
`formed_ts`; downstream code can only enter at or after that timestamp.
Truncating `bars` to `bars[bars.ts <= p.formed_ts]` and re-running must produce
the same pattern.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd


Direction = Literal["long", "short"]


@dataclass(frozen=True)
class M1Pattern:
    """A detected M1 entry pattern.

    Attributes:
        kind: one of "OB", "BREAKER", "INV_FVG".
        direction: the trade direction this pattern enables ("long" or "short").
        formed_ts: the M1 bar timestamp at which the pattern is COMPLETE. The
            earliest a downstream model could enter is at or after this ts.
        entry_price: limit-order price the trade enters at.
        invalidation_price: price level whose breach invalidates the pattern;
            used as the raw stop price.
        notes: short human-readable description.
    """
    kind: Literal["OB", "BREAKER", "INV_FVG"]
    direction: Direction
    formed_ts: pd.Timestamp
    entry_price: float
    invalidation_price: float
    notes: str = ""


# --------------------------------------------------------------------------- #
# Order Block
# --------------------------------------------------------------------------- #


def _find_obs_indexed(
    bars: pd.DataFrame,
    direction: Direction,
    min_body_ratio: float = 0.0,
    min_break_displacement_pts: float = 0.0,
) -> list[tuple[int, int]]:
    """Internal helper: return list of (i, j) integer-position pairs for OBs.

    For LONG: bars[i] is down-close, bars[j].high > max(bars[i:j].high), and no
    bar in [i, j) violates bars[i].low.
    For SHORT: mirror.

    `j` is the FIRST bar index that completes the structure break. (If multiple
    later bars also complete the break, only the first counts — that's where
    the pattern is "formed".)

    Returns positional indices into `bars` (0..len(bars)-1), NOT pandas Index
    labels — the caller is responsible for pulling .iloc / .iat off them.

    Filters (default off — pass-through behavior unchanged):

    - `min_body_ratio`: |close - open| / max(high - low, eps) of the OB candle
      (bar `i`) must be ≥ this ratio. Filters out doji / pin-bar OBs that the
      mentor would not call real Order Blocks. Default 0.0 = no filter.
    - `min_break_displacement_pts`: the breaking bar (bar `j`) must violate the
      running extreme by at least this many points. Filters out one-tick pokes
      that don't reflect real impulse. Default 0.0 = no filter.
    """
    n = len(bars)
    if n < 2:
        return []

    opens = bars["open"].to_numpy()
    highs = bars["high"].to_numpy()
    lows = bars["low"].to_numpy()
    closes = bars["close"].to_numpy()

    out: list[tuple[int, int]] = []

    for i in range(n - 1):
        # Body-ratio gate on the OB candle itself
        if min_body_ratio > 0.0:
            rng_i = max(highs[i] - lows[i], 1e-9)
            body_i = abs(closes[i] - opens[i])
            if (body_i / rng_i) < min_body_ratio:
                continue

        if direction == "long":
            if not (closes[i] < opens[i]):  # need DOWN-close
                continue
            ob_high = highs[i]
            ob_low = lows[i]
            running_max_high = ob_high  # max of bars[i..j-1].high
            for j in range(i + 1, n):
                # Check: does bars[j].high break the running max?
                if highs[j] > running_max_high:
                    # Displacement gate: the break must be at least N points
                    if (highs[j] - running_max_high) < min_break_displacement_pts:
                        # Not enough displacement; abort this OB candidate
                        break
                    out.append((i, j))
                    break
                # Otherwise check invalidation BEFORE updating running max.
                # If bars[j].low < ob_low, the OB is invalidated; abort.
                if lows[j] < ob_low:
                    break
                running_max_high = max(running_max_high, highs[j])
        else:  # short
            if not (closes[i] > opens[i]):  # need UP-close
                continue
            ob_high = highs[i]
            ob_low = lows[i]
            running_min_low = ob_low
            for j in range(i + 1, n):
                if lows[j] < running_min_low:
                    if (running_min_low - lows[j]) < min_break_displacement_pts:
                        break
                    out.append((i, j))
                    break
                if highs[j] > ob_high:
                    break
                running_min_low = min(running_min_low, lows[j])

    return out


def find_order_blocks(
    bars: pd.DataFrame,
    direction: Direction,
    min_body_ratio: float = 0.0,
    min_break_displacement_pts: float = 0.0,
) -> list[M1Pattern]:
    """Find all OB patterns of `direction` in the slice `bars`.

    Args:
        bars: M1 bars DataFrame (same dtypes as engine.db.load_bars).
        direction: "long" or "short".
        min_body_ratio: filter — OB candle's body must be ≥ this fraction of
            its total range. Default 0.0 = no filter. Use ~0.5 to require
            at least an even-body candle, ~0.6 to require a clear directional
            body (mentor's "aggressive candle" notion).
        min_break_displacement_pts: filter — the breaking bar must violate
            the OB's running extreme by at least this many points. Default
            0.0 = no filter. Use ~1.0 on NQ to filter out one-tick pokes
            that don't reflect real impulse.

    Returns:
        List of M1Pattern (kind="OB"), sorted by formed_ts ascending.
    """
    if direction not in ("long", "short"):
        raise ValueError(f"direction must be 'long' or 'short', got {direction!r}")

    n = len(bars)
    if n < 2:
        return []

    pairs = _find_obs_indexed(
        bars, direction,
        min_body_ratio=min_body_ratio,
        min_break_displacement_pts=min_break_displacement_pts,
    )
    ts = bars["ts"].to_numpy()
    opens = bars["open"].to_numpy()
    highs = bars["high"].to_numpy()
    lows = bars["low"].to_numpy()

    patterns: list[M1Pattern] = []
    for (i, j) in pairs:
        if direction == "long":
            entry = float(opens[i])
            invalid = float(lows[i])
        else:
            entry = float(opens[i])
            invalid = float(highs[i])
        formed_ts = pd.Timestamp(ts[j])
        ob_ts = pd.Timestamp(ts[i])
        patterns.append(M1Pattern(
            kind="OB",
            direction=direction,
            formed_ts=formed_ts,
            entry_price=entry,
            invalidation_price=invalid,
            notes=f"OB bar {ob_ts} broken at {formed_ts}",
        ))

    patterns.sort(key=lambda p: p.formed_ts)
    return patterns


# --------------------------------------------------------------------------- #
# Breaker Block
# --------------------------------------------------------------------------- #


def find_breakers(
    bars: pd.DataFrame,
    direction: Direction,
    min_body_ratio: float = 0.0,
    min_break_displacement_pts: float = 0.0,
) -> list[M1Pattern]:
    """Find all Breaker patterns of `direction` in the slice `bars`.

    A LONG breaker = a SHORT-direction OB at (i, j) that is then violated to
    the upside (some bar k > j has close > bars[i].high), and then re-tested
    from above (some bar m > k has low <= bars[i].open — i.e., back into the
    OB body, which is now flipped support).

    SHORT mirrors: a LONG-direction OB violated downward then re-tested from
    below.

    Args:
        bars, direction: as in find_order_blocks.
        min_body_ratio, min_break_displacement_pts: filters applied to the
            SOURCE OB (the failed OB that becomes the breaker). See
            find_order_blocks for semantics. Defaults 0.0 = no filter.

    Returns: list of M1Pattern (kind="BREAKER") sorted by formed_ts ascending.
    """
    if direction not in ("long", "short"):
        raise ValueError(f"direction must be 'long' or 'short', got {direction!r}")

    n = len(bars)
    if n < 2:
        return []

    # Opposite-direction OBs are the SOURCE of breakers in this direction.
    opp = "short" if direction == "long" else "long"
    ob_pairs = _find_obs_indexed(
        bars, opp,
        min_body_ratio=min_body_ratio,
        min_break_displacement_pts=min_break_displacement_pts,
    )
    if not ob_pairs:
        return []

    ts = bars["ts"].to_numpy()
    opens = bars["open"].to_numpy()
    highs = bars["high"].to_numpy()
    lows = bars["low"].to_numpy()
    closes = bars["close"].to_numpy()

    patterns: list[M1Pattern] = []
    for (i, j) in ob_pairs:
        # Find first k > j where the OB has been violated.
        # For a SHORT OB (used to build a LONG breaker): OB_high = highs[i].
        # Violation = close > OB_high.
        # For a LONG OB (SHORT breaker): OB_low = lows[i]. Violation = close < OB_low.
        if direction == "long":
            ob_far = float(highs[i])  # OB_high — the side that gets broken
            entry_price = float(opens[i])
            invalid_price = float(lows[i])
            k = None
            for kk in range(j + 1, n):
                if closes[kk] > ob_far:
                    k = kk
                    break
            if k is None:
                continue
            # Find first m > k where price retests OB body from above.
            # Retest condition: low <= entry_price (i.e., touches OB_open from above).
            m = None
            for mm in range(k + 1, n):
                if lows[mm] <= entry_price:
                    m = mm
                    break
            if m is None:
                continue
        else:  # short breaker from a LONG OB
            ob_far = float(lows[i])  # OB_low — broken downward
            entry_price = float(opens[i])
            invalid_price = float(highs[i])
            k = None
            for kk in range(j + 1, n):
                if closes[kk] < ob_far:
                    k = kk
                    break
            if k is None:
                continue
            m = None
            for mm in range(k + 1, n):
                if highs[mm] >= entry_price:
                    m = mm
                    break
            if m is None:
                continue

        formed_ts = pd.Timestamp(ts[m])
        ob_ts = pd.Timestamp(ts[i])
        patterns.append(M1Pattern(
            kind="BREAKER",
            direction=direction,
            formed_ts=formed_ts,
            entry_price=entry_price,
            invalidation_price=invalid_price,
            notes=f"Breaker from OB at {ob_ts}, broken at {pd.Timestamp(ts[k])}, retested at {formed_ts}",
        ))

    # De-duplicate on (formed_ts, entry_price): two different source OBs could
    # in theory produce the same breaker. Keep the first occurrence.
    seen: set[tuple[pd.Timestamp, float]] = set()
    unique: list[M1Pattern] = []
    for p in sorted(patterns, key=lambda x: x.formed_ts):
        key = (p.formed_ts, p.entry_price)
        if key in seen:
            continue
        seen.add(key)
        unique.append(p)
    return unique


# --------------------------------------------------------------------------- #
# Inversion FVG
# --------------------------------------------------------------------------- #


def _find_fvgs_indexed(bars: pd.DataFrame, fvg_dir: Literal["bullish", "bearish"]) -> list[tuple[int, int, int]]:
    """Return all FVG triples (i, i+1, i+2) of the given polarity.

    Bullish FVG: bars[i].high < bars[i+2].low (an upward gap in the trio).
    Bearish FVG: bars[i].low > bars[i+2].high (a downward gap).
    """
    n = len(bars)
    if n < 3:
        return []
    highs = bars["high"].to_numpy()
    lows = bars["low"].to_numpy()
    out: list[tuple[int, int, int]] = []
    for i in range(n - 2):
        if fvg_dir == "bullish":
            if highs[i] < lows[i + 2]:
                out.append((i, i + 1, i + 2))
        else:  # bearish
            if lows[i] > highs[i + 2]:
                out.append((i, i + 1, i + 2))
    return out


def find_inversion_fvgs(bars: pd.DataFrame, direction: Direction) -> list[M1Pattern]:
    """Find all Inversion-FVG patterns of `direction` in the slice `bars`.

    LONG: a BEARISH FVG (bar i.low > bar i+2.high) that gets violated upward
    (some bar k > i+2 has close > bar i.low), then re-tested from above (some
    bar m > k has low <= bar i+2.high).

    SHORT mirrors: a BULLISH FVG violated downward then re-tested from below.

    Returns: list of M1Pattern (kind="INV_FVG") sorted by formed_ts ascending.
    """
    if direction not in ("long", "short"):
        raise ValueError(f"direction must be 'long' or 'short', got {direction!r}")

    n = len(bars)
    if n < 3:
        return []

    # For a LONG inversion, we need a BEARISH FVG (gap that's later inverted upward).
    fvg_polarity = "bearish" if direction == "long" else "bullish"
    triples = _find_fvgs_indexed(bars, fvg_polarity)
    if not triples:
        return []

    ts = bars["ts"].to_numpy()
    highs = bars["high"].to_numpy()
    lows = bars["low"].to_numpy()
    closes = bars["close"].to_numpy()

    patterns: list[M1Pattern] = []
    for (i, _i1, i2) in triples:
        if direction == "long":
            # Bearish FVG zone = [bars[i2].high, bars[i].low].
            # Upper edge (entry on inversion) = bars[i].low.
            # Lower edge (invalidation) = bars[i2].high.
            entry_price = float(lows[i])
            invalid_price = float(highs[i2])
            # k = first bar > i2 with close > entry_price (gap violated upward)
            k = None
            for kk in range(i2 + 1, n):
                if closes[kk] > entry_price:
                    k = kk
                    break
            if k is None:
                continue
            # m = first bar > k with low <= invalid_price (retest from above)
            m = None
            for mm in range(k + 1, n):
                if lows[mm] <= invalid_price:
                    m = mm
                    break
            if m is None:
                continue
        else:  # short
            # Bullish FVG zone = [bars[i].high, bars[i2].low].
            # Lower edge (entry on inversion for shorts) = bars[i].high.
            # Upper edge (invalidation) = bars[i2].low.
            entry_price = float(highs[i])
            invalid_price = float(lows[i2])
            k = None
            for kk in range(i2 + 1, n):
                if closes[kk] < entry_price:
                    k = kk
                    break
            if k is None:
                continue
            m = None
            for mm in range(k + 1, n):
                if highs[mm] >= invalid_price:
                    m = mm
                    break
            if m is None:
                continue

        formed_ts = pd.Timestamp(ts[m])
        fvg_ts = pd.Timestamp(ts[i])
        patterns.append(M1Pattern(
            kind="INV_FVG",
            direction=direction,
            formed_ts=formed_ts,
            entry_price=entry_price,
            invalidation_price=invalid_price,
            notes=f"InvFVG from FVG at {fvg_ts}, inverted at {pd.Timestamp(ts[k])}, retested at {formed_ts}",
        ))

    seen: set[tuple[pd.Timestamp, float]] = set()
    unique: list[M1Pattern] = []
    for p in sorted(patterns, key=lambda x: x.formed_ts):
        key = (p.formed_ts, p.entry_price)
        if key in seen:
            continue
        seen.add(key)
        unique.append(p)
    return unique
