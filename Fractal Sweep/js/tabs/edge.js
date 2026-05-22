import { SVG_FONT, isDark, activeModel, activeSmt, activeF3, activeF4 } from '../state.js';
import { getActiveTrades } from '../data.js';
import { C, lineChart } from '../charts.js';

function _wilsonCI(wins, n, z=1.96) {
  if (n === 0) return [0, 0];
  const p = wins / n;
  const denom = 1 + z*z/n;
  const centre = (p + z*z/(2*n)) / denom;
  const margin = (z * Math.sqrt(p*(1-p)/n + z*z/(4*n*n))) / denom;
  return [Math.max(0, centre - margin), Math.min(1, centre + margin)];
}

function _linearReg(xs, ys) {
  const n = xs.length;
  if (n < 2) return null;
  const mx = xs.reduce((a,b)=>a+b,0)/n;
  const my = ys.reduce((a,b)=>a+b,0)/n;
  let sxy=0, sxx=0, syy=0;
  for (let i=0;i<n;i++) { const dx=xs[i]-mx, dy=ys[i]-my; sxy+=dx*dy; sxx+=dx*dx; syy+=dy*dy; }
  if (sxx === 0) return null;
  const slope = sxy/sxx;
  const intercept = my - slope*mx;
  const r = sxy / Math.sqrt(sxx*syy || 1);
  let ss=0;
  for (let i=0;i<n;i++) { const e = ys[i] - (slope*xs[i]+intercept); ss += e*e; }
  const residStd = n > 2 ? Math.sqrt(ss/(n-2)) : 0;
  return { slope, intercept, r, residStd };
}

