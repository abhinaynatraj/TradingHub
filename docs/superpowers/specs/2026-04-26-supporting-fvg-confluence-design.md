# Supporting FVG Confluence — Design

**Date:** 2026-04-26
**Project:** Fractal Sweep
**Status:** Design (engine-only first; dashboard exposure deferred)

---

## Motivation

Fractal Sweep currently sits at ~50–55% WR baseline on `simple_1r`, with the
strongest known edge coming from the SMT (NQ-ES Divergence) filter (+7.8% WR,
+0.150R EV). We want to test whether requiring a **supporting LTF FVG behind
entry** adds edge — the intuition being that a sweep which prints a clean
displacement-driven FVG on the way back into range gives the CISD a piece of
structure to lean on, while a sweep with no such gap is "thinner."

Original sketch: *"H1 low sweep into 15 / 5 min BISI + CISD."*

This is a hypothesis, not a known edge. The point of this spec is to compute
the flags cheaply, look at the numbers, and then decide what to expose.

## Non-goals

- No dashboard chip wiring in this iteration. Engine + JSON output only.
- No Pine indicator changes.
- No removal or modification of F3, F4, or SMT.
- No continuous distance-to-FVG feature (`dist_to_fvg_top` etc.). Binary flags
  only. We can layer continuous features on later if there's edge to refine.
- No cross-anchor FVGs. The "everything happens within one anchor HTF window"
  invariant aligned in 2026-04-24 is preserved.

## Definitions

### Supporting FVG (geometry C from brainstorm)

A **supporting FVG** for a trade is an unfilled same-side LTF FVG that the
trade can fall back into before stop. We compute two geometric tightness
levels per timeframe:

- **Strict** — FVG body fully between the sweep extreme (SL level) and the
  entry price. Trade literally has a gap to fall into before stop.
- **Loose** — FVG top below entry (for longs; mirror for shorts), anywhere in
  the anchor HTF window. Includes strict as a subset.

For a LONG trade (sweep of prior HTF low):

- Bullish FVG at LTF index `i`: `low[i] > high[i-2]`
- Strict requires: `sweep_extreme ≤ high[i-2]` AND `low[i] ≤ entry_price`
  (entire body inside the SL→entry band)
- Loose requires: `low[i] ≤ entry_price` (top of gap below entry)

SHORT trade is the mirror: bearish FVG `high[i] < low[i-2]`, geometry inverted.

### "Unfilled at entry"

An FVG is unfilled at entry if **no candle between FVG formation (bar `i`) and
entry has wicked into the gap.** For a bullish FVG with body `[high[i-2], low[i]]`:
unfilled iff for all bars `j` in `(i, entry_idx)`, `low[j] > high[i-2]` (no
LTF wick has dipped into the upper edge of the gap). Mirror for bearish.

We track this once per FVG by scanning forward from formation and breaking on
first fill. Trades that occur after fill see the FVG as filled.

### Two timeframes scanned

- **CISD-TF FVGs** — 5M for `1H_5M`, 3M for `30M_3M`. Already resampled in
  the engine.
- **1M FVGs** — raw 1-minute bars from `m1_arrs`. Already loaded.

Both scans are restricted to the **current anchor HTF window** (sweep_anchor
window), consistent with the rest of the engine.

## Trade Row Fields (added)

Four new boolean fields per trade row:

| Field | TF | Geometry |
|---|---|---|
| `passes_fvg_cisd_strict` | CISD-TF | Body fully between sweep extreme and entry |
| `passes_fvg_cisd_loose`  | CISD-TF | Top below entry |
| `passes_fvg_1m_strict`   | 1M | Body fully between sweep extreme and entry |
| `passes_fvg_1m_loose`    | 1M | Top below entry |

Invariant: `strict ⇒ loose` per TF. Asserted in tests and at engine boundary.

The CISD-TF and 1M flags are independent — a trade can have a 1M FVG without
a CISD-TF FVG and vice versa.

## Aggregation Output

A new `fvg_summary` block in `build_model_stats` output (one per model ×
profile, alongside `smt_summary`). Structured the same way `smt_summary` is —
each leaf runs through the existing `agg()` and produces
`{n, wins, wr, ev, pf, avg_risk_pts, avg_rr, avg_mae, avg_mfe, avg_mae_hr, avg_mfe_hr}`:

```
fvg_summary: {
  cisd_strict, cisd_loose, no_cisd_fvg,
  m1_strict,   m1_loose,   no_m1_fvg,
  any_strict,  any_loose,                          # OR across both TFs
  cisd_strict_smt, m1_strict_smt, any_strict_smt   # confluence with SMT
}
```

`any_strict` = `passes_fvg_cisd_strict OR passes_fvg_1m_strict`. Same for
loose. `any_strict_smt` is `any_strict AND smt`. The SMT-confluence keys exist
because SMT is the strongest existing filter; the marginal edge of FVG over
SMT-alone is the real test.

