# Doctrine Validation Features — Design Spec

**Date:** 2026-04-12
**Scope:** Fixed Constant model (engine + dashboard)
**Source:** Wolf Tank "How to Build a Validated Model" doctrine — gap analysis against Fractal Sweep codebase

## Purpose

Close four doctrine gaps identified in the audit of `Fractal Sweep/model_stats_fixed_constant.py` and `Fractal Sweep/model_dashboard_fixed_constant.html`:

1. **Fade simulation engine** — what happens to the model's thesis after the aggregated MAE99 is breached
2. **Custom IS/OOS filter** — turn the dashboard into a true in-sample / out-of-sample engine with a date-range lens
3. **Variance display** — show MAE/MFE drift across rolling lookbacks so the user can see whether the edge is stable or regime-dependent
4. **Volatility regime cheat sheet + rolling 70-day lookback** — the doctrine's "load the matching profile before each block" working document, plus the rolling live-parameter view

TTFM engine / dashboard is explicitly out of scope. Consecutive-loss streak analysis, named IS/OOS run persistence, and standard-deviation variance overlay are also out of scope (see § 8).

## Architecture overview

Three layers change, in this order:

**Layer 1 — Engine (`Fractal Sweep/model_stats_fixed_constant.py`).** Gains two responsibilities:
- Emit `block_range_pts` on every rep (block high − block low over the full HTF block window, not just the lock candle)
- Run a second pass computing fade metrics: `fade_triggered`, `fade_breach_side`, `fade_reached_anchor`, `fade_reached_mfe50_opp`, `fade_reached_mae99_opp`, `fade_mfe_opp_pct`. Non-triggered reps have `null` on the fade fields.

**Layer 2 — JSON schema (`Fractal Sweep/model_stats_fixed_constant.json`).** Per-rep grows by seven fields; per-model gains one new aggregate block `fade_summary`. No structural changes.

**Layer 3 — Dashboard (`Fractal Sweep/model_dashboard_fixed_constant.html`).** Gains a global IS/OOS filter in the header (date range + regime pill + rolling window selector), a client-side recompute pipeline that threads the filter through every existing tab, a `classifyRegimes()` load-time function, and a new Validation tab hosting four panels.

**Design principles:**
- Engine stays narrow: raw reps + fade metrics. No rolling snapshots, no regime labels, no pre-computed lookback variants.
- Dashboard is the single source of truth for everything the user interacts with. All filtering, rolling windows, regime classification, variance computation happen client-side.
- One JSON, one engine pass. No parallel engines, no split data files.
- Zero new dependencies. Vanilla JS + SVG/HTML for charts, matching the existing zero-CDN convention.

## § 1 — Fade engine mechanics

**Input state.** After the primary excursion pass, the engine has computed `up_dist.p99` and `down_dist.p99` per model (the aggregated MAE99 on each side). These become the fade trigger thresholds:
- `mae99_up_pct` — 99th percentile of `excursion_up_pct` across all reps in the model
- `mae99_down_pct` — 99th percentile of `excursion_down_pct`

The "aggregated" framing matters: in the no-bias (aggregated) model, every rep carries both an up and a down excursion from the anchor, so MAE99 lives on both sides.

**Trigger logic.** For each rep:

1. If `excursion_up_pct >= mae99_up_pct` → primary direction is up, opposite is down. Breach bar is the first 1m bar where price reached `lock_close × (1 + mae99_up_pct/100)`.
2. Else if `excursion_down_pct >= mae99_down_pct` → primary direction is down, opposite is up. Breach bar is the first 1m bar where price reached `lock_close × (1 − mae99_down_pct/100)`.
3. Else → `fade_triggered = false`, all fade fields `null`.

**Both-sides tiebreaker.** A rep can theoretically breach both sides in the same block. Tiebreaker: whichever side breached first (earliest 1m bar timestamp) is the breach side. Assert in tests.

