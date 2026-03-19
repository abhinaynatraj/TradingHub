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
- DB path: `Path(__file__).parent.parent / 'CandleScience' / 'candle_science.duckdb'` (read-only)
