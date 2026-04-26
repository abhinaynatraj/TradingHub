# NQ Hourly Candle Analysis — Design

**Date:** 2026-04-26
**Status:** Draft, pending review
**Location:** `Analysis/` (new top-level folder)

## Overview

Two related studies on NQ futures, both operating on hourly bars built from the shared `nq_1m` table:

1. **Breakout follow-through study** — when an hourly candle closes above the prior hour's high (or below the prior low), how often does the next hour take out the newly-formed extreme, and which quarter of the next hour does it?
2. **Quarter-of-the-hour study** — a standalone, in-depth study of intra-hour quarter price action across every valid hour: where highs/lows form, sequencing, directional bias, conditional shifts, early-extreme persistence, and Q1-range expansion.

Outputs: parquet files written by a Python engine; thin HTML dashboards read those files and let the user re-slice the data interactively.

## Scope and Conventions

### Session
- 24-hour Globex session, hour-boundary candles (00:00, 01:00, … 23:00 ET)
- Trading day: 18:00 ET → next-day 17:00 ET (futures convention)
- Daily settlement gap: 17:00–18:00 ET — the 17:00 hour is excluded from the dataset (no data)
- Weekend gap: Fri 17:00 → Sun 18:00 — Sun 18:00 hour treats Fri 16:00 as its previous trading hour

### Date range
- Full history available in `nq_1m`
- All metrics also broken out by year so regime stability is visible

### Data quality
- An hourly bar is included only if all 60 of its 1-minute bars are present (per Q9a). Hours with any missing minute are dropped from the entire analysis.
- The 17:00 ET hour is dropped (settlement gap, always empty)

### Definitions
- **Bullish breakout close:** `H1.close > H0.high` (strict; equality counts as "neither")
- **Bearish breakout close:** `H1.close < H0.low` (strict)
- **Inside bar / "neither":** anything else, including inside bars (current high ≤ prev high AND current low ≥ prev low)
- **Follow-through (bullish):** `H2.high > H1.high` at any point during H2 (strict; touch at any tick during H2)
- **Follow-through (bearish):** `H2.low < H1.low` at any point during H2
- **Previous trading hour:** the previous row in the cleaned hourly dataframe (since incomplete hours and the 17:00 gap are already removed, "previous row" = "previous valid trading hour"); naturally handles the 49-hour weekend gap (Sun 18:00 → Fri 16:00)
- **Prev-hour mid:** `(prev_hour_high + prev_hour_low) / 2` — the prior hour's range midpoint
- **Quarters:** Q1 = `:00`–`:14`, Q2 = `:15`–`:29`, Q3 = `:30`–`:44`, Q4 = `:45`–`:59`

### Slicing dimensions
Every metric is reported across:
- Aggregate
- By year
- By hour-of-day (0–23 ET)
- By DOW (Python `0=Mon` … `6=Sun`; Sat absent)
- By hour-of-day × DOW grid

## Architecture

Layered Python engine plus a thin HTML viewer.

```
Analysis/
├── hourly-analysis.md             (existing scratch file)
├── engine/
│   ├── __init__.py
│   ├── bars.py                    canonical bar construction
│   ├── breakout_study.py          breakout follow-through study
│   ├── quarter_study.py           in-depth quarter study
│   ├── slicers.py                 reusable groupby helpers
│   └── run_all.py                 driver — runs everything, writes manifest
├── data/
│   ├── manifest.json
│   ├── breakout/
│   │   ├── breakouts.parquet
│   │   ├── summary_aggregate.parquet
│   │   ├── summary_by_year.parquet
│   │   ├── summary_by_hour.parquet
│   │   ├── summary_by_dow.parquet
│   │   └── summary_grid.parquet
│   └── quarters/
│       ├── quarter_features.parquet
│       └── study_<a-f>_<slice>.parquet
├── dashboard/
│   ├── index.html
│   ├── breakout.html
│   └── quarters.html
└── tests/
    ├── test_bars.py
    ├── test_breakout.py
    ├── test_quarter_study.py
    ├── test_slicers.py
    └── test_integration.py
```

