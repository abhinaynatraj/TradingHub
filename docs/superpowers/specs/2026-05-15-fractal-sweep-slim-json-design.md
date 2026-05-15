# Fractal Sweep — Slim JSON Design (Option A)

**Status:** approved, ready for implementation planning
**Date:** 2026-05-15
**Author:** Abhiney (with Claude)

## Context

`Fractal Sweep/model_stats.json` is 270 MB. Profiling shows 75% of that bulk is `recent_trades` (raw trade rows duplicated at the top level of each profile) and 22.7% is `by_tf` sub-slices that each embed their own `recent_trades`. The remaining 29 keys per profile combined are <1% of the file.

Parquet support was already added in [server.py:73-108](../../../server.py#L73-L108) and [engine/model_stats.py:2739-2743](../../../Fractal%20Sweep/engine/model_stats.py#L2739-L2743) by an earlier change (commit 6793c7a), but it currently only serves the Trades tab. All other tabs still read trade rows from JSON.

This spec scopes "Option A — Slim JSON": remove trade rows from JSON entirely, route every consumer to the parquet-backed `/trades` endpoint. JSON keeps its 29 aggregate keys per profile.

The deferred follow-ups, documented for context but not in this scope:
- **Option B:** apply the same slim pattern to Amas Models (uses similar `{model→profiles→stats}` JSON).
- **Option C:** migrate to NPG/Hourly's DuckDB-WASM architecture — parquet read directly in the browser, JSON eliminated, `server.py` reduced to `/recalc` only.

Every design choice in A is made to keep B and C cheap.

## Goals

1. Reduce `Fractal Sweep/model_stats.json` from 270 MB to a small file containing only aggregate stats. Expected outcome: under 30 MB. Final size depends on `by_tf` aggregate footprint after trade rows are stripped.
2. Frontend reads trade rows exclusively from `model_stats.parquet` via the `/trades` endpoint, never from JSON.
3. JS consumers adapt to parquet's native column schema so a future migration to DuckDB-WASM is mechanical.
4. Verify zero stat drift via deterministic snapshot tests AND one-session shadow-mode runtime asserts.

## Non-Goals

- Migrating Amas / NPG / Hourly (B).
- Eliminating JSON entirely or moving to DuckDB-WASM (C).
- Touching `engine/model_stats.py` aggregation math — only output serialization.
- Re-implementing any of the 29 precomputed aggregations server-side or in SQL.

## Constraints

- `engine/model_stats.py` continues to write parquet from the same DataFrame as JSON. No engine math changes.
- `/data` endpoint behavior unchanged — continues to slice JSON for aggregates.
- `server.py` remains required for `/data` and `/recalc`.
- Parquet is the canonical schema source of truth (option β). Server returns parquet rows as-is, with no column renames or derived fields. JS consumers adapt.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│ engine/model_stats.py  (writes both, parquet from same df as JSON)      │
│   ├─ model_stats.json     ← aggregates only (NO recent_trades anywhere) │
│   └─ model_stats.parquet  ← all trade rows (unchanged from today)       │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ server.py                                                                │
│   /data?engine=fractal_sweep&model=X&profile=Y                          │
│       → JSON slice (aggregates only, no recent_trades)                  │
│   /trades?engine=fractal_sweep&model=X&profile=Y&period=2y              │
│       → parquet slice, anchored to MAX(date), parquet-native schema     │
│   /trades?engine=fractal_sweep&model=X&profile=Y&from=YYYY-MM-DD&to=... │
│       → parquet slice, arbitrary date window, parquet-native schema     │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ js/data.js  (frontend trade cache, keyed by (model, profile, period))   │
│   loadTrades(model, profile, periodOrRange)                             │
│     → cached in DATA[fullKey].trades[cacheKey]                          │
│     → consumers read parquet column names directly                      │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
            ┌───────────────┬───────┴────────┬───────────────┐
            ▼               ▼                ▼               ▼
        verdict.js    walkforward.js    excursion.js    filters.js  etc.
        (reads stop_price; dow→name JS-side; etc.)
```

### Sequence — user changes Period in dashboard

1. UI fires `switchTF('2y')` → calls existing `loadProfile(fullKey, profile)` AND new `loadTrades(fullKey, profile, '2y')`.
2. `loadTrades` checks `DATA[fullKey].trades['2y']`. Hit → resolve immediately. Miss → `fetch('/trades?engine=fractal_sweep&model=...&profile=...&period=2y')`.
3. Server `_get_trades()` loads cached pandas DataFrame, filters by `model_key + profile_key`, then `WHERE date >= MAX(date) - INTERVAL '2 years'`, returns JSON array of records using parquet's native column names.
4. Frontend caches result under `DATA[fullKey].trades['2y']`.
5. Render functions (verdict, excursion, edge, filters) read from cache. If filter chips (SMT/F3/F4) are toggled, they filter the cached list in JS — no extra fetch.
6. `data.js` re-aggregator at line 382 rebuilds by_hour/by_session/by_dow/dir_summary/by_year/top_combos/worst_combos from the filtered cache, using parquet column names.

### Sequence — walkforward custom range

1. User defines train range `2020-01-01 → 2022-12-31` and test range `2023-01-01 → 2024-12-31`.
2. `walkforward.js` calls `loadTrades(fullKey, profile, {from:'2020-01-01', to:'2022-12-31'})` then `loadTrades(..., {from:'2023-01-01', to:'2024-12-31'})`.
3. Server `_get_trades()` enforces XOR: exactly one of `period` or `(from,to)`. Returns 400 on violation.
4. Cache key for custom ranges: `"${from}:${to}"` string. Caches like canonical periods.

### Schema bridge (β)

Parquet column names are canonical. The known JSON↔parquet differences:

| Old JSON name | New parquet name | Derived JS-side? |
|---|---|---|
| `sl_price` | `stop_price` | No — rename consumers |
| `dow_name` | (none — derive from `dow`) | Yes — `['Sun','Mon','Tue','Wed','Thu','Fri','Sat'][dow]` |

Additional differences may surface during shadow mode — that is its job.

### Failure modes

| Condition | Behavior |
|---|---|
| Parquet missing on disk | `/trades` returns `404 {"error": "no parquet"}`. Frontend shows error matching today's "model_stats.json not found" UX. Recalc button still works. |
| Parquet older mtime than JSON | Server logs warning, serves anyway. Engine writes both together; this should not happen unless files are hand-edited. |
| XOR violation (`period=2y&from=...`) | 400 with explicit error message. |
| Empty parquet slice (model/profile not in parquet) | `{"trades": [], "count": 0}` — frontend handles this same as "no data" today. |

## File-Level Changes

### `Fractal Sweep/engine/model_stats.py`
- Remove `recent_trades` from the top-level profile dict ([line 2256](../../../Fractal%20Sweep/engine/model_stats.py#L2256)) and from each by_tf sub-slice ([line 2395](../../../Fractal%20Sweep/engine/model_stats.py#L2395)).
- Add to each by_tf sub-slice: `date_start` and `date_end` (the anchored period boundaries the engine already computes for `wl_sub_full`). This lets the dashboard pass exact windows to `/trades?from=...&to=...` if needed for verification or future features.
- Parquet writer unchanged.
- Expected JSON shrink: 270 MB → ~30-50 MB.

### `server.py`
- Extend `_get_trades()` ([lines 73-108](../../../server.py#L73-L108)) to accept:
  - `period`: one of `'2y' | '1y' | '6m' | '3m' | '1m' | 'all'` — anchored to `df['date'].max()`.
  - `from`, `to`: `'YYYY-MM-DD'` — arbitrary window.
  - **XOR enforced**: returns 400 if both or neither (besides `model`+`profile`) supplied.
  - `limit` becomes optional default-None (return all rows in slice).
- Pass-through schema — no column renames, no derived fields. Return parquet records as-is.
- Routing in `do_GET` for `/trades` already exists; expand query-param validation.
- No changes to `_get_data()` aggregate slicing.

### `Fractal Sweep/js/data.js`
- Add `loadTrades(fullKey, profile, periodOrRange)` — caches under `DATA[fullKey].trades[cacheKey]` where cacheKey is the period string (e.g. `'2y'`) or `"${from}:${to}"` for custom ranges.
- Update `getProfileData()` and the in-JS re-aggregator at [line 382](../../../Fractal%20Sweep/js/data.js#L382) to read trades from `DATA[fullKey].trades[activePeriod]` instead of `profileData.recent_trades`.
- Update column references inside re-aggregator: `sl_price` → `stop_price`; remove reads of `dow_name` (derive `['Sun','Mon','Tue','Wed','Thu','Fri','Sat'][dow]` at the one place that displays it).

### Six trade-row consumers (parquet-native column reads)

| File | What changes |
|---|---|
| [verdict.js:74-78](../../../Fractal%20Sweep/js/verdict.js#L74) | Read trades from `loadTrades(...)` instead of `pd.recent_trades` / `pd.by_tf[tf].recent_trades` |
| [walkforward.js:753-754](../../../Fractal%20Sweep/js/walkforward.js#L753) | Read trades from `loadTrades(..., {from,to})` for the custom-range path |
| [tabs/edge.js:331](../../../Fractal%20Sweep/js/tabs/edge.js#L331) | Read from `loadTrades` cache; rename `sl_price` if used |
| [tabs/excursion.js:238,487](../../../Fractal%20Sweep/js/tabs/excursion.js#L238) | Same as above |
| [tabs/filters.js:4](../../../Fractal%20Sweep/js/tabs/filters.js#L4) | Same as above |
| [app.js:130](../../../Fractal%20Sweep/js/app.js#L130) | Same as above |

### Period switcher integration
Whatever function handles `switchTF('2y')` etc. — add `await loadTrades(fullKey, profile, newTF)` before re-render. Exact integration point identified during implementation.

### Recalc reload path
[app.js:166](../../../Fractal%20Sweep/js/app.js#L166) currently does the full `fetch('./model_stats.json')` reload after recalc. Replace with `initProfileData()` (already exists for initial load) plus invalidation of `DATA[fullKey].trades` cache so next period switch refetches. Carried as a bonus fix.

## Testing — Snapshot

New file: `Fractal Sweep/tests/test_no_drift.py`.

Before any code changes (on `main`), generate a snapshot via `tests/gen_no_drift_snapshot.py`:
- For a fixed `(model, profile, period)` set covering every model × `simple_1r` × every canonical period.
- Capture: verdict score, dir_summary `{wr, ev, pf}`, by_hour distribution, top_combos top-5, MAE p50/p75/p90, MFE p50/p75/p90, walkforward train/test EV for one canonical range.
- Stored as `tests/fixtures/no_drift_snapshot.json`, committed.

After migration: re-run the same computations against the new code path (Python-side equivalent of what the JS does for re-aggregation). Assert per-field deltas <0.1% for floats, exact match for integer counts.

## Testing — Shadow Mode

New file: `Fractal Sweep/js/shadow.js`, imported only when `?shadow=1` is in URL.

- Hooks `loadTrades` to also fetch the JSON `recent_trades` (kept in JSON for ONE engine run during the rollout transition) and `console.assert` row counts plus a sampled 50-row deep-equality check after parquet→JSON column renames are applied.
- Cycle through dashboard (every period, every filter toggle, walkforward custom range) with `?shadow=1` once.
- If console clean → flip the `engine/model_stats.py` switch that removes `recent_trades` from JSON, regenerate, delete `shadow.js`.

## Rollout Sequence (intentional ordering)

1. Land snapshot test on `main` (no code changes yet).
2. Add `/trades` extensions to `server.py` — new params only, old behavior preserved. Test in isolation.
3. Add `loadTrades` and parquet-native reads in JS. Keep a fallback path that reads `recent_trades` from JSON if `loadTrades` cache empty — safety net during the transition.
4. Add `shadow.js`. Run with `?shadow=1` for one full dashboard session. Fix any drifts surfaced.
5. Flip engine to stop writing `recent_trades` to JSON. Regenerate. Snapshot test must pass.
6. Remove fallback paths in JS. Delete `shadow.js`.

## Out of Scope

- Amas / NPG / Hourly migrations (B/C).
- Walkforward custom-range UI changes — existing UI already produces ranges; this design only routes them to `loadTrades`.
- Splitting `data.js` or any of the 6 consumer files further — they remain within size bounds.

## Open Questions for Implementation Plan

(None — design is fully resolved. Implementation plan will sequence the rollout steps above and identify the exact integration point for the period switcher.)
