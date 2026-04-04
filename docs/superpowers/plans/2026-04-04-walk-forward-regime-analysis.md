# Walk-Forward Regime Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the custom date ranges view with a walk-forward regime analysis that pairs consecutive ranges into train→test pairs, derives MAE stop variants from train winners, and compares performance across regimes to detect overfitting.

**Architecture:** All changes in `Fractal Sweep/model_dashboard.html` (client-side JS). New computation functions (`computeTrainParams`, `resolveWithStopCap`, `buildWalkForwardPairs`) feed into a rewritten `renderCustomViewV2`. Existing `computeRangeStats` and chart helpers are reused unchanged.

**Tech Stack:** Vanilla JS, Canvas 2D (existing chart helpers), HTML/CSS (existing theme system)

---

## File Structure

All changes in a single file:

- **Modify:** `Fractal Sweep/model_dashboard.html`
  - **New functions** (insert after `computeRangeStats`, before `applyCustomRanges` ~line 1551):
    - `computeTrainParams(trades)` — extract MAE/MFE parameters from winners
    - `resolveWithStopCap(trades, slCapPct)` — adjust trade outcomes for a MAE stop cap
    - `computeRegimeFingerprint(trades, startDate, endDate)` — regime characteristics
    - `computeOverfitScore(trainEV, testEV)` — overfitting badge
    - `findBestVariant(pairs)` — lowest CV variant across pairs
    - `buildWalkForwardPairs(rangeResults)` — pair ranges, compute all variants
  - **Modified functions:**
    - `applyCustomRanges()` (~line 1552) — call `buildWalkForwardPairs` then render
    - `renderCustomViewV2(pairs, unpairedRanges, combinedTestStats)` (~line 1746) — full rewrite
  - **New rendering helper** (inside rewritten `renderCustomViewV2`):
    - `drawKDEOverlay(canvas, trainDensity, testDensity, label)` — overlaid distribution curves

---

### Task 1: Core Computation Functions

**Files:**
- Modify: `Fractal Sweep/model_dashboard.html:1551` (insert after `computeRangeStats` closing brace)

- [ ] **Step 1: Add `computeTrainParams` function**

Insert after the `computeRangeStats` function (after line 1551):

```javascript
function computeTrainParams(trades) {
  // Extract MAE/MFE parameters from winners for walk-forward analysis
  const winners = trades.filter(t => t.outcome === 'WIN');
  const n = winners.length;
  if (n < 5) return null;

  const maeVals = winners.map(t => t.mae_pct).filter(v => v != null && v > 0).sort((a,b) => a-b);
  const mfeVals = winners.map(t => t.mfe_pct).filter(v => v != null && v > 0).sort((a,b) => a-b);
  if (maeVals.length < 5 || mfeVals.length < 5) return null;

  const maePct = p => maeVals[Math.min(Math.floor(p/100 * maeVals.length), maeVals.length-1)];
  const mfePct = p => mfeVals[Math.min(Math.floor(p/100 * mfeVals.length), mfeVals.length-1)];

  // MAE stop variants
  const maeMax = maeVals[maeVals.length - 1];
  const maeP90 = maePct(90);
  const maeP85 = maePct(85);
  const maeP50 = maePct(50);

  // MFE targets — PTQ: highest reach where p_pos >= 0.70, fallback 0.50
  const allTrades = trades; // need all trades for p_pos calculation
  let ptqLevel = null, ptqReachRate = null;
  let ptqFallback = null, ptqFallbackRR = null;
  const triggerPcts = [5,10,15,20,25,30,33,40,50,60,75,90];
  triggerPcts.forEach(reachRate => {
    const thr = mfePct(100 - reachRate);
    const reached = allTrades.filter(t => t.mfe_pct != null && t.mfe_pct >= thr);
    if (reached.length === 0) return;
    const nPos = reached.filter(t => t.outcome === 'WIN').length;
    const pPos = nPos / reached.length;
    if (pPos >= 0.70) {
      ptqLevel = Math.round(thr * 10000) / 10000;
      ptqReachRate = reachRate;
    } else if (pPos >= 0.50) {
      ptqFallback = Math.round(thr * 10000) / 10000;
      ptqFallbackRR = reachRate;
    }
  });
  if (ptqLevel === null && ptqFallback !== null) {
    ptqLevel = ptqFallback;
    ptqReachRate = ptqFallbackRR;
  }

  const mfeP50 = Math.round(mfePct(50) * 10000) / 10000;

  return {
    nWinners: n,
    mae: {
      max: Math.round(maeMax * 10000) / 10000,
      p90: Math.round(maeP90 * 10000) / 10000,
      p85: Math.round(maeP85 * 10000) / 10000,
      p50: Math.round(maeP50 * 10000) / 10000,
    },
    mfe: {
      ptq: ptqLevel,
      ptqReachRate: ptqReachRate,
      p50: mfeP50,
    },
    maeDensity: computeKDE(maeVals),
    mfeDensity: computeKDE(mfeVals),
  };
}
```

- [ ] **Step 2: Add `resolveWithStopCap` function**

Insert immediately after `computeTrainParams`:

```javascript
function resolveWithStopCap(trades, slCapPct) {
  // Simulate trades with a MAE-based stop cap
  // If trade's MAE exceeded the cap, it would have been stopped out
  return trades.map(t => {
    if (t.mae_pct != null && t.mae_pct > slCapPct) {
      return Object.assign({}, t, { outcome: 'LOSS', r: -1.0, _adjusted: true });
    }
    return t;
  });
}
```

- [ ] **Step 3: Add `computeRegimeFingerprint` function**

Insert immediately after `resolveWithStopCap`:

```javascript
function computeRegimeFingerprint(trades, startDate, endDate) {
  if (!trades.length) return { avgRisk: 0, longPct: 0, mfeMaeRatio: 0, density: 0 };
  const riskVals = trades.map(t => t.risk_pts).filter(v => v != null && v > 0);
  const avgRisk = riskVals.length > 0 ? Math.round(riskVals.reduce((s,v)=>s+v,0) / riskVals.length * 10) / 10 : 0;
  const longPct = Math.round(trades.filter(t => t.direction === 'LONG').length / trades.length * 1000) / 10;
  const maeVals = trades.map(t => t.mae_pct).filter(v => v != null && v > 0).sort((a,b)=>a-b);
  const mfeVals = trades.map(t => t.mfe_pct).filter(v => v != null && v > 0).sort((a,b)=>a-b);
  const medMAE = maeVals.length > 0 ? maeVals[Math.floor(maeVals.length/2)] : 1;
  const medMFE = mfeVals.length > 0 ? mfeVals[Math.floor(mfeVals.length/2)] : 0;
  const mfeMaeRatio = medMAE > 0 ? Math.round(medMFE / medMAE * 100) / 100 : 0;
  // Trade density: trades per calendar day
  const d0 = new Date(startDate), d1 = new Date(endDate);
  const calDays = Math.max(1, (d1 - d0) / (1000*60*60*24));
  const density = Math.round(trades.length / calDays * 100) / 100;
  return { avgRisk, longPct, mfeMaeRatio, density };
}
```

- [ ] **Step 4: Add diagnostic functions**

Insert immediately after `computeRegimeFingerprint`:

```javascript
function computeOverfitScore(trainEV, testEV) {
  if (trainEV == null || trainEV === 0) return { score: null, label: '—', cls: 'var(--text-muted)' };
  const pct = (testEV / trainEV) * 100;
  if (pct >= 80 && pct <= 120) return { score: Math.round(pct), label: 'ROBUST', cls: 'var(--green)' };
  if (pct >= 60) return { score: Math.round(pct), label: 'MILD DECAY', cls: 'var(--amber)' };
  return { score: Math.round(pct), label: 'OVERFIT', cls: 'var(--red)' };
}

function findBestVariant(pairs) {
  // Find the stop variant with most consistent test EV across pairs (lowest CV)
  const variantNames = ['Max MAE', 'P90 MAE', 'P85 MAE', 'P50 MAE'];
  let bestIdx = 0, bestCV = Infinity;
  for (let vi = 0; vi < 4; vi++) {
    const testEVs = pairs.map(p => p.variants[vi].test.ev_r).filter(v => v != null);
    if (testEVs.length < 2) continue;
    const mean = testEVs.reduce((s,v)=>s+v,0) / testEVs.length;
    const std = Math.sqrt(testEVs.reduce((s,v)=>s+(v-mean)**2,0) / (testEVs.length-1));
    const cv = mean !== 0 ? Math.abs(std / mean) : Infinity;
    if (cv < bestCV) { bestCV = cv; bestIdx = vi; }
  }
  return { name: variantNames[bestIdx], index: bestIdx, cv: Math.round(bestCV * 100) };
}
```

- [ ] **Step 5: Add `buildWalkForwardPairs` function**

Insert immediately after `findBestVariant`:

```javascript
function buildWalkForwardPairs(rangeResults) {
  const STOP_VARIANTS = ['Max MAE', 'P90 MAE', 'P85 MAE', 'P50 MAE'];
  const pairs = [];
  const unpaired = [];

  for (let i = 0; i < rangeResults.length; i += 2) {
    if (i + 1 >= rangeResults.length) {
      unpaired.push(rangeResults[i]);
      break;
    }
    const train = rangeResults[i];
    const test = rangeResults[i + 1];
    const params = computeTrainParams(train.trades);

    if (!params) {
      // Not enough winners — show as unpaired
      unpaired.push(train, test);
      continue;
    }

    const slCaps = [params.mae.max, params.mae.p90, params.mae.p85, params.mae.p50];
    const variants = slCaps.map((cap, vi) => {
      const trainResolved = resolveWithStopCap(train.trades, cap);
      const testResolved = resolveWithStopCap(test.trades, cap);
      return {
        name: STOP_VARIANTS[vi],
        slCap: cap,
        train: computeRangeStats(trainResolved),
        test: computeRangeStats(testResolved),
      };
    });

    // Find best variant for this pair (highest test EV)
    let bestVI = 0, bestTestEV = -Infinity;
    variants.forEach((v, vi) => {
      if (v.test && v.test.ev_r > bestTestEV) { bestTestEV = v.test.ev_r; bestVI = vi; }
    });

    const trainDates = train.label.split(' to ');
    const testDates = test.label.split(' to ');

    pairs.push({
      index: pairs.length + 1,
      train: { label: train.label, color: train.color, trades: train.trades,
               stats: computeRangeStats(train.trades),
               fingerprint: computeRegimeFingerprint(train.trades, trainDates[0], trainDates[1]) },
      test:  { label: test.label, color: test.color, trades: test.trades,
               stats: computeRangeStats(test.trades),
               fingerprint: computeRegimeFingerprint(test.trades, testDates[0], testDates[1]) },
      params: params,
      variants: variants,
      bestVariantIdx: bestVI,
      overfitScore: computeOverfitScore(
        variants[bestVI].train?.ev_r, variants[bestVI].test?.ev_r),
    });
  }

  return { pairs, unpaired };
}
```

- [ ] **Step 6: Verify computation functions**

Open the browser at `http://localhost:8001/Fractal Sweep/model_dashboard.html`, open the console, and manually test:

```javascript
// In console — verify functions exist and return expected shapes
const baseD = getProfileData('1H_5M_PREV_CISD', 'structural_dynamic');
const trades = baseD.recent_trades.filter(t => t.date >= '2025-01-01' && t.date <= '2025-06-30');
console.log('trades:', trades.length);
console.log('trainParams:', computeTrainParams(trades));
console.log('resolved:', resolveWithStopCap(trades, 0.1).filter(t=>t._adjusted).length, 'adjusted');
console.log('fingerprint:', computeRegimeFingerprint(trades, '2025-01-01', '2025-06-30'));
```

Expected: `computeTrainParams` returns object with `mae.max/p90/p85/p50` and `mfe.ptq/p50`. `resolveWithStopCap` adjusts some trades. `computeRegimeFingerprint` returns 4 numeric fields.

- [ ] **Step 7: Commit**

```bash
git add "Fractal Sweep/model_dashboard.html"
git commit -m "feat: add walk-forward computation functions (trainParams, resolveWithStopCap, fingerprint, diagnostics)"
```

---

### Task 2: Rewrite `applyCustomRanges`

**Files:**
- Modify: `Fractal Sweep/model_dashboard.html:1552-1565`

- [ ] **Step 1: Replace `applyCustomRanges`**

Replace the existing function (lines 1552-1565):

