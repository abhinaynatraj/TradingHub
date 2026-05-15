import { isDark } from './state.js';

const pct = v => v!=null ? (v*100).toFixed(1)+'%' : '\u2014';
const evFmt = v => v!=null ? (v>0?'+':'')+v.toFixed(3)+'R' : '\u2014';
const pfFmt = v => v!=null ? v.toFixed(2) : '\u2014';
const evCls = v => v>0.4?'evp':v>0.1?'evm':'evn';

function wrHeatClr(wr){
  if(wr==null)return'transparent';
  const d=isDark;
  if(wr<0.35)return d?'rgba(239,68,68,.32)':'rgba(239,68,68,.20)';
  if(wr<0.42)return d?'rgba(239,68,68,.18)':'rgba(239,68,68,.10)';
  if(wr<0.48)return d?'rgba(245,158,11,.18)':'rgba(245,158,11,.14)';
  if(wr<0.53)return d?'rgba(245,158,11,.10)':'rgba(245,158,11,.08)';
  if(wr<0.58)return d?'rgba(16,185,129,.14)':'rgba(16,185,129,.10)';
  if(wr<0.63)return d?'rgba(16,185,129,.26)':'rgba(16,185,129,.20)';
  return d?'rgba(16,185,129,.4)':'rgba(16,185,129,.32)';
}

function wrHeatTxt(wr){
  if(!wr)return isDark?'#4a6480':'#94a3b8';
  const s = getComputedStyle(document.documentElement);
  const red = s.getPropertyValue('--red'), amber = s.getPropertyValue('--amber'), green = s.getPropertyValue('--green');
  return wr<0.45?red:wr<0.52?amber:green;
}

const tip = document.getElementById('tooltip');
function showTip(e,rows){tip.innerHTML=rows.map(r=>r==='---'?'<hr class="tt-divider"/>': `<div class="tt-row"><span class="tt-lbl">${r[0]}</span><span class="tt-val ${r[2]||''}">${r[1]}</span></div>`).join('');tip.style.display='block';moveTip(e);}
function moveTip(e){tip.style.left=(e.clientX+16)+'px';tip.style.top=(e.clientY-8)+'px';}
function hideTip(){tip.style.display='none';}
document.addEventListener('mousemove',e=>{try{if(tip&&tip.style.display==='block')moveTip(e);}catch{}});

function fmtDate(s){ return s ? String(s).slice(0,10) : '\u2014'; }

function fmtDateRange(dr) {
  if (!dr) return '';
  const parts = String(dr).split(/\s+[\u2013\u2014]\s+/);
  return parts.map(fmtDate).join(' to ');
}

function _tradingDaysFromRange(dr) {
  if (!dr) return null;
  const parts = String(dr).split(/\s+(?:[\u2013\u2014]|to)\s+/);
  if (parts.length !== 2) return null;
  const start = new Date(parts[0].trim());
  const end = new Date(parts[1].trim());
  if (isNaN(start) || isNaN(end) || end < start) return null;
  let days = 0;
  const cur = new Date(start);
  while (cur <= end) {
    const dow = cur.getUTCDay();
    if (dow !== 0 && dow !== 6) days++;
    cur.setUTCDate(cur.getUTCDate() + 1);
  }
  return days;
}

function csvEscape(v) {
  if (v == null) return '';
  const s = String(v);
  if (s.includes(',') || s.includes('"') || s.includes('\n')) return '"' + s.replace(/"/g, '""') + '"';
  return s;
}

function triggerCSVDownload(rows, headers, filename) {
  const lines = [headers.join(','), ...rows.map(r => headers.map(h => csvEscape(r[h])).join(','))];
  const blob = new Blob([lines.join('\n')], {type:'text/csv'});
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
  a.download = filename; a.click(); URL.revokeObjectURL(a.href);
}

export { pct, evFmt, pfFmt, evCls, wrHeatClr, wrHeatTxt };
export { showTip, moveTip, hideTip };
export { fmtDateRange, _tradingDaysFromRange };
export { csvEscape, triggerCSVDownload };

