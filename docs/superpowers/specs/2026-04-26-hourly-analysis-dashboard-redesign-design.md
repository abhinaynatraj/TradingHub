# NQ Hourly Analysis Dashboard — Visual Redesign

**Date:** 2026-04-26
**Status:** Draft, pending review
**Location:** `Analysis/dashboard/`
**Supersedes:** dashboard sections of `2026-04-26-hourly-analysis-design.md`

## Overview

The first dashboard pass shipped functional but unreadable: both pages used a generic table renderer that dumped every column with cryptic names (`q1_body_to_range_ratio`) side-by-side. This spec replaces that with study-specific layouts, inline-bar visualizations, side-by-side bull/bear breakout panels, multi-filter chips, and a sidebar nav for the quarters page.

No engine changes. The parquet outputs stay exactly as they are. This is a pure presentation refactor.

## Goals

- Each panel tells a clear story at a glance, not a dump of numbers.
- Visualizations are inline (table cells double as bar charts) — no charting library dependency.
- Filters compose; multiple cuts can be applied simultaneously and breakdowns are always visible.
- Curated headline + drill-down: one-sentence summary above each panel, raw numbers always available below.
- Filter state survives page reloads.

## Architecture

### Files changed

```
Analysis/dashboard/
├── index.html        unchanged
├── shared.css        extended (new components: filter chips, inline-bar table, study panels, donut, heatmap, sidebar)
├── shared.js         extended (filter-chip component, inline-bar table renderer, headline-insight helper, localStorage persistence)
├── breakout.html     rewritten
└── quarters.html     rewritten
```

### Shared building blocks (in `shared.js` / `shared.css`)

**1. Filter bar (`<div class="filter-bar collapsible">`)**

Multi-dimension chip selector at the top of each page. Always-visible header bar with toggle to collapse to a single line ("Filters: All years · RTH · Mon–Fri · n=12,847").

Dimensions:
- **Year** — pills for All / 2014 / 2015 / ... / 2026. Multi-select; click to toggle. Default: All.
- **Hour-of-day** — two rows: a "preset" row (RTH = 9–16, London = 3–8, Asia = 18–2 prev day, Overnight = 17–2, All 24h) and an "individual hour" row (0–23). Clicking a preset selects that preset's hour set; clicking an individual hour toggles that hour. Default: All 24h.
- **Day-of-week** — pills for Mon / Tue / Wed / Thu / Fri / Sat / Sun. Default: Mon–Fri.
- **Direction** (breakout page only) — radio toggle: Both / Bullish / Bearish. Default: Both. When set to Bullish or Bearish, the non-selected hero panel renders dimmed (50% opacity) and breakdown tables hide the non-selected direction's columns.
- **Min sample size** — small number input (default 30). Cells with `count < threshold` get `.row-low-count` (existing behavior).

Each chip group displays a count of matching rows: `Years: 2023, 2024, 2025  ·  n=12,847 hours`.

State: written to `localStorage` per page (`analysis-breakout-filters`, `analysis-quarters-filters`) on every change. Read on page load. Schema-versioned so future changes don't break stored state.

API:
```js
window.FilterBar = {
  init(containerEl, pageKey, dims, onChange),  // dims: ['year','hour','dow','direction','minCount']
  whereClause(): string,                       // returns SQL: "year IN (2024,2025) AND hour_of_day_et IN (9,10,...,16) AND dow IN (0,1,2,3,4)"
  filterEvents(rows): rows,                    // client-side equivalent for non-SQL data
  state(): {year, hour, dow, direction, minCount}
};
```

**2. Inline-bar table renderer (`renderInlineBarTable(targetEl, rows, columnSpec)`)**

Replaces the existing `genericTable()`. Columns are explicitly specified (label, key, format, optional inline-bar config).

Column types:
- `'label'` — text (row header)
- `'count'` — formatted integer (used for greying-out via min-count)
- `'pct'` — percentage with optional inline horizontal bar (`maxPct` for bar scaling)
- `'num'` — number with optional unit suffix (e.g. ` pts`)
- `'inlineBar'` — bar with the value rendered inside or to the right
- `'baseline'` — pct with a dotted reference line at a baseline value (e.g. 25% for 4-quarter distributions)

Bar coloring rules:
- Above baseline → green; below baseline → blue (per Q3 visual choice).
- For directional bars (e.g. Bull rate), uses green/red.
- Color is set per column in the spec.

Example use:
```js
renderInlineBarTable(el, rows, [
  { key: 'quarter',       label: 'Quarter', type: 'label' },
  { key: 'q_high_pct',    label: 'High lands here', type: 'baseline', baseline: 0.25, maxPct: 0.5 },
  { key: 'q_low_pct',     label: 'Low lands here',  type: 'baseline', baseline: 0.25, maxPct: 0.5 },
]);
```

**3. Stat card (`<div class="stat-card">`)**

Existing markup, polished slightly. Variants: `.stat-card--accent`, `.stat-card--bull` (green), `.stat-card--bear` (red), `.stat-card--neutral`.

**4. Headline insight (`renderHeadline(el, template, vars)`)**

