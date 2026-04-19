# Fractal Sweep Legacy

Actively-evolving sweep+CISD backtesting engine. Originally extracted from commit `66b7581` as a frozen pre-TTFM snapshot; now the canonical home for this strategy. See `LEGACY_NOTE.md` for the full history.

This folder runs **independently** from `Fractal Sweep/`. No cross-merging unless explicitly ported. `candle_science.duckdb` is a symlink to `../Fractal Sweep/candle_science.duckdb`.

## Stack
- Python 3.14 · DuckDB 1.4.4 · pandas
- Dashboards are standalone HTML (zero CDN deps)

## Key Files
- `model_stats.py` — sweep+CISD detection engine → `model_stats.json` (gitignored)
- `model_dashboard.html` — dashboard with SMT filter, 6 runtime filter chips, 64 filter combinations
- `daily_update.py` — unused here; the main `Fractal Sweep/daily_update.py` keeps the shared DB current
- `master_backtester.py`, `sltp_analyzer.py`, `recalc.py` — supporting tooling carried over from the original snapshot
- `tests/` — pytest suite (188 pass · 7 pre-existing fail · 20 skip as of 2026-04-15)

## Running
```bash
python3 model_stats.py                          # all 4 sweep models
python3 model_stats.py --models 1H_5M 1H_3M    # subset
python3 model_stats.py --table es_1m            # ES instead of NQ
python3 -m pytest tests/ -q                     # test suite
```

Dashboard is served from the repo root: `python3 -m http.server 8001`, then open `http://localhost:8001/Fractal Sweep Legacy/model_dashboard.html`.

## Trading Model
- 4 timeframe pairs: `4H_15M`, `1H_5M`, `1H_3M`, `30M_3M`
- Setup: prior candle swept in Q1 → price returns inside range → CISD confirms
- Entry: next candle open · Stop: sweep extreme · Target: 1R (structural)
- CISD has no bar limit — can form anytime after sweep returns within the HTF period
- Baseline filters (always on): `SWEEP_MAX_PCT = 0.50`, `MIN_RISK_PTS = 3.0`, `MAX_RISK_PTS = 112.5`
- `long_base`/`short_base` separated from `max_risk` check — enables over-risk detection
- **F1 (min prior range) was removed on 2026-04-15.** Data showed it rejected above-average trades across all 4 TFs. WR/EV improved everywhere after removal. The main `Fractal Sweep/model_stats.py` still has F1 intact.

## Runtime Filters (6, dashboard-toggleable)

Two groups below the Period/TF/Profile dropdowns. Each chip shows a live `±N` badge before you click.

**Setup Quality** (default ON, uncheck to relax)
- **Shallow Sweep** (`F3_SWEEP_TOO_LARGE`) — sweep pierced ≤ 50% of prior range
- **Closed Back Inside** (`F4_NO_CLOSE_BACK`) — price returned inside prior range

**Add Confirmation** (default OFF, check to narrow)
- **NQ-ES Divergence** (`SMT`) — NQ swept but ES did not
- **Hour Open Aligned** (`HOUR_ALIGNED`) — CISD close on correct side of current hour open
- **Prior Bar Counters** (`PRIOR_COUNTER_CLOSE`) — prior sweep-TF candle closed against trade direction
- **Prior Bar Engulfs** (`PRIOR_ENGULFING`) — prior sweep-TF candle engulfs its predecessor wick-inclusive

`2⁶ = 64` combinations are precomputed in `filter_variants.all_combinations` for the Filters tab.

Filters work on **every Period** (All Time, 2y, 1y, 6m, 3m, 1m). `_compute_by_tf` builds `recent_trades` per sub-slice from `wl_full` (which includes F3/F4-rejected trades), so runtime toggles can bring rejected trades back in.

## SMT Divergence

SMT = NQ sweeps its HTF level but ES does **not** sweep its corresponding level. Exposed as "NQ-ES Divergence" in the dashboard filter bar.

- `model_stats.py` loads `es_1m` alongside `nq_1m`, builds ES sweep-TF candles, checks ES Q1 window at NQ sweep detection time
- Each trade row carries `smt: bool`
- `smt_summary` in JSON output: WR/EV/PF split for SMT vs non-SMT

## Risk Profiles (`RR_PROFILES` in `model_stats.py`)

12 profiles total — 10 fixed-% DDLI-ranked + 2 structural/split-exit:

| profile_type | Keys | Stop/Target |
|---|---|---|
| `pct` | `sl_026_tp_018` … `sl_019_tp_019` | Fixed % of entry price; SL/TP independent of sweep size |
| `structural` | `structural_dynamic` | SL = sweep extreme (1×base_risk); TP1 @ 1R, 90% off; 10% runner free with BE stop |
| `split_tp` | `split_80_20` | SL = min(sweep extreme, MAE p90 winners); TP1 @ PTQ, 90% off; 10% runner → TP2 @ p50 MFE; BE stop |

### split_tp mechanics
- `stop_dist = min(1 × base_risk, entry × mae_p90 / 100)`
- `TP1 = entry ± entry × ptq_level / 100` (PTQ from structural winners)
- Runner TP2 = `entry ± entry × p50_mfe / 100` (p50 MFE from winners)
- After TP1: 10% runner with BE stop toward TP2
- `net_r = 0.90 × tp1_r + 0.10 × runner_exit_r`

### MAE/MFE Recommendation Logic
- **PTQ**: highest reach_rate where P(positive exit | MFE ≥ X) ≥ 0.70, fallback 0.50
- **opt_sl**: tightest MAE where P(genuine loss | MAE ≥ X) ≥ 0.70, fallback 0.50
- Computed both in `model_stats.py` and client-side in `model_dashboard.html` for recent trades

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
- Scan window: anchor+1 bar through 16:00 ET same day
- Group results by day of week (0=Mon … 4=Fri)
