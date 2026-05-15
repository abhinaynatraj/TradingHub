// shadow.js — runtime cross-check that parquet-sourced trades match what
// the JSON recent_trades would have returned for the same (model, profile,
// period) tuple. Activated only when ?shadow=1 is in the URL.
//
// Lifecycle:
//   - Lives only during the rollout transition. Phase 4 (Task 10) strips
//     recent_trades from JSON; after that, shadow comparisons have nothing
//     to compare against and skip gracefully.
//   - Phase 5 (Task 12) deletes this file entirely once the migration is
//     verified.

import { DATA, loadTrades } from './data.js';
import { activeModel, activeMode, activeCisd, activeProfile, activeTF } from './state.js';

const SAMPLE = 50;
const _checked = new Set();

function _key(fullKey, profile, period) {
  return `${fullKey}::${profile}::${period}`;
}

function _jsonTradesForPeriod(profileData, period) {
  if (!profileData) return null;
  // Custom date ranges have no JSON-side equivalent — the JSON's
  // recent_trades is the full top-level array, not date-scoped. Skip
  // the check entirely rather than logging false count mismatches.
  if (period === 'custom') return null;
  if (period === 'all') return profileData.recent_trades || [];
  return profileData.by_tf?.[period]?.recent_trades || [];
}

// Map parquet column → JSON column to compare like-for-like.
// JSON has `sl_price` and `dow_name`; parquet has `stop_price` and `dow`.
function _normalize(row, source) {
  const r = { ...row };
  if (source === 'parquet') {
    if (r.stop_price !== undefined && r.sl_price === undefined) r.sl_price = r.stop_price;
    if (r.dow !== undefined && r.dow_name === undefined) {
      r.dow_name = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'][r.dow];
    }
  }
  return r;
}

async function _check(fullKey, profile, period) {
  const k = _key(fullKey, profile, period);
  if (_checked.has(k)) return;
  _checked.add(k);

  const profData = DATA[fullKey]?.profiles?.[profile];
  const jsonTrades = _jsonTradesForPeriod(profData, period);
  let parquetTrades;
  try {
    parquetTrades = await loadTrades(fullKey, profile, period);
  } catch (e) {
    console.warn('[shadow]', k, 'parquet fetch failed:', e);
    return;
  }

  if (jsonTrades === null) {
    console.info('[shadow]', k, 'period not comparable (e.g. custom date range) — skipping');
    return;
  }
  if (!jsonTrades.length) {
    console.info('[shadow]', k, 'JSON has no trades for this slice — skipping (expected post-Phase-4)');
    return;
  }

  if (jsonTrades.length !== parquetTrades.length) {
    console.error('[shadow]', k, 'COUNT MISMATCH: json=', jsonTrades.length, 'parquet=', parquetTrades.length);
    return;
  }

  // Compare a sampled subset of rows on key fields, both sorted by date desc.
  const sortByDate = (a, b) => (b.date || '').localeCompare(a.date || '');
  const jSorted = [...jsonTrades].sort(sortByDate);
  const pSorted = [...parquetTrades].sort(sortByDate);
  const FIELDS = ['date', 'direction', 'hr', 'dow', 'r', 'outcome', 'mae_pct', 'mfe_pct'];
  let mismatches = 0;
  for (let i = 0; i < Math.min(SAMPLE, jSorted.length); i++) {
    const j = jSorted[i];
    const p = _normalize(pSorted[i], 'parquet');
    for (const f of FIELDS) {
      const a = j[f], b = p[f];
      const ok = (a == null && b == null) || (typeof a === 'number'
        ? Math.abs((a||0) - (b||0)) < 1e-4
        : a === b);
      if (!ok) {
        console.error('[shadow]', k, `row ${i} field ${f}: json=${a} parquet=${b}`);
        mismatches++;
      }
    }
    if (mismatches > 5) {
      console.error('[shadow]', k, 'stopping at 5+ mismatches');
      return;
    }
  }
  if (mismatches === 0) {
    console.log('[shadow]', k, '✓ count + sampled rows match');
  }
}

// Public hook — called from key UI transitions.
export async function shadowCheck() {
  const fullKey = `${activeModel}_${activeMode}_${activeCisd}`;
  await _check(fullKey, activeProfile, activeTF || 'all');
}

// Auto-trigger after each window.renderActive() call by wrapping it.
const _origRenderActive = window.renderActive;
if (_origRenderActive) {
  window.renderActive = function() {
    const result = _origRenderActive.apply(this, arguments);
    shadowCheck();
    return result;
  };
}
console.log('[shadow] mode active — comparing parquet vs JSON trades on each renderActive()');