A one-sentence insight at the top of each panel, computed from the active data. Templates use `${var}` interpolation. Example:

```js
renderHeadline(el,
  'Q${topQuarter} contains the high ${topPct} of the time, well above the ${baseline} baseline.',
  { topQuarter: 1, topPct: '36.4%', baseline: '25%' });
```

Headlines re-render whenever filters change. If no data passes the filter, the headline shows "Not enough data for this slice."

**5. Donut chart (CSS-only)**

Pure CSS conic-gradient donut for study B sequencing. Three segments, color-coded, with labels.

**6. Heatmap (CSS grid)**

Grid of cells colored on a value scale. Used for breakout page hour×DOW grid and quarter page A's q_of_high × q_of_low cross-tab.

## Breakout Page (`breakout.html`)

### Top: filter bar (collapsible)

All five dimensions: Year, Hour-of-day (with session presets), DOW, Direction, Min sample.

### Hero: side-by-side bull/bear panels

Two equal-width panels, ~50/50 horizontal split.

**Bull panel** (green border, dark green gradient bg):
- Header: "▲ BULLISH BREAKOUT"
- "Happens in" → big number `bullish_breakout_rate` (e.g. "26.6%") → "of hours (15,775 events)"
- Divider
- "When it does, next hour follows through" → `bullish_followthrough_rate` (e.g. "69.4%") → "10,948 of 15,775 cases"
- Footer line: "Reversal: `bullish_immediate_reversal_rate` (e.g. 21.6%)"

**Bear panel** mirrors with red.

All numbers reflect the active filter (computed via DuckDB query against filtered events).

### Panel 1: Quarter-of-H2 takeout attribution

Headline: "Most follow-throughs happen in Q1 — momentum after a breakout is fast."

Two inline-bar tables stacked:
- "Bullish follow-throughs (n=10,948)" — rows = Q1/Q2/Q3/Q4, column = % of takeouts in this quarter (with inline bar). Sums to 100%.
- "Bearish follow-throughs (n=8,384)" — same shape, mirrored.

Data source: aggregate over `breakouts.parquet` filtered, grouping by `takeout_quarter_of_h2`.

### Panel 2: H1 open vs prev-mid conditioning

Headline: "Bull breakouts that opened *below* prev-hour mid follow through X% of the time vs Y% when they opened above."

2×2 grid of stat cards:
- Top-left: "Bull / opened above prev-mid" — follow-through % + n
- Top-right: "Bull / opened below prev-mid" — follow-through % + n
- Bottom-left: "Bear / opened above prev-mid" — follow-through % + n
- Bottom-right: "Bear / opened below prev-mid" — follow-through % + n

Data source: aggregate over filtered events, grouping by (breakout, h1_open_vs_prev_mid).

### Panel 3: By year breakdown

Always-on, regardless of year filter (so the user can see year-over-year stability even when filtering to a specific year for the hero).

Inline-bar table:
- Rows = year (2014–2026)
- Columns: count (n) | Bull rate (with inline bar) | Bull FT (with inline bar) | Bear rate (with inline bar) | Bear FT (with inline bar)
- Years filtered to year-filter scope are highlighted; the other years render dimmed (the filter narrows the hero, not the breakdown — by-year always shows all years).

### Panel 4: By hour-of-day (ET)

Same inline-bar table, rows = 0–23. Hours that are *not* in the active hour-filter render dimmed (50% opacity) so the user sees the contrast between in-filter and out-of-filter rows without losing the full distribution.

### Panel 5: By day-of-week

Same inline-bar table, rows = Mon–Sun. DOWs not in the active dow-filter render dimmed (same convention as Panel 4).

### Panel 6: Hour × DOW heatmap

Bottom of page. Single grid:
- Rows = hour-of-day (0–23 ET)
- Columns = DOW (Mon–Fri)
- Cell color = follow-through rate on green→amber→red scale; cell text = follow-through %; hover/click → tooltip showing count, bull rate, bull FT, bear rate, bear FT.

Cells below `min-count` threshold render with low opacity.

## Quarters Page (`quarters.html`)

### Top: filter bar (collapsible)

