# NQ Hourly Candle Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python engine + HTML dashboard that analyzes NQ hourly breakout follow-through and in-depth quarter-of-the-hour price action from the shared `nq_1m` DuckDB.

**Architecture:** Layered Python engine (`bars.py` → `breakout_study.py` + `quarter_study.py` → `run_all.py`) writes parquet to `Analysis/data/`. Three thin HTML pages in `Analysis/dashboard/` read parquet via DuckDB-Wasm.

**Tech Stack:** Python 3.9+, DuckDB, pandas, numpy, pyarrow (parquet), pytest. Browser: vanilla HTML/CSS/JS + DuckDB-Wasm + Chart.js (CDN).

**Spec reference:** `docs/superpowers/specs/2026-04-26-hourly-analysis-design.md`

---

## File Structure

```
Analysis/
├── hourly-analysis.md             (existing — leave alone)
├── engine/
│   ├── __init__.py
│   ├── bars.py
│   ├── breakout_study.py
│   ├── quarter_study.py
│   ├── slicers.py
│   └── run_all.py
├── data/                          (gitignored; created by run_all.py)
│   ├── manifest.json
│   ├── breakout/*.parquet
│   └── quarters/*.parquet
├── dashboard/
│   ├── index.html
│   ├── breakout.html
│   ├── quarters.html
│   ├── shared.css
│   └── shared.js
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── helpers.py
    ├── test_bars.py
    ├── test_breakout.py
    ├── test_quarter_study.py
    ├── test_slicers.py
    └── test_integration.py
```

---

## Task 1: Folder scaffold + gitignore + conftest

**Files:**
- Create: `Analysis/engine/__init__.py` (empty)
- Create: `Analysis/tests/__init__.py` (empty)
- Create: `Analysis/tests/conftest.py`
- Modify: `.gitignore` (root)

- [ ] **Step 1: Create folders**

```bash
mkdir -p Analysis/engine Analysis/tests Analysis/dashboard
touch Analysis/engine/__init__.py Analysis/tests/__init__.py
```

- [ ] **Step 2: Create `Analysis/tests/conftest.py`**

```python
"""Pytest conftest — adds engine dir to sys.path."""
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'engine'))
sys.path.insert(0, os.path.dirname(__file__))
```

- [ ] **Step 3: Add data dir to `.gitignore`**

Read the existing `.gitignore` first. Append (or add if missing):

```
Analysis/data/
```

- [ ] **Step 4: Verify pytest discovers the folder**

Run: `cd /Users/abhi/Projects/Statistic.ally && pytest Analysis/tests/ -v`
Expected: `no tests ran in 0.0Xs` (folder exists, no tests yet — this is success)

- [ ] **Step 5: Commit**

```bash
git add Analysis/engine/ Analysis/tests/ .gitignore
git commit -m "Analysis: scaffold engine + tests folders"
```

---

## Task 2: Test helpers (synthetic 1-min builder)

**Files:**
- Create: `Analysis/tests/helpers.py`

- [ ] **Step 1: Write `helpers.py`**

```python
"""Synthetic data builders for unit tests.

All tests build deterministic 1-min DataFrames with this builder rather than
hitting the real DuckDB. Timestamps are tz-aware in America/New_York.
"""
from __future__ import annotations
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
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
```

- [ ] **Step 2: Sanity test the helper**

Create `Analysis/tests/test_helpers.py`:

```python
"""Sanity check for the helpers themselves."""
import helpers


def test_make_hour_aggregates_correctly():
    df = helpers.make_hour('2024-01-02 10:00', ohlc=(100, 110, 90, 105),
                           high_at_minute=20, low_at_minute=40)
    assert len(df) == 60
    assert df['open'].iloc[0] == 100
    assert df['close'].iloc[59] == 105
    assert df['high'].max() == 110
    assert df['low'].min() == 90
    # Volume: 10 * 60
    assert df['volume'].sum() == 600


def test_make_minutes_default_pattern():
    df = helpers.make_minutes('2024-01-02 10:00', 5)
    assert len(df) == 5
    assert df['open'].iloc[0] == 100.0
    assert df['open'].iloc[4] == 104.0
```

- [ ] **Step 3: Run helper tests**

Run: `cd /Users/abhi/Projects/Statistic.ally && pytest Analysis/tests/test_helpers.py -v`
Expected: 2 passed

- [ ] **Step 4: Commit**

```bash
git add Analysis/tests/helpers.py Analysis/tests/test_helpers.py
git commit -m "Analysis: synthetic 1-min data builders for tests"
```

---

## Task 3: `bars.py` — DB connection and raw 1-min loader

**Files:**
- Create: `Analysis/engine/bars.py`

- [ ] **Step 1: Write the failing test**

Create `Analysis/tests/test_bars.py` (will grow over later tasks):

```python
"""Tests for Analysis/engine/bars.py."""
import pandas as pd
import pytest
import bars
import helpers


def test_db_path_resolves_to_fractal_sweep_duckdb():
    p = bars.db_path()
    assert p.name == 'candle_science.duckdb'
    assert p.parent.name == 'Fractal Sweep'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest Analysis/tests/test_bars.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bars'`

- [ ] **Step 3: Implement `bars.db_path()`**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest Analysis/tests/test_bars.py::test_db_path_resolves_to_fractal_sweep_duckdb -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add Analysis/engine/bars.py Analysis/tests/test_bars.py
git commit -m "Analysis: bars.db_path() resolves shared DuckDB"
```

---

## Task 4: `bars.py` — load 1-min data with NY tz conversion

**Files:**
- Modify: `Analysis/engine/bars.py`
- Modify: `Analysis/tests/test_bars.py`

- [ ] **Step 1: Add a test that loads from a synthetic dataframe (not the real DB)**

Append to `test_bars.py`:

```python
def test_load_minutes_from_df_adds_ny_columns():
    raw = helpers.make_minutes('2024-01-02 10:00', 3)
    df = bars._enrich_minutes(raw)
    assert 'ny_ts' in df.columns
    assert df['ny_ts'].dt.tz.zone == 'America/New_York'
    # First bar at 10:00 ET → year/dow/hour
    assert df['year'].iloc[0] == 2024
    assert df['hour_of_day_et'].iloc[0] == 10
    # 2024-01-02 is Tuesday → Python dow = 1
    assert df['dow'].iloc[0] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest Analysis/tests/test_bars.py::test_load_minutes_from_df_adds_ny_columns -v`
Expected: FAIL with `AttributeError: module 'bars' has no attribute '_enrich_minutes'`

- [ ] **Step 3: Implement `_enrich_minutes` and `load_minutes`**

Append to `bars.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest Analysis/tests/test_bars.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add Analysis/engine/bars.py Analysis/tests/test_bars.py
git commit -m "Analysis: bars.load_minutes() with NY tz enrichment"
```

---

## Task 5: `bars.py` — hourly aggregation with completeness filter

**Files:**
- Modify: `Analysis/engine/bars.py`
- Modify: `Analysis/tests/test_bars.py`

- [ ] **Step 1: Write failing tests for `build_hourly`**

Append to `test_bars.py`:

```python
def test_hourly_ohlc_matches_synthetic():
    minutes = helpers.make_hour('2024-01-02 10:00', ohlc=(100, 110, 90, 105),
                                high_at_minute=20, low_at_minute=40)
    minutes = bars._enrich_minutes(minutes)
    hourly = bars.build_hourly(minutes)
    assert len(hourly) == 1
    row = hourly.iloc[0]
    assert row['open'] == 100
    assert row['high'] == 110
    assert row['low'] == 90
    assert row['close'] == 105
    assert row['volume'] == 600
    assert row['hour_start_et'] == pd.Timestamp('2024-01-02 10:00', tz='America/New_York')


def test_hourly_drops_incomplete_hour():
    """An hour with only 59 minutes should be dropped."""
    minutes = helpers.make_hour('2024-01-02 10:00')
    minutes = minutes.iloc[:59].copy()  # remove last minute
    minutes = bars._enrich_minutes(minutes)
    hourly = bars.build_hourly(minutes)
    assert len(hourly) == 0


def test_hourly_drops_17_et_settlement_hour():
    """The 17:00 ET hour is always excluded even if data is present."""
    h17 = helpers.make_hour('2024-01-02 17:00')
    h18 = helpers.make_hour('2024-01-02 18:00')
    minutes = helpers.concat_hours(h17, h18)
    minutes = bars._enrich_minutes(minutes)
    hourly = bars.build_hourly(minutes)
    assert len(hourly) == 1
    assert hourly['hour_of_day_et'].iloc[0] == 18
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest Analysis/tests/test_bars.py -v`
Expected: 3 new tests FAIL with `AttributeError: module 'bars' has no attribute 'build_hourly'`

- [ ] **Step 3: Implement `build_hourly`**

Append to `bars.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest Analysis/tests/test_bars.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add Analysis/engine/bars.py Analysis/tests/test_bars.py
git commit -m "Analysis: bars.build_hourly() with 60-min completeness + 17:00 drop"
```

---

## Task 6: `bars.py` — previous-hour linkage including weekend gap

**Files:**
- Modify: `Analysis/engine/bars.py`
- Modify: `Analysis/tests/test_bars.py`

- [ ] **Step 1: Write failing tests for `attach_prev_hour`**

Append to `test_bars.py`:

```python
def test_prev_hour_columns_for_consecutive_hours():
    """Two adjacent hours: H2's prev_hour_* should equal H1's OHLC."""
    h1 = helpers.make_hour('2024-01-02 10:00', ohlc=(100, 110, 90, 105),
                           high_at_minute=20, low_at_minute=40)
    h2 = helpers.make_hour('2024-01-02 11:00', ohlc=(105, 115, 95, 110),
                           high_at_minute=10, low_at_minute=30)
    minutes = helpers.concat_hours(h1, h2)
    hourly = bars.build_hourly(bars._enrich_minutes(minutes))
    hourly = bars.attach_prev_hour(hourly)
    h2_row = hourly.iloc[1]
    assert h2_row['prev_hour_open'] == 100
    assert h2_row['prev_hour_high'] == 110
    assert h2_row['prev_hour_low'] == 90
    assert h2_row['prev_hour_close'] == 105
    assert h2_row['prev_hour_mid'] == 100.0  # (110 + 90) / 2


def test_prev_hour_skips_settlement_gap():
    """18:00 hour's prev_hour_* should equal previous day's 16:00 (skipping 17:00)."""
    h16 = helpers.make_hour('2024-01-02 16:00', ohlc=(200, 210, 190, 205),
                            high_at_minute=20, low_at_minute=40)
    h18 = helpers.make_hour('2024-01-02 18:00', ohlc=(205, 215, 195, 210),
                            high_at_minute=10, low_at_minute=30)
    minutes = helpers.concat_hours(h16, h18)
    hourly = bars.build_hourly(bars._enrich_minutes(minutes))
    hourly = bars.attach_prev_hour(hourly)
    h18_row = hourly[hourly['hour_of_day_et'] == 18].iloc[0]
    assert h18_row['prev_hour_high'] == 210
    assert h18_row['prev_hour_low'] == 190


