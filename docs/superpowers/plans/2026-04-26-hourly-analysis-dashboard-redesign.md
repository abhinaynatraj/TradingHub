# NQ Hourly Analysis Dashboard Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the existing generic-table dashboard with study-specific layouts: side-by-side bull/bear breakout panels, sidebar nav for the quarters page, multi-filter chips with session presets, and inline-bar tables throughout.

**Architecture:** Pure presentation refactor — no engine or parquet changes. All visualizations are CSS+small JS helpers (no charting library). Three new shared components in `shared.js`/`shared.css` (filter bar, inline-bar table renderer, headline insights), then `breakout.html` and `quarters.html` get rewritten on top of them.

**Tech Stack:** Vanilla HTML/CSS/JavaScript, DuckDB-Wasm for parquet querying (existing). No new dependencies.

**Spec reference:** `docs/superpowers/specs/2026-04-26-hourly-analysis-dashboard-redesign-design.md`

---

## File Structure

```
Analysis/dashboard/
├── index.html        unchanged
├── shared.css        EXTEND — add filter chips, inline-bar tables, study panels, donut, heatmap, sidebar
├── shared.js         EXTEND — add FilterBar, renderInlineBarTable, renderHeadline, renderDonut, renderHeatmap
├── breakout.html     REWRITE — hero + 6 panels
└── quarters.html     REWRITE — sidebar nav + 6 study layouts
```

The plan keeps the existing `getDB`, `loadParquet`, `query`, `fmtPct`, `fmtNum`, `toggleTheme` exports unchanged so nothing else in the project breaks.

**Validation strategy:** No automated tests for HTML/JS (matches existing dashboard convention). Each task ends with manual browser validation via `http://localhost:8001/Analysis/dashboard/...` and a `node --check` syntax check on extracted inline JS.

---

## Task 1: CSS scaffolding for new components

**Files:**
- Modify: `Analysis/dashboard/shared.css`

- [ ] **Step 1: Read the existing `shared.css` to understand current tokens**

Run: `cat /Users/abhi/Projects/Statistic.ally/Analysis/dashboard/shared.css`
Confirm it has `:root` tokens for `--green`, `--red`, `--amber`, `--blue`, theme blocks for `[data-theme="dark"]` and `[data-theme="light"]`, and existing `.card`, `.card-grid`, `.metric-value`, `.metric-label`, `.row-low-count`, `.theme-toggle`, `.filter-bar` classes.

- [ ] **Step 2: Append new CSS tokens needed by the redesign**

Add the following block immediately after the `[data-theme="light"]` closing brace (around line 23):

```css
/* ── Redesign tokens ─────────────────────────────────────────── */
:root {
  --green-tint: rgba(16,185,129,.10);
  --green-tint-strong: rgba(16,185,129,.18);
  --green-border: rgba(16,185,129,.35);
  --red-tint: rgba(239,68,68,.10);
  --red-tint-strong: rgba(239,68,68,.18);
  --red-border: rgba(239,68,68,.35);
  --amber-tint: rgba(245,158,11,.12);
  --blue-tint: rgba(59,130,246,.12);
  --bar-track: rgba(255,255,255,.04);
}
[data-theme="light"] {
  --bar-track: rgba(15,23,42,.05);
}
```

- [ ] **Step 3: Append filter-chip styles**

Append to `shared.css`:

```css
/* ── Filter bar (collapsible) ────────────────────────────────── */
.filter-bar.collapsible {
  display: block;
  padding: 12px 16px;
}
.filter-bar.collapsible .fb-header {
  display: flex; align-items: center; gap: 12px;
  cursor: pointer; user-select: none;
}
.filter-bar.collapsible .fb-toggle {
  font-family: var(--font-data); font-size: 11px; color: var(--text-secondary);
  transition: transform .15s var(--ease);
}
.filter-bar.collapsible[data-collapsed="true"] .fb-toggle { transform: rotate(-90deg); }
.filter-bar.collapsible .fb-summary {
  font-family: var(--font-data); font-size: 12px; color: var(--text-secondary);
  flex: 1;
}
.filter-bar.collapsible .fb-body {
  margin-top: 14px; display: flex; flex-direction: column; gap: 10px;
}
.filter-bar.collapsible[data-collapsed="true"] .fb-body { display: none; }
.fb-group {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
}
.fb-group-label {
  font-size: 11px; text-transform: uppercase; letter-spacing: .05em;
  color: var(--text-secondary); min-width: 70px;
}
.fb-chip {
  font-family: var(--font-data); font-size: 11px;
  padding: 4px 10px; border-radius: 12px;
  background: var(--bg-card); color: var(--text-secondary);
  border: 1px solid var(--border); cursor: pointer;
  transition: background .12s var(--ease), color .12s var(--ease), border-color .12s var(--ease);
}
.fb-chip:hover { border-color: var(--border-hi); color: var(--text-primary); }
.fb-chip[data-active="true"] {
  background: var(--green-tint-strong); color: var(--green); border-color: var(--green-border);
}
.fb-chip[data-preset="true"] {
  background: var(--bg-raised); color: var(--text-primary);
}
.fb-chip[data-preset="true"][data-active="true"] {
  background: var(--green-tint-strong); color: var(--green); border-color: var(--green-border);
}
.fb-count {
  font-family: var(--font-data); font-size: 11px; color: var(--text-muted); margin-left: 4px;
}
.fb-input {
  font-family: var(--font-data); font-size: 12px;
  width: 70px; padding: 4px 8px; border-radius: 4px;
  background: var(--bg-card); color: var(--text-primary);
  border: 1px solid var(--border);
}
```

- [ ] **Step 4: Append inline-bar-table styles**

Append:

```css
/* ── Inline-bar tables ───────────────────────────────────────── */
.ibt {
  width: 100%; border-collapse: separate; border-spacing: 0;
  font-family: var(--font-data); font-size: 12px;
}
.ibt th, .ibt td {
  padding: 6px 10px; border-bottom: 1px solid var(--border); text-align: right;
  vertical-align: middle;
}
.ibt th {
  background: var(--bg-raised); color: var(--text-secondary); text-align: left;
  font-weight: 500; text-transform: uppercase; font-size: 10px; letter-spacing: .05em;
}
.ibt td.label, .ibt th.label { text-align: left; color: var(--text-primary); }
.ibt tr.dim { opacity: .35; }
.ibt-bar-cell {
  position: relative; min-width: 120px;
}
.ibt-bar-track {
  position: relative; height: 18px; background: var(--bar-track); border-radius: 3px;
  overflow: hidden;
}
.ibt-bar-fill {
  position: absolute; left: 0; top: 0; bottom: 0; border-radius: 3px;
  background: var(--accent);
  transition: width .15s var(--ease);
}
.ibt-bar-fill.bar-green   { background: var(--green); }
.ibt-bar-fill.bar-red     { background: var(--red); }
.ibt-bar-fill.bar-amber   { background: var(--amber); }
.ibt-bar-fill.bar-blue    { background: var(--blue); }
.ibt-bar-fill.bar-neutral { background: var(--text-secondary); opacity: .55; }
.ibt-bar-label {
  position: absolute; right: 8px; top: 0; bottom: 0;
  display: flex; align-items: center;
  font-family: var(--font-data); font-size: 11px; font-weight: 500;
  color: var(--text-primary); pointer-events: none;
}
.ibt-baseline {
  position: absolute; top: 0; bottom: 0; width: 1px;
  background: var(--text-muted); opacity: .6;
}
.ibt-baseline-label {
  font-size: 9px; color: var(--text-muted); margin-top: 2px;
  font-style: italic; text-align: right;
}
```

- [ ] **Step 5: Append hero panel + headline + sidebar styles**

Append:

```css
/* ── Hero panels (breakout page) ─────────────────────────────── */
.hero-pair { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 24px; }
.hero-panel {
  border-radius: 10px; padding: 20px;
  border: 1px solid var(--border); position: relative;
  transition: opacity .15s var(--ease);
}
.hero-panel.dimmed { opacity: .4; }
.hero-panel.bull {
  background: linear-gradient(135deg, var(--green-tint), transparent 70%);
  border-color: var(--green-border);
}
.hero-panel.bear {
  background: linear-gradient(135deg, var(--red-tint), transparent 70%);
  border-color: var(--red-border);
}
.hero-eyebrow {
  font-size: 11px; text-transform: uppercase; letter-spacing: .08em;
  font-weight: 600; margin-bottom: 12px;
}
.hero-panel.bull .hero-eyebrow { color: var(--green); }
.hero-panel.bear .hero-eyebrow { color: var(--red); }
.hero-line { font-size: 12px; color: var(--text-secondary); margin-bottom: 4px; }
.hero-big {
  font-family: var(--font-data); font-size: 32px; font-weight: 700; line-height: 1;
  margin-bottom: 4px;
}
.hero-panel.bull .hero-big { color: var(--green); }
.hero-panel.bear .hero-big { color: var(--red); }
.hero-divider { border-top: 1px solid var(--border); margin: 14px 0 10px; }
.hero-mid {
  font-family: var(--font-data); font-size: 24px; font-weight: 600; margin-bottom: 2px;
}
.hero-panel.bull .hero-mid { color: var(--green); }
.hero-panel.bear .hero-mid { color: var(--red); }
.hero-foot { font-size: 10px; color: var(--text-muted); margin-top: 6px; }
.hero-foot.warn { color: var(--amber); }

/* ── Headline insight ────────────────────────────────────────── */
.headline {
  background: var(--bg-raised);
  border-left: 3px solid var(--accent);
  border-radius: 0 6px 6px 0;
  padding: 10px 14px; margin-bottom: 14px;
  font-size: 13px; color: var(--text-primary);
  line-height: 1.5;
}
.headline.warn { border-left-color: var(--amber); color: var(--text-secondary); }

/* ── Quarters sidebar nav ────────────────────────────────────── */
.qs-layout {
  display: grid; grid-template-columns: 220px 1fr; gap: 18px;
}
.qs-sidebar {
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 8px; padding: 8px; height: fit-content;
  position: sticky; top: 20px;
}
.qs-nav-item {
  display: block; padding: 10px 12px; border-radius: 6px;
  cursor: pointer; border-left: 3px solid transparent;
  transition: background .12s var(--ease);
}
.qs-nav-item:hover { background: var(--bg-hover); }
.qs-nav-item[data-active="true"] {
  background: var(--green-tint); border-left-color: var(--accent);
}
.qs-nav-label {
  font-family: var(--font-display); font-weight: 600; font-size: 13px;
  color: var(--text-primary);
}
.qs-nav-item[data-active="true"] .qs-nav-label { color: var(--accent); }
.qs-nav-sub {
  font-size: 10px; color: var(--text-muted); margin-top: 2px;
}
.qs-main {
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 8px; padding: 20px;
}
.study-section { margin-bottom: 24px; }
.study-section:last-child { margin-bottom: 0; }
.study-section-title {
  font-size: 12px; text-transform: uppercase; letter-spacing: .05em;
  color: var(--text-secondary); margin-bottom: 10px;
}
.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.four-col { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }

/* ── Stat card variants ──────────────────────────────────────── */
.stat-card {
  background: var(--bg-raised); border: 1px solid var(--border);
  border-radius: 6px; padding: 12px;
}
.stat-card-label {
  font-size: 10px; text-transform: uppercase; letter-spacing: .05em;
  color: var(--text-secondary); margin-bottom: 4px;
}
.stat-card-value {
  font-family: var(--font-data); font-size: 22px; font-weight: 600;
  color: var(--text-primary);
}
.stat-card-sub { font-size: 10px; color: var(--text-muted); margin-top: 2px; }
.stat-card.bull .stat-card-value { color: var(--green); }
.stat-card.bear .stat-card-value { color: var(--red); }
.stat-card.amber .stat-card-value { color: var(--amber); }

/* ── Donut (CSS-only) ────────────────────────────────────────── */
.donut {
  width: 140px; height: 140px; border-radius: 50%; position: relative;
  display: inline-block;
}
.donut-center {
  position: absolute; inset: 28px; background: var(--bg-card);
  border-radius: 50%; display: flex; align-items: center; justify-content: center;
  font-family: var(--font-data); font-size: 11px; color: var(--text-secondary);
  text-align: center;
}
.donut-legend {
  display: inline-flex; flex-direction: column; gap: 4px;
  margin-left: 16px; vertical-align: top;
  font-family: var(--font-data); font-size: 11px; color: var(--text-secondary);
}
.donut-legend .swatch {
  display: inline-block; width: 10px; height: 10px; border-radius: 2px;
  margin-right: 6px; vertical-align: middle;
}

/* ── Heatmap (CSS grid) ──────────────────────────────────────── */
.hm {
  display: grid; gap: 2px;
  font-family: var(--font-data); font-size: 10px;
}
.hm-cell {
  padding: 6px 4px; text-align: center; border-radius: 2px;
  color: var(--text-primary); cursor: default;
  transition: transform .1s var(--ease);
}
.hm-cell:hover { transform: scale(1.06); z-index: 1; position: relative; }
.hm-cell.dim { opacity: .25; }
.hm-cell.empty { background: transparent; color: var(--text-muted); }
.hm-axis {
  font-family: var(--font-data); font-size: 10px;
  color: var(--text-secondary); padding: 4px;
}
.hm-axis.right { text-align: right; }
.hm-axis.center { text-align: center; }

/* ── Cross-tab heatmap (4×4) ─────────────────────────────────── */
.crosstab {
  display: grid; grid-template-columns: 60px repeat(4, 1fr);
  gap: 2px; max-width: 320px; font-family: var(--font-data); font-size: 11px;
}
.crosstab-corner, .crosstab-axis {
  padding: 6px; color: var(--text-secondary); text-align: center;
}
.crosstab-cell {
  padding: 10px 6px; border-radius: 3px; text-align: center;
  color: var(--text-primary);
}
.crosstab-cell.diag { font-weight: 600; outline: 1px solid var(--border-hi); }
```

- [ ] **Step 6: Verify CSS doesn't break the existing pages**

Run server (or reuse): `cd /Users/abhi/Projects/Statistic.ally && (pgrep -f "http.server 8001" || python3 -m http.server 8001 &)`

