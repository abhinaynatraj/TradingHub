# NPG Sweep

Statistical engine for the npg "Sweep · CISD · FVG · Key Levels" indicator's setup model. Phase 1: detection + outcomes + JSON output. Reads from shared `../Fractal Sweep/candle_science.duckdb` (read-only).

## Stack
- Python 3.14 · DuckDB 1.4.4 · pandas
- Engine output: `npg_stats.json` (gitignored)

## Run
```bash
python3 engine/npg_stats.py                          # all 3 pairings, both profiles
python3 engine/npg_stats.py --pairings 1H_5M         # subset
python3 engine/npg_stats.py --table es_1m            # ES instead of NQ
python3 -m pytest tests/ -q                          # test suite
```

## Model spec
Source of truth: `../Fractal Sweep/pine/sweep_cisd_mtf_fvg.pine` (npg's Pine source).
- Wick Lick: HTF candle sweeps prior HTF extreme, closes back inside
- CISD: opposing-candle series before sweep, broken by opposing close (max 20 bars, body-confirmed by default)
- Projections: 0.5/1.0/1.5/2.0× of opposing-series range from break price
- Silver: late-week timing filter (Fri OR Thu ≥ 1pm ET) with aggressive close
- Anchor lockout: one setup per HTF candle, must complete in same HTF window

## Differences from Fractal Sweep engine
- CISD is series-based (npg) vs single-bar engulf (Fractal Sweep)
- Targets are series-range multiples (npg) vs 1R (Fractal Sweep)
- Silver filter has no analog in Fractal Sweep
- Otherwise: same DB, same risk constants, same anchor-window semantics, same SMT