```javascript
function applyCustomRanges(){
  const fullKey = `${activeModel}_${activeMode}_${activeCisd}`;
  const baseD = getProfileData(fullKey, activeProfile);
  if(!baseD || !baseD.recent_trades) return;
  const allTrades = baseD.recent_trades;

  const rangeResults = customRanges.map((r, i) => {
    if(!r.start || !r.end) return null;
    const filtered = allTrades.filter(t => t.date >= r.start && t.date <= r.end);
    return { label: r.start + ' to ' + r.end, color: RANGE_COLORS[i], stats: computeRangeStats(filtered), trades: filtered };
  }).filter(Boolean);

  if (rangeResults.length === 0) return;

  if (rangeResults.length === 1) {
    // Single range — no pairing, show standalone card
    const combinedStats = computeRangeStats(rangeResults.flatMap(r => r.trades));
    renderCustomViewV2([], rangeResults, combinedStats);
    return;
  }

  // Build walk-forward pairs from consecutive ranges
  const { pairs, unpaired } = buildWalkForwardPairs(rangeResults);

  // Combined stats from ALL test periods (for hero tiles)
  const allTestTrades = pairs.flatMap(p => p.test.trades);
  const allUnpairedTrades = unpaired.flatMap(r => r.trades);
  const combinedStats = computeRangeStats([...allTestTrades, ...allUnpairedTrades]);

  renderCustomViewV2(pairs, unpaired, combinedStats);
}
```

- [ ] **Step 2: Commit**

```bash
git add "Fractal Sweep/model_dashboard.html"
git commit -m "feat: rewrite applyCustomRanges to build walk-forward pairs"
```

---

### Task 3: Rewrite `renderCustomViewV2` — Sections A & B

**Files:**
- Modify: `Fractal Sweep/model_dashboard.html:1746` — full rewrite of `renderCustomViewV2`

This is the largest task. Replace the entire `renderCustomViewV2` function (from line 1746 to just before the chart drawing code at ~line 1958).

- [ ] **Step 1: Replace function signature and Section A (hero tiles)**

Replace from `function renderCustomViewV2(rangeResults, combinedStats){` through the end of Section A hero tiles. The new function takes `(pairs, unpairedRanges, combinedStats)`:

```javascript
function renderCustomViewV2(pairs, unpairedRanges, combinedStats){
  const cv = document.getElementById('custom-view');
  if(!cv) return;

  if(!combinedStats && pairs.length === 0 && unpairedRanges.length === 0){
    cv.innerHTML = '<div style="padding:40px 0;text-align:center;font-family:var(--font-data);font-size:12px;color:var(--text-muted)">No trades found in selected ranges. Adjust dates and click Apply.</div>';
    return;
  }

  function statColor(val, threshGood, threshBad, invert){
    if(invert) return val <= threshGood ? 'var(--green)' : val >= threshBad ? 'var(--red)' : 'var(--amber)';
    return val >= threshGood ? 'var(--green)' : val <= threshBad ? 'var(--red)' : 'var(--amber)';
  }
  function pct(v){ return (v*100).toFixed(1)+'%'; }
  function secHeader(title){ return `<div style="font-family:var(--font-data);font-size:10px;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:var(--text-muted);border-bottom:1px solid var(--border);padding-bottom:6px;margin-bottom:16px;margin-top:32px">${title}</div>`; }
  function heroTile(lbl, val, color, sub){
    return `<div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:16px 18px;box-shadow:var(--shadow);position:relative;overflow:hidden">
      <div style="position:absolute;top:0;left:0;width:100%;height:3px;background:${color};border-radius:10px 10px 0 0"></div>
      <div style="font-family:var(--font-data);font-size:11px;font-weight:500;letter-spacing:0.04em;color:var(--text-muted);text-transform:uppercase;margin-bottom:6px">${lbl}</div>
      <div style="font-family:var(--font-display);font-size:28px;font-weight:700;letter-spacing:-0.02em;line-height:1;margin-bottom:4px;color:${color}">${val}</div>
      ${sub ? `<div style="font-family:var(--font-data);font-size:11px;color:var(--text-muted)">${sub}</div>` : ''}
    </div>`;
  }

  const acctSize = 4500, rpt = 225;
  let html = '';

  // ── SECTION A: Combined Test Summary ──────────────────────────────────────
  if(combinedStats){
    const cs = combinedStats;
    const sourceLabel = pairs.length > 0 ? 'Out-of-Sample Combined' : 'Combined Stats';
    html += secHeader(sourceLabel + ' (' + cs.n + ' trades)');
    html += `<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:10px">`;
    html += heroTile('Win Rate', pct(cs.wr), statColor(cs.wr, 0.55, 0.45, false), `${cs.nWins}W / ${cs.nLosses}L`);
    html += heroTile('EV (R)', cs.ev_r.toFixed(3), statColor(cs.ev_r, 0.05, -0.05, false), 'per trade');
    html += heroTile('Profit Factor', cs.pf.toFixed(3), statColor(cs.pf, 1.5, 1.0, false), 'gross win / gross loss');
    html += heroTile('CE', cs.ce.toFixed(3), statColor(cs.ce, 0.1, 0, false), 'EV × PF');
    html += `</div>`;
    html += `<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:10px">`;
    html += heroTile('P&L', '$'+cs.totalPnl.toLocaleString(), statColor(cs.totalPnl, 0, -1, false), '$'+acctSize.toLocaleString()+' account');
    html += heroTile('Min Equity', '$'+cs.minEq.toLocaleString(), statColor(cs.minEq, acctSize*0.8, acctSize*0.5, false), cs.blown ? '⚠ ACCOUNT BLOWN' : '');
    html += heroTile('Max DD', cs.maxDDPct.toFixed(2)+'%', statColor(cs.maxDDPct, 10, 25, true), '$'+Math.round(cs.maxDDPct/100*acctSize).toLocaleString()+' drawdown');
    html += heroTile('Sharpe', cs.sharpe != null ? cs.sharpe.toFixed(2) : '\u2014', cs.sharpe != null ? statColor(cs.sharpe, 1.5, 0.5, false) : 'var(--text-muted)', 'annualised');
    html += `</div>`;
    html += `<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:20px">`;
    html += heroTile('Avg Win R', cs.avgWinR.toFixed(3)+'R', statColor(cs.avgWinR, 1.5, 0.5, false), 'mean winner size');
    html += heroTile('Max W Run', cs.mcw, statColor(cs.mcw, 5, 3, false), 'consecutive wins');
    html += heroTile('Max L Run', cs.mcl, statColor(cs.mcl, 5, 10, true), 'consecutive losses');
    const _blwnBdg = cs.blown
      ? '<span style="font-family:var(--font-data);font-size:11px;font-weight:700;padding:4px 10px;border-radius:4px;background:rgba(239,68,68,0.15);border:1px solid rgba(239,68,68,0.3);color:var(--red)">BLOWN</span>'
      : '<span style="font-family:var(--font-data);font-size:11px;font-weight:700;padding:4px 10px;border-radius:4px;background:rgba(34,197,94,0.12);border:1px solid rgba(34,197,94,0.25);color:var(--green)">SAFE</span>';
    html += heroTile('Account', _blwnBdg, 'var(--text-secondary)', '$'+acctSize.toLocaleString()+' @ $'+rpt+'/trade');
    html += `</div>`;
  }