def test_prev_hour_skips_weekend_gap():
    """Sun 18:00 hour's prev_hour_* should equal Fri 16:00's OHLC."""
    fri_16 = helpers.make_hour('2024-01-05 16:00', ohlc=(300, 310, 290, 305),
                               high_at_minute=20, low_at_minute=40)
    sun_18 = helpers.make_hour('2024-01-07 18:00', ohlc=(305, 315, 295, 310),
                               high_at_minute=10, low_at_minute=30)
    minutes = helpers.concat_hours(fri_16, sun_18)
    hourly = bars.build_hourly(bars._enrich_minutes(minutes))
    hourly = bars.attach_prev_hour(hourly)
    # Sunday in Python = dow 6
    sun_row = hourly[hourly['dow'] == 6].iloc[0]
    assert sun_row['prev_hour_high'] == 310
    assert sun_row['prev_hour_low'] == 290


def test_first_row_has_null_prev_hour():
    h1 = helpers.make_hour('2024-01-02 10:00')
    hourly = bars.build_hourly(bars._enrich_minutes(h1))
    hourly = bars.attach_prev_hour(hourly)
    assert pd.isna(hourly['prev_hour_high'].iloc[0])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest Analysis/tests/test_bars.py -v`
Expected: 4 new tests FAIL with `AttributeError: module 'bars' has no attribute 'attach_prev_hour'`

- [ ] **Step 3: Implement `attach_prev_hour`**

Append to `bars.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest Analysis/tests/test_bars.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add Analysis/engine/bars.py Analysis/tests/test_bars.py
git commit -m "Analysis: bars.attach_prev_hour() handles settlement + weekend gaps"
```

---

## Task 7: `bars.py` — quarter bars

**Files:**
- Modify: `Analysis/engine/bars.py`
- Modify: `Analysis/tests/test_bars.py`

- [ ] **Step 1: Write failing tests for `build_quarters`**

Append to `test_bars.py`:

```python
def test_quarter_bars_tile_hour_exactly():
    """Q1.open = hour.open, Q4.close = hour.close, max(Q.high) = hour.high,
    min(Q.low) = hour.low."""
    minutes = helpers.make_hour('2024-01-02 10:00', ohlc=(100, 110, 90, 105),
                                high_at_minute=20, low_at_minute=40)
    enriched = bars._enrich_minutes(minutes)
    hourly = bars.build_hourly(enriched)
    quarters = bars.build_quarters(enriched, hourly)
    assert len(quarters) == 4
    qs = quarters.sort_values('quarter').reset_index(drop=True)
    assert qs['quarter'].tolist() == [1, 2, 3, 4]
    assert qs['open'].iloc[0] == 100
    assert qs['close'].iloc[3] == 105
    assert qs['high'].max() == 110
    assert qs['low'].min() == 90


def test_quarter_high_low_minute_offsets_correct():
    """Quarter 2 contains minutes 15-29; high at minute 20 → q_high_minute = 20."""
    minutes = helpers.make_hour('2024-01-02 10:00', ohlc=(100, 110, 90, 105),
                                high_at_minute=20, low_at_minute=40)
    enriched = bars._enrich_minutes(minutes)
    hourly = bars.build_hourly(enriched)
    quarters = bars.build_quarters(enriched, hourly)
    q2 = quarters[quarters['quarter'] == 2].iloc[0]
    q3 = quarters[quarters['quarter'] == 3].iloc[0]
    assert q2['q_high_minute'] == 20
    assert q3['q_low_minute'] == 40


