export let html = document.documentElement;
export const THEME_ORDER = ['dark','light','gold','indigo'];
export let currentTheme = 'dark';
export let isDark = true;

export function setCurrentTheme(v) { currentTheme = v; }
export function setIsDark(v) { isDark = v; }

export function applyTheme(name){
  if (!THEME_ORDER.includes(name)) name = 'dark';
  currentTheme = name;
  isDark = (name !== 'light');
  html.setAttribute('data-theme', name);
  document.querySelectorAll('.theme-opt').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.theme === name);
  });
  localStorage.setItem('hub-theme', name);
  setTimeout(() => { if (window.renderActive) window.renderActive(); }, 50);
}

export const _savedTheme = (() => {
  try { const v = localStorage.getItem('hub-theme'); return v && THEME_ORDER.includes(v) ? v : null; }
  catch(e) { return null; }
})();
export let _excSegment = 'all';
export let activePageTab = 'overview';
export const RAW_TABS = ['excursion', 'trades'];
export const RAW_TAB_LABELS = {excursion:'mae/mfestudy', trades:'trades'};
export const SVG_FONT = "'JetBrains Mono',monospace";
export const MODEL_KEYS = ['1H_5M','30M_3M','15M_1M'];
export const MODEL_LABELS = {'1H_5M':'1H \u00b7 5M CISD', '30M_3M':'30M \u00b7 3M CISD', '15M_1M':'15M \u00b7 1M CISD'};

export let isDemo = true;
export function setIsDemo(v) { isDemo = v; }

export let activeModel = '1H_5M';
export function setActiveModel(v) { activeModel = v; }

export let activeMode = 'PREV';
export function setActiveMode(v) { activeMode = v; }

export let activeCisd = 'CISD';
export function setActiveCisd(v) { activeCisd = v; }

export let activeProfile = 'simple_1r';
export function setActiveProfile(v) { activeProfile = v; }

export let activeTF = 'all';
export function setActiveTF(v) { activeTF = v; }

export let activeSmt = false;
export function setActiveSmt(v) { activeSmt = v; }

export let activeF3 = false;
export function setActiveF3(v) { activeF3 = v; }

export let activeF4 = false;
export function setActiveF4(v) { activeF4 = v; }

export function setActivePageTab(v) { activePageTab = v; }

export const FILTER_STORAGE_KEY = 'fractal-filters-v1';
export const RR_PROFILES = [
  'simple_1r','simple_1r5','simple_2r',
  'ob_1r','ob_1r5','ob_2r',
  'l33_1r','l33_1r5','l33_2r',
  'l50_1r','l50_1r5','l50_2r',
  'l66_1r','l66_1r5','l66_2r',
  'l33_ob_1r','l33_ob_1r5','l33_ob_2r',
  'l50_ob_1r','l50_ob_1r5','l50_ob_2r',
  'l66_ob_1r','l66_ob_1r5','l66_ob_2r',
  'raw_measure',
];
export const PROFILE_LABELS = {
  'simple_1r':   'Simple 1R',
  'simple_1r5':  'Simple 1.5R',
  'simple_2r':   'Simple 2R',
  'ob_1r':       'OB 1R',
  'ob_1r5':      'OB 1.5R',
  'ob_2r':       'OB 2R',
  'l33_1r':      'L33 Entry · 1R',
  'l33_1r5':     'L33 Entry · 1.5R',
  'l33_2r':      'L33 Entry · 2R',
  'l50_1r':      'L50 Entry · 1R',
  'l50_1r5':     'L50 Entry · 1.5R',
  'l50_2r':      'L50 Entry · 2R',
  'l66_1r':      'L66 Entry · 1R',
  'l66_1r5':     'L66 Entry · 1.5R',
  'l66_2r':      'L66 Entry · 2R',
  'l33_ob_1r':   'L33 · OB 1R',
  'l33_ob_1r5':  'L33 · OB 1.5R',
  'l33_ob_2r':   'L33 · OB 2R',
  'l50_ob_1r':   'L50 · OB 1R',
  'l50_ob_1r5':  'L50 · OB 1.5R',
  'l50_ob_2r':   'L50 · OB 2R',
  'l66_ob_1r':   'L66 · OB 1R',
  'l66_ob_1r5':  'L66 · OB 1.5R',
  'l66_ob_2r':   'L66 · OB 2R',
  'raw_measure': 'Raw Measure',
};
export const PCT_PROFILES = new Set();
export const CLS_META = {
  dwp:          {label:'DWP',    sub:'Directional With Pullback', dot:'#22d3ee', color:'var(--blue)'},
  dnp:          {label:'DNP',    sub:'Directional No Pullback',   dot:'#f59e0b', color:'var(--amber)'},
  r1:           {label:'R1',     sub:'Range Day Type 1',          dot:'#3b82f6', color:'var(--blue)'},
  r2:           {label:'R2',     sub:'Range Day Type 2',          dot:'#8b5cf6', color:'var(--purple)'},
  unclassified: {label:'Unclas', sub:'Unclassified Days',         dot:'#4a6480', color:'var(--text-muted)'},
};
export const EQ_ACCT = 2000, EQ_RPT = 200;
export const DASHBOARD_SCHEMA_VERSION = 1;
