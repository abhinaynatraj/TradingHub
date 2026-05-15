import { isDemo, activeModel, activeMode, activeCisd, activeProfile, activeTF, MODEL_KEYS, MODEL_LABELS, RR_PROFILES, PROFILE_LABELS, PCT_PROFILES, DASHBOARD_SCHEMA_VERSION, activeSmt, activeF3, activeF4, activeP42, activePd, setIsDemo, setActiveModel, setActiveMode, setActiveCisd, setActiveProfile } from './state.js';
function makeDemoModel(key, label, mode, cisd, wrBase, evBase, pfBase, riskMed, spd){
  const fi=[
    {label:'Baseline (unfiltered)',n:Math.round(6200*(riskMed/18)),wr:wrBase-0.07,ev:evBase-0.22,pf:pfBase-0.58,removed:0},
    {label:'CISD',n:Math.round(3400*(riskMed/18)),wr:wrBase,ev:evBase,pf:pfBase,removed:Math.round(800*(riskMed/18))},
  ];
  const wl=Math.round(3400*(riskMed/18));
  const by_hour=[8,9,10,11,12,13,14,15].flatMap(hr=>[
    {hr,direction:'LONG', n:Math.round((30+hr*4)*(riskMed/18)),wr:+(wrBase+0.02+Math.sin(hr)*0.04).toFixed(3),ev:0,pf:0,hr_label:`${hr.toString().padStart(2,'0')}:00`},
    {hr,direction:'SHORT',n:Math.round((25+hr*3)*(riskMed/18)),wr:+(wrBase-0.02+Math.sin(hr*1.3)*0.04).toFixed(3),ev:0,pf:0,hr_label:`${hr.toString().padStart(2,'0')}:00`},
  ]).map(d=>({...d,wins:Math.round(d.n*d.wr),ev:+(d.wr*2-(1-d.wr)).toFixed(3),pf:+(d.wr*2/Math.max(1-d.wr,0.01)).toFixed(3),avg_risk_pts:riskMed}));
  const by_dow=[1,2,3,4,5].flatMap((dow,di)=>{
    const dn=['Mon','Tue','Wed','Thu','Fri'][di];
    return ['LONG','SHORT'].map((dir,diri)=>({dow,dow_name:dn,direction:dir,
      n:Math.round((90+di*10)*(riskMed/18)),
      wr:+(wrBase+(di===3?0.05:di===2?-0.04:0)+(diri?-0.03:0.01)).toFixed(3),ev:0,pf:0}));
  }).map(d=>({...d,wins:Math.round(d.n*d.wr),ev:+(d.wr*2-(1-d.wr)).toFixed(3),pf:+(d.wr*2/Math.max(1-d.wr,0.01)).toFixed(3)}));
  const by_session=[
    {session:'NY1',direction:'LONG', n:Math.round(1050*(riskMed/18)),wr:+(wrBase+0.04).toFixed(3)},
    {session:'NY1',direction:'SHORT',n:Math.round(890*(riskMed/18)), wr:+(wrBase+0.01).toFixed(3)},
    {session:'NY2',direction:'LONG', n:Math.round(850*(riskMed/18)), wr:+(wrBase-0.02).toFixed(3)},
    {session:'NY2',direction:'SHORT',n:Math.round(720*(riskMed/18)), wr:+(wrBase-0.05).toFixed(3)},
  ].map(d=>({...d,wins:Math.round(d.n*d.wr),ev:+(d.wr*2-(1-d.wr)).toFixed(3),pf:+(d.wr*2/Math.max(1-d.wr,0.01)).toFixed(3),avg_risk_pts:riskMed}));
  const DOW=['Mon','Tue','Wed','Thu','Fri'];
  const top_combos=[9,10,9,14,10,9,14,10].map((hr,i)=>({hr,dow:([4,1,2,4,1,1,2,2][i]),dow_name:DOW[[4,1,2,4,1,1,2,2][i]-1],direction:i%3===2?'SHORT':'LONG',n:Math.round((55+i*5)*(riskMed/18)),wr:+(wrBase+0.10-i*0.012).toFixed(3),avg_risk_pts:riskMed+2})).map(d=>({...d,wins:Math.round(d.n*d.wr),ev:+(d.wr*2-(1-d.wr)).toFixed(3),pf:+(d.wr*2/Math.max(1-d.wr,0.01)).toFixed(3),label:`${d.dow_name} ${d.hr}:00 ${d.direction}`}));
  const worst_combos=[12,12,13,15,12].map((hr,i)=>({hr,dow:([3,5,5,5,3][i]),dow_name:DOW[[3,5,5,5,3][i]-1],direction:i===3?'LONG':'SHORT',n:Math.round((25+i*3)*(riskMed/18)),wr:+(wrBase-0.18+i*0.03).toFixed(3),avg_risk_pts:riskMed-4})).map(d=>({...d,wins:Math.round(d.n*d.wr),ev:+(d.wr*2-(1-d.wr)).toFixed(3),pf:+(d.wr*2/Math.max(1-d.wr,0.01)).toFixed(3),label:`${d.dow_name} ${d.hr}:00 ${d.direction}`}));
  const heatmap=[8,9,10,11,12,13,14,15].flatMap(hr=>[1,2,3,4,5].map(dow=>({hr,dow,dow_name:DOW[dow-1],wr:+(wrBase+(dow===4?0.05:dow===3?-0.04:0)+Math.sin(hr+dow)*0.03).toFixed(3),n:Math.round((18+hr+dow)*(riskMed/18))})));
  const by_year=[2010,2011,2012,2013,2014,2015,2016,2017,2018,2019,2020,2021,2022,2023,2024,2025].map((yr,i)=>({yr,n:Math.round((300+i*5)*(riskMed/18)),wr:+(wrBase+Math.sin(i*0.8)*0.025).toFixed(3)})).map(d=>({...d,wins:Math.round(d.n*d.wr),ev:+(d.wr*2-(1-d.wr)).toFixed(3)}));
  const r_hist=[{bucket:'-2R (loss)',n:Math.round(wl*(1-wrBase)),fill:'loss'},{bucket:'0–0.5R',n:Math.round(wl*0.08),fill:'mid'},{bucket:'0.5–1.5R',n:Math.round(wl*0.05),fill:'mid'},{bucket:'2R (target)',n:Math.round(wl*wrBase),fill:'win'},{bucket:'3R+',n:Math.round(wl*0.03),fill:'win+'}];
  const dir_summary=[
    {direction:'LONG', n:Math.round(wl*0.56),wr:+(wrBase+0.02).toFixed(3),pf:+((wrBase+0.02)*2/Math.max(1-(wrBase+0.02),0.01)).toFixed(3),avg_risk_pts:riskMed},
    {direction:'SHORT',n:Math.round(wl*0.44),wr:+(wrBase-0.03).toFixed(3),pf:+((wrBase-0.03)*2/Math.max(1-(wrBase-0.03),0.01)).toFixed(3),avg_risk_pts:riskMed},
  ].map(d=>({...d,wins:Math.round(d.n*d.wr),ev:+(d.wr*2-(1-d.wr)).toFixed(3)}));
  // T-Spot breakdown demo data
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
  // Demo MAE/MFE distribution stats
  const _mkHist = (mu, sd, n, bins=20) => Array.from({length:bins},(_, i)=>{const lo=+(mu-2*sd+i*(4*sd/bins)).toFixed(4),hi=+(lo+4*sd/bins).toFixed(4);const v=(lo+hi)/2,z=(v-mu)/sd,cnt=Math.max(0,Math.round(n*Math.exp(-0.5*z*z)*0.25));return{lo,hi,n:cnt};});
  const mae_all_dist = {count:wl,min:0.02,p10:0.03,p25:0.05,p50:+(riskMed*0.35/18).toFixed(4),p75:+(riskMed*0.65/18).toFixed(4),p90:+(riskMed*0.90/18).toFixed(4),p95:+(riskMed*1.05/18).toFixed(4),p99:+(riskMed*1.4/18).toFixed(4),max:+(riskMed*2.2/18).toFixed(4),mean:+(riskMed*0.42/18).toFixed(4),std:+(riskMed*0.25/18).toFixed(4),mode:+(riskMed*0.30/18).toFixed(4),hist:_mkHist(riskMed*0.42/18,riskMed*0.25/18,wl)};
  const mfe_all_dist = {count:wl,min:0.01,p10:0.04,p25:0.08,p50:+(riskMed*0.55/18).toFixed(4),p75:+(riskMed*1.10/18).toFixed(4),p90:+(riskMed*1.80/18).toFixed(4),p95:+(riskMed*2.20/18).toFixed(4),p99:+(riskMed*3.0/18).toFixed(4),max:+(riskMed*4.5/18).toFixed(4),mean:+(riskMed*0.80/18).toFixed(4),std:+(riskMed*0.60/18).toFixed(4),mode:+(riskMed*0.45/18).toFixed(4),hist:_mkHist(riskMed*0.80/18,riskMed*0.50/18,wl)};
  const nW=Math.round(wl*wrBase), nL=wl-nW;
  const mae_wins_dist={...mae_all_dist,count:nW,p50:+(mae_all_dist.p50*0.7).toFixed(4),mean:+(mae_all_dist.mean*0.7).toFixed(4)};
  const mfe_wins_dist={...mfe_all_dist,count:nW,p50:+(mfe_all_dist.p50*1.4).toFixed(4),mean:+(mfe_all_dist.mean*1.4).toFixed(4)};
  const mae_loss_dist={...mae_all_dist,count:nL,p50:+(mae_all_dist.p50*1.5).toFixed(4),mean:+(mae_all_dist.mean*1.5).toFixed(4)};
  const mfe_loss_dist={...mfe_all_dist,count:nL,p50:+(mfe_all_dist.p50*0.5).toFixed(4),mean:+(mfe_all_dist.mean*0.5).toFixed(4)};
  return {
    meta:{model_key:key,full_key:`${key}_${mode}_${cisd}`,model_label:label,sweep_mode:mode,cisd_mode:cisd,cisd_mode_label:'ICT Body Open (True CISD)',instrument:'NQ',date_range:'2010-01-04 – 2025-03-07',trading_days:3782,total_raw:Math.round(8000*(riskMed/18)),total_wl:wl,total_expired:Math.round(wl*0.12),win_rate:wrBase,ev_per_trade:evBase,profit_factor:pfBase,avg_risk_pts:riskMed+2,risk_median:riskMed,risk_p25:Math.round(riskMed*0.6),risk_p75:Math.round(riskMed*1.55),risk_p90:Math.round(riskMed*2.3),setups_per_day_ny:spd,risk_breakeven_wr:0.333,rr_target:2},
    by_hour,by_session,by_dow,heatmap,top_combos,worst_combos,by_year,r_hist,dir_summary,filter_impact:fi,tspot_breakdown,
    mae_dist:{ext_count:wl,...Object.fromEntries(Object.entries(mae_all_dist).map(([k,v])=>[`ext_${k}`,v]))},
    mfe_dist:{ext_count:wl,...Object.fromEntries(Object.entries(mfe_all_dist).map(([k,v])=>[`ext_${k}`,v]))},
    mae_wins_dist, mfe_wins_dist, mae_loss_dist, mfe_loss_dist,
  };
}

