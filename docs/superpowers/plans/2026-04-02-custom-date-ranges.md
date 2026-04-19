# Custom Date Ranges Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Custom" period option to the Fractal Sweep dashboard that lets users define 1–4 date ranges and see combined + side-by-side comparison stats in a dedicated vertical layout.

**Architecture:** Client-side filtering of `recent_trades` array in the dashboard HTML. Two small changes to `model_stats.py`: remove the 500-trade cap on `recent_trades` and add `classification` field to each trade row. All rendering, stat computation, and persistence happens in `model_dashboard.html`.

**Tech Stack:** Vanilla JS, HTML5 date inputs, Canvas 2D for charts, localStorage for persistence. No new dependencies.

---

### Task 1: Uncap recent_trades and add classification field in model_stats.py

**Files:**
- Modify: `Fractal Sweep/model_stats.py:1435-1449` (main recent_trades builder)
- Modify: `Fractal Sweep/model_stats.py:1855-1858` (by_tf slice recent_trades builder)

- [ ] **Step 1: Remove .head(500) cap and add classification column**

In `Fractal Sweep/model_stats.py`, find the recent_trades builder around line 1438:

```python
# BEFORE:
recent_rows = (wl[recent_cols]
               .sort_values('date', ascending=False)
               .head(500)
               .copy())

# AFTER:
recent_rows = (wl[recent_cols]
               .sort_values('date', ascending=False)
               .copy())
```

Then add classification lookup after the `dow_name` line (around line 1442):

```python
recent_rows['dow_name'] = recent_rows['dow'].map(lambda d: DOW_NAMES.get(int(d), '?'))
# Add classification from DATE_CLASSIFICATION lookup
recent_rows['classification'] = recent_rows['date'].astype(str).str[:10].map(
    lambda d: DATE_CLASSIFICATION.get(d, 'Unclassified'))
```

Also add `'classification'` to the `recent_cols` list is NOT needed — we add it after the select. But we do need to ensure it's serialized. Check that `recent_trades` dict output includes it (it will, since we added the column before `.to_dict('records')`).

- [ ] **Step 2: Do the same for the by_tf slice builder**

In `Fractal Sweep/model_stats.py` around line 1855-1858, the by_tf `_slice_stats` also builds recent_trades. Find:

```python
recent_cols = ['date','direction','hr','mn','session','dow','entry_price',
               'sweep_extreme','target_price','risk_pts','r','outcome',
               'mae_pct','mfe_pct']
available = [c for c in recent_cols if c in wl_sub.columns]
```

After the recent_rows are built (check for `.head(500)` or similar cap), add the same classification column:

```python
recent_rows['classification'] = recent_rows['date'].astype(str).str[:10].map(
    lambda d: DATE_CLASSIFICATION.get(d, 'Unclassified'))
```

Remove any `.head(500)` cap if present.

- [ ] **Step 3: Re-run model_stats.py to regenerate JSON**

```bash
cd "Fractal Sweep" && python3 model_stats.py
```

Expected: JSON regenerated with all trades (not capped at 500) and each trade having a `classification` field.

- [ ] **Step 4: Verify the output**

```bash
python3 -c "
import json
with open('model_stats.json') as f:
    data = json.load(f)
trades = data['30M_3M_PREV_CISD']['profiles']['structural_dynamic']['recent_trades']
print('Count:', len(trades))
print('Has classification:', 'classification' in trades[0])
print('Sample classification:', trades[0].get('classification'))
"
```

Expected: Count ~2199, classification present with values like 'DWP', 'DNP', etc.

- [ ] **Step 5: Commit**

```bash
git add "Fractal Sweep/model_stats.py" "Fractal Sweep/model_stats.json"
git commit -m "Uncap recent_trades, add classification field for custom date ranges"
```

---

### Task 2: Add "Custom" option to Period dropdown and range builder UI

**Files:**
- Modify: `Fractal Sweep/model_dashboard.html` (HTML + CSS + JS)

- [ ] **Step 1: Add "Custom" option to the Period select**

Find the Period `<select>` (line ~285):

```html
<select id="tf-select" class="sel-drop" onchange="switchTF(this.value)">
  <option value="all" selected>All Time (2014–2026)</option>
  <!-- ... existing options ... -->
  <option value="1m">Last 1 Month</option>
</select>
```

Add after the last option:

```html
  <option value="custom">Custom Ranges</option>
```

- [ ] **Step 2: Add range builder HTML after the selector bar**

Find the closing `</div>` of the `.sel-bar` div (after the profile select, around line 302). Add immediately after:

