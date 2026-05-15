# NPG Sweep Phase 2 — Dashboard + Silver Back-Port Implementation Plan (rev 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship an interactive HTML dashboard for the NPG Sweep engine using the existing `Analysis/dashboard/shared.js` infrastructure (DuckDB-WASM + parquet), trim the engine output to a parquet-friendly shape, integrate into the hub, and back-port the Silver filter to the Fractal Sweep engine + dashboard.

**Architecture:** Engine writes per-pairing parquet trade tables + a small JSON summary/manifest. Dashboard is a single `npg_dashboard.html` (~600–800 LOC target) that uses `Analysis/dashboard/shared.js` for theme, DuckDB-WASM data loading, and the `FilterBar` component. All filter recomputation happens via SQL queries against the loaded views. Silver back-port follows the same shape as Phase 1's NPG implementation but in a local FS module.

**Tech Stack:** Python 3.14, pandas, numpy, pyarrow (engine — write parquet); HTML5, vanilla JS, DuckDB-WASM via shared.js (dashboard). Theme via shared `localStorage hub-theme` key. Parquet served from `NPG Sweep/data/` directory.

**Revision note (vs rev 1):** Switched from single-file inline-JS dashboard reading 16MB JSON to parquet+DuckDB-WASM via existing `Analysis/dashboard/shared.js`. Aggregation happens server-side in SQL, not hand-rolled JS. Dashboard LOC target halved.

---

## File Structure

```
NPG Sweep/
├── npg_dashboard.html               (NEW — ~600–800 LOC; uses shared.js + shared.css)
├── npg_stats.json                   (DEPRECATED after this phase — see Task 2)
├── data/                            (NEW — parquet trade tables + manifest)
│   ├── manifest.json
│   ├── trades_1H_5M_series_multi.parquet
│   ├── trades_1H_5M_raw_measure.parquet
│   ├── trades_4H_15M_series_multi.parquet
│   ├── trades_4H_15M_raw_measure.parquet
│   ├── trades_D_1H_series_multi.parquet
│   └── trades_D_1H_raw_measure.parquet
├── engine/
│   ├── npg_stats.py                 (modify: add parquet writer alongside JSON; add entry_ts_ns)
│   └── parquet_writer.py            (NEW — small module wrapping pyarrow trade-table writes)
└── tests/
    └── test_parquet_output.py       (NEW — assert shape + manifest contract)

Fractal Sweep/
├── engine/
│   ├── filters_silver.py            (NEW — local copy of Silver logic from NPG)
│   └── model_stats.py               (modify: import filters_silver, add silver flag, extend filter variants)
├── tests/
│   └── test_filters_silver.py       (NEW — mirror NPG silver tests against FS module)
├── model_stats.json                 (regenerated after Silver port)
└── model_dashboard.html             (modify: add Silver chip alongside F3/F4/SMT)

Analysis/dashboard/                  (READ-ONLY in this plan — we consume shared.js / shared.css)

index.html                            (modify: add NPG card to model grid)
docs/superpowers/specs/2026-05-03-npg-dashboard-phase2-design.md  (already committed)
```

**Boundaries:**
- `npg_dashboard.html` — single file. Loads `../Analysis/dashboard/shared.css` and `../Analysis/dashboard/shared.js`. Inline `<script>` block contains: data loading (call `loadParquet()` for each pairing/profile), filter chip wiring, render functions that issue SQL queries via `query()`, vanilla SVG chart helpers (reach-rate bars, equity curve).
- `engine/parquet_writer.py` — pure function module. Takes a list of trade dicts + an output path; writes parquet via pyarrow. No engine logic. Independently testable.
- `engine/npg_stats.py` — minimal change: invoke `parquet_writer` after assembling each pairing/profile's trades; also keep a much smaller `npg_stats.json` containing only summary numbers (`n_trades`, top-line `agg`, `reach_rates` baseline) so the hub card can read summary stats without loading parquet.
- `Fractal Sweep/engine/filters_silver.py` — verbatim copy of `is_silver` + `candle_of_day` from NPG. Same signatures, same behavior. Local module to avoid cross-folder imports.
- `Fractal Sweep/engine/model_stats.py` — additive only: import `is_silver`, compute `silver` flag in trade-row construction block, extend `compute_filter_variants` to enumerate Silver as a 4th filter.
- `Fractal Sweep/model_dashboard.html` — additive: new Silver chip with same wiring pattern as existing SMT chip.

---

## Architectural Decisions Locked Upfront

These propagate through every task — do not relitigate during execution:

1. **Data format:** parquet, one file per `<pairing>_<profile>` combination. JSON kept only as a small summary/manifest for hub cards. Rationale: shared.js + DuckDB-WASM expect parquet; queries are far simpler than JS aggregation; file sizes drop ~10×.

2. **Trade row schema** (parquet column types):

   | column | type | notes |
   |---|---|---|
   | `direction` | string | 'LONG' or 'SHORT' |
   | `composite_r` | float64 | for series_multi: weighted partial-exit R; for raw_measure: 0.0 |
   | `hits_05x`, `hits_10x`, `hits_15x`, `hits_20x` | bool | one column per projection level (replaces the `hits` array — SQL-friendlier) |
   | `silver` | bool | |
   | `smt` | bool | |
   | `hour` | int32 | 0–23 in ET |
   | `dow` | int32 | 0=Mon..6=Sun in ET |
   | `mae_pts` | float64 | |
   | `mfe_pts` | float64 | |
   | `entry_price` | float64 | |
   | `sl_price` | float64 | |
   | `series_range` | float64 | |
   | `sweep_extreme` | float64 | |
   | `sl_hit` | bool | |
   | `entry_ts_ns` | int64 | UTC nanoseconds; sortable for equity curve |

   Dropped from Phase 1: `targets`, `hit_ts_ns`, `sweep_ts_ns`, `risk_pts`, `body_cisd`, `series_count`. Added: `entry_ts_ns`, plus the 4 boolean `hits_*` columns.

3. **DuckDB view naming:** one view per pairing/profile, alias `t_<pairing>_<profile>` with `/` replaced by `_`. Examples: `t_1H_5M_series_multi`, `t_4H_15M_raw_measure`, `t_D_1H_series_multi`. SQL queries reference these aliases directly.

4. **Filter chips → SQL WHERE:** chip state translates to a WHERE clause. Helper `buildWhere(filters)` returns the clause string. Example with silver=on, direction=LONG, session=NY: `WHERE silver = TRUE AND direction = 'LONG' AND hour BETWEEN 8 AND 15`. Session bucketing is a CASE expression, computed in SQL.

5. **`raw_measure` profile UX:** EV/PF cards hidden, equity curve hidden, breakdowns hidden — only WR (= 1.0× reach), N, and reach-rate bars shown. Same as rev 1.

6. **Silver back-port unchanged from rev 1:** local copy in FS, port wired into `model_stats.py`, FS dashboard gets a chip, regenerate JSON, record marginal edge.

7. **Constants** (carried from Phase 1):
   - `MIN_RISK_PTS = 3.0`, `MAX_RISK_PTS = 112.5`
   - `OUTCOME_MAX_BARS = 1440`
   - WIN_LEVEL_IDX = 1 (1.0× projection defines a "win")
   - Same-bar TP/SL ties: SL wins

---

## Tasks

### Task 0: Branch + baseline test confirmation

- [ ] **Step 1: Create branch off main**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
git checkout main
git status --short
git checkout -b npg-dashboard-phase2
```

Expected: clean working tree (other than the unrelated `Fractal Sweep/pine/daily_high_low_*` untracked files which we leave alone).

- [ ] **Step 2: Confirm NPG test suite passes (baseline)**

```bash
cd "/Users/abhi/Projects/Statistic.ally/NPG Sweep"
python3 -m pytest tests/ -q
```

Expected: `42 passed`. If any fail, stop and investigate.

- [ ] **Step 3: Confirm Fractal Sweep test suite passes (baseline before Silver port)**

```bash
cd "/Users/abhi/Projects/Statistic.ally/Fractal Sweep"
python3 -m pytest tests/ -q
```

Expected: All pass per the existing baseline (~195 pass + ~20 skip).

- [ ] **Step 4: Confirm pyarrow is available**

```bash
python3 -c "import pyarrow; print(pyarrow.__version__)"
```

Expected: prints a version (e.g. `15.0.0` or higher). If missing: `pip install pyarrow` and re-confirm.

---

### Task 1: NPG engine — `parquet_writer` module + tests

**Files:**
- Create: `NPG Sweep/engine/parquet_writer.py`
- Create: `NPG Sweep/tests/test_parquet_writer.py`

Pure function: takes a list of trade dicts + a path, writes parquet with the schema locked above.

- [ ] **Step 1: Write the failing test**

Path: `NPG Sweep/tests/test_parquet_writer.py`

```python
"""Tests for the NPG parquet writer.

Asserts schema (column names + types) and that hits arrays expand into
hits_05x/hits_10x/hits_15x/hits_20x boolean columns.
"""
import os
import tempfile
import pyarrow.parquet as pq
import pytest

import parquet_writer as pw


EXPECTED_COLUMNS = {
    'direction', 'composite_r',
    'hits_05x', 'hits_10x', 'hits_15x', 'hits_20x',
    'silver', 'smt', 'hour', 'dow',
    'mae_pts', 'mfe_pts',
    'entry_price', 'sl_price', 'series_range', 'sweep_extreme',
    'sl_hit', 'entry_ts_ns',
}


def _sample_trade(**overrides):
    base = dict(
        direction='SHORT',
        composite_r=1.25,
        hits=[True, True, False, False],
        silver=False,
        smt=False,
        hour=10,
        dow=2,
        mae_pts=5.0,
        mfe_pts=12.0,
        entry_price=100.0,
        sl_price=110.0,
        series_range=10.0,
        sweep_extreme=110.0,
        sl_hit=False,
        entry_ts_ns=1_700_000_000_000_000_000,
    )
    base.update(overrides)
    return base