// Demo: 2 variants (2 models × PREV sweep × CISD)
const DEMO = {
  '1H_5M_PREV_CISD':   makeDemoModel('1H_5M','1H Sweep · 5M CISD','PREV','CISD',0.557,0.671,1.82,18,1.82),
  '30M_3M_PREV_CISD':  makeDemoModel('30M_3M','30M Sweep · 3M CISD','PREV','CISD',0.551,0.652,1.78,10,2.80),
  '15M_1M_PREV_CISD':  makeDemoModel('15M_1M','15M Sweep · 1M CISD','PREV','CISD',0.545,0.635,1.72,8,3.50),
};

let DATA = DEMO;
export function setData(v) { DATA = v; }

async function fetchData(params = {}) {
  const qs = new URLSearchParams({ engine: 'fractal_sweep', ...params }).toString();
  const r = await fetch('/data?' + qs);
  if (!r.ok) throw new Error('HTTP ' + r.status);
  return r.json();
}

async function loadModelList() {
  const data = await fetchData();
  if (data.models) {
    const newData = { _meta: data._meta };
    for (const m of data.models) {
      if (!DATA[m] || !DATA[m].profiles) newData[m] = { profiles: {} };
      else newData[m] = DATA[m];
    }
    Object.assign(DATA, newData);
    return data.models;
  }
  return Object.keys(DATA).filter(k => k !== '_meta');
}

