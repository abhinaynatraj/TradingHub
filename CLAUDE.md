# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Repo Layout

```
Statistic.ally/
├── index.html                         Hub page (links Fractal Sweep)
├── Fractal Sweep/                     Sweep+CISD engine, dashboard, Pine scripts, DB
├── TTrades Fractal Model Analysis/    T-Spot touch strategy
├── docs/superpowers/specs/            Design docs (reference only)
└── .claude/rules/                     Per-folder guidance
```

## Serving

Always serve via HTTP — dashboards use `fetch()` and break on `file://`:

```bash
python3 -m http.server 8001   # from repo root → http://localhost:8001
```

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
- Scripts inside `Fractal Sweep/` connect via `Path(__file__).parent / 'candle_science.duckdb'`; scripts elsewhere use `Path(__file__).parent.parent / 'Fractal Sweep' / 'candle_science.duckdb'`

## Data Updates

Only `Fractal Sweep/daily_update.py` fetches new bars from Databento. Cron installed via `install_cron.sh` runs it 7am ET weekdays. All other engines read from the shared DB read-only.

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
- `TTrades Fractal Model Analysis/README.md` — T-Spot touch engine
- Rules files under `.claude/rules/` scope automatically by path