def test_writer_emits_expected_columns():
    trades = [_sample_trade(), _sample_trade(direction='LONG', composite_r=-0.5, hits=[True, False, False, False])]
    with tempfile.NamedTemporaryFile(suffix='.parquet', delete=False) as f:
        path = f.name
    try:
        pw.write_trades_parquet(trades, path)
        tbl = pq.read_table(path)
        actual = set(tbl.column_names)
        assert actual == EXPECTED_COLUMNS, f"expected {EXPECTED_COLUMNS}, got {actual}"
        assert tbl.num_rows == 2
    finally:
        os.unlink(path)


def test_hits_array_expands_to_four_boolean_columns():
    trades = [_sample_trade(hits=[True, False, True, False])]
    with tempfile.NamedTemporaryFile(suffix='.parquet', delete=False) as f:
        path = f.name
    try:
        pw.write_trades_parquet(trades, path)
        tbl = pq.read_table(path)
        rows = tbl.to_pylist()
        assert rows[0]['hits_05x'] is True
        assert rows[0]['hits_10x'] is False
        assert rows[0]['hits_15x'] is True
        assert rows[0]['hits_20x'] is False
    finally:
        os.unlink(path)


def test_empty_trades_writes_empty_parquet_with_schema():
    with tempfile.NamedTemporaryFile(suffix='.parquet', delete=False) as f:
        path = f.name
    try:
        pw.write_trades_parquet([], path)
        tbl = pq.read_table(path)
        assert tbl.num_rows == 0
        assert set(tbl.column_names) == EXPECTED_COLUMNS
    finally:
        os.unlink(path)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd "/Users/abhi/Projects/Statistic.ally/NPG Sweep"
python3 -m pytest tests/test_parquet_writer.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'parquet_writer'`.

- [ ] **Step 3: Write the module**

Path: `NPG Sweep/engine/parquet_writer.py`

```python
"""Parquet writer for NPG trade tables.

Expands the legacy `hits` list (4 booleans) into 4 named boolean columns —
SQL-friendlier and matches the dashboard's per-projection-level chip pattern.
"""
import pyarrow as pa
import pyarrow.parquet as pq


SCHEMA = pa.schema([
    ('direction', pa.string()),
    ('composite_r', pa.float64()),
    ('hits_05x', pa.bool_()),
    ('hits_10x', pa.bool_()),
    ('hits_15x', pa.bool_()),
    ('hits_20x', pa.bool_()),
    ('silver', pa.bool_()),
    ('smt', pa.bool_()),
    ('hour', pa.int32()),
    ('dow', pa.int32()),
    ('mae_pts', pa.float64()),
    ('mfe_pts', pa.float64()),
    ('entry_price', pa.float64()),
    ('sl_price', pa.float64()),
    ('series_range', pa.float64()),
    ('sweep_extreme', pa.float64()),
    ('sl_hit', pa.bool_()),
    ('entry_ts_ns', pa.int64()),
])


def write_trades_parquet(trades, path):
    """Write a list of trade dicts to a parquet file matching SCHEMA.

    Args:
        trades: list of dicts. Each dict must contain a `hits` list of 4 bools
                (corresponding to 0.5x/1.0x/1.5x/2.0x projection reach) plus
                all other SCHEMA columns.
        path: filesystem path to write to.
    """
    cols = {col.name: [] for col in SCHEMA}
    for t in trades:
        cols['direction'].append(t['direction'])
        cols['composite_r'].append(float(t['composite_r']))
        hits = t['hits']
        cols['hits_05x'].append(bool(hits[0]))
        cols['hits_10x'].append(bool(hits[1]))
        cols['hits_15x'].append(bool(hits[2]))
        cols['hits_20x'].append(bool(hits[3]))
        cols['silver'].append(bool(t['silver']))
        cols['smt'].append(bool(t['smt']))
        cols['hour'].append(int(t['hour']))
        cols['dow'].append(int(t['dow']))
        cols['mae_pts'].append(float(t['mae_pts']))
        cols['mfe_pts'].append(float(t['mfe_pts']))
        cols['entry_price'].append(float(t['entry_price']))
        cols['sl_price'].append(float(t['sl_price']))
        cols['series_range'].append(float(t['series_range']))
        cols['sweep_extreme'].append(float(t['sweep_extreme']))
        cols['sl_hit'].append(bool(t['sl_hit']))
        cols['entry_ts_ns'].append(int(t['entry_ts_ns']))

    table = pa.table(cols, schema=SCHEMA)
    pq.write_table(table, path, compression='snappy')
```

- [ ] **Step 4: Run tests**

```bash
cd "/Users/abhi/Projects/Statistic.ally/NPG Sweep"
python3 -m pytest tests/test_parquet_writer.py -v
```

Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
git add "NPG Sweep/engine/parquet_writer.py" "NPG Sweep/tests/test_parquet_writer.py"
git commit -m "feat(npg): parquet writer for trade tables (hits expanded to 4 columns)"
```

---

### Task 2: NPG engine — wire parquet output + add `entry_ts_ns` to trade rows

**Files:**
- Modify: `NPG Sweep/engine/npg_stats.py`
- Create: `NPG Sweep/tests/test_orchestrator_output.py`

The orchestrator currently writes a single `npg_stats.json` containing `_trades` arrays. Add: emit one parquet per pairing/profile + write a small JSON containing only the summaries (no `_trades`). Also add `entry_ts_ns` to each trade row.

- [ ] **Step 1: Write the failing test**

Path: `NPG Sweep/tests/test_orchestrator_output.py`

```python
"""Tests asserting the shape of trade rows emitted by run_pairing post-Phase 2.

Phase 2 adds entry_ts_ns to every trade row (needed for parquet equity-curve
sort) and drops the now-unused fields targets/hit_ts_ns/sweep_ts_ns/risk_pts/
body_cisd/series_count.
"""
import numpy as np
import pytest
from helpers import NS_PER_MIN, BASE_TS
import npg_stats as ns


EXPECTED_TRADE_KEYS = {
    'direction', 'composite_r', 'hits', 'silver', 'smt',
    'hour', 'dow', 'mae_pts', 'mfe_pts',
    'entry_price', 'sl_price', 'series_range', 'sweep_extreme',
    'sl_hit', 'entry_ts_ns',
}

FORBIDDEN_TRADE_KEYS = {
    'targets', 'hit_ts_ns', 'sweep_ts_ns', 'risk_pts', 'body_cisd', 'series_count',
}


def _make_synthetic_1m_with_setup():
    """Same builder as test_integration; produces exactly one bearish setup."""
    n = 120
    HOUR_NS = np.int64(60 * 60 * 1_000_000_000)
    START_TS = (BASE_TS // HOUR_NS) * HOUR_NS
    ts_ns = np.array([START_TS + i * NS_PER_MIN for i in range(n)], dtype='int64')
    o = np.zeros(n); h = np.zeros(n); l = np.zeros(n); c = np.zeros(n)
    for i in range(60):
        o[i] = 24025; c[i] = 24025
        h[i] = 24050 if i == 30 else 24030
        l[i] = 24000 if i == 45 else 24020
    for i in range(60, 70):
        o[i] = 24025 + (i - 60) * 3
        c[i] = o[i] + 3
        h[i] = c[i] + 1
        l[i] = o[i] - 1
    o[70] = 24054; h[70] = 24070; l[70] = 24008; c[70] = 24056
    for i in range(71, 75):
        o[i] = 24056 + (i - 71) * 0.5
        c[i] = o[i] + 0.5
        h[i] = c[i] + 0.5
        l[i] = o[i] - 0.5
    for i in range(75, n):
        o[i] = 24050 - (i - 75) * 1.5
        c[i] = o[i] - 1.5
        h[i] = o[i] + 0.5
        l[i] = c[i] - 0.5
    return dict(ts_ns=ts_ns, open=o, high=h, low=l, close=c)


def test_trade_rows_contain_entry_ts_ns():
    m1 = _make_synthetic_1m_with_setup()
    result = ns.run_pairing(m1, sweep_tf_min=60, cisd_tf_min=5,
                            profile='series_multi', body_confirm=True,
                            multipliers=[0.5, 1.0, 1.5, 2.0])
    rows = result['trades']
    assert len(rows) >= 1
    for r in rows:
        assert 'entry_ts_ns' in r
        assert isinstance(r['entry_ts_ns'], int)


def test_trade_rows_have_exact_expected_keys():
    m1 = _make_synthetic_1m_with_setup()
    result = ns.run_pairing(m1, sweep_tf_min=60, cisd_tf_min=5,
                            profile='series_multi', body_confirm=True,
                            multipliers=[0.5, 1.0, 1.5, 2.0])
    rows = result['trades']
    assert len(rows) >= 1
    for r in rows:
        actual = set(r.keys())
        missing = EXPECTED_TRADE_KEYS - actual
        forbidden_present = FORBIDDEN_TRADE_KEYS & actual
        assert not missing, f"missing keys: {missing}"
        assert not forbidden_present, f"forbidden keys: {forbidden_present}"
```

- [ ] **Step 2: Run test (expect FAIL)**

```bash
cd "/Users/abhi/Projects/Statistic.ally/NPG Sweep"
python3 -m pytest tests/test_orchestrator_output.py -v
```

Expected: FAIL — both `entry_ts_ns` missing and forbidden keys (`targets`, `hit_ts_ns`, etc.) still present.

- [ ] **Step 3: Modify `run_pairing` trade-row dict in `engine/npg_stats.py`**

In `NPG Sweep/engine/npg_stats.py`, find the `trades.append(dict(...))` block in `run_pairing`. Replace it with:

```python
        trades.append(dict(
            direction=ev['direction'],
            sweep_extreme=ev['sweep_extreme'],
            entry_price=entry_price,
            sl_price=sl_price,
            series_range=cisd['series_range'],
            hits=outcome['hits'],
            sl_hit=outcome.get('sl_hit', False),
            composite_r=outcome['composite_r'],
            mae_pts=outcome['mae_pts'],
            mfe_pts=outcome['mfe_pts'],
            silver=silver_flag,
            smt=smt_flag,
            hour=_hour_of_day_et(int(cisd_tf['ts_ns'][entry_idx_cisd_tf])),
            dow=_day_of_week_et(int(cisd_tf['ts_ns'][entry_idx_cisd_tf])),
            entry_ts_ns=int(cisd_tf['ts_ns'][entry_idx_cisd_tf]),
        ))
```

- [ ] **Step 4: Modify `main()` to emit parquet + slim JSON**

Find the `main()` function in `engine/npg_stats.py`. It currently writes everything (including `_trades`) into `npg_stats.json`. Replace its output section with:

```python
    # Output paths
    parquet_dir = OUT_PATH.parent / 'data'
    parquet_dir.mkdir(exist_ok=True)
    summary_out = {}
    manifest = dict(
        schema_version=1,
        run_timestamp_utc=__import__('datetime').datetime.utcnow().isoformat() + 'Z',
        pairings=list(args.pairings),
        profiles=list(args.profiles),
        files={},
    )

    # Lazy import to keep pyarrow optional at module-load time
    from parquet_writer import write_trades_parquet

    for pairing in args.pairings:
        cfg = PAIRINGS[pairing]
        for profile in args.profiles:
            key = f"{pairing}/{profile}"
            print(f"[2] Running {key}")
            result = run_pairing(
                m1,
                sweep_tf_min=cfg['sweep_tf_min'],
                cisd_tf_min=cfg['cisd_tf_min'],
                profile=profile,
                body_confirm=True,
                multipliers=MULTIPLIERS,
                m1_es=m1_es,
            )
            trades = result['trades']

            # Write parquet (one file per pairing/profile)
            slug = key.replace('/', '_')
            pq_path = parquet_dir / f"trades_{slug}.parquet"
            write_trades_parquet(trades, str(pq_path))
            manifest['files'][key] = f"data/trades_{slug}.parquet"
            print(f"  → {pq_path.name} ({len(trades):,} trades)")

            # Slim summary for hub card / sanity reads (NO _trades)
            summary = result['summary']
            summary['n_trades'] = len(trades)
            summary.pop('_trades', None)
            summary_out[key] = summary

    print(f"[3] Writing {OUT_PATH}")
    with open(OUT_PATH, 'w') as f:
        json.dump(dict(summary=summary_out, manifest=manifest), f, default=_json_default)
    print(f"  Written: {OUT_PATH}")
    return summary_out
```

The `out[key]['_trades'] = result['trades']` line that existed before is gone — trades only live in parquet now.

- [ ] **Step 5: Run new tests + full suite**

```bash
cd "/Users/abhi/Projects/Statistic.ally/NPG Sweep"
python3 -m pytest tests/ -v
```

Expected: all pass (44 = 42 prior + 2 new orchestrator tests + 0 net change to parquet tests already passing from Task 1).

- [ ] **Step 6: Commit**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
git add "NPG Sweep/engine/npg_stats.py" "NPG Sweep/tests/test_orchestrator_output.py"
git commit -m "feat(npg): add entry_ts_ns + emit parquet + slim summary JSON

Engine now writes per-pairing/profile parquet trade tables to data/, plus a
small npg_stats.json containing only summaries + manifest. Replaces the
previous embedded _trades array (16 MB → ~1 MB JSON + ~2 MB parquet total)."
```

---

### Task 3: Regenerate engine output against full data

- [ ] **Step 1: Re-run engine**

```bash
cd "/Users/abhi/Projects/Statistic.ally/NPG Sweep"
python3 engine/npg_stats.py
```

Expected: completes in 1–5 min. Prints a `→ trades_<slug>.parquet (N trades)` line for each of the 6 pairing/profile combos.

- [ ] **Step 2: Verify output structure**

```bash
cd "/Users/abhi/Projects/Statistic.ally/NPG Sweep"
ls -lh npg_stats.json data/
python3 -c "
import json, pyarrow.parquet as pq
m = json.load(open('npg_stats.json'))
assert 'manifest' in m and 'summary' in m
print(f'Summary keys: {list(m[\"summary\"].keys())}')
print(f'Manifest files: {len(m[\"manifest\"][\"files\"])}')
tbl = pq.read_table('data/trades_1H_5M_series_multi.parquet')
print(f'1H_5M/series_multi rows: {tbl.num_rows:,}, cols: {len(tbl.column_names)}')
print(f'Columns: {sorted(tbl.column_names)}')
"
```

Expected:
- `npg_stats.json` ≤ 1 MB (just summaries + manifest)
- 6 parquet files in `data/`, each in single-digit MB range, totaling ~5–10 MB
- 1H_5M/series_multi has 15,148 rows
- 18 columns matching SCHEMA from Task 1

- [ ] **Step 3: No commit yet** — both `npg_stats.json` and `data/` are gitignored. Update `.gitignore` to keep `data/` excluded.

```bash
cd "/Users/abhi/Projects/Statistic.ally"
grep -q "^NPG Sweep/data/" .gitignore 2>/dev/null && echo "already gitignored" || (echo "" >> .gitignore && echo "NPG Sweep/data/" >> .gitignore && git add .gitignore && git commit -m "chore: gitignore NPG Sweep/data/ parquet output")
```

If repo `.gitignore` doesn't exist or doesn't manage `NPG Sweep/`, instead add to `NPG Sweep/.gitignore`:

```bash
cd "/Users/abhi/Projects/Statistic.ally/NPG Sweep"
grep -q "^data/$" .gitignore 2>/dev/null && echo "already gitignored" || (echo "data/" >> .gitignore && cd .. && git add "NPG Sweep/.gitignore" && git commit -m "chore: gitignore NPG Sweep parquet data dir")
```

---

### Task 4: NPG dashboard — scaffolding + shared.js wiring + data load smoke

**Files:**
- Create: `NPG Sweep/npg_dashboard.html`

Set up the dashboard with shared.css + shared.js, load all 6 parquet views, and display a sanity check (row count for one view).

- [ ] **Step 1: Write the scaffolding**

Path: `NPG Sweep/npg_dashboard.html`

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>NPG Sweep · Probability Engine</title>
  <link rel="stylesheet" href="../Analysis/dashboard/shared.css" />
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;700&family=IBM+Plex+Mono:wght@400;500&family=Inter:wght@400;500&display=swap" rel="stylesheet" />
  <style>
    .toolbar { display: flex; flex-wrap: wrap; gap: 16px; align-items: center; margin-bottom: 24px; }
    .toolbar-group { display: flex; align-items: center; gap: 8px; }
    .toolbar-label { font-family: var(--font-data); font-size: 11px; text-transform: uppercase; color: var(--text-muted); letter-spacing: 0.05em; }
    .chip-row { display: flex; gap: 4px; }
    .chip { font-family: var(--font-data); font-size: 12px; padding: 6px 12px; border: 1px solid var(--border-mid); background: var(--bg-raised); color: var(--text-secondary); cursor: pointer; border-radius: 4px; transition: all .15s; }
    .chip:hover { background: var(--bg-hover); color: var(--text-primary); }
    .chip.active { background: var(--accent); color: #fff; border-color: var(--accent); }
    .profile-select { font-family: var(--font-data); font-size: 12px; padding: 6px 10px; background: var(--bg-raised); color: var(--text-primary); border: 1px solid var(--border-mid); border-radius: 4px; cursor: pointer; }
    .tabs { display: flex; gap: 4px; margin-bottom: 16px; border-bottom: 1px solid var(--border); }
    .tab { padding: 10px 16px; cursor: pointer; color: var(--text-secondary); border-bottom: 2px solid transparent; font-family: var(--font-data); font-size: 12px; font-weight: 600; background: transparent; border-top: none; border-left: none; border-right: none; }
    .tab.active { color: var(--accent); border-bottom-color: var(--accent); }
    .compare-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }
    @media (max-width: 1100px) { .compare-grid { grid-template-columns: 1fr; } }
    .pairing-panel { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 20px; }
    .panel-title { font-family: var(--font-display); font-weight: 700; font-size: 16px; margin-bottom: 16px; color: var(--text-primary); }
    .metric-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-bottom: 20px; }
    .metric { background: var(--bg-raised); padding: 12px; border-radius: 6px; border: 1px solid var(--border); }
    .metric-label { font-family: var(--font-data); font-size: 10px; text-transform: uppercase; color: var(--text-muted); letter-spacing: 0.05em; margin-bottom: 4px; }
    .metric-value { font-family: var(--font-data); font-size: 20px; font-weight: 600; color: var(--text-primary); }
    .metric-value.positive { color: var(--green); }
    .metric-value.negative { color: var(--red); }
    .section-title { font-family: var(--font-data); font-size: 11px; text-transform: uppercase; color: var(--text-muted); letter-spacing: 0.05em; margin: 20px 0 8px; padding-bottom: 6px; border-bottom: 1px solid var(--border); }
    .chart-wrap { margin-top: 8px; background: var(--bg-raised); padding: 12px; border-radius: 6px; border: 1px solid var(--border); }
    .chart-wrap svg { display: block; width: 100%; height: auto; }
    .bar-row { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; font-family: var(--font-data); font-size: 11px; }
    .bar-label { width: 36px; color: var(--text-muted); }
    .bar-track { flex: 1; background: var(--bg-card); height: 18px; border-radius: 3px; overflow: hidden; border: 1px solid var(--border); }
    .bar-fill { height: 100%; background: var(--accent); transition: width .2s; }
    .bar-pct { width: 48px; text-align: right; color: var(--text-primary); }
    .breakdown-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; margin-top: 24px; }
    @media (max-width: 800px) { .breakdown-grid { grid-template-columns: 1fr; } }
    .breakdown-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 16px; }
    .breakdown-card h3 { font-family: var(--font-data); font-size: 12px; text-transform: uppercase; color: var(--text-muted); letter-spacing: 0.05em; margin-bottom: 10px; font-weight: 600; }
    .breakdown-table { width: 100%; border-collapse: collapse; font-family: var(--font-data); font-size: 12px; }
    .breakdown-table th { text-align: left; padding: 6px 8px; color: var(--text-muted); font-weight: 500; font-size: 10px; text-transform: uppercase; border-bottom: 1px solid var(--border); }
    .breakdown-table th.num { text-align: right; }
    .breakdown-table td { padding: 6px 8px; border-bottom: 1px solid var(--border); }
    .breakdown-table td.num { text-align: right; }
    .breakdown-table tr:last-child td { border-bottom: none; }
    .ev-heat { padding-left: 10px; padding-right: 10px; border-radius: 3px; }
  </style>
</head>
<body>
  <button class="theme-toggle" onclick="toggleTheme()">theme</button>
  <div class="container">
    <nav><a href="../index.html">← Statistic.ally</a></nav>
    <h1>NPG Sweep · Probability Engine</h1>

    <div id="status" style="font-family: var(--font-data); color: var(--text-secondary); font-size: 13px; margin-bottom: 16px;">Loading parquet views…</div>
    <div id="content"></div>
  </div>

  <script src="../Analysis/dashboard/shared.js"></script>
  <script>
    const PAIRINGS = ['1H_5M', '4H_15M', 'D_1H'];
    const PROFILES = ['series_multi', 'raw_measure'];

    // DuckDB view alias: `t_<pairing>_<profile>` with pairing slashes replaced.
    function viewAlias(pairing, profile) {
      return `t_${pairing}_${profile}`;
    }

    async function loadAllViews() {
      for (const pairing of PAIRINGS) {
        for (const profile of PROFILES) {
          const slug = `${pairing}_${profile}`;
          try {
            await loadParquet(`data/trades_${slug}.parquet`, viewAlias(pairing, profile));
          } catch (e) {
            console.error(`Failed to load ${slug}:`, e);
            throw e;
          }
        }
      }
    }

    async function init() {
      try {
        await loadAllViews();
        // Smoke check: row count for 1H_5M/series_multi
        const result = await query(`SELECT COUNT(*) AS n FROM ${viewAlias('1H_5M', 'series_multi')}`);
        const n = result[0].n;
        document.getElementById('status').textContent =
          `Loaded ${PAIRINGS.length * PROFILES.length} parquet views. 1H_5M/series_multi has ${n.toLocaleString()} trades.`;
      } catch (e) {
        document.getElementById('status').textContent = `Error: ${e.message}`;
        document.getElementById('status').style.color = 'var(--red)';
      }
    }

    init();
  </script>
</body>
</html>
```

