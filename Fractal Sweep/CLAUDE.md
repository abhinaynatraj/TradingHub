# Fractal Sweep

Statistical backtesting engine for NQ and ES futures. Detects sweep + CISD setups across 15 years of 1-minute data and drives an interactive probability dashboard.

> Historical note: this folder previously coexisted with `Fractal Sweep Legacy/`. As of 2026-04-19 the Legacy engine is the canonical one; it was merged here and the Legacy folder was deleted. See `LEGACY_NOTE.md` for the earlier history.

## Stack
- Python 3.14 · DuckDB 1.4.4 · pandas
- Dashboards are standalone HTML (zero CDN deps)

## Folder Layout
```
Fractal Sweep/
├── model_dashboard.html        dashboard (served from repo root)
├── model_stats.json            engine output (gitignored, ~140 MB)
├── candle_science.duckdb       shared DB (gitignored, ~550 MB)
├── engine/                     Python backtest code
│   ├── model_stats.py          sweep+CISD detection engine
│   ├── daily_update.py         cron entry point — Databento fetch + rerun backtests
│   ├── master_backtester.py    supporting tool
│   ├── sltp_analyzer.py        supporting tool
│   ├── recalc.py               supporting tool
│   └── install_cron.sh         one-time cron setup helper
├── pine/                       TradingView scripts
│   ├── fractal_sweep.pine      indicator
│   ├── fractal_sweep_strategy.pine
│   ├── ttfm+fadi.pine          separate experiment
│   └── snapshots/              dated backups of the indicator
├── data/                       raw Databento dumps (gitignored)
├── docs/                       standalone notes (indicator description, analysis write-ups)
├── assets/                     images used by the dashboard/hub
└── tests/                      pytest suite — 215 pass · 0 skip as of 2026-04-29
```

## Running
All engine scripts self-locate — run them from the `Fractal Sweep/` folder (they resolve `candle_science.duckdb` and `model_stats.json` via `Path(__file__).parent.parent`).

```bash
python3 engine/model_stats.py                         # all 2 sweep models
python3 engine/model_stats.py --models 1H_5M          # subset
python3 engine/model_stats.py --table es_1m           # ES instead of NQ
python3 -m pytest tests/ -q                           # test suite
python3 engine/daily_update.py                        # fetch new bars from Databento
```

Dashboard served from the repo root: `python3 -m http.server 8001`, then open `http://localhost:8001/Fractal Sweep/model_dashboard.html`.

