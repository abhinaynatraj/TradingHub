import { activeModel, activeTF, activeSmt, activeF3, activeF4, activeP42, activePd, activeProfile, activeMode, activeCisd, FILTER_STORAGE_KEY, SVG_FONT, isDark, setActiveSmt, setActiveF3, setActiveF4, setActiveP42, setActivePd } from './state.js';
import { C, lineChart, drawSetupViz, _drawMAEProbCurve, _drawMFEProbCurve, _drawExcursionHeatmap } from './charts.js';
import { pct, evFmt, pfFmt, evCls, fmtDateRange, _tradingDaysFromRange, showTip, hideTip, csvEscape, triggerCSVDownload } from './utils.js';
import { getProfileData, getActiveTFData, getFilteredD } from './data.js';


let _tradesPage = 0;

let _renderActiveCallback = null;
export function setRenderActive(fn) { _renderActiveCallback = fn; }
function renderActive() { if (_renderActiveCallback) _renderActiveCallback(); }

function _getActiveD() {
  const fullKey = activeModel + '_' + activeMode + '_' + activeCisd;
  const baseD = getProfileData(fullKey, activeProfile);
  if (!baseD) return null;
  return getActiveTFData(baseD);
}

const _RANGE_PALETTE = ['#3b82f6','#f59e0b','#8b5cf6','#14b8a6','#ef4444','#06b6d4','#ec4899','#84cc16','#f97316','#6366f1'];
const RANGE_COLORS = new Proxy(_RANGE_PALETTE, { get: (t, p) => typeof p === 'string' && !isNaN(p) ? t[p % t.length] : t[p] });
const COMBINED_COLOR = '#94a3b8';
export let customRanges = JSON.parse(localStorage.getItem('fractal-custom-ranges') || '[]');

function getSmtFilteredTrades(trades) {
  if (!trades || !trades.length) return trades;
  let out = trades;
  if (activeSmt) out = out.filter(t => t.smt === true);
  if (activeF3)  out = out.filter(t => t.passes_f3 === true);
  if (activeF4)  out = out.filter(t => t.passes_f4 === true);
  if (activeP42) out = out.filter(t => t.passes_p42 === true);
  if (activePd)  out = out.filter(t => t.passes_pd_cisd === true);
  return out;
}

function hasNonBaselineFilters() {
  return activeSmt || activeF3 || activeF4 || activeP42 || activePd;
}

function switchSMT(checked) {
  setActiveSmt(!!checked);
  _saveFilters();
  _tradesPage = 0;
  const D = _getActiveD();
  if (!D) return;
  renderActive();
}

function switchF3(checked) {
  setActiveF3(!!checked);
  _saveFilters();
  _tradesPage = 0;
  renderActive();
}

function switchF4(checked) {
  setActiveF4(!!checked);
  _saveFilters();
  _tradesPage = 0;
  renderActive();
}

function switchP42(checked) {
  setActiveP42(!!checked);
  _saveFilters();
  _tradesPage = 0;
  renderActive();
}

function switchPD(checked) {
  setActivePd(!!checked);
  _saveFilters();
  _tradesPage = 0;
  renderActive();
}

function _saveFilters() {
  localStorage.setItem(FILTER_STORAGE_KEY, JSON.stringify({
    smt: activeSmt, f3: activeF3, f4: activeF4, p42: activeP42, pd: activePd
  }));
}
function _restoreFilters() {
  try {
    const s = JSON.parse(localStorage.getItem(FILTER_STORAGE_KEY) || '{}');
    setActiveSmt(!!s.smt); setActiveF3(!!s.f3); setActiveF4(!!s.f4);
    setActiveP42(!!s.p42); setActivePd(!!s.pd);
  } catch(e) { /* ignore corrupt storage */ }
  const smtEl = document.getElementById('smt-checkbox');
  const f3El  = document.getElementById('f3-checkbox');
  const f4El  = document.getElementById('f4-checkbox');
  const p42El = document.getElementById('p42-checkbox');
  const pdEl  = document.getElementById('pd-checkbox');
  if(smtEl) smtEl.checked = activeSmt;
  if(f3El)  f3El.checked  = activeF3;
  if(f4El)  f4El.checked  = activeF4;
  if(p42El) p42El.checked = activeP42;
  if(pdEl)  pdEl.checked  = activePd;
}
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
  const btn = document.getElementById('add-range-btn');
  if(btn) btn.disabled = false;
}