- [ ] **Step 2: Smoke test in browser**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
python3 -m http.server 8001 &
sleep 1
echo "Open http://localhost:8001/NPG%20Sweep/npg_dashboard.html"
```

Manually open the URL. Expected:
- Page renders with title and a "Loaded 6 parquet views. 1H_5M/series_multi has 15,148 trades." message after a brief loading delay (DuckDB-WASM initial load is ~1–3s).
- Theme toggle button works.
- No console errors.

If it errors with "Failed to load …": the parquet file paths are wrong, or the http server isn't being served from the repo root. Make sure to serve from `/Users/abhi/Projects/Statistic.ally`, not from `NPG Sweep/`.

Kill server: `kill %1`.

- [ ] **Step 3: Commit**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
git add "NPG Sweep/npg_dashboard.html"
git commit -m "feat(npg-dashboard): scaffold with shared.js + DuckDB-WASM parquet load"
```

---

### Task 5: NPG dashboard — filter chip bar + SQL WHERE builder

**Files:**
- Modify: `NPG Sweep/npg_dashboard.html`

Add the filter chips (Silver, SMT, Direction, Session) and profile selector. Wire chip clicks to update `FILTERS` state and re-render the smoke-check display via SQL.

- [ ] **Step 1: Add toolbar HTML between status and content divs**

Locate `<div id="status">…</div>` in `npg_dashboard.html`. Replace that line + the empty `<div id="content"></div>` with:

```html
    <div class="toolbar" id="toolbar">
      <div class="toolbar-group">
        <span class="toolbar-label">Profile</span>
        <select class="profile-select" id="profileSelect" onchange="onProfileChange(this.value)">
          <option value="series_multi">series_multi</option>
          <option value="raw_measure">raw_measure</option>
        </select>
      </div>
      <div class="toolbar-group">
        <span class="toolbar-label">Silver</span>
        <div class="chip-row" data-filter="silver"></div>
      </div>
      <div class="toolbar-group">
        <span class="toolbar-label">SMT</span>
        <div class="chip-row" data-filter="smt"></div>
      </div>
      <div class="toolbar-group">
        <span class="toolbar-label">Direction</span>
        <div class="chip-row" data-filter="direction"></div>
      </div>
      <div class="toolbar-group">
        <span class="toolbar-label">Session</span>
        <div class="chip-row" data-filter="session"></div>
      </div>
    </div>
    <div id="status" style="font-family: var(--font-data); color: var(--text-secondary); font-size: 13px; margin-bottom: 16px;">Loading parquet views…</div>
    <div id="content"></div>
```

- [ ] **Step 2: Add filter state + chip rendering + WHERE builder JS**

In the existing `<script>` block, BEFORE the `init()` function, add:

```javascript
const FILTERS = {
  silver: 'all',
  smt: 'all',
  direction: 'all',
  session: 'all',
};

const CHIP_OPTIONS = {
  silver: [['all', 'All'], ['on', 'On'], ['off', 'Off']],
  smt: [['all', 'All'], ['on', 'On'], ['off', 'Off']],
  direction: [['all', 'All'], ['LONG', 'Long'], ['SHORT', 'Short']],
  session: [['all', 'All'], ['ASIA', 'Asia'], ['LONDON', 'London'], ['NY', 'NY'], ['OTHER', 'Other']],
};

let ACTIVE_PROFILE = 'series_multi';

function renderChips() {
  Object.entries(CHIP_OPTIONS).forEach(([filter, options]) => {
    const row = document.querySelector(`[data-filter="${filter}"]`);
    row.innerHTML = '';
    options.forEach(([value, label]) => {
      const btn = document.createElement('button');
      btn.className = 'chip' + (FILTERS[filter] === value ? ' active' : '');
      btn.textContent = label;
      btn.onclick = () => { FILTERS[filter] = value; renderChips(); rerender(); };
      row.appendChild(btn);
    });
  });
}

function onProfileChange(value) {
  ACTIVE_PROFILE = value;
  rerender();
}

function buildWhere() {
  const conds = [];
  if (FILTERS.silver === 'on') conds.push('silver = TRUE');
  if (FILTERS.silver === 'off') conds.push('silver = FALSE');
  if (FILTERS.smt === 'on') conds.push('smt = TRUE');
  if (FILTERS.smt === 'off') conds.push('smt = FALSE');
  if (FILTERS.direction !== 'all') conds.push(`direction = '${FILTERS.direction}'`);
  if (FILTERS.session === 'ASIA') conds.push('(hour >= 18 OR hour < 2)');
  if (FILTERS.session === 'LONDON') conds.push('hour BETWEEN 2 AND 7');
  if (FILTERS.session === 'NY') conds.push('hour BETWEEN 8 AND 15');
  if (FILTERS.session === 'OTHER') conds.push('hour BETWEEN 16 AND 17');
  return conds.length ? 'WHERE ' + conds.join(' AND ') : '';
}
```

- [ ] **Step 3: Add a simple `rerender()` showing filtered counts**

In the same `<script>` block, add:

```javascript
async function rerender() {
  const where = buildWhere();
  const view = viewAlias('1H_5M', ACTIVE_PROFILE);
  const sql = `
    SELECT COUNT(*) AS n,
           AVG(composite_r) AS ev,
           100.0 * AVG(CASE WHEN hits_10x THEN 1 ELSE 0 END) AS wr
    FROM ${view} ${where}
  `;
  try {
    const result = await query(sql);
    const r = result[0];
    document.getElementById('status').innerHTML =
      `<strong>1H_5M / ${ACTIVE_PROFILE}</strong> (filters: ${JSON.stringify(FILTERS)})<br>` +
      `N = ${Number(r.n).toLocaleString()} · WR = ${(+r.wr).toFixed(1)}% · EV = ${(+r.ev).toFixed(3)}R`;
  } catch (e) {
    document.getElementById('status').textContent = `Query error: ${e.message}`;
    document.getElementById('status').style.color = 'var(--red)';
  }
}
```

- [ ] **Step 4: Wire chip rendering and rerender into init**

Replace the existing `init()` function with:

```javascript
async function init() {
  try {
    await loadAllViews();
    renderChips();
    await rerender();
  } catch (e) {
    document.getElementById('status').textContent = `Error: ${e.message}`;
    document.getElementById('status').style.color = 'var(--red)';
  }
}
```

- [ ] **Step 5: Smoke test chip behavior**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
python3 -m http.server 8001 &
sleep 1
```

Open `http://localhost:8001/NPG%20Sweep/npg_dashboard.html`. Verify (numbers from Phase 1 findings — must match):

- Default (all chips "All", profile series_multi): N=15,148, WR=85.9%, EV=+0.182R
- Silver=On: N=508, WR=96.5%, EV=+0.347R
- Silver=On + SMT=On: N=274, WR=96.4%, EV=+0.359R
- Direction=Long: N≈7,441, WR≈86.5%, EV≈+0.195R
- Session=NY: N=6,018, WR=87.0%, EV=+0.197R
- Profile=raw_measure: N=15,148, WR=96.5%, EV≈0.000R

Kill server: `kill %1`.

