---
paths:
  - "CandleScience/**"
---

# CandleScience Rules

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

- `SWEEP_MIN_PCT = 0.10`, `SWEEP_MAX_PCT = 1.50`
- `CISD_FAST_BARS = 8` — CISD must form within 8 CISD-TF bars
- RTH window: 07:00–16:00 ET (all models)

## Refinement Filters (F1–F5)

Prior range floor, sweep min size, sweep max cap, close-back required, CISD speed — applied cumulatively.

## Database

- `candle_science.duckdb` — primary DB (gitignored), tables: `nq_1m`, `es_1m`
- Schema: `timestamp TIMESTAMPTZ, open, high, low, close DOUBLE, volume BIGINT`
- Timestamps: `TIMESTAMP WITH TIME ZONE (America/Toronto)` — always convert: `timezone('America/New_York', timestamp)`
