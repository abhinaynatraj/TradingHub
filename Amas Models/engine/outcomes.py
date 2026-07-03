"""SL/TP outcome resolver for the Amas Models engine.

Per the design spec, Category D (Outcome resolver fidelity):
- Same-bar TP/SL tie → SL (matches Fractal Sweep + indicator)
- OUTCOME_MAX_BARS = 1440; unresolved trades are EXPIRED (excluded from WR/EV)
- MAE/MFE for resolved trades stop at resolution bar
- Direction symmetric (long/short tested separately)
- Deterministic & idempotent (same input → same output)

Entry bar (where bar.ts == setup.entry_ts) is EXCLUDED from resolution per
invariant C.3 — it contributes to entry price only, never to TP/SL detection.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

import pandas as pd

from engine.constants import OUTCOME_MAX_BARS


Direction = Literal["long", "short"]
OutcomeKind = Literal["TP", "SL", "EXPIRED"]


@dataclass(frozen=True)
class Setup:
    """A trade setup ready for outcome resolution."""
    entry_ts: pd.Timestamp
    entry_price: float
    sl_price: float
    tp_price: float
    direction: Direction

    def __post_init__(self):
        if self.direction not in ("long", "short"):
            raise ValueError(f"direction must be 'long' or 'short', got {self.direction!r}")
        if abs(self.entry_price - self.sl_price) < 1e-9:
            raise ValueError(f"setup has zero risk (entry == sl_price = {self.entry_price})")
        if self.direction == "long":
            if self.sl_price >= self.entry_price:
                raise ValueError(f"long setup requires sl_price < entry_price")
            if self.tp_price <= self.entry_price:
                raise ValueError(f"long setup requires tp_price > entry_price")
        else:  # short
            if self.sl_price <= self.entry_price:
                raise ValueError(f"short setup requires sl_price > entry_price")
            if self.tp_price >= self.entry_price:
                raise ValueError(f"short setup requires tp_price < entry_price")

    @property
    def risk_pts(self) -> float:
        return abs(self.entry_price - self.sl_price)


@dataclass(frozen=True)
class Outcome:
    """Result of outcome resolution."""
    outcome: OutcomeKind
    r: Optional[float]  # None for EXPIRED
    resolution_ts: Optional[pd.Timestamp]  # None for EXPIRED
    mae_pts: float  # max adverse excursion (always non-negative)
    mfe_pts: float  # max favorable excursion (always non-negative)
    bars_to_resolve: int  # number of bars scanned (entry-bar-exclusive)


def resolve_outcome(bars: pd.DataFrame, setup: Setup, max_bars: int = OUTCOME_MAX_BARS) -> Outcome:
    """Walk forward bar-by-bar from entry+1 until TP, SL, or max_bars exhausted.

    Per spec invariants:
    - Bars where ts <= setup.entry_ts are excluded.
    - If a single bar's high >= TP AND low <= SL, outcome is SL (tie-break).
    - MAE/MFE measured only over bars actually scanned (stop at resolution).
    """
    post_entry = bars[bars["ts"] > setup.entry_ts]
    if len(post_entry) == 0:
        return Outcome(outcome="EXPIRED", r=None, resolution_ts=None, mae_pts=0.0, mfe_pts=0.0, bars_to_resolve=0)

    scan = post_entry.iloc[:max_bars]

    mae = 0.0
    mfe = 0.0

    for i, bar in enumerate(scan.itertuples(index=False), start=1):
        if setup.direction == "long":
            adverse = setup.entry_price - bar.low
            favorable = bar.high - setup.entry_price
            sl_hit = bar.low <= setup.sl_price
            tp_hit = bar.high >= setup.tp_price
        else:  # short
            adverse = bar.high - setup.entry_price
            favorable = setup.entry_price - bar.low
            sl_hit = bar.high >= setup.sl_price
            tp_hit = bar.low <= setup.tp_price

        if adverse > mae:
            mae = adverse
        if favorable > mfe:
            mfe = favorable

        if sl_hit and tp_hit:
            # Same-bar tie → SL
            return Outcome(
                outcome="SL", r=-1.0, resolution_ts=bar.ts,
                mae_pts=mae, mfe_pts=mfe, bars_to_resolve=i,
            )
        if tp_hit:
            r = (setup.tp_price - setup.entry_price) / setup.risk_pts
            if setup.direction == "short":
                r = (setup.entry_price - setup.tp_price) / setup.risk_pts
            return Outcome(
                outcome="TP", r=r, resolution_ts=bar.ts,
                mae_pts=mae, mfe_pts=mfe, bars_to_resolve=i,
            )
        if sl_hit:
            return Outcome(
                outcome="SL", r=-1.0, resolution_ts=bar.ts,
                mae_pts=mae, mfe_pts=mfe, bars_to_resolve=i,
            )

    # Exhausted max_bars
    return Outcome(
        outcome="EXPIRED", r=None, resolution_ts=None,
        mae_pts=mae, mfe_pts=mfe, bars_to_resolve=len(scan),
    )


def compute_draw_hit(
    bars: pd.DataFrame,
    setup: Setup,
    draw_price: float,
    max_bars: int = OUTCOME_MAX_BARS,
) -> tuple[bool, Optional[pd.Timestamp]]:
    """Did price reach `draw_price` within max_bars after entry, before SL?

    The mentor's edge claim is "the prior H1 extreme is hit ~80% of the time
    after the H1 closes outside it." That's measured by THIS function, not by
    the 1R take profit. The 1R is risk management; the draw_hit is the edge.

    Returns (hit: bool, hit_ts: Timestamp | None). hit=True if any bar's high
    reached `draw_price` (long) or low reached `draw_price` (short) before
    SL was hit; the timestamp is that bar's ts. hit=False otherwise.

    Note: this scan ignores TP — it's measuring "did the draw get touched
    eventually," even if the trade was already booked at 1R. SL still
    invalidates the draw thesis (if price reverses past SL before reaching
    the draw, the move never happened and hit=False).
    """
    post_entry = bars[bars["ts"] > setup.entry_ts]
    if len(post_entry) == 0:
        return (False, None)
    scan = post_entry.iloc[:max_bars]

    for bar in scan.itertuples(index=False):
        if setup.direction == "long":
            sl_hit = bar.low <= setup.sl_price
            draw_hit = bar.high >= draw_price
        else:  # short
            sl_hit = bar.high >= setup.sl_price
            draw_hit = bar.low <= draw_price

        # Same-bar tie → SL invalidates the draw thesis
        if sl_hit and draw_hit:
            return (False, None)
        if draw_hit:
            return (True, bar.ts)
        if sl_hit:
            return (False, None)

    return (False, None)