```html
<!-- Custom Range Builder -->
<div id="custom-range-builder" style="display:none;background:var(--bg-card);border-bottom:1px solid var(--border);padding:14px 28px;">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:10px;">
    <span style="font-family:var(--font-data);font-size:10px;font-weight:600;letter-spacing:0.06em;color:var(--text-muted);text-transform:uppercase;">Date Ranges</span>
    <button id="add-range-btn" onclick="addCustomRange()" style="font-family:var(--font-data);font-size:11px;padding:4px 10px;border-radius:6px;border:1px solid var(--border-mid);background:var(--bg-raised);color:var(--text-secondary);cursor:pointer;">+ Add Range</button>
    <button onclick="applyCustomRanges()" style="font-family:var(--font-data);font-size:11px;font-weight:600;padding:4px 14px;border-radius:6px;border:1px solid var(--green);background:rgba(52,211,153,0.1);color:var(--green);cursor:pointer;">Apply</button>
  </div>
  <div id="range-slots" style="display:flex;flex-wrap:wrap;gap:10px;"></div>
</div>
```

- [ ] **Step 3: Add CSS for range slots**

Add to the `<style>` block:

```css
.range-slot{display:flex;align-items:center;gap:8px;padding:8px 12px;border-radius:8px;border:1px solid var(--border-mid);background:var(--bg-raised)}
.range-slot input[type="date"]{font-family:var(--font-data);font-size:12px;padding:4px 8px;border-radius:6px;border:1px solid var(--border-mid);background:var(--bg-card);color:var(--text-primary)}
.range-swatch{width:12px;height:12px;border-radius:3px;flex-shrink:0}
.range-remove{background:none;border:none;color:var(--text-muted);cursor:pointer;font-size:14px;padding:0 4px}
.range-remove:hover{color:var(--red)}
```

- [ ] **Step 4: Add range builder JS**

Add to the `<script>` section, before `renderActive()`:

```javascript
// ── CUSTOM DATE RANGES ───────────────────────────────────────────────────────
const RANGE_COLORS = ['#3b82f6','#f59e0b','#8b5cf6','#14b8a6'];
const COMBINED_COLOR = '#94a3b8';
let customRanges = JSON.parse(localStorage.getItem('fractal-custom-ranges') || '[]');

function renderRangeSlots(){
  const container = document.getElementById('range-slots');
  if(!container) return;
  container.innerHTML = customRanges.map((r, i) => `
    <div class="range-slot">
      <div class="range-swatch" style="background:${RANGE_COLORS[i]}"></div>
      <input type="date" value="${r.start||''}" onchange="updateRange(${i},'start',this.value)">
      <span style="color:var(--text-muted);font-size:11px">to</span>
      <input type="date" value="${r.end||''}" onchange="updateRange(${i},'end',this.value)">
      <button class="range-remove" onclick="removeRange(${i})">×</button>
    </div>
  `).join('');
  document.getElementById('add-range-btn').disabled = customRanges.length >= 4;
}

function addCustomRange(){
  if(customRanges.length >= 4) return;
  customRanges.push({start:'', end:''});
  saveAndRenderRanges();
}

function removeRange(i){
  customRanges.splice(i, 1);
  saveAndRenderRanges();
}

function updateRange(i, field, val){
  customRanges[i][field] = val;
  saveAndRenderRanges();
}

function saveAndRenderRanges(){
  localStorage.setItem('fractal-custom-ranges', JSON.stringify(customRanges));
  renderRangeSlots();
}
```

- [ ] **Step 5: Update switchTF to show/hide range builder**

Modify the existing `switchTF` function:

```javascript
function switchTF(tf){
  activeTF=tf; _tradesPage=0;
  const builder = document.getElementById('custom-range-builder');
  if(builder) builder.style.display = tf === 'custom' ? '' : 'none';
  if(tf === 'custom'){
    if(customRanges.length === 0) addCustomRange();
    renderRangeSlots();
  }
  renderActive();
}
```

- [ ] **Step 6: Commit**

```bash
git add "Fractal Sweep/model_dashboard.html"
git commit -m "Add Custom option to Period dropdown with range builder UI"
```

---

### Task 3: Implement computeRangeStats() — client-side stat computation

**Files:**
- Modify: `Fractal Sweep/model_dashboard.html` (JS)

- [ ] **Step 1: Add the core computation function**

Add after the range builder JS:

```javascript
function computeRangeStats(trades){
  const n = trades.length;
  if(n === 0) return null;
  const wins = trades.filter(t => t.outcome === 'WIN');
  const losses = trades.filter(t => t.outcome === 'LOSS');
  const nWins = wins.length, nLosses = losses.length;
  const wr = n > 0 ? nWins / n : 0;
  const sumWinR = wins.reduce((s,t) => s + t.r, 0);
  const sumLossR = losses.reduce((s,t) => s + Math.abs(t.r), 0);
  const ev_r = n > 0 ? (sumWinR - sumLossR) / n : 0;
  const pf = sumLossR > 0 ? sumWinR / sumLossR : 0;
  const ce = ev_r * pf;

  // Max consecutive losses
  let mcl = 0, run = 0;
  trades.forEach(t => { if(t.outcome==='LOSS'){run++;mcl=Math.max(mcl,run)}else{run=0} });

  // Equity curve + max DD + Sharpe
  const ACCT = 4500, RPT = 225;
  let eq = ACCT, peak = ACCT, minEq = ACCT, maxDD = 0;
  const dailyPnl = {};
  trades.slice().sort((a,b) => a.date.localeCompare(b.date)).forEach(t => {
    const pnl = t.r * RPT;
    eq += pnl;
    if(eq < minEq) minEq = eq;
    if(eq > peak) peak = eq;
    const dd = peak > 0 ? (peak - eq) / peak : 0;
    if(dd > maxDD) maxDD = dd;
    dailyPnl[t.date] = (dailyPnl[t.date]||0) + pnl;
  });
  const totalPnl = eq - ACCT;
  const blown = minEq <= 0;
  const dpArr = Object.values(dailyPnl);
  let sharpe = null;
  if(dpArr.length > 1){
    const mu = dpArr.reduce((s,v)=>s+v,0)/dpArr.length;
    const sd = Math.sqrt(dpArr.reduce((s,v)=>s+(v-mu)**2,0)/(dpArr.length-1));
    if(sd > 0) sharpe = Math.round(mu / sd * Math.sqrt(252) * 100) / 100;
  }
  const maxDDPct = Math.round(maxDD * 10000) / 100;

  // Classification breakdown
  const byClass = {};
  trades.forEach(t => {
    const cls = t.classification || 'Unclassified';
    if(!byClass[cls]) byClass[cls] = {n:0, wins:0};
    byClass[cls].n++;
    if(t.outcome === 'WIN') byClass[cls].wins++;
  });
  Object.values(byClass).forEach(c => {
    c.wr = c.n > 0 ? c.wins / c.n : 0;
    c.ev = 0; // simplified
  });

  // MAE/MFE distribution stats
  const maeVals = trades.map(t => t.mae_pct).filter(v => v != null && v > 0);
  const mfeVals = trades.map(t => t.mfe_pct).filter(v => v != null && v > 0);

  function distStats(vals){
    if(vals.length === 0) return {mean:0, median:0, mode:0, std:0};
    const sorted = vals.slice().sort((a,b)=>a-b);
    const mean = sorted.reduce((s,v)=>s+v,0) / sorted.length;
    const median = sorted.length % 2 === 0
      ? (sorted[sorted.length/2-1] + sorted[sorted.length/2]) / 2
      : sorted[Math.floor(sorted.length/2)];
    // Mode via binning at 0.01%
    const bins = {};
    sorted.forEach(v => { const b = Math.round(v * 100) / 100; bins[b] = (bins[b]||0)+1; });
    let modeVal = 0, modeCount = 0;
    Object.entries(bins).forEach(([b,c]) => { if(c > modeCount){modeCount=c; modeVal=+b} });
    const variance = sorted.reduce((s,v)=>s+(v-mean)**2,0) / (sorted.length - 1 || 1);
    const std = Math.sqrt(variance);
    return {mean: Math.round(mean*10000)/10000, median: Math.round(median*10000)/10000, mode: Math.round(modeVal*10000)/10000, std: Math.round(std*10000)/10000, values: sorted};
  }

  const maeDist = distStats(maeVals);
  const mfeDist = distStats(mfeVals);
  const mfeMaeRatio = maeDist.median > 0 ? Math.round(mfeDist.median / maeDist.median * 100) / 100 : 0;

  // Direction breakdown
  const longs = trades.filter(t => t.direction === 'LONG');
  const shorts = trades.filter(t => t.direction === 'SHORT');
  const longWR = longs.length > 0 ? longs.filter(t=>t.outcome==='WIN').length / longs.length : 0;
  const shortWR = shorts.length > 0 ? shorts.filter(t=>t.outcome==='WIN').length / shorts.length : 0;

  return {
    n, nWins, nLosses, wr, ev_r: Math.round(ev_r*1000)/1000, pf: Math.round(pf*1000)/1000,
    ce: Math.round(ce*1000)/1000, mcl, maxDDPct, totalPnl: Math.round(totalPnl),
    sharpe, blown, byClass, maeDist, mfeDist, mfeMaeRatio,
    longN: longs.length, shortN: shorts.length, longWR, shortWR,
    dateRange: trades.length > 0
      ? trades.map(t=>t.date).sort()[0] + ' to ' + trades.map(t=>t.date).sort().pop()
      : ''
  };
}
```

