// Analysis/dashboard/shared.js
// Theme: shared with the rest of Statistic.ally via localStorage 'hub-theme'
(function () {
  const t = localStorage.getItem('hub-theme') || 'dark';
  document.documentElement.setAttribute('data-theme', t);
})();

window.toggleTheme = function () {
  const cur = document.documentElement.getAttribute('data-theme');
  const next = cur === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('hub-theme', next);
};

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
    return result.toArray().map(r => Object.fromEntries(
      Object.entries(r).map(([k, v]) => [k, typeof v === 'bigint' ? Number(v) : v])
    ));
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
