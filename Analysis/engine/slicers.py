"""Reusable groupby helpers for the analyses.

A `metric_fn` takes a sub-dataframe and returns a dict of metric values. The
slicer attaches a `count` column automatically and returns one row per slice.
"""
from __future__ import annotations
from typing import Callable, Any
import pandas as pd

MetricFn = Callable[[pd.DataFrame], dict[str, Any]]

_RESERVED = frozenset({'count'})


def _apply(df: pd.DataFrame, by: list[str] | None, metric_fn: MetricFn) -> pd.DataFrame:
    if by is None:
        rec = dict(metric_fn(df))
        if _RESERVED & rec.keys():
            raise ValueError(
                f"metric_fn returned reserved key(s): {sorted(_RESERVED & rec.keys())!r}"
            )
        rec['count'] = len(df)
        return pd.DataFrame([rec])
    rows = []
    reserved = _RESERVED | set(by)
    for keys, sub in df.groupby(by):
        if not isinstance(keys, tuple):
            keys = (keys,)
        rec = dict(metric_fn(sub))
        if reserved & rec.keys():
            raise ValueError(
                f"metric_fn returned reserved key(s) overlapping with count or {by!r}: "
                f"{sorted(reserved & rec.keys())!r}"
            )
        rec['count'] = len(sub)
        for k_name, k_val in zip(by, keys):
            rec[k_name] = k_val
        rows.append(rec)
    return pd.DataFrame(rows)


def slice_aggregate(df: pd.DataFrame, metric_fn: MetricFn) -> pd.DataFrame:
    return _apply(df, None, metric_fn)


def slice_by_year(df: pd.DataFrame, metric_fn: MetricFn) -> pd.DataFrame:
    return _apply(df, ['year'], metric_fn)


def slice_by_hour(df: pd.DataFrame, metric_fn: MetricFn) -> pd.DataFrame:
    return _apply(df, ['hour_of_day_et'], metric_fn)


def slice_by_dow(df: pd.DataFrame, metric_fn: MetricFn) -> pd.DataFrame:
    return _apply(df, ['dow'], metric_fn)


def slice_by_hour_dow(df: pd.DataFrame, metric_fn: MetricFn) -> pd.DataFrame:
    return _apply(df, ['hour_of_day_et', 'dow'], metric_fn)
