# Hourly Analysis — H2 MAE/MFE Excursion by Hour-of-Day

**Status:** approved, ready for implementation planning
**Date:** 2026-05-17
**Author:** Abhiney (with Claude)

## Context

The Hourly Analysis dashboard (`Analysis/dashboard/index.html`) studies hour-of-day price behavior across 15 years of 1-minute NQ data. The Breakout tab classifies each hour as bullish/bearish/neither based on whether its close crossed the prior hour's high or low, then measures whether the next hour (H2) follows through (extends in the breakout direction) or immediately reverses.

Today the dashboard reports follow-through rates, immediate-reversal rates, and takeout-quarter timing — all binary or categorical signals about H2's *direction*. There's no measurement of H2's *magnitude*: how far did the breakout-direction trade run in favor before exit, and how deep did it draw down against?

This spec adds MAE (Maximum Adverse Excursion) and MFE (Maximum Favorable Excursion) for the implied breakout trade, measured intrabar during H2 only, expressed as percentage of H2 open price (basis-point-style normalization).

## Goals

1. For every confirmed breakout row in `breakouts.parquet`, compute MAE and MFE during H2, expressed as percentage of H2 open.
2. Surface a new "Excursion by Hour-of-Day (H2 window)" section on the existing Breakout tab — table + chart.
3. Stay fully within the parquet + DuckDB-WASM architecture. No JSON aggregates, no server endpoints, no Python at runtime.

## Non-Goals

- Touching Fractal Sweep, Amas, NPG, or any other engine.
- Adding a dedicated "MAE Study / MFE Study" tab.
- Recommendation logic (PTQ / opt_sl).
- Trade simulation beyond H2 (no multi-hour holding, no SL/TP modeling).
- Backtesting filter combinations on excursion.

## Constraints

- Direction = same as breakout (`bullish` → long, `bearish` → short). No reverse / mean-reversion trades.
- Entry = H2 open (the same instant as H1 close).
- Exit window = H2 close (60 minutes max).
- MAE/MFE strictly intrabar within H2, from 1-min bars.
- Units = `(pts / h2_open) * 100` — percentage of entry price. NOT % of H2 range. NOT raw points.
- Engine re-run required after merge (regenerates `breakouts.parquet`).

## Architecture

```
Analysis/engine/breakout_study.py
  ├── classify(hourly)              [unchanged]
  ├── attach_followthrough(classified, minutes)
  │     [extends — adds h2_mae_pct + h2_mfe_pct in the same loop
  │      as the existing followthrough/immediate_reversal/takeout columns]
  └── breakout_metric(events)        [unchanged]

Analysis/data/breakout/breakouts.parquet
  [+2 new float columns: h2_mae_pct, h2_mfe_pct]
  (~3.4 MB → ~5 MB after change)

Analysis/dashboard/index.html
  ├── <div class="page-pane" id="pane-breakout">
  │     ├── [existing] breakout-ribbon
  │     ├── [existing] breakout-bull-ft / breakout-bear-ft
  │     ├── [existing] breakout-reversal / takeout / prevmid
  │     └── [NEW]      breakout-excursion-by-hour
  │
  └── <script> (or per-pane render module)
        └── renderBreakoutExcursionByHour()  [NEW]
        ↓
        DuckDB-WASM aggregates from br alias (breakouts.parquet)
```

### Engine: per-row computation

In `attach_followthrough`, after the existing H2 minute lookup (already there for follow-through):

```python
# H2 minute bars subset already loaded
h2_open = float(h2['open'].iloc[0])
if b == 'bullish':
    # Long: MAE = open - lowest H2 low; MFE = highest H2 high - open
    mae_pts = h2_open - float(h2['low'].min())
    mfe_pts = float(h2['high'].max()) - h2_open
else:  # bearish → short
    mae_pts = float(h2['high'].max()) - h2_open
    mfe_pts = h2_open - float(h2['low'].min())

# Percentage of entry price
mae_pct = (mae_pts / h2_open) * 100  if h2_open > 0 else None
mfe_pct = (mfe_pts / h2_open) * 100  if h2_open > 0 else None
```

Both values are always ≥ 0 by construction. No sign convention to track.

### Non-breakout rows

`breakout in ('neither', 'no_prev')` → NaN for both columns. Same convention as existing `followthrough` / `immediate_reversal` columns.

### Edge cases

| Case | Handling |
|---|---|
| H2 has no matching minute bars (data gap, end of day) | NaN for both — matches followthrough behavior today |
| H2 open is 0 or missing | NaN for both (avoid divide-by-zero) |
| Bullish breakout that immediately reverses | Real MAE (large) + real MFE (small) — this is the signal we want |
| H2 stays above open the whole hour (bullish) | MAE = 0, MFE > 0 |

### Dashboard: SQL aggregation

The Hourly Analysis dashboard already loads `breakouts.parquet` as alias `br` via `window.loadParquet`. Single DuckDB-WASM query:

