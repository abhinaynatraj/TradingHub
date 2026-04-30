"""Stats helpers: Wilson CI for binomial proportions.

Adapted from Amas Models/engine/stats.py — same formula, same conventions.
"""
from __future__ import annotations

import math


def wilson_ci(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Return (lo, hi) of the Wilson 95%-CI for wins / n. (0, 0) when n=0.

    Ensures the interval is strictly contained in [0, 1).
    """
    if n == 0:
        return 0.0, 0.0
    p = wins / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    lo = max(0.0, centre - half)
    hi = min(0.9999999999, centre + half)
    return lo, hi
