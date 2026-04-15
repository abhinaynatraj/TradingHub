# Fractal Sweep — Legacy

Originally a frozen copy of the **pre-TTrades** Sweep+CISD model, extracted
from git commit `66b7581` (April 11, 2026 — "Revert Fractal Sweep to pre-TTFM
state"). The main `Fractal Sweep/` folder has since moved on to Fixed Constant
and TTFM as its primary models, but this folder continues to evolve the
original sweep+CISD framework as an actively-maintained strategy with its own
risk profiles, equity tracking, win/loss resolution, and R-multiple
calculations.

See the **"Changes since the snapshot"** section at the bottom for what's
been layered on top of the original `66b7581` state.

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

**Known test state** (as of 2026-04-15):
- **188 pass** · 7 fail · 20 skip (was 191/7/20 at the snapshot — 3 F1-specific
  tests were deleted when F1 was removed from the engine)
- The 7 failures are in `tests/test_cisd.py` and `tests/test_detection.py`
  and trace to a `KeyError: 'trade_date'` in fixture construction — they
  were failing at the reference commit `66b7581` and are preserved verbatim.
  They do not affect engine correctness at runtime on real data.

**Engine smoke test** (re-verified 2026-04-15 on 1H_5M after F1 removal):
reads 15 years of NQ 1m bars, runs the full backtest pipeline, and emits
`model_stats.json`. Sample baseline (structural_dynamic, F3+F4 only):
`1H_5M_PREV_CISD — WR=85.5%, EV=+0.831R, PF=6.73, N=985`.

Serve the dashboard:

```bash
cd ..                                           # back to repo root
python3 -m http.server 8001
# Open http://localhost:8001/Fractal%20Sweep%20Legacy/model_dashboard.html
```

## Why this exists

The main `Fractal Sweep/` folder has moved on: the sweep+CISD dashboard was
removed on April 12, 2026, and the Fixed Constant model (doctrine-compliant)
is now the primary view. This folder was originally extracted to preserve the
sweep+CISD engine and dashboard as a frozen reference so the old calculations,
R-multiples, and equity analysis would remain accessible without needing to
`git checkout` an older commit.

The folder has since become the active home for the sweep+CISD strategy. It
runs independently from the main `Fractal Sweep/` folder (which owns the
Fixed Constant and TTFM models) and maintains its own engine, dashboard,
tests, and filter set.

## Changes since the snapshot

The folder is no longer a frozen `66b7581` snapshot. Evolution since extraction:

| Date | Change | Commit |
|---|---|---|
| 2026-04-12 | Doctrine validation pass (regime classification, fade engine fields on base rows, custom range walk-forward improvements) | `e07d0f2` |
| 2026-04-13 | SMT divergence support (ES Q1 check, `smt` bool per trade, SMT-aware summary) | (in `e07d0f2`) |
| 2026-04-14 | Prior Counter-Close + Prior Engulfing filters added | `36279e6` |
| 2026-04-14 | F1/F3/F4 made individually runtime-toggleable | `c42f44f` |
| 2026-04-14 | Secondary panels (Compare, Verdict, Custom Ranges, MAE/MFE study) now honor all filter toggles, not just SMT | `f2947f1` |
| 2026-04-14 | F3/F4 toggles work on every Period sub-slice (not just All Time) + plain-English filter labels (Shallow Sweep, Closed Back Inside, NQ-ES Divergence, Hour Open Aligned, Prior Bar Counters, Prior Bar Engulfs) | `80b1cc8` |
| 2026-04-14 | Live `±N` trade-count badges on each filter chip | `61a6cbd` |
| 2026-04-14 | F1 toggle moved out of runtime UI, kept as baked-in baseline | `6ad66e6` |
| 2026-04-15 | **F1 removed entirely from the engine, JSON schema, and tests.** `min_range` parameter deleted from all 4 model configs. WR and EV improved across every timeframe (1H_5M 84.8% → 85.5%, 4H_15M 86.1% → 88.5%) because F1 was rejecting above-average trades. | `62eda17` |
| 2026-04-15 | Filter chips moved to a dedicated bar below the dropdowns for cleaner alignment | `ea00915` |
| 2026-04-15 | Demo-data badge / banner no longer flash during refresh | `d7a82d8` |

## Current runtime filter set (2⁶ = 64 combinations)

**Setup Quality** (default ON): Shallow Sweep, Closed Back Inside
**Add Confirmation** (default OFF): NQ-ES Divergence, Hour Open Aligned, Prior Bar Counters, Prior Bar Engulfs

Each chip in the dashboard renders a live `±N` delta so users can see how many trades each filter is actually gating before toggling.

## Relationship to main `Fractal Sweep/`

- **Separate engines.** The main folder's `model_stats.py` (original sweep+CISD) still has F1 intact and is not touched by Legacy changes.
- **Shared database.** `candle_science.duckdb` lives in `../Fractal Sweep/` and is symlinked from this folder. Both folders read it read-only.
- **Separate JSON.** `Fractal Sweep/model_stats.json` is committed (smaller, from the original engine). `Fractal Sweep Legacy/model_stats.json` is **gitignored** — treat it as a build artifact and regenerate locally.
- **No cross-merging.** Changes in this folder do not flow back to `Fractal Sweep/` and vice versa unless explicitly ported.