**Walk forward.** From the breach bar (exclusive) to `block_end` (inclusive), iterate 1m bars and track the maximum opposite-direction excursion measured from `lock_close` (not from the breach point). Record:
- `fade_mfe_opp_pct` — max opposite-side excursion as % of `lock_close`, always positive
- `fade_reached_anchor` — true if any post-breach bar's opposite-direction reach returns past `lock_close`
- `fade_reached_mfe50_opp` — true if the opposite excursion from the anchor reaches the aggregated P50 MFE on the opposite side (for an up-breach: `low_of_any_bar <= lock_close × (1 − p50_down_pct/100)`)
- `fade_reached_mae99_opp` — true if the opposite excursion reaches the opposite-side MAE99 (full symmetric breach)

**Threshold source — explicit design choice.** The MAE99 threshold used for both trigger and confirm-MAE99 is from the *full sample* the engine is processing, not a rolling 70-day window. This is correct for the engine's purpose (stable historical fade rate) but creates an interaction with the dashboard's IS/OOS filter that must be surfaced: when the user filters to a narrower date range, the per-rep fade booleans are re-scoped, but the underlying MAE99 trigger threshold stays fixed at the full-sample value. The Validation tab's Panel 3 displays both the static engine threshold and the rolling 70-day threshold side-by-side so the user can see the drift.

**Bar source.** The engine already has `df_1m` in memory from the primary pass. Fade pass uses the same slice — no extra DuckDB query. Per rep: O(block_duration_min) bars. For `1H_5M`, ≤60 bars per triggered rep. Total cost: well under 1% of current engine runtime.

## § 2 — JSON schema additions

### Per-rep fields

Appended to each entry in `recent_reps`:

| Field | Type | Populated when | Description |
|---|---|---|---|
| `block_range_pts` | float | always | high − low of all 1m bars inside the full HTF block |
| `fade_triggered` | bool | always | true if either excursion side breached aggregated MAE99 |
| `fade_breach_side` | string \| null | always | `"up"` / `"down"` / `null` |
| `fade_reached_anchor` | bool \| null | null if not triggered | true if post-breach price returned past `lock_close` |
| `fade_reached_mfe50_opp` | bool \| null | null if not triggered | true if post-breach opposite excursion reached aggregated MFE P50 |
| `fade_reached_mae99_opp` | bool \| null | null if not triggered | true if post-breach opposite excursion reached aggregated MAE99 |
| `fade_mfe_opp_pct` | float \| null | null if not triggered | max opposite-side excursion after breach, % of `lock_close` |

**Null is deliberate, not 0.** A rep that didn't trigger is structurally different from a rep that triggered but didn't fade; collapsing them on a zero would break client-side aggregation.

### Model-level addition

New key `fade_summary` alongside `up_dist`, `down_dist`, `by_hour`, etc.:

```json
"fade_summary": {
  "n_total": 68281,
  "n_triggered": 1420,
  "trigger_rate": 0.0208,
  "trigger_rate_up": 0.0104,
  "trigger_rate_down": 0.0104,

  "mae99_up_pct": 0.42,
  "mae99_down_pct": 0.38,
  "p50_mfe_up_pct": 0.11,
  "p50_mfe_down_pct": 0.09,

  "confirm_anchor_rate": 0.64,
  "confirm_mfe50_opp_rate": 0.19,
  "confirm_mae99_opp_rate": 0.03,

  "fade_mfe_opp_dist": {
    "mean": 0.18, "median": 0.15, "std": 0.12,
    "p10": 0.03, "p25": 0.08, "p50": 0.15,
    "p75": 0.24, "p90": 0.35, "p95": 0.42, "p99": 0.58
  }
}
```

**Echoed thresholds (`mae99_up_pct`, etc) are intentional.** The dashboard compares the static engine threshold to its own rolling 70-day threshold to show drift.

### Back-compat

- Old dashboard reading new JSON: extra fields ignored via JS destructuring.
- New dashboard reading old JSON (pre-fade run): `if (model.fade_summary)` guard before rendering Panel 3 of the Validation tab. Placeholder text: "run `model_stats_fixed_constant.py` to compute fade data."
- Same defensive pattern for `block_range_pts` on reps — reps missing the field skip regime classification (marked `_regime = 'unknown'`).

### File size impact