def test_quarters_only_built_for_valid_hours():
    """Hour with only 59 minutes is excluded → no quarter rows for it."""
    h_full = helpers.make_hour('2024-01-02 10:00')
    h_short = helpers.make_hour('2024-01-02 11:00').iloc[:59]
    minutes = helpers.concat_hours(h_full, h_short)
    enriched = bars._enrich_minutes(minutes)
    hourly = bars.build_hourly(enriched)
    quarters = bars.build_quarters(enriched, hourly)
    assert quarters['hour_start_et'].nunique() == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest Analysis/tests/test_bars.py -v`
Expected: 3 new tests FAIL with `AttributeError: module 'bars' has no attribute 'build_quarters'`

- [ ] **Step 3: Implement `build_quarters`**

Append to `bars.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest Analysis/tests/test_bars.py -v`
Expected: 12 passed

- [ ] **Step 5: Commit**

```bash
git add Analysis/engine/bars.py Analysis/tests/test_bars.py
git commit -m "Analysis: bars.build_quarters() with extreme-minute attribution"
```

---

## Task 8: `bars.py` — top-level `build_all` driver

**Files:**
- Modify: `Analysis/engine/bars.py`
- Modify: `Analysis/tests/test_bars.py`

- [ ] **Step 1: Write failing test**

Append to `test_bars.py`:

```python
def test_build_all_from_minutes_returns_both_dataframes():
    h1 = helpers.make_hour('2024-01-02 10:00', ohlc=(100, 110, 90, 105),
                           high_at_minute=20, low_at_minute=40)
    h2 = helpers.make_hour('2024-01-02 11:00', ohlc=(105, 115, 95, 110),
                           high_at_minute=10, low_at_minute=30)
    minutes = helpers.concat_hours(h1, h2)
    enriched = bars._enrich_minutes(minutes)
    hourly, quarters = bars.build_all_from_minutes(enriched)
    assert len(hourly) == 2
    assert len(quarters) == 8
    assert 'prev_hour_high' in hourly.columns
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest Analysis/tests/test_bars.py -v`
Expected: 1 new test FAIL with `AttributeError`

- [ ] **Step 3: Implement `build_all_from_minutes` and `build_all`**

Append to `bars.py`:

```python
def build_all_from_minutes(minutes: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build (hourly_with_prev, quarters) from already-enriched 1-min bars."""
    hourly = build_hourly(minutes)
    hourly = attach_prev_hour(hourly)
    quarters = build_quarters(minutes, hourly)
    return hourly, quarters


def build_all(start: str | None = None, end: str | None = None
              ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Connect to the shared DB, load minutes in [start, end), build both dataframes."""
    minutes = load_minutes(start=start, end=end)
    return build_all_from_minutes(minutes)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest Analysis/tests/test_bars.py -v`
Expected: 13 passed

- [ ] **Step 5: Commit**

```bash
git add Analysis/engine/bars.py Analysis/tests/test_bars.py
git commit -m "Analysis: bars.build_all() top-level driver"
```

---

## Task 9: `slicers.py` — groupby helpers

**Files:**
- Create: `Analysis/engine/slicers.py`
- Create: `Analysis/tests/test_slicers.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for Analysis/engine/slicers.py."""
import pandas as pd
import pytest
import slicers


def _sample_df():
    return pd.DataFrame({
        'year': [2024, 2024, 2025, 2025, 2025],
        'dow': [0, 1, 0, 1, 2],
        'hour_of_day_et': [10, 10, 11, 11, 12],
        'value': [1, 2, 3, 4, 5],
    })


def _mean_metric(sub: pd.DataFrame) -> dict:
    return {'avg': sub['value'].mean()}


def test_slice_aggregate_returns_one_row():
    out = slicers.slice_aggregate(_sample_df(), _mean_metric)
    assert len(out) == 1
    assert out['avg'].iloc[0] == 3.0
    assert out['count'].iloc[0] == 5


def test_slice_by_year_returns_one_row_per_year():
    out = slicers.slice_by_year(_sample_df(), _mean_metric)
    assert len(out) == 2
    assert set(out['year']) == {2024, 2025}
    row_2024 = out[out['year'] == 2024].iloc[0]
    assert row_2024['count'] == 2
    assert row_2024['avg'] == 1.5


def test_slice_by_hour_returns_one_row_per_hour():
    out = slicers.slice_by_hour(_sample_df(), _mean_metric)
    assert set(out['hour_of_day_et']) == {10, 11, 12}


def test_slice_by_dow_returns_one_row_per_dow():
    out = slicers.slice_by_dow(_sample_df(), _mean_metric)
    assert set(out['dow']) == {0, 1, 2}


def test_slice_by_hour_dow_grid():
    out = slicers.slice_by_hour_dow(_sample_df(), _mean_metric)
    # 5 unique (hour, dow) combos in the sample
    assert len(out) == 5
    assert {'hour_of_day_et', 'dow', 'count', 'avg'}.issubset(out.columns)


def test_count_column_always_present():
    out = slicers.slice_by_year(_sample_df(), _mean_metric)
    assert 'count' in out.columns
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest Analysis/tests/test_slicers.py -v`
Expected: 6 FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `slicers.py`**

```python
"""Reusable groupby helpers for the analyses.

A `metric_fn` takes a sub-dataframe and returns a dict of metric values. The
slicer attaches a `count` column automatically and returns one row per slice.
"""
from __future__ import annotations
from typing import Callable, Any
import pandas as pd

MetricFn = Callable[[pd.DataFrame], dict[str, Any]]


def _apply(df: pd.DataFrame, by: list[str] | None, metric_fn: MetricFn) -> pd.DataFrame:
    if by is None:
        rec = metric_fn(df)
        rec['count'] = len(df)
        return pd.DataFrame([rec])
    rows = []
    for keys, sub in df.groupby(by):
        if not isinstance(keys, tuple):
            keys = (keys,)
        rec = metric_fn(sub)
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest Analysis/tests/test_slicers.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add Analysis/engine/slicers.py Analysis/tests/test_slicers.py
git commit -m "Analysis: slicers.py with year/hour/dow/grid groupby helpers"
```

---

## Task 10: `breakout_study.py` — classification

**Files:**
- Create: `Analysis/engine/breakout_study.py`
- Create: `Analysis/tests/test_breakout.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for Analysis/engine/breakout_study.py."""
import pandas as pd
import pytest
import breakout_study as bs
import bars
import helpers


def _build_pair(h1_ohlc, h2_ohlc, h1_high_min=20, h1_low_min=40,
                h2_high_min=20, h2_low_min=40):
    h0 = helpers.make_hour('2024-01-02 09:00', ohlc=(100, 105, 95, 100),
                           high_at_minute=20, low_at_minute=40)
    h1 = helpers.make_hour('2024-01-02 10:00', ohlc=h1_ohlc,
                           high_at_minute=h1_high_min, low_at_minute=h1_low_min)
    h2 = helpers.make_hour('2024-01-02 11:00', ohlc=h2_ohlc,
                           high_at_minute=h2_high_min, low_at_minute=h2_low_min)
    minutes = helpers.concat_hours(h0, h1, h2)
    enriched = bars._enrich_minutes(minutes)
    hourly, quarters = bars.build_all_from_minutes(enriched)
    return enriched, hourly, quarters


def test_classify_bullish_breakout():
    """H1.close > H0.high → bullish."""
    # H0 high = 105; H1 close = 110 > 105
    _, hourly, _ = _build_pair((100, 115, 95, 110), (110, 120, 100, 115))
    result = bs.classify(hourly)
    h1 = result.iloc[1]
    assert h1['breakout'] == 'bullish'


def test_classify_bearish_breakout():
    """H1.close < H0.low → bearish."""
    # H0 low = 95; H1 close = 90 < 95
    _, hourly, _ = _build_pair((100, 105, 85, 90), (90, 95, 80, 85))
    result = bs.classify(hourly)
    assert result.iloc[1]['breakout'] == 'bearish'


def test_classify_strict_inequality_equal_is_neither():
    """H1.close == H0.high → neither (strict)."""
    # H0 high = 105; H1 close = 105 exactly
    _, hourly, _ = _build_pair((100, 110, 95, 105), (105, 115, 100, 110))
    result = bs.classify(hourly)
    assert result.iloc[1]['breakout'] == 'neither'


def test_classify_inside_bar_is_neither():
    """H1.high < H0.high AND H1.low > H0.low → inside bar → neither."""
    # H0: 95-105; H1: 97-103 (inside)
    _, hourly, _ = _build_pair((100, 103, 97, 100), (100, 110, 95, 105))
    result = bs.classify(hourly)
    assert result.iloc[1]['breakout'] == 'neither'


def test_classify_first_row_excluded():
    """First row has null prev_hour and is excluded from classification."""
    h0 = helpers.make_hour('2024-01-02 10:00')
    enriched = bars._enrich_minutes(h0)
    hourly, _ = bars.build_all_from_minutes(enriched)
    result = bs.classify(hourly)
    # First (only) row has null prev_hour_high → not classified
    assert result.iloc[0]['breakout'] == 'no_prev'
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest Analysis/tests/test_breakout.py -v`
Expected: 5 FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `classify`**

```python
"""Hourly breakout follow-through study.

For each hour H1 with a valid prev hour H0:
- bullish breakout: H1.close > H0.high  (strict)
- bearish breakout: H1.close < H0.low   (strict)
- neither: everything else (including inside bars)

Then for each breakout, look at H2 to detect:
- bullish follow-through: H2 prints high > H1.high at any minute
- bearish follow-through: H2 prints low < H1.low at any minute
- immediate-reversal: H2 takes out the *opposite* extreme of H1
"""
from __future__ import annotations
import pandas as pd
import numpy as np


def classify(hourly: pd.DataFrame) -> pd.DataFrame:
    """Add a `breakout` column to the hourly dataframe.

    Values: 'bullish', 'bearish', 'neither', or 'no_prev' (first row, no H0).
    """
    df = hourly.copy()
    breakout = pd.Series('neither', index=df.index, dtype='object')
    no_prev_mask = df['prev_hour_high'].isna()
    bull = df['close'] > df['prev_hour_high']
    bear = df['close'] < df['prev_hour_low']
    breakout.loc[bull] = 'bullish'
    breakout.loc[bear] = 'bearish'
    breakout.loc[no_prev_mask] = 'no_prev'
    df['breakout'] = breakout
    # h1_open vs prev_mid (above/below/equal)
    df['h1_open_vs_prev_mid'] = np.where(
        df['open'] > df['prev_hour_mid'], 'above',
        np.where(df['open'] < df['prev_hour_mid'], 'below', 'equal')
    )
    df.loc[no_prev_mask, 'h1_open_vs_prev_mid'] = None
    return df
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest Analysis/tests/test_breakout.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add Analysis/engine/breakout_study.py Analysis/tests/test_breakout.py
git commit -m "Analysis: breakout_study.classify() + prev_mid context"
```

---

## Task 11: `breakout_study.py` — H2 follow-through detection with first-touch minute

**Files:**
- Modify: `Analysis/engine/breakout_study.py`
- Modify: `Analysis/tests/test_breakout.py`

- [ ] **Step 1: Write failing tests**

Append to `test_breakout.py`:

```python
def test_followthrough_bullish_takeout_in_q1_of_h2():
    """H1 close > H0 high (bullish). H2 prints higher high at minute 7 (Q1)."""
    # H0 high=105, H1 high=115/close=110, H2 high=120 at minute 7
    h0 = helpers.make_hour('2024-01-02 09:00', ohlc=(100, 105, 95, 100),
                           high_at_minute=20, low_at_minute=40)
    h1 = helpers.make_hour('2024-01-02 10:00', ohlc=(100, 115, 95, 110),
                           high_at_minute=30, low_at_minute=40)
    h2 = helpers.make_hour('2024-01-02 11:00', ohlc=(110, 120, 105, 115),
                           high_at_minute=7, low_at_minute=40)
    minutes = helpers.concat_hours(h0, h1, h2)
    enriched = bars._enrich_minutes(minutes)
    hourly, _ = bars.build_all_from_minutes(enriched)
    classified = bs.classify(hourly)
    events = bs.attach_followthrough(classified, enriched)
    # H1 (row 1) is bullish breakout; followthrough should be True; q = 1
    h1_row = events.iloc[1]
    assert h1_row['breakout'] == 'bullish'
    assert h1_row['followthrough'] == True
    assert h1_row['takeout_quarter_of_h2'] == 1


def test_followthrough_bullish_takeout_in_q2():
    """Higher high in H2 first occurs at minute 16 → Q2."""
    h0 = helpers.make_hour('2024-01-02 09:00', ohlc=(100, 105, 95, 100),
                           high_at_minute=20, low_at_minute=40)
    h1 = helpers.make_hour('2024-01-02 10:00', ohlc=(100, 115, 95, 110),
                           high_at_minute=30, low_at_minute=40)
    h2 = helpers.make_hour('2024-01-02 11:00', ohlc=(110, 120, 105, 115),
                           high_at_minute=16, low_at_minute=40)
    minutes = helpers.concat_hours(h0, h1, h2)
    enriched = bars._enrich_minutes(minutes)
    hourly, _ = bars.build_all_from_minutes(enriched)
    events = bs.attach_followthrough(bs.classify(hourly), enriched)
    assert events.iloc[1]['takeout_quarter_of_h2'] == 2


def test_followthrough_strict_no_takeout_when_equal():
    """H2.high == H1.high (no strict break) → not a takeout."""
    h0 = helpers.make_hour('2024-01-02 09:00', ohlc=(100, 105, 95, 100),
                           high_at_minute=20, low_at_minute=40)
    h1 = helpers.make_hour('2024-01-02 10:00', ohlc=(100, 115, 95, 110),
                           high_at_minute=30, low_at_minute=40)
    # H2 high equals H1 high (115) — exactly, no strict break
    h2 = helpers.make_hour('2024-01-02 11:00', ohlc=(110, 115, 105, 112),
                           high_at_minute=10, low_at_minute=40)
    minutes = helpers.concat_hours(h0, h1, h2)
    enriched = bars._enrich_minutes(minutes)
    hourly, _ = bars.build_all_from_minutes(enriched)
    events = bs.attach_followthrough(bs.classify(hourly), enriched)
    assert events.iloc[1]['followthrough'] == False
    assert pd.isna(events.iloc[1]['takeout_quarter_of_h2'])


def test_immediate_reversal_bullish_breakout_takes_out_h1_low():
    """Bullish H1 breakout, but H2 takes out H1's low → immediate_reversal=True."""
    h0 = helpers.make_hour('2024-01-02 09:00', ohlc=(100, 105, 95, 100),
                           high_at_minute=20, low_at_minute=40)
    # H1 bullish breakout: H1 close 110 > H0 high 105
    h1 = helpers.make_hour('2024-01-02 10:00', ohlc=(100, 115, 95, 110),
                           high_at_minute=30, low_at_minute=40)
    # H2 prints below H1.low (95) at some minute — H2 low = 90
    h2 = helpers.make_hour('2024-01-02 11:00', ohlc=(110, 112, 90, 100),
                           high_at_minute=5, low_at_minute=20)
    minutes = helpers.concat_hours(h0, h1, h2)
    enriched = bars._enrich_minutes(minutes)
    hourly, _ = bars.build_all_from_minutes(enriched)
    events = bs.attach_followthrough(bs.classify(hourly), enriched)
    h1_row = events.iloc[1]
    assert h1_row['breakout'] == 'bullish'
    assert h1_row['immediate_reversal'] == True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest Analysis/tests/test_breakout.py -v`
Expected: 4 new tests FAIL with `AttributeError`

- [ ] **Step 3: Implement `attach_followthrough`**

Append to `breakout_study.py`:

```python
def _quarter_for_minute(minute_of_hour: int) -> int:
    """Q1=:00-14, Q2=:15-29, Q3=:30-44, Q4=:45-59."""
    return minute_of_hour // 15 + 1


def attach_followthrough(classified: pd.DataFrame, minutes: pd.DataFrame) -> pd.DataFrame:
    """For each breakout row in `classified`, look at the next hour's 1-min bars
    and determine:
    - followthrough: True if H2 trades strictly beyond H1's extreme in the
      breakout direction
    - takeout_quarter_of_h2: 1..4 indicating which quarter of H2 first crossed
      (NaN if no takeout)
    - immediate_reversal: True if H2 strictly takes out H1's *opposite* extreme
      (only meaningful for breakout rows)

    Non-breakout rows ('neither', 'no_prev') get NaN for all three.
    """
    df = classified.copy().sort_values('hour_start_et').reset_index(drop=True)

    # Pre-bucket minutes by hour for fast lookup
    m = minutes.copy()
    m['hour_start_et'] = m['ny_ts'].dt.floor('h')
    m['minute_of_hour'] = m['ny_ts'].dt.minute
    grouped = dict(list(m.groupby('hour_start_et')))

    next_hour = df['hour_start_et'].shift(-1)

    followthrough = []
    takeout_q = []
    reversal = []

    for i, row in df.iterrows():
        b = row['breakout']
        if b not in ('bullish', 'bearish'):
            followthrough.append(np.nan)
            takeout_q.append(np.nan)
            reversal.append(np.nan)
            continue
        h2_start = next_hour.iloc[i]
        if pd.isna(h2_start) or h2_start not in grouped:
            followthrough.append(np.nan)
            takeout_q.append(np.nan)
            reversal.append(np.nan)
            continue
        h2 = grouped[h2_start].sort_values('minute_of_hour')
        h1_high = row['high']
        h1_low = row['low']
        if b == 'bullish':
            crossed = h2[h2['high'] > h1_high]
            if len(crossed) > 0:
                first_min = int(crossed['minute_of_hour'].iloc[0])
                followthrough.append(True)
                takeout_q.append(_quarter_for_minute(first_min))
            else:
                followthrough.append(False)
                takeout_q.append(np.nan)
            reversal.append(bool((h2['low'] < h1_low).any()))
        else:  # bearish
            crossed = h2[h2['low'] < h1_low]
            if len(crossed) > 0:
                first_min = int(crossed['minute_of_hour'].iloc[0])
                followthrough.append(True)
                takeout_q.append(_quarter_for_minute(first_min))
            else:
                followthrough.append(False)
                takeout_q.append(np.nan)
            reversal.append(bool((h2['high'] > h1_high).any()))

    df['followthrough'] = followthrough
    df['takeout_quarter_of_h2'] = takeout_q
    df['immediate_reversal'] = reversal
    return df
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest Analysis/tests/test_breakout.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add Analysis/engine/breakout_study.py Analysis/tests/test_breakout.py
git commit -m "Analysis: breakout follow-through + first-touch quarter attribution"
```

---

## Task 12: `breakout_study.py` — summary tables via slicers

**Files:**
- Modify: `Analysis/engine/breakout_study.py`
- Modify: `Analysis/tests/test_breakout.py`

- [ ] **Step 1: Write failing test**

Append to `test_breakout.py`:

```python
def test_breakout_metric_returns_rates():
    """Build a tiny events df and run the metric function directly."""
    events = pd.DataFrame({
        'breakout': ['bullish', 'bullish', 'bearish', 'neither', 'no_prev'],
        'followthrough': [True, False, True, None, None],
        'immediate_reversal': [False, True, False, None, None],
        'h1_open_vs_prev_mid': ['above', 'below', 'above', None, None],
    })
    rec = bs.breakout_metric(events)
    assert rec['n_total'] == 5
    assert rec['n_bullish'] == 2
    assert rec['n_bearish'] == 1
    assert rec['bullish_followthrough_rate'] == 0.5
    assert rec['bearish_followthrough_rate'] == 1.0
    assert rec['bullish_immediate_reversal_rate'] == 0.5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest Analysis/tests/test_breakout.py::test_breakout_metric_returns_rates -v`
Expected: FAIL with `AttributeError: module 'breakout_study' has no attribute 'breakout_metric'`

- [ ] **Step 3: Implement `breakout_metric` and `build_summaries`**

Append to `breakout_study.py`:

```python
def breakout_metric(events: pd.DataFrame) -> dict:
    """Aggregation function fed into a slicer."""
    n_total = len(events)
    bull = events[events['breakout'] == 'bullish']
    bear = events[events['breakout'] == 'bearish']
    n_bull, n_bear = len(bull), len(bear)

    def _rate(sub: pd.DataFrame, col: str) -> float:
        s = sub[col].dropna()
        return float(s.mean()) if len(s) else float('nan')

    return {
        'n_total': n_total,
        'n_bullish': n_bull,
        'n_bearish': n_bear,
        'bullish_breakout_rate': n_bull / n_total if n_total else float('nan'),
        'bearish_breakout_rate': n_bear / n_total if n_total else float('nan'),
        'bullish_followthrough_rate': _rate(bull, 'followthrough'),
        'bearish_followthrough_rate': _rate(bear, 'followthrough'),
        'bullish_immediate_reversal_rate': _rate(bull, 'immediate_reversal'),
        'bearish_immediate_reversal_rate': _rate(bear, 'immediate_reversal'),
    }


def build_summaries(events: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Return {summary_name: dataframe} dict for all 5 slicing dimensions."""
    import slicers
    return {
        'aggregate': slicers.slice_aggregate(events, breakout_metric),
        'by_year': slicers.slice_by_year(events, breakout_metric),
        'by_hour': slicers.slice_by_hour(events, breakout_metric),
        'by_dow': slicers.slice_by_dow(events, breakout_metric),
        'grid': slicers.slice_by_hour_dow(events, breakout_metric),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest Analysis/tests/test_breakout.py -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add Analysis/engine/breakout_study.py Analysis/tests/test_breakout.py
git commit -m "Analysis: breakout summary metric + 5-slice build_summaries"
```

---

## Task 13: `quarter_study.py` — feature-row builder

**Files:**
- Create: `Analysis/engine/quarter_study.py`
- Create: `Analysis/tests/test_quarter_study.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for Analysis/engine/quarter_study.py."""
import pandas as pd
import numpy as np
import pytest
import quarter_study as qs
import bars
import helpers


def _build_one_hour(ohlc=(100, 110, 90, 105), high_min=20, low_min=40):
    minutes = helpers.make_hour('2024-01-02 10:00', ohlc=ohlc,
                                high_at_minute=high_min, low_at_minute=low_min)
    enriched = bars._enrich_minutes(minutes)
    hourly, quarters = bars.build_all_from_minutes(enriched)
    return enriched, hourly, quarters


def test_q_of_high_when_high_in_q2():
    _, hourly, quarters = _build_one_hour(high_min=20, low_min=40)
    feats = qs.build_features(hourly, quarters)
    assert feats.iloc[0]['q_of_high'] == 2  # minute 20 → Q2


def test_q_of_high_when_high_in_q4():
    _, hourly, quarters = _build_one_hour(high_min=50, low_min=10)
    feats = qs.build_features(hourly, quarters)
    assert feats.iloc[0]['q_of_high'] == 4
    assert feats.iloc[0]['q_of_low'] == 1


def test_extreme_first_high_before_low():
    _, hourly, quarters = _build_one_hour(high_min=10, low_min=50)
    feats = qs.build_features(hourly, quarters)
    assert feats.iloc[0]['extreme_first'] == 'H'


def test_extreme_first_low_before_high():
    _, hourly, quarters = _build_one_hour(high_min=50, low_min=10)
    feats = qs.build_features(hourly, quarters)
    assert feats.iloc[0]['extreme_first'] == 'L'


def test_quarter_directions_present():
    _, hourly, quarters = _build_one_hour()
    feats = qs.build_features(hourly, quarters)
    assert 'q1_dir' in feats.columns
    assert 'q4_range' in feats.columns
    assert 'hour_dir' in feats.columns
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest Analysis/tests/test_quarter_study.py -v`
Expected: 5 FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `build_features`**

```python
"""In-depth quarter-of-the-hour study.

Builds a per-hour feature row with quarter OHLCs, location of extremes,
direction signs, range/body stats, and runs the A-F sub-studies.
"""
from __future__ import annotations
import pandas as pd
import numpy as np


def _sign(x: float) -> int:
    if x > 0: return 1
    if x < 0: return -1
    return 0


def build_features(hourly: pd.DataFrame, quarters: pd.DataFrame) -> pd.DataFrame:
    """One row per valid hour with quarter OHLC, location of extremes,
    directions, ranges, bodies."""
    # Pivot quarters: 4 rows per hour → 1 row per hour with q1_*, q2_*, ...
    pivot_cols = ['open', 'high', 'low', 'close', 'q_high_minute', 'q_low_minute']
    qp = quarters.pivot(index='hour_start_et', columns='quarter',
                        values=pivot_cols)
    qp.columns = [f'q{q}_{stat}' for stat, q in qp.columns]
    qp = qp.reset_index()

    df = hourly.merge(qp, on='hour_start_et', how='inner')

    # Hour-level extreme location
    high_cols = ['q1_high', 'q2_high', 'q3_high', 'q4_high']
    low_cols = ['q1_low', 'q2_low', 'q3_low', 'q4_low']
    # idxmax across columns gives the col name containing the max — map to quarter int
    df['q_of_high'] = df[high_cols].idxmax(axis=1).str[1].astype(int)
    df['q_of_low'] = df[low_cols].idxmin(axis=1).str[1].astype(int)

    # extreme_first: compare absolute minute-of-hour for the high vs low
    high_q = df['q_of_high']
    low_q = df['q_of_low']
    high_abs_min = (high_q - 1) * 15 + df.apply(
        lambda r: r[f'q{int(r["q_of_high"])}_q_high_minute'] - (int(r['q_of_high']) - 1) * 15, axis=1)
    low_abs_min = (low_q - 1) * 15 + df.apply(
        lambda r: r[f'q{int(r["q_of_low"])}_q_low_minute'] - (int(r['q_of_low']) - 1) * 15, axis=1)
    # Note: q_high_minute is already a minute-of-hour (0..59), not minute-of-quarter,
    # because helpers/bars store it that way. Simplify:
    df['_high_abs_min'] = df.apply(
        lambda r: int(r[f'q{int(r["q_of_high"])}_q_high_minute']), axis=1)
    df['_low_abs_min'] = df.apply(
        lambda r: int(r[f'q{int(r["q_of_low"])}_q_low_minute']), axis=1)
    df['extreme_first'] = np.where(
        df['_high_abs_min'] < df['_low_abs_min'], 'H',
        np.where(df['_high_abs_min'] > df['_low_abs_min'], 'L', 'T'))

    # Per-quarter directions, ranges, bodies
    for q in (1, 2, 3, 4):
        df[f'q{q}_dir'] = (df[f'q{q}_close'] - df[f'q{q}_open']).apply(_sign)
        df[f'q{q}_range'] = df[f'q{q}_high'] - df[f'q{q}_low']
        df[f'q{q}_body'] = (df[f'q{q}_close'] - df[f'q{q}_open']).abs()

    # Hour-level
    df['hour_range'] = df['high'] - df['low']
    df['hour_dir'] = (df['close'] - df['open']).apply(_sign)

    # Drop helper cols
    df = df.drop(columns=['_high_abs_min', '_low_abs_min'])
    return df
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest Analysis/tests/test_quarter_study.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add Analysis/engine/quarter_study.py Analysis/tests/test_quarter_study.py
git commit -m "Analysis: quarter_study.build_features() per-hour feature rows"
```

---

## Task 14: `quarter_study.py` — sub-studies A through F

**Files:**
- Modify: `Analysis/engine/quarter_study.py`
- Modify: `Analysis/tests/test_quarter_study.py`

- [ ] **Step 1: Write failing tests**

Append to `test_quarter_study.py`:

```python
def _synthetic_features(n=20):
    """Build a small synthetic feature df with known structure for metric tests."""
    rng = np.random.default_rng(42)
    df = pd.DataFrame({
        'q_of_high': rng.integers(1, 5, n),
        'q_of_low': rng.integers(1, 5, n),
        'extreme_first': rng.choice(['H', 'L'], n),
        'q1_dir': rng.choice([-1, 0, 1], n),
        'q2_dir': rng.choice([-1, 0, 1], n),
        'q3_dir': rng.choice([-1, 0, 1], n),
        'q4_dir': rng.choice([-1, 0, 1], n),
        'q1_range': rng.uniform(1, 10, n),
        'q2_range': rng.uniform(1, 10, n),
        'q3_range': rng.uniform(1, 10, n),
        'q4_range': rng.uniform(1, 10, n),
        'q1_body': rng.uniform(0, 5, n),
        'q2_body': rng.uniform(0, 5, n),
        'q3_body': rng.uniform(0, 5, n),
        'q4_body': rng.uniform(0, 5, n),
        'q1_high': rng.uniform(100, 110, n),
        'q1_low': rng.uniform(90, 100, n),
        'q4_high': rng.uniform(100, 110, n),
        'q4_low': rng.uniform(90, 100, n),
        'hour_range': rng.uniform(5, 20, n),
        'hour_dir': rng.choice([-1, 0, 1], n),
        'hour_high': rng.uniform(105, 115, n),
        'hour_low': rng.uniform(85, 95, n),
        'year': 2024,
        'dow': 1,
        'hour_of_day_et': 10,
    })
    return df


def test_study_a_returns_q_of_high_distribution():
    df = _synthetic_features()
    rec = qs.study_a_metric(df)
    # Should have keys for q1..q4 high and low pcts
    assert 'q_of_high_q1_pct' in rec
    assert 'q_of_low_q4_pct' in rec
    assert 0 <= rec['q_of_high_q1_pct'] <= 1


def test_study_b_returns_extreme_first_pct():
    df = _synthetic_features()
    rec = qs.study_b_metric(df)
    assert 'extreme_first_H_pct' in rec
    assert 'extreme_first_L_pct' in rec


def test_study_c_returns_per_quarter_directional_rates():
    df = _synthetic_features()
    rec = qs.study_c_metric(df)
    for q in (1, 2, 3, 4):
        assert f'q{q}_up_pct' in rec
        assert f'q{q}_down_pct' in rec
        assert f'q{q}_avg_range' in rec


def test_study_d_q1_to_hour_dir():
    df = _synthetic_features()
    rec = qs.study_d_metric(df)
    # P(hour_dir=+1 | q1_dir=+1)
    assert 'p_hour_up_given_q1_up' in rec
    assert 'p_q4_reversal_given_q1_dir' in rec


def test_study_e_q1_high_hold_rate():
    df = _synthetic_features()
    rec = qs.study_e_metric(df)
    assert 'q1_high_hold_rate' in rec
    assert 'q4_high_hold_rate' in rec


def test_study_f_quintile_table_returns_5_rows():
    df = _synthetic_features(n=100)  # need enough for clean quintiles
    out = qs.study_f_table(df)
    assert len(out) == 5
    assert 'q1_range_quintile' in out.columns
    assert 'avg_hour_range' in out.columns
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest Analysis/tests/test_quarter_study.py -v`
Expected: 6 new FAIL with `AttributeError`

- [ ] **Step 3: Implement studies A through F**

Append to `quarter_study.py`:

```python
def study_a_metric(df: pd.DataFrame) -> dict:
    """High/low location distribution."""
    n = len(df)
    rec = {}
    for q in (1, 2, 3, 4):
        rec[f'q_of_high_q{q}_pct'] = float((df['q_of_high'] == q).mean()) if n else float('nan')
        rec[f'q_of_low_q{q}_pct'] = float((df['q_of_low'] == q).mean()) if n else float('nan')
    return rec


def study_b_metric(df: pd.DataFrame) -> dict:
    """Sequencing: H-first vs L-first."""
    n = len(df)
    return {
        'extreme_first_H_pct': float((df['extreme_first'] == 'H').mean()) if n else float('nan'),
        'extreme_first_L_pct': float((df['extreme_first'] == 'L').mean()) if n else float('nan'),
        'extreme_first_T_pct': float((df['extreme_first'] == 'T').mean()) if n else float('nan'),
    }


def study_c_metric(df: pd.DataFrame) -> dict:
    """Per-quarter directional bias and range."""
    rec = {}
    for q in (1, 2, 3, 4):
        n = len(df)
        rec[f'q{q}_up_pct'] = float((df[f'q{q}_dir'] == 1).mean()) if n else float('nan')
        rec[f'q{q}_down_pct'] = float((df[f'q{q}_dir'] == -1).mean()) if n else float('nan')
        rec[f'q{q}_flat_pct'] = float((df[f'q{q}_dir'] == 0).mean()) if n else float('nan')
        rec[f'q{q}_avg_range'] = float(df[f'q{q}_range'].mean()) if n else float('nan')
        rec[f'q{q}_median_range'] = float(df[f'q{q}_range'].median()) if n else float('nan')
        rec[f'q{q}_avg_body'] = float(df[f'q{q}_body'].mean()) if n else float('nan')
        avg_range = df[f'q{q}_range'].mean()
        avg_body = df[f'q{q}_body'].mean()
        rec[f'q{q}_body_to_range_ratio'] = float(avg_body / avg_range) if avg_range else float('nan')
    return rec


def _conditional_dir_pct(df: pd.DataFrame, given_col: str, given_val: int,
                         then_col: str, then_val: int) -> float:
    sub = df[df[given_col] == given_val]
    if not len(sub):
        return float('nan')
    return float((sub[then_col] == then_val).mean())


def study_d_metric(df: pd.DataFrame) -> dict:
    """Conditional shift detection."""
    rec = {
        'p_hour_up_given_q1_up': _conditional_dir_pct(df, 'q1_dir', 1, 'hour_dir', 1),
        'p_hour_down_given_q1_down': _conditional_dir_pct(df, 'q1_dir', -1, 'hour_dir', -1),
        'p_q2_up_given_q1_up': _conditional_dir_pct(df, 'q1_dir', 1, 'q2_dir', 1),
        'p_q3_up_given_q1_up': _conditional_dir_pct(df, 'q1_dir', 1, 'q3_dir', 1),
        'p_q4_up_given_q1_up': _conditional_dir_pct(df, 'q1_dir', 1, 'q4_dir', 1),
        'p_q4_down_given_q1_up': _conditional_dir_pct(df, 'q1_dir', 1, 'q4_dir', -1),
        'p_q4_up_given_q1_down': _conditional_dir_pct(df, 'q1_dir', -1, 'q4_dir', 1),
    }
    # Reversal: q4_dir opposite of q1_dir given q1_dir != 0
    nz = df[df['q1_dir'] != 0]
    if len(nz):
        rec['p_q4_reversal_given_q1_dir'] = float(((nz['q4_dir'] != 0) & (nz['q4_dir'] != nz['q1_dir'])).mean())
    else:
        rec['p_q4_reversal_given_q1_dir'] = float('nan')
    return rec


def study_e_metric(df: pd.DataFrame) -> dict:
    """Early- and late-extreme persistence + overshoot when Q1 fails."""
    n = len(df)
    rec = {
        'q1_high_hold_rate': float((df['q_of_high'] == 1).mean()) if n else float('nan'),
        'q1_low_hold_rate': float((df['q_of_low'] == 1).mean()) if n else float('nan'),
        'q4_high_hold_rate': float((df['q_of_high'] == 4).mean()) if n else float('nan'),
        'q4_low_hold_rate': float((df['q_of_low'] == 4).mean()) if n else float('nan'),
    }
    failed = df[df['q_of_high'] != 1]
    if 'hour_high' in df.columns and len(failed):
        overshoot = failed['hour_high'] - failed['q1_high']
        rec['q1_high_fail_overshoot_mean'] = float(overshoot.mean())
        rec['q1_high_fail_overshoot_median'] = float(overshoot.median())
    else:
        rec['q1_high_fail_overshoot_mean'] = float('nan')
        rec['q1_high_fail_overshoot_median'] = float('nan')
    return rec


def study_f_table(df: pd.DataFrame) -> pd.DataFrame:
    """Q1-range quintile bucketing.

    Returns 5 rows (one per quintile) with avg hour range, remaining range,
    Q1-extreme hold rates, and direction distribution.
    """
    if len(df) < 5:
        return pd.DataFrame()
    df = df.copy()
    df['q1_range_quintile'] = pd.qcut(df['q1_range'], 5, labels=[1, 2, 3, 4, 5],
                                      duplicates='drop')
    rows = []
    for quintile, sub in df.groupby('q1_range_quintile', observed=True):
        rows.append({
            'q1_range_quintile': int(quintile),
            'count': len(sub),
            'avg_q1_range': float(sub['q1_range'].mean()),
            'avg_hour_range': float(sub['hour_range'].mean()),
            'avg_remaining_range': float((sub['hour_range'] - sub['q1_range']).mean()),
            'q1_high_hold_rate': float((sub['q_of_high'] == 1).mean()),
            'q1_low_hold_rate': float((sub['q_of_low'] == 1).mean()),
            'hour_up_pct': float((sub['hour_dir'] == 1).mean()),
            'hour_down_pct': float((sub['hour_dir'] == -1).mean()),
        })
    return pd.DataFrame(rows)


def build_summaries(features: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Run every (study, slice) combination and return a dict of dataframes.

    Keys are like 'study_a_aggregate', 'study_d_by_hour', 'study_f_aggregate', etc.
    Study F is a table-style study, so it only has aggregate / by_year / by_hour /
    by_dow variants, not the full grid (the grid would be too sparse for quintiles).
    """
    import slicers
    out = {}
    metric_studies = [
        ('study_a', study_a_metric),
        ('study_b', study_b_metric),
        ('study_c', study_c_metric),
        ('study_d', study_d_metric),
        ('study_e', study_e_metric),
    ]
    slice_fns = [
        ('aggregate', slicers.slice_aggregate),
        ('by_year', slicers.slice_by_year),
        ('by_hour', slicers.slice_by_hour),
        ('by_dow', slicers.slice_by_dow),
        ('grid', slicers.slice_by_hour_dow),
    ]
    for study_name, metric_fn in metric_studies:
        for slice_name, slice_fn in slice_fns:
            out[f'{study_name}_{slice_name}'] = slice_fn(features, metric_fn)
    # Study F: aggregate + by_year + by_hour + by_dow only
    out['study_f_aggregate'] = study_f_table(features)
    for slice_name, by_col in [('by_year', 'year'), ('by_hour', 'hour_of_day_et'),
                               ('by_dow', 'dow')]:
        rows = []
        for k, sub in features.groupby(by_col):
            t = study_f_table(sub)
            if len(t):
                t[by_col] = k
                rows.append(t)
        out[f'study_f_{slice_name}'] = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest Analysis/tests/test_quarter_study.py -v`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add Analysis/engine/quarter_study.py Analysis/tests/test_quarter_study.py
git commit -m "Analysis: quarter_study sub-studies A-F + build_summaries"
```

---

## Task 15: `run_all.py` — top-level driver

**Files:**
- Create: `Analysis/engine/run_all.py`

- [ ] **Step 1: Write the script**

```python
"""Top-level driver — builds bars, runs both studies, writes parquet + manifest.

Run from repo root:
    python Analysis/engine/run_all.py
or from anywhere:
    python -m Analysis.engine.run_all
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

# Ensure local imports work whether invoked as script or module
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import bars
import breakout_study
import quarter_study


SCHEMA_VERSION = 1


def main(start: str | None = None, end: str | None = None) -> None:
    out_root = HERE.parent / 'data'
    out_breakout = out_root / 'breakout'
    out_quarters = out_root / 'quarters'
    out_breakout.mkdir(parents=True, exist_ok=True)
    out_quarters.mkdir(parents=True, exist_ok=True)

    print(f"[run_all] Loading 1-min bars (start={start}, end={end})...")
    minutes = bars.load_minutes(start=start, end=end)
    print(f"[run_all] Loaded {len(minutes):,} 1-min rows")

    hourly, quarters = bars.build_all_from_minutes(minutes)
    n_input_hours = (minutes['ny_ts'].dt.floor('h')).nunique()
    n_dropped = n_input_hours - len(hourly)
    print(f"[run_all] Built {len(hourly):,} hourly bars (dropped {n_dropped:,} for completeness/settlement)")

    # Breakout study
    print(f"[run_all] Running breakout study...")
    classified = breakout_study.classify(hourly)
    events = breakout_study.attach_followthrough(classified, minutes)
    events.to_parquet(out_breakout / 'breakouts.parquet', index=False)
    summaries = breakout_study.build_summaries(events)
    for name, df in summaries.items():
        df.to_parquet(out_breakout / f'summary_{name}.parquet', index=False)

    n_bull = int((events['breakout'] == 'bullish').sum())
    n_bear = int((events['breakout'] == 'bearish').sum())
    print(f"[run_all]   {n_bull:,} bullish breakouts, {n_bear:,} bearish breakouts")

    # Quarter study
    print(f"[run_all] Running quarter study...")
    features = quarter_study.build_features(hourly, quarters)
    features.to_parquet(out_quarters / 'quarter_features.parquet', index=False)
    q_summaries = quarter_study.build_summaries(features)
    for name, df in q_summaries.items():
        if len(df):
            df.to_parquet(out_quarters / f'{name}.parquet', index=False)

    # Manifest
    manifest = {
        'schema_version': SCHEMA_VERSION,
        'run_timestamp_utc': datetime.now(timezone.utc).isoformat(),
        'date_range_start': str(hourly['hour_start_et'].min()),
        'date_range_end': str(hourly['hour_start_et'].max()),
        'total_hours': int(len(hourly)),
        'hours_dropped': int(n_dropped),
        'n_bullish_breakouts': n_bull,
        'n_bearish_breakouts': n_bear,
        'years_covered': sorted(int(y) for y in hourly['year'].unique()),
    }
    (out_root / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    print(f"[run_all] Wrote manifest: {out_root / 'manifest.json'}")
    print(f"[run_all] Done.")


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--start', help="ISO date (NY local), e.g. 2020-01-01")
    p.add_argument('--end', help="ISO date (NY local), exclusive")
    args = p.parse_args()
    main(start=args.start, end=args.end)
```

- [ ] **Step 2: Smoke-test against a small slice of the real DB**

Run: `cd /Users/abhi/Projects/Statistic.ally && python Analysis/engine/run_all.py --start 2025-01-01 --end 2025-02-01`

Expected output: progress lines, file paths, no exceptions. Verify with:

```bash
ls -la Analysis/data/ Analysis/data/breakout/ Analysis/data/quarters/
cat Analysis/data/manifest.json
```

`manifest.json` should show ~ 400-500 hours, both breakout counts non-zero, year list `[2025]`.

- [ ] **Step 3: Commit**

```bash
git add Analysis/engine/run_all.py
git commit -m "Analysis: run_all.py driver writes parquet + manifest"
```

---

## Task 16: Integration smoke test

**Files:**
- Create: `Analysis/tests/test_integration.py`

- [ ] **Step 1: Write the test**

```python
"""End-to-end smoke test against the real DuckDB.

Skipped automatically if the DB file is missing (CI environments without it).
Runs against a small recent slice so it stays fast.
"""
import json
import os
from pathlib import Path
import pytest
import bars


pytestmark = pytest.mark.skipif(
    not bars.db_path().exists(),
    reason=f"shared DuckDB not found at {bars.db_path()}"
)


def test_run_all_against_recent_30_days(tmp_path, monkeypatch):
    """Run the engine against a recent 1-month slice; assert outputs land + are sane."""
    import run_all

    # Redirect output dir to tmp_path
    monkeypatch.setattr(run_all, 'HERE', tmp_path)
    out_root = tmp_path.parent / 'data'  # HERE.parent / 'data' in driver
    # Easier: just set HERE such that HERE.parent / 'data' = tmp_path
    fake_here = tmp_path / 'engine'
    fake_here.mkdir()
    monkeypatch.setattr(run_all, 'HERE', fake_here)

    run_all.main(start='2025-09-01', end='2025-10-01')

    data_root = tmp_path / 'data'
    assert (data_root / 'manifest.json').exists()
    manifest = json.loads((data_root / 'manifest.json').read_text())
    assert manifest['total_hours'] > 0
    assert manifest['schema_version'] == 1

    # Critical files
    assert (data_root / 'breakout' / 'breakouts.parquet').exists()
    assert (data_root / 'breakout' / 'summary_aggregate.parquet').exists()
    assert (data_root / 'quarters' / 'quarter_features.parquet').exists()

    # No NaNs in critical prev-hour columns (after the first row)
    import pandas as pd
    breakouts = pd.read_parquet(data_root / 'breakout' / 'breakouts.parquet')
    # After the first row, prev_hour_high should be non-null
    non_first = breakouts.iloc[1:]
    assert non_first['prev_hour_high'].notna().all()
    assert non_first['prev_hour_low'].notna().all()
    assert non_first['prev_hour_mid'].notna().all()
```

- [ ] **Step 2: Run integration test**

Run: `cd /Users/abhi/Projects/Statistic.ally && pytest Analysis/tests/test_integration.py -v`
Expected: 1 passed (or skipped if DB not available)

- [ ] **Step 3: Commit**

```bash
git add Analysis/tests/test_integration.py
git commit -m "Analysis: end-to-end integration smoke test"
```

---

## Task 17: Dashboard — shared CSS + JS scaffolding

**Files:**
- Create: `Analysis/dashboard/shared.css`
- Create: `Analysis/dashboard/shared.js`

- [ ] **Step 1: Write `shared.css`**

This pulls the same dark/light tokens used by `Fractal Sweep/model_dashboard.html`. Copy the `:root`, `[data-theme="dark"]`, and `[data-theme="light"]` blocks from there (lines ~10-65). Add Analysis-specific layout below.

```css
/* Analysis/dashboard/shared.css */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --green:#10b981;--red:#ef4444;--amber:#f59e0b;--blue:#3b82f6;--purple:#8b5cf6;
  --font-display:'Plus Jakarta Sans',sans-serif;
  --font-data:'IBM Plex Mono',monospace;
  --font-body:'Inter',sans-serif;
  --ease:cubic-bezier(0.16,1,0.3,1);
}
[data-theme="dark"]{
  --bg:#0a0e17;--bg-card:#111827;--bg-raised:#1a2235;--bg-hover:#1e2d42;
  --border:#1e2d42;--border-mid:#243447;--border-hi:#2e4460;
  --text-primary:#e2eaf4;--text-secondary:#8ba4bc;--text-muted:#4a6480;
  --shadow:0 1px 3px rgba(0,0,0,.5),0 4px 16px rgba(0,0,0,.3);
  --accent:#10b981;
}
[data-theme="light"]{
  --bg:#f8fafc;--bg-card:#ffffff;--bg-raised:#f1f5f9;--bg-hover:#e2e8f0;
  --border:#e2e8f0;--border-mid:#cbd5e1;--border-hi:#94a3b8;
  --text-primary:#0f172a;--text-secondary:#334155;--text-muted:#64748b;
  --shadow:0 1px 3px rgba(15,23,42,.06),0 4px 12px rgba(15,23,42,.04);
  --accent:#059669;
}
body {
  font-family: var(--font-body);
  background: var(--bg);
  color: var(--text-primary);
  min-height: 100vh;
  padding: 24px;
}
.container { max-width: 1400px; margin: 0 auto; }
h1, h2, h3 { font-family: var(--font-display); margin-bottom: 12px; }
h1 { font-size: 28px; margin-bottom: 24px; }
h2 { font-size: 20px; margin-top: 32px; }
.card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 16px;
  box-shadow: var(--shadow);
}
.card-grid { display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }
.metric-value { font-family: var(--font-data); font-size: 28px; color: var(--accent); }
.metric-label { color: var(--text-secondary); font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 6px; }
table { width: 100%; border-collapse: collapse; font-family: var(--font-data); font-size: 13px; }
th, td { padding: 8px 12px; border-bottom: 1px solid var(--border); text-align: right; }
th { background: var(--bg-raised); color: var(--text-secondary); text-align: left; font-weight: 500; }
td:first-child, th:first-child { text-align: left; }
.row-low-count { opacity: 0.4; }
.theme-toggle {
  position: fixed; top: 16px; right: 16px; padding: 8px 12px;
  background: var(--bg-card); border: 1px solid var(--border); border-radius: 6px;
  cursor: pointer; color: var(--text-primary);
}
.filter-bar {
  display: flex; gap: 12px; flex-wrap: wrap; padding: 16px;
  background: var(--bg-raised); border-radius: 8px; margin-bottom: 24px;
}
.filter-bar label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--text-secondary); }
.filter-bar select, .filter-bar input { background: var(--bg-card); color: var(--text-primary); border: 1px solid var(--border); padding: 6px 8px; border-radius: 4px; font-family: var(--font-body); }
nav { margin-bottom: 24px; }
nav a { color: var(--accent); text-decoration: none; margin-right: 16px; }
nav a:hover { text-decoration: underline; }
```

- [ ] **Step 2: Write `shared.js`** — DuckDB-Wasm bootstrap + theme + filter helpers

```javascript
// Analysis/dashboard/shared.js
// Theme: shared with the rest of Statistic.ally via localStorage 'hub-theme'
(function () {
  const t = localStorage.getItem('hub-theme') || 'dark';
  document.documentElement.setAttribute('data-theme', t);
})();

