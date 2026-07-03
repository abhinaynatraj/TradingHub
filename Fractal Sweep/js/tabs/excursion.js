import { _excSegment, SVG_FONT, isDark, activeProfile, activeTF, activeSmt, activeF3, activeF4 } from '../state.js';
import { C, _heatColor, _drawMAEProbCurve, _drawMFEProbCurve, _drawExcursionHeatmap } from '../charts.js';
import { pct, evFmt, evCls, pfFmt } from '../utils.js';
import { getFilteredD, getActiveTrades } from '../data.js';
import { getSmtFilteredTrades, computeRangeStats, computeTrainParams, resolveWithStopCap, resolveWithMFETarget } from '../walkforward.js';

function computeRichStudy(trades, field) {
  // Include all trades with a numeric value (zeros are meaningful — trade never went adverse/favourable).
  // Every trade has an MAE and MFE, so counts must match Overview/Trades.
  const vals = trades.map(t => t[field]).filter(v => v != null && isFinite(v) && v >= 0);
  const n = vals.length;
  if (n < 3) return null;

  const sorted = vals.slice().sort((a,b) => a-b);

  // Basic stats
  const mean = sorted.reduce((s,v) => s+v, 0) / n;
  const median = n % 2 === 0 ? (sorted[n/2-1] + sorted[n/2]) / 2 : sorted[Math.floor(n/2)];
  const variance = sorted.reduce((s,v) => s + (v-mean)**2, 0) / (n-1);
  const std = Math.sqrt(variance);

  // Mode via binning
  const binSize = std > 0 ? std / 5 : 0.01;
  const bins = {};
  sorted.forEach(v => { const b = Math.round(v / binSize) * binSize; bins[b] = (bins[b]||0)+1; });
  let mode = 0, modeCount = 0;
  Object.entries(bins).forEach(([b,c]) => { if(c > modeCount){ modeCount=c; mode=+b; }});

  // Skewness and kurtosis
  const m3 = std > 0 ? sorted.reduce((s,v) => s + ((v-mean)/std)**3, 0) / n : 0;
  const m4 = std > 0 ? sorted.reduce((s,v) => s + ((v-mean)/std)**4, 0) / n : 3;
  const skewness = Math.round(m3 * 10) / 10;
  const kurtosis = Math.round((m4 - 3) * 10) / 10;

  // Percentiles
  function pct(p) {
    const idx = (p/100) * (n-1);
    const lo = Math.floor(idx), hi = Math.ceil(idx);
    return lo === hi ? sorted[lo] : sorted[lo] + (sorted[hi]-sorted[lo]) * (idx-lo);
  }
  const percentiles = {};
  [5,10,15,20,25,30,35,40,50,60,65,70,75,80,85,90,95,99].forEach(p => {
    percentiles['p'+p] = Math.round(pct(p) * 10000) / 10000;
  });

  // Lognormal fit
  const logVals = sorted.filter(v => v > 0).map(v => Math.log(v));
  const logMu = logVals.reduce((s,v) => s+v, 0) / logVals.length;
  const logSigma = Math.sqrt(logVals.reduce((s,v) => s + (v-logMu)**2, 0) / (logVals.length-1));
  // Goodness of fit: correlation between sorted log values and theoretical normal quantiles
  let goodness = 0.99;
  if (logVals.length >= 5) {
    const nL = logVals.length;
    const sortedLog = logVals.slice().sort((a,b) => a-b);
    // Theoretical quantiles (inverse normal approximation via Beasley-Springer-Moro)
    const normInv = p => {
      // Rational approx for inverse normal CDF (Abramowitz & Stegun)
      if (p <= 0 || p >= 1) return 0;
      const t = p < 0.5 ? Math.sqrt(-2 * Math.log(p)) : Math.sqrt(-2 * Math.log(1-p));
      const c0=2.515517, c1=0.802853, c2=0.010328, d1=1.432788, d2=0.189269, d3=0.001308;
      const r = t - (c0 + c1*t + c2*t*t) / (1 + d1*t + d2*t*t + d3*t*t*t);
      return p < 0.5 ? -r : r;
    };
    const theoQ = [];
    for (let i = 0; i < nL; i++) theoQ.push(normInv((i + 0.5) / nL));
    // Pearson correlation between sortedLog and theoQ
    const mX = sortedLog.reduce((s,v)=>s+v,0)/nL;
    const mY = theoQ.reduce((s,v)=>s+v,0)/nL;
    let sXY=0, sXX=0, sYY=0;
    for (let i = 0; i < nL; i++) {
      sXY += (sortedLog[i]-mX)*(theoQ[i]-mY);
      sXX += (sortedLog[i]-mX)**2;
      sYY += (theoQ[i]-mY)**2;
    }
    goodness = sXX > 0 && sYY > 0 ? Math.abs(sXY / Math.sqrt(sXX*sYY)) : 0;
  }
  const lognorm = {
    mu: Math.round(logMu * 10000) / 10000,
    sigma: Math.round(logSigma * 10000) / 10000,
    implied_median: Math.round(Math.exp(logMu) * 10000) / 10000,
    implied_mean: Math.round(Math.exp(logMu + logSigma**2/2) * 10000) / 10000,
    implied_mode: Math.round(Math.exp(logMu - logSigma**2) * 10000) / 10000,
    goodness: Math.round(goodness * 10000) / 10000
  };

  // Clusters (3-tier: 0->p33, p33->p75, p75+)
  const p33 = pct(33), p75 = pct(75);
  const tier1 = sorted.filter(v => v <= p33);
  const tier2 = sorted.filter(v => v > p33 && v <= p75);
  const tier3 = sorted.filter(v => v > p75);
  const isMAE = field === 'mae_pct';
  const clusterData = [
    {label: isMAE ? 'Tight' : 'Small', range: '0 \u2013 ' + p33.toFixed(4) + '%',
     n: tier1.length, pct_of_trades: Math.round(tier1.length/n*100),
     mean: tier1.length ? Math.round(tier1.reduce((s,v)=>s+v,0)/tier1.length*10000)/10000 : 0,
     median: tier1.length ? tier1[Math.floor(tier1.length/2)] : 0,
     max: tier1.length ? tier1[tier1.length-1] : 0},
    {label: 'Moderate', range: p33.toFixed(4) + '% \u2013 ' + p75.toFixed(4) + '%',
     n: tier2.length, pct_of_trades: Math.round(tier2.length/n*100),
     mean: tier2.length ? Math.round(tier2.reduce((s,v)=>s+v,0)/tier2.length*10000)/10000 : 0,
     median: tier2.length ? tier2[Math.floor(tier2.length/2)] : 0,
     max: tier2.length ? tier2[tier2.length-1] : 0},
    {label: isMAE ? 'Wide' : 'Large', range: p75.toFixed(4) + '%+',
     n: tier3.length, pct_of_trades: Math.round(tier3.length/n*100),
     mean: tier3.length ? Math.round(tier3.reduce((s,v)=>s+v,0)/tier3.length*10000)/10000 : 0,
     median: tier3.length ? tier3[Math.floor(tier3.length/2)] : 0,
     max: tier3.length ? tier3[tier3.length-1] : 0}
  ];

  // Histogram (50 bins from 0 to p99)
  const maxVal = pct(99);
  const nBins = 50;
  const binW = maxVal / nBins;
  const histCounts = new Array(nBins).fill(0);
  const histEdges = [];
  for (let i = 0; i <= nBins; i++) histEdges.push(Math.round(i * binW * 10000) / 10000);
  sorted.forEach(v => {
    if (v > maxVal) { histCounts[nBins-1]++; return; }
    const bi = Math.min(nBins-1, Math.floor(v / binW));
    histCounts[bi]++;
  });

  // SL Sweep (MAE) or BE Triggers (MFE)
  let sl_sweep = null, opt_sl = null, be_triggers = null, ptq_level = null, ptq_reach_rate = null;
  const totalTrades = trades.length;

  // Baseline WR across the full slice — used as lift benchmark
  const baselineWins = trades.filter(t => t.outcome === 'WIN').length;
  const baselineWL   = trades.filter(t => t.outcome === 'WIN' || t.outcome === 'LOSS').length;
  const baselineWR   = baselineWL > 0 ? baselineWins / baselineWL : 0;

  if (isMAE) {
    sl_sweep = [];
    let opt_p_ko = null;
    [5,10,15,20,25,30,33,40,50,60,75,90].forEach(exceedPct => {
      const thr = pct(exceedPct);
      const touched = trades.filter(t => t[field] != null && t[field] >= thr);
      const nt = touched.length;
      if (nt === 0) return;
      const nWin = touched.filter(t => t.outcome === 'WIN').length;
      const nLoss = touched.filter(t => t.outcome === 'LOSS').length;
      const wlTouched = nWin + nLoss;
      const pRec = wlTouched > 0 ? Math.round(nWin / wlTouched * 10000) / 10000 : 0;
      const pKo  = wlTouched > 0 ? Math.round(nLoss / wlTouched * 10000) / 10000 : 0;
      sl_sweep.push({exceed_pct: exceedPct, threshold: Math.round(thr*10000)/10000,
                     n_exceeded: nt, p_recovered: pRec, p_ko: pKo, ev_cost: 0});
      // Optimal SL: TIGHTEST threshold (smallest MAE) where reaching it almost always
      // means the trade is already lost. Criteria: P(LOSS|touched) >= 70%, and enough
      // sample size (touch rate >= 10% of trades).
      // Iteration goes tight → loose, so first match = tightest level. Don't overwrite.
      const touchFrac = nt / totalTrades;
      if (opt_sl === null && pKo >= 0.70 && touchFrac >= 0.10 && wlTouched >= 20) {
        opt_sl = Math.round(thr*10000)/10000;
        opt_p_ko = pKo;
      }
    });
    // Stash the KO probability at opt_sl so the callout can report it
    if (opt_sl !== null) sl_sweep._opt_p_ko = opt_p_ko;
  } else {
    be_triggers = [];
    const rVals = trades.map(t => t.r).filter(v => v != null);
    const baseEV = rVals.length > 0 ? rVals.reduce((s,v) => s+v, 0) / rVals.length : 0;
    let ptq_p_pos = null;

    // Iterate TIGHT → LOOSE: reach_rate small = threshold large (stringent).
    // Reverse: reach_rate large = threshold small (trivial level).
    // We want the SMALLEST threshold where reaching it provides MEANINGFUL lift
    // over baseline WR. So iterate LOOSE → TIGHT and pick first level clearing the bar.
    const reachRates = [90,75,60,50,40,33,30,25,20,15,10,5];
    const liftTarget = Math.min(0.95, baselineWR + 0.10); // at least +10pp lift, capped at 95%
    const minSampleFrac = 0.25;  // PTQ level must be reachable by >= 25% of trades

    reachRates.forEach(reachRate => {
      const thr = pct(100 - reachRate);
      const reached = trades.filter(t => t[field] != null && t[field] >= thr);
      const nr = reached.length;
      if (nr === 0) return;
      const nPos = reached.filter(t => t.outcome === 'WIN').length;
      const nLossReached = reached.filter(t => t.outcome === 'LOSS').length;
      const wlReached = nPos + nLossReached;
      const pPos = wlReached > 0 ? Math.round(nPos / wlReached * 10000) / 10000 : 0;
      const rescuedLossR = reached.filter(t => t.outcome === 'LOSS').map(t => t.r).filter(v => v != null);
      const savedR = rescuedLossR.length > 0 ? rescuedLossR.reduce((s,v) => s + Math.abs(v), 0) : 0;
      const evDelta = totalTrades > 0 ? Math.round(savedR / totalTrades * 10000) / 10000 : 0;
      const newEV = Math.round((baseEV + evDelta) * 10000) / 10000;
      be_triggers.push({reach_rate: reachRate, trigger_pct: Math.round(thr*10000)/10000,
                        n_reached: nr, p_pos_given: pPos, n_rescued: nLossReached,
                        ev_delta: evDelta, new_ev: newEV});
      // PTQ: tightest (smallest) threshold where P(WIN|reached) >= baselineWR + 0.10
      //      AND reach rate >= 25% of all trades (enough to matter)
      //      AND >= 20 resolved trades in the conditional group (statistical validity)
      if (ptq_level === null
          && pPos >= liftTarget
          && (nr / totalTrades) >= minSampleFrac
          && wlReached >= 20) {
        ptq_level = Math.round(thr*10000)/10000;
        ptq_reach_rate = reachRate;
        ptq_p_pos = pPos;
      }
    });
    if (ptq_level !== null) be_triggers._ptq_p_pos = ptq_p_pos;
    be_triggers._baselineWR = Math.round(baselineWR * 10000) / 10000;
  }

  // CE score: concentration efficiency (median/mean ratio)
  const ce = mean > 0 ? Math.round(median / mean * 100) / 100 : null;

  // Bell curve stats
  const bell = {
    mean: Math.round(mean*10000)/10000, std: Math.round(std*10000)/10000,
    plus_0_5s: Math.round((mean + 0.5*std)*10000)/10000,
    plus_1s: Math.round((mean + std)*10000)/10000,
    plus_1_5s: Math.round((mean + 1.5*std)*10000)/10000,
    plus_2s: Math.round((mean + 2*std)*10000)/10000,
  };

  return {
    n, mean: Math.round(mean*10000)/10000, median: Math.round(median*10000)/10000,
    mode: Math.round(mode*10000)/10000, std: Math.round(std*10000)/10000,
    skewness, kurtosis, ce,
    percentiles, lognorm, clusters: clusterData,
    histogram: { edges: histEdges, counts: histCounts },
    ...(isMAE
      ? { sl_sweep, opt_sl, opt_p_ko: sl_sweep?._opt_p_ko ?? null }
      : { be_triggers, ptq_level, ptq_reach_rate,
          ptq_p_pos: be_triggers?._ptq_p_pos ?? null,
          baseline_wr: be_triggers?._baselineWR ?? null }),
    bell
  };
}

