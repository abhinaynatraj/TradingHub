# Fractal Sweep Pipeline — Complete Architecture

**Last updated:** 2026-05-15 (slim-JSON migration)

---

## Overview

Statistical backtesting engine for NQ and ES micro futures. Detects fractal sweep + CISD setups across 15 years of 1-minute data, validates with walk-forward regime analysis, Monte Carlo simulation, and cross-instrument SMT divergence — then displays results in an interactive probability dashboard.

**Stack:** Python 3.14 · DuckDB 1.4.4 · pandas · numpy · pyarrow · standalone HTML (zero CDN deps) · local Python HTTP server (`server.py`)

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
  ├── resample()      → sweep TF candles (1H/30M/15M)
  ├── resample()      → CISD TF candles (5M/3M/1M)
  ├── df_to_arrays()  → numpy arrays (one pass, reused)
  ├── detect_setups_base() → sweep + CISD + SMT detection
  ├── apply_profile_and_resolve() → exit simulation per RR_PROFILE
  └── build_model_stats() → aggregation by hour/DOW/year/session
    ↓
    ├── model_stats.json    (aggregate stats only — 29 keys per profile, ~56 MB)
    └── model_stats.parquet (raw trade rows — 49 cols × ~1.4M rows, ~78 MB)
        ↓
server.py
  ├── /data?engine=fractal_sweep&model=X&profile=Y
  │     → slice JSON, return aggregate stats for one profile
  ├── /trades?engine=fractal_sweep&model=X&profile=Y&period=2y|1y|6m|3m|1m|all
  │     → filter parquet by (model_key, sweep_mode, cisd_mode, profile_key)
  │       + exclude EXPIRED + period anchored to MAX(date) → return trade rows
  ├── /trades?...&from=YYYY-MM-DD&to=YYYY-MM-DD
  │     → arbitrary date window (XOR with period=)
  └── /recalc?engine=fractal_sweep   (POST)
        → re-runs the engine subprocess
    ↓
model_dashboard.html (client-side rendering)
  ├── js/data.js: loadTrades + getActiveTrades cache, keyed by (model, profile, period)
  ├── Overview      → hero tiles, heatmaps, combos, filter waterfall
  ├── MAE Study     → optimal SL, percentiles, KDE
  ├── MFE Study     → PTQ level, p50, structural panel
  ├── Risk          → equity curve, drawdown, Sharpe
  ├── Trades        → filterable trade table (period-scoped)
  └── Custom Ranges → walk-forward, Monte Carlo, feature attribution,
                      distribution shift, regime analysis, stress testing
