# Nested FVG Backtest — Design

**Date:** 2026-06-01
**Status:** ✅ Implemented & validated — see verdict below.
**Source indicator:** `Kelli/nested-fvg.pine`
**Branch:** `feat/nested-fvg-backtest`

> **⚠️ OUTCOME (2026-06-05): the model has NO tradeable edge.** A look-ahead bias was
> found and fixed during validation (resampled FVGs were timestamped at bar-open, not
> bar-close, so entries used future data). De-biased, all three pairings are confidently
> negative (EV ≈ −0.10R, PF ≈ 0.80, 95% bootstrap CIs entirely below zero). One slice
> (ASIA+LONG, 1m_5m) is a forward-test hypothesis, not a validated edge. Full analysis:
> [`2026-06-05-nested-fvg-validation-verdict.md`](2026-06-05-nested-fvg-validation-verdict.md).
> This design doc describes the model **as originally specified**; read the verdict for what's true.

## Goal

Backtest the Nested FVG Pine indicator to measure how it performs, mirroring the
study/data/navigation feel of the existing models. The indicator's thesis: a
1-minute Fair Value Gap (FVG) is a high-quality signal only when it forms *nested
inside* a same-direction higher-timeframe FVG, during an overnight futures session,
with a fixed point-based stop/target.

## Architecture

**Parquet-native / DuckDB-WASM** (the NPG Sweep / Hourly Analysis pattern), NOT the
Fractal Sweep server + slim-JSON + `/trades` pattern. No `server.py` changes. The
engine writes per-pairing parquet files plus a small `manifest.json`; the dashboard
loads parquets directly via `window.loadParquet` and does all aggregation in-browser
via SQL. Dashboard look/navigation is modeled on Fractal Sweep so it feels consistent.

### Folder layout

```
Statistic.ally/Nested FVG/
├── dashboard.html              single-file dashboard (DuckDB-WASM in browser)
├── CLAUDE.md                   engine + dashboard notes, intentional divergences from Pine
├── data/
│   ├── manifest.json           SLIM: aggregates + metadata only, no trade rows
│   ├── trades_1m_5m.parquet    one parquet per TF pair (NQ + ES rows, instrument column)
│   ├── trades_3m_15m.parquet
│   └── trades_5m_30m.parquet
├── engine/
│   ├── build_stats.py          main: load DB → detect → simulate → write parquet+manifest
│   ├── detect.py               FVG detection + nesting + mitigation (pure, unit-testable)
│   ├── simulate.py             entry-fill, 50% scale-out, expiry resolution (pure)
│   └── parquet_writer.py       schema definition + writer (mirrors NPG parquet_writer.py)
└── tests/
    ├── test_detect.py
    ├── test_simulate.py
    └── test_smoke.py
```

### Data flow

`build_stats.py` reads `nq_1m` + `es_1m` from the shared `candle_science.duckdb`
(read-only; convert `timestamp` → `America/New_York` per repo convention) →
resamples HTF side to 5m/15m/30m → detects nested FVGs per TF pair → simulates trades
(fixed-point exit + 50% scale-out) → writes one parquet per pair + a slim
`manifest.json` → dashboard loads parquets and aggregates in SQL.

`detect.py` and `simulate.py` are pure functions (arrays in, trade-rows out), testable
without a DB or browser — isolating the bug-prone logic (gap geometry, scale-out P&L).

## Locked decisions

| Decision | Choice |
|---|---|
| TF nesting pairs | 1m-in-5m, 3m-in-15m, 5m-in-30m |
| Instruments | NQ + ES (both; enables SMT NQ-ES divergence filter) |
| Exit model | Fixed points (Pine): 15 stop / 45 target / 15 partial / 60 extended |
| Entry fill | Open of the **next** bar after the nested FVG forms |
| Partial | Real 50% scale-out at +15pt, runner to +45 target or stop (blended P&L) |
| Session | Full Globex **18:00 ET → 16:00 ET**, signals only in-session |
| Expiry | Force-close flat at 16:00 ET; expired excluded from WR/EV, kept in count |
| Mitigation | HTF FVG dies on close-through far edge (no nesting vs filled gaps) |
| JSON | SLIM aggregates/manifest only — all trade rows in parquet |
| P&L units | points **and** R (pnl/15) **and** dollars (MNQ $2/pt) |

