# Hourly Analysis — H2 MAE/MFE Excursion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add intrabar MAE/MFE measurement during H2 (the hour after a confirmed breakout) to the Hourly Analysis Breakout tab — two new float columns on `breakouts.parquet` (`h2_mae_pct`, `h2_mfe_pct`) and one new "Excursion by Hour-of-Day" panel rendering a table + chart in the dashboard.

**Architecture:** Engine writes the two new columns inside the existing `attach_followthrough` loop in `Analysis/engine/breakout_study.py` (zero new data loads — H2 minute bars are already in scope). Dashboard adds one new SQL aggregation via DuckDB-WASM against the existing `br` alias, plus one new render function and one new DOM panel — no new server endpoints, no JSON, no Python at runtime.

**Tech Stack:** Python 3.14 · pandas · pyarrow · pytest · vanilla HTML/JS · DuckDB-WASM · Chart.js (already loaded by the dashboard)

**Reference spec:** [docs/superpowers/specs/2026-05-17-hourly-breakout-h2-excursion-design.md](../specs/2026-05-17-hourly-breakout-h2-excursion-design.md)

---

## File-level plan

| File | Action | What changes |
|---|---|---|
| `Analysis/engine/breakout_study.py` | Modify | Extend `attach_followthrough` to compute `h2_mae_pct` + `h2_mfe_pct` in the same H2 loop. Output 2 new float columns. |
| `Analysis/tests/test_breakout.py` | Modify | Add 4 unit tests for the new excursion logic. |
| `Analysis/tests/test_integration.py` | Modify | Extend existing breakout integration test with 3 assertions verifying new columns exist + are populated + are ≥ 0. |
| `Analysis/dashboard/index.html` | Modify | Add one new `<div id="breakout-excursion-by-hour">` panel inside `pane-breakout` and one new `renderBreakoutExcursionByHour()` function called from `renderBreakout()`. Uses Chart.js (already loaded for other panels). |

---

## Phase 1 — Engine: add h2_mae_pct / h2_mfe_pct to attach_followthrough

### Task 1: Failing test for bullish H2 excursion

**Files:**
- Modify: `Analysis/tests/test_breakout.py` (append at end of file)

- [ ] **Step 1: Append the failing test**

```python
def test_h2_excursion_bullish_basic():
    """Bullish breakout, H2 open=110, intra-H2 low=108, high=115.
    Expected: MAE = (110-108)/110 * 100 = 1.818...%
              MFE = (115-110)/110 * 100 = 4.545...%
    """
    h0 = helpers.make_hour('2024-01-02 09:00', ohlc=(100, 105, 95, 100),
                           high_at_minute=20, low_at_minute=40)
    h1 = helpers.make_hour('2024-01-02 10:00', ohlc=(100, 115, 95, 110),
                           high_at_minute=30, low_at_minute=40)
    # H2: open=110, low=108 at min 5, high=115 at min 20, close=112
    h2 = helpers.make_hour('2024-01-02 11:00', ohlc=(110, 115, 108, 112),
                           high_at_minute=20, low_at_minute=5)
    minutes = helpers.concat_hours(h0, h1, h2)
    enriched = bars._enrich_minutes(minutes)
    hourly, _ = bars.build_all_from_minutes(enriched)
    events = bs.attach_followthrough(bs.classify(hourly), enriched)
    h1_row = events.iloc[1]
    assert h1_row['breakout'] == 'bullish'
    assert h1_row['h2_mae_pct'] == pytest.approx((110 - 108) / 110 * 100, rel=1e-6)
    assert h1_row['h2_mfe_pct'] == pytest.approx((115 - 110) / 110 * 100, rel=1e-6)
```

- [ ] **Step 2: Run to confirm it fails**

```bash
cd "/Users/abhi/Projects/Statistic.ally/Analysis"
python3 -m pytest tests/test_breakout.py::test_h2_excursion_bullish_basic -v 2>&1 | tail -10
```

Expected: FAIL with `KeyError: 'h2_mae_pct'` or similar — column doesn't exist yet.

### Task 2: Implement h2_mae_pct / h2_mfe_pct in attach_followthrough

**Files:**
- Modify: `Analysis/engine/breakout_study.py:50-118`

- [ ] **Step 1: Update the function**

Open `Analysis/engine/breakout_study.py`. Replace the entire `attach_followthrough` function (lines 50-118) with:

