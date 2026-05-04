import { activeModel, activeMode, activeCisd, activeProfile, activeTF, activeSmt, activeF3, activeF4, MODEL_KEYS, MODEL_LABELS, RR_PROFILES, PROFILE_LABELS, PCT_PROFILES, CLS_META, SVG_FONT, isDark, activePageTab, setActiveModel, setActiveProfile, setActiveTF } from '../state.js';
import { pct, evFmt, pfFmt, evCls, wrHeatClr, wrHeatTxt, fmtDateRange, _tradingDaysFromRange } from '../utils.js';
import { C, lineChart, rDistChart, filterWaterfall, dirCards, drawSetupViz, _buildEquityPts, renderEquityCurveFS, renderOverviewEquityCurve } from '../charts.js';
import { getProfileData, getActiveTFData, getFilteredD, getSmtD, getAvailableProfiles } from '../data.js';
import { renderEdgeStudy } from './edge.js';
import { renderFilterVariants, renderProfileComparison, renderVerdict } from '../verdict.js';
import { renderMAEStudy, renderMFEStudy } from './excursion.js';
import { updateFilterChipDeltas } from './filters.js';
import { switchSMT, switchF3, switchF4, customRanges, applyCustomRanges } from '../walkforward.js';

function renderClassificationBreakdown(){
  const container = document.getElementById('classification-breakdown');
  if (!container) return;
  const fullKey = `${activeModel}_${activeMode}_${activeCisd}`;
  const profileD = getProfileData(fullKey, activeProfile);
  const D = activeSmt || activeF3 || activeF4 ? getFilteredD(getActiveTFData(profileD)) : getActiveTFData(profileD);
  const live = D?.by_classification;
  const cd = live
    ? { dwp: live.DWP, dnp: live.DNP, r1: live.R1, r2: live.R2, unclassified: live.Unclassified }
    : null;
  const cCfg = (meta, cls) => {
    if (!cls || !cls.n || cls.n <= 0) {
      return `<div class="cls-tile" style="border-top:2px solid ${meta.dot};opacity:0.45">
                <div style="font-family:var(--font-data);font-size:9px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.04em;margin-bottom:6px">${meta.label}</div>
                <div style="font-family:var(--font-display);font-size:15px;font-weight:800;color:${meta.color};letter-spacing:-0.02em;line-height:1">${meta.label}</div>
                <div style="font-family:var(--font-data);font-size:9px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.04em;margin-top:3px">${meta.sub}</div>
                <div style="font-family:var(--font-data);font-size:9px;color:var(--text-muted);margin-top:6px">No trades in selected period</div>
              </div>`;
    }
    const wrPct = (cls.wr * 100).toFixed(1);
    return `<div class="cls-tile" style="border-top:2px solid ${meta.dot}">
              <div style="display:flex;justify-content:space-between;align-items:baseline">
                <div style="font-family:var(--font-data);font-size:9px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.04em">${meta.label}</div>
                <div style="font-family:var(--font-data);font-size:9px;color:var(--text-muted);letter-spacing:.04em">${cls.n||0} trades</div>
              </div>
              <div style="font-family:var(--font-display);font-size:15px;font-weight:800;color:${meta.color};letter-spacing:-0.02em;line-height:1">${meta.label}</div>
              <div style="font-family:var(--font-data);font-size:9px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.04em;margin-top:3px">${meta.sub}</div>
              <div style="display:flex;gap:10px;margin-top:8px">
                <div><span style="font-family:var(--font-data);font-size:18px;font-weight:700;color:${wrPct>=50?'var(--green)':'var(--red)'}">${wrPct}%</span><span style="font-size:9px;color:var(--text-muted);display:block">Win Rate</span></div>
                <div><span style="font-family:var(--font-data);font-size:18px;font-weight:700;color:${cls.ev!=null?(cls.ev>0?'var(--green)':'var(--red)'):'var(--text-muted)'}">${cls.ev!=null?(cls.ev>0?'+':'')+cls.ev.toFixed(3)+'R':'—'}</span><span style="font-size:9px;color:var(--text-muted);display:block">EV</span></div>
              </div>
            </div>`;
  };
  container.innerHTML = Object.entries(CLS_META).map(([key, meta]) => (cd?.[key] ? cCfg(meta, cd[key]) : cCfg(meta, null))).join('');
}