- [ ] **Step 2: Add applyCustomRanges() function**

```javascript
function applyCustomRanges(){
  const fullKey = `${activeModel}_${activeMode}_${activeCisd}`;
  const baseD = getProfileData(fullKey, activeProfile);
  if(!baseD || !baseD.recent_trades) return;

  const allTrades = baseD.recent_trades;
  const rangeResults = customRanges.map((r, i) => {
    if(!r.start || !r.end) return null;
    const filtered = allTrades.filter(t => t.date >= r.start && t.date <= r.end);
    return {
      label: `${r.start} to ${r.end}`,
      color: RANGE_COLORS[i],
      stats: computeRangeStats(filtered),
      trades: filtered
    };
  }).filter(Boolean);

  // Combined
  const allFiltered = rangeResults.flatMap(r => r.trades);
  const combinedStats = computeRangeStats(allFiltered);

  renderCustomView(rangeResults, combinedStats);
}
```

- [ ] **Step 3: Commit**

```bash
git add "Fractal Sweep/model_dashboard.html"
git commit -m "Add computeRangeStats and applyCustomRanges client-side engine"
```

---

### Task 4: Implement renderCustomView() — the dedicated Custom tab layout

**Files:**
- Modify: `Fractal Sweep/model_dashboard.html` (JS + HTML)

- [ ] **Step 1: Add the custom view container HTML**

After the existing tab content containers (search for the last `</div>` of tab content area), add:

```html
<div id="custom-view" style="display:none;padding:0 28px 40px;"></div>
```

- [ ] **Step 2: Update renderActive() to handle custom mode**

Modify `renderActive()`:

```javascript
function renderActive(){
  const fullKey = `${activeModel}_${activeMode}_${activeCisd}`;
  const baseD = getProfileData(fullKey, activeProfile);
  const customView = document.getElementById('custom-view');
  const normalTabs = document.getElementById('page-tabs');
  const metaRow = document.getElementById('meta-row');

  if(activeTF === 'custom'){
    // Hide normal tabs and hero, show custom view
    if(normalTabs) normalTabs.style.display = 'none';
    if(metaRow) metaRow.innerHTML = '';
    if(customView) customView.style.display = '';
    // Auto-apply if ranges exist
    if(customRanges.some(r => r.start && r.end)) applyCustomRanges();
    return;
  }

  // Normal mode
  if(normalTabs) normalTabs.style.display = '';
  if(customView) customView.style.display = 'none';
  if(!baseD){
    metaRow.innerHTML=`<div style="grid-column:1/-1;font-family:var(--font-data);font-size:11px;color:var(--text-muted);padding:8px">No data for ${fullKey} / ${activeProfile}. Run model_stats.py to generate.</div>`;
    return;
  }
  const D = getActiveTFData(baseD);
  renderModel(D);
  renderProfileCompare();
}
```

- [ ] **Step 3: Implement renderCustomView()**

