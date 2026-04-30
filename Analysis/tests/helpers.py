"""Synthetic data builders for unit tests.

All tests build deterministic 1-min DataFrames with this builder rather than
hitting the real DuckDB. Timestamps are tz-aware in America/New_York.
"""
from __future__ import annotations
import pandas as pd
from datetime import timedelta
from zoneinfo import ZoneInfo

NY = ZoneInfo('America/New_York')


def make_minutes(start: str, n: int, ohlc_pattern=None, freq: str = '1min') -> pd.DataFrame:
    """Build n consecutive 1-min bars starting at `start` (ET).

    `ohlc_pattern`: optional callable(i) -> (open, high, low, close, volume).
    Default pattern: open=100+i, high=open+1, low=open-1, close=open+0.5, vol=10.
    """
    ts = pd.date_range(
        start=pd.Timestamp(start, tz=NY),
        periods=n,
        freq=freq,
    )
    rows = []
    for i, t in enumerate(ts):
        if ohlc_pattern is None:
            o, h, l, c, v = 100.0 + i, 100.0 + i + 1, 100.0 + i - 1, 100.0 + i + 0.5, 10
        else:
            o, h, l, c, v = ohlc_pattern(i)
        rows.append({
            'timestamp': t,
            'open': o, 'high': h, 'low': l, 'close': c, 'volume': v,
        })
    return pd.DataFrame(rows)


def make_hour(hour_start: str, *, ohlc=(100, 105, 95, 102), volume_per_min: int = 10,
              high_at_minute: int | None = None, low_at_minute: int | None = None) -> pd.DataFrame:
    """Build exactly 60 1-min bars covering a single hour.

    The high is placed at `high_at_minute` (default minute 0); low at `low_at_minute`
    (default minute 59). Other bars sit between to ensure aggregate OHLC == `ohlc`.
    """
    o, h, l, c = ohlc
    h_min = 0 if high_at_minute is None else high_at_minute
    l_min = 59 if low_at_minute is None else low_at_minute
    if h_min == l_min:
        raise ValueError("high and low minute must differ")

    # Validate OHLC internal consistency
    if not (l <= o and l <= c and h >= o and h >= c):
        raise ValueError(
            f"Malformed ohlc: must satisfy l<=o,c and h>=o,c — got {ohlc}"
        )

    # Validate minute indices are in [0, 59]
    if not (0 <= h_min <= 59):
        raise ValueError(f"high_at_minute must be in [0, 59], got {h_min}")
    if not (0 <= l_min <= 59):
        raise ValueError(f"low_at_minute must be in [0, 59], got {l_min}")

    rows = []
    base_ts = pd.Timestamp(hour_start, tz=NY)
    for i in range(60):
        ts = base_ts + timedelta(minutes=i)
        if i == 0:
            o_i = o
        else:
            o_i = (o + c) / 2
        if i == 59:
            c_i = c
        else:
            c_i = (o + c) / 2
        if i == h_min:
            h_i = h
        else:
            h_i = max(o_i, c_i)
        if i == l_min:
            l_i = l
        else:
            l_i = min(o_i, c_i)
        rows.append({'timestamp': ts, 'open': o_i, 'high': h_i, 'low': l_i,
                     'close': c_i, 'volume': volume_per_min})
    return pd.DataFrame(rows)


def concat_hours(*dfs: pd.DataFrame) -> pd.DataFrame:
    return pd.concat(dfs, ignore_index=True).sort_values('timestamp').reset_index(drop=True)
