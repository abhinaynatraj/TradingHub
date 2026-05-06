// ── Imports ───────────────────────────────────────────────────────────────
import { activePageTab, RAW_TABS, RAW_TAB_LABELS,
         activeModel, activeMode, activeCisd, activeProfile, activeTF,
         activeSmt, activeF3, activeF4,
         MODEL_KEYS, MODEL_LABELS, isDemo,
         DASHBOARD_SCHEMA_VERSION,
         setActiveTF, setIsDemo, setActivePageTab, setCurrentTheme } from './state.js';
import { applyTheme, _savedTheme } from './theme.js';
import { fmtDateRange, triggerCSVDownload, csvEscape, showTip, hideTip } from './utils.js';
import { getProfileData, getActiveTFData, getSmtD, applyLoadedData, DEMO, DATA, setData } from './data.js';
import { drawSetupViz, renderOverviewEquityCurve, lineChart, rDistChart, renderEquityCurveFS } from './charts.js';
import { renderModel, renderModelDropdown, renderProfileDropdown, switchProfile, switchTF, renderControls, switchModel } from './tabs/overview.js';
import { renderEdgeStudy } from './tabs/edge.js';
import { updateFilterChipDeltas } from './tabs/filters.js';
import { renderRecentTrades } from './tabs/trades.js';
import { renderMAEStudy, renderMFEStudy } from './tabs/excursion.js';
import { renderFilterVariants } from './verdict.js';
import { switchSMT, switchF3, switchF4, _restoreFilters,
         renderRangeSlots, addCustomRange, removeRange, updateRange, saveAndRenderRanges,
         applyCustomRanges, switchCustomTab, customRanges,
         setRenderActive } from './walkforward.js';

// ── PAGE TAB NAVIGATION ────────────────────────────────────────────────────

function updateTabVisibility() {
  const isRaw = activeProfile === 'raw_measure';
  document.querySelectorAll('.page-tab').forEach(btn => {
    const label = btn.textContent.trim().toLowerCase().replace(/\s+/g,'');
    const isRawTab = RAW_TABS.some(t => label.includes(RAW_TAB_LABELS[t] || t));
    btn.style.display = (isRaw && !isRawTab) ? 'none' : '';
  });
  if (isRaw && !RAW_TABS.includes(activePageTab)) {
    switchPageTab('excursion');
  }
}

function switchPageTab(tab){
  setActivePageTab(tab);
  document.querySelectorAll('.page-pane').forEach(p => { p.classList.remove('active'); p.style.display = 'none'; });
  const pane = document.getElementById('pane-' + tab);
  if(pane){ pane.classList.add('active'); pane.style.display = ''; }
  document.querySelectorAll('.page-tab').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.sb-nav-btn').forEach(b => b.classList.remove('active'));
  const btn = [...document.querySelectorAll('.page-tab')].find(b => b.textContent.toLowerCase().replace(/\s+/g,'').includes(tab.replace('-','')));
  const sbBtn = [...document.querySelectorAll('.sb-nav-btn')].find(b => b.textContent.toLowerCase().replace(/\s+/g,'').includes(tab.replace('-','')));
  if(btn) btn.classList.add('active');
  if(sbBtn) sbBtn.classList.add('active');
  window.scrollTo({top:0,behavior:'smooth'});
  // Re-render canvases that need sizing when tab becomes visible
  const fullKey = `${activeModel}_${activeMode}_${activeCisd}`;
  const baseD = getProfileData(fullKey, activeProfile);
  if(!baseD) return;
  const D = getSmtD(getActiveTFData(baseD));
  if(tab === 'overview'){
    renderOverviewEquityCurve(D);
  }
  if(tab === 'edge'){
    renderEdgeStudy(D);
  }
  if(tab === 'filters'){
    renderFilterVariants(D);
  }
  if(tab === 'risk'){
    rDistChart(document.getElementById('rdist-chart'),D.r_hist||[]);
    lineChart(document.getElementById('year-chart'),D.by_year||[],200,40,75,'wr','yr');
    renderEquityCurveFS(D);
  }
  if(tab === 'excursion'){
    renderMAEStudy(D);
    renderMFEStudy(D);
  }
  if(tab === 'trades') renderRecentTrades(0);
  if(tab === 'overview') drawSetupViz();
}

