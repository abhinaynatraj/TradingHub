# NPG Sweep — Phase 2 Design

**Date:** 2026-05-03
**Predecessor:** [Phase 1 plan](../plans/2026-05-02-npg-sweep-engine-phase1.md) — engine + statistical study, complete and merged to main as of 2026-05-02
**Predecessor findings:** [npg_engine_findings.md](../../../NPG%20Sweep/docs/npg_engine_findings.md)

## Goal

Make the NPG Sweep engine's results interactively explorable in a web dashboard, and verify the Phase 1 finding that Silver is a load-bearing filter (no Fractal Sweep analog) by back-porting it to the Fractal Sweep engine.

## Scope

Four deliverables, in approximate dependency order:

1. **Engine output cleanup** — drop unused `_trades` fields, add `entry_ts_ns`, regenerate `npg_stats.json` (~16 MB → ~8 MB)
2. **NPG dashboard** — hand-written single-file HTML, vanilla SVG charts, ~1,500 LOC ceiling
3. **Hub integration** — add NPG card to `Statistic.ally/index.html`
4. **Silver back-port to Fractal Sweep** — port `is_silver` + `candle_of_day` to the FS engine, add chip to FS dashboard

Out of scope (deferred to Phase 3): key-level confluence filter (PDH/PDL/Asia/RTH overlap), MTF FVG flags, cross-model overlap analysis (NPG ∩ Fractal Sweep), walk-forward / regime analysis, RTH-only filter.

---

## Architecture

### Data flow

```
1m bars (DuckDB)
   │
   ▼
engine/npg_stats.py   ──→   npg_stats.json  (~8 MB after field strip)
                                 │
                                 ▼
                        npg_dashboard.html
                          • fetch() once on load
                          • hold _trades arrays in memory per pairing
                          • re-aggregate on every chip change (client-side)
                          • render via vanilla SVG
```

The dashboard is a pure consumer of `npg_stats.json`. All math (`agg`, `reach_rates`, `by_hour`, etc.) is reimplemented in JS, mirroring [engine/aggregation.py](../../../NPG%20Sweep/engine/aggregation.py) exactly so dashboard numbers match a fresh engine run.

### File boundaries

```
NPG Sweep/
├── npg_dashboard.html               (NEW — ~1,500 LOC ceiling)
├── npg_stats.json                   (regenerated, smaller)
├── engine/
│   └── npg_stats.py                 (modify: trim trade fields, add entry_ts_ns)
└── tests/
    └── test_orchestrator_output.py  (NEW — verify trade row shape post-cleanup)

Fractal Sweep/
├── engine/
│   ├── model_stats.py               (modify: import is_silver, add silver flag to rows)
│   └── filters_silver.py            (NEW — local copy of Silver logic; do not import across roots)
├── tests/
│   └── test_silver.py               (NEW — mirror of NPG silver tests against FS module)
└── model_dashboard.html             (modify: add Silver chip alongside F3/F4/SMT)

index.html                            (modify: add 3rd model card)
```

**Why a local copy of Silver instead of importing across folders:** the two engines are intentionally independent (different DBs, different schemas, different deploy story). Cross-folder imports create a coupling the repo doesn't want. The Silver function is ~25 lines — a copy is cheaper than the coupling.

### Dashboard architecture

Hand-written single-file HTML, modeled after [Fractal Sweep/model_dashboard.html](../../../Fractal%20Sweep/model_dashboard.html) for visual consistency but built fresh (not forked).

**Hard ceiling: 1,500 LOC.** If it grows past that during implementation, stop and ask why — likely means scope is creeping.

**No CDN dependencies.** All styling is inline `<style>`. All charting is vanilla SVG (~100 LOC for what we need). All JS is inline `<script>`.

**Theme integration:** Inherit `localStorage.getItem('hub-theme')` per repo CLAUDE.md hard rule. Never write a per-page theme key.

**CSS reuse strategy:** Copy the CSS variable definitions (the `--bg`, `--green`, `--font-data`, etc. tokens at the top of `model_dashboard.html`) verbatim into NPG dashboard's `<style>`. Don't share a stylesheet file — both dashboards are standalone.

### State model

