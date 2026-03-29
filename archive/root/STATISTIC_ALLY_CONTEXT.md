# Statistic.ally — Complete Project Context
> Last updated 2026-03-26. NQ/ES futures research hub. 15+ years of 1-minute bar data.

---

## 1. Repository

| Item | Value |
|---|---|
| Local path | `/Users/abhi/Downloads/Statistic.ally` |
| Git remote | `https://github.com/abhinaynatraj/TradingHub.git` |
| Branch | `main` |
| Python | 3.9+ |
| Key deps | `duckdb pandas numpy openpyxl` |

---

## 2. Serving

All dashboards use `fetch()` and break on `file://`. Always serve from repo root:

```bash
cd /Users/abhi/Downloads/Statistic.ally
python3 -m http.server 8001
# Hub → http://localhost:8001
```

---

## 3. Database

| Item | Value |
|---|---|
| File | `Fractal Sweep/candle_science.duckdb` (gitignored, large) |
| Tables | `nq_1m`, `es_1m` |
| Schema | `timestamp TIMESTAMPTZ, open, high, low, close DOUBLE, volume BIGINT` |
| Timezone | Always convert: `timezone('America/New_York', timestamp)` |
| Connect | `duckdb.connect(str(DB_PATH), read_only=True)` |
| DB path constant | `Path(__file__).parent.parent / 'Fractal Sweep' / 'candle_science.duckdb'` |
| DOW note | Python `0=Mon…4=Fri`; DuckDB `dow` uses `0=Sun` |

---

## 4. Project Structure

```
Statistic.ally/
├── index.html                              ← Hub page
├── mae_mfe_guide.html                      ← MAE/MFE reference
├── wolfpack.html
├── generate_classification.py
├── CLAUDE.md
├── Fractal Sweep/
│   ├── model_dashboard.html                ← Sweep dashboard
│   ├── model_stats.py                      ← Backtest engine → model_stats.json
│   ├── daily_update.py                     ← Databento cron fetcher
│   ├── candle_science.duckdb               ← Shared DB (gitignored)
│   └── [various analysis scripts]
├── NY1 FPFVG/
│   ├── index.html                          ← NY1 dashboard
│   ├── ny1_backtest.py                     ← Backtest engine → ny1_results.json
│   ├── ny1_results.json                    ← Pre-computed (committed)
│   ├── 1stfvg_phase1_collector_v2.py       ← Phase 1: collect setups per day
│   ├── 1stfvg_phase2_grid_search_v3.py     ← Phase 2: grid search SL/TP
│   ├── daily_classifier.py                 ← Day type classifier
│   ├── master_backtester.py                ← 636-combo brute-force ranker
│   ├── fixed_profile_scan.py               ← Fixed-% stop/TP scanner
│   ├── recalc.py                           ← Recalculate combos from Excel
│   ├── sltp_analyzer.py                    ← Per-classification deep analysis
│   ├── export_trades.py                    ← Excel trade log exporter
│   └── ny1_fpfvg_strategy.pine             ← TradingView PineScript
└── TTrades Fractal Model Analysis/
    ├── index.html                          ← TTrades dashboard
    ├── ttfm_backtest.py                    ← Backtest engine → ttfm_results.json
    └── ttfm_results.json                   ← Pre-computed (committed)
```

---

## 5. Theme System

All pages share one localStorage key: `hub-theme` → `'dark'` | `'light'`

- **Never** introduce per-page theme keys
- Button is always in the **top-right** of the nav/header bar, same position on all pages
- Icon: `☀` (in dark mode) / `☾` (in light mode)
- CSS class: `.theme-btn` (hub, NY1) or `.theme-toggle` (TTrades, Fractal Sweep) — same visual style

```javascript
// Pattern used by hub + NY1 FPFVG
function toggleTheme() {
  const t = localStorage.getItem('hub-theme') === 'light' ? 'dark' : 'light';
  localStorage.setItem('hub-theme', t);
  document.body.classList.toggle('light', t === 'light');
  document.getElementById('themeBtn').textContent = t === 'dark' ? '☀' : '☾';
}
```

