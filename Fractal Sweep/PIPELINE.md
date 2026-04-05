# Fractal Sweep Pipeline — Complete Architecture

**Last updated:** 2026-04-05

---

## Overview

Statistical backtesting engine for NQ and ES micro futures. Detects fractal sweep + CISD setups across 15 years of 1-minute data, validates with walk-forward regime analysis, Monte Carlo simulation, and cross-instrument SMT divergence — then displays results in an interactive probability dashboard.

**Stack:** Python 3.9+ · DuckDB · pandas · numpy · Pine v5 · standalone HTML (zero CDN deps)

---

## Data Flow

```
Databento API (1m OHLCV)
    ↓
daily_update.py (cron: 7am ET, weekdays)
    ↓
candle_science.duckdb
  ├── nq_1m  (4M+ bars, 2010–present)
  └── es_1m  (4M+ bars, 2010–present)
    ↓
model_stats.py
  ├── load_1m()       → RTH + full-day DataFrames
  ├── resample()      → sweep TF candles (4H/1H/30M)
  ├── resample()      → CISD TF candles (15M/5M/3M)
  ├── df_to_arrays()  → numpy arrays (one pass, reused)
  ├── detect_setups_base() → sweep + CISD + SMT detection
  ├── apply_profile_and_resolve() → exit simulation
  └── build_model_stats() → aggregation by hour/DOW/year/session
    ↓
model_stats.json (all models × all profiles)
    ↓
model_dashboard.html (client-side rendering)
  ├── Overview      → hero tiles, heatmaps, combos, filter waterfall
  ├── MAE Study     → optimal SL, percentiles, KDE
  ├── MFE Study     → PTQ level, p50, structural panel
  ├── Risk          → equity curve, drawdown, Sharpe
  ├── Trades        → filterable trade table (SMT toggle)
  └── Custom Ranges → walk-forward, Monte Carlo, feature attribution,
                      distribution shift, regime analysis, stress testing
```

---

## Database

**File:** `candle_science.duckdb` (gitignored, ~2GB)

| Table | Schema |
|-------|--------|
| `nq_1m` | `timestamp TIMESTAMPTZ, open/high/low/close DOUBLE, volume BIGINT` |
| `es_1m` | Same schema |

Timestamps stored as `TIMESTAMP WITH TIME ZONE` (America/Toronto). Always convert: `timezone('America/New_York', timestamp)`.

---

## The 4 Sweep Models

| Key | Sweep TF | CISD TF | Q1 Window | Min Range |
|-----|----------|---------|-----------|-----------|
| `4H_15M` | 4 Hour | 15 Min | 60 min | 30 pts |
| `1H_5M` | 1 Hour | 5 Min | 15 min | 12 pts |
| `1H_3M` | 1 Hour | 3 Min | 15 min | 12 pts |
| `30M_3M` | 30 Min | 3 Min | 8 min | 8 pts |

**Constants:** `SWEEP_MAX_PCT = 0.50` · `MIN_RISK_PTS = 3.0` · `MAX_RISK_PTS = 112.5` · `CISD_FAST_BARS = None` (unlimited)

---

## Setup Detection (3 Phases)

### Phase 1 — Sweep
Price breaks beyond the prior HTF candle's high or low within Q1. Sweep must be ≤50% of prior range. Prior range ≥ min_range. Sweep extreme (lowest low for long, highest high for short) locked at detection.

### Phase 2 — Return to Range
Price closes back inside the prior candle's range. No deadline — can happen anytime within the HTF period.

### Phase 3 — CISD
Backward scan from the return bar finds the consecutive opposing delivery run. CISD level = open of the earliest candle in that run. Fires when current close crosses through CISD level. Dojis skipped, no bar limit.

**Entry:** Next CISD-TF candle open (backtest) · Current bar close (indicator)

---

## Risk Profiles

### Structural Dynamic
- SL = sweep extreme (1× base_risk)
- TP1 = 1R, 90% exit; runner (10%) with BE stop
- Purpose: baseline for MAE/MFE derivation

