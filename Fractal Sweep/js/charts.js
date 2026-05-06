import { isDark, SVG_FONT, EQ_ACCT, EQ_RPT, currentTheme, activeProfile } from './state.js';
import { showTip, hideTip, pct, evFmt, pfFmt } from './utils.js';
// ── CHART COLOR HELPERS ────────────────────────────────────────────────────
// Per-theme palette. Gold theme remaps green/red/amber/blue to warm metallic tones
// so charts stay on-theme. Light mode uses darker saturations for contrast.
const C = () => {
  if (currentTheme === 'gold') {
    return {
      green:'#d4af37', red:'#c0432f', amber:'#e5b743', blue:'#8a6d2a', purple:'#b8860b',
      gridLine:'rgba(212,175,55,.06)', beLine:'rgba(212,175,55,.6)',
      axisText:'#7a6236', barMid:'#3d2f1d', bgCard:'#14110c',
    };
  }
  if (currentTheme === 'indigo') {
    return {
      green:'#34d399', red:'#f87171', amber:'#fbbf24', blue:'#60a5fa', purple:'#a78bfa',
      gridLine:'rgba(139,124,254,.07)', beLine:'rgba(251,191,36,.55)',
      axisText:'#7e75a8', barMid:'#3a3263', bgCard:'#1a1530',
    };
  }
  if (currentTheme === 'light') {
    return {
      green:'#059669', red:'#dc2626', amber:'#d97706', blue:'#2563eb', purple:'#7c3aed',
      gridLine:'rgba(15,23,42,.06)', beLine:'rgba(217,119,6,.6)',
      axisText:'#64748b', barMid:'#cbd5e1', bgCard:'#ffffff',
    };
  }
  return {
    green:'#10b981', red:'#ef4444', amber:'#f59e0b', blue:'#3b82f6', purple:'#8b5cf6',
    gridLine:'rgba(255,255,255,.04)', beLine:'rgba(245,158,11,.5)',
    axisText:'#4a6480', barMid:'#2e4460', bgCard:'#111827',
  };
};
function lineChart(container,data,H,yMin,yMax,key,labelKey){
  const W=container.clientWidth||340,c=C();
  const ml=42,mr=20,mt=12,mb=28,cw=W-ml-mr,ch=H-mt-mb,range=yMax-yMin;
  const yS=v=>(1-(v-yMin)/range)*ch,xS=i=>i/(data.length-1||1)*cw;
  const pts=data.map((d,i)=>({x:xS(i),y:yS(d[key]*100)}));
  let grid='',yl='',dots='',xl='';
  const path=pts.map((p,i)=>(i===0?`M${p.x},${p.y}`:`L${p.x},${p.y}`)).join('');
  const area=`M${pts[0].x},${ch} `+pts.map(p=>`L${p.x},${p.y}`).join(' ')+` L${pts[pts.length-1].x},${ch} Z`;
  const gId='ag'+Math.random().toString(36).slice(2);
  const grad=`<defs><linearGradient id="${gId}" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="${c.green}" stop-opacity="0.18"/><stop offset="100%" stop-color="${c.green}" stop-opacity="0"/></linearGradient></defs>`;
  [33.3,40,50,60,70].forEach(yv=>{
    if(yv<yMin||yv>yMax)return;
    const y=yS(yv),isBe=yv===33.3;
    grid+=`<line x1="0" y1="${y}" x2="${cw}" y2="${y}" stroke="${isBe?c.beLine:c.gridLine}" stroke-width="${isBe?1.5:1}" stroke-dasharray="${isBe?'6,3':'2,4'}"/>`;
    yl+=`<text x="-6" y="${y+4}" text-anchor="end" font-size="9" fill="${c.axisText}" font-family="${SVG_FONT}">${yv}%</text>`;
  });
  pts.forEach((p,i)=>{
    const d=data[i];
    dots+=`<circle cx="${p.x}" cy="${p.y}" r="3.5" fill="${c.green}" stroke="${isDark?'#111827':'#ffffff'}" stroke-width="2" onmouseenter="showTip(event,[['${d[labelKey]}','${(d[key]*100).toFixed(1)}%','g'],['n','${d.n||0}',''],['EV','${d.ev!=null?(d.ev>0?'+':'')+d.ev.toFixed(3)+'R':'—'}','g']])" onmouseleave="hideTip()" style="cursor:default"/>`;
    if(i%(Math.ceil(data.length/8))===0||i===data.length-1)xl+=`<text x="${p.x}" y="${ch+20}" text-anchor="middle" font-size="9" fill="${c.axisText}" font-family="${SVG_FONT}">${d[labelKey]}</text>`;
  });
  container.innerHTML=`<svg width="${W}" height="${H}" style="overflow:visible;display:block">${grad}<g transform="translate(${ml},${mt})">${grid}<path d="${area}" fill="url(#${gId})"/><path d="${path}" fill="none" stroke="${c.green}" stroke-width="2" stroke-linejoin="round"/>${dots}${yl}${xl}</g></svg>`;
}
function rDistChart(container,data){
  const W=container.clientWidth||340,H=200,c=C();
  const ml=42,mr=8,mt=12,mb=48,cw=W-ml-mr,ch=H-mt-mb;
  const total=data.reduce((s,d)=>s+d.n,0);
  const pcts=data.map(d=>+(d.n/total*100).toFixed(1));
  const maxP=Math.max(...pcts)+4;
  const bw=cw/data.length*0.52,gap=cw/data.length;
  const _rFill=d=>{const b=d.bucket||'';if(/^(Loss|Expired)/.test(b))return c.red;if(/^(1R|>1R)/.test(b))return c.green;if(/^(BE)/.test(b))return c.amber;return c.barMid;};
  let bars='',lbls='',yl='';
  [10,20,30,40,50].forEach(yv=>{if(yv>maxP)return;const y=ch-(yv/maxP)*ch;lbls+=`<line x1="0" y1="${y}" x2="${cw}" y2="${y}" stroke="${c.gridLine}" stroke-width="1" stroke-dasharray="2,4"/>`;yl+=`<text x="-6" y="${y+4}" text-anchor="end" font-size="9" fill="${c.axisText}" font-family="${SVG_FONT}">${yv}%</text>`;});
  data.forEach((d,i)=>{const x=i*gap+gap/2-bw/2,bh=(pcts[i]/maxP)*ch,y=ch-bh,fill=_rFill(d);bars+=`<rect x="${x}" y="${y}" width="${bw}" height="${bh}" fill="${fill}" fill-opacity="0.85" rx="3" onmouseenter="showTip(event,[['${d.bucket}','${pcts[i]}%','g'],['count','${d.n.toLocaleString()}','']])" onmouseleave="hideTip()" style="cursor:default"/>`;d.bucket.split(' ').forEach((w,wi)=>{lbls+=`<text x="${x+bw/2}" y="${ch+15+wi*11}" text-anchor="middle" font-size="8" fill="${c.axisText}" font-family="${SVG_FONT}">${w}</text>`;});});
  container.innerHTML=`<svg width="${W}" height="${H}" style="overflow:visible;display:block"><g transform="translate(${ml},${mt})">${lbls}${bars}${yl}</g></svg>`;
}
function filterWaterfall(container,data){
  if(!data||data.length<2){container.innerHTML=`<div style="font-size:10px;color:var(--text-muted);font-family:${SVG_FONT};padding:8px">Run model_stats.py to see filter impact.</div>`;return;}
  const c=C();
  const W=container.clientWidth||700,H=Math.max(180,data.length*36+44);
  const ml=198,mr=110,mt=12,mb=28,cw=W-ml-mr,ch=H-mt-mb;
  const evs=data.map(d=>d.ev);
  const minEv=Math.min(...evs)-0.1,maxEv=Math.max(...evs)+0.14,range=maxEv-minEv;
  const xS=v=>(v-minEv)/range*cw;
  const bh=Math.min(24,ch/data.length-6),gap=ch/data.length;
  let bars='',labels='',axis='';
  [-0.2,-0.1,0,0.2,0.4,0.6,0.8,1.0,1.2].forEach(xv=>{if(xv<minEv||xv>maxEv)return;const x=xS(xv),isZ=xv===0;axis+=`<line x1="${x}" y1="0" x2="${x}" y2="${ch}" stroke="${isZ?'rgba(148,163,184,.4)':c.gridLine}" stroke-width="${isZ?1.5:1}" stroke-dasharray="${isZ?'':'2,4'}"/>`;axis+=`<text x="${x}" y="${ch+20}" text-anchor="middle" font-size="8" fill="${c.axisText}" font-family="${SVG_FONT}">${(xv>=0?'+':'')+xv.toFixed(1)}R</text>`;});
  data.forEach((d,i)=>{
    const y=i*gap+gap/2-bh/2,x=xS(d.ev),isBase=i===0;
    const fill=isBase?c.barMid:d.ev>0.5?c.green:d.ev>0.2?c.amber:c.red;
    const x0=xS(0),barW=Math.abs(x-x0),barX=d.ev>=0?x0:x;
    const tipRows=[['','',''],['---','',''],['EV',`${(d.ev>=0?'+':'')+d.ev.toFixed(3)}R`,'g'],['Win Rate',`${(d.wr*100).toFixed(1)}%`,'g'],['PF',`${d.pf?.toFixed(2)||'—'}`,'a'],['n',`${d.n}`,''],['Removed',`−${d.removed||0}`,'r']];tipRows[0][0]=d.label.slice(0,30);
    bars+=`<rect x="${barX}" y="${y}" width="${Math.max(barW,1)}" height="${bh}" fill="${fill}" fill-opacity="${isBase?0.3:0.8}" rx="3" onmouseenter="showTip(event,${JSON.stringify(tipRows)})" onmouseleave="hideTip()" style="cursor:default"/>`;
    bars+=`<text x="${x+(d.ev>=0?5:-5)}" y="${y+bh/2+4}" text-anchor="${d.ev>=0?'start':'end'}" font-size="10" font-weight="600" fill="${fill}" font-family="${SVG_FONT}">${(d.ev>=0?'+':'')+d.ev.toFixed(3)}R</text>`;
    if(d.removed>0)bars+=`<text x="${cw+6}" y="${y+bh/2+4}" text-anchor="start" font-size="9" fill="${c.red}" font-family="${SVG_FONT}">−${d.removed.toLocaleString()}</text>`;
    labels+=`<text x="-8" y="${y+bh/2+4}" text-anchor="end" font-size="9" fill="${isBase?c.axisText:'var(--text-secondary)'}" font-family="${SVG_FONT}">${d.label.slice(0,26)}</text>`;
  });
  container.innerHTML=`<svg width="${W}" height="${H+10}" style="overflow:visible;display:block"><g transform="translate(${ml},${mt})">${axis}${bars}${labels}<text x="${cw+6}" y="-2" font-size="7" fill="${c.red}" font-family="${SVG_FONT}" letter-spacing="1">REMOVED</text></g></svg>`;
}
function dirCards(container,data){
  container.innerHTML=data.map(d=>`<div class="dir-card ${d.direction==='LONG'?'long':'short'}">
    <div class="dir-head" style="color:${d.direction==='LONG'?'var(--green)':'var(--red)'}">${d.direction==='LONG'?'↑ Long':'↓ Short'}</div>
    <div class="dir-stats">${[['Win Rate',pct(d.wr),d.wr>=0.5?'var(--green)':'var(--amber)'],['EV / Trade',evFmt(d.ev),d.ev>0?'var(--green)':'var(--red)'],['Profit Factor',pfFmt(d.pf),d.pf>=2?'var(--green)':d.pf>=1.5?'var(--amber)':'var(--red)'],['Setups',d.n.toLocaleString(),'var(--text-primary)']].map(([l,v,col])=>`<div><div class="ds-lbl">${l}</div><div class="ds-val" style="color:${col}">${v}</div></div>`).join('')}</div>
  </div>`).join('');
}

