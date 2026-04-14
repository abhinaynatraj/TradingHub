# Fractal Sweep — Legacy Snapshot

Self-contained copy of the original **pre-TTrades** Sweep+CISD model, extracted
from git commit `66b7581` (April 11, 2026 — "Revert Fractal Sweep to pre-TTFM
state"). This is the original sweep+CISD framework with risk profiles, equity
tracking, win/loss resolution, and R-multiple calculations — as it existed
before the TTrades Fractal Model, the Fixed Constant model, or any doctrine
rewrites.

## Scope

- `model_stats.py` — the original sweep+CISD engine (4 timeframe pairs:
  `4H_15M`, `1H_5M`, `1H_3M`, `30M_3M`)
- `model_dashboard.html` — original dashboard with win/loss, equity curve,
  blown/safe status, MCL/MCW, profile selector, risk profiles, R-multiples,
  and all outcome-derived metrics
- `daily_update.py`, `master_backtester.py`, `recalc.py`, `sltp_analyzer.py` —
  supporting Python tooling as it existed at that commit
- `tests/` — the full pytest suite that covers the sweep+CISD engine
- `CLAUDE.md`, `PIPELINE.md`, `README.md` — documentation at that commit

## Running

The engine expects `candle_science.duckdb` to live inside this folder. The
database is gitignored (~550 MB) and is shared with the main `Fractal Sweep/`
working directory, so this folder uses a symlink:

```bash
cd "Fractal Sweep Legacy"
ln -sf "../Fractal Sweep/candle_science.duckdb" candle_science.duckdb
```

(The symlink is untracked — if you clone fresh, recreate it.)

Commands from inside this folder:

```bash
python3 model_stats.py                          # all 4 sweep models
python3 model_stats.py --models 1H_5M 1H_3M    # specific models only
python3 -m pytest tests/ -q                     # run the legacy test suite
```

**Known test state** (as extracted from commit `66b7581`):
- 191 tests pass · 7 fail · 20 skip
- The 7 failures are in `tests/test_cisd.py` and `tests/test_detection.py`
  and trace to a `KeyError: 'trade_date'` in fixture construction — they
  were failing at the reference commit and are preserved verbatim. They do
  not affect engine correctness at runtime on real data.

**Engine smoke test** (verified 2026-04-13 on 1H_5M): reads 15 years of NQ
1m bars, classifies days, runs the 5-phase backtest pipeline, and emits
`model_stats.json`. Sample output: `1H_5M_PREV_CISD — WR=84.8%, EV=+0.811R,
PF=6.341, N=863`.

Serve the dashboard:

```bash
cd ..                                           # back to repo root
python3 -m http.server 8001
# Open http://localhost:8001/Fractal%20Sweep%20Legacy/model_dashboard.html
```

## Why this exists

The main `Fractal Sweep/` folder has moved on: the sweep+CISD dashboard was
removed on April 12, 2026, and the Fixed Constant model (doctrine-compliant)
is now the primary view. This legacy folder preserves the original sweep+CISD
engine and dashboard as a frozen reference so the old calculations,
R-multiples, and equity analysis remain accessible without needing to
`git checkout` an older commit.

No work in this folder should be merged back into the main `Fractal Sweep/`
flow. Treat it as a read-only historical snapshot.
