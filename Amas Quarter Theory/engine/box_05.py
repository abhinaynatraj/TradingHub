"""05-box construction and band level derivation.

The 05-box = price range from the first 5 minute bars of an hour (minutes
:00, :01, :02, :03, :04 inclusive). Bands at ±0.05% and ±0.10% from box
edges. Pine and Python must produce identical numeric outputs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd

from engine import constants as C


@dataclass(frozen=True)
class Box05:
    high: float
    low: float
    locked: bool                # True iff all 5 bars (:00..:04) have arrived


@dataclass(frozen=True)
class BandLevels:
    upper_05: float             # box_high * 1.0005
    upper_10: float             # box_high * 1.0010
    lower_05: float             # box_low  * 0.9995
    lower_10: float             # box_low  * 0.9990


def build_box_05(bars: Iterable[dict], hour_anchor_ts: pd.Timestamp) -> Box05:
    """Build a Box05 from any iterable of bar dicts (must include 'ts','high','low').

    Filters bars to those at minutes 0-4 of the hour matching hour_anchor_ts.
    `locked` is True iff all 5 minutes are represented.
    """
    minutes_seen: set[int] = set()
    box_high = float("-inf")
    box_low = float("inf")
    for bar in bars:
        ts: pd.Timestamp = bar["ts"]
        if ts.normalize() != hour_anchor_ts.normalize() or ts.hour != hour_anchor_ts.hour:
            continue
        if ts.minute not in C.BOX_05_MINUTES:
            continue
        minutes_seen.add(ts.minute)
        if bar["high"] > box_high:
            box_high = bar["high"]
        if bar["low"] < box_low:
            box_low = bar["low"]
    locked = minutes_seen == set(C.BOX_05_MINUTES)
    return Box05(high=box_high, low=box_low, locked=locked)


def band_levels(box_high: float, box_low: float) -> BandLevels:
    """Compute the four band levels from a 05-box's high/low."""
    o05, o10 = C.BAND_OFFSETS  # (0.0005, 0.0010)
    return BandLevels(
        upper_05=box_high * (1.0 + o05),
        upper_10=box_high * (1.0 + o10),
        lower_05=box_low  * (1.0 - o05),
        lower_10=box_low  * (1.0 - o10),
    )