function _buildEquityPts(D){
  const rs=D?.risk_stats||{};
  const byYear=D?.by_year||[];
  const avgWinR=rs.avg_win_r, avgLossR=rs.avg_loss_r;
  if(!byYear.length||avgWinR==null||avgLossR==null) return null;
  let eq=EQ_ACCT, peak=eq;
  const pts=[{yr:'Start',eq,dd:0,pnl:null}];
  byYear.forEach(d=>{
    const pnl=d.wins*(avgWinR*EQ_RPT)+(d.n-d.wins)*(avgLossR*EQ_RPT);
    eq+=pnl;
    if(eq>peak) peak=eq;
    pts.push({yr:d.yr,eq,dd:(peak-eq)/peak*100,pnl});
  });
  return pts;
}

function renderEquityCurveFS(D){
  const container=document.getElementById('equity-curve-chart');
  if(!container) return;
  const an=document.getElementById('eq-acct-size');
  const rn2=document.getElementById('eq-risk-per-trade');
  if(an) an.textContent=EQ_ACCT.toLocaleString();
  if(rn2) rn2.textContent=EQ_RPT.toLocaleString();
  const pts=_buildEquityPts(D);
  if(!pts){
    container.innerHTML=`<div style="font-family:var(--font-data);font-size:11px;color:var(--text-muted);padding:8px">Load real model_stats.json to see the equity curve.</div>`;
    return;
  }
  _drawEquityCurveSVG(container,pts,EQ_ACCT);
}

function renderOverviewEquityCurve(D){
  const container=document.getElementById('overview-equity-curve-chart');
  if(!container) return;
  const an=document.getElementById('ov-eq-acct-size');
  const rn2=document.getElementById('ov-eq-risk-per-trade');
  if(an) an.textContent=EQ_ACCT.toLocaleString();
  if(rn2) rn2.textContent=EQ_RPT.toLocaleString();
  const pts=_buildEquityPts(D);
  if(!pts){
    container.innerHTML=`<div style="font-family:var(--font-data);font-size:11px;color:var(--text-muted);padding:8px">Load real model_stats.json to see the equity curve.</div>`;
    return;
  }
  _drawEquityCurveSVG(container,pts,EQ_ACCT);
}