## Implementation Surface

All changes confined to `engine/model_stats.py` and `tests/`.

### `engine/model_stats.py`

1. New helper near `find_cisd`:
   ```python
   def find_supporting_fvg(
       arrs,                       # dict of OHLC numpy arrays (high, low, ...)
       window_start_idx, entry_idx,
       sweep_extreme, entry_price, direction,
   ) -> tuple[bool, bool]:         # (strict, loose)
   ```
   Scans `[window_start_idx + 2, entry_idx)` for 3-bar FVGs of correct
   polarity, verifies unfilled-at-entry, returns the two booleans. Returns
   early on the first strict hit. Correctness over speed for v1.

2. Inside `detect_setups_base`, for each setup that reaches the entry phase,
   call `find_supporting_fvg` twice — once on `c_arrs` (CISD-TF) and once on
   `m1_arrs` (1M) — and write the four resulting flags onto the row.

3. Inside `build_model_stats`, after `smt_summary` is built, build
   `fvg_summary` using the same helpers (`agg`, group masks).

4. JSON output adds `fvg_summary` per model × profile.

### `tests/`

Unit tests for `find_supporting_fvg` covering:

- Bullish FVG strictly between SL and entry → strict True, loose True
- Bullish FVG below entry but extending below SL → strict False, loose True
- Bullish FVG above entry → strict False, loose False
- Bullish FVG that gets wicked into before entry → strict False, loose False
- Wrong-side (bearish FVG on a long trade) → both False
- No 3-bar gap in window → both False
- Mirror cases for SHORT trades

Engine-boundary invariant test: for the full backtest output,
`passes_fvg_*_strict ⇒ passes_fvg_*_loose` element-wise per TF.

Existing tests continue to pass unchanged — adding flags doesn't move
`outcome`, `r`, or any of the existing aggregates.

## Decision Criterion (after first run)

Promote a flag to a dashboard chip in a follow-up iteration if **either**:

1. **Standalone edge** — WR delta ≥ +3% over the ~50% baseline AND N ≥ 500
   over 12y on at least one model, OR
2. **Stacks with SMT** — `*_smt` block shows ≥ +1% WR over `smt`-alone with
   N ≥ 200 over 12y on at least one model.

Lower bars than F3 (which sat at +3.4%) are not interesting in isolation.

