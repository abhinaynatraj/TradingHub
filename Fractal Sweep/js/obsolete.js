// Obsolete code — archived during 2026-05-04 refactor.
// NOT imported by any active module. See obsolete.md for explanations.


// ── Segment stubs (never read) ──
Object.defineProperty(window, '_maeSegment', { get: () => 'all', set: () => {} });
Object.defineProperty(window, '_mfeSegment', { get: () => 'all', set: () => {} });

// ── Dead segment switchers ──
function switchExcSeg(seg) {
  _excSegment = seg;
  const D = _getActiveD();
  if (D) { renderMAEStudy(D); renderMFEStudy(D); }
}
// Legacy aliases
function switchMAESeg(seg) { switchExcSeg(seg); }
function switchMFESeg(seg) { switchExcSeg(seg); }

// ── T-Spot demo data (never consumed) ──
  const TSPOT_CFG=[
    {key:'Normal_BULL',    wrMod:+0.04, frac:0.40, isBull:true},
    {key:'Normal_BEAR',    wrMod:+0.01, frac:0.40, isBull:false},
    {key:'Expansive_BULL', wrMod:+0.06, frac:0.30, isBull:true},
    {key:'Expansive_BEAR', wrMod:-0.02, frac:0.30, isBull:false},
    {key:'ProTrend_BULL',  wrMod:+0.02, frac:0.30, isBull:true},
    {key:'ProTrend_BEAR',  wrMod:-0.01, frac:0.30, isBull:false},
  ];
  const tspot_breakdown={};
  TSPOT_CFG.forEach(({key,wrMod,frac,isBull})=>{
    const tkWr=Math.max(0.10,Math.min(0.95,wrBase+wrMod));
    const tkN=Math.round(wl*frac*(isBull?0.55:0.45));
    const tkW=Math.round(tkN*tkWr);
    const mkEv=wr=>+(wr*2-(1-wr)).toFixed(3);
    const mkPf=wr=>+(wr*2/Math.max(1-wr,0.01)).toFixed(3);
    const hm=[8,9,10,11,12,13,14,15].flatMap(hr=>[1,2,3,4,5].map(dow=>{
      const w=+(tkWr+(dow===4?0.05:dow===3?-0.03:0)+Math.sin(hr*0.7+dow)*0.025).toFixed(3);
      const n=Math.max(2,Math.round((6+hr-7+dow)*(riskMed/18)));
      return {hr,dow,dow_name:DOW[dow-1],wr:w,n,ev:mkEv(w)};
    }));
    const bh=[8,9,10,11,12,13,14,15].map(hr=>{
      const w=+(tkWr+Math.sin(hr*0.8)*0.03).toFixed(3);
      return {hr,hr_label:`${hr.toString().padStart(2,'0')}:00`,n:Math.max(3,Math.round((10+hr*1.5)*(riskMed/18))),wr:w,wins:0,ev:mkEv(w)};
    }).map(d=>({...d,wins:Math.round(d.n*d.wr)}));
    const bd=[1,2,3,4,5].map((dow,di)=>{
      const w=+(tkWr+(dow===4?0.05:0)+Math.sin(di*0.9)*0.02).toFixed(3);
      return {dow,dow_name:DOW[di],n:Math.max(3,Math.round((22+di*6)*(riskMed/18))),wr:w,ev:mkEv(w)};
    });
    const tc=[{hr:9,dow:4},{hr:10,dow:1},{hr:14,dow:2}].map((x,i)=>{
      const w=+(tkWr+0.08-i*0.025).toFixed(3);
      const n=Math.max(4,Math.round((15+i*4)*(riskMed/18)));
      const dir=isBull?'LONG':'SHORT';
      return {hr:x.hr,dow:x.dow,dow_name:DOW[x.dow-1],direction:dir,n,wr:w,wins:Math.round(n*w),ev:mkEv(w),pf:mkPf(w),label:`${DOW[x.dow-1]} ${x.hr}:00 ${dir}`};
    });
    tspot_breakdown[key]={overall:{n:tkN,wins:tkW,wr:tkWr,ev:mkEv(tkWr),pf:mkPf(tkWr),avg_risk_pts:riskMed},heatmap:hm,by_hour:bh,by_dow:bd,top_combos:tc};
  });

// ── Empty classification fallback ──
const CLASSIFICATION_DATA = {};