```javascript
function renderCustomView(ranges, combined){
  const el = document.getElementById('custom-view');
  if(!el) return;
  const pct = v => v != null ? (v*100).toFixed(1)+'%' : '—';
  const fmtR = v => v != null ? (v>=0?'+':'')+v.toFixed(3)+'R' : '—';
  const fmtPct = v => v != null ? v.toFixed(4)+'%' : '—';

  let html = '';

  // ── A. Combined Hero Tiles ──
  if(combined){
    html += `<div style="margin-bottom:24px">
      <div style="font-family:var(--font-data);font-size:10px;font-weight:600;letter-spacing:0.06em;color:var(--text-muted);text-transform:uppercase;margin-bottom:10px">Combined · ${combined.n} trades · ${ranges.length} ranges</div>
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:10px">
        ${[
          {l:'Win Rate', v:pct(combined.wr), c:combined.wr>=0.55?'var(--green)':'var(--red)'},
          {l:'EV (R)', v:fmtR(combined.ev_r), c:combined.ev_r>0?'var(--green)':'var(--red)'},
          {l:'Prof Factor', v:combined.pf.toFixed(3), c:combined.pf>=1.5?'var(--green)':'var(--amber)'},
          {l:'CE', v:combined.ce.toFixed(3), c:combined.ce>=0.4?'var(--green)':combined.ce>=0.2?'var(--amber)':'var(--red)'},
          {l:'Total P&L', v:'$'+combined.totalPnl.toLocaleString(), c:combined.totalPnl>0?'var(--green)':'var(--red)'},
          {l:'Sharpe', v:combined.sharpe!=null?combined.sharpe.toFixed(2):'—', c:combined.sharpe>=5?'var(--green)':'var(--amber)'},
          {l:'Max DD', v:combined.maxDDPct.toFixed(1)+'%', c:combined.maxDDPct<10?'var(--green)':combined.maxDDPct<25?'var(--amber)':'var(--red)'},
          {l:'Max L Run', v:combined.mcl, c:'var(--red)'},
        ].map(c => `<div style="background:var(--bg-raised);border:1px solid var(--border);border-radius:8px;padding:10px 12px;text-align:center">
          <div style="font-family:var(--font-data);font-size:10px;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.04em;margin-bottom:4px">${c.l}</div>
          <div style="font-family:var(--font-data);font-size:18px;font-weight:700;color:${c.c}">${c.v}</div>
        </div>`).join('')}
      </div>
    </div>`;
  }

  // ── B. Side-by-Side Hero Tiles ──
  html += `<div style="margin-bottom:24px">
    <div style="font-family:var(--font-data);font-size:10px;font-weight:600;letter-spacing:0.06em;color:var(--text-muted);text-transform:uppercase;margin-bottom:10px">Side-by-Side Comparison</div>
    <div style="display:grid;grid-template-columns:repeat(${ranges.length},1fr);gap:12px">
      ${ranges.map(r => {
        if(!r.stats) return `<div style="background:var(--bg-raised);border:1px solid var(--border);border-radius:8px;padding:14px;color:var(--text-muted);font-size:11px">No trades in range</div>`;
        const s = r.stats;
        return `<div style="background:var(--bg-raised);border:1px solid var(--border);border-radius:8px;padding:14px;border-top:3px solid ${r.color}">
          <div style="font-family:var(--font-data);font-size:11px;font-weight:600;color:${r.color};margin-bottom:8px">${r.label}</div>
          <div style="font-family:var(--font-data);font-size:11px;color:var(--text-secondary);line-height:1.8">
            Trades: <strong>${s.n}</strong> · WR: <strong>${pct(s.wr)}</strong><br>
            EV: <strong>${fmtR(s.ev_r)}</strong> · PF: <strong>${s.pf.toFixed(2)}</strong><br>
            CE: <strong>${s.ce.toFixed(3)}</strong> · Max DD: <strong>${s.maxDDPct.toFixed(1)}%</strong><br>
            Long: ${s.longN} (${pct(s.longWR)}) · Short: ${s.shortN} (${pct(s.shortWR)})
          </div>
        </div>`;
      }).join('')}
    </div>
  </div>`;

  // ── C. Classification Breakdown ──
  const classNames = ['DWP','DNP','R1','R2','Unclassified'];
  html += `<div style="margin-bottom:24px">
    <div style="font-family:var(--font-data);font-size:10px;font-weight:600;letter-spacing:0.06em;color:var(--text-muted);text-transform:uppercase;margin-bottom:10px">Classification Breakdown</div>
    <table style="width:100%;border-collapse:collapse;font-family:var(--font-data);font-size:11px">
      <thead><tr style="border-bottom:1px solid var(--border)">
        <th style="text-align:left;padding:6px 10px;color:var(--text-muted)">Class</th>
        ${ranges.map(r => `<th style="text-align:center;padding:6px 10px;color:${r.color}">${r.label.split(' to ')[0]}</th>`).join('')}
        <th style="text-align:center;padding:6px 10px;color:${COMBINED_COLOR}">Combined</th>
      </tr></thead>
      <tbody>
        ${classNames.map(cls => `<tr style="border-bottom:1px solid var(--border)">
          <td style="padding:6px 10px;color:var(--text-primary)">${cls}</td>
          ${ranges.map(r => {
            const c = r.stats?.byClass?.[cls];
            return `<td style="text-align:center;padding:6px 10px;color:var(--text-secondary)">${c ? c.n+' · '+pct(c.wr) : '—'}</td>`;
          }).join('')}
          <td style="text-align:center;padding:6px 10px;color:var(--text-secondary)">${combined?.byClass?.[cls] ? combined.byClass[cls].n+' · '+pct(combined.byClass[cls].wr) : '—'}</td>
        </tr>`).join('')}
      </tbody>
    </table>
  </div>`;

  // ── D. MAE Distribution ──
  html += `<div style="margin-bottom:24px">
    <div style="font-family:var(--font-data);font-size:10px;font-weight:600;letter-spacing:0.06em;color:var(--text-muted);text-transform:uppercase;margin-bottom:10px">MAE Distribution</div>
    <div style="display:grid;grid-template-columns:repeat(${ranges.length + 1},1fr);gap:12px">
      ${ranges.map(r => renderDistCard('MAE', r.stats?.maeDist, r.color, r.label)).join('')}
      ${renderDistCard('MAE', combined?.maeDist, COMBINED_COLOR, 'Combined')}
    </div>
  </div>`;

  // ── E. MFE Distribution ──
  html += `<div style="margin-bottom:24px">
    <div style="font-family:var(--font-data);font-size:10px;font-weight:600;letter-spacing:0.06em;color:var(--text-muted);text-transform:uppercase;margin-bottom:10px">MFE Distribution</div>
    <div style="display:grid;grid-template-columns:repeat(${ranges.length + 1},1fr);gap:12px">
      ${ranges.map(r => renderDistCard('MFE', r.stats?.mfeDist, r.color, r.label)).join('')}
      ${renderDistCard('MFE', combined?.mfeDist, COMBINED_COLOR, 'Combined')}
    </div>
  </div>`;

  // ── F. Variance Comparison Chart ──
  html += `<div style="margin-bottom:24px">
    <div style="font-family:var(--font-data);font-size:10px;font-weight:600;letter-spacing:0.06em;color:var(--text-muted);text-transform:uppercase;margin-bottom:10px">MAE / MFE / Ratio Variance</div>
    <canvas id="cv-variance" style="width:100%;border-radius:8px;border:1px solid var(--border);background:var(--bg-raised)"></canvas>
  </div>`;

  el.innerHTML = html;

  // Draw variance chart
  drawVarianceChart(ranges, combined);
}

function renderDistCard(type, dist, color, label){
  if(!dist) return `<div style="background:var(--bg-raised);border:1px solid var(--border);border-radius:8px;padding:12px;color:var(--text-muted);font-size:11px">No data</div>`;
  return `<div style="background:var(--bg-raised);border:1px solid var(--border);border-radius:8px;padding:12px;border-top:3px solid ${color}">
    <div style="font-family:var(--font-data);font-size:10px;font-weight:600;color:${color};margin-bottom:8px">${label}</div>
    <canvas class="cv-dist-${type.toLowerCase()}" data-color="${color}" data-values='${JSON.stringify(dist.values||[])}' style="width:100%;height:80px"></canvas>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px;margin-top:8px;font-family:var(--font-data);font-size:10px;color:var(--text-secondary)">
      <div>Mode: <strong>${dist.mode.toFixed(4)}%</strong></div>
      <div>Median: <strong>${dist.median.toFixed(4)}%</strong></div>
      <div>Mean: <strong>${dist.mean.toFixed(4)}%</strong></div>
      <div>Std: <strong>${dist.std.toFixed(4)}%</strong></div>
    </div>
  </div>`;
}
```