```python
def attach_followthrough(classified: pd.DataFrame, minutes: pd.DataFrame) -> pd.DataFrame:
    """For each breakout row in `classified`, look at the next hour's 1-min bars
    and determine:
    - followthrough: True if H2 trades strictly beyond H1's extreme in the
      breakout direction
    - takeout_quarter_of_h2: 1..4 indicating which quarter of H2 first crossed
      (NaN if no takeout)
    - immediate_reversal: True if H2 strictly takes out H1's *opposite* extreme
      (only meaningful for breakout rows)
    - h2_mae_pct: max adverse excursion during H2 as % of H2 open
    - h2_mfe_pct: max favorable excursion during H2 as % of H2 open

    Direction convention for MAE/MFE: bullish breakout → simulated long entry
    at H2 open; bearish breakout → simulated short entry at H2 open. Both
    values are always >= 0 (expressed as positive distance from entry).

    Non-breakout rows ('neither', 'no_prev') get NaN for all five.
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
    mae_pct = []
    mfe_pct = []

    for i, row in df.iterrows():
        b = row['breakout']
        if b not in ('bullish', 'bearish'):
            followthrough.append(np.nan)
            takeout_q.append(np.nan)
            reversal.append(np.nan)
            mae_pct.append(np.nan)
            mfe_pct.append(np.nan)
            continue
        h2_start = next_hour.iloc[i]
        if pd.isna(h2_start) or h2_start not in grouped:
            followthrough.append(np.nan)
            takeout_q.append(np.nan)
            reversal.append(np.nan)
            mae_pct.append(np.nan)
            mfe_pct.append(np.nan)
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

        # ── H2 MAE / MFE as % of H2 open ────────────────────────────────────
        # Both values >= 0 by construction. NaN when H2 open is missing or zero.
        h2_open = float(h2['open'].iloc[0])
        if h2_open > 0:
            h2_low = float(h2['low'].min())
            h2_high = float(h2['high'].max())
            if b == 'bullish':
                # Long: MAE = open - lowest low; MFE = highest high - open
                mae_pts = h2_open - h2_low
                mfe_pts = h2_high - h2_open
            else:
                # Short: MAE = highest high - open; MFE = open - lowest low
                mae_pts = h2_high - h2_open
                mfe_pts = h2_open - h2_low
            mae_pct.append((mae_pts / h2_open) * 100)
            mfe_pct.append((mfe_pts / h2_open) * 100)
        else:
            mae_pct.append(np.nan)
            mfe_pct.append(np.nan)

    # Use nullable boolean / Int dtypes so NaN is represented as pd.NA
    # and parquet round-trips with proper typing for the dashboard.
    df['followthrough'] = pd.array(followthrough, dtype='boolean')
    df['takeout_quarter_of_h2'] = pd.array(takeout_q, dtype='Int64')
    df['immediate_reversal'] = pd.array(reversal, dtype='boolean')
    df['h2_mae_pct'] = pd.array(mae_pct, dtype='Float64')
    df['h2_mfe_pct'] = pd.array(mfe_pct, dtype='Float64')
    return df
```

- [ ] **Step 2: Run the failing test, expect it to pass**

```bash
cd "/Users/abhi/Projects/Statistic.ally/Analysis"
python3 -m pytest tests/test_breakout.py::test_h2_excursion_bullish_basic -v 2>&1 | tail -10
```

Expected: PASS.

- [ ] **Step 3: Run the full breakout test file to ensure no regressions**

```bash
python3 -m pytest tests/test_breakout.py -v 2>&1 | tail -20
```

Expected: all tests pass (existing + the one new).

### Task 3: Bearish excursion test

**Files:**
- Modify: `Analysis/tests/test_breakout.py` (append after the bullish test)

- [ ] **Step 1: Append the test**

```python
def test_h2_excursion_bearish_basic():
    """Bearish breakout, H2 open=90, intra-H2 high=92, low=87.
    Expected (short): MAE = (92-90)/90 * 100 = 2.222...%
                      MFE = (90-87)/90 * 100 = 3.333...%
    """
    h0 = helpers.make_hour('2024-01-02 09:00', ohlc=(100, 105, 95, 100),
                           high_at_minute=20, low_at_minute=40)
    h1 = helpers.make_hour('2024-01-02 10:00', ohlc=(100, 105, 85, 90),
                           high_at_minute=10, low_at_minute=40)
    # H2: open=90, high=92 at min 5, low=87 at min 30, close=88
    h2 = helpers.make_hour('2024-01-02 11:00', ohlc=(90, 92, 87, 88),
                           high_at_minute=5, low_at_minute=30)
    minutes = helpers.concat_hours(h0, h1, h2)
    enriched = bars._enrich_minutes(minutes)
    hourly, _ = bars.build_all_from_minutes(enriched)
    events = bs.attach_followthrough(bs.classify(hourly), enriched)
    h1_row = events.iloc[1]
    assert h1_row['breakout'] == 'bearish'
    assert h1_row['h2_mae_pct'] == pytest.approx((92 - 90) / 90 * 100, rel=1e-6)
    assert h1_row['h2_mfe_pct'] == pytest.approx((90 - 87) / 90 * 100, rel=1e-6)
```

