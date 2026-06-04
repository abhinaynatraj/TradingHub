# Nested FVG

Backtest for the `Kelli/nested-fvg.pine` indicator: a 1-min FVG nested inside a
same-direction higher-timeframe FVG, during the Globex session, with fixed-point
risk. Reads the shared `../Fractal Sweep/candle_science.duckdb` (read-only).
Parquet-native / DuckDB-WASM (no server endpoints).

## Stack
Python 3.14 · DuckDB · numpy · pyarrow · pandas · pytest. Browser: DuckDB-WASM
1.29.0 via `../Analysis/dashboard/shared.js`.

## Run
```bash
python3 engine/build_stats.py                 # all 3 pairings, NQ + ES, SMT on
python3 engine/build_stats.py --pairings 1m_5m --no-smt
python3 -m pytest tests/ -q                    # unit suite (smoke test hits the real DB, ~5min)
```
Dashboard: serve repo root (`python3 server.py` or `python3 -m http.server 8001`)
and open `Nested FVG/dashboard.html`.

## TF pairs
`1m_5m`, `3m_15m`, `5m_30m` (LTF gap nested in HTF gap).

## Pipeline (engine/)
- `constants.py` — Pine-default thresholds, session window, pairings.
- `detect.py` — pure FVG geometry: `find_fvgs`, `is_mitigated`, `is_nested`.
- `simulate.py` — pure trade sim: fixed-point exit + 50% scale-out, expiry.
- `parquet_writer.py` — 30-col canonical trade schema (read directly by the dashboard).
- `build_stats.py` — orchestrator: load DB → detect → simulate → parquet + slim manifest.

### Performance note
The nesting search is a **sweep-line** (`_find_nested_hosts`), not a brute-force
cross-product — a full pairing is ~2 min instead of hours over 4M+ bars.
`tests/test_nesting_sweep.py` locks the sweep to a brute-force reference; do not
"simplify" it back to the quadratic form.

## Intentional divergences from the Pine (backtest != raw indicator)
- Entry = OPEN of the next bar after the nested FVG forms (Pine assumes immediate
  fill at the gap edge).
- Partial is a REAL 50% scale-out at +15pt; runner to +45 or stop. (Pine flags a
  partial but keeps full size.) Blended points P&L: pure target=+30 (R=+2), pure
  stop=-15 (R=-1), partial-then-stop=0 (scratch), partial-then-expiry=+7.5.
- Session recast to NY: full Globex 18:00->16:00 ET. Signals whose entry bar lands
  at/after 16:00 ET are skipped. Expiry force-closes the runner flat at 16:00 ET.
- Outcomes: win/loss/scratch/expired. WR = win/(win+loss+scratch); expired excluded
  from WR **and EV** (the +7.5 partial-expiry P&L must not leak into EV — dashboard
  SQL and engine `_agg` both filter `outcome != 'expired'` for EV/PF).
- HTF mitigation: gap dies on close-through far edge (matches Pine).
- SMT is a crude NQ-ES 2-bar divergence proxy (flagged in `_smt_at`); sharpen later
  without schema change.

## Outputs
`data/trades_<pair>.parquet` (gitignored) + `data/manifest.json` (committed, slim
aggregates only). Spec: `../docs/superpowers/specs/2026-06-01-nested-fvg-backtest-design.md`.
Plan: `../docs/superpowers/plans/2026-06-01-nested-fvg-backtest.md`.

## Baseline result (unfiltered, NQ)
The raw model (no session/SMT/direction filter) is a **losing edge** on 1m_5m
(WR ~23%, EV ~-0.065R) — consistent with FVGs testing non-additive in Fractal Sweep
and Amas. The dashboard exists to find whether any slice (pairing/session/SMT/
direction) is positive. Treat unfiltered aggregate as a baseline, not a verdict.
```