function addCustomRange(){
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

function computeKDE(values, nPoints){
  nPoints = nPoints || 200;
  if(values.length < 2) return [];
  const sorted = values.slice().sort((a,b) => a-b);
  const n = sorted.length;
  const mean = sorted.reduce((s,v)=>s+v,0)/n;
  const std = Math.sqrt(sorted.reduce((s,v)=>s+(v-mean)**2,0)/(n-1));
  const iqr = sorted[Math.floor(n*0.75)] - sorted[Math.floor(n*0.25)];
  const h = 0.9 * Math.min(std, iqr/1.34) * Math.pow(n, -0.2);
  if(h <= 0) return [];
  const min = sorted[0] - 3*h, max = sorted[n-1] + 3*h;
  const step = (max - min) / nPoints;
  const points = [];
  for(let i = 0; i < nPoints; i++){
    const x = min + i * step;
    let density = 0;
    for(const v of sorted) density += Math.exp(-0.5 * ((x - v) / h) ** 2);
    density /= n * h * Math.sqrt(2 * Math.PI);
    points.push({x, y: density});
  }
  return points;
}

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
  const avgWinR = nWins > 0 ? sumWinR / nWins : 0;

  // Streaks
  let mcl = 0, mcw = 0, lRun = 0, wRun = 0;
  const winStreaks = [], lossStreaks = [];
  trades.forEach(t => {
    if(t.outcome === 'LOSS'){ lRun++; mcl = Math.max(mcl, lRun); if(wRun > 0) winStreaks.push(wRun); wRun = 0; }
    else { wRun++; mcw = Math.max(mcw, wRun); if(lRun > 0) lossStreaks.push(lRun); lRun = 0; }
  });
  if(wRun > 0) winStreaks.push(wRun);
  if(lRun > 0) lossStreaks.push(lRun);
  const avgWinStreak = winStreaks.length > 0 ? winStreaks.reduce((s,v)=>s+v,0)/winStreaks.length : 0;
  const avgLossStreak = lossStreaks.length > 0 ? lossStreaks.reduce((s,v)=>s+v,0)/lossStreaks.length : 0;

  // Equity curve
  const ACCT = 2000, RPT = 200;
  let eq = ACCT, peak = ACCT, minEq = ACCT, maxDD = 0;
  const dailyPnl = {};
  const equityCurve = [ACCT];
  const sortedTrades = trades.slice().sort((a,b) => a.date.localeCompare(b.date));
  sortedTrades.forEach(t => {
    const pnl = t.r * RPT;
    eq += pnl;
    equityCurve.push(eq);
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

  // By hour
  const byHour = {};
  for(let h = 7; h <= 16; h++) byHour[h] = {n:0, wins:0, wr:0};
  trades.forEach(t => {
    const h = t.hr != null ? t.hr : null;
    if(h == null || h < 7 || h > 16) return;
    byHour[h].n++;
    if(t.outcome === 'WIN') byHour[h].wins++;
  });
  Object.values(byHour).forEach(b => { b.wr = b.n > 0 ? b.wins / b.n : 0; });

  // MAE/MFE distributions
  const maeVals = trades.map(t => t.mae_pct).filter(v => v != null && v > 0);
  const mfeVals = trades.map(t => t.mfe_pct).filter(v => v != null && v > 0);
  function distStats(vals){
    if(vals.length === 0) return {mean:0, median:0, mode:0, std:0, values:[]};
    const sorted = vals.slice().sort((a,b)=>a-b);
    const mean = sorted.reduce((s,v)=>s+v,0) / sorted.length;
    const median = sorted.length % 2 === 0 ? (sorted[sorted.length/2-1] + sorted[sorted.length/2]) / 2 : sorted[Math.floor(sorted.length/2)];
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

  // Percentiles helper
  function percentiles(sorted){
    if(sorted.length === 0) return {p5:0,p10:0,p25:0,p50:0,p75:0,p90:0,p95:0};
    const p = q => { const i = q * (sorted.length - 1); const lo = Math.floor(i); const hi = Math.ceil(i); return lo === hi ? sorted[lo] : sorted[lo] * (hi - i) + sorted[hi] * (i - lo); };
    return {p5:+p(0.05).toFixed(4),p10:+p(0.10).toFixed(4),p25:+p(0.25).toFixed(4),p50:+p(0.50).toFixed(4),p75:+p(0.75).toFixed(4),p90:+p(0.90).toFixed(4),p95:+p(0.95).toFixed(4)};
  }
  const maePercentiles = percentiles(maeDist.values);
  const mfePercentiles = percentiles(mfeDist.values);

  // R-distribution
  const rDist = {'-1':0, '0-1':0, '1-2':0, '2-3':0, '3-5':0, '5+':0};
  trades.forEach(t => {
    const r = t.r;
    if(r <= -0.5) rDist['-1']++;
    else if(r < 1) rDist['0-1']++;
    else if(r < 2) rDist['1-2']++;
    else if(r < 3) rDist['2-3']++;
    else if(r < 5) rDist['3-5']++;
    else rDist['5+']++;
  });

  // Risk pts stats
  const riskVals = trades.map(t => t.risk_pts).filter(v => v != null && v > 0).sort((a,b)=>a-b);
  const riskMean = riskVals.length > 0 ? riskVals.reduce((s,v)=>s+v,0)/riskVals.length : 0;
  function quartileStats(vals, allTrades){
    if(vals.length < 4) return {low:{n:0,wr:0,ev:0},medLow:{n:0,wr:0,ev:0},medHigh:{n:0,wr:0,ev:0},high:{n:0,wr:0,ev:0}};
    const q1 = vals[Math.floor(vals.length*0.25)], q2 = vals[Math.floor(vals.length*0.5)], q3 = vals[Math.floor(vals.length*0.75)];
    function bucket(lo, hi){
      const bt = allTrades.filter(t => t.risk_pts != null && t.risk_pts >= lo && t.risk_pts < hi);
      const bw = bt.filter(t => t.outcome === 'WIN').length;
      const bwr = bt.length > 0 ? bw / bt.length : 0;
      const bev = bt.length > 0 ? (bt.filter(t=>t.outcome==='WIN').reduce((s,t)=>s+t.r,0) - bt.filter(t=>t.outcome==='LOSS').reduce((s,t)=>s+Math.abs(t.r),0)) / bt.length : 0;
      return {n: bt.length, wr: bwr, ev: +bev.toFixed(3)};
    }
    return {low: bucket(0, q1), medLow: bucket(q1, q2), medHigh: bucket(q2, q3), high: bucket(q3, Infinity)};
  }
  const riskPtsStats = {mean: +riskMean.toFixed(2), quartiles: quartileStats(riskVals, trades)};

  // Direction stats
  const longs = trades.filter(t => t.direction === 'LONG');
  const shorts = trades.filter(t => t.direction === 'SHORT');
  const longWR = longs.length > 0 ? longs.filter(t=>t.outcome==='WIN').length / longs.length : 0;
  const shortWR = shorts.length > 0 ? shorts.filter(t=>t.outcome==='WIN').length / shorts.length : 0;
  const longWins = longs.filter(t=>t.outcome==='WIN');
  const longLosses = longs.filter(t=>t.outcome==='LOSS');
  const longEV = longs.length > 0 ? (longWins.reduce((s,t)=>s+t.r,0) - longLosses.reduce((s,t)=>s+Math.abs(t.r),0)) / longs.length : 0;
  const shortWins = shorts.filter(t=>t.outcome==='WIN');
  const shortLosses = shorts.filter(t=>t.outcome==='LOSS');
  const shortEV = shorts.length > 0 ? (shortWins.reduce((s,t)=>s+t.r,0) - shortLosses.reduce((s,t)=>s+Math.abs(t.r),0)) / shorts.length : 0;

  // KDE and scatter
  const maeDensity = computeKDE(maeVals);
  const mfeDensity = computeKDE(mfeVals);
  const scatterPoints = trades.filter(t => t.mae_pct != null && t.mfe_pct != null).map(t => ({mae: t.mae_pct, mfe: t.mfe_pct}));

  return {
    n, nWins, nLosses, wr, ev_r: Math.round(ev_r*1000)/1000, pf: Math.round(pf*1000)/1000,
    ce: Math.round(ce*1000)/1000, mcl, mcw, maxDDPct, totalPnl: Math.round(totalPnl), sharpe, blown, minEq: Math.round(minEq),
    byHour, maeDist, mfeDist, mfeMaeRatio,
    longN: longs.length, shortN: shorts.length, longWR, shortWR, longEV: +longEV.toFixed(3), shortEV: +shortEV.toFixed(3),
    avgWinR: +avgWinR.toFixed(3),
    maePercentiles, mfePercentiles,
    rDistribution: rDist,
    riskPtsStats,
    winStreaks, lossStreaks,
    maxWinStreak: mcw, maxLossStreak: mcl,
    avgWinStreak: +avgWinStreak.toFixed(1), avgLossStreak: +avgLossStreak.toFixed(1),
    equityCurve,
    maeDensity, mfeDensity, scatterPoints,
    dateRange: trades.length > 0 ? trades.map(t=>t.date).sort()[0] + ' to ' + trades.map(t=>t.date).sort().pop() : ''
  };
}

/* ── Walk-Forward Regime Analysis: Core Computation Functions ─────── */

// Regime stats for raw_measure: MAE/MFE distribution characteristics per range.
// No WIN/LOSS needed — every trade has mae_pct and mfe_pct.
function computeRegimeStats(trades) {
  const n = trades.length;
  if (n === 0) return null;

  function pctl(sorted, q) {
    if (!sorted.length) return 0;
    const i = q * (sorted.length - 1);
    const lo = Math.floor(i), hi = Math.ceil(i);
    return lo === hi ? sorted[lo] : sorted[lo] + (sorted[hi]-sorted[lo]) * (i-lo);
  }
  function mean(arr) { return arr.length ? arr.reduce((s,v)=>s+v,0)/arr.length : 0; }

  const mae = trades.map(t => t.mae_pct).filter(v => v != null && isFinite(v) && v >= 0).sort((a,b)=>a-b);
  const mfe = trades.map(t => t.mfe_pct).filter(v => v != null && isFinite(v) && v >= 0).sort((a,b)=>a-b);

  const medMAE  = pctl(mae, 0.5);
  const medMFE  = pctl(mfe, 0.5);
  const meanMAE = mean(mae);
  const meanMFE = mean(mfe);

  // Ratio: MAE / MFE. Low = directional (little pullback vs run). High = choppy.
  const ratioMed  = medMFE  > 0 ? medMAE / medMFE : null;
  const ratioMean = meanMFE > 0 ? meanMAE / meanMFE : null;

  // Asymmetry: (MFE - MAE) / (MFE + MAE). -1 = all pain, +1 = all reward, 0 = symmetric.
  const asymMed  = (medMFE + medMAE) > 0 ? (medMFE - medMAE) / (medMFE + medMAE) : 0;
  const asymMean = (meanMFE + meanMAE) > 0 ? (meanMFE - meanMAE) / (meanMFE + meanMAE) : 0;

  // Per-trade ratios for dispersion
  const perTradeRatios = trades
    .map(t => (t.mae_pct != null && t.mfe_pct != null && t.mfe_pct > 0) ? t.mae_pct / t.mfe_pct : null)
    .filter(v => v != null && isFinite(v) && v >= 0)
    .sort((a,b)=>a-b);
  const ratioP25 = pctl(perTradeRatios, 0.25);
  const ratioP75 = pctl(perTradeRatios, 0.75);

  // Direction split
  const longs  = trades.filter(t => t.direction === 'LONG');
  const shorts = trades.filter(t => t.direction === 'SHORT');
  function subRatio(sub) {
    const sMae = sub.map(t=>t.mae_pct).filter(v=>v!=null && v>=0).sort((a,b)=>a-b);
    const sMfe = sub.map(t=>t.mfe_pct).filter(v=>v!=null && v>=0).sort((a,b)=>a-b);
    const mm = pctl(sMae, 0.5), mf = pctl(sMfe, 0.5);
    return { n: sub.length, medMAE: mm, medMFE: mf, ratio: mf > 0 ? mm/mf : null };
  }

  return {
    n,
    med_mae: medMAE,
    med_mfe: medMFE,
    mean_mae: meanMAE,
    mean_mfe: meanMFE,
    ratio_med: ratioMed,
    ratio_mean: ratioMean,
    asym_med: asymMed,
    asym_mean: asymMean,
    ratio_p25: ratioP25,
    ratio_p75: ratioP75,
    long: subRatio(longs),
    short: subRatio(shorts),
  };
}
function renderCustomRangesRegime(rangeResults) {
  const cv = document.getElementById('custom-view');
  if (!cv) return;

  if (!rangeResults || rangeResults.length === 0) {
    cv.innerHTML = '<div style="padding:40px 0;text-align:center;font-family:var(--font-data);font-size:12px;color:var(--text-muted)">No ranges defined. Add ranges and click Apply.</div>';
    return;
  }

  const fmtPct = v => v != null ? (+v).toFixed(4) + '%' : '\u2014';
  const fmtRatio = v => v != null ? v.toFixed(3) : '\u2014';
  const fmtAsym = v => v != null ? (v >= 0 ? '+' : '') + (v*100).toFixed(1) + '%' : '\u2014';

  // Regime character classifier for the ratio
  function regimeLabel(ratio) {
    if (ratio == null) return { label: '\u2014', color: 'var(--text-muted)' };
    if (ratio <= 0.40) return { label: 'Directional',   color: '#10b981' };
    if (ratio <= 0.65) return { label: 'Favourable',    color: '#60a5fa' };
    if (ratio <= 0.90) return { label: 'Balanced',      color: '#fbbf24' };
    if (ratio <= 1.25) return { label: 'Choppy',        color: '#fb923c' };
    return                     { label: 'Adverse',      color: '#ef4444' };
  }

  // Delta vs first range (baseline)
  const baseline = rangeResults[0]?.stats;

  let html = `<div style="padding:24px 0 40px">`;
  html += `<div style="font-family:var(--font-data);font-size:10px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--text-muted);margin-bottom:8px">Regime Comparison \u00b7 MAE : MFE</div>`;
  html += `<div style="font-family:var(--font-data);font-size:11px;color:var(--text-secondary);line-height:1.6;margin-bottom:20px">
    Compares the <strong style="color:var(--text-primary)">character</strong> of each period by MAE / MFE ratio \u2014 lower ratio means trades run favourably with little pullback (directional regime); higher ratio means trades take as much heat as reward (choppy).
    Performance metrics (WR / EV / PF) aren't applicable for raw measure \u2014 there's no SL/TP resolution. This view shows regime drift only.
  </div>`;

  // Headline comparison cards
  html += `<div style="display:grid;grid-template-columns:repeat(${rangeResults.length},1fr);gap:12px;margin-bottom:24px">`;
  rangeResults.forEach((r, idx) => {
    const s = r.stats;
    if (!s) {
      html += `<div style="background:var(--bg-raised);border:1px solid var(--border);border-radius:10px;padding:16px">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
          <div style="width:10px;height:10px;border-radius:3px;background:${r.color}"></div>
          <div style="font-family:var(--font-data);font-size:10px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.05em">${r.label}</div>
        </div>
        <div style="font-family:var(--font-data);font-size:11px;color:var(--text-muted)">No trades in range.</div>
      </div>`;
      return;
    }
    const reg = regimeLabel(s.ratio_med);
    const isBaseline = idx === 0;
    const drift = !isBaseline && baseline && baseline.ratio_med != null && s.ratio_med != null
      ? ((s.ratio_med - baseline.ratio_med) / baseline.ratio_med * 100)
      : null;
    const driftStr = drift != null
      ? `<span style="color:${Math.abs(drift) < 10 ? 'var(--green)' : Math.abs(drift) < 25 ? 'var(--amber)' : 'var(--red)'};font-weight:600">${drift >= 0 ? '+' : ''}${drift.toFixed(1)}% vs baseline</span>`
      : `<span style="color:var(--text-muted)">baseline</span>`;

    html += `<div style="background:var(--bg-card);border:1px solid ${r.color}44;border-radius:10px;padding:16px 18px;box-shadow:var(--shadow);position:relative;overflow:hidden">
      <div style="position:absolute;top:0;left:0;width:100%;height:3px;background:${r.color}"></div>
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
        <div style="width:10px;height:10px;border-radius:3px;background:${r.color}"></div>
        <div style="font-family:var(--font-data);font-size:10px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.05em">${r.label}</div>
      </div>
      <div style="font-family:var(--font-data);font-size:10px;color:var(--text-muted);margin-bottom:4px">MAE : MFE ratio</div>
      <div style="font-family:var(--font-display);font-size:30px;font-weight:800;color:${reg.color};line-height:1">${fmtRatio(s.ratio_med)}</div>
      <div style="font-family:var(--font-data);font-size:11px;font-weight:700;color:${reg.color};margin-top:4px">${reg.label}</div>
      <div style="font-family:var(--font-data);font-size:10px;color:var(--text-muted);margin-top:8px">${s.n.toLocaleString()} trades \u00b7 ${driftStr}</div>
    </div>`;
  });
  html += `</div>`;

  // Detailed metrics table
  html += `<div style="font-family:var(--font-data);font-size:10px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--text-muted);margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid var(--border)">Detailed Regime Metrics</div>`;
  html += `<div style="overflow-x:auto;margin-bottom:28px"><table style="width:100%;border-collapse:collapse;font-family:var(--font-data);font-size:11px">
    <thead><tr style="border-bottom:1px solid var(--border-mid);color:var(--text-muted);font-size:10px;text-transform:uppercase;letter-spacing:.04em">
      <th style="padding:8px 10px;text-align:left;font-weight:400">Metric</th>
      ${rangeResults.map(r => `<th style="padding:8px 10px;text-align:right;font-weight:500;color:${r.color}">${r.label.split(' to ')[0]}</th>`).join('')}
    </tr></thead><tbody>`;

  const rows = [
    { lbl:'Trades',          f:s=> s.n.toLocaleString(),     note:'sample size' },
    { lbl:'Median MAE',      f:s=> fmtPct(s.med_mae),        note:'typical adverse excursion' },
    { lbl:'Median MFE',      f:s=> fmtPct(s.med_mfe),        note:'typical favourable excursion' },
    { lbl:'Mean MAE',        f:s=> fmtPct(s.mean_mae),       note:'arithmetic avg' },
    { lbl:'Mean MFE',        f:s=> fmtPct(s.mean_mfe),       note:'arithmetic avg' },
    { lbl:'MAE : MFE (med)', f:s=> fmtRatio(s.ratio_med),    note:'lower = directional', emphasize:true },
    { lbl:'MAE : MFE (mean)',f:s=> fmtRatio(s.ratio_mean),   note:'mean-based ratio' },
    { lbl:'Asymmetry (med)', f:s=> fmtAsym(s.asym_med),      note:'+1 = all reward, \u22121 = all pain' },
    { lbl:'Ratio IQR',       f:s=> `${fmtRatio(s.ratio_p25)} \u2013 ${fmtRatio(s.ratio_p75)}`, note:'p25\u2013p75 per-trade ratio spread' },
  ];
  rows.forEach(row => {
    html += `<tr style="border-bottom:1px solid var(--border)${row.emphasize?';background:var(--bg-raised)':''}">
      <td style="padding:7px 10px;color:var(--text-primary);font-weight:${row.emphasize?700:500}">${row.lbl}
        <div style="font-size:9px;color:var(--text-muted);font-weight:400;margin-top:1px">${row.note}</div>
      </td>
      ${rangeResults.map(r => {
        if (!r.stats) return `<td style="padding:7px 10px;text-align:right;color:var(--text-muted)">\u2014</td>`;
        return `<td style="padding:7px 10px;text-align:right;color:var(--text-primary);font-weight:${row.emphasize?700:500}">${row.f(r.stats)}</td>`;
      }).join('')}
    </tr>`;
  });
  html += `</tbody></table></div>`;

  // Direction split
  html += `<div style="font-family:var(--font-data);font-size:10px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--text-muted);margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid var(--border)">Direction Split \u00b7 LONG vs SHORT Regime</div>`;
  html += `<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-family:var(--font-data);font-size:11px">
    <thead><tr style="border-bottom:1px solid var(--border-mid);color:var(--text-muted);font-size:10px;text-transform:uppercase;letter-spacing:.04em">
      <th style="padding:8px 10px;text-align:left;font-weight:400">Range</th>
      <th style="padding:8px 10px;text-align:left;font-weight:400">Dir</th>
      <th style="padding:8px 10px;text-align:right;font-weight:400">N</th>
      <th style="padding:8px 10px;text-align:right;font-weight:400">Med MAE</th>
      <th style="padding:8px 10px;text-align:right;font-weight:400">Med MFE</th>
      <th style="padding:8px 10px;text-align:right;font-weight:400">MAE : MFE</th>
      <th style="padding:8px 10px;text-align:left;font-weight:400">Character</th>
    </tr></thead><tbody>`;
  rangeResults.forEach(r => {
    if (!r.stats) return;
    [['LONG', r.stats.long, 'var(--green)'], ['SHORT', r.stats.short, 'var(--red)']].forEach(([dir, sub, dirColor]) => {
      if (!sub || sub.n === 0) {
        html += `<tr style="border-bottom:1px solid var(--border)">
          <td style="padding:6px 10px;color:${r.color}">${r.label.split(' to ')[0]}</td>
          <td style="padding:6px 10px;font-weight:700;color:${dirColor}">${dir}</td>
          <td style="padding:6px 10px;text-align:right;color:var(--text-muted)" colspan="5">\u2014 no trades</td>
        </tr>`;
        return;
      }
      const reg = regimeLabel(sub.ratio);
      html += `<tr style="border-bottom:1px solid var(--border)">
        <td style="padding:6px 10px;color:${r.color}">${r.label.split(' to ')[0]}</td>
        <td style="padding:6px 10px;font-weight:700;color:${dirColor}">${dir}</td>
        <td style="padding:6px 10px;text-align:right;color:var(--text-muted)">${sub.n.toLocaleString()}</td>
        <td style="padding:6px 10px;text-align:right;color:#fbbf24">${fmtPct(sub.medMAE)}</td>
        <td style="padding:6px 10px;text-align:right;color:#10b981">${fmtPct(sub.medMFE)}</td>
        <td style="padding:6px 10px;text-align:right;color:${reg.color};font-weight:700">${fmtRatio(sub.ratio)}</td>
        <td style="padding:6px 10px;color:${reg.color};font-weight:600">${reg.label}</td>
      </tr>`;
    });
  });
  html += `</tbody></table></div>`;

  html += `</div>`;
  cv.innerHTML = html;
}
function computeTrainParams(trades) {
  const winners = trades.filter(t => t.outcome === 'WIN');
  if (winners.length < 5) return null;

  // Percentile helper (linear interpolation on sorted array)
  function pctl(sorted, q) {
    const i = q * (sorted.length - 1);
    const lo = Math.floor(i), hi = Math.ceil(i);
    return lo === hi ? sorted[lo] : sorted[lo] * (hi - i) + sorted[hi] * (i - lo);
  }

  // MAE percentiles from winners
  const maeVals = winners.map(t => t.mae_pct).filter(v => v != null).sort((a, b) => a - b);
  const maeMax = maeVals.length ? maeVals[maeVals.length - 1] : 0;
  const maeP90 = maeVals.length ? pctl(maeVals, 0.90) : 0;
  const maeP85 = maeVals.length ? pctl(maeVals, 0.85) : 0;
  const maeP50 = maeVals.length ? pctl(maeVals, 0.50) : 0;

  // MFE PTQ from winners: highest reach_rate where p_pos >= 0.70, fallback 0.50
  const mfeVals = winners.map(t => t.mfe_pct).filter(v => v != null).sort((a, b) => a - b);
  const mfeP50 = mfeVals.length ? pctl(mfeVals, 0.50) : 0;

  let ptqLevel = null, ptqReachRate = null;
  let _ptqFallback = null, _ptqFallbackRR = null;

  if (mfeVals.length > 0) {
    [5, 10, 15, 20, 25, 30, 33, 40, 50, 60, 75, 90].forEach(reachRate => {
      const thr = pctl(mfeVals, 1 - reachRate / 100);
      const reached = winners.filter(t => t.mfe_pct != null && t.mfe_pct >= thr);
      if (reached.length === 0) return;
      const nPos = reached.filter(t => t.outcome === 'WIN').length;
      const pPos = nPos / reached.length;
      if (pPos >= 0.70) { ptqLevel = thr; ptqReachRate = reachRate; }
      else if (pPos >= 0.50 && _ptqFallback === null) { _ptqFallback = thr; _ptqFallbackRR = reachRate; }
    });
    if (ptqLevel === null && _ptqFallback !== null) { ptqLevel = _ptqFallback; ptqReachRate = _ptqFallbackRR; }
  }

  // KDE densities
  const maeDensity = computeKDE(maeVals);
  const mfeDensity = computeKDE(mfeVals);

  return {
    nWinners: winners.length,
    mae: { max: maeMax, p90: maeP90, p85: maeP85, p50: maeP50 },
    mfe: { ptq: ptqLevel, ptqReachRate, p50: mfeP50 },
    maeDensity, mfeDensity
  };
}

function resolveWithStopCap(trades, slCapPct) {
  return trades.map(t => {
    if (t.mae_pct > slCapPct) {
      return Object.assign({}, t, { outcome: 'LOSS', r: -1.0 });
    }
    return Object.assign({}, t);
  });
}

// Re-resolve trades with a fixed MFE-based take-profit cap.
// Trades where mfe_pct >= tpLevelPct are converted to WIN with r = tpLevelPct / original_risk_pct.
// Because risk_pts varies per trade we approximate the TP R-multiple as (tpLevelPct / original_mae_sl_pct)
// but since we don't have a clean "risk_pct" field we use the trade's structural r on wins and keep losses.
// Simpler and consistent with walk-forward logic: treat TP as a fixed fraction of the structural 1R.
// Specifically: if mfe_pct >= tpLevelPct → WIN with r = tpLevelPct / mfe_pct * original_r  (scale winner's R)
// For a structural-1R trade the original_r on a WIN is already 1.0, so scaled r = tpLevelPct / mfe_pct.
// Trades that are already LOSSes and whose mfe_pct < tpLevelPct keep their original outcome.
function resolveWithMFETarget(trades, tpLevelPct) {
  if (tpLevelPct == null || tpLevelPct <= 0) return trades.map(t => Object.assign({}, t));
  return trades.map(t => {
    const mfe = t.mfe_pct;
    if (mfe == null) return Object.assign({}, t);
    if (mfe >= tpLevelPct) {
      // This trade reached the TP — record as WIN with r scaled to TP level
      const originalR = Math.abs(t.r);
      const scaledR = originalR > 0 ? (tpLevelPct / mfe) * originalR : tpLevelPct / mfe;
      return Object.assign({}, t, { outcome: 'WIN', r: Math.max(scaledR, 0.01) });
    }
    // Trade never reached TP — keep original outcome
    return Object.assign({}, t);
  });
}

function computeRegimeFingerprint(trades, startDate, endDate) {
  const n = trades.length;
  const avgRisk = n > 0 ? trades.reduce((s, t) => s + (t.risk_pts || 0), 0) / n : 0;
  const longPct = n > 0 ? trades.filter(t => t.direction === 'LONG').length / n * 100 : 0;

  const maeVals = trades.map(t => t.mae_pct).filter(v => v != null).sort((a, b) => a - b);
  const mfeVals = trades.map(t => t.mfe_pct).filter(v => v != null).sort((a, b) => a - b);
  const medMAE = maeVals.length ? maeVals[Math.floor(maeVals.length / 2)] : 0;
  const medMFE = mfeVals.length ? mfeVals[Math.floor(mfeVals.length / 2)] : 0;
  const mfeMaeRatio = medMAE > 0 ? medMFE / medMAE : 0;

  // Trades per calendar day
  const d0 = new Date(startDate), d1 = new Date(endDate);
  const calDays = Math.max(1, (d1 - d0) / (1000 * 60 * 60 * 24) + 1);
  const density = n / calDays;

  return { avgRisk, longPct, mfeMaeRatio, density };
}

function computeOverfitScore(trainEV, testEV) {
  if (trainEV == null || trainEV === 0) return { score: null, label: '\u2014', cls: 'var(--text-muted)' };
  const score = Math.round((testEV / trainEV) * 100);
  let label, cls;
  if (score >= 80) { label = 'ROBUST'; cls = 'var(--green)'; }
  else if (score >= 60) { label = 'MILD DECAY'; cls = 'var(--amber)'; }
  else if (score >= 0) { label = 'OVERFIT'; cls = 'var(--red)'; }
  else { label = 'INVERTED'; cls = 'var(--red)'; }
  return { score, label, cls };
}

function findBestVariant(pairs) {
  const names = ['Sweep Extreme', 'Max MAE', 'P90 MAE', 'P85 MAE', 'P50 MAE'];
  let bestIdx = 0, bestCV = Infinity;

  for (let vi = 0; vi < 5; vi++) {
    const testEVs = pairs.map(p => p.variants[vi].test?.ev_r).filter(v => v != null);
    if (testEVs.length < 2) continue;
    const mean = testEVs.reduce((s, v) => s + v, 0) / testEVs.length;
    if (mean === 0) continue;
    const std = Math.sqrt(testEVs.reduce((s, v) => s + (v - mean) ** 2, 0) / (testEVs.length - 1));
    const cv = Math.abs(std / mean);
    if (cv < bestCV) { bestCV = cv; bestIdx = vi; }
  }

  return { name: names[bestIdx], index: bestIdx, cv: bestCV };
}

function buildWalkForwardPairs(rangeResults) {
  // Rolling walk-forward: R1→R2, R2→R3, R3→R4, etc.
  const pairs = [], unpaired = [];
  const capNames = ['Sweep Extreme', 'Max MAE', 'P90 MAE', 'P85 MAE', 'P50 MAE'];

  if (rangeResults.length < 2) {
    unpaired.push(...rangeResults);
    return { pairs, unpaired };
  }

  for (let i = 0; i < rangeResults.length - 1; i++) {
    const train = rangeResults[i];
    const test = rangeResults[i + 1];

    const trainParams = computeTrainParams(train.trades);
    if (!trainParams) {
      // Too few winners to derive parameters — skip this pair
      continue;
    }

    const caps = [Infinity, trainParams.mae.max, trainParams.mae.p90, trainParams.mae.p85, trainParams.mae.p50];
    const variants = caps.map((cap, ci) => {
      const trainResolved = resolveWithStopCap(train.trades, cap);
      const testResolved = resolveWithStopCap(test.trades, cap);
      return {
        name: capNames[ci],
        cap,
        train: computeRangeStats(trainResolved),
        test: computeRangeStats(testResolved)
      };
    });

    // Best variant for this pair: highest test EV
    let bestIdx = 0;
    for (let vi = 1; vi < variants.length; vi++) {
      if (variants[vi].test && variants[bestIdx].test &&
          variants[vi].test.ev_r > variants[bestIdx].test.ev_r) bestIdx = vi;
    }

    // MFE target variants — Structural (no TP cap), PTQ Level, P50 MFE, P75 MFE, P90 MFE
    const mfeCapNames = ['1R Baseline', 'PTQ Level', 'P50 MFE', 'P75 MFE', 'P90 MFE'];

    // Compute MFE percentiles from train winners
    function pctlLocal(sorted, q) {
      if (!sorted.length) return null;
      const i = q * (sorted.length - 1);
      const lo = Math.floor(i), hi = Math.ceil(i);
      return lo === hi ? sorted[lo] : sorted[lo] * (hi - i) + sorted[hi] * (i - lo);
    }
    const trainWinners = train.trades.filter(t => t.outcome === 'WIN');
    const trainMfeVals = trainWinners.map(t => t.mfe_pct).filter(v => v != null).sort((a, b) => a - b);
    const mfeP50 = pctlLocal(trainMfeVals, 0.50);
    const mfeP75 = pctlLocal(trainMfeVals, 0.75);
    const mfeP90 = pctlLocal(trainMfeVals, 0.90);
    const mfePtq = trainParams.mfe.ptq;

    const mfeTpLevels = [null, mfePtq, mfeP50, mfeP75, mfeP90];
    const mfeVariants = mfeTpLevels.map((tp, mi) => {
      const trainResolved = tp != null ? resolveWithMFETarget(train.trades, tp) : train.trades.map(t => Object.assign({}, t));
      const testResolved  = tp != null ? resolveWithMFETarget(test.trades, tp)  : test.trades.map(t => Object.assign({}, t));
      return {
        name: mfeCapNames[mi],
        tp,
        train: computeRangeStats(trainResolved),
        test: computeRangeStats(testResolved)
      };
    });

    // Best MFE variant for this pair: highest test EV
    let bestMfeIdx = 0;
    for (let mi = 1; mi < mfeVariants.length; mi++) {
      if (mfeVariants[mi].test && mfeVariants[bestMfeIdx].test &&
          mfeVariants[mi].test.ev_r > mfeVariants[bestMfeIdx].test.ev_r) bestMfeIdx = mi;
    }

    // Extract date ranges from labels
    const trainDates = train.label.split(' to ');
    const testDates = test.label.split(' to ');
    const trainFP = computeRegimeFingerprint(train.trades, trainDates[0], trainDates[1]);
    const testFP = computeRegimeFingerprint(test.trades, testDates[0], testDates[1]);

    const bestVariant = variants[bestIdx];
    const overfit = (bestVariant.train && bestVariant.test)
      ? computeOverfitScore(bestVariant.train.ev_r, bestVariant.test.ev_r)
      : { score: 0, label: 'N/A', cls: 'var(--text-secondary)' };

    pairs.push({
      train, test, trainParams, variants,
      bestVariantIdx: bestIdx,
      mfeVariants, bestMfeVariantIdx: bestMfeIdx,
      trainFingerprint: trainFP, testFingerprint: testFP,
      overfit
    });
  }

  return { pairs, unpaired };
}
function applyCustomRanges(){
  const fullKey = `${activeModel}_${activeMode}_${activeCisd}`;
  const baseD = getProfileData(fullKey, activeProfile);
  if(!baseD || !baseD.recent_trades) return;
  const allTrades = getSmtFilteredTrades(baseD.recent_trades);

  // Raw-measure: no WIN/LOSS → use MAE:MFE regime analysis instead of performance stats.
  if (activeProfile === 'raw_measure') {
    const rangeResults = customRanges.map((r, i) => {
      if (!r.start || !r.end) return null;
      const filtered = allTrades.filter(t => t.date >= r.start && t.date <= r.end);
      return { label: r.start + ' to ' + r.end, color: RANGE_COLORS[i],
               trades: filtered, stats: computeRegimeStats(filtered) };
    }).filter(Boolean);
    renderCustomRangesRegime(rangeResults);
    return;
  }

  const rangeResults = customRanges.map((r, i) => {
    if(!r.start || !r.end) return null;
    const filtered = allTrades.filter(t => t.date >= r.start && t.date <= r.end);
    return { label: r.start + ' to ' + r.end, color: RANGE_COLORS[i], stats: computeRangeStats(filtered), trades: filtered };
  }).filter(Boolean);

  if(rangeResults.length === 0) return;

  // Single range — no walk-forward, just show as unpaired
  if(rangeResults.length === 1){
    const combinedStats = computeRangeStats(rangeResults[0].trades);
    combinedStats._trades = rangeResults[0].trades;
    combinedStats._rangeResults = rangeResults;
    renderCustomViewV2([], rangeResults, combinedStats);
    return;
  }

  // 2+ ranges — build walk-forward pairs
  const { pairs, unpaired } = buildWalkForwardPairs(rangeResults);

  // Combined stats from all TEST trades + unpaired trades
  const combinedTrades = [
    ...pairs.flatMap(p => p.test.trades),
    ...unpaired.flatMap(u => u.trades)
  ];
  const combinedStats = computeRangeStats(combinedTrades);
  if (!combinedStats) { renderCustomViewV2(pairs, unpaired, null); return; }
  combinedStats._trades = combinedTrades;
  combinedStats._rangeResults = rangeResults;
  renderCustomViewV2(pairs, unpaired, combinedStats);
}

function drawGroupedBars(canvas, groups, opts){
  if(!canvas || groups.length === 0) return;
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth, h = canvas.clientHeight;
  canvas.width = w * dpr; canvas.height = h * dpr;
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  const pad = {l:50, r:16, t:16, b:36};
  const plotW = w - pad.l - pad.r, plotH = h - pad.t - pad.b;
  const gridColor = getComputedStyle(document.documentElement).getPropertyValue('--grid-line').trim() || 'rgba(255,255,255,0.04)';
  const mutedColor = getComputedStyle(document.documentElement).getPropertyValue('--text-muted').trim() || '#4a6480';
  // Compute max
  let maxVal = 0;
  groups.forEach(g => g.values.forEach(v => { if(Math.abs(v.value) > maxVal) maxVal = Math.abs(v.value); }));
  maxVal = maxVal * 1.2 || 1;
  const hasNeg = groups.some(g => g.values.some(v => v.value < 0));
  const baseY = hasNeg ? pad.t + plotH * 0.6 : pad.t + plotH;
  const posH = hasNeg ? plotH * 0.6 : plotH;
  const negH = hasNeg ? plotH * 0.4 : 0;
  // Grid
  ctx.strokeStyle = gridColor; ctx.lineWidth = 1;
  ctx.font = '9px IBM Plex Mono'; ctx.fillStyle = mutedColor; ctx.textAlign = 'right';
  for(let i = 0; i <= 4; i++){
    const y = pad.t + (1 - i/4) * posH;
    const val = (maxVal * i / 4);
    ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(w-pad.r, y); ctx.stroke();
    ctx.fillText(opts && opts.formatY ? opts.formatY(val) : val.toFixed(2), pad.l - 4, y + 3);
  }
  if(hasNeg){
    ctx.beginPath(); ctx.moveTo(pad.l, baseY); ctx.lineTo(w-pad.r, baseY); ctx.stroke();
    for(let i = 1; i <= 2; i++){
      const y = baseY + (i/2) * negH;
      const val = -(maxVal * i / 2 * (negH/posH));
      ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(w-pad.r, y); ctx.stroke();
      ctx.fillText(opts && opts.formatY ? opts.formatY(val) : val.toFixed(2), pad.l - 4, y + 3);
    }
  }
  // Bars
  const groupW = plotW / groups.length;
  groups.forEach((g, gi) => {
    const nBars = g.values.length;
    const barW = Math.min((groupW - 10) / nBars, 40);
    const totalW = barW * nBars;
    const startX = pad.l + gi * groupW + (groupW - totalW) / 2;
    g.values.forEach((v, vi) => {
      const x = startX + vi * barW;
      const barH = Math.abs(v.value) / maxVal * posH;
      ctx.fillStyle = v.color;
      ctx.globalAlpha = 0.75;
      if(v.value >= 0){
        ctx.fillRect(x + 1, baseY - barH, barW - 2, barH);
      } else {
        ctx.fillRect(x + 1, baseY, barW - 2, barH * (negH/posH));
      }
      ctx.globalAlpha = 1;
      // Value label
      ctx.fillStyle = v.color;
      ctx.font = '9px IBM Plex Mono'; ctx.textAlign = 'center';
      const valStr = opts && opts.formatVal ? opts.formatVal(v.value) : v.value.toFixed(2);
      if(v.value >= 0){
        ctx.fillText(valStr, x + barW/2, baseY - barH - 3);
      } else {
        ctx.fillText(valStr, x + barW/2, baseY + barH * (negH/posH) + 10);
      }
    });
    // Group label
    ctx.fillStyle = mutedColor;
    ctx.font = '9px IBM Plex Mono'; ctx.textAlign = 'center';
    const label = g.label.length > 12 ? g.label.slice(0,10)+'..' : g.label;
    ctx.fillText(label, pad.l + gi * groupW + groupW/2, h - pad.b + 12);
  });
  // Title
  if(opts && opts.title){
    ctx.fillStyle = mutedColor; ctx.font = 'bold 10px IBM Plex Mono'; ctx.textAlign = 'left';
    ctx.fillText(opts.title, pad.l, pad.t - 4);
  }
}

function drawLineChart(canvas, series, opts){
  if(!canvas || series.length === 0) return;
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth, h = canvas.clientHeight;
  canvas.width = w * dpr; canvas.height = h * dpr;
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  const pad = {l:60, r:16, t:16, b:36};
  const plotW = w - pad.l - pad.r, plotH = h - pad.t - pad.b;
  const gridColor = getComputedStyle(document.documentElement).getPropertyValue('--grid-line').trim() || 'rgba(255,255,255,0.04)';
  const mutedColor = getComputedStyle(document.documentElement).getPropertyValue('--text-muted').trim() || '#4a6480';
  let allX = [], allY = [];
  series.forEach(s => s.points.forEach(p => { allX.push(p.x); allY.push(p.y); }));
  if(allX.length === 0) return;
  const xMin = opts && opts.xMin != null ? opts.xMin : Math.min(...allX);
  const xMax = opts && opts.xMax != null ? opts.xMax : Math.max(...allX);
  const yMin = opts && opts.yMin != null ? opts.yMin : Math.min(...allY);
  const yMax = opts && opts.yMax != null ? opts.yMax : Math.max(...allY);
  const xRange = xMax - xMin || 1;
  const yRange = yMax - yMin || 1;
  function toX(v){ return pad.l + ((v - xMin) / xRange) * plotW; }
  function toY(v){ return pad.t + plotH - ((v - yMin) / yRange) * plotH; }
  // Grid
  ctx.strokeStyle = gridColor; ctx.lineWidth = 1;
  ctx.font = '9px IBM Plex Mono'; ctx.fillStyle = mutedColor;
  for(let i = 0; i <= 4; i++){
    const y = pad.t + (i/4) * plotH;
    const val = yMax - (i/4) * yRange;
    ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(w-pad.r, y); ctx.stroke();
    ctx.textAlign = 'right';
    ctx.fillText(opts && opts.formatY ? opts.formatY(val) : val.toFixed(2), pad.l - 4, y + 3);
  }
  // Lines
  series.forEach(s => {
    ctx.strokeStyle = s.color;
    ctx.lineWidth = 2;
    ctx.globalAlpha = 0.85;
    ctx.beginPath();
    s.points.forEach((p, i) => {
      const x = toX(p.x), y = toY(p.y);
      if(i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    });
    ctx.stroke();
    ctx.globalAlpha = 1;
  });
  // X-axis label
  if(opts && opts.xLabel){
    ctx.fillStyle = mutedColor; ctx.font = '9px IBM Plex Mono'; ctx.textAlign = 'center';
    ctx.fillText(opts.xLabel, pad.l + plotW/2, h - 4);
  }
}

function drawScatterPlot(canvas, datasets, opts){
  if(!canvas || datasets.length === 0) return;
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth, h = canvas.clientHeight;
  canvas.width = w * dpr; canvas.height = h * dpr;
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  const pad = {l:56, r:16, t:16, b:40};
  const plotW = w - pad.l - pad.r, plotH = h - pad.t - pad.b;
  const gridColor = getComputedStyle(document.documentElement).getPropertyValue('--grid-line').trim() || 'rgba(255,255,255,0.04)';
  const mutedColor = getComputedStyle(document.documentElement).getPropertyValue('--text-muted').trim() || '#4a6480';
  let allX = [], allY = [];
  datasets.forEach(d => d.points.forEach(p => { allX.push(p.x); allY.push(p.y); }));
  if(allX.length === 0) return;
  const xMax = Math.max(...allX) * 1.1 || 1;
  const yMax = Math.max(...allY) * 1.1 || 1;
  function toX(v){ return pad.l + (v / xMax) * plotW; }
  function toY(v){ return pad.t + plotH - (v / yMax) * plotH; }
  // Grid
  ctx.strokeStyle = gridColor; ctx.lineWidth = 1;
  ctx.font = '9px IBM Plex Mono'; ctx.fillStyle = mutedColor;
  for(let i = 0; i <= 4; i++){
    const y = pad.t + (i/4) * plotH;
    ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(w-pad.r, y); ctx.stroke();
    ctx.textAlign = 'right';
    ctx.fillText((yMax * (4-i)/4).toFixed(2)+'%', pad.l - 4, y + 3);
    const x = pad.l + (i/4) * plotW;
    ctx.beginPath(); ctx.moveTo(x, pad.t); ctx.lineTo(x, pad.t+plotH); ctx.stroke();
    ctx.textAlign = 'center';
    ctx.fillText((xMax * i/4).toFixed(2)+'%', x, h - pad.b + 14);
  }
  // Points
  datasets.forEach(d => {
    ctx.fillStyle = d.color;
    ctx.globalAlpha = 0.5;
    d.points.forEach(p => {
      ctx.beginPath();
      ctx.arc(toX(p.x), toY(p.y), 3, 0, Math.PI*2);
      ctx.fill();
    });
    ctx.globalAlpha = 1;
  });
  // Axis labels
  ctx.fillStyle = mutedColor; ctx.font = '10px IBM Plex Mono'; ctx.textAlign = 'center';
  ctx.fillText(opts && opts.xLabel || 'MAE%', pad.l + plotW/2, h - 2);
  ctx.save(); ctx.translate(12, pad.t + plotH/2); ctx.rotate(-Math.PI/2);
  ctx.fillText(opts && opts.yLabel || 'MFE%', 0, 0); ctx.restore();
}
function switchCustomTab(tabId){
  document.querySelectorAll('.cv-pane').forEach(p => p.style.display = 'none');
  const pane = document.getElementById(tabId);
  if(pane) pane.style.display = '';
  document.querySelectorAll('.cv-tab').forEach(b => {
    const isActive = b.id === 'cv-tab-' + tabId;
    b.style.borderBottomColor = isActive ? 'var(--green)' : 'transparent';
    b.style.color = isActive ? 'var(--text-primary)' : 'var(--text-muted)';
  });
  // Trigger deferred canvas renders (canvases can't size when hidden)
  if(window._cvDeferredRenders && window._cvDeferredRenders[tabId] && !window._cvRendered?.[tabId]){
    setTimeout(() => {
      window._cvDeferredRenders[tabId]();
      window._cvRendered = window._cvRendered || {};
      window._cvRendered[tabId] = true;
    }, 50);
  }
}

function renderCustomViewV2(pairs, unpairedRanges, combinedStats){
  const cv = document.getElementById('custom-view');
  if(!cv) return;

  const ACCT = 2000, RPT = 200;

  function statColor(val, threshGood, threshBad, invert){
    if(invert) return val <= threshGood ? 'var(--green)' : val >= threshBad ? 'var(--red)' : 'var(--amber)';
    return val >= threshGood ? 'var(--green)' : val <= threshBad ? 'var(--red)' : 'var(--amber)';
  }
  function pct(v){ return (v*100).toFixed(1)+'%'; }
  function fmtPct(v){ return v.toFixed(2)+'%'; }
  function fmtDol(v){ return '$'+Math.round(v).toLocaleString(); }
  function secHeader(title){ return `<div style="font-family:var(--font-data);font-size:10px;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:var(--text-muted);border-bottom:1px solid var(--border);padding-bottom:6px;margin-bottom:16px;margin-top:32px">${title}</div>`; }
  function heroTile(lbl, val, color, sub){
    return `<div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:16px 18px;box-shadow:var(--shadow);position:relative;overflow:hidden">
      <div style="position:absolute;top:0;left:0;width:100%;height:3px;background:${color};border-radius:10px 10px 0 0"></div>
      <div style="font-family:var(--font-data);font-size:11px;font-weight:500;letter-spacing:0.04em;color:var(--text-muted);text-transform:uppercase;margin-bottom:6px">${lbl}</div>
      <div style="font-family:var(--font-display);font-size:28px;font-weight:700;letter-spacing:-0.02em;line-height:1;margin-bottom:4px;color:${color}">${val}</div>
      ${sub ? `<div style="font-family:var(--font-data);font-size:11px;color:var(--text-muted)">${sub}</div>` : ''}
    </div>`;
  }
  function deltaColor(trainVal, testVal){
    if(trainVal === 0) return 'var(--text-muted)';
    const pctChange = Math.abs((testVal - trainVal) / trainVal) * 100;
    return pctChange < 20 ? 'var(--green)' : pctChange < 40 ? 'var(--amber)' : 'var(--red)';
  }
  function deltaStr(trainVal, testVal){
    if(trainVal === 0) return '—';
    const d = ((testVal - trainVal) / trainVal) * 100;
    return (d >= 0 ? '+' : '') + d.toFixed(1) + '%';
  }

  if(!combinedStats && pairs.length === 0 && unpairedRanges.length === 0){
    cv.innerHTML = '<div style="padding:40px 0;text-align:center;font-family:var(--font-data);font-size:12px;color:var(--text-muted)">No trades found in selected ranges. Adjust dates and click Apply.</div>';
    return;
  }

  let html = '';

  // ── Custom View Tab Bar ────────────────────────────────────────────────────
  const cvTabs = [
    {id:'cv-summary', label:'Summary'},
    {id:'cv-walkforward', label:'Walk-Forward'},
    {id:'cv-risk', label:'Risk'},
    {id:'cv-edge', label:'Edge Analysis'},
    {id:'cv-trades', label:'Trades'},
  ];
  html += `<div style="display:flex;gap:2px;margin-bottom:20px;border-bottom:2px solid var(--border);padding-bottom:0">`;
  cvTabs.forEach((tab, i) => {
    const active = i === 0;
    html += `<button onclick="switchCustomTab('${tab.id}')" class="cv-tab" id="cv-tab-${tab.id}" style="font-family:var(--font-data);font-size:11px;font-weight:600;padding:8px 16px;border:none;cursor:pointer;border-bottom:2px solid ${active ? 'var(--green)' : 'transparent'};margin-bottom:-2px;color:${active ? 'var(--text-primary)' : 'var(--text-muted)'};background:transparent;transition:all .15s">${tab.label}</button>`;
  });
  html += `</div>`;

  // ── TAB: SUMMARY ──────────────────────────────────────────────────────────
  html += `<div class="cv-pane" id="cv-summary">`;

  // ── SECTION A: Combined Test Summary (hero tiles) ─────────────────────────
  if(combinedStats){
    const cs = combinedStats;
    const heroLabel = pairs.length > 0 ? 'Out-of-Sample Combined' : 'Combined Stats';
    html += secHeader(heroLabel + ' (' + cs.n + ' trades)');
    // Row 1: WR, EV, PF, CE
    html += `<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:10px">`;
    html += heroTile('Win Rate', pct(cs.wr), statColor(cs.wr, 0.55, 0.45, false), `${cs.nWins}W / ${cs.nLosses}L`);
    html += heroTile('EV (R)', cs.ev_r.toFixed(3), statColor(cs.ev_r, 0.05, -0.05, false), 'per trade');
    html += heroTile('Profit Factor', cs.pf.toFixed(3), statColor(cs.pf, 1.5, 1.0, false), 'gross win / gross loss');
    html += heroTile('CE', cs.ce.toFixed(3), statColor(cs.ce, 0.1, 0, false), 'EV x PF');
    html += `</div>`;
    // Row 2: P&L, Min Equity, Max DD, Sharpe
    html += `<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:10px">`;
    html += heroTile('P&L', fmtDol(cs.totalPnl), statColor(cs.totalPnl, 0, -1, false), '$2,000 account');
    html += heroTile('Min Equity', fmtDol(cs.minEq), statColor(cs.minEq, 1600, 1000, false), cs.blown ? 'ACCOUNT BLOWN' : '');
    html += heroTile('Max DD', cs.maxDDPct.toFixed(2)+'%', statColor(cs.maxDDPct, 10, 25, true), fmtDol(cs.maxDDPct/100*ACCT)+' drawdown');
    html += heroTile('Sharpe', cs.sharpe != null ? cs.sharpe.toFixed(2) : '\u2014', cs.sharpe != null ? statColor(cs.sharpe, 1.5, 0.5, false) : 'var(--text-muted)', 'annualised');
    html += `</div>`;
    // Row 3: Avg Win R, Max W Run, Max L Run, Account badge
    html += `<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:20px">`;
    html += heroTile('Avg Win R', cs.avgWinR.toFixed(3)+'R', statColor(cs.avgWinR, 1.5, 0.5, false), 'mean winner size');
    html += heroTile('Max W Run', cs.mcw, statColor(cs.mcw, 5, 3, false), 'consecutive wins');
    html += heroTile('Max L Run', cs.mcl, statColor(cs.mcl, 5, 10, true), 'consecutive losses');
    const _blownBadge = cs.blown
      ? '<span style="font-family:var(--font-data);font-size:11px;font-weight:700;padding:4px 10px;border-radius:4px;background:rgba(239,68,68,0.15);border:1px solid rgba(239,68,68,0.3);color:var(--red)">BLOWN</span>'
      : '<span style="font-family:var(--font-data);font-size:11px;font-weight:700;padding:4px 10px;border-radius:4px;background:rgba(34,197,94,0.12);border:1px solid rgba(34,197,94,0.25);color:var(--green)">SAFE</span>';
    html += heroTile('Account', _blownBadge, 'var(--text-secondary)', '$2,000 @ $200/trade');
    html += `</div>`;
  }

  // Close Summary pane (unpaired ranges, profile comparison, verdict are added post-render)
  html += `<div id="cv-summary-profile"></div>`;
  html += `<div id="cv-summary-verdict" style="margin-top:8px"></div>`;
  html += `</div>`; // end cv-summary

  // ── TAB: WALK-FORWARD ─────────────────────────────────────────────────────
  html += `<div class="cv-pane" id="cv-walkforward" style="display:none">`;

  // ── SECTION B: Walk-Forward Pairs ─────────────────────────────────────────
  pairs.forEach((pair, pi) => {
    const trainDates = pair.train.label.split(' to ');
    const testDates = pair.test.label.split(' to ');
    const of = pair.overfit;

    // Pair header
    html += `<div style="margin-top:36px;margin-bottom:16px;display:flex;align-items:center;gap:12px;flex-wrap:wrap">`;
    html += `<div style="font-family:var(--font-display);font-size:18px;font-weight:800;color:var(--text-primary);letter-spacing:-0.02em">Pair ${pi+1}: ${trainDates[0]} \u2192 ${testDates[1]}</div>`;
    html += `<div style="font-family:var(--font-data);font-size:11px;color:var(--text-muted)">`;
    html += `<span style="color:${pair.train.color}">Train</span> (${pair.train.trades.length}) \u2192 <span style="color:${pair.test.color}">Test</span> (${pair.test.trades.length})`;
    html += `</div>`;
    html += `<span style="font-family:var(--font-data);font-size:10px;font-weight:700;padding:3px 10px;border-radius:4px;color:${of.cls};background:color-mix(in srgb,${of.cls} 15%,transparent);border:1px solid color-mix(in srgb,${of.cls} 30%,transparent)">${of.label} (${of.score != null ? of.score.toFixed(0) + '%' : '—'})</span>`;
    html += `</div>`;

    // Train Parameters block
    if(pair.trainParams){
      const tp = pair.trainParams;
      const lowSample = tp.nWinners < 20;
      html += `<div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:14px 18px;margin-bottom:12px">`;
      html += `<div style="font-family:var(--font-data);font-size:11px;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:8px">Train Parameters (${tp.nWinners} winners)`;
      if(lowSample) html += ` <span style="color:var(--amber);font-weight:600;text-transform:none;letter-spacing:0"> — low sample warning</span>`;
      html += `</div>`;
      html += `<div style="font-family:var(--font-data);font-size:12px;color:var(--text-primary);line-height:1.8">`;
      html += `<div>MAE: Max=${fmtPct(tp.mae.max)} · P90=${fmtPct(tp.mae.p90)} · P85=${fmtPct(tp.mae.p85)} · P50=${fmtPct(tp.mae.p50)}</div>`;
      html += `<div>MFE: PTQ=${tp.mfe.ptq != null ? fmtPct(tp.mfe.ptq) : '—'} (${tp.mfe.ptqReachRate != null ? tp.mfe.ptqReachRate+'%' : '—'} reach) · P50=${fmtPct(tp.mfe.p50)}</div>`;
      html += `</div></div>`;
    }

    // Regime fingerprint table
    const tfp = pair.trainFingerprint, tfpT = pair.testFingerprint;
    html += `<div style="overflow-x:auto;margin-bottom:12px"><table style="width:100%;border-collapse:collapse;font-family:var(--font-data);font-size:12px;background:var(--bg-card);border:1px solid var(--border);border-radius:10px;overflow:hidden">`;
    html += `<thead><tr style="border-bottom:1px solid var(--border);color:var(--text-muted);font-size:10px;text-transform:uppercase;letter-spacing:0.06em">`;
    html += `<th style="padding:8px 12px;text-align:left">Regime</th><th style="padding:8px 12px;text-align:center;color:${pair.train.color}">Train</th><th style="padding:8px 12px;text-align:center;color:${pair.test.color}">Test</th><th style="padding:8px 12px;text-align:center">\u0394</th>`;
    html += `</tr></thead><tbody>`;
    [
      {label:'Avg Risk (pts)', train: tfp.avgRisk, test: tfpT.avgRisk, fmt: v=>v.toFixed(1)},
      {label:'Long %', train: tfp.longPct, test: tfpT.longPct, fmt: v=>v.toFixed(1)+'%'},
      {label:'MFE/MAE Ratio', train: tfp.mfeMaeRatio, test: tfpT.mfeMaeRatio, fmt: v=>v.toFixed(2)},
      {label:'Trades/Day', train: tfp.density, test: tfpT.density, fmt: v=>v.toFixed(2)},
    ].forEach(row => {
      const dCol = deltaColor(row.train, row.test);
      html += `<tr style="border-bottom:1px solid color-mix(in srgb,var(--border) 50%,transparent)">`;
      html += `<td style="padding:7px 12px;color:var(--text-muted)">${row.label}</td>`;
      html += `<td style="padding:7px 12px;text-align:center;color:var(--text-primary)">${row.fmt(row.train)}</td>`;
      html += `<td style="padding:7px 12px;text-align:center;color:var(--text-primary)">${row.fmt(row.test)}</td>`;
      html += `<td style="padding:7px 12px;text-align:center;font-weight:600;color:${dCol}">${deltaStr(row.train, row.test)}</td>`;
      html += `</tr>`;
    });
    html += `</tbody></table></div>`;

    // Metric row helper for variant cards (shared between MAE and MFE variants)
    const mRow = (label, trainVal, testVal, testColor) => {
        return `<div style="display:flex;align-items:center;padding:5px 14px;border-bottom:1px solid color-mix(in srgb,var(--border) 30%,transparent)">
          <span style="flex:1;font-family:var(--font-data);font-size:11px;color:var(--text-muted)">${label}</span>
          <span style="width:68px;text-align:right;font-family:var(--font-data);font-size:11px;color:var(--text-muted);opacity:0.5">${trainVal}</span>
          <span style="width:68px;text-align:right;font-family:var(--font-data);font-size:12px;font-weight:700;color:${testColor}">${testVal}</span>
        </div>`;
    };

    // Stop variant cards (5 in a row)
    html += `<div style="display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:16px">`;
    pair.variants.forEach((v, vi) => {
      const isBest = vi === pair.bestVariantIdx;
      const tr = v.train, te = v.test;
      if(!tr || !te) return;
      html += `<div style="background:var(--bg-card);border:1px solid ${isBest ? 'var(--green-border)' : 'var(--border)'};border-radius:10px;overflow:hidden;${isBest ? 'box-shadow:0 0 0 1px var(--green-border);' : ''}">`;
      html += `<div style="padding:10px 14px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center">`;
      html += `<div><div style="font-family:var(--font-data);font-size:12px;font-weight:700;color:var(--text-primary)">${v.name}</div>`;
      html += `<div style="font-family:var(--font-data);font-size:10px;color:var(--text-muted)">SL: ${v.cap === Infinity ? 'sweep extreme' : fmtPct(v.cap)}</div></div>`;
      if(isBest) html += `<span style="font-family:var(--font-data);font-size:9px;font-weight:700;padding:2px 8px;border-radius:3px;background:var(--green-tint);border:1px solid var(--green-border);color:var(--green)">BEST</span>`;
      html += `</div>`;
      html += `<div style="display:flex;justify-content:flex-end;padding:6px 14px 2px;gap:8px;border-bottom:1px solid color-mix(in srgb,var(--border) 40%,transparent)">`;
      html += `<span style="width:68px;text-align:right;font-family:var(--font-data);font-size:9px;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.05em;opacity:0.5">Train</span>`;
      html += `<span style="width:68px;text-align:right;font-family:var(--font-data);font-size:9px;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.05em">Test</span>`;
      html += `</div>`;
      html += mRow('Win Rate %', (tr.wr*100).toFixed(1), (te.wr*100).toFixed(1), statColor(te.wr, 0.55, 0.45, false));
      html += mRow('EV $/trade', fmtDol(tr.ev_r*RPT), fmtDol(te.ev_r*RPT), statColor(te.ev_r, 0.05, -0.05, false));
      html += mRow('Sharpe', tr.sharpe != null ? tr.sharpe.toFixed(2) : '\u2014', te.sharpe != null ? te.sharpe.toFixed(2) : '\u2014', te.sharpe != null ? statColor(te.sharpe, 1.5, 0.5, false) : 'var(--text-muted)');
      html += mRow('Profit Factor', tr.pf.toFixed(2), te.pf.toFixed(2), statColor(te.pf, 1.5, 1.0, false));
      html += mRow('Max DD $', '-'+fmtDol(tr.maxDDPct/100*ACCT), '-'+fmtDol(te.maxDDPct/100*ACCT), statColor(te.maxDDPct, 10, 25, true));
      html += mRow('Max Consec L', tr.mcl, te.mcl, statColor(te.mcl, 5, 10, true));
      html += mRow('Total $', fmtDol(tr.totalPnl), fmtDol(te.totalPnl), statColor(te.totalPnl, 0, -1, false));
      html += mRow('Final Bal $', fmtDol(ACCT + tr.totalPnl), fmtDol(ACCT + te.totalPnl), statColor(ACCT + te.totalPnl, ACCT, ACCT*0.5, false));
      html += `</div>`;
    });
    html += `</div>`;

    // MFE Target Variant Cards (5 in a row)
    if (pair.mfeVariants && pair.mfeVariants.length) {
      html += `<div style="font-family:var(--font-data);font-size:10px;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.08em;margin-bottom:8px;margin-top:4px;padding-bottom:4px;border-bottom:1px solid var(--border)">MFE Target Variants — TP Cap Analysis (Train-derived MFE levels)</div>`;
      html += `<div style="display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:16px">`;
      pair.mfeVariants.forEach((v, mi) => {
        const isBestMfe = mi === pair.bestMfeVariantIdx;
        const tr = v.train, te = v.test;
        if (!tr || !te) return;
        const tpLabel = v.tp != null ? fmtPct(v.tp) : '1R baseline';
        html += `<div style="background:var(--bg-card);border:1px solid ${isBestMfe ? 'rgba(16,185,129,0.5)' : 'var(--border)'};border-radius:10px;overflow:hidden;${isBestMfe ? 'box-shadow:0 0 0 1px rgba(16,185,129,0.3);' : ''}">`;
        // Card header
        html += `<div style="padding:10px 14px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;background:${isBestMfe ? 'rgba(16,185,129,0.06)' : 'transparent'}">`;
        html += `<div><div style="font-family:var(--font-data);font-size:12px;font-weight:700;color:var(--text-primary)">${v.name}</div>`;
        html += `<div style="font-family:var(--font-data);font-size:10px;color:var(--text-muted)">TP: ${tpLabel}</div></div>`;
        if (isBestMfe) html += `<span style="font-family:var(--font-data);font-size:9px;font-weight:700;padding:2px 8px;border-radius:3px;background:rgba(16,185,129,0.15);border:1px solid rgba(16,185,129,0.4);color:#10b981">BEST</span>`;
        html += `</div>`;
        // Column headers
        html += `<div style="display:flex;justify-content:flex-end;padding:6px 14px 2px;gap:8px;border-bottom:1px solid color-mix(in srgb,var(--border) 40%,transparent)">`;
        html += `<span style="width:68px;text-align:right;font-family:var(--font-data);font-size:9px;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.05em;opacity:0.5">Train</span>`;
        html += `<span style="width:68px;text-align:right;font-family:var(--font-data);font-size:9px;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.05em">Test</span>`;
        html += `</div>`;
        html += mRow('Win Rate %', (tr.wr*100).toFixed(1), (te.wr*100).toFixed(1), statColor(te.wr, 0.55, 0.45, false));
        html += mRow('EV $/trade', fmtDol(tr.ev_r*RPT), fmtDol(te.ev_r*RPT), statColor(te.ev_r, 0.05, -0.05, false));
        html += mRow('Sharpe', tr.sharpe != null ? tr.sharpe.toFixed(2) : '\u2014', te.sharpe != null ? te.sharpe.toFixed(2) : '\u2014', te.sharpe != null ? statColor(te.sharpe, 1.5, 0.5, false) : 'var(--text-muted)');
        html += mRow('Profit Factor', tr.pf.toFixed(2), te.pf.toFixed(2), statColor(te.pf, 1.5, 1.0, false));
        html += mRow('Max DD $', '-'+fmtDol(tr.maxDDPct/100*ACCT), '-'+fmtDol(te.maxDDPct/100*ACCT), statColor(te.maxDDPct, 10, 25, true));
        html += mRow('Total $', fmtDol(tr.totalPnl), fmtDol(te.totalPnl), statColor(te.totalPnl, 0, -1, false));
        html += mRow('Final Bal $', fmtDol(ACCT + tr.totalPnl), fmtDol(ACCT + te.totalPnl), statColor(ACCT + te.totalPnl, ACCT, ACCT*0.5, false));
        html += `</div>`;
      });
      html += `</div>`;
    }

    // Distribution overlay placeholders (2 canvases per pair)
    html += `<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:24px">`;
    html += `<div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:12px">
      <div style="font-family:var(--font-data);font-size:10px;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:8px">MAE Distribution · Train vs Test</div>
      <canvas id="kde-mae-pair-${pi}" style="width:100%;height:180px"></canvas>
    </div>`;
    html += `<div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:12px">
      <div style="font-family:var(--font-data);font-size:10px;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:8px">MFE Distribution · Train vs Test</div>
      <canvas id="kde-mfe-pair-${pi}" style="width:100%;height:180px"></canvas>
    </div>`;
    html += `</div>`;
  });

  // ── SECTION C: Drift Summary Table ────────────────────────────────────────
  if(pairs.length > 0){
    const bestVar = findBestVariant(pairs);
    html += secHeader('Drift Summary — ' + bestVar.name + ' Stop');

    html += `<div style="overflow-x:auto;margin-bottom:12px"><table style="width:100%;border-collapse:collapse;font-family:var(--font-data);font-size:12px;background:var(--bg-card);border:1px solid var(--border);border-radius:10px;overflow:hidden">`;
    html += `<thead><tr style="border-bottom:1px solid var(--border);color:var(--text-muted);font-size:10px;text-transform:uppercase;letter-spacing:0.06em">`;
    html += `<th style="padding:8px 12px;text-align:left">Metric</th>`;
    pairs.forEach((p, pi) => {
      html += `<th style="padding:8px 8px;text-align:center;color:${p.train.color}">P${pi+1} Train</th>`;
      html += `<th style="padding:8px 8px;text-align:center;color:${p.test.color}">P${pi+1} Test</th>`;
      html += `<th style="padding:8px 8px;text-align:center">\u0394${pi+1}</th>`;
    });
    html += `</tr></thead><tbody>`;

    const vi = bestVar.index;
    [
      {label:'Win Rate %', get: s=>s.wr*100, fmt: v=>v.toFixed(1)+'%'},
      {label:'EV $/trade', get: s=>s.ev_r*RPT, fmt: v=>fmtDol(v)},
      {label:'Profit Factor', get: s=>s.pf, fmt: v=>v.toFixed(2)},
      {label:'Sharpe', get: s=>s.sharpe||0, fmt: v=>v.toFixed(2)},
      {label:'Max DD %', get: s=>s.maxDDPct, fmt: v=>v.toFixed(1)+'%'},
      {label:'Max Consec L', get: s=>s.mcl, fmt: v=>String(v)},
    ].forEach(metric => {
      html += `<tr style="border-bottom:1px solid color-mix(in srgb,var(--border) 50%,transparent)">`;
      html += `<td style="padding:7px 12px;color:var(--text-muted)">${metric.label}</td>`;
      pairs.forEach(p => {
        const trV = metric.get(p.variants[vi].train);
        const teV = metric.get(p.variants[vi].test);
        html += `<td style="padding:7px 8px;text-align:center;color:var(--text-primary)">${metric.fmt(trV)}</td>`;
        html += `<td style="padding:7px 8px;text-align:center;color:var(--text-primary);font-weight:600">${metric.fmt(teV)}</td>`;
        html += `<td style="padding:7px 8px;text-align:center;font-weight:600;color:${deltaColor(trV, teV)}">${deltaStr(trV, teV)}</td>`;
      });
      html += `</tr>`;
    });
    html += `</tbody></table></div>`;

    // Best variant callout
    html += `<div style="background:var(--bg-card);border:1px solid var(--green-border);border-radius:10px;padding:14px 18px;margin-bottom:24px;display:flex;align-items:center;gap:12px">`;
    html += `<span style="font-family:var(--font-data);font-size:12px;color:var(--text-muted)">Most Regime-Stable:</span>`;
    html += `<span style="font-family:var(--font-data);font-size:13px;font-weight:700;color:var(--green)">${bestVar.name} Stop</span>`;
    html += `<span style="font-family:var(--font-data);font-size:11px;color:var(--text-muted)">CV = ${(bestVar.cv*100).toFixed(1)}%</span>`;
    html += `</div>`;
  }

  // ── SECTION D: Unpaired Ranges ────────────────────────────────────────────
  if(unpairedRanges.length > 0){
    html += secHeader('Unpaired Ranges \u2014 no walk-forward analysis');
    const cols = Math.min(unpairedRanges.length, 3);
    html += `<div style="display:grid;grid-template-columns:repeat(${cols},1fr);gap:16px;margin-bottom:20px">`;
    unpairedRanges.forEach(r => {
      const s = r.stats;
      if(!s) return;
      const finalBal = ACCT + s.totalPnl;
      const statusBadge = s.blown
        ? '<span style="font-family:var(--font-data);font-size:9px;font-weight:700;padding:2px 6px;border-radius:3px;background:rgba(239,68,68,0.15);border:1px solid rgba(239,68,68,0.3);color:var(--red)">BLOWN</span>'
        : '<span style="font-family:var(--font-data);font-size:9px;font-weight:700;padding:2px 6px;border-radius:3px;background:rgba(34,197,94,0.12);border:1px solid rgba(34,197,94,0.25);color:var(--green)">SAFE</span>';

      html += `<div style="border-left:3px solid ${r.color};border-radius:10px;background:var(--bg-card);overflow:hidden">`;
      html += `<div style="padding:14px 16px;border-bottom:1px solid var(--border)">
        <div style="font-family:var(--font-data);font-size:13px;font-weight:800;color:${r.color};letter-spacing:-0.01em">${r.label}</div>
        <div style="font-family:var(--font-data);font-size:10px;color:var(--text-muted);margin-top:3px">${s.n} trades · $${RPT}/trade ${statusBadge}</div>
      </div>`;
      const row = (label, val, color) => `<div style="display:flex;justify-content:space-between;align-items:center;padding:8px 16px;border-bottom:1px solid color-mix(in srgb,var(--border) 50%,transparent)">
        <span style="font-family:var(--font-data);font-size:12px;color:var(--text-muted)">${label}</span>
        <span style="font-family:var(--font-data);font-size:13px;font-weight:700;color:${color}">${val}</span>
      </div>`;
      html += row('Win Rate %', (s.wr*100).toFixed(2), statColor(s.wr, 0.55, 0.45, false));
      html += row('EV $/trade', fmtDol(s.ev_r * RPT), statColor(s.ev_r, 0.05, -0.05, false));
      html += row('Profit Factor', s.pf.toFixed(2), statColor(s.pf, 1.5, 1.0, false));
      html += row('Sharpe', s.sharpe != null ? s.sharpe.toFixed(2) : '\u2014', s.sharpe != null ? statColor(s.sharpe, 1.5, 0.5, false) : 'var(--text-muted)');
      html += row('Total $', fmtDol(s.totalPnl), statColor(s.totalPnl, 0, -1, false));
      html += row('Final Bal $', fmtDol(finalBal), statColor(finalBal, ACCT, ACCT*0.5, false));
      html += `</div>`;
    });
    html += `</div>`;
  }

  html += `</div>`; // end cv-walkforward

  // ── TAB: TRADES ───────────────────────────────────────────────────────────
  html += `<div class="cv-pane" id="cv-trades" style="display:none">`;

  // ── SECTION E: Trades Table ───────────────────────────────────────────────
  const allTradesForTable = [
    ...pairs.flatMap(p => p.test.trades),
    ...unpairedRanges.flatMap(u => u.trades)
  ].sort((a,b) => b.date.localeCompare(a.date));

  if(allTradesForTable.length > 0){
    html += secHeader(`Trades (${allTradesForTable.length})`);
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
    allTradesForTable.forEach((t, i) => {
      const bg = i % 2 === 0 ? 'transparent' : 'color-mix(in srgb,var(--bg-raised) 60%,transparent)';
      const isWin = t.outcome === 'WIN';
      const resColor = isWin ? 'var(--green)' : 'var(--red)';
      const dirColor = t.direction === 'LONG' ? 'var(--green)' : 'var(--red)';
      const dirArrow = t.direction === 'LONG' ? '\u25B2' : '\u25BC';
      const dowName = t.dow_name || DOW_NAMES[t.dow] || '?';
      html += `<tr style="background:${bg};border-bottom:1px solid color-mix(in srgb,var(--border-mid) 40%,transparent);">
        <td style="padding:7px 10px;color:var(--text-primary);">${String(t.date).slice(0,10)}</td>
        <td style="padding:7px 6px;color:var(--text-muted);">${dowName}</td>
        <td style="padding:7px 6px;text-align:center;color:var(--text-primary);">${String(t.hr).padStart(2,'0')}:${String(t.mn ?? 0).padStart(2,'0')}</td>
        <td style="padding:7px 6px;color:${dirColor};font-weight:700;">${dirArrow} ${t.direction}</td>
        <td style="padding:7px 6px;text-align:right;color:var(--text-primary);">${t.entry_price != null ? t.entry_price.toFixed(2) : '\u2014'}</td>
        <td style="padding:7px 6px;text-align:right;color:var(--text-primary);">${t.risk_pts != null ? t.risk_pts.toFixed(1) : '\u2014'}</td>
        <td style="padding:7px 6px;text-align:right;color:var(--red);font-size:11px;">${t.mae_pct != null ? t.mae_pct.toFixed(4) + '%' : '\u2014'}</td>
        <td style="padding:7px 6px;text-align:right;color:var(--green);font-size:11px;">${t.mfe_pct != null ? t.mfe_pct.toFixed(4) + '%' : '\u2014'}</td>
        <td style="padding:7px 6px;text-align:right;color:${resColor};font-weight:600;">${t.r != null ? (t.r > 0 ? '+' : '') + t.r.toFixed(2) : '\u2014'}</td>
        <td style="padding:7px 6px;text-align:center;font-weight:700;color:${resColor};">${isWin ? '\u2713 WIN' : '\u2717 LOSS'}</td>
      </tr>`;
    });
    html += '</tbody></table></div>';
  }

  html += `</div>`; // end cv-trades

  // ── TAB: RISK ─────────────────────────────────────────────────────────────
  html += `<div class="cv-pane" id="cv-risk" style="display:none">`;

  // ── SECTION: MONTE CARLO & ROLLING STABILITY ANALYSIS ──────────────────────
  if(combinedStats && combinedStats.n >= 20){
    const allTrades = (combinedStats._trades || []).slice().sort((a,b) => a.date.localeCompare(b.date));
    const rValues = allTrades.map(t => t.r);
    const N_SIM = 1000;
    const ACCT_MC = 4500, RPT_MC = 225;

    // ── Monte Carlo: shuffle R values N_SIM times, build equity curves ──────
    function shuffleArray(arr){
      const a = arr.slice();
      for(let i = a.length - 1; i > 0; i--){
        const j = Math.floor(Math.random() * (i + 1));
        [a[i], a[j]] = [a[j], a[i]];
      }
      return a;
    }

    const mcCurves = [];
    const mcFinals = [];
    const mcMaxDDs = [];
    const mcRuins = [];
    for(let sim = 0; sim < N_SIM; sim++){
      const shuffled = shuffleArray(rValues);
      let eq = ACCT_MC, peak = ACCT_MC, maxDD = 0, ruined = false;
      const curve = [ACCT_MC];
      for(let i = 0; i < shuffled.length; i++){
        eq += shuffled[i] * RPT_MC;
        curve.push(eq);
        if(eq > peak) peak = eq;
        const dd = peak > 0 ? (peak - eq) / peak : 0;
        if(dd > maxDD) maxDD = dd;
        if(eq <= 0) ruined = true;
      }
      mcCurves.push(curve);
      mcFinals.push(eq);
      mcMaxDDs.push(maxDD * 100);
      mcRuins.push(ruined);
    }

    // Compute percentile bands at each trade index
    const nSteps = rValues.length + 1;
    const bands = {p5:[], p25:[], p50:[], p75:[], p95:[]};
    for(let step = 0; step < nSteps; step++){
      const vals = mcCurves.map(c => c[step]).sort((a,b) => a - b);
      bands.p5.push(vals[Math.floor(N_SIM * 0.05)]);
      bands.p25.push(vals[Math.floor(N_SIM * 0.25)]);
      bands.p50.push(vals[Math.floor(N_SIM * 0.50)]);
      bands.p75.push(vals[Math.floor(N_SIM * 0.75)]);
      bands.p95.push(vals[Math.floor(N_SIM * 0.95)]);
    }

    // Actual equity curve
    const actualCurve = [ACCT_MC];
    {let eq = ACCT_MC; rValues.forEach(r => { eq += r * RPT_MC; actualCurve.push(eq); });}

    // Ruin probability
    const ruinPct = (mcRuins.filter(Boolean).length / N_SIM * 100).toFixed(1);

    // Final equity CI
    const sortedFinals = mcFinals.slice().sort((a,b) => a - b);
    const ciLow = sortedFinals[Math.floor(N_SIM * 0.025)];
    const ciHigh = sortedFinals[Math.floor(N_SIM * 0.975)];
    const ciMedian = sortedFinals[Math.floor(N_SIM * 0.50)];

    // Max DD distribution
    const sortedDDs = mcMaxDDs.slice().sort((a,b) => a - b);
    const ddMedian = sortedDDs[Math.floor(N_SIM * 0.50)];
    const ddP90 = sortedDDs[Math.floor(N_SIM * 0.90)];
    const ddP95 = sortedDDs[Math.floor(N_SIM * 0.95)];

    // Bootstrap WR/EV CI (1000 resamples)
    const bsWRs = [], bsEVs = [];
    for(let b = 0; b < N_SIM; b++){
      let wins = 0, sumR = 0;
      for(let i = 0; i < rValues.length; i++){
        const idx = Math.floor(Math.random() * rValues.length);
        if(rValues[idx] > 0) wins++;
        sumR += rValues[idx];
      }
      bsWRs.push(wins / rValues.length);
      bsEVs.push(sumR / rValues.length);
    }
    bsWRs.sort((a,b) => a - b);
    bsEVs.sort((a,b) => a - b);
    const wrCILow = (bsWRs[Math.floor(N_SIM * 0.025)] * 100).toFixed(1);
    const wrCIHigh = (bsWRs[Math.floor(N_SIM * 0.975)] * 100).toFixed(1);
    const evCILow = bsEVs[Math.floor(N_SIM * 0.025)].toFixed(3);
    const evCIHigh = bsEVs[Math.floor(N_SIM * 0.975)].toFixed(3);

    // ── Rolling Stability: rolling window stats ─────────────────────────────
    const ROLL_N = Math.min(50, Math.floor(rValues.length / 3));
    const rollWR = [], rollEV = [], rollPF = [];
    for(let i = ROLL_N; i <= rValues.length; i++){
      const window = rValues.slice(i - ROLL_N, i);
      const ww = window.filter(r => r > 0).length;
      const wSum = window.filter(r => r > 0).reduce((s,v) => s+v, 0);
      const lSum = window.filter(r => r <= 0).reduce((s,v) => s+Math.abs(v), 0);
      rollWR.push(ww / ROLL_N);
      rollEV.push(window.reduce((s,v) => s+v, 0) / ROLL_N);
      rollPF.push(lSum > 0 ? wSum / lSum : wSum > 0 ? 10 : 0);
    }

    // CUSUM: cumulative sum of (r - mean_r)
    const meanR = rValues.reduce((s,v) => s+v, 0) / rValues.length;
    const cusum = [0];
    for(let i = 0; i < rValues.length; i++){
      cusum.push(cusum[i] + (rValues[i] - meanR));
    }

    // ── Helper: draw line chart on canvas ────────────────────────────────────
    function drawLineCanvas(canvasId, datasets, opts = {}){
      setTimeout(() => {
        const canvas = document.getElementById(canvasId);
        if(!canvas) return;
        const ctx = canvas.getContext('2d');
        const W = canvas.width = canvas.parentElement.clientWidth;
        const H = canvas.height = opts.height || 220;
        const pad = {t:20, r:50, b:30, l:60};
        const plotW = W - pad.l - pad.r;
        const plotH = H - pad.t - pad.b;

        // Find global min/max
        let yMin = Infinity, yMax = -Infinity;
        datasets.forEach(ds => {
          ds.data.forEach(v => { if(v < yMin) yMin = v; if(v > yMax) yMax = v; });
        });
        if(opts.yMin != null) yMin = opts.yMin;
        if(opts.yMax != null) yMax = opts.yMax;
        const yRange = yMax - yMin || 1;
        yMin -= yRange * 0.05;
        yMax += yRange * 0.05;
        const yR = yMax - yMin;

        const maxLen = Math.max(...datasets.map(ds => ds.data.length));
        const xScale = plotW / (maxLen - 1 || 1);

        // Background
        ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue('--bg-card').trim() || '#1a1a2e';
        ctx.fillRect(0, 0, W, H);

        // Grid lines
        ctx.strokeStyle = 'rgba(128,128,128,0.15)';
        ctx.lineWidth = 0.5;
        const nGrid = 5;
        for(let i = 0; i <= nGrid; i++){
          const y = pad.t + plotH * (1 - i / nGrid);
          ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(pad.l + plotW, y); ctx.stroke();
          ctx.fillStyle = 'rgba(180,180,180,0.6)';
          ctx.font = '10px monospace';
          ctx.textAlign = 'right';
          const val = yMin + yR * (i / nGrid);
          ctx.fillText(opts.yFmt ? opts.yFmt(val) : val.toFixed(0), pad.l - 4, y + 3);
        }

        // Draw fill bands (if dataset has fill property)
        datasets.filter(ds => ds.fill).forEach(ds => {
          const fillDs = datasets.find(d => d.id === ds.fill);
          if(!fillDs) return;
          ctx.fillStyle = ds.fillColor || 'rgba(100,100,255,0.1)';
          ctx.beginPath();
          for(let i = 0; i < ds.data.length; i++){
            const x = pad.l + i * xScale;
            const y = pad.t + plotH * (1 - (ds.data[i] - yMin) / yR);
            if(i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
          }
          for(let i = fillDs.data.length - 1; i >= 0; i--){
            const x = pad.l + i * xScale;
            const y = pad.t + plotH * (1 - (fillDs.data[i] - yMin) / yR);
            ctx.lineTo(x, y);
          }
          ctx.closePath();
          ctx.fill();
        });

        // Draw lines
        datasets.filter(ds => !ds.fill).forEach(ds => {
          ctx.strokeStyle = ds.color || 'white';
          ctx.lineWidth = ds.width || 1.5;
          ctx.globalAlpha = ds.alpha || 1;
          if(ds.dash) ctx.setLineDash(ds.dash);
          ctx.beginPath();
          ds.data.forEach((v, i) => {
            const x = pad.l + i * xScale;
            const y = pad.t + plotH * (1 - (v - yMin) / yR);
            if(i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
          });
          ctx.stroke();
          ctx.setLineDash([]);
          ctx.globalAlpha = 1;
        });

        // Zero line if applicable
        if(opts.zeroLine && yMin < 0 && yMax > 0){
          const zeroY = pad.t + plotH * (1 - (0 - yMin) / yR);
          ctx.strokeStyle = 'rgba(255,255,255,0.3)';
          ctx.lineWidth = 1;
          ctx.setLineDash([4,4]);
          ctx.beginPath(); ctx.moveTo(pad.l, zeroY); ctx.lineTo(pad.l + plotW, zeroY); ctx.stroke();
          ctx.setLineDash([]);
        }

        // Legend
        if(opts.legend){
          ctx.font = '10px monospace';
          let lx = pad.l + 8;
          opts.legend.forEach(item => {
            ctx.fillStyle = item.color;
            ctx.fillRect(lx, pad.t + 4, 12, 3);
            lx += 16;
            ctx.fillStyle = 'rgba(200,200,200,0.8)';
            ctx.textAlign = 'left';
            ctx.fillText(item.label, lx, pad.t + 10);
            lx += ctx.measureText(item.label).width + 14;
          });
        }

        // Title
        if(opts.title){
          ctx.fillStyle = 'rgba(200,200,200,0.5)';
          ctx.font = '10px monospace';
          ctx.textAlign = 'right';
          ctx.fillText(opts.title, pad.l + plotW, pad.t - 6);
        }
      }, 50);
    }

    // ── Helper: draw histogram on canvas ─────────────────────────────────────
    function drawHistCanvas(canvasId, values, opts = {}){
      setTimeout(() => {
        const canvas = document.getElementById(canvasId);
        if(!canvas) return;
        const ctx = canvas.getContext('2d');
        const W = canvas.width = canvas.parentElement.clientWidth;
        const H = canvas.height = opts.height || 180;
        const pad = {t:20, r:20, b:30, l:50};
        const plotW = W - pad.l - pad.r;
        const plotH = H - pad.t - pad.b;

        const nBins = opts.bins || 30;
        const mn = Math.min(...values);
        const mx = Math.max(...values);
        const binW = (mx - mn) / nBins || 1;
        const bins = new Array(nBins).fill(0);
        values.forEach(v => {
          const idx = Math.min(Math.floor((v - mn) / binW), nBins - 1);
          bins[idx]++;
        });
        const maxBin = Math.max(...bins);

        ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue('--bg-card').trim() || '#1a1a2e';
        ctx.fillRect(0, 0, W, H);

        const barW = plotW / nBins;
        bins.forEach((count, i) => {
          const h = maxBin > 0 ? (count / maxBin) * plotH : 0;
          const x = pad.l + i * barW;
          const y = pad.t + plotH - h;
          ctx.fillStyle = opts.color || 'rgba(239,68,68,0.6)';
          ctx.fillRect(x + 1, y, barW - 2, h);
        });

        // X-axis labels
        ctx.fillStyle = 'rgba(180,180,180,0.6)';
        ctx.font = '10px monospace';
        ctx.textAlign = 'center';
        for(let i = 0; i <= 4; i++){
          const val = mn + (mx - mn) * i / 4;
          const x = pad.l + plotW * i / 4;
          ctx.fillText(opts.xFmt ? opts.xFmt(val) : val.toFixed(1), x, H - 8);
        }

        // Percentile lines
        if(opts.percentiles){
          opts.percentiles.forEach(p => {
            const x = pad.l + ((p.value - mn) / (mx - mn || 1)) * plotW;
            ctx.strokeStyle = p.color || 'white';
            ctx.lineWidth = 1.5;
            ctx.setLineDash(p.dash || []);
            ctx.beginPath(); ctx.moveTo(x, pad.t); ctx.lineTo(x, pad.t + plotH); ctx.stroke();
            ctx.setLineDash([]);
            ctx.fillStyle = p.color || 'white';
            ctx.font = '9px monospace';
            ctx.textAlign = 'center';
            ctx.fillText(p.label, x, pad.t - 4);
          });
        }

        if(opts.title){
          ctx.fillStyle = 'rgba(200,200,200,0.5)';
          ctx.font = '10px monospace';
          ctx.textAlign = 'right';
          ctx.fillText(opts.title, pad.l + plotW, pad.t - 6);
        }
      }, 50);
    }

    html += secHeader('Monte Carlo Simulation (' + N_SIM.toLocaleString() + ' runs, ' + rValues.length + ' trades)');

    // MC Hero tiles
    html += `<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:16px">`;
    html += heroTile('Ruin Probability', ruinPct + '%', parseFloat(ruinPct) <= 1 ? 'var(--green)' : parseFloat(ruinPct) <= 5 ? 'var(--amber)' : 'var(--red)', 'P(account ≤ $0)');
    html += heroTile('Final Equity 95% CI', fmtDol(ciLow) + ' – ' + fmtDol(ciHigh), 'var(--blue, #3b82f6)', 'median ' + fmtDol(ciMedian));
    html += heroTile('Win Rate 95% CI', wrCILow + '% – ' + wrCIHigh + '%', 'var(--blue, #3b82f6)', 'bootstrap');
    html += heroTile('EV 95% CI', evCILow + 'R – ' + evCIHigh + 'R', parseFloat(evCILow) > 0 ? 'var(--green)' : 'var(--red)', 'bootstrap');
    html += `</div>`;

    // MC Max DD tiles
    html += `<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:16px">`;
    html += heroTile('Max DD (Median)', ddMedian.toFixed(1) + '%', statColor(ddMedian, 15, 30, true), 'across ' + N_SIM + ' orderings');
    html += heroTile('Max DD (P90)', ddP90.toFixed(1) + '%', statColor(ddP90, 20, 40, true), '90th percentile');
    html += heroTile('Max DD (P95)', ddP95.toFixed(1) + '%', statColor(ddP95, 25, 50, true), '95th percentile — expect this');
    html += `</div>`;

    // MC Equity Fan Chart
    html += `<div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:12px;margin-bottom:16px;box-shadow:var(--shadow)">
      <div style="font-family:var(--font-data);font-size:11px;font-weight:600;color:var(--text-muted);margin-bottom:8px">EQUITY CURVE — Monte Carlo Confidence Bands</div>
      <canvas id="mc-equity-fan" style="width:100%"></canvas>
    </div>`;

    // MC Max DD Histogram
    html += `<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px">`;
    html += `<div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:12px;box-shadow:var(--shadow)">
      <div style="font-family:var(--font-data);font-size:11px;font-weight:600;color:var(--text-muted);margin-bottom:8px">MAX DRAWDOWN DISTRIBUTION</div>
      <canvas id="mc-dd-hist" style="width:100%"></canvas>
    </div>`;

    // MC Final Equity Histogram
    html += `<div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:12px;box-shadow:var(--shadow)">
      <div style="font-family:var(--font-data);font-size:11px;font-weight:600;color:var(--text-muted);margin-bottom:8px">FINAL EQUITY DISTRIBUTION</div>
      <canvas id="mc-final-hist" style="width:100%"></canvas>
    </div>`;
    html += `</div>`;

    // ── Rolling Stability Section ──────────────────────────────────────────────
    html += secHeader('Rolling Stability (window = ' + ROLL_N + ' trades)');

    // Rolling WR/EV/PF charts
    html += `<div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:12px;margin-bottom:12px;box-shadow:var(--shadow)">
      <div style="font-family:var(--font-data);font-size:11px;font-weight:600;color:var(--text-muted);margin-bottom:8px">ROLLING WIN RATE</div>
      <canvas id="roll-wr" style="width:100%"></canvas>
    </div>`;
    html += `<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px">`;
    html += `<div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:12px;box-shadow:var(--shadow)">
      <div style="font-family:var(--font-data);font-size:11px;font-weight:600;color:var(--text-muted);margin-bottom:8px">ROLLING EV (R)</div>
      <canvas id="roll-ev" style="width:100%"></canvas>
    </div>`;
    html += `<div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:12px;box-shadow:var(--shadow)">
      <div style="font-family:var(--font-data);font-size:11px;font-weight:600;color:var(--text-muted);margin-bottom:8px">ROLLING PROFIT FACTOR</div>
      <canvas id="roll-pf" style="width:100%"></canvas>
    </div>`;
    html += `</div>`;

    // CUSUM chart
    html += `<div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:12px;margin-bottom:16px;box-shadow:var(--shadow)">
      <div style="font-family:var(--font-data);font-size:11px;font-weight:600;color:var(--text-muted);margin-bottom:8px">CUSUM — Cumulative Performance Deviation (upslope = edge active, downslope = edge degrading)</div>
      <canvas id="cusum-chart" style="width:100%"></canvas>
    </div>`;

    // Store render callbacks for after innerHTML is set
    combinedStats._mcRender = function(){
      // Equity fan chart
      drawLineCanvas('mc-equity-fan', [
        {id:'p5',  data: bands.p5,  color:'transparent'},
        {id:'p95', data: bands.p95, color:'transparent'},
        {data: bands.p95, fill:'p5',  fillColor:'rgba(59,130,246,0.08)'},
        {id:'p25', data: bands.p25, color:'transparent'},
        {id:'p75', data: bands.p75, color:'transparent'},
        {data: bands.p75, fill:'p25', fillColor:'rgba(59,130,246,0.15)'},
        {data: bands.p50, color:'rgba(59,130,246,0.5)', width:1, dash:[4,4]},
        {data: actualCurve, color:'#10b981', width:2.5},
      ], {
        height: 260,
        yFmt: v => '$' + Math.round(v).toLocaleString(),
        legend: [
          {color:'#10b981', label:'Actual'},
          {color:'rgba(59,130,246,0.5)', label:'Median'},
          {color:'rgba(59,130,246,0.15)', label:'25–75%'},
          {color:'rgba(59,130,246,0.08)', label:'5–95%'},
        ]
      });

      // DD histogram
      drawHistCanvas('mc-dd-hist', mcMaxDDs, {
        height: 180,
        color: 'rgba(239,68,68,0.5)',
        xFmt: v => v.toFixed(0) + '%',
        percentiles: [
          {value: ddMedian, label: 'p50 ' + ddMedian.toFixed(0) + '%', color: '#f59e0b', dash: [4,4]},
          {value: ddP95, label: 'p95 ' + ddP95.toFixed(0) + '%', color: '#ef4444', dash: [2,2]},
          {value: combinedStats.maxDDPct, label: 'Actual ' + combinedStats.maxDDPct.toFixed(0) + '%', color: '#10b981'},
        ]
      });

      // Final equity histogram
      drawHistCanvas('mc-final-hist', mcFinals, {
        height: 180,
        color: 'rgba(59,130,246,0.5)',
        xFmt: v => '$' + Math.round(v/1000) + 'k',
        percentiles: [
          {value: ciMedian, label: 'Median', color: '#3b82f6', dash: [4,4]},
          {value: actualCurve[actualCurve.length - 1], label: 'Actual', color: '#10b981'},
        ]
      });

      // Rolling WR
      const wrMean = combinedStats.wr;
      drawLineCanvas('roll-wr', [
        {data: rollWR, color:'#3b82f6', width:2},
        {data: new Array(rollWR.length).fill(wrMean), color:'rgba(255,255,255,0.3)', width:1, dash:[4,4]},
      ], {height:180, yFmt: v => (v*100).toFixed(0) + '%', title: 'Mean: ' + (wrMean*100).toFixed(1) + '%'});

      // Rolling EV
      drawLineCanvas('roll-ev', [
        {data: rollEV, color:'#10b981', width:2},
        {data: new Array(rollEV.length).fill(0), color:'rgba(255,255,255,0.3)', width:1, dash:[4,4]},
      ], {height:180, zeroLine:true, yFmt: v => v.toFixed(2) + 'R'});

      // Rolling PF
      drawLineCanvas('roll-pf', [
        {data: rollPF.map(v => Math.min(v, 15)), color:'#f59e0b', width:2},
        {data: new Array(rollPF.length).fill(1), color:'rgba(255,255,255,0.3)', width:1, dash:[4,4]},
      ], {height:180, yFmt: v => v.toFixed(1)});

      // CUSUM
      drawLineCanvas('cusum-chart', [
        {data: cusum, color:'#8b5cf6', width:2.5},
      ], {height:200, zeroLine:true, yFmt: v => v.toFixed(1) + 'R',
        title: 'Slope up = edge active · Slope down = degrading'});
    };
  }

  html += `</div>`; // end cv-risk

  // ── TAB: EDGE ANALYSIS ────────────────────────────────────────────────────
  html += `<div class="cv-pane" id="cv-edge" style="display:none">`;

  // Helper: compute WR and EV for a group of trades (used by multiple sections)
  function grpStats(trades){
    const n = trades.length; if(n === 0) return {n:0, wr:0, ev:0, pf:0};
    const w = trades.filter(t => t.outcome === 'WIN').length;
    const sumW = trades.filter(t => t.r > 0).reduce((s,t) => s+t.r, 0);
    const sumL = trades.filter(t => t.r <= 0).reduce((s,t) => s+Math.abs(t.r), 0);
    return {n, wr: w/n, ev: (sumW - sumL)/n, pf: sumL > 0 ? sumW/sumL : sumW > 0 ? 99 : 0};
  }

  // ── SECTION: FEATURE ATTRIBUTION ───────────────────────────────────────────
  if(combinedStats && combinedStats.n >= 20){
    const allTr = (combinedStats._trades || []);
    const wlTr = allTr.filter(t => t.outcome === 'WIN' || t.outcome === 'LOSS');
    if(wlTr.length >= 20){

      html += secHeader('Feature Attribution (' + wlTr.length + ' trades)');

      // Helper: quartile buckets
      function quartileBuckets(arr){
        const s = arr.slice().sort((a,b) => a - b);
        return [s[Math.floor(s.length*0.25)], s[Math.floor(s.length*0.5)], s[Math.floor(s.length*0.75)]];
      }

      // 1. Feature importance bars — WR by category
      const features = [];
      // By session
      const sessions = {};
      wlTr.forEach(t => { const s = t.session || 'OTHER'; if(!sessions[s]) sessions[s] = []; sessions[s].push(t); });
      Object.entries(sessions).forEach(([k,v]) => { const g = grpStats(v); if(g.n >= 5) features.push({feature:'Session', bucket:k, ...g}); });
      // By direction
      ['LONG','SHORT'].forEach(d => { const g = grpStats(wlTr.filter(t => t.direction === d)); if(g.n >= 5) features.push({feature:'Direction', bucket:d, ...g}); });
      // By DOW
      const dowNames = {0:'Sun',1:'Mon',2:'Tue',3:'Wed',4:'Thu',5:'Fri',6:'Sat'};
      const dows = {};
      wlTr.forEach(t => { const d = t.dow_name || dowNames[t.dow] || '?'; if(!dows[d]) dows[d] = []; dows[d].push(t); });
      Object.entries(dows).forEach(([k,v]) => { const g = grpStats(v); if(g.n >= 5) features.push({feature:'DOW', bucket:k, ...g}); });
      // By SMT
      if(wlTr.some(t => t.smt != null)){
        const smtY = grpStats(wlTr.filter(t => t.smt === true));
        const smtN = grpStats(wlTr.filter(t => !t.smt));
        if(smtY.n >= 3) features.push({feature:'SMT', bucket:'Yes', ...smtY});
        if(smtN.n >= 3) features.push({feature:'SMT', bucket:'No', ...smtN});
      }
      // By sweep_pct quartile
      const spVals = wlTr.map(t => t.sweep_pct).filter(v => v != null);
      if(spVals.length >= 20){
        const sq = quartileBuckets(spVals);
        const spBuckets = [
          {label:'Q1 (small)', filter: t => t.sweep_pct != null && t.sweep_pct <= sq[0]},
          {label:'Q2', filter: t => t.sweep_pct != null && t.sweep_pct > sq[0] && t.sweep_pct <= sq[1]},
          {label:'Q3', filter: t => t.sweep_pct != null && t.sweep_pct > sq[1] && t.sweep_pct <= sq[2]},
          {label:'Q4 (large)', filter: t => t.sweep_pct != null && t.sweep_pct > sq[2]},
        ];
        spBuckets.forEach(b => { const g = grpStats(wlTr.filter(b.filter)); if(g.n >= 3) features.push({feature:'Sweep %', bucket:b.label, ...g}); });
      }
      // By risk_pts quartile
      const rpVals = wlTr.map(t => t.risk_pts).filter(v => v != null);
      if(rpVals.length >= 20){
        const rq = quartileBuckets(rpVals);
        const rpBuckets = [
          {label:'Low ≤'+rq[0].toFixed(0), filter: t => t.risk_pts != null && t.risk_pts <= rq[0]},
          {label:'Med-Lo', filter: t => t.risk_pts != null && t.risk_pts > rq[0] && t.risk_pts <= rq[1]},
          {label:'Med-Hi', filter: t => t.risk_pts != null && t.risk_pts > rq[1] && t.risk_pts <= rq[2]},
          {label:'High >'+rq[2].toFixed(0), filter: t => t.risk_pts != null && t.risk_pts > rq[2]},
        ];
        rpBuckets.forEach(b => { const g = grpStats(wlTr.filter(b.filter)); if(g.n >= 3) features.push({feature:'Risk (pts)', bucket:b.label, ...g}); });
      }

      // Sort by EV descending
      features.sort((a,b) => b.ev - a.ev);
      const baseWR = combinedStats.wr;
      const baseEV = combinedStats.ev_r;

      // Render feature table
      html += `<div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:16px;margin-bottom:16px;box-shadow:var(--shadow);overflow-x:auto">
        <table style="width:100%;border-collapse:collapse;font-family:var(--font-data);font-size:12px">
          <thead><tr style="border-bottom:2px solid var(--border)">
            <th style="padding:8px 10px;text-align:left;color:var(--text-muted)">Feature</th>
            <th style="padding:8px 6px;text-align:left;color:var(--text-muted)">Bucket</th>
            <th style="padding:8px 6px;text-align:right;color:var(--text-muted)">N</th>
            <th style="padding:8px 6px;text-align:right;color:var(--text-muted)">WR</th>
            <th style="padding:8px 6px;text-align:right;color:var(--text-muted)">WR vs Base</th>
            <th style="padding:8px 6px;text-align:right;color:var(--text-muted)">EV (R)</th>
            <th style="padding:8px 6px;text-align:right;color:var(--text-muted)">EV vs Base</th>
            <th style="padding:8px 6px;text-align:right;color:var(--text-muted)">PF</th>
            <th style="padding:8px 6px;text-align:left;color:var(--text-muted)">Edge Bar</th>
          </tr></thead><tbody>`;
      features.forEach((f,i) => {
        const bg = i % 2 === 0 ? 'transparent' : 'color-mix(in srgb,var(--bg-raised) 60%,transparent)';
        const wrDelta = ((f.wr - baseWR) * 100);
        const evDelta = f.ev - baseEV;
        const wrDeltaColor = wrDelta >= 0 ? 'var(--green)' : 'var(--red)';
        const evDeltaColor = evDelta >= 0 ? 'var(--green)' : 'var(--red)';
        const barWidth = Math.min(Math.abs(f.ev / (Math.max(...features.map(x=>Math.abs(x.ev))) || 1)) * 100, 100);
        const barColor = f.ev >= 0 ? 'var(--green)' : 'var(--red)';
        html += `<tr style="background:${bg}">
          <td style="padding:6px 10px;font-weight:600;color:var(--text-primary)">${f.feature}</td>
          <td style="padding:6px;color:var(--text-primary)">${f.bucket}</td>
          <td style="padding:6px;text-align:right;color:var(--text-muted)">${f.n}</td>
          <td style="padding:6px;text-align:right;font-weight:600;color:${f.wr >= baseWR ? 'var(--green)' : 'var(--text-primary)'}">${(f.wr*100).toFixed(1)}%</td>
          <td style="padding:6px;text-align:right;color:${wrDeltaColor}">${wrDelta >= 0 ? '+' : ''}${wrDelta.toFixed(1)}%</td>
          <td style="padding:6px;text-align:right;font-weight:600;color:${f.ev >= baseEV ? 'var(--green)' : 'var(--text-primary)'}">${f.ev.toFixed(3)}</td>
          <td style="padding:6px;text-align:right;color:${evDeltaColor}">${evDelta >= 0 ? '+' : ''}${evDelta.toFixed(3)}</td>
          <td style="padding:6px;text-align:right;color:var(--text-primary)">${f.pf.toFixed(2)}</td>
          <td style="padding:6px"><div style="height:12px;width:${barWidth}%;background:${barColor};border-radius:2px;opacity:0.7"></div></td>
        </tr>`;
      });
      html += `</tbody></table></div>`;

      // 2. Hour x Direction heatmap
      html += `<div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:16px;margin-bottom:16px;box-shadow:var(--shadow)">
        <div style="font-family:var(--font-data);font-size:11px;font-weight:600;color:var(--text-muted);margin-bottom:10px">CONDITIONAL EV HEATMAP — Hour × Direction</div>
        <div style="display:grid;grid-template-columns:60px repeat(10,1fr);gap:2px;font-family:var(--font-data);font-size:11px">`;
      // Header row
      html += `<div style="padding:4px;color:var(--text-muted)"></div>`;
      for(let h = 7; h <= 16; h++) html += `<div style="padding:4px;text-align:center;color:var(--text-muted)">${h}:00</div>`;
      // LONG row
      html += `<div style="padding:4px;color:var(--green);font-weight:600">LONG</div>`;
      for(let h = 7; h <= 16; h++){
        const g = grpStats(wlTr.filter(t => t.hr === h && t.direction === 'LONG'));
        const intensity = g.n >= 3 ? Math.min(Math.abs(g.ev) / 1.5, 1) : 0;
        const bg = g.n < 3 ? 'var(--bg-raised)' : g.ev >= 0 ? `rgba(16,185,129,${0.15 + intensity * 0.5})` : `rgba(239,68,68,${0.15 + intensity * 0.5})`;
        html += `<div style="padding:6px 2px;text-align:center;background:${bg};border-radius:4px;color:var(--text-primary)" title="N=${g.n} WR=${(g.wr*100).toFixed(0)}% EV=${g.ev.toFixed(2)}R">${g.n >= 3 ? g.ev.toFixed(2) : '—'}</div>`;
      }
      // SHORT row
      html += `<div style="padding:4px;color:var(--red);font-weight:600">SHORT</div>`;
      for(let h = 7; h <= 16; h++){
        const g = grpStats(wlTr.filter(t => t.hr === h && t.direction === 'SHORT'));
        const intensity = g.n >= 3 ? Math.min(Math.abs(g.ev) / 1.5, 1) : 0;
        const bg = g.n < 3 ? 'var(--bg-raised)' : g.ev >= 0 ? `rgba(16,185,129,${0.15 + intensity * 0.5})` : `rgba(239,68,68,${0.15 + intensity * 0.5})`;
        html += `<div style="padding:6px 2px;text-align:center;background:${bg};border-radius:4px;color:var(--text-primary)" title="N=${g.n} WR=${(g.wr*100).toFixed(0)}% EV=${g.ev.toFixed(2)}R">${g.n >= 3 ? g.ev.toFixed(2) : '—'}</div>`;
      }
      html += `</div></div>`;
    }
  }

  // ── SECTION: DISTRIBUTION SHIFT TESTS ──────────────────────────────────────
  if(pairs.length > 0){
    // Wasserstein distance (earth mover's distance) approximation
    function wasserstein(a, b){
      if(a.length === 0 || b.length === 0) return 0;
      const sa = a.slice().sort((x,y) => x - y);
      const sb = b.slice().sort((x,y) => x - y);
      const n = Math.max(sa.length, sb.length);
      let sum = 0;
      for(let i = 0; i < n; i++){
        const ai = sa[Math.min(Math.floor(i / n * sa.length), sa.length - 1)];
        const bi = sb[Math.min(Math.floor(i / n * sb.length), sb.length - 1)];
        sum += Math.abs(ai - bi);
      }
      return sum / n;
    }
    // KS statistic
    function ksTest(a, b){
      if(a.length === 0 || b.length === 0) return {stat: 0, significant: false};
      const all = [...a.map(v => ({v, g:0})), ...b.map(v => ({v, g:1}))].sort((x,y) => x.v - y.v);
      let cdfA = 0, cdfB = 0, maxD = 0;
      all.forEach(p => {
        if(p.g === 0) cdfA += 1/a.length; else cdfB += 1/b.length;
        const d = Math.abs(cdfA - cdfB);
        if(d > maxD) maxD = d;
      });
      // Critical value at alpha=0.05
      const crit = 1.36 * Math.sqrt((a.length + b.length) / (a.length * b.length));
      return {stat: maxD, significant: maxD > crit, critical: crit};
    }

    html += secHeader('Distribution Shift Tests (Train vs Test)');

    html += `<div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:16px;margin-bottom:16px;box-shadow:var(--shadow);overflow-x:auto">
      <table style="width:100%;border-collapse:collapse;font-family:var(--font-data);font-size:12px">
        <thead><tr style="border-bottom:2px solid var(--border)">
          <th style="padding:8px 10px;text-align:left;color:var(--text-muted)">Pair</th>
          <th style="padding:8px 6px;text-align:right;color:var(--text-muted)">MAE Wasserstein</th>
          <th style="padding:8px 6px;text-align:center;color:var(--text-muted)">MAE KS Test</th>
          <th style="padding:8px 6px;text-align:right;color:var(--text-muted)">MFE Wasserstein</th>
          <th style="padding:8px 6px;text-align:center;color:var(--text-muted)">MFE KS Test</th>
          <th style="padding:8px 6px;text-align:right;color:var(--text-muted)">R Wasserstein</th>
          <th style="padding:8px 6px;text-align:center;color:var(--text-muted)">R KS Test</th>
          <th style="padding:8px 6px;text-align:center;color:var(--text-muted)">Verdict</th>
        </tr></thead><tbody>`;

    pairs.forEach((pair, pi) => {
      const trMae = pair.train.trades.map(t => t.mae_pct).filter(v => v != null);
      const teMae = pair.test.trades.map(t => t.mae_pct).filter(v => v != null);
      const trMfe = pair.train.trades.map(t => t.mfe_pct).filter(v => v != null);
      const teMfe = pair.test.trades.map(t => t.mfe_pct).filter(v => v != null);
      const trR = pair.train.trades.map(t => t.r);
      const teR = pair.test.trades.map(t => t.r);

      const maeW = wasserstein(trMae, teMae);
      const mfeW = wasserstein(trMfe, teMfe);
      const rW = wasserstein(trR, teR);
      const maeKS = ksTest(trMae, teMae);
      const mfeKS = ksTest(trMfe, teMfe);
      const rKS = ksTest(trR, teR);

      const nSig = [maeKS, mfeKS, rKS].filter(k => k.significant).length;
      const verdict = nSig === 0 ? 'STABLE' : nSig <= 1 ? 'MILD SHIFT' : 'REGIME CHANGE';
      const verdictColor = nSig === 0 ? 'var(--green)' : nSig <= 1 ? 'var(--amber)' : 'var(--red)';

      const bg = pi % 2 === 0 ? 'transparent' : 'color-mix(in srgb,var(--bg-raised) 60%,transparent)';
      html += `<tr style="background:${bg}">
        <td style="padding:6px 10px;font-weight:600;color:var(--text-primary)">P${pi+1}: ${pair.train.label} → ${pair.test.label}</td>
        <td style="padding:6px;text-align:right;color:var(--text-primary)">${maeW.toFixed(4)}</td>
        <td style="padding:6px;text-align:center;font-weight:600;color:${maeKS.significant ? 'var(--red)' : 'var(--green)'}">${maeKS.significant ? 'REJECT' : 'PASS'} <span style="font-weight:400;color:var(--text-muted);font-size:10px">(D=${maeKS.stat.toFixed(3)})</span></td>
        <td style="padding:6px;text-align:right;color:var(--text-primary)">${mfeW.toFixed(4)}</td>
        <td style="padding:6px;text-align:center;font-weight:600;color:${mfeKS.significant ? 'var(--red)' : 'var(--green)'}">${mfeKS.significant ? 'REJECT' : 'PASS'} <span style="font-weight:400;color:var(--text-muted);font-size:10px">(D=${mfeKS.stat.toFixed(3)})</span></td>
        <td style="padding:6px;text-align:right;color:var(--text-primary)">${rW.toFixed(4)}</td>
        <td style="padding:6px;text-align:center;font-weight:600;color:${rKS.significant ? 'var(--red)' : 'var(--green)'}">${rKS.significant ? 'REJECT' : 'PASS'} <span style="font-weight:400;color:var(--text-muted);font-size:10px">(D=${rKS.stat.toFixed(3)})</span></td>
        <td style="padding:6px;text-align:center;font-weight:700;color:${verdictColor}">${verdict}</td>
      </tr>`;
    });
    html += `</tbody></table>
      <div style="font-family:var(--font-data);font-size:10px;color:var(--text-muted);margin-top:8px">Wasserstein = earth mover distance (lower = more similar). KS Test: PASS = same distribution at 95% confidence. REJECT = distributions differ significantly.</div>
    </div>`;
  }

  // ── SECTION: REGIME CLASSIFICATION & TRANSITIONS ───────────────────────────
  if(combinedStats && combinedStats.n >= 30){
    const allTr = (combinedStats._trades || []).slice().sort((a,b) => a.date.localeCompare(b.date));
    if(allTr.length >= 30){
      html += secHeader('Regime Analysis');

      // Classify each trade into a regime based on risk_pts and direction bias
      // Use rolling 20-trade window to determine local regime
      const REG_WIN = Math.min(20, Math.floor(allTr.length / 3));
      const regimeLabels = [];
      const regimeColors = {'Low Vol':'#3b82f6', 'High Vol':'#ef4444', 'Trending':'#10b981', 'Choppy':'#f59e0b'};

      for(let i = REG_WIN; i <= allTr.length; i++){
        const win = allTr.slice(i - REG_WIN, i);
        const avgRisk = win.reduce((s,t) => s + (t.risk_pts || 0), 0) / REG_WIN;
        const longPct = win.filter(t => t.direction === 'LONG').length / REG_WIN;
        const wr = win.filter(t => t.outcome === 'WIN').length / REG_WIN;

        // Classify: median risk as vol proxy, direction bias as trend proxy
        const allRisks = allTr.map(t => t.risk_pts || 0).sort((a,b) => a - b);
        const medRisk = allRisks[Math.floor(allRisks.length / 2)];
        const highVol = avgRisk > medRisk * 1.2;
        const biased = Math.abs(longPct - 0.5) > 0.25;

        let regime;
        if(highVol && biased) regime = 'Trending';
        else if(highVol && !biased) regime = 'High Vol';
        else if(!highVol && biased) regime = 'Trending';
        else regime = longPct > 0.5 ? 'Low Vol' : 'Choppy';

        // Override: low WR in window suggests choppy
        if(wr < 0.6) regime = 'Choppy';
        else if(wr > 0.9 && biased) regime = 'Trending';

        regimeLabels.push(regime);
      }

      // Build regime performance table
      const regimeStats = {};
      for(let i = 0; i < regimeLabels.length; i++){
        const r = regimeLabels[i];
        const t = allTr[i + REG_WIN - 1]; // trade at the end of the window
        if(!regimeStats[r]) regimeStats[r] = [];
        regimeStats[r].push(t);
      }

      html += `<div style="display:grid;grid-template-columns:repeat(${Object.keys(regimeStats).length},1fr);gap:10px;margin-bottom:16px">`;
      Object.entries(regimeStats).forEach(([regime, trades]) => {
        const g = grpStats(trades);
        const col = regimeColors[regime] || 'var(--text-muted)';
        html += `<div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:16px;box-shadow:var(--shadow);position:relative;overflow:hidden">
          <div style="position:absolute;top:0;left:0;width:100%;height:3px;background:${col}"></div>
          <div style="font-family:var(--font-data);font-size:13px;font-weight:700;color:${col};margin-bottom:8px">${regime}</div>
          <div style="font-family:var(--font-display);font-size:24px;font-weight:700;color:var(--text-primary)">${(g.wr*100).toFixed(1)}%</div>
          <div style="font-family:var(--font-data);font-size:11px;color:var(--text-muted);margin-top:4px">${g.n} trades · EV ${g.ev.toFixed(3)}R · PF ${g.pf.toFixed(2)}</div>
        </div>`;
      });
      html += `</div>`;

      // Transition matrix
      if(regimeLabels.length >= 10){
        const regimes = [...new Set(regimeLabels)];
        const trans = {};
        regimes.forEach(r => { trans[r] = {}; regimes.forEach(c => trans[r][c] = 0); });
        for(let i = 1; i < regimeLabels.length; i++){
          trans[regimeLabels[i-1]][regimeLabels[i]]++;
        }
        // Normalize rows to probabilities
        regimes.forEach(r => {
          const rowSum = regimes.reduce((s,c) => s + trans[r][c], 0);
          if(rowSum > 0) regimes.forEach(c => trans[r][c] = trans[r][c] / rowSum);
        });

        html += `<div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:16px;margin-bottom:16px;box-shadow:var(--shadow)">
          <div style="font-family:var(--font-data);font-size:11px;font-weight:600;color:var(--text-muted);margin-bottom:10px">REGIME TRANSITION MATRIX — P(next regime | current regime)</div>
          <div style="display:grid;grid-template-columns:80px repeat(${regimes.length},1fr);gap:2px;font-family:var(--font-data);font-size:11px">`;
        // Header
        html += `<div></div>`;
        regimes.forEach(c => html += `<div style="padding:6px;text-align:center;font-weight:600;color:${regimeColors[c] || 'var(--text-muted)'}">${c}</div>`);
        // Rows
        regimes.forEach(r => {
          html += `<div style="padding:6px;font-weight:600;color:${regimeColors[r] || 'var(--text-muted)'}">${r}</div>`;
          regimes.forEach(c => {
            const p = trans[r][c];
            const intensity = Math.min(p * 1.5, 1);
            const bg = p > 0.5 ? `rgba(59,130,246,${0.1 + intensity * 0.4})` : p > 0.2 ? `rgba(148,163,184,${0.1 + intensity * 0.2})` : 'transparent';
            html += `<div style="padding:6px;text-align:center;background:${bg};border-radius:4px;color:var(--text-primary)">${(p*100).toFixed(0)}%</div>`;
          });
        });
        html += `</div></div>`;
      }

      // Regime timeline canvas
      html += `<div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:12px;margin-bottom:16px;box-shadow:var(--shadow)">
        <div style="font-family:var(--font-data);font-size:11px;font-weight:600;color:var(--text-muted);margin-bottom:8px">REGIME TIMELINE — color = regime, y = trade R outcome</div>
        <canvas id="regime-timeline" style="width:100%"></canvas>
      </div>`;

      // Store regime timeline render
      combinedStats._regimeRender = function(){
        setTimeout(() => {
          const canvas = document.getElementById('regime-timeline');
          if(!canvas) return;
          const ctx = canvas.getContext('2d');
          const W = canvas.width = canvas.parentElement.clientWidth;
          const H = canvas.height = 160;
          const pad = {t:15, r:20, b:20, l:50};
          const plotW = W - pad.l - pad.r;
          const plotH = H - pad.t - pad.b;

          ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue('--bg-card').trim() || '#1a1a2e';
          ctx.fillRect(0, 0, W, H);

          const rVals = [];
          for(let i = 0; i < regimeLabels.length; i++) rVals.push(allTr[i + REG_WIN - 1].r);
          const yMin = Math.min(...rVals) - 0.2;
          const yMax = Math.max(...rVals) + 0.2;
          const yR = yMax - yMin;

          // Zero line
          const zeroY = pad.t + plotH * (1 - (0 - yMin) / yR);
          ctx.strokeStyle = 'rgba(255,255,255,0.2)';
          ctx.lineWidth = 1;
          ctx.setLineDash([4,4]);
          ctx.beginPath(); ctx.moveTo(pad.l, zeroY); ctx.lineTo(pad.l + plotW, zeroY); ctx.stroke();
          ctx.setLineDash([]);

          // Draw bars
          const barW = Math.max(plotW / regimeLabels.length - 1, 2);
          regimeLabels.forEach((regime, i) => {
            const x = pad.l + (i / regimeLabels.length) * plotW;
            const r = rVals[i];
            const y = pad.t + plotH * (1 - (r - yMin) / yR);
            const h = Math.abs(zeroY - y);
            ctx.fillStyle = regimeColors[regime] || '#666';
            ctx.globalAlpha = 0.7;
            ctx.fillRect(x, Math.min(y, zeroY), barW, h || 1);
          });
          ctx.globalAlpha = 1;

          // Y axis labels
          ctx.fillStyle = 'rgba(180,180,180,0.6)';
          ctx.font = '10px monospace';
          ctx.textAlign = 'right';
          for(let i = 0; i <= 4; i++){
            const val = yMin + yR * i / 4;
            const y = pad.t + plotH * (1 - i / 4);
            ctx.fillText(val.toFixed(1) + 'R', pad.l - 4, y + 3);
          }
        }, 80);
      };
    }
  }

  // ── SECTION: STRESS TESTING ────────────────────────────────────────────────
  if(combinedStats && combinedStats.n >= 20){
    const rValues = (combinedStats._trades || []).map(t => t.r);
    if(rValues.length >= 20){
      html += secHeader('Stress Testing');

      const ACCT_ST = 4500, RPT_ST = 225;
      const actualWR = combinedStats.wr;
      const actualEV = combinedStats.ev_r;

      // 1. WR Degradation curves — what if true WR is lower?
      const wrSteps = [];
      for(let wr = actualWR; wr >= Math.max(actualWR - 0.30, 0.40); wr -= 0.05){
        // Simulate: flip some wins to losses to achieve target WR
        const wins = rValues.filter(r => r > 0);
        const losses = rValues.filter(r => r <= 0);
        const targetWins = Math.round(wr * rValues.length);
        const currentWins = wins.length;
        const flips = currentWins - targetWins;

        let simR;
        if(flips <= 0){
          simR = rValues.slice();
        } else {
          // Flip the smallest wins to -1R losses
          const sortedWins = wins.slice().sort((a,b) => a - b);
          const flipped = new Set(sortedWins.slice(0, flips));
          let flipCount = 0;
          simR = rValues.map(r => {
            if(r > 0 && flipCount < flips && flipped.has(r)){
              flipCount++;
              flipped.delete(r);
              return -1.0;
            }
            return r;
          });
        }

        const simEV = simR.reduce((s,v) => s+v, 0) / simR.length;
        const simSumW = simR.filter(r => r > 0).reduce((s,v) => s+v, 0);
        const simSumL = simR.filter(r => r <= 0).reduce((s,v) => s+Math.abs(v), 0);
        const simPF = simSumL > 0 ? simSumW / simSumL : 99;

        // Monte Carlo ruin at this WR (100 sims)
        let ruinCount = 0;
        for(let s = 0; s < 100; s++){
          const shuffled = simR.slice().sort(() => Math.random() - 0.5);
          let eq = ACCT_ST;
          for(let i = 0; i < shuffled.length; i++){
            eq += shuffled[i] * RPT_ST;
            if(eq <= 0){ ruinCount++; break; }
          }
        }

        // Max DD (single pass)
        let eq = ACCT_ST, peak = ACCT_ST, maxDD = 0;
        simR.forEach(r => {
          eq += r * RPT_ST;
          if(eq > peak) peak = eq;
          const dd = peak > 0 ? (peak - eq) / peak : 0;
          if(dd > maxDD) maxDD = dd;
        });

        wrSteps.push({
          wr: wr, ev: simEV, pf: simPF,
          ruinPct: ruinCount,
          maxDD: (maxDD * 100).toFixed(1),
          pnl: simR.reduce((s,v) => s + v * RPT_ST, 0)
        });
      }

      html += `<div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:16px;margin-bottom:16px;box-shadow:var(--shadow)">
        <div style="font-family:var(--font-data);font-size:11px;font-weight:600;color:var(--text-muted);margin-bottom:10px">WIN RATE DEGRADATION — What if your true WR is lower?</div>
        <table style="width:100%;border-collapse:collapse;font-family:var(--font-data);font-size:12px">
          <thead><tr style="border-bottom:2px solid var(--border)">
            <th style="padding:8px 10px;text-align:left;color:var(--text-muted)">Win Rate</th>
            <th style="padding:8px 6px;text-align:right;color:var(--text-muted)">EV (R)</th>
            <th style="padding:8px 6px;text-align:right;color:var(--text-muted)">PF</th>
            <th style="padding:8px 6px;text-align:right;color:var(--text-muted)">Max DD</th>
            <th style="padding:8px 6px;text-align:right;color:var(--text-muted)">Ruin %</th>
            <th style="padding:8px 6px;text-align:right;color:var(--text-muted)">P&L</th>
            <th style="padding:8px 6px;text-align:left;color:var(--text-muted)">Viability</th>
          </tr></thead><tbody>`;

      wrSteps.forEach((s, i) => {
        const isActual = i === 0;
        const bg = isActual ? 'rgba(59,130,246,0.1)' : i % 2 === 0 ? 'transparent' : 'color-mix(in srgb,var(--bg-raised) 60%,transparent)';
        const viable = s.ev > 0 && s.ruinPct <= 5;
        const marginal = s.ev > 0 && s.ruinPct <= 20;
        const badge = viable ? '<span style="color:var(--green);font-weight:700">VIABLE</span>' : marginal ? '<span style="color:var(--amber);font-weight:700">MARGINAL</span>' : '<span style="color:var(--red);font-weight:700">DANGEROUS</span>';
        html += `<tr style="background:${bg}">
          <td style="padding:6px 10px;font-weight:${isActual ? '700' : '400'};color:var(--text-primary)">${(s.wr*100).toFixed(1)}%${isActual ? ' (actual)' : ''}</td>
          <td style="padding:6px;text-align:right;color:${s.ev >= 0 ? 'var(--green)' : 'var(--red)'}">${s.ev.toFixed(3)}</td>
          <td style="padding:6px;text-align:right;color:var(--text-primary)">${s.pf.toFixed(2)}</td>
          <td style="padding:6px;text-align:right;color:var(--text-primary)">${s.maxDD}%</td>
          <td style="padding:6px;text-align:right;color:${s.ruinPct <= 1 ? 'var(--green)' : s.ruinPct <= 5 ? 'var(--amber)' : 'var(--red)'}">${s.ruinPct}%</td>
          <td style="padding:6px;text-align:right;color:${s.pnl >= 0 ? 'var(--green)' : 'var(--red)'}">$${Math.round(s.pnl).toLocaleString()}</td>
          <td style="padding:6px">${badge}</td>
        </tr>`;
      });
      html += `</tbody></table>
        <div style="font-family:var(--font-data);font-size:10px;color:var(--text-muted);margin-top:8px">Simulates progressive WR decline by converting smallest wins to -1R losses. Ruin = P(account ≤ $0) over 100 random orderings.</div>
      </div>`;

      // 2. Adverse streak probability table
      const nTrades = rValues.length;
      const observedWR = actualWR;
      html += `<div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:16px;margin-bottom:16px;box-shadow:var(--shadow)">
        <div style="font-family:var(--font-data);font-size:11px;font-weight:600;color:var(--text-muted);margin-bottom:10px">ADVERSE STREAK PROBABILITY — at WR = ${(observedWR*100).toFixed(1)}%</div>
        <div style="display:grid;grid-template-columns:repeat(6,1fr);gap:8px">`;
      [3,4,5,6,8,10].forEach(streak => {
        const p = Math.pow(1 - observedWR, streak);
        const expectedOccurrences = Math.max(0, (nTrades - streak + 1) * p);
        const acctLoss = streak * RPT_ST;
        const survives = (ACCT_ST - acctLoss) > 0;
        html += `<div style="background:var(--bg-raised);border-radius:8px;padding:12px;text-align:center">
          <div style="font-family:var(--font-display);font-size:22px;font-weight:700;color:${p > 0.05 ? 'var(--red)' : p > 0.001 ? 'var(--amber)' : 'var(--green)'}">${streak}L</div>
          <div style="font-family:var(--font-data);font-size:10px;color:var(--text-muted);margin-top:4px">P = ${(p * 100).toFixed(p < 0.01 ? 3 : 1)}%</div>
          <div style="font-family:var(--font-data);font-size:10px;color:var(--text-muted)">~${expectedOccurrences.toFixed(1)}x in ${nTrades} trades</div>
          <div style="font-family:var(--font-data);font-size:10px;color:${survives ? 'var(--green)' : 'var(--red)'}; margin-top:4px">${survives ? 'Survives' : 'BLOWN'} (−$${acctLoss.toLocaleString()})</div>
        </div>`;
      });
      html += `</div></div>`;
    }
  }

  // ── SECTION: FILTER ANALYSIS (from main profile data) ───────────────────
  // Fetch the full profile data to get filter_impact and filter_variants
  const fullKey = `${activeModel}_${activeMode}_${activeCisd}`;
  const _profileD = getProfileData(fullKey, activeProfile);
  // ── MAE/MFE Percentile Comparison Across Ranges ─────────────────────────────
  if(combinedStats && combinedStats._rangeResults && combinedStats._rangeResults.length > 0){
    const ranges = combinedStats._rangeResults;
    const pctLevels = ['p5','p10','p25','p50','p75','p90','p95'];
    const pctLabels = {p5:'P5',p10:'P10',p25:'P25',p50:'P50 (Median)',p75:'P75',p90:'P90',p95:'P95'};
    const RANGE_COLS = ['#3b82f6','#f59e0b','#8b5cf6','#14b8a6','#ef4444','#6366f1','#ec4899','#84cc16','#f97316','#06b6d4'];

    // higherIsBad: true for MAE (deeper drawdown = worse), false for MFE (higher reach = better)
    function buildPctTable(title, titleColor, field, distField, higherIsBad){
      const showDrift = ranges.length >= 2;

      // Helper: compute drift and stability for a set of values across ranges
      function driftInfo(vals){
        const valid = vals.filter(v => v != null && v > 0);
        if(valid.length < 2) return {delta: null, deltaPct: null, cv: null};
        const first = vals.find(v => v != null && v > 0);
        const last = [...vals].reverse().find(v => v != null && v > 0);
        const delta = last - first;
        const deltaPct = first > 0 ? (delta / first) * 100 : 0;
        const mean = valid.reduce((s,v) => s+v, 0) / valid.length;
        const std = Math.sqrt(valid.reduce((s,v) => s + (v - mean)**2, 0) / valid.length);
        const cv = mean > 0 ? (std / mean) * 100 : 0;
        return {delta, deltaPct: Math.round(deltaPct * 10) / 10, cv: Math.round(cv * 10) / 10};
      }

      function driftColor(deltaPct, higherBad){
        if(deltaPct == null) return 'var(--text-muted)';
        const bad = higherBad ? deltaPct > 0 : deltaPct < 0;
        const mag = Math.abs(deltaPct);
        if(mag < 10) return 'var(--text-muted)';
        return bad ? 'var(--red)' : 'var(--green)';
      }

      function stabilityDot(cv){
        if(cv == null) return '';
        const color = cv < 15 ? '#10b981' : cv < 30 ? '#f59e0b' : '#ef4444';
        const label = cv < 15 ? 'Stable' : cv < 30 ? 'Moderate' : 'Unstable';
        return `<span title="CV=${cv}% — ${label}" style="color:${color}">●</span>`;
      }

      let h = `<div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;overflow:hidden;box-shadow:var(--shadow);margin-bottom:16px">
        <div style="padding:10px 16px;border-bottom:1px solid var(--border);background:var(--bg-raised);display:flex;justify-content:space-between;align-items:center">
          <div>
            <span style="font-family:var(--font-data);font-size:11px;font-weight:700;color:${titleColor}">${title}</span>
            <span style="font-family:var(--font-data);font-size:10px;color:var(--text-muted);margin-left:8px">${higherIsBad ? '(worst drawdown — lower is better)' : '(best excursion — higher is better)'}</span>
          </div>
          ${showDrift ? `<div style="font-family:var(--font-data);font-size:9px;color:var(--text-muted)">
            <span style="color:#10b981">●</span> CV&lt;15% &nbsp;
            <span style="color:#f59e0b">●</span> 15-30% &nbsp;
            <span style="color:#ef4444">●</span> &gt;30%
          </div>` : ''}
        </div>
        <div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-family:var(--font-data);font-size:12px">
          <thead><tr style="border-bottom:2px solid var(--border)">
            <th style="font-size:9px;color:var(--text-muted);text-transform:uppercase;padding:7px 14px;text-align:left;font-weight:400">Percentile</th>`;
      ranges.forEach((r, i) => {
        const col = RANGE_COLS[i % RANGE_COLS.length];
        const shortLabel = r.label.split(' to ')[0];
        h += `<th style="font-size:9px;color:${col};text-transform:uppercase;padding:7px 10px;text-align:right;font-weight:600">${shortLabel}</th>`;
      });
      if(showDrift){
        h += `<th style="font-size:9px;color:var(--text-muted);text-transform:uppercase;padding:7px 10px;text-align:right;font-weight:400">\u0394 Drift</th>`;
        h += `<th style="font-size:9px;color:var(--text-muted);text-transform:uppercase;padding:7px 6px;text-align:center;font-weight:400" title="Coefficient of Variation across ranges">Stab</th>`;
      }
      h += `</tr></thead><tbody>`;

      // Build rows for Mean + percentiles
      const allRows = [
        {key: 'mean', label: 'Mean', isMean: true},
        ...pctLevels.map(pk => ({key: pk, label: pctLabels[pk], isMean: false})),
      ];

      allRows.forEach(row => {
        const isP50 = row.key === 'p50';
        const bold = isP50 ? 'font-weight:700;' : '';
        const rowBg = isP50 ? 'background:color-mix(in srgb,var(--bg-raised) 60%,transparent)' : '';

        // Collect values across ranges
        const rowVals = ranges.map(r => {
          if(row.isMean) return r.stats?.[distField]?.mean;
          return r.stats?.[field]?.[row.key];
        });

        const drift = showDrift ? driftInfo(rowVals) : null;

        h += `<tr style="border-bottom:1px solid color-mix(in srgb,var(--border) 30%,transparent);${rowBg}">
          <td style="padding:5px 14px;color:${isP50 ? titleColor : row.isMean ? 'var(--text-muted)' : 'var(--text-primary)'};font-size:11px;${bold}">${row.label}</td>`;

        ranges.forEach(r => {
          const v = row.isMean ? r.stats?.[distField]?.mean : r.stats?.[field]?.[row.key];
          h += `<td style="padding:5px 10px;text-align:right;color:var(--text-primary);${bold}">${v != null ? (+v).toFixed(4) + '%' : '—'}</td>`;
        });

        if(showDrift && drift){
          const dColor = driftColor(drift.deltaPct, higherIsBad);
          const arrow = drift.deltaPct > 0 ? '▲' : drift.deltaPct < 0 ? '▼' : '';
          h += `<td style="padding:5px 10px;text-align:right;color:${dColor};font-size:11px;${bold}">${drift.deltaPct != null ? arrow + ' ' + (drift.deltaPct >= 0 ? '+' : '') + drift.deltaPct + '%' : '—'}</td>`;
          h += `<td style="padding:5px 6px;text-align:center;font-size:14px">${stabilityDot(drift.cv)}</td>`;
        }

        h += `</tr>`;
      });

      h += `</tbody></table></div></div>`;
      return h;
    }

    html += secHeader('MAE / MFE Percentile Comparison Across Ranges');
    html += buildPctTable('MAE Distribution', 'var(--red)', 'maePercentiles', 'maeDist', true);
    html += buildPctTable('MFE Distribution', 'var(--green)', 'mfePercentiles', 'mfeDist', false);
  }

  html += `</div>`; // end cv-edge

  cv.innerHTML = html;

  // Render profile comparison and verdict into Summary tab
  if(_profileD){
    const tradeDateSet = (combinedStats && combinedStats._trades && combinedStats._trades.length > 0)
      ? new Set(combinedStats._trades.map(t => t.date)) : null;

    const compPanel = document.getElementById('cv-summary-profile');
    if(compPanel){
      if(tradeDateSet) renderProfileComparison(compPanel, null, tradeDateSet);
      else renderProfileComparison(compPanel, customRanges.filter(r => r.start && r.end));
    }
    const verdictPanel = document.getElementById('cv-summary-verdict');
    if(verdictPanel){
      renderVerdict(verdictPanel, {tradeDateSet, walkForwardPairs: pairs});
    }
  }

  // Defer canvas rendering until their tabs are visible.
  // Canvases can't measure size when parent is display:none.
  const _deferredRenders = {
    'cv-risk': () => {
      if(combinedStats && combinedStats._mcRender) combinedStats._mcRender();
    },
    'cv-edge': () => {
      if(combinedStats && combinedStats._regimeRender) combinedStats._regimeRender();
    },
    'cv-walkforward': () => {
      // KDE overlays for walk-forward pairs
      _renderKDE();
    },
  };
  // Store on window so switchCustomTab can trigger them
  window._cvDeferredRenders = _deferredRenders;
  window._cvRendered = {};

  function _renderKDE(){
  // ── DRAW KDE OVERLAYS ─────────────────────────────────────────────────────
  pairs.forEach((pair, pi) => {
    ['mae','mfe'].forEach(type => {
      const canvas = document.getElementById(`kde-${type}-pair-${pi}`);
      if(!canvas) return;

      // Get train density from precomputed params
      const trainDensity = type === 'mae' ? pair.trainParams.maeDensity : pair.trainParams.mfeDensity;
      // Compute test density
      const testVals = pair.test.trades.map(t => t[type+'_pct']).filter(v => v != null && v > 0);
      const testDensity = computeKDE(testVals);

      if(trainDensity.length === 0 && testDensity.length === 0) return;

      const dpr = window.devicePixelRatio || 1;
      const w = canvas.clientWidth, h = canvas.clientHeight;
      canvas.width = w * dpr; canvas.height = h * dpr;
      const ctx = canvas.getContext('2d');
      ctx.scale(dpr, dpr);

      const pad = {l:50, r:16, t:10, b:40};
      const plotW = w - pad.l - pad.r, plotH = h - pad.t - pad.b;
      const gridColor = getComputedStyle(document.documentElement).getPropertyValue('--grid-line').trim() || 'rgba(255,255,255,0.04)';
      const mutedColor = getComputedStyle(document.documentElement).getPropertyValue('--text-muted').trim() || '#4a6480';

      // Find global bounds
      const allPts = [...trainDensity, ...testDensity];
      let xMin = Infinity, xMax = -Infinity, yMax = 0;
      allPts.forEach(p => { if(p.x < xMin) xMin = p.x; if(p.x > xMax) xMax = p.x; if(p.y > yMax) yMax = p.y; });
      xMin = Math.max(0, xMin);
      const xRange = xMax - xMin || 1;
      yMax = yMax * 1.15 || 1;

      function toX(v){ return pad.l + ((v - xMin) / xRange) * plotW; }
      function toY(v){ return pad.t + plotH - (v / yMax) * plotH; }

      // Grid lines
      ctx.strokeStyle = gridColor; ctx.lineWidth = 1;
      ctx.font = '9px IBM Plex Mono'; ctx.fillStyle = mutedColor;
      for(let i = 0; i <= 3; i++){
        const y = pad.t + (i/3) * plotH;
        ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(w-pad.r, y); ctx.stroke();
        ctx.textAlign = 'right';
        ctx.fillText((yMax * (3-i)/3).toFixed(3), pad.l - 4, y + 3);
      }
      // X-axis labels
      ctx.textAlign = 'center';
      for(let i = 0; i <= 4; i++){
        const xVal = xMin + (i/4) * xRange;
        ctx.fillText(xVal.toFixed(3)+'%', toX(xVal), h - pad.b + 14);
      }

      // Draw train curve (dashed, 40% opacity)
      if(trainDensity.length > 0){
        ctx.save();
        ctx.setLineDash([5, 4]);
        ctx.strokeStyle = pair.train.color;
        ctx.lineWidth = 2;
        ctx.globalAlpha = 0.4;
        ctx.beginPath();
        trainDensity.forEach((p, i) => {
          const x = toX(p.x), y = toY(p.y);
          if(i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        });
        ctx.stroke();
        ctx.restore();
      }

      // Draw test curve (solid, full opacity with fill)
      if(testDensity.length > 0){
        ctx.save();
        ctx.strokeStyle = pair.test.color;
        ctx.lineWidth = 2;
        ctx.globalAlpha = 1;
        ctx.beginPath();
        testDensity.forEach((p, i) => {
          const x = toX(p.x), y = toY(p.y);
          if(i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        });
        ctx.stroke();

        // Fill under test curve
        ctx.globalAlpha = 0.08;
        ctx.fillStyle = pair.test.color;
        ctx.beginPath();
        testDensity.forEach((p, i) => {
          const x = toX(p.x), y = toY(p.y);
          if(i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        });
        ctx.lineTo(toX(testDensity[testDensity.length-1].x), pad.t + plotH);
        ctx.lineTo(toX(testDensity[0].x), pad.t + plotH);
        ctx.closePath();
        ctx.fill();
        ctx.restore();
      }

      // Legend
      const legendY = h - 6;
      ctx.font = '9px IBM Plex Mono';
      ctx.textAlign = 'left';
      // Train legend
      ctx.save();
      ctx.setLineDash([5, 4]);
      ctx.strokeStyle = pair.train.color;
      ctx.lineWidth = 2;
      ctx.globalAlpha = 0.5;
      ctx.beginPath(); ctx.moveTo(pad.l, legendY); ctx.lineTo(pad.l+20, legendY); ctx.stroke();
      ctx.restore();
      ctx.fillStyle = mutedColor;
      ctx.fillText('Train', pad.l+24, legendY+3);
      // Test legend
      ctx.strokeStyle = pair.test.color;
      ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(pad.l+60, legendY); ctx.lineTo(pad.l+80, legendY); ctx.stroke();
      ctx.fillText('Test', pad.l+84, legendY+3);
    });
  });
  } // end _renderKDE
}

export { addCustomRange };
export { applyCustomRanges };
export { buildWalkForwardPairs };
export { computeKDE };
export { computeOverfitScore };
export { computeRangeStats };
export { computeRegimeFingerprint };
export { computeRegimeStats };
export { computeTrainParams };
export { drawGroupedBars };
export { drawLineChart };
export { drawScatterPlot };
export { findBestVariant };
export { getSmtFilteredTrades };
export { _restoreFilters, _saveFilters };
export { removeRange };
export { renderCustomRangesRegime };
export { renderCustomViewV2 };
export { renderRangeSlots };
export { resolveWithMFETarget };
export { resolveWithStopCap };
export { saveAndRenderRanges };
export { switchCustomTab };
export { switchF3 };
export { switchF4 };
export { switchSMT };
export { switchP42 };
export { switchPD };
export { updateRange };