- [ ] **Step 2: Run the test**

```bash
cd "/Users/abhi/Projects/Statistic.ally/Analysis"
python3 -m pytest tests/test_breakout.py::test_h2_excursion_bearish_basic -v 2>&1 | tail -10
```

Expected: PASS.

### Task 4: Non-breakout NaN test

**Files:**
- Modify: `Analysis/tests/test_breakout.py` (append after the bearish test)

- [ ] **Step 1: Append the test**

```python
def test_h2_excursion_na_for_non_breakouts():
    """Inside bar (breakout='neither') → h2_mae_pct + h2_mfe_pct both NaN.
    Also covers the first row which is 'no_prev'.
    """
    h0 = helpers.make_hour('2024-01-02 09:00', ohlc=(100, 110, 90, 100),
                           high_at_minute=20, low_at_minute=40)
    # H1 inside H0 range entirely
    h1 = helpers.make_hour('2024-01-02 10:00', ohlc=(100, 105, 95, 102),
                           high_at_minute=30, low_at_minute=40)
    h2 = helpers.make_hour('2024-01-02 11:00', ohlc=(102, 108, 98, 104),
                           high_at_minute=10, low_at_minute=40)
    minutes = helpers.concat_hours(h0, h1, h2)
    enriched = bars._enrich_minutes(minutes)
    hourly, _ = bars.build_all_from_minutes(enriched)
    events = bs.attach_followthrough(bs.classify(hourly), enriched)
    # H0 row is 'no_prev' (first row); H1 is 'neither' (inside bar)
    assert events.iloc[0]['breakout'] == 'no_prev'
    assert pd.isna(events.iloc[0]['h2_mae_pct'])
    assert pd.isna(events.iloc[0]['h2_mfe_pct'])
    assert events.iloc[1]['breakout'] == 'neither'
    assert pd.isna(events.iloc[1]['h2_mae_pct'])
    assert pd.isna(events.iloc[1]['h2_mfe_pct'])
```

- [ ] **Step 2: Run the test**

```bash
cd "/Users/abhi/Projects/Statistic.ally/Analysis"
python3 -m pytest tests/test_breakout.py::test_h2_excursion_na_for_non_breakouts -v 2>&1 | tail -10
```

Expected: PASS.

### Task 5: No-H2-minutes returns NaN test

**Files:**
- Modify: `Analysis/tests/test_breakout.py` (append after the previous test)

- [ ] **Step 1: Append the test**

```python
def test_h2_excursion_no_minutes_returns_na():
    """If a breakout's next hour has no minute bars (data gap), both
    excursion columns are NaN — matches followthrough behavior."""
    h0 = helpers.make_hour('2024-01-02 09:00', ohlc=(100, 105, 95, 100),
                           high_at_minute=20, low_at_minute=40)
    # Bullish breakout, but no H2 minutes (we only feed h0 + h1)
    h1 = helpers.make_hour('2024-01-02 10:00', ohlc=(100, 115, 95, 110),
                           high_at_minute=30, low_at_minute=40)
    minutes = helpers.concat_hours(h0, h1)
    enriched = bars._enrich_minutes(minutes)
    hourly, _ = bars.build_all_from_minutes(enriched)
    events = bs.attach_followthrough(bs.classify(hourly), enriched)
    h1_row = events.iloc[1]
    assert h1_row['breakout'] == 'bullish'
    # H2 has no minutes → NaN for everything including new columns
    assert pd.isna(h1_row['h2_mae_pct'])
    assert pd.isna(h1_row['h2_mfe_pct'])
```

- [ ] **Step 2: Run the test**

```bash
cd "/Users/abhi/Projects/Statistic.ally/Analysis"
python3 -m pytest tests/test_breakout.py::test_h2_excursion_no_minutes_returns_na -v 2>&1 | tail -10
```

Expected: PASS.

