import { activeModel, activeMode, activeCisd, activeProfile, activeTF, activeSmt, activeF3, activeF4, MODEL_KEYS, MODEL_LABELS, RR_PROFILES, PROFILE_LABELS, PCT_PROFILES, SVG_FONT, isDark, activePageTab, setActiveModel, setActiveProfile, setActiveTF } from '../state.js';
import { pct, evFmt, pfFmt, evCls, wrHeatClr, wrHeatTxt, fmtDateRange, _tradingDaysFromRange } from '../utils.js';
import { C, lineChart, rDistChart, filterWaterfall, dirCards, drawSetupViz, _buildEquityPts, renderEquityCurveFS, renderOverviewEquityCurve } from '../charts.js';
import { getProfileData, getActiveTFData, getFilteredD, getSmtD, getAvailableProfiles, loadProfile } from '../data.js';
import { renderEdgeStudy } from './edge.js';
import { renderFilterVariants, renderProfileComparison, renderVerdict } from '../verdict.js';
import { renderMAEStudy, renderMFEStudy } from './excursion.js';
import { updateFilterChipDeltas } from './filters.js';
import { renderRecentTrades } from './trades.js';
import { switchSMT, switchF3, switchF4, customRanges, applyCustomRanges } from '../walkforward.js';

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
  // Set selector values from activeProfile
  updateProfileSelectorsFromKey(activeProfile);
}
async function switchProfile(pk){
  const fullKey = `${activeModel}_${activeMode}_${activeCisd}`;
  // Ensure profile data is loaded from API
  await loadProfile(fullKey, pk);
  setActiveProfile(pk);
  updateProfileSelectorsFromKey(pk);
  window.render();
}

function profileKeyFromSelectors() {
  const special = document.getElementById('profile-special')?.value;
  if (special === 'raw_measure') return 'raw_measure';
  const r = document.getElementById('profile-r')?.value || '1';
  const ref = document.getElementById('profile-ref')?.value || 'entry';
  const entry = document.getElementById('profile-entry')?.value || 'open';
  return buildProfileKey(r, ref, entry);
}

function buildProfileKey(r, ref, entry) {
  const rSuffix = r === '1' ? '1r' : r === '1.5' ? '1r5' : '2r';
  if (entry === 'open' && ref === 'entry') return `simple_${rSuffix}`;
  if (entry === 'open' && ref === 'ob')    return `ob_${rSuffix}`;
  if (ref === 'entry') return `${entry}_${rSuffix}`;
  return `${entry}_ob_${rSuffix}`;
}

function parseProfileKey(pk) {
  if (pk === 'raw_measure') return { r: '1', ref: 'entry', entry: 'open' };
  if (pk.startsWith('simple_')) return { r: pk.includes('1r5') ? '1.5' : pk.includes('2r') ? '2' : '1', ref: 'entry', entry: 'open' };
  if (pk.startsWith('ob_'))    return { r: pk.includes('1r5') ? '1.5' : pk.includes('2r') ? '2' : '1', ref: 'ob',    entry: 'open' };
  const m = pk.match(/^(l\d+)_(ob_)?(\w+)$/);
  if (m) return { entry: m[1], ref: m[2] ? 'ob' : 'entry', r: m[3].includes('1r5') ? '1.5' : m[3].includes('2r') ? '2' : '1' };
  return { r: '1', ref: 'entry', entry: 'open' };
}

let _updatingSelectors = 0;

function updateProfileSelectorsFromKey(pk) {
  _updatingSelectors = Date.now();
  const special = document.getElementById('profile-special');
  const rEl = document.getElementById('profile-r');
  const refEl = document.getElementById('profile-ref');
  const entryEl = document.getElementById('profile-entry');
  if (pk === 'raw_measure') {
    if (special) special.value = 'raw_measure';
    return;
  }
  if (special) special.value = '';
  const p = parseProfileKey(pk);
  if (rEl) rEl.value = p.r;
  if (refEl) refEl.value = p.ref;
  if (entryEl) entryEl.value = p.entry;
}

function updateProfileFromSelectors() {
  if (Date.now() - _updatingSelectors < 100) return;
  const pk = profileKeyFromSelectors();
  if (pk && pk !== activeProfile) switchProfile(pk);
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
  if (activePageTab === 'trades') renderRecentTrades(0);

  renderOverviewEquityCurve(D);
  renderProfileComparison();
  renderVerdict(document.getElementById('overview-verdict-panel'));
}

export { renderModel, renderModelDropdown, renderProfileDropdown, switchProfile, switchTF, renderControls, switchModel, renderClassificationBreakdown, updateProfileFromSelectors };
