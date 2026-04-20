---
paths:
  - "Fractal Sweep/**"
---

# Fractal Sweep Rules

Sweep+CISD backtesting engine. F1 (min prior range) and the Q1 window gate are removed — detection runs over the full HTF period. Setup-quality filters (F3 shallow sweep, F4 close-back) are runtime-toggleable from the dashboard, not baked-in rejections.

## Engine

```bash
python3 model_stats.py                          # all 4 sweep models → model_stats.json
python3 model_stats.py --models 1H_5M 1H_3M    # subset
python3 model_stats.py --table es_1m            # ES instead of NQ
python3 daily_update.py                         # fetch new bars from Databento
python3 -m pytest tests/ -q                     # test suite
```

## 4 Sweep Models

| Key | Sweep TF | CISD TF |
|---|---|---|
| `4H_15M` | 4 Hour | 15 Min |
| `1H_5M` | 1 Hour | 5 Min |
| `1H_3M` | 1 Hour | 3 Min |
| `30M_3M` | 30 Min | 3 Min |

## Constants (`model_stats.py`)

- `SWEEP_MAX_PCT = 0.50` — now a runtime-toggleable reference, not a baked rejection
- `CISD_FAST_BARS = None` — no bar limit, CISD can form anytime after sweep returns
- `MIN_RISK_PTS = 3.0`, `MAX_RISK_PTS = 112.5` (MNQ $225 ÷ $2.00/pt)
- `OUTCOME_MAX_BARS = 360`
- `long_base`/`short_base` separated from `max_risk` check — enables over-risk detection

## Risk Profiles

| Key | profile_type | Description |
|---|---|---|
| `simple_1r` | `mult` | SL = sweep extreme (1× base_risk); TP = 1R (100% exit). Default. |
| `raw_measure` | `raw` | No SL/TP — records full-session MAE/MFE only, `outcome='MEASURED'` |

## Runtime Filter Fields on Each Trade Row

Beyond `outcome`/`r`/`mae_pct`/`mfe_pct`/`smt`, each row carries:
- `cisd_close`, `cisd_hour_open`, `cisd_aligned` — for HOUR_ALIGNED filter
- `prior_counter_close` — for PRIOR_COUNTER_CLOSE filter
- `prior_engulfing` — for PRIOR_ENGULFING filter
- `passes_f3`, `passes_f4` — for Shallow Sweep / Closed Back Inside filters

## Runtime Filters (6, dashboard-toggleable)

**Setup Quality** (default ON)
- `F3_SWEEP_TOO_LARGE` (Shallow Sweep) — `sweep_ext / ref_range ≤ 0.50`
- `F4_NO_CLOSE_BACK` (Closed Back Inside) — `ret_close` inside prior range

**Add Confirmation** (default OFF)
- `SMT` (NQ-ES Divergence)
- `HOUR_ALIGNED` (Hour Open Aligned)
- `PRIOR_COUNTER_CLOSE` (Prior Bar Counters)
- `PRIOR_ENGULFING` (Prior Bar Engulfs)

`compute_filter_variants()` enumerates 2⁶ = 64 combinations per model × profile, sorted by EV.

## MAE/MFE Recommendation Logic

Both Python (`model_stats.py`) and JS (`model_dashboard.html`) compute:
- **PTQ**: highest reach_rate where P(positive exit | MFE ≥ X) ≥ 0.70, fallback 0.50
- **opt_sl**: tightest MAE where P(genuine loss | MAE ≥ X) ≥ 0.70, fallback 0.50

Segment behavior:
- Winners MFE: p_pos ≈ 1.0 → PTQ = lowest trigger (highest reach)
- Losers MFE: p_pos ≈ 0 → PTQ = None
- Winners MAE: p_ko = 0 → opt_sl = None (use p90 percentile instead)
- Losers MAE: p_ko = 1 → opt_sl = lowest threshold

## SMT Divergence

SMT = NQ sweeps its HTF level but ES does **not** sweep its corresponding level.

- `model_stats.py` loads `es_1m`, builds ES sweep-TF candles, checks the ES window at NQ sweep detection time
- Each trade row carries `smt: bool`
- `smt_summary` in JSON output: WR/EV/PF for SMT vs non-SMT

## Trade Row Fields

- `mae_pct` / `mfe_pct` — as % of entry price
- `hour_range_pts` — high−low of all 1m bars sharing the trade's (date, hour)
- `mae_pct_hr` / `mfe_pct_hr` — as % of hourly range (regime-independent)
- `min_equity_usd` — running minimum equity
- `max_dd_usd` — dollar value of worst peak-to-trough drawdown
- `date_range` — always `YYYY-MM-DD to YYYY-MM-DD`

## Aggregation (`agg`)

Returns: `n, wins, wr, ev, pf, avg_risk_pts, avg_rr, avg_mae, avg_mfe, avg_mae_hr, avg_mfe_hr`

Used in: `by_hour`, `by_session`, `by_dow`, `dir_summary`, `by_year`, `tspot_breakdown`, `smt_summary`

## Pine Scripts

- `fractal_sweep.pine` — indicator
- `fractal_sweep_strategy.pine` — strategy
- `fractal-sweep-indicator-apr16` — older snapshot (Pine v5 source, no extension)
- `fractal-sweep-indicator-apr19` — snapshot after fixing same-bar return-to-range (F4 lockout) and same-bar DRAW (entry mis-placement) bugs
- `ttfm+fadi.pine` — TTFM+Fadi experimental indicator

## Database

- `candle_science.duckdb` — primary DB (gitignored, ~550 MB), tables `nq_1m`, `es_1m`
- Schema: `timestamp TIMESTAMPTZ, open/high/low/close DOUBLE, volume BIGINT`
- Timestamps stored as `America/Toronto` — always convert: `timezone('America/New_York', timestamp)`

## Date Classification

`DATE_CLASSIFICATION` is an empty dict. The classifier source (`daily_classifier.py`) lived in the deleted NY1 FPFVG folder. Downstream aggregations read it defensively.