The engine is the source of truth. The dashboard reads parquet via DuckDB-Wasm and never mutates it.

## Component: `bars.py`

Builds the canonical bar dataframes consumed by every downstream study.

### Inputs
- `nq_1m` table from `Fractal Sweep/candle_science.duckdb`
- Connection path: `Path(__file__).parent.parent.parent / 'Fractal Sweep' / 'candle_science.duckdb'`
- Convert timestamps with `timezone('America/New_York', timestamp)` per project convention

### Outputs (in-memory dataframes)

**`hourly_bars`** — one row per valid hour:
- `hour_start_et` (timestamp, hour boundary in ET)
- `open`, `high`, `low`, `close`, `volume`
- `prev_hour_open`, `prev_hour_high`, `prev_hour_low`, `prev_hour_close`
- `prev_hour_mid` = `(prev_hour_high + prev_hour_low) / 2`
- `year`, `dow` (Python convention), `hour_of_day_et`

**`quarter_bars`** — four rows per valid hour:
- `hour_start_et` (foreign key to `hourly_bars`)
- `quarter` (1, 2, 3, 4)
- `open`, `high`, `low`, `close`, `volume`
- `q_high_minute`, `q_low_minute` — minute offsets within the quarter where the extremes occurred (used by the quarter study for sequencing)

### Construction rules
- Aggregate from 1-min bars: `open` = first minute's open, `high` = max, `low` = min, `close` = last minute's close, `volume` = sum
- Drop hours with fewer than 60 one-minute bars (completeness)
- Drop the 17:00 ET hour (settlement gap)
- Quarter completeness is automatic when the parent hour has all 60 minutes
- `prev_hour_*` columns: window over the cleaned, sorted hourly dataframe (`shift(1)`)
- The first row in the dataset has null `prev_hour_*` and is excluded from the breakout study (but included in the quarter study)

## Component: `breakout_study.py`

### Classification

For every H1 with a valid prev hour H0:
- Bullish breakout close: `H1.close > H0.high`
- Bearish breakout close: `H1.close < H0.low`
- Neither: everything else

Inside bars and "broke but didn't close beyond" cases naturally land in "neither" (no special exclusion).

### Follow-through (per breakout in H1, evaluated against H2)

For every breakout where H2 exists (i.e. H1 is not the last row):
- Bullish follow-through: H2 prints `bar.high > H1.high` at any point
- Bearish follow-through: H2 prints `bar.low < H1.low`
- Immediate-reversal (secondary): bullish breakout where H2 instead prints `bar.low < H1.low`; mirrored for bearish

Follow-through detection uses the 1-min table (not the H2 quarter aggregates) so the *first-touch minute* can be identified for the next step.

### Quarter-of-H2 attribution

For each follow-through, find the first 1-min bar in H2 where the takeout occurred (`high > H1.high` for bullish, `low < H1.low` for bearish). Map its minute-offset within H2 to Q1/Q2/Q3/Q4. Report distribution.

### Prev-mid conditioning

For each H1 breakout, attach:
- `h1_open_vs_prev_mid` ∈ {`above`, `below`, `equal`}

Report follow-through rates conditioned on H1's open relative to prev_mid. Hypothesis: bullish breakouts that opened *below* prev_mid (full prior-range traversal) may behave differently from those that opened above (continuation breakouts).

### Outputs (`Analysis/data/breakout/`)

- `breakouts.parquet` — one row per breakout event with all classification + outcome columns; the dashboard's drill-down source
- `summary_aggregate.parquet`, `summary_by_year.parquet`, `summary_by_hour.parquet`, `summary_by_dow.parquet`, `summary_grid.parquet` — pre-aggregated tables, one row per slice cell, columns include count + every reported rate

## Component: `quarter_study.py`

Runs on every valid hour (no breakout filter).

### Per-hour feature row