function renderModelDropdown(){
  const sel = document.getElementById('model-select');
  if (!sel) return;
  sel.innerHTML = MODEL_KEYS.map(k => `<option value="${k}" ${k===activeModel?'selected':''}>${MODEL_LABELS[k]||k}</option>`).join('');
}
function switchModel(k){
  setActiveModel(k);
  window.render();
}

function renderProfileDropdown(){
  const sel = document.getElementById('profile-select');
  if (!sel) return;
  const fullKey = `${activeModel}_${activeMode}_${activeCisd}`;
  const profiles = getAvailableProfiles(fullKey);
  sel.innerHTML = profiles.map(pk => `<option value="${pk}" ${pk===activeProfile?'selected':''}>${PROFILE_LABELS[pk]||pk}${PCT_PROFILES.has(pk)?' %':''}</option>`).join('');
}
function switchProfile(pk){
  setActiveProfile(pk);
  window.render();
}

function switchTF(tf){
  setActiveTF(tf);
  const builder = document.getElementById('custom-range-builder');
  if (builder) builder.style.display = tf === 'custom' ? '' : 'none';
  if (tf === 'custom') {
    if (customRanges.length === 0) addCustomRange();
    renderRangeSlots();
  }
  localStorage.setItem('fractal-active-tf', tf);
  window.renderActive();
  window.updateTabVisibility();
  drawSetupViz();
}

function renderControls(){
  const pills = document.getElementById('mode-pills');
  pills.innerHTML = `<div class="mode-pill active-prev">Prior Candle</div>`;
  const cpills = document.getElementById('cisd-pills');
  cpills.innerHTML = `<div class="mode-pill active-cisd">CISD</div>`;
  const note = document.getElementById('mode-note');
  note.style.display = '';
  note.textContent = 'PREV = prior candle high/low · CISD = close beyond open of first opposing delivery candle';
}