```

- [ ] **Step 2: Add Section B — Walk-Forward Pairs**

Continue inside the same function, after Section A:

```javascript
  // ── SECTION B: Walk-Forward Pairs ─────────────────────────────────────────
  pairs.forEach(pair => {
    const os = pair.overfitScore;
    const osBadge = `<span style="font-family:var(--font-data);font-size:10px;font-weight:700;padding:3px 8px;border-radius:4px;background:color-mix(in srgb,${os.cls} 15%,transparent);border:1px solid color-mix(in srgb,${os.cls} 30%,transparent);color:${os.cls}">${os.label}${os.score != null ? ' '+os.score+'%' : ''}</span>`;

    html += secHeader(`Pair ${pair.index}: ${pair.train.label.split(' to ')[0]} → ${pair.test.label.split(' to ')[1]}`);

    // Pair header with overfitting badge
    html += `<div style="display:flex;align-items:center;gap:16px;margin-bottom:16px;flex-wrap:wrap">
      <div style="display:flex;align-items:center;gap:8px">
        <div style="width:10px;height:10px;border-radius:3px;background:${pair.train.color}"></div>
        <span style="font-family:var(--font-data);font-size:11px;color:var(--text-muted)">Train: <strong style="color:var(--text-secondary)">${pair.train.label}</strong> (${pair.train.trades.length} trades)</span>
      </div>
      <span style="font-family:var(--font-data);font-size:14px;color:var(--text-muted)">→</span>
      <div style="display:flex;align-items:center;gap:8px">
        <div style="width:10px;height:10px;border-radius:3px;background:${pair.test.color}"></div>
        <span style="font-family:var(--font-data);font-size:11px;color:var(--text-muted)">Test: <strong style="color:var(--text-secondary)">${pair.test.label}</strong> (${pair.test.trades.length} trades)</span>
      </div>
      ${osBadge}
    </div>`;

    // Train parameters block
    const p = pair.params;
    const lowSampleWarn = p.nWinners < 20 ? ` <span style="color:var(--amber);font-size:10px">⚠ low sample</span>` : '';
    html += `<div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:14px 18px;margin-bottom:12px">
      <div style="font-family:var(--font-data);font-size:10px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--text-muted);margin-bottom:8px">Train Parameters (${p.nWinners} winners)${lowSampleWarn}</div>
      <div style="display:flex;gap:24px;flex-wrap:wrap;font-family:var(--font-data);font-size:12px">
        <div><span style="color:var(--text-muted)">MAE:</span>
          <span style="color:var(--red)">Max=${p.mae.max.toFixed(4)}%</span> ·
          <span style="color:var(--amber)">P90=${p.mae.p90.toFixed(4)}%</span> ·
          <span style="color:var(--amber)">P85=${p.mae.p85.toFixed(4)}%</span> ·
          <span style="color:var(--text-primary)">P50=${p.mae.p50.toFixed(4)}%</span>
        </div>
        <div><span style="color:var(--text-muted)">MFE:</span>
          <span style="color:var(--green)">PTQ=${p.mfe.ptq != null ? p.mfe.ptq.toFixed(4)+'%' : '—'}</span>
          ${p.mfe.ptqReachRate != null ? '<span style="color:var(--text-muted)">('+p.mfe.ptqReachRate+'% reach)</span>' : ''} ·
          <span style="color:var(--green)">P50=${p.mfe.p50.toFixed(4)}%</span>
        </div>
      </div>
    </div>`;

    // Regime fingerprint comparison
    const tf = pair.train.fingerprint, tsf = pair.test.fingerprint;
    const fpRow = (lbl, tv, testv, unit, fmt) => {
      const tStr = fmt ? fmt(tv) : tv;
      const tsStr = fmt ? fmt(testv) : testv;
      const delta = testv - tv;
      const deltaPct = tv !== 0 ? Math.abs(delta / tv) : 0;
      const dColor = deltaPct < 0.2 ? 'var(--green)' : deltaPct < 0.4 ? 'var(--amber)' : 'var(--red)';
      return `<td style="padding:6px 10px;text-align:right;font-family:var(--font-data);font-size:11px;color:var(--text-primary)">${tStr}${unit}</td>
              <td style="padding:6px 10px;text-align:right;font-family:var(--font-data);font-size:11px;color:var(--text-primary)">${tsStr}${unit}</td>
              <td style="padding:6px 10px;text-align:right;font-family:var(--font-data);font-size:11px;color:${dColor}">${delta >= 0 ? '+' : ''}${fmt ? fmt(delta) : delta}${unit}</td>`;
    };
    html += `<div style="overflow-x:auto;margin-bottom:12px">
    <table style="width:100%;border-collapse:collapse;font-family:var(--font-data);font-size:11px">
      <thead><tr style="border-bottom:1px solid var(--border)">
        <th style="padding:6px 10px;text-align:left;color:var(--text-muted);font-size:10px;text-transform:uppercase;letter-spacing:.06em">Regime</th>
        <th style="padding:6px 10px;text-align:right;color:${pair.train.color};font-size:10px">Train</th>
        <th style="padding:6px 10px;text-align:right;color:${pair.test.color};font-size:10px">Test</th>
        <th style="padding:6px 10px;text-align:right;color:var(--text-muted);font-size:10px">Δ</th>
      </tr></thead>
      <tbody>
        <tr style="border-bottom:1px solid color-mix(in srgb,var(--border) 50%,transparent)"><td style="padding:6px 10px;color:var(--text-muted)">Avg Risk (pts)</td>${fpRow('', tf.avgRisk, tsf.avgRisk, '', v=>v.toFixed(1))}</tr>
        <tr style="border-bottom:1px solid color-mix(in srgb,var(--border) 50%,transparent)"><td style="padding:6px 10px;color:var(--text-muted)">Long %</td>${fpRow('', tf.longPct, tsf.longPct, '%', v=>v.toFixed(1))}</tr>
        <tr style="border-bottom:1px solid color-mix(in srgb,var(--border) 50%,transparent)"><td style="padding:6px 10px;color:var(--text-muted)">MFE/MAE Ratio</td>${fpRow('', tf.mfeMaeRatio, tsf.mfeMaeRatio, '', v=>v.toFixed(2))}</tr>
        <tr><td style="padding:6px 10px;color:var(--text-muted)">Trades/Day</td>${fpRow('', tf.density, tsf.density, '', v=>v.toFixed(2))}</tr>
      </tbody>
    </table></div>`;

    // Stop variant cards — 4 in a row, each with train|test columns
    html += `<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:16px">`;
    pair.variants.forEach((v, vi) => {
      const isBest = vi === pair.bestVariantIdx;
      const borderColor = isBest ? 'var(--green)' : 'var(--border)';
      const row = (label, trainVal, testVal, tColor, tsColor) =>
        `<div style="display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid color-mix(in srgb,var(--border) 30%,transparent)">
          <span style="font-family:var(--font-data);font-size:11px;color:var(--text-muted)">${label}</span>
          <span style="display:flex;gap:12px">
            <span style="font-family:var(--font-data);font-size:11px;color:${tColor};opacity:0.5;min-width:55px;text-align:right">${trainVal}</span>
            <span style="font-family:var(--font-data);font-size:11px;font-weight:700;color:${tsColor};min-width:55px;text-align:right">${testVal}</span>
          </span>
        </div>`;

      const ts = v.train, te = v.test;
      const fmtEV = s => s ? '$'+(s.ev_r * rpt).toFixed(0) : '—';
      const fmtWR = s => s ? (s.wr*100).toFixed(1) : '—';
      const fmtPF = s => s ? s.pf.toFixed(2) : '—';
      const fmtSh = s => s && s.sharpe != null ? s.sharpe.toFixed(2) : '—';
      const fmtDD = s => s ? '-$'+Math.round(s.maxDDPct/100*acctSize) : '—';
      const fmtMCL = s => s ? s.mcl : '—';
      const fmtTot = s => s ? '$'+s.totalPnl.toLocaleString() : '—';
      const fmtBal = s => s ? '$'+Math.round(acctSize + s.totalPnl).toLocaleString() : '—';

      html += `<div style="border:1.5px solid ${borderColor};border-radius:10px;background:var(--bg-card);overflow:hidden${isBest ? ';box-shadow:0 0 0 1px var(--green)' : ''}">`;
      // Card header
      html += `<div style="padding:10px 12px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center">
        <div>
          <div style="font-family:var(--font-data);font-size:12px;font-weight:800;color:var(--text-primary)">${v.name} Stop</div>
          <div style="font-family:var(--font-data);font-size:10px;color:var(--text-muted)">SL cap: ${v.slCap.toFixed(4)}%</div>
        </div>
        ${isBest ? '<span style="font-family:var(--font-data);font-size:8px;font-weight:700;padding:2px 6px;border-radius:3px;background:rgba(34,197,94,0.12);border:1px solid rgba(34,197,94,0.25);color:var(--green)">BEST</span>' : ''}
      </div>`;
      // Column headers
      html += `<div style="display:flex;justify-content:flex-end;padding:6px 12px 0;gap:12px">
        <span style="font-family:var(--font-data);font-size:9px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.06em;min-width:55px;text-align:right;opacity:0.5">Train</span>
        <span style="font-family:var(--font-data);font-size:9px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.06em;min-width:55px;text-align:right">Test</span>
      </div>`;
      // Metric rows
      html += `<div style="padding:4px 12px 12px">`;
      html += row('Win Rate %', fmtWR(ts), fmtWR(te), statColor(ts?.wr||0,0.55,0.45,false), statColor(te?.wr||0,0.55,0.45,false));
      html += row('EV $/trade', fmtEV(ts), fmtEV(te), statColor(ts?.ev_r||0,0.05,-0.05,false), statColor(te?.ev_r||0,0.05,-0.05,false));
      html += row('Sharpe', fmtSh(ts), fmtSh(te), statColor(ts?.sharpe||0,1.5,0.5,false), statColor(te?.sharpe||0,1.5,0.5,false));
      html += row('Profit Factor', fmtPF(ts), fmtPF(te), statColor(ts?.pf||0,1.5,1.0,false), statColor(te?.pf||0,1.5,1.0,false));
      html += row('Max DD $', fmtDD(ts), fmtDD(te), statColor(ts?.maxDDPct||0,10,25,true), statColor(te?.maxDDPct||0,10,25,true));
      html += row('Max Consec L', fmtMCL(ts), fmtMCL(te), statColor(ts?.mcl||0,5,10,true), statColor(te?.mcl||0,5,10,true));
      html += row('Total $', fmtTot(ts), fmtTot(te), statColor(ts?.totalPnl||0,0,-1,false), statColor(te?.totalPnl||0,0,-1,false));
      html += row('Final Bal $', fmtBal(ts), fmtBal(te), statColor(acctSize+(ts?.totalPnl||0),acctSize,acctSize*0.5,false), statColor(acctSize+(te?.totalPnl||0),acctSize,acctSize*0.5,false));
      html += `</div></div>`;
    });
    html += `</div>`;

    // Distribution overlays (canvas placeholders)
    html += `<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:24px">
      <div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:12px">
        <div style="font-family:var(--font-data);font-size:10px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--text-muted);margin-bottom:8px">MAE Distribution · Train vs Test</div>
        <canvas id="kde-mae-pair-${pair.index}" style="width:100%;height:180px"></canvas>
      </div>
      <div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:12px">
        <div style="font-family:var(--font-data);font-size:10px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--text-muted);margin-bottom:8px">MFE Distribution · Train vs Test</div>
        <canvas id="kde-mfe-pair-${pair.index}" style="width:100%;height:180px"></canvas>
      </div>
    </div>`;
  }); // end pairs.forEach
