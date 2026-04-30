"""Mutual information ranking of state-vector fields.

The empirical aggregator emits state keys as concatenations. To compute MI,
we need samples broken out into individual fields. compute_strip_order takes
a long-form DataFrame with one column per field and one outcome column.

Strip order = ascending by MI (least informative field stripped first).
"""
from __future__ import annotations

import math
from typing import Iterable

import pandas as pd


def _mutual_information(df: pd.DataFrame, field: str, outcome_col: str = "outcome") -> float:
    """Standard MI(X; Y) in nats."""
    n = len(df)
    if n == 0:
        return 0.0
    pxy = df.groupby([field, outcome_col]).size() / n
    px = df.groupby(field).size() / n
    py = df.groupby(outcome_col).size() / n
    mi = 0.0
    for (x, y), p in pxy.items():
        if p > 0:
            mi += p * math.log(p / (px[x] * py[y]))
    return mi


def compute_strip_order(df: pd.DataFrame, fields: Iterable[str], outcome_col: str = "outcome") -> list[str]:
    """Return field names sorted ascending by MI with outcome.
    Lowest-MI field is stripped first in fallback."""
    scored = [(f, _mutual_information(df, f, outcome_col)) for f in fields]
    scored.sort(key=lambda x: x[1])
    return [f for f, _ in scored]