function renderEdgeStudy(D) {
  if (!D) return;
  const meta = D.meta || {};
  const wr = meta.win_rate ?? 0;
  const ev = meta.ev_per_trade ?? 0;
  const pf = meta.profit_factor ?? 0;
  const n  = meta.total_wl ?? 0;
  const sharpe = D.risk_stats?.sharpe;
  const be = meta.risk_breakeven_wr ?? 0.5;

  const heroEl = document.getElementById('edge-hero');
  if (heroEl) {
    const byYear = (D.by_year||[]).filter(y => y.n >= 20).sort((a,b)=>a.yr-b.yr);
    const regYr = byYear.length >= 3 ? _linearReg(byYear.map(y=>y.yr), byYear.map(y=>y.ev)) : null;
    const slope = regYr?.slope;
    const [wrLo, wrHi] = _wilsonCI(Math.round(wr*n), n);

    const tiles = [
      { lbl:'Win Rate',    v:(wr*100).toFixed(1)+'%', sub:`95% CI ${(wrLo*100).toFixed(1)}–${(wrHi*100).toFixed(1)}%`, c: wr>=be?'var(--green)':'var(--red)' },
      { lbl:'EV / Trade',  v:(ev>=0?'+':'')+ev.toFixed(3)+'R', sub:`${n.toLocaleString()} resolved trades`, c: ev>0?'var(--green)':'var(--red)' },
      { lbl:'Profit Factor', v:pf.toFixed(2), sub: pf>=1.5?'strong':pf>=1.0?'marginal':'losing', c: pf>=1.5?'var(--green)':pf>=1.0?'var(--amber)':'var(--red)' },
      { lbl:'Sharpe',      v:sharpe!=null?sharpe.toFixed(2):'—', sub:'annualised · daily returns', c: sharpe!=null && sharpe>=1.5?'var(--green)':sharpe!=null && sharpe>=1?'var(--amber)':'var(--red)' },
      { lbl:'EV Decay / yr', v:slope!=null?(slope>=0?'+':'')+slope.toFixed(4)+'R':'—', sub:regYr?`r=${regYr.r.toFixed(2)} over ${byYear.length}y`:'needs ≥3 yrs', c: slope==null?'var(--text-muted)':slope>=0?'var(--green)':slope>=-0.02?'var(--amber)':'var(--red)' },
    ];
    heroEl.innerHTML = tiles.map(t=>`
      <div style="background:var(--bg-raised);border:1px solid var(--border-mid);border-radius:8px;padding:14px">
        <div style="font-family:var(--font-data);font-size:9px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.05em;margin-bottom:6px">${t.lbl}</div>
        <div style="font-family:var(--font-display);font-size:22px;font-weight:800;color:${t.c};line-height:1.1">${t.v}</div>
        <div style="font-family:var(--font-data);font-size:10px;color:var(--text-muted);margin-top:6px">${t.sub}</div>
      </div>`).join('');
  }

  const dirEl = document.getElementById('edge-dir-table');
  if (dirEl) {
    const dirs = D.dir_summary || [];
    const fmtPctPts = v => v!=null ? (+v).toFixed(4)+'%' : '—';
    const rows = dirs.map(d => {
      const [lo, hi] = _wilsonCI(d.wins||0, d.n||0);
      return { ...d, wr_lo: lo, wr_hi: hi };
    });
    let html = `<table style="width:100%;border-collapse:collapse;font-family:var(--font-data);font-size:12px">
      <thead><tr style="border-bottom:1px solid var(--border-mid);background:var(--bg-raised);color:var(--text-muted);font-size:10px;text-transform:uppercase;letter-spacing:.05em">
        <th style="padding:8px 10px;text-align:left;font-weight:400">Direction</th>
        <th style="padding:8px 10px;text-align:right;font-weight:400">N</th>
        <th style="padding:8px 10px;text-align:right;font-weight:400">Win Rate</th>
        <th style="padding:8px 10px;text-align:right;font-weight:400">Wilson 95% CI</th>
        <th style="padding:8px 10px;text-align:right;font-weight:400">EV</th>
        <th style="padding:8px 10px;text-align:right;font-weight:400">PF</th>
        <th style="padding:8px 10px;text-align:right;font-weight:400">Avg MAE</th>
        <th style="padding:8px 10px;text-align:right;font-weight:400">Avg MFE</th>
        <th style="padding:8px 10px;text-align:right;font-weight:400">Risk (pts)</th>
      </tr></thead><tbody>`;
    rows.forEach(d => {
      const dirColor = d.direction==='LONG'?'var(--green)':'var(--red)';
      const evColor = d.ev>0?'var(--green)':'var(--red)';
      const pfColor = d.pf>=1.5?'var(--green)':d.pf>=1?'var(--amber)':'var(--red)';
      html += `<tr style="border-bottom:1px solid var(--border)">
        <td style="padding:8px 10px;font-weight:700;color:${dirColor}">${d.direction==='LONG'?'↑ LONG':'↓ SHORT'}</td>
        <td style="padding:8px 10px;text-align:right;color:var(--text-primary)">${(d.n||0).toLocaleString()}</td>
        <td style="padding:8px 10px;text-align:right;font-weight:600;color:var(--text-primary)">${((d.wr||0)*100).toFixed(1)}%</td>
        <td style="padding:8px 10px;text-align:right;color:var(--text-muted)">[${(d.wr_lo*100).toFixed(1)}–${(d.wr_hi*100).toFixed(1)}]</td>
        <td style="padding:8px 10px;text-align:right;font-weight:600;color:${evColor}">${d.ev>0?'+':''}${(d.ev||0).toFixed(3)}R</td>
        <td style="padding:8px 10px;text-align:right;font-weight:600;color:${pfColor}">${(d.pf||0).toFixed(2)}</td>
        <td style="padding:8px 10px;text-align:right;color:#fbbf24">${fmtPctPts(d.avg_mae)}</td>
        <td style="padding:8px 10px;text-align:right;color:#10b981">${fmtPctPts(d.avg_mfe)}</td>
        <td style="padding:8px 10px;text-align:right;color:var(--text-muted)">${(d.avg_risk_pts||0).toFixed(1)}</td>
      </tr>`;
    });
    html += `</tbody></table>`;
    if (rows.length === 2) {
      const [a,b] = rows;
      const evGap = Math.abs(a.ev - b.ev);
      const better = a.ev > b.ev ? a.direction : b.direction;
      const ciOverlap = !(a.wr_hi < b.wr_lo || b.wr_hi < a.wr_lo);
      html += `<div style="margin-top:12px;padding:10px 14px;background:var(--bg-raised);border:1px solid var(--border);border-radius:6px;font-family:var(--font-data);font-size:11px;color:var(--text-secondary);line-height:1.6">
        <strong style="color:var(--text-primary)">${better}</strong> leads by <strong>${evGap.toFixed(3)}R</strong> in EV.
        Win-rate CIs ${ciOverlap ? '<span style="color:var(--amber)">overlap</span> — asymmetry is not statistically significant at 95%' : '<span style="color:var(--green)">do not overlap</span> — asymmetry is statistically significant at 95%'}.
      </div>`;
    }
    dirEl.innerHTML = html;
  }

  const yrEl = document.getElementById('edge-yearly');
  if (yrEl) {
    const byYear = (D.by_year||[]).filter(y => y.n >= 20).sort((a,b)=>a.yr-b.yr);
    if (byYear.length < 2) {
      yrEl.innerHTML = `<div style="padding:20px;font-family:var(--font-data);font-size:11px;color:var(--text-muted)">Need at least 2 years with ≥20 trades for regime analysis.</div>`;
    } else {
      const reg = _linearReg(byYear.map(y=>y.yr), byYear.map(y=>y.ev));
      const W = 900, H = 240, padL = 50, padR = 20, padT = 20, padB = 38;
      const cW = W - padL - padR, cH = H - padT - padB;
      const evs = byYear.map(y=>y.ev);
      const evMin = Math.min(0, ...evs) - 0.05;
      const evMax = Math.max(0.5, ...evs) + 0.05;
      const xS = yr => padL + (byYear.length===1?0.5:(yr - byYear[0].yr)/(byYear[byYear.length-1].yr - byYear[0].yr))*cW;
      const yS = ev => padT + (1 - (ev - evMin)/(evMax - evMin))*cH;

      let svg = `<svg viewBox="0 0 ${W} ${H}" style="width:100%;max-width:100%;display:block" preserveAspectRatio="xMidYMid meet">`;
      [0.0, 0.25, 0.5, 0.75, 1.0].forEach(f => {
        const y = padT + f*cH;
        svg += `<line x1="${padL}" y1="${y}" x2="${padL+cW}" y2="${y}" stroke="var(--border)" stroke-width="0.5"/>`;
        const ev = evMin + (1-f)*(evMax-evMin);
        svg += `<text x="${padL-6}" y="${y+3}" text-anchor="end" font-family="IBM Plex Mono, monospace" font-size="10" fill="var(--text-muted)">${ev.toFixed(2)}R</text>`;
      });
      const y0 = yS(0);
      svg += `<line x1="${padL}" y1="${y0}" x2="${padL+cW}" y2="${y0}" stroke="var(--amber)" stroke-width="1" stroke-dasharray="4,3" opacity="0.6"/>`;
      svg += `<text x="${padL+cW-4}" y="${y0-4}" text-anchor="end" font-family="IBM Plex Mono, monospace" font-size="9" fill="var(--amber)">break-even</text>`;
      if (reg) {
        const r0 = reg.slope*byYear[0].yr + reg.intercept;
        const r1 = reg.slope*byYear[byYear.length-1].yr + reg.intercept;
        const band = reg.residStd;
        svg += `<polygon points="${xS(byYear[0].yr)},${yS(r0+band)} ${xS(byYear[byYear.length-1].yr)},${yS(r1+band)} ${xS(byYear[byYear.length-1].yr)},${yS(r1-band)} ${xS(byYear[0].yr)},${yS(r0-band)}" fill="${reg.slope>=0?'rgba(16,185,129,0.08)':'rgba(239,68,68,0.08)'}"/>`;
        svg += `<line x1="${xS(byYear[0].yr)}" y1="${yS(r0)}" x2="${xS(byYear[byYear.length-1].yr)}" y2="${yS(r1)}" stroke="${reg.slope>=0?'var(--green)':'var(--red)'}" stroke-width="2" stroke-dasharray="5,4"/>`;
      }
      const pts = byYear.map(y => `${xS(y.yr)},${yS(y.ev)}`).join(' ');
      svg += `<polyline points="${pts}" fill="none" stroke="var(--blue)" stroke-width="2"/>`;
      byYear.forEach(y => {
        const r = Math.min(8, Math.max(3, Math.sqrt(y.n)/3));
        svg += `<circle cx="${xS(y.yr)}" cy="${yS(y.ev)}" r="${r}" fill="var(--blue)" stroke="var(--bg-card)" stroke-width="2">
          <title>${y.yr}: ${y.n} trades · WR ${(y.wr*100).toFixed(1)}% · EV ${y.ev>0?'+':''}${y.ev.toFixed(3)}R · PF ${y.pf.toFixed(2)}</title>
        </circle>`;
        svg += `<text x="${xS(y.yr)}" y="${padT+cH+16}" text-anchor="middle" font-family="IBM Plex Mono, monospace" font-size="10" fill="var(--text-muted)">${y.yr}</text>`;
      });
      svg += `</svg>`;

      let regNote = '';
      if (reg) {
        const trend = reg.slope >= 0.005 ? 'improving' : reg.slope <= -0.005 ? 'degrading' : 'stable';
        const trendColor = reg.slope >= 0 ? 'var(--green)' : Math.abs(reg.slope) < 0.01 ? 'var(--amber)' : 'var(--red)';
        regNote = `<div style="margin-top:10px;padding:10px 14px;background:var(--bg-raised);border:1px solid var(--border);border-radius:6px;font-family:var(--font-data);font-size:11px;color:var(--text-secondary);line-height:1.6">
          Linear trend: <strong style="color:${trendColor}">${trend}</strong> at
          <strong>${reg.slope>=0?'+':''}${reg.slope.toFixed(4)}R/yr</strong>
          · correlation r=${reg.r.toFixed(2)}
          · residual σ=${reg.residStd.toFixed(3)}R
          ${Math.abs(reg.r) < 0.3 ? '· <span style="color:var(--amber)">weak fit — EV likely noisy around mean</span>' : ''}
        </div>`;
      }
      yrEl.innerHTML = svg + regNote;
    }
  }

  const hmEl = document.getElementById('heatmap');
  if (hmEl) {
    const data = D.heatmap || [];
    const DOW_ORDER = ['Mon','Tue','Wed','Thu','Fri'];
    const hrs = [...new Set(data.map(d=>d.hr))].sort((a,b)=>a-b);
    const byKey = {};
    data.forEach(d => byKey[`${d.dow_name}_${d.hr}`] = d);
    const evs = data.map(d=>d.ev).filter(v=>v!=null);
    const evMax = Math.max(0.1, ...evs);
    const evMin = Math.min(0, ...evs);
    const evBg = ev => {
      if (ev == null) return 'var(--bg-raised)';
      if (ev >= 0) {
        const t = Math.min(1, ev/evMax);
        return `rgba(16,185,129,${0.22 + t*0.55})`;
      }
      const t = Math.min(1, Math.abs(ev)/Math.abs(evMin||1));
      return `rgba(239,68,68,${0.22 + t*0.55})`;
    };
    const evText = ev => {
      if (ev == null) return 'var(--text-muted)';
      const intensity = ev >= 0 ? ev/evMax : Math.abs(ev)/Math.abs(evMin||1);
      return intensity >= 0.35 ? '#ffffff' : 'var(--text-primary)';
    };
    let html = `
      <div style="display:flex;align-items:center;gap:14px;margin-bottom:10px;font-family:var(--font-data);font-size:10px;color:var(--text-muted);flex-wrap:wrap">
        <span style="text-transform:uppercase;letter-spacing:.08em;font-weight:700">Color scale</span>
        <span style="display:inline-flex;align-items:center;gap:6px"><span style="display:inline-block;width:14px;height:14px;background:rgba(239,68,68,.75);border-radius:3px"></span>worst EV (${evMin.toFixed(2)}R)</span>
        <span style="display:inline-flex;align-items:center;gap:6px"><span style="display:inline-block;width:14px;height:14px;background:var(--bg-raised);border:1px solid var(--border);border-radius:3px"></span>~flat</span>
        <span style="display:inline-flex;align-items:center;gap:6px"><span style="display:inline-block;width:14px;height:14px;background:rgba(16,185,129,.75);border-radius:3px"></span>best EV (+${evMax.toFixed(2)}R)</span>
      </div>
      <div style="overflow-x:auto">
      <table style="border-collapse:separate;border-spacing:2px;font-family:var(--font-data);font-size:12px;margin:0 auto">
        <thead><tr>
          <th style="padding:6px 10px"></th>
          ${hrs.map(h=>`<th style="padding:6px 4px;text-align:center;color:var(--text-muted);font-weight:600;font-size:11px;min-width:52px">${String(h).padStart(2,'0')}:00</th>`).join('')}
        </tr></thead><tbody>`;
    DOW_ORDER.forEach(dn => {
      html += `<tr><td style="padding:6px 12px 6px 2px;color:var(--text-secondary);font-weight:700;font-size:12px;text-align:right">${dn}</td>`;
      hrs.forEach(h => {
        const c = byKey[`${dn}_${h}`];
        if (!c) { html += `<td style="background:var(--bg-raised);min-width:52px;height:44px;border-radius:6px"></td>`; return; }
        const bg = evBg(c.ev);
        const textColor = evText(c.ev);
        const nStr = c.n.toLocaleString();
        html += `<td style="background:${bg};min-width:52px;height:44px;padding:0;text-align:center;border-radius:6px;color:${textColor};font-weight:700;font-size:12px;cursor:help;line-height:1.2;box-shadow:inset 0 0 0 1px rgba(255,255,255,.04)" title="${dn} ${h}:00\u000An=${nStr}\u000AWR ${(c.wr*100).toFixed(1)}%\u000APF ${c.pf!=null?c.pf.toFixed(2):'\u2014'}\u000AEV ${c.ev>0?'+':''}${c.ev.toFixed(3)}R">
          <div>${c.ev>=0?'+':''}${c.ev.toFixed(2)}</div>
          <div style="font-size:9px;font-weight:500;opacity:.75;margin-top:1px">n=${nStr}</div>
        </td>`;
      });
      html += `</tr>`;
    });
    html += `</tbody></table></div>`;
    hmEl.innerHTML = html;
  }

  function renderGrpTable(el, rows, groupKey, groupLabel) {
    if (!el) return;
    if (!rows || !rows.length) { el.innerHTML = `<div style="padding:16px;color:var(--text-muted);font-family:var(--font-data);font-size:11px">No data.</div>`; return; }
    const byG = {};
    rows.forEach(r => {
      const k = r[groupKey];
      if (!byG[k]) byG[k] = { n:0, wins:0, evSum:0, pfNum:0, pfDen:0 };
      byG[k].n += r.n;
      byG[k].wins += r.wins;
      byG[k].evSum += r.ev * r.n;
    });
    const aggregated = Object.entries(byG).map(([k,v]) => {
      const [lo, hi] = _wilsonCI(v.wins, v.n);
      return { grp:k, n:v.n, wr:v.n?v.wins/v.n:0, wr_lo:lo, wr_hi:hi, ev:v.n?v.evSum/v.n:0 };
    }).sort((a,b)=> b.ev - a.ev);
    let html = `<table style="width:100%;border-collapse:collapse;font-family:var(--font-data);font-size:11px">
      <thead><tr style="border-bottom:1px solid var(--border-mid);color:var(--text-muted);font-size:10px;text-transform:uppercase;letter-spacing:.04em">
        <th style="padding:7px 8px;text-align:left;font-weight:400">${groupLabel}</th>
        <th style="padding:7px 8px;text-align:right;font-weight:400">N</th>
        <th style="padding:7px 8px;text-align:right;font-weight:400">WR</th>
        <th style="padding:7px 8px;text-align:right;font-weight:400">95% CI</th>
        <th style="padding:7px 8px;text-align:right;font-weight:400">EV</th>
      </tr></thead><tbody>`;
    aggregated.forEach(a => {
      const evC = a.ev>0?'var(--green)':'var(--red)';
      html += `<tr style="border-bottom:1px solid var(--border)">
        <td style="padding:6px 8px;color:var(--text-primary);font-weight:600">${a.grp}</td>
        <td style="padding:6px 8px;text-align:right;color:var(--text-muted)">${a.n.toLocaleString()}</td>
        <td style="padding:6px 8px;text-align:right;color:var(--text-primary);font-weight:600">${(a.wr*100).toFixed(1)}%</td>
        <td style="padding:6px 8px;text-align:right;color:var(--text-muted)">[${(a.wr_lo*100).toFixed(0)}–${(a.wr_hi*100).toFixed(0)}]</td>
        <td style="padding:6px 8px;text-align:right;color:${evC};font-weight:600">${a.ev>0?'+':''}${a.ev.toFixed(3)}R</td>
      </tr>`;
    });
    html += `</tbody></table>`;
    el.innerHTML = html;
  }
  renderGrpTable(document.getElementById('edge-sess-table'), D.by_session||[], 'session', 'Session');
  renderGrpTable(document.getElementById('edge-dow-table'),  D.by_dow||[],     'dow_name','Day');

  const baseEV = ev, baseVar = (be*(1-be))/Math.max(n,1);
  const rankCombo = c => {
    const sd = Math.sqrt(Math.max(0.001, (c.pf||1) * 0.5 / Math.max(c.n,1)));
    return (c.ev - baseEV) / sd;
  };
  const topEl = document.getElementById('top-combos');
  const worstEl = document.getElementById('worst-combos');
  if (topEl || worstEl) {
    const combos = (D.top_combos||[]).filter(c => c.n >= 6).map(c => ({...c, z: rankCombo(c)}));
    combos.sort((a,b)=> b.z - a.z);
    const renderCombo = (container, rows) => {
      if (!container) return;
      if (!rows.length) { container.innerHTML = `<div style="padding:14px;color:var(--text-muted);font-family:var(--font-data);font-size:11px">No combos meeting n≥6.</div>`; return; }
      let html = `<table style="width:100%;border-collapse:collapse;font-family:var(--font-data);font-size:11px">
        <thead><tr style="border-bottom:1px solid var(--border-mid);color:var(--text-muted);font-size:10px;text-transform:uppercase;letter-spacing:.04em">
          <th style="padding:7px 8px;text-align:left;font-weight:400">Setup</th>
          <th style="padding:7px 8px;text-align:right;font-weight:400">N</th>
          <th style="padding:7px 8px;text-align:right;font-weight:400">WR</th>
          <th style="padding:7px 8px;text-align:right;font-weight:400">EV</th>
          <th style="padding:7px 8px;text-align:right;font-weight:400">PF</th>
          <th style="padding:7px 8px;text-align:right;font-weight:400">z-vs-base</th>
        </tr></thead><tbody>`;
      rows.forEach(c => {
        const evC = c.ev>0?'var(--green)':'var(--red)';
        const zC  = c.z>=1.5?'var(--green)':c.z>=0.5?'var(--amber)':c.z<=-0.5?'var(--red)':'var(--text-muted)';
        html += `<tr style="border-bottom:1px solid var(--border)">
          <td style="padding:6px 8px;color:var(--text-primary)">${c.label}</td>
          <td style="padding:6px 8px;text-align:right;color:var(--text-muted)">${c.n}</td>
          <td style="padding:6px 8px;text-align:right;color:var(--text-primary);font-weight:600">${(c.wr*100).toFixed(1)}%</td>
          <td style="padding:6px 8px;text-align:right;color:${evC};font-weight:600">${c.ev>0?'+':''}${c.ev.toFixed(3)}R</td>
          <td style="padding:6px 8px;text-align:right;color:var(--text-secondary)">${c.pf.toFixed(2)}</td>
          <td style="padding:6px 8px;text-align:right;color:${zC};font-weight:700">${c.z>=0?'+':''}${c.z.toFixed(2)}σ</td>
        </tr>`;
      });
      html += `</tbody></table>`;
      container.innerHTML = html;
    };
    renderCombo(topEl, combos.slice(0, 10));
    renderCombo(worstEl, [...combos].reverse().slice(0, 8));
  }

  // Sub-hour detail — based on active model
  renderSubHourEl(D);
}