```

- [ ] **Step 3: Commit**

```bash
git add "Fractal Sweep/model_dashboard.html"
git commit -m "feat: render walk-forward pairs with variant cards and regime fingerprint"
```

---

### Task 4: Sections C, D, and Closing

**Files:**
- Modify: `Fractal Sweep/model_dashboard.html` — continue inside `renderCustomViewV2`

- [ ] **Step 1: Add Section C — Drift Summary Table and Best Variant**

Continue inside `renderCustomViewV2`, after the pairs loop:

```javascript
  // ── SECTION C: Drift Summary Table ────────────────────────────────────────
  if (pairs.length > 0) {
    const bestOverall = findBestVariant(pairs);

    html += secHeader('Drift Summary — ' + pairs[0].variants[bestOverall.index].name + ' Stop');
    html += `<div style="overflow-x:auto;margin-bottom:16px">
    <table style="width:100%;border-collapse:collapse;font-family:var(--font-data);font-size:11px">
      <thead><tr style="border-bottom:1px solid var(--border)">
        <th style="padding:8px 10px;text-align:left;color:var(--text-muted);font-size:10px;text-transform:uppercase">Metric</th>`;
    pairs.forEach(p => {
      html += `<th style="padding:8px 6px;text-align:right;color:${p.train.color};font-size:10px">P${p.index} Train</th>
               <th style="padding:8px 6px;text-align:right;color:${p.test.color};font-size:10px">P${p.index} Test</th>
               <th style="padding:8px 6px;text-align:right;color:var(--text-muted);font-size:10px">Δ</th>`;
    });
    html += `</tr></thead><tbody>`;

    const driftMetrics = [
      { label: 'Win Rate %', get: s => s ? (s.wr*100) : 0, fmt: v => v.toFixed(1), unit: '' },
      { label: 'EV $/trade', get: s => s ? (s.ev_r * rpt) : 0, fmt: v => v.toFixed(0), unit: '' },
      { label: 'Profit Factor', get: s => s ? s.pf : 0, fmt: v => v.toFixed(2), unit: '' },
      { label: 'Sharpe', get: s => s && s.sharpe != null ? s.sharpe : 0, fmt: v => v.toFixed(2), unit: '' },
      { label: 'Max DD %', get: s => s ? s.maxDDPct : 0, fmt: v => v.toFixed(1), unit: '%' },
      { label: 'Max Consec L', get: s => s ? s.mcl : 0, fmt: v => String(Math.round(v)), unit: '' },
    ];

    driftMetrics.forEach(dm => {
      html += `<tr style="border-bottom:1px solid color-mix(in srgb,var(--border) 50%,transparent)">
        <td style="padding:7px 10px;color:var(--text-muted)">${dm.label}</td>`;
      pairs.forEach(p => {
        const vi = bestOverall.index;
        const tv = dm.get(p.variants[vi].train);
        const tsv = dm.get(p.variants[vi].test);
        const delta = tsv - tv;
        const deltaPct = tv !== 0 ? Math.abs(delta / tv) : 0;
        const dColor = deltaPct < 0.2 ? 'var(--green)' : deltaPct < 0.4 ? 'var(--amber)' : 'var(--red)';
        html += `<td style="padding:7px 6px;text-align:right;color:var(--text-primary)">${dm.fmt(tv)}${dm.unit}</td>
                 <td style="padding:7px 6px;text-align:right;color:var(--text-primary);font-weight:600">${dm.fmt(tsv)}${dm.unit}</td>
                 <td style="padding:7px 6px;text-align:right;color:${dColor};font-weight:600">${delta >= 0 ? '+' : ''}${dm.fmt(delta)}${dm.unit}</td>`;
      });
      html += `</tr>`;
    });
    html += `</tbody></table></div>`;

    // Best variant callout
    html += `<div style="background:var(--bg-card);border:1px solid var(--green-border);border-radius:10px;padding:14px 18px;margin-bottom:24px">
      <div style="font-family:var(--font-data);font-size:12px;font-weight:700;color:var(--green);margin-bottom:4px">Most Regime-Stable: ${bestOverall.name} Stop</div>
      <div style="font-family:var(--font-data);font-size:11px;color:var(--text-muted)">Test EV coefficient of variation: ${bestOverall.cv}% across ${pairs.length} pair${pairs.length>1?'s':''}. Lower = more consistent out-of-sample performance.</div>
    </div>`;
  }

  // ── Unpaired Ranges ───────────────────────────────────────────────────────
  if (unpairedRanges.length > 0) {
    html += secHeader('Unpaired Ranges — no walk-forward analysis');
    const cols = Math.min(unpairedRanges.length, 3);
    html += `<div style="display:grid;grid-template-columns:repeat(${cols},1fr);gap:16px;margin-bottom:20px">`;
    unpairedRanges.forEach(r => {
      const s = r.stats;
      if (!s) return;
      const finalBal = acctSize + s.totalPnl;
      html += `<div style="border-left:3px solid ${r.color};border-radius:10px;background:var(--bg-card);overflow:hidden">`;
      html += `<div style="padding:14px 16px;border-bottom:1px solid var(--border)">
        <div style="font-family:var(--font-data);font-size:13px;font-weight:800;color:${r.color}">${r.label}</div>
        <div style="font-family:var(--font-data);font-size:10px;color:var(--text-muted);margin-top:3px">${s.n} trades</div>
      </div>`;
      const uRow = (label, val, color) => `<div style="display:flex;justify-content:space-between;align-items:center;padding:8px 16px;border-bottom:1px solid color-mix(in srgb,var(--border) 50%,transparent)">
        <span style="font-family:var(--font-data);font-size:12px;color:var(--text-muted)">${label}</span>
        <span style="font-family:var(--font-data);font-size:13px;font-weight:700;color:${color}">${val}</span>
      </div>`;
      html += uRow('Win Rate %', (s.wr*100).toFixed(1), statColor(s.wr, 0.55, 0.45, false));
      html += uRow('EV $/trade', '$'+(s.ev_r*rpt).toFixed(0), statColor(s.ev_r, 0.05, -0.05, false));
      html += uRow('Profit Factor', s.pf.toFixed(2), statColor(s.pf, 1.5, 1.0, false));
      html += uRow('Sharpe', s.sharpe != null ? s.sharpe.toFixed(2) : '\u2014', s.sharpe != null ? statColor(s.sharpe, 1.5, 0.5, false) : 'var(--text-muted)');
      html += uRow('Total $', '$'+s.totalPnl.toLocaleString(), statColor(s.totalPnl, 0, -1, false));
      html += uRow('Final Bal $', '$'+Math.round(finalBal).toLocaleString(), statColor(finalBal, acctSize, acctSize*0.5, false));
      html += `</div>`;
    });
    html += `</div>`;
  }