```js
// Loaded once on page load, never mutated:
const DATA = await fetch('npg_stats.json').then(r => r.json());
// Shape: { '1H_5M/series_multi': { _trades: [...], n_trades, agg, ... }, ... }

// Filter state, mutated by chip clicks:
const FILTERS = {
  silver: 'all' | 'on' | 'off',
  smt:    'all' | 'on' | 'off',
  direction: 'all' | 'LONG' | 'SHORT',
  session:   'all' | 'ASIA' | 'LONDON' | 'NY' | 'OTHER',
};

// Active tab:
let ACTIVE_TAB = 'compare' | '1H_5M' | '4H_15M' | 'D_1H';

// Active profile (toggle, not chip — defaults to series_multi):
let ACTIVE_PROFILE = 'series_multi' | 'raw_measure';
```

On every chip change OR tab switch:
1. Apply filter mask to `DATA[pairing][ACTIVE_PROFILE]._trades` for each visible pairing
2. Recompute `agg`, `reach_rates`, and (per-pairing tab only) `by_hour` / `by_dow` / `by_session` / `by_direction`
3. Re-render visible panels

For the equity curve, sort filtered trades by `entry_ts_ns` and accumulate `composite_r`. With ~15k trades on 1H_5M and re-aggregation at 60fps target, this is well within budget — no throttling needed.

---

## Components

### 1. Engine cleanup (deliverable 1)

**File:** [engine/npg_stats.py](../../../NPG%20Sweep/engine/npg_stats.py) — modify the `trades.append(dict(...))` block in `run_pairing`.

**Drop these fields:**
- `targets` (list, computed client-side from `series_range` and break_price if needed; not needed for any current dashboard view)
- `hit_ts_ns` (per-target hit times; only `hits` boolean array needed)
- `sweep_ts_ns` (already have `entry_ts_ns` for ordering)
- `risk_pts` (= `|entry_price - sl_price|`, derive client-side if needed)
- `body_cisd` (constant per run; redundant)
- `series_count` (no current view needs it)

**Keep:** `direction`, `composite_r`, `hits`, `silver`, `smt`, `hour`, `dow`, `mae_pts`, `mfe_pts`, `entry_price`, `sl_price`, `series_range`, `sweep_extreme`, `sl_hit`.

**Add:** `entry_ts_ns` (= `int(cisd_tf['ts_ns'][entry_idx_cisd_tf])`). Needed for equity curve sort.

**JSON shape unchanged otherwise.** Top-level keys (`<pairing>/<profile>` → `{n_trades, agg, reach_rates, by_hour, by_dow, by_session, by_direction, filter_combinations, _trades}`) all preserved.

**Acceptance:** `npg_stats.json` size drops from 16 MB to ≤ 9 MB. All 42 existing tests still pass. New test `test_orchestrator_output.py` asserts trade row keys match the new contract.

### 2. NPG Dashboard (deliverable 2)

**File:** `Statistic.ally/NPG Sweep/npg_dashboard.html` (NEW)

#### Layout