```sql
SELECT
  hour_of_day_et,
  breakout,
  COUNT(*) AS n,
  AVG(h2_mae_pct)  AS avg_mae_pct,
  AVG(h2_mfe_pct)  AS avg_mfe_pct,
  quantile_cont(h2_mfe_pct, 0.9)  AS p90_mfe_pct,
  quantile_cont(h2_mae_pct, 0.9)  AS p90_mae_pct
FROM br
WHERE breakout IN ('bullish', 'bearish')
  AND h2_mae_pct IS NOT NULL
  AND h2_mfe_pct IS NOT NULL
  -- + global filter clauses interpolated by JS: year, dow, direction
GROUP BY hour_of_day_et, breakout
HAVING n >= <mincount>
ORDER BY hour_of_day_et, breakout
```

Returns ≤ 24 hours × 2 directions = 48 rows. Negligible client-side processing.

### Dashboard: filter awareness

The new section honors the global sidebar filters the same way other Breakout panels do (`year-select`, `hour-select`, `dow-pills`, `direction-select`, `mincount-select`). If user filters to a single hour-of-day, the table collapses to 1-2 rows — correct behavior, no special handling.

### Dashboard: UI layout

Two side-by-side renderings:

**(1) Table** (left, ~40% width) — sortable, matches `summary_by_hour` table look:

| Hour ET | Direction | N | Avg MAE | P90 MAE | Avg MFE | P90 MFE |
|---|---|---|---|---|---|---|
| 7  | ↑ Bull | 412 | 0.08% | 0.21% | 0.14% | 0.38% |
| 7  | ↓ Bear | 287 | 0.09% | 0.24% | 0.12% | 0.31% |
| 8  | ↑ Bull | 615 | 0.07% | 0.19% | 0.16% | 0.42% |
| ...| | | | | | |

- Hours sorted 0-23, bullish-first within each hour.
- MAE cells red-tinted, MFE cells green-tinted (matches dashboard's edge color language).
- Numbers formatted as `0.XX%` (2 decimal places).

**(2) Chart** (right, ~60% width) — grouped bar chart via Chart.js (already loaded on this page):
- X-axis = hour of day (0..23 or filtered subset)
- Paired bars per hour: bullish MFE (green), bullish MAE (red); bearish overlay toggleable
- Y-axis = % of entry price

On narrow viewports, the two stack vertically.

### Dashboard: loading and empty states

- Initial: `<div class="loading">Loading…</div>` (matches other panels)
- Empty after filters: "No breakouts match current filters"
- **Old parquet (no new columns)**: DuckDB query fails with "column not found" → wrapped in try/catch → shows "Re-run `python3 Analysis/engine/run_all.py` to generate excursion data". Same fallback pattern as Fractal Sweep's missing-JSON message.

## Parquet schema impact

| Column | Type | Nullable | Computed from |
|---|---|---|---|
| `h2_mae_pct` | float64 | yes (NaN on non-breakout or missing H2) | H2 1-min bars |
| `h2_mfe_pct` | float64 | yes (NaN on non-breakout or missing H2) | H2 1-min bars |

Size: 2 × 8 bytes × 59,677 rows ≈ ~1 MB raw (less after parquet compression). File grows from ~3.4 MB to ~5 MB. Negligible.

## Testing

### Unit tests (`Analysis/tests/test_breakout.py`)

1. **`test_h2_excursion_bullish`** — fabricated H2: open=100, low=98, high=103.
   - Expected MAE = (100-98)/100*100 = 2.0%
   - Expected MFE = (103-100)/100*100 = 3.0%

2. **`test_h2_excursion_bearish`** — fabricated H2: open=100, high=102, low=97.
   - Expected MAE (short) = (102-100)/100*100 = 2.0%
   - Expected MFE (short) = (100-97)/100*100 = 3.0%

3. **`test_h2_excursion_na_for_non_breakouts`** — assert rows with `breakout in ('neither', 'no_prev')` have NaN in both columns.

4. **`test_h2_excursion_no_minutes_returns_na`** (optional) — when H2 has zero matching minute bars (data gap), both columns are NaN.

### Integration test (`Analysis/tests/test_integration.py`)

Extend existing breakout integration test with one assertion block:
- Produced parquet has both new columns
- At least one bullish-breakout row has non-null values for both
- All non-null values are ≥ 0

### Manual dashboard verification

After engine + dashboard land:

1. `python3 Analysis/engine/run_all.py` — regenerates `breakouts.parquet` with the new columns.
2. `python3 server.py` from repo root.
3. Open `http://localhost:8001/Analysis/dashboard/index.html`, navigate to Breakout tab.
4. Scroll to bottom — new "Excursion by Hour-of-Day (H2 window)" panel visible.
5. Table populates with both bullish + bearish rows for hours 0-23.
6. Chart renders with paired bars.
7. Apply year filter → table + chart update.
8. Apply hour filter ("10 ET only") → table collapses to 2 rows.
9. Console clean (no DuckDB SQL errors).

## Rollout Sequence

1. Engine change + unit tests + integration test (one commit).
2. Regenerate `breakouts.parquet` locally (gitignored — not committed).
3. Dashboard SQL + UI + render function (one commit).
4. Manual browser check passes.
5. Open PR.

## Out of Scope

- Drift test (Hourly Analysis dashboard never had one — every render computes from parquet via SQL).
- Shadow mode (no pre/post comparison — purely additive).
- JSON schema version bump (no JSON touched).
- Backfilling excursion for follow-through-only events or H3 / H4 windows — explicitly punted to a future spec if interest emerges.