async function loadProfile(fullKey, profileKey) {
  if (!DATA[fullKey] || !DATA[fullKey].profiles) DATA[fullKey] = { profiles: {} };
  if (DATA[fullKey].profiles[profileKey]) return DATA[fullKey].profiles[profileKey];

  const data = await fetchData({ model: fullKey, profile: profileKey });
  const modelData = data[fullKey];
  if (modelData?.profiles) {
    Object.assign(DATA[fullKey].profiles, modelData.profiles);
    return modelData.profiles[profileKey];
  }
  return null;
}

async function initProfileData() {
  const models = await loadModelList();
  const fullKey = '1H_5M_PREV_CISD';
  if (models.includes(fullKey)) {
    await loadProfile(fullKey, 'simple_1r');
    return true;
  }
  const firstModel = models.find(k => k !== '_meta') || fullKey;
  await loadProfile(firstModel, 'simple_1r');
  return true;
}

// Helper — resolve active profile data (handles both flat DEMO and {profiles:{}} real JSON)
function getProfileData(fullKey, profile) {
  const base = DATA[fullKey];
  if (!base) return null;
  if (base.profiles) {
    // New structure: {profiles: {profile_key: stats_obj}}
    return base.profiles[profile] || base.profiles[Object.keys(base.profiles)[0]] || null;
  }
  // Old flat structure: the value IS the stats object (demo data has .meta directly)
  if (base.meta) return base;
  return null;
}