```
┌──────────────────────────────────────────────────────────────────────┐
│  NPG Sweep · Probability Engine          [☀/🌙]                      │
├──────────────────────────────────────────────────────────────────────┤
│  Profile: [series_multi ▾]  Silver: [All|On|Off]                    │
│           SMT: [All|On|Off]  Direction: [All|Long|Short]            │
│           Session: [All|Asia|London|NY|Other]                       │
├──────────────────────────────────────────────────────────────────────┤
│  [ Compare ]  1H_5M   4H_15M   D_1H                                  │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   ┌──── 1H_5M ────┐  ┌──── 4H_15M ────┐  ┌──── D_1H ────┐         │
│   │ N    15,148   │  │ N    4,077      │  │ N    668      │         │
│   │ WR   85.9%    │  │ WR   88.6%      │  │ WR   90.7%    │         │
│   │ EV  +0.182R   │  │ EV  +0.225R     │  │ EV  +0.311R   │         │
│   │ PF   2.25     │  │ PF   2.89       │  │ PF   6.72     │         │
│   │               │  │                 │  │               │         │
│   │ Reach rates   │  │ Reach rates     │  │ Reach rates   │         │
│   │ ▓▓▓▓▓ 0.5x    │  │ ▓▓▓▓▓ 0.5x      │  │ ▓▓▓▓▓ 0.5x    │         │
│   │ ▓▓▓▓  1.0x    │  │ ▓▓▓▓  1.0x      │  │ ▓▓▓▓▓ 1.0x    │         │
│   │ ▓▓▓   1.5x    │  │ ▓▓▓   1.5x      │  │ ▓▓▓▓  1.5x    │         │
│   │ ▓▓▓   2.0x    │  │ ▓▓▓   2.0x      │  │ ▓▓▓▓  2.0x    │         │
│   │               │  │                 │  │               │         │
│   │ Equity curve  │  │ Equity curve    │  │ Equity curve  │         │
│   │   ╱╱╱╱╱╱      │  │   ╱╱╱╱╱╱        │  │   ╱╱╱╱╱╱      │         │
│   └───────────────┘  └─────────────────┘  └───────────────┘         │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

#### Compare tab (default view)

Three pairing panels side-by-side, each showing:
- **Metric cards** (4 stats): N, WR, EV (R), PF
- **Reach-rate bar chart** (4 bars): 0.5×, 1.0×, 1.5×, 2.0× as horizontal bars with % labels
- **Equity curve** (line): cumulative `composite_r` from oldest to newest filtered trade. Y-axis = R, X-axis = trade index (not time). Includes a horizontal zero-line and final-value annotation.

Filter chips at top affect all three panels simultaneously.

#### Per-pairing tabs (1H_5M / 4H_15M / D_1H)

Same metric cards + reach-rate bars + equity curve as in Compare, but for ONE pairing only and full-width. Below those, four breakdown tables:

- **By hour** (24 rows): hour 0–23 with N / WR% / EV. Heatmap shading on EV column (red→white→green).
- **By DOW** (5 rows, Mon–Fri): N / WR% / EV.
- **By session** (4 rows, ASIA/LONDON/NY/OTHER): N / WR% / EV.
- **By direction** (2 rows, LONG/SHORT): N / WR% / EV.

#### Filter chips

Profile selector: `series_multi` (default) | `raw_measure`. When `raw_measure` is selected:
- EV and PF are hidden from metric cards (always 0/0 by design)
- WR shows reach-1.0× rate
- Reach-rate bars and breakdown tables still render
- Equity curve hidden (composite_r = 0 for all)

Silver chip: `All` | `On` | `Off`. `On` filters to `silver === true`; `Off` to `silver === false`; `All` no-op.

SMT chip: same pattern.

Direction chip: `All` | `Long` | `Short`. Filters on `direction === 'LONG' | 'SHORT'`.

Session chip: `All` | `Asia` | `London` | `NY` | `Other`. Buckets via `hour` field client-side using same logic as `aggregation.py`:

```
ASIA   = hour ≥ 18 OR hour < 2
LONDON = hour 2..7
NY     = hour 8..15
OTHER  = hour 16..17
```

All chip changes recompute aggregations live. No "Apply" button.

#### Aggregation math (JS, mirrors `engine/aggregation.py`)

```js
const WIN_LEVEL_IDX = 1;          // 1.0× projection
const LEVEL_LABELS = ['0.5x', '1.0x', '1.5x', '2.0x'];

function agg(rows) {
  const n = rows.length;
  if (n === 0) return { n: 0, wins: 0, wr: 0, ev: 0, pf: 0, avg_mae: 0, avg_mfe: 0 };
  const wins = rows.filter(r => r.hits[WIN_LEVEL_IDX]).length;
  const rs = rows.map(r => r.composite_r);
  const ev = rs.reduce((a, b) => a + b, 0) / n;
  const pos = rs.filter(r => r > 0).reduce((a, b) => a + b, 0);
  const neg = rs.filter(r => r < 0).reduce((a, b) => a + b, 0);
  const pf = neg < 0 ? pos / Math.abs(neg) : 0;
  return {
    n,
    wins,
    wr: 100 * wins / n,
    ev,
    pf,
    avg_mae: rows.reduce((a, r) => a + r.mae_pts, 0) / n,
    avg_mfe: rows.reduce((a, r) => a + r.mfe_pts, 0) / n,
  };
}

