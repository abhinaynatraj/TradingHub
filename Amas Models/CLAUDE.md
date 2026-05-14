# Amas Models

Backtest engine + dashboard for trading models extracted from the Amas mentorship materials. Same pattern as `Fractal Sweep/`: Python engine writes `model_stats.json`, single-file dashboard reads it.

## Stack
- Python 3.14 · DuckDB 1.4.4 · pandas
- Standalone HTML dashboard, zero CDN deps

## Folder layout

```
Amas Models/
├── model_dashboard.html        single-file dashboard
├── model_stats.json            engine output (gitignored)
├── engine/                     Python backtest code
│   ├── constants.py            single source of truth: MAX_RISK_PTS=20.0, RISK_PER_TRADE_USD=400, point values, OUTCOME_MAX_BARS=1440
│   ├── db.py                   DB load, TZ conversion, data-quality assertions
│   ├── outcomes.py             SL/TP scanner, MAE/MFE, equity tracking
│   ├── filters.py              filter primitives (SMT, etc.)
│   ├── stats.py                agg(), Wilson CI, EV/PF, walk-forward helpers
│   ├── models/                 one Python file per Amas model
│   │   ├── __init__.py         MODELS registry
│   │   └── <model>.py
│   ├── model_stats.py          orchestrator + CLI
│   └── daily_update.py         (Phase 7) hook into Fractal Sweep's cron
├── docs/
│   ├── model_specs.md          formal spec per model — canonical source of truth
│   └── source_index.md         per-source-file summary
├── pine/                       (Phase 6) one .pine per validated model
├── tests/                      pytest suite
├── data/                       cached intermediates (gitignored)
└── assets/                     dashboard images
```

## Running

Engine scripts self-locate. Run from the `Amas Models/` folder:

```bash
python3 engine/model_stats.py                            # all models, NQ
python3 engine/model_stats.py --models <model_key>       # subset
python3 engine/model_stats.py --table es_1m              # ES instead of NQ
python3 -m pytest tests/ -q                              # test suite
```

Dashboard served from the repo root (Statistic.ally/):

```bash
python3 -m http.server 8001
# → http://localhost:8001/Amas Models/model_dashboard.html
```

## Database

Reads `../Fractal Sweep/candle_science.duckdb` (the shared DB). **Read-only from this folder.** Daily updates stay in `Fractal Sweep/engine/daily_update.py`.

Schema: `nq_1m`, `es_1m` — `timestamp TIMESTAMPTZ, open/high/low/close DOUBLE, volume BIGINT`. Stored as `America/Toronto`. **Always convert at the SQL layer:** `SELECT timezone('America/New_York', timestamp) AS ts, ...`.

## Correctness invariants (non-negotiable)

See [`../docs/superpowers/specs/2026-04-26-amas-models-design.md`](../docs/superpowers/specs/2026-04-26-amas-models-design.md) section "Correctness invariants" — 8 categories of silent-edge bug each engine commit must defend against:

A. Timestamp/TZ correctness — `[ns]` resolution, NY tz, duration-based windows
B. Trade deduplication — unique by (model, instrument, anchor_ts, direction)
C. Lookahead/future-leak — causal detection, no cross-anchor lookahead
D. Outcome resolver fidelity — same-bar tie → SL, OUTCOME_MAX_BARS=1440, expired excluded from WR
E. Data quality — gap/dup/monotonic/OHLC/schema assertions on every load
F. Risk arithmetic — single-source constants, NQ vs ES point values, R-in-points-then-converted
G. Statistical hygiene — N visible, Wilson CIs, period-matched comparisons, AND-semantics filter combos
H. Determinism — no randomness, no wall-clock in logic, byte-for-byte JSON reproducibility

These invariants are enforced via runtime assertions (not gated on DEBUG) and pytest tests. Every reported finding gets the edge-inflation checklist before being trusted.