window.toggleTheme = function () {
  const cur = document.documentElement.getAttribute('data-theme');
  const next = cur === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('hub-theme', next);
};

// DuckDB-Wasm singleton
let _dbPromise = null;
async function getDB() {
  if (_dbPromise) return _dbPromise;
  _dbPromise = (async () => {
    const duckdb = await import('https://cdn.jsdelivr.net/npm/@duckdb/duckdb-wasm@1.29.0/+esm');
    const JSDELIVR_BUNDLES = duckdb.getJsDelivrBundles();
    const bundle = await duckdb.selectBundle(JSDELIVR_BUNDLES);
    const worker_url = URL.createObjectURL(
      new Blob([`importScripts("${bundle.mainWorker}");`], { type: 'text/javascript' })
    );
    const worker = new Worker(worker_url);
    const logger = new duckdb.ConsoleLogger();
    const db = new duckdb.AsyncDuckDB(logger, worker);
    await db.instantiate(bundle.mainModule, bundle.pthreadWorker);
    URL.revokeObjectURL(worker_url);
    return db;
  })();
  return _dbPromise;
}

window.loadParquet = async function (path, alias) {
  const db = await getDB();
  const conn = await db.connect();
  // Register the parquet file via fetch
  const resp = await fetch(path);
  if (!resp.ok) throw new Error(`Failed to fetch ${path}: ${resp.status}`);
  const buf = new Uint8Array(await resp.arrayBuffer());
  await db.registerFileBuffer(`${alias}.parquet`, buf);
  await conn.query(`CREATE OR REPLACE VIEW ${alias} AS SELECT * FROM read_parquet('${alias}.parquet')`);
  await conn.close();
};