function renderModel(D){
  const mrEl = document.getElementById('meta-row');
  if (!mrEl) return;
  mrEl.innerHTML = '';
  if (!D) return;
  const m = D.meta || {};
  const rs = D.risk_stats || {};
  const be = m.risk_breakeven_wr ?? 0.5;
  const rrTarget = m.rr_target ?? 2.0;
  const rrStr = rrTarget != null ? rrTarget.toFixed(2)+':1' : '—';
  const wrVal = m.win_rate;
  const wrCls = wrVal == null ? 'w' : wrVal >= 0.55 ? 'g' : wrVal >= 0.45 ? 'a' : 'r';
  const evVal = m.ev_per_trade;
  const pfVal = m.profit_factor;
  const pfCls = pfVal == null ? 'w' : pfVal >= 1.5 ? 'g' : pfVal >= 1.2 ? 'a' : pfVal >= 1.0 ? 'b' : 'r';
  const ceVal = rs.ce;
  const ceCls = ceVal == null ? 'w' : ceVal >= 0.40 ? 'g' : ceVal >= 0.20 ? 'a' : 'r';
  const dr = fmtDateRange(m.date_range);
  const tradesStr = (rs.trades ?? m.total_wl ?? 0).toLocaleString() + ' trades · ' + dr;
  const totalWl = rs.trades ?? m.total_wl ?? 0;
  const tradingDays = m.trading_days != null && m.trading_days > 0
    ? m.trading_days
    : _tradingDaysFromRange(m.date_range);
  const tradesPerDay = tradingDays && tradingDays > 0 ? (totalWl / tradingDays) : null;
  const tpdStr = tradesPerDay != null ? tradesPerDay.toFixed(2) : '—';
  const tpdCls = tradesPerDay == null ? 'w' : tradesPerDay >= 1 ? 'g' : tradesPerDay >= 0.3 ? 'a' : 'r';
  const tpdSub = tradingDays ? `${totalWl.toLocaleString()} trades ÷ ${tradingDays.toLocaleString()} trading days` : '—';
  [
    {label:'Win Rate',    val:wrVal!=null?pct(wrVal):'—',                      sub:tradesStr,                      cls:wrCls,  vc:wrCls},
    {label:'EV (R)',      val:evVal!=null?(evVal>0?'+':'')+evVal.toFixed(3)+'R':'—', sub:'Expected value per R risked', cls:evVal==null?'w':evVal>0?'g':'r', vc:evVal==null?'w':evVal>0?'g':'r'},
    {label:'Prof Factor', val:pfVal!=null?pfVal.toFixed(3):'—',                sub:'Gross profit ÷ gross loss',     cls:pfCls,  vc:pfCls},
    {label:'CE',          val:ceVal!=null?ceVal.toFixed(3):'—',                sub:'Combined Edge · EV/R × PF',    cls:ceCls,  vc:ceCls},
    {label:'R:R',         val:rrStr,                                           sub:'Reward-to-risk ratio (TP÷SL)', cls:'b',    vc:'b'},
    {label:'Trades/Day',  val:tpdStr,                                          sub:tpdSub,                         cls:tpdCls, vc:tpdCls},
    {label:'Max W Run',   val:rs.max_consec_wins??'—',                         sub:'Longest winning streak · '+dr, cls:'g',    vc:'g'},
    {label:'Avg W Run',   val:rs.avg_consec_wins!=null?rs.avg_consec_wins.toFixed(1):'—', sub:'Average winning streak length · '+dr, cls:'g', vc:'g'},
    {label:'Max L Run',   val:rs.max_consec_losses??'—',                       sub:'Longest losing streak · '+dr,  cls:'r',    vc:'r'},
    {label:'Avg L Run',   val:rs.avg_consec_losses!=null?rs.avg_consec_losses.toFixed(1):'—', sub:'Average losing streak length · '+dr, cls:'r', vc:'r'},
  ].forEach(card=>{
    const el=document.createElement('div'); el.className=`mc ${card.cls}`;
    el.innerHTML=`<div class="mc-accent"></div><div class="mc-lbl">${card.label}</div><div class="mc-val ${card.vc}">${card.val}</div><div class="mc-sub">${card.sub}</div>`;
    mrEl.appendChild(el);
  });

  drawSetupViz();
  if (activePageTab === 'edge') renderEdgeStudy(D);
  if (document.getElementById('dir-cards')) dirCards(document.getElementById('dir-cards'), D.dir_summary || []);
  if (activePageTab === 'filters') {
    filterWaterfall(document.getElementById('filter-waterfall'), D.filter_impact || []);
    renderFilterVariants(D);
  }
  rDistChart(document.getElementById('rdist-chart'), D.r_hist || []);
  lineChart(document.getElementById('year-chart'), D.by_year || [], 200, 40, 75, 'wr', 'yr');

  const rg = document.getElementById('risk-grid'), rn = document.getElementById('risk-note');
  rg.innerHTML = [
    {l:'P25',v:m.risk_p25||'—',u:'pt',c:'var(--green)'},
    {l:'Median',v:m.risk_median||'—',u:'pt',c:'var(--text-primary)'},
    {l:'Mean',v:m.avg_risk_pts||'—',u:'pt',c:'var(--text-primary)'},
    {l:'P75',v:m.risk_p75||'—',u:'pt',c:'var(--amber)'},
    {l:'P90',v:m.risk_p90||'—',u:'pt',c:'var(--red)'},
    {l:'Breakeven',v:pct(be),u:'',c:'var(--amber)'},
  ].map(i => `<div class="rg-cell"><div class="rg-lbl">${i.l}</div><div class="rg-val" style="color:${i.c}">${i.v}<span class="rg-unit">${i.u}</span></div></div>`).join('');
  rn.textContent = `Stop = |entry – sweep extreme|. Median stop = ${m.risk_median||'—'}pt → ~${(m.risk_median||0)*2}pt target at 1:2. Breakeven WR = ${pct(be)}.`;

  if (activePageTab === 'excursion') { renderMAEStudy(D); renderMFEStudy(D); }
  if (activePageTab === 'risk') renderEquityCurveFS(D);

  renderOverviewEquityCurve(D);
  renderClassificationBreakdown();
  renderProfileComparison();
  renderVerdict(document.getElementById('overview-verdict-panel'));
}

export { renderModel, renderModelDropdown, renderProfileDropdown, switchProfile, switchTF, renderControls, switchModel, renderClassificationBreakdown };