---

## 6. Hub Dashboard (`index.html`)

Entry point for all three projects. Shows a card per project with 3 live stats pulled from each project's JSON.

**Adding a new project card:**
1. Add entry to `PROJECTS` array: `{ id, title, subtitle, desc, json, link, color, icon, type }`
2. Add `if (project.type === 'yourtype')` block in `loadStats()` returning `{ label1, val1, cls1, label2, val2, cls2, label3, val3, cls3, dateRange }`
3. `cls` values: `'pos'` (green), `'neg'` (red), `'neutral'`

NY1 card shows top-4 combos ranked by weighted composite score (from `SLTP_DATA`).

---

## 7. NY1 F.P.FVG Model

### 7a. Trade Logic

**Detection window:** 9:31–9:59 ET (9:30 bar excluded)

**FVG criteria (3-candle pattern):**
- Bullish: C1.low > C3.high (gap between C1 bottom and C3 top)
- Bearish: C1.high < C3.low
- C2 body filter: C2 must be green for bullish FVG, red for bearish FVG
- Only the **first** qualifying FVG of the session is used

**Entry:**
- Long: enter at C3.low
- Short: enter at C3.high
- Fill window: C3+1 bar through 16:00 ET (first bar that touches entry price)

**Structural stop (cashflow model):**
- Long: stop = min(C1.low, C2.low)
- Short: stop = max(C1.high, C2.high)

**Fixed-% stop/TP profiles:**
- Entry at fill price, stop = entry ± stop_pct%, TP = entry ± tp_pct%

**TP1 (cashflow):** Fixed 10 bps = 0.10% from entry (`TP1_BPS = 0.001`)

**Sizing:** `$225/trade` risk, `$4,500` account → fixed fractional (stop-out = exactly $225)

### 7b. Key Constants (`ny1_backtest.py`)

```python
TP1_BPS        = 0.001    # 10 bps = 0.10%
MIN_RISK_PTS   = 0.25     # guard against zero-risk setups
TICK_SIZE      = 0.25     # NQ tick size
ACCOUNT_SIZE   = 4500     # account ($)
RISK_PER_TRADE = 225      # risk per trade ($)
```

### 7c. Top 10 PCT Profiles (ranked by weighted composite score — blown excluded)

**Ranking weights:** Sharpe 25% · PF 20% · EV 15% · SQN 15% · MaxDD 10% · RoR 10% · CE 5%
**Streak/MCL excluded** from scoring — irrelevant for automated systems.
**Blown combos removed:** `pct_010_005`, `pct_010_006`, `pct_005_007` all blow in the NY1 model despite appearing safe in the FVG2_FIXED spreadsheet (different trade populations).

| Rank | Key | SL % | TP % | R:R | EV(R) | PF | CE | Max DD |
|---|---|---|---|---|---|---|---|---|
| 1 | pct_005_006 | 0.05% | 0.06% | 1.20 | 0.225 | 1.507 | 0.339 | 44.0% |
| 2 | pct_004_006 | 0.04% | 0.06% | 1.50 | 0.234 | 1.462 | 0.342 | 5.0% |
| 3 | pct_005_008 | 0.05% | 0.08% | 1.60 | 0.240 | 1.459 | 0.351 | 19.0% |
| 4 | pct_004_008 | 0.04% | 0.08% | 2.00 | 0.257 | 1.442 | 0.370 | 5.0% |
| 5 | pct_004_007 | 0.04% | 0.07% | 1.75 | 0.243 | 1.444 | 0.351 | 5.0% |
| 6 | pct_005_009 | 0.05% | 0.09% | 1.80 | 0.247 | 1.446 | 0.357 | 40.0% |
| 7 | pct_003_006 | 0.03% | 0.06% | 2.00 | 0.252 | 1.433 | 0.362 | 5.0% |
| 8 | pct_005_005 | 0.05% | 0.05% | 1.00 | 0.206 | 1.519 | 0.313 | 60.0% |
| 9 | pct_004_005 | 0.04% | 0.05% | 1.25 | 0.205 | 1.441 | 0.295 | 10.0% |
| 10 | pct_003_005 | 0.03% | 0.05% | 1.67 | 0.206 | 1.377 | 0.284 | 5.0% |