window.query = async function (sql) {
  const db = await getDB();
  const conn = await db.connect();
  try {
    const result = await conn.query(sql);
    return result.toArray().map(r => Object.fromEntries(
      Object.entries(r).map(([k, v]) => [k, typeof v === 'bigint' ? Number(v) : v])
    ));
  } finally {
    await conn.close();
  }
};

window.fmtPct = (x) => (x == null || isNaN(x)) ? '—' : (x * 100).toFixed(1) + '%';
window.fmtNum = (x) => (x == null || isNaN(x)) ? '—' : Number(x).toLocaleString();
```

- [ ] **Step 3: Commit (no test — manual validation in next tasks)**

```bash
git add Analysis/dashboard/shared.css Analysis/dashboard/shared.js
git commit -m "Analysis dashboard: shared CSS + DuckDB-Wasm JS bootstrap"
```

---

## Task 18: Dashboard — landing page (`index.html`)

**Files:**
- Create: `Analysis/dashboard/index.html`

- [ ] **Step 1: Write `index.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Hourly Analysis · Statistic.ally</title>
  <link rel="stylesheet" href="shared.css" />
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;700&family=IBM+Plex+Mono:wght@400;500&family=Inter:wght@400;500&display=swap" rel="stylesheet" />
</head>
<body>
  <button class="theme-toggle" onclick="toggleTheme()">theme</button>
  <div class="container">
    <nav>
      <a href="../../index.html">← Statistic.ally hub</a>
    </nav>
    <h1>NQ Hourly Analysis</h1>

    <div id="manifest-card" class="card">
      <div class="metric-label">Loading manifest...</div>
    </div>

    <div class="card-grid">
      <a href="breakout.html" class="card" style="text-decoration:none;color:inherit;">
        <h2>Breakout Follow-Through</h2>
        <p style="color:var(--text-secondary);margin-top:8px;">When an hourly candle closes above the prior hour's high (or below the prior low), how often does the next hour take out the newly-formed extreme — and in which quarter?</p>
      </a>
      <a href="quarters.html" class="card" style="text-decoration:none;color:inherit;">
        <h2>Quarter-of-the-Hour Study</h2>
        <p style="color:var(--text-secondary);margin-top:8px;">In-depth analysis of intra-hour price action: where highs/lows form, sequencing, conditional shifts (Q1 → Q4), early-extreme persistence, and Q1-range expansion.</p>
      </a>
    </div>
  </div>

  <script src="shared.js"></script>
  <script>
    (async () => {
      try {
        const resp = await fetch('../data/manifest.json');
        const m = await resp.json();
        const card = document.getElementById('manifest-card');
        card.innerHTML = `
          <div class="card-grid">
            <div><div class="metric-label">Date range</div><div class="metric-value" style="font-size:18px;">${m.date_range_start.slice(0,10)} → ${m.date_range_end.slice(0,10)}</div></div>
            <div><div class="metric-label">Total hours</div><div class="metric-value">${fmtNum(m.total_hours)}</div></div>
            <div><div class="metric-label">Bullish breakouts</div><div class="metric-value">${fmtNum(m.n_bullish_breakouts)}</div></div>
            <div><div class="metric-label">Bearish breakouts</div><div class="metric-value">${fmtNum(m.n_bearish_breakouts)}</div></div>
            <div><div class="metric-label">Last run</div><div class="metric-value" style="font-size:14px;">${m.run_timestamp_utc.slice(0,16)}Z</div></div>
          </div>
        `;
      } catch (e) {
        document.getElementById('manifest-card').innerHTML =
          `<div class="metric-label">Could not load manifest: ${e.message}. Run <code>python Analysis/engine/run_all.py</code> first.</div>`;
      }
    })();
  </script>
