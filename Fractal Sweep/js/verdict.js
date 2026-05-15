import { activeModel, activeMode, activeCisd, activeProfile, activeTF, activeSmt, activeF3, activeF4, SVG_FONT, isDark, RR_PROFILES, PROFILE_LABELS, PCT_PROFILES, MODEL_LABELS } from './state.js';
import { C } from './charts.js';
import { pct, evFmt, evCls, pfFmt, wrHeatClr, wrHeatTxt } from './utils.js';
import { getProfileData, DATA } from './data.js';

function getSmtFilteredTrades(trades) {
  if (!trades || !trades.length) return trades;
  let out = trades;
  if (activeSmt) out = out.filter(t => t.smt === true);
  if (activeF3)  out = out.filter(t => t.passes_f3 === true);
  if (activeF4)  out = out.filter(t => t.passes_f4 === true);
  return out;
}

function renderProfileComparison(){
  const el = document.getElementById('profile-comparison-panel');
  if (!el) return;
  const fullKey = `${activeModel}_${activeMode}_${activeCisd}`;

  let html = `<div style="font-family:var(--font-data);font-size:11px;font-weight:600;letter-spacing:.04em;color:var(--text-muted);text-transform:uppercase;margin-bottom:10px">Risk Profile Comparison — ${MODEL_LABELS[activeModel]||activeModel}</div>`;
  html += `<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-family:var(--font-data);font-size:11px;">
    <thead><tr style="border-bottom:1px solid var(--border-mid);color:var(--text-muted);font-size:10px;letter-spacing:.06em;text-transform:uppercase;">
      <th style="padding:6px 10px;text-align:left;">Profile</th>
      <th style="padding:6px 8px;text-align:right;">Setups</th>
      <th style="padding:6px 8px;text-align:right;">Win Rate</th>
      <th style="padding:6px 8px;text-align:right;">EV / Trade</th>
      <th style="padding:6px 8px;text-align:right;">Profit Factor</th>
      <th style="padding:6px 8px;text-align:right;">Breakeven WR</th>
      <th style="padding:6px 8px;text-align:right;">Avg Risk</th>
    </tr></thead><tbody>`;

  const comparisonKeys = RR_PROFILES.filter(k => getProfileData(fullKey, k)).slice(0, 6);
  comparisonKeys.forEach((pk, i) => {
    const d = getProfileData(fullKey, pk);
    if (!d) return;
    const m = d.meta || {};
    const isActive = pk === activeProfile;
    const bg = isActive
      ? 'color-mix(in srgb,var(--accent) 12%,transparent)'
      : i % 2 === 0 ? 'transparent' : 'color-mix(in srgb,var(--bg-raised) 50%,transparent)';
    const wrCol = (m.win_rate||0) >= (m.risk_breakeven_wr||0.333) ? 'var(--green)' : 'var(--red)';
    const evCol = (m.ev_per_trade||0) > 0 ? 'var(--green)' : 'var(--red)';
    const pfCol = (m.profit_factor||0) >= 1.5 ? 'var(--green)' : (m.profit_factor||0) >= 1 ? 'var(--amber)' : 'var(--red)';
    html += `<tr style="background:${bg};border-bottom:1px solid color-mix(in srgb,var(--border-mid) 40%,transparent);cursor:pointer;" onclick="switchProfile('${pk}')">
      <td style="padding:7px 10px;font-weight:${isActive?700:400};color:${isActive?'var(--accent)':'var(--text-primary)'}">${isActive?'▶ ':''}${PROFILE_LABELS[pk]||pk}</td>
      <td style="padding:7px 8px;text-align:right;color:var(--text-muted)">${(m.total_wl||0).toLocaleString()}</td>
      <td style="padding:7px 8px;text-align:right;color:${wrCol};font-weight:600">${m.win_rate!=null?pct(m.win_rate):'—'}</td>
      <td style="padding:7px 8px;text-align:right;color:${evCol};font-weight:600">${m.ev_per_trade!=null?evFmt(m.ev_per_trade):'—'}</td>
      <td style="padding:7px 8px;text-align:right;color:${pfCol}">${m.profit_factor!=null?pfFmt(m.profit_factor):'—'}</td>
      <td style="padding:7px 8px;text-align:right;color:var(--text-muted)">${m.risk_breakeven_wr!=null?pct(m.risk_breakeven_wr):'—'}</td>
      <td style="padding:7px 8px;text-align:right;color:var(--text-muted)">${m.avg_risk_pts!=null?m.avg_risk_pts+'pt':'—'}</td>
    </tr>`;
  });

  html += '</tbody></table></div>';
  el.innerHTML = html;
}