### Task 6: Run full Analysis test suite, commit

- [ ] **Step 1: Run all Analysis tests**

```bash
cd "/Users/abhi/Projects/Statistic.ally/Analysis"
python3 -m pytest tests/ -q 2>&1 | tail -5
```

Expected: all pass (whatever the current baseline is, +4 new tests).

- [ ] **Step 2: Commit**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
git add "Analysis/engine/breakout_study.py" "Analysis/tests/test_breakout.py"
git commit -m "$(cat <<'EOF'
feat(hourly-analysis): h2_mae_pct + h2_mfe_pct on breakouts.parquet

Adds intrabar MAE/MFE excursion during H2 (the hour after a confirmed
breakout) as two new float columns on every breakout row.

Direction: bullish breakout → long entry at H2 open; bearish → short.
Both values >= 0 by construction (expressed as positive distance from
entry, as % of H2 open price — basis-point-style normalization).

Non-breakout rows ('neither', 'no_prev') and rows with missing H2
minutes get NaN. Computed in the same loop as followthrough — zero
extra data loads.

4 unit tests added: bullish basic, bearish basic, non-breakout NaN,
missing-H2-minutes NaN.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 2 — Integration test + regenerate parquet

### Task 7: Extend the integration test

**Files:**
- Modify: `Analysis/tests/test_integration.py`

- [ ] **Step 1: Find the existing test_run_all_against_recent_slice**

```bash
grep -n "test_run_all_against_recent_slice\|breakouts = pd.read_parquet" /Users/abhi/Projects/Statistic.ally/Analysis/tests/test_integration.py 2>&1 | head -5
```

Note the file location and the existing assertion block that reads `breakouts.parquet`.

- [ ] **Step 2: Add a new test below the existing one**

Append at the end of `Analysis/tests/test_integration.py`:

```python
def test_breakout_parquet_has_h2_excursion_columns(tmp_path, monkeypatch):
    """breakouts.parquet must include h2_mae_pct + h2_mfe_pct columns after
    run_all completes, with non-null values on actual breakout rows and
    all non-null values >= 0."""
    import pandas as pd
    import run_all
    monkeypatch.setenv('ANALYSIS_DATA_ROOT', str(tmp_path / 'data'))
    monkeypatch.setenv('ANALYSIS_START_DATE', '2024-01-01')
    monkeypatch.setenv('ANALYSIS_END_DATE', '2024-03-31')
    run_all.main()
    df = pd.read_parquet(tmp_path / 'data' / 'breakout' / 'breakouts.parquet')
    assert 'h2_mae_pct' in df.columns
    assert 'h2_mfe_pct' in df.columns
    # At least one bullish-breakout row should have non-null excursion
    bull_with_data = df[(df['breakout'] == 'bullish') & df['h2_mae_pct'].notna()]
    assert len(bull_with_data) > 0, "no bullish breakouts had populated h2_mae_pct"
    # All non-null values must be >= 0
    assert (df['h2_mae_pct'].dropna() >= 0).all(), "h2_mae_pct has negative values"
    assert (df['h2_mfe_pct'].dropna() >= 0).all(), "h2_mfe_pct has negative values"
```

- [ ] **Step 3: Run the new test**

```bash
cd "/Users/abhi/Projects/Statistic.ally/Analysis"
python3 -m pytest tests/test_integration.py::test_breakout_parquet_has_h2_excursion_columns -v 2>&1 | tail -10
```

Expected: PASS. If the test errors with `KeyError` on the env vars, look at how `test_run_all_against_recent_slice` (the existing test in the same file) configures `run_all` — adapt the setup pattern to match. If it patches the data root differently (e.g., via a fixture rather than env vars), use that pattern instead.

- [ ] **Step 4: Run full test suite, commit**

```bash
cd "/Users/abhi/Projects/Statistic.ally/Analysis"
python3 -m pytest tests/ -q 2>&1 | tail -5
```

Expected: all pass.