</body>
</html>
```

- [ ] **Step 2: Manual validation**

Run: `cd /Users/abhi/Projects/Statistic.ally && python3 -m http.server 8001` (background)

Open `http://localhost:8001/Analysis/dashboard/index.html` in a browser. Verify:
- Page loads, theme toggle works
- Manifest card shows date range, hour count, breakout counts (assuming Task 15 was run)
- Both navigation cards are visible

- [ ] **Step 3: Commit**

```bash
git add Analysis/dashboard/index.html
git commit -m "Analysis dashboard: landing page with manifest summary"
```

---

## Task 19: Dashboard — breakout page (`breakout.html`)

**Files:**
- Create: `Analysis/dashboard/breakout.html`

- [ ] **Step 1: Write `breakout.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Breakout Follow-Through · NQ Hourly</title>
  <link rel="stylesheet" href="shared.css" />
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;700&family=IBM+Plex+Mono:wght@400;500&family=Inter:wght@400;500&display=swap" rel="stylesheet" />
</head>
<body>
  <button class="theme-toggle" onclick="toggleTheme()">theme</button>
  <div class="container">
    <nav><a href="index.html">← Hourly Analysis</a></nav>
    <h1>Breakout Follow-Through</h1>

    <div class="filter-bar">
      <label>Min sample size <input type="number" id="min-count" value="30" min="0" step="10" /></label>
      <label>Direction
        <select id="direction">
          <option value="both">Both</option>
          <option value="bullish">Bullish only</option>
          <option value="bearish">Bearish only</option>
        </select>
      </label>
    </div>

    <h2>Headline rates (aggregate)</h2>
    <div id="headline" class="card-grid"></div>

    <h2>By year</h2>
    <div class="card"><table id="t-by-year"></table></div>

    <h2>By hour-of-day (ET)</h2>
    <div class="card"><table id="t-by-hour"></table></div>

    <h2>By day-of-week</h2>
    <div class="card"><table id="t-by-dow"></table></div>

    <h2>Quarter-of-H2 takeout attribution</h2>
    <div class="card"><table id="t-takeout-q"></table></div>

    <h2>Conditioned on H1 open vs prev-mid</h2>
    <div class="card"><table id="t-prev-mid"></table></div>
  </div>

  <script src="shared.js"></script>
  <script>
    const DOW_NAMES = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];

    function pctTd(x, count, minCount) {
      const cls = (count != null && count < minCount) ? ' class="row-low-count"' : '';
      return `<td${cls}>${fmtPct(x)}</td>`;
    }

    function renderTable(rows, columns, getMinCount) {
      if (!rows.length) return '<tr><td>(no data)</td></tr>';
      let html = '<thead><tr>' + columns.map(c => `<th>${c.label}</th>`).join('') + '</tr></thead><tbody>';
      const minC = getMinCount();
      for (const r of rows) {
        html += '<tr' + (r.count != null && r.count < minC ? ' class="row-low-count"' : '') + '>';
        for (const c of columns) {
          const v = r[c.key];
          html += `<td>${c.fmt ? c.fmt(v) : v}</td>`;
        }
        html += '</tr>';
      }
      return html + '</tbody>';
    }

    async function init() {
      await loadParquet('../data/breakout/breakouts.parquet', 'events');
      await loadParquet('../data/breakout/summary_aggregate.parquet', 's_agg');
      await loadParquet('../data/breakout/summary_by_year.parquet', 's_year');
      await loadParquet('../data/breakout/summary_by_hour.parquet', 's_hour');
      await loadParquet('../data/breakout/summary_by_dow.parquet', 's_dow');
      await render();
      document.getElementById('min-count').addEventListener('change', render);
      document.getElementById('direction').addEventListener('change', render);
    }

    function getMinCount() { return parseInt(document.getElementById('min-count').value, 10) || 0; }
    function getDirection() { return document.getElementById('direction').value; }

    async function render() {
      const dir = getDirection();
      // Headline
      const agg = (await query('SELECT * FROM s_agg'))[0];
      const headlineCards = [
        { label: 'Total hours analyzed', value: fmtNum(agg.n_total) },
        { label: 'Bullish breakout rate', value: fmtPct(agg.bullish_breakout_rate) },
        { label: 'Bearish breakout rate', value: fmtPct(agg.bearish_breakout_rate) },
        { label: 'Bullish follow-through', value: fmtPct(agg.bullish_followthrough_rate) },
        { label: 'Bearish follow-through', value: fmtPct(agg.bearish_followthrough_rate) },
        { label: 'Bullish immediate-reversal', value: fmtPct(agg.bullish_immediate_reversal_rate) },
        { label: 'Bearish immediate-reversal', value: fmtPct(agg.bearish_immediate_reversal_rate) },
      ];
      document.getElementById('headline').innerHTML = headlineCards.map(c =>
        `<div class="card"><div class="metric-label">${c.label}</div><div class="metric-value">${c.value}</div></div>`).join('');

      const cols = (keyLabel) => [
        { key: keyLabel.key, label: keyLabel.label },
        { key: 'count', label: 'n', fmt: fmtNum },
        ...(dir !== 'bearish' ? [
          { key: 'bullish_breakout_rate', label: 'Bull rate', fmt: fmtPct },
          { key: 'bullish_followthrough_rate', label: 'Bull FT', fmt: fmtPct },
        ] : []),
        ...(dir !== 'bullish' ? [
          { key: 'bearish_breakout_rate', label: 'Bear rate', fmt: fmtPct },
          { key: 'bearish_followthrough_rate', label: 'Bear FT', fmt: fmtPct },
        ] : []),
      ];

      document.getElementById('t-by-year').innerHTML = renderTable(
        await query('SELECT * FROM s_year ORDER BY year'),
        cols({ key: 'year', label: 'Year' }), getMinCount);

      document.getElementById('t-by-hour').innerHTML = renderTable(
        await query('SELECT * FROM s_hour ORDER BY hour_of_day_et'),
        cols({ key: 'hour_of_day_et', label: 'Hour ET' }), getMinCount);

      const dowRows = await query('SELECT * FROM s_dow ORDER BY dow');
      dowRows.forEach(r => r.dow_name = DOW_NAMES[r.dow]);
      document.getElementById('t-by-dow').innerHTML = renderTable(
        dowRows, cols({ key: 'dow_name', label: 'DOW' }), getMinCount);

      // Quarter-of-H2 takeout attribution
      const dirFilter = dir === 'both' ? "breakout IN ('bullish','bearish')"
        : dir === 'bullish' ? "breakout = 'bullish'" : "breakout = 'bearish'";
      const tq = await query(`
        SELECT takeout_quarter_of_h2 AS q, COUNT(*) AS n
        FROM events
        WHERE ${dirFilter} AND followthrough = TRUE
        GROUP BY q ORDER BY q
      `);
      const totalQ = tq.reduce((s, r) => s + r.n, 0);
      document.getElementById('t-takeout-q').innerHTML =
        '<thead><tr><th>Quarter of H2</th><th>n</th><th>%</th></tr></thead><tbody>' +
        tq.map(r => `<tr><td>Q${r.q}</td><td>${fmtNum(r.n)}</td><td>${fmtPct(r.n / totalQ)}</td></tr>`).join('') +
        '</tbody>';

      // Prev-mid conditioning
      const pm = await query(`
        SELECT breakout, h1_open_vs_prev_mid AS side,
               COUNT(*) AS n,
               AVG(CASE WHEN followthrough THEN 1.0 ELSE 0.0 END) AS ft_rate
        FROM events
        WHERE ${dirFilter} AND h1_open_vs_prev_mid IS NOT NULL
        GROUP BY breakout, side ORDER BY breakout, side
      `);
      document.getElementById('t-prev-mid').innerHTML =
        '<thead><tr><th>Direction</th><th>H1 open vs prev-mid</th><th>n</th><th>Follow-through</th></tr></thead><tbody>' +
        pm.map(r => `<tr${r.n < getMinCount() ? ' class="row-low-count"' : ''}>` +
          `<td>${r.breakout}</td><td>${r.side}</td><td>${fmtNum(r.n)}</td><td>${fmtPct(r.ft_rate)}</td></tr>`).join('') +
        '</tbody>';
    }

    init().catch(e => alert('Failed to load: ' + e.message));
  </script>
</body>
</html>
```