function renderVerdict(targetEl, opts = {}) {
  const el = targetEl;
  if (!el) return;

  const fullKey = `${activeModel}_${activeMode}_${activeCisd}`;
  const base = DATA[fullKey];
  if (!base || !base.profiles) { el.innerHTML = ''; return; }

  const ACCT_V = 4500, RPT_V = 225;
  const {tradeDateSet, walkForwardPairs} = opts;

  // ── Score each profile ─────────────────────────────────────────────────
  function scoreProfile(pk) {
    const pd = base.profiles[pk];
    if (!pd || !pd.recent_trades) return null;
    let pt = pd.recent_trades;
    // Apply TF period filter (for overview tab)
    if (!tradeDateSet && activeTF !== 'all' && pd.by_tf && pd.by_tf[activeTF] && pd.by_tf[activeTF].recent_trades) {
      pt = pd.by_tf[activeTF].recent_trades;
    }
    // Apply date filter (for custom ranges)
    if (tradeDateSet) pt = pt.filter(t => tradeDateSet.has(t.date));
    // Apply full 4-filter pipeline (F3/SMT/Hour/PriorEng)
    pt = getSmtFilteredTrades(pt);
    const wl = pt.filter(t => t.outcome === 'WIN' || t.outcome === 'LOSS');
    if (wl.length < 5) return null;
    const n = wl.length;
    const wins = wl.filter(t => t.outcome === 'WIN').length;
    const wr = wins / n;
    const sumW = wl.filter(t => t.r > 0).reduce((s,t) => s+t.r, 0);
    const sumL = wl.filter(t => t.r <= 0).reduce((s,t) => s+Math.abs(t.r), 0);
    const ev = (sumW - sumL) / n;
    const pf = sumL > 0 ? sumW / sumL : sumW > 0 ? 99 : 0;
    let eq = ACCT_V, peak = ACCT_V, maxDD = 0;
    wl.slice().sort((a,b) => a.date.localeCompare(b.date)).forEach(t => {
      eq += t.r * RPT_V;
      if (eq > peak) peak = eq;
      const dd = peak > 0 ? (peak - eq) / peak : 0;
      if (dd > maxDD) maxDD = dd;
    });
    const dp = {};
    wl.forEach(t => { dp[t.date] = (dp[t.date]||0) + t.r * RPT_V; });
    const dpArr = Object.values(dp);
    let sharpe = null;
    if (dpArr.length > 1) {
      const mu = dpArr.reduce((s,v)=>s+v,0)/dpArr.length;
      const sd = Math.sqrt(dpArr.reduce((s,v)=>s+(v-mu)**2,0)/(dpArr.length-1));
      if (sd > 0) sharpe = mu / sd * Math.sqrt(252);
    }
    // SMT stats from this profile's trades
    const smtT = pt.filter(t => t.smt === true && (t.outcome === 'WIN' || t.outcome === 'LOSS'));
    const noSmtT = pt.filter(t => !t.smt && (t.outcome === 'WIN' || t.outcome === 'LOSS'));
    const smtWR = smtT.length >= 5 ? smtT.filter(t => t.outcome === 'WIN').length / smtT.length : null;
    const noSmtWR = noSmtT.length >= 5 ? noSmtT.filter(t => t.outcome === 'WIN').length / noSmtT.length : null;

    return {pk, label: (PROFILE_LABELS[pk] || pk).split('—')[0].trim(),
            n, wr, ev, pf, sharpe, maxDD: maxDD*100, blown: eq <= 0, smtWR, noSmtWR};
  }

  // Score active profile + up to 5 others to avoid browser freeze with 25 profiles
  const allKeys = Object.keys(base.profiles);
  const keysToScore = new Set([activeProfile]);
  for (const k of allKeys) { if (keysToScore.size >= 6) break; keysToScore.add(k); }
  const profileScores = [...keysToScore].map(scoreProfile).filter(Boolean);
  if (profileScores.length === 0) { el.innerHTML = ''; return; }

  // Composite score
  profileScores.forEach(p => {
    const maxEV = Math.max(...profileScores.map(x => Math.max(0.001, x.ev)));
    const maxSharpe = Math.max(...profileScores.map(x => Math.max(0.001, x.sharpe || 0)));
    const normEV = Math.max(0, p.ev) / maxEV;
    const normSharpe = p.sharpe != null ? Math.max(0, p.sharpe) / maxSharpe : 0;
    const normDD = 1 - Math.min(1, p.maxDD / 50);
    const normPF = Math.min(1, p.pf / 10);
    p.score = normEV * 0.40 + normSharpe * 0.30 + normDD * 0.20 + normPF * 0.10;
  });
  profileScores.sort((a,b) => b.score - a.score);
  const best = profileScores[0];

  // ── Assess edge ────────────────────────────────────────────────────────
  const signals = [];
  let edgeScore = 0, maxEdgeScore = 0;

  maxEdgeScore += 2;
  if (best.ev > 0.3) { edgeScore += 2; signals.push({text: `EV ${best.ev.toFixed(3)}R per trade`, color: 'var(--green)'}); }
  else if (best.ev > 0) { edgeScore += 1; signals.push({text: `EV ${best.ev.toFixed(3)}R — marginal`, color: 'var(--amber)'}); }
  else { signals.push({text: `Negative EV ${best.ev.toFixed(3)}R`, color: 'var(--red)'}); }

  maxEdgeScore += 1;
  if (best.wr > 0.55) edgeScore += 1;

  maxEdgeScore += 2;
  if (best.sharpe != null && best.sharpe > 2) { edgeScore += 2; signals.push({text: `Sharpe ${best.sharpe.toFixed(1)}`, color: 'var(--green)'}); }
  else if (best.sharpe != null && best.sharpe > 1) { edgeScore += 1; signals.push({text: `Sharpe ${best.sharpe.toFixed(1)}`, color: 'var(--amber)'}); }

  maxEdgeScore += 2;
  if (best.maxDD < 10) { edgeScore += 2; signals.push({text: `Max DD ${best.maxDD.toFixed(1)}%`, color: 'var(--green)'}); }
  else if (best.maxDD < 25) { edgeScore += 1; signals.push({text: `Max DD ${best.maxDD.toFixed(1)}%`, color: 'var(--amber)'}); }
  else { signals.push({text: `Max DD ${best.maxDD.toFixed(1)}%`, color: 'var(--red)'}); }

  if (walkForwardPairs && walkForwardPairs.length > 0) {
    maxEdgeScore += 2;
    const ofs = walkForwardPairs.map(p => {
      const bv = p.variants[p.bestVariantIdx];
      return (bv.train && bv.test && bv.train.ev_r > 0) ? (bv.test.ev_r / bv.train.ev_r) * 100 : 0;
    }).filter(s => s > 0);
    const avg = ofs.length > 0 ? ofs.reduce((s,v)=>s+v,0)/ofs.length : 0;
    if (avg >= 80) { edgeScore += 2; signals.push({text: `Walk-forward ${Math.round(avg)}%`, color: 'var(--green)'}); }
    else if (avg >= 50) { edgeScore += 1; signals.push({text: `Walk-forward ${Math.round(avg)}%`, color: 'var(--amber)'}); }
    else { signals.push({text: `Walk-forward ${Math.round(avg)}%`, color: 'var(--red)'}); }
  }

  if (best.smtWR != null && best.noSmtWR != null && best.smtWR > best.noSmtWR + 0.03) {
    signals.push({text: `SMT +${((best.smtWR - best.noSmtWR)*100).toFixed(1)}% WR`, color: 'var(--green)'});
  }

  // Verdict
  const confidence = maxEdgeScore > 0 ? edgeScore / maxEdgeScore : 0;
  let verdict, verdictColor, verdictBg;
  if (best.blown) { verdict = 'NOT VIABLE'; verdictColor = '#ef4444'; verdictBg = 'rgba(239,68,68,0.08)'; }
  else if (confidence >= 0.75 && best.ev > 0.2) { verdict = 'TRADEABLE EDGE'; verdictColor = '#10b981'; verdictBg = 'rgba(16,185,129,0.06)'; }
  else if (confidence >= 0.50 && best.ev > 0) { verdict = 'CONDITIONAL EDGE'; verdictColor = '#f59e0b'; verdictBg = 'rgba(245,158,11,0.06)'; }
  else if (best.ev > 0) { verdict = 'WEAK EDGE'; verdictColor = '#f59e0b'; verdictBg = 'rgba(245,158,11,0.04)'; }
  else { verdict = 'NO EDGE'; verdictColor = '#ef4444'; verdictBg = 'rgba(239,68,68,0.06)'; }

  let why = '';
  if (profileScores.length >= 2) {
    const second = profileScores[1];
    if (best.ev > second.ev && best.sharpe >= (second.sharpe || 0)) why = `Higher EV (${best.ev.toFixed(3)}R vs ${second.ev.toFixed(3)}R) with better risk-adjusted returns`;
    else if (best.ev > second.ev) why = `Highest EV (${best.ev.toFixed(3)}R) across ${best.n} trades`;
    else if (best.maxDD < second.maxDD) why = `Lower drawdown (${best.maxDD.toFixed(1)}% vs ${second.maxDD.toFixed(1)}%) with comparable returns`;
    else why = `Best composite score (EV + Sharpe + DD + PF)`;
  }

  el.innerHTML = `<div style="background:${verdictBg};border:2px solid ${verdictColor}40;border-radius:12px;padding:24px">
    <div style="display:flex;align-items:center;gap:14px;margin-bottom:${why || signals.length ? '16px' : '0'}">
      <div style="font-family:var(--font-display);font-size:28px;font-weight:800;color:${verdictColor};letter-spacing:-0.02em">${verdict}</div>
      <div style="font-family:var(--font-data);font-size:13px;font-weight:700;color:var(--text-primary);padding:4px 12px;border-radius:6px;background:var(--bg-raised);border:1px solid var(--border)">${best.label}</div>
      <div style="font-family:var(--font-data);font-size:11px;color:var(--text-muted)">${best.n} trades · ${(best.wr*100).toFixed(1)}% WR · ${best.pf.toFixed(2)} PF</div>
    </div>
    ${why ? `<div style="font-family:var(--font-data);font-size:12px;color:var(--text-primary);margin-bottom:14px">${why}</div>` : ''}
    ${signals.length ? `<div style="display:flex;flex-wrap:wrap;gap:8px">${signals.map(s => `<span style="font-family:var(--font-data);font-size:11px;padding:4px 10px;border-radius:5px;background:var(--bg-raised);border:1px solid var(--border);color:${s.color}">${s.text}</span>`).join('')}</div>` : ''}
  </div>`;
}