Open http://localhost:8001/Analysis/dashboard/index.html in a browser. The page should still render correctly (manifest card + 2 navigation cards, dark theme). Open the existing breakout.html and quarters.html pages — they should also still render (they don't use the new classes yet).

Kill server: `pkill -f "http.server 8001" || true`

- [ ] **Step 7: Commit**

```bash
cd /Users/abhi/Projects/Statistic.ally
git add Analysis/dashboard/shared.css
git commit -m "Analysis dashboard: CSS scaffolding for redesign components"
```

---

## Task 2: FilterBar component in shared.js

**Files:**
- Modify: `Analysis/dashboard/shared.js`

- [ ] **Step 1: Append FilterBar implementation**

Add to the bottom of `Analysis/dashboard/shared.js`:

```javascript
// ── FilterBar ────────────────────────────────────────────────
// Multi-dimension filter chip component. Persists state to localStorage.
// Emits SQL WHERE clauses via .whereClause().
//
// Usage:
//   FilterBar.init(document.getElementById('filters'), 'analysis-breakout',
//                  ['year','hour','dow','direction','minCount'],
//                  () => render());

window.FilterBar = (function () {
  // Session presets (hour-of-day in ET, 0-23)
  const HOUR_PRESETS = {
    'All 24h':    Array.from({length: 24}, (_, i) => i),
    'RTH':        [9, 10, 11, 12, 13, 14, 15, 16],
    'London':     [3, 4, 5, 6, 7, 8],
    'Asia':       [18, 19, 20, 21, 22, 23, 0, 1, 2],
    'Overnight':  [17, 18, 19, 20, 21, 22, 23, 0, 1, 2],
  };
  const ALL_HOURS = Array.from({length: 24}, (_, i) => i);
  const ALL_DOWS = [0, 1, 2, 3, 4, 5, 6];
  const DOW_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  // Years are discovered dynamically from the dataset (passed in via init).

  let state = null;
  let containerEl = null;
  let storageKey = null;
  let onChangeFn = null;
  let availableYears = [];
  let dimensions = [];

  function load() {
    try {
      const raw = localStorage.getItem(storageKey);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      if (parsed.__schema !== 1) return null;
      return parsed;
    } catch (e) { return null; }
  }

  function save() {
    const payload = { __schema: 1, ...state };
    localStorage.setItem(storageKey, JSON.stringify(payload));
  }

  function defaults() {
    return {
      year: new Set(availableYears),       // all years
      hour: new Set(ALL_HOURS),             // all 24h
      dow: new Set([0, 1, 2, 3, 4]),        // Mon-Fri
      direction: 'both',                    // 'both' | 'bullish' | 'bearish'
      minCount: 30,
      collapsed: false,
    };
  }

  // Initialize: discover years from optional list, load persisted state, render.
  async function init(container, key, dims, onChange, opts = {}) {
    containerEl = container;
    storageKey = `analysis-${key}-filters`;
    dimensions = dims;
    onChangeFn = onChange;
    availableYears = opts.years || [];

    const persisted = load();
    state = defaults();
    if (persisted) {
      // Coerce arrays back to Sets
      if (persisted.year) state.year = new Set(persisted.year);
      if (persisted.hour) state.hour = new Set(persisted.hour);
      if (persisted.dow) state.dow = new Set(persisted.dow);
      if (persisted.direction) state.direction = persisted.direction;
      if (persisted.minCount != null) state.minCount = persisted.minCount;
      if (persisted.collapsed != null) state.collapsed = persisted.collapsed;
    }
    render();
  }

  function setActiveYears(years) {
    availableYears = years;
    // If state.year is "all years" set, expand it to include any new years
    state.year = new Set(years);
    render();
  }

  function _serialize() {
    return {
      year: [...state.year], hour: [...state.hour], dow: [...state.dow],
      direction: state.direction, minCount: state.minCount, collapsed: state.collapsed,
    };
  }

  function _change() {
    save();
    render();
    if (onChangeFn) onChangeFn();
  }

  function _toggleSet(setName, value) {
    const s = state[setName];
    if (s.has(value)) s.delete(value); else s.add(value);
    if (s.size === 0) {
      // Don't allow zero-selection — restore defaults for this dim
      state[setName] = new Set(defaults()[setName]);
    }
    _change();
  }

  function _setHourPreset(presetName) {
    state.hour = new Set(HOUR_PRESETS[presetName]);
    _change();
  }

  function _setAllHours() { state.hour = new Set(ALL_HOURS); _change(); }
  function _setAllDows()  { state.dow = new Set(ALL_DOWS); _change(); }
  function _setAllYears() { state.year = new Set(availableYears); _change(); }

  function _isPresetActive(presetName) {
    const presetSet = HOUR_PRESETS[presetName];
    if (presetSet.length !== state.hour.size) return false;
    return presetSet.every(h => state.hour.has(h));
  }

  function summary() {
    const yearCount = state.year.size;
    const isAllYears = yearCount === availableYears.length;
    const yearPart = isAllYears ? 'All years' : `${yearCount} years`;
    const isAllHours = state.hour.size === ALL_HOURS.length;
    let hourPart = isAllHours ? 'All 24h' : `${state.hour.size}h`;
    for (const [name, hrs] of Object.entries(HOUR_PRESETS)) {
      if (hrs.length === state.hour.size && hrs.every(h => state.hour.has(h))) {
        hourPart = name; break;
      }
    }
    const dowPart = state.dow.size === 5 && [0,1,2,3,4].every(d => state.dow.has(d))
      ? 'Mon-Fri'
      : state.dow.size === 7 ? 'All days'
      : `${state.dow.size} days`;
    const dirPart = state.direction === 'both' ? '' : ` · ${state.direction}`;
    return `${yearPart} · ${hourPart} · ${dowPart}${dirPart} · min n=${state.minCount}`;
  }

  function render() {
    const fbId = `fb-${Math.random().toString(36).slice(2, 8)}`;
    const yearChips = availableYears.map(y =>
      `<button class="fb-chip" data-active="${state.year.has(y)}" data-fb-action="toggle-year" data-fb-value="${y}">${y}</button>`
    ).join('');
    const yearAllActive = state.year.size === availableYears.length;

    const presetChips = Object.keys(HOUR_PRESETS).map(name =>
      `<button class="fb-chip" data-preset="true" data-active="${_isPresetActive(name)}" data-fb-action="hour-preset" data-fb-value="${name}">${name}</button>`
    ).join('');

    const hourChips = ALL_HOURS.map(h =>
      `<button class="fb-chip" data-active="${state.hour.has(h)}" data-fb-action="toggle-hour" data-fb-value="${h}">${h.toString().padStart(2,'0')}</button>`
    ).join('');

    const dowChips = ALL_DOWS.map(d =>
      `<button class="fb-chip" data-active="${state.dow.has(d)}" data-fb-action="toggle-dow" data-fb-value="${d}">${DOW_NAMES[d]}</button>`
    ).join('');

    const showDirection = dimensions.includes('direction');
    const directionBlock = showDirection ? `
      <div class="fb-group">
        <span class="fb-group-label">Direction</span>
        <button class="fb-chip" data-preset="true" data-active="${state.direction==='both'}" data-fb-action="set-direction" data-fb-value="both">Both</button>
        <button class="fb-chip" data-preset="true" data-active="${state.direction==='bullish'}" data-fb-action="set-direction" data-fb-value="bullish">Bullish</button>
        <button class="fb-chip" data-preset="true" data-active="${state.direction==='bearish'}" data-fb-action="set-direction" data-fb-value="bearish">Bearish</button>
      </div>
    ` : '';

    containerEl.innerHTML = `
      <div class="filter-bar collapsible" data-collapsed="${state.collapsed}" id="${fbId}">
        <div class="fb-header" data-fb-action="toggle-collapsed">
          <span class="fb-toggle">▼</span>
          <span class="fb-summary">${summary()}</span>
        </div>
        <div class="fb-body">
          <div class="fb-group">
            <span class="fb-group-label">Year</span>
            <button class="fb-chip" data-preset="true" data-active="${yearAllActive}" data-fb-action="all-years">All</button>
            ${yearChips}
          </div>
          <div class="fb-group">
            <span class="fb-group-label">Session</span>
            ${presetChips}
          </div>
          <div class="fb-group">
            <span class="fb-group-label">Hour</span>
            ${hourChips}
          </div>
          <div class="fb-group">
            <span class="fb-group-label">DOW</span>
            <button class="fb-chip" data-preset="true" data-active="${state.dow.size===7}" data-fb-action="all-dows">All</button>
            ${dowChips}
          </div>
          ${directionBlock}
          <div class="fb-group">
            <span class="fb-group-label">Min n</span>
            <input class="fb-input" type="number" value="${state.minCount}" min="0" step="10" data-fb-action="set-min-count" />
          </div>
        </div>
      </div>
    `;

    // Wire actions
    const root = document.getElementById(fbId);
    root.addEventListener('click', (e) => {
      const t = e.target.closest('[data-fb-action]');
      if (!t) return;
      const action = t.dataset.fbAction;
      const v = t.dataset.fbValue;
      if (action === 'toggle-collapsed') { state.collapsed = !state.collapsed; _change(); }
      else if (action === 'toggle-year')  _toggleSet('year', Number(v));
      else if (action === 'all-years')    _setAllYears();
      else if (action === 'hour-preset')  _setHourPreset(v);
      else if (action === 'toggle-hour')  _toggleSet('hour', Number(v));
      else if (action === 'toggle-dow')   _toggleSet('dow', Number(v));
      else if (action === 'all-dows')     _setAllDows();
      else if (action === 'set-direction'){ state.direction = v; _change(); }
    });
    root.addEventListener('change', (e) => {
      if (e.target.dataset.fbAction === 'set-min-count') {
        const n = parseInt(e.target.value, 10);
        if (!Number.isNaN(n) && n >= 0) { state.minCount = n; _change(); }
      }
    });
  }

  function whereClause() {
    if (!state) return '1=1';
    const parts = [];
    if (state.year.size && state.year.size < availableYears.length) {
      parts.push(`year IN (${[...state.year].join(',')})`);
    }
    if (state.hour.size < ALL_HOURS.length) {
      parts.push(`hour_of_day_et IN (${[...state.hour].join(',')})`);
    }
    if (state.dow.size < 7) {
      parts.push(`dow IN (${[...state.dow].join(',')})`);
    }
    return parts.length ? parts.join(' AND ') : '1=1';
  }

  function getState() { return _serialize(); }
  function getMinCount() { return state ? state.minCount : 0; }
  function getDirection() { return state ? state.direction : 'both'; }
  function getYears() { return state ? [...state.year] : []; }
  function getHours() { return state ? [...state.hour] : []; }
  function getDows()  { return state ? [...state.dow] : []; }
  function getActiveAvailableYears() { return availableYears.slice(); }

  return {
    init, render, whereClause,
    setActiveYears,
    state: getState,
    minCount: getMinCount, direction: getDirection,
    years: getYears, hours: getHours, dows: getDows,
    availableYears: getActiveAvailableYears,
    HOUR_PRESETS, ALL_HOURS, ALL_DOWS, DOW_NAMES,
  };
})();
```

- [ ] **Step 2: Syntax check**

```bash
node --check /Users/abhi/Projects/Statistic.ally/Analysis/dashboard/shared.js
```
Expected: no output (success).

- [ ] **Step 3: Smoke-test in browser**

Create a temporary HTML test file at `/tmp/test-filterbar.html`:

```html
<!DOCTYPE html>
<html data-theme="dark">
<head>
  <link rel="stylesheet" href="http://localhost:8001/Analysis/dashboard/shared.css" />
</head>
<body style="padding:20px;">
  <div id="filters"></div>
  <pre id="out" style="color:#e2eaf4;font-family:monospace;"></pre>
  <script src="http://localhost:8001/Analysis/dashboard/shared.js"></script>
  <script>
    function update() {
      document.getElementById('out').textContent =
        'WHERE: ' + FilterBar.whereClause() + '\n' +
        'state: ' + JSON.stringify(FilterBar.state(), null, 2);
    }
    FilterBar.init(document.getElementById('filters'), 'test', ['year','hour','dow','direction','minCount'], update, { years: [2024, 2025, 2026] });
    update();
  </script>
</body>
</html>
```

Then start server, copy the file in, and open in the browser:

```bash
cd /Users/abhi/Projects/Statistic.ally
(pgrep -f "http.server 8001" || python3 -m http.server 8001 &) && sleep 2
cp /tmp/test-filterbar.html .
echo "Open: http://localhost:8001/test-filterbar.html"
echo "Verify: filter chips render, clicking toggles them, the WHERE clause and state JSON update on each click."
echo "When done: rm test-filterbar.html"
```

This is a **manual** validation step. You should see filter pills, be able to click them to toggle, see the summary line update, see the WHERE clause update, and verify the JSON state changes. Cleanup: `rm /Users/abhi/Projects/Statistic.ally/test-filterbar.html` and `pkill -f "http.server 8001" || true`.

- [ ] **Step 4: Commit**

```bash
cd /Users/abhi/Projects/Statistic.ally
git add Analysis/dashboard/shared.js
git commit -m "Analysis dashboard: FilterBar component with chip selectors + persistence"
```

---

## Task 3: Inline-bar table renderer + headline insight + helpers

**Files:**
- Modify: `Analysis/dashboard/shared.js`

- [ ] **Step 1: Append the helpers**

Add to the bottom of `Analysis/dashboard/shared.js`:

```javascript
// ── Inline-bar table renderer ────────────────────────────────
// Usage:
//   renderInlineBarTable(el, rows, [
//     { key: 'quarter',   label: 'Q', type: 'label' },
//     { key: 'hi_pct',    label: 'High lands here', type: 'baseline',
//       baseline: 0.25, maxPct: 0.5, colorAbove: 'green', colorBelow: 'blue' },
//     { key: 'count',     label: 'n', type: 'count' },
//   ], { minCount: 30, dimRowFn: (r) => r.year !== 2025 });

window.renderInlineBarTable = function (el, rows, columnSpec, opts = {}) {
  const minCount = opts.minCount || 0;
  const dimRowFn = opts.dimRowFn || null;

  const head = '<thead><tr>' + columnSpec.map(c => {
    const cls = c.type === 'label' ? 'label' : '';
    return `<th class="${cls}">${escapeHtml(c.label)}</th>`;
  }).join('') + '</tr></thead>';

  const body = '<tbody>' + rows.map(r => {
    const lowCount = r.count != null && r.count < minCount;
    const dimByFn = dimRowFn ? dimRowFn(r) : false;
    const rowClass = (lowCount || dimByFn) ? ' class="dim"' : '';
    return `<tr${rowClass}>` + columnSpec.map(c => renderCell(r, c)).join('') + '</tr>';
  }).join('') + '</tbody>';

  el.innerHTML = `<table class="ibt">${head}${body}</table>`;
};

function renderCell(row, col) {
  const v = row[col.key];
  if (col.type === 'label') {
    return `<td class="label">${escapeHtml(col.formatter ? col.formatter(v, row) : v)}</td>`;
  }
  if (col.type === 'count') {
    return `<td>${v == null ? '—' : Number(v).toLocaleString()}</td>`;
  }
  if (col.type === 'num') {
    if (v == null || isNaN(v)) return '<td>—</td>';
    const formatted = col.formatter ? col.formatter(v, row) : Number(v).toFixed(col.digits ?? 2);
    const unit = col.unit ? ` ${col.unit}` : '';
    return `<td>${formatted}${unit}</td>`;
  }
  if (col.type === 'pct') {
    if (v == null || isNaN(v)) return '<td>—</td>';
    return `<td>${(v * 100).toFixed(1)}%</td>`;
  }
  if (col.type === 'inlineBar' || col.type === 'baseline') {
    return `<td class="ibt-bar-cell">${renderBarCell(v, col)}</td>`;
  }
  return `<td>${v == null ? '—' : escapeHtml(String(v))}</td>`;
}

function renderBarCell(value, col) {
  if (value == null || isNaN(value)) return '—';
  const isPct = col.type === 'baseline' || col.unit === '%' || col.maxPct != null;
  // Determine bar fill width as percent of track
  const max = col.maxPct != null ? col.maxPct
            : col.maxValue != null ? col.maxValue
            : isPct ? 1.0 : 1.0;
  const widthPct = Math.max(0, Math.min(100, (value / max) * 100));
  // Determine color
  let colorClass = 'bar-neutral';
  if (col.type === 'baseline' && col.baseline != null) {
    colorClass = value >= col.baseline ? `bar-${col.colorAbove || 'green'}` : `bar-${col.colorBelow || 'blue'}`;
  } else if (col.color) {
    colorClass = `bar-${col.color}`;
  }
  // Format displayed value
  const display = isPct
    ? `${(value * 100).toFixed(1)}%`
    : col.formatter ? col.formatter(value)
    : Number(value).toFixed(col.digits ?? 2);
  // Optional baseline marker
  let baseline = '';
  if (col.type === 'baseline' && col.baseline != null && max > 0) {
    const baseLeft = (col.baseline / max) * 100;
    baseline = `<div class="ibt-baseline" style="left:${baseLeft}%"></div>`;
  }
  return `<div class="ibt-bar-track">
    <div class="ibt-bar-fill ${colorClass}" style="width:${widthPct}%"></div>
    ${baseline}
    <div class="ibt-bar-label">${display}</div>
  </div>`;
}

function escapeHtml(s) {
  if (s == null) return '';
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// ── Headline insight ─────────────────────────────────────────
// Usage:
//   renderHeadline(el, 'Q${topQuarter} contains the high ${topPct} of the time.',
//                  { topQuarter: 1, topPct: '36.4%' });
window.renderHeadline = function (el, template, vars, opts = {}) {
  if (!vars) {
    el.innerHTML = `<div class="headline warn">Not enough data for this slice.</div>`;
    return;
  }
  const text = template.replace(/\$\{(\w+)\}/g, (_, k) => {
    const v = vars[k];
    return v == null ? '—' : escapeHtml(String(v));
  });
  const cls = opts.warn ? ' warn' : '';
  el.innerHTML = `<div class="headline${cls}">${text}</div>`;
};

// ── Donut (CSS conic-gradient) ───────────────────────────────
// Usage:
//   renderDonut(el, [
//     { label: 'H first', value: 0.47, color: 'var(--green)' },
//     { label: 'L first', value: 0.51, color: 'var(--red)' },
//     { label: 'Tie',     value: 0.02, color: 'var(--text-muted)' },
//   ], { centerText: '47% / 51% / 2%' });

window.renderDonut = function (el, segments, opts = {}) {
  const total = segments.reduce((s, x) => s + x.value, 0);
  if (total <= 0) { el.innerHTML = '<div class="headline warn">No data.</div>'; return; }
  const stops = [];
  let cumulative = 0;
  for (const seg of segments) {
    const start = (cumulative / total) * 360;
    cumulative += seg.value;
    const end = (cumulative / total) * 360;
    stops.push(`${seg.color} ${start}deg ${end}deg`);
  }
  const conic = `conic-gradient(${stops.join(', ')})`;
  const center = opts.centerText ? `<div class="donut-center">${escapeHtml(opts.centerText)}</div>` : '';
  const legend = segments.map(s =>
    `<div><span class="swatch" style="background:${s.color}"></span>${escapeHtml(s.label)}: ${(s.value * 100 / total).toFixed(1)}%</div>`
  ).join('');
  el.innerHTML = `
    <div class="donut" style="background:${conic}">${center}</div>
    <div class="donut-legend">${legend}</div>
  `;
};

// ── Heatmap (rectangular) ────────────────────────────────────
// Usage:
//   renderHeatmap(el, {
//     rowLabels: ['00','01',...'23'], colLabels: ['Mon','Tue','Wed','Thu','Fri'],
//     values: [[0.42, 0.51, ...], ...],   // rows × cols
//     counts: [[123, 145, ...], ...],
//     colorScale: 'green-red',            // green high → red low
//     minCount: 30,
//     fmt: (v) => (v*100).toFixed(0)+'%',
//     tooltip: (r,c) => `Mon hour 09 — bull FT 64% (n=145)`,
//   });

window.renderHeatmap = function (el, cfg) {
  const { rowLabels, colLabels, values, counts, fmt, minCount = 0, tooltip } = cfg;
  const allVals = values.flat().filter(v => v != null && !isNaN(v));
  const vMin = Math.min(...allVals);
  const vMax = Math.max(...allVals);
  const range = vMax - vMin || 1;

  function colorFor(v) {
    if (v == null || isNaN(v)) return 'transparent';
    const t = (v - vMin) / range; // 0 (low) → 1 (high)
    // green-amber-red scale
    if (t > 0.5) {
      const a = (t - 0.5) * 2;
      return `rgba(16,185,129,${0.15 + a * 0.55})`;
    } else {
      const a = (0.5 - t) * 2;
      return `rgba(239,68,68,${0.15 + a * 0.55})`;
    }
  }

  const cols = colLabels.length;
  let html = `<div class="hm" style="grid-template-columns: 60px repeat(${cols}, 1fr)">`;
  // Header row
  html += `<div class="hm-axis"></div>`;
  for (const c of colLabels) html += `<div class="hm-axis center">${escapeHtml(c)}</div>`;
  // Body
  for (let r = 0; r < rowLabels.length; r++) {
    html += `<div class="hm-axis right">${escapeHtml(rowLabels[r])}</div>`;
    for (let c = 0; c < cols; c++) {
      const v = values[r]?.[c];
      const n = counts ? counts[r]?.[c] : null;
      const dim = (n != null && n < minCount) ? ' dim' : '';
      const tip = tooltip ? tooltip(r, c, v, n) : '';
      const tipAttr = tip ? ` title="${escapeHtml(tip)}"` : '';
      if (v == null || isNaN(v)) {
        html += `<div class="hm-cell empty"${tipAttr}>—</div>`;
      } else {
        html += `<div class="hm-cell${dim}" style="background:${colorFor(v)}"${tipAttr}>${fmt ? fmt(v) : v.toFixed(2)}</div>`;
      }
    }
  }
  html += `</div>`;
  el.innerHTML = html;
};

// ── Cross-tab heatmap (4×4) ──────────────────────────────────
// Used by quarter study A. Same shape as renderHeatmap but smaller and labels axes.

window.renderCrossTab = function (el, cfg) {
  const { rowLabels, colLabels, values, fmt, rowAxisLabel = '', colAxisLabel = '' } = cfg;
  const allVals = values.flat().filter(v => v != null && !isNaN(v));
  const vMax = Math.max(...allVals);
  function colorFor(v) {
    if (v == null) return 'transparent';
    const t = vMax > 0 ? v / vMax : 0;
    return `rgba(16,185,129,${0.10 + t * 0.50})`;
  }
  let html = `<div class="crosstab">`;
  html += `<div class="crosstab-corner">${escapeHtml(rowAxisLabel)}\\${escapeHtml(colAxisLabel)}</div>`;
  for (const c of colLabels) html += `<div class="crosstab-axis">${escapeHtml(c)}</div>`;
  for (let r = 0; r < rowLabels.length; r++) {
    html += `<div class="crosstab-axis">${escapeHtml(rowLabels[r])}</div>`;
    for (let c = 0; c < colLabels.length; c++) {
      const v = values[r][c];
      const diag = r === c ? ' diag' : '';
      html += `<div class="crosstab-cell${diag}" style="background:${colorFor(v)}">${fmt ? fmt(v) : v}</div>`;
    }
  }
  html += `</div>`;
  el.innerHTML = html;
};
```

- [ ] **Step 2: Syntax check**

```bash
node --check /Users/abhi/Projects/Statistic.ally/Analysis/dashboard/shared.js
```
Expected: no output (success).

- [ ] **Step 3: Smoke-test the renderers**

Update `/tmp/test-filterbar.html` (or create `/tmp/test-renderers.html`) with the following body:

```html
<!DOCTYPE html>
<html data-theme="dark">
<head>
  <link rel="stylesheet" href="http://localhost:8001/Analysis/dashboard/shared.css" />
</head>
<body style="padding:20px;">
  <div class="container">
    <div id="headline"></div>
    <div class="card"><div id="bartable"></div></div>
    <div class="card"><div id="donut"></div></div>
    <div class="card"><div id="heatmap"></div></div>
    <div class="card"><div id="crosstab"></div></div>
  </div>
  <script src="http://localhost:8001/Analysis/dashboard/shared.js"></script>
  <script>
    renderHeadline(document.getElementById('headline'),
      'Q${topQuarter} contains the high ${topPct} of the time, well above the ${baseline} baseline.',
      { topQuarter: 1, topPct: '36.4%', baseline: '25%' });

    renderInlineBarTable(document.getElementById('bartable'),
      [
        { quarter: 'Q1', hi_pct: 0.364, count: 59340 },
        { quarter: 'Q2', hi_pct: 0.156, count: 59340 },
        { quarter: 'Q3', hi_pct: 0.186, count: 59340 },
        { quarter: 'Q4', hi_pct: 0.294, count: 59340 },
      ], [
        { key: 'quarter', label: 'Q', type: 'label' },
        { key: 'hi_pct',  label: 'High lands here', type: 'baseline', baseline: 0.25, maxPct: 0.5,
          colorAbove: 'green', colorBelow: 'blue' },
        { key: 'count',   label: 'n',  type: 'count' },
      ]);

    renderDonut(document.getElementById('donut'),
      [
        { label: 'H first', value: 0.47, color: '#10b981' },
        { label: 'L first', value: 0.51, color: '#ef4444' },
        { label: 'Tie',     value: 0.02, color: '#8ba4bc' },
      ], { centerText: '59,340\\nhours' });

    renderHeatmap(document.getElementById('heatmap'), {
      rowLabels: ['00','01','02','09','10','11','15','16'],
      colLabels: ['Mon','Tue','Wed','Thu','Fri'],
      values: [[0.4,0.5,0.6,0.5,0.4],[0.3,0.6,0.7,0.5,0.4],[0.5,0.6,0.7,0.6,0.5],
               [0.7,0.7,0.8,0.7,0.7],[0.7,0.8,0.8,0.8,0.7],[0.6,0.7,0.7,0.7,0.6],
               [0.5,0.5,0.6,0.5,0.5],[0.4,0.4,0.5,0.4,0.4]],
      counts: [[20,40,42,41,38],[100,110,108,109,107],[100,110,108,109,107],
               [120,140,142,141,138],[120,140,142,141,138],[120,140,142,141,138],
               [120,140,142,141,138],[120,140,142,141,138]],
      fmt: (v) => (v*100).toFixed(0)+'%',
      minCount: 30,
    });

    renderCrossTab(document.getElementById('crosstab'), {
      rowAxisLabel: 'q_hi', colAxisLabel: 'q_lo',
      rowLabels: ['Q1','Q2','Q3','Q4'], colLabels: ['Q1','Q2','Q3','Q4'],
      values: [[0.05,0.08,0.10,0.15],[0.04,0.02,0.04,0.06],
               [0.05,0.04,0.03,0.07],[0.10,0.08,0.07,0.04]],
      fmt: (v) => (v*100).toFixed(1)+'%',
    });
  </script>
</body>
</html>
```

```bash
cd /Users/abhi/Projects/Statistic.ally
(pgrep -f "http.server 8001" || python3 -m http.server 8001 &) && sleep 2
cp /tmp/test-renderers.html .
echo "Open: http://localhost:8001/test-renderers.html"
```

Manually verify each component renders. Then cleanup: `rm /Users/abhi/Projects/Statistic.ally/test-renderers.html` and `pkill -f "http.server 8001" || true`.

- [ ] **Step 4: Commit**

```bash
cd /Users/abhi/Projects/Statistic.ally
git add Analysis/dashboard/shared.js
git commit -m "Analysis dashboard: inline-bar table + headline + donut + heatmap renderers"
```

---

## Task 4: Rewrite breakout.html — hero + filter bar + scaffolding

**Files:**
- Rewrite: `Analysis/dashboard/breakout.html`

- [ ] **Step 1: Replace breakout.html with the new layout (hero + 6 panels, panel content empty for now)**