## Engine semantics

### FVG detection (per the Pine geometry)
- Bullish FVG (BISI): `low[i] > high[i-2]` → gap `[high[i-2], low[i]]`, formed at bar `i`.
- Bearish FVG (SIBI): `high[i] < low[i-2]` → gap `[high[i], low[i-2]]`.
- Min-size filter (Pine default 0.15 bp): `gap ≥ price × bp/10000`.

### HTF mitigation
An HTF gap is removed once an HTF bar *closes through its far edge* (bull dies on
`close < bottom`; bear on `close > top`). Tracked chronologically so a nested signal
fires only against a still-live HTF gap.

### Nesting check
When an LTF FVG forms, scan live same-direction HTF gaps; nested if the LTF gap fits
within the HTF gap ± proximity (Pine `proximity_bp`, default 5 bp):
`ltf_bot ≥ htf_bot − prox AND ltf_top ≤ htf_top + prox`. First match wins. A
per-direction cooldown (Pine default 30 bars) suppresses clustered repeats; suppressed
events are counted in the manifest but **not** written as trade rows.

### Simulation (fixed-point, 50% scale-out)
- Entry = open of the next bar after the nested LTF FVG forms.
- Bull levels (bear mirrored): entry `E`, stop `E−15`, partial `E+15`, target `E+45`.
  Extended `+60` logged as an MFE-reach flag, not a separate exit.
- Walk 1m bars forward; **stop checked before target on the same bar** (conservative tie).
  On +15 touch → realize 50%, runner continues; runner exits at +45 (win) or stop.
- Expiry: if unresolved by 16:00 ET, force-close runner at that close → `expired`.

### Outcome taxonomy
- `win` — runner hit +45. Blended (pure target) = +30 pts, R = +2.0.
- `loss` — stopped before partial = −15 pts, R = −1.0.
- `scratch` — partial banked then runner stopped = 0 pts (BE), `partial_hit=true`.
- `expired` — timed out at 16:00 ET; excluded from WR/EV, kept in trade count.
- Win-rate = `win / (win + loss + scratch)`.

### SMT
NQ-ES divergence computed per trade at signal time, stored as a boolean column for
dashboard filtering.

## Parquet schema (one row per trade)

`instrument` (NQ/ES), `direction` (LONG/SHORT), `entry_ts_ns` (int64, NY),
`date` (YYYY-MM-DD), `yr`, `dow` (DuckDB 0=Sun), `hour` (0–23 ET), `minute`,
`session` (ASIA/LONDON/NY/OTHER), `entry_price`, `stop_price`, `partial_price`,
`target_price`, `htf_top`, `htf_bot`, `ltf_top`, `ltf_bot`, `gap_ltf_pts`,
`gap_htf_pts`, `outcome`, `partial_hit` (bool), `reached_ext` (bool), `pnl_pts`,
`r`, `pnl_usd`, `mae_pts`, `mfe_pts`, `bars_held`, `smt` (bool).

Canonical column names, no server-side aliasing (β-bridge convention).

## Slim manifest

```json
{
  "schema_version": 1,
  "run_timestamp_utc": "...",
  "date_range_start": "...", "date_range_end": "...",
  "instrument_pricing": "NQ price action, MNQ sized ($2/pt)",
  "constants": { "STOP_PTS":15,"PARTIAL_PTS":15,"TARGET_PTS":45,"EXT_PTS":60,
                 "MIN_FVG_BP":0.15,"PROXIMITY_BP":5,"COOLDOWN_BARS":30,
                 "SESSION":"18:00→16:00 ET","POINT_VALUE_USD":2.0 },
  "pairings": {
    "1m_5m": { "file":"trades_1m_5m.parquet","n_trades":0,"n_suppressed_cooldown":0,
               "agg": { "n":0,"wr":0.0,"ev_r":0.0,"pf":0.0,"avg_pnl_usd":0.0,
                        "wins":0,"losses":0,"scratches":0,"expired":0 } },
    "3m_15m": { "...": "..." }, "5m_30m": { "...": "..." }
  }
}
```