// ── Superseded chart: barChart ──
function barChart(container,data,H,yMin,yMax){
  const W=container.clientWidth||600,c=C();
  const ml=44,mr=18,mt=20,mb=36,cw=W-ml-mr,ch=H-mt-mb,range=yMax-yMin;
  const yS=v=>(1-(v-yMin)/range)*ch;
  const groups=[...new Set(data.map(d=>d.group))];
  const keys=[...new Set(data.map(d=>d.key))];
  const clrs={LONG:c.green,SHORT:c.red};
  const gw=cw/groups.length,bw=Math.min(24,gw/(keys.length+0.8)),bgap=4;
  let defs='',grid='',bars='',vlbls='',xl='',yl='';

  // Edge zone highlight (>55%)
  if(55>=yMin&&55<=yMax){
    const y55=yS(55),yTop=yS(yMax);
    grid+=`<rect x="0" y="${yTop}" width="${cw}" height="${y55-yTop}" fill="${isDark?'rgba(16,185,129,.04)':'rgba(16,185,129,.03)'}" rx="0"/>`;
  }
  // Grid lines
  [33.3,40,50,55,60,70].forEach(yv=>{
    if(yv<yMin||yv>yMax)return;
    const y=yS(yv),isBe=yv===33.3,isEdge=yv===55;
    const col=isBe?c.beLine:isEdge?'rgba(16,185,129,.35)':c.gridLine;
    const dash=isBe?'6,3':isEdge?'5,3':'2,4';
    const lw=isBe?1.5:1;
    grid+=`<line x1="0" y1="${y}" x2="${cw}" y2="${y}" stroke="${col}" stroke-width="${lw}" stroke-dasharray="${dash}"/>`;
    const tag=isBe?'BE':isEdge?'55%':`${yv}%`;
    if(isBe||isEdge) grid+=`<text x="${cw+6}" y="${y+4}" text-anchor="start" font-size="8" font-weight="600" fill="${isBe?c.amber:c.green}" font-family="${SVG_FONT}">${tag}</text>`;
    yl+=`<text x="-7" y="${y+4}" text-anchor="end" font-size="9" fill="${c.axisText}" font-family="${SVG_FONT}">${yv===33.3?'33':yv}%</text>`;
  });


// ── Superseded chart: renderHeatmap ──
function renderHeatmap(container,data){
  const HOURS=[8,9,10,11,12,13,14,15],DOWS=[1,2,3,4,5];
  const DN={1:'Mon',2:'Tue',3:'Wed',4:'Thu',5:'Fri'};
  const HL={8:'08:00',9:'09:00',10:'10:00',11:'11:00',12:'12:00',13:'13:00',14:'14:00',15:'15:00'};
  const lk={};data.forEach(d=>{lk[`${d.hr}_${d.dow}`]=d;});
  const hdrs=`<div></div>${DOWS.map(d=>`<div class="hm-hdr">${DN[d]}</div>`).join('')}`;
  const rows=HOURS.map(hr=>{
    const cells=DOWS.map(dow=>{const c=lk[`${hr}_${dow}`],wr=c?.wr;return `<div class="hm-cell" style="background:${wrHeatClr(wr)}"${c?` onmouseenter="showTip(event,[['${HL[hr]} ${DN[dow]}','',''],['---','',''],['Win Rate','${pct(wr)}','g'],['EV','${c.ev!=null?(c.ev>0?'+':'')+c.ev.toFixed(3)+'R':'—'}','g'],['n','${c.n}','']])" onmouseleave="hideTip()"`:''}>
        ${c?`<div class="hm-wr" style="color:${wrHeatTxt(wr)}">${pct(wr)}</div><div class="hm-n">n=${c.n}</div>`:`<div class="hm-n" style="color:var(--text-faint)">—</div>`}
      </div>`;}).join('');
    return `<div class="hm-row-lbl">${HL[hr]}</div>${cells}`;
  }).join('');
  const leg=`<div class="hm-legend">${[['rgba(239,68,68,.32)','< 35%'],['rgba(245,158,11,.15)','48–53%'],['rgba(16,185,129,.30)','> 58%']].map(([bg,l])=>`<div class="hm-leg-item"><div class="hm-leg-swatch" style="background:${bg}"></div>${l}</div>`).join('')}<span style="margin-left:auto;font-family:${SVG_FONT};font-size:11px;color:var(--text-muted)">Breakeven = 33.3%</span></div>`;
  container.innerHTML=`<div class="hm-grid">${hdrs}${rows}</div>${leg}`;
}

// ── Superseded chart: comboTable ──
function comboTable(container,data){
  const rows=data.map((c,i)=>`<tr>
    <td><span class="rnk">${i+1}</span></td>
    <td><span class="setup-name">${c.dow_name} ${c.hr}:00</span><span class="dir-tag ${c.direction==='LONG'?'long':'short'}">${c.direction}</span></td>
    <td style="color:var(--text-secondary)">${c.n}</td>
    <td style="color:${c.wr>=0.55?'var(--green)':c.wr>=0.45?'var(--amber)':'var(--red)'};font-weight:600">${pct(c.wr)}</td>
    <td class="${evCls(c.ev)}">${evFmt(c.ev)}</td>
    <td style="color:${c.pf>=2?'var(--green)':c.pf>=1.5?'var(--amber)':'var(--red)'};font-weight:600">${pfFmt(c.pf)}</td>
    <td style="color:var(--text-muted)">${c.avg_risk_pts?c.avg_risk_pts+'pt':'—'}</td>
  </tr>`).join('');
  container.innerHTML=`<table class="ct"><thead><tr><th>#</th><th>Setup</th><th>N</th><th>Win Rate</th><th>EV</th><th>PF</th><th>Avg Risk</th></tr></thead><tbody>${rows}</tbody></table>`;
}

// ── Unused fmtDate ──
function fmtDate(s) {
  if (!s) return '';
  // Trim to YYYY-MM-DD (handles ISO timestamps like 2014-09-08T00:00:00.000000)
  const m = String(s).match(/^(\d{4}-\d{2}-\d{2})/);
  return m ? m[1] : String(s);

// ── Dead switchers: switchMode, switchCisd ──
function switchMode(m){  activeMode=m;  _tradesPage=0; renderControls(); renderActive(); }
function switchCisd(c){  activeCisd=c;  renderControls(); renderActive(); }

// ── Dead canvas: drawGroupedBars ──
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

// ── Dead canvas: drawLineChart ──
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

// ── Dead canvas: drawScatterPlot ──
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

// ── Superseded: renderSweepMAEAnalysis ──
function renderSweepMAEAnalysis(D) {
  const mgEl  = document.getElementById('mae-mfe-grid');
  const mn2El = document.getElementById('mae-mfe-note');
  if (!mgEl) return;
  const rs   = D?.risk_stats || {};
  const m    = D?.meta       || {};
  const bell = rs.mae_bell;
  const ce   = rs.ce;
  const slPct = rs.sl_pct;

  const fp = v => v != null ? v.toFixed(4) + '%' : '—';

  const ceColor  = ce == null ? 'var(--text-muted)' : ce >= 0.40 ? 'var(--green)' : ce >= 0.20 ? 'var(--amber)' : 'var(--red)';
  const ceRating = ce == null ? '—' : ce >= 0.40 ? 'Strong' : ce >= 0.20 ? 'Workable' : 'Weak';

  const candidates = bell ? [
    {label:'Mean (μ)',  val:bell.mean,      cov:bell.cov_mean,  color:'#60a5fa'},
    {label:'+0.5σ',     val:bell.plus_0_5s, cov:bell.cov_0_5s,  color:'#fbbf24'},
    {label:'+1σ',       val:bell.plus_1s,   cov:bell.cov_1s,    color:'#fb923c'},
    {label:'+1.5σ',     val:bell.plus_1_5s, cov:bell.cov_1_5s,  color:'#a78bfa'},
    {label:'+2σ',       val:bell.plus_2s,   cov:bell.cov_2s,    color:'#c084fc'},
  ] : [];

  const slRow = c => {
    const isCurrent = slPct != null && Math.abs(c.val - slPct) / slPct < 0.05;
    return `<tr style="background:${isCurrent?'rgba(16,185,129,0.08)':''}">
      <td style="font-family:var(--font-data);font-size:11px;color:${c.color};padding:6px 10px;width:80px">${c.label}</td>
      <td style="font-family:var(--font-data);font-size:12px;color:var(--text-primary);padding:6px 10px;font-weight:600">${c.val.toFixed(4)}%</td>
      <td style="padding:6px 10px">
        <div style="display:flex;align-items:center;gap:8px">
          <div style="flex:1;height:5px;background:var(--border);border-radius:3px;max-width:100px">
            <div style="width:${c.cov}%;height:100%;background:${c.color};border-radius:3px;opacity:0.7"></div>
          </div>
          <span style="font-family:var(--font-data);font-size:10px;color:var(--text-muted)">${c.cov}%</span>
        </div>
      </td>
      <td style="font-family:var(--font-data);font-size:10px;color:var(--green);padding:6px 10px">${isCurrent?'← current profile':''}</td>
    </tr>`;
  };

  mgEl.style.display = 'block';
  mgEl.innerHTML = `
    <div style="display:grid;grid-template-columns:1fr 1.4fr;gap:24px;align-items:start">
      <!-- Left: CE + R stats -->
      <div>
        <div style="background:var(--bg-alt,#0d1420);border:1px solid var(--border);border-radius:8px;padding:14px 16px;margin-bottom:12px">
          <div style="font-family:var(--font-data);font-size:9px;letter-spacing:.08em;text-transform:uppercase;color:var(--text-muted);margin-bottom:6px">Combined Edge (CE)</div>
          <div style="font-size:32px;font-weight:700;color:${ceColor};line-height:1;margin-bottom:3px">${ce != null ? ce.toFixed(2) : '—'}</div>
          <div style="font-family:var(--font-data);font-size:11px;color:${ceColor};margin-bottom:6px">${ceRating} entries</div>
          <div style="font-size:11px;color:var(--text-muted);line-height:1.5">avg(MFE ÷ MAE) on wins — how hard price runs for you vs. against you</div>
        </div>

// ── Superseded: drawSweepMAEBell ──
function drawSweepMAEBell(canvas, bell, currentSlPct) {
  const dpr = window.devicePixelRatio || 1;
  const W = canvas.offsetWidth || 400, H = 120;
  canvas.width = W * dpr; canvas.height = H * dpr;
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);

  const mu = bell.mean, sd = bell.std;
  const xMin = Math.max(0, mu - 1.5*sd), xMax = mu + 2.8*sd;
  const pad = {l:8, r:8, t:12, b:28};
  const w = W - pad.l - pad.r, h = H - pad.t - pad.b;

  function normPDF(x) {
    return Math.exp(-0.5*Math.pow((x-mu)/sd,2)) / (sd*Math.sqrt(2*Math.PI));
  }
  const maxPDF = normPDF(mu);
  const px = x => pad.l + Math.max(0,Math.min(1,(x-xMin)/(xMax-xMin)))*w;
  const py = y => pad.t + h - (y/(maxPDF*1.15))*h;

  const bands = [
    {from:xMin,to:mu,fill:'rgba(96,165,250,0.06)'},
    {from:mu,to:mu+0.5*sd,fill:'rgba(251,191,36,0.08)'},
    {from:mu+0.5*sd,to:mu+sd,fill:'rgba(251,146,60,0.10)'},
    {from:mu+sd,to:mu+1.5*sd,fill:'rgba(167,139,250,0.12)'},
    {from:mu+1.5*sd,to:mu+2.5*sd,fill:'rgba(192,132,252,0.12)'},
  ];
  bands.forEach(({from,to,fill})=>{
    ctx.beginPath(); ctx.moveTo(px(from),py(0));
    for(let i=0;i<=50;i++){const x=from+(to-from)*i/50;ctx.lineTo(px(x),py(normPDF(x)));}
    ctx.lineTo(px(to),py(0)); ctx.closePath(); ctx.fillStyle=fill; ctx.fill();
  });

  ctx.beginPath();
  for(let i=0;i<=300;i++){const x=xMin+(xMax-xMin)*i/300;i===0?ctx.moveTo(px(x),py(normPDF(x))):ctx.lineTo(px(x),py(normPDF(x)));}
  ctx.strokeStyle='rgba(148,163,184,0.5)'; ctx.lineWidth=1.5; ctx.stroke();

  [{x:mu,c:'#60a5fa',lbl:'μ'},{x:mu+0.5*sd,c:'#fbbf24',lbl:'+½σ'},{x:mu+sd,c:'#fb923c',lbl:'+1σ'},{x:mu+1.5*sd,c:'#a78bfa',lbl:'+1.5σ'},{x:mu+2*sd,c:'#c084fc',lbl:'+2σ'}]
  .forEach(({x,c,lbl})=>{
    if(x<xMin||x>xMax)return;
    ctx.save(); ctx.strokeStyle=c; ctx.lineWidth=1; ctx.setLineDash([3,3]);
    ctx.beginPath(); ctx.moveTo(px(x),pad.t); ctx.lineTo(px(x),pad.t+h); ctx.stroke(); ctx.restore();
    ctx.fillStyle=c; ctx.font='8px monospace';
    ctx.fillText(lbl, Math.min(px(x)+2,W-24), pad.t+h+10);
  });

  if(currentSlPct!=null){
    const cx=px(currentSlPct);
    ctx.save(); ctx.strokeStyle='#10b981'; ctx.lineWidth=2; ctx.setLineDash([]);
    ctx.beginPath(); ctx.moveTo(cx,pad.t); ctx.lineTo(cx,pad.t+h+6); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(cx,pad.t+h+6); ctx.lineTo(cx-4,pad.t+h+14); ctx.lineTo(cx+4,pad.t+h+14); ctx.closePath();
    ctx.fillStyle='#10b981'; ctx.fill(); ctx.restore();
  }
}

// ── Superseded: renderDistributionStudy ──
function renderDistributionStudy(D){
  _renderDistSection('mae', D);
  _renderDistSection('mfe', D);

// ── Superseded: _renderDistSection ──
function _renderDistSection(which, D){
  const allKey  = which + '_dist';
  const winsKey = which + '_wins_dist';
  const lossKey = which + '_loss_dist';
  const statsEl = document.getElementById(which + '-dist-stats');
  const canvasEl= document.getElementById(which + '-hist-canvas');
  if(!statsEl || !canvasEl) return;

  const allD  = D?.[allKey]  || {};
  const winsD = D?.[winsKey] || {};
  const lossD = D?.[lossKey] || {};