Write the following to `/Users/abhi/Projects/Statistic.ally/Analysis/dashboard/breakout.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Breakout Follow-Through · NQ Hourly</title>
  <link rel="stylesheet" href="shared.css" />
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;700&family=IBM+Plex+Mono:wght@400;500;600&family=Inter:wght@400;500&display=swap" rel="stylesheet" />
</head>
<body>
  <button class="theme-toggle" onclick="toggleTheme()">theme</button>
  <div class="container">
    <nav><a href="index.html">← Hourly Analysis</a></nav>
    <h1>Breakout Follow-Through</h1>

    <div id="filters"></div>

    <div class="hero-pair">
      <div class="hero-panel bull" id="hero-bull">
        <div class="hero-eyebrow">▲ BULLISH BREAKOUT</div>
        <div class="hero-line">Loading…</div>
      </div>
      <div class="hero-panel bear" id="hero-bear">
        <div class="hero-eyebrow">▼ BEARISH BREAKOUT</div>
        <div class="hero-line">Loading…</div>
      </div>
    </div>

    <div class="card">
      <h2 style="margin-top:0;">Quarter-of-H2 takeout attribution</h2>
      <div id="hl-takeout"></div>
      <div class="study-section"><div class="study-section-title">Bullish follow-throughs</div><div id="t-takeout-bull"></div></div>
      <div class="study-section"><div class="study-section-title">Bearish follow-throughs</div><div id="t-takeout-bear"></div></div>
    </div>

    <div class="card">
      <h2 style="margin-top:0;">H1 open vs prev-hour mid (conditioning)</h2>
      <div id="hl-prevmid"></div>
      <div class="four-col" id="t-prevmid"></div>
    </div>

    <div class="card">
      <h2 style="margin-top:0;">By year</h2>
      <div id="t-by-year"></div>
    </div>

    <div class="card">
      <h2 style="margin-top:0;">By hour-of-day (ET)</h2>
      <div id="t-by-hour"></div>
    </div>

    <div class="card">
      <h2 style="margin-top:0;">By day-of-week</h2>
      <div id="t-by-dow"></div>
    </div>

    <div class="card">
      <h2 style="margin-top:0;">Hour × DOW heatmap (bullish follow-through %)</h2>
      <div id="t-grid"></div>
    </div>
  </div>

  <script src="shared.js"></script>
  <script>
    const DOW_NAMES = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];

    async function init() {
      // Load all parquet sources upfront
      await loadParquet('../data/breakout/breakouts.parquet', 'events');
      await loadParquet('../data/breakout/summary_aggregate.parquet', 's_agg');
      await loadParquet('../data/breakout/summary_by_year.parquet', 's_year');
      await loadParquet('../data/breakout/summary_by_hour.parquet', 's_hour');
      await loadParquet('../data/breakout/summary_by_dow.parquet', 's_dow');
      await loadParquet('../data/breakout/summary_grid.parquet', 's_grid');

      // Discover available years from the events table for the filter bar
      const years = (await query('SELECT DISTINCT year FROM events ORDER BY year')).map(r => Number(r.year));

      await FilterBar.init(
        document.getElementById('filters'),
        'breakout',
        ['year', 'hour', 'dow', 'direction', 'minCount'],
        () => render(),
        { years }
      );
      await render();
    }

    async function render() {
      // Subsequent tasks fill these in
      await renderHero();
    }

    async function renderHero() {
      const where = FilterBar.whereClause();
      // Aggregate metrics over filtered events
      const sql = `
        SELECT
          COUNT(*) AS n_total,
          COUNT(*) FILTER (WHERE breakout != 'no_prev') AS n_classifiable,
          COUNT(*) FILTER (WHERE breakout = 'bullish') AS n_bullish,
          COUNT(*) FILTER (WHERE breakout = 'bearish') AS n_bearish,
          AVG(CASE WHEN breakout = 'bullish' AND followthrough THEN 1.0
                   WHEN breakout = 'bullish' THEN 0.0 END)        AS bull_ft,
          AVG(CASE WHEN breakout = 'bearish' AND followthrough THEN 1.0
                   WHEN breakout = 'bearish' THEN 0.0 END)        AS bear_ft,
          AVG(CASE WHEN breakout = 'bullish' AND immediate_reversal THEN 1.0
                   WHEN breakout = 'bullish' THEN 0.0 END)        AS bull_rev,
          AVG(CASE WHEN breakout = 'bearish' AND immediate_reversal THEN 1.0
                   WHEN breakout = 'bearish' THEN 0.0 END)        AS bear_rev
        FROM events
        WHERE ${where}
      `;
      const row = (await query(sql))[0];
      const n_class = Number(row.n_classifiable) || 0;
      const n_bull = Number(row.n_bullish) || 0;
      const n_bear = Number(row.n_bearish) || 0;
      const bull_rate = n_class > 0 ? n_bull / n_class : null;
      const bear_rate = n_class > 0 ? n_bear / n_class : null;
      const bull_ft = row.bull_ft;
      const bear_ft = row.bear_ft;
      const bull_rev = row.bull_rev;
      const bear_rev = row.bear_rev;

      const dir = FilterBar.direction();
      document.getElementById('hero-bull').classList.toggle('dimmed', dir === 'bearish');
      document.getElementById('hero-bear').classList.toggle('dimmed', dir === 'bullish');

      const ftBull = bull_rate != null
        ? Math.round(bull_rate * n_class)
        : 0;
      const ftBullCount = Math.round((bull_ft || 0) * n_bull);
      const ftBearCount = Math.round((bear_ft || 0) * n_bear);

      document.getElementById('hero-bull').innerHTML = `
        <div class="hero-eyebrow">▲ BULLISH BREAKOUT</div>
        <div class="hero-line">Happens in</div>
        <div class="hero-big">${fmtPct(bull_rate)}</div>
        <div class="hero-line">of classifiable hours (${fmtNum(n_bull)} events)</div>
        <div class="hero-divider"></div>
        <div class="hero-line">When it does, next hour follows through</div>
        <div class="hero-mid">${fmtPct(bull_ft)}</div>
        <div class="hero-foot">${fmtNum(ftBullCount)} of ${fmtNum(n_bull)} cases</div>
        <div class="hero-foot warn">Reversal: ${fmtPct(bull_rev)}</div>
      `;
      document.getElementById('hero-bear').innerHTML = `
        <div class="hero-eyebrow">▼ BEARISH BREAKOUT</div>
        <div class="hero-line">Happens in</div>
        <div class="hero-big">${fmtPct(bear_rate)}</div>
        <div class="hero-line">of classifiable hours (${fmtNum(n_bear)} events)</div>
        <div class="hero-divider"></div>
        <div class="hero-line">When it does, next hour follows through</div>
        <div class="hero-mid">${fmtPct(bear_ft)}</div>
        <div class="hero-foot">${fmtNum(ftBearCount)} of ${fmtNum(n_bear)} cases</div>
        <div class="hero-foot warn">Reversal: ${fmtPct(bear_rev)}</div>
      `;
    }

    init().catch(e => alert('Failed to load: ' + e.message));
  </script>
</body>
</html>
```

- [ ] **Step 2: Syntax check the inline JS**

```bash
python3 -c "
import re
with open('/Users/abhi/Projects/Statistic.ally/Analysis/dashboard/breakout.html') as f:
    html = f.read()
scripts = re.findall(r'<script>(.*?)</script>', html, re.DOTALL)
with open('/tmp/inline_breakout.js', 'w') as f:
    f.write(scripts[0])
"
node --check /tmp/inline_breakout.js
```
Expected: no output (success).

- [ ] **Step 3: Manual browser validation**

```bash
cd /Users/abhi/Projects/Statistic.ally
(pgrep -f "http.server 8001" || python3 -m http.server 8001 &) && sleep 2
echo "Open: http://localhost:8001/Analysis/dashboard/breakout.html"
```

