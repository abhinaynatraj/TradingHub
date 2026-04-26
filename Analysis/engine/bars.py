"""Bar construction layer.

Builds canonical hourly + quarter-of-hour bar dataframes from the shared
nq_1m table. All downstream studies consume these dataframes.

Trading day convention: 18:00 ET → next-day 17:00 ET.
- 17:00 ET hour is excluded (settlement gap, no data).
- Sunday 18:00 hour treats Friday 16:00 as its previous trading hour
  (handled implicitly: cleaned hourly dataframe has Sun 18:00 as the
   row immediately after Fri 16:00, so shift(1) gives the right answer).
"""
from __future__ import annotations
from pathlib import Path
import duckdb
import pandas as pd
import numpy as np


def db_path() -> Path:
    """Resolve the shared DuckDB path (always Fractal Sweep/candle_science.duckdb)."""
    # Analysis/engine/bars.py → Analysis/engine → Analysis → Statistic.ally
    return Path(__file__).resolve().parent.parent.parent / 'Fractal Sweep' / 'candle_science.duckdb'


def _enrich_minutes(df: pd.DataFrame) -> pd.DataFrame:
    """Add ny_ts, year, dow, hour_of_day_et columns. Input timestamp may be
    naive, UTC, or tz-aware; output ny_ts is always America/New_York."""
    out = df.copy()
    ts = pd.to_datetime(out['timestamp'])
    if ts.dt.tz is None:
        # Stored timestamps in the DB are tz-aware (America/Toronto);
        # synthetic data may be naive in NY — handle both.
        ts = ts.dt.tz_localize('America/New_York')
    out['ny_ts'] = ts.dt.tz_convert('America/New_York')
    out['year'] = out['ny_ts'].dt.year
    out['dow'] = out['ny_ts'].dt.dayofweek  # Mon=0
    out['hour_of_day_et'] = out['ny_ts'].dt.hour
    return out


def load_minutes(con: duckdb.DuckDBPyConnection | None = None,
                 start: str | None = None,
                 end: str | None = None) -> pd.DataFrame:
    """Load 1-min NQ bars from the shared DuckDB.

    Returns a dataframe with columns: timestamp (raw), ny_ts, open, high, low,
    close, volume, year, dow, hour_of_day_et.
    """
    close_when_done = False
    if con is None:
        con = duckdb.connect(str(db_path()), read_only=True)
        close_when_done = True
    try:
        where = []
        params: list = []
        if start:
            where.append("timezone('America/New_York', timestamp) >= ?")
            params.append(start)
        if end:
            where.append("timezone('America/New_York', timestamp) < ?")
            params.append(end)
        where_sql = ('WHERE ' + ' AND '.join(where)) if where else ''
        sql = f"""
        SELECT timestamp, open, high, low, close, volume
        FROM nq_1m
        {where_sql}
        ORDER BY timestamp
        """
        df = con.execute(sql, params).fetchdf()
    finally:
        if close_when_done:
            con.close()
    return _enrich_minutes(df)
