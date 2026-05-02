"""DB load and data-quality enforcement for the Quarter Theory engine.

Reads the shared ../Fractal Sweep/candle_science.duckdb in read-only mode.
Asserts tz-aware [ns] resolution, monotonic, unique, OHLC-sane on every load.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import duckdb
import pandas as pd


def db_path() -> Path:
    """Path to the shared candle_science.duckdb. The DB lives in Fractal Sweep/."""
    return Path(__file__).resolve().parent.parent.parent / "Fractal Sweep" / "candle_science.duckdb"


def load_bars(
    table: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> pd.DataFrame:
    """Load 1m bars from the shared DB, converted to America/New_York at the SQL layer.

    Args:
        table: 'nq_1m' or 'es_1m'.
        start: inclusive start date 'YYYY-MM-DD' (NY tz). Optional.
        end: exclusive end date 'YYYY-MM-DD' (NY tz). Optional.
    """
    if table not in ("nq_1m", "es_1m"):
        raise ValueError(f"Unknown table: {table!r}. Expected 'nq_1m' or 'es_1m'.")

    where_clauses: list[str] = []
    params: list[object] = []
    if start is not None:
        where_clauses.append("timezone('America/New_York', timestamp) >= ?::TIMESTAMPTZ")
        params.append(f"{start} 00:00:00-05")
    if end is not None:
        where_clauses.append("timezone('America/New_York', timestamp) < ?::TIMESTAMPTZ")
        params.append(f"{end} 00:00:00-05")
    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    sql = f"""
        SELECT
            timezone('America/New_York', timestamp) AS ts,
            open, high, low, close, volume
        FROM {table}
        {where_sql}
        ORDER BY timestamp
    """

    with duckdb.connect(str(db_path()), read_only=True) as con:
        df = con.execute(sql, params).fetchdf()

    if df["ts"].dt.tz is None:
        df["ts"] = df["ts"].dt.tz_localize("UTC").dt.tz_convert("America/New_York")
    df["ts"] = df["ts"].astype("datetime64[ns, America/New_York]")
    df["volume"] = df["volume"].astype("int64")

    assert_load_invariants(df)
    return df


def assert_load_invariants(df: pd.DataFrame) -> None:
    """Fail loudly on schema, tz, monotonicity, uniqueness, or OHLC violations."""
    expected_cols = ["ts", "open", "high", "low", "close", "volume"]
    assert list(df.columns) == expected_cols, f"schema: expected {expected_cols}, got {list(df.columns)}"

    assert df["ts"].dt.tz is not None, "ts must be tz-aware (got naive timestamps)"
    assert df["ts"].dtype.unit == "ns", f"ts must be [ns] resolution, got [{df['ts'].dtype.unit}]"

    assert df["ts"].is_unique, "ts must be unique (duplicate bars)"
    assert df["ts"].is_monotonic_increasing, "ts must be monotonic increasing"

    if len(df) > 0:
        low_le_min = (df["low"] <= df[["open", "close", "high"]].min(axis=1)).all()
        high_ge_max = (df["high"] >= df[["open", "close", "low"]].max(axis=1)).all()
        assert low_le_min and high_ge_max, "OHLC sanity violated"