function getAvailableProfiles(fullKey) {
  const base = DATA[fullKey];
  if (!base) return RR_PROFILES;
  if (base.profiles) {
    const fromJson = new Set(Object.keys(base.profiles));
    return RR_PROFILES.filter(pk => fromJson.has(pk));
  }
  return RR_PROFILES; // demo data — all profiles point to same data
}
function getActiveTFData(fullProfileData){
  if (!fullProfileData) return null;
  if (activeTF === 'all') return fullProfileData;
  const slice = fullProfileData.by_tf?.[activeTF];
  if (!slice) return fullProfileData; // no data for this TF — fall back to all
  // Merge: slice provides meta/risk_stats/charts, full profile provides heatmap/combos/filter_impact.
  // Patch back avg_win_r/avg_loss_r/mae_bell from full risk_stats — not recomputed per sub-period.
  const mergedRS = Object.assign({}, fullProfileData.risk_stats || {}, slice.risk_stats || {}, {
    avg_win_r:  (fullProfileData.risk_stats || {}).avg_win_r,
    avg_loss_r: (fullProfileData.risk_stats || {}).avg_loss_r,
    mae_bell:   (fullProfileData.risk_stats || {}).mae_bell,
  });
  const mergedMeta = Object.assign({}, fullProfileData.meta || {}, slice.meta || {});
  return Object.assign({}, fullProfileData, slice, { meta: mergedMeta, risk_stats: mergedRS });
}
// ── SMT DATA OVERRIDE ────────────────────────────────────────────────────────
// When SMT checkbox is checked, recompute aggregated stats from filtered trades
// so hero tiles, by_hour, by_session, by_dow, and dir_summary all reflect SMT-only trades.
// Combined filter entry point: applies all 4 runtime filters individually.
//
// F3 defaults CHECKED (active) — it's the baseline quality filter.
function getFilteredD(D) {
  const anyActive = activeSmt || activeF3 || activeF4 || activeP42 || activePd;
  if (!anyActive) return D;
  const rawTrades = D?.recent_trades;
  if (!rawTrades || !rawTrades.length) return D;
  let trades = rawTrades;
  if (activeSmt) trades = trades.filter(t => t.smt === true);
  if (activeF3)  trades = trades.filter(t => t.passes_f3 === true);
  if (activeF4)  trades = trades.filter(t => t.passes_f4 === true);
  if (activeP42) trades = trades.filter(t => t.passes_p42 === true);
  if (activePd)  trades = trades.filter(t => t.passes_pd_cisd === true);
  if (!trades.length) return D;

  const wins = trades.filter(t => t.outcome === 'WIN');
  const losses = trades.filter(t => t.outcome === 'LOSS');
  const n = trades.length, nw = wins.length;
  const wr = n > 0 ? nw / n : 0;
  const sumWinR = wins.reduce((s,t) => s + t.r, 0);
  const sumLossR = losses.reduce((s,t) => s + Math.abs(t.r), 0);
  const ev = n > 0 ? (sumWinR - sumLossR) / n : 0;
  const pf = sumLossR > 0 ? sumWinR / sumLossR : 0;
  const ce = ev * pf;

  // Equity / drawdown from filtered trades
  const ACCT = 2000, RPT = 200;
  let eq = ACCT, peak = ACCT, minEq = ACCT, maxDD = 0;
  const dailyPnl = {};
  const sortedT = trades.slice().sort((a,b) => a.date.localeCompare(b.date));
  sortedT.forEach(t => {
    const pnl = t.r * RPT;
    eq += pnl;
    if (eq < minEq) minEq = eq;
    if (eq > peak) peak = eq;
    const dd = peak > 0 ? (peak - eq) / peak : 0;
    if (dd > maxDD) maxDD = dd;
    dailyPnl[t.date] = (dailyPnl[t.date]||0) + pnl;
  });
  const totalPnl = eq - ACCT;
  const dpArr = Object.values(dailyPnl);
  let sharpe = null;
  if (dpArr.length > 1) {
    const mu = dpArr.reduce((s,v)=>s+v,0)/dpArr.length;
    const sd = Math.sqrt(dpArr.reduce((s,v)=>s+(v-mu)**2,0)/(dpArr.length-1));
    if (sd > 0) sharpe = Math.round(mu/sd*Math.sqrt(252)*100)/100;
  }
  const maxDDPct = Math.round(maxDD*10000)/100;
  let mcw = 0, mcl = 0, wRun = 0, lRun = 0;
  trades.forEach(t => {
    if (t.outcome === 'WIN') { wRun++; mcw = Math.max(mcw, wRun); lRun = 0; }
    else { lRun++; mcl = Math.max(mcl, lRun); wRun = 0; }
  });

  // by_hour — group by hr and direction, compute wr/ev/pf
  function aggGroup(groups) {
    return Object.values(groups).map(g => {
      const gn = g.n, gw = g.wins;
      const gwr = gn > 0 ? gw / gn : 0;
      const gSumW = g.sumW, gSumL = g.sumL;
      const gev = gn > 0 ? (gSumW - gSumL) / gn : 0;
      const gpf = gSumL > 0 ? gSumW / gSumL : 0;
      const gavgMae = g.n > 0 ? g.sumMae / g.n : 0;
      const gavgMfe = g.n > 0 ? g.sumMfe / g.n : 0;
      const gavgMaeHr = g.n > 0 ? g.sumMaeHr / g.n : 0;
      const gavgMfeHr = g.n > 0 ? g.sumMfeHr / g.n : 0;
      return { ...g, wr: +gwr.toFixed(3), ev: +gev.toFixed(3), pf: +gpf.toFixed(3),
               avg_mae: +gavgMae.toFixed(4), avg_mfe: +gavgMfe.toFixed(4),
               avg_mae_hr: +gavgMaeHr.toFixed(4), avg_mfe_hr: +gavgMfeHr.toFixed(4) };
    });
  }
  function emptyBucket(extra) {
    return { n:0, wins:0, sumW:0, sumL:0, sumMae:0, sumMfe:0, sumMaeHr:0, sumMfeHr:0, ...extra };
  }
  function addTrade(bucket, t) {
    bucket.n++;
    if (t.outcome === 'WIN') { bucket.wins++; bucket.sumW += t.r; }
    else { bucket.sumL += Math.abs(t.r); }
    bucket.sumMae += t.mae_pct || 0;
    bucket.sumMfe += t.mfe_pct || 0;
    bucket.sumMaeHr += t.mae_pct_hr || 0;
    bucket.sumMfeHr += t.mfe_pct_hr || 0;
  }

  // by_hour
  const hrMap = {};
  trades.forEach(t => {
    const h = t.hr, dir = t.direction;
    if (h == null) return;
    const key = `${h}_${dir}`;
    if (!hrMap[key]) hrMap[key] = emptyBucket({ hr: h, direction: dir, hr_label: `${String(h).padStart(2,'0')}:00` });
    addTrade(hrMap[key], t);
  });
  const by_hour = aggGroup(hrMap);

  // by_session
  const sessMap = {};
  trades.forEach(t => {
    const sess = t.session, dir = t.direction;
    if (!sess) return;
    const key = `${sess}_${dir}`;
    if (!sessMap[key]) sessMap[key] = emptyBucket({ session: sess, direction: dir });
    addTrade(sessMap[key], t);
  });
  const by_session = aggGroup(sessMap);

  // by_dow — DuckDB dow: 0=Sun, but trades have dow_name too
  const DOW_NAMES_MAP = {0:'Sun',1:'Mon',2:'Tue',3:'Wed',4:'Thu',5:'Fri',6:'Sat'};
  const dowMap = {};
  trades.forEach(t => {
    const dow = t.dow, dir = t.direction;
    if (dow == null) return;
    const dn = t.dow_name || DOW_NAMES_MAP[dow] || String(dow);
    const key = `${dow}_${dir}`;
    if (!dowMap[key]) dowMap[key] = emptyBucket({ dow, dow_name: dn, direction: dir });
    addTrade(dowMap[key], t);
  });
  const by_dow = aggGroup(dowMap);

  // dir_summary
  const dirMap = {};
  trades.forEach(t => {
    const dir = t.direction;
    if (!dirMap[dir]) dirMap[dir] = emptyBucket({ direction: dir });
    addTrade(dirMap[dir], t);
  });
  const dir_summary = aggGroup(dirMap);

  const dateRange = trades.length > 0
    ? trades.map(t=>t.date).sort()[0] + ' to ' + trades.map(t=>t.date).sort().pop()
    : (D?.meta?.date_range || '');

  // Build overridden D with recomputed aggregates and updated meta
  const avgWinR = wins.length > 0 ? sumWinR / wins.length : null;
  const avgLossR = losses.length > 0 ? -(sumLossR / losses.length) : null;
  const origMeta = D?.meta || {};
  const newMeta = { ...origMeta,
    win_rate: +wr.toFixed(3), ev_per_trade: +ev.toFixed(3),
    profit_factor: +pf.toFixed(3), total_wl: n,
    date_range: dateRange,
  };
  const origRS = D?.risk_stats || {};
  const newRS = { ...origRS,
    trades: n, sharpe, blown: minEq <= 0, min_equity_usd: Math.round(minEq),
    max_dd_pct: maxDDPct, max_dd_usd: Math.round(maxDD * ACCT),
    total_pnl_usd: Math.round(totalPnl),
    ce: +ce.toFixed(3), max_consec_wins: mcw, max_consec_losses: mcl,
    avg_win_r: avgWinR, avg_loss_r: avgLossR,
  };

  // Build by_year from filtered trades
  const yearMap = {};
  trades.forEach(t => {
    const yr = parseInt(t.date.slice(0, 4));
    if (!yearMap[yr]) yearMap[yr] = { yr, n: 0, wins: 0, sumR: 0 };
    yearMap[yr].n++;
    yearMap[yr].sumR += t.r;
    if (t.outcome === 'WIN') yearMap[yr].wins++;
  });
  const by_year = Object.values(yearMap).sort((a, b) => a.yr - b.yr).map(y => ({
    yr: y.yr,
    n: y.n,
    wins: y.wins,
    wr: +(y.wins / y.n).toFixed(4),
    ev: +(y.sumR / y.n).toFixed(4),
    pf: 1,
  }));

  // Recompute top_combos / worst_combos from filtered trades
  const DOW_NAMES = {0:'Sun',1:'Mon',2:'Tue',3:'Wed',4:'Thu',5:'Fri',6:'Sat'};
  const comboMap = {};
  trades.forEach(t => {
    if (t.hr == null || t.dow == null) return;
    const key = `${t.hr}_${t.dow}_${t.direction}`;
    if (!comboMap[key]) {
      const dn = t.dow_name || DOW_NAMES[t.dow] || String(t.dow);
      comboMap[key] = { hr: t.hr, dow: t.dow, dow_name: dn, direction: t.direction,
        label: `${dn} ${String(t.hr).padStart(2,'0')}:00 ${t.direction}`,
        n: 0, wins: 0, sumR: 0, sumAbsR: 0, sumMae: 0, sumMfe: 0, sumMaeHr: 0, sumMfeHr: 0 };
    }
    const b = comboMap[key];
    b.n++; b.sumR += t.r; b.sumAbsR += Math.abs(t.r);
    if (t.outcome === 'WIN') b.wins++;
    b.sumMae += t.mae_pct || 0; b.sumMfe += t.mfe_pct || 0;
    b.sumMaeHr += t.mae_pct_hr || 0; b.sumMfeHr += t.mfe_pct_hr || 0;
  });
  const combos = Object.values(comboMap).filter(c => c.n >= 6).map(c => ({
    ...c, wr: +(c.wins / c.n).toFixed(4),
    ev: +(c.sumR / c.n).toFixed(4),
    pf: +(c.sumAbsR / Math.max(c.sumR - c.wins * (c.sumR > 0 ? 1 : -1), 0.001)).toFixed(3),
    avg_risk_pts: 0,
  }));
  combos.sort((a, b) => b.ev - a.ev);
  const top_combos = combos.slice(0, 15);
  const worst_combos = [...combos].sort((a, b) => a.ev - b.ev).slice(0, 5);

  return { ...D, meta: newMeta, risk_stats: newRS, by_hour, by_session, by_dow, dir_summary, by_year, recent_trades: trades, top_combos, worst_combos };
}