For each valid hour, build a feature row:
- 4 quarter OHLCs
- Hour OHLC
- `q_of_high` ∈ {1,2,3,4} — which quarter contains the hour's high
- `q_of_low` ∈ {1,2,3,4}
- `extreme_first` ∈ {`H`, `L`, `T`} — high-minute before low-minute, low-minute before high-minute, or same minute (rare tie)
- `q1_dir` … `q4_dir` ∈ {-1, 0, +1} — sign of `Q.close - Q.open`
- `q1_range` … `q4_range` — `high - low` per quarter
- `q1_body` … `q4_body` — `abs(close - open)` per quarter
- `hour_range`, `hour_dir`

This `quarter_features.parquet` is the workhorse for the dashboard's interactive querying.

### Sub-studies

**A. High/low location distribution**
- Distribution of `q_of_high` across all hours
- Distribution of `q_of_low`
- 4×4 cross-tab: `q_of_high` × `q_of_low`

**B. Sequencing**
- Distribution of `extreme_first` (H-first vs L-first)
- Conditional: given `extreme_first == 'H'`, distribution of `q_of_high` (and mirrored)

**C. Per-quarter directional bias and range**
- Per quarter (1–4): % up / down / flat closes
- Per quarter: average and median range
- Per quarter: average body, average body/range ratio (decisiveness proxy)

**D. Conditional shift detection**
- `q1_dir` → distribution of `q2_dir`, `q3_dir`, `q4_dir`
- `q1_dir` → distribution of `hour_dir`
- (`q1_dir`, `q2_dir`) joint → distribution of `hour_dir`
- `P(q4_dir = -q1_dir | q1_dir)` — full reversal probability
- Three-quarter conditionals (Q1+Q2+Q3 → Q4) deferred — 27 cells get thin per slice; easy to add later

**E. Early-extreme persistence**
- When `q_of_high == 1`: trivially true that Q1's high is the hour's high; the deeper stat is **distribution of overshoot** `(hour_high - q1_high)` for hours where Q1's high *failed* to hold
- Mirrored for Q1's low
- Same for Q4 (does the last quarter often print the hour extreme?)

**F. Q1-range expansion**
- Bucket hours into Q1-range quintiles (auto-adapts to volatility regime per slice)
- Per bucket: avg `hour_range`, avg remaining range `(hour_range - q1_range)`, % of hours where Q1's high or low held as the hour extreme, distribution of `hour_dir`

### Outputs (`Analysis/data/quarters/`)

- `quarter_features.parquet` — one row per hour, all features
- One pre-aggregated parquet per (study, slice) pair, e.g. `study_a_by_hour.parquet`, `study_d_by_hour_dow.parquet`

## Component: `slicers.py`

Pure utility module — every study reuses these.

```
slice_aggregate(df, metric_fn) -> 1-row dataframe
slice_by_year(df, metric_fn) -> n-rows
slice_by_hour(df, metric_fn) -> 24-rows max
slice_by_dow(df, metric_fn) -> 6-rows max (Mon–Sun, no Sat)
slice_by_hour_dow(df, metric_fn) -> hour×dow grid
```

`metric_fn(subframe) -> dict[str, Any]` — slicer is agnostic to metrics. Every output row carries a `count` column. Slicers do not drop low-count rows; the dashboard handles thresholding.

## Component: `run_all.py`

Top-level driver:
1. Build bars (`bars.build_all()`)
2. Run breakout study; write to `Analysis/data/breakout/`
3. Run quarter study; write to `Analysis/data/quarters/`
4. Write `Analysis/data/manifest.json` with run timestamp, row counts, date range, schema version
5. Print a one-page validation summary to stdout (date range, hours dropped + reason, breakout counts per year, spot-check values)

## Component: Dashboard

Three pages, all served via the existing `python3 -m http.server 8001` from repo root.

### Reading data
- DuckDB-Wasm loaded from CDN (`@duckdb/duckdb-wasm`)
- Reads parquet directly from `Analysis/data/`
- Pre-aggregated summaries serve the default views; raw `breakouts.parquet` and `quarter_features.parquet` enable user-driven re-slicing