function _drawEquityCurveSVG(container,pts,acctSize){
  const W=container.clientWidth||700,H=280,c=C();
  const ml=70,mr=24,mt=20,mb=36,cw=W-ml-mr,ch=H-mt-mb;
  const n=pts.length;
  const equities=pts.map(p=>p.eq);
  const minEq=Math.min(...equities,acctSize),maxEq=Math.max(...equities);
  const range=Math.max(maxEq-minEq,500);
  const pad=range*0.12;
  const yLo=minEq-pad, yHi=maxEq+pad, yRange=yHi-yLo;
  const yS=v=>((yHi-v)/yRange)*ch;
  const xS=i=>i/(n-1)*cw;

  // Line path
  const linePath=pts.map((p,i)=>`${i===0?'M':'L'}${xS(i).toFixed(1)},${yS(p.eq).toFixed(1)}`).join(' ');

  // Green fill above starting equity
  const yStart=yS(acctSize);
  const greenFill='M'+pts.map((p,i)=>`${xS(i).toFixed(1)},${Math.min(yS(p.eq),yStart).toFixed(1)}`).join(' L')+
    ` L${xS(n-1)},${yStart} L${xS(0)},${yStart} Z`;

  // Red fill below starting equity (underwater)
  const redFill='M'+pts.map((p,i)=>`${xS(i).toFixed(1)},${Math.max(yS(p.eq),yStart).toFixed(1)}`).join(' L')+
    ` L${xS(n-1)},${yStart} L${xS(0)},${yStart} Z`;

  // Drawdown shading (peak-to-trough)
  let pkEq=acctSize;
  const ddTop=pts.map((p,i)=>{if(p.eq>pkEq)pkEq=p.eq;return`${xS(i).toFixed(1)},${yS(pkEq).toFixed(1)}`;});
  const ddBot=[...pts].reverse().map((p,i)=>`${xS(n-1-i).toFixed(1)},${yS(p.eq).toFixed(1)}`);
  const ddPath='M'+ddTop.join(' L')+' '+ddBot.map((s,i)=>(i===0?'L':' L')+s).join('')+' Z';

  // Y-axis ticks
  function niceTick(v){const o=Math.pow(10,Math.floor(Math.log10(Math.max(v,1))));const r=v/o;return r<1.5?o:r<3?2*o:r<7?5*o:10*o;}
  function fmtEqLbl(v){const a=Math.abs(v);if(a>=10000)return'$'+(v/1000).toFixed(0)+'k';if(a>=1000)return'$'+(v/1000).toFixed(1)+'k';return'$'+Math.round(v);}
  const tickStep=niceTick(yRange/5);
  let grid='',yl='',t=Math.ceil(yLo/tickStep)*tickStep;
  while(t<=yHi){
    const y=yS(t);
    const isStart=Math.abs(t-acctSize)<tickStep*0.3;
    grid+=`<line x1="0" y1="${y.toFixed(1)}" x2="${cw}" y2="${y.toFixed(1)}" stroke="${isStart?c.beLine:c.gridLine}" stroke-width="${isStart?1.5:1}" stroke-dasharray="${isStart?'5,3':'2,4'}"/>`;
    yl+=`<text x="-6" y="${(y+4).toFixed(1)}" text-anchor="end" font-size="9" fill="${isStart?c.amber:c.axisText}" font-family="${SVG_FONT}">${fmtEqLbl(t)}</text>`;
    t+=tickStep;
  }

  // Dots + x-labels
  let dots='',xl='';
  pts.forEach((p,i)=>{
    const x=xS(i),y=yS(p.eq);
    const col=p.eq>=acctSize?c.green:c.red;
    const isFinal=i===n-1;
    const tipData=[
      [String(p.yr), '$'+Math.round(p.eq).toLocaleString(), p.eq>=acctSize?'g':'r'],
      ['P&L', p.pnl!=null?(p.pnl>=0?'+$':'-$')+Math.abs(Math.round(p.pnl)).toLocaleString():'Start', p.pnl==null?'':p.pnl>=0?'g':'r'],
      ['DD', '-'+p.dd.toFixed(1)+'%', p.dd>0?'r':''],
    ];
    dots+=`<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${isFinal?4.5:3.5}" fill="${col}" stroke="${isDark?'#111827':'#fff'}" stroke-width="2" onmouseenter="showTip(event,${JSON.stringify(tipData)})" onmouseleave="hideTip()" style="cursor:default"/>`;
    if(isFinal){
      const totalPnl=p.eq-acctSize;
      const lbl=(totalPnl>=0?'+$':'-$')+Math.abs(Math.round(totalPnl)).toLocaleString();
      dots+=`<text x="${(x-6).toFixed(1)}" y="${(y-10).toFixed(1)}" text-anchor="end" font-size="10" font-weight="700" fill="${col}" font-family="${SVG_FONT}">${lbl}</text>`;
    }
    xl+=`<text x="${x.toFixed(1)}" y="${(ch+22).toFixed(1)}" text-anchor="middle" font-size="${p.yr==='Start'?8:9}" fill="${c.axisText}" font-family="${SVG_FONT}">${p.yr}</text>`;
  });

  const gId='eqfs'+Math.random().toString(36).slice(2);
  const ddGid='ddfs'+Math.random().toString(36).slice(2);
  container.innerHTML=`<svg width="${W}" height="${H}" style="overflow:visible;display:block">
    <defs>
      <linearGradient id="${gId}" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="${c.green}" stop-opacity="0.25"/><stop offset="100%" stop-color="${c.green}" stop-opacity="0.03"/></linearGradient>
      <linearGradient id="${ddGid}" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="${c.red}" stop-opacity="0.28"/><stop offset="100%" stop-color="${c.red}" stop-opacity="0.05"/></linearGradient>
    </defs>
    <g transform="translate(${ml},${mt})">
      ${grid}
      <path d="${ddPath}" fill="url(#${ddGid})"/>
      <path d="${greenFill}" fill="url(#${gId})"/>
      <path d="${redFill}" fill="${c.red}" fill-opacity="0.06"/>
      <path d="${linePath}" fill="none" stroke="${c.green}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>
      ${dots}${yl}${xl}
    </g>
  </svg>`;
}
function _heatColor(t) {
  if (t <= 0) return null;
  const stops = [[0,[17,24,39]],[0.25,[67,20,99]],[0.55,[185,28,28]],[0.8,[194,65,12]],[1,[253,224,71]]];
  let s0=stops[0],s1=stops[stops.length-1];
  for(let i=0;i<stops.length-1;i++){if(t>=stops[i][0]&&t<=stops[i+1][0]){s0=stops[i];s1=stops[i+1];break;}}
  const f=s0[0]===s1[0]?1:(t-s0[0])/(s1[0]-s0[0]);
  const lr=(a,b)=>Math.round(a+(b-a)*f);
  return `rgb(${lr(s0[1][0],s1[1][0])},${lr(s0[1][1],s1[1][1])},${lr(s0[1][2],s1[1][2])})`;
}

