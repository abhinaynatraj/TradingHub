---
paths:
  - "TTrades Fractal Model Analysis/**"
---

# TTFM° Rules

## Engine

```bash
python3 ttfm_backtest.py                        # → ttfm_results.json
python3 ttfm_backtest.py --htf 240 --rr 1.5
python3 ttfm_backtest.py --min-risk 3 --max-hold 120
```

## Model

- HTF default: 60-minute candles; entry on 1-minute chart
- T-Spot zone: `C3.close ↔ sweep_mid` (log-weighted midpoint of C3)
- 6 variants: `Normal`, `Expansive`, `ProTrend` × `BEAR`/`BULL`
- `DEFAULT_MIN_RISK = 5.0 pts`, `DEFAULT_MAX_HOLD = 240 bars`
- DB path: `Path(__file__).parent.parent / 'Fractal Sweep' / 'candle_science.duckdb'` (read-only)