- [ ] **Step 4: Commit**

```bash
git add "Fractal Sweep/model_dashboard.html"
git commit -m "Add renderCustomView with combined hero, side-by-side, classification, MAE/MFE"
```

---

### Task 5: Implement variance comparison chart and mini histograms

**Files:**
- Modify: `Fractal Sweep/model_dashboard.html` (JS)

- [ ] **Step 1: Add drawVarianceChart()**

```javascript
function drawVarianceChart(ranges, combined){
  const canvas = document.getElementById('cv-variance');
  if(!canvas) return;
  const dpr = window.devicePixelRatio || 1;
  const W = canvas.clientWidth * dpr;
  const H = 240 * dpr;
  canvas.width = W; canvas.height = H;
  canvas.style.height = '240px';
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  const w = canvas.clientWidth, h = 240;

  const bg = getComputedStyle(document.documentElement).getPropertyValue('--bg-raised').trim() || '#1a2332';
  const textC = getComputedStyle(document.documentElement).getPropertyValue('--text-muted').trim() || '#4a6480';
  const gridC = getComputedStyle(document.documentElement).getPropertyValue('--grid').trim() || '#1e2d3d';
  ctx.fillStyle = bg; ctx.fillRect(0,0,w,h);

  // Data points: each range + combined
  const points = [
    ...ranges.map(r => ({label: r.label.split(' to ')[0], color: r.color, stats: r.stats})),
    {label: 'Combined', color: COMBINED_COLOR, stats: combined}
  ].filter(p => p.stats);

  if(points.length === 0) return;

  const PAD = {top:30, right:20, bottom:40, left:50};
  const cW = w - PAD.left - PAD.right;
  const cH = h - PAD.top - PAD.bottom;
  const nGroups = points.length;
  const groupW = cW / nGroups;
  const barW = Math.min(20, groupW / 5);

  // Find max value for Y scale
  let maxVal = 0;
  points.forEach(p => {
    const s = p.stats;
    maxVal = Math.max(maxVal, s.maeDist.median + s.maeDist.std, s.mfeDist.median + s.mfeDist.std, s.mfeMaeRatio + 0.5);
  });
  maxVal = Math.ceil(maxVal * 10) / 10;
  if(maxVal === 0) maxVal = 1;

  // Y grid
  ctx.font = '500 9px "IBM Plex Mono",monospace';
  ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
  for(let i=0;i<=4;i++){
    const v = maxVal * i / 4;
    const y = PAD.top + cH - (v / maxVal) * cH;
    ctx.strokeStyle = gridC; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(PAD.left, y); ctx.lineTo(PAD.left+cW, y); ctx.stroke();
    ctx.fillStyle = textC;
    ctx.fillText(v.toFixed(2), PAD.left - 6, y);
  }

  points.forEach((p, gi) => {
    const cx = PAD.left + gi * groupW + groupW / 2;
    const s = p.stats;

    // 3 bars: MAE, MFE, Ratio
    const bars = [
      {val: s.maeDist.mode, med: s.maeDist.median, std: s.maeDist.std, col: '#f87171', label: 'MAE'},
      {val: s.mfeDist.mode, med: s.mfeDist.median, std: s.mfeDist.std, col: '#34d399', label: 'MFE'},
      {val: s.mfeMaeRatio, med: s.mfeMaeRatio, std: 0, col: '#60a5fa', label: 'Ratio'},
    ];

    bars.forEach((b, bi) => {
      const bx = cx + (bi - 1) * (barW + 3);
      // Mode bar (solid)
      const modeH = (b.val / maxVal) * cH;
      const modeY = PAD.top + cH - modeH;
      ctx.fillStyle = b.col + '99';
      ctx.fillRect(bx - barW/2, modeY, barW, modeH);

      // Median line (outline)
      const medH = (b.med / maxVal) * cH;
      const medY = PAD.top + cH - medH;
      ctx.strokeStyle = b.col; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(bx - barW/2, medY); ctx.lineTo(bx + barW/2, medY); ctx.stroke();

      // Std dev whiskers (skip for ratio)
      if(b.std > 0){
        const topW = Math.min(PAD.top + cH, PAD.top + cH - ((b.med + b.std) / maxVal) * cH);
        const botW = Math.min(PAD.top + cH, PAD.top + cH - (Math.max(0, b.med - b.std) / maxVal) * cH);
        ctx.strokeStyle = b.col + '88'; ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(bx, topW); ctx.lineTo(bx, botW);
        ctx.moveTo(bx - 4, topW); ctx.lineTo(bx + 4, topW);
        ctx.moveTo(bx - 4, botW); ctx.lineTo(bx + 4, botW);
        ctx.stroke();
      }
    });

    // X label
    ctx.fillStyle = p.color; ctx.font = '600 9px "IBM Plex Mono",monospace';
    ctx.textAlign = 'center'; ctx.textBaseline = 'top';
    ctx.fillText(p.label, cx, PAD.top + cH + 8);
  });

  // Legend
  ctx.font = '500 9px "IBM Plex Mono",monospace';
  ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
  [{col:'#f87171',l:'MAE'},{col:'#34d399',l:'MFE'},{col:'#60a5fa',l:'Ratio'}].forEach((lg, i) => {
    const lx = PAD.left + i * 70;
    ctx.fillStyle = lg.col; ctx.fillRect(lx, 8, 10, 10);
    ctx.fillStyle = textC; ctx.fillText(lg.l, lx + 14, 13);
  });
}
```