```bash
cd "/Users/abhi/Projects/Statistic.ally"
git add "Analysis/tests/test_integration.py"
git commit -m "$(cat <<'EOF'
test(hourly-analysis): integration test for h2 excursion columns

Asserts breakouts.parquet produced by run_all() has the two new excursion
columns, at least one bullish breakout has non-null values, and all
non-null values are >= 0 (excursion is positive distance by construction).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 8: Regenerate breakouts.parquet locally

The dashboard reads from `Analysis/data/breakout/breakouts.parquet`. The dashboard work in Phase 3 requires that file to have the new columns. The file is gitignored so it stays local.

- [ ] **Step 1: Re-run the engine**

```bash
cd "/Users/abhi/Projects/Statistic.ally/Analysis"
python3 engine/run_all.py 2>&1 | tail -20
```

Expected: completes without errors. Should print study progress lines and end with manifest stats.

- [ ] **Step 2: Verify new columns landed**

```bash
python3 -c "
import pyarrow.parquet as pq
t = pq.read_table('/Users/abhi/Projects/Statistic.ally/Analysis/data/breakout/breakouts.parquet')
cols = t.column_names
print('total rows:', t.num_rows)
print('total cols:', len(cols))
print('h2_mae_pct present:', 'h2_mae_pct' in cols)
print('h2_mfe_pct present:', 'h2_mfe_pct' in cols)
"
```

Expected:
```
total rows: ~59000+ (close to current 59677)
total cols: 21
h2_mae_pct present: True
h2_mfe_pct present: True
```

- [ ] **Step 3: Verify values are sane**

```bash
python3 -c "
import pyarrow.parquet as pq
df = pq.read_table('/Users/abhi/Projects/Statistic.ally/Analysis/data/breakout/breakouts.parquet').to_pandas()
bull = df[df['breakout'] == 'bullish']
print(f'bullish breakouts: {len(bull)}')
print(f'  h2_mae_pct: avg={bull[\"h2_mae_pct\"].mean():.4f}% median={bull[\"h2_mae_pct\"].median():.4f}%')
print(f'  h2_mfe_pct: avg={bull[\"h2_mfe_pct\"].mean():.4f}% median={bull[\"h2_mfe_pct\"].median():.4f}%')
bear = df[df['breakout'] == 'bearish']
print(f'bearish breakouts: {len(bear)}')
print(f'  h2_mae_pct: avg={bear[\"h2_mae_pct\"].mean():.4f}% median={bear[\"h2_mae_pct\"].median():.4f}%')
print(f'  h2_mfe_pct: avg={bear[\"h2_mfe_pct\"].mean():.4f}% median={bear[\"h2_mfe_pct\"].median():.4f}%')
print(f'all non-null >= 0: {(df[\"h2_mae_pct\"].dropna() >= 0).all() and (df[\"h2_mfe_pct\"].dropna() >= 0).all()}')
"
```

Expected: all 4 averages between roughly 0.05% and 1.5% (typical NQ intrabar excursion magnitudes); `all non-null >= 0: True`.

If any check fails, STOP and report — the engine output is wrong.

(No commit — `breakouts.parquet` is gitignored.)

---

## Phase 3 — Dashboard panel

### Task 9: Add the empty panel DOM node

**Files:**
- Modify: `Analysis/dashboard/index.html` (insert into `pane-breakout` div)

- [ ] **Step 1: Locate the end of pane-breakout**

```bash
grep -n "breakout-prevmid\|pane-quarters" /Users/abhi/Projects/Statistic.ally/Analysis/dashboard/index.html 2>&1 | head -3
```

The `<div id="breakout-prevmid">` line marks where the last existing panel is. The next non-blank tag will be the closing of the section containing it, followed by `</div>` for `pane-breakout`.

- [ ] **Step 2: Add the new panel block**

Find this block in `Analysis/dashboard/index.html` (around line 295-298):

```html
        <div id="breakout-prevmid"><div class="loading">Loading…</div></div>
```

Inside `pane-breakout`, AFTER the existing section that contains `breakout-prevmid`, add a new section. The exact insertion point: find `<div id="breakout-prevmid">...</div>`, look for the closing `</section>` (or container `</div>`) that wraps the section it's in, and ADD this immediately after:

```html
      <section class="card">
        <h3 class="card-title">Excursion by Hour-of-Day (H2 window)</h3>
        <p class="card-subtitle">MAE / MFE for an implied breakout trade entered at H2 open, exited at H2 close. Values are % of entry price.</p>
        <div id="breakout-excursion-by-hour" class="excursion-layout">
          <div id="breakout-excursion-table" class="excursion-table"><div class="loading">Loading…</div></div>
          <div id="breakout-excursion-chart" class="excursion-chart"><canvas id="breakout-excursion-canvas"></canvas></div>
        </div>
      </section>