### Split 80/20
- SL = min(sweep extreme, MAE p90 of winners)
- TP1 = PTQ level (highest reach_rate where P(pos exit | MFE ≥ X) ≥ 0.70)
- TP2 = p50 MFE, runner (10%) with BE stop
- All targets computed per TF period from structural winners

---

## SMT Divergence

NQ sweeps its HTF level but ES does **not** sweep its corresponding level.

| Component | Implementation |
|-----------|---------------|
| **Backtest** | Loads ES 1m, builds ES sweep-TF candles, checks ES Q1 window at sweep detection. `smt` bool per trade row |
| **Indicator** | 10 ES security calls. "SMT" (green/red) or "NO SMT" (gray) label |
| **Dashboard** | SMT checkbox filter — when checked, all stats recompute from SMT-only trades |

**Results (1H_5M):** SMT = 90.2% WR / 10.2 PF vs non-SMT = 84.4% WR / 6.1 PF

---

## Over-Risk Handling

Setups where `risk_pts > MAX_RISK_PTS (112.5)` are detected but treated differently:

- **Backtest:** Resolved but marked `rejected_by = 'RISK_TOO_LARGE'`
- **Indicator:** Drawn with orange dashed lines, red/teal R:R boxes, "OVER RISK X pts" badge. No alert fired

---

## MAE/MFE & Hourly Normalization

- `mae_pct` / `mfe_pct` — as % of entry price
- `mae_pct_hr` / `mfe_pct_hr` — as % of entry hour's range (regime-independent)
- `hour_range_pts` = high − low of all 1m bars in the trade's (date, hour)

### Recommendation Logic
- **PTQ:** Highest reach_rate where P(positive exit | MFE ≥ X) ≥ 0.70, fallback 0.50
- **opt_sl:** Tightest MAE where P(genuine loss | MAE ≥ X) ≥ 0.70, fallback 0.50

---

## Walk-Forward Regime Analysis

Client-side in `model_dashboard.html`. User defines consecutive date ranges.

1. **Train period:** Derive MAE stop variants (max, p90, p85, p50) + MFE targets (PTQ, p50)
2. **Test period:** Re-resolve trades with each train-derived stop cap
3. **5 stop variants tested:** Structural, Max MAE, P90 MAE, P85 MAE, P50 MAE
4. **Overfitting score:** Test EV / Train EV × 100 — ≥80% = ROBUST, 60-80% = MILD DECAY, <60% = OVERFIT
5. **Best variant:** Lowest CV across pairs (most regime-stable)
6. **Rolling pairs:** R1→R2, R2→R3, R3→R4

---

## Advanced Analysis (Custom Ranges View)

### Monte Carlo Simulation (N=1,000)
- Shuffles actual R values, builds equity curves per ordering
- **Equity fan chart:** p5/p25/p50/p75/p95 confidence bands + actual curve
- **Ruin probability:** P(account ≤ $0)
- **Bootstrap 95% CI** for final equity, WR, EV
- **Max DD distribution:** histogram with p50/p95/actual markers

### Rolling Stability (50-trade window)
- Rolling WR, EV, PF time series with mean reference lines
- **CUSUM chart:** Cumulative performance deviation — upslope = edge active, downslope = degrading

### Feature Attribution
- WR/EV/PF by feature bucket: session, direction, DOW, SMT, classification, sweep %, risk pts
- Sorted by EV with delta-vs-baseline and visual edge bars
- **Hour × Direction conditional EV heatmap** (green/red intensity)