**Max DD** = `max(0, $4,500 − min_equity_usd)` — how far below initial balance the account fell (not peak-to-trough). True peak-to-trough max DD is larger for combos that rose above initial first.

**Cashflow model:** Structural stop, 10bps TP, 1:1 R. WR ≈ 56.2%, EV(R) = +0.309, PF = 1.893.

**Grade thresholds** (from FVG2 Metadata sheet):
| Grade | EV(R) | PF | CE | RoR% |
|---|---|---|---|---|
| A | >0.40 | ≥2.0 | ≥0.70 | <1% |
| B | 0.25–0.40 | 1.6–1.99 | 0.40–0.69 | 1–5% |
| C | 0.10–0.25 | 1.4–1.59 | 0.20–0.39 | 5–10% |
| D | 0.01–0.10 | 1.2–1.39 | — | 10–20% |
| F | ≤0 | <1.2 | <0.20 | >20% |

### 7d. Classification Buckets

Day type is classified daily using `daily_classifier.py`:

| Bucket | Meaning |
|---|---|
| DWP | Directional With Pullback |
| DNP | Directional No Pullback |
| R1 | Range Day Type 1 |
| R2 | Range Day Type 2 |
| Unclassified | Does not fit above |

Per-classification performance data is embedded in `SLTP_DATA` in `index.html`.

### 7e. Script Pipeline

```
Step 0: daily_classifier.py          → classifies each day as DWP/DNP/R1/R2/Unclassified
Step 1: 1stfvg_phase1_collector_v2.py → scans for FVGs, records setup + result per day
                                        Output: FVG_Phase1_v2_YYYYMMDD_HHMMSS.xlsx
Step 2: 1stfvg_phase2_grid_search_v3.py → grid search over SL/TP combos on Phase 1 data
Step 3: master_backtester.py         → brute-force 636 combos; ranks by CE
                                        (also uses TV Backtester template + recalc.py)
Step 4: sltp_analyzer.py             → deep per-classification analysis for top combos
                                        Input: Phase 1 xlsx + DuckDB (1-min OHLC)
                                        Output: FVG2_FIXED_*.xlsx with charts + trade log
Step 5: ny1_backtest.py              → full backtest → ny1_results.json
```

**Run backtest:**
```bash
cd "NY1 FPFVG"
python3 ny1_backtest.py              # NQ (default)
python3 ny1_backtest.py --table es_1m  # ES
```

### 7f. ny1_results.json Structure

```json
{
  "all": {
    "cashflow":          { "meta": {...}, "overall": {...}, "by_dow": {...}, "by_year": {...},
                           "by_direction": {...}, "risk_stats": {...}, "recent_trades": [...] },
    "pct_004_008":       { ... },
    ...
  },
  "2y":  { "cashflow": {...}, "pct_004_008": {...}, ... },
  "1y":  { ... },
  "6m":  { ... },
  "3m":  { ... },
  "1m":  { ... }
}
```

`risk_stats` keys: `ror, max_consec_wins, max_consec_losses, sharpe, mae_median, mfe_median, account_size, risk_per_trade, trades, wins, losses, be_count, avg_win_usd, avg_loss_usd, min_equity_usd, blown, sl_pct, tp_pct, ce, mae_bell`

`recent_trades` fields: `date, time, dow, dow_name, yr, mo, direction, c1_ts, c2_ts, c3_ts, fvg_top, fvg_bot, entry, stop, tp1, risk_pts, mae_pct, fill_hr, fill_mn, mfe1_pct, mfe2_pct, runner_exit_price, runner_outcome, outcome_main, combined_r, pct_stop, pct_tp`