// Back-compat alias — legacy call sites use getSmtD
const getSmtD = getFilteredD;
function applyLoadedData(j){
  DATA=j; setIsDemo(false);

  // Schema version check + freshness display
  const meta = j['_meta'];
  if(meta){
    const freshEl = document.getElementById('data-freshness');
    if(freshEl && meta.generated_at){
      const d = new Date(meta.generated_at);
      const fmt = new Intl.DateTimeFormat('en-US',{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',timeZoneName:'short'});
      freshEl.textContent = 'Data: ' + fmt.format(d);
      freshEl.style.display = '';
    }
    if(meta.schema_version !== undefined && meta.schema_version !== DASHBOARD_SCHEMA_VERSION){
      console.warn(`[sweep] schema version mismatch: file=${meta.schema_version} dashboard=${DASHBOARD_SCHEMA_VERSION}`);
      const badge = document.getElementById('demo-badge');
      if(badge){ badge.textContent = `⚠ Schema v${meta.schema_version} (dashboard expects v${DASHBOARD_SCHEMA_VERSION}) — regenerate`; badge.style.display=''; }
    }
  }

  // Prefer 1H_5M_PREV_CISD as default; fall back to first key in the JSON
  const preferredKey = '1H_5M_PREV_CISD';
  const resolvedKey  = j[preferredKey] ? preferredKey : (Object.keys(j).filter(k=>k!=='_meta')[0] || '');
  if(resolvedKey){
    const {model,sweep,cisd}=parseKey(resolvedKey);
    setActiveModel(model); setActiveMode(sweep); setActiveCisd(cisd);
    // Keep activeProfile ('sl_026_tp_018') if it exists; otherwise use first available profile
    const profiles=j[resolvedKey]?.profiles;
    if(profiles && !profiles[activeProfile]){
      const fp=Object.keys(profiles)[0]; if(fp) setActiveProfile(fp);
    }
  }
}

export { DEMO, DATA };
export { makeDemoModel };
export { getProfileData, getAvailableProfiles };
export { getActiveTFData };
export { getFilteredD };
export { getSmtD };
export { applyLoadedData };
export { initProfileData, loadProfile };
