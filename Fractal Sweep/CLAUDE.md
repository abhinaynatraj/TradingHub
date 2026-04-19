# Fractal Sweep (main workspace)

This folder hosts three independent backtesting engines that share a single database. The original sweep+CISD model lives on in `Fractal Sweep Legacy/` as the actively-evolved strategy; this folder's primary dashboards are now **Fixed Constant** and **TTFM**.

## Stack
- Python 3.14 · DuckDB 1.4.4 · pandas · numpy
- No web framework — dashboards are standalone HTML (zero CDN deps)

## Engines

| Script | Output JSON | Dashboard | Purpose |
|---|---|---|---|
| `model_stats_fixed_constant.py` | `model_stats_fixed_constant.json` | `model_dashboard_fixed_constant.html` | Doctrine-compliant locked-anchor MAE/MFE study. One rep per HTF block. No filters, no win/loss. |
| `model_stats_ttfm.py` | `model_stats_ttfm.json` | `model_dashboard_ttfm.html` | TTrades Fractal Model — T-Spot touch setups. MAE/MFE only, no win/loss. |
| `model_stats.py` | `model_stats.json` | *(dashboard lives in Fractal Sweep Legacy/)* | Original sweep+CISD engine with F1 intact. Still here for regression comparison. |

The hub `index.html` links only the Fixed Constant dashboard. TTFM and Legacy dashboards are opened directly.

## Running

```bash
python3 model_stats_fixed_constant.py           # Fixed Constant (30M_3M, 1H_5M, 4H_15M)
python3 model_stats_ttfm.py                     # TTFM (15M_1M, 30M_3M, 1H_5M, 4H_15M)
python3 model_stats.py                          # Original sweep+CISD
python3 daily_update.py                         # Fetch new bars from Databento
```

Any engine also accepts `--table es_1m` and `--models <keys>`. Serve dashboards from the repo root (`python3 -m http.server 8001`).

## Database

`candle_science.duckdb` lives in this folder. `Fractal Sweep Legacy/candle_science.duckdb` is a symlink pointing here. Schema and timezone rules are in the root `CLAUDE.md`.

## Fixed Constant Engine

Locked-anchor H3 architecture from the Wolf Tank doctrine. For each new HTF block, the engine locks the anchor at the close of the FIRST chart-TF bar inside that block. From that lock close, MAE/MFE are measured to the end of the HTF block.

- One rep per HTF block · Same time every rep · Zero conditional judgment
- Models: `30M_3M`, `1H_5M`, `4H_15M` (no `15M_1M` — measurement window too short)
- No filters, no direction labels, no win/loss resolution

## TTFM Engine

T-Spot → Touch → Pivot Sweep Confirmation. No WIN/LOSS resolution, MAE/MFE only.

- T-Spot zone: `C3.close ↔ sweep_mid` (log-weighted midpoint of the C3 sweep candle)
- 6 variants: `Normal` × `Expansive` × `ProTrend` crossed with `BEAR`/`BULL`
- Defaults: `DEFAULT_MIN_RISK = 5.0 pts`, `DEFAULT_MAX_HOLD = 240 bars`
- Models: `15M_1M`, `30M_3M`, `1H_5M`, `4H_15M`

## Original Sweep+CISD Engine (`model_stats.py`)

Still the canonical reference implementation. F1 (min prior range) is **intact** here — the removal happened only in `Fractal Sweep Legacy/`. Keep this engine unchanged unless you are explicitly re-baselining.

- 4 TF pairs: `4H_15M`, `1H_5M`, `1H_3M`, `30M_3M`
- Filters F1–F5 applied cumulatively
- `SWEEP_MAX_PCT = 0.50`, `MIN_RISK_PTS = 3.0`, `MAX_RISK_PTS = 112.5`
- `CISD_FAST_BARS = None` (no bar limit)
- `min_range` per model: 4H=30, 1H=12, 30M=8 pts
- SMT divergence included (loads `es_1m`, per-trade `smt` bool)

## Pine Scripts

| File | Purpose |
|---|---|
| `fractal_sweep.pine` | Indicator — draws sweep/CISD setups, SMT labels, over-risk badges |
| `fractal_sweep_strategy.pine` | Strategy version for TradingView backtester |
| `fractal-sweep-indicator-apr16` | Snapshot (Pine v5 source, extension missing on purpose) |

## Key Files
- `daily_update.py` — cron entry point (weekdays 7am), refreshes the shared DB
- `install_cron.sh` — one-time cron setup helper
- `tests/` — pytest suite for the sweep+CISD engine