```

If the existing panels don't use `<section class="card">`, use whatever container pattern they DO use — match the surrounding code exactly. The point is one new container with two children (table div + chart canvas).

- [ ] **Step 3: Add minimal CSS for the layout (also inside index.html)**

Find the `<style>` block (search for the first `<style>` tag) and add at the bottom of it:

```css
.excursion-layout {
  display: grid;
  grid-template-columns: minmax(280px, 40%) 1fr;
  gap: 16px;
  align-items: start;
}
@media (max-width: 900px) {
  .excursion-layout { grid-template-columns: 1fr; }
}
.excursion-table table { width: 100%; border-collapse: collapse; font-size: 11px; }
.excursion-table th, .excursion-table td { padding: 4px 6px; border-bottom: 1px solid var(--border-mid, #2a2a2a); }
.excursion-table th { text-align: left; font-weight: 600; color: var(--text-muted, #999); text-transform: uppercase; font-size: 10px; }
.excursion-table td.num { text-align: right; font-variant-numeric: tabular-nums; }
.excursion-table td.mae { color: var(--red, #ef4444); }
.excursion-table td.mfe { color: var(--green, #22c55e); }
.excursion-chart { min-height: 240px; position: relative; }
.excursion-chart canvas { max-width: 100%; }
```

- [ ] **Step 4: Smoke-test that the page loads without breaking**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
python3 server.py &
SERVER_PID=$!
sleep 1
curl -s -o /dev/null -w "HTTP %{http_code}\n" "http://localhost:8001/Analysis/dashboard/index.html"
kill $SERVER_PID 2>/dev/null
wait $SERVER_PID 2>/dev/null
```

Expected: `HTTP 200`. The new panel will show "Loading…" forever since no render function exists yet — that's expected.

- [ ] **Step 5: Commit**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
git add "Analysis/dashboard/index.html"
git commit -m "$(cat <<'EOF'
feat(hourly-analysis): scaffold "Excursion by Hour-of-Day" panel

Adds an empty container + table + chart canvas inside pane-breakout,
plus minimal CSS for the side-by-side layout. Render function lands in
the next commit. Panel currently shows "Loading…" — not wired yet.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 10: Implement the render function

**Files:**
- Modify: `Analysis/dashboard/index.html` (add `renderBreakoutExcursionByHour` function + call from `renderBreakout`)

- [ ] **Step 1: Add the render function**

Find the existing `async function renderBreakout()` block (around line 539-606). Immediately AFTER its closing `}`, ADD this new function:

```javascript
async function renderBreakoutExcursionByHour() {
  const tableEl = document.getElementById('breakout-excursion-table');
  const canvasEl = document.getElementById('breakout-excursion-canvas');
  if (!tableEl || !canvasEl) return;

  // Same filter scope as the rest of the breakout tab.
  const where = buildBreakoutWhere(true);
  const havingClause = STATE.minCount > 0 ? `HAVING n >= ${STATE.minCount}` : '';

  let rows;
  try {
    rows = await window.query(`
      SELECT
        hour_of_day_et,
        breakout,
        COUNT(*) AS n,
        AVG(h2_mae_pct)  AS avg_mae_pct,
        AVG(h2_mfe_pct)  AS avg_mfe_pct,
        quantile_cont(h2_mfe_pct, 0.9)  AS p90_mfe_pct,
        quantile_cont(h2_mae_pct, 0.9)  AS p90_mae_pct
      FROM br
      ${where ? where + ' AND' : 'WHERE'} breakout IN ('bullish', 'bearish')
        AND h2_mae_pct IS NOT NULL
        AND h2_mfe_pct IS NOT NULL
      GROUP BY hour_of_day_et, breakout
      ${havingClause}
      ORDER BY hour_of_day_et, breakout
    `);
  } catch (e) {
    tableEl.innerHTML = `<div style="color:var(--text-muted);font-size:12px;padding:12px">
      Re-run <code>python3 Analysis/engine/run_all.py</code> to generate excursion data.
    </div>`;
    return;
  }

  if (!rows || rows.length === 0) {
    tableEl.innerHTML = `<div style="color:var(--text-muted);font-size:12px;padding:12px">
      No breakouts match the current filters.
    </div>`;
    return;
  }

  // ── Render table ────────────────────────────────────────────────────────
  const dirArrow = (d) => d === 'bullish' ? '↑ Bull' : '↓ Bear';
  const fmt = (v) => v == null ? '—' : (+v).toFixed(2) + '%';
  tableEl.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>Hour ET</th>
          <th>Dir</th>
          <th class="num">N</th>
          <th class="num">Avg MAE</th>
          <th class="num">P90 MAE</th>
          <th class="num">Avg MFE</th>
          <th class="num">P90 MFE</th>
        </tr>
      </thead>
      <tbody>
        ${rows.map(r => `
          <tr>
            <td>${r.hour_of_day_et}</td>
            <td>${dirArrow(r.breakout)}</td>
            <td class="num">${fmtN(+r.n)}</td>
            <td class="num mae">${fmt(r.avg_mae_pct)}</td>
            <td class="num mae">${fmt(r.p90_mae_pct)}</td>
            <td class="num mfe">${fmt(r.avg_mfe_pct)}</td>
            <td class="num mfe">${fmt(r.p90_mfe_pct)}</td>
          </tr>`).join('')}
      </tbody>
    </table>`;

  // ── Render chart (grouped bars: bullish MFE/MAE per hour) ───────────────
  const hours = [...new Set(rows.map(r => +r.hour_of_day_et))].sort((a, b) => a - b);
  const bullByHour = new Map(rows.filter(r => r.breakout === 'bullish').map(r => [+r.hour_of_day_et, r]));
  const bearByHour = new Map(rows.filter(r => r.breakout === 'bearish').map(r => [+r.hour_of_day_et, r]));

  // Destroy any existing chart instance to avoid Chart.js "Canvas is already in use" errors on re-render.
  if (canvasEl._chart) { canvasEl._chart.destroy(); canvasEl._chart = null; }

  canvasEl._chart = new Chart(canvasEl.getContext('2d'), {
    type: 'bar',
    data: {
      labels: hours.map(h => `${h}:00`),
      datasets: [
        {
          label: 'Bull MFE (avg)',
          data: hours.map(h => bullByHour.get(h)?.avg_mfe_pct ?? null),
          backgroundColor: 'rgba(34,197,94,0.8)',
        },
        {
          label: 'Bull MAE (avg)',
          data: hours.map(h => bullByHour.get(h)?.avg_mae_pct ?? null),
          backgroundColor: 'rgba(239,68,68,0.8)',
        },
        {
          label: 'Bear MFE (avg)',
          data: hours.map(h => bearByHour.get(h)?.avg_mfe_pct ?? null),
          backgroundColor: 'rgba(34,197,94,0.4)',
        },
        {
          label: 'Bear MAE (avg)',
          data: hours.map(h => bearByHour.get(h)?.avg_mae_pct ?? null),
          backgroundColor: 'rgba(239,68,68,0.4)',
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: { title: { display: true, text: 'Hour of Day (ET)' } },
        y: { title: { display: true, text: '% of H2 open' }, beginAtZero: true,
             ticks: { callback: (v) => v.toFixed(2) + '%' } },
      },
      plugins: {
        legend: { position: 'top', labels: { font: { size: 11 } } },
        tooltip: { callbacks: { label: (ctx) => `${ctx.dataset.label}: ${(+ctx.parsed.y).toFixed(2)}%` } },
      },
    },
  });
}
```

- [ ] **Step 2: Call the new render function from renderBreakout**

In the SAME file, find the existing `async function renderBreakout()` body. At the very END of that function (right before its closing `}`), add:

```javascript
  await renderBreakoutExcursionByHour();
```

So the structure becomes:

```javascript
async function renderBreakout() {
  // ... all existing code ...
  document.getElementById('breakout-prevmid').innerHTML = `...`;

  await renderBreakoutExcursionByHour();   // ← NEW
}
```

- [ ] **Step 3: Verify the file still parses as valid HTML/JS**

```bash
node --check <(awk '/<script>/,/<\/script>/' /Users/abhi/Projects/Statistic.ally/Analysis/dashboard/index.html | sed 's/<script>//;s/<\/script>//') 2>&1 | head -5
```

If `node --check` errors with a SyntaxError, STOP and fix the JS — don't proceed.

If `node --check` works cleanly (no output), continue.

- [ ] **Step 4: Manual browser check — REQUIRED**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
python3 server.py &
SERVER_PID=$!
sleep 1
echo "Open http://localhost:8001/Analysis/dashboard/index.html in your browser"
echo "Click the 'Breakout' tab in the top nav"
echo "Scroll to the bottom of the Breakout tab"
echo ""
echo "VERIFY:"
echo "1. New 'Excursion by Hour-of-Day (H2 window)' panel is visible"
echo "2. Table populates with rows showing hours, directions (Bull/Bear), N, Avg/P90 MAE, Avg/P90 MFE"
echo "3. All percentages render as positive numbers with '%' suffix (typical 0.05% - 1.50% range)"
echo "4. Chart shows grouped bars per hour with 4 series (Bull/Bear × MAE/MFE)"
echo "5. DevTools Console clean (no SQL errors or undefined Chart errors)"
echo "6. Apply year filter (e.g. '2024') in sidebar → panel updates"
echo "7. Apply direction filter to 'bullish' only → table collapses to bullish rows only"
echo ""
echo "Press Enter when verified..."
read
kill $SERVER_PID 2>/dev/null
wait $SERVER_PID 2>/dev/null
```

If anything fails the visual check, STOP and report what you saw.

- [ ] **Step 5: Commit**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
git add "Analysis/dashboard/index.html"
git commit -m "$(cat <<'EOF'
feat(hourly-analysis): wire Excursion by Hour-of-Day panel

Adds renderBreakoutExcursionByHour() that aggregates h2_mae_pct /
h2_mfe_pct from breakouts.parquet (DuckDB-WASM SQL) and renders:

- Table: hour of day × direction × N + Avg/P90 MAE + Avg/P90 MFE
- Chart: grouped bars per hour (Chart.js), 4 series (Bull/Bear × MFE/MAE)

Honors the existing breakout sidebar filters (year, hour-of-day,
DOW, direction, min count). If parquet is older and missing the new
columns, shows a "re-run engine" message instead of a SQL error.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 4 — Final verification

### Task 11: Full test suite + final smoke

- [ ] **Step 1: Full Analysis pytest run**

```bash
cd "/Users/abhi/Projects/Statistic.ally/Analysis"
python3 -m pytest tests/ -q 2>&1 | tail -5
```

Expected: all pass.

- [ ] **Step 2: Run full repo pytest (sanity — should be unchanged by Analysis work)**

```bash
cd "/Users/abhi/Projects/Statistic.ally"
python3 -m pytest "Fractal Sweep/tests" Analysis/tests "NPG Sweep/tests" 2>&1 | tail -5
```

Expected: no regressions in any project.

- [ ] **Step 3: Final dashboard smoke + commit log review**

```bash
git -C /Users/abhi/Projects/Statistic.ally log --oneline main..HEAD 2>&1
```

Expected: 5 commits on `hourly-breakout-excursion`:
1. `docs: spec for Hourly Analysis H2 MAE/MFE excursion by hour-of-day`
2. `feat(hourly-analysis): h2_mae_pct + h2_mfe_pct on breakouts.parquet`
3. `test(hourly-analysis): integration test for h2 excursion columns`
4. `feat(hourly-analysis): scaffold "Excursion by Hour-of-Day" panel`
5. `feat(hourly-analysis): wire Excursion by Hour-of-Day panel`

If the count or order is wrong, STOP and report what's actually there.

- [ ] **Step 4: Hand off to finishing-a-development-branch**

Branch is ready to merge or PR. Stop here; the orchestrator will invoke the next skill.

---

## Self-Review

**Spec coverage:**
- [x] Engine writes `h2_mae_pct` + `h2_mfe_pct` columns — Task 2.
- [x] Direction = bullish→long, bearish→short — Task 2 code block.
- [x] Entry = H2 open, exit = H2 close, both ≥ 0 — Task 2.
- [x] Non-breakout rows get NaN — Task 2 + Task 4 test.
- [x] H2-missing-minutes get NaN — Task 2 + Task 5 test.
- [x] H2 open = 0 guard — Task 2.
- [x] Unit tests for bullish + bearish + NaN cases — Tasks 1, 3, 4, 5.
- [x] Integration test for parquet column presence — Task 7.
- [x] Dashboard panel inside `pane-breakout` — Task 9.
- [x] Table + chart layout — Task 10.
- [x] DuckDB-WASM SQL on `br` alias — Task 10.
- [x] Filter awareness via `buildBreakoutWhere` + `STATE.minCount` — Task 10.
- [x] Old-parquet fallback message — Task 10 try/catch.
- [x] Empty-result fallback message — Task 10 length check.
- [x] Manual browser verification step — Task 10 Step 4.

**Placeholder scan:** None.

**Type consistency:** Column names `h2_mae_pct` / `h2_mfe_pct` used identically across engine (Task 2), tests (Tasks 1, 3, 4, 5, 7), and dashboard SQL (Task 10). Chart canvas id `breakout-excursion-canvas` used identically in HTML (Task 9) and JS (Task 10). Panel ids `breakout-excursion-table` and `breakout-excursion-chart` likewise consistent.

Plan is ready.
