import { SVG_FONT } from '../state.js';
import { C } from '../charts.js';

function statColor(val, threshGood, threshBad, invert){
  if(invert) return val <= threshGood ? 'var(--green)' : val >= threshBad ? 'var(--red)' : 'var(--amber)';
  return val >= threshGood ? 'var(--green)' : val <= threshBad ? 'var(--red)' : 'var(--amber)';
}
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

export function runMonteCarlo(combinedStats) {
  if (!combinedStats || combinedStats.n < 20) {
    combinedStats._mcRender = null;
    return { html: '' };
  }

  const allTrades = (combinedStats._trades || []).slice().sort((a,b) => a.date.localeCompare(b.date));
  const rValues = allTrades.map(t => t.r);
  const N_SIM = 1000;
  const ACCT_MC = 4500, RPT_MC = 225;

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

  const actualCurve = [ACCT_MC];
  {let eq = ACCT_MC; rValues.forEach(r => { eq += r * RPT_MC; actualCurve.push(eq); });}

  const ruinPct = (mcRuins.filter(Boolean).length / N_SIM * 100).toFixed(1);

  const sortedFinals = mcFinals.slice().sort((a,b) => a - b);
  const ciLow = sortedFinals[Math.floor(N_SIM * 0.025)];
  const ciHigh = sortedFinals[Math.floor(N_SIM * 0.975)];
  const ciMedian = sortedFinals[Math.floor(N_SIM * 0.50)];

  const sortedDDs = mcMaxDDs.slice().sort((a,b) => a - b);
  const ddMedian = sortedDDs[Math.floor(N_SIM * 0.50)];
  const ddP90 = sortedDDs[Math.floor(N_SIM * 0.90)];
  const ddP95 = sortedDDs[Math.floor(N_SIM * 0.95)];

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

  const meanR = rValues.reduce((s,v) => s+v, 0) / rValues.length;
  const cusum = [0];
  for(let i = 0; i < rValues.length; i++){
    cusum.push(cusum[i] + (rValues[i] - meanR));
  }

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

      ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue('--bg-card').trim() || '#1a1a2e';
      ctx.fillRect(0, 0, W, H);

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

      if(opts.zeroLine && yMin < 0 && yMax > 0){
        const zeroY = pad.t + plotH * (1 - (0 - yMin) / yR);
        ctx.strokeStyle = 'rgba(255,255,255,0.3)';
        ctx.lineWidth = 1;
        ctx.setLineDash([4,4]);
        ctx.beginPath(); ctx.moveTo(pad.l, zeroY); ctx.lineTo(pad.l + plotW, zeroY); ctx.stroke();
        ctx.setLineDash([]);
      }

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

      if(opts.title){
        ctx.fillStyle = 'rgba(200,200,200,0.5)';
        ctx.font = '10px monospace';
        ctx.textAlign = 'right';
        ctx.fillText(opts.title, pad.l + plotW, pad.t - 6);
      }
    }, 50);
  }

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

      ctx.fillStyle = 'rgba(180,180,180,0.6)';
      ctx.font = '10px monospace';
      ctx.textAlign = 'center';
      for(let i = 0; i <= 4; i++){
        const val = mn + (mx - mn) * i / 4;
        const x = pad.l + plotW * i / 4;
        ctx.fillText(opts.xFmt ? opts.xFmt(val) : val.toFixed(1), x, H - 8);
      }

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

  let html = '';
  html += secHeader('Monte Carlo Simulation (' + N_SIM.toLocaleString() + ' runs, ' + rValues.length + ' trades)');

  html += `<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:16px">`;
  html += heroTile('Ruin Probability', ruinPct + '%', parseFloat(ruinPct) <= 1 ? 'var(--green)' : parseFloat(ruinPct) <= 5 ? 'var(--amber)' : 'var(--red)', 'P(account \u2264 $0)');
  html += heroTile('Final Equity 95% CI', fmtDol(ciLow) + ' \u2013 ' + fmtDol(ciHigh), 'var(--blue, #3b82f6)', 'median ' + fmtDol(ciMedian));
  html += heroTile('Win Rate 95% CI', wrCILow + '% \u2013 ' + wrCIHigh + '%', 'var(--blue, #3b82f6)', 'bootstrap');
  html += heroTile('EV 95% CI', evCILow + 'R \u2013 ' + evCIHigh + 'R', parseFloat(evCILow) > 0 ? 'var(--green)' : 'var(--red)', 'bootstrap');
  html += `</div>`;

  html += `<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:16px">`;
  html += heroTile('Max DD (Median)', ddMedian.toFixed(1) + '%', statColor(ddMedian, 15, 30, true), 'across ' + N_SIM + ' orderings');
  html += heroTile('Max DD (P90)', ddP90.toFixed(1) + '%', statColor(ddP90, 20, 40, true), '90th percentile');
  html += heroTile('Max DD (P95)', ddP95.toFixed(1) + '%', statColor(ddP95, 25, 50, true), '95th percentile \u2014 expect this');
  html += `</div>`;

  html += `<div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:12px;margin-bottom:16px;box-shadow:var(--shadow)">
    <div style="font-family:var(--font-data);font-size:11px;font-weight:600;color:var(--text-muted);margin-bottom:8px">EQUITY CURVE \u2014 Monte Carlo Confidence Bands</div>
    <canvas id="mc-equity-fan" style="width:100%"></canvas>
  </div>`;

  html += `<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px">`;
  html += `<div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:12px;box-shadow:var(--shadow)">
    <div style="font-family:var(--font-data);font-size:11px;font-weight:600;color:var(--text-muted);margin-bottom:8px">MAX DRAWDOWN DISTRIBUTION</div>
    <canvas id="mc-dd-hist" style="width:100%"></canvas>
  </div>`;

  html += `<div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:12px;box-shadow:var(--shadow)">
    <div style="font-family:var(--font-data);font-size:11px;font-weight:600;color:var(--text-muted);margin-bottom:8px">FINAL EQUITY DISTRIBUTION</div>
    <canvas id="mc-final-hist" style="width:100%"></canvas>
  </div>`;
  html += `</div>`;

  html += secHeader('Rolling Stability (window = ' + ROLL_N + ' trades)');

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

  html += `<div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:12px;margin-bottom:16px;box-shadow:var(--shadow)">
    <div style="font-family:var(--font-data);font-size:11px;font-weight:600;color:var(--text-muted);margin-bottom:8px">CUSUM \u2014 Cumulative Performance Deviation (upslope = edge active, downslope = edge degrading)</div>
    <canvas id="cusum-chart" style="width:100%"></canvas>
  </div>`;

  combinedStats._mcRender = function(){
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
        {color:'rgba(59,130,246,0.15)', label:'25\u201375%'},
        {color:'rgba(59,130,246,0.08)', label:'5\u201395%'},
      ]
    });

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

    drawHistCanvas('mc-final-hist', mcFinals, {
      height: 180,
      color: 'rgba(59,130,246,0.5)',
      xFmt: v => '$' + Math.round(v/1000) + 'k',
      percentiles: [
        {value: ciMedian, label: 'Median', color: '#3b82f6', dash: [4,4]},
        {value: actualCurve[actualCurve.length - 1], label: 'Actual', color: '#10b981'},
      ]
    });

    const wrMean = combinedStats.wr;
    drawLineCanvas('roll-wr', [
      {data: rollWR, color:'#3b82f6', width:2},
      {data: new Array(rollWR.length).fill(wrMean), color:'rgba(255,255,255,0.3)', width:1, dash:[4,4]},
    ], {height:180, yFmt: v => (v*100).toFixed(0) + '%', title: 'Mean: ' + (wrMean*100).toFixed(1) + '%'});

    drawLineCanvas('roll-ev', [
      {data: rollEV, color:'#10b981', width:2},
      {data: new Array(rollEV.length).fill(0), color:'rgba(255,255,255,0.3)', width:1, dash:[4,4]},
    ], {height:180, zeroLine:true, yFmt: v => v.toFixed(2) + 'R'});

    drawLineCanvas('roll-pf', [
      {data: rollPF.map(v => Math.min(v, 15)), color:'#f59e0b', width:2},
      {data: new Array(rollPF.length).fill(1), color:'rgba(255,255,255,0.3)', width:1, dash:[4,4]},
    ], {height:180, yFmt: v => v.toFixed(1)});

    drawLineCanvas('cusum-chart', [
      {data: cusum, color:'#8b5cf6', width:2.5},
    ], {height:200, zeroLine:true, yFmt: v => v.toFixed(1) + 'R',
      title: 'Slope up = edge active \u00b7 Slope down = degrading'});
  };

  return { html };
}

export function renderRollingStability(combinedStats) {
  if (combinedStats && combinedStats._mcRender) combinedStats._mcRender();
}
