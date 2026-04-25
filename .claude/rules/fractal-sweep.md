---
paths:
  - "Fractal Sweep/**"
---

# Fractal Sweep Rules

Sweep+CISD backtesting engine. The Python engine and Pine indicator are aligned (2026-04-24): sweep, return-to-range, and CISD-fire must all occur within the same anchor HTF window. Setups that don't complete before the next anchor are discarded.

## Folder Layout

```
Fractal Sweep/
├── model_dashboard.html
├── model_stats.json           (gitignored engine output)
├── candle_science.duckdb      (gitignored shared DB)
├── engine/                    Python backtest code
├── pine/                      TradingView scripts (+ snapshots/)
├── data/                      Databento .dbn dumps (gitignored)
├── docs/                      analysis write-ups
├── assets/                    images
└── tests/                     pytest suite
```

Engine scripts self-locate via `Path(__file__).parent.parent` — run from the `Fractal Sweep/` folder.

## Engine

```bash
python3 engine/model_stats.py                         # all 2 sweep models → model_stats.json
python3 engine/model_stats.py --models 1H_5M          # subset
python3 engine/model_stats.py --table es_1m           # ES instead of NQ
python3 engine/daily_update.py                        # fetch new bars from Databento
python3 -m pytest tests/ -q                           # test suite
```

## 2 Sweep Models

| Key | Sweep TF | CISD TF |
|---|---|---|
| `1H_5M` | 1 Hour | 5 Min |
| `30M_3M` | 30 Min | 3 Min |

## Constants (`engine/model_stats.py`)

- `MIN_RISK_PTS = 3.0`, `MAX_RISK_PTS = 112.5` (MNQ $225 ÷ $2.00/pt) — always-on baseline gates
- `OUTCOME_MAX_BARS = 1440` (24h of 1m bars; bumped from 360 to match indicator's effectively-unlimited resolution lifetime)
- `RISK_PER_TRADE = 225`, `POINT_VALUE = 2.0` — MNQ-configured (price action is identical to NQ; only sizing differs)
- Same-bar TP/SL ties resolve to **SL** (matches indicator)
- CISD must fire within the same anchor's HTF window — no cross-anchor lookahead

## Risk Profiles

| Key | profile_type | Description |
|---|---|---|
| `simple_1r` | `mult` | SL = sweep extreme (1× base_risk); TP = 1R (100% exit). Default. |
| `raw_measure` | `raw` | No SL/TP — records full-session MAE/MFE only, `outcome='MEASURED'` |

## Runtime Filter Fields on Each Trade Row

Beyond `outcome`/`r`/`mae_pct`/`mfe_pct`/`smt`, each row carries:
- `passes_f3`, `passes_f4` — for Shallow Sweep / Closed Back Inside filters
- `cisd_close` — close of the CISD bar at fire

## Runtime Filters (3, dashboard-toggleable, all default OFF)

- `F3` (Shallow Sweep) — `sweep_ext / ref_range ≤ 0.50`. Standalone: +3.4% WR.
- `F4` (Closed Back Inside) — `ret_close` inside prior HTF range. Standalone: noise; useful in combo.
- `SMT` (NQ-ES Divergence) — NQ swept its HTF level but ES did not. Standalone: +7.8% WR (strongest).

`compute_filter_variants()` enumerates 2³ = 8 combinations per model × profile, sorted by EV.

### Filter edge (over 12y NQ, baseline ~50% WR)

Best practical combo: `F3 + F4 + SMT` → 59.1% WR, +0.182R EV (N=1,711 over 12y) on 1H_5M.

History: HOUR_ALIGNED, PRIOR_COUNTER, PRIOR_ENGULFING (and experimental H4_BIAS, DAILY_BIAS, PD_LIQUIDITY, P12_BIAS) were tested over the full dataset and removed in 2026-04-24 — none had standalone edge.

## MAE/MFE Recommendation Logic

Both Python (`engine/model_stats.py`) and JS (`model_dashboard.html`) compute:
- **PTQ**: highest reach_rate where P(positive exit | MFE ≥ X) ≥ 0.70, fallback 0.50
- **opt_sl**: tightest MAE where P(genuine loss | MAE ≥ X) ≥ 0.70, fallback 0.50

Segment behavior:
- Winners MFE: p_pos ≈ 1.0 → PTQ = lowest trigger (highest reach)
- Losers MFE: p_pos ≈ 0 → PTQ = None
- Winners MAE: p_ko = 0 → opt_sl = None (use p90 percentile instead)
- Losers MAE: p_ko = 1 → opt_sl = lowest threshold

## SMT Divergence

SMT = NQ sweeps its HTF level but ES does **not** sweep its corresponding level.

- `engine/model_stats.py` loads `es_1m`, builds ES sweep-TF candles, checks the ES window at NQ sweep detection time
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

All Pine scripts live under `pine/`.

- `pine/fractal_sweep.pine` — indicator
- `pine/fractal_sweep_strategy.pine` — strategy
- `pine/ttfm+fadi.pine` — TTFM+Fadi experimental indicator
- `pine/snapshots/fractal-sweep-indicator-apr16` — older snapshot (Pine v5 source, no extension)
- `pine/snapshots/fractal-sweep-indicator-apr19` — snapshot after fixing same-bar return-to-range (F4 lockout) and same-bar DRAW (entry mis-placement) bugs

## Database

- `candle_science.duckdb` — primary DB (gitignored, ~550 MB), tables `nq_1m`, `es_1m`
- Schema: `timestamp TIMESTAMPTZ, open/high/low/close DOUBLE, volume BIGINT`
- Timestamps stored as `America/Toronto` — always convert: `timezone('America/New_York', timestamp)`

## Date Classification

`DATE_CLASSIFICATION` is an empty dict. The classifier source (`daily_classifier.py`) lived in the deleted NY1 FPFVG folder. Downstream aggregations read it defensively.
