import { activeModel, activeMode, activeCisd, activeProfile, activeTF } from '../state.js';
import { C, dirCards } from '../charts.js';
import { csvEscape, triggerCSVDownload, evFmt, evCls, pfFmt, pct } from '../utils.js';
import { getSmtFilteredTrades } from '../walkforward.js';

let _tradesPage = 0;
const TRADES_PER_PAGE = 40;
let _tradesCache = { key: '', trades: [] };

async function fetchTrades() {
  const fullKey = `${activeModel}_${activeMode}_${activeCisd}`;
  const cacheKey = `${fullKey}_${activeProfile}`;
  if (_tradesCache.key === cacheKey) return _tradesCache.trades;

  const params = new URLSearchParams({
    engine: 'fractal_sweep',
    model: fullKey,
    profile: activeProfile,
    period: 'all',
    limit: '12000',
  });
  const r = await fetch('/trades?' + params);
  if (!r.ok) throw new Error('HTTP ' + r.status);
  const data = await r.json();
  _tradesCache = { key: cacheKey, trades: data.trades || [] };
  return _tradesCache.trades;
}

async function renderRecentTrades(page) {
  const el = document.getElementById('recent-trades-table');
  const pgEl = document.getElementById('recent-trades-pagination');
  if (!el) return;

  try {
    const rawTrades = await fetchTrades();
    if (!rawTrades || !rawTrades.length) {
      el.innerHTML = '<p style="color:var(--text-muted);font-size:13px;padding:8px 0;">No trades data. Run <code>python3 model_stats.py</code> to generate.</p>';
      const titleEl = document.getElementById('trades-panel-title');
      if (titleEl) titleEl.textContent = 'Resolved Trades';
      if (pgEl) pgEl.style.display = 'none';
      return;
    }
    const trades = getSmtFilteredTrades(rawTrades);
    const totalCount = trades.length;
    const totalPages = Math.ceil(totalCount / TRADES_PER_PAGE);
    if (page !== undefined) _tradesPage = page;
    _tradesPage = Math.max(0, Math.min(_tradesPage, totalPages - 1));
    const start = _tradesPage * TRADES_PER_PAGE;
  const displayTrades = trades.slice(start, start + TRADES_PER_PAGE);
  const end = start + displayTrades.length;
  if (titleEl) titleEl.textContent = totalPages > 1
    ? `Showing ${start + 1}–${end} of ${totalCount.toLocaleString()} Resolved Trades`
    : `${totalCount.toLocaleString()} Resolved Trades`;
  const DOW_NAMES = {0:'Sun',1:'Mon',2:'Tue',3:'Wed',4:'Thu',5:'Fri',6:'Sat'};
  let html = `<div style="overflow-x:auto;">
  <table style="width:100%;border-collapse:collapse;font-family:var(--font-data);font-size:12px;">
    <thead><tr style="border-bottom:1px solid var(--border-mid);color:var(--text-muted);text-transform:uppercase;font-size:10px;letter-spacing:.06em;">
      <th style="padding:8px 10px;text-align:left;">Date</th>
      <th style="padding:8px 6px;text-align:left;">Day</th>
      <th style="padding:8px 6px;text-align:center;">Time</th>
      <th style="padding:8px 6px;text-align:left;">Session</th>
      <th style="padding:8px 6px;text-align:left;">Dir</th>
      <th style="padding:8px 6px;text-align:right;">Entry</th>
      <th style="padding:8px 6px;text-align:right;">Stop</th>
      <th style="padding:8px 6px;text-align:right;">SL %</th>
      <th style="padding:8px 6px;text-align:right;">Target</th>
      <th style="padding:8px 6px;text-align:right;">TP %</th>
      <th style="padding:8px 6px;text-align:right;">Risk</th>
      <th style="padding:8px 6px;text-align:right;">MAE %</th>
      <th style="padding:8px 6px;text-align:right;">MFE %</th>
      <th style="padding:8px 6px;text-align:center;">Result</th>
    </tr></thead><tbody>`;

  displayTrades.forEach((t, i) => {
    const bg = i % 2 === 0 ? 'transparent' : 'color-mix(in srgb,var(--bg-raised) 60%,transparent)';
    const isWin = t.outcome === 'WIN';
    const isMeasured = t.outcome === 'MEASURED';
    const resColor = isMeasured ? 'var(--blue)' : isWin ? 'var(--green)' : 'var(--red)';
    const dirColor = t.direction === 'LONG' ? 'var(--green)' : 'var(--red)';
    const dirArrow = t.direction === 'LONG' ? '▲' : '▼';
    const dowName  = t.dow_name || DOW_NAMES[t.dow] || '?';
    html += `<tr style="background:${bg};border-bottom:1px solid color-mix(in srgb,var(--border-mid) 40%,transparent);">
      <td style="padding:7px 10px;color:var(--text-primary);">${String(t.date).slice(0,10)}</td>
      <td style="padding:7px 6px;color:var(--text-primary);">${dowName}</td>
      <td style="padding:7px 6px;text-align:center;color:var(--text-primary);">${String(t.hr).padStart(2,'0')}:${String(t.mn ?? 0).padStart(2,'0')}</td>
      <td style="padding:7px 6px;color:var(--text-primary);font-size:11px;">${t.session||'—'}</td>
      <td style="padding:7px 6px;color:${dirColor};font-weight:700;">${dirArrow} ${t.direction}</td>
      <td style="padding:7px 6px;text-align:right;color:var(--text-primary);">${t.entry_price != null ? t.entry_price.toFixed(2) : '—'}</td>
      <td style="padding:7px 6px;text-align:right;color:var(--red);">${t.sweep_extreme != null ? t.sweep_extreme.toFixed(2) : '—'}</td>
      <td style="padding:7px 6px;text-align:right;color:var(--red);font-size:11px;">${t.entry_price && t.sweep_extreme ? (Math.abs(t.entry_price - t.sweep_extreme) / t.entry_price * 100).toFixed(2) + '%' : '—'}</td>
      <td style="padding:7px 6px;text-align:right;color:var(--green);">${t.target_price != null ? t.target_price.toFixed(2) : '—'}</td>
      <td style="padding:7px 6px;text-align:right;color:var(--green);font-size:11px;">${t.entry_price && t.target_price ? (Math.abs(t.target_price - t.entry_price) / t.entry_price * 100).toFixed(2) + '%' : '—'}</td>
      <td style="padding:7px 6px;text-align:right;color:var(--text-primary);">${t.risk_pts != null ? t.risk_pts.toFixed(1) : '—'}</td>
      <td style="padding:7px 6px;text-align:right;color:var(--red);font-size:11px;">${t.mae_pct != null ? t.mae_pct.toFixed(4) + '%' : '—'}</td>
      <td style="padding:7px 6px;text-align:right;color:var(--green);font-size:11px;">${t.mfe_pct != null ? t.mfe_pct.toFixed(4) + '%' : '—'}</td>
      <td style="padding:7px 6px;text-align:center;font-weight:700;color:${resColor};">${isMeasured ? '● MEASURED' : isWin ? '✓ WIN' : '✗ LOSS'}</td>
    </tr>`;
  });
  html += '</tbody></table></div>';
  el.innerHTML = html;

  if (!pgEl) return;
  if (totalPages <= 1) { pgEl.style.display = 'none'; return; }
  const btnStyle = (disabled) => `font-family:var(--font-data);font-size:11px;font-weight:600;padding:4px 12px;border-radius:5px;border:1px solid var(--border-mid);background:var(--bg-raised);color:${disabled?'var(--text-muted)':'var(--text-primary)'};cursor:${disabled?'default':'pointer'};opacity:${disabled?'0.4':'1'}`;
  const pageNums = [];
  const show = new Set([0, totalPages-1, _tradesPage-1, _tradesPage, _tradesPage+1].filter(p=>p>=0&&p<totalPages));
  [...show].sort((a,b)=>a-b).forEach((p,i,arr)=>{
    if(i>0 && arr[i]-arr[i-1]>1) pageNums.push('…');
    pageNums.push(p);
  });
  const paginationHTML = [
    `<button style="${btnStyle(_tradesPage===0)}" onclick="if(${_tradesPage}>0)renderRecentTrades(${_tradesPage-1})" ${_tradesPage===0?'disabled':''}>‹ Prev</button>`,
    ...pageNums.map(p => p==='…'
      ? `<span style="color:var(--text-muted);padding:0 2px">…</span>`
      : `<button style="${btnStyle(false)};${p===_tradesPage?'background:var(--accent);color:#fff;border-color:var(--accent)':''}" onclick="renderRecentTrades(${p})">${p+1}</button>`),
    `<button style="${btnStyle(_tradesPage===totalPages-1)}" onclick="if(${_tradesPage}<${totalPages-1})renderRecentTrades(${_tradesPage+1})" ${_tradesPage===totalPages-1?'disabled':''}>Next ›</button>`,
    `<span style="color:var(--text-muted);margin-left:4px">Page ${_tradesPage+1} of ${totalPages}</span>`,
  ].join('');
  pgEl.style.display = 'flex';
  pgEl.innerHTML = paginationHTML;
  } catch(e) {
    console.error('[trades]', e);
    el.innerHTML = `<p style="color:var(--red);font-size:13px;padding:8px 0;">Failed to load trades: ${e.message}. Ensure server.py is running.</p>`;
  }
}

export { renderRecentTrades, _tradesPage, TRADES_PER_PAGE };