Only `all` timeframe includes the full `trades` array. Shorter timeframes have `recent_trades` only.

### 7g. Dashboard (`NY1 FPFVG/index.html`)

**Dropdowns:**
- Timeframe: All Time / 2Y / 1Y / 6M / 3M / 1M → `_activeTF`, calls `switchTF(tf)`
- Model: Top 10 PCT combos + Cashflow (Reference Models) → `_activeModel`, calls `switchModel(key)`

**Key JS variables:**
```javascript
let _data = null;         // full parsed ny1_results.json
let _activeTF = 'all';    // current timeframe key
let _activeModel = 'pct_005_006';  // current model key (default = #1 combo)
```

**`SLTP_DATA` constant** (hardcoded all-time stats for hero tiles + rankings):
```javascript
const SLTP_DATA = {
  pct_005_006: {   // #1 combo
    label, sl, tp, rr, ev_r, pf, ce, mcl, mcw,
    combined: { n, wr, pl, sharpe, blown },
    DWP:      { n, wr, pl, sharpe, blown },
    DNP:      { n, wr, pl, sharpe, blown },
    R1:       { n, wr, pl, sharpe, blown },
    R2:       { n, wr, pl, sharpe, blown },
    Unclassified: { n, wr, pl, sharpe, blown }
  },
  // ... pct_004_006 through pct_003_005 (10 total, all non-blown)
  cashflow: { ... },
}
```

**Important:** When updating PCT_PROFILES in `ny1_backtest.py`, you must also update ALL of:
1. `<select>` dropdown options (values + labels)
2. `SLTP_DATA` object (all combo keys + per-classification stats)
3. `let _activeModel` default
4. `keys` array in `renderRankingsTable()`

Stats for `SLTP_DATA` come from: `FVG2_0325_2135_M11A.xlsx` leaderboard sheets (n, wr, pl, sharpe, blown per classification) and `FVG2_FIXED_0325_2224_JS2Q.xlsx` (ev_r, pf, ce, mcl, mcw for the 7 original combos).

**Hero stats** read from `_data[_activeTF][_activeModel]` (live JSON) for WR, P&L, Sharpe, Blown, streaks. EV(R) and PF computed from live data. CE shown from SLTP_DATA (all-time reference).

**Risk stats row** includes: SL%, TP%, R:R, Blown, **Max DD**, Max W Run, Max L Run.
Max DD = `max(0, account_size − min_equity_usd)` from `risk_stats`. Color: green <20%, amber 20–50%, red ≥50%.

**Recent Trades table columns:**
Date | Contract | FVG Time | Entry | Entry $ | Dir | Stop $ | MAE (%) | MFE (%) | TP $ | TP1

- Contract computed client-side by `nqContract(dateStr)` → rolls on 3rd Friday of Mar/Jun/Sep/Dec
- Table is sortable by clicking column headers

**Render functions:**
- `renderAll(d)` — master, calls everything
- `renderHero(meta, rs)` — hero stat tiles
- `renderClassificationGrid()` — 5-card DWP/DNP/R1/R2/Unclassified grid
- `renderRankingsTable()` — all 10 combos + cashflow side-by-side
- `renderDirection(d.by_direction)`
- `renderCharts(d)` — equity curve, MAE bell, DOW bar, MFE scatter
- `renderYearTable(d.by_year)`
- `renderMAEAnalysis(d.risk_stats)`
- `renderTradesTable(d.recent_trades || d.trades)`

---

## 8. Fractal Sweep Model

**Setup:** Prior candle swept in Q1 → price returns inside range → CISD confirms
**Entry:** Next candle open | **Stop:** Sweep extreme | **Target:** 2R (1:2)
**RTH window:** 07:00–16:00 ET

**4 model variants:**

| Key | Sweep TF | CISD TF | Q1 Window |
|---|---|---|---|
| 4H_15M | 4 Hour | 15 Min | First 1h |
| 1H_5M | 1 Hour | 5 Min | First 15m |
| 1H_3M | 1 Hour | 3 Min | First 15m |
| 30M_3M | 30 Min | 3 Min | First 8m |

