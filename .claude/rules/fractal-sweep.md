---
paths:
  - "Fractal Sweep/**"
---

# Fractal Sweep Rules (main folder)

Three independent engines live here. The original sweep+CISD strategy is no longer the primary — its evolved form is in `Fractal Sweep Legacy/`.

## Engines

| Script | Output | Model |
|---|---|---|
| `model_stats_fixed_constant.py` | `model_stats_fixed_constant.json` | Doctrine locked-anchor MAE/MFE (primary dashboard) |
| `model_stats_ttfm.py` | `model_stats_ttfm.json` | TTrades T-Spot touch (MAE/MFE only) |
| `model_stats.py` | `model_stats.json` | Original sweep+CISD (F1 intact — do not remove here) |
| `daily_update.py` | — | Cron entry point; fetches bars from Databento |

```bash
python3 model_stats_fixed_constant.py           # Fixed Constant
python3 model_stats_ttfm.py                     # TTFM
python3 model_stats.py                          # Original sweep+CISD
# Shared flags: --models <keys>, --table es_1m
python3 daily_update.py                         # fetch new bars
```

## Fixed Constant Model

Locked-anchor H3 architecture. For each new HTF block, the engine locks the anchor at the close of the first chart-TF bar. From that lock close, MAE/MFE are measured to the end of the HTF block. One rep per HTF block. No filters, no direction, no WIN/LOSS.

| Key | HTF | Chart TF |
|---|---|---|
| `30M_3M` | 30 min | 3 min |
| `1H_5M` | 1 hour | 5 min |
| `4H_15M` | 4 hour | 15 min |

`15M_1M` is deliberately excluded.

## TTFM Model

T-Spot → Touch → Pivot Sweep Confirmation. MAE/MFE only. 6 variants: `Normal`/`Expansive`/`ProTrend` × `BEAR`/`BULL`. Defaults: `DEFAULT_MIN_RISK = 5.0 pts`, `DEFAULT_MAX_HOLD = 240 bars`.

Models: `15M_1M`, `30M_3M`, `1H_5M`, `4H_15M`.

## Original Sweep + CISD Model

Reference implementation, F1 intact. Do not alter filter semantics here — Legacy is where evolution happens.

| Key | Sweep TF | CISD TF | Q1 Window | min_range |
|-----|----------|---------|-----------|-----------|
| `4H_15M` | 4 Hour | 15 Min | 60 min | 30 pts |
| `1H_5M` | 1 Hour | 5 Min | 15 min | 12 pts |
| `1H_3M` | 1 Hour | 3 Min | 15 min | 12 pts |
| `30M_3M` | 30 Min | 3 Min | 8 min | 8 pts |

**Constants:** `SWEEP_MAX_PCT = 0.50` · `MIN_RISK_PTS = 3.0` · `MAX_RISK_PTS = 112.5` · `CISD_FAST_BARS = None`

Filters F1–F5 applied cumulatively. `long_base`/`short_base` separated from `max_risk` — enables over-risk detection.

### SMT Divergence
Loads `es_1m`, builds ES sweep-TF candles, checks ES Q1 window at NQ sweep time. Per-trade `smt` bool. `smt_summary` in JSON with WR/EV/PF split.

### Risk Profiles (12 total)
| profile_type | Keys | Stop/Target |
|---|---|---|
| `pct` | `sl_026_tp_018` … `sl_019_tp_019` | Fixed % of entry price |
| `structural` | `structural_dynamic` | SL = sweep extreme; TP1 @ 1R, 90% off; 10% runner with BE stop |
| `split_tp` | `split_80_20` | SL = min(sweep extreme, MAE p90 winners); TP1 @ PTQ, 90% off; 10% runner → TP2 @ p50 MFE |

### MAE/MFE Recommendation Logic
- **PTQ**: highest reach_rate where P(positive exit | MFE ≥ X) ≥ 0.70, fallback 0.50
- **opt_sl**: tightest MAE where P(genuine loss | MAE ≥ X) ≥ 0.70, fallback 0.50

## Database

- `candle_science.duckdb` — primary DB (gitignored, ~550 MB), tables `nq_1m`, `es_1m`
- Schema: `timestamp TIMESTAMPTZ, open/high/low/close DOUBLE, volume BIGINT`
- Timestamps stored as `America/Toronto` — always convert: `timezone('America/New_York', timestamp)`

## Pine

- `fractal_sweep.pine` — indicator
- `fractal_sweep_strategy.pine` — strategy version
- `fractal_sweep_indicator_description.md` — TradingView publish description
- `fractal-sweep-indicator-apr16` — Apr 16 snapshot (Pine v5 source, no extension)