- [ ] **Step 6: Commit**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
git add "NPG Sweep/npg_dashboard.html"
git commit -m "feat(npg-dashboard): filter chip bar + SQL WHERE builder"
```

---

### Task 6: NPG dashboard — tabs + 3-pairing Compare layout

**Files:**
- Modify: `NPG Sweep/npg_dashboard.html`

Replace the smoke status with the actual Compare-tab layout: three pairing panels side-by-side, each showing N / WR / EV / PF metric cards. No charts yet (Task 7).

- [ ] **Step 1: Replace status div with tabs + content**

In the body, locate the `<div id="status">…</div>` and `<div id="content"></div>` block. Replace just those two with:

```html
    <div class="tabs" id="tabs">
      <button class="tab active" data-tab="compare" onclick="setTab('compare')">Compare</button>
      <button class="tab" data-tab="1H_5M" onclick="setTab('1H_5M')">1H_5M</button>
      <button class="tab" data-tab="4H_15M" onclick="setTab('4H_15M')">4H_15M</button>
      <button class="tab" data-tab="D_1H" onclick="setTab('D_1H')">D_1H</button>
    </div>
    <div id="content">Loading…</div>
```

- [ ] **Step 2: Add tab + render functions**

Replace the existing `rerender()` with:

```javascript
let ACTIVE_TAB = 'compare';

function setTab(tab) {
  ACTIVE_TAB = tab;
  document.querySelectorAll('.tab').forEach(t =>
    t.classList.toggle('active', t.dataset.tab === tab));
  rerender();
}

function fmtNum(n) { return Number(n).toLocaleString(); }
function fmtPct(n) { return (+n).toFixed(1) + '%'; }
function fmtR(n)   { return (n >= 0 ? '+' : '') + (+n).toFixed(3) + 'R'; }
function fmtPF(n)  { return (+n).toFixed(2); }
function evClass(n) { return n > 0 ? 'positive' : n < 0 ? 'negative' : ''; }

// Compute summary metrics for a pairing/profile via SQL.
async function summaryFor(pairing) {
  const view = viewAlias(pairing, ACTIVE_PROFILE);
  const where = buildWhere();
  const sql = `
    SELECT
      COUNT(*) AS n,
      100.0 * AVG(CASE WHEN hits_10x THEN 1 ELSE 0 END) AS wr,
      AVG(composite_r) AS ev,
      SUM(CASE WHEN composite_r > 0 THEN composite_r ELSE 0 END) AS pos_sum,
      SUM(CASE WHEN composite_r < 0 THEN -composite_r ELSE 0 END) AS neg_sum
    FROM ${view} ${where}
  `;
  const result = await query(sql);
  const r = result[0];
  const ev = +r.ev || 0;
  const pos_sum = +r.pos_sum || 0;
  const neg_sum = +r.neg_sum || 0;
  const pf = neg_sum > 0 ? pos_sum / neg_sum : 0;
  return { n: +r.n, wr: +r.wr || 0, ev, pf };
}

function renderMetricGrid(s) {
  const showEvPf = ACTIVE_PROFILE === 'series_multi';
  const cells = [
    { label: 'N',  value: fmtNum(s.n), cls: '' },
    { label: 'WR', value: fmtPct(s.wr), cls: '' },
  ];
  if (showEvPf) {
    cells.push({ label: 'EV', value: fmtR(s.ev), cls: evClass(s.ev) });
    cells.push({ label: 'PF', value: fmtPF(s.pf), cls: '' });
  }
  return `<div class="metric-grid">${cells.map(c =>
    `<div class="metric"><div class="metric-label">${c.label}</div>` +
    `<div class="metric-value ${c.cls}">${c.value}</div></div>`).join('')}</div>`;
}

async function renderPairingPanel(pairing) {
  const s = await summaryFor(pairing);
  return `<div class="pairing-panel">
    <div class="panel-title">${pairing}</div>
    ${renderMetricGrid(s)}
  </div>`;
}

async function renderCompare() {
  const panels = await Promise.all(PAIRINGS.map(renderPairingPanel));
  return `<div class="compare-grid">${panels.join('')}</div>`;
}

async function rerender() {
  const content = document.getElementById('content');
  content.innerHTML = 'Loading…';
  try {
    if (ACTIVE_TAB === 'compare') {
      content.innerHTML = await renderCompare();
    } else {
      content.innerHTML = await renderPairingPanel(ACTIVE_TAB);
    }
  } catch (e) {
    content.innerHTML = `<div style="color: var(--red)">Render error: ${e.message}</div>`;
  }
}
```

- [ ] **Step 3: Smoke test**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
python3 -m http.server 8001 &
sleep 1
```

Open dashboard. Verify:
- Compare tab shows 3 panels with N / WR / EV / PF (matching: 15148/85.9%/+0.182R/2.25, 4077/88.6%/+0.225R/2.89, 668/90.7%/+0.311R/6.72)
- Filter chips affect all 3 panels simultaneously
- Tabs switch correctly; per-pairing tabs show single panel
- raw_measure profile hides EV / PF cards
- Theme toggle works

Kill server: `kill %1`.

- [ ] **Step 4: Commit**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
git add "NPG Sweep/npg_dashboard.html"
git commit -m "feat(npg-dashboard): tabs + Compare layout with SQL-driven metric cards"
```

---

### Task 7: NPG dashboard — reach-rate bars + equity curve

**Files:**
- Modify: `NPG Sweep/npg_dashboard.html`

Add reach-rate bar chart and equity curve to each pairing panel. Both fetched via SQL.

- [ ] **Step 1: Add chart helpers**

Insert into the `<script>` block, before `renderPairingPanel`:

```javascript
async function reachRatesFor(pairing) {
  const view = viewAlias(pairing, ACTIVE_PROFILE);
  const where = buildWhere();
  const sql = `
    SELECT
      100.0 * AVG(CASE WHEN hits_05x THEN 1 ELSE 0 END) AS r05,
      100.0 * AVG(CASE WHEN hits_10x THEN 1 ELSE 0 END) AS r10,
      100.0 * AVG(CASE WHEN hits_15x THEN 1 ELSE 0 END) AS r15,
      100.0 * AVG(CASE WHEN hits_20x THEN 1 ELSE 0 END) AS r20
    FROM ${view} ${where}
  `;
  const result = await query(sql);
  const r = result[0];
  return { '0.5x': +r.r05 || 0, '1.0x': +r.r10 || 0, '1.5x': +r.r15 || 0, '2.0x': +r.r20 || 0 };
}

function renderReachRateBars(rrates) {
  const labels = ['0.5x', '1.0x', '1.5x', '2.0x'];
  const rows = labels.map(label => {
    const pct = rrates[label];
    return `<div class="bar-row">
      <span class="bar-label">${label}</span>
      <div class="bar-track"><div class="bar-fill" style="width:${pct.toFixed(1)}%"></div></div>
      <span class="bar-pct">${pct.toFixed(1)}%</span>
    </div>`;
  }).join('');
  return `<div class="chart-wrap">${rows}</div>`;
}

async function equityPointsFor(pairing) {
  // Pull entry_ts_ns + composite_r ordered, accumulate client-side. With ~15k
  // rows this is fast; doing the cumulative sum in SQL would require a window
  // function and shipping the result anyway.
  const view = viewAlias(pairing, ACTIVE_PROFILE);
  const where = buildWhere();
  const sql = `SELECT composite_r FROM ${view} ${where} ORDER BY entry_ts_ns`;
  const rows = await query(sql);
  const cum = [];
  let running = 0;
  rows.forEach(r => { running += +r.composite_r; cum.push(running); });
  return cum;
}

function renderEquityCurve(cum) {
  if (cum.length === 0) {
    return `<div class="chart-wrap" style="text-align:center;color:var(--text-muted);font-size:12px;padding:30px">No trades</div>`;
  }
  const W = 320, H = 100, PAD_L = 36, PAD_R = 8, PAD_Y = 12;
  const innerW = W - PAD_L - PAD_R;
  const innerH = H - 2 * PAD_Y;
  const minY = Math.min(0, ...cum);
  const maxY = Math.max(0, ...cum);
  const yRange = (maxY - minY) || 1;
  const xStep = cum.length > 1 ? innerW / (cum.length - 1) : 0;
  const yToPx = y => PAD_Y + innerH - ((y - minY) / yRange) * innerH;
  const points = cum.map((y, i) => `${PAD_L + i * xStep},${yToPx(y).toFixed(1)}`).join(' ');
  const zeroPx = yToPx(0);
  const finalR = cum[cum.length - 1];
  const yLabels = [maxY, (maxY + minY) / 2, minY].map(v => ({ v, y: yToPx(v) }));

  return `<div class="chart-wrap"><svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
    ${yLabels.map(yl =>
      `<text x="4" y="${(yl.y + 3).toFixed(1)}" font-family="IBM Plex Mono,monospace" font-size="9" fill="var(--text-muted)">${yl.v >= 0 ? '+' : ''}${yl.v.toFixed(2)}</text>`
    ).join('')}
    <line x1="${PAD_L}" y1="${zeroPx.toFixed(1)}" x2="${W - PAD_R}" y2="${zeroPx.toFixed(1)}" stroke="var(--text-muted)" stroke-dasharray="3,3" stroke-width="1"/>
    <polyline points="${points}" stroke="var(--accent)" stroke-width="1.5" fill="none"/>
    <text x="${W - PAD_R - 2}" y="14" text-anchor="end" font-family="IBM Plex Mono,monospace" font-size="11" fill="var(--text-secondary)">${finalR >= 0 ? '+' : ''}${finalR.toFixed(2)}R total</text>
  </svg></div>`;
}
```

- [ ] **Step 2: Update `renderPairingPanel` to fetch + render charts**

Replace the existing `renderPairingPanel`:

```javascript
async function renderPairingPanel(pairing) {
  const s = await summaryFor(pairing);
  const rrates = await reachRatesFor(pairing);
  const showEquity = ACTIVE_PROFILE === 'series_multi';
  let equityHtml = '';
  if (showEquity) {
    const cum = await equityPointsFor(pairing);
    equityHtml = `<div class="section-title">Equity curve</div>${renderEquityCurve(cum)}`;
  }
  return `<div class="pairing-panel">
    <div class="panel-title">${pairing}</div>
    ${renderMetricGrid(s)}
    <div class="section-title">Reach rates</div>
    ${renderReachRateBars(rrates)}
    ${equityHtml}
  </div>`;
}
```

- [ ] **Step 3: Smoke test**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
python3 -m http.server 8001 &
sleep 1
```