```

**Slim-JSON migration (2026-05-15).** Engine previously wrote ~270 MB of `recent_trades` arrays into `model_stats.json`. Migration stripped those out — JSON shrunk to ~56 MB, parquet became the canonical trade-row source. Frontend `loadTrades(fullKey, profile, period)` cache replaces all `D.recent_trades` reads. See `docs/superpowers/specs/2026-05-15-fractal-sweep-slim-json-design.md` and PR #15.

---

## Database

**File:** `candle_science.duckdb` (gitignored, ~2GB)

| Table | Schema |
|-------|--------|
| `nq_1m` | `timestamp TIMESTAMPTZ, open/high/low/close DOUBLE, volume BIGINT` |
| `es_1m` | Same schema |

Timestamps stored as `TIMESTAMP WITH TIME ZONE` (America/Toronto). Always convert: `timezone('America/New_York', timestamp)`.

---

## The 3 Sweep Models

| Key | Sweep TF | CISD TF |
|-----|----------|---------|
| `1H_5M` | 1 Hour | 5 Min |
| `30M_3M` | 30 Min | 3 Min |
| `15M_1M` | 15 Min | 1 Min |

**Constants:** `MIN_RISK_PTS = 3.0` · `MAX_RISK_PTS = 112.5` (= MNQ $225 / $2/pt) · `OUTCOME_MAX_BARS = 1440` (24h)

**Engine ↔ Indicator alignment (2026-04-24):** Sweep, return-to-range, and CISD-fire must all occur within the same anchor HTF window. Same-bar TP/SL ties resolve to SL. Outcome window bumped from 360 to 1440 bars to match the indicator's effectively-unlimited resolution lifetime. A pandas resolution bug ([ns] vs [us]) that silently inflated anchor windows from 1h to 41 days was fixed at the same time — that was the root cause of the previously-reported ~70% baseline WR.

---

## Setup Detection (3 Phases)

### Phase 1 — Sweep
Price breaks beyond the prior HTF candle's high or low at any point within the current anchor HTF window. Sweep extreme (lowest low for long, highest high for short) locked at detection.

### Phase 2 — Return to Range
Price closes back inside the prior candle's range. Must happen within the same anchor HTF window.

### Phase 3 — CISD
Backward scan from the return bar finds the consecutive opposing delivery run. CISD level = open of the earliest candle in that run. Fires when current close crosses through CISD level. Dojis skipped. **CISD must fire within the same anchor HTF window** — setups not completing before the next anchor are discarded.

**Entry:** Next CISD-TF candle open (both engine and indicator)

---

## Risk Profiles (`RR_PROFILES` in `engine/model_stats.py`)

25 profiles total: 24 trade-resolving profiles (3 R-targets × 4 entry modes × 2 target refs) + 1 measurement-only profile.

| profile_type | Example keys | Stop / Target |
|---|---|---|
| `mult` | `simple_1r`, `simple_1r5`, `simple_2r` | Market entry, TP from entry, 1R/1.5R/2R |
| `mult` | `ob_1r`, `ob_1r5`, `ob_2r` | Market entry, TP from CISD OB open, 1R/1.5R/2R |
| `mult` | `l33_1r`, `l50_1r`, `l66_1r` (and `_1r5`/`_2r` variants) | L33/L50/L66 limit entries (cascade between OB and SL) |
| `mult` | `l33_ob_1r`, `l50_ob_1r`, `l66_ob_1r` (and variants) | L33/L50/L66 limit entries with OB-based target |
| `raw` | `raw_measure` | No SL/TP — full-session MAE/MFE only, `outcome='MEASURED'` |

`simple_1r` drives the default Overview hero cards. `raw_measure` is measurement-only for MAE/MFE distribution studies.

All 25 are written to both `model_stats.json` (per-profile aggregates) and `model_stats.parquet` (per-profile trade rows, partitioned by `profile_key` column).

---

## Runtime Filters (3, dashboard-toggleable, all default OFF)

The dashboard's filter bar renders three chips. Each chip shows a live `±N` badge indicating how many trades would be added or removed if toggled.

| Chip | Code | What it requires | Standalone edge |
|---|---|---|---|
| Shallow Sweep | `F3` | `sweep_ext / ref_range ≤ 0.50` | +3.4% WR · +0.061R EV |
| Closed Back Inside | `F4` | `ret_close` is inside the prior candle's range | Noise (helpful in combo) |
| **NQ-ES Divergence** | `SMT` | NQ swept but ES did not sweep its corresponding level | **+7.8% WR · +0.150R EV** (strongest single filter) |

**Combinatorics.** `compute_filter_variants()` enumerates 2³ = 8 combinations per model × profile, sorted by EV.

**SMT backtest.** Loads `es_1m` alongside `nq_1m`, builds ES sweep-TF candles, checks the ES window at NQ sweep detection time. Pine indicator implements the same logic via `request.security` on the ES symbol.

**Toggle scope.** Filters work on every Period selection (All Time + 2y/1y/6m/3m/1m). `_compute_by_tf` builds aggregate stats per sub-slice from `wl_full`. Filter-chip recomputation re-aggregates trade rows client-side from the `loadTrades` cache (populated from `/trades?period=...`) — toggling restores rejected trades within that period without server roundtrip.

### Best practical combo (over 12y NQ, baseline ~50% WR)

| Combo | Model | WR | EV | N |
|---|---|---|---|---|
| F3 + F4 + SMT | 1H_5M | 59.1% | +0.182R | 1,711 (~143/yr) |
| F3 + F4 + SMT | 30M_3M | 58.6% | +0.172R | 3,234 (~270/yr) |

**Removed (2026-04-24):** HOUR_ALIGNED, PRIOR_COUNTER, PRIOR_ENGULFING and experimental H4_BIAS / DAILY_BIAS / PD_LIQUIDITY / P12_BIAS were all tested over 12y and removed — none had standalone edge.

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

## Pine Indicator

Lives in `Fractal Sweep/pine/fractal_sweep.pine` (indicator) and `pine/fractal_sweep_strategy.pine` (strategy version). Auto-detects chart TF → maps to sweep/CISD combo. Draws sweep lines, CISD lines, R:R boxes, T-Spot zones, SMT labels, over-risk badges.

### Visual Hierarchy
| Setup Type | Lines | Boxes | Badge |
|-----------|-------|-------|-------|
| **Q1 valid** | Solid red/blue, width 2 | Red risk + teal reward | — |
| **Non-Q1 valid** | Solid orange/amber, width 2 | Dark red + amber | `*` suffix |
| **Over-risk** | Dashed orange, width 1 | Light red + light teal | OVER RISK X pts |
| **Pending** | Dashed, 75% opacity, width 1 | — | — |

---

## Daily Update Pipeline

**File:** `Fractal Sweep/engine/daily_update.py`

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
| `risk_pts` | float | \|entry − sweep_extreme\| |
| `r` | float | R-multiple outcome |
| `outcome` | str | WIN / LOSS / INVALID / SKIP |
| `mae_pct`, `mfe_pct` | float | As % of entry price |
| `mae_pct_hr`, `mfe_pct_hr` | float | As % of hourly range |
| `hour_range_pts` | float | High − low of 1m bars in entry (date, hour) |
| `smt` | bool | NQ-ES Divergence flag |
| `cisd_aligned` | bool | CISD close on correct side of hour open |
| `prior_counter_close` | bool | Prior sweep-TF bar closed against trade direction |
| `prior_engulfing` | bool | Prior sweep-TF bar engulfs its predecessor (wick-inclusive) |
| `passes_f3`, `passes_f4` | bool | Whether trade passes the Shallow Sweep / Closed Back Inside filters |
| `classification` | str | DWP / DNP / R1 / R2 |
| `sweep_pct` | float | Sweep / prior range ratio |

---

## Execution

```bash
# Run backtest (all models) — writes model_stats.json + model_stats.parquet to this folder
python3 engine/model_stats.py

