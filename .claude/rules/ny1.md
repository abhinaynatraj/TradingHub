---
paths:
  - "NY1 FPFVG/**"
---

# NY1 F.P.FVG Rules

## Engine

```bash
python3 ny1_backtest.py                # → ny1_results.json
python3 ny1_backtest.py --table es_1m
```

## Model

- Scan 9:31–9:59 ET for the **first** 3-candle FVG (9:30 excluded)
- `TP1_BPS = 0.001` (10 bps = 0.10%) captures 80% of position
- Runner (20%) exits at 16:00 close or stop
- DB path: `Path(__file__).parent.parent / 'Fractal Sweep' / 'candle_science.duckdb'` (read-only)

## Risk Profile Dropdown

`ny1_results.json` structure: `{tf: {profiles: {open_run: ..., sl003_tp008: ..., ...}}}`

- **open_run** — structural profile: TP1 0.10% + runner
- **Top-10 fixed SL/TP** — ranked by weighted composite score on NY1-only data (no daily classification):
  - Weights: Sharpe 25%, PF 20%, EV 15%, SQN 15%, MaxDD 10%, RoR 10%, CE 5%
  - All SL=0.03%, TP=0.08%–0.17% (MIN_SL_PCT=0.03% filter applied)
  - All 10 verified non-blown across all 6 timeframes (all, 2y, 1y, 6m, 3m, 1m)

## profile_key() Format

`f"sl{round(sl_pct*100):03d}_tp{round(tp_pct*100):03d}"` — e.g. SL=0.03%, TP=0.08% → `sl003_tp008`

## Scan Scripts

- `fixed_profile_scan.py` — scans all SL/TP combos, scores by weighted composite, outputs `fixed_scan_results.json`
- `ny1_backtest.py` — runs TOP10_FIXED_PROFILES through `resolve_fixed_profile()`, outputs `ny1_results.json`