Open dashboard. Verify:
- Each panel now shows 4 reach-rate bars matching Phase 1 findings (1H_5M: 94.7/85.9/77.3/70.2)
- Equity curve renders below bars (only when profile = series_multi)
- 1H_5M unfiltered equity curve final ≈ 15148 × 0.182R ≈ +2,757R
- Toggling Silver=On shrinks the equity curve dramatically (508 trades) but the slope is steeper
- Switching to raw_measure hides the equity curve

Kill server: `kill %1`.

- [ ] **Step 4: Commit**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
git add "NPG Sweep/npg_dashboard.html"
git commit -m "feat(npg-dashboard): reach-rate bars + SVG equity curve via SQL"
```

---

### Task 8: NPG dashboard — per-pairing breakdown tables

**Files:**
- Modify: `NPG Sweep/npg_dashboard.html`

When a per-pairing tab is active, render four breakdown tables: by-session, by-direction, by-DOW, by-hour with EV heatmap.

- [ ] **Step 1: Add breakdown helpers**

Insert into `<script>`, before the existing `renderPairingPanel`:

```javascript
const DOW_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

function evHeatColor(ev) {
  // Red→white→green interpolation, clamped at ±0.5R for color saturation.
  const t = Math.max(-1, Math.min(1, (ev || 0) / 0.5));
  if (t >= 0) return `rgba(16,185,129,${(t * 0.4).toFixed(2)})`;
  return `rgba(239,68,68,${(-t * 0.4).toFixed(2)})`;
}

async function bucketStats(pairing, bucketExpr, bucketLabelMap) {
  // bucketExpr is a SQL expression yielding the bucket key for each row.
  const view = viewAlias(pairing, ACTIVE_PROFILE);
  const where = buildWhere();
  const sql = `
    SELECT
      ${bucketExpr} AS bucket,
      COUNT(*) AS n,
      100.0 * AVG(CASE WHEN hits_10x THEN 1 ELSE 0 END) AS wr,
      AVG(composite_r) AS ev
    FROM ${view} ${where}
    GROUP BY bucket
    ORDER BY bucket
  `;
  const rows = await query(sql);
  return rows.map(r => ({
    bucket: bucketLabelMap ? (bucketLabelMap[r.bucket] || String(r.bucket)) : String(r.bucket),
    n: +r.n,
    wr: +r.wr || 0,
    ev: +r.ev || 0,
  }));
}

function renderBreakdownTable(title, bucketLabel, rows) {
  const body = rows.map(r => `<tr>
    <td>${r.bucket}</td>
    <td class="num">${fmtNum(r.n)}</td>
    <td class="num">${fmtPct(r.wr)}</td>
    <td class="num ev-heat" style="background:${evHeatColor(r.ev)}">${fmtR(r.ev)}</td>
  </tr>`).join('');
  return `<div class="breakdown-card">
    <h3>${title}</h3>
    <table class="breakdown-table">
      <thead><tr><th>${bucketLabel}</th><th class="num">N</th><th class="num">WR</th><th class="num">EV</th></tr></thead>
      <tbody>${body}</tbody>
    </table>
  </div>`;
}

async function renderBreakdowns(pairing) {
  if (ACTIVE_PROFILE !== 'series_multi') {
    return `<div class="breakdown-card" style="margin-top:24px;color:var(--text-muted);font-size:12px;padding:20px;text-align:center">Breakdowns hidden for raw_measure profile (composite_r=0 by design — EV/PF not meaningful).</div>`;
  }
  const sessionExpr = `CASE
    WHEN hour >= 18 OR hour < 2 THEN 'ASIA'
    WHEN hour BETWEEN 2 AND 7   THEN 'LONDON'
    WHEN hour BETWEEN 8 AND 15  THEN 'NY'
    ELSE 'OTHER'
  END`;
  const [bySession, byDir, byDow, byHour] = await Promise.all([
    bucketStats(pairing, sessionExpr),
    bucketStats(pairing, 'direction'),
    bucketStats(pairing, 'dow', Object.fromEntries(DOW_NAMES.map((n, i) => [i, n]))),
    bucketStats(pairing, 'hour'),
  ]);
  return `<div class="breakdown-grid">
    ${renderBreakdownTable('By Session', 'Session', bySession)}
    ${renderBreakdownTable('By Direction', 'Direction', byDir)}
    ${renderBreakdownTable('By Day of Week', 'DOW', byDow)}
    ${renderBreakdownTable('By Hour', 'Hour', byHour)}
  </div>`;
}
```

- [ ] **Step 2: Update `rerender()` to include breakdowns on per-pairing tabs**

Replace the existing `rerender()`:

```javascript
async function rerender() {
  const content = document.getElementById('content');
  content.innerHTML = 'Loading…';
  try {
    if (ACTIVE_TAB === 'compare') {
      content.innerHTML = await renderCompare();
    } else {
      const panel = await renderPairingPanel(ACTIVE_TAB);
      const bk = await renderBreakdowns(ACTIVE_TAB);
      content.innerHTML = panel + bk;
    }
  } catch (e) {
    content.innerHTML = `<div style="color: var(--red)">Render error: ${e.message}</div>`;
  }
}
```

- [ ] **Step 3: Smoke test**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
python3 -m http.server 8001 &
sleep 1
```

Open dashboard. Click 1H_5M tab. Verify:
- Below the metric panel: 4 breakdown cards (Session, Direction, DOW, Hour)
- By Session: ASIA / LONDON / NY / OTHER. NY EV ≈ +0.197R (matches Phase 1)
- By Direction: LONG ≈ +0.195R, SHORT ≈ +0.170R
- By Hour: up to 24 rows; EV cell color shifts red→white→green
- Switching to raw_measure shows the explanatory message instead

Kill server: `kill %1`.

- [ ] **Step 4: Commit**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
git add "NPG Sweep/npg_dashboard.html"
git commit -m "feat(npg-dashboard): per-pairing breakdown tables (session/dir/dow/hour) via SQL"
```

---

### Task 9: NPG dashboard — final polish + LOC check

- [ ] **Step 1: Verify LOC budget**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
wc -l "NPG Sweep/npg_dashboard.html"
```

Expected: ≤ 800 lines (target). Hard ceiling 1,000. If over 1,000, identify the largest section and prune dead code or flag follow-up.

- [ ] **Step 2: Hard-refresh full integration smoke**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
python3 -m http.server 8001 &
sleep 1
```

Run the full check in a fresh browser tab:

1. Page loads, theme matches `localStorage hub-theme` (test toggling on hub first then opening dashboard — should inherit)
2. Theme toggle button works on dashboard, persists
3. Compare tab shows 3 panels with metrics + reach bars + equity curves
4. All 4 chips toggle and recompute live
5. Profile dropdown switches series_multi ↔ raw_measure correctly
6. All 4 tabs switch + preserve filter state
7. Per-pairing tabs render 4 breakdown tables with heatmap shading
8. Numbers spot-check matches Phase 1 findings exactly (baseline, silver-on, NY session)
9. No console errors

Kill server: `kill %1`.

- [ ] **Step 3: Commit any final polish edits**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
git add "NPG Sweep/npg_dashboard.html"
git commit -m "polish(npg-dashboard): final LOC trim + smoke-test fixes" 2>/dev/null || echo "Nothing to commit (clean)"
```

---

### Task 10: Hub integration — add NPG card to `index.html`

**Files:**
- Modify: `index.html`

- [ ] **Step 1: Inspect existing model card pattern**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
sed -n '755,785p' index.html
```

Identify the `models` JS data array (around line 761) and note the exact field names used. The pattern uses `title`, `desc`, `json`, `link` (per the earlier grep at line 765 showing `'Fractal Sweep/model_dashboard.html'`).

- [ ] **Step 2: Add NPG entry to the `models` array**

In `index.html`, find the existing entries for Fractal Sweep + Amas Models. Add a new entry for NPG with the exact same shape:

```javascript
,{
  title:    'NPG Sweep',
  subtitle: 'Wick Lick + CISD',
  desc:     'Statistical engine for the npg "Sweep · CISD · FVG · Key Levels" model. 3 HTF/LTF pairings, 4-leg partial-exit profile, Silver late-week timing filter. Companion to Fractal Sweep — same data, different model spec.',
  json:     'NPG Sweep/npg_stats.json',
  link:     'NPG Sweep/npg_dashboard.html',
}
```

If the page also renders a static `<div class="model-panel">` block per model (around line 657), copy the FS panel structure and adapt it for NPG.

- [ ] **Step 3: Smoke test**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
python3 -m http.server 8001 &
sleep 1
```

Open `http://localhost:8001/index.html`. Verify:
- Three model cards visible (FS, NPG, Amas)
- Click NPG card → opens `NPG Sweep/npg_dashboard.html`
- Dashboard loads (regression check on path resolution from hub link)

Kill server: `kill %1`.

- [ ] **Step 4: Commit**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
git add index.html
git commit -m "feat(hub): add NPG Sweep card to model grid"
```

---

### Task 11: Silver back-port to FS — module + tests

**Files:**
- Create: `Fractal Sweep/engine/filters_silver.py`
- Create: `Fractal Sweep/tests/test_filters_silver.py`

Local copy of `is_silver` + `candle_of_day`. Same signatures, same behavior as NPG.

- [ ] **Step 1: Write failing tests**

Path: `Fractal Sweep/tests/test_filters_silver.py`

```python
"""Tests for the FS Silver filter (port from NPG).

Same test cases as NPG Sweep/tests/test_silver.py — proves the local copy
behaves identically.
"""
import pytest
import filters_silver as f