## Trading Model
- 2 timeframe pairs: `1H_5M`, `30M_3M`
- Setup: prior candle swept → price returns inside range → CISD confirms
- Entry: next candle open · Stop: sweep extreme · Target: 1R (`simple_1r`)
- Sweep, return-to-range, and CISD-fire must all occur within the **same anchor HTF window**. Setups that don't complete before the next anchor are discarded — matches the indicator's `is_new_anchor` reset semantics.
- Baseline gates (always on, not toggleable): `MIN_RISK_PTS = 3.0`, `MAX_RISK_PTS = 112.5` (= $225 / $2/pt for MNQ). Setups outside this range are rejected.
- Outcome resolution scans up to `OUTCOME_MAX_BARS = 1440` (24h of 1m bars). Same-bar TP/SL ties resolve to **SL** (matches indicator's intrabar tie-break).

## Engine ↔ Indicator alignment

The engine and Pine indicator implement the same model. Aligned 2026-04-24:
- CISD must fire within the same anchor's HTF window (no cross-anchor lookahead)
- Same-bar tie-break: SL wins (was TP in earlier engine versions)
- `OUTCOME_MAX_BARS` bumped 360 → 1440 to match indicator's effectively-unlimited resolution lifetime
- Removed `gap_limit` weekend filter (indicator doesn't filter gaps)
- Forced `[ns]` resolution on timestamp arrays — pandas 2.0+ defaults to `[us]`, which silently inflated anchor windows from 1h to 41 days. **This was the root cause of inflated baseline WR (~70%) in older outputs.** Post-fix baseline WR is ~50%, matching live indicator behavior.

## Runtime Filters (3, dashboard-toggleable)

The dashboard chip bar exposes three filters. Each chip shows a live `±N` badge before you click.

**Setup Quality** (default OFF on dashboard chip; engine row tags `passes_f3`/`passes_f4` always present)
- **Shallow Sweep** (`F3`) — `sweep_ext / ref_range ≤ 0.50`. Standalone edge: +3.4% WR, +0.061R EV.
- **Closed Back Inside** (`F4`) — `ret_close` inside prior HTF range. Standalone edge: noise on its own; useful in combination.

**Add Confirmation** (default OFF)
- **NQ-ES Divergence** (`SMT`) — NQ swept its HTF level but ES did not. Strongest single edge: +7.8% WR, +0.150R EV.

`2³ = 8` combinations are precomputed in `filter_variants.all_combinations` for the Filters tab.

### Filter edge (over 12y NQ, both models)

Standalone marginal edge over the ~50% baseline:
- **SMT** — strongest single edge (+7-8% WR, +0.15R EV)
- **F3 Shallow Sweep** — moderate (+3-4% WR, +0.05-0.06R EV)
- **F4 Closed Back Inside** — noise standalone; helpful in combos

Best practical combo (both models):
- **F3 + F4 + SMT** → 59.1% WR, +0.182R EV, N=1,711 over 12y on 1H_5M (~143 trades/yr)
- 30M_3M: same combo → 58.6% WR, +0.172R EV, N=3,234 (~270/yr)

History note: prior versions of this engine had additional filters (HOUR_ALIGNED, PRIOR_COUNTER, PRIOR_ENGULFING, plus experimental H4_BIAS, DAILY_BIAS, PD_LIQUIDITY, P12_BIAS). All were tested over the full 12y dataset and removed in 2026-04-24 — they showed no standalone edge or were anti-edge. Only F3, F4, SMT remain.

Filters work on **every Period** (All Time, 2y, 1y, 6m, 3m, 1m). `_compute_by_tf` builds `recent_trades` per sub-slice from `wl_full`, so runtime toggles update stats live without re-running the engine.

## SMT Divergence

SMT = NQ sweeps its HTF level but ES does **not** sweep its corresponding level. Exposed as "NQ-ES Divergence" in the dashboard filter bar.

- `engine/model_stats.py` loads `es_1m` alongside `nq_1m`, builds ES sweep-TF candles, checks the ES window at NQ sweep detection time
- Each trade row carries `smt: bool`
- `smt_summary` in JSON output: WR/EV/PF split for SMT vs non-SMT

## Risk Profiles (`RR_PROFILES` in `engine/model_stats.py`)

| profile_type | Key | Description |
|---|---|---|
| `mult` | `simple_1r` | SL = sweep extreme (1× base_risk); TP = 1R (100% exit) |
| `raw` | `raw_measure` | No SL/TP — records full-session MAE/MFE only, `outcome='MEASURED'` |

`simple_1r` is the default and drives all win/loss stats. `raw_measure` is the measurement-only profile used for MAE/MFE distribution studies.

### MAE/MFE Recommendation Logic
- **PTQ**: highest reach_rate where P(positive exit | MFE ≥ X) ≥ 0.70, fallback 0.50
- **opt_sl**: tightest MAE where P(genuine loss | MAE ≥ X) ≥ 0.70, fallback 0.50
- Computed both in `engine/model_stats.py` and client-side in `model_dashboard.html` for recent trades

## Hourly Normalization
- `hour_range_pts` — high minus low of all 1m bars sharing the trade's (date, hour)
- `mae_pct_hr = mae_pts / hour_range_pts × 100`
- `mfe_pct_hr = mfe_pts / hour_range_pts × 100`
- `agg()` emits `avg_mae`, `avg_mfe`, `avg_mae_hr`, `avg_mfe_hr` in all breakdowns

## Equity Tracking
- `min_equity_usd` — actual running minimum equity (not final equity)
- `max_dd_usd` — dollar value of worst peak-to-trough drawdown
- `max_dd_pct` — percentage drawdown from running peak

### Walk-Forward Regime Analysis
Custom date ranges view pairs consecutive ranges into train→test walk-forward pairs. Train period derives MAE stop variants (max, p90, p85, p50) and MFE targets (PTQ, p50) from winners. Test period resolves trades with each variant. Overfitting score = Test EV / Train EV × 100. Fully client-side in `model_dashboard.html`.

## Analysis Scripts Convention
- Reference point for candle analysis: `close` of the anchor candle
- Group results by day of week (0=Mon … 4=Fri)

## Date Classification
- `DATE_CLASSIFICATION` is an empty dict — the classifier source (`daily_classifier.py`) was in the deleted NY1 FPFVG folder
- Downstream aggregations read it defensively; absence is fine