### Distribution Shift Tests (Train vs Test)
- **Wasserstein distance** (earth mover's) for MAE, MFE, R distributions
- **Kolmogorov-Smirnov test** at 95% confidence: PASS/REJECT
- Per-pair verdict: STABLE / MILD SHIFT / REGIME CHANGE

### Regime Analysis
- Rolling 20-trade window classification: Low Vol, High Vol, Trending, Choppy
- Performance cards per regime (WR/EV/PF)
- **Regime transition matrix** — P(next regime | current regime)
- Regime timeline canvas (bars colored by regime, y = R outcome)

### Stress Testing
- **WR degradation table:** 5% decrements from actual WR, showing EV/PF/DD/ruin/viability
- **Adverse streak probability:** 3L through 10L — P(streak), expected occurrences, account survival

---

## Pine v5 Indicator

**File:** `Live Scanner/fractal_sweep_cisd.pine` (971 lines)

Auto-detects chart TF → maps to sweep/CISD combo. Draws sweep lines, CISD lines, R:R boxes, T-Spot zones, CISD projections, SMT labels, over-risk badges.

**35 security calls** (25 NQ + 10 ES). All pre-declared with literal TF strings.

### Visual Hierarchy
| Setup Type | Lines | Boxes | Badge |
|-----------|-------|-------|-------|
| **Q1 valid** | Solid red/blue, width 2 | Red risk + teal reward | — |
| **Non-Q1 valid** | Solid orange/amber, width 2 | Dark red + amber | `*` suffix |
| **Over-risk** | Dashed orange, width 1 | Light red + light teal | OVER RISK X pts |
| **Pending** | Dashed, 75% opacity, width 1 | — | — |

---

## Daily Update Pipeline

**File:** `Fractal Sweep/daily_update.py`

```
Cron (7am ET, weekdays)
  → Query DB for max(timestamp) per table
  → Fetch new bars from Databento API
  → Upsert into candle_science.duckdb
  → Run model_stats.py + other backtests
  → Mac notification (success/error)
```

---

## Aggregation Function

`agg(g)` returns: `n, wins, wr, ev, pf, avg_risk_pts, avg_rr, avg_mae, avg_mfe, avg_mae_hr, avg_mfe_hr`

Applied to: `by_hour`, `by_session`, `by_dow`, `by_year`, `dir_summary`, `tspot_breakdown`, `smt_summary`

---

## Trade Row Fields

| Field | Type | Description |
|-------|------|-------------|
| `date` | str | YYYY-MM-DD |
| `direction` | str | LONG / SHORT |
| `hr`, `mn`, `dow` | int | Entry time components |
| `session` | str | PRE / NY1 / NY2 / OTHER |
| `entry_price` | float | CISD-TF candle open |
| `sweep_extreme` | float | Wick tip (SL level) |
| `risk_pts` | float | |entry − sweep_extreme| |
| `r` | float | R-multiple outcome |
| `outcome` | str | WIN / LOSS / INVALID / SKIP |
| `mae_pct`, `mfe_pct` | float | As % of entry price |
| `mae_pct_hr`, `mfe_pct_hr` | float | As % of hourly range |
| `smt` | bool | SMT divergence flag |
| `classification` | str | DWP / DNP / R1 / R2 |
| `sweep_pct` | float | Sweep / prior range ratio |

---

## Execution

```bash
# Run backtest (all models)
python3 model_stats.py

# Run specific models
python3 model_stats.py --models 1H_5M 1H_3M

# Run for ES
python3 model_stats.py --table es_1m

# Fetch new data
python3 daily_update.py

# Serve dashboard
python3 -m http.server 8001
# → http://localhost:8001/Fractal Sweep/model_dashboard.html
```

---

## File Structure

```
Statistic.ally/
├── Fractal Sweep/
│   ├── candle_science.duckdb      [gitignored]
│   ├── model_stats.py             [backtest engine, 2400 lines]
│   ├── model_stats.json           [pre-computed results]
│   ├── model_dashboard.html       [dashboard, 5600+ lines]
│   ├── daily_update.py            [cron data fetcher]
│   ├── CLAUDE.md                  [project context]
│   └── PIPELINE.md                [this file]
├── Live Scanner/
│   ├── fractal_sweep_cisd.pine    [Pine v5 indicator, 971 lines]
│   └── fractal_sweep_cisd_description.md
├── .claude/rules/fractal-sweep.md [system rules]
└── CLAUDE.md                      [root project config]
```