Verify:
- Filter bar renders at the top with collapsible header showing summary
- Two hero panels (green Bull, red Bear) with all numbers populated
- Six empty panel cards below (no content yet — they're filled in by Tasks 5-9)
- Click filter chips → hero panels update with new numbers
- Click "Bullish only" direction → bear panel dims; click "Both" → both visible
- Reload page → filter state persists

Cleanup: `pkill -f "http.server 8001" || true`

- [ ] **Step 4: Commit**

```bash
cd /Users/abhi/Projects/Statistic.ally
git add Analysis/dashboard/breakout.html
git commit -m "Analysis dashboard: breakout.html — filter bar + bull/bear hero panels"
```

---

## Task 5: Breakout — quarter-of-H2 takeout attribution panel

**Files:**
- Modify: `Analysis/dashboard/breakout.html`

- [ ] **Step 1: Add the renderTakeout function and call it from render()**

Find the inline `<script>` section. After `renderHero()` is defined and before `init().catch(...)`, add:

```javascript
    async function renderTakeout() {
      const where = FilterBar.whereClause();
      const dir = FilterBar.direction();
      const minCount = FilterBar.minCount();

      async function getRows(direction) {
        const sql = `
          SELECT takeout_quarter_of_h2 AS q, COUNT(*) AS n
          FROM events
          WHERE ${where}
            AND breakout = '${direction}'
            AND followthrough = TRUE
            AND takeout_quarter_of_h2 IS NOT NULL
          GROUP BY q ORDER BY q
        `;
        const rows = await query(sql);
        const total = rows.reduce((s, r) => s + Number(r.n), 0);
        const byQ = { 1: 0, 2: 0, 3: 0, 4: 0 };
        for (const r of rows) byQ[Number(r.q)] = Number(r.n);
        return { byQ, total };
      }

      const bull = await getRows('bullish');
      const bear = await getRows('bearish');

      // Headline insight: which quarter dominates for bull (since direction-symmetric)
      const dominantBull = Object.entries(bull.byQ).sort((a, b) => b[1] - a[1])[0];
      if (bull.total > 0) {
        const dPct = (dominantBull[1] / bull.total * 100).toFixed(0);
        renderHeadline(document.getElementById('hl-takeout'),
          'Most bull follow-throughs happen in Q${q} (${pct}%) — momentum after a breakout is fast.',
          { q: dominantBull[0], pct: dPct });
      } else {
        renderHeadline(document.getElementById('hl-takeout'), null);
      }

      function rowsFor(byQ, total) {
        return [1, 2, 3, 4].map(q => ({
          q: `Q${q}`,
          pct: total > 0 ? byQ[q] / total : 0,
          count: total,
        }));
      }

      const cols = [
        { key: 'q', label: 'Quarter of H2', type: 'label' },
        { key: 'pct', label: '% of follow-throughs', type: 'inlineBar', maxPct: 1.0, color: 'green' },
      ];
      const colsBear = cols.slice();
      colsBear[1] = { ...colsBear[1], color: 'red' };

      // Show or hide based on direction filter
      const bullEl = document.getElementById('t-takeout-bull');
      const bearEl = document.getElementById('t-takeout-bear');
      bullEl.parentElement.style.display = (dir === 'bearish') ? 'none' : '';
      bearEl.parentElement.style.display = (dir === 'bullish') ? 'none' : '';

      bullEl.parentElement.querySelector('.study-section-title').textContent =
        `Bullish follow-throughs (n=${fmtNum(bull.total)})`;
      bearEl.parentElement.querySelector('.study-section-title').textContent =
        `Bearish follow-throughs (n=${fmtNum(bear.total)})`;

      renderInlineBarTable(bullEl, rowsFor(bull.byQ, bull.total), cols, { minCount });
      renderInlineBarTable(bearEl, rowsFor(bear.byQ, bear.total), colsBear, { minCount });
    }
```

Then update the `render()` function:

```javascript
    async function render() {
      await renderHero();
      await renderTakeout();
    }
```

- [ ] **Step 2: Syntax check + browser validation**

Same node check as Task 4:
```bash
python3 -c "
import re
with open('/Users/abhi/Projects/Statistic.ally/Analysis/dashboard/breakout.html') as f:
    html = f.read()
scripts = re.findall(r'<script>(.*?)</script>', html, re.DOTALL)
open('/tmp/inline_breakout.js', 'w').write(scripts[0])
"
node --check /tmp/inline_breakout.js
```

Then:
```bash
cd /Users/abhi/Projects/Statistic.ally
(pgrep -f "http.server 8001" || python3 -m http.server 8001 &) && sleep 2
echo "Open: http://localhost:8001/Analysis/dashboard/breakout.html"
```

Verify:
- Quarter-of-H2 attribution panel populates with 2 sub-tables (bull + bear), each with 4 quarters
- Bars are visible with correct percentages summing to 100%
- Headline insight at top of the panel mentions the dominant quarter
- Direction filter "Bullish only" hides the bear table
- Filter changes update the numbers

Cleanup: `pkill -f "http.server 8001" || true`

- [ ] **Step 3: Commit**

```bash
cd /Users/abhi/Projects/Statistic.ally
git add Analysis/dashboard/breakout.html
git commit -m "Analysis dashboard: breakout — quarter-of-H2 takeout attribution panel"
```

---

## Task 6: Breakout — H1 open vs prev-mid conditioning panel

**Files:**
- Modify: `Analysis/dashboard/breakout.html`

- [ ] **Step 1: Add renderPrevMid function and call from render()**

Add a new function inside the inline `<script>`, after `renderTakeout`:

```javascript
    async function renderPrevMid() {
      const where = FilterBar.whereClause();
      const minCount = FilterBar.minCount();

      const sql = `
        SELECT breakout, h1_open_vs_prev_mid AS side,
               COUNT(*) AS n,
               AVG(CASE WHEN followthrough THEN 1.0 ELSE 0.0 END) AS ft_rate
        FROM events
        WHERE ${where}
          AND breakout IN ('bullish','bearish')
          AND h1_open_vs_prev_mid IN ('above', 'below')
        GROUP BY breakout, side
      `;
      const rows = await query(sql);
      const lookup = {};
      for (const r of rows) lookup[`${r.breakout}-${r.side}`] = r;

      function card(direction, side) {
        const key = `${direction}-${side}`;
        const r = lookup[key] || { n: 0, ft_rate: null };
        const lowCount = Number(r.n) < minCount;
        const cls = direction === 'bullish' ? 'bull' : 'bear';
        const sideLabel = side === 'above' ? 'opened above prev-mid' : 'opened below prev-mid';
        return `
          <div class="stat-card ${cls}${lowCount ? ' dim' : ''}">
            <div class="stat-card-label">${direction === 'bullish' ? '▲ Bull' : '▼ Bear'} — ${sideLabel}</div>
            <div class="stat-card-value">${fmtPct(r.ft_rate)}</div>
            <div class="stat-card-sub">follow-through · n=${fmtNum(r.n)}</div>
          </div>
        `;
      }

      // Headline insight: pick bullish row that has data
      const bullAbove = lookup['bullish-above'];
      const bullBelow = lookup['bullish-below'];
      if (bullAbove && bullBelow && Number(bullAbove.n) >= minCount && Number(bullBelow.n) >= minCount) {
        renderHeadline(document.getElementById('hl-prevmid'),
          'Bull breakouts that opened ${aboveOrBelow} prev-mid follow through ${aboveBelowRate}, vs ${otherRate} when they opened the other way.',
          {
            aboveOrBelow: bullAbove.ft_rate >= bullBelow.ft_rate ? 'above' : 'below',
            aboveBelowRate: fmtPct(Math.max(bullAbove.ft_rate, bullBelow.ft_rate)),
            otherRate: fmtPct(Math.min(bullAbove.ft_rate, bullBelow.ft_rate)),
          });
      } else {
        renderHeadline(document.getElementById('hl-prevmid'), null);
      }

      document.getElementById('t-prevmid').innerHTML =
        card('bullish', 'above') +
        card('bullish', 'below') +
        card('bearish', 'above') +
        card('bearish', 'below');
    }
```

Update `render()`:

```javascript
    async function render() {
      await renderHero();
      await renderTakeout();
      await renderPrevMid();
    }
```

- [ ] **Step 2: Syntax check + browser validation**

```bash
python3 -c "
import re
html = open('/Users/abhi/Projects/Statistic.ally/Analysis/dashboard/breakout.html').read()
scripts = re.findall(r'<script>(.*?)</script>', html, re.DOTALL)
open('/tmp/inline_breakout.js', 'w').write(scripts[0])
"
node --check /tmp/inline_breakout.js
```

Then:
```bash
cd /Users/abhi/Projects/Statistic.ally
(pgrep -f "http.server 8001" || python3 -m http.server 8001 &) && sleep 2
echo "Open: http://localhost:8001/Analysis/dashboard/breakout.html"
```

Verify:
- 4 stat cards in 2×2 grid (bull/above, bull/below, bear/above, bear/below)
- Each card shows follow-through % and sample count
- Headline above explains the bullish open-vs-mid asymmetry
- Filter changes update the cards

Cleanup: `pkill -f "http.server 8001" || true`

- [ ] **Step 3: Commit**

```bash
cd /Users/abhi/Projects/Statistic.ally
git add Analysis/dashboard/breakout.html
git commit -m "Analysis dashboard: breakout — H1 open vs prev-mid conditioning panel"
```

---

## Task 7: Breakout — by-year, by-hour, by-DOW breakdown panels

**Files:**
- Modify: `Analysis/dashboard/breakout.html`

- [ ] **Step 1: Add a shared breakdown renderer**

Add inside the inline `<script>`, after `renderPrevMid`:

```javascript
    async function renderBreakdowns() {
      const where = FilterBar.whereClause();
      const minCount = FilterBar.minCount();
      const dir = FilterBar.direction();
      const activeYears = new Set(FilterBar.years());
      const activeHours = new Set(FilterBar.hours());
      const activeDows = new Set(FilterBar.dows());

      // Common SQL pattern: aggregate over events at the slice-key level,
      // computing classifiable count, bull rate, bear rate, bull FT, bear FT.
      function sliceSql(keyExpr) {
        return `
          SELECT ${keyExpr} AS k,
                 COUNT(*) AS n,
                 COUNT(*) FILTER (WHERE breakout != 'no_prev') AS n_class,
                 COUNT(*) FILTER (WHERE breakout = 'bullish') AS n_bull,
                 COUNT(*) FILTER (WHERE breakout = 'bearish') AS n_bear,
                 AVG(CASE WHEN breakout = 'bullish' AND followthrough THEN 1.0
                          WHEN breakout = 'bullish' THEN 0.0 END) AS bull_ft,
                 AVG(CASE WHEN breakout = 'bearish' AND followthrough THEN 1.0
                          WHEN breakout = 'bearish' THEN 0.0 END) AS bear_ft
          FROM events
          GROUP BY k ORDER BY k
        `;
      }

      function transform(rows) {
        return rows.map(r => {
          const n_class = Number(r.n_class) || 0;
          return {
            k: r.k,
            count: Number(r.n) || 0,
            bull_rate: n_class > 0 ? Number(r.n_bull) / n_class : null,
            bear_rate: n_class > 0 ? Number(r.n_bear) / n_class : null,
            bull_ft: r.bull_ft,
            bear_ft: r.bear_ft,
          };
        });
      }

      const baseCols = (keyLabel) => {
        const cols = [
          { key: 'k', label: keyLabel, type: 'label' },
          { key: 'count', label: 'n', type: 'count' },
        ];
        if (dir !== 'bearish') {
          cols.push({ key: 'bull_rate', label: 'Bull rate', type: 'inlineBar', maxPct: 0.4, color: 'green' });
          cols.push({ key: 'bull_ft',   label: 'Bull FT',   type: 'baseline', baseline: 0.5, maxPct: 1.0, colorAbove: 'green', colorBelow: 'red' });
        }
        if (dir !== 'bullish') {
          cols.push({ key: 'bear_rate', label: 'Bear rate', type: 'inlineBar', maxPct: 0.4, color: 'red' });
          cols.push({ key: 'bear_ft',   label: 'Bear FT',   type: 'baseline', baseline: 0.5, maxPct: 1.0, colorAbove: 'red', colorBelow: 'green' });
        }
        return cols;
      };

      // By year
      const yearRows = transform(await query(sliceSql('year')));
      renderInlineBarTable(document.getElementById('t-by-year'),
        yearRows.map(r => ({ ...r, k: r.k })),
        baseCols('Year'),
        { minCount, dimRowFn: (r) => !activeYears.has(Number(r.k)) });

      // By hour-of-day
      const hourRows = transform(await query(sliceSql('hour_of_day_et')));
      renderInlineBarTable(document.getElementById('t-by-hour'),
        hourRows.map(r => ({ ...r, k: String(r.k).padStart(2, '0') + ' ET' })),
        baseCols('Hour'),
        { minCount, dimRowFn: (r) => !activeHours.has(Number(String(r.k).slice(0,2))) });

      // By DOW
      const dowRows = transform(await query(sliceSql('dow')));
      renderInlineBarTable(document.getElementById('t-by-dow'),
        dowRows.map(r => ({ ...r, k: ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][Number(r.k)] })),
        baseCols('DOW'),
        { minCount, dimRowFn: (r) => {
            const idx = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].indexOf(r.k);
            return !activeDows.has(idx);
        }});
    }
```

Update `render()`:

```javascript
    async function render() {
      await renderHero();
      await renderTakeout();
      await renderPrevMid();
      await renderBreakdowns();
    }
```

- [ ] **Step 2: Syntax check + browser validation**

```bash
python3 -c "
import re
html = open('/Users/abhi/Projects/Statistic.ally/Analysis/dashboard/breakout.html').read()
scripts = re.findall(r'<script>(.*?)</script>', html, re.DOTALL)
open('/tmp/inline_breakout.js', 'w').write(scripts[0])
"
node --check /tmp/inline_breakout.js
```

Then:
```bash
cd /Users/abhi/Projects/Statistic.ally
(pgrep -f "http.server 8001" || python3 -m http.server 8001 &) && sleep 2
echo "Open: http://localhost:8001/Analysis/dashboard/breakout.html"
```

Verify:
- By-year table shows all years (2014-2026), inline bars for bull/bear rate and FT
- By-hour table shows 24 rows (00 ET - 23 ET), inline bars
- By-dow table shows Mon-Sun
- Rows outside the active filter render dimmed (e.g. filter to 2025 only → other years dim)
- Direction filter "Bullish only" hides bear columns
- Min-count filter dims rows below threshold

Cleanup: `pkill -f "http.server 8001" || true`

- [ ] **Step 3: Commit**

```bash
cd /Users/abhi/Projects/Statistic.ally
git add Analysis/dashboard/breakout.html
git commit -m "Analysis dashboard: breakout — by-year / by-hour / by-dow breakdown panels"
```

---

## Task 8: Breakout — hour × DOW heatmap

**Files:**
- Modify: `Analysis/dashboard/breakout.html`

- [ ] **Step 1: Add renderGrid function**

Add inside the inline `<script>`, after `renderBreakdowns`:

```javascript
    async function renderGrid() {
      const minCount = FilterBar.minCount();
      const sql = `
        SELECT hour_of_day_et AS h, dow,
               COUNT(*) AS n,
               AVG(CASE WHEN breakout = 'bullish' AND followthrough THEN 1.0
                        WHEN breakout = 'bullish' THEN 0.0 END) AS bull_ft,
               AVG(CASE WHEN breakout = 'bullish' THEN 1.0 ELSE 0.0 END) AS bull_rate,
               AVG(CASE WHEN breakout = 'bearish' THEN 1.0 ELSE 0.0 END) AS bear_rate,
               AVG(CASE WHEN breakout = 'bearish' AND followthrough THEN 1.0
                        WHEN breakout = 'bearish' THEN 0.0 END) AS bear_ft
        FROM events
        GROUP BY h, dow
      `;
      const rows = await query(sql);

      // Build 24 × 7 grids
      const hourLabels = Array.from({length: 24}, (_, i) => i.toString().padStart(2, '0'));
      const dowLabels = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
      const values = Array.from({length: 24}, () => Array(7).fill(null));
      const counts = Array.from({length: 24}, () => Array(7).fill(0));
      const tooltips = Array.from({length: 24}, () => Array(7).fill(''));
      for (const r of rows) {
        const h = Number(r.h), d = Number(r.dow);
        values[h][d] = r.bull_ft;
        counts[h][d] = Number(r.n);
        tooltips[h][d] =
          `${dowLabels[d]} ${hourLabels[h]} ET\n` +
          `n=${fmtNum(r.n)}\n` +
          `Bull rate: ${fmtPct(r.bull_rate)}, FT: ${fmtPct(r.bull_ft)}\n` +
          `Bear rate: ${fmtPct(r.bear_rate)}, FT: ${fmtPct(r.bear_ft)}`;
      }

      renderHeatmap(document.getElementById('t-grid'), {
        rowLabels: hourLabels.map(h => `${h} ET`),
        colLabels: dowLabels,
        values, counts,
        fmt: (v) => v == null ? '' : (v * 100).toFixed(0) + '%',
        minCount,
        tooltip: (r, c) => tooltips[r][c],
      });
    }
```

Update `render()`:

```javascript
    async function render() {
      await renderHero();
      await renderTakeout();
      await renderPrevMid();
      await renderBreakdowns();
      await renderGrid();
    }
```

- [ ] **Step 2: Syntax check + browser validation**

```bash
python3 -c "
import re
html = open('/Users/abhi/Projects/Statistic.ally/Analysis/dashboard/breakout.html').read()
scripts = re.findall(r'<script>(.*?)</script>', html, re.DOTALL)
open('/tmp/inline_breakout.js', 'w').write(scripts[0])
"
node --check /tmp/inline_breakout.js
```

Then:
```bash
cd /Users/abhi/Projects/Statistic.ally
(pgrep -f "http.server 8001" || python3 -m http.server 8001 &) && sleep 2
echo "Open: http://localhost:8001/Analysis/dashboard/breakout.html"
```

Verify:
- Heatmap renders at the bottom: 24 rows (hours) × 7 columns (days)
- Cells are colored on a green→red scale by bull follow-through rate
- Hovering a cell shows the tooltip with bull/bear rate + FT + count
- Cells with low counts are dimmed
- Sat/Sun cells are mostly empty (no Saturday data; few Sunday hours)

Cleanup: `pkill -f "http.server 8001" || true`

- [ ] **Step 3: Commit**

```bash
cd /Users/abhi/Projects/Statistic.ally
git add Analysis/dashboard/breakout.html
git commit -m "Analysis dashboard: breakout — hour × DOW heatmap"
```

---

## Task 9: Rewrite quarters.html — sidebar nav + scaffolding + filter bar

**Files:**
- Rewrite: `Analysis/dashboard/quarters.html`

- [ ] **Step 1: Replace quarters.html with sidebar layout (study panels are stubbed; filled in by Tasks 10-15)**

Write to `/Users/abhi/Projects/Statistic.ally/Analysis/dashboard/quarters.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Quarter Study · NQ Hourly</title>
  <link rel="stylesheet" href="shared.css" />
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;700&family=IBM+Plex+Mono:wght@400;500;600&family=Inter:wght@400;500&display=swap" rel="stylesheet" />
</head>
<body>
  <button class="theme-toggle" onclick="toggleTheme()">theme</button>
  <div class="container">
    <nav><a href="index.html">← Hourly Analysis</a></nav>
    <h1>Quarter-of-the-Hour Study</h1>

    <div id="filters"></div>

    <div class="qs-layout">
      <div class="qs-sidebar" id="sidebar">
        <div class="qs-nav-item" data-study="a">
          <div class="qs-nav-label">A · Location</div>
          <div class="qs-nav-sub">Where the high/low lands</div>
        </div>
        <div class="qs-nav-item" data-study="b">
          <div class="qs-nav-label">B · Sequencing</div>
          <div class="qs-nav-sub">High first or low first</div>
        </div>
        <div class="qs-nav-item" data-study="c">
          <div class="qs-nav-label">C · Per-quarter bias</div>
          <div class="qs-nav-sub">Direction & range stats</div>
        </div>
        <div class="qs-nav-item" data-study="d">
          <div class="qs-nav-label">D · Conditional</div>
          <div class="qs-nav-sub">Q1 → later quarter shifts</div>
        </div>
        <div class="qs-nav-item" data-study="e">
          <div class="qs-nav-label">E · Persistence</div>
          <div class="qs-nav-sub">Hold rate & overshoot</div>
        </div>
        <div class="qs-nav-item" data-study="f">
          <div class="qs-nav-label">F · Q1 expansion</div>
          <div class="qs-nav-sub">Range bucketing</div>
        </div>
      </div>
      <div class="qs-main" id="main">Loading…</div>
    </div>
  </div>

  <script src="shared.js"></script>
  <script>
    let activeStudy = localStorage.getItem('analysis-quarters-study') || 'a';

    async function init() {
      // Load all parquet sources upfront
      await loadParquet('../data/quarters/quarter_features.parquet', 'features');

      // Discover years
      const years = (await query('SELECT DISTINCT year FROM features ORDER BY year')).map(r => Number(r.year));

      await FilterBar.init(
        document.getElementById('filters'),
        'quarters',
        ['year', 'hour', 'dow', 'minCount'],
        () => render(),
        { years }
      );

      // Wire sidebar
      document.querySelectorAll('.qs-nav-item').forEach(el => {
        el.addEventListener('click', () => {
          activeStudy = el.dataset.study;
          localStorage.setItem('analysis-quarters-study', activeStudy);
          render();
        });
      });

      await render();
    }

    function setActiveSidebar() {
      document.querySelectorAll('.qs-nav-item').forEach(el => {
        el.dataset.active = (el.dataset.study === activeStudy) ? 'true' : 'false';
      });
    }

    async function render() {
      setActiveSidebar();
      const main = document.getElementById('main');
      main.innerHTML = 'Loading…';
      const fn = STUDIES[activeStudy];
      if (!fn) { main.innerHTML = `<div class="headline warn">Unknown study: ${activeStudy}</div>`; return; }
      await fn(main);
    }

    // Each study renderer is defined in subsequent tasks. Stubs for now:
    const STUDIES = {
      a: async (main) => { main.innerHTML = '<div class="headline">Study A — placeholder</div>'; },
      b: async (main) => { main.innerHTML = '<div class="headline">Study B — placeholder</div>'; },
      c: async (main) => { main.innerHTML = '<div class="headline">Study C — placeholder</div>'; },
      d: async (main) => { main.innerHTML = '<div class="headline">Study D — placeholder</div>'; },
      e: async (main) => { main.innerHTML = '<div class="headline">Study E — placeholder</div>'; },
      f: async (main) => { main.innerHTML = '<div class="headline">Study F — placeholder</div>'; },
    };

    init().catch(e => alert('Failed to load: ' + e.message));
  </script>
</body>
</html>
```

- [ ] **Step 2: Syntax check + browser validation**

```bash
python3 -c "
import re
html = open('/Users/abhi/Projects/Statistic.ally/Analysis/dashboard/quarters.html').read()
scripts = re.findall(r'<script>(.*?)</script>', html, re.DOTALL)
open('/tmp/inline_quarters.js', 'w').write(scripts[0])
"
node --check /tmp/inline_quarters.js
```

Then:
```bash
cd /Users/abhi/Projects/Statistic.ally
(pgrep -f "http.server 8001" || python3 -m http.server 8001 &) && sleep 2
echo "Open: http://localhost:8001/Analysis/dashboard/quarters.html"
```

Verify:
- Filter bar renders at top (no Direction toggle — quarters page doesn't need it)
- Sidebar with 6 study items renders on the left
- Active study (default A) has accent border + tinted background
- Clicking a different sidebar item updates the active study
- Reloading the page preserves the active study selection
- Filter changes call render() (visible in the brief "Loading…" flash)

Cleanup: `pkill -f "http.server 8001" || true`

- [ ] **Step 3: Commit**

```bash
cd /Users/abhi/Projects/Statistic.ally
git add Analysis/dashboard/quarters.html
git commit -m "Analysis dashboard: quarters.html — sidebar nav + filter bar (study stubs)"
```

---

## Task 10: Quarters Study A — Location

**Files:**
- Modify: `Analysis/dashboard/quarters.html`

- [ ] **Step 1: Replace the Study A stub with the full implementation**

In the `STUDIES` object, replace the `a:` entry with:

```javascript
      a: async (main) => {
        const where = FilterBar.whereClause();
        const minCount = FilterBar.minCount();

        // Load distribution
        const distSql = `
          SELECT
            AVG(CASE WHEN q_of_high = 1 THEN 1.0 ELSE 0.0 END) AS hi_q1,
            AVG(CASE WHEN q_of_high = 2 THEN 1.0 ELSE 0.0 END) AS hi_q2,
            AVG(CASE WHEN q_of_high = 3 THEN 1.0 ELSE 0.0 END) AS hi_q3,
            AVG(CASE WHEN q_of_high = 4 THEN 1.0 ELSE 0.0 END) AS hi_q4,
            AVG(CASE WHEN q_of_low = 1 THEN 1.0 ELSE 0.0 END) AS lo_q1,
            AVG(CASE WHEN q_of_low = 2 THEN 1.0 ELSE 0.0 END) AS lo_q2,
            AVG(CASE WHEN q_of_low = 3 THEN 1.0 ELSE 0.0 END) AS lo_q3,
            AVG(CASE WHEN q_of_low = 4 THEN 1.0 ELSE 0.0 END) AS lo_q4,
            COUNT(*) AS n
          FROM features
          WHERE ${where}
        `;
        const dist = (await query(distSql))[0];
        const n = Number(dist.n) || 0;

        // Headline
        const hiVals = [dist.hi_q1, dist.hi_q2, dist.hi_q3, dist.hi_q4];
        const topQ = hiVals.indexOf(Math.max(...hiVals)) + 1;
        const topPct = (hiVals[topQ - 1] * 100).toFixed(1) + '%';
        const delta = ((hiVals[topQ - 1] - 0.25) * 100).toFixed(1);

        // Cross-tab
        const ctSql = `
          SELECT q_of_high AS h, q_of_low AS l, COUNT(*) AS n
          FROM features
          WHERE ${where}
          GROUP BY h, l
        `;
        const ctRows = await query(ctSql);
        const ctValues = [[0,0,0,0],[0,0,0,0],[0,0,0,0],[0,0,0,0]];
        for (const r of ctRows) {
          ctValues[Number(r.h) - 1][Number(r.l) - 1] = Number(r.n) / n;
        }

        main.innerHTML = `
          <div id="hl-a"></div>
          <div class="study-section">
            <div class="two-col">
              <div>
                <div class="study-section-title">Where the high lands</div>
                <div id="t-hi"></div>
              </div>
              <div>
                <div class="study-section-title">Where the low lands</div>
                <div id="t-lo"></div>
              </div>
            </div>
          </div>
          <div class="study-section">
            <div class="study-section-title">Joint distribution: q_of_high × q_of_low (n=${fmtNum(n)})</div>
            <div id="t-crosstab"></div>
          </div>
        `;

        if (n < minCount) {
          renderHeadline(document.getElementById('hl-a'), null);
        } else {
          renderHeadline(document.getElementById('hl-a'),
            'Q${topQ} contains the hourly high ${topPct} of the time, ${delta} percentage points ${dir} the 25% baseline.',
            { topQ, topPct, delta: Math.abs(delta), dir: delta >= 0 ? 'above' : 'below' });
        }

        const cols = (key) => [
          { key: 'q', label: 'Quarter', type: 'label' },
          { key, label: 'Share of hours', type: 'baseline', baseline: 0.25, maxPct: 0.5,
            colorAbove: 'green', colorBelow: 'blue' },
        ];
        renderInlineBarTable(document.getElementById('t-hi'),
          [
            { q: 'Q1', hi: dist.hi_q1, count: n },
            { q: 'Q2', hi: dist.hi_q2, count: n },
            { q: 'Q3', hi: dist.hi_q3, count: n },
            { q: 'Q4', hi: dist.hi_q4, count: n },
          ], cols('hi'), { minCount });
        renderInlineBarTable(document.getElementById('t-lo'),
          [
            { q: 'Q1', lo: dist.lo_q1, count: n },
            { q: 'Q2', lo: dist.lo_q2, count: n },
            { q: 'Q3', lo: dist.lo_q3, count: n },
            { q: 'Q4', lo: dist.lo_q4, count: n },
          ], cols('lo'), { minCount });

        renderCrossTab(document.getElementById('t-crosstab'), {
          rowAxisLabel: 'q_hi', colAxisLabel: 'q_lo',
          rowLabels: ['Q1','Q2','Q3','Q4'], colLabels: ['Q1','Q2','Q3','Q4'],
          values: ctValues,
          fmt: (v) => (v * 100).toFixed(1) + '%',
        });
      },
```

- [ ] **Step 2: Syntax check + browser validation**

```bash
python3 -c "
import re
html = open('/Users/abhi/Projects/Statistic.ally/Analysis/dashboard/quarters.html').read()
scripts = re.findall(r'<script>(.*?)</script>', html, re.DOTALL)
open('/tmp/inline_quarters.js', 'w').write(scripts[0])
"
node --check /tmp/inline_quarters.js
```

Then:
```bash
cd /Users/abhi/Projects/Statistic.ally
(pgrep -f "http.server 8001" || python3 -m http.server 8001 &) && sleep 2
echo "Open: http://localhost:8001/Analysis/dashboard/quarters.html"
```

Verify Study A:
- Headline summarizes Q1 dominance ("Q1 contains the hourly high 36.4% of the time, ~11pp above 25% baseline")
- Two side-by-side tables (high / low) with 4 quarters each
- Bars colored green if above 25% baseline, blue if below
- Dotted baseline marker visible at the 25% line (50% of bar width since maxPct=0.5)
- 4×4 cross-tab heatmap below shows joint distribution; diagonal cells outlined
- Filter changes update everything

Cleanup: `pkill -f "http.server 8001" || true`

- [ ] **Step 3: Commit**

```bash
cd /Users/abhi/Projects/Statistic.ally
git add Analysis/dashboard/quarters.html
git commit -m "Analysis dashboard: quarters Study A — Location distribution + cross-tab"
```

---

## Task 11: Quarters Study B — Sequencing (donut + conditional)

**Files:**
- Modify: `Analysis/dashboard/quarters.html`

- [ ] **Step 1: Replace the Study B stub**

```javascript
      b: async (main) => {
        const where = FilterBar.whereClause();
        const minCount = FilterBar.minCount();

        const sql = `
          SELECT
            AVG(CASE WHEN extreme_first = 'H' THEN 1.0 ELSE 0.0 END) AS h_first,
            AVG(CASE WHEN extreme_first = 'L' THEN 1.0 ELSE 0.0 END) AS l_first,
            AVG(CASE WHEN extreme_first = 'T' THEN 1.0 ELSE 0.0 END) AS tie,
            COUNT(*) AS n
          FROM features
          WHERE ${where}
        `;
        const seq = (await query(sql))[0];
        const n = Number(seq.n) || 0;

        // Conditional: when high came first, where did it land?
        const hCondSql = `
          SELECT q_of_high AS q, COUNT(*) AS n
          FROM features
          WHERE ${where} AND extreme_first = 'H'
          GROUP BY q ORDER BY q
        `;
        const lCondSql = `
          SELECT q_of_low AS q, COUNT(*) AS n
          FROM features
          WHERE ${where} AND extreme_first = 'L'
          GROUP BY q ORDER BY q
        `;
        const hCond = await query(hCondSql);
        const lCond = await query(lCondSql);
        const hTotal = hCond.reduce((s, r) => s + Number(r.n), 0);
        const lTotal = lCond.reduce((s, r) => s + Number(r.n), 0);
        const hByQ = { 1: 0, 2: 0, 3: 0, 4: 0 };
        for (const r of hCond) hByQ[Number(r.q)] = Number(r.n);
        const lByQ = { 1: 0, 2: 0, 3: 0, 4: 0 };
        for (const r of lCond) lByQ[Number(r.q)] = Number(r.n);

        main.innerHTML = `
          <div id="hl-b"></div>
          <div class="study-section" style="display:flex;align-items:center;gap:16px;flex-wrap:wrap;">
            <div id="donut-b"></div>
          </div>
          <div class="study-section">
            <div class="two-col">
              <div>
                <div class="study-section-title">When high came first (n=${fmtNum(hTotal)}), where did it land?</div>
                <div id="t-hcond"></div>
              </div>
              <div>
                <div class="study-section-title">When low came first (n=${fmtNum(lTotal)}), where did it land?</div>
                <div id="t-lcond"></div>
              </div>
            </div>
          </div>
        `;

        if (n < minCount) {
          renderHeadline(document.getElementById('hl-b'), null);
        } else {
          renderHeadline(document.getElementById('hl-b'),
            'High came first in ${hPct} of hours, low first in ${lPct}, tied in ${tPct}.',
            { hPct: fmtPct(seq.h_first), lPct: fmtPct(seq.l_first), tPct: fmtPct(seq.tie) });
        }

        renderDonut(document.getElementById('donut-b'), [
          { label: 'High first', value: seq.h_first, color: '#10b981' },
          { label: 'Low first',  value: seq.l_first, color: '#ef4444' },
          { label: 'Tie',        value: seq.tie,     color: '#8ba4bc' },
        ], { centerText: `${fmtNum(n)} hours` });

        const condCols = (color) => [
          { key: 'q',   label: 'Quarter', type: 'label' },
          { key: 'pct', label: 'Share',   type: 'baseline', baseline: 0.25, maxPct: 0.7,
            colorAbove: color, colorBelow: 'blue' },
        ];
        renderInlineBarTable(document.getElementById('t-hcond'),
          [1,2,3,4].map(q => ({ q: `Q${q}`, pct: hTotal > 0 ? hByQ[q] / hTotal : 0, count: hTotal })),
          condCols('green'), { minCount });
        renderInlineBarTable(document.getElementById('t-lcond'),
          [1,2,3,4].map(q => ({ q: `Q${q}`, pct: lTotal > 0 ? lByQ[q] / lTotal : 0, count: lTotal })),
          condCols('red'), { minCount });
      },
```

- [ ] **Step 2: Syntax check + browser validation**

```bash
python3 -c "
import re
html = open('/Users/abhi/Projects/Statistic.ally/Analysis/dashboard/quarters.html').read()
scripts = re.findall(r'<script>(.*?)</script>', html, re.DOTALL)
open('/tmp/inline_quarters.js', 'w').write(scripts[0])
"
node --check /tmp/inline_quarters.js
```

Then open Study B in the browser. Verify:
- Donut chart renders with 3 segments (H first / L first / Tie)
- Center text shows total hour count
- Two side-by-side conditional tables show distribution of high-quarter when high came first, and low-quarter when low came first
- Headline summarizes the H-first vs L-first percentages

Cleanup: `pkill -f "http.server 8001" || true`

- [ ] **Step 3: Commit**

```bash
cd /Users/abhi/Projects/Statistic.ally
git add Analysis/dashboard/quarters.html
git commit -m "Analysis dashboard: quarters Study B — Sequencing donut + conditional tables"
```

---

## Task 12: Quarters Study C — Per-quarter bias

**Files:**
- Modify: `Analysis/dashboard/quarters.html`

- [ ] **Step 1: Replace the Study C stub**

```javascript
      c: async (main) => {
        const where = FilterBar.whereClause();
        const minCount = FilterBar.minCount();

        const sql = `
          SELECT
            ${[1,2,3,4].map(q => `
              AVG(CASE WHEN q${q}_dir = 1 THEN 1.0 ELSE 0.0 END) AS q${q}_up,
              AVG(CASE WHEN q${q}_dir = -1 THEN 1.0 ELSE 0.0 END) AS q${q}_down,
              AVG(CASE WHEN q${q}_dir = 0 THEN 1.0 ELSE 0.0 END) AS q${q}_flat,
              AVG(q${q}_range) AS q${q}_avg_range,
              AVG(q${q}_body)  AS q${q}_avg_body
            `).join(',')},
            COUNT(*) AS n
          FROM features
          WHERE ${where}
        `;
        const r = (await query(sql))[0];
        const n = Number(r.n) || 0;

        // Find widest and quietest
        const ranges = [Number(r.q1_avg_range), Number(r.q2_avg_range), Number(r.q3_avg_range), Number(r.q4_avg_range)];
        const widestQ = ranges.indexOf(Math.max(...ranges)) + 1;
        const quietestQ = ranges.indexOf(Math.min(...ranges)) + 1;

        const maxRange = Math.max(...ranges) * 1.05;
        const maxBody = Math.max(Number(r.q1_avg_body), Number(r.q2_avg_body), Number(r.q3_avg_body), Number(r.q4_avg_body)) * 1.05;

        const rows = [1,2,3,4].map(q => ({
          q: `Q${q}`,
          up: r[`q${q}_up`],
          down: r[`q${q}_down`],
          flat: r[`q${q}_flat`],
          range: Number(r[`q${q}_avg_range`]),
          body: Number(r[`q${q}_avg_body`]),
          decisive: Number(r[`q${q}_avg_range`]) > 0
            ? Number(r[`q${q}_avg_body`]) / Number(r[`q${q}_avg_range`])
            : null,
          count: n,
        }));

        main.innerHTML = `
          <div id="hl-c"></div>
          <div class="study-section">
            <div id="t-c"></div>
          </div>
        `;

        if (n < minCount) {
          renderHeadline(document.getElementById('hl-c'), null);
        } else {
          renderHeadline(document.getElementById('hl-c'),
            'Q${widestQ} has the widest average range (${widestRange} pts); Q${quietestQ} is the quietest (${quietestRange} pts).',
            {
              widestQ, quietestQ,
              widestRange: ranges[widestQ - 1].toFixed(1),
              quietestRange: ranges[quietestQ - 1].toFixed(1),
            });
        }

        renderInlineBarTable(document.getElementById('t-c'), rows, [
          { key: 'q',     label: 'Quarter', type: 'label' },
          { key: 'up',    label: 'Up %',    type: 'inlineBar', maxPct: 0.6, color: 'green' },
          { key: 'down',  label: 'Down %',  type: 'inlineBar', maxPct: 0.6, color: 'red' },
          { key: 'flat',  label: 'Flat %',  type: 'inlineBar', maxPct: 0.1, color: 'neutral' },
          { key: 'range', label: 'Avg range (pts)', type: 'inlineBar', maxValue: maxRange, color: 'neutral',
            formatter: (v) => v.toFixed(1) },
          { key: 'body',  label: 'Avg body (pts)',  type: 'inlineBar', maxValue: maxBody, color: 'neutral',
            formatter: (v) => v.toFixed(1) },
          { key: 'decisive', label: 'Decisiveness (body/range)', type: 'inlineBar', maxPct: 1.0, color: 'amber' },
        ], { minCount });
      },
```

- [ ] **Step 2: Syntax check + browser validation**

```bash
python3 -c "
import re
html = open('/Users/abhi/Projects/Statistic.ally/Analysis/dashboard/quarters.html').read()
scripts = re.findall(r'<script>(.*?)</script>', html, re.DOTALL)
open('/tmp/inline_quarters.js', 'w').write(scripts[0])
"
node --check /tmp/inline_quarters.js
```

Then open Study C. Verify:
- Single 4-row table (Q1, Q2, Q3, Q4) with 7 columns: Up %, Down %, Flat %, Avg range (pts), Avg body (pts), Decisiveness
- Each numeric column has an inline bar
- Up % bars green, Down % bars red, Flat % muted, range/body neutral, Decisiveness amber
- Headline reports widest and quietest quarter

Cleanup: `pkill -f "http.server 8001" || true`

- [ ] **Step 3: Commit**

```bash
cd /Users/abhi/Projects/Statistic.ally
git add Analysis/dashboard/quarters.html
git commit -m "Analysis dashboard: quarters Study C — per-quarter bias 4-row table"
```

---

## Task 13: Quarters Study D — Conditional shifts

**Files:**
- Modify: `Analysis/dashboard/quarters.html`

- [ ] **Step 1: Replace the Study D stub**

```javascript
      d: async (main) => {
        const where = FilterBar.whereClause();
        const minCount = FilterBar.minCount();

        const condSql = `
          SELECT q1_dir,
                 COUNT(*) AS n,
                 AVG(CASE WHEN q2_dir = 1 THEN 1.0 ELSE 0.0 END) AS q2_up,
                 AVG(CASE WHEN q3_dir = 1 THEN 1.0 ELSE 0.0 END) AS q3_up,
                 AVG(CASE WHEN q4_dir = 1 THEN 1.0 ELSE 0.0 END) AS q4_up,
                 AVG(CASE WHEN hour_dir = 1 THEN 1.0 ELSE 0.0 END) AS hour_up
          FROM features
          WHERE ${where}
          GROUP BY q1_dir
        `;
        const rows = await query(condSql);
        const lookup = {};
        for (const r of rows) lookup[String(r.q1_dir)] = r;

        const totalN = rows.reduce((s, r) => s + Number(r.n), 0);

        // Reversal: q4_dir opposite of q1_dir, given q1_dir != 0
        const revSql = `
          SELECT
            AVG(CASE WHEN (q1_dir = 1 AND q4_dir = -1) OR (q1_dir = -1 AND q4_dir = 1)
                     THEN 1.0 ELSE 0.0 END) AS rev,
            COUNT(*) AS n
          FROM features
          WHERE ${where} AND q1_dir != 0
        `;
        const rev = (await query(revSql))[0];

        // Headline
        const upGivenUp = lookup['1'] ? lookup['1'].hour_up : null;
        const downGivenDown = lookup['-1'] ? lookup['-1'].hour_up : null;

        main.innerHTML = `
          <div id="hl-d"></div>
          <div class="study-section">
            <div class="two-col">
              <div class="stat-card">
                <div class="stat-card-label">P(hour ↑ | Q1 ↑)</div>
                <div class="stat-card-value">${fmtPct(upGivenUp)}</div>
                <div class="stat-card-sub">n=${fmtNum(lookup['1'] ? lookup['1'].n : 0)}</div>
              </div>
              <div class="stat-card">
                <div class="stat-card-label">P(hour ↓ | Q1 ↓)</div>
                <div class="stat-card-value">${fmtPct(lookup['-1'] ? (1 - lookup['-1'].hour_up) : null)}</div>
                <div class="stat-card-sub">n=${fmtNum(lookup['-1'] ? lookup['-1'].n : 0)}</div>
              </div>
            </div>
          </div>
          <div class="study-section">
            <div class="study-section-title">Conditional probability of an UP close in subsequent quarters</div>
            <div id="t-d"></div>
          </div>
          <div class="study-section">
            <div class="stat-card amber">
              <div class="stat-card-label">P(Q4 reverses Q1) — given Q1 was non-flat</div>
              <div class="stat-card-value">${fmtPct(rev.rev)}</div>
              <div class="stat-card-sub">n=${fmtNum(rev.n)}</div>
            </div>
          </div>
        `;

        if (totalN < minCount) {
          renderHeadline(document.getElementById('hl-d'), null);
        } else {
          renderHeadline(document.getElementById('hl-d'),
            'When Q1 closes up, the hour closes up ${upGivenUp} of the time. Q4 reverses Q1 in ${revPct} of cases.',
            { upGivenUp: fmtPct(upGivenUp), revPct: fmtPct(rev.rev) });
        }

        function rowFor(q1dir) {
          const r = lookup[String(q1dir)];
          if (!r) return { q1: q1dir, count: 0, q2_up: null, q3_up: null, q4_up: null, hour_up: null };
          return {
            q1: q1dir,
            count: Number(r.n),
            q2_up: r.q2_up, q3_up: r.q3_up, q4_up: r.q4_up, hour_up: r.hour_up,
          };
        }

        const tableRows = [
          { ...rowFor(1), q1Label: 'Q1 ↑' },
          { ...rowFor(0), q1Label: 'Q1 flat' },
          { ...rowFor(-1), q1Label: 'Q1 ↓' },
        ];

        renderInlineBarTable(document.getElementById('t-d'), tableRows, [
          { key: 'q1Label', label: 'Q1 direction', type: 'label' },
          { key: 'count',   label: 'n', type: 'count' },
          { key: 'q2_up',   label: 'P(Q2 ↑)',   type: 'baseline', baseline: 0.5, maxPct: 1.0, colorAbove: 'green', colorBelow: 'red' },
          { key: 'q3_up',   label: 'P(Q3 ↑)',   type: 'baseline', baseline: 0.5, maxPct: 1.0, colorAbove: 'green', colorBelow: 'red' },
          { key: 'q4_up',   label: 'P(Q4 ↑)',   type: 'baseline', baseline: 0.5, maxPct: 1.0, colorAbove: 'green', colorBelow: 'red' },
          { key: 'hour_up', label: 'P(hour ↑)', type: 'baseline', baseline: 0.5, maxPct: 1.0, colorAbove: 'green', colorBelow: 'red' },
        ], { minCount });
      },
```

- [ ] **Step 2: Syntax check + browser validation**

```bash
python3 -c "
import re
html = open('/Users/abhi/Projects/Statistic.ally/Analysis/dashboard/quarters.html').read()
scripts = re.findall(r'<script>(.*?)</script>', html, re.DOTALL)
open('/tmp/inline_quarters.js', 'w').write(scripts[0])
"
node --check /tmp/inline_quarters.js
```

Then open Study D. Verify:
- Two stat cards at top: P(hour up | Q1 up) and P(hour down | Q1 down)
- Conditional probability table with 3 rows (Q1 up / flat / down) and 4 P-columns (Q2/Q3/Q4/hour up)
- Bars green if ≥50% baseline, red if below
- Reversal stat card at bottom (amber color)

Cleanup: `pkill -f "http.server 8001" || true`

- [ ] **Step 3: Commit**

```bash
cd /Users/abhi/Projects/Statistic.ally
git add Analysis/dashboard/quarters.html
git commit -m "Analysis dashboard: quarters Study D — conditional shift probabilities"
```

---

## Task 14: Quarters Study E — Persistence

**Files:**
- Modify: `Analysis/dashboard/quarters.html`

- [ ] **Step 1: Replace the Study E stub**

```javascript
      e: async (main) => {
        const where = FilterBar.whereClause();
        const minCount = FilterBar.minCount();

        const sql = `
          SELECT
            AVG(CASE WHEN q_of_high = 1 THEN 1.0 ELSE 0.0 END) AS q1_hi_hold,
            AVG(CASE WHEN q_of_low = 1 THEN 1.0 ELSE 0.0 END)  AS q1_lo_hold,
            AVG(CASE WHEN q_of_high = 4 THEN 1.0 ELSE 0.0 END) AS q4_hi_hold,
            AVG(CASE WHEN q_of_low = 4 THEN 1.0 ELSE 0.0 END)  AS q4_lo_hold,
            COUNT(*) AS n
          FROM features
          WHERE ${where}
        `;
        const r = (await query(sql))[0];
        const n = Number(r.n) || 0;

        // Overshoot when Q1 high failed (high in some later quarter)
        const oshHiSql = `
          SELECT
            AVG(hour_high - q1_high) AS mean,
            MEDIAN(hour_high - q1_high) AS median,
            COUNT(*) AS n
          FROM features
          WHERE ${where} AND q_of_high != 1
        `;
        const oshHi = (await query(oshHiSql))[0];

        // Overshoot when Q1 low failed (low in some later quarter)
        const oshLoSql = `
          SELECT
            AVG(q1_low - hour_low) AS mean,
            MEDIAN(q1_low - hour_low) AS median,
            COUNT(*) AS n
          FROM features
          WHERE ${where} AND q_of_low != 1
        `;
        const oshLo = (await query(oshLoSql))[0];

        main.innerHTML = `
          <div id="hl-e"></div>
          <div class="study-section">
            <div class="study-section-title">Hold rates — when does the extreme stay an extreme?</div>
            <div class="four-col">
              <div class="stat-card">
                <div class="stat-card-label">Q1 high held as hour high</div>
                <div class="stat-card-value">${fmtPct(r.q1_hi_hold)}</div>
              </div>
              <div class="stat-card">
                <div class="stat-card-label">Q1 low held as hour low</div>
                <div class="stat-card-value">${fmtPct(r.q1_lo_hold)}</div>
              </div>
              <div class="stat-card">
                <div class="stat-card-label">Q4 high held as hour high</div>
                <div class="stat-card-value">${fmtPct(r.q4_hi_hold)}</div>
              </div>
              <div class="stat-card">
                <div class="stat-card-label">Q4 low held as hour low</div>
                <div class="stat-card-value">${fmtPct(r.q4_lo_hold)}</div>
              </div>
            </div>
          </div>
          <div class="study-section">
            <div class="study-section-title">Overshoot when Q1 extreme failed to hold (in NQ points)</div>
            <div id="t-overshoot"></div>
          </div>
        `;

        if (n < minCount) {
          renderHeadline(document.getElementById('hl-e'), null);
        } else {
          renderHeadline(document.getElementById('hl-e'),
            "Q1's high holds as the hour high ${q1Hold} of the time. When it fails, average overshoot is ${oshMean} pts (median ${oshMed}).",
            {
              q1Hold: fmtPct(r.q1_hi_hold),
              oshMean: oshHi.mean != null ? Number(oshHi.mean).toFixed(1) : '—',
              oshMed: oshHi.median != null ? Number(oshHi.median).toFixed(1) : '—',
            });
        }

        const oshRows = [
          {
            label: 'Q1 high failed',
            mean: Number(oshHi.mean) || 0,
            median: Number(oshHi.median) || 0,
            count: Number(oshHi.n) || 0,
          },
          {
            label: 'Q1 low failed',
            mean: Number(oshLo.mean) || 0,
            median: Number(oshLo.median) || 0,
            count: Number(oshLo.n) || 0,
          },
        ];
        const maxOsh = Math.max(oshRows[0].mean, oshRows[1].mean) * 1.2 || 1;

        renderInlineBarTable(document.getElementById('t-overshoot'), oshRows, [
          { key: 'label',  label: 'Case',   type: 'label' },
          { key: 'count',  label: 'n',       type: 'count' },
          { key: 'mean',   label: 'Mean overshoot (pts)', type: 'inlineBar',
            maxValue: maxOsh, color: 'amber', formatter: (v) => v.toFixed(1) },
          { key: 'median', label: 'Median overshoot (pts)', type: 'inlineBar',
            maxValue: maxOsh, color: 'amber', formatter: (v) => v.toFixed(1) },
        ], { minCount });
      },
```

- [ ] **Step 2: Syntax check + browser validation**

```bash
python3 -c "
import re
html = open('/Users/abhi/Projects/Statistic.ally/Analysis/dashboard/quarters.html').read()
scripts = re.findall(r'<script>(.*?)</script>', html, re.DOTALL)
open('/tmp/inline_quarters.js', 'w').write(scripts[0])
"
node --check /tmp/inline_quarters.js
```

Then open Study E. Verify:
- 4 stat cards in a row showing Q1 hi/lo hold and Q4 hi/lo hold rates
- Overshoot table with 2 rows (Q1 high failed / Q1 low failed) showing mean and median pts overshoot
- Headline summarizes Q1 hold rate + overshoot
- Numbers are non-NaN (Task 22 of the prior project verified the engine column-name fix)

Cleanup: `pkill -f "http.server 8001" || true`

- [ ] **Step 3: Commit**

```bash
cd /Users/abhi/Projects/Statistic.ally
git add Analysis/dashboard/quarters.html
git commit -m "Analysis dashboard: quarters Study E — persistence + overshoot"
```

---

## Task 15: Quarters Study F — Q1-range expansion

**Files:**
- Modify: `Analysis/dashboard/quarters.html`

- [ ] **Step 1: Replace the Study F stub**

```javascript
      f: async (main) => {
        const where = FilterBar.whereClause();
        const minCount = FilterBar.minCount();

        // Compute quintile boundaries client-side from filtered data, then aggregate
        const sql = `
          WITH ranked AS (
            SELECT *, NTILE(5) OVER (ORDER BY q1_range) AS quintile
            FROM features
            WHERE ${where}
          )
          SELECT quintile,
                 COUNT(*) AS n,
                 AVG(q1_range) AS avg_q1_range,
                 AVG(hour_range) AS avg_hour_range,
                 AVG(hour_range - q1_range) AS avg_remaining,
                 AVG(CASE WHEN q_of_high = 1 THEN 1.0 ELSE 0.0 END) AS q1_hi_hold,
                 AVG(CASE WHEN q_of_low = 1 THEN 1.0 ELSE 0.0 END) AS q1_lo_hold,
                 AVG(CASE WHEN hour_dir = 1 THEN 1.0 ELSE 0.0 END) AS hour_up,
                 AVG(CASE WHEN hour_dir = -1 THEN 1.0 ELSE 0.0 END) AS hour_down
          FROM ranked
          GROUP BY quintile ORDER BY quintile
        `;
        const rows = await query(sql);

        main.innerHTML = `
          <div id="hl-f"></div>
          <div class="study-section">
            <div class="study-section-title">Hour outcomes by Q1-range quintile (1 = narrowest, 5 = widest)</div>
            <div id="t-f"></div>
          </div>
        `;

        if (!rows.length || rows[0].n < minCount) {
          renderHeadline(document.getElementById('hl-f'), null);
        } else {
          const q1 = rows[0], q5 = rows[rows.length - 1];
          renderHeadline(document.getElementById('hl-f'),
            'Widest-quintile Q1s (avg ${q5Range} pts) precede ${q5Hour}-pt hour ranges, vs ${q1Hour} for the narrowest quintile.',
            {
              q5Range: Number(q5.avg_q1_range).toFixed(1),
              q5Hour: Number(q5.avg_hour_range).toFixed(1),
              q1Hour: Number(q1.avg_hour_range).toFixed(1),
            });
        }

        const maxRange = Math.max(...rows.map(r => Number(r.avg_hour_range))) * 1.05;
        const maxRemain = Math.max(...rows.map(r => Number(r.avg_remaining))) * 1.05;
        const maxQ1Range = Math.max(...rows.map(r => Number(r.avg_q1_range))) * 1.05;

        const tableRows = rows.map(r => ({
          quintile: `Q${r.quintile}`,
          count: Number(r.n),
          avg_q1: Number(r.avg_q1_range),
          avg_hour: Number(r.avg_hour_range),
          avg_remain: Number(r.avg_remaining),
          q1_hi: r.q1_hi_hold,
          q1_lo: r.q1_lo_hold,
          h_up: r.hour_up,
          h_down: r.hour_down,
        }));

        renderInlineBarTable(document.getElementById('t-f'), tableRows, [
          { key: 'quintile', label: 'Q1-range quintile', type: 'label' },
          { key: 'count',    label: 'n',                 type: 'count' },
          { key: 'avg_q1',   label: 'Avg Q1 range (pts)',     type: 'inlineBar',
            maxValue: maxQ1Range, color: 'neutral', formatter: (v) => v.toFixed(1) },
          { key: 'avg_hour', label: 'Avg hour range (pts)',   type: 'inlineBar',
            maxValue: maxRange, color: 'neutral', formatter: (v) => v.toFixed(1) },
          { key: 'avg_remain', label: 'Avg remaining (pts)',  type: 'inlineBar',
            maxValue: maxRemain, color: 'neutral', formatter: (v) => v.toFixed(1) },
          { key: 'q1_hi', label: 'Q1 high held %', type: 'baseline',
            baseline: 0.25, maxPct: 0.6, colorAbove: 'green', colorBelow: 'blue' },
          { key: 'q1_lo', label: 'Q1 low held %',  type: 'baseline',
            baseline: 0.25, maxPct: 0.6, colorAbove: 'green', colorBelow: 'blue' },
          { key: 'h_up',  label: 'Hour ↑ %',       type: 'baseline',
            baseline: 0.5, maxPct: 1.0, colorAbove: 'green', colorBelow: 'red' },
          { key: 'h_down', label: 'Hour ↓ %',      type: 'baseline',
            baseline: 0.5, maxPct: 1.0, colorAbove: 'red', colorBelow: 'green' },
        ], { minCount });
      },
```

- [ ] **Step 2: Syntax check + browser validation**

```bash
python3 -c "
import re
html = open('/Users/abhi/Projects/Statistic.ally/Analysis/dashboard/quarters.html').read()
scripts = re.findall(r'<script>(.*?)</script>', html, re.DOTALL)
open('/tmp/inline_quarters.js', 'w').write(scripts[0])
"
node --check /tmp/inline_quarters.js
```

Then open Study F. Verify:
- 5-row table (Q1–Q5 quintiles by Q1 range)
- Columns: n, Avg Q1 range, Avg hour range, Avg remaining, Q1 hi held %, Q1 lo held %, Hour up %, Hour down %
- Quintile 1 = narrowest, Quintile 5 = widest — verify the avg_q1_range is monotonically increasing
- Hour up/down columns use 50% baseline; hold rate columns use 25% baseline

Cleanup: `pkill -f "http.server 8001" || true`

- [ ] **Step 3: Commit**

```bash
cd /Users/abhi/Projects/Statistic.ally
git add Analysis/dashboard/quarters.html
git commit -m "Analysis dashboard: quarters Study F — Q1-range quintile expansion"
```

---

## Task 16: Final cross-page polish + landing page light refresh

**Files:**
- Modify: `Analysis/dashboard/index.html`

- [ ] **Step 1: Refresh the landing-page card descriptions to match the new dashboards**

The landing page already exists from the prior project. Just update the manifest card labels to match the new layouts and ensure the card descriptions match what's now available.

Read the current file:

```bash
cat /Users/abhi/Projects/Statistic.ally/Analysis/dashboard/index.html
```

Apply this `Edit`: change the `desc` text inside the breakout link card to reflect the new layout.

Find the existing `<a href="breakout.html" ...>` block. Replace its content with:

```html
      <a href="breakout.html" class="card" style="text-decoration:none;color:inherit;">
        <h2>Breakout Follow-Through</h2>
        <p style="color:var(--text-secondary);margin-top:8px;">When an hourly candle closes above the prior hour's high (or below the prior low), how often does the next hour take out the newly-formed extreme — and in which quarter? Filter by year, session (RTH / London / Asia / Overnight), and DOW.</p>
      </a>
```

Find the existing `<a href="quarters.html" ...>` block. Replace its content with:

```html
      <a href="quarters.html" class="card" style="text-decoration:none;color:inherit;">
        <h2>Quarter-of-the-Hour Study</h2>
        <p style="color:var(--text-secondary);margin-top:8px;">In-depth analysis of intra-hour price action across six sub-studies: where extremes form, sequencing, conditional shifts (Q1 → Q4), early-extreme persistence, and Q1-range expansion.</p>
      </a>
```

- [ ] **Step 2: Manual browser validation of all three pages**

```bash
cd /Users/abhi/Projects/Statistic.ally
(pgrep -f "http.server 8001" || python3 -m http.server 8001 &) && sleep 2
echo "Open and verify each:"
echo "  - http://localhost:8001/Analysis/dashboard/index.html"
echo "  - http://localhost:8001/Analysis/dashboard/breakout.html"
echo "  - http://localhost:8001/Analysis/dashboard/quarters.html"
```

End-to-end checklist:
- [ ] Landing page: manifest card populated, both nav cards have updated descriptions
- [ ] Breakout: filter bar collapsible, hero panels populated, all 6 panel cards (takeout, prev-mid, by-year, by-hour, by-dow, heatmap) render
- [ ] Breakout: changing year/hour/dow filter updates everything; direction filter dims the unselected hero panel
- [ ] Breakout: heatmap shows tooltips on hover
- [ ] Quarters: filter bar collapsible, sidebar nav with 6 items, active item highlighted
- [ ] Quarters: clicking through all 6 studies (A → F) renders without error; numbers populate; bars are visible
- [ ] Both pages: theme toggle (top-right) flips dark/light; localStorage persists between reloads
- [ ] Both pages: filter selections persist between reloads
- [ ] Both pages: navigating to landing page with `← Hourly Analysis` link works
- [ ] Browser console (F12): no JavaScript errors, no failed network requests

Cleanup: `pkill -f "http.server 8001" || true`

- [ ] **Step 3: Commit**

```bash
cd /Users/abhi/Projects/Statistic.ally
git add Analysis/dashboard/index.html
git commit -m "Analysis dashboard: refresh landing page descriptions for redesigned pages"
```

---

## Self-Review Checklist (run after writing this plan)

Reviewed against the spec on 2026-04-26.

1. **Spec coverage:** Every section of the design doc maps to at least one task:
   - CSS scaffolding (spec §Architecture, §Color & Visual Conventions) → Task 1
   - FilterBar (spec §Architecture point 1) → Task 2
   - Inline-bar table renderer + headline (§Architecture points 2, 4) → Task 3
   - Donut + heatmap (§Architecture points 5, 6) → Task 3
   - Breakout hero panels (§Hero) → Task 4
   - Breakout panels 1–6 → Tasks 5–8
   - Quarters sidebar nav (§Layout) → Task 9
   - Quarters Studies A–F → Tasks 10–15
   - Landing page polish → Task 16

2. **Placeholder scan:** No TBD/TODO. Each step shows actual code or actual commands.

3. **Type/name consistency:**
   - `FilterBar.whereClause()`, `FilterBar.minCount()`, `FilterBar.direction()`, `FilterBar.years()`, `FilterBar.hours()`, `FilterBar.dows()` — used consistently in tasks 4–15
   - Element IDs (`hero-bull`, `hero-bear`, `hl-takeout`, `t-takeout-bull`, etc.) defined in HTML scaffolding (Task 4) and referenced by population functions (Tasks 5–8). Cross-checked.
   - `renderInlineBarTable(el, rows, columnSpec, opts)` signature consistent across all calls.
   - Column types (`'label'`, `'count'`, `'pct'`, `'num'`, `'inlineBar'`, `'baseline'`) defined in Task 3 and used in 5, 6, 7, 10, 11, 12, 13, 14, 15.

4. **Flagged ambiguities:**
   - The `FilterBar.setActiveYears` is defined but never called by the new pages — they discover years up-front and pass via `init({ years })`. The function is left in for future use; harmless.
   - `escapeHtml` is used by the renderers (Task 3) but defined as a non-window helper. Confirmed it's defined inside the same script block as the consumers, so scope is fine.
   - `crosstab-corner` rendering uses `\\` for the slash — single backslash in JS is fine, will render as `\` in the HTML.
   - Study F uses `MEDIAN()` which is a DuckDB function — confirmed available in DuckDB-Wasm 1.29.0 (it's a SQL standard aggregate).