function renderMAEStudy(D) {
  const el = document.getElementById('mae-study-panel');
  if (!el) return;

  // Compute MAE stats client-side from recent_trades so data matches selected Period/TF/Profile
  const isRaw = activeProfile === 'raw_measure';
  const allTrades = getSmtFilteredTrades(getActiveTrades(D));
  const winTrades = isRaw ? [] : allTrades.filter(t => t.outcome === 'WIN');
  const lossTrades = isRaw ? [] : allTrades.filter(t => t.outcome === 'LOSS');
  const maeAll = computeRichStudy(allTrades, 'mae_pct');
  const maeWins = isRaw ? null : computeRichStudy(winTrades, 'mae_pct');
  const maeLosses = isRaw ? null : computeRichStudy(lossTrades, 'mae_pct');

  const _activeSeg = isRaw ? 'all' : _excSegment;
  // Mirror active state onto shared pill bar (if present)
  document.querySelectorAll('#exc-seg-bar .seg-btn').forEach(b => {
    const active = b.dataset.seg === _activeSeg;
    b.classList.toggle('active', active);
  });
  const dist = _activeSeg === 'wins' ? maeWins
             : _activeSeg === 'losses' ? maeLosses
             : maeAll;
  const _segCount = _activeSeg === 'wins' ? winTrades.length : _activeSeg === 'losses' ? lossTrades.length : allTrades.length;
  const ce   = dist?.ce ?? D?.risk_stats?.ce;
  if (!dist) {
    const _segName = _activeSeg === 'wins' ? 'winning' : _activeSeg === 'losses' ? 'losing' : '';
    el.innerHTML = `<div style="padding:24px;font-family:var(--font-data);font-size:12px;color:var(--text-muted)">Not enough ${_segName} trades for MAE study (${_segCount} trades, need at least 3 with MAE &gt; 0).</div>`;
    return;
  }

  // Segment-specific accent and callout
  const segAccent = _activeSeg === 'wins' ? 'green' : _activeSeg === 'losses' ? 'red' : 'blue';
  const segColor  = _activeSeg === 'wins' ? 'var(--green)' : _activeSeg === 'losses' ? 'var(--red)' : 'var(--blue)';
  const segBg     = _activeSeg === 'wins' ? 'var(--green-tint)' : _activeSeg === 'losses' ? 'var(--red-tint)' : 'rgba(59,130,246,.08)';
  const segBorder = _activeSeg === 'wins' ? 'var(--green-border)' : _activeSeg === 'losses' ? 'var(--red-border)' : 'rgba(59,130,246,.2)';
  const fmtPctCb  = v => v != null ? (+v).toFixed(4) + '%' : '--';
  const segTitle  = _activeSeg === 'wins' ? 'Optimal Stop Placement' : _activeSeg === 'losses' ? 'Stop Validation' : isRaw ? 'Raw MAE Distribution (all setups)' : 'Combined MAE Distribution';
  const segDetail = _activeSeg === 'wins'
    ? `90% of winners stay within ${fmtPctCb((dist.percentiles||{}).p90)} MAE · Median dip: ${fmtPctCb(dist.median)}${dist.opt_sl != null ? ' · Optimal SL: ' + fmtPctCb(dist.opt_sl) : ''}`
    : _activeSeg === 'losses'
    ? `Losers MAE median: ${fmtPctCb(dist.median)} confirms SL placement · Mean: ${fmtPctCb(dist.mean)} · ${dist.n||0} losing trades`
    : `${dist.n||0} trades · Median MAE: ${fmtPctCb(dist.median)} · Mean: ${fmtPctCb(dist.mean)}`;
  const segLabel  = _activeSeg === 'wins' ? 'Winners' : _activeSeg === 'losses' ? 'Losers' : 'All Trades';
  const p   = dist.percentiles || {};
  const ln  = dist.lognorm || {};
  const clus = dist.clusters || [];
  const sweep = dist.sl_sweep || [];
  const hist  = dist.histogram || {};
  const optSl = dist.opt_sl;
  const clusterColors = ['#60a5fa','#fbbf24','#f87171'];
  const fmt    = (v, d=4) => v != null ? (+v).toFixed(d) : '—';
  const fmtPct = v => v != null ? (+v).toFixed(4) + '%' : '—';

  // Compact 4-tile summary
  const statTiles = [
    { lbl:'Median (p50)', v:fmtPct(dist.median), c:'#fb923c' },
    { lbl:'p75',          v:fmtPct(p.p75),       c:'#10b981' },
    { lbl:'p90',          v:fmtPct(p.p90),       c:'#a78bfa' },
    { lbl:'p95',          v:fmtPct(p.p95),       c:'#c084fc' },
  ];

  const pctRows = [
    {lbl:'p5',  v:p.p5,        color:'#94a3b8'},
    {lbl:'p10', v:p.p10,       color:'#94a3b8'},
    {lbl:'p15', v:p.p15,       color:'#64748b'},
    {lbl:'p20', v:p.p20,       color:'#64748b'},
    {lbl:'p25', v:p.p25,       color:'#60a5fa'},
    {lbl:'p30', v:p.p30,       color:'#60a5fa'},
    {lbl:'p35', v:p.p35,       color:'#60a5fa'},
    {lbl:'p40', v:p.p40,       color:'#fb923c'},
    {lbl:'p50', v:dist.median, color:'#fb923c', bold:true, desc:'median trade'},
    {lbl:'p60', v:p.p60,       color:'#fb923c'},
    {lbl:'p65', v:p.p65,       color:'#fbbf24'},
    {lbl:'p70', v:p.p70,       color:'#fbbf24'},
    {lbl:'p75', v:p.p75,       color:'#10b981',            desc:'75% of trades dip less'},
    {lbl:'p80', v:p.p80,       color:'#10b981'},
    {lbl:'p85', v:p.p85,       color:'#10b981'},
    {lbl:'p90', v:p.p90,       color:'#a78bfa',            desc:'candidate SL \u2192 90% stay tighter'},
    {lbl:'p95', v:p.p95,       color:'#c084fc'},
    {lbl:'p99', v:p.p99,       color:'#f87171',            desc:'tail risk'},
  ];

  el.innerHTML = `
  <div style="background:${segBg};border:1px solid ${segBorder};border-radius:8px;padding:12px 14px;margin-bottom:12px;">
    <div style="font-family:var(--font-data);font-size:12px;font-weight:700;color:${segColor}">How much heat does a typical trade take?</div>
    <div style="font-family:var(--font-data);font-size:11px;color:var(--text-secondary);margin-top:4px;line-height:1.5">
      ${(dist.n||0).toLocaleString()} trades \u00b7 median dip = <strong style="color:var(--text-primary)">${fmtPct(dist.median)}</strong>.
      Zero rows at low percentiles indicate trades that never moved against the entry.
      For practical SL placement see the <em>Stop Variant Analysis</em> panel below.
    </div>
  </div>
  <div class="panel" style="margin-bottom:12px">
    <div class="ph"><span class="ph-title">MAE Distribution</span><span class="ph-note">\u03c3=${fmt(dist.std,3)}% \u00b7 skew=${fmt(dist.skewness,1)} \u00b7 right-tailed</span></div>
    <div class="pb">
      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:14px">
        ${statTiles.map(s=>`
        <div style="background:var(--bg-raised);border:1px solid var(--border-mid);border-radius:6px;padding:10px 8px;text-align:center">
          <div style="font-family:var(--font-data);font-size:9px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.04em;margin-bottom:3px">${s.lbl}</div>
          <div style="font-family:var(--font-display);font-size:15px;font-weight:700;color:${s.c};line-height:1.1">${s.v}</div>
        </div>`).join('')}
      </div>
      <div style="font-family:var(--font-data);font-size:10px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.05em;margin-bottom:6px">Frequency (0 \u2192 p99)</div>
      <canvas id="mae-study-hist" height="130" style="width:100%;display:block;border-radius:6px;background:var(--bg-raised)"></canvas>
      <table style="width:100%;border-collapse:collapse;margin-top:12px">
        <thead><tr style="border-bottom:1px solid var(--border)">
          <th style="font-family:var(--font-data);font-size:9px;color:var(--text-muted);text-transform:uppercase;padding:5px 8px;text-align:left;font-weight:400">Pct</th>
          <th style="font-family:var(--font-data);font-size:9px;color:var(--text-muted);text-transform:uppercase;padding:5px 8px;text-align:right;font-weight:400">MAE %</th>
          <th style="font-family:var(--font-data);font-size:9px;color:var(--text-muted);text-transform:uppercase;padding:5px 8px;text-align:left;font-weight:400">Reading</th>
        </tr></thead>
        <tbody>
          ${pctRows.map(r=>`<tr style="border-bottom:1px solid var(--border)">
            <td style="font-family:var(--font-data);font-size:11px;color:${r.color};padding:5px 8px;font-weight:${r.bold?700:500}">${r.lbl}</td>
            <td style="font-family:var(--font-data);font-size:11px;color:var(--text-primary);padding:5px 8px;text-align:right;font-weight:600">${r.v!=null?(+r.v).toFixed(4)+'%':'\u2014'}</td>
            <td style="font-family:var(--font-data);font-size:10px;color:var(--text-muted);padding:5px 8px">${r.desc || (r.v === 0 ? 'never moved' : '')}</td>
          </tr>`).join('')}
        </tbody>
      </table>
      <div style="margin-top:14px;padding:12px 14px;background:var(--bg-raised);border:1px solid var(--border);border-radius:8px;font-family:var(--font-data);font-size:11px;color:var(--text-secondary);line-height:1.6">
        <strong style="color:var(--text-primary)">Looking for the best stop?</strong> The table above describes <em>what happened</em> \u2014
        it doesn't prescribe an SL. See the <strong style="color:var(--red)">Stop Variant Analysis</strong> panel below \u2014 it
        simulates every candidate SL level on the actual trade set and reports resulting Win Rate, EV, PF and drawdown.
        That's the empirical answer; picking a percentile here would be circular.
      </div>
    </div>
  </div>`;

  // Draw histogram
  const canvas = document.getElementById('mae-study-hist');
  if (!canvas || !hist.edges || !hist.counts) return;
  const W = canvas.offsetWidth || 600, H = 140;
  canvas.width = W * devicePixelRatio; canvas.height = H * devicePixelRatio;
  const ctx = canvas.getContext('2d'); ctx.scale(devicePixelRatio, devicePixelRatio);
  const padL=36,padR=12,padT=14,padB=28, cW=W-padL-padR, cH=H-padT-padB;
  const counts=hist.counts, edges=hist.edges, maxC=Math.max(...counts,1), nBins=counts.length, xMax=edges[edges.length-1];
  const cc=C(); ctx.fillStyle=cc.bgCard; ctx.fillRect(0,0,W,H);
  ctx.strokeStyle=cc.gridLine; ctx.lineWidth=1;
  [.25,.5,.75,1].forEach(f=>{const y=padT+cH*(1-f);ctx.beginPath();ctx.moveTo(padL,y);ctx.lineTo(padL+cW,y);ctx.stroke();});
  const bW=cW/nBins;
  counts.forEach((c,i)=>{
    const barH=(c/maxC)*cH, x=padL+i*bW, y=padT+cH-barH, t=i/nBins;
    const r=Math.round(96+(248-96)*t), g=Math.round(165+(113-165)*t), b=Math.round(250+(113-250)*t);
    ctx.fillStyle=`rgba(${r},${g},${b},.75)`; ctx.fillRect(x+1,y,Math.max(bW-2,1),barH);
  });
  if(dist.median!=null){const mx=padL+(dist.median/xMax)*cW;ctx.strokeStyle='rgba(251,146,60,.8)';ctx.lineWidth=1.5;ctx.setLineDash([3,3]);ctx.beginPath();ctx.moveTo(mx,padT);ctx.lineTo(mx,padT+cH);ctx.stroke();ctx.setLineDash([]);ctx.fillStyle='#fb923c';ctx.font='10px IBM Plex Mono,monospace';ctx.fillText('Med',mx+3,padT+cH-4);}
  ctx.fillStyle='#64748b';ctx.font='9px IBM Plex Mono,monospace';ctx.textAlign='center';
  [0,.25,.5,.75,1].forEach(f=>{const xVal=edges[0]+f*(xMax-edges[0]);ctx.fillText(xVal.toFixed(2)+'%',padL+f*cW,padT+cH+16);});
  ctx.textAlign='right';ctx.fillText(maxC,padL-4,padT+4);ctx.fillText('0',padL-4,padT+cH+4);

  // ── Stop Variant Cards ────────────────────────────────────────────────────
  // Show how performance changes under 5 MAE-based stop caps applied to all trades.
  (function renderMAEStopVariants() {
    const trades = allTrades;
    if (trades.length < 5) return;

    const ACCT_SV = 4500, RPT_SV = 225;
    const params = computeTrainParams(trades);
    if (!params) return;

    const capNames = ['No Cap', 'Max (winners)', 'P90 (winners)', 'P85 (winners)', 'P50 (winners)'];
    const caps = [Infinity, params.mae.max, params.mae.p90, params.mae.p85, params.mae.p50];

    // Count original winners once — used to compute "Winners Killed" row per cap.
    const origWinners = trades.filter(t => t.outcome === 'WIN').length;

    const variants = caps.map((cap, ci) => {
      const resolved = resolveWithStopCap(trades, cap);
      const stats = computeRangeStats(resolved);
      // Winners killed = trades that were WIN but now LOSS under this cap
      let killed = 0;
      if (isFinite(cap)) {
        trades.forEach(t => {
          if (t.outcome === 'WIN' && t.mae_pct != null && t.mae_pct > cap) killed++;
        });
      }
      return { name: capNames[ci], cap, stats, killed };
    });

    // Best = highest EV
    let bestIdx = 0;
    for (let i = 1; i < variants.length; i++) {
      if (variants[i].stats && variants[bestIdx].stats &&
          variants[i].stats.ev_r > variants[bestIdx].stats.ev_r) bestIdx = i;
    }

    const fmtPctSV = v => v != null && isFinite(v) ? (+v).toFixed(4) + '%' : '—';
    const fmtDolSV = v => '$' + Math.round(v).toLocaleString();
    function scSV(val, threshGood, threshBad, invert) {
      if (invert) return val <= threshGood ? 'var(--green)' : val >= threshBad ? 'var(--red)' : 'var(--amber)';
      return val >= threshGood ? 'var(--green)' : val <= threshBad ? 'var(--red)' : 'var(--amber)';
    }

    // Compact table layout — rows = metrics, cols = variants.
    // "Winners Killed" appears first so you see immediately which caps actually bite.
    const metrics = [
      { lbl:'Winners Killed', fmt:(s,v)=>{
          const pct = origWinners>0 ? (v.killed/origWinners*100).toFixed(1)+'%' : '0%';
          return v.killed>0 ? `${v.killed} (${pct})` : '0';
        }, score:(s,v)=> v.killed===0 ? 'var(--text-muted)' : v.killed < origWinners*0.05 ? 'var(--amber)' : 'var(--red)' },
      { lbl:'Win %',    fmt:s=>(s.wr*100).toFixed(1)+'%',                    score:s=>scSV(s.wr, 0.55, 0.45, false) },
      { lbl:'EV $',     fmt:s=>fmtDolSV(s.ev_r * RPT_SV),                    score:s=>scSV(s.ev_r, 0.05, -0.05, false) },
      { lbl:'Sharpe',   fmt:s=>s.sharpe!=null?s.sharpe.toFixed(2):'—',       score:s=>s.sharpe!=null?scSV(s.sharpe, 1.5, 0.5, false):'var(--text-muted)' },
      { lbl:'PF',       fmt:s=>s.pf.toFixed(2),                              score:s=>scSV(s.pf, 1.5, 1.0, false) },
      { lbl:'Max DD',   fmt:s=>'-'+fmtDolSV(s.maxDDPct/100*ACCT_SV),         score:s=>scSV(s.maxDDPct, 10, 25, true) },
      { lbl:'Total $',  fmt:s=>fmtDolSV(s.totalPnl),                          score:s=>scSV(s.totalPnl, 0, -1, false) },
    ];

    let html = `<div class="panel" style="margin-bottom:14px">
      <div class="ph"><span class="ph-title">Stop Variant Analysis</span><span class="ph-note">SL caps derived from <em>winners'</em> MAE distribution \u00b7 \u2605 = highest EV</span></div>
      <div class="pb" style="padding:0">
        <table style="width:100%;border-collapse:collapse;font-family:var(--font-data);font-size:11px">
          <thead>
            <tr style="border-bottom:1px solid var(--border);background:var(--bg-raised)">
              <th style="padding:7px 8px;text-align:left;font-weight:400;font-size:9px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.04em">Metric</th>
              ${variants.map((v,vi)=>{
                const isBest = vi===bestIdx;
                const capLabel = v.cap===Infinity?'\u221E':fmtPctSV(v.cap);
                return `<th style="padding:7px 6px;text-align:right;font-weight:700;font-size:10px;color:${isBest?'var(--green)':'var(--text-secondary)'};${isBest?'background:var(--green-tint);':''}">
                  <div>${v.name}${isBest?' \u2605':''}</div>
                  <div style="font-weight:400;font-size:9px;color:var(--text-muted);margin-top:1px">${capLabel}</div>
                </th>`;
              }).join('')}
            </tr>
          </thead>
          <tbody>
            ${metrics.map(m=>`
            <tr style="border-bottom:1px solid var(--border)">
              <td style="padding:6px 8px;color:var(--text-muted)">${m.lbl}</td>
              ${variants.map((v,vi)=>{
                if(!v.stats) return `<td style="padding:6px 6px;text-align:right;color:var(--text-muted)">—</td>`;
                const isBest = vi===bestIdx;
                const val   = m.fmt(v.stats, v);
                const color = m.score(v.stats, v);
                return `<td style="padding:6px 6px;text-align:right;color:${color};font-weight:600;${isBest?'background:color-mix(in srgb,var(--green-tint) 40%,transparent);':''}">${val}</td>`;
              }).join('')}
            </tr>`).join('')}
          </tbody>
        </table>
        <div style="padding:10px 14px;border-top:1px solid var(--border);font-family:var(--font-data);font-size:10px;color:var(--text-muted);line-height:1.6">
          <strong style="color:var(--text-primary)">How to read:</strong> caps above use MAE percentiles <em>from winners only</em>.
          A cap of "P90 (winners)" converts any trade with MAE above that level into a forced LOSS.
          If <strong>Winners Killed = 0</strong>, that cap has no effect (values identical to <em>No Cap</em>).
          Compare <strong>EV $</strong> across columns \u2014 that's the column that matters for SL selection.
        </div>
      </div>
    </div>`;
    el.insertAdjacentHTML('beforeend', html);
  })();
}

