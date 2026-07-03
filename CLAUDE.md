# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Repo Layout

```
Statistic.ally/
├── index.html                         Hub page (links all dashboards)
├── server.py                          Local server: static files + /data, /trades, /recalc endpoints
├── Fractal Sweep/                     Sweep+CISD engine, dashboard, Pine scripts, DB
├── Amas Models/                       H1 continuation backtests
├── NPG Sweep/                         NPG sweep model (multi-pairing)
├── Analysis/                          Hourly Analysis (quarter + breakout studies)
├── TTrades Fractal Model Analysis/    T-Spot touch strategy
├── docs/superpowers/specs/            Design docs (reference only)
└── .claude/rules/                     Per-folder guidance
```

## Serving

Use `server.py`, not the stdlib http.server. It serves the dashboards AND the `/data`, `/trades`, `/recalc` endpoints that Fractal Sweep depends on for slim-JSON aggregate slicing and parquet-backed trade fetches:

```bash
python3 server.py   # from repo root → http://localhost:8001
```

Plain `python3 -m http.server 8001` only serves static files — Fractal Sweep's dashboard will load but stats will be empty because `/data` and `/trades` won't respond.

## Data Architecture

Two patterns coexist:

1. **JSON aggregates + parquet trades + Python server** (Fractal Sweep, Amas)
   - Engine writes `model_stats.json` (aggregate stats only) plus `model_stats.parquet` (raw trade rows).
   - Server slices JSON per request via `/data?engine=X&model=Y&profile=Z` and streams trade rows from parquet via `/trades?...&period=2y|1y|6m|3m|1m|all` (XOR with `&from=...&to=...`).
   - Frontend uses a `loadTrades(fullKey, profile, period)` cache in `js/data.js` keyed by `(model, profile, period)`.
   - **Critical**: parquet is the canonical schema (β bridge). JS reads `stop_price` (not `sl_price`), derives `dow_name` from `dow` int. No server-side aliasing.
   - Amas still embeds trade rows in JSON (smaller dataset, 2.6 MB) — could be migrated to the slim+parquet pattern later but not urgent.

2. **Parquet-native via DuckDB-WASM in the browser** (NPG Sweep, Hourly Analysis)
   - Engine writes per-study/per-pairing parquets + a small manifest JSON.
   - Dashboard loads parquets directly via `window.loadParquet` (defined in `Analysis/dashboard/shared.js`) into an in-browser DuckDB instance.
   - All aggregation happens in browser via SQL. No `/data` or `/trades` server endpoints needed.

Fractal Sweep's slim-JSON migration (PR #15 / 2026-05-15) was designed to keep pattern (1) compatible with an eventual move to (2) — JS consumers already read parquet-native column names, so swapping the source from `/trades` to `loadParquet` would be the only remaining change.

## Dependencies

```bash
pip install duckdb pandas numpy openpyxl
```

Python 3.9+ works; active development uses Python 3.14.

## Shared Database

- Canonical location: `Fractal Sweep/candle_science.duckdb` (gitignored, ~550 MB)
- Tables: `nq_1m`, `es_1m`
- Schema: `timestamp TIMESTAMPTZ, open, high, low, close DOUBLE, volume BIGINT`
- Timestamps stored as `America/Toronto` — **always convert**: `timezone('America/New_York', timestamp)`
- Engine scripts in `Fractal Sweep/engine/` connect via `Path(__file__).parent.parent / 'candle_science.duckdb'`; scripts elsewhere (e.g. `TTrades Fractal Model Analysis/`) use `Path(__file__).parent.parent / 'Fractal Sweep' / 'candle_science.duckdb'`

## Data Updates

Only `Fractal Sweep/engine/daily_update.py` fetches new bars from Databento. Cron installed via `engine/install_cron.sh` runs it on weekdays. All other engines read from the shared DB read-only.

## Theme System

All dashboards share `localStorage.getItem('hub-theme')` → `'dark'` | `'light'`. Never introduce per-page theme keys.

## Analysis Conventions

- Reference point for candle analysis: `close` of the anchor candle
- Scan window: anchor+1 bar through 16:00 ET same day
- Group by DOW: Python `0=Mon…4=Fri`; DuckDB `dow` uses `0=Sun`
- Expired setups are excluded from WR/EV but remain in the trade count

## Per-Folder Notes

See each folder's `CLAUDE.md` for engine-specific details:

- `Fractal Sweep/CLAUDE.md` — sweep+CISD engine, dashboard, Pine scripts, supporting tooling, tests
- `Amas Models/CLAUDE.md` — H1 continuation backtests
- `NPG Sweep/CLAUDE.md` — NPG sweep model
- `TTrades Fractal Model Analysis/README.md` — T-Spot touch engine
- `Analysis/hourly-analysis.md` — Hourly Analysis (quarter theory + breakout studies)
- Rules files under `.claude/rules/` scope automatically by path
