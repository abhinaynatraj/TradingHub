"""DB load and data-quality enforcement for the Amas Models engine.

Per the design spec, Category A (TZ correctness) and Category E (Data quality):
every load must be tz-aware [ns] resolution, monotonic, unique, OHLC-sane.
The assertions run in production, not gated on DEBUG.

Reads the shared `candle_science.duckdb` from the sibling Fractal Sweep folder
in read-only mode. Never writes — daily updates stay in Fractal Sweep's cron.
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
        start: inclusive start date as 'YYYY-MM-DD' (in NY tz). Optional.
        end: exclusive end date as 'YYYY-MM-DD' (in NY tz). Optional.

    Returns a DataFrame with columns: ts, open, high, low, close, volume.
    All invariants (tz-aware, [ns], unique, monotonic, OHLC-sane) are asserted
    before return. If they fail, this function raises AssertionError.
    """
    if table not in ("nq_1m", "es_1m"):
        raise ValueError(f"Unknown table: {table!r}. Expected 'nq_1m' or 'es_1m'.")

    where_clauses = []
    params: list[object] = []
    if start is not None:
        where_clauses.append("timezone('America/New_York', timestamp) >= ?::TIMESTAMPTZ")
        params.append(f"{start} 00:00:00-05")  # naive offset; query is tz-aware at SQL layer
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

    # Force [ns] resolution + NY tz. pandas 2.0+ may hand back [us]; this is the bug
    # that bit Fractal Sweep silently for months. Be explicit.
    if df["ts"].dt.tz is None:
        df["ts"] = df["ts"].dt.tz_localize("UTC").dt.tz_convert("America/New_York")
    df["ts"] = df["ts"].astype("datetime64[ns, America/New_York]")
    df["volume"] = df["volume"].astype("int64")

    assert_load_invariants(df)
    return df


def assert_load_invariants(df: pd.DataFrame) -> None:
    """Fail loudly if the loaded DataFrame violates any silent-edge invariant.

    Runs in production, not gated on DEBUG. The cost is microseconds; the value
    is loud failure on any data corruption.
    """
    expected_cols = ["ts", "open", "high", "low", "close", "volume"]
    assert list(df.columns) == expected_cols, f"schema: expected {expected_cols}, got {list(df.columns)}"

    assert df["ts"].dt.tz is not None, "ts must be tz-aware (got naive timestamps)"
    assert df["ts"].dtype.unit == "ns", f"ts must be [ns] resolution, got [{df['ts'].dtype.unit}]"

    assert df["ts"].is_unique, "ts must be unique (duplicate bars)"
    assert df["ts"].is_monotonic_increasing, "ts must be monotonic increasing"

    if len(df) > 0:
        low_le_min = (df["low"] <= df[["open", "close", "high"]].min(axis=1)).all()
        high_ge_max = (df["high"] >= df[["open", "close", "low"]].max(axis=1)).all()
        assert low_le_min and high_ge_max, "OHLC sanity violated: low > min(o,c,h) or high < max(o,c,l)"


def check_gaps(df: pd.DataFrame, threshold_minutes: int = 5) -> list[dict]:
    """Report intra-session gaps larger than threshold_minutes.

    RTH = 09:30-16:00 ET. Cross-session gaps (overnight, weekend) are expected
    and not reported. Each reported gap is a dict with keys: prev_ts, next_ts,
    gap_minutes.

    Note: this is a best-effort check. It does not abort load; it returns the
    list of gaps so callers can tag affected setups (`has_data_gap: bool`).
    """
    if len(df) < 2:
        return []
    diffs = df["ts"].diff().dt.total_seconds() / 60.0
    times = df["ts"].dt.time
    in_rth = (times >= pd.Timestamp("09:30").time()) & (times <= pd.Timestamp("16:00").time())
    same_session = df["ts"].dt.date == df["ts"].shift(1).dt.date
    flagged = (diffs > threshold_minutes) & same_session & in_rth & in_rth.shift(1, fill_value=False)
    gaps = []
    for i in df.index[flagged]:
        gaps.append({
            "prev_ts": df.loc[i - 1, "ts"] if i - 1 in df.index else df["ts"].iloc[df.index.get_loc(i) - 1],
            "next_ts": df.loc[i, "ts"],
            "gap_minutes": float(diffs.loc[i]),
        })
    return gaps
