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


def build_hourly(minutes: pd.DataFrame) -> pd.DataFrame:
    """Aggregate enriched 1-min bars into hourly bars.

    Rules:
    - Each hour requires all 60 of its 1-min bars; otherwise dropped.
    - The 17:00 ET hour is always dropped (settlement gap).
    - Output columns: hour_start_et, open, high, low, close, volume,
      year, dow, hour_of_day_et.
    """
    df = minutes.copy()
    df['hour_start_et'] = df['ny_ts'].dt.floor('h')
    grouped = df.groupby('hour_start_et').agg(
        open=('open', 'first'),
        high=('high', 'max'),
        low=('low', 'min'),
        close=('close', 'last'),
        volume=('volume', 'sum'),
        n_minutes=('open', 'size'),
    ).reset_index()
    # Completeness
    grouped = grouped[grouped['n_minutes'] == 60].drop(columns='n_minutes')
    # Drop 17:00 ET hour (settlement gap)
    grouped = grouped[grouped['hour_start_et'].dt.hour != 17]
    # Slicing columns
    grouped['year'] = grouped['hour_start_et'].dt.year
    grouped['dow'] = grouped['hour_start_et'].dt.dayofweek
    grouped['hour_of_day_et'] = grouped['hour_start_et'].dt.hour
    return grouped.sort_values('hour_start_et').reset_index(drop=True)


def attach_prev_hour(hourly: pd.DataFrame) -> pd.DataFrame:
    """Attach prev_hour_open/high/low/close/mid columns by shifting one row.

    Because build_hourly() already drops incomplete hours and the 17:00 settlement
    hour, "previous row" naturally means "previous valid trading hour." This also
    handles the 49h Fri 16:00 → Sun 18:00 gap correctly without special casing.
    """
    df = hourly.sort_values('hour_start_et').reset_index(drop=True).copy()
    for col in ('open', 'high', 'low', 'close'):
        df[f'prev_hour_{col}'] = df[col].shift(1)
    df['prev_hour_mid'] = (df['prev_hour_high'] + df['prev_hour_low']) / 2
    return df


def build_quarters(minutes: pd.DataFrame, hourly: pd.DataFrame) -> pd.DataFrame:
    """Build 4 quarter rows per valid hour (Q1=:00-14, Q2=:15-29, Q3=:30-44, Q4=:45-59).

    Only generates quarters for hours that exist in `hourly` (already filtered for
    completeness and the 17:00 gap).

    Output columns: hour_start_et, quarter, open, high, low, close, volume,
    q_high_minute, q_low_minute (minute-of-hour, 0-59).
    """
    valid_hours = set(hourly['hour_start_et'])
    df = minutes.copy()
    df['hour_start_et'] = df['ny_ts'].dt.floor('h')
    df = df[df['hour_start_et'].isin(valid_hours)].copy()
    df['minute_of_hour'] = df['ny_ts'].dt.minute
    df['quarter'] = df['minute_of_hour'] // 15 + 1  # 1..4

    # idxmax/idxmin within each (hour, quarter) for the extreme minute
    grouped = df.groupby(['hour_start_et', 'quarter'])
    agg = grouped.agg(
        open=('open', 'first'),
        high=('high', 'max'),
        low=('low', 'min'),
        close=('close', 'last'),
        volume=('volume', 'sum'),
    ).reset_index()

    # Extreme-minute attribution: get the minute_of_hour of the max-high and min-low row
    high_idx = grouped['high'].idxmax()
    low_idx = grouped['low'].idxmin()
    high_min = df.loc[high_idx.values, ['hour_start_et', 'quarter', 'minute_of_hour']].rename(
        columns={'minute_of_hour': 'q_high_minute'}).reset_index(drop=True)
    low_min = df.loc[low_idx.values, ['hour_start_et', 'quarter', 'minute_of_hour']].rename(
        columns={'minute_of_hour': 'q_low_minute'}).reset_index(drop=True)

    out = agg.merge(high_min, on=['hour_start_et', 'quarter']).merge(
        low_min, on=['hour_start_et', 'quarter'])
    return out.sort_values(['hour_start_et', 'quarter']).reset_index(drop=True)
