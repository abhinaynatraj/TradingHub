// Analysis/dashboard/shared.js
// Theme: shared with the rest of Statistic.ally via localStorage 'hub-theme'
// Four themes (Fractal Sweep parity): dark, light, gold, indigo.
const THEME_ORDER = ['dark', 'light', 'gold', 'indigo'];
(function () {
  const saved = localStorage.getItem('hub-theme');
  const t = THEME_ORDER.includes(saved) ? saved : 'dark';
  document.documentElement.setAttribute('data-theme', t);
})();

window.applyTheme = function (name) {
  if (!THEME_ORDER.includes(name)) return;
  document.documentElement.setAttribute('data-theme', name);
  document.querySelectorAll('.theme-opt').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.theme === name);
  });
  localStorage.setItem('hub-theme', name);
};

// Legacy two-state toggle kept for backward compat (cycles all four).
window.toggleTheme = function () {
  const cur = document.documentElement.getAttribute('data-theme');
  const idx = THEME_ORDER.indexOf(cur);
  const next = THEME_ORDER[(idx + 1) % THEME_ORDER.length];
  applyTheme(next);
};

// Auto-wire the theme picker on every page that includes it.
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.theme-opt').forEach(btn => {
    btn.addEventListener('click', () => applyTheme(btn.dataset.theme));
    if (btn.dataset.theme === document.documentElement.getAttribute('data-theme')) {
      btn.classList.add('active');
    }
  });
});

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
    return result.toArray().map(r => {
      const obj = typeof r.toJSON === 'function' ? r.toJSON() : { ...r };
      for (const k of Object.keys(obj)) {
        if (typeof obj[k] === 'bigint') obj[k] = Number(obj[k]);
      }
      return obj;
    });
  } finally {
    await conn.close();
  }
};

window.fmtPct = (x) => (x == null || isNaN(x)) ? '—' : (x * 100).toFixed(1) + '%';
window.fmtNum = (x) => (x == null || isNaN(x)) ? '—' : Number(x).toLocaleString();

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
      // Coerce arrays back to Sets. Guard against legacy/corrupt entries
      // (older builds may have stored Sets as plain objects, which aren't iterable).
      if (Array.isArray(persisted.year)) state.year = new Set(persisted.year);
      if (Array.isArray(persisted.hour)) state.hour = new Set(persisted.hour);
      if (Array.isArray(persisted.dow))  state.dow  = new Set(persisted.dow);
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

// ── Bar row (single-row labeled bar) ─────────────────────────
// Usage:
//   renderBarRow(el, [
//     { label: '09 ET', value: 0.74, color: 'green' },
//     { label: '10 ET', value: 0.68, color: 'green' },
//   ], { max: 1.0, fmt: (v) => (v*100).toFixed(0)+'%' });
window.renderBarRow = function (el, rows, opts = {}) {
  const max = opts.max != null ? opts.max : 1.0;
  const fmt = opts.fmt || ((v) => (v * 100).toFixed(1) + '%');
  el.innerHTML = rows.map(r => {
    const w = Math.max(0, Math.min(100, (r.value / max) * 100));
    const cls = r.color ? `bar-${r.color}` : '';
    return `<div class="bar-row">
      <div class="br-label">${escapeHtml(r.label)}</div>
      <div class="br-track"><div class="br-fill ${cls}" style="width:${w}%"></div></div>
      <div class="br-val">${fmt(r.value)}</div>
    </div>`;
  }).join('');
};

// ── 4-quarter visual strip (Q1/Q2/Q3/Q4 cards) ───────────────
// Usage:
//   renderQuarterStrip(el, [0.36, 0.16, 0.18, 0.29], { fmt: fmtPct, sub: 'high lands here' });
window.renderQuarterStrip = function (el, vals, opts = {}) {
  const fmt = opts.fmt || ((v) => (v * 100).toFixed(1) + '%');
  const labels = ['Q1', 'Q2', 'Q3', 'Q4'];
  const minutes = ['min :00–:14', 'min :15–:29', 'min :30–:44', 'min :45–:59'];
  const sub = opts.sub || '';
  const peakIdx = vals.reduce((maxI, v, i, arr) => v > arr[maxI] ? i : maxI, 0);
  el.innerHTML = labels.map((lbl, i) => {
    const cls = i === peakIdx ? 'peak' : '';
    return `<div class="q-strip-cell ${cls}">
      <div class="qsc-q">${lbl}</div>
      <div class="qsc-mins">${minutes[i]}</div>
      <div class="qsc-val">${fmt(vals[i])}</div>
      ${sub ? `<div class="qsc-sub">${escapeHtml(sub)}</div>` : ''}
    </div>`;
  }).join('');
};

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
