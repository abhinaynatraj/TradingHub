# Fractal Sweep

Statistical backtesting engine for NQ and ES futures. Detects sweep + CISD setups across 15 years of 1-minute data and outputs probability dashboards.

## Stack
- Python 3.14 + DuckDB 1.4.4 + pandas
- No web framework — dashboards are standalone HTML files

## Database
- `candle_science.duckdb` — primary DB, tables: `nq_1m`, `es_1m`
- Schema: `timestamp TIMESTAMPTZ, open, high, low, close DOUBLE, volume BIGINT`
- Timestamps stored as `TIMESTAMP WITH TIME ZONE` (America/Toronto)
- Always convert to ET for analysis: `timezone('America/New_York', timestamp)`
- Large data files (`.duckdb`, `.dbn`, `.parquet`, `.csv`) are gitignored

## Key Files
- `model_stats.py` — sweep+CISD detection engine → `model_stats.json` (includes SMT divergence)
- `daily_update.py` — cron entry point (weekdays 7am); fetches missing bars from Databento
- `model_dashboard.html` — sweep model dashboard (loads `model_stats.json`; SMT filter)
- `../Live Scanner/fractal_sweep_cisd.pine` — TradingView Pine v5 indicator (live alert equivalent of the backtest)

## Running
```bash
python3 model_stats.py              # run all 4 sweep models
python3 daily_update.py             # fetch new bars from Databento
python3 -m http.server 8000         # serve dashboard at localhost:8000
```

## Trading Model
- 4 timeframe pairs: `4H_15M`, `1H_5M`, `1H_3M`, `30M_3M`
- Setup: prior candle swept in Q1 → price returns inside range → CISD confirms
- Entry: next candle open | Stop: sweep extreme | Target: 1R (structural)
- CISD: no bar limit — can form anytime after sweep returns within the HTF period
- Baseline filters (always on): sweep max 50%, min risk 3 pts, max risk 112.5 pts
- `long_base`/`short_base` validity is separated from `max_risk` check — enables over-risk detection
- **Note:** F1 (min prior range) was removed on 2026-04-15 — data showed it was
  rejecting above-average trades across all 4 TFs. WR/EV improved after removal.

## Runtime Filters (6, dashboard-toggleable)

Two groups, visible in the dashboard filter bar below the dropdowns:

**Setup Quality** (default ON, uncheck to relax)
- **Shallow Sweep** (`F3_SWEEP_TOO_LARGE`) — sweep pierced ≤ 50% of prior range
- **Closed Back Inside** (`F4_NO_CLOSE_BACK`) — price returned inside prior range

**Add Confirmation** (default OFF, check to narrow)
- **NQ-ES Divergence** (`SMT`) — NQ swept but ES did not
- **Hour Open Aligned** (`HOUR_ALIGNED`) — CISD close on correct side of current hour open
- **Prior Bar Counters** (`PRIOR_COUNTER_CLOSE`) — prior sweep-TF candle closed against trade direction
- **Prior Bar Engulfs** (`PRIOR_ENGULFING`) — prior sweep-TF candle engulfs its predecessor wick-inclusive

Each chip shows a live `±N` badge indicating how many trades would be added or
removed if that chip were toggled. `2⁶ = 64` combinations are precomputed in
`filter_variants.all_combinations` for the dashboard's Filters tab.

Filter toggles work on **every Period** (All Time, 2y, 1y, 6m, 3m, 1m), not
just All Time. `_compute_by_tf` builds `recent_trades` for each sub-slice from
`wl_full` (which includes F3/F4-rejected trades) so runtime toggles can bring
rejected trades back in.

## SMT Divergence

SMT (Smart Money Technique) detects when NQ sweeps a HTF level but ES does **not** sweep its corresponding level — indicating divergence between the two instruments. Exposed in the dashboard filter bar as "NQ-ES Divergence".

### Backtest (`model_stats.py`)
- Loads `es_1m` data alongside `nq_1m`
- Builds ES sweep-TF candles and checks the ES Q1 window at NQ sweep detection time
- Each trade row carries a `smt` boolean
- JSON output includes `smt_summary` with WR/EV/PF split for SMT vs non-SMT trades

## Risk Profiles (RR_PROFILES in model_stats.py)

12 profiles total — 10 fixed-% DDLI-ranked + 2 structural/split-exit:

| profile_type | Key | Description |
|---|---|---|
| `pct` | `sl_026_tp_018` … `sl_019_tp_019` | Fixed % SL/TP of entry price (DDLI top-10) |
| `structural` | `structural_dynamic` | SL = sweep extreme (1×base_risk); TP1 @ 1R, 90% exit; runner (10%) free with BE stop |
| `split_tp` | `split_80_20` | SL = sweep extreme; TP1 @ PTQ level, 90% exit; 10% runner targets p50 MFE; BE stop on runner |

### split_tp profile mechanics
- `stop_dist = min(1 × base_risk, entry × mae_p90 / 100)` — tighter of structural or MAE p90 of winners
- `TP1 = entry ± entry × ptq_level / 100` (PTQ level from structural profile's winners-only MFE)
- Runner TP2 = `entry ± entry × p50_mfe / 100` (p50 MFE from winners)
- After TP1: 10% runner holds with BE stop toward TP2
- `net_r = 0.90 × tp1_r + 0.10 × runner_exit_r`
- All targets (PTQ, p50, MAE p90) are computed per TF period from the structural profile's winners

### MAE/MFE Recommendation Logic
- **PTQ**: highest reach_rate where P(positive exit | MFE ≥ X) ≥ 0.70, fallback 0.50
- **opt_sl**: tightest MAE where P(genuine loss | MAE ≥ X) ≥ 0.70, fallback 0.50
- Computed in both `model_stats.py` (backtest) and `model_dashboard.html` (client-side recent trades)

## Hourly Normalization

MAE/MFE are normalized by the entry hour's range to be comparable across volatility regimes:
- `hour_range_pts` — high minus low of all 1m bars sharing the trade's (date, hour)
- `mae_pct_hr = mae_pts / hour_range_pts × 100` — MAE as % of hourly range
- `mfe_pct_hr = mfe_pts / hour_range_pts × 100` — MFE as % of hourly range
- `agg()` emits `avg_mae`, `avg_mfe`, `avg_mae_hr`, `avg_mfe_hr` in all breakdowns (by_hour, by_session, by_dow, dir_summary, by_year)
- Dashboard tooltips show hour-normalized values

## Equity Tracking

- `min_equity_usd` — actual running minimum equity (not final equity)
- `max_dd_usd` — dollar amount of the worst peak-to-trough drawdown
- `max_dd_pct` — percentage drawdown from running peak

### Walk-Forward Regime Analysis
Custom date ranges view pairs consecutive ranges into train→test walk-forward pairs.
Train period derives MAE stop variants (max, p90, p85, p50) and MFE targets (PTQ, p50) from winners.
Test period resolves trades with each variant. Overfitting score = Test EV / Train EV × 100.
All computation is client-side in `model_dashboard.html` — no Python changes needed.

## Analysis Scripts Convention
- Reference point for candle analysis: use `close` of the anchor candle
- Scan window: anchor+1 bar through 16:00 ET same day
- Group results by day of week (0=Mon … 4=Fri)