```

- [ ] **Step 2: Add Section D — Trades Table and close function**

Continue inside `renderCustomViewV2`:

```javascript
  // ── SECTION D: Trades Table ───────────────────────────────────────────────
  const allTradesSorted = [...pairs.flatMap(p => p.test.trades), ...unpairedRanges.flatMap(r => r.trades)]
    .sort((a,b) => b.date.localeCompare(a.date));
  if (allTradesSorted.length > 0) {
    html += secHeader(`Trades (${allTradesSorted.length})`);
    const DOW_NAMES = {0:'Sun',1:'Mon',2:'Tue',3:'Wed',4:'Thu',5:'Fri',6:'Sat'};
    html += `<div style="overflow-x:auto;max-height:600px;overflow-y:auto;border:1px solid var(--border);border-radius:10px;margin-bottom:20px">
    <table style="width:100%;border-collapse:collapse;font-family:var(--font-data);font-size:12px;">
      <thead><tr style="border-bottom:1px solid var(--border-mid);color:var(--text-muted);text-transform:uppercase;font-size:10px;letter-spacing:.06em;position:sticky;top:0;background:var(--bg-card);z-index:1">
        <th style="padding:8px 10px;text-align:left;">Date</th>
        <th style="padding:8px 6px;text-align:left;">Day</th>
        <th style="padding:8px 6px;text-align:center;">Time</th>
        <th style="padding:8px 6px;text-align:left;">Dir</th>
        <th style="padding:8px 6px;text-align:right;">Entry</th>
        <th style="padding:8px 6px;text-align:right;">Risk</th>
        <th style="padding:8px 6px;text-align:right;">MAE %</th>
        <th style="padding:8px 6px;text-align:right;">MFE %</th>
        <th style="padding:8px 6px;text-align:right;">R</th>
        <th style="padding:8px 6px;text-align:center;">Result</th>
      </tr></thead><tbody>`;
    allTradesSorted.forEach((t, i) => {
      const bg = i % 2 === 0 ? 'transparent' : 'color-mix(in srgb,var(--bg-raised) 60%,transparent)';
      const isWin = t.outcome === 'WIN';
      const resColor = isWin ? 'var(--green)' : 'var(--red)';
      const dirColor = t.direction === 'LONG' ? 'var(--green)' : 'var(--red)';
      const dirArrow = t.direction === 'LONG' ? '▲' : '▼';
      const dowName = t.dow_name || DOW_NAMES[t.dow] || '?';
      html += `<tr style="background:${bg};border-bottom:1px solid color-mix(in srgb,var(--border-mid) 40%,transparent);">
        <td style="padding:7px 10px;color:var(--text-primary);">${String(t.date).slice(0,10)}</td>
        <td style="padding:7px 6px;color:var(--text-muted);">${dowName}</td>
        <td style="padding:7px 6px;text-align:center;color:var(--text-primary);">${String(t.hr).padStart(2,'0')}:${String(t.mn ?? 0).padStart(2,'0')}</td>
        <td style="padding:7px 6px;color:${dirColor};font-weight:700;">${dirArrow} ${t.direction}</td>
        <td style="padding:7px 6px;text-align:right;color:var(--text-primary);">${t.entry_price != null ? t.entry_price.toFixed(2) : '—'}</td>
        <td style="padding:7px 6px;text-align:right;color:var(--text-primary);">${t.risk_pts != null ? t.risk_pts.toFixed(1) : '—'}</td>
        <td style="padding:7px 6px;text-align:right;color:var(--red);font-size:11px;">${t.mae_pct != null ? t.mae_pct.toFixed(4) + '%' : '—'}</td>
        <td style="padding:7px 6px;text-align:right;color:var(--green);font-size:11px;">${t.mfe_pct != null ? t.mfe_pct.toFixed(4) + '%' : '—'}</td>
        <td style="padding:7px 6px;text-align:right;color:${resColor};font-weight:600;">${t.r != null ? (t.r > 0 ? '+' : '') + t.r.toFixed(2) : '—'}</td>
        <td style="padding:7px 6px;text-align:center;font-weight:700;color:${resColor};">${isWin ? '✓ WIN' : '✗ LOSS'}</td>
      </tr>`;
    });
    html += '</tbody></table></div>';
  }

  cv.innerHTML = html;