Seven new fields × ~68k reps × ~20 bytes ≈ 9 MB per model × 3 models ≈ ~27 MB growth. Current JSON is in the ~50–100 MB range. Roughly 25% growth. Acceptable for a local-served dashboard.

## § 3 — Global IS/OOS filter

### Header controls

Next to `#model-select` in the header:

```
[start date]  [end date]   [Apply] [Reset]
Regime: [all] [expanding] [neutral] [contracting]
Rolling window: [30d] [70d] [180d] [365d]
```

- Two native `<input type="date">` fields. Empty = full sample.
- Regime: four-button pill selector, default `all`.
- Rolling window: only used by Validation tab Panel 1 but lives in the header for discoverability.

**Named runs with localStorage persistence: explicitly skipped.** Austin-spec mentions named runs; plumbing for create/load/delete/compare adds ~50 lines of UI. Defer to a later pass.

### State

```js
let _filterStart  = null;  // ISO date string or null
let _filterEnd    = null;  // ISO date string or null
let _filterRegime = 'all'; // 'all' | 'expanding' | 'neutral' | 'contracting'
let _rollingWindowDays = 70;
```

### Filter primitive

One shared function, used by every render path:

```js
function filterReps(reps) {
  return reps.filter(r => {
    if (_filterStart && r.date < _filterStart) return false;
    if (_filterEnd   && r.date > _filterEnd)   return false;
    if (_filterRegime !== 'all' && r._regime !== _filterRegime) return false;
    return true;
  });
}
```

The `_regime` field is computed once on JSON load by `classifyRegimes()` (§ 5) and attached to each rep object in memory.

### Client-side recompute pipeline

The existing dashboard reads `D.up_dist`, `D.down_dist`, `D.by_hour`, etc — pre-computed aggregates from the JSON. When a filter is active these are stale. New function `computeDistributions(reps)` rebuilds them from filtered reps:

```js
function computeDistributions(reps) {
  return {
    up:       buildDist(reps.map(r => r.excursion_up_pct)),
    down:     buildDist(reps.map(r => r.excursion_down_pct)),
    by_hour:  groupAndAggregate(reps, r => r.hr),
    by_dow:   groupAndAggregate(reps, r => r.dow),
    by_session: groupAndAggregate(reps, r => r.session),
    by_year:  groupAndAggregate(reps, r => r.yr),
  };
}
```

Where `buildDist()` computes mean/median/std/p10/p25/p50/p75/p90/p95/p99 and `groupAndAggregate()` produces the same shape as the engine's existing breakdown tables.

**Performance.** 68k reps × sort-for-percentiles ≈ ~20ms in JS. Negligible.

### Render flow after filter change

```
onFilterChange()
  → filtered = filterReps(D.recent_reps)
  → if filtered.length < 30: show warning, bail
  → dist = computeDistributions(filtered)
  → renderHeroTiles({...D, up_dist: dist.up, down_dist: dist.down})
  → renderDoctrineAnchors(dist)
  → renderPctTable(dist)
  → render by_hour / by_dow / by_session / by_year from dist
  → renderValidationTab(filtered, dist)
  → renderReps(filtered)
```

Original `D.up_dist` / `D.by_hour` / etc are only used on initial page load (fast path). After the first filter change, everything flows through `computeDistributions`.

### Empty state

< 30 reps in the filtered window → `render()` does not proceed. The previously-rendered tab contents remain on screen untouched, and a dismissible banner appears at the top: "Sample too small — need ≥30 reps for valid percentiles (current filter: N reps)." 30 is the doctrine minimum for a first look. Resetting the filter or widening the range clears the banner and re-renders.

## § 4 — Validation tab layout

New tab button `Validation` added to `.page-nav` between Overview and Reps. Content is a single-column stack of four panels.

### Panel 1 — Rolling live parameters card

Three-column hero-style block:

```
┌──────────────────────┬──────────────────────┬──────────────────────┐
│ UP SIDE (rolling 70d)│ DOWN SIDE (70d)      │ MFE / MAE99 RATIO    │
│                      │                      │                      │
│ MAE99: 0.42%         │ MAE99: 0.38%         │ Up: P50/MAE99 = 0.91 │
│ P90:   0.29%         │ P90:   0.26%         │ Dn: P50/MAE99 = 0.94 │
│ P50:   0.11%         │ P50:   0.09%         │                      │
│                      │                      │                      │
│ n = 247 reps         │ n = 247 reps         │ >1 = favorable edge  │
└──────────────────────┴──────────────────────┴──────────────────────┘
```

**Rolling window anchor.** The window is anchored to the *most recent rep in the current filtered sample*, not to today. When the IS/OOS filter is set to 2023-01-01 → 2023-12-31, "rolling 70d" means "the last 70 days of that 2023 window." This respects the filter.

**Threshold drift callout** below the three columns:

```
Engine MAE99 (full sample): up 0.42%, dn 0.38%
Rolling 70d (current):      up 0.29%, dn 0.26%
Drift: -31% up, -32% dn
```

Explicit visibility of the gap between the static engine threshold and the live rolling threshold.

### Panel 2 — Variance chart

Horizontal bar chart across five fixed lookback windows, anchored to the current filter end date (or "now" if no filter): `30d / 70d / 180d / 365d / full`. Three bars per window:

- MAE99 (up)
- MFE P50 (up)
- MFE/MAE ratio

Below the chart, one-line variance statistics:
```
σ(MAE99 up across 5 windows)      = 0.031
σ(MFE P50 up across 5 windows)    = 0.008
σ(MFE/MAE ratio across 5 windows) = 0.05
```

These three numbers are what the user puts in the business plan: low = stable edge, high = regime-dependent.

**Rendering.** Pure SVG or HTML/CSS bars. No chart library.

**Standard deviation overlay on the bars: deferred.** Austin-spec advanced feature. Can add later as a toggle without changing the chart structure.

### Panel 3 — Fade engine view

**3a. Fade summary tiles.** Four hero-style tiles, values computed from filtered reps' fade fields:

```
Trigger rate     Reached anchor   Reached MFE50    Reached MAE99
 2.1%             64%              19%              3%
(of all blocks)  (of triggered)   (of triggered)   (of triggered)
```

**3b. Fade MFE distribution histogram.** Reuses existing `renderHistogram()`. Shows the distribution of `fade_mfe_opp_pct` over triggered reps in the current filter. Vertical lines at aggregated P50 and P90 MFE for comparison.