- [ ] **Step 2: Manual validation**

Open `http://localhost:8001/Analysis/dashboard/breakout.html`. Verify:
- Headline cards populate with values
- All 4 tables populate
- Direction filter changes visible columns
- Min-count slider greys out low-count rows

- [ ] **Step 3: Commit**

```bash
git add Analysis/dashboard/breakout.html
git commit -m "Analysis dashboard: breakout follow-through page"
```

---

## Task 20: Dashboard — quarters page (`quarters.html`)

**Files:**
- Create: `Analysis/dashboard/quarters.html`

- [ ] **Step 1: Write `quarters.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Quarter Study · NQ Hourly</title>
  <link rel="stylesheet" href="shared.css" />
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;700&family=IBM+Plex+Mono:wght@400;500&family=Inter:wght@400;500&display=swap" rel="stylesheet" />
  <style>
    .tabs { display: flex; gap: 4px; margin-bottom: 16px; border-bottom: 1px solid var(--border); }
    .tab { padding: 10px 16px; cursor: pointer; color: var(--text-secondary); border-bottom: 2px solid transparent; }
    .tab.active { color: var(--accent); border-bottom-color: var(--accent); }
    .tab-panel { display: none; }
    .tab-panel.active { display: block; }
  </style>
</head>
<body>
  <button class="theme-toggle" onclick="toggleTheme()">theme</button>
  <div class="container">
    <nav><a href="index.html">← Hourly Analysis</a></nav>
    <h1>Quarter-of-the-Hour Study</h1>

    <div class="filter-bar">
      <label>Min sample size <input type="number" id="min-count" value="30" min="0" step="10" /></label>
      <label>Slice
        <select id="slice">
          <option value="aggregate">Aggregate</option>
          <option value="by_year">By year</option>
          <option value="by_hour">By hour-of-day</option>
          <option value="by_dow">By DOW</option>
        </select>
      </label>
    </div>

    <div class="tabs">
      <div class="tab active" data-panel="a">A · Location</div>
      <div class="tab" data-panel="b">B · Sequencing</div>
      <div class="tab" data-panel="c">C · Per-quarter bias</div>
      <div class="tab" data-panel="d">D · Conditional shifts</div>
      <div class="tab" data-panel="e">E · Extreme persistence</div>
      <div class="tab" data-panel="f">F · Q1-range expansion</div>
    </div>

    <div id="panel-a" class="tab-panel active card"><table id="t-a"></table></div>
    <div id="panel-b" class="tab-panel card"><table id="t-b"></table></div>
    <div id="panel-c" class="tab-panel card"><table id="t-c"></table></div>
    <div id="panel-d" class="tab-panel card"><table id="t-d"></table></div>
    <div id="panel-e" class="tab-panel card"><table id="t-e"></table></div>
    <div id="panel-f" class="tab-panel card"><table id="t-f"></table></div>
  </div>

  <script src="shared.js"></script>
  <script>
    const STUDIES = ['a', 'b', 'c', 'd', 'e', 'f'];

    async function init() {
      // Register a parquet view per (study, slice). For MVP, load all aggregate views.
      for (const s of STUDIES) {
        for (const slice of ['aggregate', 'by_year', 'by_hour', 'by_dow']) {
          try {
            await loadParquet(`../data/quarters/study_${s}_${slice}.parquet`, `q_${s}_${slice}`);
          } catch (e) {
            // Some study/slice combos may be empty (e.g. study_f with sparse data)
            console.warn(`Skipped q_${s}_${slice}:`, e.message);
          }
        }
      }
      document.querySelectorAll('.tab').forEach(t => {
        t.addEventListener('click', () => {
          document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
          document.querySelectorAll('.tab-panel').forEach(x => x.classList.remove('active'));
          t.classList.add('active');
          document.getElementById('panel-' + t.dataset.panel).classList.add('active');
        });
      });
      document.getElementById('slice').addEventListener('change', render);
      document.getElementById('min-count').addEventListener('change', render);
      await render();
    }

    function getSlice() { return document.getElementById('slice').value; }
    function getMinCount() { return parseInt(document.getElementById('min-count').value, 10) || 0; }

    function genericTable(rows, sliceCol) {
      if (!rows.length) return '<thead><tr><th>(no data)</th></tr></thead>';
      const cols = Object.keys(rows[0]);
      const minC = getMinCount();
      const head = '<thead><tr>' + cols.map(c => `<th>${c}</th>`).join('') + '</tr></thead>';
      const body = '<tbody>' + rows.map(r => {
        const lowCount = r.count != null && r.count < minC;
        return `<tr${lowCount ? ' class="row-low-count"' : ''}>` +
          cols.map(c => {
            const v = r[c];
            if (v == null) return '<td>—</td>';
            if (typeof v === 'number' && c.endsWith('_pct')) return `<td>${fmtPct(v)}</td>`;
            if (typeof v === 'number' && c.endsWith('_rate')) return `<td>${fmtPct(v)}</td>`;
            if (typeof v === 'number' && Number.isInteger(v)) return `<td>${fmtNum(v)}</td>`;
            if (typeof v === 'number') return `<td>${v.toFixed(3)}</td>`;
            return `<td>${v}</td>`;
          }).join('') + '</tr>';
      }).join('') + '</tbody>';
      return head + body;
    }

    async function render() {
      const slice = getSlice();
      for (const s of STUDIES) {
        const view = `q_${s}_${slice}`;
        try {
          const rows = await query(`SELECT * FROM ${view}`);
          document.getElementById(`t-${s}`).innerHTML = genericTable(rows, slice);
        } catch (e) {
          document.getElementById(`t-${s}`).innerHTML = `<thead><tr><th>(${e.message})</th></tr></thead>`;
        }
      }
    }

    init().catch(e => alert('Failed to load: ' + e.message));
  </script>
</body>
</html>
```