function reachRates(rows) {
  const n = rows.length;
  if (n === 0) return { '0.5x': 0, '1.0x': 0, '1.5x': 0, '2.0x': 0 };
  const out = {};
  LEVEL_LABELS.forEach((label, k) => {
    out[label] = 100 * rows.filter(r => r.hits[k]).length / n;
  });
  return out;
}
```

Test parity: pick one pairing × filter combo, compute agg in both Python and JS, assert numbers match to 4 decimals. Done as a manual smoke check, not an automated test (would require running JS in a test harness — not worth the setup for Phase 2).

#### SVG charting

**Reach-rate bars:** horizontal bar chart, 4 bars, fixed width pixels. Each bar is `<rect>` with `width = (rate / 100) * MAX_WIDTH`. Label on the right with the percentage. ~30 LOC.

**Equity curve:** line chart, polyline of `(idx, cumulative_r)` points scaled to a fixed viewBox. Y-axis: 5 gridlines + zero-line in a contrasting color. Final-value text annotation top-right. ~80 LOC.

**Heatmap shading on EV column:** background color of each `<td>` interpolated red→white→green based on EV value. Range clamped at ±0.5R for color saturation. ~15 LOC of color math.

#### Tab navigation

Plain `<button>` elements with `data-tab` attrs. Click handler updates `ACTIVE_TAB`, calls `render()`. No URL hash routing in Phase 2 (could add in Phase 3 if requested).

#### Acceptance

- All 4 chips work: changing any chip updates all visible panels within 200ms
- Tab switches preserve filter state
- Compare tab renders 3 side-by-side panels at viewport width ≥ 1200px; stacks vertically below
- Per-pairing tabs render the 4 breakdown tables with heatmap shading
- Theme toggle switches between dark/light using shared `localStorage hub-theme` key
- Total file size ≤ 1,500 LOC (hard ceiling)
- Loads `npg_stats.json` once and never re-fetches

### 3. Hub integration (deliverable 3)

**File:** [index.html](../../../index.html) — modify the model card section starting around line 657.

Add a new card object alongside the existing Fractal Sweep + Amas Models entries:

```js
{
  title:    'NPG Sweep',
  subtitle: 'Wick Lick + CISD',
  desc:     'Statistical engine for the npg "Sweep · CISD · FVG · Key Levels" model. 3 HTF/LTF pairings, 4-leg partial-exit profile, Silver late-week timing filter. Companion to Fractal Sweep — same data, different model spec.',
  json:     'NPG Sweep/npg_stats.json',
  link:     'NPG Sweep/npg_dashboard.html',
}
```

Exact field names match what's in the existing entries (verify when implementing — `index.html` line 761+).

#### Acceptance

- Hub homepage shows three model cards (FS, NPG, Amas)
- Clicking the NPG card opens `NPG Sweep/npg_dashboard.html`
- The card's stats (if hub displays any from JSON) read from `NPG Sweep/npg_stats.json`

### 4. Silver back-port to Fractal Sweep (deliverable 4)

**Files:**
- `Fractal Sweep/engine/filters_silver.py` (NEW) — local copy of `is_silver` and `candle_of_day` from NPG, with the same signatures and behavior
- `Fractal Sweep/engine/model_stats.py` (modify) — import `is_silver`, compute Silver flag per trade row, add to JSON output
- `Fractal Sweep/tests/test_silver.py` (NEW) — mirror of NPG silver tests, importing from `filters_silver`
- `Fractal Sweep/model_dashboard.html` (modify) — add Silver chip alongside F3/F4/SMT in the filter chip bar

#### Engine changes

In `model_stats.py`, in the trade-row construction block:

```python
from filters_silver import is_silver

# Compute prev / prev_prev highs/lows from sweep_tf (same approach as NPG):
if anchor_idx >= 2:
    prev_high = float(sweep_tf['high'][anchor_idx - 1])
    prev_low = float(sweep_tf['low'][anchor_idx - 1])
    prev_prev_high = float(sweep_tf['high'][anchor_idx - 2])
    prev_prev_low = float(sweep_tf['low'][anchor_idx - 2])
    hour_et = _hour_of_day_et(sweep_tf['ts_ns'][anchor_idx])
    silver_flag = is_silver(
        direction, hour_et, float(sweep_tf['close'][anchor_idx]),
        prev_low, prev_prev_low, prev_high, prev_prev_high,
    )
else:
    silver_flag = False