```

- [ ] **Step 3: Commit**

```bash
git add "Fractal Sweep/model_dashboard.html"
git commit -m "feat: add drift summary table, best variant highlight, unpaired ranges, trades table"
```

---

### Task 5: KDE Distribution Overlay Drawing

**Files:**
- Modify: `Fractal Sweep/model_dashboard.html` — add canvas drawing after `cv.innerHTML = html;`

- [ ] **Step 1: Add KDE overlay drawing code**

Insert immediately after `cv.innerHTML = html;` (still inside `renderCustomViewV2`):

```javascript
  // ── DRAW KDE OVERLAYS ─────────────────────────────────────────────────────
  pairs.forEach(pair => {
    const drawKDE = (canvasId, trainDensity, testDensity, trainColor, testColor) => {
      const canvas = document.getElementById(canvasId);
      if (!canvas || (!trainDensity.length && !testDensity.length)) return;
      const dpr = window.devicePixelRatio || 1;
      const w = canvas.clientWidth, h = canvas.clientHeight;
      canvas.width = w * dpr; canvas.height = h * dpr;
      const ctx = canvas.getContext('2d');
      ctx.scale(dpr, dpr);
      const pad = {l:10, r:10, t:10, b:24};
      const plotW = w - pad.l - pad.r, plotH = h - pad.t - pad.b;

      const all = [...trainDensity, ...testDensity];
      const xMin = Math.min(...all.map(p=>p.x));
      const xMax = Math.max(...all.map(p=>p.x));
      const yMax = Math.max(...all.map(p=>p.y)) * 1.1;
      const xRange = xMax - xMin || 1;

      function toX(v){ return pad.l + ((v - xMin) / xRange) * plotW; }
      function toY(v){ return pad.t + plotH - (v / yMax) * plotH; }

      // Grid
      const gridColor = getComputedStyle(document.documentElement).getPropertyValue('--grid-line').trim() || 'rgba(255,255,255,0.04)';
      ctx.strokeStyle = gridColor; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(pad.l, pad.t + plotH); ctx.lineTo(pad.l + plotW, pad.t + plotH); ctx.stroke();

      // Train curve (dashed, muted)
      if (trainDensity.length > 1) {
        ctx.strokeStyle = trainColor;
        ctx.lineWidth = 1.5;
        ctx.globalAlpha = 0.4;
        ctx.setLineDash([6, 4]);
        ctx.beginPath();
        trainDensity.forEach((p, i) => {
          const x = toX(p.x), y = toY(p.y);
          if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        });
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.globalAlpha = 1;
      }

      // Test curve (solid, full opacity)
      if (testDensity.length > 1) {
        ctx.strokeStyle = testColor;
        ctx.lineWidth = 2;
        ctx.beginPath();
        testDensity.forEach((p, i) => {
          const x = toX(p.x), y = toY(p.y);
          if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        });
        ctx.stroke();

        // Fill under test curve
        ctx.globalAlpha = 0.08;
        ctx.fillStyle = testColor;
        ctx.beginPath();
        testDensity.forEach((p, i) => {
          const x = toX(p.x), y = toY(p.y);
          if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        });
        ctx.lineTo(toX(testDensity[testDensity.length-1].x), pad.t + plotH);
        ctx.lineTo(toX(testDensity[0].x), pad.t + plotH);
        ctx.closePath();
        ctx.fill();
        ctx.globalAlpha = 1;
      }

      // Legend
      const mutedColor = getComputedStyle(document.documentElement).getPropertyValue('--text-muted').trim() || '#4a6480';
      ctx.font = '9px IBM Plex Mono';
      ctx.fillStyle = trainColor; ctx.globalAlpha = 0.5;
      ctx.fillText('— — Train', pad.l + 4, h - 4);
      ctx.globalAlpha = 1;
      ctx.fillStyle = testColor;
      ctx.fillText('——— Test', pad.l + 80, h - 4);

      // X-axis labels
      ctx.fillStyle = mutedColor; ctx.textAlign = 'center';
      for (let i = 0; i <= 4; i++) {
        const xVal = xMin + (i/4) * xRange;
        ctx.fillText(xVal.toFixed(2) + '%', toX(xVal), h - 12);
      }
    };

    // MAE overlay
    const trainMAE = pair.params.maeDensity || [];
    const testMAEVals = pair.test.trades.map(t=>t.mae_pct).filter(v=>v!=null&&v>0);
    const testMAEDensity = computeKDE(testMAEVals);
    drawKDE('kde-mae-pair-' + pair.index, trainMAE, testMAEDensity, pair.train.color, pair.test.color);

    // MFE overlay
    const trainMFE = pair.params.mfeDensity || [];
    const testMFEVals = pair.test.trades.map(t=>t.mfe_pct).filter(v=>v!=null&&v>0);
    const testMFEDensity = computeKDE(testMFEVals);
    drawKDE('kde-mfe-pair-' + pair.index, trainMFE, testMFEDensity, pair.train.color, pair.test.color);
  });
} // end renderCustomViewV2
```

- [ ] **Step 2: Remove the old `renderCustomViewV2` function body and its chart drawing code**

Delete the old function body (the previous `renderCustomViewV2` and all chart drawing code through the closing `}` around line ~2068). The new function replaces it entirely.

- [ ] **Step 3: Verify in browser**

Open `http://localhost:8001/Fractal%20Sweep/model_dashboard.html`:
1. Select any model + profile
2. Switch to Custom period
3. Add 4 date ranges (e.g., 2023-01 to 2023-06, 2023-07 to 2023-12, 2024-01 to 2024-06, 2024-07 to 2024-12)
4. Click Apply
5. Verify: Combined hero tiles → 2 walk-forward pairs with variant cards → drift table → KDE overlays → trades table
6. Test edge case: single range → should show standalone card only
7. Test edge case: 3 ranges → 1 pair + 1 unpaired

