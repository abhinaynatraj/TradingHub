---
paths:
  - "Fractal Sweep/**"
---

# Fractal Sweep Rules

## Engines

- `model_stats.py` — sweep model engine → `model_stats.json`
- `daily_update.py` — cron entry point (fetches missing bars from Databento)

```bash
python3 model_stats.py                          # all 4 sweep models
python3 model_stats.py --models 1H_5M 1H_3M    # specific models only
python3 model_stats.py --table es_1m            # ES instead of NQ
python3 daily_update.py                         # fetch new bars from Databento
```

## 4 Sweep Model Variants

| Key | Sweep TF | CISD TF | Q1 Window |
|-----|----------|---------|-----------|
| `4H_15M` | 4 Hour | 15 Min | First 1h |
| `1H_5M` | 1 Hour | 5 Min | First 15m |
| `1H_3M` | 1 Hour | 3 Min | First 15m |
| `30M_3M` | 30 Min | 3 Min | First 8m |

## Key Constants (model_stats.py)

- `SWEEP_MAX_PCT = 0.50` — sweep must be ≤50% of prior range
- `CISD_FAST_BARS = None` — no bar limit, CISD can form anytime after sweep
- `MIN_RISK_PTS = 3.0`, `MAX_RISK_PTS = 112.5` (MNQ $225 ÷ $2.00/pt)
- `min_range` per model: 4H=30, 1H=12, 30M=8 pts

## Refinement Filters (F1–F5)

Prior range floor, sweep min size, sweep max cap, close-back required, CISD speed — applied cumulatively.

## Risk Profiles

12 profiles. 3 profile_types:

| profile_type | Keys | Stop/Target |
|---|---|---|
| `pct` | `sl_026_tp_018` … `sl_019_tp_019` | Fixed % of entry price; SL and TP independent of sweep size |
| `structural` | `structural_dynamic` | SL = sweep extreme (1×base_risk); TP1 @ 1R, 90% off; runner (10%) free with BE stop |
| `split_tp` | `split_80_20` | SL = min(sweep extreme, MAE p90 winners); TP1 @ PTQ, 90% off; 10% runner → TP2 @ p50 MFE; BE stop |

`split_tp` resolver: `resolve_outcomes_split_tp(m1_arrs, pending, tp1_size=0.90, tp2_size=0.10)`
`net_r = 0.90 × tp1_r + 0.10 × runner_exit_r`
All split_tp targets (PTQ, p50 MFE, MAE p90) are computed per TF period from structural winners.

## MAE/MFE Recommendation Logic

Both Python (`model_stats.py`) and JS (client-side in `model_dashboard.html`) compute recommendations:

- **PTQ (Protect the Queen)**: MFE BE trigger — highest reach_rate where P(positive exit | MFE ≥ X) ≥ 0.70, fallback to 0.50
- **Optimal SL (opt_sl)**: MAE stop placement — tightest MAE threshold where P(genuine loss | MAE ≥ X) ≥ 0.70, fallback to 0.50
- **Rescue Opportunity**: MFE losers — narrative only (median/p75), no threshold recommendation

Segment behavior:
- Winners MFE: p_pos ≈ 1.0 at all levels → PTQ = lowest trigger (highest reach)
- Losers MFE: p_pos ≈ 0 → PTQ = None (correct)
- Winners MAE: p_ko = 0 → opt_sl = None (use p90 percentile instead)
- Losers MAE: p_ko = 1 → opt_sl = lowest threshold (validates stop)

## Trade Row Fields

Each resolved trade row carries:
- `mae_pct` / `mfe_pct` — MAE/MFE as % of entry price
- `hour_range_pts` — high-low of the entry hour's 1m candles (precomputed lookup by date+hour)
- `mae_pct_hr` / `mfe_pct_hr` — MAE/MFE as % of hourly range (regime-independent)
- `min_equity_usd` — actual running minimum equity (not final equity)
- `max_dd_usd` — dollar value of worst peak-to-trough drawdown
- `date_range` — always `YYYY-MM-DD to YYYY-MM-DD` format

## Aggregation (agg function)

`agg(g)` returns: `n, wins, wr, ev, pf, avg_risk_pts, avg_rr, avg_mae, avg_mfe, avg_mae_hr, avg_mfe_hr`
Used in: `by_hour`, `by_session`, `by_dow`, `dir_summary`, `by_year`, `tspot_breakdown`

## Database

- `candle_science.duckdb` — primary DB (gitignored), tables: `nq_1m`, `es_1m`
- Schema: `timestamp TIMESTAMPTZ, open, high, low, close DOUBLE, volume BIGINT`
- Timestamps: `TIMESTAMP WITH TIME ZONE (America/Toronto)` — always convert: `timezone('America/New_York', timestamp)`
