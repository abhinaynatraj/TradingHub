# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Serving

Always serve via HTTP — dashboards use `fetch()` and break on `file://`:

```bash
python3 -m http.server 8001   # from repo root → http://localhost:8001
```

## Dependencies

```bash
pip install duckdb pandas numpy
```

Python 3.9+. No web framework. Dashboards are standalone HTML (zero CDN deps).

## Database

- `Fractal Sweep/candle_science.duckdb` — shared DB for all engines (gitignored)
- Tables: `nq_1m`, `es_1m`
- Schema: `timestamp TIMESTAMPTZ, open, high, low, close DOUBLE, volume BIGINT`
- **Always convert to ET:** `timezone('America/New_York', timestamp)`
- All backtest scripts connect read-only via `Path(__file__).parent.parent / 'Fractal Sweep' / 'candle_science.duckdb'`

## Theme System

All pages share `localStorage.getItem('hub-theme')` → `'dark'` | `'light'`. Do not introduce per-page theme keys.

## Analysis Conventions

- Reference point: `close` of the anchor candle
- Scan window: anchor+1 bar through 16:00 ET same day
- Group by DOW: Python `0=Mon…4=Fri`; DuckDB `dow` uses `0=Sun`
- Expired setups excluded from WR/EV but counted in output