If neither geometry nor TF clears the bar on either model, we leave the flags
in the trade rows for future reference (they're cheap) but skip the dashboard
work.

## Risks & Open Questions

- **Sparsity, especially on `30M_3M` strict.** Strict requires the gap to fit
  inside the SL→entry band, which is bounded by `MIN_RISK_PTS = 3.0`. On 3M
  CISD-TF this may be very rare. Loose is the fallback if strict has N < 200.
- **Sample bias from the unfilled requirement.** A sweep that retraces deeply
  before CISD will have wicked through any nearby FVG, killing the flag. This
  is by design (the gap really does need to be there at entry) but it means
  FVG presence is correlated with momentum sweeps, not deep retracements.
  Worth keeping in mind when reading numbers.
- **Correlation with SMT.** A clean SMT divergence often comes from
  displacement, which often produces an FVG. The marginal edge over SMT-alone
  (`*_smt` blocks) is the real test, not the standalone number.
- **1M noise floor.** 1M FVGs are common, including from low-volume one-tick
  imbalances. Loose 1M may be near-100% prevalence and provide no
  discrimination. We expect strict 1M to be the more interesting cell.

## File-by-file Change Summary

| File | Change |
|---|---|
| `engine/model_stats.py` | Add `find_supporting_fvgs` helper; call twice in `detect_setups_base`; add four flag fields to trade rows; add `fvg_summary` block to `build_model_stats`. |
| `tests/test_<new>.py` | Unit tests for `find_supporting_fvg` plus the strict-implies-loose invariant. |
| `model_stats.json` | Auto-regenerated; gains `fvg_summary` block per model × profile. |
| `engine/CLAUDE.md`, `PIPELINE.md`, `.claude/rules/fractal-sweep.md` | Document the four new fields and `fvg_summary` after the engine run lands and we know whether to expose them. |

No changes to:

- `model_dashboard.html` (deferred)
- `pine/` (deferred)
- `daily_update.py` (no schema migration; flags appear automatically on next
  full engine run)
- `engine/sltp_analyzer.py`, `master_backtester.py`, `recalc.py` (no
  consumption of the new fields yet)

## Out of Scope (explicit)

- Dashboard chip wiring
- Pine indicator FVG drawing
- Continuous `dist_to_fvg_top` / `fvg_size_r` features
- Cross-anchor FVGs
- Combining FVG with F3/F4 in the SMT-confluence aggregates (we only test
  against SMT-alone; F3/F4 confluence is a follow-up if FVG clears the
  decision criterion)

## Results (2026-04-26)

Engine ran end-to-end on the full 12y NQ dataset after Tasks 1–10 landed.
Baseline `simple_1r` WR: 49.7% on `1H_5M`, 49.2% on `30M_3M`. SMT-only WR:
57.5% on `1H_5M` (n=2,452), 56.9% on `30M_3M` (n=4,382).

### `1H_5M` `fvg_summary` (simple_1r)

| Cell | n | WR | EV | Δ baseline WR | Δ SMT-only WR |
|---|---:|---:|---:|---:|---:|
| `cisd_strict` | 4,087 | 0.502 | +0.005 | +0.5% | — |
| `cisd_loose` | 4,087 | 0.502 | +0.005 | +0.5% | — |
| `no_cisd_fvg` | 8,126 | 0.494 | −0.012 | −0.3% | — |
| `m1_strict` | 11,197 | 0.502 | +0.004 | +0.5% | — |
| `m1_loose` | 11,197 | 0.502 | +0.004 | +0.5% | — |
| `no_m1_fvg` | 1,016 | 0.440 | −0.120 | −5.7% | — |
| `any_strict` | 11,266 | 0.503 | +0.005 | +0.6% | — |
| `any_loose` | 11,266 | 0.503 | +0.005 | +0.6% | — |
| `cisd_strict_smt` | 751 | 0.554 | +0.108 | +5.7% | **−2.1%** |
| `m1_strict_smt` | 2,251 | 0.576 | +0.152 | +7.9% | **+0.1%** |
| `any_strict_smt` | 2,271 | 0.576 | +0.153 | +8.0% | **+0.1%** |

### `30M_3M` `fvg_summary` (simple_1r)

| Cell | n | WR | EV | Δ baseline WR | Δ SMT-only WR |
|---|---:|---:|---:|---:|---:|
| `cisd_strict` | 6,407 | 0.503 | +0.007 | +1.1% | — |
| `cisd_loose` | 6,407 | 0.503 | +0.007 | +1.1% | — |
| `no_cisd_fvg` | 14,071 | 0.487 | −0.026 | −0.5% | — |
| `m1_strict` | 17,026 | 0.494 | −0.011 | +0.2% | — |
| `m1_loose` | 17,026 | 0.494 | −0.011 | +0.2% | — |
| `no_m1_fvg` | 3,452 | 0.481 | −0.039 | −1.1% | — |
| `any_strict` | 17,207 | 0.495 | −0.011 | +0.3% | — |
| `any_loose` | 17,207 | 0.495 | −0.011 | +0.3% | — |
| `cisd_strict_smt` | 1,206 | 0.542 | +0.085 | +5.0% | **−2.7%** |
| `m1_strict_smt` | 3,621 | 0.563 | +0.126 | +7.1% | **−0.7%** |
| `any_strict_smt` | 3,659 | 0.563 | +0.125 | +7.1% | **−0.7%** |

### Verdict per decision criterion

- Standalone edge ≥ +3% with N ≥ 500: **no cell qualifies on either model.** Best
  standalone is `30M_3M.cisd_strict` at +1.1%.
- Stacks with SMT ≥ +1% over SMT-alone with N ≥ 200: **no cell qualifies.**
  Best confluence is `1H_5M.any_strict_smt` at +0.1% — flat. `30M_3M`'s
  confluences are all slightly negative vs SMT-alone.

**No cell promotes.** The four flag fields stay on trade rows for future
reference (cheap to keep), but no dashboard chip is added and no Pine
indicator change ships.

### What we learned

1. **Strict ≡ loose at scale.** Every cell shows identical `n` between
   strict and loose. The `bottom ≥ sweep_extreme` constraint is essentially
   always satisfied when an FVG forms above the sweep wick (`high[i-2]` is
   typically well above the lowest sweep low by the time the displacement
   forms). The strict/loose distinction we built doesn't carve out a
   meaningfully different cohort. Future work: if we want a tighter
   "supporting FVG" filter, the discriminator must be something else —
   e.g. distance from FVG to entry, FVG size as a fraction of risk, or
   whether the CISD bar itself creates the FVG.

2. **FVG and SMT are redundant.** `m1_strict_smt` (n=2,251) lands at
   essentially the same WR as `smt`-alone (n=2,452). The 200 setups SMT
   loses by also requiring an FVG don't move WR. SMT alone already
   captures the displacement signal we hoped FVG would refine.

3. **Negative-signal asymmetry is real but unactionable.** `no_m1_fvg`
   on `1H_5M` is 44.0% WR (1,016 of 12,213 setups, 8.3%). Excluding
   FVG-less setups removes 8% of trades for ~0.5% baseline WR lift —
   below the noise floor and economically marginal.

4. **The plan's "promote if standalone ≥ +3%" bar was the right
   gate.** Without it we might have shipped a chip on +1.1% +1,706
   net-trades signal that adds no real edge.