- [ ] **Step 2: Add mini histogram drawing after renderCustomView completes**

After `el.innerHTML = html;` and `drawVarianceChart()` in `renderCustomView()`, add:

```javascript
  // Draw mini histograms
  document.querySelectorAll('canvas.cv-dist-mae, canvas.cv-dist-mfe').forEach(cv => {
    const vals = JSON.parse(cv.dataset.values || '[]');
    const color = cv.dataset.color;
    drawMiniHist(cv, vals, color);
  });
```

And the helper:

```javascript
function drawMiniHist(canvas, values, color){
  if(!canvas || values.length === 0) return;
  const dpr = window.devicePixelRatio || 1;
  const W = canvas.clientWidth * dpr;
  const H = 80 * dpr;
  canvas.width = W; canvas.height = H;
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  const w = canvas.clientWidth, h = 80;
  const bg = getComputedStyle(document.documentElement).getPropertyValue('--bg-raised').trim() || '#1a2332';
  ctx.fillStyle = bg; ctx.fillRect(0,0,w,h);

  // Bin into 20 buckets
  const min = values[0], max = values[values.length-1];
  const range = max - min || 1;
  const nBins = 20;
  const bins = new Array(nBins).fill(0);
  values.forEach(v => {
    const bi = Math.min(nBins-1, Math.floor((v - min) / range * nBins));
    bins[bi]++;
  });
  const maxBin = Math.max(...bins);
  if(maxBin === 0) return;

  const barW = w / nBins;
  bins.forEach((count, i) => {
    const barH = (count / maxBin) * (h - 4);
    ctx.fillStyle = color + '66';
    ctx.fillRect(i * barW + 1, h - barH, barW - 2, barH);
  });
}
```