function renderMFEStudy(D) {
  const el = document.getElementById('mfe-study-panel');
  if (!el) return;

  // Compute MFE stats client-side from recent_trades so data matches selected Period/TF/Profile
  const isRaw = activeProfile === 'raw_measure';
  const allTrades = getSmtFilteredTrades(getActiveTrades(D));
  const winTrades = isRaw ? [] : allTrades.filter(t => t.outcome === 'WIN');
  const lossTrades = isRaw ? [] : allTrades.filter(t => t.outcome === 'LOSS');
  const mfeAll = computeRichStudy(allTrades, 'mfe_pct');
  const mfeWins = isRaw ? null : computeRichStudy(winTrades, 'mfe_pct');
  const mfeLosses = isRaw ? null : computeRichStudy(lossTrades, 'mfe_pct');

  const _activeSeg = isRaw ? 'all' : _excSegment;
  const dist = _activeSeg === 'wins' ? mfeWins
             : _activeSeg === 'losses' ? mfeLosses
             : mfeAll;
  const _segCount = _activeSeg === 'wins' ? winTrades.length : _activeSeg === 'losses' ? lossTrades.length : allTrades.length;
  if (!dist) {
    const _segName = _activeSeg === 'wins' ? 'winning' : _activeSeg === 'losses' ? 'losing' : '';
    el.innerHTML = `<div style="padding:24px;font-family:var(--font-data);font-size:12px;color:var(--text-muted)">Not enough ${_segName} trades for MFE study (${_segCount} trades, need at least 3 with MFE &gt; 0).</div>`;
    return;
  }

  // Segment-specific accent and callout
  const segAccent = _activeSeg === 'wins' ? 'green' : _activeSeg === 'losses' ? 'amber' : 'blue';
  const segColor  = _activeSeg === 'wins' ? 'var(--green)' : _activeSeg === 'losses' ? 'var(--amber)' : 'var(--blue)';
  const segBg     = _activeSeg === 'wins' ? 'var(--green-tint)' : _activeSeg === 'losses' ? 'var(--amber-tint)' : 'rgba(59,130,246,.08)';
  const segBorder = _activeSeg === 'wins' ? 'var(--green-border)' : _activeSeg === 'losses' ? 'rgba(245,158,11,.25)' : 'rgba(59,130,246,.2)';
  const fmtPctCb  = v => v != null ? (+v).toFixed(4) + '%' : '--';
  const segTitle  = _activeSeg === 'wins' ? 'Optimal Take Profit' : _activeSeg === 'losses' ? 'Rescue Opportunity' : isRaw ? 'Raw MFE Distribution (all setups)' : 'Combined MFE Distribution';
  const segDetail = _activeSeg === 'wins'
    ? `Median winner runs ${fmtPctCb(dist.median)}${dist.ptq_level != null ? ' · PTQ at ' + fmtPctCb(dist.ptq_level) : ''}${dist.ptq_reach_rate != null ? ' · ' + dist.ptq_reach_rate + '% reach rate' : ''}`
    : _activeSeg === 'losses'
    ? `50% of losers reached ${fmtPctCb(dist.median)} favorable before reversing · ${dist.n||0} losing trades`
    : `${dist.n||0} trades · Median MFE: ${fmtPctCb(dist.median)} · Mean: ${fmtPctCb(dist.mean)}`;
  const segLabel  = _activeSeg === 'wins' ? 'Winners' : _activeSeg === 'losses' ? 'Losers' : 'All Trades';
  const p       = dist.percentiles || {};
  const ln      = dist.lognorm || {};
  const clus    = dist.clusters || [];
  const triggers= dist.be_triggers || [];
  const hist    = dist.histogram || {};
  const ptq     = dist.ptq_level;
  const ptqRR   = dist.ptq_reach_rate;
  const clusterColors = ['#60a5fa','#fb923c','#10b981'];
  const fmt    = (v,d=4) => v!=null?(+v).toFixed(d):'—';
  const fmtPct = v => v!=null?(+v).toFixed(4)+'%':'—';

  const statTiles = [
    {lbl:'Median', v:fmtPct(dist.median),  c:'#fb923c'},
    {lbl:'Mean',   v:fmtPct(dist.mean),    c:'#fbbf24'},
    {lbl:'p75',    v:fmtPct(p.p75),       c:'#10b981'},
    {lbl:'p90',    v:fmtPct(p.p90),       c:'#a78bfa'},
  ];

  const pctRows = [
    {lbl:'p50', v:dist.median, rr:50, color:'#fb923c', bold:true},
    {lbl:'p75', v:p.p75, rr:25, color:'#10b981'},
    {lbl:'p90', v:p.p90, rr:10, color:'#a78bfa'},
    {lbl:'p95', v:p.p95, rr:5,  color:'#c084fc'},
    {lbl:'p99', v:p.p99, rr:1,  color:'#f87171'},
  ];

  const statTilesF = [
    { lbl:'Median (p50)', v:fmtPct(dist.median), c:'#fb923c' },
    { lbl:'p75',          v:fmtPct(p.p75),       c:'#10b981' },
    { lbl:'p90',          v:fmtPct(p.p90),       c:'#a78bfa' },
    { lbl:'p95',          v:fmtPct(p.p95),       c:'#c084fc' },
  ];
  const pctRowsF = [
    {lbl:'p5',  v:p.p5,        color:'#94a3b8'},
    {lbl:'p10', v:p.p10,       color:'#94a3b8'},
    {lbl:'p15', v:p.p15,       color:'#64748b'},
    {lbl:'p20', v:p.p20,       color:'#64748b'},
    {lbl:'p25', v:p.p25,       color:'#60a5fa'},
    {lbl:'p30', v:p.p30,       color:'#60a5fa'},
    {lbl:'p35', v:p.p35,       color:'#60a5fa'},
    {lbl:'p40', v:p.p40,       color:'#fb923c'},
    {lbl:'p50', v:dist.median, color:'#fb923c', bold:true, desc:'median run'},
    {lbl:'p60', v:p.p60,       color:'#fb923c'},
    {lbl:'p65', v:p.p65,       color:'#fbbf24'},
    {lbl:'p70', v:p.p70,       color:'#fbbf24'},
    {lbl:'p75', v:p.p75,       color:'#10b981',            desc:'25% of trades run further'},
    {lbl:'p80', v:p.p80,       color:'#10b981'},
    {lbl:'p85', v:p.p85,       color:'#10b981'},
    {lbl:'p90', v:p.p90,       color:'#a78bfa',            desc:'TP ambition \u2192 10% reach this'},
    {lbl:'p95', v:p.p95,       color:'#c084fc'},
    {lbl:'p99', v:p.p99,       color:'#f87171',            desc:'1% outliers'},
  ];

  el.innerHTML = `
  <div style="background:${segBg};border:1px solid ${segBorder};border-radius:8px;padding:12px 14px;margin-bottom:12px;">
    <div style="font-family:var(--font-data);font-size:12px;font-weight:700;color:${segColor}">How far do trades run in your favour?</div>
    <div style="font-family:var(--font-data);font-size:11px;color:var(--text-secondary);margin-top:4px;line-height:1.5">
      ${(dist.n||0).toLocaleString()} trades \u00b7 median run = <strong style="color:var(--text-primary)">${fmtPct(dist.median)}</strong>.
      For practical TP placement see the <em>Target Variant Analysis</em> panel below \u2014 it simulates each TP level on actual trades.
    </div>
  </div>
  <div class="panel" style="margin-bottom:12px">
    <div class="ph"><span class="ph-title">MFE Distribution</span><span class="ph-note">\u03c3=${fmt(dist.std,3)}% \u00b7 skew=${fmt(dist.skewness,1)}</span></div>
    <div class="pb">
      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:14px">
        ${statTilesF.map(s=>`
        <div style="background:var(--bg-raised);border:1px solid var(--border-mid);border-radius:6px;padding:10px 8px;text-align:center">
          <div style="font-family:var(--font-data);font-size:9px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.04em;margin-bottom:3px">${s.lbl}</div>
          <div style="font-family:var(--font-display);font-size:15px;font-weight:700;color:${s.c};line-height:1.1">${s.v}</div>
        </div>`).join('')}
      </div>
      <div style="font-family:var(--font-data);font-size:10px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.05em;margin-bottom:6px">Frequency (0 \u2192 p99)</div>
      <canvas id="mfe-study-hist" height="130" style="width:100%;display:block;border-radius:6px;background:var(--bg-raised)"></canvas>
      <table style="width:100%;border-collapse:collapse;margin-top:12px">
        <thead><tr style="border-bottom:1px solid var(--border)">
          <th style="font-family:var(--font-data);font-size:9px;color:var(--text-muted);text-transform:uppercase;padding:5px 8px;text-align:left;font-weight:400">Pct</th>
          <th style="font-family:var(--font-data);font-size:9px;color:var(--text-muted);text-transform:uppercase;padding:5px 8px;text-align:right;font-weight:400">MFE %</th>
          <th style="font-family:var(--font-data);font-size:9px;color:var(--text-muted);text-transform:uppercase;padding:5px 8px;text-align:left;font-weight:400">Reading</th>
        </tr></thead>
        <tbody>
          ${pctRowsF.map(r=>`<tr style="border-bottom:1px solid var(--border)">
            <td style="font-family:var(--font-data);font-size:11px;color:${r.color};padding:5px 8px;font-weight:${r.bold?700:500}">${r.lbl}</td>
            <td style="font-family:var(--font-data);font-size:11px;color:var(--text-primary);padding:5px 8px;text-align:right;font-weight:600">${r.v!=null?(+r.v).toFixed(4)+'%':'\u2014'}</td>
            <td style="font-family:var(--font-data);font-size:10px;color:var(--text-muted);padding:5px 8px">${r.desc || (r.v === 0 ? 'never moved' : '')}</td>
          </tr>`).join('')}
        </tbody>
      </table>
      <div style="margin-top:14px;padding:12px 14px;background:var(--bg-raised);border:1px solid var(--border);border-radius:8px;font-family:var(--font-data);font-size:11px;color:var(--text-secondary);line-height:1.6">
        <strong style="color:var(--text-primary)">Looking for the best take-profit?</strong> The table above describes <em>what happened</em> \u2014
        it doesn't prescribe a TP. See the <strong style="color:var(--green)">Target Variant Analysis</strong> panel below \u2014 it
        simulates every candidate TP level on the actual trade set and reports resulting Win Rate, EV, PF and drawdown.
        That's the empirical answer; picking a percentile here would be circular.
      </div>
    </div>
  </div>`;

  // Draw MFE histogram
  const canvas = document.getElementById('mfe-study-hist');
  if (!canvas || !hist.edges || !hist.counts) return;
  const W = canvas.offsetWidth || 600, H = 140;
  canvas.width = W * devicePixelRatio; canvas.height = H * devicePixelRatio;
  const ctx = canvas.getContext('2d'); ctx.scale(devicePixelRatio, devicePixelRatio);
  const padL=36,padR=12,padT=14,padB=28, cW=W-padL-padR, cH=H-padT-padB;
  const counts=hist.counts, edges=hist.edges, maxC=Math.max(...counts,1), nBins=counts.length, xMax=edges[edges.length-1];
  const cc=C(); ctx.fillStyle=cc.bgCard; ctx.fillRect(0,0,W,H);
  ctx.strokeStyle=cc.gridLine; ctx.lineWidth=1;
  [.25,.5,.75,1].forEach(f=>{const y=padT+cH*(1-f);ctx.beginPath();ctx.moveTo(padL,y);ctx.lineTo(padL+cW,y);ctx.stroke();});
  if(ptq!=null){const ptqX=padL+(ptq/xMax)*cW;ctx.strokeStyle='rgba(16,185,129,.7)';ctx.lineWidth=1.5;ctx.setLineDash([4,3]);ctx.beginPath();ctx.moveTo(ptqX,padT);ctx.lineTo(ptqX,padT+cH);ctx.stroke();ctx.setLineDash([]);ctx.fillStyle='#10b981';ctx.font='bold 10px IBM Plex Mono,monospace';ctx.fillText('PTQ',ptqX+4,padT+11);}
  const bW=cW/nBins;
  counts.forEach((c,i)=>{
    const barH=(c/maxC)*cH, x=padL+i*bW, y=padT+cH-barH, t=i/nBins;
    const r=Math.round(96+(251-96)*Math.min(t*2,1)), g=Math.round(165+(146-165)*Math.min(t*2,1)+(185-146)*Math.max(t*2-1,0)), b=Math.round(250+(60-250)*Math.min(t*2,1));
    ctx.fillStyle=`rgba(${r},${g},${b},.75)`; ctx.fillRect(x+1,y,Math.max(bW-2,1),barH);
  });
  if(dist.median!=null){const medX=padL+(dist.median/xMax)*cW;ctx.strokeStyle='rgba(251,146,60,.8)';ctx.lineWidth=1.5;ctx.setLineDash([3,3]);ctx.beginPath();ctx.moveTo(medX,padT);ctx.lineTo(medX,padT+cH);ctx.stroke();ctx.setLineDash([]);ctx.fillStyle='#fb923c';ctx.font='10px IBM Plex Mono,monospace';ctx.fillText('Med',medX+3,padT+cH-4);}
  ctx.fillStyle='#64748b';ctx.font='9px IBM Plex Mono,monospace';ctx.textAlign='center';
  [0,.25,.5,.75,1].forEach(f=>{const xVal=edges[0]+f*(xMax-edges[0]);ctx.fillText(xVal.toFixed(2)+'%',padL+f*cW,padT+cH+16);});
  ctx.textAlign='right';ctx.fillText(maxC,padL-4,padT+4);ctx.fillText('0',padL-4,padT+cH+4);

  // ── MFE Target Variant Cards ──────────────────────────────────────────────
  // Show how performance changes under 5 MFE-based take-profit caps applied to all trades.
  (function renderMFETargetVariants() {
    const trades = allTrades;
    if (trades.length < 5) return;

    const ACCT_TV = 4500, RPT_TV = 225;
    const params = computeTrainParams(trades);
    // Compute MFE percentiles from winners (use all trades as proxy for train here)
    function pctlTV(sorted, q) {
      if (!sorted.length) return null;
      const i = q * (sorted.length - 1);
      const lo = Math.floor(i), hi = Math.ceil(i);
      return lo === hi ? sorted[lo] : sorted[lo] * (hi - i) + sorted[hi] * (i - lo);
    }
    const winners = trades.filter(t => t.outcome === 'WIN');
    const mfeValsTV = winners.map(t => t.mfe_pct).filter(v => v != null).sort((a, b) => a - b);
    const mfeP50TV = pctlTV(mfeValsTV, 0.50);
    const mfeP75TV = pctlTV(mfeValsTV, 0.75);
    const mfeP90TV = pctlTV(mfeValsTV, 0.90);
    const mfePtqTV = params ? params.mfe.ptq : null;

    const varNames = ['1R Baseline', 'PTQ (winners)', 'P50 (winners)', 'P75 (winners)', 'P90 (winners)'];
    const tpLevels = [null, mfePtqTV, mfeP50TV, mfeP75TV, mfeP90TV];

    const variants = tpLevels.map((tp, vi) => {
      const resolved = tp != null ? resolveWithMFETarget(trades, tp) : trades.map(t => Object.assign({}, t));
      const stats = computeRangeStats(resolved);
      // Count how many trades actually hit this TP (reached = took profit early)
      let reached = 0;
      if (tp != null) {
        trades.forEach(t => { if (t.mfe_pct != null && t.mfe_pct >= tp) reached++; });
      }
      return { name: varNames[vi], tp, stats, reached };
    });

    // Best = highest EV
    let bestIdx = 0;
    for (let i = 1; i < variants.length; i++) {
      if (variants[i].stats && variants[bestIdx].stats &&
          variants[i].stats.ev_r > variants[bestIdx].stats.ev_r) bestIdx = i;
    }

    const fmtPctTV = v => v != null && isFinite(v) ? (+v).toFixed(4) + '%' : '—';
    const fmtDolTV = v => '$' + Math.round(v).toLocaleString();
    function scTV(val, threshGood, threshBad, invert) {
      if (invert) return val <= threshGood ? 'var(--green)' : val >= threshBad ? 'var(--red)' : 'var(--amber)';
      return val >= threshGood ? 'var(--green)' : val <= threshBad ? 'var(--red)' : 'var(--amber)';
    }

    const totalTV = trades.length;
    const metrics = [
      { lbl:'TP Hit', fmt:(s,v)=>{
          if (v.tp == null) return '\u2014';
          const pct = totalTV>0 ? (v.reached/totalTV*100).toFixed(1)+'%' : '0%';
          return `${v.reached} (${pct})`;
        }, score:(s,v)=> v.tp==null ? 'var(--text-muted)' : v.reached/totalTV >= 0.5 ? 'var(--green)' : v.reached/totalTV >= 0.2 ? 'var(--amber)' : 'var(--red)' },
      { lbl:'Win %',   fmt:s=>(s.wr*100).toFixed(1)+'%',             score:s=>scTV(s.wr, 0.55, 0.45, false) },
      { lbl:'EV $',    fmt:s=>fmtDolTV(s.ev_r * RPT_TV),             score:s=>scTV(s.ev_r, 0.05, -0.05, false) },
      { lbl:'Sharpe',  fmt:s=>s.sharpe!=null?s.sharpe.toFixed(2):'—', score:s=>s.sharpe!=null?scTV(s.sharpe, 1.5, 0.5, false):'var(--text-muted)' },
      { lbl:'PF',      fmt:s=>s.pf.toFixed(2),                       score:s=>scTV(s.pf, 1.5, 1.0, false) },
      { lbl:'Max DD',  fmt:s=>'-'+fmtDolTV(s.maxDDPct/100*ACCT_TV), score:s=>scTV(s.maxDDPct, 10, 25, true) },
      { lbl:'Total $', fmt:s=>fmtDolTV(s.totalPnl),                   score:s=>scTV(s.totalPnl, 0, -1, false) },
    ];

    let html = `<div class="panel" style="margin-bottom:14px">
      <div class="ph"><span class="ph-title">Target Variant Analysis</span><span class="ph-note">TP caps derived from <em>winners'</em> MFE distribution \u00b7 \u2605 = highest EV</span></div>
      <div class="pb" style="padding:0">
        <table style="width:100%;border-collapse:collapse;font-family:var(--font-data);font-size:11px">
          <thead>
            <tr style="border-bottom:1px solid var(--border);background:var(--bg-raised)">
              <th style="padding:7px 8px;text-align:left;font-weight:400;font-size:9px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.04em">Metric</th>
              ${variants.map((v,vi)=>{
                const isBest = vi===bestIdx;
                const tpLabel = v.tp!=null?fmtPctTV(v.tp):'1R';
                return `<th style="padding:7px 6px;text-align:right;font-weight:700;font-size:10px;color:${isBest?'var(--green)':'var(--text-secondary)'};${isBest?'background:var(--green-tint);':''}">
                  <div>${v.name}${isBest?' \u2605':''}</div>
                  <div style="font-weight:400;font-size:9px;color:var(--text-muted);margin-top:1px">${tpLabel}</div>
                </th>`;
              }).join('')}
            </tr>
          </thead>
          <tbody>
            ${metrics.map(m=>`
            <tr style="border-bottom:1px solid var(--border)">
              <td style="padding:6px 8px;color:var(--text-muted)">${m.lbl}</td>
              ${variants.map((v,vi)=>{
                if(!v.stats) return `<td style="padding:6px 6px;text-align:right;color:var(--text-muted)">—</td>`;
                const isBest = vi===bestIdx;
                const val   = m.fmt(v.stats, v);
                const color = m.score(v.stats, v);
                return `<td style="padding:6px 6px;text-align:right;color:${color};font-weight:600;${isBest?'background:color-mix(in srgb,var(--green-tint) 40%,transparent);':''}">${val}</td>`;
              }).join('')}
            </tr>`).join('')}
          </tbody>
        </table>
        <div style="padding:10px 14px;border-top:1px solid var(--border);font-family:var(--font-data);font-size:10px;color:var(--text-muted);line-height:1.6">
          <strong style="color:var(--text-primary)">How to read:</strong> TP caps above use MFE percentiles <em>from winners only</em>.
          A cap of "P75 (winners)" converts any trade that reaches that MFE into an early WIN at that level.
          <strong>TP Hit</strong> shows what fraction of trades actually reach each cap \u2014 low hit rates mean the TP rarely fires, leaving most trades to resolve at the 1R baseline.
          Compare <strong>EV $</strong> across columns \u2014 that's the column that matters for TP selection.
        </div>
      </div>
    </div>`;
    el.insertAdjacentHTML('beforeend', html);
  })();
}

export { computeRichStudy, renderMAEStudy, renderMFEStudy };