trade_row['silver'] = silver_flag
```

The FS engine doesn't currently track `prev_prev` fields but does have access to `sweep_tf` arrays — same data NPG used. Map the variable names to whatever FS calls them.

#### Filter combination enumeration

FS already enumerates `2^k` filter combinations (currently F3, F4, SMT → 8 combos). Adding Silver makes it `2^4 = 16`. The existing `compute_filter_variants` helper takes a filter list — pass `['F3', 'F4', 'SMT', 'silver']`.

#### Dashboard changes

Find the filter chip bar in `model_dashboard.html` (currently has F3, F4, SMT chips). Add a Silver chip with the same styling. Wire it into the `RuntimeFilters` state object that drives client-side recomputation.

#### Acceptance

- FS engine outputs `silver: bool` on every trade row
- 16 filter combinations enumerated in `model_stats.json`
- FS dashboard shows Silver chip; toggling it recomputes stats live
- Findings doc updated with marginal-edge measurement: "On 1H_5M with F3+F4+SMT baseline, adding Silver lifts EV from X to Y at N=Z."

#### Pass/fail criterion

Silver passes if it adds ≥ +1% WR or ≥ +0.05R EV alongside `F3+F4+SMT` (the standard FS marginal-edge gate per [Fractal Sweep/CLAUDE.md](../../../Fractal%20Sweep/CLAUDE.md)). If it doesn't, it stays in the engine + dashboard for completeness but is documented as "noise filter — kept for symmetry with NPG, no marginal edge."

---

## Testing strategy

- **Engine cleanup:** new `tests/test_orchestrator_output.py` asserts the trade dict has the exact set of expected keys (no extras, no missing). Run full pytest suite to confirm no regression.
- **Dashboard:** no automated tests (would require headless browser harness). Manual smoke check: open in browser, verify (a) all chips toggle, (b) tab switches preserve filters, (c) numbers match the JSON for at least one combo, (d) theme inherits from hub correctly.
- **Silver back-port:** `tests/test_silver.py` mirrors NPG's Silver tests. Run FS test suite to confirm no regression. After re-running engine, verify `silver_flag` distribution looks reasonable (~3-5% of trades, matching NPG).

---

## Risks

1. **Dashboard LOC creep.** SVG charting + 4 breakdown tables + 4 chips × tab persistence = real complexity. The 1,500 LOC ceiling is tight. Mitigation: dispatch a fresh subagent per major section (chip bar, charts, tables, tab nav) so each can be reviewed independently and pruned aggressively.

2. **Field-strip regression.** Removing fields from `_trades` might break a downstream script we forgot. Mitigation: grep the repo for each removed field name before deleting it. Likely safe given `_trades` was only added in Phase 1 and isn't referenced outside `npg_stats.py`.

3. **Silver back-port find no edge.** Phase 1 finding suggests Silver is strong, but it's possible the FS CISD definition (single-bar engulf) interacts differently with late-week timing than NPG's. Result is still useful — confirms the finding is NPG-specific, not universal. No design change needed; just document the result accurately.

4. **JSON load size on slow connections.** 8 MB is fine on local file:// and on a fast LAN, but if Phase 3 ever ships this to a remote URL, the loading UX needs work (progress indicator, perhaps split JSON). Out of scope for Phase 2.

5. **Re-aggregation perf on `1H_5M` with all chips active.** 15,148 trades × 4 filter predicates × per-row hit checks for reach rates × cumulative sum for equity curve = ~80k ops per re-render. Well under 16ms budget on modern hardware. Validate on smoke test.

---

## Self-review

**Placeholder scan:** none — all sections have concrete content, file paths, and acceptance criteria.

**Internal consistency:** The dashboard reads `_trades` arrays; engine cleanup keeps `_trades` but trims fields. The fields kept (`direction`, `composite_r`, `hits`, `silver`, `smt`, `hour`, `dow`, `mae_pts`, `mfe_pts`, `entry_ts_ns`) cover everything the dashboard's aggregation + visualization needs. Cross-checked.

**Scope check:** Four deliverables, each independently shippable. The Silver back-port is the only one that touches the FS folder; the other three are NPG-only. Could be split into two plans (NPG dashboard + FS Silver port) but they share enough motivation (verify Phase 1 finding) that one plan is fine.

**Ambiguity check:** "Profile selector" — clarified as a dropdown, not a chip, defaulting to `series_multi`. "Heatmap shading" — clarified to clamp at ±0.5R for color saturation. "No URL hash routing" — explicit out-of-scope note. "Silver pass/fail criterion" — explicit threshold.