**Key constants:** `SWEEP_MIN_PCT = 0.10`, `SWEEP_MAX_PCT = 1.50`, `CISD_FAST_BARS = 8`

**Refinement filters F1–F5:** Prior range floor, sweep min size, sweep max cap, close-back required, CISD speed (applied cumulatively)

**Run:**
```bash
cd "Fractal Sweep"
python3 model_stats.py                         # all 4 models → model_stats.json
python3 model_stats.py --models 1H_5M 1H_3M   # specific models
python3 model_stats.py --table es_1m           # ES instead of NQ
python3 daily_update.py                        # fetch new bars from Databento
python3 -m http.server 8000                    # serve on port 8000
```

Dashboard: `http://localhost:8001/Fractal%20Sweep/model_dashboard.html`
Loads `model_stats.json` via file picker (⚠ Demo Data badge shown until loaded).

---

## 9. TTrades Fractal Model (TTFM°)

**Setup:** 1H sweep of prior candle high/low creates T-Spot zone (sweep candle body)
**Entry:** Touch of T-Spot zone later same day
**Stop:** Above/below sweep extreme | **Target:** Fixed R:R multiple (default 2.0)
**Min risk:** 5.0 pts | **Max hold:** 240 bars

**6 variants:** Normal / Expansive / ProTrend × Bull / Bear

**Run:**
```bash
cd "TTrades Fractal Model Analysis"
python3 ttfm_backtest.py                    # default → ttfm_results.json
python3 ttfm_backtest.py --htf 240 --rr 1.5
python3 ttfm_backtest.py --min-risk 3 --max-hold 120
```

Dashboard: `http://localhost:8001/TTrades%20Fractal%20Model%20Analysis/index.html`

---

## 10. Analysis Conventions

- **Reference point:** `close` of the anchor candle
- **Scan window:** anchor+1 bar through 16:00 ET same day
- **Expired setups:** Excluded from WR/EV but counted in total output
- **Fixed fractional sizing:** Risk exactly $225 per trade regardless of stop distance
- **CE (Certainty Equivalent):** Used as primary ranking metric in master backtester
- **EV(R):** Expected value per R = WR × RR − (1 − WR)
- **PF (Profit Factor):** Gross wins ÷ gross losses

---

## 11. Excel Analysis Files (`NY1 FPFVG/`)

| File | Description |
|---|---|
| `FVG2_0325_2135_M11A.xlsx` | Master leaderboard — 636 combos × 6 classifications. Contains Sharpe, PF, CE, RoR, MCL, MCW, Blown per sheet. Source for SLTP_DATA classification stats. |
| `FVG2_0325_2135_M11A_BACKTESTER_OUTPUT.xlsx` | 168 survivors after hard filters (Blown + LowEq≤0 + RoR=F + Streak=F). Sheets: BEST PROFILES (Combined only), Metadata (grade scales), Raw Data. |
| `FVG2_FIXED_0325_2224_JS2Q.xlsx` | 60 sheets = 10 SL/TP combos × 6 classifications. Full per-sheet stats (Sharpe, SQN, DD%, RoR, CE, MCL, MCW, all trades). Source for SQN/Sharpe/MaxDD. |
| `FVG2_FIXED_0325_2224_JS2Q_RANKED.xlsx` | **Generated ranking file.** Rankings sheet + all 60 sheets reordered by weighted composite score. Has EV/PF/CE/RoR grade columns. |

**JS2Q sheet stat row locations** (read by ranked script):
- Row 14: EV R · Row 16: Profit Factor · Row 17: Comb Edge · Row 18: SQN · Row 19: Sharpe
- Row 21: RoR % · Row 23: DD % (max from peak, not initial)

---

## 12. Combo Ranking Methodology