class TestCandleOfDay:
    def test_midnight_is_candle_1(self):
        assert f.candle_of_day(0) == 1

    def test_4am_is_candle_2(self):
        assert f.candle_of_day(4) == 2

    def test_8am_is_candle_3(self):
        assert f.candle_of_day(8) == 3

    def test_noon_is_candle_4(self):
        assert f.candle_of_day(12) == 4

    def test_4pm_is_candle_5(self):
        assert f.candle_of_day(16) == 5

    def test_8pm_is_candle_6(self):
        assert f.candle_of_day(20) == 6


class TestSilverBearish:
    def test_friday_aggressive_close_is_silver(self):
        assert f.is_silver(direction='SHORT', hour_et=16,
                           last_close=90.0,
                           prev_low=95.0, prev_prev_low=96.0,
                           prev_high=110.0, prev_prev_high=109.0) is True

    def test_thursday_after_1pm_is_silver(self):
        assert f.is_silver(direction='SHORT', hour_et=12,
                           last_close=90.0,
                           prev_low=95.0, prev_prev_low=96.0,
                           prev_high=110.0, prev_prev_high=109.0) is False
        assert f.is_silver(direction='SHORT', hour_et=13,
                           last_close=90.0,
                           prev_low=95.0, prev_prev_low=96.0,
                           prev_high=110.0, prev_prev_high=109.0) is True

    def test_close_above_one_prior_low_not_silver(self):
        assert f.is_silver(direction='SHORT', hour_et=16,
                           last_close=95.5,
                           prev_low=95.0, prev_prev_low=96.0,
                           prev_high=110.0, prev_prev_high=109.0) is False


class TestSilverBullish:
    def test_friday_aggressive_close_is_silver(self):
        assert f.is_silver(direction='LONG', hour_et=16,
                           last_close=115.0,
                           prev_low=95.0, prev_prev_low=96.0,
                           prev_high=110.0, prev_prev_high=112.0) is True

    def test_close_below_one_prior_high_not_silver(self):
        assert f.is_silver(direction='LONG', hour_et=16,
                           last_close=111.0,
                           prev_low=95.0, prev_prev_low=96.0,
                           prev_high=110.0, prev_prev_high=112.0) is False


class TestSilverTimingGate:
    def test_morning_hour_no_silver(self):
        for hour in [0, 4, 8]:
            assert f.is_silver(direction='SHORT', hour_et=hour,
                               last_close=80.0,
                               prev_low=95.0, prev_prev_low=96.0,
                               prev_high=110.0, prev_prev_high=109.0) is False, \
                f"hour {hour} should not be Silver"
```

- [ ] **Step 2: Run test (expect FAIL)**

```bash
cd "/Users/abhi/Projects/Statistic.ally/Fractal Sweep"
python3 -m pytest tests/test_filters_silver.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'filters_silver'`.

- [ ] **Step 3: Create the module**

Path: `Fractal Sweep/engine/filters_silver.py`

```python
"""Silver filter — late-week timing + aggressive close gate.

Local copy of NPG Sweep's is_silver + candle_of_day. Mirrors the npg Pine
indicator's logic at sweep_cisd_mtf_fvg.pine line 1124. Kept as a standalone
module so the FS engine doesn't import across folder roots.

Source of truth: ../../NPG Sweep/engine/filters.py (keep in sync if either
side changes; cross-test is `tests/test_filters_silver.py` which mirrors NPG's
test_silver.py).
"""
import math


def candle_of_day(hour_et):
    """npg's bucket: floor(hour/4) + 1. Buckets 1..6 for hours 0..23."""
    return math.floor(hour_et / 4) + 1


def is_silver(direction, hour_et, last_close, prev_low, prev_prev_low,
              prev_high, prev_prev_high):
    """Silver gate: late-week timing AND aggressive close.

    Timing: candleOfDay==5 OR (candleOfDay==4 AND hour_et >= 13)
    Aggressive close (bearish): last_close < min(prev_low, prev_prev_low)
    Aggressive close (bullish): last_close > max(prev_high, prev_prev_high)
    """
    cod = candle_of_day(hour_et)
    timing_ok = (cod == 5) or (cod == 4 and hour_et >= 13)
    if not timing_ok:
        return False

    if direction == 'SHORT':
        return last_close < prev_low and last_close < prev_prev_low
    elif direction == 'LONG':
        return last_close > prev_high and last_close > prev_prev_high
    return False
```

- [ ] **Step 4: Run tests + full FS suite**

```bash
cd "/Users/abhi/Projects/Statistic.ally/Fractal Sweep"
python3 -m pytest tests/test_filters_silver.py -v
python3 -m pytest tests/ -q
```

Expected: 12 PASS for the new file; baseline + 12 new for the full suite.

- [ ] **Step 5: Commit**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
git add "Fractal Sweep/engine/filters_silver.py" "Fractal Sweep/tests/test_filters_silver.py"
git commit -m "feat(fs): port Silver filter from NPG (local copy, independent module)"
```

---

### Task 12: Silver back-port to FS — wire into `model_stats.py`

**Files:**
- Modify: `Fractal Sweep/engine/model_stats.py`

Compute `silver_flag` per trade row, add it alongside `passes_f3` / `passes_f4` / `smt`. Extend `compute_filter_variants` to enumerate Silver as a 4th filter.

- [ ] **Step 1: Inspect surrounding code**

```bash
cd "/Users/abhi/Projects/Statistic.ally/Fractal Sweep"
sed -n '1265,1320p' engine/model_stats.py
```

The `base_row = dict(...)` block is around line 1295. The variables in scope at that point include `s_arrs` (sweep TF arrays), `s_high`, `s_low`, `i` (current sweep index), and `direction`. Note exactly what hour-of-day field is available — likely `s_arrs['hr'][i]`.

- [ ] **Step 2: Add `is_silver` import**

At the top of `Fractal Sweep/engine/model_stats.py`, with the other imports, add:

```python
from filters_silver import is_silver
```

- [ ] **Step 3: Compute Silver flag and add to `base_row`**

In the loop where `base_row = dict(...)` is built, immediately BEFORE the `base_row = dict(...)` line, add:

```python
            # Silver filter: late-week timing + aggressive close beyond both
            # prior candles' opposing extremes. Requires the prior 2 sweep-TF
            # candles' highs/lows. If we don't have 2 priors yet, default False.
            silver_flag = False
            if i >= 2:
                _prev_high = float(s_high[i - 1])
                _prev_low = float(s_low[i - 1])
                _prev_prev_high = float(s_high[i - 2])
                _prev_prev_low = float(s_low[i - 2])
                _last_close = float(s_arrs['close'][i])
                _hour_et = int(s_arrs['hr'][i])
                silver_flag = is_silver(
                    direction, _hour_et, _last_close,
                    _prev_low, _prev_prev_low, _prev_high, _prev_prev_high,
                )
```

If `s_arrs['close']` doesn't exist (the field name in `s_arrs` may vary), check what FS calls the sweep-TF close array — could be `s_close` or similar. Same for `s_arrs['hr']` — check what hour field FS uses. The substitution is mechanical: replace with whatever the surrounding loop already uses.

Then in the `base_row = dict(...)` block, add a new field:

```python
                silver        = silver_flag,
```

Add it alongside the existing `smt = smt_divergence,` line.

- [ ] **Step 4: Extend `compute_filter_variants` to enumerate Silver**

Find `compute_filter_variants` (around line 2389). Locate the `apply_filters` helper inside it (around line 2453, where the `for f in active_set:` loop branches on `'F3'`/`'F4'`/`'SMT'`). Add a new branch:

```python
            elif f == 'silver':
                if 'silver' in all_valid.columns:
                    mask &= all_valid['silver'] == True
```

Also locate where filter combinations are enumerated (the function builds combos of available filters). Add `'silver'` to whatever list/set drives combo enumeration so `2^4 = 16` combos are produced including Silver. Look for code like:

```python
filters_to_test = ['F3', 'F4', 'SMT']
```

and change to:

```python
filters_to_test = ['F3', 'F4', 'SMT', 'silver']
```