function _drawMAEProbCurve(canvas, sweep, dist) {
  if (!canvas || !sweep || sweep.length < 2) return;
  const W=canvas.offsetWidth||600, H=140;
  canvas.width=W*devicePixelRatio; canvas.height=H*devicePixelRatio;
  const ctx=canvas.getContext('2d'); ctx.scale(devicePixelRatio,devicePixelRatio);
  const cc=C();
  const padL=40,padR=14,padT=18,padB=28,cW=W-padL-padR,cH=H-padT-padB;
  const data=[...sweep].sort((a,b)=>a.threshold-b.threshold);
  const xMax=data[data.length-1].threshold*1.08;
  const xS=v=>padL+(v/xMax)*cW, yS=v=>padT+cH*(1-v);
  ctx.fillStyle=cc.bgCard; ctx.fillRect(0,0,W,H);
  ctx.strokeStyle=cc.gridLine; ctx.lineWidth=1;
  [.25,.5,.75,1].forEach(f=>{const y=padT+cH*(1-f);ctx.beginPath();ctx.moveTo(padL,y);ctx.lineTo(padL+cW,y);ctx.stroke();});
  // 0.5 ref
  ctx.strokeStyle='rgba(148,163,184,.15)';ctx.setLineDash([3,3]);
  ctx.beginPath();ctx.moveTo(padL,yS(.5));ctx.lineTo(padL+cW,yS(.5));ctx.stroke();ctx.setLineDash([]);
  const line=(pts,color,dash=[],lw=1.8)=>{
    if(pts.length<2)return;
    ctx.strokeStyle=color;ctx.lineWidth=lw;ctx.setLineDash(dash);
    ctx.beginPath();ctx.moveTo(pts[0][0],pts[0][1]);
    pts.slice(1).forEach(p=>ctx.lineTo(p[0],p[1]));
    ctx.stroke();ctx.setLineDash([]);
  };
  line(data.map(d=>[xS(d.threshold),yS(1-d.exceed_pct/100)]),'#60a5fa',[4,2]);
  line(data.map(d=>[xS(d.threshold),yS(d.p_recovered)]),'#fb923c');
  line(data.map(d=>[xS(d.threshold),yS(d.p_ko)]),'#f87171');
  ctx.fillStyle=cc.axisText;ctx.font='9px JetBrains Mono,monospace';ctx.textAlign='center';
  [0,.25,.5,.75,1].forEach(f=>ctx.fillText((xMax*f).toFixed(3)+'%',padL+f*cW,padT+cH+16));
  ctx.textAlign='right';
  [0,.25,.5,.75,1].forEach(f=>ctx.fillText((f*100).toFixed(0)+'%',padL-4,yS(f)+4));
  // legend
  [[padL+4,'#60a5fa','P(MAE≤X) CDF',[4,2]],[padL+116,'#fb923c','P(false stop|≥X)'],[padL+236,'#f87171','P(genuine|≥X)']].forEach(([x,c,lbl,dash=[]])=>{
    ctx.strokeStyle=c;ctx.lineWidth=1.5;ctx.setLineDash(dash);
    ctx.beginPath();ctx.moveTo(x,padT+6);ctx.lineTo(x+18,padT+6);ctx.stroke();ctx.setLineDash([]);
    ctx.fillStyle=cc.axisText;ctx.textAlign='left';ctx.fillText(lbl,x+21,padT+10);
  });
}

function _drawMFEProbCurve(canvas, triggers, dist) {
  if (!canvas || !triggers || triggers.length < 2) return;
  const W=canvas.offsetWidth||600, H=140;
  canvas.width=W*devicePixelRatio; canvas.height=H*devicePixelRatio;
  const ctx=canvas.getContext('2d'); ctx.scale(devicePixelRatio,devicePixelRatio);
  const cc=C();
  const padL=40,padR=14,padT=18,padB=28,cW=W-padL-padR,cH=H-padT-padB;
  const data=[...triggers].sort((a,b)=>a.trigger_pct-b.trigger_pct);
  const xMax=data[data.length-1].trigger_pct*1.08;
  const ptq=dist.ptq_level;
  const xS=v=>padL+(v/xMax)*cW, yS=v=>padT+cH*(1-v);
  ctx.fillStyle=cc.bgCard; ctx.fillRect(0,0,W,H);
  ctx.strokeStyle=cc.gridLine; ctx.lineWidth=1;
  [.25,.5,.75,1].forEach(f=>{const y=padT+cH*(1-f);ctx.beginPath();ctx.moveTo(padL,y);ctx.lineTo(padL+cW,y);ctx.stroke();});
  const line=(pts,color,dash=[],lw=1.8)=>{
    if(pts.length<2)return;
    ctx.strokeStyle=color;ctx.lineWidth=lw;ctx.setLineDash(dash);
    ctx.beginPath();ctx.moveTo(pts[0][0],pts[0][1]);
    pts.slice(1).forEach(p=>ctx.lineTo(p[0],p[1]));
    ctx.stroke();ctx.setLineDash([]);
  };
  line(data.map(d=>[xS(d.trigger_pct),yS(d.reach_rate/100)]),'#10b981');
  line(data.map(d=>[xS(d.trigger_pct),yS(d.p_pos_given)]),'#fbbf24');
  if(ptq!=null){
    const px=xS(ptq);
    ctx.strokeStyle='rgba(16,185,129,.6)';ctx.lineWidth=1.5;ctx.setLineDash([4,3]);
    ctx.beginPath();ctx.moveTo(px,padT);ctx.lineTo(px,padT+cH);ctx.stroke();ctx.setLineDash([]);
    ctx.fillStyle='#10b981';ctx.font='bold 9px JetBrains Mono,monospace';ctx.textAlign='center';
    ctx.fillText('PTQ',px,padT+9);
  }
  ctx.fillStyle=cc.axisText;ctx.font='9px JetBrains Mono,monospace';ctx.textAlign='center';
  [0,.25,.5,.75,1].forEach(f=>ctx.fillText((xMax*f).toFixed(3)+'%',padL+f*cW,padT+cH+16));
  ctx.textAlign='right';
  [0,.25,.5,.75,1].forEach(f=>ctx.fillText((f*100).toFixed(0)+'%',padL-4,yS(f)+4));
  [[padL+4,'#10b981','P(MFE≥X) reach'],[padL+120,'#fbbf24','P(+exit | MFE≥X)']].forEach(([x,c,lbl])=>{
    ctx.strokeStyle=c;ctx.lineWidth=1.5;
    ctx.beginPath();ctx.moveTo(x,padT+6);ctx.lineTo(x+18,padT+6);ctx.stroke();
    ctx.fillStyle=cc.axisText;ctx.textAlign='left';ctx.fillText(lbl,x+21,padT+10);
  });
}