**Weighted composite score** (used to order PCT_PROFILES):
| Metric | Weight | Direction |
|---|---|---|
| Sharpe | 25% | higher = better |
| PF | 20% | higher = better |
| EV(R) | 15% | higher = better |
| SQN | 15% | higher = better |
| Max DD% | 10% | lower = better |
| RoR% | 10% | lower = better |
| CE | 5% | higher = better |

All metrics min-max normalized across the population, then weighted sum. Final score = 95% weighted + 5% gate bonus (avg of EV/PF/CE/RoR letter grades, A=4→F=0, divided by 16).

**Blown filter:** Any combo where `risk_stats.blown = True` in `ny1_results.json` (all-time) is excluded from PCT_PROFILES. Note: blown status differs between FVG2_FIXED spreadsheet model and the NY1 backtest model — always check `ny1_results.json` not the spreadsheet.

---

## 13. Recent Changes (as of 2026-03-26)

| Commit | Change |
|---|---|
| `95cffac` | NY1: reorder + expand recent trades table columns |
| `659d55e` | Fix: hero stats now update with timeframe selection |
| `9d9805d` | NY1: add timeframe selector (All / 2Y / 1Y / 6M / 3M / 1M) |
| `aa6fade` | Hub: show only top 4 combos on NY1 card |
| `8143962` | Hub: replace NY1 profile table with full 10-combo rankings |
| `cec59a5` | NY1: add cashflow model + top-10 PCT combo redesign (SLTP_DATA, classification grid) |

**Session changes (uncommitted):**
- Theme toggle synchronized across all 4 pages (same position, same ☀/☾ style)
- NY1 trades table: Contract column added (`nqContract()` helper)
- NY1 nav: fixed missing `</div>` closing nav-links
- NY1 hero: Max DD tile added to risk stats row
- NY1 PCT_PROFILES: reranked by weighted composite score, blown combos removed
- NY1 SLTP_DATA: fully rebuilt for new 10 combos (3 new: pct_005_005, pct_004_005, pct_003_005)
- Created `FVG2_FIXED_0325_2224_JS2Q_RANKED.xlsx` with Rankings sheet + weighted sort

---

## 14. Key Formulas

**NQ contract from date (JS):**
```javascript
function nqContract(dateStr) {
  const d = new Date(dateStr + 'T12:00:00');
  const y = d.getFullYear();
  for (const [mo, code] of [[2,'H'],[5,'M'],[8,'U'],[11,'Z']]) {
    const first = new Date(y, mo, 1);
    const fri1  = (5 - first.getDay() + 7) % 7;
    const tf    = new Date(y, mo, 1 + fri1 + 14); // 3rd Friday = expiry
    if (d < tf) return `NQ${code}${String(y).slice(-2)}`;
  }
  return `NQH${String(y + 1).slice(-2)}`;
}
```

**Sharpe ratio (annualised by day, Python):**
```python
daily_pnl = [sum R per day × RISK_PER_TRADE]
sharpe = (mean(daily_pnl) / std(daily_pnl)) * sqrt(252)
```

**Position size:**
```python
units = RISK_PER_TRADE / risk_pts  # contracts (can be fractional)
win_usd  = units × tp_pts
loss_usd = -RISK_PER_TRADE         # always exactly $225
```

---

## 15. Common Commands

```bash
# Start hub server
cd /Users/abhi/Downloads/Statistic.ally && python3 -m http.server 8001

# Regenerate NY1 results
cd "NY1 FPFVG" && python3 ny1_backtest.py

# Regenerate Sweep results
cd "Fractal Sweep" && python3 model_stats.py

# Regenerate TTrades results
cd "TTrades Fractal Model Analysis" && python3 ttfm_backtest.py

# Commit + push
git add -A && git commit -m "message" && git push origin main
```

---

## 16. Gitignore'd Files (never committed)

- `Fractal Sweep/candle_science.duckdb` — primary database (~large)
- `*.dbn`, `*.parquet`, `*.csv` — raw data files
- `*.xlsx` — Excel analysis outputs
- `fixed_scan_results.json` — intermediate scan output