// ── MAIN RENDER ────────────────────────────────────────────────────────────
function renderActive(){
  const customView = document.getElementById('custom-view');
  const pageNav = document.querySelector('.page-nav');
  if(activeTF === 'custom'){
    if(customView) customView.style.display = '';
    if(pageNav) pageNav.style.display = 'none';
    document.querySelectorAll('.page-pane').forEach(p => p.style.display = 'none');
    document.getElementById('meta-row').innerHTML = '';
    if(customRanges.some(r => r.start && r.end)) applyCustomRanges();
    return;
  } else {
    if(customView) customView.style.display = 'none';
    if(pageNav) pageNav.style.display = '';
    // Restore active pane visibility
    document.querySelectorAll('.page-pane').forEach(p => {
      if(p.classList.contains('active')) p.style.display = 'block';
    });
  }
  const fullKey = `${activeModel}_${activeMode}_${activeCisd}`;
  const baseD = getProfileData(fullKey, activeProfile);
  if(!baseD){
    document.getElementById('meta-row').innerHTML=`<div style="grid-column:1/-1;font-family:var(--font-data);font-size:11px;color:var(--text-muted);padding:8px">No data for ${fullKey} / ${activeProfile}. Run model_stats.py to generate.</div>`;
    return;
  }
  const D = getActiveTFData(baseD);
  renderModel(getSmtD(D));
  updateFilterChipDeltas(D);
}

// ── RENDER ─────────────────────────────────────────────────────────────────
function render(){
  const D = getProfileData(`${activeModel}_${activeMode}_${activeCisd}`, activeProfile);
  document.getElementById('hdr-sub').textContent=`Multi-TF Probability Engine · ${D?.meta?.instrument||'NQ'} · ${fmtDateRange(D?.meta?.date_range)}`;
  renderModelDropdown();
  renderProfileDropdown();
  renderControls();
  renderActive();
}

// Parse a key like "1H_5M_PREV_CISD" — last segment = cisd, second-to-last = sweep, rest = model
function parseKey(k){
  const parts = k.split('_');
  const cisd  = parts[parts.length - 1];           // last = CISD
  const sweep = parts[parts.length - 2];           // second to last = PREV
  const model = parts.slice(0, -2).join('_');      // everything else = model key
  return {model, sweep, cisd};
}

// ── Download trades ────────────────────────────────────────────────────────
function downloadFSTrades() {
  const fullKey = `${activeModel}_${activeMode}_${activeCisd}`;
  const baseD = getProfileData(fullKey, activeProfile);
  const D = getActiveTFData(baseD);
  const trades = D?.recent_trades;
  if (!trades || !trades.length) return;
  const headers = ['date','direction','session','hr','mn','dow_name','entry_price','sweep_extreme','target_price','risk_pts','r','outcome'];
  const tf = activeTF || 'all';
  const filename = `fractal_sweep_${activeModel}_${activeProfile}_${tf}_${new Date().toISOString().slice(0,10)}.csv`;
  triggerCSVDownload(trades, headers, filename);
}

// ── Recalc button (calls local server.py) ───────────────────────────────────
async function triggerRecalc(){
  const btn=document.getElementById('recalc-btn');
  if(!btn||btn.disabled)return;
  btn.disabled=true;
  btn.textContent='⟳ Running…';
  try{
    const r=await fetch('http://localhost:8001/recalc?engine=fractal_sweep',{method:'POST'});
    if(r.status===409){btn.textContent='⟳ Already running';setTimeout(()=>{btn.textContent='⟳ Recalculate';btn.disabled=false;},2000);return;}
    if(!r.ok) throw new Error('HTTP '+r.status);
    btn.textContent='⟳ Running…';
    pollRecalc();
  }catch(e){
    btn.textContent='⚠ Server not running';
    btn.title='Start server.py first: python3 server.py';
    setTimeout(()=>{btn.textContent='⟳ Recalculate';btn.disabled=false;btn.title='';},3000);
  }
}
function pollRecalc(){
  const btn=document.getElementById('recalc-btn');
  const iv=setInterval(async()=>{
    try{
      const r=await fetch('http://localhost:8001/recalc/status?engine=fractal_sweep');
      const s=await r.json();
      if(s.status==='ok'){
        clearInterval(iv);
        btn.textContent='✓ Done — reloading…';
        setTimeout(()=>{
          fetch('./model_stats.json').then(r=>r.json()).then(applyLoadedData).finally(()=>{
            btn.textContent='⟳ Recalculate';btn.disabled=false;
          });
        },400);
      } else if(s.status==='error'){
        clearInterval(iv);
        btn.textContent='⚠ Engine error';
        setTimeout(()=>{btn.textContent='⟳ Recalculate';btn.disabled=false;},3000);
      }
    }catch{clearInterval(iv);btn.textContent='⟳ Recalculate';btn.disabled=false;}
  },2000);
}