function renderFilterVariants(D, targetEl) {
  const el = targetEl || document.getElementById('filter-variants-panel');
  if (!el) return;
  const fv = D.filter_variants;
  if (!fv || !fv.all_combinations) {
    el.innerHTML = '<div style="padding:16px;font-family:var(--font-data);font-size:12px;color:var(--text-muted)">Run model_stats.py to see filter variant analysis.</div>';
    return;
  }

  const ACCT = 2000, RPT = 200;
  const combos = fv.all_combinations;
  const best = fv.best_combination;
  const baseline = fv.baseline;

  function sc(val, good, bad, inv) {
    if (inv) return val <= good ? 'var(--green)' : val >= bad ? 'var(--red)' : 'var(--amber)';
    return val >= good ? 'var(--green)' : val <= bad ? 'var(--red)' : 'var(--amber)';
  }

  let html = '';

  // Best combo callout
  if (best) {
    const isCurrent = best.label === baseline.label;
    html += `<div style="background:${isCurrent ? 'rgba(16,185,129,0.08)' : 'rgba(245,158,11,0.08)'};border:1px solid ${isCurrent ? 'rgba(16,185,129,0.3)' : 'rgba(245,158,11,0.3)'};border-radius:10px;padding:14px 18px;margin-bottom:16px;font-family:var(--font-data)">
      <div style="font-size:11px;font-weight:700;color:${isCurrent ? 'var(--green)' : 'var(--amber)'};text-transform:uppercase;letter-spacing:0.06em;margin-bottom:6px">${isCurrent ? 'Current filters are optimal' : 'Better filter combination found'}</div>
      <div style="font-size:13px;color:var(--text-primary);font-weight:600">${best.label}</div>
      <div style="font-size:11px;color:var(--text-muted);margin-top:4px">N=${best.n} · WR=${(best.wr*100).toFixed(1)}% · EV=${best.ev.toFixed(3)}R · PF=${best.pf.toFixed(2)} · Max DD=${best.max_dd_pct.toFixed(1)}%</div>
    </div>`;
  }

  // Filter legend
  html += `<div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:16px;margin-bottom:16px;box-shadow:var(--shadow)">
    <div style="font-size:11px;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:10px">Filter Definitions</div>
    <table style="width:100%;border-collapse:collapse;font-size:12px;font-family:var(--font-data)">
      <thead><tr style="border-bottom:2px solid var(--border)">
        <th style="padding:8px 10px;text-align:left;color:var(--text-muted);width:140px">Filter</th>
        <th style="padding:8px 10px;text-align:left;color:var(--text-muted)">What it does</th>
        <th style="padding:8px 10px;text-align:left;color:var(--text-muted);width:200px">Parameter</th>
      </tr></thead><tbody>
      <tr>
        <td style="padding:6px 10px;font-weight:700;color:#ff6600">NQ-ES Divergence</td>
        <td style="padding:6px 10px;color:var(--text-primary)">Only take setups where ES does <em>not</em> confirm the NQ sweep — divergence between correlated instruments signals manipulation, not genuine market direction</td>
        <td style="padding:6px 10px;color:var(--text-muted);font-family:var(--font-data)">ES holds <span style="color:var(--text-primary);font-weight:600">above/below</span> its prior HTF level</td>
      </tr>
    </tbody></table>
  </div>`;

  // Individual removal table
  html += `<div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:16px;margin-bottom:16px;box-shadow:var(--shadow)">
    <div style="font-size:11px;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:10px">Individual Filter Removal — What happens when you remove one filter?</div>
    <table style="width:100%;border-collapse:collapse;font-size:12px">
      <thead><tr style="border-bottom:2px solid var(--border)">
        <th style="padding:8px 10px;text-align:left;color:var(--text-muted)">Remove This Filter</th>
        <th style="padding:8px 6px;text-align:right;color:var(--text-muted)">Trades</th>
        <th style="padding:8px 6px;text-align:right;color:var(--text-muted)">Added</th>
        <th style="padding:8px 6px;text-align:right;color:var(--text-muted)">WR</th>
        <th style="padding:8px 6px;text-align:right;color:var(--text-muted)">WR Δ</th>
        <th style="padding:8px 6px;text-align:right;color:var(--text-muted)">EV (R)</th>
        <th style="padding:8px 6px;text-align:right;color:var(--text-muted)">EV Δ</th>
        <th style="padding:8px 6px;text-align:right;color:var(--text-muted)">PF</th>
        <th style="padding:8px 6px;text-align:right;color:var(--text-muted)">Max DD</th>
        <th style="padding:8px 6px;text-align:center;color:var(--text-muted)">Verdict</th>
      </tr></thead><tbody>`;

  // Current baseline row
  html += `<tr style="background:rgba(59,130,246,0.06);border-bottom:1px solid var(--border)">
    <td style="padding:6px 10px;font-weight:700;color:var(--blue,#3b82f6)">Current (all filters)</td>
    <td style="padding:6px;text-align:right;color:var(--text-primary)">${baseline.n}</td>
    <td style="padding:6px;text-align:right;color:var(--text-muted)">—</td>
    <td style="padding:6px;text-align:right;font-weight:600;color:var(--text-primary)">${(baseline.wr*100).toFixed(1)}%</td>
    <td style="padding:6px;text-align:right;color:var(--text-muted)">—</td>
    <td style="padding:6px;text-align:right;font-weight:600;color:var(--text-primary)">${baseline.ev.toFixed(3)}</td>
    <td style="padding:6px;text-align:right;color:var(--text-muted)">—</td>
    <td style="padding:6px;text-align:right;color:var(--text-primary)">${baseline.pf.toFixed(2)}</td>
    <td style="padding:6px;text-align:right;color:var(--text-primary)">${baseline.max_dd_pct.toFixed(1)}%</td>
    <td style="padding:6px;text-align:center;color:var(--blue,#3b82f6);font-weight:700">BASELINE</td>
  </tr>`;

  (fv.individual_removal || []).forEach((r, i) => {
    const bg = i % 2 === 0 ? 'transparent' : 'color-mix(in srgb,var(--bg-raised) 60%,transparent)';
    const evBetter = r.ev_delta > 0;
    const verdict = r.ev_delta > 0.02 ? 'REMOVE' : r.ev_delta < -0.05 ? 'KEEP' : 'NEUTRAL';
    const verdictColor = verdict === 'REMOVE' ? 'var(--green)' : verdict === 'KEEP' ? 'var(--red)' : 'var(--text-muted)';
    html += `<tr style="background:${bg}">
      <td style="padding:6px 10px;color:var(--text-primary)">${r.label}</td>
      <td style="padding:6px;text-align:right;color:var(--text-primary)">${r.n}</td>
      <td style="padding:6px;text-align:right;color:${r.n_added > 0 ? 'var(--green)' : 'var(--text-muted)'}">${r.n_added > 0 ? '+' : ''}${r.n_added}</td>
      <td style="padding:6px;text-align:right;color:${sc(r.wr, baseline.wr, baseline.wr - 0.1, false)}">${(r.wr*100).toFixed(1)}%</td>
      <td style="padding:6px;text-align:right;color:${r.wr_delta >= 0 ? 'var(--green)' : 'var(--red)'}">${r.wr_delta >= 0 ? '+' : ''}${r.wr_delta.toFixed(1)}%</td>
      <td style="padding:6px;text-align:right;font-weight:600;color:${sc(r.ev, baseline.ev, 0, false)}">${r.ev.toFixed(3)}</td>
      <td style="padding:6px;text-align:right;font-weight:600;color:${evBetter ? 'var(--green)' : 'var(--red)'}">${r.ev_delta >= 0 ? '+' : ''}${r.ev_delta.toFixed(3)}</td>
      <td style="padding:6px;text-align:right;color:var(--text-primary)">${r.pf.toFixed(2)}</td>
      <td style="padding:6px;text-align:right;color:${sc(r.max_dd_pct, 15, 30, true)}">${r.max_dd_pct.toFixed(1)}%</td>
      <td style="padding:6px;text-align:center;font-weight:700;color:${verdictColor}">${verdict}</td>
    </tr>`;
  });
  html += '</tbody></table></div>';

  // All combinations table
  html += `<div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:16px;box-shadow:var(--shadow)">
    <div style="font-size:11px;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:10px">All Filter Combinations (2³ = 8 variants, sorted by EV)</div>
    <table style="width:100%;border-collapse:collapse;font-size:12px">
      <thead><tr style="border-bottom:2px solid var(--border)">
        <th style="padding:8px 10px;text-align:left;color:var(--text-muted)">Filter Combination</th>
        <th style="padding:8px 6px;text-align:right;color:var(--text-muted)">N</th>
        <th style="padding:8px 6px;text-align:right;color:var(--text-muted)">WR</th>
        <th style="padding:8px 6px;text-align:right;color:var(--text-muted)">EV (R)</th>
        <th style="padding:8px 6px;text-align:right;color:var(--text-muted)">PF</th>
        <th style="padding:8px 6px;text-align:right;color:var(--text-muted)">Max DD</th>
        <th style="padding:8px 6px;text-align:right;color:var(--text-muted)">Sharpe</th>
        <th style="padding:8px 6px;text-align:right;color:var(--text-muted)">SPD</th>
        <th style="padding:8px 6px;text-align:left;color:var(--text-muted)">EV Bar</th>
      </tr></thead><tbody>`;

  // Determine currently active filter set based on all header toggles
  const activeFilters = [];
  if (activeF3)  activeFilters.push('F3');
  if (activeF4)  activeFilters.push('F4');
  if (activeSmt) activeFilters.push('SMT');
  const _filterLabelMap = {'F3':'Shallow Sweep','F4':'Closed Back Inside','SMT':'NQ-ES Divergence'};
  const activeLabel = activeFilters.map(f => _filterLabelMap[f]).join(' + ');

  const maxEV = Math.max(...combos.map(c => Math.abs(c.ev)));
  combos.forEach((c, i) => {
    const isBest = best && c.label === best.label;
    const isActive = c.label === activeLabel;
    const isCurrent = c.label === baseline.label;
    const bg = isActive ? 'rgba(139,92,246,0.08)' : isBest ? 'rgba(16,185,129,0.06)' : isCurrent ? 'rgba(59,130,246,0.06)' : i % 2 === 0 ? 'transparent' : 'color-mix(in srgb,var(--bg-raised) 60%,transparent)';
    let badge = '';
    if (isActive) badge += ' <span style="font-size:9px;font-weight:700;padding:1px 6px;border-radius:3px;background:rgba(139,92,246,0.15);border:1px solid rgba(139,92,246,0.4);color:#8b5cf6">ACTIVE</span>';
    if (isBest) badge += ' <span style="font-size:9px;font-weight:700;padding:1px 6px;border-radius:3px;background:rgba(16,185,129,0.15);border:1px solid rgba(16,185,129,0.4);color:#10b981">BEST</span>';
    if (isCurrent && !isActive) badge += ' <span style="font-size:9px;font-weight:700;padding:1px 6px;border-radius:3px;background:rgba(59,130,246,0.15);border:1px solid rgba(59,130,246,0.4);color:#3b82f6">DEFAULT</span>';
    const barW = maxEV > 0 ? Math.abs(c.ev) / maxEV * 100 : 0;
    const barColor = c.ev >= 0 ? 'var(--green)' : 'var(--red)';
    html += `<tr style="background:${bg}">
      <td style="padding:6px 10px;color:var(--text-primary);font-weight:${isBest || isActive || isCurrent ? '700' : '400'}">${c.label || 'No Filters'}${badge}</td>
      <td style="padding:6px;text-align:right;color:var(--text-primary)">${c.n}</td>
      <td style="padding:6px;text-align:right;color:${sc(c.wr, 0.80, 0.60, false)}">${(c.wr*100).toFixed(1)}%</td>
      <td style="padding:6px;text-align:right;font-weight:600;color:${sc(c.ev, 0.5, 0, false)}">${c.ev.toFixed(3)}</td>
      <td style="padding:6px;text-align:right;color:${sc(c.pf, 3, 1.5, false)}">${c.pf.toFixed(2)}</td>
      <td style="padding:6px;text-align:right;color:${sc(c.max_dd_pct, 15, 30, true)}">${c.max_dd_pct.toFixed(1)}%</td>
      <td style="padding:6px;text-align:right;color:var(--text-primary)">${c.sharpe != null ? c.sharpe.toFixed(2) : '—'}</td>
      <td style="padding:6px;text-align:right;color:var(--text-muted)">${c.spd}</td>
      <td style="padding:6px"><div style="height:12px;width:${barW}%;background:${barColor};border-radius:2px;opacity:0.6"></div></td>
    </tr>`;
  });
  html += '</tbody></table></div>';

  el.innerHTML = html;
}

export { renderProfileComparison, renderVerdict, renderFilterVariants };