- [ ] **Step 4: Commit**

```bash
git add "Fractal Sweep/model_dashboard.html"
git commit -m "feat: add KDE distribution overlays and finalize walk-forward regime view"
```

---

### Task 6: Final Cleanup and Push

**Files:**
- Modify: `Fractal Sweep/model_dashboard.html` — remove dead code

- [ ] **Step 1: Remove old chart drawing functions if unused**

Check if `drawGroupedBars`, `drawLineChart`, `drawScatterPlot` are still used elsewhere in the file. If they are ONLY used by the old `renderCustomViewV2` (which is now replaced), remove them. If they are used elsewhere (e.g., by the regular dashboard tabs), keep them.

Search for references:
```
drawGroupedBars — only in old custom view? Remove if so.
drawLineChart — only in old custom view? Remove if so.
drawScatterPlot — only in old custom view? Remove if so.
```

Keep any that have references outside the replaced function.

- [ ] **Step 2: Update context docs**

Add a note to `Fractal Sweep/CLAUDE.md` under a new section:

```markdown
### Walk-Forward Regime Analysis
Custom date ranges view pairs consecutive ranges into train→test walk-forward pairs.
Train period derives MAE stop variants (max, p90, p85, p50) and MFE targets (PTQ, p50) from winners.
Test period resolves trades with each variant. Overfitting score = Test EV / Train EV × 100.
All computation is client-side in `model_dashboard.html` — no Python changes needed.
```

- [ ] **Step 3: Push**

```bash
git add "Fractal Sweep/model_dashboard.html" "Fractal Sweep/CLAUDE.md"
git commit -m "feat: complete walk-forward regime analysis — replaces custom ranges view"
git push origin main
```