- [ ] **Step 3: Commit**

```bash
git add "Fractal Sweep/model_dashboard.html"
git commit -m "Add variance comparison chart and mini histograms for custom ranges"
```

---

### Task 6: Restore range builder state on page load and handle tab visibility

**Files:**
- Modify: `Fractal Sweep/model_dashboard.html` (JS)

- [ ] **Step 1: Restore custom ranges on page load**

In the initialization section (where `DATA` is loaded and first render happens), add after the initial `renderActive()` call:

```javascript
// Restore custom ranges UI if custom was last selected
if(activeTF === 'custom'){
  const builder = document.getElementById('custom-range-builder');
  if(builder) builder.style.display = '';
  renderRangeSlots();
}
```

Also persist `activeTF` to localStorage. In `switchTF()`:

```javascript
function switchTF(tf){
  activeTF=tf; _tradesPage=0;
  localStorage.setItem('fractal-active-tf', tf);
  const builder = document.getElementById('custom-range-builder');
  if(builder) builder.style.display = tf === 'custom' ? '' : 'none';
  if(tf === 'custom'){
    if(customRanges.length === 0) addCustomRange();
    renderRangeSlots();
  }
  renderActive();
}
```

And on page load, restore:

```javascript
const savedTF = localStorage.getItem('fractal-active-tf');
if(savedTF && savedTF !== 'all'){
  activeTF = savedTF;
  document.getElementById('tf-select').value = savedTF;
}
```

- [ ] **Step 2: Hide page tabs when custom is active**

The `renderActive()` function already handles this from Task 4 Step 2 — it sets `normalTabs.style.display = 'none'` when `activeTF === 'custom'`. Verify the element ID matches. The tab strip has id `page-tabs` or similar — check and update if needed.

Find the tab strip container and ensure it has an id:

```html
<div id="page-tabs" style="display:flex;...">
  <button class="page-tab" ...>Overview</button>
  <!-- ... -->
</div>
```

- [ ] **Step 3: Final integration test**

1. Open dashboard at `http://localhost:8001/Fractal Sweep/model_dashboard.html`
2. Select "Custom Ranges" from Period dropdown
3. Add 2 ranges (e.g., 2024-01-01 to 2024-06-30 and 2025-01-01 to 2025-06-30)
4. Click Apply
5. Verify: combined hero tiles, side-by-side cards, classification table, MAE/MFE histograms, variance chart
6. Refresh page — verify ranges are restored
7. Switch back to "All Time" — verify normal tabs reappear

- [ ] **Step 4: Commit**

```bash
git add "Fractal Sweep/model_dashboard.html"
git commit -m "Persist custom ranges and TF selection across page reloads"
```

---

### Task 7: Final commit and push

- [ ] **Step 1: Push all changes**

```bash
git push origin live-scanner
git stash && git checkout main && git merge live-scanner && git push origin main && git checkout live-scanner && git stash pop
```