Year, Hour-of-day (with presets), DOW, Min sample. (No direction toggle — quarter studies aren't directional.)

### Layout: sidebar nav + main panel

```
┌──────────────────┬───────────────────────────────────────┐
│ Studies          │  [Active study: full layout]          │
│                  │                                       │
│ ▶ A · Location   │  Headline insight                     │
│   B · Sequencing │  Stat cards / inline-bar tables /     │
│   C · Per-q bias │  heatmap / donut / quintile table     │
│   D · Conditional│                                       │
│   E · Persistence│                                       │
│   F · Q1 expand  │                                       │
└──────────────────┴───────────────────────────────────────┘
```

Sidebar: ~200px wide, fixed-position alongside main scroll. Each item has a label + one-line subtitle.

```
A · Location          Where the high/low lands
B · Sequencing        High first or low first
C · Per-quarter bias  Direction & range stats
D · Conditional       Q1 → later quarter shifts
E · Persistence       Hold rate & overshoot
F · Q1 expansion      Range bucketing
```

Active item gets accent green left border + subtly filled background. Click switches main panel content. Active study persists per-tab in `localStorage`.

### Study A — Location

**Headline:** "Q${topHigh} contains the hourly high ${topHighPct} of the time, ${topHighDelta} above the 25% baseline."

**Layout:**
- Two inline-bar tables side-by-side (50/50):
  - "Where the high lands" — rows Q1–Q4, column = % with bar, baseline 25%, color above baseline = green / below = blue.
  - "Where the low lands" — same shape mirrored.
- Below: 4×4 cross-tab heatmap. Rows = q_of_high (1–4), columns = q_of_low (1–4). Cells colored by joint probability. Diagonal cells (high and low in same quarter) emphasized.

### Study B — Sequencing

**Headline:** "High came first in ${hFirstPct} of hours, low in ${lFirstPct}, tied in ${tiePct}."

**Layout:**
- CSS donut: H-first / L-first / Tie. Color-coded segments with labels.
- Below: two inline-bar tables side-by-side:
  - "When the high came first, where did it land?" (Q1–Q4 with %).
  - "When the low came first, where did it land?" (Q1–Q4 with %).

### Study C — Per-quarter bias

**Headline:** "Q${widestQ} has the widest average range (${widestRange} pts); Q${quietestQ} is the quietest (${quietestRange} pts)."

**Layout:**
- Single 4-row table:
  - Rows = Q1, Q2, Q3, Q4
  - Columns: Up % | Down % | Flat % | Avg range | Avg body | Decisiveness (body/range)
  - Inline bars in each numeric column. Up % uses green, Down % uses red. Range/body columns use a neutral inline bar scaled to the column max.

### Study D — Conditional shifts

**Headline:** "When Q1 closes up, the hour closes up ${pHourUpGivenQ1Up} of the time. Reversal probability: ${pReversal}."

**Layout:**
- Top: 2 stat cards — `P(hour ↑ | Q1 ↑)` and `P(hour ↓ | Q1 ↓)`.
- Below: inline-bar table:
  - Rows: "Q1 ↑" / "Q1 flat" / "Q1 ↓"
  - Columns: P(Q2 ↑) | P(Q3 ↑) | P(Q4 ↑) | P(hour ↑) | (mirrored ↓ columns hidden by default, expandable)
  - Each cell is a percentage with an inline bar, baseline 50%, green above / red below.
- Footer stat: "P(Q4 reverses Q1) = ${pReversal}" with a single big number.

### Study E — Persistence

**Headline:** "Q1's high holds as the hour high ${q1HighHold} of the time. When it fails, the average overshoot is ${overshootMean} pts."

**Layout:**
- Top: 4 stat cards in a row — Q1 high hold %, Q1 low hold %, Q4 high hold %, Q4 low hold %.
- Below: inline-bar table for overshoot stats — rows = Q1 high failed / Q1 low failed, columns = Mean overshoot (pts) | Median overshoot (pts) | n cases. Inline bar on the overshoot columns.

### Study F — Q1 expansion

**Headline:** "When Q1 has the widest range (top quintile, avg ${q5Range} pts), the hour ends up ${q5HourRange} pts wide on average vs ${q1HourRange} for the narrowest quintile."

**Layout:**
- Single 5-row table:
  - Rows = Q1-range quintile (1 = narrowest, 5 = widest)
  - Columns: Avg Q1 range | Avg hour range | Avg remaining range | Q1-high held % | Q1-low held % | Hour ↑ % | Hour ↓ %
  - Inline bars throughout. Hold rates use green/blue baseline 25%; direction rates use green/red baseline 50%.

## Color & Visual Conventions

- **Green** (`var(--green)`) — bullish, above-baseline favorable, "follow-through"
- **Red** (`var(--red)`) — bearish, against direction
- **Amber** (`var(--amber)`) — neutral / reversal / warning
- **Blue** (`var(--blue)`) — below-baseline neutral (for distribution bars)
- **Accent green** (`var(--accent)`) — interactive elements (active filter chips, active sidebar item)
- All theme variables flow through existing `[data-theme="dark"]` / `[data-theme="light"]` blocks; both pages must work in both themes.

## Performance Constraints

- Filter changes re-execute DuckDB queries against in-memory parquet views (already loaded). Target re-render < 100ms for any single panel. The hour × DOW heatmap may take longer — render on idle if needed.
- No new JS dependencies. Inline-bar tables, donut, and heatmap are CSS + small helper functions in `shared.js`.
- `breakouts.parquet` (3.3 MB) is already lazy-loaded only when a panel needs raw events. `summary_*` parquets stay the primary aggregate source.

## Out of Scope

- Engine changes (parquet schemas stay the same).
- A real charting library (Chart.js, etc.). All visualizations are inline-bar / CSS-based per Q3-C.
- Sortable table columns (would add interaction complexity without clear value at this stage).
- CSV export from the browser.
- Real-time data refresh (manifest stays the source-of-truth for "last run").
- New studies beyond A–F.

## Open Items

None. All visual/UX decisions captured in Q1–Q6 of brainstorming.