(The exact variable name depends on the existing code — check what's there.)

- [ ] **Step 5: Run full FS suite**

```bash
cd "/Users/abhi/Projects/Statistic.ally/Fractal Sweep"
python3 -m pytest tests/ -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
git add "Fractal Sweep/engine/model_stats.py"
git commit -m "feat(fs): wire Silver flag into model_stats engine + filter variants"
```

---

### Task 13: Regenerate FS `model_stats.json` + record Silver edge

- [ ] **Step 1: Re-run FS engine**

```bash
cd "/Users/abhi/Projects/Statistic.ally/Fractal Sweep"
python3 engine/model_stats.py
```

Expected runtime: 1–10 minutes.

- [ ] **Step 2: Inspect Silver marginal edge**

```bash
cd "/Users/abhi/Projects/Statistic.ally/Fractal Sweep"
python3 << 'EOF'
import json
d = json.load(open('model_stats.json'))
# Path to filter_variants varies — try common locations:
fv = None
for path in (['1H_5M', 'PREV', 'CISD', 'filter_variants'],
             ['1H_5M', 'filter_variants']):
    cur = d
    try:
        for k in path:
            cur = cur[k]
        fv = cur
        print(f"Found filter_variants at: {' / '.join(path)}")
        break
    except (KeyError, TypeError):
        continue
if fv is None:
    print(f"Couldn't find filter_variants. Top-level keys: {list(d.keys())}")
    raise SystemExit(1)

print(f"\n{'Combo':<32} {'N':>6} {'WR':>6} {'EV':>9} {'PF':>6}")
print("-" * 64)
for v in sorted(fv, key=lambda x: -x.get('ev', 0)):
    label = v.get('label', '?')
    print(f"{label:<32} {v['n']:>6} {v['wr']*100:>5.1f}% {v['ev']:>+8.3f}R {v['pf']:>6.2f}")

def find(filters_set):
    for v in fv:
        if set(v.get('filters', [])) == set(filters_set):
            return v
    return None

base = find(['F3', 'F4', 'SMT'])
with_silver = find(['F3', 'F4', 'SMT', 'silver'])
if base and with_silver:
    print(f"\n=== Silver marginal edge alongside F3+F4+SMT ===")
    print(f"  baseline (F3+F4+SMT):      N={base['n']:,} WR={base['wr']*100:.1f}% EV={base['ev']:+.3f}R")
    print(f"  with Silver added:         N={with_silver['n']:,} WR={with_silver['wr']*100:.1f}% EV={with_silver['ev']:+.3f}R")
    print(f"  ΔWR: {(with_silver['wr']-base['wr'])*100:+.2f}pp · ΔEV: {with_silver['ev']-base['ev']:+.3f}R")
    passes = (with_silver['wr']-base['wr'])*100 >= 1.0 or (with_silver['ev']-base['ev']) >= 0.05
    print(f"  Verdict: {'PASSES' if passes else 'NOISE'} the +1%WR / +0.05R-EV gate")
else:
    print(f"\nCouldn't find baseline + with-silver combos. Available labels:")
    for v in fv:
        print(f"  {v.get('label', '?')} — filters={v.get('filters', [])}")
EOF
```

Capture the output for the findings doc.

- [ ] **Step 3: Update findings doc**

Append a new section to `NPG Sweep/docs/npg_engine_findings.md`. Use the actual numbers from Step 2:

```markdown

## Silver back-port to Fractal Sweep — Phase 2 result

Silver was ported into the Fractal Sweep engine in Phase 2 (commit on `npg-dashboard-phase2` branch).

Marginal edge alongside the F3+F4+SMT baseline (1H_5M, ~12y NQ):

| Combo | N | WR | EV |
|---|---|---|---|
| F3+F4+SMT | <fill in from Step 2> | <…> | <…> |
| F3+F4+SMT+Silver | <fill in> | <…> | <…> |

ΔWR: <fill in> · ΔEV: <fill in>

Verdict: <PASSES / NOISE> the +1%WR / +0.05R-EV marginal-edge gate.

<2-3 sentences interpreting the result. If Silver passes, this confirms the
Phase 1 finding that Silver carries edge generalises beyond NPG's CISD
definition. If it doesn't, Silver's edge in NPG is specific to the npg
opposing-series CISD and doesn't transfer to FS's single-bar engulf CISD —
also a useful finding.>
```

Fill in actual values.

- [ ] **Step 4: Commit doc update**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
git add "NPG Sweep/docs/npg_engine_findings.md"
git commit -m "docs(npg): record Silver back-port marginal edge in FS engine"
```

---

### Task 14: Silver chip in FS dashboard

**Files:**
- Modify: `Fractal Sweep/model_dashboard.html`

Add a Silver chip alongside the existing F3/F4/SMT chips, matching the existing chip wiring pattern.

- [ ] **Step 1: Inspect existing SMT chip wiring**

```bash
cd "/Users/abhi/Projects/Statistic.ally/Fractal Sweep"
grep -n "smt-checkbox\|switchSMT\|F3-checkbox\|F4-checkbox" model_dashboard.html | head -20
```

Note: the SMT chip is at `model_dashboard.html` line ~510 (`id="smt-checkbox"`, `onchange="switchSMT(this.checked)"`). The handler is around line 833.

- [ ] **Step 2: Add the Silver chip HTML**

In `model_dashboard.html` near the SMT chip (~line 510), copy the SMT chip's exact wrapper structure and add a parallel Silver entry. The exact element shape depends on what's there — match it. Example pattern:

```html
<input type="checkbox" id="silver-checkbox" onchange="switchSilver(this.checked)">
```

(Wrap in whatever label/span structure the existing F3/F4/SMT chips use.)

- [ ] **Step 3: Add `switchSilver` JS handler**

Find `switchSMT` around line 833. Add a parallel `switchSilver` immediately after it. Look at exactly what `switchSMT` does and mirror it — the handler likely sets a state flag and calls a `rebuild` function. Example:

```javascript
function switchSilver(checked) {
  // Match what switchSMT does — set the runtime filter flag and trigger rebuild.
  RUNTIME_FILTERS.silver = checked;   // adapt to actual state object name
  rebuildAll();                         // adapt to actual rebuild fn name
}
```

- [ ] **Step 4: Wire Silver into the runtime filter loop**

Search for every place `RUNTIME_FILTERS.smt` (or whatever the SMT state field is called) is consumed — there are typically 2–4 sites doing client-side trade filtering. At each, add an analogous check for Silver:

```javascript
if (activeSilver && !row.silver) return false;
```

(The exact variable names need to match what's already in the file — match the SMT pattern.)

- [ ] **Step 5: Smoke test FS dashboard**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
python3 -m http.server 8001 &
sleep 1
```

Open `http://localhost:8001/Fractal Sweep/model_dashboard.html`. Verify:
- Silver chip visible alongside F3/F4/SMT
- Toggling Silver on shifts WR/EV in the direction recorded in Task 13's findings
- Other chips still work — no regression

Kill server: `kill %1`.

- [ ] **Step 6: Commit**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
git add "Fractal Sweep/model_dashboard.html"
git commit -m "feat(fs-dashboard): add Silver chip alongside F3/F4/SMT"
```

---

### Task 15: Final sweep — full test suites + branch ready

- [ ] **Step 1: NPG test suite**

```bash
cd "/Users/abhi/Projects/Statistic.ally/NPG Sweep"
python3 -m pytest tests/ -v --tb=short
```

Expected: all pass (47 = 42 prior + 3 from `test_parquet_writer.py` + 2 from `test_orchestrator_output.py`).

- [ ] **Step 2: FS test suite**

```bash
cd "/Users/abhi/Projects/Statistic.ally/Fractal Sweep"
python3 -m pytest tests/ -q --tb=short
```

Expected: baseline + 12 from `test_filters_silver.py`. No failures.

- [ ] **Step 3: Final dashboard integration smoke**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
python3 -m http.server 8001 &
sleep 1
```

Open `http://localhost:8001/index.html`. Run through:
- Hub shows 3 cards (FS, NPG, Amas)
- Click NPG → dashboard loads, all chips + tabs work
- Click back to hub → click FS → Silver chip is present and functional
- Toggle theme on hub → confirm both dashboards inherit (close-and-reopen if needed)

Kill server: `kill %1`.

- [ ] **Step 4: Verify branch state**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
git log --oneline main..npg-dashboard-phase2
git status --short
```

Expected: ~13–15 commits on the branch, no uncommitted changes (other than the unrelated `daily_high_low_*` untracked files).

- [ ] **Step 5: Don't merge automatically**

Leave the merge decision to the user. Branch `npg-dashboard-phase2` is ready for fast-forward merge to main.

---

## Self-Review

**1. Spec coverage:**

- ✅ Engine cleanup (drop unused fields, add `entry_ts_ns`) → Task 2
- ✅ NPG dashboard (≤1,500 LOC, but lower target now ~800) → Tasks 4–9
- ✅ Filter chips (Silver, SMT, Direction, Session) + profile selector → Task 5
- ✅ Tab navigation + Compare layout → Task 6
- ✅ Reach-rate bars + equity curve → Task 7
- ✅ Per-pairing breakdowns (session/direction/dow/hour with EV heatmap) → Task 8
- ✅ Hub card → Task 10
- ✅ Silver back-port: module + tests → Task 11
- ✅ Silver back-port: engine wire-in → Task 12
- ✅ Regenerate FS JSON + edge measurement → Task 13
- ✅ Silver chip in FS dashboard → Task 14
- ✅ Final test sweep → Task 15

Spec deliverable 1 (engine cleanup) had its scope expanded to include parquet emission — this is the architecture pivot and is reflected in Tasks 1–3.

**2. Placeholder scan:**

- Task 12 Step 3: "If `s_arrs['close']` doesn't exist…" — same justification as before. The FS engine's loop variable conventions vary across code paths and must be matched on inspection. The instruction is "match what's already there", with a complete code skeleton. Acceptable.
- Task 14 Steps 2–4: same "match the existing chip pattern" justification. The FS dashboard is 6,952 LOC and has its own conventions; the implementer must read 5 lines around the SMT chip and mirror them. Code skeletons provided.
- Task 13 Step 3: `<fill in>` markers in the findings doc — intentional, filled with actual numbers from Step 2.
- No "TBD", "implement later", "handle edge cases" placeholders.

**3. Type consistency:**

- `viewAlias(pairing, profile)` defined in Task 4 step 1, consumed in Tasks 5, 6, 7, 8 — same signature.
- `FILTERS` object schema defined in Task 5, consumed in Tasks 5, 6, 7, 8.
- `buildWhere()` defined in Task 5 step 2, consumed in Tasks 5, 6, 7, 8 — returns SQL WHERE clause string.
- Parquet schema (Task 1) consumed by every dashboard SQL query (Tasks 5–8). Column names (`hits_05x`, `hits_10x`, etc.) consistent.
- `is_silver` signature identical between NPG (`engine/filters.py`) and FS (`engine/filters_silver.py`).

**4. Risks captured in the spec are addressed:**

- Dashboard LOC creep → Task 9 has explicit budget check
- Field-strip regression → Task 2 has pinned-keys test
- Silver back-port finding no edge → Task 13 explicitly accommodates either outcome
- DuckDB-WASM init time on first load → no specific check; defer to smoke test

---

Plan complete and saved to `docs/superpowers/plans/2026-05-03-npg-dashboard-phase2.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
