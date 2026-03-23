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
- `model_stats.py` — sweep+CISD detection engine → `model_stats.json`
- `daily_update.py` — cron entry point (weekdays 7am); fetches missing bars from Databento
- `model_dashboard.html` — sweep model dashboard (loads `model_stats.json`)

## Running
```bash
python3 model_stats.py              # run all 4 sweep models
python3 daily_update.py             # fetch new bars from Databento
python3 -m http.server 8000         # serve dashboard at localhost:8000
```

## Trading Model
- 4 timeframe pairs: `4H_15M`, `1H_5M`, `1H_3M`, `30M_3M`
- Setup: prior candle swept in Q1 → price returns inside range → CISD confirms
- Entry: next candle open | Stop: sweep extreme | Target: 2R (1:2)
- RTH window: 07:00–16:00 ET (all models)

## Analysis Scripts Convention
- Reference point for candle analysis: use `close` of the anchor candle
- Scan window: anchor+1 bar through 16:00 ET same day
- Group results by day of week (0=Mon … 4=Fri)