function _drawExcursionHeatmap(canvas, hm, median, axisLabel) {
  // hm = D.mae_heatmap or D.mfe_heatmap — {grid (5×n_bins), val_max, labels, n}
  if (!canvas) return;
  const W=canvas.offsetWidth||600, H=canvas.height||160;
  canvas.width=W*devicePixelRatio; canvas.height=H*devicePixelRatio;
  const ctx=canvas.getContext('2d'); ctx.scale(devicePixelRatio,devicePixelRatio);
  const cc=C();
  const padL=36,padR=24,padT=10,padB=30,cW=W-padL-padR,cH=H-padT-padB;
  ctx.fillStyle=cc.bgCard; ctx.fillRect(0,0,W,H);
  if(!hm||!hm.grid||hm.grid.length===0||hm.n<5){
    ctx.fillStyle=cc.axisText;ctx.font='11px JetBrains Mono,monospace';ctx.textAlign='center';
    ctx.fillText('No data — regenerate model_stats.json',W/2,H/2);
    return;
  }
  const grid=hm.grid, valMax=hm.val_max, labels=hm.labels||['Mon','Tue','Wed','Thu','Fri'];
  const nRows=grid.length, nCols=grid[0].length;
  const maxCount=Math.max(...grid.flat(),1);
  const cellW=cW/nCols, cellH=cH/nRows;
  for(let yi=0;yi<nRows;yi++){
    for(let xi=0;xi<nCols;xi++){
      const c=grid[yi][xi];
      if(c===0){ctx.fillStyle=isDark?'rgba(17,24,39,0.5)':'rgba(241,245,249,0.5)';ctx.fillRect(padL+xi*cellW,padT+yi*cellH,cellW,cellH);continue;}
      const col=_heatColor(c/maxCount);
      if(col){ctx.fillStyle=col;ctx.fillRect(padL+xi*cellW,padT+yi*cellH,cellW,cellH);}
    }
  }
  ctx.strokeStyle=cc.gridLine;ctx.lineWidth=0.5;ctx.strokeRect(padL,padT,cW,cH);
  // Median line
  if(median!=null&&median<=valMax){
    const mx=padL+(median/valMax)*cW;
    ctx.strokeStyle='rgba(251,146,60,.8)';ctx.lineWidth=1.5;ctx.setLineDash([3,3]);
    ctx.beginPath();ctx.moveTo(mx,padT);ctx.lineTo(mx,padT+cH);ctx.stroke();ctx.setLineDash([]);
    ctx.fillStyle='#fb923c';ctx.font='9px JetBrains Mono,monospace';ctx.textAlign='left';ctx.fillText('Med',mx+3,padT+10);
  }
  // Row labels (DOW)
  ctx.fillStyle=cc.axisText;ctx.font='9px JetBrains Mono,monospace';ctx.textAlign='right';
  labels.forEach((lbl,i)=>ctx.fillText(lbl,padL-4,padT+i*cellH+cellH/2+4));
  // X-axis labels
  ctx.textAlign='center';
  [0,.25,.5,.75,1].forEach(f=>ctx.fillText((valMax*f).toFixed(3)+'%',padL+f*cW,padT+cH+14));
  ctx.fillText(`${axisLabel}  (${hm.n.toLocaleString()} trades)`,padL+cW/2,padT+cH+26);
  // Color scale
  const bx=padL+cW+4,bw=8;
  for(let i=0;i<100;i++){const c=_heatColor((i+1)/100);if(c){ctx.fillStyle=c;ctx.fillRect(bx,padT+(99-i)/100*cH,bw,cH/100+1);}}
  ctx.fillStyle=cc.axisText;ctx.font='8px JetBrains Mono,monospace';ctx.textAlign='left';
  ctx.fillText('Hi',bx,padT+8);ctx.fillText('Lo',bx,padT+cH+3);
}

