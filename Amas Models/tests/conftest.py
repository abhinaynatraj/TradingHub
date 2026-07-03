"""Shared pytest fixtures for the Amas Models test suite.

Synthetic OHLC factories used across multiple test modules.
"""
from __future__ import annotations

import pandas as pd
import pytest


@pytest.fixture
def synthetic_bars_1m():
    """5 days of 1m bars, RTH only (09:30-16:00 ET), simple drift up.

    Returns a DataFrame with the same dtypes the real DB load produces:
    ts (tz-aware datetime64[ns, America/New_York]), open/high/low/close (float),
    volume (int64).
    """
    def _make(start: str = "2024-01-08", days: int = 5, base_price: float = 100.0):
        rows = []
        for d in pd.bdate_range(start=start, periods=days, tz="America/New_York"):
            session_start = d.replace(hour=9, minute=30, second=0, microsecond=0)
            session_end = d.replace(hour=16, minute=0, second=0, microsecond=0)
            ts_range = pd.date_range(session_start, session_end, freq="1min", inclusive="left")
            for i, ts in enumerate(ts_range):
                price = base_price + i * 0.01
                rows.append({
                    "ts": ts,
                    "open": price,
                    "high": price + 0.05,
                    "low": price - 0.05,
                    "close": price + 0.02,
                    "volume": 100,
                })
            base_price += 1.0  # carry over end-of-day to next day
        df = pd.DataFrame(rows)
        df["ts"] = df["ts"].astype("datetime64[ns, America/New_York]")
        df["volume"] = df["volume"].astype("int64")
        return df
    return _make