Manifest stays a few KB; dashboard reads it for headline tiles + file discovery, then
does all slicing in SQL.

## Dashboard

Single-file `dashboard.html`, reusing `Analysis/dashboard/shared.js` (`window.loadParquet`,
`window.query`) and the shared `localStorage['hub-theme']` (dark/light/gold/indigo).

State: `{ pairing, instrument, direction, session, smt, period, tab }`. Controls rebuild
a SQL WHERE and re-render. Period anchored to `MAX(date)` (all/2y/1y/6m/3m/1m) like
Fractal Sweep.

### Tabs (5)
1. **Overview** — hero tiles (N, WR, EV-R, PF, avg $/trade), outcome split, 3 pairings
   side-by-side, **and the SMT × session × direction filter-impact grid** (folded in).
2. **Edge** — by-hour, by-DOW, by-session; EV heatmap (hour×DOW); top/bottom by EV;
   direction asymmetry.
3. **Risk** — equity curve (cumulative R by `entry_ts_ns`), max drawdown, PF, streaks.
4. **Excursion** — MAE/MFE distributions (pts); +15/+45/+60 reach rates; heat-before-win.
5. **Trades** — paginated table (date, time, instr, dir, entry, stop, target, outcome,
   R, $), recent-first, active filters applied.

Charts: lightweight (SVG polyline equity/drawdown, CSS-grid heatmap, HTML/CSS bars).

### Hub registration
Add a `PROJECTS` entry + `loadStats()` block in `index.html` (icon ◎, color `#06b6d4`,
links `Nested FVG/dashboard.html`, reads `Nested FVG/data/manifest.json`). **Ask before
editing `index.html`** (shared hub). Do not touch `.claude/rules/*` (user maintains by hand).

## Testing & validation

**Pure-unit (no DB/browser):**
- `test_detect.py` — FVG geometry (bull/bear), min-size bp boundary, nesting containment
  (accept inside ± proximity, reject near-miss), same-direction-only, HTF mitigation
  (dies on close-through, survives wick-through).
- `test_simulate.py` — pure target → +30 pts / R +2.0 / win; pure stop → −15 / R −1 / loss;
  partial-then-runner-stop → 0 / scratch / partial_hit; same-bar stop+target tie → stop;
  entry = next-bar open (off-by-one guard); expiry at 16:00 ET → expired, excluded from WR;
  dollar ($2/pt) and R conversions.
- `test_smoke.py` — end-to-end on ~1-month slice: exact schema columns, no NaNs in
  required fields, manifest `agg.n` == parquet row count, recomputed WR == manifest WR.

**Pine cross-check:** on a handful of dates, confirm engine nested-FVG signals
(timestamp + direction + entry level) line up with the indicator's marks. Document
intentional divergences (next-bar-open entry, 50% scale-out, NY session, 16:00 expiry)
in `CLAUDE.md`.

**Sanity gates in build_stats.py:** session window non-empty; no trades outside
18:00→16:00; every `outcome` ∈ {win,loss,scratch,expired}; warn on suspiciously-few
trades per pairing.

## Overlap with existing models (context)

- **NPG Sweep** — highest *conceptual* overlap (multi-TF sweep-born gaps, futures,
  overnight-ish). Differs: ratio targets, no fixed-pt stop, FVG implicit in projections.
- **Fractal Sweep** — highest *mechanical* overlap (multi-TF, NQ/ES, fixed R, same DB).
  Differs: CISD (momentum) is the trigger, not FVG geometry; no session gate.
- **Amas H1 Continuation** — multi-TF, futures, 1R fixed; "continuation after close" logic;
  Inversion-FVG entry tested and dropped (19% vs 68% draw-hit on OB).
- **T-Spot Touch** — sweep→retouch, but zone = candle body, any same-day touch, 2.0R.
- **Hourly Analysis** — descriptive breakout study, orthogonal.

**Caution flag (not a blocker):** bare FVGs already tested non-additive in Fractal Sweep
(redundant with SMT) and dropped in Amas v1. Nested FVG's novelty is the *nesting
geometry* + overnight session gate + fixed-pt R/R — none isolated by those tests. This
backtest is the right way to find out whether that specificity earns its keep.
```