function drawSetupScene(cvs, dir, slPct, tpPct){
  if(!cvs) return;
  slPct = slPct||0.26; tpPct = tpPct||0.18;
  const DPR = window.devicePixelRatio||1;
  const W = cvs.offsetWidth, H = 370;
  cvs.width = W*DPR; cvs.height = H*DPR; cvs.style.height = H+'px';
  const ctx = cvs.getContext('2d');
  ctx.scale(DPR,DPR);

  const bg    = isDark ? '#111827' : '#ffffff';
  const teal  = '#10b981';
  const red   = '#ef4444';
  const gold  = '#f59e0b';
  const blue  = '#3b82f6';
  const orange= '#fb923c';
  const muted = isDark ? '#4a6480' : '#94a3b8';
  const border= isDark ? '#1e2d42' : '#e2e8f0';
  const textBg= isDark ? 'rgba(17,24,39,0.92)' : 'rgba(255,255,255,0.92)';

  ctx.fillStyle = bg; ctx.fillRect(0,0,W,H);

  const PAD={t:52,b:46,l:36,r:172};
  const cH=H-PAD.t-PAD.b;
  const py=p=>PAD.t+cH*(1-p/100);
  const CW=10, GAP=4, slot=CW+GAP;

  const SL_UNITS = 20;
  const TP_UNITS = SL_UNITS * (tpPct / slPct);
  const rrStr    = (tpPct/slPct).toFixed(2)+':1';
  const slStr    = slPct.toFixed(2)+'%';
  const tpStr    = tpPct.toFixed(2)+'%';

  function hl(y,x1,x2,col,dash=[],lw=1){
    ctx.save();ctx.strokeStyle=col;ctx.lineWidth=lw;ctx.setLineDash(dash);
    ctx.beginPath();ctx.moveTo(x1,y);ctx.lineTo(x2,y);ctx.stroke();
    ctx.setLineDash([]);ctx.restore();
  }
  function vl(x,y1,y2,col,dash=[]){
    ctx.save();ctx.strokeStyle=col;ctx.lineWidth=1;ctx.setLineDash(dash);
    ctx.beginPath();ctx.moveTo(x,y1);ctx.lineTo(x,y2);ctx.stroke();
    ctx.setLineDash([]);ctx.restore();
  }
  function lbl(s,x,y,col,sz=8,align='left',bold=false){
    ctx.save();ctx.fillStyle=col;ctx.textAlign=align;
    ctx.font=`${bold?'600':'400'} ${sz}px "IBM Plex Mono",monospace`;
    ctx.fillText(s,x,y);ctx.restore();
  }
  function cdl(x,o,h,l,c,w){
    const bull=c>=o,col=bull?teal:red,mid=x+w/2;
    ctx.strokeStyle=col;ctx.lineWidth=1.5;
    ctx.beginPath();ctx.moveTo(mid,h);ctx.lineTo(mid,Math.min(o,c));ctx.stroke();
    ctx.beginPath();ctx.moveTo(mid,Math.max(o,c));ctx.lineTo(mid,l);ctx.stroke();
    const bt=Math.min(o,c),bh=Math.max(Math.abs(c-o),2);
    if(bull){ctx.strokeRect(x,bt,w,bh);ctx.fillStyle=bg;ctx.fillRect(x+1.5,bt+1.5,w-3,bh-3);ctx.strokeRect(x,bt,w,bh);}
    else{ctx.fillStyle=red;ctx.fillRect(x,bt,w,bh);}
  }
  function ruler(x,y1,y2,col,topLbl,lw=1.5){
    const mid=(y1+y2)/2;
    ctx.save();ctx.strokeStyle=col;ctx.lineWidth=lw;
    ctx.beginPath();ctx.moveTo(x+4,y1);ctx.lineTo(x,y1);ctx.lineTo(x,y2);ctx.moveTo(x,y2);ctx.lineTo(x+4,y2);ctx.stroke();
    ctx.restore();
    lbl(topLbl,x+7,mid+3,col,7,'left',true);
  }
  function badge(n,cx,cy,col){
    ctx.save();ctx.fillStyle=col;ctx.beginPath();ctx.arc(cx,cy,7,0,Math.PI*2);ctx.fill();
    ctx.font='700 7px "IBM Plex Mono",monospace';ctx.fillStyle=bg;ctx.textAlign='center';
    ctx.fillText(n,cx,cy+2.5);ctx.restore();
  }
  function chip(text,x,y,bgcol,textcol){
    ctx.save();ctx.font='600 7px "IBM Plex Mono",monospace';
    const tw=ctx.measureText(text).width;
    ctx.fillStyle=bgcol;ctx.globalAlpha=0.15;ctx.fillRect(x-4,y-9,tw+10,13);
    ctx.globalAlpha=1;ctx.fillStyle=textcol;ctx.textAlign='left';ctx.fillText(text,x,y);
    ctx.restore();
  }

  if(dir==='bull'){
    const EP_P = 46;
    const STOP_P = EP_P - SL_UNITS;
    const TP_P   = EP_P + TP_UNITS;
    const SWP_P  = STOP_P - 12;
    const PHL_P  = STOP_P - 5;
    const PHH_P  = EP_P + SL_UNITS*1.7;

    const stopY=py(STOP_P), swpY=py(SWP_P), phlY=py(PHL_P), phhY=py(PHH_P);
    const entryY=py(EP_P), targetY=py(TP_P);
    const cisdLow=py(EP_P-3);

    const PHW=CW*3;
    const xPH=PAD.l+GAP, xQ1=xPH+PHW+GAP*3, xRet=xQ1+6*slot, xCisd=xRet+3*slot, xEnt=xCisd+2*slot, xEnd=xEnt+4*slot;
    const lineEnd=xEnd+4;

    // Phase bands
    [[xPH,PHW+GAP*2,'rgba(59,130,246,0.06)','① PREV HTF'],
     [xQ1,6*slot,'rgba(239,68,68,0.06)','② Q1 SWEEP'],
     [xRet,3*slot,'rgba(16,185,129,0.04)','③ RETURN'],
     [xCisd,2*slot,'rgba(251,146,60,0.07)','④ CISD'],
     [xEnt,4*slot,'rgba(245,158,11,0.05)','⑤ TRADE'],
    ].forEach(([x,w,col,lbl_])=>{
      ctx.fillStyle=col;ctx.fillRect(x,PAD.t-12,w,cH+20);
      lbl(lbl_,x+3,PAD.t-14,muted,6.5);
    });

    // Risk/reward zones in trade phase
    const tzX=xEnt-4, tzW=lineEnd-xEnt+8;
    ctx.save();
    ctx.fillStyle='rgba(239,68,68,0.10)';ctx.fillRect(tzX,stopY,tzW,entryY-stopY);
    ctx.fillStyle='rgba(16,185,129,0.13)';ctx.fillRect(tzX,targetY,tzW,entryY-targetY);
    ctx.restore();

    // Key price lines
    hl(targetY, xPH-4, lineEnd, teal,   [], 2.5);
    hl(entryY,  xPH-4, lineEnd, gold,   [4,3], 2);
    hl(stopY,   xPH-4, lineEnd, red,    [], 2.5);
    hl(phlY,    xPH-4, lineEnd, orange, [6,3], 1.5);
    hl(swpY,    xPH-4, lineEnd, red,    [2,5], 1);
    hl(phhY,    xPH-4, lineEnd, muted,  [4,4], 0.7);
    hl(cisdLow, xPH-4, xCisd+2*slot+4, blue, [5,3], 1);

    // HTF prior candle
    const phMid=xPH+PHW/2;
    ctx.strokeStyle=red;ctx.lineWidth=1.5;
    ctx.beginPath();ctx.moveTo(phMid,phhY);ctx.lineTo(phMid,py(EP_P+SL_UNITS*2));ctx.stroke();
    ctx.beginPath();ctx.moveTo(phMid,py(EP_P-SL_UNITS*0.3));ctx.lineTo(phMid,phlY);ctx.stroke();
    ctx.fillStyle=red;ctx.fillRect(xPH,py(EP_P+SL_UNITS*2),PHW,Math.max(py(EP_P-SL_UNITS*0.3)-py(EP_P+SL_UNITS*2),2));
    lbl('HTF',phMid,py(EP_P+SL_UNITS*0.7),bg,7,'center',true);
    vl(xQ1-GAP,PAD.t-12,PAD.t+cH+8,border,[3,3]);

    // Sweep candles (going down)
    let x=xQ1;
    const s0=EP_P+2;
    cdl(x,py(s0),py(s0+3),py(s0-7),py(s0-5),CW);x+=slot;
    cdl(x,py(s0-5),py(s0-3),py(s0-14),py(s0-12),CW);
    ctx.save();ctx.fillStyle=orange;
    ctx.beginPath();ctx.moveTo(x+CW/2-3,phlY+3);ctx.lineTo(x+CW/2,phlY+7);ctx.lineTo(x+CW/2+3,phlY+3);ctx.fill();
    ctx.restore();
    chip('SWEPT',x+CW/2-12,phlY+18,orange,orange);
    x+=slot;
    cdl(x,py(s0-12),py(s0-10),py(s0-20),py(s0-17),CW);x+=slot;
    cdl(x,py(s0-17),py(s0-15),py(SWP_P+3),py(SWP_P+1),CW);
    ctx.save();ctx.fillStyle=red;
    ctx.beginPath();ctx.moveTo(x+CW/2-3,swpY-4);ctx.lineTo(x+CW/2,swpY-1);ctx.lineTo(x+CW/2+3,swpY-4);ctx.fill();
    ctx.restore();
    chip('EXTREME',x+CW/2-14,swpY+11,red,red);
    x+=slot;
    cdl(x,py(SWP_P+1),py(SWP_P+11),py(SWP_P),py(SWP_P+9),CW);x+=slot;
    vl(xRet-GAP/2,PAD.t-12,PAD.t+cH+8,border,[3,3]);

    // Return candles (going up, back above prior low)
    x=xRet;
    cdl(x,py(SWP_P+9),py(SWP_P+19),py(SWP_P+6),py(SWP_P+17),CW);x+=slot;
    cdl(x,py(SWP_P+17),py(SWP_P+26),py(SWP_P+13),py(SWP_P+23),CW);x+=slot;
    cdl(x,py(SWP_P+23),py(EP_P-2),py(SWP_P+20),py(EP_P-3),CW);
    chip('BACK ABOVE',x+CW/2-18,phlY-14,orange,orange);
    chip('PREV LOW',x+CW/2-12,phlY-5,orange,orange);
    x+=slot;
    vl(xCisd-GAP/2,PAD.t-12,PAD.t+cH+8,border,[3,3]);

    // CISD candles
    x=xCisd;
    cdl(x,py(EP_P-5),py(EP_P-2),py(EP_P-8),py(EP_P-6),CW);x+=slot;
    cdl(x,py(EP_P-5),py(EP_P-1),py(EP_P-7),py(EP_P-2),CW);
    ctx.save();ctx.strokeStyle=blue;ctx.lineWidth=1.5;ctx.setLineDash([3,2]);
    ctx.beginPath();ctx.moveTo(x+CW/2,cisdLow);ctx.lineTo(x+CW/2,py(EP_P-2));ctx.stroke();
    ctx.setLineDash([]);ctx.restore();
    chip('CISD ↑',x+CW/2-14,cisdLow-6,blue,blue);
    x+=slot;
    vl(xEnt-GAP/2,PAD.t-12,PAD.t+cH+8,border,[3,3]);

    // Trade phase — entry arrow + 4 candles heading to target
    x=xEnt;
    ctx.save();ctx.fillStyle=gold;
    ctx.beginPath();ctx.moveTo(x-4,entryY-3);ctx.lineTo(x+2,entryY);ctx.lineTo(x-4,entryY+3);ctx.fill();
    ctx.restore();
    cdl(x,entryY,py(EP_P+2),py(EP_P-1),py(EP_P+1.5),CW);x+=slot;
    cdl(x,py(EP_P+1.5),py(EP_P+4),py(EP_P+0.5),py(EP_P+3.5),CW);x+=slot;
    cdl(x,py(EP_P+3.5),py(EP_P+6.5),py(EP_P+2.5),py(EP_P+5.5),CW);x+=slot;
    cdl(x,py(EP_P+5.5),py(TP_P+0.5),py(EP_P+4),py(TP_P-0.5),CW);
    // TP hit dot
    ctx.save();ctx.fillStyle=teal;ctx.beginPath();ctx.arc(x+CW/2,targetY,5,0,Math.PI*2);ctx.fill();
    ctx.fillStyle=bg;ctx.beginPath();ctx.arc(x+CW/2,targetY,2.5,0,Math.PI*2);ctx.fill();
    ctx.restore();

    // Right-side labels
    const rx=lineEnd+10;
    lbl('TARGET',rx,targetY-4,teal,8,'left',true);
    lbl(`+${tpStr} from entry`,rx,targetY+8,muted,7,'left');
    lbl('ENTRY',rx,entryY-4,gold,8,'left',true);
    lbl('(next candle open)',rx,entryY+8,muted,7,'left');
    lbl('STOP',rx,stopY+8,red,8,'left',true);
    lbl(`-${slStr} from entry`,rx,stopY+19,muted,7,'left');
    lbl('SWEEP EXTREME',rx,swpY+5,isDark?'#3d5266':'#9ca3af',7,'left');
    lbl('(not the stop)',rx,swpY+14,muted,6,'left');

    // Rulers: TP bracket (green) and SL bracket (red)
    ruler(rx-8,targetY,entryY,teal,`TP ${tpStr}`);
    ruler(rx-8,entryY,stopY,red,`SL ${slStr}`);

    // R:R chip in top-right
    const rrText=`R:R  ${rrStr}`;
    ctx.save();ctx.font='600 8px "IBM Plex Mono",monospace';
    const rrW=ctx.measureText(rrText).width+16,rrH=18,rrX=W-rrW-8,rrY=PAD.t-30;
    ctx.fillStyle=isDark?'rgba(30,45,66,0.95)':'rgba(241,245,249,0.95)';
    ctx.strokeStyle=border;ctx.lineWidth=1;
    ctx.fillRect(rrX,rrY,rrW,rrH);ctx.strokeRect(rrX,rrY,rrW,rrH);
    ctx.fillStyle=gold;ctx.textAlign='center';
    ctx.fillText(rrText,rrX+rrW/2,rrY+12);
    ctx.restore();

    const bY=PAD.t-28;
    badge('1',xPH+PHW/2,bY,blue);badge('2',xQ1+3*slot,bY,red);badge('3',xRet+1.5*slot,bY,teal);
    badge('4',xCisd+slot,bY,orange);badge('5',xEnt+2*slot,bY,gold);

  } else {
    // ── BEAR setup (mirror) ──────────────────────────────────────────────────
    const EP_P = 54;
    const STOP_P = EP_P + SL_UNITS;
    const TP_P   = EP_P - TP_UNITS;
    const SWP_P  = STOP_P + 12;
    const PHH_P  = STOP_P + 5;
    const PHL_P  = EP_P - SL_UNITS*1.7;

    const stopY=py(STOP_P), swpY=py(SWP_P), phhY=py(PHH_P), phlY=py(PHL_P);
    const entryY=py(EP_P), targetY=py(TP_P);
    const cisdHigh=py(EP_P+3);

    const PHW=CW*3;
    const xPH=PAD.l+GAP, xQ1=xPH+PHW+GAP*3, xRet=xQ1+6*slot, xCisd=xRet+3*slot, xEnt=xCisd+2*slot, xEnd=xEnt+4*slot;
    const lineEnd=xEnd+4;

    [[xPH,PHW+GAP*2,'rgba(59,130,246,0.06)','① PREV HTF'],
     [xQ1,6*slot,'rgba(239,68,68,0.06)','② Q1 SWEEP'],
     [xRet,3*slot,'rgba(16,185,129,0.04)','③ RETURN'],
     [xCisd,2*slot,'rgba(251,146,60,0.07)','④ CISD'],
     [xEnt,4*slot,'rgba(245,158,11,0.05)','⑤ TRADE'],
    ].forEach(([x,w,col,lbl_])=>{
      ctx.fillStyle=col;ctx.fillRect(x,PAD.t-12,w,cH+20);
      lbl(lbl_,x+3,PAD.t-14,muted,6.5);
    });

    // Risk/reward zones in trade phase
    const tzX=xEnt-4, tzW=lineEnd-xEnt+8;
    ctx.save();
    ctx.fillStyle='rgba(239,68,68,0.10)';ctx.fillRect(tzX,entryY,tzW,stopY-entryY);
    ctx.fillStyle='rgba(16,185,129,0.13)';ctx.fillRect(tzX,targetY,tzW,entryY-targetY);
    ctx.restore();

    hl(stopY,   xPH-4, lineEnd, red,    [], 2.5);
    hl(phhY,    xPH-4, lineEnd, orange, [6,3], 1.5);
    hl(swpY,    xPH-4, lineEnd, red,    [2,5], 1);
    hl(entryY,  xPH-4, lineEnd, gold,   [4,3], 2);
    hl(phlY,    xPH-4, lineEnd, muted,  [4,4], 0.7);
    hl(targetY, xPH-4, lineEnd, teal,   [], 2.5);
    hl(cisdHigh,xPH-4, xCisd+2*slot+4, blue, [5,3], 1);

    const phMid=xPH+PHW/2;
    ctx.strokeStyle=teal;ctx.lineWidth=1.5;
    ctx.beginPath();ctx.moveTo(phMid,phhY);ctx.lineTo(phMid,py(EP_P-SL_UNITS*2));ctx.stroke();
    ctx.beginPath();ctx.moveTo(phMid,py(EP_P+SL_UNITS*0.3));ctx.lineTo(phMid,phlY);ctx.stroke();
    ctx.strokeRect(xPH,py(EP_P-SL_UNITS*2),PHW,Math.max(py(EP_P+SL_UNITS*0.3)-py(EP_P-SL_UNITS*2),2));
    ctx.fillStyle=bg;ctx.fillRect(xPH+1.5,py(EP_P-SL_UNITS*2)+1.5,PHW-3,Math.max(py(EP_P+SL_UNITS*0.3)-py(EP_P-SL_UNITS*2),2)-3);
    ctx.strokeRect(xPH,py(EP_P-SL_UNITS*2),PHW,Math.max(py(EP_P+SL_UNITS*0.3)-py(EP_P-SL_UNITS*2),2));
    lbl('HTF',phMid,py(EP_P-SL_UNITS*0.7),teal,7,'center',true);
    vl(xQ1-GAP,PAD.t-12,PAD.t+cH+8,border,[3,3]);

    let x=xQ1;
    const s0=EP_P-2;
    cdl(x,py(s0),py(s0+7),py(s0-3),py(s0+5),CW);x+=slot;
    cdl(x,py(s0+5),py(s0+14),py(s0+3),py(s0+12),CW);
    ctx.save();ctx.fillStyle=orange;
    ctx.beginPath();ctx.moveTo(x+CW/2-3,phhY-3);ctx.lineTo(x+CW/2,phhY-7);ctx.lineTo(x+CW/2+3,phhY-3);ctx.fill();
    ctx.restore();
    chip('SWEPT',x+CW/2-12,phhY-14,orange,orange);
    x+=slot;
    cdl(x,py(s0+12),py(s0+20),py(s0+10),py(s0+18),CW);x+=slot;
    cdl(x,py(s0+18),py(SWP_P-2),py(s0+16),py(SWP_P-3),CW);
    ctx.save();ctx.fillStyle=red;
    ctx.beginPath();ctx.moveTo(x+CW/2-3,swpY+4);ctx.lineTo(x+CW/2,swpY+1);ctx.lineTo(x+CW/2+3,swpY+4);ctx.fill();
    ctx.restore();
    chip('EXTREME',x+CW/2-14,swpY+14,red,red);
    x+=slot;
    cdl(x,py(SWP_P-3),py(SWP_P-9),py(SWP_P),py(SWP_P-10),CW);x+=slot;
    vl(xRet-GAP/2,PAD.t-12,PAD.t+cH+8,border,[3,3]);

    x=xRet;
    cdl(x,py(SWP_P-10),py(SWP_P-7),py(SWP_P-19),py(SWP_P-17),CW);x+=slot;
    cdl(x,py(SWP_P-17),py(SWP_P-14),py(SWP_P-25),py(SWP_P-23),CW);x+=slot;
    cdl(x,py(SWP_P-23),py(EP_P+2),py(SWP_P-27),py(EP_P+3),CW);
    chip('BACK BELOW',x+CW/2-18,phhY+8,orange,orange);
    chip('PREV HIGH',x+CW/2-14,phhY+17,orange,orange);
    x+=slot;
    vl(xCisd-GAP/2,PAD.t-12,PAD.t+cH+8,border,[3,3]);

    x=xCisd;
    cdl(x,py(EP_P+5),py(EP_P+8),py(EP_P+2),py(EP_P+6),CW);x+=slot;
    cdl(x,py(EP_P+5),py(EP_P+2),py(EP_P+1),py(EP_P+2),CW);
    ctx.save();ctx.strokeStyle=blue;ctx.lineWidth=1.5;ctx.setLineDash([3,2]);
    ctx.beginPath();ctx.moveTo(x+CW/2,cisdHigh);ctx.lineTo(x+CW/2,py(EP_P+2));ctx.stroke();
    ctx.setLineDash([]);ctx.restore();
    chip('CISD ↓',x+CW/2-14,cisdHigh+14,blue,blue);
    x+=slot;
    vl(xEnt-GAP/2,PAD.t-12,PAD.t+cH+8,border,[3,3]);

    x=xEnt;
    ctx.save();ctx.fillStyle=gold;
    ctx.beginPath();ctx.moveTo(x-4,entryY-3);ctx.lineTo(x+2,entryY);ctx.lineTo(x-4,entryY+3);ctx.fill();
    ctx.restore();
    cdl(x,entryY,py(EP_P+1),py(EP_P-2),py(EP_P-1.5),CW);x+=slot;
    cdl(x,py(EP_P-1.5),py(EP_P-0.5),py(EP_P-4),py(EP_P-3.5),CW);x+=slot;
    cdl(x,py(EP_P-3.5),py(EP_P-2.5),py(EP_P-6.5),py(EP_P-5.5),CW);x+=slot;
    cdl(x,py(EP_P-5.5),py(EP_P-4),py(TP_P-0.5),py(TP_P+0.5),CW);
    ctx.save();ctx.fillStyle=teal;ctx.beginPath();ctx.arc(x+CW/2,targetY,5,0,Math.PI*2);ctx.fill();
    ctx.fillStyle=bg;ctx.beginPath();ctx.arc(x+CW/2,targetY,2.5,0,Math.PI*2);ctx.fill();
    ctx.restore();

    const rx=lineEnd+10;
    lbl('STOP',rx,stopY-4,red,8,'left',true);
    lbl(`+${slStr} from entry`,rx,stopY+7,muted,7,'left');
    lbl('SWEEP EXTREME',rx,swpY-4,isDark?'#3d5266':'#9ca3af',7,'left');
    lbl('(not the stop)',rx,swpY+6,muted,6,'left');
    lbl('ENTRY',rx,entryY-4,gold,8,'left',true);
    lbl('(next candle open)',rx,entryY+7,muted,7,'left');
    lbl('TARGET',rx,targetY-4,teal,8,'left',true);
    lbl(`-${tpStr} from entry`,rx,targetY+7,muted,7,'left');

    ruler(rx-8,stopY,entryY,red,`SL ${slStr}`);
    ruler(rx-8,entryY,targetY,teal,`TP ${tpStr}`);

    const rrText=`R:R  ${rrStr}`;
    ctx.save();ctx.font='600 8px "IBM Plex Mono",monospace';
    const rrW=ctx.measureText(rrText).width+16,rrH=18,rrX=W-rrW-8,rrY=PAD.t-30;
    ctx.fillStyle=isDark?'rgba(30,45,66,0.95)':'rgba(241,245,249,0.95)';
    ctx.strokeStyle=border;ctx.lineWidth=1;
    ctx.fillRect(rrX,rrY,rrW,rrH);ctx.strokeRect(rrX,rrY,rrW,rrH);
    ctx.fillStyle=gold;ctx.textAlign='center';
    ctx.fillText(rrText,rrX+rrW/2,rrY+12);
    ctx.restore();

    const bY=PAD.t-28;
    badge('1',xPH+PHW/2,bY,blue);badge('2',xQ1+3*slot,bY,red);badge('3',xRet+1.5*slot,bY,teal);
    badge('4',xCisd+slot,bY,orange);badge('5',xEnt+2*slot,bY,gold);
  }
}

function drawSetupViz(){
  // simple_1r = 1:1 SL/TP viz; raw_measure = no SL/TP (show neutral)
  let slPct=0.20, tpPct=0.20;
  if(activeProfile === 'raw_measure'){ slPct=0.20; tpPct=0.20; }
  drawSetupScene(document.getElementById('setup-canvas-bull'), 'bull', slPct, tpPct);
  drawSetupScene(document.getElementById('setup-canvas-bear'), 'bear', slPct, tpPct);
}

// ── FULL RENDER ────────────────────────────────────────────────────────────
// Note: demo-badge and infobar visibility are NOT toggled here. They ship
// hidden in the HTML and are only revealed from the fetch .catch() handler

export { C };
export { lineChart, rDistChart, filterWaterfall, dirCards };
export { _buildEquityPts, renderEquityCurveFS, renderOverviewEquityCurve, _drawEquityCurveSVG };
export { _heatColor, _drawMAEProbCurve, _drawMFEProbCurve, _drawExcursionHeatmap };
export { drawSetupViz };