function renderSubHourEl(D) {
  const el = document.getElementById('edge-subhour');
  if (!el) return;

  const segmentMin = activeModel === '15M_1M' ? 15 : activeModel === '30M_3M' ? 30 : null;
  const segLabel = document.getElementById('subhour-label');
  const titleLabel = document.getElementById('subhour-title');
  if (!segmentMin) {
    if (segLabel) segLabel.textContent = 'Sub-Hour Detail';
    if (titleLabel) titleLabel.textContent = 'Performance by Hour';
    el.innerHTML = '<div style="font-family:var(--font-data);font-size:11px;color:var(--text-muted);padding:8px">Select 30M_3M or 15M_1M model for half-hour or quarter-hour breakdowns.</div>';
    return;
  }
  const segCount = 60 / segmentMin;
  const segNames = segCount === 2 ? ['0\u201329', '30\u201359']
    : ['0\u201314', '15\u201329', '30\u201344', '45\u201359'];

  if (segLabel) segLabel.textContent = `Sub-Hour Detail \u00b7 ${segmentMin}-Minute Segments`;
  if (titleLabel) titleLabel.textContent = `Performance by ${segmentMin}-Minute Segment`;

  let trades = getActiveTrades(D);
  if (!trades || !trades.length) {
    el.innerHTML = '<div style="font-family:var(--font-data);font-size:11px;color:var(--text-muted);padding:8px">No trade data available.</div>';
    return;
  }
  // Apply active filters
  if (activeSmt) trades = trades.filter(t => t.smt === true);
  if (activeF3)  trades = trades.filter(t => t.passes_f3 === true);
  if (activeF4)  trades = trades.filter(t => t.passes_f4 === true);
  if (!trades.length) {
    el.innerHTML = '<div style="font-family:var(--font-data);font-size:11px;color:var(--text-muted);padding:8px">No trades match active filters.</div>';
    return;
  }

  const allHours = [];
  for (let h = 0; h < 24; h++) allHours.push(h);

  const map = {};
  allHours.forEach(h => {
    map[h] = {};
    for (let s = 0; s < segCount; s++) {
      map[h][s] = { n:0, wins:0, sumR:0 };
    }
  });
  trades.forEach(t => {
    const h = t.hr, mn = t.mn;
    if (h == null || mn == null || !map[h]) return;
    const seg = Math.min(Math.floor(mn / segmentMin), segCount - 1);
    const b = map[h][seg];
    b.n++;
    b.sumR += t.r;
    if (t.outcome === 'WIN') b.wins++;
  });

  const allN = Object.values(map).flatMap(h => Object.values(h)).map(s => s.n);
  const maxN = Math.max(...allN, 1);
  const bgIntensity = n => {
    const t = Math.sqrt(n / maxN);
    return `rgba(59,130,246,${0.05 + t * 0.28})`;
  };
  const wCol = wr => wr >= 0.55 ? '#10b981' : wr >= 0.45 ? '#f59e0b' : '#ef4444';

  // Only show hours with at least 1 trade
  const activeHours = allHours.filter(h => Object.values(map[h]).some(s => s.n > 0));
  if (!activeHours.length) {
    el.innerHTML = '<div style="font-family:var(--font-data);font-size:11px;color:var(--text-muted);padding:8px">No trade data for active filters.</div>';
    return;
  }

  let html = '<div style="overflow-x:auto"><table style="border-collapse:separate;border-spacing:3px;font-family:var(--font-data);font-size:11px;width:100%">';
  html += `<thead><tr><th style="padding:6px 10px;text-align:left;color:var(--text-muted);font-size:10px">Hour</th>`;
  segNames.forEach(n => {
    html += `<th style="padding:6px 4px;text-align:center;color:var(--text-muted);font-weight:600;font-size:10px;min-width:80px">Min ${n}</th>`;
  });
  html += '</tr></thead><tbody>';

  activeHours.forEach(h => {
    html += `<tr><td style="padding:8px 10px;color:var(--text-secondary);font-weight:700;font-size:12px;text-align:left">${String(h).padStart(2,'0')}:00</td>`;
    for (let s = 0; s < segCount; s++) {
      const b = map[h][s];
      if (b.n < 3) {
        html += `<td style="background:var(--bg-raised);border-radius:6px;padding:10px 6px;text-align:center;color:var(--text-muted);font-size:10px">\u2014</td>`;
      } else {
        const wr = b.wins / b.n;
        const ev = b.sumR / b.n;
        const bg = bgIntensity(b.n);
        html += `<td style="background:${bg};border-radius:6px;padding:8px 6px;text-align:center;line-height:1.4">
          <div style="font-weight:700;font-size:12px;color:${wCol(wr)}">${(wr*100).toFixed(0)}<span style="font-size:9px">%</span></div>
          <div style="font-size:10px;color:${ev>=0?'var(--green)':'var(--red)'}">${ev>=0?'+':''}${ev.toFixed(3)}R</div>
          <div style="font-size:9px;color:var(--text-muted);margin-top:2px">n=${b.n}</div>
        </td>`;
      }
    }
    html += '</tr>';
  });
  html += '</tbody></table></div>';
  el.innerHTML = html;
}

export { _wilsonCI, _linearReg, renderEdgeStudy };