# Run specific models
python3 engine/model_stats.py --models 1H_5M

# Run for ES
python3 engine/model_stats.py --table es_1m

# Run the test suite (346 pass, 20 skipped as of 2026-05-15)
python3 -m pytest tests/ -q

# Regenerate the drift-gate snapshot (after engine changes that shift trade counts)
python3 tests/gen_no_drift_snapshot.py

# Serve dashboard — use server.py (NOT python3 -m http.server) so /data, /trades, /recalc work
cd ..
python3 server.py
# → http://localhost:8001/Fractal Sweep/model_dashboard.html
```

---

## File Structure

```
Statistic.ally/
├── server.py                                [local server: static files + /data, /trades, /recalc]
├── Fractal Sweep/                           [sweep+CISD engine, F1 removed]
│   ├── candle_science.duckdb                [gitignored, ~550 MB]
│   ├── model_stats.json                     [aggregate stats, gitignored, ~56 MB]
│   ├── model_stats.parquet                  [trade rows, gitignored, ~78 MB — served via /trades]
│   ├── model_dashboard.html                 [dashboard, ~6700 lines]
│   ├── engine/                              [Python backtest code]
│   │   ├── model_stats.py                   [backtest engine, ~2700 lines]
│   │   ├── daily_update.py                  [cron data fetcher]
│   │   ├── install_cron.sh                  [cron setup helper]
│   │   ├── master_backtester.py             [supporting tool]
│   │   ├── sltp_analyzer.py                 [supporting tool]
│   │   └── recalc.py                        [supporting tool]
│   ├── js/                                  [frontend modules]
│   │   ├── data.js                          [loadTrades cache + getActiveTrades + getFilteredD]
│   │   ├── app.js                           [render orchestration + recalc flow]
│   │   ├── verdict.js                       [profile comparison + verdict panel]
│   │   ├── walkforward.js                   [custom-range walk-forward analysis]
│   │   ├── charts.js                        [equity, heatmap, R-distribution charts]
│   │   └── tabs/                            [overview, trades, edge, excursion, filters]
│   ├── pine/                                [TradingView scripts]
│   ├── data/                                [gitignored Databento .dbn dumps]
│   ├── docs/                                [standalone analysis write-ups]
│   ├── assets/                              [images]
│   ├── tests/                               [pytest suite]
│   │   ├── test_no_drift.py                 [drift gate — parquet aggregates vs snapshot]
│   │   ├── test_trades_endpoint.py          [/trades XOR validation + period anchoring + mtime cache]
│   │   ├── gen_no_drift_snapshot.py         [regenerate snapshot from current parquet]
│   │   └── fixtures/no_drift_snapshot.json  [committed baseline for drift gate]
│   ├── CLAUDE.md                            [project context]
│   ├── PIPELINE.md                          [this file]
│   ├── LEGACY_NOTE.md                       [earlier-era history from the Legacy snapshot]
│   └── README.md                            [setup + usage guide]
├── .claude/rules/fractal-sweep.md           [system rules — scoped to this folder]
└── CLAUDE.md                                [root project config]
```