**3c. Threshold drift callout.** Two-line banner (same data as Panel 1's callout, restated in-context):

```
Engine trigger threshold: MAE99 up 0.42%, dn 0.38% (full sample, static)
Rolling 70d threshold:    MAE99 up 0.29%, dn 0.26% (live, current)
Drift: -31% up, -32% dn — fade trigger may be under-reporting on recent reps
```

Note below: "fade booleans in this view are re-scoped by the date filter but the MAE99 breach threshold was fixed at engine-run time."

### Panel 4 — Regime cheat sheet

Three columns — one per regime — computed from reps matching each regime within the current date filter:

```
┌─────────────────┬─────────────────┬─────────────────┐
│ EXPANDING       │ NEUTRAL         │ CONTRACTING     │
│ (top tercile    │ (mid tercile    │ (bot tercile    │
│  block range)   │  block range)   │  block range)   │
│                 │                 │                 │
│ n: 82           │ n: 83           │ n: 82           │
│ MAE99 up: 0.61% │ MAE99 up: 0.38% │ MAE99 up: 0.22% │
│ MAE99 dn: 0.58% │ MAE99 dn: 0.36% │ MAE99 dn: 0.20% │
│ MFE50 up: 0.17% │ MFE50 up: 0.11% │ MFE50 up: 0.06% │
│ MFE50 dn: 0.16% │ MFE50 dn: 0.10% │ MFE50 dn: 0.05% │
│ Ratio:    0.28  │ Ratio:    0.29  │ Ratio:    0.27  │
└─────────────────┴─────────────────┴─────────────────┘
```

**Interaction with regime pill.** When the header's regime pill is set to something other than `all`, the selected column gets a highlight border; the other two columns remain visible for reference but the rest of the dashboard filters to the selected regime.

**Use case.** Morning of a session: check the current block's regime (computed from the trailing N days of block ranges), read the corresponding stop/target column, load those parameters. The cheat sheet *is* the working reference document.

### Shared behavior

- All four panels re-render on any filter change (date range, regime pill, rolling window dropdown).
- Each panel independently handles its own < 30 rep sample warning.
- All panels respect the date filter identically. Panel 3's fade *booleans* re-scope with the filter, but the underlying MAE99 breach threshold was fixed at engine-run time (§ 1, "Threshold source"). The threshold drift callout (3c) makes this explicit.

## § 5 — Regime classifier

**Signal.** Each rep's regime comes from `block_range_pts` — the HTF block's total high-low range (added in § 2). Larger = expansion; smaller = contraction.

**Trailing window.** Classification is relative, not absolute. For rep R at date D, rank `block_range_pts` against reps with date in `[D − 70d, D)` (exclusive of R itself). Then assign:
- `block_range_pts >= trailing P67` → `expanding`
- `block_range_pts <= trailing P33` → `contracting`
- otherwise → `neutral`

**Trailing-only, not centered.** Dashboard is for live trading; classification must only use information available before the rep closed. Centered windows would leak future data.

**Why 70 days.** Same window as the doctrine's rolling live parameters lookback. One "regime window" definition throughout the dashboard. Single constant if it needs tuning.

**Edge cases.**
- First 70 days of any model's history: no trailing window available → `_regime = 'unknown'`, excluded from regime filter and cheat sheet, counted in everything else. Cheat sheet shows a note.
- Trailing window has < 30 reps: `_regime = 'unknown'`. Prevents garbage from tiny samples.
- Rep missing `block_range_pts` (back-compat with old engine runs): `_regime = 'unknown'`.

**Implementation.** Client-side, runs once on JSON load:

```js
function classifyRegimes(reps) {
  const WINDOW_DAYS = 70;
  const msPerDay = 86400000;
  // reps are sorted ascending by date
  for (let i = 0; i < reps.length; i++) {
    const r = reps[i];
    if (r.block_range_pts == null) { r._regime = 'unknown'; continue; }
    const cutoff = new Date(r.date).getTime() - WINDOW_DAYS * msPerDay;
    const window = [];
    for (let j = i - 1; j >= 0; j--) {
      if (new Date(reps[j].date).getTime() < cutoff) break;
      if (reps[j].block_range_pts != null) window.push(reps[j].block_range_pts);
    }
    if (window.length < 30) { r._regime = 'unknown'; continue; }
    window.sort((a, b) => a - b);
    const p33 = window[Math.floor(window.length * 0.333)];
    const p67 = window[Math.floor(window.length * 0.667)];
    if      (r.block_range_pts >= p67) r._regime = 'expanding';
    else if (r.block_range_pts <= p33) r._regime = 'contracting';
    else                                r._regime = 'neutral';
  }
}
```

**Cost.** O(n × window_size). 68k reps × ~250-rep window ≈ 17M comparisons. ~200ms JS on page load. One-time; result cached on rep objects. Optimization to O(n log window) available (rolling sorted structure) but not needed for first cut.

**Stability.** Labels are computed once against the full rep set. IS/OOS filter changes do not re-derive labels — regime is a historical property of the rep, not something re-computed per filter view.

## § 6 — Testing and verification

### Layer A — Engine correctness (Python, pytest)

New file `Fractal Sweep/tests/test_fade_engine.py` with six synthetic fixtures:

1. **No trigger.** Neither excursion side breaches MAE99. Assert `fade_triggered = false`, all fade fields `null`, `block_range_pts` correct.
2. **Up breach, no fade.** Up excursion crosses `mae99_up_pct`, price stays above anchor after. Assert `fade_triggered = true`, `fade_breach_side = "up"`, `fade_reached_anchor = false`, `fade_mfe_opp_pct ≈ 0`.
3. **Up breach, anchor reached, no MFE50.** Assert `fade_reached_anchor = true`, `fade_reached_mfe50_opp = false`.
4. **Up breach, full opposite MAE99 reached.** Assert all three confirmation booleans true, `fade_mfe_opp_pct >= mae99_down_pct`.
5. **Down breach, symmetric of fixture 4.** Verifies breach-side symmetry.
6. **Both sides breach in same block.** Whichever side breached first (earliest 1m bar) wins. Assert `fade_breach_side` matches.

Fixtures are hand-built 1m bar arrays constructed inline. Test imports the fade function from the engine and asserts the output dict. Run: `python3 -m pytest "Fractal Sweep/tests/test_fade_engine.py" -v`.

Check `Fractal Sweep/tests/` for existing convention before finalizing file structure.

### Layer B — Engine output validation (manual spot checks)

New script `Fractal Sweep/tests/validate_fade_output.py`. Loads the generated JSON and runs four sanity checks:

1. `fade_summary.trigger_rate` is between 0.5% and 3% per model. Healthy aggregated distribution with MAE99 trigger produces ~1% rate, tolerate tail clustering.
2. `fade_summary.n_triggered` equals the count of reps with `fade_triggered = true`.
3. For every triggered rep, `fade_breach_side` matches which `excursion_*_pct` actually exceeded the threshold.
4. **Strict ordering of confirmation booleans.** `fade_reached_mae99_opp = true` implies `fade_reached_mfe50_opp = true` implies `fade_reached_anchor = true`. Violation means the walk-forward logic is broken.

Runs manually after each engine execution. Prints any violating rep and exits non-zero. Not in CI — workflow gate.

### Layer C — Dashboard visual verification (manual)

Checklist run against a fresh JSON in a browser:

1. Load dashboard with no filter → hero tiles match pre-filter values.
2. Set date filter to 2023-01-01 → 2023-12-31 → hero tiles, percentile tables, `by_hour` all change. Rep count in Reps tab matches expected 2023 subset.
3. Set regime pill to `expanding` → rep count drops to ~1/3. Panel 4's expanding column highlights.
4. Rolling window dropdown 70d → 30d → Panel 1 numbers and banner update.
5. Variance chart: five rows render with correct window sizes. 30d row has smaller n than full row.
6. Fade panel: pick 3–5 triggered reps from the Reps table, manually verify against TradingView using `lock_time` and `block_end` timestamps. Catches off-by-one errors in the fade walk. This is the debug/validation layer the doctrine calls for.

### Layer D — Back-compat (manual, one-shot at merge)

Run the unchanged engine once to produce an old-shape JSON, load it in the new dashboard. Expected: Validation tab Panel 3 shows "run engine to compute fade data" placeholder; Panels 1, 2, 4 work (rolling, variance, regime all computed client-side from per-rep data); all existing tabs work normally. Verifies the null-tolerance design from § 2.

### Testing rhythm

| Layer | When | Automated? |
|---|---|---|
| A | Before each engine commit | Yes (pytest) |
| B | After each full engine run | No (one-shot) |
| C | During dashboard development | No (one-shot) |
| D | Once at merge time | No (one-shot) |

Layer A is the real gate. B–D are workflow-level checks.

## § 7 — Build sequence and commits

### Commit 1 — Engine: fade pass + block_range_pts + tests

**Files:**
- `Fractal Sweep/model_stats_fixed_constant.py` — `block_range_pts` per rep, fade pass function, `fade_summary` aggregate
- `Fractal Sweep/tests/test_fade_engine.py` — six synthetic fixtures (Layer A)
- `Fractal Sweep/tests/validate_fade_output.py` — Layer B sanity script

**Verification before commit:**
- Layer A pytest passes
- Engine runs cleanly on real data
- Layer B validation passes on regenerated JSON
- Back-compat check: current dashboard loads the new JSON without errors (Validation tab absent, all other tabs work unchanged)

**Not in this commit:** any dashboard JS changes. Commit 1 can ship on its own with zero dashboard regression.

### Commit 2 — Dashboard: IS/OOS filter + client-side recompute pipeline

**Files:**
- `Fractal Sweep/model_dashboard_fixed_constant.html`

**Changes:**
- Header controls: two date inputs, regime pill, rolling window dropdown (placeholder wiring — Panel 1 consumes it in Commit 3)
- Globals: `_filterStart`, `_filterEnd`, `_filterRegime`, `_rollingWindowDays`
- `filterReps()` primitive
- `computeDistributions()` — replaces reads from `D.up_dist` / `D.down_dist` / `D.by_*` with on-the-fly recomputation
- `classifyRegimes()` — per § 5, runs once on JSON load, attaches `_regime` to each rep
- Thread filter through existing `render()` path — all existing tabs respect the filter
- Empty-state handling: < 30 rep warning

**Verification before commit:** subset of Layer C — steps 1 and 2 only (filter toggles re-scope Overview hero tiles, percentile tables, breakdowns, Reps count). Partial step 3: confirm the regime pill updates `_filterRegime` and changes rep count; Panel 4 highlight behavior is not testable yet (Panel 4 lands in Commit 3). Steps 4–6 are deferred to Commit 3's verification.

**Regression risk.** This commit touches the existing render pipeline. Mitigation: audit every reference to `D.up_dist` / `D.down_dist` / `D.by_*` and route through `computeDistributions`. No render function should read pre-computed engine aggregates directly after this commit.

### Commit 3 — Dashboard: Validation tab

**Files:**
- `Fractal Sweep/model_dashboard_fixed_constant.html`

**Changes:**
- New `Validation` tab button in `.page-nav`
- Panel 1: rolling live parameters card (reuses `computeDistributions` with a rolling-window filter of the filtered reps)
- Panel 2: variance chart — SVG/HTML bars, no library
- Panel 3: fade engine view — reuses `renderHistogram`, reads `fade_summary` + recomputes filtered fade rates from per-rep fade fields
- Panel 4: regime cheat sheet — three columns, one compute per column
- Rolling window dropdown fully wired to Panel 1

**Verification before commit:** full Layer C — steps 3 (Panel 4 highlight), 4 (rolling window dropdown drives Panel 1), 5 (variance chart rows render correctly), and 6 (spot-check 3–5 triggered reps against TradingView using `lock_time` / `block_end` timestamps). Step 6 is the hardest and catches off-by-one errors in the fade walk.

### Reorder note

Commits 2 and 3 can be merged into a single larger dashboard commit. Recommended split: Commit 2 touches existing render pipeline (regression risk) and Commit 3 is additive (new tab only). Splitting makes the risky commit small and auditable.

## § 8 — Out of scope

Explicitly deferred to avoid scope creep:

- **TTFM dashboard / engine changes.** Doctrine says fixed constant first; TTFM propagation is a separate future pass. TTFM also has the unresolved directional-labeling bug that would contaminate any fade/variance/regime results.
- **Named IS/OOS runs with localStorage persistence.** Austin-spec feature, ~50 lines of UI plumbing, not needed for first cut.
- **Standard deviation overlay on variance chart.** Austin-spec advanced feature, can add later as a toggle without changing chart structure.
- **Consecutive-loss streak analysis.** Doctrine priority #2 from the gap audit — the next thing to build after this spec ships, but separate spec.
- **Live scanner / prop tracking / payout allocation.** Operations doctrine features, not validation features.
- **VIX-based regime classification.** VIX not in duckdb; data source change is out of scope. Block-range percentile (§ 5) is the chosen classifier.

## Risk summary

| Risk | Mitigation |
|---|---|
| Fade walk off-by-one errors | Layer A fixtures 2–6 exercise breach-bar boundary conditions; Layer C step 6 manual TradingView verification |
| IS/OOS filter regression on existing tabs | Commit 2 audit: every `D.up_dist` / `D.by_*` reference routed through `computeDistributions` |
| Static MAE99 threshold misleads users on recent data | Panel 3 threshold drift callout makes the static-vs-rolling gap explicit |
| Regime labels computed from < 30 rep windows | `unknown` label excludes from regime analysis; cheat sheet shows classified count |
| JSON file size growth (~25%) | Acceptable for local-served dashboard; flagged for awareness not mitigation |
| TTFM directional bug contaminates fade interpretation | TTFM explicitly out of scope |