// ── Window bindings (for HTML onclick handlers) ──────────────────────────
window.renderActive = renderActive;
window.parseKey = parseKey;
window.applyTheme = applyTheme;
window.switchSMT = switchSMT;
window.switchF3 = switchF3;
window.switchF4 = switchF4;
window.switchModel = switchModel;
window.switchProfile = switchProfile;
window.switchTF = switchTF;
window.switchPageTab = switchPageTab;
window.triggerRecalc = triggerRecalc;
window.pollRecalc = pollRecalc;
window.addCustomRange = addCustomRange;
window.removeRange = removeRange;
window.updateRange = updateRange;
window.saveAndRenderRanges = saveAndRenderRanges;
window.switchCustomTab = switchCustomTab;
window.downloadFSTrades = downloadFSTrades;
window.showTip = showTip;
window.hideTip = hideTip;
window.render = render;
window.updateTabVisibility = updateTabVisibility;

// ── INIT ────────────────────────────────────────────────────────────────────
setRenderActive(renderActive);

const savedTF = localStorage.getItem('fractal-active-tf');
if(savedTF){
  setActiveTF(savedTF);
  const sel = document.getElementById('tf-select');
  if(sel) sel.value = savedTF;
  if(savedTF === 'custom'){
    const builder = document.getElementById('custom-range-builder');
    if(builder) builder.style.display = '';
    if(customRanges.length === 0) addCustomRange();
    renderRangeSlots();
  }
}

// Init demo data as immediate fallback
setData({
  '1H_5M_PREV_CISD': DEMO['1H_5M_PREV_CISD'],
  '30M_3M_PREV_CISD': DEMO['30M_3M_PREV_CISD'],
  '15M_1M_PREV_CISD': DEMO['15M_1M_PREV_CISD'],
});

// Restore saved theme
if(_savedTheme){ applyTheme(_savedTheme); setCurrentTheme(_savedTheme); }

render();
updateTabVisibility();
drawSetupViz();

fetch('./model_stats.json')
  .then(r => { if(!r.ok) throw new Error('HTTP '+r.status); return r.json(); })
  .then(j => {
    console.log('[sweep] model_stats.json loaded. Keys:', Object.keys(j));
    setIsDemo(false);
    const badge = document.getElementById('demo-badge');
    if(badge){ badge.style.display = 'none'; }
    applyLoadedData(j);
    render();
    updateTabVisibility();
    drawSetupViz();
  })
  .catch(e => {
    console.warn('[sweep] fetch failed:', e, '— using demo data');
    setIsDemo(true);
    const badge = document.getElementById('demo-badge');
    if(badge){ badge.style.display = ''; }
  });

// JSON file upload handler
document.getElementById('json-loader')?.addEventListener('change', e => {
  const file = e.target.files[0];
  if(!file) return;
  const reader = new FileReader();
  reader.onload = ev => {
    try{
      const j = JSON.parse(ev.target.result);
      applyLoadedData(j);
      setIsDemo(false);
      const badge = document.getElementById('demo-badge');
      if(badge) badge.style.display = 'none';
      render();
      updateTabVisibility();
      drawSetupViz();
    }catch(err){
      console.error('[sweep] Failed to parse uploaded JSON:', err);
    }
  };
  reader.readAsText(file);
});

// Resize handler
let rt; window.addEventListener('resize',()=>{clearTimeout(rt);rt=setTimeout(()=>{renderActive();drawSetupViz();},150);});