### Pages

**`index.html`** — landing
- `manifest.json` summary: date range, total hours, last run timestamp
- Links to the two studies
- Linked from the root `Statistic.ally/index.html` hub

**`breakout.html`**
- Filter bar: year (multi), hour-of-day (multi), DOW (multi), direction toggle
- Headline cards: bullish breakout rate, bearish breakout rate, follow-through % both directions, immediate-reversal %
- Quarter-of-H2 attribution: stacked bar, % by Q1/Q2/Q3/Q4
- Prev-mid panel: side-by-side follow-through % for `h1_open above prev_mid` vs `below prev_mid`
- Hour-of-day grid table (rows = hour, cols = year, cells = follow-through %)
- DOW × hour-of-day heatmap

**`quarters.html`**
- Same filter bar
- Tabbed sections, one per sub-study A–F
- A: bar chart per quarter + 4×4 heatmap
- B: H-first vs L-first donut + conditional breakdown
- C: per-quarter bars (up/down/flat, range, body, body/range ratio)
- D: conditional probability tables for Q1→Q2/Q3/Q4 dir, Q1→hour dir, Q1+Q2→hour dir
- E: Q1-extreme hold rate + overshoot distribution chart
- F: Q1-range quintile bucket table

### Theme
- `localStorage.getItem('hub-theme')` — `'dark'` / `'light'`, no per-page key (per project convention)
- Reuse styling tokens from `Fractal Sweep` dashboards

### Sample-size handling
- Slider for min-count threshold (default 30, range 10–200)
- Cells below threshold rendered greyed-out with the count visible — never silently hidden

## Testing

`pytest` in `Analysis/tests/`. Synthetic dataframes for unit tests, real-DB slice for the integration smoke test.

### `test_bars.py`
- Hourly OHLC matches min/max/first/last of 1-min inputs
- Hour with 59 minutes is dropped
- 17:00 ET hour is always dropped
- Trading day spans 18:00 → next-day 17:00 (verified via row count over a synthetic 24h window)
- Sun 18:00 hour's `prev_hour_*` columns equal Fri 16:00's OHLC
- Daily 18:00 hour's `prev_hour_*` equals previous day's 16:00
- 4 quarter bars tile each hour exactly: Q1.open = hour.open, Q4.close = hour.close, max(Q.high) = hour.high, min(Q.low) = hour.low
- `prev_hour_mid = (prev_hour_high + prev_hour_low) / 2` exact

### `test_breakout.py`
- `H1.close > H0.high` → bullish; `H1.close == H0.high` → neither (strict)
- Inside bar → neither
- `H2.high == H1.high` → not a takeout; `H2.high > H1.high` by 1 tick → takeout
- Quarter-of-H2: synthetic minute 7 of H2 first prints high > H1.high → Q1; minute 16 → Q2

### `test_quarter_study.py`
- `q_of_high` correct for each of Q1/Q2/Q3/Q4 placements
- `extreme_first` correct when high-minute precedes low-minute and vice versa
- Q1-range quintile bucketing: synthetic 100 hours, even split

### `test_slicers.py`
- `slice_by_hour` returns up to 24 rows
- `slice_by_dow` returns up to 6 rows
- `count` column matches manual groupby

### `test_integration.py`
- Run engine against last 30 days of real DB
- Assert all output files exist, row counts non-zero
- Assert `manifest.json` has expected keys
- Assert no NaNs in `prev_hour_high`, `prev_hour_low`, `prev_hour_mid`

## Out of Scope

- ES analysis (engine is NQ-only for v1; trivial to extend by parameterizing the table name)
- Sub-quarter granularity (e.g. 5-min within a quarter)
- Three-quarter conditionals in study D (deferred)
- Live/streaming updates — runs on whatever the daily-update cron has loaded
- Dashboard tests beyond manual "loads without console errors"

## Open Items

None at design time. Items deferred (three-quarter conditionals; ES support) are explicitly listed above.
