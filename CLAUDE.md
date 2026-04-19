# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Repo Layout

```
Statistic.ally/
├── index.html                         Hub page (links Fractal Sweep Fixed Constant)
├── Fractal Sweep/                     Fixed Constant · TTFM · original sweep+CISD
├── Fractal Sweep Legacy/              Evolved sweep+CISD strategy (F1 removed, 6 runtime filters)
├── TTrades Fractal Model Analysis/    T-Spot touch strategy
├── docs/superpowers/specs/            Design docs (reference only)
├── candle_science.duckdb              Shared DB (gitignored)
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
- `Fractal Sweep Legacy/candle_science.duckdb` is a symlink to the same file
- Tables: `nq_1m`, `es_1m`
- Schema: `timestamp TIMESTAMPTZ, open, high, low, close DOUBLE, volume BIGINT`
- Timestamps stored as `America/Toronto` — **always convert**: `timezone('America/New_York', timestamp)`
- All engines connect read-only via `Path(__file__).parent.parent / 'Fractal Sweep' / 'candle_science.duckdb'` (or `Path(__file__).parent / …` for scripts living inside `Fractal Sweep/` itself)

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

- `Fractal Sweep/CLAUDE.md` — primary workspace; hosts 3 engines (Fixed Constant doctrine, TTFM, original sweep+CISD)
- `Fractal Sweep Legacy/CLAUDE.md` — actively-evolved sweep+CISD strategy, separate from the main folder
- Rules files under `.claude/rules/` scope automatically by path