- [ ] **Step 2: Manual validation**

Open `http://localhost:8001/Analysis/dashboard/quarters.html`. Verify:
- All 6 tabs render their tables
- Slice selector (aggregate/by_year/by_hour/by_dow) repopulates tables
- Min-count slider greys low-count rows

- [ ] **Step 3: Commit**

```bash
git add Analysis/dashboard/quarters.html
git commit -m "Analysis dashboard: quarter study page (A-F tabs)"
```

---

## Task 21: Hub link from root `index.html`

**Files:**
- Modify: `index.html` (root)

- [ ] **Step 1: Read current root index**

Run: `head -200 /Users/abhi/Projects/Statistic.ally/index.html`

Find the section/grid where Fractal Sweep is linked. The hub uses cards/links to each sub-page.

- [ ] **Step 2: Add a card linking to `Analysis/dashboard/index.html`**

Use `Edit` to add an `<a href="Analysis/dashboard/index.html">` entry alongside the existing Fractal Sweep link. Match the existing card styling pattern. Concrete edit depends on the file's exact structure, but the link target must be `Analysis/dashboard/index.html` and the visible label "NQ Hourly Analysis".

- [ ] **Step 3: Manual validation**

Reload `http://localhost:8001/`. Verify the new card appears and clicks through to the analysis landing page.

- [ ] **Step 4: Commit**

```bash
git add index.html
git commit -m "Hub: link to NQ hourly analysis dashboard"
```

---

## Task 22: Full run + final validation

- [ ] **Step 1: Run engine across full history**

```bash
cd /Users/abhi/Projects/Statistic.ally
python Analysis/engine/run_all.py
```

Expected: progress lines, completes within a few minutes, prints non-zero counts.

- [ ] **Step 2: Manual eyeball of dashboards against full data**

- `http://localhost:8001/Analysis/dashboard/index.html` — manifest shows full date range
- `breakout.html` — by-year table shows all years with reasonable counts (low hundreds to thousands)
- `quarters.html` — all 6 tabs render across all slices

Spot-check one number: e.g. 10:00 ET bullish breakout rate should be in the ballpark of 15-25% (just a sanity range; record actual for future reference).

- [ ] **Step 3: Run the full test suite**

```bash
pytest Analysis/tests/ -v
```

Expected: all tests pass.

- [ ] **Step 4: Final commit (changelog or README if anything else updated)**

If anything else was tweaked during validation, commit with a clear message. Otherwise no commit needed.

---

## Self-Review Checklist (run after writing this plan)

Reviewed against the spec on 2026-04-26. Notes:

1. **Spec coverage** — every section of the design doc maps to at least one task:
   - Bar construction (spec §Component: bars.py) → Tasks 3-8
   - Breakout study (§Component: breakout_study.py) → Tasks 10-12
   - Quarter study (§Component: quarter_study.py) → Tasks 13-14
   - Slicers (§Component: slicers.py) → Task 9
   - run_all.py (§Component: run_all.py) → Task 15
   - Dashboard (§Component: Dashboard) → Tasks 17-21
   - Testing (§Testing section) → Tasks 3-14 (unit), Task 16 (integration); test_helpers exists from Task 2

2. **Placeholder scan** — no TBD/TODO; every code step shows actual code; every test shows the expected behavior in code.

3. **Type consistency** — column names checked across tasks:
   - `hour_start_et`, `prev_hour_high`, `prev_hour_mid`, `breakout`, `followthrough`, `takeout_quarter_of_h2`, `immediate_reversal`, `h1_open_vs_prev_mid`, `q_of_high`, `extreme_first`, `qN_dir`, `qN_range`, `qN_body`, `hour_dir`, `hour_range` — used consistently.
   - Function names: `bars.db_path`, `bars.load_minutes`, `bars._enrich_minutes`, `bars.build_hourly`, `bars.attach_prev_hour`, `bars.build_quarters`, `bars.build_all`, `bars.build_all_from_minutes` — all defined and referenced consistently.
   - Slicer fns: `slice_aggregate / slice_by_year / slice_by_hour / slice_by_dow / slice_by_hour_dow` — consistent.

4. **One known nuance** in Task 13 — the `q_high_minute` column in `quarters` is a minute-of-hour (0-59), not minute-of-quarter. The `extreme_first` derivation in `build_features` initially had a more complex computation; the simpler version (using the absolute minute directly via the apply lambda) is what's in the final code. This is correct because `bars.build_quarters` (Task 7) preserves the minute-of-hour value from the source 1-min row.
